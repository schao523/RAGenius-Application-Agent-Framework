import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.rag_runtime import get_rag_store, reset_rag_store
from rag_subsystem.schemas import Chunk


class RagRuntimePersistenceTests(unittest.TestCase):
    def _tmp_root(self) -> Path:
        root = Path(__file__).resolve().parent / "_tmp" / "rag_runtime_persistence" / str(uuid.uuid4())
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _cleanup_root(self, root: Path) -> None:
        if root.exists():
            for path in sorted(root.glob("**/*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()

    def test_json_store_persists_chunks_across_reinitialization(self):
        root = self._tmp_root()
        try:
            store_path = str(root / "rag_store.json")
            chunk = Chunk(
                doc_id="doc-1",
                chunk_id="doc-1::0",
                text="Jesus wept.",
                section_path="John 11:35",
                order=0,
                language="en",
                embedding_model="test-model",
                namespace="default",
                embedding=[1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                metadata={"title": "Bible", "version": "1.0.0"},
                hash="hash-1",
            )

            with mock.patch.dict(
                os.environ,
                {
                    "RAG_VECTOR_STORE_BACKEND": "json",
                    "RAG_VECTOR_STORE_PATH": store_path,
                },
                clear=False,
            ):
                reset_rag_store()
                store = get_rag_store()
                store.upsert([chunk])

                reset_rag_store()
                reopened = get_rag_store()
                results = reopened.semantic_search(
                    [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    "default",
                    5,
                )

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][0].doc_id, "doc-1")
            self.assertTrue(Path(store_path).exists())
        finally:
            self._cleanup_root(root)


if __name__ == "__main__":
    unittest.main()
