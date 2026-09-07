import copy
import json
import unittest
import uuid
from pathlib import Path
from unittest import mock

from backend.app import instruction_understanding_service as service


class ProviderStepProjectionTests(unittest.TestCase):
    def model(self):
        return {
            "primary_service_mode": "single_default_workflow",
            "default_workflow_id": "workflow:design",
            "primary_workflow": {
                "workflow_id": "workflow:design", "title": "Design Workflow", "is_default": True,
                "step_sequence": ["step:design:1", "step:design:2"],
                "steps": [
                    {"step_id": "step:design:1", "title": "Ask", "order": 1,
                     "body_text": "Ask for the user's intended audience.", "wait_for_user": True,
                     "advance_conditions": ["User supplies audience"]},
                    {"step_id": "step:design:2", "title": "Confirm", "order": 2,
                     "stop_after_completion": True},
                ],
            },
            "support_modules": [{
                "module_id": "module_generator_module", "title": "MODULE_GENERATOR Module",
                "procedure_id": "procedure:generator", "resource_refs": ["design.md"],
                "required_inputs": ["requirements"],
                "steps": [
                    {"step_id": "step:generator:1", "title": "Clarify", "order": 1, "wait_for_user": True},
                    {"step_id": "step:generator:2", "title": "Generate", "order": 2,
                     "execution_mode": "bundled", "resource_refs": ["design.md"], "wait_for_user": False},
                ],
            }, {
                "module_id": "execution_rules", "title": "Module Execution Rules",
                "steps": [{"step_id": "rule:wait", "title": "Always wait for the user"}],
            }],
            "followup_modules": [{
                "module_id": "refine", "title": "Refinement Module",
                "steps": [{"step_id": "step:refine:1", "title": "Review", "wait_for_user": True}],
            }],
        }

    def contract(self):
        return {"resource_reference_catalog": [{"filename": "design.md"}]}

    def test_projects_workflow_and_modules_preserving_controls_and_policy(self):
        source = self.model()
        before = copy.deepcopy(source)
        result = service._validate_semantic_compile_candidate(semantic_model=source, deterministic_contract=self.contract())
        self.assertTrue(result["valid"], result["errors"])
        model = result["normalized"]
        owners = {p["service_block_id"] for p in model["procedures"]}
        self.assertEqual(owners, {"workflow:design", "module_generator_module", "refine"})
        self.assertEqual(len(model["procedure_steps"]), 5)
        steps = {s["step_id"]: s for s in model["procedure_steps"]}
        self.assertEqual(steps["step:design:1"]["body_text"], before["primary_workflow"]["steps"][0]["body_text"])
        self.assertEqual(steps["step:design:1"]["advance_conditions"], ["User supplies audience"])
        self.assertTrue(steps["step:design:1"]["wait_for_user"])
        self.assertFalse(steps["step:generator:2"]["wait_for_user"])
        self.assertEqual(steps["step:generator:2"]["bundled_step_ids"], ["step:generator:2"])
        self.assertEqual(steps["step:generator:2"]["resource_refs"], ["design.md"])
        self.assertNotIn("rule:wait", steps)
        policy = next(b for b in model["service_blocks"] if b["block_id"] == "execution_rules")
        self.assertEqual(policy["block_type"], "global_policy")
        self.assertIn("Always wait", policy["body_text"])
        self.assertEqual(source, before)

    def test_missing_sequence_reference_is_invalid(self):
        model = self.model()
        model["primary_workflow"]["step_sequence"].append("step:missing")
        result = service._validate_semantic_compile_candidate(semantic_model=model, deterministic_contract=self.contract())
        self.assertFalse(result["valid"])
        self.assertIn("step:missing", " ".join(result["errors"]))

    def test_flat_steps_are_not_duplicated_and_foreign_ownership_is_rejected(self):
        model = self.model()
        model["procedure_steps"] = [{**model["primary_workflow"]["steps"][0], "procedure_id": "workflow:design"}]
        normalized = service._canonicalize_provider_semantic_model(model)
        self.assertEqual(sum(s["step_id"] == "step:design:1" for s in normalized["procedure_steps"]), 1)
        model["procedure_steps"][0]["procedure_id"] = "procedure:generator"
        result = service._validate_semantic_compile_candidate(semantic_model=model, deterministic_contract=self.contract())
        self.assertFalse(result["valid"])

    def test_validation_detects_steps_lost_after_normalization(self):
        original = service._ground_semantic_model_from_deterministic_contract

        def lose_steps(model, contract):
            result = original(model, contract)
            result["procedure_steps"] = []
            return result

        with mock.patch.object(service, "_ground_semantic_model_from_deterministic_contract", side_effect=lose_steps):
            result = service._validate_semantic_compile_candidate(semantic_model=self.model(), deterministic_contract=self.contract())
        self.assertFalse(result["valid"])
        self.assertIn("missing executable", " ".join(result["errors"]))

    def test_validation_detects_steps_lost_during_normalization(self):
        original = service._canonicalize_provider_semantic_model

        def lose_steps(model):
            result = original(model)
            result["procedure_steps"] = []
            return result

        with mock.patch.object(service, "_canonicalize_provider_semantic_model", side_effect=lose_steps):
            result = service._validate_semantic_compile_candidate(semantic_model=self.model(), deterministic_contract=self.contract())
        self.assertFalse(result["valid"])
        self.assertIn("missing executable", " ".join(result["errors"]))

    def test_compatibility_does_not_restore_execution_policy_as_support_module(self):
        result = service._validate_semantic_compile_candidate(semantic_model=self.model(), deterministic_contract=self.contract())
        hybrid = service._build_hybrid_runtime_model(result["normalized"], self.contract(), result)
        compatibility = service._project_compatibility_instruction_runtime_model(
            {"support_modules": [{"module_id": "execution_rules", "title": "Module Execution Rules"}]}, hybrid
        )
        self.assertFalse(any(m.get("title") == "Module Execution Rules" for m in compatibility["support_modules"]))
        self.assertEqual(len(compatibility["procedure_steps"]), 5)

    def test_duplicate_and_omitted_sequence_entries_fail_validation(self):
        for sequence in (["step:design:1", "step:design:1"], ["step:design:1"]):
            with self.subTest(sequence=sequence):
                model = self.model()
                model["primary_workflow"]["step_sequence"] = sequence
                result = service._validate_semantic_compile_candidate(semantic_model=model, deterministic_contract=self.contract())
                self.assertFalse(result["valid"])

    def test_inline_module_steps_without_ids_receive_deterministic_ids(self):
        model = self.model()
        module = model["support_modules"][0]
        module.pop("steps")
        module["step_sequence"] = [
            {
                "order": 1,
                "title": "Clarify",
                "wait_for_user": True,
                "resource_refs": ["clarify.md"],
            },
            {"order": 2, "title": "Generate", "wait_for_user": False},
        ]

        result = service._validate_semantic_compile_candidate(
            semantic_model=model,
            deterministic_contract=self.contract(),
        )

        self.assertTrue(result["valid"], result["errors"])
        projected = {
            step["step_id"]: step
            for step in result["normalized"]["procedure_steps"]
        }
        self.assertIn("step:generator:1", projected)
        self.assertIn("step:generator:2", projected)
        self.assertEqual(projected["step:generator:1"]["title"], "Clarify")
        self.assertEqual(projected["step:generator:1"]["resource_refs"], ["clarify.md"])

    def test_inline_module_steps_with_duplicate_orders_remain_invalid(self):
        model = self.model()
        module = model["support_modules"][0]
        module.pop("steps")
        module["step_sequence"] = [
            {"order": 1, "title": "Clarify"},
            {"order": 1, "title": "Generate"},
        ]

        result = service._validate_semantic_compile_candidate(
            semantic_model=model,
            deterministic_contract=self.contract(),
        )

        self.assertFalse(result["valid"])
        self.assertIn("duplicate step id", " ".join(result["errors"]))

    def test_incomplete_recompile_preserves_active_record(self):
        root = Path(__file__).resolve().parent / "_tmp" / "provider_projection" / str(uuid.uuid4())
        root.mkdir(parents=True)
        try:
            repo = service.InstructionUnderstandingRepo(root / "state.db")
            model = self.model()
            with mock.patch.object(service, "_compile_contract", return_value=self.contract()):
                def compile_model():
                    return service.compile_instruction_understanding(
                        app_id="test-app", instruction_text="Design instructions", instruction_uri=None,
                        instruction_source_version=1, documents=[], repo=repo, snapshot_root=root / "snapshots",
                        semantic_compiler=lambda context: {"app_semantic_model": copy.deepcopy(model)},
                    )

                active = compile_model()
                self.assertTrue(active["metadata"]["semantic_compile_valid"])
                model["primary_workflow"]["step_sequence"].append("missing-step")
                failed = compile_model()
            self.assertFalse(failed["metadata"]["semantic_compile_valid"])
            self.assertEqual(failed["metadata"]["publish_status"], "diagnostic_only")
            self.assertEqual(repo.get_active_compiled("test-app")["id"], active["id"])
            snapshot = json.loads((root / "snapshots/test-app/understanding.json").read_text(encoding="utf-8"))
            self.assertEqual(snapshot["id"], active["id"])
        finally:
            for path in sorted(root.glob("**/*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            root.rmdir()


if __name__ == "__main__":
    unittest.main()
