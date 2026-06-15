from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from typing import Any


class InstructionModelAdapter:
    """Read-only adapter for runtime-produced instruction understanding snapshots."""

    def __init__(self, snapshot_root: str | Path | None):
        self.snapshot_root = Path(snapshot_root).resolve() if snapshot_root else None

    def get_latest_instruction_model(self, app_id: str, current_instruction: dict[str, Any] | None):
        loaded_at = _utc_now()
        if not self.snapshot_root:
            return self._missing(
                app_id=app_id,
                source_kind="unconfigured",
                loaded_at=loaded_at,
                reason="snapshot root is not configured",
            )

        snapshot_path = (self.snapshot_root / app_id / "understanding.json").resolve()
        if not _is_relative_to(snapshot_path, self.snapshot_root):
            return {
                "app_id": app_id,
                "source_kind": "filesystem_snapshot",
                "source_path": str(snapshot_path),
                "loaded_at": loaded_at,
                "compiled_at": None,
                "status": "error",
                "freshness": "unknown",
                "freshness_reason": "snapshot path escaped configured root",
                "summary": {},
                "payload": None,
                "errors": ["snapshot path escaped configured root"],
            }
        if not snapshot_path.is_file():
            return self._missing(
                app_id=app_id,
                source_kind="filesystem_snapshot",
                loaded_at=loaded_at,
                source_path=str(snapshot_path),
                reason="understanding.json was not found for this app",
            )

        try:
            payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return {
                "app_id": app_id,
                "source_kind": "filesystem_snapshot",
                "source_path": str(snapshot_path),
                "loaded_at": loaded_at,
                "compiled_at": None,
                "status": "error",
                "freshness": "unknown",
                "freshness_reason": "understanding.json could not be parsed",
                "summary": {},
                "payload": None,
                "errors": [str(exc)],
            }

        if not isinstance(payload, dict):
            return {
                "app_id": app_id,
                "source_kind": "filesystem_snapshot",
                "source_path": str(snapshot_path),
                "loaded_at": loaded_at,
                "compiled_at": None,
                "status": "error",
                "freshness": "unknown",
                "freshness_reason": "understanding.json root is not an object",
                "summary": {},
                "payload": None,
                "errors": ["understanding.json root is not an object"],
            }

        freshness, freshness_reason = _freshness(payload, current_instruction or {})
        return {
            "app_id": app_id,
            "source_kind": "filesystem_snapshot",
            "source_path": str(snapshot_path),
            "loaded_at": loaded_at,
            "compiled_at": payload.get("compiled_at"),
            "status": payload.get("compiled_status") or "unknown",
            "freshness": freshness,
            "freshness_reason": freshness_reason,
            "summary": _summary(payload),
            "display_model": _display_model(payload),
            "payload": payload,
            "errors": [],
        }

    @staticmethod
    def _missing(
        *,
        app_id: str,
        source_kind: str,
        loaded_at: str,
        reason: str,
        source_path: str | None = None,
    ) -> dict[str, Any]:
        return {
            "app_id": app_id,
            "source_kind": source_kind,
            "source_path": source_path,
            "loaded_at": loaded_at,
            "compiled_at": None,
            "status": "missing",
            "freshness": "unknown",
            "freshness_reason": reason,
            "summary": {},
            "payload": None,
            "errors": [],
        }


