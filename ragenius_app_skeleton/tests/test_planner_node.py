import json
import shutil
import sys
import unittest
from pathlib import Path

from jsonschema.exceptions import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.planner_repo import InMemoryPlannerRepo
from workflows.nodes import load_template_registry, planner
from workflows.runtime_models import SessionExecutionState


def load_fixture(name: str):
    path = Path(__file__).resolve().parent / "fixtures" / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def make_state():
    return {
        "session_id": "00000000-0000-0000-0000-000000000123",
        "collection_id": "col1",
        "domain": "general",
        "user_id": "u1",
        "user_query": "What are policy requirements?",
        "chat_history": [],
        "config_json": {},
        "adapter_json": {
            "intent_overrides": [{"alias_intent": "qa", "triggers_from_config": ["question"], "maps_to_base_intent": "qa"}],
            "step_skeleton_mapping": {
                "use_config_step_skeletons": True,
                "default_mode": "default",
                "step_waiting_policy": {"wait_for_user_each_step": False, "max_questions_per_turn": 3},
            },
            "info_type_to_tags": {},
            "retrieval_defaults": {"top_k_range": [1, 5], "language": "en"},
            "plugin_activation_rules_file": None,
            "llm_guardrails_append": [],
        },
        "template_registry": {},
        "instruction_runtime_model": {},
        "session_execution_state": {},
    }



def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f)


def _write_domain_fixture(domains: Path):
    _write_json(domains / "general" / "intent_templates.json", {})
    _write_json(domains / "general" / "step_skeletons.json", {})
    _write_json(domains / "general" / "info_type_rules.json", {})
    _write_json(domains / "general" / "retrieval_mapping_rules.json", {})

