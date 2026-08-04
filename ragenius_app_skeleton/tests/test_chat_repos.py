import sys
import unittest
import uuid
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.chat_repos import ChatRepo, SessionRepo, _MEMORY_STORES


class ChatRepoDurabilityTests(unittest.TestCase):
    def _tmp_root(self) -> Path:
        root = Path(__file__).resolve().parent / "_tmp" / "chat_repos" / str(uuid.uuid4())
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _cleanup_root(self, root: Path) -> None:
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)

    def test_session_archive_and_messages_persist_across_repo_reconstruction(self):
        root = self._tmp_root()
        try:
            db_path = root / "runtime_state.db"

            session_repo = SessionRepo(db_path)
            chat_repo = ChatRepo(db_path)

            session_repo.get_or_create(
                "s-1",
                collection_id="app-1",
                user_id="u-1",
                title="Original Title",
                pinned=False,
                archived=False,
                config_version=1,
                adapter_version=1,
                template_version=1,
            )
            session_repo.set_flags("s-1", archived=True)
            chat_repo.append("s-1", "user", "hello")
            chat_repo.append("s-1", "assistant", "world")

            _MEMORY_STORES.clear()

            reloaded_session_repo = SessionRepo(db_path)
            reloaded_chat_repo = ChatRepo(db_path)

            session = reloaded_session_repo.get("s-1")
            self.assertIsNotNone(session)
            self.assertTrue(bool(session.get("archived")))

            visible_sessions = reloaded_session_repo.list_for_app_user("app-1", "u-1")
            self.assertEqual(visible_sessions, [])

            archived_sessions = reloaded_session_repo.list_for_app_user("app-1", "u-1", include_archived=True)
            self.assertEqual(len(archived_sessions), 1)
            self.assertEqual(archived_sessions[0]["id"], "s-1")

            history = reloaded_chat_repo.history("s-1")
            self.assertEqual([item["content"] for item in history], ["hello", "world"])
        finally:
            self._cleanup_root(root)


if __name__ == "__main__":
    unittest.main()