def _utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _freshness(payload: dict[str, Any], current_instruction: dict[str, Any]) -> tuple[str, str]:
    compiled_hash = payload.get("instruction_source_hash")
    content = current_instruction.get("content")
    if compiled_hash and isinstance(content, str):
        current_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if compiled_hash == current_hash:
            return "current", "compiled hash matches current instruction content"
        return "stale", "compiled source hash does not match current instruction content hash"

    compiled_version = payload.get("instruction_source_version")
    current_version = current_instruction.get("version")
    if compiled_version and current_version:
        if str(compiled_version) == str(current_version):
            return "current", "compiled version matches current instruction version"
        return "stale", "compiled source version does not match current instruction version"

    return "unknown", "freshness cannot be verified because source hash/version metadata is unavailable"


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    runtime_model = _runtime_model(payload)
    procedures = _as_list(runtime_model.get("instruction_procedures"))
    procedure_steps = _procedure_steps(runtime_model, procedures)
    semantic = payload.get("semantic_compile") if isinstance(payload.get("semantic_compile"), dict) else {}
    validation_errors = _as_list(payload.get("validation_errors")) + _as_list(payload.get("compile_errors"))
    validation_warnings = _as_list(payload.get("validation_warnings")) + _as_list(payload.get("semantic_warnings"))

    return {
        "primary_service_mode": runtime_model.get("primary_service_mode"),
        "default_workflow_id": runtime_model.get("default_workflow_id"),
        "service_block_count": len(_as_list(runtime_model.get("instruction_service_blocks"))),
        "procedure_count": len(procedures),
        "procedure_step_count": len(procedure_steps),
        "resource_count": len(_as_list(runtime_model.get("instruction_resources"))),
        "validation_error_count": len(validation_errors),
        "validation_warning_count": len(validation_warnings),
        "semantic_attached": semantic.get("attached"),
        "semantic_valid": semantic.get("valid"),
        "parser_contract_version": payload.get("parser_contract_version"),
        "binding_logic_version": payload.get("binding_logic_version"),
        "resource_catalog_hash": payload.get("resource_catalog_hash"),
    }


def _display_model(payload: dict[str, Any]) -> dict[str, Any]:
    runtime_model = _runtime_model(payload)
    service_blocks = [_display_service_block(item) for item in _as_list(runtime_model.get("instruction_service_blocks"))]
    step_items = _as_list(runtime_model.get("procedure_steps"))
    steps_by_procedure = _steps_by_procedure(step_items)
    fallback_steps = _fallback_steps(runtime_model)
    procedures = [
        _display_procedure(item, steps_by_procedure, fallback_steps)
        for item in _as_list(runtime_model.get("instruction_procedures"))
    ]
    resources = [_display_resource(item) for item in _as_list(runtime_model.get("instruction_resources"))]
    dependency_groups = [
        _display_dependency_group(item)
        for item in _as_list(runtime_model.get("dependency_groups"))
    ]
    phase_bindings = [
        _display_phase_binding(item)
        for item in _as_list(runtime_model.get("phase_resource_bindings"))
    ]
    return {
        "service_blocks": service_blocks,
        "procedures": procedures,
        "resources": resources,
        "dependency_groups": dependency_groups,
        "phase_resource_bindings": phase_bindings,
        "policies": _display_policies(runtime_model),
    }


def _display_service_block(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"id": None, "title": str(item), "type": None, "label": str(item)}
    title = _first_text(item, ["title", "name", "block_id"])
    block_id = _first_text(item, ["block_id", "id"])
    block_type = _first_text(item, ["block_type", "type", "role"])
    return {
        "id": block_id,
        "title": title,
        "type": block_type,
        "label": title,
        "is_default": item.get("is_default"),
        "resource_refs": _as_list(item.get("resource_refs")),
    }


