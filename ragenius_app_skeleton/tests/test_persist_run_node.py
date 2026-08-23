import shutil
import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ragenius_app_skeleton.backend.app.chat_repos import ChatRepo, SessionRepo
from ragenius_app_skeleton.workflows.nodes import execute_turn_plan
from ragenius_app_skeleton.workflows.nodes import persist_run


class PersistRunNodeTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(__file__).resolve().parent / "_tmp" / "persist_run"
        if self.tmpdir.exists():
            shutil.rmtree(self.tmpdir, ignore_errors=True)
        self.tmpdir.mkdir(parents=True, exist_ok=True)
        self.state_db = self.tmpdir / "runtime_state.db"
        self.session_repo = SessionRepo(self.state_db)
        self.chat_repo = ChatRepo(self.state_db)
        self.session_repo.reset()
        self.chat_repo.reset()
        self.session_repo.get_or_create(
            "s-upload",
            collection_id="app-1",
            user_id="u1",
            config_version=1,
            adapter_version=1,
            template_version=1,
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_upload_triggered_turn_persists_only_assistant_message(self):
        state = {
            "session_id": "s-upload",
            "turn_input_type": "session_upload",
            "user_query": "Analyze the uploaded artifact artifact.md using the application instructions.",
            "turn_execution_plan": {
                "turn_intent": "analyze_upload",
                "primary_scope": {"scope_id": "module:artifact_review", "scope_type": "module"},
            },
            "presentation_policy": {"mode": "summary_only"},
            "visible_outputs": [{"output_id": "summary", "content": "Artifact analysis"}],
            "execution_artifacts": [{"artifact_id": "artifact:1", "artifact_type": "response_action", "source_action_id": "action:1"}],
            "raw_evidence": [
                {
                    "doc_id": "upload-1",
                    "title": "artifact.md",
                    "retrieval_domain": "session_upload",
                }
            ],
            "retrieval_debug_trace": {"domains": {"session_upload": {"route": {"model": "session_upload"}}}},
            "final_answer": {
                "content": "Artifact analysis",
                "citations": [],
                "missing_infoTypes": [],
            },
            "_chat_repo": self.chat_repo,
            "_session_repo": self.session_repo,
        }

        persist_run.run(state)
        history = self.chat_repo.history("s-upload")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["role"], "assistant")
        self.assertEqual(history[0]["content"], "Artifact analysis")
        summary = history[0]["retrievalSummary"]
        self.assertEqual(summary["turn_intent"], "analyze_upload")
        self.assertEqual(summary["primary_scope_id"], "module:artifact_review")
        self.assertEqual(summary["presentation_mode"], "summary_only")
        self.assertEqual(summary["visible_output_count"], 1)
        self.assertEqual(summary["execution_artifact_count"], 1)

    def test_normal_turn_persists_attached_artifact_refs_on_user_message(self):
        state = {
            "session_id": "s-upload",
            "turn_input_type": "text_query",
            "user_query": "Summarize the attached notes.",
            "attached_artifact_refs": [{
                "artifact_id": "artifact-notes",
                "display_name": "notes.txt",
                "mime_type": "text/plain",
                "role": "attachment",
            }],
            "final_answer": {
                "content": "Summary",
                "citations": [],
                "missing_infoTypes": [],
            },
            "_chat_repo": self.chat_repo,
            "_session_repo": self.session_repo,
        }

        persist_run.run(state)

        user_message = self.chat_repo.history("s-upload")[0]
        self.assertEqual(
            user_message["retrievalSummary"]["attached_artifact_refs"],
            state["attached_artifact_refs"],
        )

    def test_persist_run_writes_hidden_execution_state_into_session_runtime_state(self):
        state = {
            "session_id": "s-upload",
            "user_query": "continue",
            "workflow_progress": {
                "workflow_id": "bible_study",
                "step_order": 1,
            },
            "session_execution_state": {
                "execution_status": "guiding",
                "active_scope_ids": ["step:bible_study:1"],
            },
            "intermediate_outputs": [
                {
                    "output_id": "obs-notes",
                    "output_type": "notes",
                    "visibility": "internal_only",
                    "content": "Observation notes",
                }
            ],
            "assembly_state": {"target_output": "study_summary"},
            "final_answer": {
                "content": "Next question",
                "citations": [],
                "missing_infoTypes": [],
            },
            "_chat_repo": self.chat_repo,
            "_session_repo": self.session_repo,
        }

        persist_run.run(state)
        session = self.session_repo.get("s-upload")
        history = self.chat_repo.history("s-upload")
        self.assertEqual(session["workflow_progress"]["workflow_id"], "bible_study")
        self.assertEqual(session["runtime_state"]["session_execution_state"]["execution_status"], "guiding")
        self.assertEqual(session["runtime_state"]["intermediate_outputs"][0]["output_id"], "obs-notes")
        self.assertEqual(session["runtime_state"]["assembly_state"]["target_output"], "study_summary")
        self.assertEqual(history[-1]["retrievalSummary"]["workflow_progress"]["workflow_id"], "bible_study")
        self.assertEqual(history[-1]["retrievalSummary"]["workflow_progress"]["step_order"], 1)

    def test_persist_run_summary_exposes_execution_layer_fields(self):
        state = {
            "session_id": "s-upload",
            "user_query": "continue",
            "turn_execution_plan": {
                "turn_intent": "answer_prior_questions",
                "primary_scope": {"scope_id": "step:bible_study:1", "scope_type": "step"},
                "secondary_scopes": [{"scope_id": "section:student_response_logic"}],
                "actions": [
                    {"action_type": "respond_to_user", "params": {"response_style": {"is_generation_request": True, "generation_subtype": "freeform"}}},
                    {"action_type": "update_session_state"},
                ],
            },
            "presentation_policy": {"mode": "question_only"},
            "session_execution_state": {"execution_status": "guiding"},
            "intermediate_outputs": [{"output_id": "obs-notes", "output_type": "notes"}],
            "visible_outputs": [{"output_id": "q1", "output_type": "user_visible_response", "visibility": "user_visible", "content": "Question"}],
            "hidden_outputs": [{"output_id": "obs-notes", "output_type": "notes"}],
            "execution_artifacts": [{"artifact_id": "artifact:state", "artifact_type": "session_state_update", "source_action_id": "action:update_state"}],
            "tool_results": [{"artifact_id": "artifact:tool", "artifact_type": "tool_call_skipped", "source_action_id": "action:tool"}],
            "assembly_state": {"target_output": "study_summary"},
            "final_answer": {
                "content": "Question",
                "citations": [],
                "missing_infoTypes": [],
            },
            "_chat_repo": self.chat_repo,
            "_session_repo": self.session_repo,
        }

        persist_run.run(state)
        history = self.chat_repo.history("s-upload")
        summary = history[-1]["retrievalSummary"]
        self.assertEqual(summary["turn_intent"], "answer_prior_questions")
        self.assertEqual(summary["action_type"], "respond_to_user")
        self.assertEqual(summary["primary_action_type"], "respond_to_user")
        self.assertEqual(summary["action_types"], ["respond_to_user", "update_session_state"])
        self.assertEqual(summary["action_count"], 2)
        self.assertEqual(summary["primary_scope_type"], "step")
        self.assertEqual(summary["secondary_scope_ids"], ["section:student_response_logic"])
        self.assertEqual(summary["presentation_mode"], "question_only")
        self.assertTrue(summary["is_generation_request"])
        self.assertEqual(summary["generation_subtype"], "freeform")
        self.assertFalse(summary["is_out_of_scope"])
        self.assertEqual(summary["visible_output_count"], 1)
        self.assertEqual(summary["hidden_output_count"], 1)
        self.assertEqual(summary["execution_artifact_count"], 1)
        self.assertEqual(summary["tool_result_count"], 1)

    def test_persist_run_summary_exposes_binding_and_selected_resource_metadata(self):
        state = {
            "session_id": "s-upload",
            "user_query": "continue",
            "turn_execution_plan": {
                "resource_requests": [
                    {
                        "filename": "Observation_Guide.md",
                        "resource_role": "instruction_source",
                        "binding_id": "binding:observation",
                        "resource_kind": "instruction_resource",
                    },
                    {
                        "filename": "Director_Bundle_Spec.md",
                        "resource_role": "output_template",
                        "binding_id": "binding:bundle-template",
                        "dependency_group_id": "group:bundle-pack",
                        "resource_kind": "schema_anchor",
                        "artifact_role": "director_bundle",
                    },
                ]
            },
            "session_execution_state": {
                "active_binding_ids": ["binding:observation", "binding:bundle-template"],
                "active_dependency_group_ids": ["group:bundle-pack"],
                "artifact_gate_status": {
                    "binding:bundle-template": {
                        "artifact_role": "director_bundle",
                        "satisfied": True,
                    }
                },
            },
            "instruction_resource_context": [
                {
                    "filename": "Observation_Guide.md",
                    "load_strategy": "inline_full",
                    "source_kind": "builder_direct_load",
                    "section_titles": ["Observation"],
                    "binding_id": "binding:observation",
                    "resource_kind": "instruction_resource",
                }
            ],
            "template_resource_context": [
                {
                    "filename": "Director_Bundle_Spec.md",
                    "load_strategy": "section_filter",
                    "source_kind": "builder_direct_load",
                    "section_titles": ["Overview"],
                    "binding_id": "binding:bundle-template",
                    "dependency_group_id": "group:bundle-pack",
                    "resource_kind": "schema_anchor",
                    "artifact_role": "director_bundle",
                }
            ],
            "final_answer": {
                "content": "Question",
                "citations": [],
                "missing_infoTypes": [],
            },
            "_chat_repo": self.chat_repo,
            "_session_repo": self.session_repo,
        }

        persist_run.run(state)
        history = self.chat_repo.history("s-upload")
        summary = history[-1]["retrievalSummary"]
        self.assertEqual(summary["active_binding_ids"], ["binding:observation", "binding:bundle-template"])
        self.assertEqual(summary["active_dependency_group_ids"], ["group:bundle-pack"])
        self.assertEqual(
            summary["artifact_gate_status"],
            {"binding:bundle-template": {"artifact_role": "director_bundle", "satisfied": True}},
        )
        self.assertEqual(summary["selected_resource_filenames"], ["Observation_Guide.md", "Director_Bundle_Spec.md"])
        self.assertEqual(summary["selected_resource_kinds"], ["instruction_resource", "schema_anchor"])

    def test_persist_run_summary_exposes_layered_scope_and_request_provenance_metadata(self):
        state = {
            "session_id": "s-upload",
            "user_query": "continue",
            "turn_execution_plan": {
                "primary_scope": {
                    "scope_id": "workflow:interaction_logic_execution_flow",
                    "scope_type": "workflow",
                    "title": "Interaction Logic & Execution Flow",
                },
                "resource_requests": [
                    {
                        "filename": "Ministry_Discovery_Questions.md",
                        "resource_role": "instruction_source",
                        "binding_id": "binding:ministry-discovery",
                        "resource_kind": "instruction_resource",
                        "source_layer": "procedure_step",
                        "step_scope_id": "step:interaction_logic_execution_flow:1",
                    },
                    {
                        "filename": "Theology_Guardrails.md",
                        "resource_role": "instruction_source",
                        "binding_id": "binding:theology-guardrails",
                        "resource_kind": "instruction_resource",
                        "source_layer": "support_module",
                        "step_scope_id": "step:interaction_logic_execution_flow:1",
                        "support_module_id": "theological_alignment_support_module",
                    },
                ],
            },
            "session_execution_state": {
                "primary_scope_id": "workflow:interaction_logic_execution_flow",
                "primary_scope_type": "workflow",
                "primary_scope_title": "Interaction Logic & Execution Flow",
                "active_step_scope_id": "step:interaction_logic_execution_flow:1",
                "procedure_step_activation": {
                    "step_scope_id": "step:interaction_logic_execution_flow:1",
                    "step_scope_type": "step",
                    "step_order": 1,
                    "step_title": "Clarify the Ministry Need",
                    "primary_support_module_id": "theological_alignment_support_module",
                    "primary_support_module_title": "Theological Alignment Support Module",
                },
                "primary_support_module_id": "theological_alignment_support_module",
                "primary_support_module_title": "Theological Alignment Support Module",
                "primary_support_module_activation": {
                    "support_module_id": "theological_alignment_support_module",
                    "title": "Theological Alignment Support Module",
                    "step_scope_id": "step:interaction_logic_execution_flow:1",
                },
            },
            "final_answer": {
                "content": "Question",
                "citations": [],
                "missing_infoTypes": [],
            },
            "_chat_repo": self.chat_repo,
            "_session_repo": self.session_repo,
        }

        persist_run.run(state)
        history = self.chat_repo.history("s-upload")
        summary = history[-1]["retrievalSummary"]
        self.assertEqual(
            summary["primary_scope"],
            {
                "scope_id": "workflow:interaction_logic_execution_flow",
                "scope_type": "workflow",
                "title": "Interaction Logic & Execution Flow",
            },
        )
        self.assertEqual(
            summary["active_step_scope"],
            {
                "scope_id": "step:interaction_logic_execution_flow:1",
                "scope_type": "step",
                "title": "Clarify the Ministry Need",
                "step_order": 1,
            },
        )
        self.assertEqual(
            summary["primary_support_module_scope"],
            {
                "scope_id": "theological_alignment_support_module",
                "scope_type": "module",
                "title": "Theological Alignment Support Module",
                "step_scope_id": "step:interaction_logic_execution_flow:1",
            },
        )
        self.assertEqual(summary["active_step_scope_id"], "step:interaction_logic_execution_flow:1")
        self.assertEqual(summary["primary_support_module_scope_id"], "theological_alignment_support_module")
        self.assertEqual(
            summary["request_provenance_summary"],
            [
                {
                    "source_layer": "procedure_step",
                    "step_scope_id": "step:interaction_logic_execution_flow:1",
                    "support_module_id": None,
                    "filenames": ["Ministry_Discovery_Questions.md"],
                    "request_count": 1,
                },
                {
                    "source_layer": "support_module",
                    "step_scope_id": "step:interaction_logic_execution_flow:1",
                    "support_module_id": "theological_alignment_support_module",
                    "filenames": ["Theology_Guardrails.md"],
                    "request_count": 1,
                },
            ],
        )

    def test_persist_run_summary_uses_execution_hydration_for_artifact_roles_and_targets(self):
        state = {
            "session_id": "s-upload",
            "user_query": "continue",
            "turn_execution_plan": {
                "resource_requests": [],
                "actions": [
                    {
                        "action_id": "action:draft_bundle",
                        "action_type": "generate_intermediate_output",
                        "target": "bundle_draft",
                        "output_key": "bundle_draft",
                        "visibility": "internal_only",
                        "params": {
                            "output_type": "artifact_draft",
                            "content": "Draft bundle",
                            "artifact_role": "director_bundle",
                            "structured_data": {"artifact_role": "director_bundle"},
                        },
                    },
                    {
                        "action_id": "action:assemble",
                        "action_type": "assemble_output",
                        "target": "output_artifact_assembler",
                        "visibility": "internal_only",
                        "params": {
                            "target_outputs": ["Director Bundle.md"],
                            "source_output_key": "final_answer",
                            "artifact_role": "director_bundle",
                        },
                    },
                ],
            },
            "_chat_repo": self.chat_repo,
            "_session_repo": self.session_repo,
        }

        out = execute_turn_plan.run(state)
        out["final_answer"] = {
            "content": "Question",
            "citations": [],
            "missing_infoTypes": [],
        }

        persist_run.run(out)
        history = self.chat_repo.history("s-upload")
        summary = history[-1]["retrievalSummary"]
        self.assertEqual(summary["active_artifact_roles"], ["director_bundle"])
        self.assertEqual(summary["artifact_gate_status"]["director_bundle"]["artifact_role"], "director_bundle")
        self.assertEqual(summary["output_artifact_targets"], ["Director Bundle.md"])
        self.assertEqual(summary["assembly_state"]["target_outputs"], ["Director Bundle.md"])

    def test_persist_run_summary_marks_binding_keyed_required_gate_satisfied_after_artifact_generation(self):
        state = {
            "session_id": "s-upload",
            "user_query": "continue",
            "turn_execution_plan": {
                "resource_requests": [
                    {
                        "filename": "Director_Bundle_Spec.md",
                        "resource_role": "output_template",
                        "binding_id": "binding:bundle-template",
                        "resource_kind": "schema_anchor",
                        "artifact_role": "director_bundle",
                        "required_for_progression": True,
                    }
                ],
                "actions": [
                    {
                        "action_id": "action:draft_bundle",
                        "action_type": "generate_intermediate_output",
                        "target": "bundle_draft",
                        "output_key": "bundle_draft",
                        "visibility": "internal_only",
                        "params": {
                            "output_type": "artifact_draft",
                            "content": "Draft bundle",
                            "artifact_role": "director_bundle",
                        },
                    }
                ],
            },
            "_chat_repo": self.chat_repo,
            "_session_repo": self.session_repo,
        }

        out = execute_turn_plan.run(state)
        out["final_answer"] = {
            "content": "Question",
            "citations": [],
            "missing_infoTypes": [],
        }

        persist_run.run(out)
        history = self.chat_repo.history("s-upload")
        summary = history[-1]["retrievalSummary"]
        self.assertTrue(summary["artifact_gate_status"]["binding:bundle-template"]["satisfied"])
        self.assertEqual(summary["artifact_gate_status"]["binding:bundle-template"]["artifact_role"], "director_bundle")

    def test_persist_run_summary_marks_retrieval_bypassed_for_out_of_scope_turn(self):
        state = {
            "session_id": "s-upload",
            "user_query": "Explain Python dataclass",
            "turn_execution_plan": {
                "turn_intent": "general_out_of_scope_question",
                "actions": [
                    {
                        "action_type": "respond_to_user",
                        "params": {"response_style": {"is_out_of_scope": True}},
                    }
                ],
            },
            "retrieval_debug_trace": {
                "retrieval_bypassed": True,
                "bypass_reason": "general_out_of_scope_question",
            },
            "final_answer": {
                "content": "Direct answer",
                "citations": [],
                "missing_infoTypes": [],
            },
            "_chat_repo": self.chat_repo,
            "_session_repo": self.session_repo,
        }

        persist_run.run(state)
        history = self.chat_repo.history("s-upload")
        summary = history[-1]["retrievalSummary"]
        self.assertEqual(summary["turn_intent"], "general_out_of_scope_question")
        self.assertTrue(summary["is_out_of_scope"])
        self.assertTrue(summary["retrieval_bypassed"])
        self.assertEqual(summary["retrieval_bypass_reason"], "general_out_of_scope_question")

    def test_persist_run_summary_prefers_execution_plan_resource_requests_for_queries(self):
        state = {
            "session_id": "s-upload",
            "user_query": "continue",
            "turn_action_plan": {
                "instruction_retrieval": {"query_text": "legacy instruction query", "context_hints": ["legacy-instruction"]},
                "template_retrieval": {"query_text": "legacy template query", "context_hints": ["legacy-template"]},
            },
            "turn_execution_plan": {
                "resource_requests": [
                    {
                        "filename": "observation_guide.md",
                        "resource_role": "instruction_source",
                        "purpose": "guide the learner through observation",
                        "query_text": "instruction guidance action guide step observation",
                        "context_hints": ["What does this word mean?", "Observation step"],
                        "load_strategy_hint": "inline_full",
                    },
                    {
                        "filename": "director_bundle.md",
                        "resource_role": "output_template",
                        "purpose": "shape the final artifact",
                        "query_text": "output template for director bundle",
                        "context_hints": ["Format the answer clearly"],
                        "load_strategy_hint": "section_filter",
                    },
                ]
            },
            "final_answer": {
                "content": "Question",
                "citations": [],
                "missing_infoTypes": [],
            },
            "_chat_repo": self.chat_repo,
            "_session_repo": self.session_repo,
        }

        persist_run.run(state)
        history = self.chat_repo.history("s-upload")
        summary = history[-1]["retrievalSummary"]
        self.assertEqual(summary["instruction_query"], "instruction guidance action guide step observation")
        self.assertEqual(summary["instruction_context_hints"], ["What does this word mean?", "Observation step", "observation_guide.md", "inline_full"])
        self.assertEqual(summary["template_query"], "output template for director bundle")
        self.assertEqual(summary["template_context_hints"], ["Format the answer clearly", "director_bundle.md", "section_filter"])

    def test_persist_run_summary_no_longer_uses_legacy_instruction_template_fallback_without_requests(self):
        state = {
            "session_id": "s-upload",
            "user_query": "continue",
            "turn_action_plan": {
                "instruction_retrieval": {"query_text": "legacy instruction query", "context_hints": ["legacy-instruction"]},
                "template_retrieval": {"query_text": "legacy template query", "context_hints": ["legacy-template"]},
            },
            "turn_execution_plan": {"resource_requests": []},
            "final_answer": {
                "content": "Question",
                "citations": [],
                "missing_infoTypes": [],
            },
            "_chat_repo": self.chat_repo,
            "_session_repo": self.session_repo,
        }

        persist_run.run(state)
        history = self.chat_repo.history("s-upload")
        summary = history[-1]["retrievalSummary"]
        self.assertIsNone(summary["instruction_query"])
        self.assertEqual(summary["instruction_context_hints"], [])
        self.assertIsNone(summary["template_query"])
        self.assertEqual(summary["template_context_hints"], [])

    def test_persist_run_refreshes_real_chat_summary_before_four_turn_window_drops_history(self):
        prior_history = []
        for index in range(4):
            prior_history.extend(
                [
                    {"role": "user", "content": f"Question {index}?"},
                    {"role": "assistant", "content": f"Answer {index}."},
                ]
            )
        state = {
            "session_id": "s-upload",
            "turn_input_type": "text_query",
            "user_query": "I prefer a short final answer. What is next?",
            "chat_history": prior_history,
            "session_execution_state": {"active_workflow": "study", "active_step_scope_id": "step-2"},
            "final_answer": {
                "content": "Continue to step 2.",
                "citations": [{"docId": "doc-2"}],
                "missing_infoTypes": [],
            },
            "_chat_repo": self.chat_repo,
            "_session_repo": self.session_repo,
        }

        persist_run.run(state)

        session = self.session_repo.get("s-upload")
        chat_summary = session["runtime_state"]["session_execution_state"]["chat_summary"]
        self.assertEqual(chat_summary["covered_message_count"], 10)
        self.assertIn("Continue to step 2.", chat_summary["assistant_conclusions"])
        self.assertEqual(chat_summary["active_workflow_state"]["active_step_scope_id"], "step-2")
        self.assertIn("doc-2", chat_summary["recent_citation_ids"])

    def test_persist_run_preserves_finalized_token_optimization_diagnostics(self):
        state = {
            "session_id": "s-upload",
            "turn_input_type": "text_query",
            "user_query": "Summarize the evidence.",
            "_task_model_diagnostics": {
                "configured_task_models": {"planner": {"model": "deepseek-chat"}},
                "selected_task_models": {"planner": {"provider": "deepseek", "model": "deepseek-chat"}},
            },
            "_context_optimization_eligible": True,
            "_context_optimization_mode": "compact",
            "_context_optimization_diagnostics": {
                "eligible": True,
                "mode": "compact",
                "calls": [
                    {
                        "task": "planner",
                        "actual_full_tokens": 1200,
                        "compact_candidate_tokens": 500,
                        "actual_outbound_tokens": 500,
                    }
                ],
            },
            "_turn_token_accounting": {
                "calls": [
                    {
                        "task": "planner",
                        "actual_full_tokens": 1200,
                        "compact_candidate_tokens": 500,
                        "actual_outbound_tokens": 500,
                    }
                ],
                "call_count": 1,
                "turn_estimated_outbound_tokens": 500,
                "turn_actual_full_tokens": 1200,
                "turn_compact_candidate_tokens": 500,
                "turn_estimated_tokens_saved": 700,
                "turn_estimated_saving_percent": 58.33,
            },
            "final_answer": {
                "content": "Evidence summary",
                "citations": [],
                "missing_infoTypes": [],
            },
            "_chat_repo": self.chat_repo,
            "_session_repo": self.session_repo,
        }

        persist_run.run(state)

        history = self.chat_repo.history("s-upload")
        diagnostics = history[-1]["retrievalSummary"]["task_model_diagnostics"]
        self.assertEqual(diagnostics["selected_task_models"]["planner"]["model"], "deepseek-chat")
        self.assertEqual(diagnostics["context_optimization"]["mode"], "compact")
        self.assertEqual(diagnostics["turn_token_accounting"]["call_count"], 1)
        self.assertEqual(diagnostics["turn_token_accounting"]["turn_estimated_tokens_saved"], 700)
        self.assertEqual(diagnostics["turn_token_accounting"]["budget_limit_tokens"], 25_000)
        self.assertFalse(diagnostics["turn_token_accounting"]["budget_exceeded"])


if __name__ == "__main__":
    unittest.main()
