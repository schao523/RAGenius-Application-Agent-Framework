import os
import unittest
import uuid
from pathlib import Path
from unittest import mock

from shared.rag_env import configure_default_rag_env
from rag_subsystem.vector_store.factory import _default_dsn


class RagEnvConsistencyTests(unittest.TestCase):
    def _clear_keys(self):
        keys = [
            "DATABASE_URL",
            "RAG_VECTOR_STORE_BACKEND",
            "RAG_VECTOR_STORE_DSN",
            "RAG_VECTOR_STORE_PGVECTOR_FALLBACK",
            "RAG_VECTOR_STORE_PATH",
            "RAG_PGVECTOR_BOOTSTRAP",
        ]
        saved = {key: os.environ.get(key) for key in keys}
        for key in keys:
            os.environ.pop(key, None)
        return saved

    def _restore_keys(self, saved):
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_configure_default_rag_env_loads_repo_env_and_aligns_vector_dsn(self):
        tmp_root = Path(__file__).resolve().parent / "_tmp" / "rag_env" / str(uuid.uuid4())
        env_dir = tmp_root / "ragenius_app_skeleton"
        env_dir.mkdir(parents=True, exist_ok=True)
        (env_dir / ".env").write_text(
            "DATABASE_URL=postgresql://ragenius:ragenius@localhost:5433/ragenius\n",
            encoding="utf-8",
        )
        saved = self._clear_keys()
        try:
            with mock.patch("shared.rag_env._repo_root", return_value=tmp_root):
                configure_default_rag_env()
            self.assertEqual(
                os.environ.get("DATABASE_URL"),
                "postgresql://ragenius:ragenius@localhost:5433/ragenius",
            )
            self.assertEqual(
                os.environ.get("RAG_VECTOR_STORE_DSN"),
                "postgresql://ragenius:ragenius@localhost:5433/ragenius",
            )
            self.assertEqual(os.environ.get("RAG_VECTOR_STORE_BACKEND"), "pgvector")
            self.assertEqual(os.environ.get("RAG_VECTOR_STORE_PGVECTOR_FALLBACK"), "error")
            self.assertTrue(
                os.environ.get("RAG_VECTOR_STORE_PATH", "").endswith(".shared_state\\rag_vector_store.json")
                or os.environ.get("RAG_VECTOR_STORE_PATH", "").endswith(".shared_state/rag_vector_store.json")
            )
            self.assertEqual(_default_dsn(), "postgresql://ragenius:ragenius@localhost:5433/ragenius")
        finally:
            self._restore_keys(saved)
            if tmp_root.exists():
                for path in sorted(tmp_root.glob("**/*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()

    def test_configure_default_rag_env_defaults_to_local_5432_when_no_env_file_exists(self):
        tmp_root = Path(__file__).resolve().parent / "_tmp" / "rag_env" / str(uuid.uuid4())
        tmp_root.mkdir(parents=True, exist_ok=True)
        saved = self._clear_keys()
        try:
            with mock.patch("shared.rag_env._repo_root", return_value=tmp_root):
                configure_default_rag_env()
            self.assertEqual(
                os.environ.get("RAG_VECTOR_STORE_DSN"),
                "postgresql://ragenius:ragenius@localhost:5433/ragenius",
            )
            self.assertEqual(_default_dsn(), "postgresql://ragenius:ragenius@localhost:5433/ragenius")
        finally:
            self._restore_keys(saved)
            if tmp_root.exists():
                for path in sorted(tmp_root.glob("**/*"), reverse=True):
                    if path.is_file():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()
