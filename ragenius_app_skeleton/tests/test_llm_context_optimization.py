import copy
import math
import os
import unittest
from unittest import mock

from backend.app import llm_runtime
from backend.app.llm_context_optimization import (
    add_task_token_accounting,
    apply_ordered_compaction,
    bounded_chat_history,
    build_answer_context,
    build_or_refresh_chat_summary,
    build_planner_context,
    compact_hybrid_decision_packet,
    compact_evidence_items,
    context_optimization_mode,
    evidence_analysis_mode,
    estimate_task_input_tokens,
    deterministic_evidence_assessment,
    normal_query_optimization_eligible,
    optimize_task_context,
    semantic_section_compact,
)
from workflows.graph_state import GraphStateModel


class LlmContextOptimizationTests(unittest.TestCase):
    def test_only_plain_text_turn_without_upload_event_is_eligible(self):
        self.assertTrue(
            normal_query_optimization_eligible(
                {
                    "turn_input_type": "text_query",
                    "pending_upload_analysis": False,
                    "session_upload_event_ids": [],
                }
            )
        )
        for state in (
            {"turn_input_type": "session_upload", "pending_upload_analysis": True},
            {"turn_input_type": "text_query", "session_upload_event_ids": ["upload-1"]},
            {"turn_input_type": "exec", "pending_upload_analysis": False},
            {},
        ):
            self.assertFalse(normal_query_optimization_eligible(state))

    def test_modes_are_explicit_and_safe_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(context_optimization_mode(), "off")
            self.assertEqual(evidence_analysis_mode(), "auto")
        with mock.patch.dict(
            os.environ,
            {
                "RAGENIUS_LLM_CONTEXT_OPTIMIZATION": "1",
                "RAGENIUS_LLM_CONTEXT_OPTIMIZATION_MODE": "compact",
                "RAGENIUS_LLM_EVIDENCE_ANALYSIS_MODE": "llm_required",
            },
            clear=True,
        ):
            self.assertEqual(context_optimization_mode(), "compact")
            self.assertEqual(evidence_analysis_mode(), "llm_required")

    def test_internal_state_fields_round_trip_with_wire_aliases(self):
        model = GraphStateModel(
            _context_optimization_eligible=True,
            _context_optimization_mode="diagnostic",
            _context_optimization_diagnostics={"planner": {}},
            _turn_token_accounting={"call_count": 1},
        )
        payload = model.model_dump(by_alias=True)
        self.assertTrue(payload["_context_optimization_eligible"])
        self.assertEqual(payload["_context_optimization_mode"], "diagnostic")

    def test_estimator_uses_same_messages_as_runtime_and_includes_tools(self):
        prompt = "Planner prompt"
        context = {"user_query": "Who is Jesus?", "policy": "x" * 20}
        tools = [{"name": "create_planner_output", "parameters": {"type": "object"}}]
        estimate = estimate_task_input_tokens(prompt, tools, context)

        self.assertEqual(estimate["messages"], llm_runtime._build_messages(prompt, context))
        self.assertGreater(estimate["tokens"], math.ceil(len(prompt) / 4))
        self.assertIn("create_planner_output", estimate["serialized_payload"])

    def test_diagnostic_measures_compact_but_sends_full(self):
        full = {"large": "x" * 1000}
        compact = {"small": "x" * 100}
        result = optimize_task_context(
            task="planner",
            prompt="prompt",
            tools=[],
            full_context=full,
            compact_context=compact,
            eligible=True,
            mode="diagnostic",
        )
        self.assertEqual(result.context, full)
        self.assertEqual(result.diagnostics["actual_outbound_tokens"], result.diagnostics["actual_full_tokens"])
        self.assertGreater(result.diagnostics["estimated_tokens_saved"], 0)

    def test_compact_sends_candidate_and_does_not_mutate_inputs(self):
        full = {"large": ["x" * 1000]}
        compact = {"small": ["x" * 100]}
        originals = copy.deepcopy((full, compact))
        result = optimize_task_context(
            task="planner",
            prompt="prompt",
            tools=[],
            full_context=full,
            compact_context=compact,
            eligible=True,
            mode="compact",
        )
        self.assertEqual(result.context, compact)
        self.assertEqual(result.diagnostics["actual_outbound_tokens"], result.diagnostics["compact_candidate_tokens"])
        self.assertEqual((full, compact), originals)

    def test_turn_accounting_is_additive_and_immutable(self):
        initial = {"calls": [{"task": "planner", "actual_outbound_tokens": 20}]}
        original = copy.deepcopy(initial)
        result = add_task_token_accounting(initial, "answer_generation", {"actual_outbound_tokens": 30})
        self.assertEqual(initial, original)
        self.assertEqual(result["call_count"], 2)
        self.assertEqual(result["turn_estimated_outbound_tokens"], 50)
        self.assertIn("turn_estimated_saving_percent", result)

    def test_history_windows_count_turns_as_two_messages(self):
        history = [{"role": "user" if index % 2 == 0 else "assistant", "content": str(index)} for index in range(20)]
        self.assertEqual(len(bounded_chat_history(history, max_turns=4)), 8)
        self.assertEqual(len(bounded_chat_history(history, max_turns=6)), 12)
        self.assertEqual(history[0]["content"], "0")

    def test_bounded_history_projects_messages_to_role_and_content_only(self):
        history = [
            {
                "id": "message-1",
                "session_id": "session-1",
                "role": "assistant",
                "content": "Prior answer",
                "citations": [{"docId": "doc-1"}],
                "missingInfoTypes": [],
                "retrievalSummary": {
                    "task_model_diagnostics": {"calls": ["x" * 10_000]},
                    "turn_execution_plan": {"actions": ["y" * 5_000]},
                },
                "created_at": "2026-07-24T00:00:00Z",
            }
        ]
        original = copy.deepcopy(history)

        result = bounded_chat_history(history, max_turns=4)

        self.assertEqual(result, [{"role": "assistant", "content": "Prior answer"}])
        self.assertEqual(history, original)

    def test_evidence_is_ranked_and_citation_identity_survives(self):
        items = [
            {"doc_id": "low", "title": "Low", "snippet": "a" * 20, "score": 0.1, "location": "p1", "version": 1, "retrieval_domain": "knowledge_source"},
            {"doc_id": "high", "filename": "high.md", "snippet": "b" * 20, "score": 0.9, "location": "p2", "version": 2, "retrieval_domain": "session_upload", "unused": "drop"},
        ]
        result = compact_evidence_items(items, limit=1, snippet_limit=10)
        self.assertEqual(result[0]["doc_id"], "high")
        self.assertEqual(result[0]["filename"], "high.md")
        self.assertEqual(result[0]["location"], "p2")
        self.assertEqual(result[0]["version"], 2)
        self.assertEqual(result[0]["retrieval_domain"], "session_upload")
        self.assertEqual(result[0]["snippet"], "b" * 10)
        self.assertNotIn("unused", result[0])

    def test_semantic_compaction_keeps_complete_active_and_safety_sections(self):
        text = """Intro\n\n## General\nLong general material.\n\n## Active Step\nDo A.\nDo B.\n\n## Safety Rules\nNever fabricate.\nAlways cite.\n\n## Appendix\nExtra."""
        result = semantic_section_compact(text, active_markers=["Active Step"], max_chars=90)
        self.assertIn("Do A.\nDo B.", result)
        self.assertIn("Never fabricate.\nAlways cite.", result)
        self.assertNotIn("Extra.", result)

    def test_ordered_compaction_applies_all_permitted_stages(self):
        context = {
            "chat_history": [{"role": "user", "content": "x" * 200} for _ in range(20)],
            "knowledge_evidence": [{"doc_id": str(index), "title": "T", "snippet": "y" * 1000, "score": index / 10} for index in range(12)],
            "duplicate": "z" * 2000,
        }
        compact, stages = apply_ordered_compaction("planner", context, budget=100)
        self.assertIn("bounded_chat_history", stages)
        self.assertIn("compact_evidence", stages)
        self.assertLessEqual(len(compact["chat_history"]), 8)
        self.assertLessEqual(len(compact["knowledge_evidence"]), 8)
        self.assertEqual(len(context["chat_history"]), 20)

    def test_planner_projection_preserves_prompt_keys_and_active_upload_metadata(self):
        state = {
            "user_query": "Continue",
            "turn_input_type": "text_query",
            "session_upload_event_ids": [],
            "collection_id": "app-1",
            "chat_history": [{"role": "user", "content": str(index)} for index in range(12)],
            "session_uploads": [
                {"id": "upload-1", "filename": "a.md", "mime_type": "text/markdown", "text_content": "secret", "file_path": "private"},
                {"id": "upload-2", "filename": "b.md", "text_content": "other"},
            ],
            "session_execution_state": {"active_session_upload_ids": ["upload-1"], "chat_summary": {"decisions": ["Use A"]}},
            "config_json": {"goals": ["help"], "safety_rules": ["cite"], "large_unused": "x" * 1000},
            "adapter_json": {"intent_overrides": [{"alias_intent": "qa"}], "large_unused": "x" * 1000},
            "template_registry": {"intent_categories": ["qa"], "templates": [{"id": "t1", "title": "Answer", "body": "x" * 1000}]},
        }
        result = build_planner_context(state)
        self.assertEqual(
            set(result),
            {"user_query", "turn_input_type", "session_upload_event_ids", "chat_history", "session_uploads", "app_id", "collection_id", "config_json", "adapter_json", "template_registry"},
        )
        self.assertEqual(result["session_uploads"][0]["id"], "upload-1")
        self.assertNotIn("text_content", result["session_uploads"][0])
        self.assertNotIn("large_unused", result["config_json"])
        self.assertLessEqual(len(result["chat_history"]), 9)  # summary plus four turns

    def test_planner_and_answer_history_exclude_persisted_turn_metadata(self):
        history = [
            {
                "id": f"message-{index}",
                "session_id": "session-1",
                "role": "user" if index % 2 == 0 else "assistant",
                "content": f"Message {index}",
                "citations": [{"docId": "doc-1"}],
                "retrievalSummary": {
                    "task_model_diagnostics": {"payload": "x" * 10_000},
                    "session_execution_state": {"payload": "y" * 5_000},
                },
                "created_at": "2026-07-24T00:00:00Z",
            }
            for index in range(6)
        ]
        state = {
            "user_query": "Continue",
            "turn_input_type": "text_query",
            "collection_id": "app-1",
            "chat_history": history,
            "session_execution_state": {
                "chat_summary": {"assistant_conclusions": ["Earlier conclusion"]}
            },
        }

        planner_context = build_planner_context(state)
        answer_context = build_answer_context(state)

        for projected_history in (
            planner_context["chat_history"],
            answer_context["chat_history"],
        ):
            self.assertTrue(projected_history)
            self.assertTrue(
                all(set(message) == {"role", "content"} for message in projected_history)
            )
            serialized = str(projected_history)
            self.assertNotIn("task_model_diagnostics", serialized)
            self.assertNotIn("retrievalSummary", serialized)
            self.assertNotIn("session_execution_state", serialized)
            self.assertNotIn("created_at", serialized)

    def test_hybrid_projection_preserves_candidate_and_routing_identities(self):
        packet = {
            "candidates": {
                "workflows": [{"block_id": "wf-1", "block_type": "primary_workflow", "title": "Flow", "body_text": "x" * 1000}],
                "followup_modules": [{"block_id": "follow-1", "title": "Follow", "steps": [{"step_id": "s1", "title": "Step"}]}],
            },
            "routing_rules": [{"rule_id": "r1", "target_scope_id": "wf-1", "expression": "when asked"}],
            "required_output": {"select_target_scope": True},
        }
        result = compact_hybrid_decision_packet(packet)
        self.assertEqual(result["candidates"]["workflows"][0]["block_id"], "wf-1")
        self.assertEqual(result["candidates"]["followup_modules"][0]["block_id"], "follow-1")
        self.assertEqual(result["routing_rules"][0]["rule_id"], "r1")
        self.assertNotIn("body_text", result["candidates"]["workflows"][0])

    def test_answer_projection_retains_required_keys_and_active_state(self):
        required = {
            "user_query", "chat_history", "planner_output", "evidence_analysis", "compressed_evidence", "prepared_inputs",
            "instruction_evidence", "selected_instruction_block", "selected_instruction_block_text", "instruction_resource_load_plan",
            "instruction_resource_context", "template_resource_load_plan", "template_resource_context", "global_instruction_context",
            "knowledge_evidence", "template_evidence", "session_upload_evidence", "adapter_json", "config_json", "template_registry",
            "turn_execution_plan", "turn_action_plan", "session_execution_state", "presentation_policy", "visible_outputs", "hidden_outputs",
            "execution_artifacts",
        }
        context = {key: {} for key in required}
        context.update(
            {
                "chat_history": [{"role": "user", "content": str(index)} for index in range(20)],
                "knowledge_evidence": [{"doc_id": "d1", "title": "Doc", "snippet": "fact", "score": 0.9, "location": "p1"}],
                "session_upload_evidence": [{"doc_id": "u1", "filename": "draft.md", "snippet": "draft", "score": 1.0}],
                "session_execution_state": {"active_workflow": "wf", "active_step_scope_id": "step-1", "active_session_upload_ids": ["u1"]},
                "selected_instruction_block": {"block_id": "step-1", "title": "Active Step"},
                "selected_instruction_block_text": "## Active Step\nDo all steps.\n\n## Safety\nNever fabricate.",
                "config_json": {"style_rules": ["concise"], "safety_rules": ["cite"], "unused": "x" * 1000},
                "adapter_json": {"llm_guardrails_append": ["no leak"], "unused": "x" * 1000},
                "template_registry": {"llm_system_prompt": "Use headings", "unused": "x" * 1000},
                "hidden_outputs": [{"id": "hidden-1"}],
                "assembly_state": {},
            }
        )
        result = build_answer_context(context)
        self.assertTrue(required.issubset(result))
        self.assertEqual(result["session_execution_state"]["active_step_scope_id"], "step-1")
        self.assertEqual(result["knowledge_evidence"][0]["doc_id"], "d1")
        self.assertEqual(result["session_upload_evidence"][0]["doc_id"], "u1")
        self.assertEqual(result["hidden_outputs"], [])
        self.assertNotIn("unused", result["config_json"])
        self.assertLessEqual(len(result["chat_history"]), 12)

    def test_answer_projection_drops_upload_evidence_without_active_upload(self):
        result = build_answer_context({"session_upload_evidence": [{"doc_id": "u1", "title": "File"}], "session_execution_state": {}})
        self.assertEqual(result["session_upload_evidence"], [])

    def test_answer_projection_deduplicates_evidence_inside_prepared_inputs(self):
        result = build_answer_context(
            {
                "knowledge_evidence": [{"doc_id": "d1", "title": "Doc", "snippet": "fact"}],
                "session_upload_evidence": [{"doc_id": "u1", "filename": "draft.md", "snippet": "draft"}],
                "session_execution_state": {"active_session_upload_ids": ["u1"]},
                "prepared_inputs": {
                    "knowledge_evidence": [{"doc_id": "d1", "title": "Doc", "snippet": "fact"}],
                    "session_upload_evidence": [{"doc_id": "u1", "filename": "draft.md", "snippet": "draft"}],
                    "resource_requests": [{"resource_id": "r1", "kind": "knowledge"}],
                    "active_binding_ids": ["binding-1"],
                    "artifact_gate_status": "ready",
                    "bundled_execution": True,
                    "turn_execution_plan": {"turn_intent": "answer"},
                },
            }
        )

        self.assertEqual(result["knowledge_evidence"][0]["doc_id"], "d1")
        self.assertEqual(result["session_upload_evidence"][0]["doc_id"], "u1")
        self.assertNotIn("knowledge_evidence", result["prepared_inputs"])
        self.assertNotIn("session_upload_evidence", result["prepared_inputs"])
        self.assertEqual(result["prepared_inputs"]["resource_requests"][0]["resource_id"], "r1")
        self.assertEqual(result["prepared_inputs"]["active_binding_ids"], ["binding-1"])
        self.assertEqual(result["prepared_inputs"]["artifact_gate_status"], "ready")
        self.assertTrue(result["prepared_inputs"]["bundled_execution"])
        self.assertEqual(result["prepared_inputs"]["turn_execution_plan"]["turn_intent"], "answer")

    def test_evidence_assessment_requires_identity_score_and_unambiguous_match(self):
        sufficient = deterministic_evidence_assessment(
            ["author"],
            [{"doc_id": "d1", "title": "Profile", "score": 0.8, "metadata": {"info_type": "author"}, "snippet": "Author: Ada"}],
        )
        self.assertTrue(sufficient["sufficient"])
        low = deterministic_evidence_assessment(
            ["author"],
            [{"doc_id": "d1", "title": "Profile", "score": 0.1, "metadata": {"info_type": "author"}}],
        )
        self.assertFalse(low["sufficient"])
        missing_identity = deterministic_evidence_assessment(["author"], [{"snippet": "author Ada", "score": 0.8}])
        self.assertFalse(missing_identity["sufficient"])

    def test_evidence_assessment_detects_conflict_and_broad_text_only_ambiguity(self):
        conflict = deterministic_evidence_assessment(
            ["approved"],
            [
                {"doc_id": "d1", "title": "A", "score": 0.8, "metadata": {"info_type": "approved"}, "snippet": "approved"},
                {"doc_id": "d2", "title": "B", "score": 0.8, "metadata": {"info_type": "approved"}, "snippet": "not approved"},
            ],
        )
        self.assertTrue(conflict["conflicting"])
        self.assertFalse(conflict["sufficient"])
        broad = deterministic_evidence_assessment(["fact"], [{"doc_id": "d1", "title": "A fact", "score": 0.8}])
        self.assertTrue(broad["ambiguous"])

    def test_summary_contains_real_current_turn_and_workflow_state(self):
        summary = build_or_refresh_chat_summary(
            existing_summary=None,
            prior_history=[{"role": "user", "content": "I prefer concise answers"}, {"role": "assistant", "content": "Noted."}],
            current_user_message="What is next?",
            current_answer={"content": "Proceed to observation.", "citations": [{"docId": "d1"}]},
            session_execution_state={
                "active_workflow": "bible-study",
                "active_step_scope_id": "observation",
                "clarification_gate_status": {"filled_slots_map": {"passage": "John 1"}},
                "output_artifact_targets": ["study-notes"],
            },
        )
        self.assertIn("I prefer concise answers", summary["user_decisions_constraints"])
        self.assertIn("Proceed to observation.", summary["assistant_conclusions"])
        self.assertIn("What is next?", summary["unresolved_questions"])
        self.assertEqual(summary["active_workflow_state"]["active_step_scope_id"], "observation")
        self.assertEqual(summary["filled_slots"]["passage"], "John 1")
        self.assertIn("d1", summary["recent_citation_ids"])


if __name__ == "__main__":
    unittest.main()
