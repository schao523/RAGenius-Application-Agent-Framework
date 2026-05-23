import json
import shutil
import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from ragenius_app_skeleton.backend.app.chat_repos import ChatRepo, RetrievalRepo, SessionRepo
from ragenius_app_skeleton.backend.app.chat_service import _build_retrieval_summary, run_chat_pipeline
from ragenius_app_skeleton.backend.app.planner_repo import InMemoryPlannerRepo
from ragenius_app_skeleton.backend.schemas import validate_final_answer, validate_planner_output
from workflows.nodes import load_template_registry, planner, retrieve


def _valid_planner_output(query_text: str) -> dict:
    payload = {
        "intentType": "qa",
        "confidence": 0.9,
        "steps": [{"id": "1", "title": "Retrieve evidence", "goal": "Answer query", "reasoning": None}],
        "infoTypes": ["fact"],
        "retrievalPlan": {"query_text": query_text, "top_k": 3, "filters": {}, "explanation": None},
        "systemInstructionSummary": {"fromConfigPdf": [], "fromAdapter": [], "fromTemplate": []},
        "normalizedQuery": query_text,
        "contextualQuery": query_text,
    }
    validate_planner_output(payload)
    return payload


def _valid_final_answer(content: str = "Answer content", *, title: str = "Reference", snippet: str = "Evidence") -> dict:
    payload = {
        "content": content,
        "citations": [
            {
                "docId": "doc-1",
                "title": title,
                "snippet": snippet,
                "score": 0.9,
                "location": None,
                "version": None,
            }
        ],
        "missing_infoTypes": [],
    }
    validate_final_answer(payload)
    return payload


class ChatPipelineRuntimeContractTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(__file__).resolve().parent / "_tmp" / "pipeline_contracts"
        if self.tmpdir.exists():
            shutil.rmtree(self.tmpdir, ignore_errors=True)
        self.tmpdir.mkdir(parents=True, exist_ok=True)
        self.state_db = self.tmpdir / "runtime_state.db"
        self.session_repo = SessionRepo(self.state_db)
        self.chat_repo = ChatRepo(self.state_db)
        self.retrieval_repo = RetrievalRepo()
        self.planner_repo = InMemoryPlannerRepo()
        self.session_repo.reset()
        self.chat_repo.reset()
        self.retrieval_repo.reset()
        self.planner_repo.reset()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _base_state(self, *, user_query: str, builder_instructions: str, builder_documents: list[dict]) -> dict:
        self.session_repo.get_or_create(
            "s-contract",
            collection_id="app-1",
            user_id="u1",
            config_version=1,
            adapter_version=1,
            template_version=1,
        )
        return {
            "session_id": "s-contract",
            "collection_id": "app-1",
            "user_id": "u1",
            "domain": "general",
            "user_query": user_query,
            "chat_history": [],
            "config_version": 1,
            "adapter_version": 1,
            "template_version": 1,
            "config_json": {
                "meta": {"llm_settings": {"model": "test-model"}, "builder_settings": {}},
                "role": {"mission": ["Answer carefully."]},
                "goals": [],
                "mode_detection": [],
                "coverage_rules": [],
                "retrieval_rules": [],
                "style_rules": [],
                "safety_rules": [],
                "step_skeletons": [],
                "modules": [],
                "controls_commands": [],
            },
            "adapter_json": {
                "domain": "general",
                "intent_overrides": [],
                "step_skeleton_mapping": {},
                "retrieval_defaults": {"top_k_range": [1, 5], "language": "zh"},
                "llm_guardrails_append": [],
            },
            "template_registry": {
                "builder_instructions": builder_instructions,
                "builder_documents": builder_documents,
            },
        }

    def _bible_tutor_instructions(self) -> str:
        return """
## 角色定位
你是一位專業聖經導師。

## 主要目標
1. 循序漸進帶領學員查經

## 教導風格
- 以提問引導學習

## 模式自動識別（Mode Detection）
• 查考經文模式（Bible Study）
  o 觸發：輸入含「查考」「研經」「經文」等字。
  o 回應：「好的，我們一起用歸納釋經法查考經文。請問想從哪一段開始？」
  o 啟動完整十步歸納釋經流程: 查經互動模組。

## 查經互動模組（歸納釋經法的十個步驟）
1. 細察事實 (Observation)
目的： 幫助學員觀察經文的具體細節。
使用資源： Resource/ observation_guide.md
操作：
• 依資源之觀察項目產出 1-3 題，等待回應後再推進。
"""

    def _church_ministry_bundled_instructions(self) -> str:
        return """
## Mode Detection
• Church Ministry Prompt Design
  o Trigger: query includes 「church ministry」 「ministry prompt」 「retreat」.
  o Start full workflow: Interaction Logic & Execution Flow

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

    def _gpt_bundled_instructions(self) -> str:
        return """
## Interaction Logic & Execution Flow
0. Clarify the App Goal
Ask one question to identify the app purpose and target user.
Use application_discovery_brief.md.

1. Configure the Interaction Model
Configure the app interaction model using interaction_patterns.md.

2. Generate the Settings Draft
Generate the builder-ready settings draft with configuration_matrix.md.