def _display_procedure(
    item: Any,
    steps_by_procedure: dict[str, list[dict[str, Any]]],
    fallback_steps: dict[str, tuple[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"id": None, "title": str(item), "label": str(item), "steps": [], "steps_source": "none"}
    procedure_id = _first_text(item, ["procedure_id", "id"])
    sequence = [str(step_id) for step_id in _as_list(item.get("step_sequence"))]
    available_steps = steps_by_procedure.get(procedure_id or "", [])
    steps_source = "procedure_steps" if available_steps else "none"
    if sequence:
        by_id = {step.get("id"): step for step in available_steps}
        steps = [by_id[step_id] for step_id in sequence if step_id in by_id]
    else:
        steps = available_steps
    if not steps:
        fallback_source, steps = _lookup_fallback_steps(item, fallback_steps)
        steps_source = fallback_source
    title = _first_text(item, ["title", "name", "procedure_id"])
    return {
        "id": procedure_id,
        "title": title,
        "label": title,
        "kind": _first_text(item, ["procedure_kind", "kind"]),
        "is_default": item.get("is_default"),
        "service_block_id": item.get("service_block_id"),
        "step_sequence": sequence,
        "steps": steps,
        "steps_source": steps_source,
    }


def _display_step(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"id": None, "title": str(item), "label": str(item), "order": None}
    step_id = _first_text(item, ["step_id", "id"])
    title = _first_text(item, ["title", "name", "step_id"])
    execution_mode = _first_text(item, ["execution_mode"])
    order = item.get("order")
    label = f"{order}. {title}" if order is not None else title
    if execution_mode:
        label = f"{label} [{execution_mode}]"
    return {
        "id": step_id,
        "procedure_id": item.get("procedure_id"),
        "order": order,
        "title": title,
        "label": label,
        "body_text": item.get("body_text"),
        "execution_mode": execution_mode,
        "stop_after_completion": item.get("stop_after_completion"),
        "wait_for_user": item.get("wait_for_user"),
        "resource_refs": _as_list(item.get("resource_refs")),
    }


def _display_embedded_step(item: Any, *, fallback_id: str, procedure_id: str | None, source: str) -> dict[str, Any]:
    if isinstance(item, dict):
        order = item.get("order") or item.get("step") or item.get("index")
        title = _first_text(item, ["title", "action", "name", "label"]) or fallback_id
        body_parts = []
        for key in ["body_text", "action", "description", "purpose"]:
            value = item.get(key)
            if value and str(value).strip() and str(value).strip() != title:
                body_parts.append(str(value).strip())
        for key in ["items", "outputs", "rules"]:
            value = item.get(key)
            if isinstance(value, list) and value:
                body_parts.append("\n".join(f"- {entry}" for entry in value))
        execution_mode = _first_text(item, ["execution_mode"])
        label = f"{order}. {title}" if order is not None else title
        if execution_mode:
            label = f"{label} [{execution_mode}]"
        return {
            "id": _first_text(item, ["step_id", "id"]) or fallback_id,
            "procedure_id": procedure_id,
            "order": order,
            "title": title,
            "label": label,
            "body_text": "\n".join(body_parts),
            "execution_mode": execution_mode,
            "stop_after_completion": item.get("stop_after_completion"),
            "wait_for_user": item.get("wait_for_user"),
            "resource_refs": _as_list(item.get("resource_refs")),
            "source": source,
        }
    return {
        "id": fallback_id,
        "procedure_id": procedure_id,
        "order": None,
        "title": str(item),
        "label": str(item),
        "body_text": "",
        "execution_mode": None,
        "stop_after_completion": None,
        "wait_for_user": None,
        "resource_refs": [],
        "source": source,
    }


def _display_resource(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"id": None, "title": str(item), "filename": None, "label": str(item)}
    resource_id = _first_text(item, ["resource_id", "id"])
    title = _first_text(item, ["title", "name", "resource_id"])
    filename = _first_text(item, ["filename", "file_name"])
    label = title
    if filename and filename != title:
        label = f"{title} - {filename}"
    elif resource_id and resource_id != title:
        label = f"{title} - {resource_id}"
    return {
        "id": resource_id,
        "title": title,
        "filename": filename,
        "label": label,
        "document_id": item.get("document_id"),
        "file_status": item.get("file_status"),
        "use_type": item.get("use_type"),
        "domain": item.get("domain"),
        "confidence": item.get("confidence"),
    }


def _display_dependency_group(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"id": None, "title": str(item), "label": str(item)}
    title = _first_text(item, ["title", "name", "group_id"])
    return {
        "id": _first_text(item, ["group_id", "id"]),
        "title": title,
        "label": title,
        "resource_ids": _as_list(item.get("resource_ids")),
        "filenames": _as_list(item.get("filenames")),
    }


def _display_phase_binding(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"id": None, "title": str(item), "label": str(item)}
    title = _first_text(item, ["title", "name", "binding_id"])
    return {
        "id": _first_text(item, ["binding_id", "id"]),
        "title": title,
        "label": title,
        "binding_mode": item.get("binding_mode"),
        "resource_ids": _as_list(item.get("resource_ids")),
        "filenames": _as_list(item.get("filenames")),
    }


def _display_policies(runtime_model: dict[str, Any]) -> list[dict[str, Any]]:
    policies = []
    for field in [
        "global_policies",
        "progression_rules",
        "turn_constraints",
        "response_policies",
        "clarification_gate_rules",
    ]:
        for item in _as_list(runtime_model.get(field)):
            policies.append({"source": field, "label": _display_scalar_or_object(item)})
    return policies


def _steps_by_procedure(step_items: list[Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in step_items:
        step = _display_step(item)
        procedure_id = str(step.get("procedure_id") or "")
        grouped.setdefault(procedure_id, []).append(step)
    for steps in grouped.values():
        steps.sort(key=lambda step: (step.get("order") is None, step.get("order") or 0, step.get("id") or ""))
    return grouped


def _fallback_steps(runtime_model: dict[str, Any]) -> dict[str, tuple[str, list[dict[str, Any]]]]:
    fallback: dict[str, tuple[str, list[dict[str, Any]]]] = {}
    _add_instruction_block_steps(fallback, _as_list(runtime_model.get("instruction_blocks")))
    _add_module_steps(fallback, _as_list(runtime_model.get("support_modules")))
    _add_module_steps(fallback, _as_list(runtime_model.get("followup_modules")))
    return fallback


def _lookup_fallback_steps(
    procedure: dict[str, Any],
    fallback_steps: dict[str, tuple[str, list[dict[str, Any]]]],
) -> tuple[str, list[dict[str, Any]]]:
    candidates = _procedure_match_keys(procedure)
    for key in candidates:
        if key in fallback_steps:
            source, steps = fallback_steps[key]
            return source, steps
    normalized_candidates = [_normalize_match_key(key) for key in candidates]
    for fallback_key, value in fallback_steps.items():
        normalized_fallback = _normalize_match_key(fallback_key)
        if any(_keys_compatible(candidate, normalized_fallback) for candidate in normalized_candidates):
            return value
    return "none", []


def _add_instruction_block_steps(
    fallback: dict[str, tuple[str, list[dict[str, Any]]]],
    blocks: list[Any],
) -> None:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in blocks:
        if not isinstance(item, dict) or item.get("block_type") != "step":
            continue
        workflow = _first_text(item, ["linked_workflow", "linked_mode_id"])
        if not workflow:
            continue
        step = _display_embedded_step(
            {
                "step_id": item.get("block_id"),
                "procedure_id": workflow,
                "order": item.get("linked_step_order"),
                "title": item.get("linked_step_title") or item.get("title"),
                "body_text": item.get("body_text"),
            },
            fallback_id=str(item.get("block_id") or f"instruction_block:{workflow}"),
            procedure_id=workflow,
            source="instruction_blocks",
        )
        grouped.setdefault(workflow, []).append(step)
    for workflow, steps in grouped.items():
        steps.sort(key=lambda step: (step.get("order") is None, step.get("order") or 0, step.get("id") or ""))
        for key in _match_key_variants(workflow):
            fallback.setdefault(key, ("instruction_blocks", steps))


def _add_module_steps(
    fallback: dict[str, tuple[str, list[dict[str, Any]]]],
    modules: list[Any],
) -> None:
    for module in modules:
        if not isinstance(module, dict):
            continue
        source_steps = _module_step_items(module)
        if not source_steps:
            continue
        module_id = _first_text(module, ["module_id", "block_id", "id"])
        title = _first_text(module, ["title", "name"])
        steps = [
            _display_embedded_step(
                step,
                fallback_id=f"{module_id or title or 'module'}:{idx + 1}",
                procedure_id=module_id,
                source="embedded_module_fields",
            )
            for idx, step in enumerate(source_steps)
        ]
        for key in _module_match_keys(module):
            fallback.setdefault(key, ("embedded_module_fields", steps))


def _module_step_items(module: dict[str, Any]) -> list[Any]:
    for key in ["step_sequence", "steps", "tasks", "core_tasks"]:
        values = _as_list(module.get(key))
        if values:
            return values
    rules = _as_list(module.get("rules"))
    if rules:
        return [{"order": idx + 1, "title": str(rule)} for idx, rule in enumerate(rules)]
    return []


def _procedure_match_keys(procedure: dict[str, Any]) -> list[str]:
    values = [
        procedure.get("procedure_id"),
        procedure.get("service_block_id"),
        procedure.get("title"),
    ]
    keys: list[str] = []
    for value in values:
        keys.extend(_match_key_variants(value))
    return _ordered_unique(keys)


def _module_match_keys(module: dict[str, Any]) -> list[str]:
    values = [
        module.get("module_id"),
        module.get("block_id"),
        module.get("id"),
        module.get("title"),
    ]
    keys: list[str] = []
    for value in values:
        keys.extend(_match_key_variants(value))
    return _ordered_unique(keys)


def _match_key_variants(value: Any) -> list[str]:
    if value is None:
        return []
    raw = str(value).strip()
    if not raw:
        return []
    variants = [raw]
    for prefix in [
        "procedure:",
        "primary_workflow:",
        "followup_module:",
        "support_module:",
        "support:",
        "mode:",
    ]:
        if raw.startswith(prefix):
            variants.append(raw[len(prefix):])
    for prefix in [
        "procedure:",
        "primary_workflow:",
        "followup_module:",
        "support_module:",
    ]:
        variants.append(f"{prefix}{raw}")
    return _ordered_unique(variants)


def _normalize_match_key(value: Any) -> str:
    if value is None:
        return ""
    normalized = str(value).strip().lower()
    for prefix in [
        "procedure:",
        "primary_workflow:",
        "followup_module:",
        "support_module:",
        "support:",
        "mode:",
    ]:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    normalized = normalized.replace("procedure:", "")
    normalized = normalized.replace("followup_module:", "")
    normalized = normalized.replace("support_module:", "")
    normalized = normalized.replace("primary_workflow:", "")
    normalized = normalized.replace("followup_module_", "")
    normalized = normalized.replace("support_module_", "")
    normalized = normalized.replace("primary_workflow_", "")
    return normalized


def _keys_compatible(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _ordered_unique(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _display_scalar_or_object(item: Any) -> str:
    if isinstance(item, dict):
        return _first_text(item, ["title", "name", "id", "policy_id"]) or json.dumps(item, ensure_ascii=False)
    return str(item)


def _first_text(item: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _runtime_model(payload: dict[str, Any]) -> dict[str, Any]:
    compiled_contract = payload.get("compiled_contract")
    if not isinstance(compiled_contract, dict):
        return {}
    model = compiled_contract.get("instruction_runtime_model")
    if isinstance(model, dict):
        return model
    hybrid = compiled_contract.get("hybrid_instruction_runtime_model")
    if isinstance(hybrid, dict):
        return hybrid
    return {}


def _procedure_steps(runtime_model: dict[str, Any], procedures: list[Any]) -> list[Any]:
    top_level_steps = _as_list(runtime_model.get("procedure_steps"))
    steps = list(top_level_steps)
    for procedure in procedures:
        if isinstance(procedure, dict):
            steps.extend(_as_list(procedure.get("procedure_steps")))
            steps.extend(_as_list(procedure.get("steps")))
    return steps


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
