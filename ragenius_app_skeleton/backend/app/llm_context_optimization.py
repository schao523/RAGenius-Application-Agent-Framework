"""Lossless, opt-in context projection and token-accounting helpers."""

from __future__ import annotations

import copy
import json
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Collection, Literal, Mapping


ContextMode = Literal["off", "diagnostic", "compact"]
EvidenceMode = Literal["auto", "deterministic", "llm_required"]

TASK_BUDGETS = {
    "planner": 8_000,
    "planner_hybrid": 8_000,
    "evidence_analysis": 3_000,
    "answer_generation": 12_000,
    "safe_answer": 12_000,
}
TURN_TOKEN_BUDGET = 25_000

EVIDENCE_IDENTITY_KEYS = (
    "doc_id",
    "source_id",
    "resource_id",
    "chunk_id",
    "title",
    "filename",
    "location",
    "version",
    "score",
    "retrieval_domain",
    "retrieval_query",
    "metadata",
    "snippet",
)


@dataclass(frozen=True)
class ContextOptimizationResult:
    context: dict[str, Any]
    diagnostics: dict[str, Any]
    budget_exceeded: bool = False
    skip_llm: bool = False
    skip_reason: str | None = None


def normal_query_optimization_eligible(state: Mapping[str, Any]) -> bool:
    return bool(
        str(state.get("turn_input_type") or "").strip().lower() == "text_query"
        and not bool(state.get("pending_upload_analysis"))
        and not [item for item in state.get("session_upload_event_ids", []) or [] if str(item or "").strip()]
    )


