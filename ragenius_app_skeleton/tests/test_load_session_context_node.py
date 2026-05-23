import shutil
import unittest
from pathlib import Path

from backend.app.chat_repos import SessionRepo
from workflows.nodes import load_session_context


class LoadSessionContextNodeTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(__file__).resolve().parent / "_tmp" / "load_session_context"
        if self.tmpdir.exists():
            shutil.rmtree(self.tmpdir, ignore_errors=True)
        self.tmpdir.mkdir(parents=True, exist_ok=True)
        self.state_db = self.tmpdir / "runtime_state.db"
        self.session_repo = SessionRepo(self.state_db)
        self.session_repo.reset()
        self.session_repo.get_or_create(
            "s-load",
            collection_id="app-1",
            user_id="u1",
            config_version=3,
            adapter_version=4,
            template_version=5,
        )
        self.session_repo.set_runtime_state(
            "s-load",
            {
                "workflow_progress": {"workflow_id": "bible_study", "step_order": 1},
                "session_execution_state": {"execution_status": "guiding"},
                "intermediate_outputs": [{"output_id": "obs-notes", "output_type": "notes"}],
                "assembly_state": {"target_output": "study_summary"},
            },
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_loads_runtime_state_from_session_when_state_is_empty(self):
        state = {
            "session_id": "s-load",
            "_session_repo": self.session_repo,
        }

        out = load_session_context.run(state)

        self.assertEqual(out["collection_id"], "app-1")
        self.assertEqual(out["user_id"], "u1")
        self.assertEqual(out["config_version"], 3)
        self.assertEqual(out["workflow_progress"]["workflow_id"], "bible_study")
        self.assertEqual(out["session_execution_state"]["execution_status"], "guiding")
        self.assertEqual(out["intermediate_outputs"][0]["output_id"], "obs-notes")
        self.assertEqual(out["assembly_state"]["target_output"], "study_summary")

    def test_keeps_provided_workflow_state_instead_of_overwriting_with_persisted_state(self):
        state = {
            "session_id": "s-load",
            "_session_repo": self.session_repo,
            "workflow_progress": {"workflow_id": "custom_flow", "step_order": 9},
            "session_execution_state": {"execution_status": "resuming"},
            "intermediate_outputs": [{"output_id": "custom-output", "output_type": "draft"}],
            "assembly_state": {"target_output": "custom_bundle"},
        }

        out = load_session_context.run(state)

        self.assertEqual(out["workflow_progress"]["workflow_id"], "custom_flow")
        self.assertEqual(out["session_execution_state"]["execution_status"], "resuming")
        self.assertEqual(out["intermediate_outputs"][0]["output_id"], "custom-output")
        self.assertEqual(out["assembly_state"]["target_output"], "custom_bundle")


if __name__ == "__main__":
    unittest.main()
