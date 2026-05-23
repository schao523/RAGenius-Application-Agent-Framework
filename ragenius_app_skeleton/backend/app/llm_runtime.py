"""Runtime LLM resolver and OpenAI-compatible function-calling client.

This module is intentionally provider-thin. Builder settings choose task-level
models, while secrets/base URLs remain in environment variables.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Callable, Dict, Optional

import httpx


logger = logging.getLogger(__name__)


TASK_MODEL_KEYS = {
    "planner": "planner",
    "planner_hybrid": "planner",
    "answer_generation": "answer_generation",
    "adapter_generation": "adapter_generation",
    "evidence_analysis": "evidence_analysis",
    "config_extraction_fallback": "config_extraction_fallback",
    "instruction_understanding_compile": "instruction_understanding_compile",
    "instruction_understanding_review": "instruction_understanding_review",
    "instruction_understanding_revision": "instruction_understanding_revision",
}

TASK_CONTEXT_LABELS = {
    "planner": "planner output generation",
    "planner_hybrid": "hybrid planner decision generation",
    "answer_generation": "final answer generation",
    "adapter_generation": "adapter draft generation",
    "evidence_analysis": "evidence coverage analysis",
    "config_extraction_fallback": "config extraction fallback",
    "instruction_understanding_compile": "instruction understanding semantic compilation",
    "instruction_understanding_review": "instruction understanding review",
    "instruction_understanding_revision": "instruction understanding revision",
}

INSTRUCTION_UNDERSTANDING_TASKS = {
    "instruction_understanding_compile",
    "instruction_understanding_review",
    "instruction_understanding_revision",
}

USER_VISIBLE_TASKS = (
    "planner",
    "planner_hybrid",
    "answer_generation",
    "adapter_generation",
    "evidence_analysis",
    "config_extraction_fallback",
)


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _extract_llm_settings(state: Dict[str, Any]) -> Dict[str, Any]:
    config_json = state.get("config_json", {})
    if isinstance(config_json, dict):
        meta = config_json.get("meta", {})
        if isinstance(meta, dict):
            llm_settings = meta.get("llm_settings")
            if isinstance(llm_settings, dict):
                return llm_settings
    return {}


def _task_temperature(llm_settings: Dict[str, Any], task: str) -> float:
    task_temps = llm_settings.get("temperature")
    if isinstance(task_temps, dict):
        value = task_temps.get(task)
        if value is not None:
            return float(value)
        if task in INSTRUCTION_UNDERSTANDING_TASKS:
            fallback_value = task_temps.get("adapter_generation")
            if fallback_value is not None:
                return float(fallback_value)
            fallback_value = task_temps.get("planner")
            if fallback_value is not None:
                return float(fallback_value)
    value = llm_settings.get("temperature")
    if value is not None and not isinstance(value, dict):
        return float(value)
    return 0.2


def resolve_task_model(llm_settings: Dict[str, Any], task: str) -> Optional[Dict[str, Any]]:
    provider = llm_settings.get("provider")
    if not provider:
        return None

    models = llm_settings.get("models")
    model_name = None
    if isinstance(models, dict):
        model_name = models.get(TASK_MODEL_KEYS.get(task, task))
        if model_name is None and task in INSTRUCTION_UNDERSTANDING_TASKS:
            model_name = models.get("adapter_generation") or models.get("planner")

    if not model_name:
        return None

    base_url = (
        llm_settings.get("base_url")
        or os.environ.get("RAGENIUS_LLM_BASE_URL")
        or os.environ.get("DEEPSEEK_BASE_URL")
        or "https://api.deepseek.com"
    )
    timeout_seconds = int(
        llm_settings.get("timeout_seconds")
        or os.environ.get("RAGENIUS_LLM_TIMEOUT_SECONDS")
        or 120
    )
    retry_attempts = int(
        llm_settings.get("retry_attempts")
        or os.environ.get("RAGENIUS_LLM_RETRY_ATTEMPTS")
        or 2
    )
    retry_backoff_seconds = float(
        llm_settings.get("retry_backoff_seconds")
        or os.environ.get("RAGENIUS_LLM_RETRY_BACKOFF_SECONDS")
        or 1.5
    )
    max_tokens = llm_settings.get("max_tokens")
    ca_bundle = llm_settings.get("ca_bundle") or os.environ.get("RAGENIUS_LLM_CA_BUNDLE")
    ssl_verify_value = llm_settings.get("ssl_verify")
    if ssl_verify_value is None:
        ssl_verify_value = _env_flag("RAGENIUS_LLM_SSL_VERIFY", True)
    elif isinstance(ssl_verify_value, str):
        ssl_verify_value = str(ssl_verify_value).strip().lower() not in {"0", "false", "no", "off"}
    trust_env = llm_settings.get("trust_env")
    if trust_env is None:
        trust_env = _env_flag("RAGENIUS_LLM_TRUST_ENV", False)
    elif isinstance(trust_env, str):
        trust_env = str(trust_env).strip().lower() not in {"0", "false", "no", "off"}
    return {
        "provider": str(provider),
        "model": str(model_name),
        "temperature": _task_temperature(llm_settings, task),
        "base_url": str(base_url).rstrip("/"),
        "timeout_seconds": timeout_seconds,
        "retry_attempts": retry_attempts,
        "retry_backoff_seconds": retry_backoff_seconds,
        "max_tokens": int(max_tokens) if max_tokens is not None else None,
        "ssl_verify": ssl_verify_value,
        "trust_env": bool(trust_env),
        "ca_bundle": str(ca_bundle) if ca_bundle else None,
    }


def configured_task_models(state: Dict[str, Any], tasks: tuple[str, ...] = USER_VISIBLE_TASKS) -> Dict[str, Dict[str, Any]]:
    llm_settings = _extract_llm_settings(state)
    resolved: Dict[str, Dict[str, Any]] = {}
    for task in tasks:
        config = resolve_task_model(llm_settings, task)
        if config is None:
            continue
        resolved[task] = {
            "provider": config.get("provider"),
            "model": config.get("model"),
            "temperature": config.get("temperature"),
        }
    return resolved


def build_task_binding(state: Dict[str, Any], task: str) -> Dict[str, Any]:
    llm_settings = _extract_llm_settings(state)
    config = resolve_task_model(llm_settings, task)
    diagnostics: Dict[str, Any] = {
        "task": task,
        "provider": config.get("provider") if isinstance(config, dict) else None,
        "model": config.get("model") if isinstance(config, dict) else None,
        "temperature": config.get("temperature") if isinstance(config, dict) else None,
        "selected_source": "default_fallback" if task in {"planner", "planner_hybrid", "answer_generation"} else "unavailable",
    }
    if config is None:
        diagnostics["fallback_reason"] = "no_task_model_configured"
        return {"callable": None, "config": None, "diagnostics": diagnostics}
    try:
        callable_ = make_task_callable(task, config)
    except RuntimeError as exc:
        diagnostics["fallback_reason"] = str(exc)
        return {"callable": None, "config": config, "diagnostics": diagnostics}
    diagnostics["selected_source"] = "builder_task_model"
    return {"callable": callable_, "config": config, "diagnostics": diagnostics}


def _api_key_for_provider(provider: str) -> str | None:
    provider_key = provider.strip().lower()
    if provider_key == "deepseek":
        return os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("RAGENIUS_LLM_API_KEY")
    if provider_key == "openai":
        return os.environ.get("OPENAI_API_KEY") or os.environ.get("RAGENIUS_LLM_API_KEY")
    return os.environ.get("RAGENIUS_LLM_API_KEY")


def _normalize_tools(tools: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    normalized: list[Dict[str, Any]] = []
    for tool in tools:
        if "type" in tool and "function" in tool:
            normalized.append(tool)
            continue
        normalized.append({"type": "function", "function": tool})
    return normalized


def _build_messages(prompt: str, context: Dict[str, Any]) -> list[Dict[str, str]]:
    context_blob = json.dumps(context, ensure_ascii=False, indent=2)
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Context JSON:\n{context_blob}"},
    ]


def _extract_balanced_json_object(text: str) -> str | None:
    if not isinstance(text, str):
        return None
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _decode_tool_arguments(arguments: str) -> Dict[str, Any]:
    try:
        decoded = json.loads(arguments)
    except json.JSONDecodeError as exc:
        recovered = _extract_balanced_json_object(arguments)
        if recovered:
            decoded = json.loads(recovered)
        else:
            raise exc
    if not isinstance(decoded, dict):
        raise RuntimeError("LLM tool call arguments must decode to an object.")
    return decoded


def _extract_tool_arguments(payload: Dict[str, Any]) -> Dict[str, Any]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("LLM response contained no choices.")

    message = choices[0].get("message", {})
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list) or not tool_calls:
        return _extract_json_object_from_content(payload)

    function = tool_calls[0].get("function", {})
    arguments = function.get("arguments")
    if not isinstance(arguments, str):
        raise RuntimeError("LLM tool call arguments were missing.")
    try:
        return _decode_tool_arguments(arguments)
    except (json.JSONDecodeError, RuntimeError):
        return _extract_json_object_from_content(payload)


def _extract_message_text(payload: Dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message", {})
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    if not isinstance(content, str):
        return ""
    return content.strip()


def _extract_answer_generation_output(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return _extract_tool_arguments(payload)
    except Exception as exc:
        text = _extract_message_text(payload)
        if text:
            logger.warning("DeepSeek answer_generation returned plain text without usable tool payload; accepting text content directly.")
            return {
                "content": text,
                "citations": [],
                "missing_infoTypes": [],
            }
        raise exc


def _should_retry_status(status_code: int) -> bool:
    return status_code in {408, 409, 429, 500, 502, 503, 504}


def _post_json(
    url: str,
    headers: Dict[str, str],
    body: Dict[str, Any],
    timeout_seconds: int,
    *,
    retry_attempts: int = 2,
    retry_backoff_seconds: float = 1.5,
    ssl_verify: bool | str = True,
    trust_env: bool = False,
) -> Dict[str, Any]:
    attempts = max(1, int(retry_attempts))
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            response = httpx.post(
                url,
                headers=headers,
                json=body,
                timeout=timeout_seconds,
                trust_env=trust_env,
                verify=ssl_verify,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if attempt < attempts - 1 and _should_retry_status(exc.response.status_code):
                time.sleep(retry_backoff_seconds * (attempt + 1))
                continue
            detail = exc.response.text
            raise RuntimeError(f"LLM HTTP error {exc.response.status_code}: {detail}") from exc
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(retry_backoff_seconds * (attempt + 1))
                continue
            raise RuntimeError(f"LLM connection failed: {exc}") from exc
        except httpx.HTTPError as exc:
            last_exc = exc
            raise RuntimeError(f"LLM connection failed: {exc}") from exc
    if last_exc is not None:
        raise RuntimeError(f"LLM connection failed: {last_exc}") from last_exc
    raise RuntimeError("LLM connection failed: unknown client error")


def _extract_json_object_from_content(payload: Dict[str, Any]) -> Dict[str, Any]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("LLM response contained no choices.")
    message = choices[0].get("message", {})
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("LLM response contained no text content.")
    match = re.search(r"\{.*\}", content, flags=re.DOTALL)
    if not match:
        raise RuntimeError("LLM text response did not contain a JSON object.")
    decoded = json.loads(match.group(0))
    if not isinstance(decoded, dict):
        raise RuntimeError("LLM JSON content must decode to an object.")
    return decoded


def make_task_callable(task: str, config: Dict[str, Any]) -> Callable[[str, list, Dict[str, Any]], Dict[str, Any]]:
    provider = config["provider"]
    api_key = _api_key_for_provider(provider)
    if not api_key:
        raise RuntimeError(f"{provider} API key is not configured.")

    endpoint = f"{config['base_url']}/chat/completions"
    default_temperature = float(config.get("temperature", 0.2))
    timeout_seconds = int(config.get("timeout_seconds", 60))
    retry_attempts = int(config.get("retry_attempts", 2))
    retry_backoff_seconds = float(config.get("retry_backoff_seconds", 1.5))
    max_tokens = config.get("max_tokens")
    ca_bundle = config.get("ca_bundle")
    ssl_verify = ca_bundle or bool(config.get("ssl_verify", True))
    trust_env = bool(config.get("trust_env", False))
    provider_name = str(provider).strip().lower()
    tool_choice = "auto" if provider_name == "deepseek" else "required"

    def _call(prompt: str, tools: list, context: Dict[str, Any]) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "model": config["model"],
            "messages": _build_messages(prompt, context),
            "tools": _normalize_tools(tools),
            "tool_choice": tool_choice,
            "temperature": default_temperature,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        payload = _post_json(
            endpoint,
            {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            body,
            timeout_seconds,
            retry_attempts=retry_attempts,
            retry_backoff_seconds=retry_backoff_seconds,
            ssl_verify=ssl_verify,
            trust_env=trust_env,
        )
        if task == "answer_generation":
            return _extract_answer_generation_output(payload)
        return _extract_tool_arguments(payload)

    _call.__name__ = f"{task}_llm_callable"
    return _call


def make_json_extractor_callable(config: Dict[str, Any]) -> Callable[[str, str], Dict[str, Any]]:
    provider = config["provider"]
    api_key = _api_key_for_provider(provider)
    if not api_key:
        raise RuntimeError(f"{provider} API key is not configured.")

    endpoint = f"{config['base_url']}/chat/completions"
    temperature = float(config.get("temperature", 0.0))
    timeout_seconds = int(config.get("timeout_seconds", 60))
    retry_attempts = int(config.get("retry_attempts", 2))
    retry_backoff_seconds = float(config.get("retry_backoff_seconds", 1.5))
    max_tokens = config.get("max_tokens")
    ca_bundle = config.get("ca_bundle")
    ssl_verify = ca_bundle or bool(config.get("ssl_verify", True))
    trust_env = bool(config.get("trust_env", False))

    def _call(pdf_text: str, prompt_text: str) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "model": config["model"],
            "messages": [
                {"role": "system", "content": prompt_text},
                {"role": "user", "content": f"Return only one JSON object.\n\nPDF text:\n{pdf_text}"},
            ],
            "temperature": temperature,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        payload = _post_json(
            endpoint,
            {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            body,
            timeout_seconds,
            retry_attempts=retry_attempts,
            retry_backoff_seconds=retry_backoff_seconds,
            ssl_verify=ssl_verify,
            trust_env=trust_env,
        )
        return _extract_json_object_from_content(payload)

    _call.__name__ = "config_extraction_llm_callable"
    return _call


def maybe_build_task_callable(state: Dict[str, Any], task: str) -> Optional[Callable[[str, list, Dict[str, Any]], Dict[str, Any]]]:
    return build_task_binding(state, task).get("callable")


def maybe_build_config_extractor(state: Dict[str, Any]) -> Optional[Callable[[str, str], Dict[str, Any]]]:
    llm_settings = _extract_llm_settings(state)
    config = resolve_task_model(llm_settings, "config_extraction_fallback")
    if config is None:
        return None
    try:
        return make_json_extractor_callable(config)
    except RuntimeError:
        return None


def maybe_build_adapter_callable(state: Dict[str, Any]) -> Optional[Callable[[str, list, Dict[str, Any]], Dict[str, Any]]]:
    return maybe_build_task_callable(state, "adapter_generation")


__all__ = [
    "TASK_CONTEXT_LABELS",
    "USER_VISIBLE_TASKS",
    "build_task_binding",
    "configured_task_models",
    "make_json_extractor_callable",
    "make_task_callable",
    "maybe_build_adapter_callable",
    "maybe_build_config_extractor",
    "maybe_build_task_callable",
    "resolve_task_model",
]