def _enabled(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def context_optimization_mode() -> ContextMode:
    if not _enabled(os.environ.get("RAGENIUS_LLM_CONTEXT_OPTIMIZATION")):
        return "off"
    mode = str(os.environ.get("RAGENIUS_LLM_CONTEXT_OPTIMIZATION_MODE") or "off").strip().lower()
    return mode if mode in {"off", "diagnostic", "compact"} else "off"  # type: ignore[return-value]


def evidence_analysis_mode() -> EvidenceMode:
    mode = str(os.environ.get("RAGENIUS_LLM_EVIDENCE_ANALYSIS_MODE") or "auto").strip().lower()
    return mode if mode in {"auto", "deterministic", "llm_required"} else "auto"  # type: ignore[return-value]


def normalize_tools(tools: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for tool in tools if isinstance(tools, list) else []:
        if not isinstance(tool, dict):
            continue
        value = copy.deepcopy(tool)
        if "type" in value and "function" in value:
            normalized.append(value)
        else:
            normalized.append({"type": "function", "function": value})
    return normalized


def build_context_messages(prompt: str, context: Mapping[str, Any]) -> list[dict[str, str]]:
    context_blob = json.dumps(dict(context), ensure_ascii=False, indent=2)
    return [
        {"role": "system", "content": str(prompt)},
        {"role": "user", "content": f"Context JSON:\n{context_blob}"},
    ]


def estimate_task_input_tokens(prompt: str, tools: Any, context: Mapping[str, Any]) -> dict[str, Any]:
    messages = build_context_messages(prompt, context)
    payload = {"messages": messages, "tools": normalize_tools(tools)}
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return {
        "tokens": math.ceil(len(serialized) / 4),
        "bytes": len(serialized.encode("utf-8")),
        "messages": messages,
        "serialized_payload": serialized,
        "estimator_name": "chars_per_token",
        "estimator_version": "v1",
    }


def optimize_task_context(
    *,
    task: str,
    prompt: str,
    tools: Any,
    full_context: Mapping[str, Any],
    compact_context: Mapping[str, Any],
    eligible: bool,
    mode: ContextMode,
    budget: int | None = None,
) -> ContextOptimizationResult:
    full = copy.deepcopy(dict(full_context))
    compact = copy.deepcopy(dict(compact_context))
    full_estimate = estimate_task_input_tokens(prompt, tools, full)
    compact_estimate = estimate_task_input_tokens(prompt, tools, compact)
    use_compact = bool(eligible and mode == "compact")
    outbound = compact if use_compact else full
    outbound_estimate = compact_estimate if use_compact else full_estimate
    limit = int(budget or TASK_BUDGETS.get(task, 0))
    saved = max(0, int(full_estimate["tokens"]) - int(compact_estimate["tokens"]))
    saving_percent = round((saved / full_estimate["tokens"] * 100), 2) if full_estimate["tokens"] else 0.0
    exceeded = bool(limit and int(outbound_estimate["tokens"]) > limit)
    diagnostics = {
        "task": task,
        "context_mode": "compact" if use_compact else "full",
        "context_bytes": int(outbound_estimate["bytes"]),
        "estimated_input_tokens": int(outbound_estimate["tokens"]),
        "actual_full_tokens": int(full_estimate["tokens"]),
        "compact_candidate_tokens": int(compact_estimate["tokens"]),
        "actual_outbound_tokens": int(outbound_estimate["tokens"]),
        "estimated_tokens_saved": saved,
        "estimated_saving_percent": saving_percent,
        "estimator_name": "chars_per_token",
        "estimator_version": "v1",
        "top_level_keys": sorted(outbound.keys()),
        "budget_limit_tokens": limit,
        "budget_exceeded": exceeded,
        "compaction_applied": use_compact,
        "compaction_reasons": [],
    }
    return ContextOptimizationResult(context=outbound, diagnostics=diagnostics, budget_exceeded=exceeded)


def optimize_context_for_state(
    state: dict[str, Any],
    *,
    task: str,
    prompt: str,
    tools: Any,
    full_context: Mapping[str, Any],
    compact_context: Mapping[str, Any],
) -> ContextOptimizationResult:
    eligible = bool(state.get("_context_optimization_eligible"))
    mode = str(state.get("_context_optimization_mode") or "off").strip().lower()
    if mode not in {"off", "diagnostic", "compact"}:
        mode = "off"
    compact_candidate, compaction_reasons = apply_ordered_compaction(
        task,
        compact_context,
        TASK_BUDGETS.get(task, 0),
    )
    result = optimize_task_context(
        task=task,
        prompt=prompt,
        tools=tools,
        full_context=full_context,
        compact_context=compact_candidate,
        eligible=eligible,
        mode=mode,  # type: ignore[arg-type]
    )
    result.diagnostics["compaction_reasons"] = compaction_reasons
    selected_models = (
        state.get("_task_model_diagnostics", {}).get("selected_task_models", {})
        if isinstance(state.get("_task_model_diagnostics"), dict)
        else {}
    )
    model_key = "answer_generation" if task == "safe_answer" else task
    selected_model = selected_models.get(model_key, {}) if isinstance(selected_models, dict) else {}
    if isinstance(selected_model, dict):
        for key in ("provider", "model"):
            if selected_model.get(key) is not None:
                result.diagnostics[key] = selected_model[key]
    outbound_context = result.context
    result.diagnostics["evidence_count"] = sum(
        len(outbound_context.get(key, []))
        for key in ("compressed_evidence", "knowledge_evidence", "instruction_evidence", "template_evidence", "session_upload_evidence")
        if isinstance(outbound_context.get(key), list)
    )
    history = outbound_context.get("chat_history")
    result.diagnostics["chat_history_turn_count"] = math.ceil(len(history) / 2) if isinstance(history, list) else 0
    if result.budget_exceeded:
        result.diagnostics["overflow_reason"] = "all_permitted_compaction_stages_exhausted"
    diagnostics = copy.deepcopy(state.get("_context_optimization_diagnostics")) if isinstance(state.get("_context_optimization_diagnostics"), dict) else {}
    calls = diagnostics.get("calls") if isinstance(diagnostics.get("calls"), list) else []
    calls.append(copy.deepcopy(result.diagnostics))
    diagnostics["calls"] = calls
    diagnostics["eligible"] = eligible
    diagnostics["mode"] = mode
    state["_context_optimization_diagnostics"] = diagnostics
    state["_turn_token_accounting"] = add_task_token_accounting(state.get("_turn_token_accounting"), task, result.diagnostics)
    return result


def add_task_token_accounting(accounting: Any, task: str, diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(accounting) if isinstance(accounting, dict) else {}
    calls = result.get("calls")
    if not isinstance(calls, list):
        calls = []
    calls.append({"task": task, **copy.deepcopy(dict(diagnostics))})
    result["calls"] = calls
    result["call_count"] = len(calls)
    result["turn_estimated_outbound_tokens"] = sum(int(call.get("actual_outbound_tokens") or 0) for call in calls if isinstance(call, dict))
    result["turn_actual_full_tokens"] = sum(int(call.get("actual_full_tokens") or 0) for call in calls if isinstance(call, dict))
    result["turn_compact_candidate_tokens"] = sum(int(call.get("compact_candidate_tokens") or 0) for call in calls if isinstance(call, dict))
    result["turn_estimated_tokens_saved"] = max(0, result["turn_actual_full_tokens"] - result["turn_compact_candidate_tokens"])
    result["turn_estimated_saving_percent"] = (
        round(result["turn_estimated_tokens_saved"] / result["turn_actual_full_tokens"] * 100, 2)
        if result["turn_actual_full_tokens"]
        else 0.0
    )
    return result


def finalize_task_model_diagnostics(state: Mapping[str, Any]) -> dict[str, Any]:
    """Build the same immutable diagnostics payload for live and persisted turns."""
    diagnostic_keys = (
        "_task_model_diagnostics",
        "_context_optimization_diagnostics",
        "_turn_token_accounting",
    )
    if not any(isinstance(state.get(key), dict) for key in diagnostic_keys):
        return {}

    result = (
        copy.deepcopy(state.get("_task_model_diagnostics"))
        if isinstance(state.get("_task_model_diagnostics"), dict)
        else {}
    )
    context_diagnostics = state.get("_context_optimization_diagnostics")
    finalized_context = (
        copy.deepcopy(context_diagnostics) if isinstance(context_diagnostics, dict) else {}
    )
    finalized_context.setdefault("eligible", bool(state.get("_context_optimization_eligible")))
    finalized_context.setdefault("mode", str(state.get("_context_optimization_mode") or "off"))
    result["context_optimization"] = finalized_context
    accounting = state.get("_turn_token_accounting")
    finalized_accounting = copy.deepcopy(accounting) if isinstance(accounting, dict) else {}
    finalized_accounting["budget_limit_tokens"] = TURN_TOKEN_BUDGET
    finalized_accounting["budget_exceeded"] = (
        int(finalized_accounting.get("turn_estimated_outbound_tokens") or 0) > TURN_TOKEN_BUDGET
    )
    result["turn_token_accounting"] = finalized_accounting
    return result


def bounded_chat_history(history: Any, *, max_turns: int) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for item in history if isinstance(history, list) else []:
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = item.get("content")
        if not role or not isinstance(content, str):
            continue
        messages.append({"role": role, "content": content})
    return messages[-max(0, int(max_turns)) * 2 :]


def compact_evidence_items(items: Any, *, limit: int, snippet_limit: int) -> list[dict[str, Any]]:
    evidence = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    ranked = sorted(evidence, key=lambda item: float(item.get("score") or 0), reverse=True)
    result: list[dict[str, Any]] = []
    for item in ranked[: max(0, int(limit))]:
        projected = {key: copy.deepcopy(item[key]) for key in EVIDENCE_IDENTITY_KEYS if key in item}
        if isinstance(projected.get("metadata"), Mapping):
            projected["metadata"] = project_mapping(
                projected["metadata"],
                ("info_type", "info_types", "tags", "mime_type", "size_bytes", "source", "page", "section"),
            )
        if isinstance(projected.get("snippet"), str):
            projected["snippet"] = projected["snippet"][: max(0, int(snippet_limit))]
        result.append(projected)
    return result


def project_mapping(source: Any, allowed_keys: Collection[str]) -> dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}
    return {key: copy.deepcopy(source[key]) for key in allowed_keys if key in source}


def _markdown_sections(text: str) -> list[str]:
    if not text.strip():
        return []
    starts = [match.start() for match in re.finditer(r"(?m)^#{1,6}\s+", text)]
    if not starts:
        return [text.strip()]
    sections: list[str] = []
    if starts[0] > 0 and text[: starts[0]].strip():
        sections.append(text[: starts[0]].strip())
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        sections.append(text[start:end].strip())
    return sections


def semantic_section_compact(text: str, *, active_markers: list[str], max_chars: int) -> str:
    source = str(text or "")
    if len(source) <= max_chars:
        return source
    sections = _markdown_sections(source)
    markers = [str(item).lower() for item in active_markers if str(item).strip()]
    safety_markers = ("safety", "constraint", "guardrail", "must not", "do not")
    required = [section for section in sections if any(marker in section.lower() for marker in markers) or any(marker in section.lower() for marker in safety_markers)]
    selected = list(required)
    for section in sections:
        if section in selected:
            continue
        candidate = "\n\n".join(selected + [section])
        if len(candidate) <= max_chars:
            selected.append(section)
    return "\n\n".join(selected) if selected else (sections[0] if sections else source)


def apply_ordered_compaction(task: str, context: Mapping[str, Any], budget: int) -> tuple[dict[str, Any], list[str]]:
    compact = copy.deepcopy(dict(context))
    stages: list[str] = ["remove_duplicates", "task_projection"]
    max_turns = 6 if task in {"answer_generation", "safe_answer"} else 4
    if "chat_history" in compact:
        compact["chat_history"] = bounded_chat_history(compact.get("chat_history"), max_turns=max_turns)
        stages.append("bounded_chat_history")
    evidence_limit = 8
    snippet_limit = 800 if task in {"answer_generation", "safe_answer"} else 500
    evidence_keys = (
        "compressed_evidence",
        "instruction_evidence",
        "knowledge_evidence",
        "template_evidence",
        "session_upload_evidence",
    )
    for key in evidence_keys:
        if isinstance(compact.get(key), list):
            key_limit = 3 if key == "template_evidence" and task in {"answer_generation", "safe_answer"} else evidence_limit
            compact[key] = compact_evidence_items(compact[key], limit=key_limit, snippet_limit=snippet_limit)
    stages.append("compact_evidence")
    for key in ("instruction_resource_context", "template_resource_context"):
        if isinstance(compact.get(key), list):
            compact[key] = compact_resource_context(compact[key], limit=8, text_limit=2_000)
    if isinstance(compact.get("selected_instruction_block_text"), str):
        block = compact.get("selected_instruction_block") if isinstance(compact.get("selected_instruction_block"), Mapping) else {}
        compact["selected_instruction_block_text"] = semantic_section_compact(
            compact["selected_instruction_block_text"],
            active_markers=[str(block.get("title") or ""), str(block.get("block_id") or "")],
            max_chars=4_000,
        )
    stages.extend(["compact_resource_context", "semantic_instruction_compaction"])
    _ = budget
    return compact, stages


RESOURCE_CONTEXT_ID_KEYS = (
    "doc_id", "source_id", "resource_id", "document_id", "filename", "title", "location", "version", "score",
    "binding_id", "dependency_group_id", "artifact_role", "resource_kind", "resource_role", "load_strategy",
    "source_layer", "step_scope_id", "support_module_id", "retrieval_domain", "metadata",
)


def compact_resource_context(items: Any, *, limit: int, text_limit: int) -> list[dict[str, Any]]:
    values = [item for item in items if isinstance(item, Mapping)] if isinstance(items, list) else []
    result: list[dict[str, Any]] = []
    for item in values[: max(0, int(limit))]:
        projected = project_mapping(item, RESOURCE_CONTEXT_ID_KEYS)
        for text_key in ("content", "text", "snippet", "body_text"):
            if isinstance(item.get(text_key), str):
                projected[text_key] = semantic_section_compact(
                    str(item[text_key]), active_markers=[], max_chars=text_limit
                )
        result.append(projected)
    return result


PLANNER_CONFIG_KEYS = (
    "role", "goals", "mode_detection", "step_skeletons", "style_rules", "safety_rules",
    "retrieval_rules", "coverage_rules", "controls_commands",
)
PLANNER_ADAPTER_KEYS = (
    "intent_overrides", "step_skeleton_mapping", "retrieval_defaults", "retrieval_mapping_rules",
    "info_type_to_tags", "llm_guardrails_append", "planner_guardrails", "use_config_step_skeletons",
)
PLANNER_TEMPLATE_KEYS = (
    "intent_categories", "step_skeletons", "templates", "workflows", "modules", "routing_rules",
    "resource_bindings", "active_binding_ids", "llm_system_prompt",
)
IDENTITY_KEYS = (
    "id", "role_id", "workflow_id", "module_id", "step_id", "block_id", "logic_id", "rule_id",
    "scope_id", "scope_type", "target_scope_id", "target_block_id", "binding_id", "dependency_group_id",
    "artifact_role", "resource_id", "filename", "title", "name", "type", "block_type", "kind", "domain",
    "intent", "intent_type", "alias_intent", "maps_to_base_intent", "trigger", "triggers", "expression",
    "conditions", "priority", "order", "required", "enabled", "steps", "children", "resource_requests",
    "description", "summary", "goal", "purpose", "keywords",
)


def _compact_identity_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_compact_identity_value(item) for item in value]
    if not isinstance(value, Mapping):
        return copy.deepcopy(value)
    projected: dict[str, Any] = {}
    for key in IDENTITY_KEYS:
        if key in value:
            projected_value = _compact_identity_value(value[key])
            if key in {"description", "summary", "goal", "purpose"} and isinstance(projected_value, str):
                projected_value = projected_value[:500]
            projected[key] = projected_value
    return projected


def _project_registry(registry: Any) -> dict[str, Any]:
    projected = project_mapping(registry, PLANNER_TEMPLATE_KEYS)
    for key, value in list(projected.items()):
        if key != "llm_system_prompt":
            projected[key] = _compact_identity_value(value)
    return projected


def _summary_history(state: Mapping[str, Any], *, max_turns: int) -> list[dict[str, Any]]:
    history = bounded_chat_history(state.get("chat_history"), max_turns=max_turns)
    session_state = state.get("session_execution_state") if isinstance(state.get("session_execution_state"), Mapping) else {}
    summary = session_state.get("chat_summary") if isinstance(session_state, Mapping) else None
    if summary:
        history.insert(0, {"role": "system", "content": "Conversation summary: " + json.dumps(summary, ensure_ascii=False)})
    return history


def build_planner_context(state: Mapping[str, Any]) -> dict[str, Any]:
    session_state = state.get("session_execution_state") if isinstance(state.get("session_execution_state"), Mapping) else {}
    active_upload_ids = {
        str(item or "").strip()
        for item in (session_state.get("active_session_upload_ids", []) if isinstance(session_state, Mapping) else []) or []
        if str(item or "").strip()
    }
    upload_metadata_keys = ("id", "filename", "mime_type", "size_bytes", "created_at", "has_text_content")
    uploads = []
    for upload in state.get("session_uploads", []) if isinstance(state.get("session_uploads"), list) else []:
        if isinstance(upload, Mapping) and str(upload.get("id") or "").strip() in active_upload_ids:
            uploads.append(project_mapping(upload, upload_metadata_keys))
    app_id = state.get("collection_id")
    return {
        "user_query": copy.deepcopy(state.get("user_query")),
        "turn_input_type": copy.deepcopy(state.get("turn_input_type")),
        "session_upload_event_ids": copy.deepcopy(state.get("session_upload_event_ids", [])),
        "chat_history": _summary_history(state, max_turns=4),
        "session_uploads": uploads,
        "app_id": copy.deepcopy(app_id),
        "collection_id": copy.deepcopy(app_id),
        "config_json": project_mapping(state.get("config_json"), PLANNER_CONFIG_KEYS),
        "adapter_json": project_mapping(state.get("adapter_json"), PLANNER_ADAPTER_KEYS),
        "template_registry": _project_registry(state.get("template_registry")),
    }


def compact_hybrid_decision_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(packet))
    candidates = result.get("candidates")
    if isinstance(candidates, Mapping):
        result["candidates"] = {key: _compact_identity_value(value) for key, value in candidates.items()}
    if isinstance(result.get("routing_rules"), list):
        result["routing_rules"] = _compact_identity_value(result["routing_rules"])
    if isinstance(result.get("interaction_logic"), list):
        result["interaction_logic"] = _compact_identity_value(result["interaction_logic"])
    return result


