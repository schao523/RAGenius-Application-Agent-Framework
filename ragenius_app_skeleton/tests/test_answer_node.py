import unittest

from jsonschema.exceptions import ValidationError

from workflows.nodes import answer


def valid_final_answer(missing=None):
    return {
        "content": "Answer content",
        "citations": [
            {
                "docId": "d1",
                "title": "Doc 1",
                "snippet": "Evidence",
                "score": 0.9,
                "location": None,
                "version": None,
            }
        ],
        "missing_infoTypes": missing or [],
    }


def base_state():
    return {
        "planner_output": {"infoTypes": ["fact"]},
        "evidence_analysis": {"infoTypes_missing": []},
        "compressed_evidence": [],
        "compressed_instruction_evidence": [],
        "compressed_knowledge_evidence": [],
        "compressed_template_evidence": [],
        "compressed_session_upload_evidence": [],
        "adapter_json": {},
        "config_json": {},
        "template_registry": {},
        "global_instruction_context": {},
        "prepared_inputs": {},
        "turn_execution_plan": {},
        "turn_action_plan": {},
        "session_execution_state": {},
        "presentation_policy": {},
        "visible_outputs": [],
        "hidden_outputs": [],
        "execution_artifacts": [],
    }


class AnswerNodeTests(unittest.TestCase):
    def test_answer_generation_happy_path(self):
        calls = {"n": 0}

        def llm(prompt, tools, context):
            calls["n"] += 1
            self.assertTrue(prompt)
            self.assertEqual(tools[0]["name"], "create_final_answer")
            self.assertIn("planner_output", context)
            self.assertIn("prepared_inputs", context)
            self.assertIn("turn_execution_plan", context)
            return valid_final_answer()

        out = answer.run(base_state(), llm_answer=llm)
        self.assertEqual(calls["n"], 1)
        self.assertIn("final_answer", out)

    def test_safe_answer_path_when_missing_info_types(self):
        calls = {"n": 0, "prompts": []}

        def llm(prompt, tools, context):
            _ = tools
            calls["n"] += 1
            calls["prompts"].append(prompt)
            if calls["n"] == 1:
                return valid_final_answer(missing=["risk"])
            self.assertIn("missing_infoTypes", context)
            return valid_final_answer(missing=[])

        out = answer.run(base_state(), llm_answer=llm)
        self.assertEqual(calls["n"], 2)
        self.assertEqual(out["final_answer"]["missing_infoTypes"], [])

    def test_raises_when_schema_invalid(self):
        def llm(_prompt, _tools, _context):
            return {"content": "bad"}

        with self.assertRaises(ValidationError):
            answer.run(base_state(), llm_answer=llm)

    def test_fills_empty_content_with_fallback(self):
        def llm(_prompt, _tools, _context):
            return {
                "content": "   ",
                "citations": [],
                "missing_infoTypes": [],
            }

        out = answer.run(base_state(), llm_answer=llm)
        self.assertTrue(out["final_answer"]["content"].strip())
        self.assertIn("No answer text was generated", out["final_answer"]["content"])

    def test_passes_instruction_and_knowledge_evidence_separately(self):
        state = base_state()
        state["compressed_instruction_evidence"] = [{"doc_id": "i1", "snippet": "Ask an observation question."}]
        state["compressed_knowledge_evidence"] = [{"doc_id": "k1", "snippet": "Jesus prays in John 17."}]
        state["compressed_template_evidence"] = [{"doc_id": "t1", "snippet": "Use headings: Observation, Meaning, Application."}]
        state["compressed_session_upload_evidence"] = [{"doc_id": "u1", "snippet": "Uploaded draft artifact."}]
        state["selected_instruction_block"] = {"block_id": "mode:bible_study", "title": "查考經文模式（Bible Study）"}
        state["selected_instruction_block_text"] = "好的，我們一起用歸納釋經法查考經文。請問想從哪一段開始？"
        state["instruction_resource_load_plan"] = [{"filename": "observation_guide.md", "load_strategy": "inline_full"}]
        state["instruction_resource_context"] = [
            {"filename": "observation_guide.md", "load_strategy": "inline_full", "content": "Ask 1-3 observation questions."}
        ]
        state["template_resource_load_plan"] = [{"filename": "answer_format_template.md", "load_strategy": "inline_full"}]
        state["template_resource_context"] = [
            {"filename": "answer_format_template.md", "load_strategy": "inline_full", "content": "Use headings: Observation, Meaning, Application."}
        ]
        state["prepared_inputs"] = {"resource_requests": [{"filename": "observation_guide.md"}]}
        state["turn_execution_plan"] = {"turn_intent": "answer_prior_questions"}
        state["hidden_outputs"] = [{"output_id": "notes", "content": "hidden"}]
        captured = {}

        def llm(prompt, _tools, context):
            captured["instruction_evidence"] = context["instruction_evidence"]
            captured["selected_instruction_block"] = context["selected_instruction_block"]
            captured["selected_instruction_block_text"] = context["selected_instruction_block_text"]
            captured["instruction_resource_load_plan"] = context["instruction_resource_load_plan"]
            captured["instruction_resource_context"] = context["instruction_resource_context"]
            captured["template_resource_load_plan"] = context["template_resource_load_plan"]
            captured["template_resource_context"] = context["template_resource_context"]
            captured["knowledge_evidence"] = context["knowledge_evidence"]
            captured["template_evidence"] = context["template_evidence"]
            captured["session_upload_evidence"] = context["session_upload_evidence"]
            captured["prepared_inputs"] = context["prepared_inputs"]
            captured["turn_execution_plan"] = context["turn_execution_plan"]
            captured["visible_outputs"] = context["visible_outputs"]
            captured["hidden_outputs"] = context["hidden_outputs"]
            captured["prompt"] = prompt
            return valid_final_answer()

        answer.run(state, llm_answer=llm)
        self.assertEqual(captured["instruction_evidence"][0]["doc_id"], "i1")
        self.assertEqual(captured["selected_instruction_block"]["block_id"], "mode:bible_study")
        self.assertIn("歸納釋經法", captured["selected_instruction_block_text"])
        self.assertEqual(captured["instruction_resource_load_plan"][0]["load_strategy"], "inline_full")
        self.assertEqual(captured["instruction_resource_context"][0]["filename"], "observation_guide.md")
        self.assertEqual(captured["template_resource_load_plan"][0]["filename"], "answer_format_template.md")
        self.assertEqual(captured["template_resource_context"][0]["filename"], "answer_format_template.md")
        self.assertEqual(captured["knowledge_evidence"][0]["doc_id"], "k1")
        self.assertEqual(captured["template_evidence"][0]["doc_id"], "t1")
        self.assertEqual(captured["session_upload_evidence"][0]["doc_id"], "u1")
        self.assertEqual(captured["prepared_inputs"]["resource_requests"][0]["filename"], "observation_guide.md")
        self.assertEqual(captured["turn_execution_plan"]["turn_intent"], "answer_prior_questions")
        self.assertEqual(captured["visible_outputs"], [])
        self.assertEqual(captured["hidden_outputs"][0]["output_id"], "notes")
        self.assertIn("instruction_evidence", captured["prompt"])
        self.assertIn("instruction_resource_context", captured["prompt"])
        self.assertIn("template_resource_context", captured["prompt"])
        self.assertIn("knowledge_evidence", captured["prompt"])
        self.assertIn("template_evidence", captured["prompt"])
        self.assertIn("session_upload_evidence", captured["prompt"])

    def test_fallback_prefers_knowledge_evidence_for_citations(self):
        state = base_state()
        state["compressed_instruction_evidence"] = [{"doc_id": "i1", "title": "Guide", "snippet": "Use observation prompts.", "score": 0.8}]
        state["compressed_knowledge_evidence"] = [{"doc_id": "k1", "title": "John 17", "snippet": "Jesus prayed for his disciples.", "score": 0.95}]

        def llm(_prompt, _tools, _context):
            raise RuntimeError("force fallback")

        out = answer.run(state, llm_answer=llm)
        self.assertEqual(out["final_answer"]["citations"][0]["docId"], "k1")
        self.assertEqual(out["final_answer"]["citations"][0]["title"], "John 17")

    def test_fallback_uses_session_upload_evidence_when_knowledge_missing(self):
        state = base_state()
        state["compressed_session_upload_evidence"] = [
            {"doc_id": "u1", "title": "artifact.md", "snippet": "Uploaded artifact body.", "score": 1.0}
        ]

        def llm(_prompt, _tools, _context):
            raise RuntimeError("force fallback")

        out = answer.run(state, llm_answer=llm)
        self.assertEqual(out["final_answer"]["citations"][0]["docId"], "u1")
        self.assertEqual(out["final_answer"]["citations"][0]["title"], "artifact.md")

    def test_guide_mode_block_only_turn_uses_direct_response_hint(self):
        state = base_state()
        state["selected_instruction_block"] = {
            "block_id": "mode:bible_study",
            "block_type": "mode",
            "response_hint": "「好的，我們一起用歸納釋經法查考經文。請問想從哪一段開始？」",
        }
        state["turn_action_plan"] = {
            "action_type": "guide",
            "response_style": {
                "use_instruction_block_only": True,
            },
        }

        def llm(_prompt, _tools, _context):
            raise AssertionError("LLM should not be called for direct block response")

        out = answer.run(state, llm_answer=llm)
        self.assertEqual(out["final_answer"]["content"], "好的，我們一起用歸納釋經法查考經文。請問想從哪一段開始？")
        self.assertEqual(out["final_answer"]["citations"], [])

    def test_visible_outputs_are_presented_without_llm(self):
        state = base_state()
        state["visible_outputs"] = [
            {
                "output_id": "draft_answer",
                "output_type": "user_visible_response",
                "visibility": "user_visible",
                "content": "Visible draft text",
            }
        ]

        def llm(_prompt, _tools, _context):
            raise AssertionError("LLM should not be called when visible outputs are already available")

        out = answer.run(state, llm_answer=llm)
        self.assertEqual(out["final_answer"]["content"], "Visible draft text")
        self.assertEqual(out["final_answer"]["citations"], [])
        self.assertEqual(out["answer_generation_meta"]["source"], "visible_outputs")

    def test_general_out_of_scope_turn_uses_direct_general_llm_context(self):
        state = base_state()
        state["user_query"] = "Explain Python dataclass vs pydantic"
        state["chat_history"] = [{"role": "user", "content": "Earlier app-scoped turn"}]
        state["turn_execution_plan"] = {"turn_intent": "general_out_of_scope_question"}
        state["global_instruction_context"] = {"role_summary": "Bible tutor"}
        state["compressed_knowledge_evidence"] = [{"doc_id": "k1", "snippet": "Should not be used"}]
        captured = {}

        def llm(prompt, _tools, context):
            captured["prompt"] = prompt
            captured["context"] = context
            return {
                "content": "Direct general answer",
                "citations": [],
                "missing_infoTypes": [],
            }

        out = answer.run(state, llm_answer=llm)
        self.assertEqual(out["final_answer"]["content"], "Direct general answer")
        self.assertEqual(out["answer_generation_meta"]["source"], "general_llm_direct")
        self.assertNotIn("planner_output", captured["context"])
        self.assertEqual(captured["context"]["user_query"], "Explain Python dataclass vs pydantic")
        self.assertIn("outside the scope", captured["prompt"])

    def test_appends_global_instruction_context_to_effective_system_prompt(self):
        state = base_state()
        state["global_instruction_context"] = {
            "role_summary": "你是一位專業聖經導師",
            "primary_objectives": ["循序漸進帶領學員查經"],
            "behavior_rules": ["每回合僅提出 1-3 個問題"],
        }
        captured = {}

        def llm(prompt, _tools, context):
            captured["prompt"] = prompt
            captured["context"] = context
            return valid_final_answer()

        answer.run(state, llm_answer=llm)
        self.assertIn("GLOBAL ALWAYS-ON APPLICATION INSTRUCTION CONTEXT", captured["prompt"])
        self.assertIn("role_summary", captured["prompt"])
        self.assertIn("你是一位專業聖經導師", captured["prompt"])
        self.assertEqual(captured["context"]["global_instruction_context"]["role_summary"], "你是一位專業聖經導師")

    def test_direct_instruction_block_sets_answer_source_metadata(self):
        state = base_state()
        state["selected_instruction_block"] = {
            "block_id": "mode:bible_study",
            "block_type": "mode",
            "response_hint": "Guide the user into the passage selection step.",
        }
        state["turn_action_plan"] = {
            "action_type": "guide",
            "response_style": {"use_instruction_block_only": True},
        }

        def llm(_prompt, _tools, _context):
            raise AssertionError("LLM should not be called for direct instruction answers")

        out = answer.run(state, llm_answer=llm)
        self.assertEqual(out["answer_generation_meta"]["source"], "direct_instruction_block")
        self.assertIsNone(out["answer_generation_meta"]["llm_error"])

    def test_visible_output_fallback_sets_answer_error_metadata(self):
        state = base_state()
        state["visible_outputs"] = [
            {
                "output_id": "draft_answer",
                "content": "Visible draft text",
            }
        ]

        def llm(_prompt, _tools, _context):
            raise AssertionError("LLM should not be called when visible outputs are already available")

        out = answer.run(state, llm_answer=llm)
        self.assertEqual(out["answer_generation_meta"]["source"], "visible_outputs")
        self.assertIsNone(out["answer_generation_meta"]["llm_error"])

    def test_generic_fallback_sets_answer_error_metadata(self):
        state = base_state()

        def llm(_prompt, _tools, _context):
            raise RuntimeError("boom")

        out = answer.run(state, llm_answer=llm)
        self.assertEqual(out["answer_generation_meta"]["source"], "fallback_generic")
        self.assertIn("RuntimeError: boom", out["answer_generation_meta"]["llm_error"])


if __name__ == "__main__":
    unittest.main()
