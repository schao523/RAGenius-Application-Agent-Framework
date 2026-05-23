"""Node: execute turn actions and prepare internal artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from ..executors import ExecutorRegistry
from ..graph_state import GraphState


def _as_dict_list(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _execution_registry(state: GraphState) -> ExecutorRegistry:
    registry = state.get("_executor_registry")
    if isinstance(registry, ExecutorRegistry):
        return registry
    return ExecutorRegistry()


def _ensure_intermediate_output(
    state: GraphState,
    *,
    output_id: str,
    output_type: str,
    visibility: str,
    content: str | None = None,
    structured_data: dict | None = None,
    producer_scope_id: str | None = None,
    producer_turn_index: int | None = None,
    consumed_by: list[str] | None = None,
) -> dict:
    outputs = _as_dict_list(state.get("intermediate_outputs"))
    for item in outputs:
        if str(item.get("output_id") or "").strip() == output_id:
            item["output_type"] = output_type
            item["visibility"] = visibility
            if content is not None:
                item["content"] = content
            if structured_data is not None:
                item["structured_data"] = structured_data
            if producer_scope_id is not None:
                item["producer_scope_id"] = producer_scope_id
            if producer_turn_index is not None:
                item["producer_turn_index"] = producer_turn_index
            if consumed_by is not None:
                existing_consumed_by = item.get("consumed_by", [])
                if not isinstance(existing_consumed_by, list):
                    existing_consumed_by = []
                item["consumed_by"] = list(dict.fromkeys([*existing_consumed_by, *consumed_by]))
            item["status"] = item.get("status") or "draft"
            return item
    created = {
        "output_id": output_id,
        "output_type": output_type,
        "visibility": visibility,
        "content": content,
        "structured_data": structured_data or {},
        "producer_scope_id": producer_scope_id,
        "producer_turn_index": producer_turn_index,
        "consumed_by": list(dict.fromkeys(consumed_by or [])),
        "status": "draft",
    }
    outputs.append(created)
    state["intermediate_outputs"] = outputs
    return created


def _append_artifact(state: GraphState, artifact: dict) -> None:
    artifacts = _as_dict_list(state.get("execution_artifacts"))
    artifacts.append(artifact)
    state["execution_artifacts"] = artifacts


def _append_visible_output(state: GraphState, payload: dict) -> None:
    outputs = _as_dict_list(state.get("visible_outputs"))
    outputs.append(payload)
    state["visible_outputs"] = outputs


def _append_hidden_output(state: GraphState, payload: dict) -> None:
    outputs = _as_dict_list(state.get("hidden_outputs"))
    outputs.append(payload)
    state["hidden_outputs"] = outputs


def _normalize_output_payload(payload: dict, default_visibility: str) -> dict:
    normalized = dict(payload)
    normalized["output_id"] = str(
        normalized.get("output_id") or normalized.get("id") or normalized.get("output_key") or "output"
    ).strip()
    normalized["output_type"] = str(normalized.get("output_type") or normalized.get("type") or "output").strip()
    normalized["visibility"] = str(normalized.get("visibility") or default_visibility).strip()
    if "structured_data" not in normalized or not isinstance(normalized.get("structured_data"), dict):
        normalized["structured_data"] = {}
    normalized["status"] = str(normalized.get("status") or "draft").strip()
    return normalized


def _store_output_payload(state: GraphState, payload: dict, default_visibility: str) -> dict:
    normalized = _normalize_output_payload(payload, default_visibility)
    plan = state.get("turn_execution_plan", {})
    primary_scope = plan.get("primary_scope", {}) if isinstance(plan, dict) else {}
    producer_scope_id = str(normalized.get("producer_scope_id") or primary_scope.get("scope_id") or "").strip() or None
    producer_turn_index = normalized.get("producer_turn_index")
    if not isinstance(producer_turn_index, int):
        chat_history = state.get("chat_history", [])
        producer_turn_index = len(chat_history) if isinstance(chat_history, list) else None
    consumed_by = normalized.get("consumed_by") if isinstance(normalized.get("consumed_by"), list) else []
    created = _ensure_intermediate_output(
        state,
        output_id=normalized["output_id"],
        output_type=normalized["output_type"],
        visibility=normalized["visibility"],
        content=str(normalized.get("content")) if normalized.get("content") is not None else None,
        structured_data=normalized.get("structured_data") if isinstance(normalized.get("structured_data"), dict) else {},
        producer_scope_id=producer_scope_id,
        producer_turn_index=producer_turn_index,
        consumed_by=consumed_by,
    )
    created["status"] = normalized.get("status") or created.get("status") or "draft"
    if created["visibility"] in {"user_visible", "final_visible", "summary_visible"}:
        _append_visible_output(state, created)
    else:
        _append_hidden_output(state, created)
    return created


def _merge_session_state(state: GraphState, updates: dict) -> None:
    session_execution_state = state.get("session_execution_state", {})
    if not isinstance(session_execution_state, dict):
        session_execution_state = {}
    merged = dict(session_execution_state)
    for key, value in (updates or {}).items():
        merged[key] = value
    state["session_execution_state"] = merged


def _merge_assembly_state(state: GraphState, updates: dict) -> None:
    assembly_state = state.get("assembly_state", {})
    if not isinstance(assembly_state, dict):
        assembly_state = {}
    merged = dict(assembly_state)
    for key, value in (updates or {}).items():
        merged[key] = value
    state["assembly_state"] = merged


def _append_unique_str(values: list[str], candidate: Any) -> None:
    normalized = str(candidate or "").strip()
    if normalized and normalized not in values:
        values.append(normalized)


def _artifact_role_from_value(value: Any) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    stem = Path(normalized).stem if Path(normalized).suffix else normalized
    role = stem.strip().lower().replace(" ", "_").replace("-", "_")
    return role or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _artifact_roles_from_payload(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    roles: list[str] = []
    for key in ("artifact_role", "generated_artifact_role", "required_artifact_role"):
        role = _artifact_role_from_value(payload.get(key))
        if role:
            _append_unique_str(roles, role)
    for key in ("artifact_roles", "generated_artifact_roles", "required_artifact_roles"):
        for item in _string_list(payload.get(key)):
            role = _artifact_role_from_value(item)
            if role:
                _append_unique_str(roles, role)
    structured_data = payload.get("structured_data")
    if isinstance(structured_data, dict):
        for role in _artifact_roles_from_payload(structured_data):
            _append_unique_str(roles, role)
    content = payload.get("content")
    if isinstance(content, dict):
        for role in _artifact_roles_from_payload(content):
            _append_unique_str(roles, role)
    return roles


def _target_outputs_from_payload(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    targets: list[str] = []
    for key in ("target_outputs", "output_artifact_targets"):
        for item in _string_list(payload.get(key)):
            _append_unique_str(targets, item)
    structured_data = payload.get("structured_data")
    if isinstance(structured_data, dict):
        for item in _target_outputs_from_payload(structured_data):
            _append_unique_str(targets, item)
    content = payload.get("content")
    if isinstance(content, dict):
        for item in _target_outputs_from_payload(content):
            _append_unique_str(targets, item)
    return targets


def _update_artifact_metadata(
    state: GraphState,
    *,
    artifact_roles: list[str] | None = None,
    required_artifact_roles: list[str] | None = None,
    target_outputs: list[str] | None = None,
    source_output_key: str | None = None,
    satisfied: bool | None = None,
) -> None:
    session_execution_state = state.get("session_execution_state", {})
    if not isinstance(session_execution_state, dict):
        session_execution_state = {}
    active_artifact_roles = _string_list(session_execution_state.get("active_artifact_roles"))
    output_artifact_targets = _string_list(session_execution_state.get("output_artifact_targets"))
    artifact_gate_status = (
        dict(session_execution_state.get("artifact_gate_status", {}))
        if isinstance(session_execution_state.get("artifact_gate_status"), dict)
        else {}
    )

    for role in artifact_roles or []:
        _append_unique_str(active_artifact_roles, role)
        existing = artifact_gate_status.get(role, {})
        if not isinstance(existing, dict):
            existing = {}
        resolved_satisfied = satisfied if satisfied is not None else bool(existing.get("satisfied"))
        artifact_gate_status[role] = {
            **existing,
            "artifact_role": role,
            "required_for_progression": bool(existing.get("required_for_progression")),
            "satisfied": resolved_satisfied,
            "status": existing.get("status") or ("satisfied" if resolved_satisfied else "available"),
        }
        if satisfied is not None:
            for gate_key, gate_value in list(artifact_gate_status.items()):
                if not isinstance(gate_value, dict):
                    continue
                gate_role = _artifact_role_from_value(gate_value.get("artifact_role"))
                if gate_role != role:
                    continue
                gate_required = bool(gate_value.get("required_for_progression"))
                if not gate_required:
                    continue
                artifact_gate_status[gate_key] = {
                    **gate_value,
                    "artifact_role": role,
                    "satisfied": resolved_satisfied,
                    "status": "satisfied" if resolved_satisfied else (gate_value.get("status") or "awaiting_artifact"),
                }

    for role in required_artifact_roles or []:
        _append_unique_str(active_artifact_roles, role)
        existing = artifact_gate_status.get(role, {})
        if not isinstance(existing, dict):
            existing = {}
        resolved_satisfied = satisfied if satisfied is not None else bool(existing.get("satisfied"))
        artifact_gate_status[role] = {
            **existing,
            "artifact_role": role,
            "required_for_progression": True,
            "satisfied": resolved_satisfied,
            "status": existing.get("status") or ("satisfied" if resolved_satisfied else "awaiting_artifact"),
        }

    for item in target_outputs or []:
        _append_unique_str(output_artifact_targets, item)

    if active_artifact_roles or output_artifact_targets or artifact_gate_status:
        _merge_session_state(
            state,
            {
                "active_artifact_roles": active_artifact_roles,
                "output_artifact_targets": output_artifact_targets,
                "artifact_gate_status": artifact_gate_status,
            },
        )
    if target_outputs or source_output_key:
        _merge_assembly_state(
            state,
            {
                "target_outputs": output_artifact_targets or list(target_outputs or []),
                "source_output_key": source_output_key,
            },
        )


def _sync_artifact_gate_state_from_plan(state: GraphState, plan: dict) -> None:
    session_execution_state = state.get("session_execution_state", {})
    if not isinstance(session_execution_state, dict):
        session_execution_state = {}

    active_artifact_roles = [
        str(item).strip()
        for item in (session_execution_state.get("active_artifact_roles", []) if isinstance(session_execution_state.get("active_artifact_roles"), list) else [])
        if str(item).strip()
    ]
    artifact_gate_status = (
        dict(session_execution_state.get("artifact_gate_status", {}))
        if isinstance(session_execution_state.get("artifact_gate_status"), dict)
        else {}
    )
    requests = plan.get("resource_requests", []) if isinstance(plan, dict) else []
    for request in requests:
        if not isinstance(request, dict):
            continue
        artifact_role = str(request.get("artifact_role") or "").strip() or _artifact_role_from_value(request.get("filename"))
        if artifact_role:
            _append_unique_str(active_artifact_roles, artifact_role)
        if not bool(request.get("required_for_progression")):
            continue
        key = str(request.get("binding_id") or "").strip() or artifact_role
        if not key:
            continue
        existing = artifact_gate_status.get(key, {})
        if not isinstance(existing, dict):
            existing = {}
        satisfied = bool(existing.get("satisfied"))
        artifact_gate_status[key] = {
            **existing,
            "artifact_role": artifact_role or existing.get("artifact_role"),
            "required_for_progression": True,
            "filename": str(request.get("filename") or "").strip() or existing.get("filename"),
            "satisfied": satisfied,
            "status": existing.get("status") or ("satisfied" if satisfied else "awaiting_artifact"),
        }

    if active_artifact_roles or artifact_gate_status:
        _merge_session_state(
            state,
            {
                "active_artifact_roles": active_artifact_roles,
                "artifact_gate_status": artifact_gate_status,
            },
        )
    actions = plan.get("actions", []) if isinstance(plan, dict) else []
    for action in actions:
        if not isinstance(action, dict):
            continue
        params = action.get("params", {})
        if not isinstance(params, dict):
            continue
        artifact_roles = _artifact_roles_from_payload(params)
        required_roles = artifact_roles if bool(params.get("required_for_progression")) else []
        _update_artifact_metadata(
            state,
            artifact_roles=artifact_roles,
            required_artifact_roles=required_roles,
            target_outputs=_target_outputs_from_payload(params),
            source_output_key=str(params.get("source_output_key") or "").strip() or None,
            satisfied=False if required_roles else None,
        )


def _sync_assembly_state_from_plan(state: GraphState, plan: dict) -> None:
    actions = plan.get("actions", []) if isinstance(plan, dict) else []
    for action in actions:
        if not isinstance(action, dict):
            continue
        if str(action.get("action_type") or "").strip() != "assemble_output":
            continue
        params = action.get("params", {})
        if not isinstance(params, dict):
            continue
        target_outputs = [
            str(item).strip()
            for item in (params.get("target_outputs", []) if isinstance(params.get("target_outputs"), list) else [])
            if str(item).strip()
        ]
        source_output_key = str(params.get("source_output_key") or "").strip() or None
        if not target_outputs and not source_output_key:
            continue
        source_output = _find_output_by_id(state, source_output_key or "") if source_output_key else None
        _update_artifact_metadata(
            state,
            target_outputs=target_outputs,
            source_output_key=source_output_key,
        )
        _merge_assembly_state(state, {"status": "ready_for_render" if source_output else "pending_source_output"})
        return


def _find_output_by_id(state: GraphState, output_id: str) -> dict | None:
    wanted = str(output_id or "").strip()
    if not wanted:
        return None
    for collection_key in ("visible_outputs", "hidden_outputs", "intermediate_outputs"):
        for item in _as_dict_list(state.get(collection_key)):
            if str(item.get("output_id") or "").strip() == wanted:
                return item
    return None


def _apply_executor_result(
    state: GraphState,
    action: Dict[str, Any],
    result: Dict[str, Any] | None,
    *,
    artifact_type: str,
) -> Dict[str, Any]:
    normalized_result = result if isinstance(result, dict) else {"result": result}
    action_params = action.get("params", {}) if isinstance(action.get("params"), dict) else {}

    for payload in _as_dict_list(normalized_result.get("intermediate_outputs")):
        _store_output_payload(state, payload, "internal_only")
        roles = _artifact_roles_from_payload(payload)
        required_roles = roles if bool(payload.get("required_for_progression")) else []
        _update_artifact_metadata(state, artifact_roles=roles, required_artifact_roles=required_roles, satisfied=True if roles else None)
    for payload in _as_dict_list(normalized_result.get("visible_outputs")):
        _store_output_payload(state, payload, "user_visible")
        roles = _artifact_roles_from_payload(payload)
        required_roles = roles if bool(payload.get("required_for_progression")) else []
        _update_artifact_metadata(state, artifact_roles=roles, required_artifact_roles=required_roles, satisfied=True if roles else None)
    for payload in _as_dict_list(normalized_result.get("hidden_outputs")):
        _store_output_payload(state, payload, "internal_only")
        roles = _artifact_roles_from_payload(payload)
        required_roles = roles if bool(payload.get("required_for_progression")) else []
        _update_artifact_metadata(state, artifact_roles=roles, required_artifact_roles=required_roles, satisfied=True if roles else None)

    if isinstance(normalized_result.get("session_state_updates"), dict):
        _merge_session_state(state, normalized_result.get("session_state_updates", {}))
    if isinstance(normalized_result.get("assembly_state"), dict):
        _merge_assembly_state(state, normalized_result.get("assembly_state", {}))
        _update_artifact_metadata(
            state,
            target_outputs=_target_outputs_from_payload(normalized_result.get("assembly_state", {})),
            source_output_key=str(normalized_result.get("assembly_state", {}).get("source_output_key") or "").strip() or None,
        )

    for extra_artifact in _as_dict_list(normalized_result.get("artifacts")):
        roles = _artifact_roles_from_payload(extra_artifact)
        required_roles = roles if bool(extra_artifact.get("required_for_progression")) else []
        _update_artifact_metadata(
            state,
            artifact_roles=roles,
            required_artifact_roles=required_roles,
            target_outputs=_target_outputs_from_payload(extra_artifact),
            satisfied=True if roles else None,
        )
        artifact = {
            "artifact_id": str(
                extra_artifact.get("artifact_id")
                or f"artifact:{action.get('action_id')}:{len(_as_dict_list(state.get('execution_artifacts')))}"
            ).strip(),
            "artifact_type": str(extra_artifact.get("artifact_type") or artifact_type).strip(),
            "source_action_id": extra_artifact.get("source_action_id") or action.get("action_id"),
            "content": extra_artifact.get("content") if isinstance(extra_artifact.get("content"), dict) else dict(extra_artifact),
        }
        _append_artifact(state, artifact)

    artifact = {
        "artifact_id": f"artifact:{action.get('action_id')}",
        "artifact_type": artifact_type,
        "source_action_id": action.get("action_id"),
        "content": normalized_result,
    }
    _append_artifact(state, artifact)
    action_roles = _artifact_roles_from_payload(action_params)
    required_action_roles = action_roles if bool(action_params.get("required_for_progression")) else []
    _update_artifact_metadata(
        state,
        artifact_roles=action_roles,
        required_artifact_roles=required_action_roles,
        target_outputs=_target_outputs_from_payload(action_params),
        source_output_key=str(action_params.get("source_output_key") or "").strip() or None,
        satisfied=True if action_roles and artifact_type in {"tool_call", "skill_call", "assembly", "validation"} else None,
    )
    return artifact


def _builtin_output_artifact_assembler(state: GraphState, action: Dict[str, Any]) -> Dict[str, Any]:
    params = action.get("params", {}) if isinstance(action.get("params"), dict) else {}
    target_outputs = [
        str(item).strip()
        for item in (params.get("target_outputs", []) if isinstance(params.get("target_outputs"), list) else [])
        if str(item).strip()
    ]
    source_output_key = str(params.get("source_output_key") or "").strip() or None
    source_output = _find_output_by_id(state, source_output_key or "")
    assembly_status = "ready_for_render" if source_output else "pending_source_output"
    return {
        "assembly_state": {
            "target_outputs": target_outputs,
            "source_output_key": source_output_key,
            "status": assembly_status,
        },
        "hidden_outputs": [
            {
                "output_id": "output_artifact_assembly_plan",
                "output_type": "assembly_plan",
                "visibility": "internal_only",
                "structured_data": {
                    "target_outputs": target_outputs,
                    "source_output_key": source_output_key,
                    "status": assembly_status,
                },
                "status": "complete",
            }
        ],
        "artifacts": [
            {
                "artifact_type": "assembly_plan",
                "content": {
                    "target_outputs": target_outputs,
                    "source_output_key": source_output_key,
                    "status": assembly_status,
                },
            }
        ],
    }


def _builtin_output_artifact_validator(state: GraphState, action: Dict[str, Any]) -> Dict[str, Any]:
    params = action.get("params", {}) if isinstance(action.get("params"), dict) else {}
    target_outputs = [
        str(item).strip()
        for item in (params.get("target_outputs", []) if isinstance(params.get("target_outputs"), list) else [])
        if str(item).strip()
    ]
    source_output_key = str(params.get("source_output_key") or "").strip() or None
    source_output = _find_output_by_id(state, source_output_key or "")
    status = "passed" if source_output else "pending_source_output"
    issues = [] if source_output else [f"Missing source output: {source_output_key}"]
    return {
        "session_state_updates": {
            "validation_status": status,
            "pending_validation_target_outputs": target_outputs if issues else [],
        },
        "hidden_outputs": [
            {
                "output_id": "output_artifact_validation_report",
                "output_type": "validation_report",
                "visibility": "internal_only",
                "structured_data": {
                    "validation_scope": params.get("validation_scope") or "output_artifacts",
                    "status": status,
                    "target_outputs": target_outputs,
                    "issues": issues,
                },
                "status": "complete",
            }
        ],
        "artifacts": [
            {
                "artifact_type": "validation_report",
                "content": {
                    "validation_scope": params.get("validation_scope") or "output_artifacts",
                    "status": status,
                    "target_outputs": target_outputs,
                    "issues": issues,
                },
            }
        ],
    }


def _execute_generate_intermediate_output(state: GraphState, action: Dict[str, Any]) -> Dict[str, Any]:
    output_id = str(action.get("output_key") or action.get("action_id") or "generated_output").strip()
    params = action.get("params", {}) if isinstance(action.get("params"), dict) else {}
    output_type = str(params.get("output_type") or action.get("target") or "intermediate_output").strip()
    visibility = str(action.get("visibility") or "internal_only").strip()
    content = params.get("content")
    structured_data = params.get("structured_data") if isinstance(params.get("structured_data"), dict) else {}
    plan = state.get("turn_execution_plan", {})
    primary_scope = plan.get("primary_scope", {}) if isinstance(plan, dict) else {}
    producer_scope_id = str(primary_scope.get("scope_id") or "").strip() or None
    chat_history = state.get("chat_history", [])
    producer_turn_index = len(chat_history) if isinstance(chat_history, list) else None
    created = _ensure_intermediate_output(
        state,
        output_id=output_id,
        output_type=output_type,
        visibility=visibility,
        content=str(content) if content is not None else None,
        structured_data=structured_data,
        producer_scope_id=producer_scope_id,
        producer_turn_index=producer_turn_index,
    )
    if visibility in {"user_visible", "final_visible", "summary_visible"}:
        _append_visible_output(state, created)
    else:
        _append_hidden_output(state, created)
    artifact = {
        "artifact_id": f"artifact:{output_id}",
        "artifact_type": "intermediate_output",
        "source_action_id": action.get("action_id"),
        "content": created,
    }
    _append_artifact(state, artifact)
    artifact_roles = _artifact_roles_from_payload(params)
    required_roles = artifact_roles if bool(params.get("required_for_progression")) else []
    _update_artifact_metadata(
        state,
        artifact_roles=artifact_roles,
        required_artifact_roles=required_roles,
        target_outputs=_target_outputs_from_payload(params),
        satisfied=True if artifact_roles else None,
    )
    return artifact


def _mark_action_input_consumption(state: GraphState, action: Dict[str, Any]) -> None:
    input_keys = action.get("input_keys", [])
    if not isinstance(input_keys, list):
        return
    outputs = _as_dict_list(state.get("intermediate_outputs"))
    if not outputs:
        return
    wanted = {str(item).strip() for item in input_keys if str(item).strip()}
    if not wanted:
        return
    for item in outputs:
        output_id = str(item.get("output_id") or "").strip()
        if output_id not in wanted:
            continue
        existing = item.get("consumed_by", [])
        if not isinstance(existing, list):
            existing = []
        item["consumed_by"] = list(dict.fromkeys([*existing, str(action.get("action_id") or "").strip()]))
        if item["consumed_by"]:
            item["status"] = "consumed"
    state["intermediate_outputs"] = outputs


def _execute_tool_call(state: GraphState, action: Dict[str, Any], executor_registry: ExecutorRegistry) -> Dict[str, Any]:
    target = str(action.get("target") or "").strip()
    tool = executor_registry.get_tool(target)
    if tool is None:
        artifact = {
            "artifact_id": f"artifact:{action.get('action_id')}",
            "artifact_type": "tool_call_skipped",
            "source_action_id": action.get("action_id"),
            "content": {"target": target, "reason": "unregistered_tool"},
        }
        _append_artifact(state, artifact)
        return artifact
    result = tool(state=state, action=action)
    return _apply_executor_result(state, action, result, artifact_type="tool_call")


def _execute_skill_call(state: GraphState, action: Dict[str, Any], executor_registry: ExecutorRegistry) -> Dict[str, Any]:
    target = str(action.get("target") or "").strip()
    skill = executor_registry.get_skill(target)
    if skill is None:
        artifact = {
            "artifact_id": f"artifact:{action.get('action_id')}",
            "artifact_type": "skill_call_skipped",
            "source_action_id": action.get("action_id"),
            "content": {"target": target, "reason": "unregistered_skill"},
        }
        _append_artifact(state, artifact)
        return artifact
    result = skill(state=state, action=action)
    return _apply_executor_result(state, action, result, artifact_type="skill_call")


def _execute_assembly_action(state: GraphState, action: Dict[str, Any], executor_registry: ExecutorRegistry) -> Dict[str, Any]:
    target = str(action.get("target") or "").strip()
    if target == "output_artifact_assembler":
        return _apply_executor_result(
            state,
            action,
            _builtin_output_artifact_assembler(state, action),
            artifact_type="assembly",
        )
    assembler = executor_registry.get_assembler(target)
    if assembler is None:
        artifact = {
            "artifact_id": f"artifact:{action.get('action_id')}",
            "artifact_type": "assembly_skipped",
            "source_action_id": action.get("action_id"),
            "content": {"target": target, "reason": "unregistered_assembler"},
        }
        _append_artifact(state, artifact)
        return artifact
    result = assembler(state=state, action=action)
    if isinstance(result, dict) and "assembly_state" not in result:
        result = {"assembly_state": result}
    return _apply_executor_result(state, action, result, artifact_type="assembly")


def _execute_validation_action(state: GraphState, action: Dict[str, Any], executor_registry: ExecutorRegistry) -> Dict[str, Any]:
    target = str(action.get("target") or "").strip()
    if target == "output_artifact_validator":
        return _apply_executor_result(
            state,
            action,
            _builtin_output_artifact_validator(state, action),
            artifact_type="validation",
        )
    validator = executor_registry.get_validator(target)
    if validator is None:
        artifact = {
            "artifact_id": f"artifact:{action.get('action_id')}",
            "artifact_type": "validation_skipped",
            "source_action_id": action.get("action_id"),
            "content": {"target": target, "reason": "unregistered_validator"},
        }
        _append_artifact(state, artifact)
        return artifact
    result = validator(state=state, action=action)
    return _apply_executor_result(state, action, result, artifact_type="validation")


def run(state: GraphState) -> GraphState:
    """Execute non-answer turn actions and populate execution artifacts."""
    registry = _execution_registry(state)
    plan = state.get("turn_execution_plan", {})
    actions = plan.get("actions", []) if isinstance(plan, dict) else []
    actions = [item for item in actions if isinstance(item, dict)]

    state.setdefault("execution_artifacts", [])
    state.setdefault("visible_outputs", [])
    state.setdefault("hidden_outputs", [])
    state.setdefault("tool_results", [])
    state.setdefault("intermediate_outputs", [])
    _sync_artifact_gate_state_from_plan(state, plan if isinstance(plan, dict) else {})
    _sync_assembly_state_from_plan(state, plan if isinstance(plan, dict) else {})

    for action in actions:
        action_type = str(action.get("action_type") or "").strip()
        _mark_action_input_consumption(state, action)
        if action_type == "update_session_state":
            _merge_session_state(state, plan.get("state_updates", {}) if isinstance(plan, dict) else {})
            artifact = {
                "artifact_id": f"artifact:{action.get('action_id')}",
                "artifact_type": "session_state_update",
                "source_action_id": action.get("action_id"),
                "content": state.get("session_execution_state", {}),
            }
            _append_artifact(state, artifact)
            continue
        if action_type == "generate_intermediate_output":
            _execute_generate_intermediate_output(state, action)
            continue
        if action_type == "invoke_tool":
            result = _execute_tool_call(state, action, registry)
            tool_results = _as_dict_list(state.get("tool_results"))
            tool_results.append(result)
            state["tool_results"] = tool_results
            continue
        if action_type == "invoke_skill":
            result = _execute_skill_call(state, action, registry)
            tool_results = _as_dict_list(state.get("tool_results"))
            tool_results.append(result)
            state["tool_results"] = tool_results
            continue
        if action_type == "assemble_output":
            _execute_assembly_action(state, action, registry)
            continue
        if action_type == "validate_output":
            result = _execute_validation_action(state, action, registry)
            tool_results = _as_dict_list(state.get("tool_results"))
            tool_results.append(result)
            state["tool_results"] = tool_results
            continue
        if action_type == "respond_to_user":
            params = action.get("params", {}) if isinstance(action.get("params"), dict) else {}
            content = params.get("content")
            if isinstance(content, str) and content.strip():
                _append_visible_output(
                    state,
                    {
                        "output_id": str(action.get("output_key") or action.get("action_id") or "visible_output"),
                        "output_type": "user_visible_response",
                        "visibility": str(action.get("visibility") or "user_visible"),
                        "content": content,
                    },
                )
            _append_artifact(
                state,
                {
                    "artifact_id": f"artifact:{action.get('action_id')}",
                    "artifact_type": "response_action",
                    "source_action_id": action.get("action_id"),
                    "content": {"target": action.get("target"), "visibility": action.get("visibility")},
                },
            )
            continue
        _append_artifact(
            state,
            {
                "artifact_id": f"artifact:{action.get('action_id')}",
                "artifact_type": "action_observed",
                "source_action_id": action.get("action_id"),
                "content": {"action_type": action_type, "target": action.get("target")},
            },
        )
    return state