ANSWER_KEYS = (
    "user_query", "chat_history", "planner_output", "evidence_analysis", "compressed_evidence", "prepared_inputs",
    "instruction_evidence", "selected_instruction_block", "selected_instruction_block_text", "instruction_resource_load_plan",
    "instruction_resource_context", "template_resource_load_plan", "template_resource_context", "global_instruction_context",
    "knowledge_evidence", "template_evidence", "session_upload_evidence", "adapter_json", "config_json", "template_registry",
    "turn_execution_plan", "turn_action_plan", "session_execution_state", "presentation_policy", "visible_outputs", "hidden_outputs",
    "execution_artifacts",
)

EXECUTION_CONTEXT_KEYS = (
    "turn_intent", "action_type", "actions", "state_updates", "resource_requests", "response_style",
    "primary_scope", "secondary_scopes", "active_workflow_id", "active_module_id", "active_step_id",
    "active_step_scope", "active_step_scope_id", "active_service_block_id", "active_service_block_type",
    "active_service_block_title", "primary_support_module_id", "primary_support_module_title",
    "active_execution_mode", "active_bundled_step_ids", "bundled_entry_step_id", "active_module_queue",
    "current_module_index", "active_binding_ids", "active_dependency_group_ids", "active_artifact_roles",
    "artifact_gate_status", "output_artifact_targets", "execution_status", "clarification_gate_status",
    "active_session_upload_ids", "chat_summary",
)


