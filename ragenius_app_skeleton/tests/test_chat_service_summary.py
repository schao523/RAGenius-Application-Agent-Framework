import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.chat_service import _build_retrieval_summary, _bundled_execution_summary


class ChatServiceSummaryTests(unittest.TestCase):
    def test_direct_instruction_and_template_contexts_surface_as_loaded_sources(self):
        result = {
            "raw_evidence": [
                {
                    "doc_id": "doc-knowledge-1",
                    "title": "Micah Notes",
                    "retrieval_domain": "knowledge_source",
                }
            ],
            "retrieval_debug_trace": {
                "route": {},
                "domains": {
                    "instruction_source": {"route": {}, "executed_queries": [], "attempt_count": 0},
                    "knowledge_source": {"route": {}, "executed_queries": [], "attempt_count": 1},
                    "output_template": {"route": {}, "executed_queries": [], "attempt_count": 0},
                    "session_upload": {"route": {}, "executed_queries": [], "attempt_count": 0},
                },
            },
            "turn_execution_plan": {
                "resource_requests": [
                    {"filename": "Ministry_Prompt_Framework.md", "resource_role": "instruction_source"},
                    {"filename": "delivery_package_template.md", "resource_role": "output_template"},
                ],
                "actions": [],
            },
            "session_execution_state": {},
            "instruction_resource_context": [
                {
                    "filename": "Ministry_Prompt_Framework.md",
                    "load_strategy": "direct_load",
                    "source_kind": "markdown",
                    "section_titles": ["Generate the Ministry Prompt Draft"],
                }
            ],
            "template_resource_context": [
                {
                    "filename": "delivery_package_template.md",
                    "load_strategy": "direct_load",
                    "source_kind": "markdown",
                    "section_titles": ["Finalize the Delivery Package"],
                }
            ],
        }

        summary = _build_retrieval_summary(result, {"citations": []})

        self.assertEqual(summary["knowledge_retrieved_count"], 1)
        self.assertEqual(summary["instruction_retrieved_count"], 1)
        self.assertEqual(summary["template_retrieved_count"], 1)
        self.assertIn("Ministry_Prompt_Framework.md", summary["instruction_titles"])
        self.assertIn("delivery_package_template.md", summary["template_titles"])
        self.assertEqual(summary["retrieved_count"], 3)
        self.assertGreaterEqual(summary["source_count"], 3)

    def test_bundled_execution_summary_exposes_bundled_chat_state(self):
        summary = _bundled_execution_summary(
            {
                "active_execution_mode": "bundled",
                "active_bundled_step_ids": [
                    "step:interaction_logic_execution_flow:2",
                    "step:interaction_logic_execution_flow:3",
                ],
                "bundled_entry_step_id": "step:interaction_logic_execution_flow:2",
                "bundled_execution_completed": False,
                "active_step_scope_id": "step:interaction_logic_execution_flow:2",
                "active_step_scope": {
                    "scope_id": "step:interaction_logic_execution_flow:2",
                    "title": "Generate the Ministry Prompt Draft",
                },
            }
        )

        self.assertTrue(summary["enabled"])
        self.assertEqual(summary["active_execution_mode"], "bundled")
        self.assertEqual(
            summary["active_bundled_step_ids"],
            [
                "step:interaction_logic_execution_flow:2",
                "step:interaction_logic_execution_flow:3",
            ],
        )
        self.assertEqual(summary["bundled_entry_step_id"], "step:interaction_logic_execution_flow:2")
        self.assertEqual(summary["active_step_scope_id"], "step:interaction_logic_execution_flow:2")
        self.assertEqual(summary["active_step_scope_title"], "Generate the Ministry Prompt Draft")

    def test_retrieval_summary_surfaces_task_model_diagnostics(self):
        result = {
            "raw_evidence": [],
            "retrieval_debug_trace": {"route": {}, "domains": {}},
            "turn_execution_plan": {"actions": []},
            "session_execution_state": {},
            "task_model_diagnostics": {
                "configured_task_models": {
                    "planner": {
                        "provider": "deepseek",
                        "model": "deepseek-reasoner",
                        "temperature": 0.1,
                    },
                    "answer_generation": {
                        "provider": "deepseek",
                        "model": "deepseek-chat",
                        "temperature": 0.2,
                    },
                },
                "selected_task_models": {
                    "planner": {
                        "provider": "deepseek",
                        "model": "deepseek-reasoner",
                        "temperature": 0.1,
                        "selected_source": "builder_task_model",
                    },
                    "answer_generation": {
                        "provider": "deepseek",
                        "model": "deepseek-chat",
                        "temperature": 0.2,
                        "selected_source": "builder_task_model",
                    },
                },
            },
        }

        summary = _build_retrieval_summary(result, {"citations": []})

        self.assertIn("task_model_diagnostics", summary)
        self.assertEqual(
            summary["task_model_diagnostics"]["configured_task_models"]["planner"]["model"],
            "deepseek-reasoner",
        )
        self.assertEqual(
            summary["task_model_diagnostics"]["selected_task_models"]["answer_generation"]["model"],
            "deepseek-chat",
        )


if __name__ == "__main__":
    unittest.main()
