import unittest

from workflows.nodes import evidence_postprocess


class EvidencePostprocessTests(unittest.TestCase):
    def test_dedupe_group_and_compress(self):
        state = {
            "raw_evidence": [
                {"doc_id": "d1", "title": "Doc 1", "snippet": "A", "score": 0.7, "metadata": {"info_type": "fact"}},
                {"doc_id": "d1", "title": "Doc 1", "snippet": "A", "score": 0.7, "metadata": {"info_type": "fact"}},
                {"doc_id": "d1", "title": "Doc 1", "snippet": "B", "score": 0.9, "metadata": {"info_type": "fact"}},
                {"doc_id": "d2", "title": "Doc 2", "snippet": "C", "score": 0.8, "metadata": {"info_type": "risk"}},
            ]
        }
        out = evidence_postprocess.run(state)
        compressed = out["compressed_evidence"]
        self.assertEqual(len(compressed), 2)
        self.assertEqual(compressed[0]["doc_id"], "d1")
        self.assertEqual(compressed[0]["score"], 0.9)
        self.assertIn("A", compressed[0]["snippet"])
        self.assertIn("B", compressed[0]["snippet"])
        self.assertGreaterEqual(compressed[0]["source_count"], 2)

    def test_sanitizes_binary_like_snippet(self):
        state = {
            "raw_evidence": [
                {
                    "doc_id": "d1",
                    "title": "Doc 1",
                    "snippet": "500 500 endobj /Filter /FlateDecode stream vj3DVK",
                    "score": 0.8,
                    "metadata": {},
                }
            ]
        }
        out = evidence_postprocess.run(state)
        self.assertEqual(out["compressed_evidence"][0]["snippet"], "[Snippet omitted: non-readable extracted content]")

    def test_preserves_instruction_and_knowledge_channels(self):
        state = {
            "raw_evidence": [
                {
                    "doc_id": "i1",
                    "title": "Observation Guide",
                    "snippet": "Ask what repeated words appear.",
                    "score": 0.8,
                    "metadata": {},
                    "retrieval_domain": "instruction_source",
                },
                {
                    "doc_id": "k1",
                    "title": "John 17 PDF",
                    "snippet": "Jesus prays for his disciples.",
                    "score": 0.9,
                    "metadata": {},
                    "retrieval_domain": "knowledge_source",
                },
                {
                    "doc_id": "t1",
                    "title": "Bundle Spec",
                    "snippet": "Use sections: Summary, Scenes, Prompts.",
                    "score": 0.85,
                    "metadata": {},
                    "retrieval_domain": "output_template",
                },
                {
                    "doc_id": "u1",
                    "title": "artifact.md",
                    "snippet": "# Draft\nUploaded artifact content",
                    "score": 1.0,
                    "metadata": {},
                    "retrieval_domain": "session_upload",
                },
            ]
        }
        out = evidence_postprocess.run(state)
        self.assertEqual(len(out["compressed_instruction_evidence"]), 1)
        self.assertEqual(out["compressed_instruction_evidence"][0]["doc_id"], "i1")
        self.assertEqual(len(out["compressed_knowledge_evidence"]), 1)
        self.assertEqual(out["compressed_knowledge_evidence"][0]["doc_id"], "k1")
        self.assertEqual(len(out["compressed_template_evidence"]), 1)
        self.assertEqual(out["compressed_template_evidence"][0]["doc_id"], "t1")
        self.assertEqual(len(out["compressed_session_upload_evidence"]), 1)
        self.assertEqual(out["compressed_session_upload_evidence"][0]["doc_id"], "u1")


if __name__ == "__main__":
    unittest.main()
