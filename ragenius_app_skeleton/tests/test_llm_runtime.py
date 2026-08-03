import json
import os
import unittest
from unittest import mock

import httpx

from backend.app import chat_service, llm_runtime


class _FakeHttpResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError("unexpected test status")


class _FakeGraph:
    def __init__(self, assertions):
        self.assertions = assertions

    def invoke(self, state):
        self.assertions(state)
        return {"final_answer": {"content": "ok", "citations": [], "missing_infoTypes": []}}


class LlmRuntimeTests(unittest.TestCase):
    def test_resolve_task_model_from_nested_builder_settings(self):
        llm_settings = {
            "provider": "deepseek",
            "models": {
                "planner": "deepseek-reasoner",
                "answer_generation": "deepseek-chat",
            },
            "temperature": {
                "planner": 0.1,
                "answer_generation": 0.3,
            },
        }

        planner = llm_runtime.resolve_task_model(llm_settings, "planner")
        answer = llm_runtime.resolve_task_model(llm_settings, "answer_generation")

        self.assertEqual(planner["model"], "deepseek-v4-pro")
        self.assertEqual(planner["provider"], "deepseek")
        self.assertEqual(planner["temperature"], 0.1)
        self.assertEqual(answer["model"], "deepseek-v4-flash")
        self.assertEqual(answer["temperature"], 0.3)

    def test_task_callable_posts_openai_compatible_tool_request_and_returns_arguments(self):
        seen = {}

        def fake_post(url, headers=None, json_body=None, timeout=None, **kwargs):
            seen["url"] = url
            seen["timeout"] = timeout
            seen["headers"] = dict(headers or {})
            seen["body"] = json_body
            return _FakeHttpResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "create_planner_output",
                                            "arguments": json.dumps(
                                                {
                                                    "intentType": "qa",
                                                    "confidence": 0.9,
                                                    "steps": [{"id": "1", "title": "Retrieve", "goal": "Answer"}],
                                                    "infoTypes": ["fact"],
                                                    "retrievalPlan": {"query_text": "Who is Jesus?", "top_k": 3, "filters": {"app_id": "app-1"}},
                                                    "systemInstructionSummary": {
                                                        "fromConfigPdf": [],
                                                        "fromAdapter": [],
                                                        "fromTemplate": [],
                                                    },
                                                    "normalizedQuery": "Who is Jesus?",
                                                    "contextualQuery": "Who is Jesus?",
                                                }
                                            ),
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            )

        config = {
            "provider": "deepseek",
            "model": "deepseek-reasoner",
            "temperature": 0.1,
            "base_url": "https://api.deepseek.com",
            "timeout_seconds": 45,
            "max_tokens": 2048,
        }

        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=False):
            with mock.patch("backend.app.llm_runtime.httpx.post", side_effect=lambda *args, **kwargs: fake_post(*args, json_body=kwargs.get("json"), timeout=kwargs.get("timeout"), headers=kwargs.get("headers"), **{k:v for k,v in kwargs.items() if k not in {'json','timeout','headers'}})):
                callable_fn = llm_runtime.make_task_callable("planner", config)
                result = callable_fn(
                    "Planner prompt",
                    [{"name": "create_planner_output", "parameters": {"type": "object"}}],
                    {"user_query": "Who is Jesus?"},
                )

        self.assertEqual(result["intentType"], "qa")
        self.assertEqual(seen["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(seen["timeout"], 45)
        self.assertEqual(seen["body"]["model"], "deepseek-reasoner")
        self.assertEqual(seen["body"]["tool_choice"], "auto")
        self.assertEqual(seen["body"]["max_tokens"], 2048)
        self.assertEqual(seen["body"]["tools"][0]["type"], "function")
        self.assertEqual(seen["body"]["tools"][0]["function"]["name"], "create_planner_output")

    def test_reasoner_uses_auto_tool_choice_and_can_fall_back_to_json_content(self):
        seen = {}

        def fake_post(url, headers=None, json_body=None, timeout=None, **kwargs):
            seen["body"] = json_body
            return _FakeHttpResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "intentType": "qa",
                                        "confidence": 0.95,
                                        "steps": [{"id": "1", "title": "Think", "goal": "Answer"}],
                                        "infoTypes": ["fact"],
                                        "retrievalPlan": {"query_text": "hi", "top_k": 3, "filters": {"app_id": "app-1"}},
                                        "systemInstructionSummary": {
                                            "fromConfigPdf": [],
                                            "fromAdapter": [],
                                            "fromTemplate": [],
                                        },
                                        "normalizedQuery": "hi",
                                        "contextualQuery": "hi",
                                    }
                                )
                            }
                        }
                    ]
                }
            )

        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=False):
            with mock.patch("backend.app.llm_runtime.httpx.post", side_effect=lambda *args, **kwargs: fake_post(*args, json_body=kwargs.get("json"), timeout=kwargs.get("timeout"), headers=kwargs.get("headers"), **{k:v for k,v in kwargs.items() if k not in {'json','timeout','headers'}})):
                callable_fn = llm_runtime.make_task_callable(
                    "planner",
                    {
                        "provider": "deepseek",
                        "model": "deepseek-reasoner",
                        "temperature": 0.1,
                        "base_url": "https://api.deepseek.com",
                        "timeout_seconds": 20,
                        "max_tokens": None,
                    },
                )
                result = callable_fn("Planner prompt", [{"name": "create_planner_output", "parameters": {"type": "object"}}], {"user_query": "hi"})

        self.assertEqual(seen["body"]["tool_choice"], "auto")
        self.assertEqual(result["intentType"], "qa")

    def test_deepseek_v4_models_use_auto_tool_choice(self):
        seen = []

        def fake_post(url, headers=None, json_body=None, timeout=None, **kwargs):
            seen.append(json_body)
            return _FakeHttpResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "emit_result",
                                            "arguments": json.dumps({"value": "ok"}),
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            )

        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=False):
            with mock.patch(
                "backend.app.llm_runtime.httpx.post",
                side_effect=lambda *args, **kwargs: fake_post(
                    *args,
                    json_body=kwargs.get("json"),
                    timeout=kwargs.get("timeout"),
                    headers=kwargs.get("headers"),
                    **{k: v for k, v in kwargs.items() if k not in {"json", "timeout", "headers"}},
                ),
            ):
                for model in ("deepseek-v4-pro", "deepseek-v4-flash"):
                    callable_fn = llm_runtime.make_task_callable(
                        "planner",
                        {
                            "provider": "deepseek",
                            "model": model,
                            "temperature": 0.1,
                            "base_url": "https://api.deepseek.com",
                            "timeout_seconds": 20,
                            "max_tokens": None,
                        },
                    )
                    callable_fn("Planner prompt", [{"name": "emit_result", "parameters": {"type": "object"}}], {"user_query": "hi"})

        self.assertEqual(len(seen), 2)
        self.assertTrue(all(body["tool_choice"] == "auto" for body in seen))

    def test_run_chat_pipeline_uses_runtime_resolved_llm_callables(self):
        planner_callable = object()
        answer_callable = object()
        evidence_callable = object()

        def assert_state(state):
            self.assertIs(state["_llm_planner"], planner_callable)
            self.assertIs(state["_llm_answer"], answer_callable)
            self.assertIs(state["_llm_evidence_analysis"], evidence_callable)

        def fake_task_binding(_state, task):
            callable_ = {
                "planner": planner_callable,
                "answer_generation": answer_callable,
                "evidence_analysis": evidence_callable,
            }.get(task)
            return {
                "callable": callable_,
                "config": None,
                "diagnostics": {"task": task, "selected_source": "test-override"},
            }

        with mock.patch.object(chat_service, "build_task_binding", side_effect=fake_task_binding):
            with mock.patch.object(chat_service, "_graph", return_value=_FakeGraph(assert_state)):
                result = chat_service.run_chat_pipeline(
                    {
                        "config_json": {"meta": {"llm_settings": {"provider": "deepseek", "models": {"planner": "deepseek-reasoner"}}}},
                        "user_query": "hello",
                    },
                    session_repo=object(),
                    chat_repo=object(),
                    planner_repo=object(),
                    retrieval_repo=object(),
                )

        self.assertEqual(result["content"], "ok")

    def test_json_extractor_callable_parses_response_object(self):
        def fake_post(url, headers=None, json_body=None, timeout=None, **kwargs):
            self.assertEqual(timeout, 30)
            self.assertEqual(json_body["model"], "deepseek-chat")
            return _FakeHttpResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": 'Result:\n{"meta":{"title":"cfg"},"role":{"name":"assistant","mission":[]},"goals":[],"mode_detection":[],"coverage_rules":[],"retrieval_rules":[],"style_rules":[],"safety_rules":[],"step_skeletons":[],"modules":[],"controls_commands":[]}'
                            }
                        }
                    ]
                }
            )

        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=False):
            with mock.patch("backend.app.llm_runtime.httpx.post", side_effect=lambda *args, **kwargs: fake_post(*args, json_body=kwargs.get("json"), timeout=kwargs.get("timeout"), headers=kwargs.get("headers"), **{k:v for k,v in kwargs.items() if k not in {'json','timeout','headers'}})):
                extractor = llm_runtime.make_json_extractor_callable(
                    {
                        "provider": "deepseek",
                        "model": "deepseek-chat",
                        "temperature": 0.0,
                        "base_url": "https://api.deepseek.com",
                        "timeout_seconds": 30,
                        "max_tokens": None,
                    }
                )
                result = extractor("pdf text", "prompt")

        self.assertEqual(result["meta"]["title"], "cfg")

    def test_task_callable_retries_after_timeout(self):
        calls = {"count": 0}

        def fake_post(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise httpx.ReadTimeout("timed out")
            return _FakeHttpResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "emit_result",
                                            "arguments": json.dumps({"value": "ok"}),
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            )

        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=False):
            with mock.patch("backend.app.llm_runtime.httpx.post", side_effect=fake_post):
                with mock.patch("backend.app.llm_runtime.time.sleep", return_value=None):
                    callable_fn = llm_runtime.make_task_callable(
                        "planner",
                        {
                            "provider": "deepseek",
                            "model": "deepseek-v4-pro",
                            "temperature": 0.1,
                            "base_url": "https://api.deepseek.com",
                            "timeout_seconds": 20,
                            "retry_attempts": 2,
                            "retry_backoff_seconds": 0.01,
                            "max_tokens": None,
                        },
                    )
                    result = callable_fn("Planner prompt", [{"name": "emit_result", "parameters": {"type": "object"}}], {"user_query": "hi"})

        self.assertEqual(result["value"], "ok")
        self.assertEqual(calls["count"], 2)

    def test_task_callable_retries_after_retryable_http_status(self):
        calls = {"count": 0}

        class _RetryableResponse(_FakeHttpResponse):
            def raise_for_status(self):
                raise httpx.HTTPStatusError("too many requests", request=None, response=self)

        def fake_post(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return _RetryableResponse({"error": "rate limit"}, status_code=429)
            return _FakeHttpResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {
                                        "function": {
                                            "name": "emit_result",
                                            "arguments": json.dumps({"value": "ok"}),
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            )

        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=False):
            with mock.patch("backend.app.llm_runtime.httpx.post", side_effect=fake_post):
                with mock.patch("backend.app.llm_runtime.time.sleep", return_value=None):
                    callable_fn = llm_runtime.make_task_callable(
                        "planner",
                        {
                            "provider": "deepseek",
                            "model": "deepseek-v4-pro",
                            "temperature": 0.1,
                            "base_url": "https://api.deepseek.com",
                            "timeout_seconds": 20,
                            "retry_attempts": 2,
                            "retry_backoff_seconds": 0.01,
                            "max_tokens": None,
                        },
                    )
                    result = callable_fn("Planner prompt", [{"name": "emit_result", "parameters": {"type": "object"}}], {"user_query": "hi"})

        self.assertEqual(result["value"], "ok")
        self.assertEqual(calls["count"], 2)

    def test_answer_generation_accepts_plain_text_content_without_tool_call(self):
        def fake_post(*args, **kwargs):
            return _FakeHttpResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "請先觀察這段經文中的命令、榜樣與操練重點。",
                            }
                        }
                    ]
                }
            )

        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "secret"}, clear=False):
            with mock.patch("backend.app.llm_runtime.httpx.post", side_effect=fake_post):
                callable_fn = llm_runtime.make_task_callable(
                    "answer_generation",
                    {
                        "provider": "deepseek",
                        "model": "deepseek-v4-flash",
                        "temperature": 0.2,
                        "base_url": "https://api.deepseek.com",
                        "timeout_seconds": 20,
                        "retry_attempts": 2,
                        "retry_backoff_seconds": 0.01,
                        "max_tokens": None,
                    },
                )
                result = callable_fn("Answer prompt", [{"name": "create_final_answer", "parameters": {"type": "object"}}], {"user_query": "hi"})

        self.assertEqual(result["content"], "請先觀察這段經文中的命令、榜樣與操練重點。")
        self.assertEqual(result["citations"], [])
        self.assertEqual(result["missing_infoTypes"], [])


if __name__ == "__main__":
    unittest.main()
