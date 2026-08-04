import unittest
from pathlib import Path
from unittest import mock

from jsonschema.exceptions import ValidationError

from workflows.nodes import extract_config_pdf


def make_valid_config_json():
    return {
        "meta": {"title": "Config", "domain_hint": "general", "version_hint": None, "author": None},
        "role": {"name": "assistant", "mission": []},
        "goals": [],
        "mode_detection": [],
        "coverage_rules": [],
        "retrieval_rules": [],
        "style_rules": [],
        "safety_rules": [],
        "step_skeletons": [],
        "modules": [],
        "controls_commands": [],
    }


class FakeConfigRepo:
    def __init__(self):
        self.calls = []

    def save(self, collection_id, config_json, extracted_text, *, source_pdf_name=None):
        self.calls.append(
            {
                "collection_id": collection_id,
                "config_json": config_json,
                "extracted_text": extracted_text,
                "source_pdf_name": source_pdf_name,
            }
        )
        return {"version": 1}


class ExtractConfigPdfNodeTests(unittest.TestCase):
    def setUp(self):
        self.sample_pdf = (
            Path(__file__).resolve().parents[1] / "10_reference_pdfs" / "ConfigPDF_Example_Bible.pdf"
        )
        self.assertTrue(self.sample_pdf.exists(), f"Missing sample PDF: {self.sample_pdf}")

    @unittest.skipUnless(extract_config_pdf.parser_available(), "pdf parser dependency not installed")
    def test_extract_text_from_sample_pdf(self):
        text = extract_config_pdf.extract_text_from_pdf(self.sample_pdf)
        self.assertIsInstance(text, str)
        self.assertGreater(len(text.strip()), 0)

    def test_run_deterministic_path_first(self):
        state = {"collection_id": "00000000-0000-0000-0000-000000000001", "config_pdf_path": str(self.sample_pdf)}
        fake_repo = FakeConfigRepo()

        with mock.patch.object(extract_config_pdf, "extract_text_from_pdf", return_value="Goals:\n- answer"), mock.patch.object(
            extract_config_pdf, "has_strong_sections", return_value=True
        ), mock.patch.object(
            extract_config_pdf, "deterministic_config_from_text", return_value=make_valid_config_json()
        ) as deterministic_fn:
            result = extract_config_pdf.run(state, repo=fake_repo)

        self.assertIn("config_extracted_text", result)
        self.assertIn("config_json", result)
        deterministic_fn.assert_called_once()
        self.assertEqual(len(fake_repo.calls), 1)

    def test_run_fallbacks_to_llm_when_sections_weak(self):
        state = {"collection_id": "00000000-0000-0000-0000-000000000001", "config_pdf_path": str(self.sample_pdf)}
        fake_repo = FakeConfigRepo()
        llm = mock.Mock(return_value=make_valid_config_json())

        with mock.patch.object(extract_config_pdf, "extract_text_from_pdf", return_value="plain text"), mock.patch.object(
            extract_config_pdf, "has_strong_sections", return_value=False
        ):
            result = extract_config_pdf.run(state, llm_extractor=llm, repo=fake_repo)

        self.assertIn("config_json", result)
        llm.assert_called_once()
        self.assertEqual(len(fake_repo.calls), 1)

    def test_run_uses_deterministic_fallback_when_llm_missing(self):
        state = {"collection_id": "00000000-0000-0000-0000-000000000001", "config_pdf_path": str(self.sample_pdf)}

        with mock.patch.object(extract_config_pdf, "extract_text_from_pdf", return_value="plain text"), mock.patch.object(
            extract_config_pdf, "has_strong_sections", return_value=False
        ):
            out = extract_config_pdf.run(state, llm_extractor=None)
            self.assertIn("config_json", out)

    def test_run_validates_schema(self):
        state = {"collection_id": "00000000-0000-0000-0000-000000000001", "config_pdf_path": str(self.sample_pdf)}
        bad_config = {"meta": {"title": "bad"}}

        with mock.patch.object(extract_config_pdf, "extract_text_from_pdf", return_value="plain text"), mock.patch.object(
            extract_config_pdf, "has_strong_sections", return_value=False
        ):
            with self.assertRaises(ValidationError):
                extract_config_pdf.run(state, llm_extractor=lambda _text, _prompt: bad_config)


if __name__ == "__main__":
    unittest.main()