def _compact_execution_context(value: Any) -> dict[str, Any]:
    return project_mapping(value, EXECUTION_CONTEXT_KEYS)


def _compact_prepared_inputs(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result = project_mapping(
        value,
        (
            "resource_requests", "active_binding_ids", "artifact_gate_status", "bundled_execution",
            "instruction_resource_context", "template_resource_context",
            "turn_execution_plan",
        ),
    )
    result["instruction_resource_context"] = compact_resource_context(value.get("instruction_resource_context"), limit=8, text_limit=2_000)
    result["template_resource_context"] = compact_resource_context(value.get("template_resource_context"), limit=8, text_limit=2_000)
    result["turn_execution_plan"] = _compact_execution_context(value.get("turn_execution_plan"))
    if isinstance(result.get("resource_requests"), list):
        result["resource_requests"] = [_compact_identity_value(item) for item in result["resource_requests"] if isinstance(item, Mapping)]
    return result


def _hidden_outputs_required(context: Mapping[str, Any]) -> bool:
    for key in ("assembly_state", "execution_artifacts", "turn_execution_plan"):
        value = context.get(key)
        if value and "hidden" in json.dumps(value, ensure_ascii=False).lower():
            return True
    return False


def build_answer_context(full_context: Mapping[str, Any]) -> dict[str, Any]:
    result = {key: copy.deepcopy(full_context.get(key, [] if key.endswith("evidence") or key.endswith("outputs") or key.endswith("plan") or key == "chat_history" else {})) for key in ANSWER_KEYS}
    result["user_query"] = copy.deepcopy(full_context.get("user_query", ""))
    result["chat_history"] = _summary_history(full_context, max_turns=6)
    for key in ("compressed_evidence", "instruction_evidence", "knowledge_evidence", "session_upload_evidence"):
        result[key] = compact_evidence_items(full_context.get(key), limit=8, snippet_limit=800)
    result["template_evidence"] = compact_evidence_items(full_context.get("template_evidence"), limit=3, snippet_limit=800)
    result["instruction_resource_context"] = compact_resource_context(full_context.get("instruction_resource_context"), limit=8, text_limit=2_000)
    result["template_resource_context"] = compact_resource_context(full_context.get("template_resource_context"), limit=8, text_limit=2_000)
    result["prepared_inputs"] = _compact_prepared_inputs(full_context.get("prepared_inputs"))
    result["config_json"] = project_mapping(full_context.get("config_json"), ("style_rules", "safety_rules", "role", "goals"))
    result["adapter_json"] = project_mapping(full_context.get("adapter_json"), ("llm_guardrails_append", "response_policy", "style_rules"))
    result["template_registry"] = project_mapping(full_context.get("template_registry"), ("llm_system_prompt", "output_schema", "presentation_policy"))
    result["selected_instruction_block"] = project_mapping(
        full_context.get("selected_instruction_block"),
        ("block_id", "block_type", "title", "response_hint", "safety_rules", "constraints", "resource_requests"),
    )
    result["turn_execution_plan"] = _compact_execution_context(full_context.get("turn_execution_plan"))
    result["turn_action_plan"] = _compact_execution_context(full_context.get("turn_action_plan"))
    result["session_execution_state"] = _compact_execution_context(full_context.get("session_execution_state"))
    block = result.get("selected_instruction_block") if isinstance(result.get("selected_instruction_block"), Mapping) else {}
    active_markers = [str(block.get("title") or ""), str(block.get("block_id") or "")]
    result["selected_instruction_block_text"] = semantic_section_compact(
        str(full_context.get("selected_instruction_block_text") or ""), active_markers=active_markers, max_chars=4_000
    )
    session_state = result.get("session_execution_state") if isinstance(result.get("session_execution_state"), Mapping) else {}
    active_upload_ids = {str(item or "").strip() for item in session_state.get("active_session_upload_ids", []) or [] if str(item or "").strip()}
    if not active_upload_ids:
        result["session_upload_evidence"] = []
    else:
        result["session_upload_evidence"] = [
            item for item in result["session_upload_evidence"]
            if str(item.get("doc_id") or item.get("source_id") or "").strip() in active_upload_ids
        ]
    if not _hidden_outputs_required(full_context):
        result["hidden_outputs"] = []
    for key in ("missing_infoTypes", "previous_answer"):
        if key in full_context:
            result[key] = copy.deepcopy(full_context[key])
    return result


def _metadata_markers(item: Mapping[str, Any]) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
    values = [metadata.get("info_type"), metadata.get("info_types"), metadata.get("tags")]
    return " ".join(json.dumps(value, ensure_ascii=False) for value in values if value).lower()


def deterministic_evidence_assessment(
    info_types: Any,
    evidence: Any,
    *,
    minimum_score: float = 0.2,
) -> dict[str, Any]:
    requested = [str(item).strip().lower() for item in info_types if str(item).strip()] if isinstance(info_types, list) else []
    items = [item for item in evidence if isinstance(item, Mapping)] if isinstance(evidence, list) else []
    reasons: list[str] = []
    ambiguous = False
    conflicting = False
    broad_labels = {"fact", "facts", "general", "information", "details", "overview", "context"}
    if requested and not items:
        reasons.append("no_evidence")
    for marker in requested:
        matches: list[Mapping[str, Any]] = []
        metadata_matches: list[Mapping[str, Any]] = []
        positive = False
        negative = False
        for item in items:
            metadata_blob = _metadata_markers(item)
            text_blob = " ".join((str(item.get("title") or ""), str(item.get("filename") or ""), str(item.get("snippet") or ""))).lower()
            if marker in metadata_blob:
                metadata_matches.append(item)
                matches.append(item)
            elif marker in text_blob:
                matches.append(item)
            if marker in text_blob:
                if any(token in text_blob for token in (f"not {marker}", f"no {marker}", f"without {marker}")):
                    negative = True
                else:
                    positive = True
        if not matches:
            reasons.append(f"missing:{marker}")
            continue
        if marker in broad_labels and not metadata_matches:
            ambiguous = True
            reasons.append(f"broad_text_only:{marker}")
        if positive and negative:
            conflicting = True
            reasons.append(f"conflict:{marker}")
        for item in matches:
            stable_id = str(item.get("doc_id") or item.get("source_id") or item.get("resource_id") or "").strip()
            title = str(item.get("title") or item.get("filename") or "").strip()
            if not stable_id or not title:
                reasons.append(f"missing_citation_identity:{marker}")
            if item.get("score") is not None and float(item.get("score") or 0) < minimum_score:
                reasons.append(f"below_minimum_score:{marker}")
    sufficient = not reasons and not ambiguous and not conflicting
    return {"sufficient": sufficient, "ambiguous": ambiguous, "conflicting": conflicting, "reasons": reasons}


def _bounded_unique(values: Any, *, limit: int = 12) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values if isinstance(values, list) else []:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        if marker and marker not in seen:
            seen.add(marker)
            result.append(copy.deepcopy(value))
        if len(result) >= limit:
            break
    return result


def build_or_refresh_chat_summary(
    *,
    existing_summary: Mapping[str, Any] | None,
    prior_history: list[dict[str, Any]],
    current_user_message: str,
    current_answer: Mapping[str, Any],
    session_execution_state: Mapping[str, Any],
) -> dict[str, Any]:
    existing = copy.deepcopy(dict(existing_summary or {}))
    messages = [copy.deepcopy(item) for item in prior_history if isinstance(item, dict)]
    messages.extend(
        [
            {"role": "user", "content": str(current_user_message or "")},
            {"role": "assistant", "content": str(current_answer.get("content") or "")},
        ]
    )
    user_texts = [str(item.get("content") or "").strip() for item in messages if item.get("role") == "user" and str(item.get("content") or "").strip()]
    assistant_texts = [str(item.get("content") or "").strip() for item in messages if item.get("role") == "assistant" and str(item.get("content") or "").strip()]
    decision_markers = ("prefer", "want", "need", "must", "decide", "choose", "希望", "需要", "必須", "選擇", "決定")
    decisions = [text[:500] for text in user_texts if any(marker in text.lower() for marker in decision_markers)]
    unresolved = [text[:500] for text in user_texts if text.rstrip().endswith(("?", "？"))]
    citations = current_answer.get("citations") if isinstance(current_answer.get("citations"), list) else []
    citation_ids = [
        str(item.get("docId") or item.get("doc_id") or item.get("source_id") or "").strip()
        for item in citations
        if isinstance(item, Mapping) and str(item.get("docId") or item.get("doc_id") or item.get("source_id") or "").strip()
    ]
    gate = session_execution_state.get("clarification_gate_status") if isinstance(session_execution_state.get("clarification_gate_status"), Mapping) else {}
    filled_slots = gate.get("filled_slots_map") if isinstance(gate.get("filled_slots_map"), Mapping) else {}
    active_state_keys = (
        "active_role_id", "active_workflow", "active_workflow_id", "active_service_block_id",
        "active_service_block_type", "active_step_scope_id", "active_step_title", "execution_status",
        "active_module_queue", "current_module_index", "active_session_upload_ids",
    )
    active_state = project_mapping(session_execution_state, active_state_keys)
    obligations = []
    for key in ("output_artifact_targets", "pending_resource_requests", "pending_obligations"):
        value = session_execution_state.get(key)
        if value:
            obligations.extend(value if isinstance(value, list) else [value])
    return {
        "version": "deterministic:v1",
        "covered_message_count": len(messages),
        "user_decisions_constraints": _bounded_unique(list(existing.get("user_decisions_constraints", [])) + decisions),
        "assistant_conclusions": _bounded_unique(list(existing.get("assistant_conclusions", [])) + [text[:500] for text in assistant_texts[-4:]]),
        "unresolved_questions": _bounded_unique(list(existing.get("unresolved_questions", [])) + unresolved),
        "active_workflow_state": active_state,
        "filled_slots": copy.deepcopy(dict(filled_slots)),
        "pending_obligations": _bounded_unique(list(existing.get("pending_obligations", [])) + obligations),
        "recent_citation_ids": _bounded_unique(list(existing.get("recent_citation_ids", [])) + citation_ids),
    }
