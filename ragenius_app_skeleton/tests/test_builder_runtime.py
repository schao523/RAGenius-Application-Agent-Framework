import unittest

from backend.app.builder_runtime import derive_builder_adapter_json, derive_builder_config_json


class BuilderRuntimeTests(unittest.TestCase):
    def test_derives_schema_valid_config_and_adapter(self):
        app_record = {
            "id": "app-1",
            "name": "Bible Helper",
            "slug": "bible-helper",
            "description": "Assist Bible study questions.",
            "starter_questions": ["Who is Jesus?", "Explain John 3:16", "", ""],
            "updated_at": "2026-04-25T00:00:00",
        }
        settings_record = {
            "config_settings": {
                "language": "zh",
                "embedding_model": "text-embedding-3-small",
            },
            "config_schema": {"type": "object"},
            "updated_at": "2026-04-25T00:00:00",
        }
        instructions_record = {
            "content": "# Mission\n- Answer from uploaded knowledge.\n# Style\n- Be concise.\n# Safety\n- Do not fabricate.\n",
            "uri": "instructions/app-1/instructions.md",
            "version": "v1",
            "updated_at": "2026-04-25T00:00:00",
        }

        config_json = derive_builder_config_json(app_record, settings_record, instructions_record)
        adapter_json = derive_builder_adapter_json(app_record, config_json)

        self.assertEqual(config_json["meta"]["builder_app_id"], "app-1")
        self.assertEqual(config_json["meta"]["llm_settings"]["model"], "text-embedding-3-small")
        self.assertIn("Answer from uploaded knowledge.", config_json["role"]["mission"])
        self.assertEqual(adapter_json["domain"], "bible-helper")
        self.assertEqual(adapter_json["retrieval_defaults"]["language"], "zh")
        self.assertIn("Do not fabricate.", adapter_json["llm_guardrails_append"])


if __name__ == "__main__":
    unittest.main()
