import io
import unittest
from unittest import mock

from backend.app import ingestion_service
from backend.app.ingestion_repo import IngestionRepo


class _FakeUpload:
    def __init__(self, filename: str, content_type: str, data: bytes):
        self.filename = filename
        self.content_type = content_type
        self.file = io.BytesIO(data)


class IngestionServiceTests(unittest.TestCase):
    def test_pdf_fallback_does_not_decode_raw_binary(self):
        # Minimal invalid PDF-like payload; extraction should fail and return safe placeholder.
        payload = b"%PDF-1.4\n1 0 obj\n<</Length 10>>stream\x00\x01\x02endstream\nendobj\n"
        text = ingestion_service._extract_text_for_document(payload, "application/pdf")
        self.assertIn("PDF text extraction failed", text)

    def test_run_ingestion_builds_safe_text_blocks(self):
        repo = IngestionRepo()
        run = repo.create_run("c1", 1)
        captured = {}

        def fake_process_files(*, documents, config=None, store=None, embed_client=None, router=None):
            captured["documents"] = documents
            return {"debug_trace": {"ok": True}}

        with mock.patch.object(ingestion_service, "_default_process_files", side_effect=fake_process_files):
            ingestion_service.run_ingestion(
                run["id"],
                "c1",
                [_FakeUpload("bad.pdf", "application/pdf", b"%PDF-1.4\nnot real")],
                repo,
            )

        self.assertEqual(repo.get_run(run["id"])["status"], "success")
        block_text = captured["documents"][0]["blocks"][0]["text"]
        self.assertNotIn("endobj", block_text.lower())
        self.assertTrue(block_text)


if __name__ == "__main__":
    unittest.main()
