import tempfile
import unittest
from pathlib import Path

from rag_subsystem.schemas import Chunk
from rag_subsystem.vector_store.json_file_store import JsonFileVectorStore


def _chunk(doc_id: str, chunk_id: str, namespace: str, text: str, app_id: str) -> Chunk:
    return Chunk(
        doc_id=doc_id,
        chunk_id=chunk_id,
        text=text,
        section_path=None,
        order=0,
        language="zh",
        embedding_model="bge-large-zh",
        namespace=namespace,
        embedding=[0.1, 0.2, 0.3],
        metadata={"app_id": app_id, "filename": "doc.pdf"},
        hash=f"hash-{chunk_id}",
    )


class JsonFileVectorStoreReloadTests(unittest.TestCase):
    def test_search_sees_external_upsert_without_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "store.json"
            store_a = JsonFileVectorStore(str(path))
            store_b = JsonFileVectorStore(str(path))
            namespace = "app-1:zh:bge-large-zh"
            app_id = "app-1"

            store_a.upsert([_chunk("doc-1", "doc-1::0", namespace, "細查事實觀察項目", app_id)])

            results = store_b.metadata_search({"filename": "doc.pdf"}, namespace, top_k=5, app_id=app_id)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][0].chunk_id, "doc-1::0")

            semantic = store_b.semantic_search([0.1, 0.2, 0.3], namespace, top_k=5, app_id=app_id)
            self.assertEqual(len(semantic), 1)
            self.assertEqual(semantic[0][0].doc_id, "doc-1")

    def test_delete_sees_external_upsert_before_removal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "store.json"
            store_a = JsonFileVectorStore(str(path))
            store_b = JsonFileVectorStore(str(path))
            namespace = "app-1:zh:bge-large-zh"
            app_id = "app-1"

            store_a.upsert(
                [
                    _chunk("doc-1", "doc-1::0", namespace, "第一段", app_id),
                    _chunk("doc-2", "doc-2::0", namespace, "第二段", app_id),
                ]
            )

            store_b.delete_by_doc_id("doc-1", app_id=app_id)

            store_c = JsonFileVectorStore(str(path))
            remaining = store_c.metadata_search({"filename": "doc.pdf"}, namespace, top_k=10, app_id=app_id)
            remaining_doc_ids = [chunk.doc_id for chunk, _score in remaining]
            self.assertEqual(remaining_doc_ids, ["doc-2"])


if __name__ == "__main__":
    unittest.main()
