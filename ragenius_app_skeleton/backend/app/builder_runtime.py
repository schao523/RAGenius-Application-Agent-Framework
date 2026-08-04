"""Deterministic runtime derivation from builder app/instructions/settings."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List

from backend.schemas import validate_adapter_json, validate_config_json
from ragenius_builder.flask_scaffold.storage import DEFAULT_APP_CONFIG_SETTINGS


LLM_TASK_KEYS = (
    "planner",
    "answer_generation",
    "adapter_generation",
    "evidence_analysis",
    "config_extraction_fallback",
    "instruction_understanding_compile",
    "instruction_understanding_review",
    "instruction_understanding_revision",
)

LLM_RUNTIME_OPTION_KEYS = (
    "max_tokens",
    "deployment",
    "base_url",
    "timeout_seconds",
    "retry_attempts",
    "retry_backoff_seconds",
    "ssl_verify",
    "trust_env",
    "ca_bundle",
)


def _clean_lines(lines: Iterable[str]) -> list[str]:
    cleaned: list[str] = []
    for raw in lines:
        line = str(raw or "").strip()
        if not line:
            continue
        if line.startswith(("- ", "* ", "+ ")):
            line = line[2:].strip()
        cleaned.append(line)
    return cleaned


def _extract_section_lines(markdown: str, headings: Iterable[str]) -> list[str]:
    heading_names = {h.strip().lower() for h in headings}
    current: str | None = None
    bucket: list[str] = []
    for raw in (markdown or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            title = line.lstrip("#").strip().lower()
            current = title
            continue
        if current is not None and current in heading_names:
            bucket.append(line)
    return _clean_lines(bucket)


def _default_mode_detection(starter_questions: list[str]) -> list[dict[str, Any]]:
    triggers = [q.strip() for q in starter_questions if q.strip()][:4]
    if not triggers:
        triggers = ["question", "ask", "explain"]
    return [{"mode": "default", "triggers": triggers, "priority": 1}]


def _default_llm_settings() -> dict[str, Any]:
    return deepcopy(DEFAULT_APP_CONFIG_SETTINGS.get("llm", {}))


def _merge_task_mapping(
    target: dict[str, Any],
    value: Any,
) -> None:
    if not isinstance(value, dict):
        return
    for key in LLM_TASK_KEYS:
        if value.get(key) is not None:
            target[key] = value[key]


def _legacy_task_models(settings: dict[str, Any]) -> dict[str, Any]:
    legacy_models: dict[str, Any] = {}
    generic_model = settings.get("model")
    if generic_model is not None:
        for key in LLM_TASK_KEYS:
            legacy_models[key] = generic_model

    planner_model = settings.get("planner_model")
    if planner_model is not None:
        legacy_models["planner"] = planner_model
    answer_model = settings.get("answer_model")
    if answer_model is not None:
        legacy_models["answer_generation"] = answer_model

    for key in LLM_TASK_KEYS:
        flat_value = settings.get(f"{key}_model")
        if flat_value is not None:
            legacy_models[key] = flat_value

    instruction_fallback = legacy_models.get("adapter_generation") or legacy_models.get("planner")
    if instruction_fallback is not None:
        for key in (
            "instruction_understanding_compile",
            "instruction_understanding_review",
            "instruction_understanding_revision",
        ):
            legacy_models.setdefault(key, instruction_fallback)
    return legacy_models


def _legacy_task_temperatures(settings: dict[str, Any]) -> dict[str, Any]:
    legacy_temperatures: dict[str, Any] = {}
    raw_temperature = settings.get("temperature")
    if isinstance(raw_temperature, dict):
        _merge_task_mapping(legacy_temperatures, raw_temperature)
    elif raw_temperature is not None:
        for key in LLM_TASK_KEYS:
            legacy_temperatures[key] = raw_temperature
    return legacy_temperatures


def _derive_llm_settings(settings: dict[str, Any]) -> dict[str, Any]:
    normalized = _default_llm_settings()
    explicit = settings.get("llm") if isinstance(settings.get("llm"), dict) else {}

    provider = explicit.get("provider")
    if provider is None:
        provider = settings.get("provider")
    if provider is not None:
        normalized["provider"] = provider

    models = normalized.setdefault("models", {})
    if not isinstance(models, dict):
        models = {}
        normalized["models"] = models
    _merge_task_mapping(models, _legacy_task_models(settings))
    _merge_task_mapping(models, explicit.get("models"))

    temperatures = normalized.setdefault("temperature", {})
    if not isinstance(temperatures, dict):
        temperatures = {}
        normalized["temperature"] = temperatures
    _merge_task_mapping(temperatures, _legacy_task_temperatures(settings))
    _merge_task_mapping(temperatures, explicit.get("temperature"))

    for key in LLM_RUNTIME_OPTION_KEYS:
        value = explicit.get(key)
        if value is None:
            value = settings.get(key)
        if value is not None:
            normalized[key] = value

    return normalized


def derive_builder_config_json(
    app_record: Dict[str, Any],
    settings_record: Dict[str, Any] | None,
    instructions_record: Dict[str, Any] | None,
) -> Dict[str, Any]:
    app_settings = dict((settings_record or {}).get("config_settings") or {})
    instructions_text = str((instructions_record or {}).get("content") or "")
    starter_questions = list(app_record.get("starter_questions") or [])
    llm_settings = _derive_llm_settings(app_settings)

    goals = _extract_section_lines(instructions_text, ("goals", "goal", "mission"))
    if not goals:
        goals = [q for q in starter_questions if q]
    if not goals:
        goals = [f"Assist users of application '{app_record.get('name', 'Application')}'."]

    role_mission = _extract_section_lines(instructions_text, ("role", "identity", "mission", "purpose"))
    if not role_mission and app_record.get("description"):
        role_mission = [str(app_record["description"])]

    coverage_rules = _extract_section_lines(instructions_text, ("coverage", "scope"))
    if not coverage_rules:
        coverage_rules = [
            f"Answer within the scope of builder application '{app_record.get('name', 'Application')}'.",
            "Do not mix content from other applications.",
        ]

    retrieval_rules = _extract_section_lines(instructions_text, ("retrieval", "retrieval rules", "sources"))
    retrieval_rules = retrieval_rules or ["Use uploaded knowledge for this application only."]
    if app_settings.get("language"):
        retrieval_rules.append(f"Prefer retrieval matching language '{app_settings['language']}'.")

    style_rules = _extract_section_lines(instructions_text, ("style", "tone", "writing style"))
    style_rules = style_rules or ["Be clear, grounded, and concise."]

    safety_rules = _extract_section_lines(instructions_text, ("safety", "guardrails", "boundaries"))
    safety_rules = safety_rules or ["Do not fabricate unsupported claims."]

    step_skeletons = app_settings.get("step_skeletons")
    if not isinstance(step_skeletons, list):
        step_skeletons = [{"intent_or_mode": "qa", "steps": ["understand", "retrieve", "answer"]}]

    modules = []
    if llm_settings:
        modules.append(
            {
                "name": "llm_runtime",
                "triggers": ["query"],
                "behavior": ", ".join(f"{k}={v}" for k, v in llm_settings.items()),
            }
        )

    controls = app_settings.get("controls_commands")
    if not isinstance(controls, list):
        controls = []

    config_json = {
        "meta": {
            "title": str(app_record.get("name") or "Builder Application"),
            "domain_hint": str(app_record.get("slug") or "general"),
            "version_hint": (instructions_record or {}).get("version"),
            "author": "ragenius_builder",
            "builder_app_id": app_record.get("id"),
            "builder_settings": app_settings,
            "llm_settings": llm_settings,
        },
        "role": {
            "name": str(app_record.get("name") or "assistant"),
            "mission": role_mission,
        },
        "goals": goals,
        "mode_detection": _default_mode_detection(starter_questions),
        "coverage_rules": coverage_rules,
        "retrieval_rules": retrieval_rules,
        "style_rules": style_rules,
        "safety_rules": safety_rules,
        "step_skeletons": step_skeletons,
        "modules": modules,
        "controls_commands": controls,
    }
    validate_config_json(config_json)
    return config_json


def derive_builder_adapter_json(app_record: Dict[str, Any], config_json: Dict[str, Any]) -> Dict[str, Any]:
    meta = config_json.get("meta", {}) if isinstance(config_json.get("meta"), dict) else {}
    builder_settings = meta.get("builder_settings", {}) if isinstance(meta.get("builder_settings"), dict) else {}
    llm_guardrails = list(config_json.get("style_rules", [])) + list(config_json.get("safety_rules", []))
    language = str(builder_settings.get("language") or "en")

    adapter_json = {
        "domain": str(app_record.get("slug") or "general"),
        "version": 1,
        "intent_overrides": [
            {
                "alias_intent": "qa",
                "triggers_from_config": list(config_json.get("goals", []))[:5] or ["question"],
                "maps_to_base_intent": "qa",
            }
        ],
        "step_skeleton_mapping": {
            "use_config_step_skeletons": True,
            "default_mode": "default",
            "step_waiting_policy": {"wait_for_user_each_step": False, "max_questions_per_turn": 3},
        },
        "info_type_to_tags": {"fact": ["builder", str(app_record.get("slug") or "general")]},
        "retrieval_defaults": {"top_k_range": [1, 5], "language": language},
        "plugin_activation_rules_file": None,
        "llm_guardrails_append": llm_guardrails[:10],
    }
    validate_adapter_json(adapter_json)
    return adapter_json
