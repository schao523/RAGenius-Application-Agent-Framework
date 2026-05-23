import unittest

from workflows.executors import ExecutorRegistry
from workflows.nodes import execute_turn_plan


class ExecuteTurnPlanNodeTests(unittest.TestCase):
    def test_execute_turn_plan_creates_hidden_intermediate_output_and_updates_session_state(self):
        state = {
            "session_execution_state": {"execution_status": "guiding"},
            "chat_history": [{"role": "user", "content": "Help me study this passage"}],
            "turn_execution_plan": {
                "primary_scope": {"scope_id": "step:bible_study:1", "scope_type": "step"},
                "state_updates": {"active_scope_ids": ["step:bible_study:1"]},
                "actions": [
                    {
                        "action_id": "action:update_state",
                        "action_type": "update_session_state",
                        "target": "session_execution_state",
                        "output_key": "session_execution_state",
                        "visibility": "internal_only",
                        "params": {},
                    },
                    {
                        "action_id": "action:notes",
                        "action_type": "generate_intermediate_output",
                        "target": "observation_notes",
                        "output_key": "observation_notes",
                        "visibility": "internal_only",
                        "params": {
                            "output_type": "notes",
                            "content": "Learner noticed Paul's commands to Timothy.",
                            "structured_data": {"commands": ["teach", "encourage"]},
                        },
                    },
                ],
            },
        }

        out = execute_turn_plan.run(state)
        self.assertEqual(out["session_execution_state"]["active_scope_ids"], ["step:bible_study:1"])
        self.assertEqual(out["intermediate_outputs"][0]["output_id"], "observation_notes")
        self.assertEqual(out["intermediate_outputs"][0]["visibility"], "internal_only")
        self.assertEqual(out["intermediate_outputs"][0]["producer_scope_id"], "step:bible_study:1")
        self.assertEqual(out["intermediate_outputs"][0]["producer_turn_index"], 1)
        self.assertEqual(out["hidden_outputs"][0]["output_id"], "observation_notes")
        self.assertEqual(len(out["execution_artifacts"]), 2)

    def test_execute_turn_plan_creates_visible_output_when_visibility_is_user_visible(self):
        state = {
            "turn_execution_plan": {
                "actions": [
                    {
                        "action_id": "action:draft",
                        "action_type": "generate_intermediate_output",
                        "target": "draft_answer",
                        "output_key": "draft_answer",
                        "visibility": "user_visible",
                        "params": {
                            "output_type": "draft",
                            "content": "Visible draft text",
                        },
                    }
                ],
            },
        }

        out = execute_turn_plan.run(state)
        self.assertEqual(out["visible_outputs"][0]["output_id"], "draft_answer")
        self.assertEqual(out["visible_outputs"][0]["content"], "Visible draft text")
        self.assertEqual(out["intermediate_outputs"][0]["output_id"], "draft_answer")

    def test_execute_turn_plan_skips_unregistered_tool_but_records_artifact(self):
        state = {
            "turn_execution_plan": {
                "actions": [
                    {
                        "action_id": "action:tool",
                        "action_type": "invoke_tool",
                        "target": "missing_tool",
                        "visibility": "internal_only",
                        "params": {},
                    }
                ],
            },
        }

        out = execute_turn_plan.run(state)
        self.assertEqual(out["tool_results"][0]["artifact_type"], "tool_call_skipped")
        self.assertEqual(out["execution_artifacts"][0]["artifact_type"], "tool_call_skipped")

    def test_execute_turn_plan_applies_assembler_result_to_state_and_outputs(self):
        registry = ExecutorRegistry()

        def assemble(*, state, action):
            _ = (state, action)
            return {
                "assembly_state": {"target_output": "study_summary", "status": "assembled"},
                "visible_outputs": [
                    {
                        "output_id": "study_summary",
                        "output_type": "summary",
                        "visibility": "final_visible",
                        "content": "Final summary text",
                    }
                ],
            }

        registry.register_assembler("summary_assembler", assemble)
        state = {
            "_executor_registry": registry,
            "turn_execution_plan": {
                "actions": [
                    {
                        "action_id": "action:assemble",
                        "action_type": "assemble_output",
                        "target": "summary_assembler",
                        "visibility": "internal_only",
                        "params": {},
                    }
                ],
            },
        }

        out = execute_turn_plan.run(state)
        self.assertEqual(out["assembly_state"]["target_output"], "study_summary")
        self.assertEqual(out["visible_outputs"][0]["output_id"], "study_summary")
        self.assertEqual(out["intermediate_outputs"][0]["output_type"], "summary")
        self.assertEqual(out["execution_artifacts"][0]["artifact_type"], "assembly")

    def test_execute_turn_plan_applies_validator_result_and_records_tool_result(self):
        registry = ExecutorRegistry()

        def validate(*, state, action):
            _ = (state, action)
            return {
                "session_state_updates": {"validation_status": "passed"},
                "artifacts": [
                    {
                        "artifact_id": "artifact:validation:report",
                        "artifact_type": "validation_report",
                        "content": {"issues": 0},
                    }
                ],
            }

        registry.register_validator("basic_validator", validate)
        state = {
            "_executor_registry": registry,
            "turn_execution_plan": {
                "actions": [
                    {
                        "action_id": "action:validate",
                        "action_type": "validate_output",
                        "target": "basic_validator",
                        "visibility": "internal_only",
                        "params": {},
                    }
                ],
            },
        }

        out = execute_turn_plan.run(state)
        self.assertEqual(out["session_execution_state"]["validation_status"], "passed")
        self.assertEqual(out["tool_results"][0]["artifact_type"], "validation")
        artifact_types = [item["artifact_type"] for item in out["execution_artifacts"]]
        self.assertIn("validation", artifact_types)
        self.assertIn("validation_report", artifact_types)

    def test_execute_turn_plan_applies_structured_tool_outputs(self):
        registry = ExecutorRegistry()

        def run_tool(*, state, action):
            _ = (state, action)
            return {
                "intermediate_outputs": [
                    {
                        "output_id": "lookup_notes",
                        "output_type": "notes",
                        "content": "Lookup notes",
                        "structured_data": {"matches": 2},
                    }
                ],
                "visible_outputs": [
                    {
                        "output_id": "lookup_summary",
                        "output_type": "summary",
                        "visibility": "user_visible",
                        "content": "Lookup summary",
                    }
                ],
                "hidden_outputs": [
                    {
                        "output_id": "lookup_trace",
                        "output_type": "trace",
                        "content": "Trace details",
                    }
                ],
                "session_state_updates": {"lookup_status": "complete"},
                "assembly_state": {"last_lookup": "lookup_summary"},
            }

        registry.register_tool("lookup_tool", run_tool)
        state = {
            "_executor_registry": registry,
            "turn_execution_plan": {
                "actions": [
                    {
                        "action_id": "action:tool",
                        "action_type": "invoke_tool",
                        "target": "lookup_tool",
                        "visibility": "internal_only",
                        "params": {},
                    }
                ],
            },
        }

        out = execute_turn_plan.run(state)
        output_ids = {item["output_id"] for item in out["intermediate_outputs"]}
        self.assertIn("lookup_notes", output_ids)
        self.assertIn("lookup_summary", output_ids)
        self.assertIn("lookup_trace", output_ids)
        self.assertEqual(out["session_execution_state"]["lookup_status"], "complete")
        self.assertEqual(out["assembly_state"]["last_lookup"], "lookup_summary")
        self.assertEqual(out["tool_results"][0]["artifact_type"], "tool_call")

    def test_execute_turn_plan_applies_structured_skill_outputs(self):
        registry = ExecutorRegistry()

        def run_skill(*, state, action):
            _ = (state, action)
            return {
                "visible_outputs": [
                    {
                        "output_id": "skill_draft",
                        "output_type": "draft",
                        "visibility": "summary_visible",
                        "content": "Draft from skill",
                    }
                ],
                "artifacts": [
                    {
                        "artifact_id": "artifact:skill:trace",
                        "artifact_type": "skill_trace",
                        "content": {"step_count": 3},
                    }
                ],
            }

        registry.register_skill("draft_skill", run_skill)
        state = {
            "_executor_registry": registry,
            "turn_execution_plan": {
                "actions": [
                    {
                        "action_id": "action:skill",
                        "action_type": "invoke_skill",
                        "target": "draft_skill",
                        "visibility": "internal_only",
                        "params": {},
                    }
                ],
            },
        }

        out = execute_turn_plan.run(state)
        self.assertEqual(out["visible_outputs"][0]["output_id"], "skill_draft")
        self.assertEqual(out["tool_results"][0]["artifact_type"], "skill_call")
        artifact_types = [item["artifact_type"] for item in out["execution_artifacts"]]
        self.assertIn("skill_call", artifact_types)
        self.assertIn("skill_trace", artifact_types)

    def test_execute_turn_plan_builtin_output_artifact_assembler_creates_assembly_plan(self):
        state = {
            "turn_execution_plan": {
                "actions": [
                    {
                        "action_id": "action:assemble",
                        "action_type": "assemble_output",
                        "target": "output_artifact_assembler",
                        "visibility": "internal_only",
                        "params": {
                            "target_outputs": ["Director Bundle.md"],
                            "source_output_key": "final_answer",
                        },
                    }
                ],
            },
        }

        out = execute_turn_plan.run(state)
        self.assertEqual(out["assembly_state"]["target_outputs"], ["Director Bundle.md"])
        self.assertEqual(out["assembly_state"]["status"], "pending_source_output")
        self.assertEqual(out["hidden_outputs"][0]["output_id"], "output_artifact_assembly_plan")
        artifact_types = [item["artifact_type"] for item in out["execution_artifacts"]]
        self.assertIn("assembly_plan", artifact_types)
        self.assertIn("assembly", artifact_types)

    def test_execute_turn_plan_builtin_output_artifact_validator_marks_pending_when_source_missing(self):
        state = {
            "turn_execution_plan": {
                "actions": [
                    {
                        "action_id": "action:validate",
                        "action_type": "validate_output",
                        "target": "output_artifact_validator",
                        "visibility": "internal_only",
                        "params": {
                            "target_outputs": ["Director Bundle.md"],
                            "validation_scope": "output_artifacts",
                            "source_output_key": "final_answer",
                        },
                    }
                ],
            },
        }

        out = execute_turn_plan.run(state)
        self.assertEqual(out["session_execution_state"]["validation_status"], "pending_source_output")
        self.assertEqual(out["session_execution_state"]["pending_validation_target_outputs"], ["Director Bundle.md"])
        self.assertEqual(out["hidden_outputs"][0]["output_id"], "output_artifact_validation_report")
        self.assertEqual(out["tool_results"][0]["artifact_type"], "validation")

    def test_execute_turn_plan_builtin_output_artifact_validator_passes_when_source_exists(self):
        state = {
            "visible_outputs": [
                {
                    "output_id": "final_answer",
                    "output_type": "user_visible_response",
                    "visibility": "user_visible",
                    "content": "Final answer content",
                }
            ],
            "turn_execution_plan": {
                "actions": [
                    {
                        "action_id": "action:validate",
                        "action_type": "validate_output",
                        "target": "output_artifact_validator",
                        "visibility": "internal_only",
                        "params": {
                            "target_outputs": ["Director Bundle.md"],
                            "validation_scope": "output_artifacts",
                            "source_output_key": "final_answer",
                        },
                    }
                ],
            },
        }

        out = execute_turn_plan.run(state)
        self.assertEqual(out["session_execution_state"]["validation_status"], "passed")
        self.assertEqual(out["session_execution_state"]["pending_validation_target_outputs"], [])
        report = next(item for item in out["hidden_outputs"] if item["output_id"] == "output_artifact_validation_report")
        self.assertEqual(report["structured_data"]["issues"], [])

    def test_execute_turn_plan_marks_input_outputs_as_consumed(self):
        state = {
            "intermediate_outputs": [
                {
                    "output_id": "lookup_notes",
                    "output_type": "notes",
                    "visibility": "internal_only",
                    "content": "Lookup notes",
                    "structured_data": {},
                    "status": "draft",
                }
            ],
            "turn_execution_plan": {
                "actions": [
                    {
                        "action_id": "action:use_notes",
                        "action_type": "respond_to_user",
                        "target": "assistant_response",
                        "input_keys": ["lookup_notes"],
                        "visibility": "user_visible",
                        "params": {"content": "Using the lookup notes."},
                    }
                ],
            },
        }

        out = execute_turn_plan.run(state)
        self.assertEqual(out["intermediate_outputs"][0]["status"], "consumed")
        self.assertEqual(out["intermediate_outputs"][0]["consumed_by"], ["action:use_notes"])


if __name__ == "__main__":
    unittest.main()
