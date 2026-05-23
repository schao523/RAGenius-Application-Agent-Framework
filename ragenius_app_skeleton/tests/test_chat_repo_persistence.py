import unittest
from pathlib import Path
import uuid

from backend.app.chat_repos import ChatRepo, InstructionUnderstandingRepo, SessionRepo


class ChatRepoPersistenceTests(unittest.TestCase):
    def test_session_and_chat_history_survive_repo_reinstantiation(self):
        tmp_dir = Path(__file__).resolve().parent / "_tmp" / "chat_repo" / str(uuid.uuid4())
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            db_path = tmp_dir / "runtime_state.db"
            session_repo = SessionRepo(db_path)
            chat_repo = ChatRepo(db_path)

            session_repo.get_or_create(
                "s1",
                collection_id="app-1",
                user_id="u1",
                title="Who is Jesus?",
                pinned=True,
                config_version=1,
                adapter_version=1,
                template_version=1,
            )
            session_repo.set_workflow_progress(
                "s1",
                {
                    "workflow_id": "bible_study",
                    "workflow_title": "Bible Study",
                    "step_order": 2,
                    "step_title": "Identify Relationships",
                    "resource_file": "identify_relation_guide.md",
                },
            )
            session_repo.set_runtime_state(
                "s1",
                {
                    "workflow_progress": {
                        "workflow_id": "bible_study",
                        "workflow_title": "Bible Study",
                        "step_order": 2,
                        "step_title": "Identify Relationships",
                        "resource_file": "identify_relation_guide.md",
                    },
                    "session_execution_state": {
                        "execution_status": "guiding",
                        "active_scope_ids": ["step:bible_study:2"],
                    },
                    "intermediate_outputs": [
                        {
                            "output_id": "obs-notes",
                            "output_type": "notes",
                            "visibility": "internal_only",
                            "content": "Observation notes",
                        }
                    ],
                    "assembly_state": {"target_output": "final_bundle"},
                },
            )
            chat_repo.append("s1", "user", "Who is Jesus?")
            chat_repo.append(
                "s1",
                "assistant",
                "Grounded answer.",
                citations=[{"title": "Ref", "snippet": "Evidence"}],
                missing_info_types=["fact"],
                retrieval_summary={"retrieved_count": 3, "source_count": 1, "route_language": "en"},
            )

            session_repo_2 = SessionRepo(db_path)
            chat_repo_2 = ChatRepo(db_path)

            session = session_repo_2.get("s1")
            history = chat_repo_2.history("s1")
            sessions = session_repo_2.list_for_app_user("app-1", "u1")
            archived_hidden = session_repo_2.list_for_app_user("app-1", "u1", include_archived=False)
            session_repo_2.set_flags("s1", archived=True)
            archived_visible = session_repo_2.list_for_app_user("app-1", "u1", include_archived=True)
            delete_ok = session_repo_2.delete("s1")
            deleted_session = session_repo_2.get("s1")
        finally:
            if tmp_dir.exists():
                for path in sorted(tmp_dir.glob("**/*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()

        self.assertIsNotNone(session)
        self.assertEqual(session["collection_id"], "app-1")
        self.assertEqual(session["title"], "Who is Jesus?")
        self.assertTrue(bool(session["pinned"]))
        self.assertEqual(session["workflow_progress"]["workflow_id"], "bible_study")
        self.assertEqual(session["workflow_progress"]["step_order"], 2)
        self.assertEqual(session["runtime_state"]["session_execution_state"]["execution_status"], "guiding")
        self.assertEqual(session["runtime_state"]["intermediate_outputs"][0]["output_id"], "obs-notes")
        self.assertEqual(session["runtime_state"]["assembly_state"]["target_output"], "final_bundle")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[1]["citations"][0]["title"], "Ref")
        self.assertEqual(history[1]["missing_infoTypes"], ["fact"])
        self.assertEqual(history[1]["retrievalSummary"]["retrieved_count"], 3)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["last_message_role"], "assistant")
        self.assertEqual(sessions[0]["last_message_preview"], "Grounded answer.")
        self.assertEqual(len(archived_hidden), 1)
        self.assertEqual(len(archived_visible), 1)
        self.assertTrue(archived_visible[0]["archived"])
        self.assertTrue(delete_ok)
        self.assertIsNone(deleted_session)

    def test_instruction_understanding_records_supersede_and_survive_repo_reinstantiation(self):
        tmp_dir = Path(__file__).resolve().parent / "_tmp" / "instruction_understanding_repo" / str(uuid.uuid4())
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            db_path = tmp_dir / "runtime_state.db"
            repo = InstructionUnderstandingRepo(db_path)
            first = repo.save_compiled(
                app_id="app-1",
                instruction_source_hash="hash-1",
                instruction_source_version=1,
                instruction_uri="instructions/app-1/instructions.md",
                parser_contract_version="parser-v1",
                binding_logic_version="binding-v1",
                resource_catalog_hash="docs-v1",
                compiled_status="ready",
                compile_duration_ms=12,
                compile_errors=[],
                compiled_contract={"instruction_service_blocks": [{"title": "Workflow A"}]},
                metadata={"service_block_count": 1},
            )
            second = repo.save_compiled(
                app_id="app-1",
                instruction_source_hash="hash-2",
                instruction_source_version=2,
                instruction_uri="instructions/app-1/instructions.md",
                parser_contract_version="parser-v2",
                binding_logic_version="binding-v2",
                resource_catalog_hash="docs-v2",
                compiled_status="ready",
                compile_duration_ms=18,
                compile_errors=[],
                compiled_contract={"instruction_service_blocks": [{"title": "Workflow B"}]},
                metadata={"service_block_count": 1},
            )
            review = repo.save_review(
                app_id="app-1",
                instruction_source_hash="hash-2",
                parser_contract_version="parser-v2",
                review_model="fake-reviewer",
                review_prompt_version="review-v1",
                review_status="reviewed_ok",
                review_confidence=0.9,
                review_findings={"default_workflow_assessment": "plausible"},
                review_summary_md="# Review\n",
                review_recommendations={"action": "none"},
            )
            repo.save_compiled(
                app_id="app-1",
                instruction_source_hash="hash-3",
                instruction_source_version=3,
                instruction_uri="instructions/app-1/instructions.md",
                parser_contract_version="parser-v3",
                binding_logic_version="binding-v3",
                resource_catalog_hash="docs-v3",
                compiled_status="ready",
                compile_duration_ms=11,
                compile_errors=[],
                compiled_contract={"instruction_service_blocks": [{"title": "Workflow C"}]},
                metadata={"service_block_count": 1},
            )

            repo_2 = InstructionUnderstandingRepo(db_path)
            active = repo_2.get_active_compiled("app-1")
            active_review = repo_2.get_active_review("app-1")
        finally:
            if tmp_dir.exists():
                for path in sorted(tmp_dir.glob("**/*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()

        self.assertEqual(first["instruction_source_hash"], "hash-1")
        self.assertEqual(second["instruction_source_hash"], "hash-2")
        self.assertIsNotNone(active)
        self.assertEqual(active["compiled_contract"]["instruction_service_blocks"][0]["title"], "Workflow C")
        self.assertEqual(active["metadata"]["service_block_count"], 1)
        self.assertIsNone(active_review)

    def test_instruction_understanding_approval_and_revision_records_survive_repo_reinstantiation(self):
        tmp_dir = Path(__file__).resolve().parent / "_tmp" / "instruction_understanding_revision_repo" / str(uuid.uuid4())
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            db_path = tmp_dir / "runtime_state.db"
            repo = InstructionUnderstandingRepo(db_path)
            compiled = repo.save_compiled(
                app_id="app-2",
                instruction_source_hash="hash-a",
                instruction_source_version=1,
                instruction_uri="instructions/app-2/instructions.md",
                parser_contract_version="parser-v1",
                binding_logic_version="binding-v1",
                resource_catalog_hash="docs-v1",
                compiled_status="ready",
                compile_duration_ms=9,
                compile_errors=[],
                compiled_contract={"instruction_service_blocks": [{"title": "Workflow A"}]},
                metadata={},
            )
            review = repo.save_review(
                app_id="app-2",
                instruction_source_hash="hash-a",
                parser_contract_version="parser-v1",
                review_model="fake-reviewer",
                review_prompt_version="review-v1",
                review_status="reviewed_with_warnings",
                review_confidence=0.75,
                review_findings={"critical": ["misclassified block"]},
                review_summary_md="# Review\n",
                review_recommendations={"action": "revise"},
            )
            approval = repo.save_approval(
                app_id="app-2",
                compiled_record_id=compiled["id"],
                review_record_id=review["id"],
                approved_findings=[
                    {"finding_id": "finding-1", "decision": "approve", "approved_revision_note": "Promote role profiles"}
                ],
                approver="tester",
            )
            revision = repo.save_revision(
                app_id="app-2",
                compiled_record_id=compiled["id"],
                review_record_id=review["id"],
                approval_record_id=approval["id"],
                instruction_source_hash="hash-a",
                parser_contract_version="parser-v1",
                revision_prompt_version="revision-v1",
                revision_status="draft",
                revised_contract={"role_profiles": [{"role_id": "role:coach"}]},
                revision_notes=["Added role profile"],
                preserved_ids=["workflow:a"],
                changed_ids=["role:coach"],
                revision_confidence=0.66,
            )

            repo_2 = InstructionUnderstandingRepo(db_path)
            active_approval = repo_2.get_active_approval("app-2")
            active_revision = repo_2.get_active_revision("app-2")
        finally:
            if tmp_dir.exists():
                for path in sorted(tmp_dir.glob("**/*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()

        self.assertIsNotNone(active_approval)
        self.assertEqual(active_approval["approved_findings"][0]["decision"], "approve")
        self.assertEqual(active_approval["approver"], "tester")
        self.assertIsNotNone(active_revision)
        self.assertEqual(active_revision["revision_status"], "draft")
        self.assertEqual(active_revision["revised_contract"]["role_profiles"][0]["role_id"], "role:coach")
        self.assertEqual(active_revision["changed_ids"], ["role:coach"])


if __name__ == "__main__":
    unittest.main()