3. Validate the Configuration Output
Validate the final configuration output with support_guardrails.md.
"""

    def _builder_document(self, filename: str, content: str) -> dict:
        path = self.tmpdir / filename
        path.write_text(content, encoding="utf-8")
        return {
            "id": f"doc-{Path(filename).stem.lower()}",
            "filename": filename,
            "mime_type": "text/markdown",
            "status": "ready",
            "file_path": str(path),
            "size_bytes": path.stat().st_size,
        }

    def _prepare_template_registry(self, state: dict) -> dict:
        domains = self.tmpdir / "domains"
        prompts = self.tmpdir / "prompts"
        domains.mkdir(parents=True, exist_ok=True)
        prompts.mkdir(parents=True, exist_ok=True)
        return load_template_registry.run(state, domains_base_dir=domains, prompts_dir=prompts)

    def _run_runtime_nodes(self, state: dict) -> dict:
        planned = planner.run(
            state,
            llm_planner=lambda _prompt, _tools, _context: _valid_planner_output(state["user_query"]),
        )
        return retrieve.run(
            planned,
            retrieve_fn=lambda *_args, **_kwargs: {"results": [], "debug_trace": {"route": {"model": "knowledge"}}},
        )

    def test_pipeline_resolves_builder_document_filename_for_instruction_step(self):
        guide_path = self.tmpdir / "Observation_Guide.md"
        guide_path.write_text("# Observation\nObserve the passage carefully.", encoding="utf-8")
        state = self._base_state(
            user_query="查考經文約翰福音第17章",
            builder_instructions="""
## Mode Detection
• Bible Study
  o Trigger: query includes 「查考」 「經文」
  o Start full workflow: 查經互動模組

## 查經互動模組
1. 細察事實 (Observation)
使用資源： observation guide.md
""",
            builder_documents=[
                {
                    "id": "doc-observation",
                    "filename": "Observation_Guide.md",
                    "mime_type": "text/markdown",
                    "status": "ready",
                    "file_path": str(guide_path),
                    "size_bytes": guide_path.stat().st_size,
                },
            ],
        )
        calls = []

        def llm_planner(_prompt, _tools, _context):
            return _valid_planner_output(state["user_query"])

        def retrieve_fn(query_text, top_k, filters):
            calls.append({"query_text": query_text, "top_k": top_k, "filters": dict(filters)})
            return {
                "results": [
                    {
                        "doc_id": "doc-observation",
                        "title": "Observation Guide",
                        "snippet": "Observe the passage carefully.",
                        "score": 0.8,
                    }
                ],
                "debug_trace": {"route": {"model": "instruction"}},
            }

        response = run_chat_pipeline(
            state,
            session_repo=self.session_repo,
            chat_repo=self.chat_repo,
            planner_repo=self.planner_repo,
            retrieval_repo=self.retrieval_repo,
            llm_planner=llm_planner,
            llm_answer=lambda _prompt, _tools, _context: _valid_final_answer(),
            retrieve_fn=retrieve_fn,
        )

        self.assertEqual(response["retrieval_summary"]["instruction_resource"], "Observation_Guide.md")
        self.assertEqual(response["retrieval_summary"]["instruction_retrieved_count"], 1)
        self.assertEqual(response["retrieval_summary"]["instruction_resource_context_summary"][0]["filename"], "Observation_Guide.md")
        self.assertEqual(response["retrieval_summary"]["instruction_resource_context_summary"][0]["source_kind"], "builder_direct_load")
        self.assertEqual(response["retrieval_summary"]["turn_intent"], "start")
        self.assertEqual(response["retrieval_summary"]["action_type"], "load_resource")
        self.assertEqual(response["retrieval_summary"]["primary_action_type"], "load_resource")
        self.assertIn("respond_to_user", response["retrieval_summary"]["action_types"])
        self.assertIn("update_session_state", response["retrieval_summary"]["action_types"])
        self.assertGreaterEqual(response["retrieval_summary"]["action_count"], 3)
        self.assertEqual(response["retrieval_summary"]["primary_scope_type"], "workflow")
        self.assertEqual(response["retrieval_summary"]["active_step_scope"]["scope_type"], "step")
        self.assertEqual(response["retrieval_summary"]["presentation_mode"], "question_only")
        self.assertEqual(response["turn_execution_plan"]["turn_intent"], "start")
        self.assertEqual(response["turn_execution_plan"]["primary_scope"]["scope_type"], "workflow")
        self.assertEqual(response["turn_execution_plan"]["active_step_scope"]["scope_type"], "step")
        self.assertFalse(any(call.get("filters", {}).get("filename") == "Observation_Guide.md" for call in calls))

    def test_chat_service_summary_exposes_binding_and_selected_resource_metadata(self):
        result = {
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
        }

        summary = _build_retrieval_summary(result, _valid_final_answer())

        self.assertEqual(summary["active_binding_ids"], ["binding:observation", "binding:bundle-template"])
        self.assertEqual(summary["active_dependency_group_ids"], ["group:bundle-pack"])
        self.assertEqual(
            summary["artifact_gate_status"],
            {"binding:bundle-template": {"artifact_role": "director_bundle", "satisfied": True}},
        )
        self.assertEqual(summary["selected_resource_filenames"], ["Observation_Guide.md", "Director_Bundle_Spec.md"])
        self.assertEqual(summary["selected_resource_kinds"], ["instruction_resource", "schema_anchor"])

    def test_chat_service_summary_exposes_layered_scope_and_request_provenance_metadata(self):
        result = {
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
        }

        summary = _build_retrieval_summary(result, _valid_final_answer())

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

    def test_chat_service_summary_exposes_bundled_execution_runtime_fields(self):
        result = {
            "turn_execution_plan": {
                "active_execution_mode": "bundled",
                "active_bundled_step_ids": [
                    "step:interaction_logic_execution_flow:2",
                    "step:interaction_logic_execution_flow:3",
                    "step:interaction_logic_execution_flow:4",
                    "step:interaction_logic_execution_flow:5",
                ],
                "bundled_entry_step_id": "step:interaction_logic_execution_flow:2",
            },
            "session_execution_state": {
                "active_execution_mode": "bundled",
                "active_bundled_step_ids": [
                    "step:interaction_logic_execution_flow:2",
                    "step:interaction_logic_execution_flow:3",
                    "step:interaction_logic_execution_flow:4",
                    "step:interaction_logic_execution_flow:5",
                ],
                "bundled_entry_step_id": "step:interaction_logic_execution_flow:2",
            },
        }

        summary = _build_retrieval_summary(result, _valid_final_answer())

        self.assertEqual(summary["active_execution_mode"], "bundled")
        self.assertEqual(
            summary["active_bundled_step_ids"],
            [
                "step:interaction_logic_execution_flow:2",
                "step:interaction_logic_execution_flow:3",
                "step:interaction_logic_execution_flow:4",
                "step:interaction_logic_execution_flow:5",
            ],
        )
        self.assertEqual(summary["bundled_entry_step_id"], "step:interaction_logic_execution_flow:2")

    def test_chat_service_summary_falls_back_to_assembly_targets_when_session_targets_missing(self):
        result = {
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
                ]
            },
            "session_execution_state": {
                "active_artifact_roles": ["director_bundle"],
                "artifact_gate_status": {
                    "binding:bundle-template": {
                        "artifact_role": "director_bundle",
                        "required_for_progression": True,
                        "status": "awaiting_artifact",
                    }
                },
            },
            "assembly_state": {
                "target_outputs": ["Director Bundle.md"],
                "source_output_key": "final_answer",
                "status": "pending_source_output",
            },
        }

        summary = _build_retrieval_summary(result, _valid_final_answer())

        self.assertEqual(summary["active_artifact_roles"], ["director_bundle"])
        self.assertEqual(summary["output_artifact_targets"], ["Director Bundle.md"])
        self.assertEqual(summary["assembly_state"]["target_outputs"], ["Director Bundle.md"])

    def test_pipeline_uses_template_evidence_and_excludes_output_artifacts_from_retrieval(self):
        template_path = self.tmpdir / "Director_Bundle_Spec.md"
        template_path.write_text("# Director Bundle\n## Overview\n## Scenes\n## Prompts", encoding="utf-8")
        state = self._base_state(
            user_query="Please use Director Bundle Spec template to generate output",
            builder_instructions="""
