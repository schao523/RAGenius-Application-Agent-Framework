import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app import llm_runtime
from backend.app.llm_runtime import (
    _extract_tool_arguments,
    make_task_callable,
    resolve_task_model,
)
from ragenius_builder.flask_scaffold.storage import (
    DEFAULT_APP_CONFIG_SCHEMA,
    DEFAULT_APP_CONFIG_SETTINGS,
)


class LlmRuntimeCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_instruction_understanding_tasks_fallback_to_adapter_generation_model(self):
        llm_settings = {
            "provider": "deepseek",
            "models": {
                "planner": "planner-model",
                "adapter_generation": "adapter-model",
            },
            "temperature": {
                "planner": 0.1,
                "adapter_generation": 0.0,
            },
        }

        for task in (
            "instruction_understanding_compile",
            "instruction_understanding_review",
            "instruction_understanding_revision",
        ):
            with self.subTest(task=task):
                config = resolve_task_model(llm_settings, task)
                self.assertIsNotNone(config)
                self.assertEqual(config["model"], "adapter-model")
                self.assertEqual(config["temperature"], 0.0)

    def test_instruction_understanding_tasks_fallback_to_planner_when_adapter_missing(self):
        llm_settings = {
            "provider": "deepseek",
            "models": {
                "planner": "planner-model",
            },
            "temperature": {
                "planner": 0.1,
            },
        }

        config = resolve_task_model(llm_settings, "instruction_understanding_compile")
        self.assertIsNotNone(config)
        self.assertEqual(config["model"], "planner-model")
        self.assertEqual(config["temperature"], 0.1)

    def test_builder_default_settings_include_instruction_understanding_task_models(self):
        models = DEFAULT_APP_CONFIG_SETTINGS["llm"]["models"]
        temperatures = DEFAULT_APP_CONFIG_SETTINGS["llm"]["temperature"]
        self.assertIn("instruction_understanding_compile", models)
        self.assertIn("instruction_understanding_review", models)
        self.assertIn("instruction_understanding_revision", models)
        self.assertIn("instruction_understanding_compile", temperatures)
        self.assertIn("instruction_understanding_review", temperatures)
        self.assertIn("instruction_understanding_revision", temperatures)

    def test_builder_default_schema_includes_instruction_understanding_task_models(self):
        llm_properties = DEFAULT_APP_CONFIG_SCHEMA["properties"]["llm"]["properties"]
        model_properties = llm_properties["models"]["properties"]
        temperature_properties = llm_properties["temperature"]["properties"]
        self.assertIn("instruction_understanding_compile", model_properties)
        self.assertIn("instruction_understanding_review", model_properties)
        self.assertIn("instruction_understanding_revision", model_properties)
        self.assertIn("instruction_understanding_compile", temperature_properties)
        self.assertIn("instruction_understanding_review", temperature_properties)
        self.assertIn("instruction_understanding_revision", temperature_properties)

    def test_resolve_task_model_includes_ssl_controls(self):
        os.environ["RAGENIUS_LLM_SSL_VERIFY"] = "false"
        os.environ["RAGENIUS_LLM_TRUST_ENV"] = "true"
        os.environ["RAGENIUS_LLM_CA_BUNDLE"] = "C:/certs/custom.pem"
        config = resolve_task_model(
            {
                "provider": "deepseek",
                "models": {"planner": "planner-model"},
            },
            "planner",
        )
        self.assertIsNotNone(config)
        self.assertEqual(config["ssl_verify"], False)
        self.assertEqual(config["trust_env"], True)
        self.assertEqual(config["ca_bundle"], "C:/certs/custom.pem")

    def test_make_task_callable_passes_ssl_controls_to_httpx(self):
        os.environ["DEEPSEEK_API_KEY"] = "test-key"

        class _Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "arguments": "{\"review_status\":\"reviewed_ok\",\"review_confidence\":0.9,\"review_findings\":{},\"review_summary_md\":\"ok\",\"review_recommendations\":{}}"
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }

        with mock.patch.object(llm_runtime.httpx, "post", return_value=_Response()) as post_mock:
            call = make_task_callable(
                "instruction_understanding_review",
                {
                    "provider": "deepseek",
                    "model": "deepseek-v4-pro",
                    "temperature": 0.2,
                    "base_url": "https://api.deepseek.com",
                    "timeout_seconds": 30,
                    "retry_attempts": 1,
                    "retry_backoff_seconds": 0.1,
                    "ssl_verify": False,
                    "trust_env": True,
                    "ca_bundle": None,
                },
            )
            result = call("prompt", [{"name": "noop", "parameters": {"type": "object"}}], {"x": 1})

        self.assertEqual(result["review_status"], "reviewed_ok")
        kwargs = post_mock.call_args.kwargs
        self.assertEqual(kwargs["verify"], False)
        self.assertEqual(kwargs["trust_env"], True)

    def test_extract_tool_arguments_recovers_balanced_json_substring(self):
        payload = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "arguments": (
                                        '{"app_semantic_model":{"primary_service_mode":"intent_routed_multi_workflow"}}'
                                        "\nextra trailing text"
                                    )
                                }
                            }
                        ]
                    }
                }
            ]
        }

        decoded = _extract_tool_arguments(payload)

        self.assertEqual(
            decoded["app_semantic_model"]["primary_service_mode"],
            "intent_routed_multi_workflow",
        )

    def test_extract_tool_arguments_falls_back_to_message_content_json(self):
        payload = {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"app_semantic_model":{"primary_service_mode":"single_default_workflow"}}'
                        ),
                        "tool_calls": [
                            {
                                "function": {
                                    "arguments": '{"app_semantic_model":{"primary_service_mode":"broken"'
                                }
                            }
                        ],
                    }
                }
            ]
        }

        decoded = _extract_tool_arguments(payload)

        self.assertEqual(
            decoded["app_semantic_model"]["primary_service_mode"],
            "single_default_workflow",
        )
