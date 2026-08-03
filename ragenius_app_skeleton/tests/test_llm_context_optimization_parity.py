import copy
import unittest

from workflows.nodes import answer, evidence_analysis, planner


def _planner_result(query):
    return {
        "intentType": "qa",
        "confidence": 0.95,
        "steps": [{"id": "step-1", "title": "Answer", "goal": "Grounded answer"}],
        "infoTypes": ["fact"],
        "retrievalPlan": {"query_text": query, "top_k": 3, "filters": {"app_id": "app-1"}},
        "systemInstructionSummary": {"fromConfigPdf": [], "fromAdapter": [], "fromTemplate": []},
        "normalizedQuery": query,
        "contextualQuery": query,
    }


def _rich_state(mode):
    history = []
    for index in range(8):
        history.extend(
            [
                {"role": "user", "content": f"Question {index} " + "q" * 250},
                {"role": "assistant", "content": f"Answer {index} " + "a" * 250},
            ]
        )
    evidence = [
        {
            "doc_id": f"doc-{index}",
            "title": f"Source {index}",
            "snippet": "fact " + "e" * 1200,
            "score": 0.9 - index / 100,
            "location": f"p{index}",
            "metadata": {"info_type": "fact", "unused": "m" * 1000},
            "retrieval_domain": "knowledge_source",
        }
        for index in range(10)
    ]
    return {
        "user_query": "Give a concise grounded answer",
        "turn_input_type": "text_query",
        "pending_upload_analysis": False,
        "session_upload_event_ids": [],
        "collection_id": "app-1",
        "chat_history": history,
        "session_uploads": [],
        "config_json": {
            "goals": ["answer"], "style_rules": ["concise"], "safety_rules": ["cite facts"],
            "step_skeletons": [{"id": "step-1", "title": "Answer"}], "unused_compiler_snapshot": "c" * 9000,
        },
        "adapter_json": {
            "intent_overrides": [{"alias_intent": "qa", "triggers": ["answer"]}],
            "retrieval_defaults": {"top_k_range": [1, 8]}, "unused_runtime_projection": "d" * 8000,
        },
        "template_registry": {
            "intent_categories": ["qa"],
            "workflows": [
                {"block_id": "church-ministry", "block_type": "primary_workflow", "title": "Church Ministry", "body_text": "w" * 5000},
                {"block_id": "grow-with-children", "block_type": "primary_workflow", "title": "與孩子一起成長", "body_text": "w" * 5000},
            ],
            "unused_snapshot": "t" * 8000,
            "compiled_instruction_understanding": {
                "hybrid_instruction_runtime_model": {
                    "instruction_service_blocks": [
                        {"block_id": "church-ministry", "block_type": "primary_workflow", "title": "Church Ministry", "body_text": "w" * 5000},
                        {"block_id": "grow-with-children", "block_type": "primary_workflow", "title": "與孩子一起成長", "body_text": "w" * 5000},
                    ]
                }
            },
        },
        "planner_output": _planner_result("Give a concise grounded answer"),
        "compressed_evidence": copy.deepcopy(evidence),
        "compressed_knowledge_evidence": copy.deepcopy(evidence),
        "compressed_instruction_evidence": [],
        "compressed_template_evidence": [],
        "compressed_session_upload_evidence": [],
        "evidence_analysis": {"infoTypes_with_evidence": ["fact"], "infoTypes_missing": [], "evidence_summary": ["fact present"]},
        "prepared_inputs": {"knowledge_evidence": copy.deepcopy(evidence), "resource_requests": [], "turn_execution_plan": {"turn_intent": "answer"}},
        "selected_instruction_block": {"block_id": "step-1", "title": "Active Step"},
        "selected_instruction_block_text": "## Active Step\nAnswer concisely.\n\n## Safety Rules\nCite every factual claim.",
        "global_instruction_context": {"safety_rules": ["cite facts"]},
        "turn_execution_plan": {"turn_intent": "answer", "active_step_scope_id": "step-1"},
        "turn_action_plan": {"action_type": "answer"},
        "session_execution_state": {"active_workflow": "church-ministry", "active_step_scope_id": "step-1"},
        "presentation_policy": {"mode": "answer"},
        "visible_outputs": [], "hidden_outputs": [], "execution_artifacts": [],
        "_context_optimization_eligible": True,
        "_context_optimization_mode": mode,
    }


class LlmContextOptimizationParityTests(unittest.TestCase):
    def _execute(self, mode):
        state = _rich_state(mode)

        planner_output = planner._call_planner(
            lambda _prompt, _tools, context: _planner_result(context["user_query"]),
            "planner prompt",
            state,
        )
        state["planner_output"] = planner_output

        evidence_analysis.run(
            state,
            llm_evidence_analysis=lambda _prompt, _tools, _context: {
                "infoTypes_with_evidence": ["fact"], "infoTypes_missing": [], "evidence_summary": ["fact present"]
            },
        )

        answer.run(
            state,
            llm_answer=lambda _prompt, _tools, context: {
                "content": "Grounded answer.",
                "citations": [{"docId": context["knowledge_evidence"][0]["doc_id"], "title": context["knowledge_evidence"][0]["title"], "snippet": "fact", "score": 0.9}],
                "missing_infoTypes": [],
            },
        )
        return state

    def test_full_and_compact_modes_preserve_outputs_and_save_at_least_40_percent(self):
        full = self._execute("diagnostic")
        compact = self._execute("compact")

        self.assertEqual(compact["planner_output"], full["planner_output"])
        self.assertEqual(compact["evidence_analysis"], full["evidence_analysis"])
        self.assertEqual(compact["final_answer"], full["final_answer"])
        self.assertEqual(compact["session_execution_state"], full["session_execution_state"])

        accounting = compact["_turn_token_accounting"]
        self.assertGreaterEqual(accounting["turn_estimated_saving_percent"], 40.0)
        self.assertLess(accounting["turn_compact_candidate_tokens"], accounting["turn_actual_full_tokens"])

    def test_hybrid_compaction_preserves_protected_application_ids(self):
        packet = planner._build_hybrid_turn_decision_packet(_rich_state("compact"))
        captured = {}
        state = _rich_state("compact")
        planner._call_hybrid_planner_shadow(
            lambda _prompt, _tools, context: captured.update(context) or {"intent": "qa"},
            packet,
            state,
        )
        serialized = str(captured)
        self.assertIn("church-ministry", serialized)
        self.assertIn("grow-with-children", serialized)


if __name__ == "__main__":
    unittest.main()