## Output Template Module
Use Director_Bundle_Spec.md
Generate Director Bundle.md
""",
            builder_documents=[
                {
                    "id": "doc-template",
                    "filename": "Director_Bundle_Spec.md",
                    "mime_type": "text/markdown",
                    "status": "ready",
                    "file_path": str(template_path),
                    "size_bytes": template_path.stat().st_size,
                },
                {"id": "doc-artifact", "filename": "Director Bundle.md", "mime_type": "text/markdown", "status": "ready"},
            ],
        )
        calls = []
        captured = {}

        def llm_planner(_prompt, _tools, _context):
            return _valid_planner_output(state["user_query"])

        def retrieve_fn(query_text, top_k, filters):
            calls.append({"query_text": query_text, "top_k": top_k, "filters": dict(filters)})
            return {"results": [], "debug_trace": {"route": {"model": "knowledge"}}}

        def llm_answer(_prompt, _tools, context):
            captured["template_evidence"] = json.loads(json.dumps(context.get("template_evidence", [])))
            captured["template_resource_context"] = json.loads(json.dumps(context.get("template_resource_context", [])))
            captured["instruction_evidence"] = json.loads(json.dumps(context.get("instruction_evidence", [])))
            captured["knowledge_evidence"] = json.loads(json.dumps(context.get("knowledge_evidence", [])))
            return _valid_final_answer(
                content="# Director Bundle\n\n## Overview\nGenerated from template guidance.",
                title="Director Bundle Spec",
                snippet="Use sections: Overview, Scenes, Prompts.",
            )

        response = run_chat_pipeline(
            state,
            session_repo=self.session_repo,
            chat_repo=self.chat_repo,
            planner_repo=self.planner_repo,
            retrieval_repo=self.retrieval_repo,
            llm_planner=llm_planner,
            llm_answer=llm_answer,
            retrieve_fn=retrieve_fn,
        )

        self.assertFalse(
            any(call.get("filters", {}).get("filename") == "Director_Bundle_Spec.md" for call in calls)
        )
        self.assertFalse(
            any(call.get("filters", {}).get("filename") == "Director Bundle.md" for call in calls)
        )
        self.assertNotIn("Director Bundle.md", json.dumps(calls, ensure_ascii=False))
        self.assertEqual(captured["template_evidence"][0]["title"], "Director_Bundle_Spec.md")
        self.assertEqual(captured["template_resource_context"][0]["filename"], "Director_Bundle_Spec.md")
        self.assertEqual(captured["instruction_evidence"], [])
        self.assertEqual(captured["knowledge_evidence"], [])
        self.assertEqual(response["retrieval_summary"]["template_retrieved_count"], 1)
        self.assertEqual(response["retrieval_summary"]["template_titles"], ["Director_Bundle_Spec.md"])
        self.assertIn("Director Bundle.md", response["retrieval_summary"]["output_artifact_targets"])

    def test_bible_tutor_starter_turn_uses_mode_block_only(self):
        state = self._base_state(
            user_query="我想查考一段經文",
            builder_instructions=self._bible_tutor_instructions(),
            builder_documents=[],
        )

        def llm_planner(_prompt, _tools, _context):
            return _valid_planner_output(state["user_query"])

        def llm_answer(_prompt, _tools, _context):
            raise AssertionError("Starter turn should use direct instruction-block response")

        response = run_chat_pipeline(
            state,
            session_repo=self.session_repo,
            chat_repo=self.chat_repo,
            planner_repo=self.planner_repo,
            retrieval_repo=self.retrieval_repo,
            llm_planner=llm_planner,
            llm_answer=llm_answer,
            retrieve_fn=lambda *_args, **_kwargs: {"results": [], "debug_trace": {"route": {"model": "knowledge"}}},
        )

        self.assertEqual(response["content"], "好的，我們一起用歸納釋經法查考經文。請問想從哪一段開始？")
        self.assertEqual(response["retrieval_summary"]["instruction_block_type"], "mode")
        self.assertEqual(response["retrieval_summary"]["instruction_retrieved_count"], 0)
        self.assertEqual(response["retrieval_summary"]["knowledge_retrieved_count"], 0)
        self.assertEqual(response["retrieval_summary"]["turn_intent"], "start")
        self.assertEqual(response["retrieval_summary"]["action_type"], "load_resource")
        self.assertIn("respond_to_user", response["retrieval_summary"]["action_types"])
        self.assertEqual(response["retrieval_summary"]["primary_scope_type"], "mode")
        self.assertEqual(response["retrieval_summary"]["presentation_mode"], "question_only")
        self.assertEqual(response["turn_execution_plan"]["turn_intent"], "start")
        self.assertEqual(response["turn_execution_plan"]["primary_scope"]["scope_type"], "mode")

    def test_bible_tutor_passage_selection_turn_loads_observation_guide(self):
        guide_path = self.tmpdir / "observation_guide.md"
        guide_path.write_text(
            "# Observation\nAsk 1-3 observation questions about people, actions, repeated words, and commands.",
            encoding="utf-8",
        )
        state = self._base_state(
            user_query="提摩太前書 4:11-16",
            builder_instructions=self._bible_tutor_instructions(),
            builder_documents=[
                {
                    "id": "doc-observation",
                    "filename": "observation_guide.md",
                    "mime_type": "text/markdown",
                    "status": "ready",
                    "file_path": str(guide_path),
                    "size_bytes": guide_path.stat().st_size,
                }
            ],
        )
        state["workflow_progress"] = {
            "workflow_id": "bible_study",
            "workflow_title": "æŸ¥ç¶“äº’å‹•æ¨¡çµ„",
        }
        def llm_planner(_prompt, _tools, _context):
            return _valid_planner_output(state["user_query"])

        response = run_chat_pipeline(
            state,
            session_repo=self.session_repo,
            chat_repo=self.chat_repo,
            planner_repo=self.planner_repo,
            retrieval_repo=self.retrieval_repo,
            llm_planner=llm_planner,
            llm_answer=lambda _prompt, _tools, _context: _valid_final_answer(),
            retrieve_fn=lambda *_args, **_kwargs: {"results": [], "debug_trace": {"route": {"model": "knowledge"}}},
        )

        self.assertEqual(response["retrieval_summary"]["instruction_block_type"], "step")
        self.assertEqual(response["retrieval_summary"]["instruction_resource_context_summary"][0]["filename"], "observation_guide.md")
        self.assertEqual(response["retrieval_summary"]["instruction_resource_context_summary"][0]["load_strategy"], "inline_full")
        self.assertTrue(str(response["content"]).strip())
        self.assertEqual(response["retrieval_summary"]["turn_intent"], "start")
        self.assertEqual(response["retrieval_summary"]["action_type"], "load_resource")
        self.assertIn("respond_to_user", response["retrieval_summary"]["action_types"])
        self.assertIn("update_session_state", response["retrieval_summary"]["action_types"])
        self.assertEqual(response["retrieval_summary"]["primary_scope_type"], "workflow")
        self.assertEqual(response["retrieval_summary"]["active_step_scope"]["scope_type"], "step")
        self.assertEqual(response["retrieval_summary"]["presentation_mode"], "question_only")
        self.assertEqual(response["turn_execution_plan"]["turn_intent"], "start")
        self.assertEqual(response["turn_execution_plan"]["primary_scope"]["scope_type"], "workflow")

    def test_bible_tutor_first_observation_followup_keeps_step_context(self):
        guide_path = self.tmpdir / "observation_guide_followup.md"
        guide_path.write_text(
            "# Observation\nKeep asking focused observation questions and wait for the learner before advancing.",
            encoding="utf-8",
        )
        state = self._base_state(
            user_query="保羅先吩咐提摩太要教導和勸勉人",
            builder_instructions=self._bible_tutor_instructions(),
            builder_documents=[
                {
                    "id": "doc-observation-2",
                    "filename": "observation_guide.md",
                    "mime_type": "text/markdown",
                    "status": "ready",
                    "file_path": str(guide_path),
                    "size_bytes": guide_path.stat().st_size,
                }
            ],
        )
        state["workflow_progress"] = {
            "workflow_id": "bible_study",
            "workflow_title": "æŸ¥ç¶“äº’å‹•æ¨¡çµ„",
            "step_order": 1,
            "step_title": "ç´°å¯Ÿäº‹å¯¦ (Observation)",
            "resource_file": "observation_guide.md",
        }
        def llm_planner(_prompt, _tools, _context):
            return _valid_planner_output(state["user_query"])

        response = run_chat_pipeline(
            state,
            session_repo=self.session_repo,
            chat_repo=self.chat_repo,
            planner_repo=self.planner_repo,
            retrieval_repo=self.retrieval_repo,
            llm_planner=llm_planner,
            llm_answer=lambda _prompt, _tools, _context: _valid_final_answer(),
            retrieve_fn=lambda *_args, **_kwargs: {"results": [], "debug_trace": {"route": {"model": "knowledge"}}},
        )

        self.assertEqual(response["retrieval_summary"]["instruction_block_type"], "step")
        self.assertEqual(response["retrieval_summary"]["instruction_resource_context_summary"][0]["filename"], "observation_guide.md")
        self.assertEqual(response["session_execution_state"]["active_step_order"], 1)
        self.assertEqual(response["workflow_progress"]["step_order"], 1)
        self.assertTrue(str(response["content"]).strip())
        self.assertEqual(response["retrieval_summary"]["turn_intent"], "answer_prior_questions")
        self.assertEqual(response["retrieval_summary"]["action_type"], "load_resource")
        self.assertIn("respond_to_user", response["retrieval_summary"]["action_types"])
        self.assertIn("update_session_state", response["retrieval_summary"]["action_types"])
        self.assertEqual(response["retrieval_summary"]["primary_scope_type"], "workflow")
        self.assertEqual(response["retrieval_summary"]["active_step_scope"]["scope_type"], "step")
        self.assertEqual(response["retrieval_summary"]["presentation_mode"], "question_only")
        self.assertEqual(response["turn_execution_plan"]["turn_intent"], "answer_prior_questions")
        self.assertEqual(response["turn_execution_plan"]["primary_scope"]["scope_type"], "workflow")

    def test_church_ministry_pipeline_transitions_from_interactive_checkpoints_to_bundled_execution(self):
        builder_documents = [
            self._builder_document(
                "Ministry_Discovery_Questions.md",
                "# Discovery\nAsk one clarifying ministry-goal question before drafting.",
            ),
            self._builder_document(
                "Ministry_Constraint_Checklist.md",
                "# Constraints\nConfirm denomination, audience, and tone before continuing.",
            ),
            self._builder_document(
                "Ministry_Prompt_Framework.md",
                "# Framework\nGenerate the structured ministry prompt draft.",
            ),
            self._builder_document(
                "tool_selection_map.md",
                "# Tool Selection\nRoute the prompt through the correct tool pair.",
            ),
            self._builder_document(
                "ministry_output_rules.md",
                "# Output Rules\nValidate the ministry prompt output.",
            ),
            self._builder_document(
                "ministry_prompt_guardrails.md",
                "# Guardrails\nCheck pastoral and doctrinal guardrails.",
            ),
            self._builder_document(
                "delivery_package_template.md",
                "# Delivery Package\nAssemble the final delivery package.",
            ),
        ]

        turn1_state = self._base_state(
            user_query="Design a church ministry prompt for our volunteer retreat.",
            builder_instructions=self._church_ministry_bundled_instructions(),
            builder_documents=builder_documents,
        )
        turn1_state = self._prepare_template_registry(turn1_state)
        turn1_state["workflow_progress"] = {
            "workflow_id": "interaction_logic_execution_flow",
            "workflow_title": "Interaction Logic & Execution Flow",
            "step_order": 0,
            "step_title": "Clarify the Ministry Goal",
            "resource_file": "Ministry_Discovery_Questions.md",
        }

        result1 = self._run_runtime_nodes(turn1_state)
        summary1 = _build_retrieval_summary(result1, _valid_final_answer())

        self.assertIsNone(summary1["active_execution_mode"])
        self.assertEqual(summary1["active_step_scope"]["step_order"], 0)
        self.assertEqual(
            summary1["instruction_resource_context_summary"][0]["filename"],
            "Ministry_Discovery_Questions.md",
        )

        turn2_state = self._base_state(
            user_query="The audience is youth ministry leaders.",
            builder_instructions=self._church_ministry_bundled_instructions(),
            builder_documents=builder_documents,
        )
        turn2_state = self._prepare_template_registry(turn2_state)
        turn2_state["workflow_progress"] = result1["session_execution_state"]["workflow_progress"]
        turn2_state["session_execution_state"] = result1["session_execution_state"]

        result2 = self._run_runtime_nodes(turn2_state)
        summary2 = _build_retrieval_summary(result2, _valid_final_answer())

        self.assertIsNone(summary2["active_execution_mode"])
        self.assertEqual(summary2["active_step_scope"]["step_order"], 0)
        self.assertEqual(
            summary2["instruction_resource_context_summary"][0]["filename"],
            "Ministry_Discovery_Questions.md",
        )

        turn3_state = self._base_state(
            user_query="Continue with the confirmed ministry details.",
            builder_instructions=self._church_ministry_bundled_instructions(),
            builder_documents=builder_documents,
        )
        turn3_state = self._prepare_template_registry(turn3_state)
        turn3_state["workflow_progress"] = {
            "workflow_id": "interaction_logic_execution_flow",
            "workflow_title": "Interaction Logic & Execution Flow",
            "step_order": 1,
            "step_title": "Confirm the Ministry Constraints",
            "resource_file": "Ministry_Constraint_Checklist.md",
        }
        turn3_state["session_execution_state"] = {
            "workflow_progress": dict(turn3_state["workflow_progress"]),
            "active_step_order": 1,
            "active_step_title": "Confirm the Ministry Constraints",
            "active_step_scope_id": "step:interaction_logic_execution_flow:1",
            "procedure_step_activation": {
                "step_scope_id": "step:interaction_logic_execution_flow:1",
                "step_scope_type": "step",
                "step_order": 1,
                "step_title": "Confirm the Ministry Constraints",
            },
        }

        result3 = self._run_runtime_nodes(turn3_state)
        summary3 = _build_retrieval_summary(result3, _valid_final_answer())

        self.assertEqual(summary3["active_execution_mode"], "bundled")
        self.assertEqual(
            summary3["bundled_entry_step_id"],
            "step:interaction_logic_execution_flow:2",
        )
        self.assertEqual(
            summary3["active_bundled_step_ids"],
            [
                "step:interaction_logic_execution_flow:2",
                "step:interaction_logic_execution_flow:3",
                "step:interaction_logic_execution_flow:4",
                "step:interaction_logic_execution_flow:5",
            ],
        )
        self.assertEqual(summary3["active_step_scope"]["step_order"], 2)
        self.assertTrue(
            {
                "Ministry_Prompt_Framework.md",
                "tool_selection_map.md",
                "ministry_output_rules.md",
                "ministry_prompt_guardrails.md",
                "delivery_package_template.md",
            }.issubset(set(summary3["selected_resource_filenames"]))
        )
        self.assertEqual(result3["turn_execution_plan"]["active_execution_mode"], "bundled")
        self.assertEqual(result3["session_execution_state"]["active_execution_mode"], "bundled")

    def test_gpt_application_pipeline_exposes_bundled_configuration_phase_runtime_contract(self):
        result = {
            "turn_execution_plan": {
                "active_execution_mode": "bundled",
                "active_bundled_step_ids": [
                    "step:interaction_logic_execution_flow:1",
                    "step:interaction_logic_execution_flow:2",
                    "step:interaction_logic_execution_flow:3",
                ],
                "bundled_entry_step_id": "step:interaction_logic_execution_flow:1",
                "resource_requests": [
                    {
                        "filename": "interaction_patterns.md",
                        "resource_role": "instruction_source",
                        "source_layer": "procedure_step",
                        "step_scope_id": "step:interaction_logic_execution_flow:1",
                    },
                    {
                        "filename": "configuration_matrix.md",
                        "resource_role": "instruction_source",
                        "source_layer": "procedure_step",
                        "step_scope_id": "step:interaction_logic_execution_flow:1",
                    },
                    {
                        "filename": "support_guardrails.md",
                        "resource_role": "instruction_source",
                        "source_layer": "procedure_step",
                        "step_scope_id": "step:interaction_logic_execution_flow:1",
                    },
                ],
            },
            "session_execution_state": {
                "active_execution_mode": "bundled",
                "active_bundled_step_ids": [
                    "step:interaction_logic_execution_flow:1",
                    "step:interaction_logic_execution_flow:2",
                    "step:interaction_logic_execution_flow:3",
                ],
                "bundled_entry_step_id": "step:interaction_logic_execution_flow:1",
                "procedure_step_activation": {
                    "step_scope_id": "step:interaction_logic_execution_flow:1",
                    "step_scope_type": "step",
                    "step_order": 1,
                    "step_title": "Configure the Interaction Model",
                },
                "active_step_scope_id": "step:interaction_logic_execution_flow:1",
            },
            "instruction_resource_context": [
                {"filename": "interaction_patterns.md", "load_strategy": "inline_full", "source_kind": "builder_direct_load"},
                {"filename": "configuration_matrix.md", "load_strategy": "inline_full", "source_kind": "builder_direct_load"},
                {"filename": "support_guardrails.md", "load_strategy": "inline_full", "source_kind": "builder_direct_load"},
            ],
        }
        summary = _build_retrieval_summary(result, _valid_final_answer())

        self.assertEqual(summary["active_execution_mode"], "bundled")
        self.assertEqual(summary["bundled_entry_step_id"], "step:interaction_logic_execution_flow:1")
        self.assertEqual(
            summary["active_bundled_step_ids"],
            [
                "step:interaction_logic_execution_flow:1",
                "step:interaction_logic_execution_flow:2",
                "step:interaction_logic_execution_flow:3",
            ],
        )
        self.assertEqual(summary["active_step_scope"]["step_order"], 1)
        self.assertTrue(
            {
                "interaction_patterns.md",
                "configuration_matrix.md",
                "support_guardrails.md",
            }.issubset(set(summary["selected_resource_filenames"]))
        )

    def test_out_of_scope_query_bypasses_retrieval_and_answers_directly(self):
        state = self._base_state(
            user_query="Explain Python dataclass vs pydantic",
            builder_instructions=self._bible_tutor_instructions(),
            builder_documents=[],
        )
        calls = {"retrieve": 0, "answer_contexts": []}

        def llm_planner(_prompt, _tools, _context):
            return _valid_planner_output(state["user_query"])

        def retrieve_fn(_query_text, _top_k, _filters):
            calls["retrieve"] += 1
            return {"results": [{"doc_id": "unexpected"}], "debug_trace": {"route": {"model": "knowledge"}}}

        def llm_answer(prompt, _tools, context):
            calls["answer_contexts"].append({"prompt": prompt, "context": json.loads(json.dumps(context))})
            return _valid_final_answer(content="General answer", title="General", snippet="Direct")

        response = run_chat_pipeline(
            state,
            session_repo=self.session_repo,
            chat_repo=self.chat_repo,
            planner_repo=self.planner_repo,
            retrieval_repo=self.retrieval_repo,
            llm_planner=llm_planner,
            llm_answer=llm_answer,
            retrieve_fn=retrieve_fn,
        )

        self.assertEqual(calls["retrieve"], 0)
        self.assertEqual(response["retrieval_summary"]["turn_intent"], "general_out_of_scope_question")
        self.assertTrue(response["retrieval_summary"]["is_out_of_scope"])
        self.assertTrue(response["retrieval_summary"]["retrieval_bypassed"])
        self.assertEqual(response["retrieval_summary"]["retrieval_bypass_reason"], "general_out_of_scope_question")
        self.assertEqual(response["retrieval_summary"]["answer_source"], "general_llm_direct")
        self.assertNotIn("planner_output", calls["answer_contexts"][0]["context"])

    def test_pipeline_emits_cross_app_binding_metadata_and_keeps_app_scoped_retrieval(self):
        scenarios = [
            {
                "name": "church",
                "query": "Church Ministry Prompt Designer Tool Selection Support Module tool selection mapping",
                "instructions": """