class PlannerNodeTests(unittest.TestCase):
    def setUp(self):
        self.valid = load_fixture("planner_output_valid.json")
        self.low_conf = load_fixture("planner_output_low_conf.json")
        self.state = make_state()

    def test_planner_happy_path_with_persistence(self):
        repo = InMemoryPlannerRepo()
        calls = {"n": 0, "prompt": ""}

        def llm(prompt, tools, context):
            calls["n"] += 1
            calls["prompt"] = prompt
            self.assertEqual(tools[0]["name"], "create_planner_output")
            self.assertEqual(context["user_query"], self.state["user_query"])
            return self.valid

        out = planner.run(self.state.copy(), llm_planner=llm, repo=repo)
        self.assertEqual(calls["n"], 1)
        self.assertIn("intent_overrides", calls["prompt"])
        self.assertIn("step_skeleton_mapping", calls["prompt"])
        self.assertEqual(out["planner_output"]["confidence"], 0.85)
        self.assertEqual(out["retrieval_plan"]["query_text"], self.valid["retrievalPlan"]["query_text"])
        self.assertEqual(len(repo._rows), 1)

    def test_planner_normalizes_non_string_system_instruction_summary_items_before_validation(self):
        repo = InMemoryPlannerRepo()

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["systemInstructionSummary"]["fromAdapter"] = [
                {
                    "alias_intent": "qa",
                    "maps_to_base_intent": "qa",
                    "triggers": [
                        "我想透過【主題或經文】幫助人更深認識神的真理，請幫我建立一個能支持這目的的最佳化提示（prompt）。"
                    ],
                }
            ]
            return output

        out = planner.run(self.state.copy(), llm_planner=llm, repo=repo)
        from_adapter = out["planner_output"]["systemInstructionSummary"]["fromAdapter"]
        self.assertEqual(len(from_adapter), 1)
        self.assertIsInstance(from_adapter[0], str)
        self.assertIn("qa", from_adapter[0])
        self.assertIn("triggers:", from_adapter[0])

    def test_planner_builds_hybrid_decision_packet_when_hybrid_runtime_model_is_present(self):
        state = self.state.copy()
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "global_app_contract": {"mission": "Support users", "constraints": ["Stay in scope"]},
                    "interaction_logic_blocks": [
                        {
                            "logic_id": "logic:global",
                            "scope": "global",
                            "rules": [{"expression": "Ask one question at a time"}],
                        }
                    ],
                    "role_profiles": [{"role_id": "role:coach", "name": "Coach"}],
                    "routing_rules": [{"rule_id": "route:1"}],
                    "module_orchestration": {"composition_mode": "ordered_sequential"},
                    "instruction_service_blocks": [
                        {"block_id": "workflow:one", "block_type": "primary_workflow", "title": "Workflow One"}
                    ],
                    "instruction_procedures": [{"procedure_id": "proc:one", "title": "Procedure One"}],
                    "procedure_steps": [{"step_id": "step:1", "title": "Clarify", "execution_mode": "interactive"}],
                    "clarification_gate_rules": [{"gate_rule_id": "gate:1", "minimum_filled_slots": 2}],
                }
            }
        }

        out = planner.run(state, llm_planner=lambda _p, _t, _c: self.valid)
        packet = out["hybrid_planner_decision_packet"]
        self.assertEqual(packet["task"], "turn_intent_and_next_action_inference")
        self.assertEqual(packet["app"]["mission"], "Support users")
        self.assertEqual(packet["candidates"]["roles"][0]["role_id"], "role:coach")
        self.assertEqual(packet["module_orchestration"]["composition_mode"], "ordered_sequential")

    def test_planner_runs_hybrid_shadow_llm_only_when_callable_is_present(self):
        state = self.state.copy()
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "global_app_contract": {},
                    "interaction_logic_blocks": [],
                    "role_profiles": [],
                    "routing_rules": [],
                    "module_orchestration": {},
                    "instruction_service_blocks": [],
                    "instruction_procedures": [],
                    "procedure_steps": [],
                    "clarification_gate_rules": [],
                }
            }
        }
        calls = {"n": 0}

        def hybrid_llm(prompt, tools, context):
            calls["n"] += 1
            self.assertIn("compiled application contract", prompt)
            self.assertEqual(tools[0]["name"], "create_hybrid_planner_decision")
            self.assertIn("decision_packet", context)
            return {
                "intent_label": "qa",
                "confidence": 0.9,
                "continue_current_scope": True,
                "selected_role_id": None,
                "selected_workflow_id": None,
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {"action_type": "stay_idle", "target_service_block_id": None, "target_workflow_id": None, "target_step_id": None, "bundled_step_ids": [], "module_queue": []},
                "reasoning_summary": ["shadow only"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=lambda _p, _t, _c: self.valid)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(out["hybrid_planner_shadow_output"]["intent_label"], "qa")

    def test_planner_prefers_semantic_default_workflow_id_over_legacy_trigger_matching(self):
        state = self.state.copy()
        state["user_query"] = "Please help me with the app"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "default_workflow_id": "workflow:default",
                    "instruction_service_blocks": [
                        {
                            "block_id": "workflow:default",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                            "is_default": True,
                        }
                    ],
                    "instruction_procedures": [],
                    "procedure_steps": [],
                }
            },
            "instruction_workflows": [
                {
                    "id": "workflow:nondefault",
                    "title": "Non Default Workflow",
                    "workflow_name": "Non Default Workflow",
                    "triggers": ["help"],
                    "steps": [{"order": 1, "title": "Non Default Step", "resource_file": "nondefault.md"}],
                },
                {
                    "id": "workflow:default",
                    "title": "Interaction Logic & Execution Flow",
                    "workflow_name": "Interaction Logic & Execution Flow",
                    "triggers": [],
                    "steps": [{"order": 1, "title": "Default Step", "resource_file": "default.md"}],
                },
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["instruction_workflow"]["id"], "workflow:default")

    def test_planner_advances_clarification_gate_from_semantic_slot_threshold(self):
        state = self.state.copy()
        state["user_query"] = "continue"
        state["workflow_progress"] = {
            "workflow_id": "workflow:default",
            "workflow_title": "Interaction Logic & Execution Flow",
            "step_order": 1,
            "step_title": "Clarify Inputs",
            "resource_file": "clarify.md",
        }
        state["session_execution_state"] = {
            "execution_status": "waiting_user",
            "clarification_gate_status": {
                "filled_slots_map": {
                    "audience": True,
                    "theme_or_passage": True,
                    "tone": True,
                }
            },
        }
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "default_workflow_id": "workflow:default",
                    "clarification_gate_rules": [
                        {
                            "gate_rule_id": "gate:default",
                            "procedure_id": "procedure:default",
                            "clarification_step_id": "step:workflow:1",
                            "completion_step_id": "step:workflow:2",
                            "slot_policy": {
                                "mode": "threshold",
                                "minimum_filled_slots": 3,
                            },
                        }
                    ],
                    "instruction_service_blocks": [
                        {
                            "block_id": "workflow:default",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                            "is_default": True,
                        }
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "procedure:default",
                            "service_block_id": "workflow:default",
                            "title": "Interaction Logic & Execution Flow",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:workflow:1",
                            "procedure_id": "procedure:default",
                            "order": 1,
                            "title": "Clarify Inputs",
                            "execution_mode": "interactive",
                        },
                        {
                            "step_id": "step:workflow:2",
                            "procedure_id": "procedure:default",
                            "order": 2,
                            "title": "Generate Draft",
                            "execution_mode": "bundled",
                            "bundled_step_ids": ["step:workflow:2", "step:workflow:3"],
                        },
                    ],
                }
            },
            "instruction_workflows": [
                {
                    "id": "workflow:default",
                    "title": "Interaction Logic & Execution Flow",
                    "workflow_name": "Interaction Logic & Execution Flow",
                    "triggers": [],
                    "steps": [
                        {"order": 1, "title": "Clarify Inputs", "resource_file": "clarify.md", "step_scope_id": "step:workflow:1"},
                        {"order": 2, "title": "Generate Draft", "resource_file": "draft.md", "step_scope_id": "step:workflow:2"},
                        {"order": 3, "title": "Validate Draft", "resource_file": "validate.md", "step_scope_id": "step:workflow:3"},
                    ],
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["instruction_step"]["order"], 2)
        self.assertEqual(out["turn_execution_plan"]["active_execution_mode"], "bundled")
        self.assertEqual(out["turn_execution_plan"]["bundled_entry_step_id"], "step:workflow:2")
        self.assertTrue(out["session_execution_state"]["bundled_execution_completed"])

    def test_planner_hybrid_active_prefers_semantic_selected_workflow_for_intent_routed_app(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "I need parenting advice for young children"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "intent_routed_multi_workflow",
                    "default_workflow_id": None,
                    "instruction_service_blocks": [
                        {"block_id": "workflow:advice", "block_type": "primary_workflow", "title": "Advice Workflow"},
                        {"block_id": "workflow:bible", "block_type": "primary_workflow", "title": "Bible Workflow"},
                    ],
                    "instruction_procedures": [],
                    "procedure_steps": [],
                    "routing_rules": [{"rule_id": "route:parenting-advice"}],
                }
            },
            "instruction_workflows": [
                {
                    "id": "workflow:bible",
                    "title": "Bible Workflow",
                    "workflow_name": "Bible Workflow",
                    "triggers": ["advice"],
                    "steps": [{"order": 1, "title": "Bible Step", "resource_file": "bible.md"}],
                },
                {
                    "id": "workflow:advice",
                    "title": "Advice Workflow",
                    "workflow_name": "Advice Workflow",
                    "triggers": [],
                    "steps": [{"order": 1, "title": "Advice Step", "resource_file": "advice.md"}],
                },
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "parenting_advice",
                "confidence": 0.91,
                "continue_current_scope": False,
                "selected_role_id": None,
                "selected_workflow_id": "workflow:advice",
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "select_workflow",
                    "target_service_block_id": "workflow:advice",
                    "target_workflow_id": "workflow:advice",
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [],
                },
                "reasoning_summary": ["route to advice workflow"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["instruction_workflow"]["id"], "workflow:advice")
        self.assertEqual(out["hybrid_planner_shadow_output"]["selected_workflow_id"], "workflow:advice")

    def test_planner_hybrid_active_persists_semantic_selected_role_id(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "Please coach parents through this situation"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "default_workflow_id": "workflow:advice",
                    "role_profiles": [
                        {
                            "role_id": "role:coach",
                            "name": "Coach",
                            "allowed_workflow_ids": ["workflow:advice"],
                        },
                        {
                            "role_id": "role:teacher",
                            "name": "Teacher",
                            "allowed_workflow_ids": ["workflow:advice"],
                        },
                    ],
                    "instruction_service_blocks": [
                        {"block_id": "workflow:advice", "block_type": "primary_workflow", "title": "Advice Workflow", "is_default": True},
                    ],
                    "instruction_procedures": [],
                    "procedure_steps": [],
                }
            },
            "instruction_workflows": [
                {
                    "id": "workflow:advice",
                    "title": "Advice Workflow",
                    "workflow_name": "Advice Workflow",
                    "triggers": [],
                    "steps": [{"order": 1, "title": "Advice Step", "resource_file": "advice.md"}],
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "parenting_advice",
                "confidence": 0.95,
                "continue_current_scope": False,
                "selected_role_id": "role:coach",
                "selected_workflow_id": "workflow:advice",
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "select_workflow",
                    "target_service_block_id": "workflow:advice",
                    "target_workflow_id": "workflow:advice",
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [],
                },
                "reasoning_summary": ["select coaching role"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["turn_execution_plan"]["selected_role_id"], "role:coach")
        self.assertEqual(out["session_execution_state"]["active_role_id"], "role:coach")

    def test_planner_hybrid_active_allows_logic_only_route_without_active_step(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "Help me think through layered parenting needs"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "intent_routed_interaction_logic",
                    "default_workflow_id": None,
                    "role_profiles": [
                        {
                            "role_id": "role:mentor",
                            "name": "Mentor",
                            "allowed_module_ids": [],
                            "target_workflow_ids": [],
                        }
                    ],
                    "instruction_service_blocks": [],
                    "instruction_procedures": [],
                    "procedure_steps": [],
                    "routing_rules": [
                        {"rule_id": "route:layered", "target_role_id": "role:mentor"}
                    ],
                    "interaction_logic_blocks": [
                        {
                            "logic_id": "logic:layered",
                            "title": "多重需求分層規則",
                            "rules": [{"expression": "route by layered parenting need"}],
                        }
                    ],
                }
            },
            "instruction_workflows": [],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "layered_parenting_support",
                "confidence": 0.93,
                "continue_current_scope": False,
                "selected_role_id": "role:mentor",
                "selected_workflow_id": None,
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "respond",
                    "target_service_block_id": None,
                    "target_workflow_id": None,
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [],
                },
                "reasoning_summary": ["route through mentor logic without executable workflow step"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["turn_execution_plan"]["selected_role_id"], "role:mentor")
        self.assertIsNone(out["turn_execution_plan"]["active_step_scope"])

    def test_planner_hybrid_active_binds_subordinate_support_module_from_logic_route(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "我想查考一段經文"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "intent_routed_interaction_logic",
                    "default_workflow_id": None,
                    "instruction_service_blocks": [
                        {
                            "block_id": "support_module:bible_study",
                            "block_type": "support_module",
                            "title": "查經互動模組",
                        }
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "procedure:support_module_bible_study",
                            "service_block_id": "support_module:bible_study",
                            "title": "查經互動模組",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:support_module:bible_study:1",
                            "procedure_id": "procedure:support_module_bible_study",
                            "order": 1,
                            "title": "細察事實",
                            "execution_mode": "interactive",
                            "resource_refs": ["observation_guide.md"],
                        }
                    ],
                    "routing_rules": [
                        {
                            "rule_id": "route:bible_study",
                            "trigger_keywords": ["查考", "經文"],
                            "target": "interaction_logic_block:mode_bible_study",
                        }
                    ],
                    "interaction_logic_blocks": [
                        {
                            "block_id": "interaction_logic_block:mode_bible_study",
                            "logic_id": "interaction_logic_block:mode_bible_study",
                            "title": "查考經文模式",
                            "subordinate_modules": ["support_module:bible_study"],
                            "rules": [{"expression": "route bible-study requests to the study module"}],
                        }
                    ],
                }
            },
            "instruction_workflows": [],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": [
                {
                    "block_id": "support_module:bible_study",
                    "block_type": "support_module",
                    "title": "查經互動模組",
                }
            ],
            "instruction_procedures": [
                {
                    "procedure_id": "procedure:support_module_bible_study",
                    "service_block_id": "support_module:bible_study",
                    "title": "查經互動模組",
                }
            ],
            "procedure_steps": [
                {
                    "step_id": "step:support_module:bible_study:1",
                    "procedure_id": "procedure:support_module_bible_study",
                    "order": 1,
                    "title": "細察事實",
                    "execution_mode": "interactive",
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "bible_study",
                "confidence": 0.96,
                "continue_current_scope": False,
                "selected_role_id": None,
                "selected_workflow_id": None,
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "respond",
                    "target_service_block_id": "interaction_logic_block:mode_bible_study",
                    "target_workflow_id": None,
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [],
                },
                "reasoning_summary": ["choose bible study route and let runtime bind the executable module"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(
            out["turn_execution_plan"]["primary_support_module_scope"]["scope_id"],
            "support_module:bible_study",
        )
        self.assertEqual(
            out["turn_execution_plan"]["active_step_scope"]["scope_id"],
            "step:support_module:bible_study:1",
        )
        self.assertEqual(
            out["session_execution_state"]["primary_support_module_id"],
            "support_module:bible_study",
        )
        self.assertEqual(
            out["session_execution_state"]["active_step_scope_id"],
            "step:support_module:bible_study:1",
        )

    def test_planner_hybrid_active_does_not_promote_on_demand_exegesis_support_for_life_application_starter(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "我正在面對生活中的一些問題，想知道聖經怎麼教導或給我方向。"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "intent_routed_interaction_logic",
                    "default_workflow_id": None,
                    "instruction_service_blocks": [
                        {
                            "block_id": "support_module:查經互動模組",
                            "block_type": "support_module",
                            "title": "查經互動模組",
                        },
                        {
                            "block_id": "support_module:釋經支援模組_exegesis_support_module_八種合法處境",
                            "block_type": "support_module",
                            "title": "釋經支援模組（Exegesis Support Module — 八種合法處境）",
                        },
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "service_block_id": "support_module:查經互動模組",
                            "title": "查經互動模組",
                        },
                        {
                            "procedure_id": "procedure:support_module_釋經支援模組_exegesis_support_module_八種合法處境",
                            "service_block_id": "support_module:釋經支援模組_exegesis_support_module_八種合法處境",
                            "title": "釋經支援模組（Exegesis Support Module — 八種合法處境）",
                        },
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:support_module:查經互動模組:1",
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "order": 1,
                            "title": "細察事實",
                            "execution_mode": "interactive",
                        },
                        {
                            "step_id": "step:support_module:釋經支援模組_exegesis_support_module_八種合法處境:1",
                            "procedure_id": "procedure:support_module_釋經支援模組_exegesis_support_module_八種合法處境",
                            "order": 1,
                            "title": "釋經支援模組（Exegesis Support Module — 八種合法處境）",
                            "execution_mode": "interactive",
                        },
                    ],
                    "routing_rules": [
                        {
                            "rule_id": "route:life_application",
                            "trigger_keywords": ["生活", "教導", "方向"],
                            "target_logic_block_id": "logic:life_application_mode",
                        }
                    ],
                    "interaction_logic_blocks": [
                        {
                            "block_id": "logic:life_application_mode",
                            "logic_id": "logic:life_application_mode",
                            "title": "生活應用模式（Life Application）",
                            "support_modules_on_demand": ["support_module:釋經支援模組_exegesis_support_module_八種合法處境"],
                            "rules": [{"expression": "use life-application reflection first"}],
                        }
                    ],
                }
            },
            "instruction_workflows": [],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "life_application",
                "confidence": 0.94,
                "continue_current_scope": False,
                "selected_role_id": None,
                "selected_workflow_id": None,
                "selected_support_module_ids": [
                    "support_module:釋經支援模組_exegesis_support_module_八種合法處境"
                ],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [
                    "support_module:釋經支援模組_exegesis_support_module_八種合法處境"
                ],
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "respond",
                    "target_service_block_id": "logic:life_application_mode",
                    "target_workflow_id": None,
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [
                        "support_module:釋經支援模組_exegesis_support_module_八種合法處境"
                    ],
                },
                "reasoning_summary": ["remain in life-application mode; exegesis is only on-demand support"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["turn_execution_plan"]["selected_routing_rule_id"], "route:life_application")
        self.assertIsNone(out["turn_execution_plan"].get("primary_support_module_scope"))
        self.assertIsNone(out["turn_execution_plan"].get("active_step_scope"))
        self.assertFalse(out["session_execution_state"].get("primary_support_module_id"))
        self.assertFalse(out["session_execution_state"].get("active_service_block_id"))

    def test_planner_hybrid_active_persists_life_application_starter_without_falling_back_to_bible_study(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["instruction_understanding_mode"] = "hybrid_active"
        state["user_query"] = "\u9019\u6bb5\u7d93\u6587\u5c0d\u6211\u73fe\u5728\u7684\u751f\u6d3b\u65b9\u5411\u6709\u4ec0\u9ebc\u63d0\u9192\uff1f"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "intent_routed_interaction_logic",
                    "default_workflow_id": None,
                    "instruction_service_blocks": [
                        {
                            "block_id": "support_module:\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                            "block_type": "support_module",
                            "title": "\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                        },
                        {
                            "block_id": "support_module:\u91cb\u7d93\u652f\u63f4\u6a21\u7d44_exegesis_support_module_\u516b\u7a2e\u5408\u6cd5\u8655\u5883",
                            "block_type": "support_module",
                            "title": "\u91cb\u7d93\u652f\u63f4\u6a21\u7d44\uff08Exegesis Support Module - \u516b\u7a2e\u5408\u6cd5\u8655\u5883\uff09",
                        },
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "procedure:support_module_\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                            "service_block_id": "support_module:\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                            "title": "\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                        },
                        {
                            "procedure_id": "procedure:support_module_\u91cb\u7d93\u652f\u63f4\u6a21\u7d44_exegesis_support_module_\u516b\u7a2e\u5408\u6cd5\u8655\u5883",
                            "service_block_id": "support_module:\u91cb\u7d93\u652f\u63f4\u6a21\u7d44_exegesis_support_module_\u516b\u7a2e\u5408\u6cd5\u8655\u5883",
                            "title": "\u91cb\u7d93\u652f\u63f4\u6a21\u7d44\uff08Exegesis Support Module - \u516b\u7a2e\u5408\u6cd5\u8655\u5883\uff09",
                        },
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:support_module:\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44:1",
                            "procedure_id": "procedure:support_module_\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                            "order": 1,
                            "title": "\u7d30\u5bdf\u4e8b\u5be6",
                            "execution_mode": "interactive",
                        },
                        {
                            "step_id": "step:support_module:\u91cb\u7d93\u652f\u63f4\u6a21\u7d44_exegesis_support_module_\u516b\u7a2e\u5408\u6cd5\u8655\u5883:1",
                            "procedure_id": "procedure:support_module_\u91cb\u7d93\u652f\u63f4\u6a21\u7d44_exegesis_support_module_\u516b\u7a2e\u5408\u6cd5\u8655\u5883",
                            "order": 1,
                            "title": "\u5408\u6cd5\u8655\u5883\u53cd\u601d",
                            "execution_mode": "interactive",
                        },
                    ],
                    "routing_rules": [
                        {
                            "rule_id": "route_to_bible_study",
                            "priority": 1,
                            "trigger_keywords": ["\u67e5\u8003", "\u7814\u7d93", "\u7d93\u6587"],
                            "target_logic_block_id": "mode_bible_study",
                        },
                        {
                            "rule_id": "route_to_life_application",
                            "priority": 3,
                            "trigger_keywords": ["\u751f\u6d3b", "\u61c9\u7528", "\u6311\u6230", "\u56f0\u96e3", "\u65b9\u5411"],
                            "target_logic_block_id": "mode_life_application",
                        },
                    ],
                    "interaction_logic_blocks": [
                        {
                            "block_id": "mode_bible_study",
                            "logic_id": "mode_bible_study",
                            "title": "\u67e5\u8003\u7d93\u6587\u6a21\u5f0f\uff08Bible Study\uff09",
                            "subordinate_target": {
                                "target_type": "support_module",
                                "target_id": "support_module:\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                            },
                        },
                        {
                            "block_id": "mode_life_application",
                            "logic_id": "mode_life_application",
                            "title": "\u751f\u6d3b\u61c9\u7528\u6a21\u5f0f\uff08Life Application\uff09",
                            "support_modules_on_demand": [
                                "support_module:\u91cb\u7d93\u652f\u63f4\u6a21\u7d44_exegesis_support_module_\u516b\u7a2e\u5408\u6cd5\u8655\u5883"
                            ],
                            "rules": [{"expression": "use life-application reflection first"}],
                        },
                    ],
                }
            },
            "instruction_workflows": [
                {
                    "id": "bible_study",
                    "title": "\u67e5\u8003\u7d93\u6587\u6a21\u5f0f\uff08Bible Study\uff09",
                    "workflow_name": "\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                    "triggers": ["\u67e5\u8003", "\u7814\u7d93", "\u7d93\u6587"],
                    "steps": [
                        {
                            "order": 1,
                            "title": "\u7d30\u5bdf\u4e8b\u5be6",
                            "resource_file": "observation_guide.md",
                        }
                    ],
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "life_application",
                "confidence": 0.94,
                "continue_current_scope": False,
                "selected_role_id": None,
                "selected_workflow_id": None,
                "selected_support_module_ids": [
                    "support_module:\u91cb\u7d93\u652f\u63f4\u6a21\u7d44_exegesis_support_module_\u516b\u7a2e\u5408\u6cd5\u8655\u5883"
                ],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [
                    "support_module:\u91cb\u7d93\u652f\u63f4\u6a21\u7d44_exegesis_support_module_\u516b\u7a2e\u5408\u6cd5\u8655\u5883"
                ],
                "selected_routing_rule_id": "route_to_life_application",
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "respond",
                    "target_service_block_id": "mode_life_application",
                    "target_workflow_id": None,
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [
                        "support_module:\u91cb\u7d93\u652f\u63f4\u6a21\u7d44_exegesis_support_module_\u516b\u7a2e\u5408\u6cd5\u8655\u5883"
                    ],
                },
                "reasoning_summary": ["compiled evidence favors life application over bible study"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        persisted_state = out["session_execution_state"]
        self.assertEqual(persisted_state.get("selected_routing_rule_id"), "route_to_life_application")
        self.assertEqual(persisted_state.get("active_mode"), "mode_life_application")
        self.assertEqual(persisted_state.get("primary_scope_type"), "mode")
        self.assertEqual(persisted_state.get("primary_scope_id"), "mode_life_application")
        workflow_progress = persisted_state.get("workflow_progress") or {}
        self.assertFalse(workflow_progress.get("workflow_id"))

    def test_planner_hybrid_active_binds_subordinate_target_module_for_bible_study_starter(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "我想查考一段經文"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "intent_routed_interaction_logic",
                    "default_workflow_id": None,
                    "instruction_service_blocks": [
                        {
                            "block_id": "support_module:查經互動模組",
                            "block_type": "support_module",
                            "title": "查經互動模組",
                        }
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "service_block_id": "support_module:查經互動模組",
                            "title": "查經互動模組",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:support_module:查經互動模組:1",
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "order": 1,
                            "title": "細察事實",
                            "execution_mode": "interactive",
                            "resource_refs": ["observation_guide.md"],
                        }
                    ],
                    "routing_rules": [
                        {
                            "rule_id": "route:bible_study",
                            "trigger_keywords": ["查考", "經文"],
                            "target_logic_block_id": "logic:bible_study_mode",
                        }
                    ],
                    "interaction_logic_blocks": [
                        {
                            "block_id": "logic:bible_study_mode",
                            "logic_id": "logic:bible_study_mode",
                            "title": "查考經文模式",
                            "subordinate_target": {
                                "target_type": "support_module",
                                "target_id": "support_module:查經互動模組",
                            },
                            "rules": [{"expression": "route bible-study requests to the study module"}],
                        }
                    ],
                }
            },
            "instruction_workflows": [],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "bible_study",
                "confidence": 0.97,
                "continue_current_scope": False,
                "selected_role_id": None,
                "selected_workflow_id": None,
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "respond",
                    "target_service_block_id": "logic:bible_study_mode",
                    "target_workflow_id": None,
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [],
                },
                "reasoning_summary": ["choose bible study route and let runtime bind the module-owned procedure"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["turn_execution_plan"]["selected_routing_rule_id"], "route:bible_study")
        self.assertEqual(
            out["turn_execution_plan"]["primary_support_module_scope"]["scope_id"],
            "support_module:查經互動模組",
        )
        self.assertEqual(
            out["turn_execution_plan"]["active_step_scope"]["scope_id"],
            "step:support_module:查經互動模組:1",
        )

    def test_planner_hybrid_active_followup_turn_enters_first_module_step_for_bible_study(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "我想看彌迦書第二章"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "intent_routed_interaction_logic",
                    "instruction_service_blocks": [
                        {
                            "block_id": "module:查經互動模組",
                            "block_type": "support_module",
                            "title": "查經互動模組",
                        }
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "procedure:module_查經互動模組",
                            "service_block_id": "module:查經互動模組",
                            "title": "查經互動模組",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:support_module_查經互動模組:1",
                            "procedure_id": "procedure:module_查經互動模組",
                            "order": 1,
                            "title": "細察事實",
                            "execution_mode": "interactive",
                            "resource_refs": ["observation_guide.md"],
                        }
                    ],
                    "routing_rules": [
                        {
                            "rule_id": "route:bible_study",
                            "trigger_keywords": ["查考", "經文"],
                            "target_logic_block_id": "logic:bible_study_mode",
                            "target_module_id": "module:查經互動模組",
                        }
                    ],
                    "interaction_logic_blocks": [
                        {
                            "block_id": "logic:bible_study_mode",
                            "logic_id": "logic:bible_study_mode",
                            "title": "查考經文模式",
                            "subordinate_target": {
                                "target_type": "support_module",
                                "target_id": "module:查經互動模組",
                            },
                        }
                    ],
                }
            },
            "instruction_workflows": [],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
            "support_modules": [
                {
                    "module_id": "查經互動模組",
                    "title": "查經互動模組",
                    "block_type": "support_module",
                    "resource_ids": [],
                    "notes": "",
                }
            ],
        }
        state["session_execution_state"] = {
            "selected_routing_rule_id": "route:bible_study",
            "active_service_block_id": "module:查經互動模組",
            "active_service_block_type": "support_module",
            "active_service_block_title": "查經互動模組",
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "bible_study",
                "confidence": 0.97,
                "continue_current_scope": True,
                "selected_role_id": None,
                "selected_workflow_id": None,
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "respond",
                    "target_service_block_id": "logic:bible_study_mode",
                    "target_workflow_id": None,
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [],
                },
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(
            out["session_execution_state"].get("active_step_scope_id"),
            "step:support_module_查經互動模組:1",
        )
        self.assertEqual(
            out["turn_execution_plan"]["active_step_scope"]["title"],
            "細察事實",
        )

    def test_planner_hybrid_active_step_one_only_loads_observation_guide_for_bible_study(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "我想看彌迦書第二章"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "intent_routed_interaction_logic",
                    "instruction_service_blocks": [
                        {
                            "block_id": "module:查經互動模組",
                            "block_type": "support_module",
                            "title": "查經互動模組",
                        }
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "procedure:module_查經互動模組",
                            "service_block_id": "module:查經互動模組",
                            "title": "查經互動模組",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:support_module_查經互動模組:1",
                            "procedure_id": "procedure:module_查經互動模組",
                            "order": 1,
                            "title": "細察事實",
                            "execution_mode": "interactive",
                            "resource_refs": ["observation_guide.md"],
                        },
                        {
                            "step_id": "step:support_module_查經互動模組:2",
                            "procedure_id": "procedure:module_查經互動模組",
                            "order": 2,
                            "title": "認清關係",
                            "execution_mode": "interactive",
                            "resource_refs": ["identify_relationships_guide.md"],
                        },
                    ],
                    "routing_rules": [
                        {
                            "rule_id": "route:bible_study",
                            "trigger_keywords": ["查考", "經文"],
                            "target_logic_block_id": "logic:bible_study_mode",
                            "target_module_id": "module:查經互動模組",
                        }
                    ],
                    "interaction_logic_blocks": [
                        {
                            "block_id": "logic:bible_study_mode",
                            "logic_id": "logic:bible_study_mode",
                            "title": "查考經文模式",
                            "subordinate_target": {
                                "target_type": "support_module",
                                "target_id": "module:查經互動模組",
                            },
                        }
                    ],
                }
            },
            "instruction_workflows": [],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
            "instruction_resources": [
                {"resource_id": "obs", "filename": "observation_guide.md", "domain": "instruction_source"},
                {"resource_id": "rel", "filename": "identify_relationships_guide.md", "domain": "instruction_source"},
                {"resource_id": "form", "filename": "formulate_questions_guide.md", "domain": "instruction_source"},
            ],
            "support_modules": [
                {
                    "module_id": "查經互動模組",
                    "title": "查經互動模組",
                    "block_type": "support_module",
                    "resource_ids": [],
                    "notes": "legacy module note",
                }
            ],
        }
        state["session_execution_state"] = {
            "selected_routing_rule_id": "route:bible_study",
            "active_service_block_id": "module:查經互動模組",
            "active_service_block_type": "support_module",
            "active_service_block_title": "查經互動模組",
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "bible_study",
                "confidence": 0.97,
                "continue_current_scope": True,
                "selected_role_id": None,
                "selected_workflow_id": None,
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "respond",
                    "target_service_block_id": "logic:bible_study_mode",
                    "target_workflow_id": None,
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [],
                },
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        instruction_filenames = [
            str(item.get("filename") or "").strip()
            for item in out["turn_execution_plan"].get("resource_requests", []) or []
            if str(item.get("purpose") or "").strip() == "instruction_support"
        ]
        self.assertIn("observation_guide.md", instruction_filenames)
        self.assertNotIn("identify_relationships_guide.md", instruction_filenames)
        self.assertNotIn("formulate_questions_guide.md", instruction_filenames)

    def test_planner_hybrid_active_step_scope_does_not_readd_module_wide_support_resources_for_bible_tutor(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["instruction_understanding_mode"] = "hybrid_active"
        state["user_query"] = "提摩太前書 4:11-16"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "intent_routed_interaction_logic",
                    "instruction_service_blocks": [
                        {
                            "block_id": "support_module:查經互動模組",
                            "block_type": "support_module",
                            "title": "查經互動模組",
                        }
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "service_block_id": "support_module:查經互動模組",
                            "title": "查經互動模組",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:support_module_查經互動模組:1",
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "order": 1,
                            "title": "細察事實",
                            "execution_mode": "interactive",
                            "resource_refs": ["observation_guide.md"],
                        },
                        {
                            "step_id": "step:support_module_查經互動模組:2",
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "order": 2,
                            "title": "認清關係",
                            "execution_mode": "interactive",
                            "resource_refs": ["identify_relationships_guide.md"],
                        },
                    ],
                    "routing_rules": [
                        {
                            "rule_id": "route:bible_study",
                            "trigger_keywords": ["查考", "經文"],
                            "target_logic_block_id": "logic:bible_study_mode",
                            "target_module_id": "support_module:查經互動模組",
                        }
                    ],
                    "interaction_logic_blocks": [
                        {
                            "block_id": "logic:bible_study_mode",
                            "title": "查考經文模式",
                            "subordinate_target": {
                                "target_type": "support_module",
                                "target_id": "support_module:查經互動模組",
                            },
                        }
                    ],
                }
            },
            "instruction_workflows": [],
            "instruction_modules": [
                {
                    "id": "support_module:查經互動模組",
                    "title": "查經互動模組",
                    "keywords": [],
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
            "instruction_resources": [
                {"resource_id": "obs", "filename": "observation_guide.md", "domain": "instruction_source"},
                {"resource_id": "rel", "filename": "identify_relationships_guide.md", "domain": "instruction_source"},
                {"resource_id": "form", "filename": "formulate_questions_guide.md", "domain": "instruction_source"},
            ],
            "support_modules": [
                {
                    "module_id": "support_module:查經互動模組",
                    "title": "查經互動模組",
                    "resource_ids": ["obs", "rel", "form"],
                }
            ],
        }
        state["session_execution_state"] = {
            "selected_routing_rule_id": "route:bible_study",
            "active_service_block_id": "support_module:查經互動模組",
            "active_service_block_type": "support_module",
            "active_service_block_title": "查經互動模組",
            "primary_support_module_id": "support_module:查經互動模組",
            "primary_support_module_title": "查經互動模組",
            "active_step_scope_id": "step:support_module_查經互動模組:1",
            "active_step_order": 1,
            "active_step_title": "細察事實",
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "bible_study",
                "confidence": 0.97,
                "continue_current_scope": True,
                "selected_role_id": None,
                "selected_workflow_id": None,
                "selected_support_module_ids": ["support_module:查經互動模組"],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": ["support_module:查經互動模組"],
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "guide",
                    "target_service_block_id": "logic:bible_study_mode",
                    "target_workflow_id": None,
                    "target_step_id": "step:support_module_查經互動模組:1",
                    "bundled_step_ids": [],
                    "module_queue": ["support_module:查經互動模組"],
                },
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        instruction_filenames = [
            str(item.get("filename") or "").strip()
            for item in out["turn_execution_plan"].get("resource_requests", []) or []
            if str(item.get("purpose") or "").strip() == "instruction_support"
        ]
        self.assertIn("observation_guide.md", instruction_filenames)
        self.assertNotIn("identify_relationships_guide.md", instruction_filenames)
        self.assertNotIn("formulate_questions_guide.md", instruction_filenames)

    def test_planner_hybrid_active_bible_tutor_starter_turn_prefers_first_step_resource_over_phase_binding_bundle(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["instruction_understanding_mode"] = "hybrid_active"
        state["user_query"] = "我想查考一段經文"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "intent_routed_interaction_logic",
                    "instruction_service_blocks": [
                        {
                            "block_id": "support_module:查經互動模組",
                            "block_type": "support_module",
                            "title": "查經互動模組",
                        }
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "service_block_id": "support_module:查經互動模組",
                            "title": "查經互動模組",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:support_module_查經互動模組:1",
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "order": 1,
                            "title": "細察事實",
                            "execution_mode": "interactive",
                            "resource_refs": ["observation_guide.md"],
                        },
                        {
                            "step_id": "step:support_module_查經互動模組:2",
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "order": 2,
                            "title": "認清關係",
                            "execution_mode": "interactive",
                            "resource_refs": ["identify_relationships_guide.md"],
                        },
                    ],
                    "routing_rules": [
                        {
                            "rule_id": "route:bible_study",
                            "trigger_keywords": ["查考", "經文"],
                            "target_logic_block_id": "logic:bible_study_mode",
                            "target_module_id": "support_module:查經互動模組",
                        }
                    ],
                    "interaction_logic_blocks": [
                        {
                            "block_id": "logic:bible_study_mode",
                            "title": "查考經文模式",
                            "subordinate_target": {
                                "target_type": "support_module",
                                "target_id": "support_module:查經互動模組",
                            },
                        }
                    ],
                }
            },
            "instruction_workflows": [],
            "instruction_modules": [
                {
                    "id": "support_module:查經互動模組",
                    "title": "查經互動模組",
                    "keywords": [],
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
            "instruction_resources": [
                {"resource_id": "obs", "filename": "observation_guide.md", "domain": "instruction_source"},
                {"resource_id": "rel", "filename": "identify_relationships_guide.md", "domain": "instruction_source"},
            ],
            "phase_resource_bindings": [
                {
                    "binding_id": "phase:查經互動模組",
                    "title": "查經互動模組",
                    "trigger_type": "phase",
                    "binding_mode": "multi_required",
                    "scope_id": "support_module:查經互動模組",
                    "resource_ids": ["obs", "rel"],
                    "resource_kinds": ["instruction_resource", "instruction_resource"],
                    "activation_reason": "broad module phase bundle",
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "bible_study",
                "confidence": 0.98,
                "continue_current_scope": False,
                "selected_role_id": None,
                "selected_workflow_id": None,
                "selected_support_module_ids": ["support_module:查經互動模組"],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": ["support_module:查經互動模組"],
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "guide",
                    "target_service_block_id": "logic:bible_study_mode",
                    "target_workflow_id": None,
                    "target_step_id": "step:support_module_查經互動模組:1",
                    "bundled_step_ids": [],
                    "module_queue": ["support_module:查經互動模組"],
                },
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        instruction_filenames = [
            str(item.get("filename") or "").strip()
            for item in out["turn_execution_plan"].get("resource_requests", []) or []
            if str(item.get("purpose") or "").strip() == "instruction_support"
        ]
        self.assertEqual(instruction_filenames, ["observation_guide.md"])
        self.assertEqual(
            out["session_execution_state"]["active_step_scope_id"],
            "step:support_module_查經互動模組:1",
        )

    def test_planner_hybrid_active_followup_turn_advances_module_owned_step_to_second_step(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "move to the next step"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "intent_routed_interaction_logic",
                    "instruction_service_blocks": [
                        {
                            "block_id": "support_module:查經互動模組",
                            "block_type": "support_module",
                            "title": "查經互動模組",
                        }
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "service_block_id": "support_module:查經互動模組",
                            "title": "查經互動模組",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:support_module_查經互動模組:1",
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "order": 1,
                            "title": "細察事實",
                            "execution_mode": "interactive",
                            "resource_refs": ["observation_guide.md"],
                        },
                        {
                            "step_id": "step:support_module_查經互動模組:2",
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "order": 2,
                            "title": "認清關係",
                            "execution_mode": "interactive",
                            "resource_refs": ["identify_relationships_guide.md"],
                        },
                    ],
                    "routing_rules": [
                        {
                            "rule_id": "route:bible_study",
                            "trigger_keywords": ["查考", "經文"],
                            "target_logic_block_id": "logic:bible_study_mode",
                            "target_module_id": "support_module:查經互動模組",
                        }
                    ],
                    "interaction_logic_blocks": [
                        {
                            "block_id": "logic:bible_study_mode",
                            "logic_id": "logic:bible_study_mode",
                            "title": "查考經文模式",
                            "subordinate_target": {
                                "target_type": "support_module",
                                "target_id": "support_module:查經互動模組",
                            },
                        }
                    ],
                }
            },
            "instruction_workflows": [],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
            "instruction_resources": [
                {"resource_id": "obs", "filename": "observation_guide.md", "domain": "instruction_source"},
                {"resource_id": "rel", "filename": "identify_relationships_guide.md", "domain": "instruction_source"},
            ],
        }
        state["session_execution_state"] = {
            "selected_routing_rule_id": "route:bible_study",
            "active_service_block_id": "support_module:查經互動模組",
            "active_service_block_type": "support_module",
            "active_service_block_title": "查經互動模組",
            "active_step_scope_id": "step:support_module_查經互動模組:1",
            "active_step_order": 1,
            "active_step_title": "細察事實",
            "primary_support_module_id": "support_module:查經互動模組",
            "primary_support_module_title": "查經互動模組",
            "procedure_step_activation": {
                "step_scope_id": "step:support_module_查經互動模組:1",
                "step_order": 1,
                "step_title": "細察事實",
                "resource_ids": ["obs"],
                "primary_support_module_id": "support_module:查經互動模組",
            },
            "primary_support_module_activation": {
                "support_module_id": "support_module:查經互動模組",
                "support_module_title": "查經互動模組",
                "resource_ids": [],
                "step_scope_id": "step:support_module_查經互動模組:1",
            },
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "bible_study",
                "confidence": 0.97,
                "continue_current_scope": True,
                "selected_role_id": None,
                "selected_workflow_id": None,
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "advance_step",
                    "target_service_block_id": "logic:bible_study_mode",
                    "target_workflow_id": None,
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [],
                },
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["session_execution_state"]["active_step_scope_id"], "step:support_module_查經互動模組:2")
        self.assertEqual(out["session_execution_state"]["active_step_order"], 2)
        self.assertEqual(out["session_execution_state"]["active_step_title"], "認清關係")
        instruction_filenames = [
            str(item.get("filename") or "").strip()
            for item in out["turn_execution_plan"].get("resource_requests", []) or []
            if str(item.get("purpose") or "").strip() == "instruction_support"
        ]
        self.assertIn("identify_relationships_guide.md", instruction_filenames)
        self.assertNotIn("observation_guide.md", instruction_filenames)

    def test_planner_hybrid_active_followup_turn_session_state_round_trips_with_canonical_support_module_id(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "阿摩司書第五章"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "intent_routed_interaction_logic",
                    "instruction_service_blocks": [
                        {
                            "block_id": "support_module:查經互動模組",
                            "block_type": "support_module",
                            "title": "查經互動模組",
                        }
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "service_block_id": "support_module:查經互動模組",
                            "title": "查經互動模組",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:support_module_查經互動模組:1",
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "order": 1,
                            "title": "細察事實",
                            "execution_mode": "interactive",
                            "resource_refs": ["observation_guide.md"],
                        }
                    ],
                    "routing_rules": [
                        {
                            "rule_id": "route:bible_study",
                            "trigger_keywords": ["查考", "經文"],
                            "target_logic_block_id": "logic:bible_study_mode",
                            "target_module_id": "module:查經互動模組",
                        }
                    ],
                    "interaction_logic_blocks": [
                        {
                            "block_id": "logic:bible_study_mode",
                            "logic_id": "logic:bible_study_mode",
                            "title": "查考經文模式",
                            "subordinate_target": {
                                "target_type": "support_module",
                                "target_id": "module:查經互動模組",
                            },
                        }
                    ],
                }
            },
            "instruction_workflows": [],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
            "instruction_resources": [
                {"resource_id": "obs", "filename": "observation_guide.md", "domain": "instruction_source"},
            ],
            "support_modules": [
                {
                    "module_id": "查經互動模組",
                    "title": "查經互動模組",
                    "block_type": "support_module",
                    "resource_ids": [],
                    "notes": "",
                }
            ],
        }
        state["session_execution_state"] = {
            "selected_routing_rule_id": "route:bible_study",
            "active_service_block_id": "module:查經互動模組",
            "active_service_block_type": "support_module",
            "active_service_block_title": "查經互動模組",
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "bible_study",
                "confidence": 0.97,
                "continue_current_scope": True,
                "selected_role_id": None,
                "selected_workflow_id": None,
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "respond",
                    "target_service_block_id": "logic:bible_study_mode",
                    "target_workflow_id": None,
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [],
                },
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        validated = SessionExecutionState(**out["session_execution_state"])
        self.assertEqual(validated.primary_support_module_id, "support_module:查經互動模組")
        self.assertEqual(validated.procedure_step_activation.primary_support_module_id, "support_module:查經互動模組")

    def test_planner_hybrid_active_canonicalizes_symbolic_module_queue_id_to_service_block_id(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "我想查考一段經文"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "intent_routed_interaction_logic",
                    "instruction_service_blocks": [
                        {
                            "block_id": "support_module:查經互動模組",
                            "block_type": "support_module",
                            "title": "查經互動模組",
                        }
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "service_block_id": "support_module:查經互動模組",
                            "title": "查經互動模組",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:support_module_查經互動模組:1",
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "order": 1,
                            "title": "細察事實",
                            "execution_mode": "interactive",
                            "resource_refs": ["observation_guide.md"],
                        }
                    ],
                    "routing_rules": [
                        {
                            "rule_id": "route:bible_study",
                            "trigger_keywords": ["查考", "經文"],
                            "target_logic_block_id": "logic:bible_study_mode",
                        }
                    ],
                    "interaction_logic_blocks": [
                        {
                            "block_id": "logic:bible_study_mode",
                            "logic_id": "logic:bible_study_mode",
                            "title": "查考經文模式",
                            "subordinate_target": {
                                "target_type": "support_module",
                                "target_id": "bible_study_module",
                            },
                        }
                    ],
                }
            },
            "instruction_workflows": [],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
            "instruction_resources": [
                {"resource_id": "obs", "filename": "observation_guide.md", "domain": "instruction_source"},
            ],
            "support_modules": [
                {
                    "module_id": "查經互動模組",
                    "title": "查經互動模組",
                    "block_type": "support_module",
                    "resource_ids": [],
                    "notes": "",
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "bible_study",
                "confidence": 0.97,
                "continue_current_scope": False,
                "selected_role_id": None,
                "selected_workflow_id": None,
                "selected_support_module_ids": ["bible_study_module"],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": ["bible_study_module"],
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "respond",
                    "target_service_block_id": "logic:bible_study_mode",
                    "target_workflow_id": None,
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": ["bible_study_module"],
                },
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["session_execution_state"]["primary_support_module_id"], "support_module:查經互動模組")
        self.assertEqual(
            out["session_execution_state"]["procedure_step_activation"]["primary_support_module_id"],
            "support_module:查經互動模組",
        )

    def test_planner_hybrid_active_step_scoped_binding_suppresses_module_wide_dependency_bundle(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "阿摩司書第五章"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "intent_routed_interaction_logic",
                    "instruction_service_blocks": [
                        {
                            "block_id": "support_module:查經互動模組",
                            "block_type": "support_module",
                            "title": "查經互動模組",
                        }
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "service_block_id": "support_module:查經互動模組",
                            "title": "查經互動模組",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:support_module_查經互動模組:1",
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "order": 1,
                            "title": "細察事實",
                            "execution_mode": "interactive",
                            "resource_refs": ["observation_guide.md"],
                        },
                        {
                            "step_id": "step:support_module_查經互動模組:2",
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "order": 2,
                            "title": "認清關係",
                            "execution_mode": "interactive",
                            "resource_refs": ["identify_relationships_guide.md"],
                        },
                    ],
                    "routing_rules": [
                        {
                            "rule_id": "route:bible_study",
                            "trigger_keywords": ["查考", "經文"],
                            "target_logic_block_id": "logic:bible_study_mode",
                            "target_module_id": "support_module:查經互動模組",
                        }
                    ],
                    "interaction_logic_blocks": [
                        {
                            "block_id": "logic:bible_study_mode",
                            "logic_id": "logic:bible_study_mode",
                            "title": "查考經文模式",
                            "subordinate_target": {
                                "target_type": "support_module",
                                "target_id": "support_module:查經互動模組",
                            },
                        }
                    ],
                }
            },
            "instruction_workflows": [],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
            "instruction_resources": [
                {"resource_id": "obs", "filename": "observation_guide.md", "domain": "instruction_source"},
                {"resource_id": "rel", "filename": "identify_relationships_guide.md", "domain": "instruction_source"},
                {"resource_id": "form", "filename": "formulate_questions_guide.md", "domain": "instruction_source"},
            ],
            "dependency_groups": [
                {
                    "group_id": "dependency:查經互動模組",
                    "resource_ids": ["obs", "rel", "form"],
                    "required": True,
                }
            ],
            "phase_resource_bindings": [
                {
                    "binding_id": "phase:查經互動模組",
                    "scope_id": "phase:查經互動模組",
                    "title": "查經互動模組",
                    "dependency_groups": ["dependency:查經互動模組"],
                    "activation_reason": "module-wide legacy binding",
                }
            ],
            "support_modules": [
                {
                    "module_id": "查經互動模組",
                    "title": "查經互動模組",
                    "block_type": "support_module",
                    "resource_ids": [],
                    "notes": "legacy module note with all steps",
                }
            ],
        }
        state["session_execution_state"] = {
            "selected_routing_rule_id": "route:bible_study",
            "active_service_block_id": "support_module:查經互動模組",
            "active_service_block_type": "support_module",
            "active_service_block_title": "查經互動模組",
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "bible_study",
                "confidence": 0.97,
                "continue_current_scope": True,
                "selected_role_id": None,
                "selected_workflow_id": None,
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "respond",
                    "target_service_block_id": "logic:bible_study_mode",
                    "target_workflow_id": None,
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [],
                },
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        filenames = [
            str(item.get("filename") or "").strip()
            for item in out["turn_execution_plan"].get("resource_requests", []) or []
            if str(item.get("purpose") or "").strip() == "instruction_support"
        ]
        self.assertEqual(filenames.count("observation_guide.md"), 1)
        self.assertNotIn("identify_relationships_guide.md", filenames)
        self.assertNotIn("formulate_questions_guide.md", filenames)

    def test_planner_hybrid_active_persists_semantic_module_sequence(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "Help me design the app and then validate it"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "default_workflow_id": "workflow:design",
                    "instruction_service_blocks": [
                        {"block_id": "workflow:design", "block_type": "primary_workflow", "title": "Design Workflow", "is_default": True},
                        {"block_id": "module:use-case", "block_type": "support_module", "title": "Use Case Module"},
                        {"block_id": "module:testing", "block_type": "support_module", "title": "Testing Module"},
                    ],
                    "instruction_procedures": [],
                    "procedure_steps": [],
                    "module_orchestration": {
                        "composition_mode": "ordered_sequential",
                    },
                }
            },
            "instruction_workflows": [
                {
                    "id": "workflow:design",
                    "title": "Design Workflow",
                    "workflow_name": "Design Workflow",
                    "triggers": [],
                    "steps": [{"order": 1, "title": "Design Step", "resource_file": "design.md"}],
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "design_then_test",
                "confidence": 0.93,
                "continue_current_scope": False,
                "selected_role_id": None,
                "selected_workflow_id": "workflow:design",
                "selected_support_module_ids": ["module:use-case", "module:testing"],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": ["module:use-case", "module:testing"],
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "select_module",
                    "target_service_block_id": "workflow:design",
                    "target_workflow_id": "workflow:design",
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": ["module:use-case", "module:testing"],
                },
                "reasoning_summary": ["compose two support modules in sequence"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(
            out["turn_execution_plan"]["active_module_queue"],
            ["module:use-case", "module:testing"],
        )
        self.assertEqual(
            out["session_execution_state"]["active_module_queue"],
            ["module:use-case", "module:testing"],
        )

    def test_planner_hybrid_active_persists_selected_routing_rule_id(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "Help me coach parents"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "default_workflow_id": "workflow:advice",
                    "routing_rules": [{"rule_id": "route:coach-parents", "title": "Coach Parents"}],
                    "instruction_service_blocks": [
                        {"block_id": "workflow:advice", "block_type": "primary_workflow", "title": "Advice Workflow", "is_default": True},
                    ],
                    "instruction_procedures": [],
                    "procedure_steps": [],
                }
            },
            "instruction_workflows": [
                {
                    "id": "workflow:advice",
                    "title": "Advice Workflow",
                    "workflow_name": "Advice Workflow",
                    "triggers": [],
                    "steps": [{"order": 1, "title": "Advice Step", "resource_file": "advice.md"}],
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "coach_parents",
                "confidence": 0.94,
                "continue_current_scope": False,
                "selected_role_id": None,
                "selected_workflow_id": "workflow:advice",
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "select_workflow",
                    "target_service_block_id": "workflow:advice",
                    "target_workflow_id": "workflow:advice",
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [],
                },
                "selected_routing_rule_id": "route:coach-parents",
                "reasoning_summary": ["apply coach parents route"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["turn_execution_plan"]["selected_routing_rule_id"], "route:coach-parents")
        self.assertEqual(out["session_execution_state"]["selected_routing_rule_id"], "route:coach-parents")

    def test_bible_tutor_life_guidance_query_prefers_life_application_over_shadow_bible_study(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "我正在面對生活中的一些問題，想知道聖經怎麼教導或給我方向。"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "intent_routed_interaction_logic",
                    "instruction_service_blocks": [
                        {
                            "block_id": "support_module:查經互動模組",
                            "block_type": "support_module",
                            "title": "查經互動模組",
                        }
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "service_block_id": "support_module:查經互動模組",
                            "title": "查經互動模組",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:support_module_查經互動模組:1",
                            "procedure_id": "procedure:support_module_查經互動模組",
                            "order": 1,
                            "title": "細察事實",
                            "execution_mode": "interactive",
                            "resource_refs": ["observation_guide.md"],
                        }
                    ],
                    "routing_rules": [
                        {
                            "rule_id": "route_to_bible_study",
                            "priority": 1,
                            "trigger_keywords": ["查考", "研經", "經文"],
                            "target_logic_block_id": "mode_bible_study",
                        },
                        {
                            "rule_id": "route_to_life_application",
                            "priority": 3,
                            "trigger_keywords": ["生活", "應用", "挑戰", "困難", "方向"],
                            "target_logic_block_id": "mode_life_application",
                        },
                    ],
                    "interaction_logic_blocks": [
                        {
                            "block_id": "mode_bible_study",
                            "logic_id": "mode_bible_study",
                            "title": "查考經文模式",
                            "subordinate_target": {
                                "target_type": "support_module",
                                "target_id": "support_module:查經互動模組",
                            },
                        },
                        {
                            "block_id": "mode_life_application",
                            "logic_id": "mode_life_application",
                            "title": "生活應用模式",
                            "support_modules_on_demand": [
                                "support_module:釋經支援模組_exegesis_support_module_八種合法處境"
                            ],
                        },
                    ],
                }
            },
            "instruction_workflows": [],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "bible_study",
                "confidence": 0.82,
                "continue_current_scope": False,
                "selected_role_id": None,
                "selected_workflow_id": None,
                "selected_support_module_ids": ["support_module:查經互動模組"],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": ["support_module:查經互動模組"],
                "selected_routing_rule_id": "route_to_bible_study",
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "respond",
                    "target_service_block_id": "mode_bible_study",
                    "target_workflow_id": None,
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": ["support_module:查經互動模組"],
                },
                "reasoning_summary": ["semantic shadow inferred bible study from biblical guidance wording"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["turn_execution_plan"]["selected_routing_rule_id"], "route_to_life_application")
        self.assertIsNone(out["turn_execution_plan"].get("primary_support_module_scope"))
        self.assertIsNone(out["turn_execution_plan"].get("active_step_scope"))
        self.assertFalse(out["session_execution_state"].get("primary_support_module_id"))
        self.assertFalse(out["session_execution_state"].get("active_step_scope_id"))

    def test_grow_with_children_role_route_resolves_to_executable_target(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "最近在教養孩子時，我遇到的挑戰是…"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "intent_routed_interaction_logic",
                    "role_profiles": [
                        {
                            "role_id": "consultant",
                            "name": "Consultant",
                            "permitted_workflows": ["3x1_advice_workflow"],
                            "permitted_modules": [],
                        },
                        {
                            "role_id": "mentor",
                            "name": "Mentor",
                            "permitted_workflows": ["deep_analysis_workflow"],
                            "permitted_modules": [],
                        },
                    ],
                    "routing_rules": [
                        {
                            "rule_id": "route_behavior_to_consultant",
                            "priority": 2,
                            "trigger_keywords": ["挑戰", "困難", "怎麼辦"],
                            "target_type": "role",
                            "target_id": "consultant",
                        }
                    ],
                    "interaction_logic_blocks": [
                        {
                            "block_id": "five_role_mode_definition",
                            "logic_id": "five_role_mode_definition",
                            "title": "五重角色模式",
                        }
                    ],
                    "instruction_service_blocks": [
                        {
                            "block_id": "primary_workflow:互動模式與流程",
                            "block_type": "primary_workflow",
                            "title": "互動模式與流程",
                        }
                    ],
                    "instruction_procedures": [],
                    "procedure_steps": [],
                }
            },
            "instruction_workflows": [
                {
                    "id": "3x1_advice_workflow",
                    "title": "3×1 建議清單流程（快速回應模式）",
                    "workflow_name": "3×1 建議清單流程（快速回應模式）",
                    "triggers": [],
                    "steps": [
                        {"order": 1, "title": "教養技巧（父母角度）", "step_scope_id": "step:3x1_advice_workflow:1"}
                    ],
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": [],
            "procedure_steps": [],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "answer",
                "confidence": 0.93,
                "continue_current_scope": False,
                "selected_role_id": "consultant",
                "selected_workflow_id": None,
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "selected_routing_rule_id": "route_behavior_to_consultant",
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "respond",
                    "target_service_block_id": "five_role_mode_definition",
                    "target_workflow_id": None,
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [],
                },
                "reasoning_summary": ["route selected consultant role but left executable target unresolved"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["turn_execution_plan"]["selected_role_id"], "consultant")
        self.assertEqual(out["session_execution_state"]["active_role_id"], "consultant")
        self.assertEqual(out["instruction_workflow"]["id"], "3x1_advice_workflow")
        self.assertEqual(out["turn_execution_plan"]["primary_scope"]["scope_type"], "workflow")
        self.assertEqual(out["session_execution_state"].get("primary_scope_type"), "workflow")

    def test_planner_hybrid_active_persists_non_null_executable_state_for_parenting_role_route(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["instruction_understanding_mode"] = "hybrid_active"
        state["user_query"] = "\u9762\u5c0d\u5b69\u5b50\u6700\u8fd1\u7684\u884c\u70ba\u6311\u6230\uff0c\u6211\u8a72\u600e\u9ebc\u8fa6\uff1f"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "intent_routed_interaction_logic",
                    "default_workflow_id": None,
                    "role_profiles": [
                        {
                            "role_id": "role:consultant",
                            "name": "Consultant",
                            "allowed_workflow_ids": ["workflow:3x1\u5efa\u8b70\u6e05\u55ae\u6cd5"],
                        },
                        {
                            "role_id": "role:tutor",
                            "name": "Tutor",
                            "allowed_module_ids": ["support_module:\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44"],
                        },
                    ],
                    "routing_rules": [
                        {
                            "rule_id": "route:consultant",
                            "trigger_keywords": ["\u6311\u6230", "\u56f0\u96e3", "\u600e\u9ebc\u8fa6"],
                            "target_role_id": "role:consultant",
                        },
                        {
                            "rule_id": "route:tutor",
                            "trigger_keywords": ["\u7814\u7d93"],
                            "target_role_id": "role:tutor",
                        },
                    ],
                    "interaction_logic_blocks": [
                        {
                            "block_id": "logic:five_roles",
                            "title": "\u4e94\u91cd\u89d2\u8272\u6a21\u5f0f",
                        }
                    ],
                    "instruction_service_blocks": [
                        {
                            "block_id": "workflow:3x1\u5efa\u8b70\u6e05\u55ae\u6cd5",
                            "block_type": "primary_workflow",
                            "title": "3x1 \u5efa\u8b70\u6e05\u55ae\u6d41\u7a0b",
                        },
                        {
                            "block_id": "support_module:\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                            "block_type": "support_module",
                            "title": "\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                        },
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "procedure:consultant",
                            "service_block_id": "workflow:3x1\u5efa\u8b70\u6e05\u55ae\u6cd5",
                            "title": "3x1 \u5efa\u8b70\u6e05\u55ae\u6d41\u7a0b",
                        },
                        {
                            "procedure_id": "procedure:tutor",
                            "service_block_id": "support_module:\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                            "title": "\u67e5\u7d93\u4e92\u52d5\u6a21\u7d44",
                        },
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:consultant:1",
                            "procedure_id": "procedure:consultant",
                            "order": 1,
                            "title": "\u63d0\u4f9b\u4e09\u500b\u5efa\u8b70\u8207\u4e00\u500b\u7acb\u5373\u884c\u52d5",
                            "execution_mode": "interactive",
                        },
                        {
                            "step_id": "step:tutor:1",
                            "procedure_id": "procedure:tutor",
                            "order": 1,
                            "title": "\u7d30\u5bdf\u4e8b\u5be6",
                            "execution_mode": "interactive",
                        },
                    ],
                }
            }
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "parenting_support",
                "confidence": 0.92,
                "continue_current_scope": False,
                "selected_role_id": "role:consultant",
                "selected_workflow_id": None,
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "selected_routing_rule_id": "route:consultant",
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "respond",
                    "target_service_block_id": "logic:five_roles",
                    "target_workflow_id": None,
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [],
                },
                "reasoning_summary": ["role route should resolve to executable consultant workflow"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["session_execution_state"]["active_role_id"], "role:consultant")
        self.assertIsNotNone(out.get("instruction_workflow"))
        self.assertEqual(out["session_execution_state"]["active_service_block_type"], "primary_workflow")
        self.assertEqual(
            out["session_execution_state"]["active_service_block_id"],
            "workflow:3x1\u5efa\u8b70\u6e05\u55ae\u6cd5",
        )
        self.assertIsNotNone(out["session_execution_state"]["primary_scope_id"])
        self.assertIsNotNone(out["session_execution_state"]["active_step_scope_id"])

    def test_church_ministry_prompt_designer_starter_binds_clarification_workflow_from_default_workflow_alias(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = (
            "Please create an optimized ministry prompt from a topic or passage so people can better understand God's truth."
        )
        state["session_execution_state"] = {"active_workflow": "Church Ministry Prompt Designer"}
        state["full_instruction_text"] = (
            "Church Ministry Prompt Designer helps create ministry prompts from a topic or passage. "
            "When key variables are missing, first ask one clarification question before drafting the prompt."
        )
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "wf:interaction_logic_execution_flow",
                    "instruction_service_blocks": [
                        {
                            "block_id": "primary_workflow:interaction_logic_execution_flow",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                        }
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "procedure:interaction_logic_execution_flow",
                            "service_block_id": "primary_workflow:interaction_logic_execution_flow",
                            "title": "Interaction Logic & Execution Flow",
                            "is_default": False,
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:clarification",
                            "procedure_id": "procedure:interaction_logic_execution_flow",
                            "order": 0,
                            "title": "Clarify the Need",
                            "execution_mode": "interactive",
                        }
                    ],
                    "clarification_gate_rules": [],
                }
            },
            "instruction_workflows": [
                {
                    "id": "interaction_logic_execution_flow",
                    "title": "Interaction Logic & Execution Flow",
                    "workflow_name": "Interaction Logic & Execution Flow",
                    "triggers": [],
                    "steps": [
                        {
                            "order": 0,
                            "title": "Clarify the Need",
                            "step_scope_id": "step:clarification",
                            "resource_file": "Ministry_Discovery_Questions.md",
                        }
                    ],
                }
            ],
            "builder_instructions": (
                "Build ministry prompts from a topic or passage. Start with clarification when the prompt brief is underspecified."
            ),
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        self.assertTrue(out["turn_routing_classification"]["is_generation_request"])
        self.assertFalse(out["turn_routing_classification"]["skip_workflow_selection"])
        self.assertEqual(out["instruction_workflow"]["id"], "interaction_logic_execution_flow")
        self.assertEqual(out["instruction_step"]["order"], 0)
        self.assertEqual(out["session_execution_state"].get("active_workflow"), "Interaction Logic & Execution Flow")
        self.assertEqual(out["session_execution_state"].get("active_step_scope_id"), "step:clarification")

    def test_planner_hybrid_active_advances_church_ministry_clarification_when_workflow_ids_are_equivalent_aliases(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["instruction_understanding_mode"] = "hybrid_active"
        state["user_query"] = "給一般會眾，主題是基督裡的新生命"
        state["chat_history"] = [
            {
                "role": "assistant",
                "content": "請問這個 Prompt 主要是要給哪一類對象使用的呢？",
            }
        ]
        state["workflow_progress"] = {
            "workflow_id": "interaction_logic_execution_flow",
            "workflow_title": "Interaction Logic & Execution Flow",
            "step_order": 1,
            "step_title": "Clarification",
        }
        state["session_execution_state"] = {
            "primary_scope_id": "workflow:interaction_logic_execution_flow",
            "primary_scope_type": "workflow",
            "primary_scope_title": "Interaction Logic & Execution Flow",
            "active_mode": "interaction_logic_execution_flow",
            "active_workflow": "Interaction Logic & Execution Flow",
            "active_step_order": 1,
            "active_step_title": "Clarification",
            "active_step_scope_id": "step:clarification",
            "execution_status": "guiding",
        }
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "wf:interaction_logic_execution_flow",
                    "instruction_service_blocks": [
                        {
                            "block_id": "primary_workflow:interaction_logic_execution_flow",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                        }
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "procedure:interaction_logic_execution_flow",
                            "service_block_id": "primary_workflow:interaction_logic_execution_flow",
                            "title": "Interaction Logic & Execution Flow",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:clarification",
                            "procedure_id": "procedure:interaction_logic_execution_flow",
                            "order": 1,
                            "title": "Clarification",
                            "execution_mode": "interactive",
                        },
                        {
                            "step_id": "step:core_workflow_execution",
                            "procedure_id": "procedure:interaction_logic_execution_flow",
                            "order": 2,
                            "title": "Core Workflow",
                            "execution_mode": "bundled",
                            "bundled_step_ids": ["step:core_workflow_execution"],
                            "bundled_resource_refs": ["template_library.md"],
                        },
                    ],
                    "clarification_gate_rules": [],
                }
            },
            "instruction_workflows": [
                {
                    "id": "wf:interaction_logic_execution_flow",
                    "title": "Interaction Logic & Execution Flow",
                    "workflow_name": "Interaction Logic & Execution Flow",
                    "triggers": [],
                    "steps": [
                        {
                            "order": 1,
                            "title": "Clarification",
                            "step_scope_id": "step:clarification",
                        },
                        {
                            "order": 2,
                            "title": "Core Workflow",
                            "step_scope_id": "step:core_workflow_execution",
                            "resource_file": "template_library.md",
                        },
                    ],
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["instruction_step"]["order"], 2)
        self.assertEqual(out["session_execution_state"].get("active_step_scope_id"), "step:core_workflow_execution")
        self.assertEqual(out["session_execution_state"].get("active_execution_mode"), "bundled")

    def test_planner_hybrid_active_church_ministry_clarification_step_does_not_fallback_to_phase_docs(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["instruction_understanding_mode"] = "hybrid_active"
        state["user_query"] = "準備以弗所書第一章的查經分享材料"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "primary_workflow:interaction_logic_execution_flow",
                    "instruction_service_blocks": [
                        {
                            "block_id": "primary_workflow:interaction_logic_execution_flow",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                        }
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "service_block_id": "primary_workflow:interaction_logic_execution_flow",
                            "title": "Interaction Logic & Execution Flow",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:interaction_logic_execution_flow:1",
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "order": 1,
                            "title": "Clarification",
                            "execution_mode": "interactive",
                            "resource_refs": [],
                        },
                        {
                            "step_id": "step:interaction_logic_execution_flow:2",
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "order": 2,
                            "title": "核心流程（Workflow Execution）",
                            "execution_mode": "bundled",
                            "resource_refs": ["template_library.md", "dynamic_prompt_optimizer.md"],
                            "bundled_step_ids": ["step:interaction_logic_execution_flow:2"],
                        },
                    ],
                    "clarification_gate_rules": [],
                }
            },
            "instruction_workflows": [
                {
                    "id": "primary_workflow:interaction_logic_execution_flow",
                    "title": "Interaction Logic & Execution Flow",
                    "workflow_name": "Interaction Logic & Execution Flow",
                    "triggers": [],
                    "steps": [
                        {
                            "order": 1,
                            "title": "Clarification",
                            "step_scope_id": "step:interaction_logic_execution_flow:1",
                        },
                        {
                            "order": 2,
                            "title": "核心流程（Workflow Execution）",
                            "step_scope_id": "step:interaction_logic_execution_flow:2",
                            "resource_file": "template_library.md",
                        },
                    ],
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
            "instruction_resources": [
                {"resource_id": "template_library", "filename": "template_library.md", "domain": "output_template"},
                {"resource_id": "prompt_rules", "filename": "prompt_design_rules.md", "domain": "instruction_source"},
                {"resource_id": "delimiter_rules", "filename": "delimiter_rules.md", "domain": "instruction_source"},
                {"resource_id": "optimization_strategy", "filename": "Optimization Strategy Library.md", "domain": "instruction_source"},
                {"resource_id": "suite_type", "filename": "suite_type_mapping.md", "domain": "instruction_source"},
                {"resource_id": "suite_tool", "filename": "suite_tool_mapping.md", "domain": "instruction_source"},
                {"resource_id": "dpo", "filename": "dynamic_prompt_optimizer.md", "domain": "instruction_source"},
            ],
            "phase_resource_bindings": [
                {
                    "binding_id": "phase:1_knowledge_modules_知識模組",
                    "title": "1 Knowledge Modules",
                    "trigger_type": "phase",
                    "binding_mode": "multi_required",
                    "scope_id": "primary_workflow:interaction_logic_execution_flow",
                    "resource_ids": ["template_library", "prompt_rules", "delimiter_rules", "optimization_strategy", "suite_type", "suite_tool"],
                    "resource_kinds": ["template_resource", "instruction_resource", "instruction_resource", "instruction_resource", "instruction_resource", "instruction_resource"],
                    "activation_reason": "knowledge module phase",
                },
                {
                    "binding_id": "phase:2_instruction_modules_指令模組",
                    "title": "2 Instruction Modules",
                    "trigger_type": "phase",
                    "binding_mode": "multi_required",
                    "scope_id": "primary_workflow:interaction_logic_execution_flow",
                    "resource_ids": ["dpo"],
                    "resource_kinds": ["instruction_resource"],
                    "activation_reason": "instruction module phase",
                },
                {
                    "binding_id": "phase:step_1_clarification_單一問題規則",
                    "title": "Step 1 Clarification",
                    "trigger_type": "phase",
                    "binding_mode": "none",
                    "scope_id": "step:interaction_logic_execution_flow:1",
                    "activation_reason": "clarification phase",
                },
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        instruction_requests = [
            item
            for item in out["turn_execution_plan"]["resource_requests"]
            if item.get("resource_role") == "instruction_source"
        ]
        template_requests = [
            item
            for item in out["turn_execution_plan"]["resource_requests"]
            if item.get("resource_role") == "output_template"
        ]
        self.assertEqual(instruction_requests, [])
        self.assertEqual(template_requests, [])
        self.assertEqual(
            out["session_execution_state"]["active_step_scope_id"],
            "step:interaction_logic_execution_flow:1",
        )

    def test_planner_hybrid_active_church_ministry_core_step_loads_only_explicit_step_docs(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["instruction_understanding_mode"] = "hybrid_active"
        state["user_query"] = "青少年小組，請直接產生 prompt"
        state["chat_history"] = [{"role": "assistant", "content": "請問這次查經分享的對象主要是誰？"}]
        state["workflow_progress"] = {
            "workflow_id": "interaction_logic_execution_flow",
            "workflow_title": "Interaction Logic & Execution Flow",
            "step_order": 1,
            "step_title": "Clarification",
        }
        state["session_execution_state"] = {
            "primary_scope_id": "workflow:interaction_logic_execution_flow",
            "primary_scope_type": "workflow",
            "primary_scope_title": "Interaction Logic & Execution Flow",
            "active_mode": "interaction_logic_execution_flow",
            "active_workflow": "Interaction Logic & Execution Flow",
            "active_step_order": 1,
            "active_step_title": "Clarification",
            "active_step_scope_id": "step:interaction_logic_execution_flow:1",
            "execution_status": "guiding",
        }
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "primary_workflow:interaction_logic_execution_flow",
                    "instruction_service_blocks": [
                        {
                            "block_id": "primary_workflow:interaction_logic_execution_flow",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                        }
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "service_block_id": "primary_workflow:interaction_logic_execution_flow",
                            "title": "Interaction Logic & Execution Flow",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:interaction_logic_execution_flow:1",
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "order": 1,
                            "title": "Clarification",
                            "execution_mode": "interactive",
                            "resource_refs": [],
                        },
                        {
                            "step_id": "step:interaction_logic_execution_flow:2",
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "order": 2,
                            "title": "核心流程（Workflow Execution）",
                            "execution_mode": "bundled",
                            "resource_refs": ["template_library.md", "dynamic_prompt_optimizer.md"],
                            "bundled_step_ids": ["step:interaction_logic_execution_flow:2"],
                        },
                    ],
                    "clarification_gate_rules": [],
                }
            },
            "instruction_workflows": [
                {
                    "id": "primary_workflow:interaction_logic_execution_flow",
                    "title": "Interaction Logic & Execution Flow",
                    "workflow_name": "Interaction Logic & Execution Flow",
                    "triggers": [],
                    "steps": [
                        {"order": 1, "title": "Clarification", "step_scope_id": "step:interaction_logic_execution_flow:1"},
                        {
                            "order": 2,
                            "title": "核心流程（Workflow Execution）",
                            "step_scope_id": "step:interaction_logic_execution_flow:2",
                            "resource_file": "template_library.md",
                        },
                    ],
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
            "instruction_resources": [
                {"resource_id": "template_library", "filename": "template_library.md", "domain": "output_template"},
                {"resource_id": "prompt_rules", "filename": "prompt_design_rules.md", "domain": "instruction_source"},
                {"resource_id": "delimiter_rules", "filename": "delimiter_rules.md", "domain": "instruction_source"},
                {"resource_id": "optimization_strategy", "filename": "Optimization Strategy Library.md", "domain": "instruction_source"},
                {"resource_id": "suite_type", "filename": "suite_type_mapping.md", "domain": "instruction_source"},
                {"resource_id": "suite_tool", "filename": "suite_tool_mapping.md", "domain": "instruction_source"},
                {"resource_id": "dpo", "filename": "dynamic_prompt_optimizer.md", "domain": "instruction_source"},
            ],
            "phase_resource_bindings": [
                {
                    "binding_id": "phase:1_knowledge_modules_知識模組",
                    "title": "1 Knowledge Modules",
                    "trigger_type": "phase",
                    "binding_mode": "multi_required",
                    "scope_id": "primary_workflow:interaction_logic_execution_flow",
                    "resource_ids": ["template_library", "prompt_rules", "delimiter_rules", "optimization_strategy", "suite_type", "suite_tool"],
                    "resource_kinds": ["template_resource", "instruction_resource", "instruction_resource", "instruction_resource", "instruction_resource", "instruction_resource"],
                    "activation_reason": "knowledge module phase",
                },
                {
                    "binding_id": "phase:2_instruction_modules_指令模組",
                    "title": "2 Instruction Modules",
                    "trigger_type": "phase",
                    "binding_mode": "multi_required",
                    "scope_id": "primary_workflow:interaction_logic_execution_flow",
                    "resource_ids": ["dpo"],
                    "resource_kinds": ["instruction_resource"],
                    "activation_reason": "instruction module phase",
                },
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "church_ministry",
                "confidence": 0.97,
                "continue_current_scope": True,
                "selected_role_id": None,
                "selected_workflow_id": "primary_workflow:interaction_logic_execution_flow",
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "clarification_status": {"is_active": False, "is_complete": True, "missing_slots": [], "filled_slot_names": ["audience"]},
                "next_action": {
                    "action_type": "guide",
                    "target_service_block_id": "primary_workflow:interaction_logic_execution_flow",
                    "target_workflow_id": "primary_workflow:interaction_logic_execution_flow",
                    "target_step_id": "step:interaction_logic_execution_flow:2",
                    "bundled_step_ids": ["step:interaction_logic_execution_flow:2"],
                    "module_queue": [],
                },
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        request_filenames = [
            item.get("filename")
            for item in out["turn_execution_plan"]["resource_requests"]
            if item.get("resource_role") in {"instruction_source", "output_template"}
        ]
        self.assertCountEqual(request_filenames, ["template_library.md", "dynamic_prompt_optimizer.md"])
        self.assertEqual(
            out["session_execution_state"]["active_step_scope_id"],
            "step:interaction_logic_execution_flow:2",
        )

    def test_planner_hybrid_active_church_ministry_input_gate_collapses_to_clarification_step(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["instruction_understanding_mode"] = "hybrid_active"
        state["user_query"] = "準備以弗所書第一章的查經分享材料"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "primary_workflow:interaction_logic_execution_flow",
                    "instruction_service_blocks": [
                        {
                            "block_id": "primary_workflow:interaction_logic_execution_flow",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                        },
                        {
                            "block_id": "followup_module:optimization_module",
                            "block_type": "followup_module",
                            "title": "Optimization Module（Prompt 優化模組）",
                        },
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "service_block_id": "primary_workflow:interaction_logic_execution_flow",
                            "title": "Interaction Logic & Execution Flow",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:interaction_logic_execution_flow:0",
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "order": 0,
                            "title": "Step 0：輸入完整度判斷（Input Gate）",
                            "execution_mode": "interactive",
                            "resource_refs": [],
                        },
                        {
                            "step_id": "step:interaction_logic_execution_flow:1",
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "order": 1,
                            "title": "Clarification",
                            "execution_mode": "interactive",
                            "resource_refs": [],
                        },
                        {
                            "step_id": "step:interaction_logic_execution_flow:2",
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "order": 2,
                            "title": "核心流程（Workflow Execution）",
                            "execution_mode": "bundled",
                            "resource_refs": ["template_library.md", "dynamic_prompt_optimizer.md"],
                            "bundled_step_ids": ["step:interaction_logic_execution_flow:2"],
                        },
                    ],
                    "clarification_gate_rules": [],
                }
            },
            "instruction_workflows": [
                {
                    "id": "primary_workflow:interaction_logic_execution_flow",
                    "title": "Interaction Logic & Execution Flow",
                    "workflow_name": "Interaction Logic & Execution Flow",
                    "triggers": [],
                    "steps": [
                        {
                            "order": 0,
                            "title": "Step 0：輸入完整度判斷（Input Gate）",
                            "step_scope_id": "step:interaction_logic_execution_flow:0",
                        },
                        {
                            "order": 1,
                            "title": "Clarification",
                            "step_scope_id": "step:interaction_logic_execution_flow:1",
                        },
                        {
                            "order": 2,
                            "title": "核心流程（Workflow Execution）",
                            "step_scope_id": "step:interaction_logic_execution_flow:2",
                            "resource_file": "template_library.md",
                        },
                    ],
                }
            ],
            "instruction_blocks": [
                {
                    "block_id": "step:interaction_logic_execution_flow:0",
                    "block_type": "step",
                    "title": "輸入完整度判斷（Input Gate）",
                    "body_text": "關鍵變數：theme, passage, audience, goal\nIF 提供變數 ≥ 3：\n→ 進入 Step 2（核心流程）\nELSE：\n→ 進入 Step 1（Clarification）",
                    "linked_mode_id": "primary_workflow:interaction_logic_execution_flow",
                    "linked_step_order": 0,
                    "linked_step_title": "輸入完整度判斷（Input Gate）",
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["instruction_step"]["order"], 1)
        self.assertEqual(out["session_execution_state"]["active_step_scope_id"], "step:interaction_logic_execution_flow:1")
        self.assertEqual(out["session_execution_state"]["active_service_block_type"], "primary_workflow")
        self.assertNotEqual(
            out["session_execution_state"].get("active_service_block_id"),
            "followup_module:optimization_module",
        )

    def test_planner_hybrid_active_church_ministry_input_gate_collapses_to_core_step_without_premature_followup(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["instruction_understanding_mode"] = "hybrid_active"
        state["user_query"] = "核心目標（goal）是幫助青年認識在基督裡的屬靈福氣"
        state["chat_history"] = [
            {"role": "assistant", "content": "請問這次查經的主要對象是誰？"},
            {"role": "user", "content": "準備以弗所書第一章的查經分享材料"},
            {"role": "assistant", "content": "請提供主要對象（audience）。"},
            {"role": "user", "content": "查經的主要對象（audience）是青年團契"},
        ]
        state["workflow_progress"] = {
            "workflow_id": "primary_workflow:interaction_logic_execution_flow",
            "workflow_title": "Interaction Logic & Execution Flow",
            "step_order": 0,
            "step_title": "Step 0：輸入完整度判斷（Input Gate）",
        }
        state["session_execution_state"] = {
            "primary_scope_id": "workflow:interaction_logic_execution_flow",
            "primary_scope_type": "workflow",
            "primary_scope_title": "Interaction Logic & Execution Flow",
            "active_mode": "interaction_logic_execution_flow",
            "active_workflow": "Interaction Logic & Execution Flow",
            "active_step_order": 0,
            "active_step_title": "Step 0：輸入完整度判斷（Input Gate）",
            "active_step_scope_id": "step:interaction_logic_execution_flow:0",
            "active_execution_mode": "bundled",
            "bundled_execution_completed": True,
            "active_module_queue": ["step:interaction_logic_execution_flow:2"],
            "primary_support_module_id": "step:interaction_logic_execution_flow:2",
        }
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "primary_workflow:interaction_logic_execution_flow",
                    "instruction_service_blocks": [
                        {
                            "block_id": "primary_workflow:interaction_logic_execution_flow",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                        },
                        {
                            "block_id": "followup_module:optimization_module",
                            "block_type": "followup_module",
                            "title": "Optimization Module（Prompt 優化模組）",
                        },
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "service_block_id": "primary_workflow:interaction_logic_execution_flow",
                            "title": "Interaction Logic & Execution Flow",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:interaction_logic_execution_flow:0",
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "order": 0,
                            "title": "Step 0：輸入完整度判斷（Input Gate）",
                            "execution_mode": "interactive",
                            "resource_refs": [],
                        },
                        {
                            "step_id": "step:interaction_logic_execution_flow:1",
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "order": 1,
                            "title": "Clarification",
                            "execution_mode": "interactive",
                            "resource_refs": [],
                        },
                        {
                            "step_id": "step:interaction_logic_execution_flow:2",
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "order": 2,
                            "title": "核心流程（Workflow Execution）",
                            "execution_mode": "bundled",
                            "resource_refs": ["template_library.md", "dynamic_prompt_optimizer.md"],
                            "bundled_step_ids": ["step:interaction_logic_execution_flow:2"],
                        },
                    ],
                    "clarification_gate_rules": [],
                }
            },
            "instruction_workflows": [
                {
                    "id": "primary_workflow:interaction_logic_execution_flow",
                    "title": "Interaction Logic & Execution Flow",
                    "workflow_name": "Interaction Logic & Execution Flow",
                    "triggers": [],
                    "steps": [
                        {
                            "order": 0,
                            "title": "Step 0：輸入完整度判斷（Input Gate）",
                            "step_scope_id": "step:interaction_logic_execution_flow:0",
                        },
                        {
                            "order": 1,
                            "title": "Clarification",
                            "step_scope_id": "step:interaction_logic_execution_flow:1",
                        },
                        {
                            "order": 2,
                            "title": "核心流程（Workflow Execution）",
                            "step_scope_id": "step:interaction_logic_execution_flow:2",
                            "resource_file": "template_library.md",
                        },
                    ],
                }
            ],
            "instruction_blocks": [
                {
                    "block_id": "step:interaction_logic_execution_flow:0",
                    "block_type": "step",
                    "title": "輸入完整度判斷（Input Gate）",
                    "body_text": "關鍵變數：theme, passage, audience, goal\nIF 提供變數 ≥ 3：\n→ 進入 Step 2（核心流程）\nELSE：\n→ 進入 Step 1（Clarification）",
                    "linked_mode_id": "primary_workflow:interaction_logic_execution_flow",
                    "linked_step_order": 0,
                    "linked_step_title": "輸入完整度判斷（Input Gate）",
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
            "instruction_resources": [
                {"resource_id": "template_library", "filename": "template_library.md", "domain": "output_template"},
                {"resource_id": "dpo", "filename": "dynamic_prompt_optimizer.md", "domain": "instruction_source"},
                {"resource_id": "opt", "filename": "Optimization Strategy Library.md", "domain": "instruction_source"},
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "create_prompt",
                "confidence": 0.92,
                "continue_current_scope": True,
                "selected_role_id": "role:church_ministry_prompt_designer",
                "selected_workflow_id": "primary_workflow:interaction_logic_execution_flow",
                "selected_support_module_ids": ["step:interaction_logic_execution_flow:2"],
                "selected_followup_module_ids": ["followup_module:optimization_module"],
                "selected_supplementary_workflow_id": None,
                "module_sequence": ["step:interaction_logic_execution_flow:2"],
                "clarification_status": {"is_active": False, "is_complete": True, "missing_slots": [], "filled_slot_names": ["theme", "passage", "audience", "goal"]},
                "next_action": {
                    "action_type": "guide",
                    "target_workflow_id": "primary_workflow:interaction_logic_execution_flow",
                    "target_service_block_id": None,
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": ["step:interaction_logic_execution_flow:2"],
                },
                "reasoning_summary": ["enough variables are present; planner should enter core workflow before any optimization followup"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["instruction_step"]["order"], 2)
        self.assertEqual(out["session_execution_state"]["active_step_scope_id"], "step:interaction_logic_execution_flow:2")
        self.assertEqual(out["session_execution_state"]["active_service_block_type"], "primary_workflow")
        self.assertEqual(
            out["session_execution_state"]["active_service_block_id"],
            "primary_workflow:interaction_logic_execution_flow",
        )
        self.assertNotEqual(
            out["session_execution_state"].get("active_service_block_id"),
            "followup_module:optimization_module",
        )

    def test_planner_hybrid_active_shadow_target_step_cannot_bypass_input_gate_when_explicit_slots_are_insufficient(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["instruction_understanding_mode"] = "hybrid_active"
        state["user_query"] = "準備以弗所書第一章的查經分享材料"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "primary_workflow:interaction_logic_execution_flow",
                    "instruction_service_blocks": [
                        {
                            "block_id": "primary_workflow:interaction_logic_execution_flow",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                        }
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "service_block_id": "primary_workflow:interaction_logic_execution_flow",
                            "title": "Interaction Logic & Execution Flow",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:interaction_logic_execution_flow:0",
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "order": 0,
                            "title": "Step 0：輸入完整度判斷（Input Gate）",
                            "execution_mode": "interactive",
                            "resource_refs": [],
                        },
                        {
                            "step_id": "step:interaction_logic_execution_flow:1",
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "order": 1,
                            "title": "Clarification",
                            "execution_mode": "interactive",
                            "resource_refs": [],
                        },
                        {
                            "step_id": "step:interaction_logic_execution_flow:2",
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "order": 2,
                            "title": "核心流程（Workflow Execution）",
                            "execution_mode": "bundled",
                            "resource_refs": ["template_library.md", "dynamic_prompt_optimizer.md"],
                            "bundled_step_ids": ["step:interaction_logic_execution_flow:2"],
                        },
                    ],
                    "clarification_gate_rules": [],
                }
            },
            "instruction_workflows": [
                {
                    "id": "primary_workflow:interaction_logic_execution_flow",
                    "title": "Interaction Logic & Execution Flow",
                    "workflow_name": "Interaction Logic & Execution Flow",
                    "triggers": [],
                    "steps": [
                        {"order": 0, "title": "Step 0：輸入完整度判斷（Input Gate）", "step_scope_id": "step:interaction_logic_execution_flow:0"},
                        {"order": 1, "title": "Clarification", "step_scope_id": "step:interaction_logic_execution_flow:1"},
                        {"order": 2, "title": "核心流程（Workflow Execution）", "step_scope_id": "step:interaction_logic_execution_flow:2", "resource_file": "template_library.md"},
                    ],
                }
            ],
            "instruction_blocks": [
                {
                    "block_id": "step:interaction_logic_execution_flow:0",
                    "block_type": "step",
                    "title": "輸入完整度判斷（Input Gate）",
                    "body_text": "關鍵變數：theme, passage, audience, goal\nIF 提供變數 ≥ 3：\n→ 進入 Step 2（核心流程）\nELSE：\n→ 進入 Step 1（Clarification）",
                    "linked_mode_id": "primary_workflow:interaction_logic_execution_flow",
                    "linked_step_order": 0,
                    "linked_step_title": "輸入完整度判斷（Input Gate）",
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = "這是一個給青年團契、要幫助他們理解真理的請求：" + state["user_query"]
            output["contextualQuery"] = output["normalizedQuery"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "create_prompt",
                "confidence": 0.92,
                "continue_current_scope": True,
                "selected_role_id": "role:church_ministry_prompt_designer",
                "selected_workflow_id": "primary_workflow:interaction_logic_execution_flow",
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "clarification_status": {"is_active": False, "is_complete": True, "missing_slots": [], "filled_slot_names": ["theme", "passage", "audience", "goal"]},
                "next_action": {
                    "action_type": "guide",
                    "target_workflow_id": "primary_workflow:interaction_logic_execution_flow",
                    "target_service_block_id": None,
                    "target_step_id": "step:interaction_logic_execution_flow:2",
                    "bundled_step_ids": [],
                    "module_queue": [],
                },
                "reasoning_summary": ["shadow attempted to jump directly to core workflow"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["instruction_step"]["order"], 1)
        self.assertEqual(out["session_execution_state"]["active_step_scope_id"], "step:interaction_logic_execution_flow:1")
        self.assertEqual(out["session_execution_state"]["active_service_block_type"], "primary_workflow")

    def test_planner_hybrid_active_clarification_slot_persistence_uses_raw_user_query_not_llm_expanded_query(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["instruction_understanding_mode"] = "hybrid_active"
        state["user_query"] = "準備以弗所書第一章的查經分享材料"
        state["workflow_progress"] = {
            "workflow_id": "primary_workflow:interaction_logic_execution_flow",
            "workflow_title": "Interaction Logic & Execution Flow",
            "step_order": 1,
            "step_title": "Clarification",
        }
        state["session_execution_state"] = {
            "active_step_scope_id": "step:interaction_logic_execution_flow:1",
            "clarification_gate_status": {},
        }
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "primary_workflow:interaction_logic_execution_flow",
                    "instruction_service_blocks": [
                        {
                            "block_id": "primary_workflow:interaction_logic_execution_flow",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                        }
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "service_block_id": "primary_workflow:interaction_logic_execution_flow",
                            "title": "Interaction Logic & Execution Flow",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:interaction_logic_execution_flow:1",
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "order": 1,
                            "title": "Clarification",
                            "execution_mode": "interactive",
                            "resource_refs": [],
                        },
                        {
                            "step_id": "step:interaction_logic_execution_flow:2",
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "order": 2,
                            "title": "核心流程（Workflow Execution）",
                            "execution_mode": "bundled",
                            "resource_refs": ["template_library.md", "dynamic_prompt_optimizer.md"],
                            "bundled_step_ids": ["step:interaction_logic_execution_flow:2"],
                        },
                    ],
                    "clarification_gate_rules": [],
                }
            },
            "instruction_workflows": [
                {
                    "id": "primary_workflow:interaction_logic_execution_flow",
                    "title": "Interaction Logic & Execution Flow",
                    "workflow_name": "Interaction Logic & Execution Flow",
                    "triggers": [],
                    "steps": [
                        {"order": 1, "title": "Clarification", "step_scope_id": "step:interaction_logic_execution_flow:1"},
                        {"order": 2, "title": "核心流程（Workflow Execution）", "step_scope_id": "step:interaction_logic_execution_flow:2", "resource_file": "template_library.md"},
                    ],
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = "請為青年團契準備以弗所書第一章查經分享材料，幫助他們更深認識真理"
            output["contextualQuery"] = output["normalizedQuery"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        filled = out["session_execution_state"]["clarification_gate_status"]["filled_slots_map"]
        self.assertTrue(filled["passage"])
        self.assertTrue(filled["theme"])
        self.assertFalse(filled.get("audience"))
        self.assertFalse(filled.get("goal"))

    def test_planner_hybrid_active_updates_clarification_gate_status_from_current_turn_slot_signals(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["instruction_understanding_mode"] = "hybrid_active"
        state["user_query"] = "核心目標（goal）是幫助青年認識在基督裡的屬靈福氣"
        state["workflow_progress"] = {
            "workflow_id": "primary_workflow:interaction_logic_execution_flow",
            "workflow_title": "Interaction Logic & Execution Flow",
            "step_order": 1,
            "step_title": "Clarification",
        }
        state["session_execution_state"] = {
            "active_step_scope_id": "step:interaction_logic_execution_flow:1",
            "clarification_gate_status": {"filled_slots_map": {"passage": True, "audience": True}},
        }
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "primary_workflow:interaction_logic_execution_flow",
                    "instruction_service_blocks": [
                        {
                            "block_id": "primary_workflow:interaction_logic_execution_flow",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                        }
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "service_block_id": "primary_workflow:interaction_logic_execution_flow",
                            "title": "Interaction Logic & Execution Flow",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:interaction_logic_execution_flow:1",
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "order": 1,
                            "title": "Clarification",
                            "execution_mode": "interactive",
                            "resource_refs": [],
                        },
                        {
                            "step_id": "step:interaction_logic_execution_flow:2",
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "order": 2,
                            "title": "核心流程（Workflow Execution）",
                            "execution_mode": "bundled",
                            "resource_refs": ["template_library.md", "dynamic_prompt_optimizer.md"],
                            "bundled_step_ids": ["step:interaction_logic_execution_flow:2"],
                        },
                    ],
                    "clarification_gate_rules": [],
                }
            },
            "instruction_workflows": [
                {
                    "id": "primary_workflow:interaction_logic_execution_flow",
                    "title": "Interaction Logic & Execution Flow",
                    "workflow_name": "Interaction Logic & Execution Flow",
                    "triggers": [],
                    "steps": [
                        {"order": 1, "title": "Clarification", "step_scope_id": "step:interaction_logic_execution_flow:1"},
                        {
                            "order": 2,
                            "title": "核心流程（Workflow Execution）",
                            "step_scope_id": "step:interaction_logic_execution_flow:2",
                            "resource_file": "template_library.md",
                        },
                    ],
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        filled = out["session_execution_state"]["clarification_gate_status"]["filled_slots_map"]
        self.assertTrue(filled["passage"])
        self.assertTrue(filled["audience"])
        self.assertTrue(filled["goal"])

    def test_planner_hybrid_active_church_ministry_advances_from_clarification_when_goal_slot_arrives(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["instruction_understanding_mode"] = "hybrid_active"
        state["user_query"] = "核心目標（goal）是幫助青年認識在基督裡的屬靈福氣"
        state["chat_history"] = [
            {"role": "assistant", "content": "請問這次查經分享的對象主要是誰？"},
            {"role": "user", "content": "準備以弗所書第一章的查經分享材料"},
            {"role": "assistant", "content": "請提供主要對象（audience）。"},
            {"role": "user", "content": "對象主要是小組長訓練"},
        ]
        state["workflow_progress"] = {
            "workflow_id": "primary_workflow:interaction_logic_execution_flow",
            "workflow_title": "Interaction Logic & Execution Flow",
            "step_order": 1,
            "step_title": "Clarification",
        }
        state["session_execution_state"] = {
            "primary_scope_id": "workflow:interaction_logic_execution_flow",
            "primary_scope_type": "workflow",
            "primary_scope_title": "Interaction Logic & Execution Flow",
            "active_mode": "interaction_logic_execution_flow",
            "active_workflow": "Interaction Logic & Execution Flow",
            "active_step_order": 1,
            "active_step_title": "Clarification",
            "active_step_scope_id": "step:interaction_logic_execution_flow:1",
            "clarification_gate_status": {
                "filled_slots_map": {
                    "passage": True,
                    "audience": True,
                }
            },
        }
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "primary_workflow:interaction_logic_execution_flow",
                    "instruction_service_blocks": [
                        {
                            "block_id": "primary_workflow:interaction_logic_execution_flow",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                        }
                    ],
                    "instruction_procedures": [
                        {
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "service_block_id": "primary_workflow:interaction_logic_execution_flow",
                            "title": "Interaction Logic & Execution Flow",
                        }
                    ],
                    "procedure_steps": [
                        {
                            "step_id": "step:interaction_logic_execution_flow:1",
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "order": 1,
                            "title": "Clarification",
                            "execution_mode": "interactive",
                            "resource_refs": [],
                        },
                        {
                            "step_id": "step:interaction_logic_execution_flow:2",
                            "procedure_id": "primary_workflow:interaction_logic_execution_flow",
                            "order": 2,
                            "title": "核心流程（Workflow Execution）",
                            "execution_mode": "bundled",
                            "resource_refs": ["template_library.md", "dynamic_prompt_optimizer.md"],
                            "bundled_step_ids": ["step:interaction_logic_execution_flow:2"],
                        },
                    ],
                    "clarification_gate_rules": [],
                }
            },
            "instruction_workflows": [
                {
                    "id": "primary_workflow:interaction_logic_execution_flow",
                    "title": "Interaction Logic & Execution Flow",
                    "workflow_name": "Interaction Logic & Execution Flow",
                    "triggers": [],
                    "steps": [
                        {"order": 1, "title": "Clarification", "step_scope_id": "step:interaction_logic_execution_flow:1"},
                        {
                            "order": 2,
                            "title": "核心流程（Workflow Execution）",
                            "step_scope_id": "step:interaction_logic_execution_flow:2",
                            "resource_file": "template_library.md",
                        },
                    ],
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_service_blocks"]
            ),
            "instruction_procedures": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["instruction_procedures"]
            ),
            "procedure_steps": list(
                state["template_registry"]["compiled_instruction_understanding"]["hybrid_instruction_runtime_model"]["procedure_steps"]
            ),
            "instruction_resources": [
                {"resource_id": "template_library", "filename": "template_library.md", "domain": "output_template"},
                {"resource_id": "dpo", "filename": "dynamic_prompt_optimizer.md", "domain": "instruction_source"},
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["instruction_step"]["order"], 2)
        self.assertEqual(out["session_execution_state"]["active_step_scope_id"], "step:interaction_logic_execution_flow:2")
        self.assertEqual(out["session_execution_state"]["active_service_block_type"], "primary_workflow")

    def test_planner_hybrid_active_sets_primary_support_module_from_semantic_module_queue(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "Help me design the use case"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "default_workflow_id": "workflow:design",
                    "instruction_service_blocks": [
                        {"block_id": "workflow:design", "block_type": "primary_workflow", "title": "Design Workflow", "is_default": True},
                        {"block_id": "module:use-case", "block_type": "support_module", "title": "Use Case Module"},
                    ],
                    "instruction_procedures": [],
                    "procedure_steps": [],
                }
            },
            "instruction_workflows": [
                {
                    "id": "workflow:design",
                    "title": "Design Workflow",
                    "workflow_name": "Design Workflow",
                    "triggers": [],
                    "steps": [{"order": 1, "title": "Design Step", "resource_file": "design.md"}],
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "support_modules": [
                {
                    "module_id": "module:use-case",
                    "title": "Use Case Module",
                    "resource_ids": ["resource:use-case"],
                }
            ],
            "instruction_resources": [
                {
                    "resource_id": "resource:use-case",
                    "filename": "use_case.md",
                    "domain": "instruction_source",
                    "title": "Use Case Guide",
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "use_case_design",
                "confidence": 0.92,
                "continue_current_scope": False,
                "selected_role_id": None,
                "selected_workflow_id": "workflow:design",
                "selected_support_module_ids": ["module:use-case"],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": ["module:use-case"],
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "select_module",
                    "target_service_block_id": "workflow:design",
                    "target_workflow_id": "workflow:design",
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": ["module:use-case"],
                },
                "reasoning_summary": ["activate use case module first"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["turn_execution_plan"]["primary_support_module_scope"]["scope_id"], "module:use-case")
        self.assertEqual(out["session_execution_state"]["primary_support_module_id"], "module:use-case")

    def test_planner_hybrid_active_prefers_semantic_instruction_module_over_legacy_keyword_match(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "observation checklist please"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "default_workflow_id": "workflow:design",
                    "instruction_service_blocks": [
                        {"block_id": "workflow:design", "block_type": "primary_workflow", "title": "Design Workflow", "is_default": True},
                        {"block_id": "module:use-case", "block_type": "support_module", "title": "Use Case Module"},
                    ],
                    "instruction_procedures": [],
                    "procedure_steps": [],
                }
            },
            "instruction_workflows": [
                {
                    "id": "workflow:design",
                    "title": "Design Workflow",
                    "workflow_name": "Design Workflow",
                    "triggers": [],
                    "steps": [],
                }
            ],
            "instruction_modules": [
                {
                    "id": "module:observation",
                    "title": "Observation Module",
                    "primary_resource": "observation.md",
                    "keywords": ["observation", "checklist"],
                },
                {
                    "id": "module:use-case",
                    "title": "Use Case Module",
                    "primary_resource": "use_case.md",
                    "keywords": ["use case"],
                },
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "design_support",
                "confidence": 0.96,
                "continue_current_scope": False,
                "selected_role_id": None,
                "selected_workflow_id": "workflow:design",
                "selected_support_module_ids": ["module:use-case"],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": ["module:use-case"],
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "select_module",
                    "target_service_block_id": "workflow:design",
                    "target_workflow_id": "workflow:design",
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": ["module:use-case"],
                },
                "reasoning_summary": ["semantic module selection should override keyword match"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["instruction_module"]["id"], "module:use-case")
        self.assertEqual(out["instruction_resource"], "use_case.md")

    def test_planner_hybrid_active_uses_followup_module_ids_when_module_sequence_missing(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "Please provide the follow-up wrap-up"
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "default_workflow_id": "workflow:design",
                    "instruction_service_blocks": [
                        {"block_id": "workflow:design", "block_type": "primary_workflow", "title": "Design Workflow", "is_default": True},
                        {"block_id": "followup:wrapup", "block_type": "followup_module", "title": "Wrap-up Followup"},
                    ],
                    "instruction_procedures": [],
                    "procedure_steps": [],
                }
            },
            "instruction_workflows": [
                {
                    "id": "workflow:design",
                    "title": "Design Workflow",
                    "workflow_name": "Design Workflow",
                    "triggers": [],
                    "steps": [{"order": 1, "title": "Design Step", "resource_file": "design.md"}],
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "wrapup",
                "confidence": 0.9,
                "continue_current_scope": False,
                "selected_role_id": None,
                "selected_workflow_id": "workflow:design",
                "selected_support_module_ids": [],
                "selected_followup_module_ids": ["followup:wrapup"],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "clarification_status": {"is_active": False, "is_complete": False, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "select_followup_module",
                    "target_service_block_id": "followup:wrapup",
                    "target_workflow_id": "workflow:design",
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [],
                },
                "reasoning_summary": ["use followup module ids as queue fallback"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["turn_execution_plan"]["active_module_queue"], ["followup:wrapup"])
        self.assertEqual(out["session_execution_state"]["active_module_queue"], ["followup:wrapup"])

    def test_planner_hybrid_active_promotes_followup_module_scope_and_dependency_resources(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["user_query"] = "請幫我優化這個 prompt"
        state["workflow_progress"] = {
            "workflow_id": "workflow:church-ministry",
            "workflow_title": "Interaction Logic & Execution Flow",
            "step_order": 2,
            "step_title": "核心流程（Workflow Execution）",
            "resource_file": "dynamic_prompt_optimizer.md",
        }
        state["session_execution_state"] = {
            "active_mode": "workflow:church-ministry",
            "active_workflow": "Interaction Logic & Execution Flow",
            "active_step_order": 2,
            "active_step_title": "核心流程（Workflow Execution）",
            "active_execution_mode": "bundled",
            "bundled_execution_completed": True,
            "active_step_scope_id": "step:interaction_logic_execution_flow:2",
        }
        state["template_registry"] = {
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "default_workflow_id": "workflow:church-ministry",
                    "instruction_service_blocks": [
                        {
                            "block_id": "workflow:church-ministry",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                            "is_default": True,
                        },
                        {
                            "block_id": "followup_module:optimization_module",
                            "block_type": "followup_module",
                            "title": "Optimization Module",
                        },
                    ],
                    "instruction_procedures": [],
                    "procedure_steps": [],
                }
            },
            "instruction_workflows": [
                {
                    "id": "workflow:church-ministry",
                    "title": "Interaction Logic & Execution Flow",
                    "workflow_name": "Interaction Logic & Execution Flow",
                    "triggers": [],
                    "steps": [
                        {
                            "order": 2,
                            "title": "核心流程（Workflow Execution）",
                            "resource_file": "dynamic_prompt_optimizer.md",
                            "step_scope_id": "step:interaction_logic_execution_flow:2",
                        }
                    ],
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": [
                {
                    "block_id": "workflow:church-ministry",
                    "block_type": "primary_workflow",
                    "title": "Interaction Logic & Execution Flow",
                },
                {
                    "block_id": "followup_module:optimization_module",
                    "block_type": "followup_module",
                    "title": "Optimization Module",
                },
            ],
            "instruction_resources": [
                {
                    "resource_id": "res:optimization-strategy",
                    "filename": "Optimization Strategy Library.md",
                    "domain": "instruction_source",
                }
            ],
            "dependency_groups": [
                {
                    "group_id": "group:optimization-pack",
                    "resource_ids": ["res:optimization-strategy"],
                }
            ],
            "phase_resource_bindings": [
                {
                    "binding_id": "binding:optimization-followup",
                    "scope_id": "followup_module:optimization_module",
                    "trigger_type": "phase",
                    "trigger_signals": [],
                    "dependency_groups": ["group:optimization-pack"],
                    "resource_kinds": ["instruction_resource"],
                    "activation_reason": "followup optimization module resources",
                    "priority": 1,
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "optimize_prompt",
                "confidence": 0.96,
                "continue_current_scope": False,
                "selected_role_id": "role:church_ministry_prompt_designer",
                "selected_workflow_id": "workflow:church-ministry",
                "selected_support_module_ids": [],
                "selected_followup_module_ids": ["followup_module:optimization_module"],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "clarification_status": {"is_active": False, "is_complete": True, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "select_followup_module",
                    "target_service_block_id": "followup_module:optimization_module",
                    "target_workflow_id": "workflow:church-ministry",
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [],
                },
                "reasoning_summary": ["activate optimization followup module and its dependency pack"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["turn_execution_plan"]["active_module_queue"], ["followup_module:optimization_module"])
        self.assertEqual(out["session_execution_state"]["active_module_queue"], ["followup_module:optimization_module"])
        self.assertEqual(out["session_execution_state"]["active_service_block_type"], "followup_module")
        self.assertEqual(out["session_execution_state"]["active_service_block_id"], "followup_module:optimization_module")
        self.assertIn("group:optimization-pack", out["session_execution_state"]["active_dependency_group_ids"])
        requests = {
            item["filename"]: item for item in out["turn_execution_plan"]["resource_requests"] if item.get("filename")
        }
        self.assertIn("Optimization Strategy Library.md", requests)
        self.assertEqual(requests["Optimization Strategy Library.md"]["dependency_group_id"], "group:optimization-pack")

    def test_planner_hybrid_active_promotes_queued_followup_module_after_bundled_completion(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["instruction_understanding_mode"] = "hybrid_active"
        state["user_query"] = "請幫我優化這個 prompt"
        state["workflow_progress"] = {
            "workflow_id": "interaction_logic_execution_flow",
            "workflow_title": "Interaction Logic & Execution Flow",
            "step_order": 2,
            "step_title": "核心流程（Workflow Execution）",
        }
        state["session_execution_state"] = {
            "primary_scope_id": "workflow:interaction_logic_execution_flow",
            "primary_scope_type": "workflow",
            "primary_scope_title": "Interaction Logic & Execution Flow",
            "active_mode": "interaction_logic_execution_flow",
            "active_workflow": "Interaction Logic & Execution Flow",
            "active_step_order": 2,
            "active_step_title": "核心流程（Workflow Execution）",
            "active_execution_mode": "bundled",
            "bundled_execution_completed": True,
            "active_module_queue": ["followup_module:optimization_module"],
            "primary_support_module_id": "followup_module:optimization_module",
            "primary_support_module_title": "Optimization Module",
        }
        state["compiled_instruction_understanding"] = {
            "compiled_contract": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "workflow:church-ministry",
                    "instruction_service_blocks": [
                        {
                            "block_id": "workflow:church-ministry",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                        },
                        {
                            "block_id": "followup_module:optimization_module",
                            "block_type": "followup_module",
                            "title": "Optimization Module",
                        },
                    ],
                    "procedure_steps": [],
                    "role_profiles": [],
                }
            }
        }
        state["template_registry"] = {
            "instruction_blocks": [],
            "instruction_workflows": [
                {
                    "id": "workflow:church-ministry",
                    "title": "Interaction Logic & Execution Flow",
                    "workflow_name": "Interaction Logic & Execution Flow",
                    "triggers": [],
                    "steps": [
                        {
                            "order": 2,
                            "title": "核心流程（Workflow Execution）",
                            "resource_file": "dynamic_prompt_optimizer.md",
                            "step_scope_id": "step:interaction_logic_execution_flow:2",
                        }
                    ],
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": [
                {
                    "block_id": "workflow:church-ministry",
                    "block_type": "primary_workflow",
                    "title": "Interaction Logic & Execution Flow",
                },
                {
                    "block_id": "followup_module:optimization_module",
                    "block_type": "followup_module",
                    "title": "Optimization Module",
                },
            ],
            "instruction_resources": [
                {
                    "resource_id": "res:optimization-strategy",
                    "filename": "Optimization Strategy Library.md",
                    "domain": "instruction_source",
                }
            ],
            "dependency_groups": [
                {
                    "group_id": "group:optimization-pack",
                    "resource_ids": ["res:optimization-strategy"],
                }
            ],
            "phase_resource_bindings": [
                {
                    "binding_id": "binding:optimization-followup",
                    "scope_id": "followup_module:optimization_module",
                    "trigger_type": "phase",
                    "trigger_signals": [],
                    "dependency_groups": ["group:optimization-pack"],
                    "resource_kinds": ["instruction_resource"],
                    "activation_reason": "followup optimization module resources",
                    "priority": 1,
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "optimize_prompt",
                "confidence": 0.91,
                "continue_current_scope": False,
                "selected_role_id": "role:church_ministry_prompt_designer",
                "selected_workflow_id": "workflow:church-ministry",
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "clarification_status": {"is_active": False, "is_complete": True, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "guide",
                    "target_workflow_id": "workflow:church-ministry",
                    "target_service_block_id": None,
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [],
                },
                "reasoning_summary": ["use queued followup module from session state after bundled completion"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["session_execution_state"]["active_service_block_type"], "followup_module")
        self.assertEqual(out["session_execution_state"]["active_service_block_id"], "followup_module:optimization_module")
        self.assertIn("group:optimization-pack", out["session_execution_state"]["active_dependency_group_ids"])
        requests = {
            item["filename"]: item for item in out["turn_execution_plan"]["resource_requests"] if item.get("filename")
        }
        self.assertIn("Optimization Strategy Library.md", requests)

    def test_planner_hybrid_active_prioritizes_queued_followup_module_over_stale_support_step(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["instruction_understanding_mode"] = "hybrid_active"
        state["user_query"] = "請幫我優化這個 prompt"
        state["workflow_progress"] = {
            "workflow_id": "interaction_logic_execution_flow",
            "workflow_title": "Interaction Logic & Execution Flow",
            "step_order": 2,
            "step_title": "核心流程（Workflow Execution）",
        }
        state["session_execution_state"] = {
            "primary_scope_id": "workflow:interaction_logic_execution_flow",
            "primary_scope_type": "workflow",
            "primary_scope_title": "Interaction Logic & Execution Flow",
            "active_mode": "interaction_logic_execution_flow",
            "active_workflow": "Interaction Logic & Execution Flow",
            "active_step_order": 2,
            "active_step_title": "核心流程（Workflow Execution）",
            "active_execution_mode": "bundled",
            "bundled_execution_completed": True,
            "active_module_queue": ["step:routing", "followup_module:optimization_module"],
            "primary_support_module_id": "step:routing",
            "primary_support_module_title": None,
        }
        state["compiled_instruction_understanding"] = {
            "compiled_contract": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "workflow:church-ministry",
                    "instruction_service_blocks": [
                        {
                            "block_id": "primary_workflow:interaction_logic_execution_flow",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                        },
                        {
                            "block_id": "followup_module:optimization_module",
                            "block_type": "followup_module",
                            "title": "Optimization Module",
                        },
                    ],
                    "procedure_steps": [],
                    "role_profiles": [],
                }
            }
        }
        state["template_registry"] = {
            "instruction_blocks": [],
            "instruction_workflows": [
                {
                    "id": "interaction_logic_execution_flow",
                    "title": "Interaction Logic & Execution Flow",
                    "workflow_name": "Interaction Logic & Execution Flow",
                    "triggers": [],
                    "steps": [
                        {
                            "order": 2,
                            "title": "核心流程（Workflow Execution）",
                            "resource_file": "dynamic_prompt_optimizer.md",
                            "step_scope_id": "step:interaction_logic_execution_flow:2",
                        }
                    ],
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": [
                {
                    "block_id": "primary_workflow:interaction_logic_execution_flow",
                    "block_type": "primary_workflow",
                    "title": "Interaction Logic & Execution Flow",
                },
                {
                    "block_id": "followup_module:optimization_module",
                    "block_type": "followup_module",
                    "title": "Optimization Module",
                },
            ],
            "instruction_resources": [
                {
                    "resource_id": "res:optimization-strategy",
                    "filename": "Optimization Strategy Library.md",
                    "domain": "instruction_source",
                }
            ],
            "dependency_groups": [
                {
                    "group_id": "group:optimization-pack",
                    "resource_ids": ["res:optimization-strategy"],
                }
            ],
            "phase_resource_bindings": [
                {
                    "binding_id": "binding:optimization-followup",
                    "scope_id": "followup_module:optimization_module",
                    "trigger_type": "phase",
                    "trigger_signals": [],
                    "dependency_groups": ["group:optimization-pack"],
                    "resource_kinds": ["instruction_resource"],
                    "activation_reason": "followup optimization module resources",
                    "priority": 1,
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "optimize_prompt",
                "confidence": 0.93,
                "continue_current_scope": False,
                "selected_role_id": "role:church_ministry_prompt_designer",
                "selected_workflow_id": "interaction_logic_execution_flow",
                "selected_support_module_ids": ["step:routing"],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": ["step:routing"],
                "clarification_status": {"is_active": False, "is_complete": True, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "guide",
                    "target_workflow_id": "interaction_logic_execution_flow",
                    "target_service_block_id": None,
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": ["step:routing"],
                },
                "reasoning_summary": ["followup optimization should override stale routing support after bundled completion"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["turn_execution_plan"]["active_module_queue"][0], "followup_module:optimization_module")
        self.assertEqual(out["session_execution_state"]["active_module_queue"][0], "followup_module:optimization_module")
        self.assertEqual(out["session_execution_state"]["primary_support_module_id"], "followup_module:optimization_module")
        self.assertEqual(out["session_execution_state"]["active_service_block_type"], "followup_module")
        self.assertEqual(out["session_execution_state"]["active_service_block_id"], "followup_module:optimization_module")
        requests = {
            item["filename"]: item for item in out["turn_execution_plan"]["resource_requests"] if item.get("filename")
        }
        self.assertIn("Optimization Strategy Library.md", requests)
        self.assertEqual(requests["Optimization Strategy Library.md"]["dependency_group_id"], "group:optimization-pack")

    def test_planner_hybrid_active_resolves_followup_alias_to_canonical_block_and_phase_binding(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["instruction_understanding_mode"] = "hybrid_active"
        state["user_query"] = "請幫我優化這個 prompt"
        state["workflow_progress"] = {
            "workflow_id": "interaction_logic_execution_flow",
            "workflow_title": "Interaction Logic & Execution Flow",
            "step_order": 2,
            "step_title": "核心流程（Workflow Execution）",
        }
        state["session_execution_state"] = {
            "primary_scope_id": "workflow:interaction_logic_execution_flow",
            "primary_scope_type": "workflow",
            "primary_scope_title": "Interaction Logic & Execution Flow",
            "active_mode": "interaction_logic_execution_flow",
            "active_workflow": "Interaction Logic & Execution Flow",
            "active_step_order": 2,
            "active_step_title": "核心流程（Workflow Execution）",
            "active_execution_mode": "bundled",
            "bundled_execution_completed": True,
            "active_module_queue": ["followup_module:optimization_module"],
            "primary_support_module_id": "followup_module:optimization_module",
            "primary_support_module_title": "Optimization Module（Prompt 優化模組）",
        }
        canonical_followup_id = "followup_module:optimization_module_prompt_優化模組"
        state["compiled_instruction_understanding"] = {
            "compiled_contract": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "workflow:church-ministry",
                    "instruction_service_blocks": [
                        {
                            "block_id": "primary_workflow:interaction_logic_execution_flow",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                        },
                        {
                            "block_id": canonical_followup_id,
                            "block_type": "followup_module",
                            "title": "Optimization Module（Prompt 優化模組）",
                        },
                    ],
                    "procedure_steps": [],
                    "role_profiles": [],
                }
            }
        }
        state["template_registry"] = {
            "instruction_blocks": [],
            "instruction_workflows": [
                {
                    "id": "interaction_logic_execution_flow",
                    "title": "Interaction Logic & Execution Flow",
                    "workflow_name": "Interaction Logic & Execution Flow",
                    "triggers": [],
                    "steps": [
                        {
                            "order": 2,
                            "title": "核心流程（Workflow Execution）",
                            "resource_file": "dynamic_prompt_optimizer.md",
                            "step_scope_id": "step:interaction_logic_execution_flow:2",
                        }
                    ],
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": [
                {
                    "block_id": "primary_workflow:interaction_logic_execution_flow",
                    "block_type": "primary_workflow",
                    "title": "Interaction Logic & Execution Flow",
                },
                {
                    "block_id": canonical_followup_id,
                    "block_type": "followup_module",
                    "title": "Optimization Module（Prompt 優化模組）",
                },
            ],
            "instruction_resources": [
                {
                    "resource_id": "res:optimization-strategy",
                    "filename": "Optimization Strategy Library.md",
                    "domain": "instruction_source",
                }
            ],
            "dependency_groups": [
                {
                    "group_id": "group:optimization-pack",
                    "resource_ids": ["res:optimization-strategy"],
                }
            ],
            "phase_resource_bindings": [
                {
                    "binding_id": "binding:optimization-followup",
                    "scope_id": "phase:optimization_module_prompt_優化模組",
                    "trigger_type": "phase",
                    "trigger_signals": [],
                    "dependency_groups": ["group:optimization-pack"],
                    "resource_kinds": ["instruction_resource"],
                    "activation_reason": "followup optimization module resources",
                    "priority": 1,
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "optimize_prompt",
                "confidence": 0.96,
                "continue_current_scope": False,
                "selected_role_id": "role:church_ministry_prompt_designer",
                "selected_workflow_id": "interaction_logic_execution_flow",
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "clarification_status": {"is_active": False, "is_complete": True, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "guide",
                    "target_workflow_id": "interaction_logic_execution_flow",
                    "target_service_block_id": None,
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [],
                },
                "reasoning_summary": ["queued followup alias should resolve to canonical compiled followup block"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["turn_execution_plan"]["active_module_queue"][0], "followup_module:optimization_module")
        self.assertIsNone(out["session_execution_state"].get("primary_support_module_id"))
        self.assertEqual(out["session_execution_state"]["active_service_block_type"], "followup_module")
        self.assertEqual(out["session_execution_state"]["active_service_block_id"], canonical_followup_id)
        requests = {
            item["filename"]: item for item in out["turn_execution_plan"]["resource_requests"] if item.get("filename")
        }
        self.assertIn("Optimization Strategy Library.md", requests)
        self.assertEqual(requests["Optimization Strategy Library.md"]["dependency_group_id"], "group:optimization-pack")

    def test_planner_hybrid_active_persists_optimization_module_instead_of_bundled_step_two_scope(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["instruction_understanding_mode"] = "hybrid_active"
        state["user_query"] = "\u8acb\u5e6b\u6211\u512a\u5316\u9019\u500b prompt"
        state["workflow_progress"] = {
            "workflow_id": "interaction_logic_execution_flow",
            "workflow_title": "Interaction Logic & Execution Flow",
            "step_order": 2,
            "step_title": "\u6838\u5fc3\u6d41\u7a0b\uff08Workflow Execution\uff09",
        }
        state["session_execution_state"] = {
            "primary_scope_id": "workflow:interaction_logic_execution_flow",
            "primary_scope_type": "workflow",
            "primary_scope_title": "Interaction Logic & Execution Flow",
            "active_mode": "interaction_logic_execution_flow",
            "active_workflow": "Interaction Logic & Execution Flow",
            "active_step_order": 2,
            "active_step_title": "\u6838\u5fc3\u6d41\u7a0b\uff08Workflow Execution\uff09",
            "active_execution_mode": "bundled",
            "active_bundled_step_ids": [
                "step:interaction_logic_execution_flow:2",
                "step:interaction_logic_execution_flow:3",
            ],
            "bundled_execution_completed": True,
        }
        canonical_followup_id = "followup_module:optimization_module"
        state["compiled_instruction_understanding"] = {
            "compiled_contract": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "workflow:church-ministry",
                    "instruction_service_blocks": [
                        {
                            "block_id": "primary_workflow:interaction_logic_execution_flow",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                        },
                        {
                            "block_id": canonical_followup_id,
                            "block_type": "followup_module",
                            "title": "Optimization Module",
                        },
                    ],
                    "procedure_steps": [],
                    "role_profiles": [],
                }
            }
        }
        state["template_registry"] = {
            "instruction_blocks": [],
            "instruction_workflows": [
                {
                    "id": "interaction_logic_execution_flow",
                    "title": "Interaction Logic & Execution Flow",
                    "workflow_name": "Interaction Logic & Execution Flow",
                    "triggers": [],
                    "steps": [
                        {
                            "order": 2,
                            "title": "\u6838\u5fc3\u6d41\u7a0b\uff08Workflow Execution\uff09",
                            "resource_file": "dynamic_prompt_optimizer.md",
                            "step_scope_id": "step:interaction_logic_execution_flow:2",
                        }
                    ],
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": [
                {
                    "block_id": "primary_workflow:interaction_logic_execution_flow",
                    "block_type": "primary_workflow",
                    "title": "Interaction Logic & Execution Flow",
                },
                {
                    "block_id": canonical_followup_id,
                    "block_type": "followup_module",
                    "title": "Optimization Module",
                },
            ],
            "instruction_resources": [
                {
                    "resource_id": "opt-lib",
                    "filename": "Optimization Strategy Library.md",
                    "domain": "instruction_source",
                }
            ],
            "followup_modules": [
                {
                    "module_id": canonical_followup_id,
                    "title": "Optimization Module（Prompt 優化模組）",
                    "step_sequence": [
                        {
                            "order": 2,
                            "step_id": "followup:optimization:dual_evaluation",
                            "title": "Step 2：雙軸評估（Dual Evaluation）",
                            "execution_mode": "bundled",
                            "resource_refs": ["Optimization Strategy Library.md"],
                        },
                        {
                            "order": 4,
                            "step_id": "followup:optimization:selectable_options",
                            "title": "Step 4：優化建議（Selectable Options 🔥）",
                            "execution_mode": "bundled",
                            "resource_refs": ["Optimization Strategy Library.md"],
                        },
                    ],
                }
            ],
            "dependency_groups": [],
            "phase_resource_bindings": [
                {
                    "binding_id": "binding:optimization-followup",
                    "scope_id": "followup_module:optimization_module",
                    "trigger_type": "phase",
                    "trigger_signals": [],
                    "resource_ids": ["opt-lib"],
                    "resource_kinds": ["instruction_resource"],
                    "activation_reason": "optimization resources",
                    "priority": 1,
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "optimize_prompt",
                "confidence": 0.97,
                "continue_current_scope": False,
                "selected_role_id": "role:church_ministry_prompt_designer",
                "selected_workflow_id": "interaction_logic_execution_flow",
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "clarification_status": {"is_active": False, "is_complete": True, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "guide",
                    "target_workflow_id": "interaction_logic_execution_flow",
                    "target_service_block_id": "step:interaction_logic_execution_flow:2",
                    "target_step_id": "step:interaction_logic_execution_flow:2",
                    "bundled_step_ids": [
                        "step:interaction_logic_execution_flow:2",
                        "step:interaction_logic_execution_flow:3",
                    ],
                    "module_queue": [],
                },
                "reasoning_summary": ["optimization requested after bundled workflow; should promote optimization module"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["session_execution_state"]["active_service_block_type"], "followup_module")
        self.assertEqual(out["session_execution_state"]["active_service_block_id"], "followup_module:optimization_module")
        self.assertEqual(out["turn_execution_plan"]["primary_support_module_scope"]["scope_id"], "followup_module:optimization_module")
        self.assertEqual(out["session_execution_state"]["active_step_title"], "Optimization Module")
        self.assertNotIn("active_step_scope_id", out["session_execution_state"])
        request_filenames = {
            item.get("filename")
            for item in out["turn_execution_plan"]["resource_requests"]
            if item.get("filename")
        }
        self.assertIn("Optimization Strategy Library.md", request_filenames)

    def test_planner_hybrid_active_keeps_followup_module_queued_until_followup_turn(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["instruction_understanding_mode"] = "hybrid_active"
        state["user_query"] = "深入理解以弗所書第一章的神學真理"
        state["workflow_progress"] = {
            "workflow_id": "interaction_logic_execution_flow",
            "workflow_title": "Interaction Logic & Execution Flow",
            "step_order": 1,
            "step_title": "Clarification（單一問題規則）",
        }
        state["session_execution_state"] = {
            "primary_scope_id": "workflow:interaction_logic_execution_flow",
            "primary_scope_type": "workflow",
            "primary_scope_title": "Interaction Logic & Execution Flow",
            "active_mode": "interaction_logic_execution_flow",
            "active_workflow": "Interaction Logic & Execution Flow",
            "active_step_order": 1,
            "active_step_title": "Clarification（單一問題規則）",
            "active_step_scope_id": "step:interaction_logic_execution_flow:1",
            "active_execution_mode": "interactive",
            "clarification_gate_status": {
                "minimum_filled_slots": 3,
                "filled_slots_map": {"passage": True, "audience": True},
            },
            "active_module_queue": ["followup_module:optimization_module"],
            "primary_support_module_id": "followup_module:optimization_module",
            "primary_support_module_title": "Optimization Module（Prompt 優化模組）",
            "bundled_execution_completed": True,
        }
        canonical_followup_id = "followup_module:optimization_module"
        state["compiled_instruction_understanding"] = {
            "compiled_contract": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "workflow:church-ministry",
                    "instruction_service_blocks": [
                        {
                            "block_id": "primary_workflow:interaction_logic_execution_flow",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                        },
                        {
                            "block_id": canonical_followup_id,
                            "block_type": "followup_module",
                            "title": "Optimization Module",
                        },
                    ],
                    "procedure_steps": [],
                    "role_profiles": [],
                }
            }
        }
        state["template_registry"] = {
            "instruction_blocks": [],
            "instruction_workflows": [
                {
                    "id": "interaction_logic_execution_flow",
                    "title": "Interaction Logic & Execution Flow",
                    "workflow_name": "Interaction Logic & Execution Flow",
                    "triggers": [],
                    "steps": [
                        {
                            "order": 2,
                            "title": "核心流程（Workflow Execution）",
                            "resource_file": "dynamic_prompt_optimizer.md",
                            "step_scope_id": "step:interaction_logic_execution_flow:2",
                        }
                    ],
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": [
                {
                    "block_id": "primary_workflow:interaction_logic_execution_flow",
                    "block_type": "primary_workflow",
                    "title": "Interaction Logic & Execution Flow",
                },
                {
                    "block_id": canonical_followup_id,
                    "block_type": "followup_module",
                    "title": "Optimization Module",
                },
            ],
            "instruction_resources": [
                {
                    "resource_id": "opt-lib",
                    "filename": "Optimization Strategy Library.md",
                    "domain": "instruction_source",
                },
                {
                    "resource_id": "tpl",
                    "filename": "template_library.md",
                    "domain": "output_template",
                },
                {
                    "resource_id": "dpo",
                    "filename": "dynamic_prompt_optimizer.md",
                    "domain": "instruction_source",
                },
            ],
            "followup_modules": [
                {
                    "module_id": canonical_followup_id,
                    "title": "Optimization Module（Prompt 優化模組）",
                    "step_sequence": [
                        {
                            "order": 2,
                            "step_id": "followup:optimization:dual_evaluation",
                            "title": "Step 2：雙軸評估（Dual Evaluation）",
                            "execution_mode": "bundled",
                            "resource_refs": ["Optimization Strategy Library.md"],
                        }
                    ],
                }
            ],
            "dependency_groups": [],
            "phase_resource_bindings": [],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "prompt_design",
                "confidence": 0.96,
                "continue_current_scope": False,
                "selected_role_id": "role:church_ministry_prompt_designer",
                "selected_workflow_id": "interaction_logic_execution_flow",
                "selected_support_module_ids": [],
                "selected_followup_module_ids": ["followup_module:optimization_module"],
                "selected_supplementary_workflow_id": None,
                "module_sequence": ["followup_module:optimization_module"],
                "clarification_status": {
                    "is_active": False,
                    "is_complete": True,
                    "missing_slots": [],
                    "filled_slot_names": ["passage", "audience", "goal"],
                },
                "next_action": {
                    "action_type": "guide",
                    "target_workflow_id": "interaction_logic_execution_flow",
                    "target_service_block_id": "primary_workflow:interaction_logic_execution_flow",
                    "target_step_id": "step:interaction_logic_execution_flow:2",
                    "bundled_step_ids": ["step:interaction_logic_execution_flow:2"],
                    "module_queue": ["followup_module:optimization_module"],
                },
                "reasoning_summary": ["goal answer should advance to core workflow but must not activate followup yet"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(
            out["session_execution_state"].get("active_step_scope_id"),
            "step:interaction_logic_execution_flow:2",
        )
        self.assertNotEqual(
            out["session_execution_state"].get("active_service_block_type"),
            "followup_module",
        )
        self.assertNotEqual(
            out["session_execution_state"].get("active_service_block_id"),
            canonical_followup_id,
        )
        request_filenames = {
            item.get("filename")
            for item in out["turn_execution_plan"]["resource_requests"]
            if item.get("filename")
        }
        self.assertIn("dynamic_prompt_optimizer.md", request_filenames)
        self.assertNotIn("Optimization Strategy Library.md", request_filenames)
        self.assertIn("followup_module:optimization_module", out["session_execution_state"].get("active_module_queue", []))

    def test_planner_hybrid_active_loads_descendant_followup_phase_resources_from_heading_tree(self):
        state = self.state.copy()
        state["planner_mode"] = "hybrid_active"
        state["instruction_understanding_mode"] = "hybrid_active"
        state["user_query"] = "請幫我優化這個 prompt"
        state["workflow_progress"] = {
            "workflow_id": "interaction_logic_execution_flow",
            "workflow_title": "Interaction Logic & Execution Flow",
            "step_order": 2,
            "step_title": "核心流程（Workflow Execution）",
        }
        state["session_execution_state"] = {
            "primary_scope_id": "workflow:interaction_logic_execution_flow",
            "primary_scope_type": "workflow",
            "primary_scope_title": "Interaction Logic & Execution Flow",
            "active_mode": "interaction_logic_execution_flow",
            "active_workflow": "Interaction Logic & Execution Flow",
            "active_step_order": 2,
            "active_step_title": "核心流程（Workflow Execution）",
            "active_execution_mode": "bundled",
            "bundled_execution_completed": True,
            "active_module_queue": ["followup_module:optimization_module"],
            "primary_support_module_id": "followup_module:optimization_module",
            "primary_support_module_title": "Optimization Module（Prompt 優化模組）",
        }
        canonical_followup_id = "followup_module:optimization_module_prompt_優化模組"
        state["compiled_instruction_understanding"] = {
            "compiled_contract": {
                "hybrid_instruction_runtime_model": {
                    "primary_service_mode": "single_default_workflow",
                    "default_workflow_id": "workflow:church-ministry",
                    "instruction_service_blocks": [
                        {
                            "block_id": "primary_workflow:interaction_logic_execution_flow",
                            "block_type": "primary_workflow",
                            "title": "Interaction Logic & Execution Flow",
                        },
                        {
                            "block_id": canonical_followup_id,
                            "block_type": "followup_module",
                            "title": "Optimization Module（Prompt 優化模組）",
                        },
                    ],
                    "procedure_steps": [],
                    "role_profiles": [],
                }
            }
        }
        state["template_registry"] = {
            "instruction_blocks": [],
            "instruction_heading_tree": [
                {
                    "title": "Optimization Module（Prompt 優化模組）",
                    "normalized_title": "optimization_module_prompt_優化模組",
                    "children": [
                        {
                            "title": "【Execution Flow】",
                            "normalized_title": "execution_flow",
                            "children": [
                                {
                                    "title": "Step 2：雙軸評估（Dual Evaluation）",
                                    "normalized_title": "step_2_雙軸評估_dual_evaluation",
                                    "children": [],
                                },
                                {
                                    "title": "Step 4：優化建議（Selectable Options 🔥）",
                                    "normalized_title": "step_4_優化建議_selectable_options",
                                    "children": [],
                                },
                            ],
                        }
                    ],
                }
            ],
            "instruction_workflows": [
                {
                    "id": "interaction_logic_execution_flow",
                    "title": "Interaction Logic & Execution Flow",
                    "workflow_name": "Interaction Logic & Execution Flow",
                    "triggers": [],
                    "steps": [
                        {
                            "order": 2,
                            "title": "\u6838\u5fc3\u6d41\u7a0b\uff08Workflow Execution\uff09",
                            "resource_file": "dynamic_prompt_optimizer.md",
                            "step_scope_id": "step:interaction_logic_execution_flow:2",
                        }
                    ],
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_service_blocks": [
                {
                    "block_id": "primary_workflow:interaction_logic_execution_flow",
                    "block_type": "primary_workflow",
                    "title": "Interaction Logic & Execution Flow",
                },
                {
                    "block_id": canonical_followup_id,
                    "block_type": "followup_module",
                    "title": "Optimization Module（Prompt 優化模組）",
                },
            ],
            "instruction_resources": [
                {
                    "resource_id": "optimization strategy library",
                    "filename": "Optimization Strategy Library.md",
                    "domain": "instruction_source",
                }
            ],
            "followup_modules": [
                {
                    "module_id": canonical_followup_id,
                    "title": "Optimization Module（Prompt 優化模組）",
                    "step_sequence": [
                        {
                            "order": 2,
                            "step_id": "followup:optimization:dual_evaluation",
                            "title": "Step 2：雙軸評估（Dual Evaluation）",
                            "execution_mode": "bundled",
                            "resource_refs": ["Optimization Strategy Library.md"],
                        },
                        {
                            "order": 4,
                            "step_id": "followup:optimization:selectable_options",
                            "title": "Step 4：優化建議（Selectable Options 🔥）",
                            "execution_mode": "bundled",
                            "resource_refs": ["Optimization Strategy Library.md"],
                        },
                    ],
                }
            ],
            "dependency_groups": [],
            "phase_resource_bindings": [
                {
                    "binding_id": "phase:optimization_module_prompt_優化模組",
                    "scope_id": "phase:optimization_module_prompt_優化模組",
                    "title": "Optimization Module（Prompt 優化模組）",
                    "trigger_type": "module",
                    "trigger_signals": [],
                    "dependency_groups": [],
                    "resource_ids": [],
                    "filenames": [],
                    "resource_kinds": [],
                    "activation_reason": None,
                    "priority": 100,
                },
                {
                    "binding_id": "phase:step_2_雙軸評估_dual_evaluation",
                    "scope_id": "phase:step_2_雙軸評估_dual_evaluation",
                    "title": "Step 2：雙軸評估（Dual Evaluation）",
                    "trigger_type": "phase",
                    "trigger_signals": [],
                    "dependency_groups": [],
                    "resource_ids": ["optimization strategy library"],
                    "filenames": ["Optimization Strategy Library.md"],
                    "resource_kinds": ["instruction_resource"],
                    "activation_reason": "followup optimization evaluation resources",
                    "priority": 100,
                },
                {
                    "binding_id": "phase:step_4_優化建議_selectable_options",
                    "scope_id": "phase:step_4_優化建議_selectable_options",
                    "title": "Step 4：優化建議（Selectable Options 🔥）",
                    "trigger_type": "phase",
                    "trigger_signals": [],
                    "dependency_groups": [],
                    "resource_ids": ["optimization strategy library"],
                    "filenames": ["Optimization Strategy Library.md"],
                    "resource_kinds": ["instruction_resource"],
                    "activation_reason": "followup optimization option resources",
                    "priority": 100,
                },
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        def hybrid_llm(_prompt, _tools, _context):
            return {
                "intent_label": "optimize_prompt",
                "confidence": 0.96,
                "continue_current_scope": False,
                "selected_role_id": "role:church_ministry_prompt_designer",
                "selected_workflow_id": "interaction_logic_execution_flow",
                "selected_support_module_ids": [],
                "selected_followup_module_ids": [],
                "selected_supplementary_workflow_id": None,
                "module_sequence": [],
                "clarification_status": {"is_active": False, "is_complete": True, "missing_slots": [], "filled_slot_names": []},
                "next_action": {
                    "action_type": "guide",
                    "target_workflow_id": "interaction_logic_execution_flow",
                    "target_service_block_id": None,
                    "target_step_id": None,
                    "bundled_step_ids": [],
                    "module_queue": [],
                },
                "reasoning_summary": ["followup optimization should load explicit followup-module resources"],
            }

        state["_llm_planner_hybrid"] = hybrid_llm
        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["session_execution_state"]["active_service_block_type"], "followup_module")
        self.assertEqual(out["session_execution_state"]["active_service_block_id"], canonical_followup_id)
        requests = {
            item["filename"]: item for item in out["turn_execution_plan"]["resource_requests"] if item.get("filename")
        }
        self.assertIn("Optimization Strategy Library.md", requests)
        load_plan_filenames = {
            item["filename"]
            for item in out.get("instruction_resource_load_plan", [])
            if isinstance(item, dict) and item.get("filename")
        }
        self.assertIn("Optimization Strategy Library.md", load_plan_filenames)
        self.assertIn(
            "Optimization Strategy Library.md",
            out["session_execution_state"]["active_instruction_resources"],
        )

    def test_planner_fallback_on_low_confidence(self):
        calls = {"n": 0, "prompts": []}

        def llm(prompt, tools, context):
            _ = (tools, context)
            calls["n"] += 1
            calls["prompts"].append(prompt)
            if calls["n"] == 1:
                return self.low_conf
            return self.valid

        out = planner.run(self.state.copy(), llm_planner=llm)
        self.assertEqual(calls["n"], 2)
        self.assertIn("fallback", calls["prompts"][1].lower())
        self.assertEqual(out["planner_output"]["confidence"], 0.85)

    def test_planner_raises_on_invalid_schema(self):
        invalid = {"intentType": "qa"}  # missing required fields

        def llm(_prompt, _tools, _context):
            return invalid

        with self.assertRaises(ValidationError):
            planner.run(self.state.copy(), llm_planner=llm)

    def test_planner_falls_back_to_local_default_when_llm_call_errors(self):
        state = self.state.copy()
        state["user_query"] = "我想查考一段經文"
        state["template_registry"] = {
            "instruction_blocks": [
                {
                    "block_id": "mode:bible_study",
                    "block_type": "mode",
                    "title": "查考經文模式（Bible Study）",
                    "body_text": "好的，我們一起用歸納釋經法查考經文。",
                    "response_hint": "好的，我們一起用歸納釋經法查考經文。請問想從哪一段開始？",
                    "activation_triggers": ["查考", "研經", "經文"],
                    "linked_mode_id": "bible_study",
                    "linked_workflow": "查經互動模組",
                }
            ],
            "instruction_workflows": [
                {
                    "id": "bible_study",
                    "title": "查考經文模式（Bible Study）",
                    "triggers": ["查考", "研經", "經文"],
                    "workflow_name": "查經互動模組",
                    "steps": [
                        {"order": 1, "title": "細察事實 (Observation)", "resource_file": "observation_guide.md"},
                    ],
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            raise RuntimeError("LLM HTTP error 402: Insufficient Balance")

        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["planner_output"]["normalizedQuery"], "我想查考一段經文")
        self.assertEqual(out["turn_execution_plan"]["turn_intent"], "start")
        self.assertEqual(out["selected_instruction_block"]["block_type"], "mode")

    def test_planner_persist_fn_takes_precedence(self):
        repo = InMemoryPlannerRepo()
        persisted = {"called": 0}

        def llm(_prompt, _tools, _context):
            return self.valid

        def persist_fn(state, planner_output):
            _ = (state, planner_output)
            persisted["called"] += 1

        planner.run(self.state.copy(), llm_planner=llm, persist_fn=persist_fn, repo=repo)
        self.assertEqual(persisted["called"], 1)
        self.assertEqual(len(repo._rows), 0)

    def test_selects_instruction_module_from_builder_registry(self):
        state = self.state.copy()
        state["user_query"] = "ç´°æŸ¥äº‹å¯¦æœ‰å“ªäº›è§€å¯Ÿé …ç›®?"
        state["template_registry"] = {
            "instruction_modules": [
                {
                    "id": "observation_guide",
                    "title": "ç´°å¯Ÿäº‹å¯¦ (Observation)",
                    "primary_resource": "observation_guide.md",
                    "resource_files": ["observation_guide.md"],
                    "keywords": ["ç´°å¯Ÿäº‹å¯¦", "ç´°æŸ¥äº‹å¯¦", "observation"],
                }
            ]
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["instruction_resource"], "observation_guide.md")
        self.assertEqual(out["instruction_resource_filters"]["filename"], "observation_guide.md")

    def test_selects_mode_block_without_step_for_starter_bible_study_query(self):
        state = self.state.copy()
        state["user_query"] = "我想查考一段經文"
        state["template_registry"] = {
            "instruction_blocks": [
                {
                    "block_id": "mode:bible_study",
                    "block_type": "mode",
                    "title": "查考經文模式（Bible Study）",
                    "body_text": "觸發：輸入含查考、研經、經文等字。回應：好的，我們一起用歸納釋經法查考經文。請問想從哪一段開始？",
                    "response_hint": "好的，我們一起用歸納釋經法查考經文。請問想從哪一段開始？",
                    "activation_triggers": ["查考", "研經", "經文"],
                    "linked_mode_id": "bible_study",
                    "linked_workflow": "查經互動模組",
                }
            ],
            "instruction_workflows": [
                {
                    "id": "bible_study",
                    "title": "查考經文模式（Bible Study）",
                    "triggers": ["查考", "研經", "經文"],
                    "workflow_name": "查經互動模組",
                    "steps": [
                        {"order": 1, "title": "細察事實 (Observation)", "resource_file": "observation_guide.md"},
                        {"order": 2, "title": "認清關係 (Identify Relationships)", "resource_file": "identify_relation_guide.md"},
                    ],
                }
            ]
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["instruction_workflow"]["id"], "bible_study")
        self.assertNotIn("instruction_step", out)
        self.assertEqual(out["selected_instruction_block"]["block_type"], "mode")
        self.assertEqual(out["selected_instruction_block"]["title"], "查考經文模式（Bible Study）")
        self.assertEqual(out["turn_execution_plan"]["turn_intent"], "start")
        self.assertEqual(out["turn_execution_plan"]["primary_scope"]["scope_type"], "mode")
        self.assertEqual(out["turn_execution_plan"]["presentation_policy"]["mode"], "question_only")
        action_types = [item["action_type"] for item in out["turn_execution_plan"]["actions"]]
        self.assertIn("respond_to_user", action_types)
        self.assertIn("update_session_state", action_types)
        self.assertFalse(any(item["resource_role"] == "instruction_source" for item in out["turn_execution_plan"]["resource_requests"]))

    def test_selects_first_step_when_query_contains_passage_reference(self):
        state = self.state.copy()
        state["user_query"] = "我想查考約翰福音第17章"
        state["template_registry"] = {
            "instruction_blocks": [
                {
                    "block_id": "mode:bible_study",
                    "block_type": "mode",
                    "title": "查考經文模式（Bible Study）",
                    "body_text": "好的，我們一起用歸納釋經法查考經文。",
                    "activation_triggers": ["查考", "研經", "經文"],
                    "linked_mode_id": "bible_study",
                    "linked_workflow": "查經互動模組",
                },
                {
                    "block_id": "step:bible_study:1",
                    "block_type": "step",
                    "title": "細察事實 (Observation)",
                    "body_text": "依資源之觀察項目產出 1–3 題。",
                    "objective": "幫助學員觀察經文的具體細節。",
                    "operation_text": "依資源之觀察項目產出 1–3 題。",
                    "referenced_resources": ["observation_guide.md"],
                    "linked_mode_id": "bible_study",
                    "linked_workflow": "查經互動模組",
                    "linked_step_order": 1,
                    "linked_step_title": "細察事實 (Observation)",
                },
            ],
            "instruction_workflows": [
                {
                    "id": "bible_study",
                    "title": "查考經文模式（Bible Study）",
                    "triggers": ["查考", "研經", "經文"],
                    "workflow_name": "查經互動模組",
                    "steps": [
                        {"order": 1, "title": "細察事實 (Observation)", "resource_file": "observation_guide.md"},
                        {"order": 2, "title": "認清關係 (Identify Relationships)", "resource_file": "identify_relation_guide.md"},
                    ],
                }
            ]
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["instruction_workflow"]["id"], "bible_study")
        self.assertEqual(out["instruction_step"]["order"], 1)
        self.assertEqual(out["instruction_resource"], "observation_guide.md")
        self.assertEqual(out["selected_instruction_block"]["block_type"], "step")
        self.assertEqual(out["turn_execution_plan"]["primary_scope"]["scope_type"], "step")
        self.assertTrue(any(item.get("filename") == "observation_guide.md" for item in out["turn_execution_plan"]["resource_requests"]))

    def test_turn_execution_plan_includes_response_logic_scope_candidate(self):
        state = self.state.copy()
        state["user_query"] = "我回答剛才的問題"
        state["workflow_progress"] = {
            "workflow_id": "bible_study",
            "workflow_title": "查考經文模式（Bible Study）",
            "step_order": 1,
            "step_title": "細察事實 (Observation)",
            "resource_file": "observation_guide.md",
        }
        state["instruction_scope_candidates"] = [
            {
                "scope_id": "section:student_response_logic",
                "scope_type": "response_logic",
                "title": "學員回應處理邏輯（Student Response Handling Logic）",
                "body_text": "如果學員回答部分正確，先肯定，再追問。",
            }
        ]
        state["template_registry"] = {
            "instruction_blocks": [
                {
                    "block_id": "step:bible_study:1",
                    "block_type": "step",
                    "title": "細察事實 (Observation)",
                    "body_text": "依資源之觀察項目產出 1–3 題。",
                    "objective": "幫助學員觀察經文的具體細節。",
                    "operation_text": "依資源之觀察項目產出 1–3 題。",
                    "referenced_resources": ["observation_guide.md"],
                    "linked_mode_id": "bible_study",
                    "linked_workflow": "查經互動模組",
                    "linked_step_order": 1,
                    "linked_step_title": "細察事實 (Observation)",
                }
            ],
            "instruction_workflows": [
                {
                    "id": "bible_study",
                    "title": "查考經文模式（Bible Study）",
                    "triggers": ["查考", "研經", "經文"],
                    "workflow_name": "查經互動模組",
                    "steps": [
                        {"order": 1, "title": "細察事實 (Observation)", "resource_file": "observation_guide.md"},
                    ],
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["turn_execution_plan"]["turn_intent"], "answer_prior_questions")
        self.assertEqual(out["turn_execution_plan"]["secondary_scopes"][0]["scope_type"], "response_logic")

    def test_short_generation_request_routes_to_freeform_generation_not_bible_study_workflow(self):
        state = self.state.copy()
        state["user_query"] = "生成提摩太前書的查經材料"
        state["global_instruction_context"] = {
            "role_summary": "你是一位專業聖經導師",
            "primary_objectives": ["帶領學員查經"],
        }
        state["template_registry"] = {
            "builder_instructions": "這個應用專注於聖經查考與查經材料。",
            "instruction_workflows": [
                {
                    "id": "bible_study",
                    "title": "查考經文模式（Bible Study）",
                    "triggers": ["查考", "研經", "經文"],
                    "workflow_name": "查經互動模組",
                    "steps": [
                        {"order": 1, "title": "細察事實 (Observation)", "resource_file": "observation_guide.md"},
                    ],
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["turn_execution_plan"]["turn_intent"], "freeform_generation_request")
        self.assertEqual(out["turn_execution_plan"]["presentation_policy"]["mode"], "full_output")
        self.assertEqual(out["instruction_workflow"], {})
        self.assertFalse(out["turn_action_plan"]["response_style"]["instruction_guided"])
        self.assertTrue(out["turn_action_plan"]["response_style"]["is_generation_request"])
        self.assertEqual(out["turn_action_plan"]["response_style"]["generation_subtype"], "freeform")

    def test_structured_generation_brief_routes_to_generation_not_workflow(self):
        state = self.state.copy()
        state["user_query"] = (
            "請根據以下資料生成青年查經材料\\n"
            "用途：青年小組\\n"
            "基本資料：加拉太書 5:22-23\\n"
            "輸出要求：\\n"
            "1. 主題導入\\n"
            "2. 啟發問題\\n"
            "3. 生活應用"
        )
        state["global_instruction_context"] = {"primary_objectives": ["帶領學員查經"]}
        state["template_registry"] = {
            "builder_instructions": "這個應用專注於聖經查考與查經材料。",
            "instruction_workflows": [
                {
                    "id": "bible_study",
                    "title": "查考經文模式（Bible Study）",
                    "triggers": ["查考", "經文"],
                    "workflow_name": "查經互動模組",
                    "steps": [{"order": 1, "title": "細察事實 (Observation)", "resource_file": "observation_guide.md"}],
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["turn_execution_plan"]["turn_intent"], "structured_generation_brief")
        self.assertEqual(out["turn_action_plan"]["response_style"]["generation_subtype"], "structured")
        self.assertEqual(out["instruction_workflow"], {})

    def test_out_of_scope_general_question_bypasses_app_workflow(self):
        state = self.state.copy()
        state["user_query"] = "幫我解釋 Python dataclass 跟 pydantic 差異"
        state["global_instruction_context"] = {
            "role_summary": "你是一位專業聖經導師",
            "primary_objectives": ["帶領學員查經"],
        }
        state["template_registry"] = {
            "builder_instructions": "這個應用專注於聖經查考與講章材料。",
            "instruction_workflows": [
                {
                    "id": "bible_study",
                    "title": "查考經文模式（Bible Study）",
                    "triggers": ["查考", "經文"],
                    "workflow_name": "查經互動模組",
                    "steps": [{"order": 1, "title": "細察事實 (Observation)", "resource_file": "observation_guide.md"}],
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["turn_execution_plan"]["turn_intent"], "general_out_of_scope_question")
        self.assertEqual(out["instruction_workflow"], {})
        self.assertTrue(out["turn_action_plan"]["response_style"]["is_out_of_scope"])

    def test_advances_to_next_workflow_step_from_session_progress(self):
        state = self.state.copy()
        state["user_query"] = "ä¸‹ä¸€æ­¥ï¼Œè«‹å¸¶æˆ‘é€²å…¥èªæ¸…é—œä¿‚"
        state["workflow_progress"] = {
            "workflow_id": "bible_study",
            "workflow_title": "Bible Study",
            "step_order": 1,
            "step_title": "Observation",
            "resource_file": "observation_guide.md",
        }
        state["template_registry"] = {
            "instruction_workflows": [
                {
                    "id": "bible_study",
                    "title": "Bible Study",
                    "triggers": ["æŸ¥è€ƒ", "ç ”ç¶“", "ç¶“æ–‡"],
                    "workflow_name": "æŸ¥ç¶“äº’å‹•æ¨¡çµ„",
                    "steps": [
                        {
                            "order": 1,
                            "title": "ç´°å¯Ÿäº‹å¯¦ (Observation)",
                            "resource_file": "observation_guide.md",
                            "keywords": ["ç´°å¯Ÿäº‹å¯¦", "è§€å¯Ÿ", "observation"],
                        },
                        {
                            "order": 2,
                            "title": "èªæ¸…é—œä¿‚ (Identify Relationships)",
                            "resource_file": "identify_relation_guide.md",
                            "keywords": ["èªæ¸…é—œä¿‚", "é—œä¿‚", "identify relationships"],
                        },
                    ],
                }
            ]
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["instruction_workflow"]["id"], "bible_study")
        self.assertEqual(out["instruction_step"]["order"], 2)
        self.assertEqual(out["instruction_resource"], "identify_relation_guide.md")
        self.assertEqual(out["workflow_progress"]["step_order"], 2)

    def test_builds_turn_action_plan_with_instruction_and_support_retrieval(self):
        state = self.state.copy()
        state["user_query"] = "æŸ¥è€ƒç¶“æ–‡æ™‚ï¼Œé€™å€‹å­—çš„åŽŸæ–‡æ„æ€æ˜¯ä»€éº¼ï¼Ÿ"
        state["workflow_progress"] = {
            "workflow_id": "bible_study",
            "workflow_title": "Bible Study",
            "step_order": 1,
            "step_title": "ç´°å¯Ÿäº‹å¯¦ (Observation)",
            "resource_file": "observation_guide.md",
        }
        state["template_registry"] = {
            "instruction_workflows": [
                {
                    "id": "bible_study",
                    "title": "Bible Study",
                    "triggers": ["æŸ¥è€ƒ", "ç¶“æ–‡"],
                    "workflow_name": "æŸ¥ç¶“äº’å‹•æ¨¡çµ„",
                    "steps": [
                        {
                            "order": 1,
                            "title": "ç´°å¯Ÿäº‹å¯¦ (Observation)",
                            "resource_file": "observation_guide.md",
                            "keywords": ["ç´°å¯Ÿäº‹å¯¦", "è§€å¯Ÿ", "observation"],
                        }
                    ],
                }
            ]
        }
        state["instruction_runtime_model"] = {
            "support_modules": [
                {
                    "module_id": "lexical_support",
                    "title": "Lexical Support",
                    "activation_triggers": [],
                    "resource_ids": ["lexical_support", "legal_context_pdf", "answer_format_template"],
                }
            ],
            "instruction_resources": [
                {
                    "resource_id": "observation_guide",
                    "title": "Observation",
                    "filename": "observation_guide.md",
                    "domain": "instruction_source",
                    "use_type": "primary",
                },
                {
                    "resource_id": "lexical_support",
                    "title": "Lexical Support",
                    "filename": "åŽŸæ–‡å­—ç¾©èˆ‡è­¯æœ¬æ¯”è¼ƒæ”¯æ´.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
                {
                    "resource_id": "legal_context_pdf",
                    "title": "Legal Context",
                    "filename": "åˆæ³•è™•å¢ƒè£œå……ææ–™.pdf",
                    "domain": "knowledge_source",
                    "use_type": "support",
                },
                {
                    "resource_id": "answer_format_template",
                    "title": "Answer Format Template",
                    "filename": "answer_format_template.md",
                    "domain": "output_template",
                    "use_type": "support",
                },
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["session_execution_state"]["execution_status"], "guiding")
        self.assertIn("answer_format_template.md", out["session_execution_state"]["active_template_resources"])
        execution_requests = out["turn_execution_plan"]["resource_requests"]
        instruction_request = next(item for item in execution_requests if item["resource_role"] == "instruction_source")
        self.assertTrue(str(instruction_request["query_text"]).startswith("instruction guidance"))
        self.assertGreaterEqual(len(instruction_request["context_hints"]), 1)
        self.assertEqual(instruction_request["request_reason"], "instruction_load_plan")
        template_request = next(item for item in execution_requests if item["resource_role"] == "output_template")
        self.assertEqual(template_request["request_reason"], "template_load_plan")
        knowledge_request = next(item for item in execution_requests if item["resource_role"] == "knowledge_source")
        self.assertTrue(bool(knowledge_request["query_text"]))
        self.assertEqual(knowledge_request["request_reason"], "knowledge_filename_filter")
        actions = out["turn_execution_plan"]["actions"]
        prepare_action = next(item for item in actions if item["action_type"] == "load_resource")
        self.assertGreaterEqual(prepare_action["params"]["request_count"], 3)
        self.assertIn("instruction_source", prepare_action["params"]["resource_roles"])
        self.assertIn("output_template", prepare_action["params"]["resource_roles"])
        retrieve_action = next(item for item in actions if item["action_type"] == "retrieve_knowledge")
        self.assertTrue(bool(retrieve_action["params"]["query_text"]))
        self.assertTrue(retrieve_action["params"]["retry_on_weak_results"] is False or isinstance(retrieve_action["params"]["retry_on_weak_results"], bool))
        respond_action = next(item for item in actions if item["action_type"] == "respond_to_user")
        self.assertEqual(respond_action["params"]["action_type"], "guide")
        update_state_action = next(item for item in actions if item["action_type"] == "update_session_state")
        self.assertIn("session_execution_state", update_state_action["params"]["state_update_keys"])

    def test_tracks_output_artifact_targets_without_retrieving_them(self):
        state = self.state.copy()
        state["user_query"] = "Please generate Director Bundle output"
        state["template_registry"] = {
            "instruction_modules": [
                {
                    "id": "director_bundle_spec",
                    "title": "Director Bundle Workflow",
                    "primary_resource": "Director_Bundle_Spec.md",
                    "resource_files": ["Director_Bundle_Spec.md"],
                    "keywords": ["director bundle", "bundle spec"],
                }
            ]
        }
        state["instruction_runtime_model"] = {
            "instruction_resources": [
                {
                    "resource_id": "director_bundle_spec",
                    "title": "Director Bundle Workflow",
                    "filename": "Director_Bundle_Spec.md",
                    "domain": "output_template",
                    "use_type": "primary",
                },
                {
                    "resource_id": "director_bundle_output",
                    "title": "Director Bundle Output",
                    "filename": "Director Bundle.md",
                    "domain": "output_artifact",
                    "use_type": "auxiliary",
                },
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        self.assertIn("Director Bundle.md", out["session_execution_state"]["output_artifact_targets"])
        template_request = next(item for item in out["turn_execution_plan"]["resource_requests"] if item["resource_role"] == "output_template")
        self.assertEqual(template_request["load_strategy_hint"], "inline_full")
        self.assertEqual(template_request["filename"], "Director_Bundle_Spec.md")
        assemble_action = next(
            item for item in out["turn_execution_plan"]["actions"] if item["action_type"] == "assemble_output"
        )
        self.assertEqual(assemble_action["params"]["target_outputs"], ["Director Bundle.md"])
        self.assertEqual(assemble_action["params"]["source_output_key"], "final_answer")
        validate_action = next(
            item for item in out["turn_execution_plan"]["actions"] if item["action_type"] == "validate_output"
        )
        self.assertEqual(validate_action["params"]["target_outputs"], ["Director Bundle.md"])
        self.assertEqual(validate_action["params"]["validation_scope"], "output_artifacts")

    def test_builds_knowledge_query_variants_for_complex_turns(self):
        state = self.state.copy()
        state["user_query"] = "Ã¨Â«â€¹Ã§Â¸Â½Ã§ÂµÂÃ§Â´â€žÃ§Â¿Â°Ã§Â¦ÂÃ©Å¸Â³17Ã§Â«Â Ã§Å¡â€žÃ§Â¦Â±Ã¥â€˜Å Ã©â€¡ÂÃ©Â»Å¾Ã¯Â¼Å’Ã¤Â¸Â¦Ã¨ÂªÂªÃ¦ËœÅ½Ã¥â€¦Â¶Ã§ÂµÂÃ¦Â§â€¹Ã¨Ë†â€¡Ã©â€”Å“Ã©ÂÂµÃ¤Â¸Â»Ã©Â¡Å’"
        state["chat_history"] = [{"role": "user", "content": "Ã¦Å¸Â¥Ã¨â‚¬Æ’Ã§Â¶â€œÃ¦â€“â€¡Ã§Â´â€žÃ§Â¿Â°Ã§Â¦ÂÃ©Å¸Â³Ã§Â¬Â¬17Ã§Â«Â "}]

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        retrieve_action = next(item for item in out["turn_execution_plan"]["actions"] if item["action_type"] == "retrieve_knowledge")
        self.assertTrue(retrieve_action["params"]["retry_on_weak_results"])
        alternates = retrieve_action["params"]["query_variants"] + retrieve_action["params"]["fallback_queries"]
        self.assertGreaterEqual(len(alternates), 1)
        self.assertTrue(any(query != retrieve_action["params"]["query_text"] for query in alternates))
        self.assertGreaterEqual(len(retrieve_action["params"]["fallback_queries"]), 1)

    def test_selects_session_upload_evidence_for_uploaded_artifact_analysis(self):
        state = self.state.copy()
        state["user_query"] = "Please analyze this uploaded artifact and review the markdown"
        state["session_uploads"] = [
            {
                "id": "upload-1",
                "filename": "artifact.md",
                "mime_type": "text/markdown",
                "text_content": "# Draft\nExample artifact",
            }
        ]

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        upload_ids = [
            item["resource_id"]
            for item in out["turn_execution_plan"]["resource_requests"]
            if item["purpose"] == "session_upload"
        ]
        self.assertEqual(upload_ids, ["upload-1"])
        self.assertEqual(out["session_execution_state"]["active_session_upload_ids"], ["upload-1"])

    def test_selects_session_upload_evidence_from_upload_event_without_query_markers(self):
        state = self.state.copy()
        state["user_query"] = "Please help"
        state["turn_input_type"] = "session_upload"
        state["session_upload_event_ids"] = ["upload-2"]
        state["session_uploads"] = [
            {"id": "upload-1", "filename": "older.md", "text_content": "Older upload"},
            {"id": "upload-2", "filename": "latest.md", "text_content": "Latest upload"},
        ]

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        upload_ids = [
            item["resource_id"]
            for item in out["turn_execution_plan"]["resource_requests"]
            if item["purpose"] == "session_upload"
        ]
        self.assertEqual(upload_ids, ["upload-2"])
        self.assertEqual(out["session_execution_state"]["active_session_upload_ids"], ["upload-2"])
        self.assertEqual(out["session_execution_state"]["last_input_type"], "session_upload")

    def test_reuses_active_session_upload_for_ambiguous_compare_followup(self):
        state = self.state.copy()
        state["user_query"] = "Compare this with the template"
        state["session_uploads"] = [
            {"id": "upload-1", "filename": "artifact.md", "text_content": "artifact body"},
        ]
        state["session_execution_state"] = {
            "active_session_upload_ids": ["upload-1"],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        upload_ids = [
            item["resource_id"]
            for item in out["turn_execution_plan"]["resource_requests"]
            if item["purpose"] == "session_upload"
        ]
        self.assertEqual(upload_ids, ["upload-1"])
        self.assertEqual(out["session_execution_state"]["active_session_upload_ids"], ["upload-1"])

    def test_selects_upload_by_explicit_filename_reference(self):
        state = self.state.copy()
        state["user_query"] = "Review storyboard_v2.md against the template"
        state["session_uploads"] = [
            {"id": "upload-1", "filename": "notes.md", "text_content": "notes"},
            {"id": "upload-2", "filename": "storyboard_v2.md", "text_content": "storyboard"},
        ]

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        upload_ids = [
            item["resource_id"]
            for item in out["turn_execution_plan"]["resource_requests"]
            if item["purpose"] == "session_upload"
        ]
        self.assertEqual(upload_ids, ["upload-2"])

    def test_selects_latest_upload_when_query_says_latest(self):
        state = self.state.copy()
        state["user_query"] = "Analyze the latest upload"
        state["session_uploads"] = [
            {"id": "upload-1", "filename": "older.md", "text_content": "older"},
            {"id": "upload-2", "filename": "newer.md", "text_content": "newer"},
        ]

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        upload_ids = [
            item["resource_id"]
            for item in out["turn_execution_plan"]["resource_requests"]
            if item["purpose"] == "session_upload"
        ]
        self.assertEqual(upload_ids, ["upload-2"])

    def test_selects_previous_upload_relative_to_active_upload(self):
        state = self.state.copy()
        state["user_query"] = "Review the previous upload"
        state["session_uploads"] = [
            {"id": "upload-1", "filename": "first.md", "text_content": "first"},
            {"id": "upload-2", "filename": "second.md", "text_content": "second"},
            {"id": "upload-3", "filename": "third.md", "text_content": "third"},
        ]
        state["session_execution_state"] = {
            "active_session_upload_ids": ["upload-3"],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        upload_ids = [
            item["resource_id"]
            for item in out["turn_execution_plan"]["resource_requests"]
            if item["purpose"] == "session_upload"
        ]
        self.assertEqual(upload_ids, ["upload-2"])

    def test_vibe_story_director_emits_artifact_assembly_and_validation_actions(self):
        state = self.state.copy()
        state["user_query"] = "Generate a director bundle for this animation concept"
        state["template_registry"] = {
            "instruction_modules": [
                {
                    "id": "director_bundle_module",
                    "title": "Director Bundle Planning",
                    "primary_resource": "Director_Bundle_Spec.md",
                    "resource_files": ["Director_Bundle_Spec.md"],
                    "keywords": ["director bundle", "animation concept", "story director"],
                }
            ]
        }
        state["instruction_runtime_model"] = {
            "instruction_resources": [
                {
                    "resource_id": "director_bundle_spec",
                    "title": "Director Bundle Spec",
                    "filename": "Director_Bundle_Spec.md",
                    "domain": "output_template",
                    "use_type": "primary",
                },
                {
                    "resource_id": "director_bundle_output",
                    "title": "Director Bundle Output",
                    "filename": "Director Bundle.md",
                    "domain": "output_artifact",
                    "use_type": "auxiliary",
                },
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        action_types = [item["action_type"] for item in out["turn_execution_plan"]["actions"]]
        self.assertIn("load_resource", action_types)
        self.assertIn("assemble_output", action_types)
        self.assertIn("validate_output", action_types)
        self.assertIn("Director Bundle.md", out["session_execution_state"]["output_artifact_targets"])

    def test_church_instruction_designer_emits_instruction_and_template_resource_requests(self):
        state = self.state.copy()
        state["user_query"] = "Design a church ministry workshop outline with a structured output"
        state["template_registry"] = {
            "instruction_modules": [
                {
                    "id": "ministry_workshop_designer",
                    "title": "Church Ministry Workshop Designer",
                    "primary_resource": "workshop_outline_template.md",
                    "resource_files": ["workshop_outline_template.md", "ministry_design_guide.md"],
                    "keywords": ["church ministry", "workshop outline", "ministry design"],
                }
            ]
        }
        state["instruction_runtime_model"] = {
            "instruction_resources": [
                {
                    "resource_id": "workshop_outline_template",
                    "title": "Workshop Outline Template",
                    "filename": "workshop_outline_template.md",
                    "domain": "output_template",
                    "use_type": "primary",
                },
                {
                    "resource_id": "ministry_design_guide",
                    "title": "Ministry Design Guide",
                    "filename": "ministry_design_guide.md",
                    "domain": "instruction_source",
                    "use_type": "auxiliary",
                },
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        requests = out["turn_execution_plan"]["resource_requests"]
        roles = {item["resource_role"] for item in requests}
        self.assertIn("output_template", roles)
        self.assertEqual(out["session_execution_state"]["active_template_resources"], ["workshop_outline_template.md"])

    def test_direct_module_trigger_sets_module_as_primary_scope_without_layered_step_fields(self):
        state = self.state.copy()
        state["user_query"] = "Help me define the GPT application interaction configuration"
        state["template_registry"] = {
            "instruction_modules": [
                {
                    "id": "gpt_interaction_configuration",
                    "title": "GPT Application Interaction Configuration",
                    "primary_resource": "application_discovery_brief.md",
                    "resource_files": ["application_discovery_brief.md"],
                    "keywords": ["interaction configuration", "gpt application"],
                }
            ]
        }
        state["instruction_runtime_model"] = {
            "instruction_resources": [
                {
                    "resource_id": "application_discovery_brief",
                    "title": "Application Discovery Brief",
                    "filename": "application_discovery_brief.md",
                    "domain": "instruction_source",
                    "use_type": "primary",
                }
            ]
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)

        self.assertEqual(out["turn_execution_plan"]["primary_scope"]["scope_type"], "module")
        self.assertEqual(
            out["turn_execution_plan"]["primary_scope"]["scope_id"],
            "module:gpt_application_interaction_configuration",
        )
        self.assertEqual(
            out["session_execution_state"]["primary_scope_id"],
            "module:gpt_application_interaction_configuration",
        )
        self.assertEqual(out["session_execution_state"]["primary_scope_type"], "module")
        self.assertEqual(
            out["session_execution_state"]["primary_scope_title"],
            "GPT Application Interaction Configuration",
        )
        self.assertIsNone(out["session_execution_state"]["active_step_scope_id"])
        self.assertIsNone(out["session_execution_state"]["primary_support_module_id"])
        self.assertIsNone(out["session_execution_state"]["primary_support_module_title"])
        self.assertIsNone(out["session_execution_state"]["procedure_step_activation"])
        self.assertIsNone(out["session_execution_state"]["primary_support_module_activation"])

        request = next(
            item
            for item in out["turn_execution_plan"]["resource_requests"]
            if item.get("filename") == "application_discovery_brief.md"
        )
        self.assertEqual(request["source_layer"], "direct_query")
        self.assertIsNone(request["step_scope_id"])
        self.assertIsNone(request["support_module_id"])

    def test_church_ministry_first_turn_activates_default_primary_workflow(self):
        root = Path(__file__).resolve().parent / "_workdirs" / "planner_church_default_workflow"
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        try:
            domains = root / "domains"
            prompts = root / "prompts"
            _write_domain_fixture(domains)
            prompts.mkdir(parents=True, exist_ok=True)

            markdown = """
## Mode Detection
• Ministry Prompt Design
  o Trigger: query includes 「prompt」 「ministry」
  o Start full workflow: Interaction Logic & Execution Flow

## Interaction Logic & Execution Flow
### Step 0: Clarify the Need
Use Ministry_Discovery_Questions.md to collect the missing ministry details.

## Knowledge Modules
- template_library.md
"""
            state = self.state.copy()
            state["user_query"] = "幫助基督徒學習高階的指令技巧"
            state["template_version"] = 1
            state["template_registry"] = {"builder_instructions": markdown}
            state = load_template_registry.run(state, domains_base_dir=domains, prompts_dir=prompts)

            def llm(_prompt, _tools, _context):
                output = json.loads(json.dumps(self.valid))
                output["normalizedQuery"] = state["user_query"]
                output["contextualQuery"] = state["user_query"]
                output["retrievalPlan"]["query_text"] = state["user_query"]
                return output

            out = planner.run(state, llm_planner=llm)
            plan = out["turn_execution_plan"]

            self.assertEqual(plan["active_service_block_type"], "primary_workflow")
            self.assertEqual(plan["primary_scope"]["scope_type"], "workflow")
            self.assertEqual(
                plan["primary_scope"]["title"],
                "Interaction Logic & Execution Flow",
            )
            self.assertEqual(
                out["session_execution_state"]["primary_scope_id"],
                "workflow:interaction_logic_execution_flow",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_grow_with_children_scripture_request_does_not_force_supplementary_workflow(self):
        root = Path(__file__).resolve().parent / "_workdirs" / "planner_grow_with_children_supplementary"
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        try:
            domains = root / "domains"
            prompts = root / "prompts"
            _write_domain_fixture(domains)
            prompts.mkdir(parents=True, exist_ok=True)

            markdown = """
## 互動模式
- 3×1 建議清單
- 按步就班
- 深度解析

## 查經互動模組（歸納釋經法的十個步驟, Supplementary Module）
1. 細察事實
Use 歸納釋經法 102025.pdf
"""
            state = self.state.copy()
            state["user_query"] = "我想查考一段經文"
            state["template_version"] = 1
            state["template_registry"] = {"builder_instructions": markdown}
            state = load_template_registry.run(state, domains_base_dir=domains, prompts_dir=prompts)

            def llm(_prompt, _tools, _context):
                output = json.loads(json.dumps(self.valid))
                output["normalizedQuery"] = state["user_query"]
                output["contextualQuery"] = state["user_query"]
                output["retrievalPlan"]["query_text"] = state["user_query"]
                return output

            out = planner.run(state, llm_planner=llm)
            plan = out["turn_execution_plan"]

            self.assertNotEqual(plan["active_service_block_type"], "supplementary_workflow")
            if isinstance(plan.get("primary_scope"), dict):
                self.assertNotEqual(plan["primary_scope"].get("scope_type"), "workflow")
            self.assertIsNone(plan.get("primary_support_module_scope"))
            self.assertIsNone(out["session_execution_state"]["active_step_scope_id"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_procedure_trigger_keeps_procedure_primary_and_attaches_step_support_provenance(self):
        root = Path(__file__).resolve().parent / "_workdirs" / "planner_procedure_scope_layering"
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        try:
            domains = root / "domains"
            prompts = root / "prompts"
            _write_domain_fixture(domains)
            prompts.mkdir(parents=True, exist_ok=True)

            markdown = """
## Interaction Logic & Execution Flow
1. Clarify the Ministry Need
Objective: Ground the request before proposing any solution.
Use Ministry_Discovery_Questions.md to collect the missing ministry details.
When doctrine or terminology needs review, activate the Theological Alignment Support Module and use Theology_Guardrails.md.

2. Shape the Ministry Prompt
Objective: Turn the approved intent into a structured ministry prompt.
Use Ministry_Prompt_Framework.md before drafting the final answer.

## Theological Alignment Support Module
Use Theology_Guardrails.md and Denomination_Terms.md when the ministry request needs doctrinal review.
"""
            state = self.state.copy()
            state["user_query"] = "The ministry request needs doctrine and terminology review"
            state["template_version"] = 1
            state["template_registry"] = {"builder_instructions": markdown}
            state["workflow_progress"] = {
                "workflow_id": "interaction_logic_execution_flow",
                "workflow_title": "Interaction Logic & Execution Flow",
                "step_order": 1,
                "step_title": "Clarify the Ministry Need",
                "resource_file": "Ministry_Discovery_Questions.md",
            }
            state = load_template_registry.run(state, domains_base_dir=domains, prompts_dir=prompts)

            def llm(_prompt, _tools, _context):
                output = json.loads(json.dumps(self.valid))
                output["normalizedQuery"] = state["user_query"]
                output["contextualQuery"] = state["user_query"]
                output["retrievalPlan"]["query_text"] = state["user_query"]
                return output

            out = planner.run(state, llm_planner=llm)

            self.assertEqual(out["turn_execution_plan"]["primary_scope"]["scope_type"], "workflow")
            self.assertEqual(
                out["turn_execution_plan"]["primary_scope"]["scope_id"],
                "workflow:interaction_logic_execution_flow",
            )
            self.assertEqual(
                out["turn_execution_plan"]["active_step_scope"]["scope_id"],
                "step:interaction_logic_execution_flow:1",
            )
            self.assertEqual(
                out["turn_execution_plan"]["active_step_scope"]["scope_type"],
                "step",
            )
            self.assertEqual(
                out["turn_execution_plan"]["active_step_scope"]["title"],
                "Clarify the Ministry Need",
            )
            self.assertEqual(
                out["turn_execution_plan"]["primary_support_module_scope"]["scope_id"],
                "theological_alignment_support_module",
            )
            self.assertEqual(
                out["turn_execution_plan"]["primary_support_module_scope"]["scope_type"],
                "module",
            )
            self.assertEqual(
                out["turn_execution_plan"]["primary_support_module_scope"]["title"],
                "Theological Alignment Support Module",
            )
            self.assertEqual(
                out["session_execution_state"]["primary_scope_id"],
                "workflow:interaction_logic_execution_flow",
            )
            self.assertEqual(out["session_execution_state"]["primary_scope_type"], "workflow")
            self.assertEqual(
                out["session_execution_state"]["primary_scope_title"],
                "Interaction Logic & Execution Flow",
            )
            self.assertEqual(
                out["session_execution_state"]["active_step_scope_id"],
                "step:interaction_logic_execution_flow:1",
            )
            self.assertEqual(
                out["session_execution_state"]["primary_support_module_id"],
                "theological_alignment_support_module",
            )
            self.assertEqual(
                out["session_execution_state"]["primary_support_module_title"],
                "Theological Alignment Support Module",
            )
            self.assertEqual(
                out["session_execution_state"]["procedure_step_activation"]["step_scope_id"],
                "step:interaction_logic_execution_flow:1",
            )
            self.assertEqual(
                out["session_execution_state"]["procedure_step_activation"]["primary_support_module_id"],
                "theological_alignment_support_module",
            )
            self.assertEqual(
                out["session_execution_state"]["primary_support_module_activation"]["support_module_id"],
                "theological_alignment_support_module",
            )
            self.assertEqual(
                out["session_execution_state"]["primary_support_module_activation"]["step_scope_id"],
                "step:interaction_logic_execution_flow:1",
            )

            requests_by_filename = {
                item["filename"]: item
                for item in out["turn_execution_plan"]["resource_requests"]
                if item.get("filename")
            }
            self.assertEqual(
                requests_by_filename["Ministry_Discovery_Questions.md"]["source_layer"],
                "procedure_step",
            )
            self.assertEqual(
                requests_by_filename["Ministry_Discovery_Questions.md"]["step_scope_id"],
                "step:interaction_logic_execution_flow:1",
            )
            self.assertIsNone(requests_by_filename["Ministry_Discovery_Questions.md"]["support_module_id"])
            self.assertEqual(
                requests_by_filename["Theology_Guardrails.md"]["source_layer"],
                "support_module",
            )
            self.assertEqual(
                requests_by_filename["Theology_Guardrails.md"]["step_scope_id"],
                "step:interaction_logic_execution_flow:1",
            )
            self.assertEqual(
                requests_by_filename["Theology_Guardrails.md"]["support_module_id"],
                "theological_alignment_support_module",
            )
            self.assertEqual(
                requests_by_filename["Denomination_Terms.md"]["source_layer"],
                "support_module",
            )
            self.assertEqual(
                requests_by_filename["Denomination_Terms.md"]["step_scope_id"],
                "step:interaction_logic_execution_flow:1",
            )
            self.assertEqual(
                requests_by_filename["Denomination_Terms.md"]["support_module_id"],
                "theological_alignment_support_module",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_church_ministry_clarification_turn_stays_on_interactive_step(self):
        root = Path(__file__).resolve().parent / "_workdirs" / "planner_church_interactive_clarification"
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        try:
            domains = root / "domains"
            prompts = root / "prompts"
            _write_domain_fixture(domains)
            prompts.mkdir(parents=True, exist_ok=True)

            markdown = """
## Interaction Logic & Execution Flow
0. Clarify the Ministry Goal
Ask one question to clarify the ministry request before drafting anything.
Use Ministry_Discovery_Questions.md.

1. Confirm the Ministry Constraints
Wait for user confirmation on denomination, audience, and ministry tone.
Use Ministry_Constraint_Checklist.md.

2. Generate the Ministry Prompt Draft
Generate the first structured ministry prompt using Ministry_Prompt_Framework.md.

3. Route the Tool and Module Pair
Route the prompt through the correct tool pair using tool_selection_map.md.

4. Validate the Prompt Output
Use ministry_output_rules.md and ministry_prompt_guardrails.md to validate the draft.

5. Finalize the Delivery Package
Assemble the final delivery package using delivery_package_template.md.
"""
            state = self.state.copy()
            state["user_query"] = "The audience is youth ministry leaders and the tone should be pastoral."
            state["template_version"] = 1
            state["template_registry"] = {"builder_instructions": markdown}
            state["workflow_progress"] = {
                "workflow_id": "interaction_logic_execution_flow",
                "workflow_title": "Interaction Logic & Execution Flow",
                "step_order": 1,
                "step_title": "Confirm the Ministry Constraints",
                "resource_file": "Ministry_Constraint_Checklist.md",
            }
            state = load_template_registry.run(state, domains_base_dir=domains, prompts_dir=prompts)

            def llm(_prompt, _tools, _context):
                output = json.loads(json.dumps(self.valid))
                output["normalizedQuery"] = state["user_query"]
                output["contextualQuery"] = state["user_query"]
                output["retrievalPlan"]["query_text"] = state["user_query"]
                return output

            out = planner.run(state, llm_planner=llm)

            self.assertEqual(out["instruction_step"]["order"], 1)
            self.assertEqual(
                out["turn_execution_plan"]["active_step_scope"]["scope_id"],
                "step:interaction_logic_execution_flow:1",
            )
            self.assertIsNone(out["turn_execution_plan"]["active_execution_mode"])
            self.assertEqual(out["turn_execution_plan"]["active_bundled_step_ids"], [])
            self.assertIsNone(out["turn_execution_plan"]["bundled_entry_step_id"])
            self.assertIsNone(out["session_execution_state"]["active_execution_mode"])
            self.assertEqual(out["session_execution_state"]["active_bundled_step_ids"], [])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_church_ministry_continue_turn_selects_bundled_entry_step_and_aggregates_bundled_resources(self):
        root = Path(__file__).resolve().parent / "_workdirs" / "planner_church_bundled_entry"
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        try:
            domains = root / "domains"
            prompts = root / "prompts"
            _write_domain_fixture(domains)
            prompts.mkdir(parents=True, exist_ok=True)

            markdown = """
## Interaction Logic & Execution Flow
0. Clarify the Ministry Goal
Ask one question to clarify the ministry request before drafting anything.
Use Ministry_Discovery_Questions.md.

1. Confirm the Ministry Constraints
Wait for user confirmation on denomination, audience, and ministry tone.
Use Ministry_Constraint_Checklist.md.

2. Generate the Ministry Prompt Draft
Generate the first structured ministry prompt using Ministry_Prompt_Framework.md.

3. Route the Tool and Module Pair
Route the prompt through the correct tool pair using tool_selection_map.md.

4. Validate the Prompt Output
Use ministry_output_rules.md and ministry_prompt_guardrails.md to validate the draft.

5. Finalize the Delivery Package
Assemble the final delivery package using delivery_package_template.md.
"""
            state = self.state.copy()
            state["user_query"] = "Continue with the confirmed ministry details."
            state["template_version"] = 1
            state["template_registry"] = {"builder_instructions": markdown}
            state["workflow_progress"] = {
                "workflow_id": "interaction_logic_execution_flow",
                "workflow_title": "Interaction Logic & Execution Flow",
                "step_order": 1,
                "step_title": "Confirm the Ministry Constraints",
                "resource_file": "Ministry_Constraint_Checklist.md",
            }
            state = load_template_registry.run(state, domains_base_dir=domains, prompts_dir=prompts)

            def llm(_prompt, _tools, _context):
                output = json.loads(json.dumps(self.valid))
                output["normalizedQuery"] = state["user_query"]
                output["contextualQuery"] = state["user_query"]
                output["retrievalPlan"]["query_text"] = state["user_query"]
                return output

            out = planner.run(state, llm_planner=llm)
            request_filenames = {
                item.get("filename")
                for item in out["turn_execution_plan"]["resource_requests"]
                if item.get("filename")
            }

            self.assertEqual(out["instruction_step"]["order"], 2)
            self.assertEqual(
                out["turn_execution_plan"]["active_step_scope"]["scope_id"],
                "step:interaction_logic_execution_flow:2",
            )
            self.assertEqual(out["turn_execution_plan"]["active_execution_mode"], "bundled")
            self.assertIn(
                "step:interaction_logic_execution_flow:2",
                out["turn_execution_plan"]["active_bundled_step_ids"],
            )
            self.assertIn(
                "step:interaction_logic_execution_flow:3",
                out["turn_execution_plan"]["active_bundled_step_ids"],
            )
            self.assertIn(
                "step:interaction_logic_execution_flow:4",
                out["turn_execution_plan"]["active_bundled_step_ids"],
            )
            self.assertEqual(
                out["turn_execution_plan"]["bundled_entry_step_id"],
                "step:interaction_logic_execution_flow:2",
            )
            self.assertEqual(out["session_execution_state"]["active_execution_mode"], "bundled")
            self.assertEqual(
                out["session_execution_state"]["active_bundled_step_ids"],
                [
                    "step:interaction_logic_execution_flow:2",
                    "step:interaction_logic_execution_flow:3",
                    "step:interaction_logic_execution_flow:4",
                    "step:interaction_logic_execution_flow:5",
                ],
            )
            self.assertEqual(
                out["session_execution_state"]["bundled_entry_step_id"],
                "step:interaction_logic_execution_flow:2",
            )
            self.assertTrue(
                {
                    "Ministry_Prompt_Framework.md",
                    "tool_selection_map.md",
                    "ministry_output_rules.md",
                    "ministry_prompt_guardrails.md",
                    "delivery_package_template.md",
                }.issubset(request_filenames)
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_church_ministry_multi_turn_clarification_answers_advance_into_bundled_generation(self):
        root = Path(__file__).resolve().parent / "_workdirs" / "planner_church_multiturn_bundled_entry"
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        try:
            domains = root / "domains"
            prompts = root / "prompts"
            _write_domain_fixture(domains)
            prompts.mkdir(parents=True, exist_ok=True)

            markdown = """
## Interaction Logic & Execution Flow
0. Clarify the Ministry Goal
Ask one question to clarify the ministry request before drafting anything.
Use Ministry_Discovery_Questions.md.

1. Confirm the Ministry Constraints
Wait for user confirmation on denomination, audience, and ministry tone.
Use Ministry_Constraint_Checklist.md.

2. Generate the Ministry Prompt Draft
Generate the first structured ministry prompt using Ministry_Prompt_Framework.md.

3. Route the Tool and Module Pair
Route the prompt through the correct tool pair using template_library.md and dynamic_prompt_optimizer.md and tool_selection_map.md.

4. Validate the Prompt Output
Use ministry_output_rules.md and ministry_prompt_guardrails.md to validate the draft.

5. Finalize the Delivery Package
Assemble the final delivery package using delivery_package_template.md.
"""
            state = self.state.copy()
            state["user_query"] = "彌迦書 2:1-11"
            state["template_version"] = 1
            state["template_registry"] = {"builder_instructions": markdown}
            state["workflow_progress"] = {
                "workflow_id": "interaction_logic_execution_flow",
                "workflow_title": "Interaction Logic & Execution Flow",
                "step_order": 1,
                "step_title": "Confirm the Ministry Constraints",
                "resource_file": "Ministry_Constraint_Checklist.md",
            }
            state["chat_history"] = [
                {
                    "role": "user",
                    "content": "我想透過【主題或經文】幫助人更深認識神的真理，請幫我建立一個能支持這目的的最佳化提示（prompt）。",
                },
                {"role": "assistant", "content": "請問這份 Prompt 主要要給哪一類對象使用？"},
                {"role": "user", "content": "領袖同工"},
                {"role": "assistant", "content": "請提供要聚焦的主題或經文。"},
            ]
            state = load_template_registry.run(state, domains_base_dir=domains, prompts_dir=prompts)

            def llm(_prompt, _tools, _context):
                output = json.loads(json.dumps(self.valid))
                output["normalizedQuery"] = state["user_query"]
                output["contextualQuery"] = state["user_query"]
                output["retrievalPlan"]["query_text"] = state["user_query"]
                return output

            out = planner.run(state, llm_planner=llm)
            request_filenames = {
                item.get("filename")
                for item in out["turn_execution_plan"]["resource_requests"]
                if item.get("filename")
            }

            self.assertEqual(out["instruction_step"]["order"], 2)
            self.assertEqual(
                out["turn_execution_plan"]["active_step_scope"]["scope_id"],
                "step:interaction_logic_execution_flow:2",
            )
            self.assertEqual(out["turn_execution_plan"]["active_execution_mode"], "bundled")
            self.assertIn(
                "step:interaction_logic_execution_flow:2",
                out["turn_execution_plan"]["active_bundled_step_ids"],
            )
            self.assertIn(
                "step:interaction_logic_execution_flow:3",
                out["turn_execution_plan"]["active_bundled_step_ids"],
            )
            self.assertIn(
                "step:interaction_logic_execution_flow:4",
                out["turn_execution_plan"]["active_bundled_step_ids"],
            )
            self.assertTrue(
                {
                    "Ministry_Prompt_Framework.md",
                    "template_library.md",
                    "dynamic_prompt_optimizer.md",
                    "tool_selection_map.md",
                    "ministry_output_rules.md",
                    "ministry_prompt_guardrails.md",
                }.issubset(request_filenames)
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_church_ministry_non_entry_bundled_member_match_normalizes_to_bundled_entry_metadata(self):
        root = Path(__file__).resolve().parent / "_workdirs" / "planner_church_bundled_member_match"
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        try:
            domains = root / "domains"
            prompts = root / "prompts"
            _write_domain_fixture(domains)
            prompts.mkdir(parents=True, exist_ok=True)

            markdown = """
## Interaction Logic & Execution Flow
0. Clarify the Ministry Goal
Ask one question to clarify the ministry request before drafting anything.
Use Ministry_Discovery_Questions.md.

1. Confirm the Ministry Constraints
Wait for user confirmation on denomination, audience, and ministry tone.
Use Ministry_Constraint_Checklist.md.

2. Generate the Ministry Prompt Draft
Generate the first structured ministry prompt using Ministry_Prompt_Framework.md.

3. Route the Tool and Module Pair
Route the prompt through the correct tool pair using tool_selection_map.md.

4. Validate the Prompt Output
Use ministry_output_rules.md and ministry_prompt_guardrails.md to validate the draft.

5. Finalize the Delivery Package
Assemble the final delivery package using delivery_package_template.md.
"""
            state = self.state.copy()
            state["user_query"] = "Please validate the prompt output against the ministry guardrails."
            state["template_version"] = 1
            state["template_registry"] = {"builder_instructions": markdown}
            state["workflow_progress"] = {
                "workflow_id": "interaction_logic_execution_flow",
                "workflow_title": "Interaction Logic & Execution Flow",
                "step_order": 1,
                "step_title": "Confirm the Ministry Constraints",
                "resource_file": "Ministry_Constraint_Checklist.md",
            }
            state = load_template_registry.run(state, domains_base_dir=domains, prompts_dir=prompts)

            def llm(_prompt, _tools, _context):
                output = json.loads(json.dumps(self.valid))
                output["normalizedQuery"] = state["user_query"]
                output["contextualQuery"] = state["user_query"]
                output["retrievalPlan"]["query_text"] = state["user_query"]
                return output

            out = planner.run(state, llm_planner=llm)
            request_filenames = {
                item.get("filename")
                for item in out["turn_execution_plan"]["resource_requests"]
                if item.get("filename")
            }

            self.assertEqual(out["instruction_step"]["order"], 4)
            self.assertEqual(
                out["turn_execution_plan"]["active_step_scope"]["scope_id"],
                "step:interaction_logic_execution_flow:4",
            )
            self.assertEqual(out["turn_execution_plan"]["active_execution_mode"], "bundled")
            self.assertEqual(
                out["turn_execution_plan"]["active_bundled_step_ids"],
                [
                    "step:interaction_logic_execution_flow:2",
                    "step:interaction_logic_execution_flow:3",
                    "step:interaction_logic_execution_flow:4",
                    "step:interaction_logic_execution_flow:5",
                ],
            )
            self.assertEqual(
                out["turn_execution_plan"]["bundled_entry_step_id"],
                "step:interaction_logic_execution_flow:2",
            )
            self.assertEqual(
                out["session_execution_state"]["bundled_entry_step_id"],
                "step:interaction_logic_execution_flow:2",
            )
            self.assertTrue(
                {
                    "Ministry_Prompt_Framework.md",
                    "tool_selection_map.md",
                    "ministry_output_rules.md",
                    "ministry_prompt_guardrails.md",
                    "delivery_package_template.md",
                }.issubset(request_filenames)
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_bible_tutor_workflow_remains_interactive_without_bundled_execution_state(self):
        state = self.state.copy()
        state["user_query"] = "我想查考約翰福音第17章"
        state["template_registry"] = {
            "instruction_blocks": [
                {
                    "block_id": "mode:bible_study",
                    "block_type": "mode",
                    "title": "查考經文模式（Bible Study）",
                    "body_text": "好的，我們一起用歸納釋經法查考經文。",
                    "activation_triggers": ["查考", "研經", "經文"],
                    "linked_mode_id": "bible_study",
                    "linked_workflow": "查經互動模組",
                },
            ],
            "instruction_workflows": [
                {
                    "id": "bible_study",
                    "title": "查考經文模式（Bible Study）",
                    "triggers": ["查考", "研經", "經文"],
                    "workflow_name": "查經互動模組",
                    "steps": [
                        {
                            "order": 1,
                            "title": "細察事實 (Observation)",
                            "resource_file": "observation_guide.md",
                            "step_scope_id": "step:bible_study:1",
                            "execution_mode": "interactive",
                            "bundled_step_ids": [],
                            "bundled_resource_refs": [],
                            "activation": {
                                "direct_resource_files": ["observation_guide.md"],
                                "primary_support_module_id": None,
                                "primary_support_module_title": None,
                                "support_resource_files": [],
                            },
                        },
                    ],
                },
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        self.assertIsNone(out["turn_execution_plan"]["active_execution_mode"])
        self.assertEqual(out["turn_execution_plan"]["active_bundled_step_ids"], [])
        self.assertIsNone(out["session_execution_state"]["active_execution_mode"])
        self.assertEqual(out["session_execution_state"]["active_bundled_step_ids"], [])

    def test_story_director_short_generation_request_routes_to_freeform_generation(self):
        state = self.state.copy()
        state["user_query"] = "Generate a cinematic story bundle for a desert escape sequence"
        state["template_registry"] = {
            "builder_instructions": "This app creates animated story bundles and scene direction assets.",
            "instruction_modules": [
                {
                    "id": "story_bundle_designer",
                    "title": "Story Bundle Designer",
                    "primary_resource": "story_bundle_template.md",
                    "resource_files": ["story_bundle_template.md", "scene_direction_guide.md"],
                    "keywords": ["story bundle", "cinematic story", "scene direction"],
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_resources": [
                {
                    "resource_id": "story_bundle_template",
                    "title": "Story Bundle Template",
                    "filename": "story_bundle_template.md",
                    "domain": "output_template",
                    "use_type": "primary",
                },
                {
                    "resource_id": "scene_direction_guide",
                    "title": "Scene Direction Guide",
                    "filename": "scene_direction_guide.md",
                    "domain": "instruction_source",
                    "use_type": "auxiliary",
                },
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        self.assertEqual(out["turn_execution_plan"]["turn_intent"], "freeform_generation_request")
        self.assertEqual(out["turn_action_plan"]["response_style"]["generation_subtype"], "freeform")
        roles = {item["resource_role"] for item in out["turn_execution_plan"]["resource_requests"]}
        self.assertIn("output_template", roles)

    def test_out_of_scope_does_not_trigger_when_query_overlaps_app_vocabulary(self):
        state = self.state.copy()
        state["user_query"] = "Python workshop outline for church ministry volunteers"
        state["template_registry"] = {
            "builder_instructions": "This app designs church ministry workshop outlines and facilitation materials.",
            "instruction_modules": [
                {
                    "id": "ministry_workshop_designer",
                    "title": "Church Ministry Workshop Designer",
                    "primary_resource": "workshop_outline_template.md",
                    "resource_files": ["workshop_outline_template.md"],
                    "keywords": ["church ministry", "workshop outline", "volunteers"],
                }
            ],
        }
        state["instruction_runtime_model"] = {
            "instruction_resources": [
                {
                    "resource_id": "workshop_outline_template",
                    "title": "Workshop Outline Template",
                    "filename": "workshop_outline_template.md",
                    "domain": "output_template",
                    "use_type": "primary",
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        self.assertNotEqual(out["turn_execution_plan"]["turn_intent"], "general_out_of_scope_question")
        self.assertFalse(out["turn_action_plan"]["response_style"]["is_out_of_scope"])

    def test_generation_request_activates_phase_binding_with_multi_required_resources(self):
        state = self.state.copy()
        state["user_query"] = "Generate a launch brief for the new product story"
        state["session_execution_state"] = {
            "active_mode": "launch_mode",
            "active_workflow": "Launch Mode",
        }
        state["instruction_runtime_model"] = {
            "instruction_resources": [
                {
                    "resource_id": "brief_guide",
                    "title": "Brief Guide",
                    "filename": "brief_guide.md",
                    "domain": "instruction_source",
                    "use_type": "primary",
                },
                {
                    "resource_id": "tone_rules",
                    "title": "Tone Rules",
                    "filename": "tone_rules.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
            ],
            "phase_resource_bindings": [
                {
                    "binding_id": "binding:launch-generation",
                    "title": "Launch generation bundle",
                    "trigger_type": "phase",
                    "binding_mode": "multi_required",
                    "scope_id": "launch_mode",
                    "trigger_signals": ["generate", "launch brief", "product story"],
                    "resource_ids": ["brief_guide", "tone_rules"],
                    "resource_kinds": ["instruction_resource", "instruction_resource"],
                    "objective": "Produce a launch brief",
                    "activation_reason": "launch generation request",
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        requests = [
            item for item in out["turn_execution_plan"]["resource_requests"]
            if item.get("binding_id") == "binding:launch-generation"
        ]
        self.assertEqual({item["filename"] for item in requests}, {"brief_guide.md", "tone_rules.md"})
        self.assertTrue(all(item["resource_kind"] == "instruction_resource" for item in requests))
        self.assertIn("binding:launch-generation", out["session_execution_state"]["active_binding_ids"])

    def test_command_trigger_turn_activates_command_binding_requests(self):
        state = self.state.copy()
        state["user_query"] = "/generate_video_prompt create a desert chase scene"
        state["instruction_runtime_model"] = {
            "instruction_resources": [
                {
                    "resource_id": "video_prompt_template",
                    "title": "Video Prompt Template",
                    "filename": "video_prompt_template.md",
                    "domain": "output_template",
                    "use_type": "primary",
                }
            ],
            "phase_resource_bindings": [
                {
                    "binding_id": "binding:video-command",
                    "title": "Video prompt command",
                    "trigger_type": "command_trigger",
                    "binding_mode": "single_required",
                    "trigger_signals": ["/generate_video_prompt"],
                    "resource_ids": ["video_prompt_template"],
                    "resource_kinds": ["template_resource"],
                    "objective": "Generate a video prompt",
                    "activation_reason": "command turn",
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        requests = [
            item for item in out["turn_execution_plan"]["resource_requests"]
            if item.get("binding_id") == "binding:video-command"
        ]
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0]["filename"], "video_prompt_template.md")
        self.assertEqual(requests[0]["resource_kind"], "template_resource")
        self.assertIn("binding:video-command", out["session_execution_state"]["active_binding_ids"])

    def test_session_followup_activates_artifact_gate_binding_from_uploaded_artifact(self):
        state = self.state.copy()
        state["user_query"] = "Use the uploaded director bundle to continue the next pass"
        state["session_execution_state"] = {
            "active_mode": "director_mode",
            "active_workflow": "Director Workflow",
        }
        state["session_uploads"] = [
            {
                "id": "upload-bundle",
                "filename": "Director Bundle.md",
                "mime_type": "text/markdown",
                "text_content": "# Director Bundle\nready",
            }
        ]
        state["instruction_runtime_model"] = {
            "phase_resource_bindings": [
                {
                    "binding_id": "binding:director-artifact-gate",
                    "title": "Director bundle follow-up",
                    "trigger_type": "artifact_gate",
                    "binding_mode": "none",
                    "scope_id": "director_mode",
                    "trigger_signals": ["continue", "next pass", "uploaded director bundle"],
                    "artifact_contract": {
                        "mode": "requires_artifact",
                        "artifact_role": "director_bundle",
                        "filename_patterns": ["Director Bundle.md"],
                        "required_for_progression": True,
                        "missing_artifact_prompt": "Upload Director Bundle.md before continuing.",
                    },
                    "objective": "Continue from uploaded artifact",
                    "activation_reason": "follow-up requires uploaded bundle",
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        requests = [
            item for item in out["turn_execution_plan"]["resource_requests"]
            if item.get("binding_id") == "binding:director-artifact-gate"
        ]
        self.assertTrue(requests)
        self.assertTrue(all(item["artifact_role"] == "director_bundle" for item in requests))
        self.assertTrue(all(item["required_for_progression"] for item in requests))
        self.assertIn("binding:director-artifact-gate", out["session_execution_state"]["active_binding_ids"])
        self.assertIn("director_bundle", out["session_execution_state"]["active_artifact_roles"])
        self.assertTrue(
            out["session_execution_state"]["artifact_gate_status"]["binding:director-artifact-gate"]["satisfied"]
        )

    def test_phase_turn_activates_dependency_group_requests_instead_of_single_resource(self):
        state = self.state.copy()
        state["user_query"] = "Please help with the storyboard sequencing phase"
        state["template_registry"] = {
            "instruction_workflows": [
                {
                    "id": "storyboard_flow",
                    "title": "Storyboard Workflow",
                    "workflow_name": "Storyboard Workflow",
                    "triggers": ["storyboard", "sequencing"],
                    "steps": [
                        {
                            "order": 2,
                            "title": "Storyboard Sequencing",
                            "resource_file": "storyboard_primary.md",
                            "keywords": ["storyboard sequencing", "sequencing phase"],
                        }
                    ],
                }
            ]
        }
        state["instruction_runtime_model"] = {
            "instruction_resources": [
                {
                    "resource_id": "storyboard_checklist",
                    "title": "Storyboard Checklist",
                    "filename": "storyboard_checklist.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
                {
                    "resource_id": "scene_beats",
                    "title": "Scene Beats",
                    "filename": "scene_beats.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
            ],
            "dependency_groups": [
                {
                    "group_id": "group:storyboard-pack",
                    "title": "Storyboard Pack",
                    "resource_ids": ["storyboard_checklist", "scene_beats"],
                    "filenames": ["storyboard_checklist.md", "scene_beats.md"],
                }
            ],
            "phase_resource_bindings": [
                {
                    "binding_id": "binding:storyboard-phase",
                    "title": "Storyboard phase pack",
                    "trigger_type": "workflow_step",
                    "binding_mode": "multi_required",
                    "scope_id": "storyboard_flow",
                    "step_order": 2,
                    "trigger_signals": ["sequencing phase", "storyboard sequencing"],
                    "dependency_groups": ["group:storyboard-pack"],
                    "objective": "Support storyboard sequencing",
                    "activation_reason": "phase step bundle",
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        requests = [
            item for item in out["turn_execution_plan"]["resource_requests"]
            if item.get("binding_id") == "binding:storyboard-phase"
        ]
        self.assertEqual({item["dependency_group_id"] for item in requests}, {"group:storyboard-pack"})
        self.assertEqual({item["filename"] for item in requests}, {"storyboard_checklist.md", "scene_beats.md"})
        self.assertIn("binding:storyboard-phase", out["session_execution_state"]["active_binding_ids"])
        self.assertIn("group:storyboard-pack", out["session_execution_state"]["active_dependency_group_ids"])

    def test_step_scoped_binding_matches_when_hydrated_active_step_order_is_string(self):
        state = self.state.copy()
        state["user_query"] = "Continue the storyboard sequencing phase"
        state["session_execution_state"] = {
            "active_mode": "storyboard_flow",
            "active_workflow": "Storyboard Workflow",
            "active_step_order": "2",
            "active_step_title": "Storyboard Sequencing",
            "active_binding_ids": ["binding:storyboard-phase"],
            "active_dependency_group_ids": ["group:storyboard-pack"],
        }
        state["instruction_runtime_model"] = {
            "instruction_resources": [
                {
                    "resource_id": "storyboard_checklist",
                    "title": "Storyboard Checklist",
                    "filename": "storyboard_checklist.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
                {
                    "resource_id": "scene_beats",
                    "title": "Scene Beats",
                    "filename": "scene_beats.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
            ],
            "dependency_groups": [
                {
                    "group_id": "group:storyboard-pack",
                    "title": "Storyboard Pack",
                    "resource_ids": ["storyboard_checklist", "scene_beats"],
                }
            ],
            "phase_resource_bindings": [
                {
                    "binding_id": "binding:storyboard-phase",
                    "title": "Storyboard phase pack",
                    "trigger_type": "workflow_step",
                    "binding_mode": "multi_required",
                    "scope_id": "storyboard_flow",
                    "step_order": 2,
                    "trigger_signals": ["storyboard sequencing"],
                    "dependency_groups": ["group:storyboard-pack"],
                    "objective": "Support storyboard sequencing",
                    "activation_reason": "phase step bundle",
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        requests = [
            item for item in out["turn_execution_plan"]["resource_requests"]
            if item.get("binding_id") == "binding:storyboard-phase"
        ]
        self.assertEqual({item["filename"] for item in requests}, {"storyboard_checklist.md", "scene_beats.md"})
        self.assertIn("group:storyboard-pack", out["session_execution_state"]["active_dependency_group_ids"])

    def test_resumed_followup_reuses_hydrated_artifact_gate_status_without_uploads(self):
        state = self.state.copy()
        state["user_query"] = "Continue with the artifact review"
        state["session_execution_state"] = {
            "active_mode": "artifact_review",
            "active_workflow": "Artifact Review",
            "active_binding_ids": ["binding:artifact-review-gate"],
            "active_artifact_roles": ["review_bundle"],
            "artifact_gate_status": {
                "binding:artifact-review-gate": {
                    "artifact_role": "review_bundle",
                    "required_for_progression": True,
                    "matched_upload_ids": ["upload-review-bundle"],
                    "matched_filenames": ["review_bundle.md"],
                    "satisfied": True,
                    "binding_id": "binding:artifact-review-gate",
                }
            },
        }
        state["instruction_runtime_model"] = {
            "phase_resource_bindings": [
                {
                    "binding_id": "binding:artifact-review-gate",
                    "title": "Artifact review gate",
                    "trigger_type": "artifact_gate",
                    "binding_mode": "none",
                    "scope_id": "artifact_review",
                    "trigger_signals": ["continue", "artifact review"],
                    "artifact_contract": {
                        "mode": "requires_artifact",
                        "artifact_role": "review_bundle",
                        "filename_patterns": ["review_bundle.md"],
                        "required_for_progression": True,
                    },
                    "objective": "Resume review from hydrated artifact gate",
                    "activation_reason": "resumed follow-up",
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        requests = [
            item for item in out["turn_execution_plan"]["resource_requests"]
            if item.get("binding_id") == "binding:artifact-review-gate"
        ]
        self.assertTrue(requests)
        self.assertEqual({item["resource_id"] for item in requests}, {"upload-review-bundle"})
        self.assertTrue(
            out["session_execution_state"]["artifact_gate_status"]["binding:artifact-review-gate"]["satisfied"]
        )

    def test_resumed_artifact_gate_reuse_does_not_cross_bindings_with_same_role(self):
        state = self.state.copy()
        state["user_query"] = "Continue this artifact phase"
        state["session_execution_state"] = {
            "active_mode": "artifact_review",
            "active_workflow": "Artifact Review",
            "active_binding_ids": ["binding:artifact-review-gate-b"],
            "active_artifact_roles": ["shared_bundle"],
            "artifact_gate_status": {
                "binding:artifact-review-gate-a": {
                    "artifact_role": "shared_bundle",
                    "required_for_progression": True,
                    "matched_upload_ids": ["upload-a"],
                    "matched_filenames": ["bundle_a.md"],
                    "satisfied": True,
                    "binding_id": "binding:artifact-review-gate-a",
                }
            },
        }
        state["instruction_runtime_model"] = {
            "phase_resource_bindings": [
                {
                    "binding_id": "binding:artifact-review-gate-b",
                    "title": "Artifact review gate B",
                    "trigger_type": "artifact_gate",
                    "binding_mode": "none",
                    "scope_id": "artifact_review",
                    "trigger_signals": ["continue", "artifact phase"],
                    "artifact_contract": {
                        "mode": "requires_artifact",
                        "artifact_role": "shared_bundle",
                        "filename_patterns": ["bundle_b.md"],
                        "required_for_progression": True,
                    },
                    "objective": "Resume review from matching binding only",
                    "activation_reason": "resumed follow-up",
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        requests = [
            item for item in out["turn_execution_plan"]["resource_requests"]
            if item.get("binding_id") == "binding:artifact-review-gate-b"
        ]
        self.assertFalse(requests)
        self.assertFalse(
            out["session_execution_state"]["artifact_gate_status"]["binding:artifact-review-gate-b"]["satisfied"]
        )

    def test_followup_reuses_hydrated_dependency_group_binding_context(self):
        state = self.state.copy()
        state["user_query"] = "Continue this phase and refine it"
        state["session_execution_state"] = {
            "active_mode": "storyboard_flow",
            "active_workflow": "Storyboard Workflow",
            "active_step_order": 2,
            "active_step_title": "Storyboard Sequencing",
            "active_binding_ids": ["binding:storyboard-phase"],
            "active_dependency_group_ids": ["group:storyboard-pack"],
        }
        state["instruction_runtime_model"] = {
            "instruction_resources": [
                {
                    "resource_id": "storyboard_checklist",
                    "title": "Storyboard Checklist",
                    "filename": "storyboard_checklist.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
                {
                    "resource_id": "scene_beats",
                    "title": "Scene Beats",
                    "filename": "scene_beats.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
            ],
            "dependency_groups": [
                {
                    "group_id": "group:storyboard-pack",
                    "title": "Storyboard Pack",
                    "resource_ids": ["storyboard_checklist", "scene_beats"],
                }
            ],
            "phase_resource_bindings": [
                {
                    "binding_id": "binding:storyboard-phase",
                    "title": "Storyboard phase pack",
                    "trigger_type": "workflow_step",
                    "binding_mode": "multi_required",
                    "scope_id": "storyboard_flow",
                    "step_order": 2,
                    "dependency_groups": ["group:storyboard-pack"],
                    "objective": "Support storyboard sequencing",
                    "activation_reason": "phase step bundle",
                }
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        requests = [
            item for item in out["turn_execution_plan"]["resource_requests"]
            if item.get("binding_id") == "binding:storyboard-phase"
        ]
        self.assertEqual({item["dependency_group_id"] for item in requests}, {"group:storyboard-pack"})
        self.assertEqual({item["filename"] for item in requests}, {"storyboard_checklist.md", "scene_beats.md"})

    def test_church_ministry_prompt_designer_bindings_activate_route_output_bundle_and_tool_pair(self):
        state = self.state.copy()
        state["user_query"] = "Design a church ministry prompt using the template route and tool selection mapping"
        state["instruction_runtime_model"] = {
            "instruction_resources": [
                {
                    "resource_id": "template_library",
                    "title": "Template Library",
                    "filename": "template_library.md",
                    "domain": "output_template",
                    "use_type": "primary",
                },
                {
                    "resource_id": "dynamic_optimizer",
                    "title": "Dynamic Prompt Optimizer",
                    "filename": "dynamic_prompt_optimizer.md",
                    "domain": "instruction_source",
                    "use_type": "primary",
                },
                {
                    "resource_id": "ministry_output_rules",
                    "title": "Ministry Output Rules",
                    "filename": "ministry_output_rules.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
                {
                    "resource_id": "ministry_prompt_guardrails",
                    "title": "Ministry Prompt Guardrails",
                    "filename": "ministry_prompt_guardrails.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
                {
                    "resource_id": "tool_selection_map",
                    "title": "Tool Selection Map",
                    "filename": "tool_selection_map.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
                {
                    "resource_id": "tool_usage_matrix",
                    "title": "Tool Usage Matrix",
                    "filename": "tool_usage_matrix.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
            ],
            "dependency_groups": [
                {
                    "group_id": "group:ministry-output-rules",
                    "title": "Church Ministry Prompt Designer Output Rules",
                    "resource_ids": ["ministry_output_rules", "ministry_prompt_guardrails"],
                },
                {
                    "group_id": "group:tool-selection-pair",
                    "title": "Church Ministry Prompt Designer Tool Selection Mapping",
                    "resource_ids": ["tool_selection_map", "tool_usage_matrix"],
                },
            ],
            "phase_resource_bindings": [
                {
                    "binding_id": "binding:ministry-route",
                    "title": "Church Ministry Prompt Designer Template Routing",
                    "trigger_type": "phase",
                    "binding_mode": "one_of",
                    "trigger_signals": ["template route"],
                    "resource_ids": ["template_library", "dynamic_optimizer"],
                    "resource_kinds": ["template_resource", "instruction_resource"],
                    "objective": "Route the ministry prompt through the right source",
                    "activation_reason": "route the ministry design request",
                },
                {
                    "binding_id": "binding:ministry-output-rules",
                    "title": "Church Ministry Prompt Designer Output Rules",
                    "trigger_type": "phase",
                    "binding_mode": "multi_required",
                    "trigger_signals": ["church ministry prompt"],
                    "dependency_groups": ["group:ministry-output-rules"],
                    "resource_kinds": ["instruction_resource"],
                    "objective": "Apply the ministry output rule bundle",
                    "activation_reason": "generation requires output rules",
                },
                {
                    "binding_id": "binding:tool-selection-pair",
                    "title": "Church Ministry Prompt Designer Tool Selection Mapping",
                    "trigger_type": "phase",
                    "binding_mode": "multi_required",
                    "trigger_signals": ["tool selection mapping"],
                    "dependency_groups": ["group:tool-selection-pair"],
                    "resource_kinds": ["instruction_resource"],
                    "objective": "Map the supporting tool pair",
                    "activation_reason": "tool selection support",
                },
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        requests = {
            item["filename"]: item
            for item in out["turn_execution_plan"]["resource_requests"]
            if item.get("binding_id") in {
                "binding:ministry-route",
                "binding:ministry-output-rules",
                "binding:tool-selection-pair",
            }
        }

        self.assertEqual(
            set(requests),
            {
                "template_library.md",
                "dynamic_prompt_optimizer.md",
                "ministry_output_rules.md",
                "ministry_prompt_guardrails.md",
                "tool_selection_map.md",
                "tool_usage_matrix.md",
            },
        )
        self.assertEqual(requests["template_library.md"]["resource_kind"], "template_resource")
        self.assertEqual(requests["dynamic_prompt_optimizer.md"]["resource_kind"], "instruction_resource")
        self.assertEqual(requests["ministry_output_rules.md"]["dependency_group_id"], "group:ministry-output-rules")
        self.assertEqual(requests["tool_selection_map.md"]["dependency_group_id"], "group:tool-selection-pair")
        self.assertEqual(
            set(out["session_execution_state"]["active_binding_ids"]),
            {
                "binding:ministry-route",
                "binding:ministry-output-rules",
                "binding:tool-selection-pair",
            },
        )
        self.assertEqual(
            set(out["session_execution_state"]["active_dependency_group_ids"]),
            {"group:ministry-output-rules", "group:tool-selection-pair"},
        )

    def test_church_ministry_refinement_followup_reuses_prior_generation_binding_context(self):
        state = self.state.copy()
        state["user_query"] = "優化此 Prompt for 同工培訓"
        state["chat_history"] = [
            {"role": "user", "content": "Create an optimized prompt to 幫助基督徒學習高階的指令技巧"},
            {"role": "assistant", "content": "這是上一輪生成的 Prompt 草稿。"},
        ]
        state["session_execution_state"] = {
            "active_binding_ids": [
                "binding:ministry-route",
                "binding:ministry-output-rules",
                "binding:tool-selection-pair",
            ],
            "active_dependency_group_ids": ["group:ministry-output-rules", "group:tool-selection-pair"],
            "execution_status": "answering",
            "last_turn_action": "answer",
        }
        state["instruction_runtime_model"] = {
            "instruction_resources": [
                {
                    "resource_id": "template_library",
                    "title": "Template Library",
                    "filename": "template_library.md",
                    "domain": "output_template",
                    "use_type": "primary",
                },
                {
                    "resource_id": "dynamic_optimizer",
                    "title": "Dynamic Prompt Optimizer",
                    "filename": "dynamic_prompt_optimizer.md",
                    "domain": "instruction_source",
                    "use_type": "primary",
                },
                {
                    "resource_id": "ministry_output_rules",
                    "title": "Ministry Output Rules",
                    "filename": "ministry_output_rules.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
                {
                    "resource_id": "ministry_prompt_guardrails",
                    "title": "Ministry Prompt Guardrails",
                    "filename": "ministry_prompt_guardrails.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
                {
                    "resource_id": "tool_selection_map",
                    "title": "Tool Selection Map",
                    "filename": "tool_selection_map.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
                {
                    "resource_id": "tool_usage_matrix",
                    "title": "Tool Usage Matrix",
                    "filename": "tool_usage_matrix.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
            ],
            "dependency_groups": [
                {
                    "group_id": "group:ministry-output-rules",
                    "title": "Church Ministry Prompt Designer Output Rules",
                    "resource_ids": ["ministry_output_rules", "ministry_prompt_guardrails"],
                },
                {
                    "group_id": "group:tool-selection-pair",
                    "title": "Church Ministry Prompt Designer Tool Selection Mapping",
                    "resource_ids": ["tool_selection_map", "tool_usage_matrix"],
                },
            ],
            "phase_resource_bindings": [
                {
                    "binding_id": "binding:ministry-route",
                    "title": "Church Ministry Prompt Designer Template Routing",
                    "trigger_type": "phase",
                    "binding_mode": "one_of",
                    "trigger_signals": ["template route"],
                    "resource_ids": ["template_library", "dynamic_optimizer"],
                    "resource_kinds": ["template_resource", "instruction_resource"],
                    "objective": "Route the ministry prompt through the right source",
                    "activation_reason": "route the ministry design request",
                },
                {
                    "binding_id": "binding:ministry-output-rules",
                    "title": "Church Ministry Prompt Designer Output Rules",
                    "trigger_type": "phase",
                    "binding_mode": "multi_required",
                    "trigger_signals": ["church ministry prompt"],
                    "dependency_groups": ["group:ministry-output-rules"],
                    "resource_kinds": ["instruction_resource"],
                    "objective": "Apply the ministry output rule bundle",
                    "activation_reason": "generation requires output rules",
                },
                {
                    "binding_id": "binding:tool-selection-pair",
                    "title": "Church Ministry Prompt Designer Tool Selection Mapping",
                    "trigger_type": "phase",
                    "binding_mode": "multi_required",
                    "trigger_signals": ["tool selection mapping"],
                    "dependency_groups": ["group:tool-selection-pair"],
                    "resource_kinds": ["instruction_resource"],
                    "objective": "Map the supporting tool pair",
                    "activation_reason": "tool selection support",
                },
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        request_filenames = [item.get("filename") for item in out["turn_execution_plan"]["resource_requests"]]
        self.assertIn("template_library.md", request_filenames)
        self.assertIn("ministry_output_rules.md", request_filenames)
        self.assertIn("tool_selection_map.md", request_filenames)
        self.assertTrue(
            {
                "binding:ministry-route",
                "binding:ministry-output-rules",
                "binding:tool-selection-pair",
            }.issubset(set(out["session_execution_state"]["active_binding_ids"]))
        )

    def test_option_selection_followup_reuses_prior_binding_context(self):
        state = self.state.copy()
        state["user_query"] = "A + C + D"
        state["chat_history"] = [
            {"role": "user", "content": "優化此 Prompt for 同工培訓"},
            {"role": "assistant", "content": "以下是優化分析：A、B、C、D。請選擇要採用的方向。"},
        ]
        state["session_execution_state"] = {
            "active_binding_ids": ["binding:ministry-output-rules"],
            "active_dependency_group_ids": ["group:ministry-output-rules"],
            "execution_status": "answering",
            "last_turn_action": "answer",
        }
        state["instruction_runtime_model"] = {
            "instruction_resources": [
                {
                    "resource_id": "ministry_output_rules",
                    "title": "Ministry Output Rules",
                    "filename": "ministry_output_rules.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
                {
                    "resource_id": "ministry_prompt_guardrails",
                    "title": "Ministry Prompt Guardrails",
                    "filename": "ministry_prompt_guardrails.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
            ],
            "dependency_groups": [
                {
                    "group_id": "group:ministry-output-rules",
                    "title": "Church Ministry Prompt Designer Output Rules",
                    "resource_ids": ["ministry_output_rules", "ministry_prompt_guardrails"],
                },
            ],
            "phase_resource_bindings": [
                {
                    "binding_id": "binding:ministry-output-rules",
                    "title": "Church Ministry Prompt Designer Output Rules",
                    "trigger_type": "phase",
                    "binding_mode": "multi_required",
                    "trigger_signals": ["church ministry prompt"],
                    "dependency_groups": ["group:ministry-output-rules"],
                    "resource_kinds": ["instruction_resource"],
                    "objective": "Apply the ministry output rule bundle",
                    "activation_reason": "generation requires output rules",
                },
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        request_filenames = [item.get("filename") for item in out["turn_execution_plan"]["resource_requests"]]
        self.assertEqual(
            request_filenames,
            ["ministry_output_rules.md", "ministry_prompt_guardrails.md"],
        )
        self.assertIn("binding:ministry-output-rules", out["session_execution_state"]["active_binding_ids"])

    def test_followup_can_keep_prior_binding_and_activate_new_binding_together(self):
        state = self.state.copy()
        state["user_query"] = "優化此 Prompt，並加入 tool selection mapping"
        state["chat_history"] = [
            {"role": "user", "content": "Create an optimized prompt to 幫助基督徒學習高階的指令技巧"},
            {"role": "assistant", "content": "這是上一輪生成的 Prompt 草稿。"},
        ]
        state["session_execution_state"] = {
            "active_binding_ids": ["binding:ministry-output-rules"],
            "active_dependency_group_ids": ["group:ministry-output-rules"],
            "execution_status": "answering",
            "last_turn_action": "answer",
        }
        state["instruction_runtime_model"] = {
            "instruction_resources": [
                {
                    "resource_id": "ministry_output_rules",
                    "title": "Ministry Output Rules",
                    "filename": "ministry_output_rules.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
                {
                    "resource_id": "ministry_prompt_guardrails",
                    "title": "Ministry Prompt Guardrails",
                    "filename": "ministry_prompt_guardrails.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
                {
                    "resource_id": "tool_selection_map",
                    "title": "Tool Selection Map",
                    "filename": "tool_selection_map.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
                {
                    "resource_id": "tool_usage_matrix",
                    "title": "Tool Usage Matrix",
                    "filename": "tool_usage_matrix.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
            ],
            "dependency_groups": [
                {
                    "group_id": "group:ministry-output-rules",
                    "title": "Church Ministry Prompt Designer Output Rules",
                    "resource_ids": ["ministry_output_rules", "ministry_prompt_guardrails"],
                },
                {
                    "group_id": "group:tool-selection-pair",
                    "title": "Church Ministry Prompt Designer Tool Selection Mapping",
                    "resource_ids": ["tool_selection_map", "tool_usage_matrix"],
                },
            ],
            "phase_resource_bindings": [
                {
                    "binding_id": "binding:ministry-output-rules",
                    "title": "Church Ministry Prompt Designer Output Rules",
                    "trigger_type": "phase",
                    "binding_mode": "multi_required",
                    "trigger_signals": ["church ministry prompt"],
                    "dependency_groups": ["group:ministry-output-rules"],
                    "resource_kinds": ["instruction_resource"],
                    "objective": "Apply the ministry output rule bundle",
                    "activation_reason": "generation requires output rules",
                },
                {
                    "binding_id": "binding:tool-selection-pair",
                    "title": "Church Ministry Prompt Designer Tool Selection Mapping",
                    "trigger_type": "phase",
                    "binding_mode": "multi_required",
                    "trigger_signals": ["tool selection mapping"],
                    "dependency_groups": ["group:tool-selection-pair"],
                    "resource_kinds": ["instruction_resource"],
                    "objective": "Map the supporting tool pair",
                    "activation_reason": "tool selection support",
                },
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        request_filenames = {item.get("filename") for item in out["turn_execution_plan"]["resource_requests"]}
        self.assertTrue(
            {
                "ministry_output_rules.md",
                "ministry_prompt_guardrails.md",
                "tool_selection_map.md",
                "tool_usage_matrix.md",
            }.issubset(request_filenames)
        )
        self.assertEqual(
            set(out["session_execution_state"]["active_binding_ids"]),
            {"binding:ministry-output-rules", "binding:tool-selection-pair"},
        )
        self.assertEqual(
            set(out["session_execution_state"]["active_dependency_group_ids"]),
            {"group:ministry-output-rules", "group:tool-selection-pair"},
        )

    def test_gpt_application_design_assistant_phase_and_support_module_bindings_activate_together(self):
        state = self.state.copy()
        state["user_query"] = "Help me define the GPT application interaction configuration with support guidance"
        state["template_registry"] = {
            "instruction_modules": [
                {
                    "id": "gpt_interaction_configuration",
                    "title": "GPT Application Interaction Configuration",
                    "primary_resource": "application_discovery_brief.md",
                    "resource_files": ["application_discovery_brief.md"],
                    "keywords": ["interaction configuration", "gpt application"],
                }
            ]
        }
        state["instruction_runtime_model"] = {
            "instruction_resources": [
                {
                    "resource_id": "application_discovery_brief",
                    "title": "Application Discovery Brief",
                    "filename": "application_discovery_brief.md",
                    "domain": "instruction_source",
                    "use_type": "primary",
                },
                {
                    "resource_id": "interaction_patterns",
                    "title": "Interaction Patterns",
                    "filename": "interaction_patterns.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
                {
                    "resource_id": "configuration_matrix",
                    "title": "Configuration Matrix",
                    "filename": "configuration_matrix.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
                {
                    "resource_id": "support_prompt_library",
                    "title": "Support Prompt Library",
                    "filename": "support_prompt_library.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
                {
                    "resource_id": "support_guardrails",
                    "title": "Support Guardrails",
                    "filename": "support_guardrails.md",
                    "domain": "instruction_source",
                    "use_type": "support",
                },
            ],
            "dependency_groups": [
                {
                    "group_id": "group:gpt-interaction-pack",
                    "title": "GPT Application Design Assistant Interaction Configuration Phase",
                    "resource_ids": ["interaction_patterns", "configuration_matrix"],
                },
                {
                    "group_id": "group:gpt-support-pack",
                    "title": "GPT Application Design Assistant Support Module",
                    "resource_ids": ["support_prompt_library", "support_guardrails"],
                },
            ],
            "phase_resource_bindings": [
                {
                    "binding_id": "binding:gpt-discovery",
                    "title": "GPT Application Design Assistant Discovery Phase",
                    "trigger_type": "phase",
                    "binding_mode": "single_required",
                    "scope_id": "GPT Application Interaction Configuration",
                    "resource_ids": ["application_discovery_brief"],
                    "resource_kinds": ["instruction_resource"],
                    "objective": "Frame the design phase",
                    "activation_reason": "phase entry brief",
                },
                {
                    "binding_id": "binding:gpt-configuration",
                    "title": "GPT Application Design Assistant Interaction Configuration Phase",
                    "trigger_type": "phase",
                    "binding_mode": "multi_required",
                    "scope_id": "GPT Application Interaction Configuration",
                    "trigger_signals": ["interaction configuration"],
                    "dependency_groups": ["group:gpt-interaction-pack"],
                    "resource_kinds": ["instruction_resource"],
                    "objective": "Configure the app interaction model",
                    "activation_reason": "interaction configuration phase",
                },
                {
                    "binding_id": "binding:gpt-support-module",
                    "title": "GPT Application Design Assistant Support Module",
                    "trigger_type": "module",
                    "binding_mode": "multi_required",
                    "scope_id": "GPT Application Interaction Configuration",
                    "trigger_signals": ["support guidance"],
                    "dependency_groups": ["group:gpt-support-pack"],
                    "resource_kinds": ["instruction_resource"],
                    "objective": "Activate support guidance",
                    "activation_reason": "support module activation",
                },
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        requests = {
            item["filename"]: item
            for item in out["turn_execution_plan"]["resource_requests"]
            if item.get("binding_id") in {
                "binding:gpt-discovery",
                "binding:gpt-configuration",
                "binding:gpt-support-module",
            }
        }

        self.assertEqual(
            set(requests),
            {
                "application_discovery_brief.md",
                "interaction_patterns.md",
                "configuration_matrix.md",
                "support_prompt_library.md",
                "support_guardrails.md",
            },
        )
        self.assertEqual(requests["application_discovery_brief.md"]["binding_id"], "binding:gpt-discovery")
        self.assertEqual(requests["interaction_patterns.md"]["dependency_group_id"], "group:gpt-interaction-pack")
        self.assertEqual(requests["support_prompt_library.md"]["dependency_group_id"], "group:gpt-support-pack")
        self.assertEqual(
            set(out["session_execution_state"]["active_binding_ids"]),
            {
                "binding:gpt-discovery",
                "binding:gpt-configuration",
                "binding:gpt-support-module",
            },
        )
        self.assertEqual(
            set(out["session_execution_state"]["active_dependency_group_ids"]),
            {"group:gpt-interaction-pack", "group:gpt-support-pack"},
        )

    def test_vibe_story_director_starter_binding_activates_schema_anchor_and_artifact_gate(self):
        state = self.state.copy()
        state["user_query"] = "Start a new vibe story director pass from the bundle spec"
        state["instruction_runtime_model"] = {
            "instruction_resources": [
                {
                    "resource_id": "director_bundle_spec",
                    "title": "Director Bundle Spec",
                    "filename": "Director_Bundle_Spec.md",
                    "domain": "output_template",
                    "use_type": "primary",
                }
            ],
            "phase_resource_bindings": [
                {
                    "binding_id": "binding:vibe-starter",
                    "title": "Vibe Story Director Starter",
                    "trigger_type": "starter",
                    "binding_mode": "single_required",
                    "trigger_signals": ["start"],
                    "resource_ids": ["director_bundle_spec"],
                    "resource_kinds": ["schema_anchor"],
                    "objective": "Open the director starter with the schema anchor",
                    "activation_reason": "starter-triggered binding",
                },
                {
                    "binding_id": "binding:vibe-artifact-gate",
                    "title": "Vibe Story Director Bundle Upload Gate",
                    "trigger_type": "artifact_gate",
                    "binding_mode": "none",
                    "trigger_signals": ["start"],
                    "artifact_contract": {
                        "mode": "requires_artifact",
                        "artifact_role": "director_bundle",
                        "filename_patterns": ["Director Bundle.md"],
                        "required_for_progression": True,
                        "missing_artifact_prompt": "Upload Director Bundle.md before continuing.",
                    },
                    "objective": "Require the director bundle before the next pass",
                    "activation_reason": "artifact-gated starter",
                },
            ],
        }

        def llm(_prompt, _tools, _context):
            output = json.loads(json.dumps(self.valid))
            output["normalizedQuery"] = state["user_query"]
            output["contextualQuery"] = state["user_query"]
            output["retrievalPlan"]["query_text"] = state["user_query"]
            return output

        out = planner.run(state, llm_planner=llm)
        requests = [
            item for item in out["turn_execution_plan"]["resource_requests"]
            if item.get("binding_id") in {"binding:vibe-starter", "binding:vibe-artifact-gate"}
        ]
        request_map = {item.get("binding_id"): item for item in requests if item.get("binding_id")}

        self.assertEqual(request_map["binding:vibe-starter"]["filename"], "Director_Bundle_Spec.md")
        self.assertEqual(request_map["binding:vibe-starter"]["resource_kind"], "schema_anchor")
        self.assertEqual(request_map["binding:vibe-starter"]["resource_role"], "output_template")
        self.assertIn("binding:vibe-starter", out["session_execution_state"]["active_binding_ids"])
        self.assertIn("binding:vibe-artifact-gate", out["session_execution_state"]["active_binding_ids"])
        self.assertIn("director_bundle", out["session_execution_state"]["active_artifact_roles"])
        self.assertFalse(
            out["session_execution_state"]["artifact_gate_status"]["binding:vibe-artifact-gate"]["satisfied"]
        )
        self.assertEqual(
            out["session_execution_state"]["artifact_gate_status"]["binding:vibe-artifact-gate"]["missing_artifact_prompt"],
            "Upload Director Bundle.md before continuing.",
        )


    def test_planner_activates_cross_app_bindings_from_registry_runtime_model(self):
        root = Path(__file__).resolve().parent / "_workdirs" / "planner_registry_contract"
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        try:
            domains = root / "domains"
            prompts = root / "prompts"
            _write_domain_fixture(domains)
            prompts.mkdir(parents=True, exist_ok=True)

            markdown = """
## Church Ministry Prompt Designer Routing Phase
Use template_library.md or dynamic_prompt_optimizer.md based on the ministry request.

## Church Ministry Prompt Designer Output Rules
Load ministry_output_rules.md and ministry_prompt_guardrails.md before writing the final prompt.

## Church Ministry Prompt Designer Tool Selection Support Module
Use tool_selection_map.md and tool_usage_matrix.md to map the selected tool pair.
"""
            state = self.state.copy()
            state["user_query"] = "Church Ministry Prompt Designer Tool Selection Support Module tool selection mapping"
            state["template_version"] = 1
            state["template_registry"] = {"builder_instructions": markdown}

            state = load_template_registry.run(state, domains_base_dir=domains, prompts_dir=prompts)

            def llm(_prompt, _tools, _context):
                output = json.loads(json.dumps(self.valid))
                output["normalizedQuery"] = state["user_query"]
                output["contextualQuery"] = state["user_query"]
                output["retrievalPlan"]["query_text"] = state["user_query"]
                return output

            out = planner.run(state, llm_planner=llm)
            requests = [
                item
                for item in out["turn_execution_plan"]["resource_requests"]
                if item.get("binding_id") == "support_module:church_ministry_prompt_designer_tool_selection_support_module"
            ]
            grouped_requests = {
                item["filename"]: item for item in requests if item.get("dependency_group_id")
            }

            self.assertEqual(
                set(grouped_requests),
                {
                    "tool_selection_map.md",
                    "tool_usage_matrix.md",
                },
            )
            self.assertEqual(grouped_requests["tool_selection_map.md"]["resource_kind"], "instruction_resource")
            self.assertEqual(
                grouped_requests["tool_selection_map.md"]["dependency_group_id"],
                "dependency:church_ministry_prompt_designer_tool_selection_support_module",
            )
            self.assertEqual(
                set(out["session_execution_state"]["active_binding_ids"]),
                {
                    "support_module:church_ministry_prompt_designer_tool_selection_support_module",
                },
            )
            self.assertEqual(
                set(out["session_execution_state"]["active_dependency_group_ids"]),
                {
                    "dependency:church_ministry_prompt_designer_tool_selection_support_module",
                },
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_planner_does_not_activate_other_app_families_from_mixed_registry(self):
        root = Path(__file__).resolve().parent / "_workdirs" / "planner_mixed_registry_contract"
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        try:
            domains = root / "domains"
            prompts = root / "prompts"
            _write_domain_fixture(domains)
            prompts.mkdir(parents=True, exist_ok=True)

            markdown = """
## Church Ministry Prompt Designer Tool Selection Support Module
Use tool_selection_map.md and tool_usage_matrix.md to map the selected tool pair.

## GPT Application Design Assistant Support Module
Use support_prompt_library.md and support_guardrails.md when the configuration phase needs extra guidance.

## Vibe Story Director Starter
Use Director_Bundle_Spec.md to open the first director pass.

## Vibe Story Director Bundle Upload Gate
If Director Bundle.md is missing, prompt the user to upload Director Bundle.md before executing the next pass.
"""

            scenarios = [
                {
                    "query": "Church Ministry Prompt Designer Tool Selection Support Module tool selection mapping",
                    "expected": {"support_module:church_ministry_prompt_designer_tool_selection_support_module"},
                    "forbidden": {
                        "support_module:gpt_application_design_assistant_support_module",
                        "starter:vibe_story_director_starter",
                        "artifact_gate:vibe_story_director_bundle_upload_gate",
                    },
                },
                {
                    "query": "GPT Application Design Assistant Support Module support guidance",
                    "expected": {"support_module:gpt_application_design_assistant_support_module"},
                    "forbidden": {
                        "support_module:church_ministry_prompt_designer_tool_selection_support_module",
                        "starter:vibe_story_director_starter",
                        "artifact_gate:vibe_story_director_bundle_upload_gate",
                    },
                },
                {
                    "query": "Start a new vibe story director pass from the bundle spec",
                    "expected": {
                        "starter:vibe_story_director_starter",
                        "artifact_gate:vibe_story_director_bundle_upload_gate",
                    },
                    "forbidden": {
                        "support_module:church_ministry_prompt_designer_tool_selection_support_module",
                        "support_module:gpt_application_design_assistant_support_module",
                    },
                },
            ]

            for scenario in scenarios:
                with self.subTest(query=scenario["query"]):
                    state = self.state.copy()
                    state["user_query"] = scenario["query"]
                    state["template_version"] = 1
                    state["template_registry"] = {"builder_instructions": markdown}
                    state = load_template_registry.run(state, domains_base_dir=domains, prompts_dir=prompts)

                    def llm(_prompt, _tools, _context):
                        output = json.loads(json.dumps(self.valid))
                        output["normalizedQuery"] = state["user_query"]
                        output["contextualQuery"] = state["user_query"]
                        output["retrievalPlan"]["query_text"] = state["user_query"]
                        return output

                    out = planner.run(state, llm_planner=llm)
                    active_binding_ids = set(out["session_execution_state"]["active_binding_ids"])

                    self.assertTrue(scenario["expected"].issubset(active_binding_ids))
                    self.assertTrue(active_binding_ids.isdisjoint(scenario["forbidden"]))
        finally:
            shutil.rmtree(root, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()










