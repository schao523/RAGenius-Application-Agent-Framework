import os
import unittest
from unittest import mock

from backend.app import chat_service
from workflows.nodes import answer, planner


def _planner_output(query):
    return {
        "intentType": "qa",
        "confidence": 0.9,
        "steps": [{"id": "1", "title": "Retrieve", "goal": "Answer"}],
        "infoTypes": ["fact"],
        "retrievalPlan": {"query_text": query, "top_k": 3, "filters": {"app_id": "app-1"}},
        "systemInstructionSummary": {"fromConfigPdf": [], "fromAdapter": [], "fromTemplate": []},
        "normalizedQuery": query,
        "contextualQuery": query,
    }


class _EchoGraph:
    def __init__(self, assertion):
        self.assertion = assertion

    def invoke(self, state):
        self.assertion(state)
        result = dict(state)
        result["final_answer"] = {"content": "ok", "citations": [], "missing_infoTypes": []}
        return result


class LlmContextOptimizationIntegrationTests(unittest.TestCase):
    def _planner_state(self):
        return {
            "user_query": "Who is Jesus?",
            "turn_input_type": "text_query",
            "pending_upload_analysis": False,
            "session_upload_event_ids": [],
            "collection_id": "app-1",
            "chat_history": [],
            "session_uploads": [],
            "config_json": {"goals": ["answer"], "safety_rules": ["cite"], "unused": "x" * 5000},
            "adapter_json": {"intent_overrides": [], "unused": "x" * 5000},
            "template_registry": {"intent_categories": ["qa"], "unused": "x" * 5000},
            "_context_optimization_eligible": True,
            "_context_optimization_mode": "diagnostic",
        }

    def test_diagnostic_planner_sends_full_and_measures_smaller_candidate(self):
        state = self._planner_state()
        captured = {}

        def llm(_prompt, _tools, context):
            captured.update(context)
            return _planner_output(state["user_query"])

        planner._call_planner(llm, "prompt", state)
        self.assertIn("unused", captured["config_json"])
        call = state["_turn_token_accounting"]["calls"][0]
        self.assertGreater(call["actual_full_tokens"], call["compact_candidate_tokens"])
        self.assertEqual(call["actual_outbound_tokens"], call["actual_full_tokens"])

    def test_compact_planner_sends_projection(self):
        state = self._planner_state()
        state["_context_optimization_mode"] = "compact"
        captured = {}
        planner._call_planner(lambda _p, _t, context: captured.update(context) or _planner_output(state["user_query"]), "prompt", state)
        self.assertNotIn("unused", captured["config_json"])
        self.assertEqual(state["_turn_token_accounting"]["calls"][0]["context_mode"], "compact")

    def test_ineligible_upload_turn_sends_full_context_even_in_compact_mode(self):
        state = self._planner_state()
        state.update(
            {
                "turn_input_type": "session_upload",
                "pending_upload_analysis": True,
                "session_upload_event_ids": ["u1"],
                "session_uploads": [{"id": "u1", "filename": "draft.md", "text_content": "full upload"}],
                "_context_optimization_eligible": False,
                "_context_optimization_mode": "compact",
            }
        )
        captured = {}
        planner._call_planner(lambda _p, _t, context: captured.update(context) or _planner_output(state["user_query"]), "prompt", state)
        self.assertEqual(captured["session_uploads"][0]["text_content"], "full upload")
        self.assertEqual(state["_turn_token_accounting"]["calls"][0]["context_mode"], "full")

    def test_answer_compact_context_keeps_schema_and_citation_identity(self):
        state = {
            "user_query": "answer",
            "turn_input_type": "text_query",
            "planner_output": {},
            "evidence_analysis": {},
            "compressed_knowledge_evidence": [{"doc_id": "d1", "title": "Doc", "snippet": "fact", "score": 0.9}],
            "session_execution_state": {},
            "config_json": {"style_rules": ["brief"], "unused": "x" * 5000},
            "adapter_json": {},
            "template_registry": {},
            "_context_optimization_eligible": True,
            "_context_optimization_mode": "compact",
        }
        captured = {}

        def llm(_prompt, _tools, context):
            captured.update(context)
            return {"content": "answer", "citations": [{"docId": "d1", "title": "Doc", "snippet": "fact", "score": 0.9}], "missing_infoTypes": []}

        out = answer.run(state, llm_answer=llm)
        self.assertEqual(out["final_answer"]["content"], "answer")
        self.assertEqual(captured["knowledge_evidence"][0]["doc_id"], "d1")
        self.assertNotIn("unused", captured["config_json"])

    def test_pipeline_sets_one_eligibility_decision_and_exposes_diagnostics(self):
        def assertion(state):
            self.assertTrue(state["_context_optimization_eligible"])
            state["_context_optimization_diagnostics"] = {"calls": [{"task": "planner"}]}
            state["_turn_token_accounting"] = {"call_count": 1, "turn_estimated_outbound_tokens": 10}

        with mock.patch.dict(os.environ, {"RAGENIUS_LLM_CONTEXT_OPTIMIZATION": "1", "RAGENIUS_LLM_CONTEXT_OPTIMIZATION_MODE": "diagnostic"}, clear=False):
            with mock.patch.object(chat_service, "_graph", return_value=_EchoGraph(assertion)):
                response = chat_service.run_chat_pipeline(
                    {"turn_input_type": "text_query", "pending_upload_analysis": False, "session_upload_event_ids": [], "user_query": "hello"},
                    session_repo=object(), chat_repo=object(), planner_repo=object(), retrieval_repo=object(),
                    llm_planner=lambda *_: {}, llm_answer=lambda *_: {},
                )
        self.assertEqual(response["task_model_diagnostics"]["turn_token_accounting"]["call_count"], 1)


if __name__ == "__main__":
    unittest.main()