## Church Ministry Prompt Designer Routing Phase
Use template_library.md or dynamic_prompt_optimizer.md based on the ministry request.

## Church Ministry Prompt Designer Output Rules
Load ministry_output_rules.md and ministry_prompt_guardrails.md before writing the final prompt.

## Church Ministry Prompt Designer Tool Selection Support Module
Use tool_selection_map.md and tool_usage_matrix.md to map the selected tool pair.
""",
                "expected_bindings": {
                    "support_module:church_ministry_prompt_designer_tool_selection_support_module",
                },
                "expected_resources": {
                    "tool_selection_map.md",
                    "tool_usage_matrix.md",
                },
            },
            {
                "name": "gpt",
                "query": "GPT Application Design Assistant Support Module support guidance",
                "instructions": """
## GPT Application Design Assistant Discovery Phase
Use application_discovery_brief.md to frame the first pass.

## GPT Application Design Assistant Interaction Configuration Phase
Load interaction_patterns.md and configuration_matrix.md before defining the app behavior.

## GPT Application Design Assistant Support Module
Use support_prompt_library.md and support_guardrails.md when the configuration phase needs extra guidance.
""",
                "expected_bindings": {
                    "support_module:gpt_application_design_assistant_support_module",
                },
                "expected_resources": {
                    "support_prompt_library.md",
                    "support_guardrails.md",
                },
            },
            {
                "name": "vibe",
                "query": "Start a new vibe story director pass from the bundle spec",
                "instructions": """
