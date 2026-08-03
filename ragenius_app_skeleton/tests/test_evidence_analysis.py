import unittest
from unittest import mock

from workflows.nodes import evidence_analysis


class EvidenceAnalysisTests(unittest.TestCase):
    def test_deterministic_info_type_comparison(self):
        state = {
            "planner_output": {"infoTypes": ["fact", "risk"]},
            "compressed_evidence": [
                {"doc_id": "d1", "title": "Doc", "snippet": "Contains fact details", "score": 0.9, "metadata": {}}
            ],
        }
        out = evidence_analysis.run(state)
        analysis = out["evidence_analysis"]
        self.assertEqual(analysis["infoTypes_with_evidence"], ["fact"])
        self.assertEqual(analysis["infoTypes_missing"], ["risk"])

    def test_llm_path_uses_prompt_and_tools(self):
        state = {
            "planner_output": {"infoTypes": ["fact"]},
            "compressed_evidence": [{"doc_id": "d1", "title": "Doc", "snippet": "x", "score": 0.7, "metadata": {}}],
        }
        calls = {"count": 0}

        def llm(prompt, tools, context):
            calls["count"] += 1
            self.assertTrue(prompt)
            # Optional tool may or may not exist; contract should still call with list.
            self.assertIsInstance(tools, list)
            self.assertEqual(context["infoTypes"], ["fact"])
            return {
                "infoTypes_with_evidence": ["fact"],
                "infoTypes_missing": [],
                "evidence_summary": ["fact: present"],
            }

        out = evidence_analysis.run(state, llm_evidence_analysis=llm)
        self.assertEqual(calls["count"], 1)
        self.assertEqual(out["evidence_analysis"]["infoTypes_missing"], [])

    def test_llm_runtime_error_falls_back_to_deterministic_analysis(self):
        state = {
            "planner_output": {"infoTypes": ["fact", "risk"]},
            "compressed_evidence": [
                {"doc_id": "d1", "title": "Doc", "snippet": "Contains fact details", "score": 0.9, "metadata": {}}
            ],
        }

        def llm(_prompt, _tools, _context):
            raise RuntimeError("LLM HTTP error 402: Insufficient Balance")

        out = evidence_analysis.run(state, llm_evidence_analysis=llm)
        analysis = out["evidence_analysis"]
        self.assertEqual(analysis["infoTypes_with_evidence"], ["fact"])
        self.assertEqual(analysis["infoTypes_missing"], ["risk"])
        self.assertTrue(any("llm_fallback:" in item for item in analysis["evidence_summary"]))

    def test_prefers_knowledge_evidence_for_grounding_analysis(self):
        state = {
            "planner_output": {"infoTypes": ["fact"]},
            "compressed_instruction_evidence": [
                {"doc_id": "i1", "title": "Guide", "snippet": "fact guidance only", "score": 0.9, "metadata": {}}
            ],
            "compressed_knowledge_evidence": [
                {"doc_id": "k1", "title": "Doc", "snippet": "No relevant grounding here", "score": 0.7, "metadata": {}}
            ],
        }
        out = evidence_analysis.run(state)
        self.assertEqual(out["evidence_analysis"]["infoTypes_with_evidence"], [])
        self.assertEqual(out["evidence_analysis"]["infoTypes_missing"], ["fact"])

    def test_guide_turn_with_selected_instruction_block_does_not_require_grounding(self):
        state = {
            "planner_output": {"infoTypes": ["fact"]},
            "turn_action_plan": {"action_type": "guide"},
            "selected_instruction_block_text": "好的，我們一起用歸納釋經法查考經文。請問想從哪一段開始？",
            "compressed_knowledge_evidence": [],
            "compressed_evidence": [],
        }
        out = evidence_analysis.run(state)
        self.assertEqual(out["evidence_analysis"]["infoTypes_missing"], [])
        self.assertEqual(out["evidence_analysis"]["evidence_summary"], ["instruction_block_guided_turn"])

    def test_auto_skips_llm_only_for_sufficient_non_conflicting_metadata(self):
        state = {
            "planner_output": {"infoTypes": ["author"]},
            "compressed_evidence": [
                {"doc_id": "d1", "title": "Profile", "snippet": "Author Ada", "score": 0.8, "metadata": {"info_type": "author"}}
            ],
        }
        llm = mock.Mock(side_effect=AssertionError("auto should use deterministic coverage"))
        with mock.patch.dict("os.environ", {"RAGENIUS_LLM_EVIDENCE_ANALYSIS_MODE": "auto"}, clear=False):
            out = evidence_analysis.run(state, llm_evidence_analysis=llm)
        llm.assert_not_called()
        self.assertEqual(out["evidence_analysis"]["infoTypes_with_evidence"], ["author"])

    def test_deterministic_mode_never_calls_llm(self):
        state = {
            "planner_output": {"infoTypes": ["fact"]},
            "compressed_evidence": [{"doc_id": "d1", "title": "Doc", "snippet": "fact", "score": 0.8}],
        }
        llm = mock.Mock(side_effect=AssertionError("deterministic mode must not call LLM"))
        with mock.patch.dict("os.environ", {"RAGENIUS_LLM_EVIDENCE_ANALYSIS_MODE": "deterministic"}, clear=False):
            evidence_analysis.run(state, llm_evidence_analysis=llm)
        llm.assert_not_called()

    def test_llm_required_calls_even_when_deterministic_coverage_is_sufficient(self):
        state = {
            "planner_output": {"infoTypes": ["author"]},
            "compressed_evidence": [
                {"doc_id": "d1", "title": "Profile", "snippet": "Author Ada", "score": 0.8, "metadata": {"info_type": "author"}}
            ],
        }
        llm = mock.Mock(return_value={"infoTypes_with_evidence": ["author"], "infoTypes_missing": [], "evidence_summary": ["ok"]})
        with mock.patch.dict("os.environ", {"RAGENIUS_LLM_EVIDENCE_ANALYSIS_MODE": "llm_required"}, clear=False):
            evidence_analysis.run(state, llm_evidence_analysis=llm)
        llm.assert_called_once()

    def test_auto_calls_llm_for_conflicting_evidence(self):
        state = {
            "planner_output": {"infoTypes": ["approved"]},
            "compressed_evidence": [
                {"doc_id": "d1", "title": "A", "snippet": "approved", "score": 0.8, "metadata": {"info_type": "approved"}},
                {"doc_id": "d2", "title": "B", "snippet": "not approved", "score": 0.8, "metadata": {"info_type": "approved"}},
            ],
        }
        llm = mock.Mock(return_value={"infoTypes_with_evidence": [], "infoTypes_missing": ["approved"], "evidence_summary": ["conflict"]})
        with mock.patch.dict("os.environ", {"RAGENIUS_LLM_EVIDENCE_ANALYSIS_MODE": "auto"}, clear=False):
            evidence_analysis.run(state, llm_evidence_analysis=llm)
        llm.assert_called_once()

    def test_llm_required_without_model_records_deterministic_fallback_reason(self):
        state = {
            "planner_output": {"infoTypes": ["fact"]},
            "compressed_evidence": [{"doc_id": "d1", "title": "Doc", "snippet": "fact", "score": 0.8}],
        }
        with mock.patch.dict("os.environ", {"RAGENIUS_LLM_EVIDENCE_ANALYSIS_MODE": "llm_required"}, clear=False):
            evidence_analysis.run(state)
        self.assertEqual(state["_evidence_analysis_policy"]["fallback_reason"], "evidence_analysis_model_unavailable")


if __name__ == "__main__":
    unittest.main()