## Vibe Story Director Starter
Use Director_Bundle_Spec.md to open the first director pass.

## Vibe Story Director Bundle Upload Gate
If Director Bundle.md is missing, prompt the user to upload Director Bundle.md before executing the next pass.
""",
                "expected_bindings": {
                    "starter:vibe_story_director_starter",
                    "artifact_gate:vibe_story_director_bundle_upload_gate",
                },
                "expected_resources": {
                    "Director_Bundle_Spec.md",
                },
                "expected_resource_kind": "template_resource",
            },
        ]

        for scenario in scenarios:
            with self.subTest(scenario=scenario["name"]):
                state = self._base_state(
                    user_query=scenario["query"],
                    builder_instructions=scenario["instructions"],
                    builder_documents=[],
                )
                calls = []

                def llm_planner(_prompt, _tools, _context):
                    return _valid_planner_output(state["user_query"])

                def retrieve_fn(query_text, top_k, filters):
                    calls.append({"query_text": query_text, "top_k": top_k, "filters": dict(filters)})
                    return {"results": [], "debug_trace": {"route": {"model": "knowledge"}}}

                response = run_chat_pipeline(
                    state,
                    session_repo=self.session_repo,
                    chat_repo=self.chat_repo,
                    planner_repo=self.planner_repo,
                    retrieval_repo=self.retrieval_repo,
                    llm_planner=llm_planner,
                    llm_answer=lambda _prompt, _tools, _context: _valid_final_answer(),
                    retrieve_fn=retrieve_fn,
                )

                self.assertTrue(all(call.get("filters", {}).get("app_id") == "app-1" for call in calls))
                self.assertTrue(
                    scenario["expected_bindings"].issubset(
                        set(response["retrieval_summary"].get("active_binding_ids") or [])
                    )
                )
                self.assertTrue(
                    scenario["expected_resources"].issubset(
                        set(response["retrieval_summary"].get("selected_resource_filenames") or [])
                    )
                )
                if scenario["name"] == "vibe":
                    self.assertIn(
                        scenario["expected_resource_kind"],
                        response["retrieval_summary"].get("selected_resource_kinds") or [],
                    )
                    self.assertFalse(
                        response["retrieval_summary"]["artifact_gate_status"][
                            "artifact_gate:vibe_story_director_bundle_upload_gate"
                        ]["satisfied"]
                    )
                    self.assertEqual(
                        response["retrieval_summary"]["artifact_gate_status"][
                            "artifact_gate:vibe_story_director_bundle_upload_gate"
                        ]["missing_artifact_prompt"],
                        "If Director Bundle.md is missing, prompt the user to upload Director Bundle.md before executing the next pass.",
                    )
    def test_retrieval_summary_preserves_cross_app_binding_contracts(self):
        result = {
            "turn_execution_plan": {
                "resource_requests": [
                    {
                        "filename": "template_library.md",
                        "resource_role": "output_template",
                        "binding_id": "binding:ministry-route",
                        "resource_kind": "template_resource",
                    },
                    {
                        "filename": "dynamic_prompt_optimizer.md",
                        "resource_role": "instruction_source",
                        "binding_id": "binding:ministry-route",
                        "resource_kind": "instruction_resource",
                    },
                    {
                        "filename": "ministry_output_rules.md",
                        "resource_role": "instruction_source",
                        "binding_id": "binding:ministry-output-rules",
                        "dependency_group_id": "group:ministry-output-rules",
                        "resource_kind": "instruction_resource",
                    },
                    {
                        "filename": "support_prompt_library.md",
                        "resource_role": "instruction_source",
                        "binding_id": "binding:gpt-support-module",
                        "dependency_group_id": "group:gpt-support-pack",
                        "resource_kind": "instruction_resource",
                    },
                    {
                        "filename": "Director_Bundle_Spec.md",
                        "resource_role": "output_template",
                        "binding_id": "binding:vibe-starter",
                        "resource_kind": "schema_anchor",
                        "artifact_role": "director_bundle",
                    },
                    {
                        "filename": "Director Bundle.md",
                        "resource_role": "knowledge_source",
                        "binding_id": "binding:vibe-artifact-gate",
                        "artifact_role": "director_bundle",
                        "required_for_progression": True,
                    },
                ]
            },
            "session_execution_state": {
                "active_binding_ids": [
                    "binding:ministry-route",
                    "binding:ministry-output-rules",
                    "binding:gpt-support-module",
                    "binding:vibe-starter",
                    "binding:vibe-artifact-gate",
                ],
                "active_dependency_group_ids": [
                    "group:ministry-output-rules",
                    "group:gpt-support-pack",
                ],
                "active_artifact_roles": ["director_bundle"],
                "artifact_gate_status": {
                    "binding:vibe-artifact-gate": {
                        "artifact_role": "director_bundle",
                        "required_for_progression": True,
                        "satisfied": False,
                        "missing_artifact_prompt": "Upload Director Bundle.md before continuing.",
                    }
                },
                "output_artifact_targets": ["Director Bundle.md"],
            },
            "instruction_resource_context": [
                {
                    "filename": "dynamic_prompt_optimizer.md",
                    "source_kind": "builder_direct_load",
                    "binding_id": "binding:ministry-route",
                    "resource_kind": "instruction_resource",
                },
                {
                    "filename": "support_prompt_library.md",
                    "source_kind": "builder_direct_load",
                    "binding_id": "binding:gpt-support-module",
                    "dependency_group_id": "group:gpt-support-pack",
                    "resource_kind": "instruction_resource",
                },
            ],
            "template_resource_context": [
                {
                    "filename": "template_library.md",
                    "source_kind": "builder_direct_load",
                    "binding_id": "binding:ministry-route",
                    "resource_kind": "template_resource",
                },
                {
                    "filename": "Director_Bundle_Spec.md",
                    "source_kind": "builder_direct_load",
                    "binding_id": "binding:vibe-starter",
                    "resource_kind": "schema_anchor",
                    "artifact_role": "director_bundle",
                },
            ],
            "assembly_state": {
                "target_outputs": ["Director Bundle.md"],
                "status": "awaiting_artifact",
            },
        }

        summary = _build_retrieval_summary(result, _valid_final_answer())

        self.assertEqual(
            summary["active_binding_ids"],
            [
                "binding:ministry-route",
                "binding:ministry-output-rules",
                "binding:gpt-support-module",
                "binding:vibe-starter",
                "binding:vibe-artifact-gate",
            ],
        )
        self.assertEqual(
            summary["active_dependency_group_ids"],
            ["group:ministry-output-rules", "group:gpt-support-pack"],
        )
        self.assertEqual(summary["active_artifact_roles"], ["director_bundle"])
        self.assertEqual(
            summary["artifact_gate_status"]["binding:vibe-artifact-gate"]["missing_artifact_prompt"],
            "Upload Director Bundle.md before continuing.",
        )
        self.assertEqual(
            summary["selected_resource_filenames"],
            [
                "template_library.md",
                "dynamic_prompt_optimizer.md",
                "ministry_output_rules.md",
                "support_prompt_library.md",
                "Director_Bundle_Spec.md",
                "Director Bundle.md",
            ],
        )
        self.assertIn("schema_anchor", summary["selected_resource_kinds"])
        self.assertIn("template_resource", summary["selected_resource_kinds"])
        self.assertEqual(summary["output_artifact_targets"], ["Director Bundle.md"])


if __name__ == "__main__":
    unittest.main()






