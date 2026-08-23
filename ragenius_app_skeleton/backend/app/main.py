"""Integrated FastAPI backend for the builder-backed RAGenius app runtime."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
import copy
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Dict

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel

from .builder_runtime import derive_builder_adapter_json, derive_builder_config_json
from .builder_store import get_builder_store
from .approved_content_service import content_hash_for, resolve_approved_snapshot
from .approved_content_service import create_approved_snapshot, create_snapshot_from_latest_assistant_message, create_snapshot_from_message_id
from .chat_repos import ChatRepo, InstructionUnderstandingRepo, RetrievalRepo, SessionRepo
from .artifact_upload_service import ArtifactUploadService
from .chat_service import run_chat_pipeline
from .instruction_understanding_service import (
    SEMANTIC_COMPILE_PROMPT_VERSION,
    SEMANTIC_COMPILER_VERSION,
    approve_instruction_understanding_findings,
    build_instruction_understanding_compiler,
    build_instruction_understanding_reviewer,
    build_instruction_understanding_reviser,
    force_recompile_instruction_understanding,
    force_review_instruction_understanding,
    load_instruction_understanding_detail,
    prepare_instruction_understanding,
    revise_instruction_understanding,
)
from .dependencies import get_settings
from .exec_router import ExecRouteDecision, parse_exec_turn
from .execution_intent_service import (
    build_execution_intent,
    get_execution_skill_policy,
    validate_execution_skill_request,
)
from .execution_subsystem_client import ExecutionSubsystemClient
from .ingestion_repo import IngestionRepo
from .ingestion_service import enqueue_builder_ingestion
from .llm_runtime import USER_VISIBLE_TASKS, resolve_task_model
from .planner_repo import InMemoryPlannerRepo
from workflows.nodes.load_template_registry import _extract_instruction_workflows

class Utf8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


_artifact_upload_cleanup_task: asyncio.Task | None = None


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    global _artifact_upload_cleanup_task
    await _run_artifact_upload_cleanup_once()
    _artifact_upload_cleanup_task = asyncio.create_task(_artifact_upload_cleanup_loop())
    try:
        yield
    finally:
        _artifact_upload_cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await _artifact_upload_cleanup_task
        _artifact_upload_cleanup_task = None


app = FastAPI(
    title="RAGenius App API",
    default_response_class=Utf8JSONResponse,
    lifespan=_app_lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

session_repo = SessionRepo()
chat_repo = ChatRepo()
instruction_understanding_repo = InstructionUnderstandingRepo()
planner_repo = InMemoryPlannerRepo()
retrieval_repo = RetrievalRepo()
ingestion_repo = IngestionRepo()
execution_client = ExecutionSubsystemClient()

LEGACY_EXEC_SKILL_TO_TOOL = {
    "notebooklm_list_notebooks": "adapter.notebooklm.list_notebooks",
    "notebooklm_list_sources": "adapter.notebooklm.list_sources",
    "notebooklm_existing_notebook_ask": "adapter.notebooklm.ask",
    "notebooklm_poll_artifact_task": "adapter.notebooklm.poll_artifact_task",
    "notebooklm_generate_report": "adapter.notebooklm.generate_report",
    "notebooklm_generate_slide_deck": "adapter.notebooklm.generate_slide_deck",
    "notebooklm_generate_video": "adapter.notebooklm.generate_video",
    "notebooklm_add_source_text": "adapter.notebooklm.add_source_text",
    "notebooklm_add_source_url": "adapter.notebooklm.add_source_url",
    "notebooklm_add_source_file": "adapter.notebooklm.add_source_file",
}


def _require_role(role: str | None, allowed: set[str]) -> None:
    if role not in allowed:
        raise HTTPException(status_code=403, detail="Forbidden")


def require_admin(x_role: str | None = Header(default=None)) -> str:
    _require_role(x_role, {"admin"})
    return x_role or "admin"


class ChatRequest(BaseModel):
    user_id: str
    app_id: str
    domain: str | None = None
    user_query: str
    config_version: int = 1
    adapter_version: int = 1
    template_version: int = 1
    execution_request: dict[str, Any] | None = None
    artifact_refs: list[dict[str, Any]] | None = None


class BuilderIngestPayload(BaseModel):
    document_ids: list[str] | None = None


class SessionUpdateRequest(BaseModel):
    app_id: str
    user_id: str
    title: str | None = None
    pinned: bool | None = None
    archived: bool | None = None


class SessionPrepareRequest(BaseModel):
    app_id: str
    user_id: str
    config_version: int = 1
    adapter_version: int = 1
    template_version: int = 1


class SessionWorkflowActionRequest(BaseModel):
    app_id: str
    user_id: str


class SessionExecutionConfirmRequest(BaseModel):
    app_id: str
    user_id: str


class SessionAgentInteractionResponseRequest(BaseModel):
    app_id: str
    user_id: str
    expected_version: int
    idempotency_key: str
    response: dict[str, Any]


class ApprovedContentCreateRequest(BaseModel):
    app_id: str
    user_id: str
    message_id: str | None = None
    content_text: str | None = None
    use_latest_assistant_message: bool = False
    artifact_refs: list[dict[str, Any]] | None = None
    target_refs: dict[str, Any] | None = None


class ApprovalRequest(BaseModel):
    approved_findings: list[dict[str, Any]]
    approver: str | None = None


class IntegrationActionRequest(BaseModel):
    app_id: str
    user_id: str


class SessionExportRequest(BaseModel):
    app_id: str
    user_id: str
    message_ids: list[str]
    format: str = "md"
    filename: str | None = None


def _extract_session_upload_text(filename: str, mime_type: str | None, content: bytes) -> str:
    suffix = Path(str(filename or "")).suffix.lower()
    if suffix in {".md", ".txt", ".json", ".csv", ".yaml", ".yml"} or str(mime_type or "").startswith("text/"):
        return content.decode("utf-8", errors="ignore")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore
            import io

            reader = PdfReader(io.BytesIO(content))
            return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        except Exception:
            return ""
    return content.decode("utf-8", errors="ignore") if not suffix else ""


def _derive_session_title(user_query: str) -> str:
    normalized = " ".join(str(user_query or "").strip().split())
    if not normalized:
        return "Untitled chat"
    return normalized[:60] + ("..." if len(normalized) > 60 else "")


def _upload_analysis_query(filename: str) -> str:
    safe_name = Path(str(filename or "uploaded artifact")).name
    return f"Analyze the uploaded artifact {safe_name} using the application instructions."


def _session_lane_state(runtime_state: Dict[str, Any] | None) -> Dict[str, Any]:
    state = copy.deepcopy(runtime_state or {})
    lane_state = state.get("session_lane_state", {})
    if not isinstance(lane_state, dict):
        lane_state = {}
    content_lane = lane_state.get("content_lane", {})
    execution_lane = lane_state.get("execution_lane", {})
    lane_state["content_lane"] = content_lane if isinstance(content_lane, dict) else {}
    lane_state["execution_lane"] = execution_lane if isinstance(execution_lane, dict) else {}
    state["session_lane_state"] = lane_state
    return lane_state


def _record_confirmation_lane_state(
    lane_state: Dict[str, Any],
    *,
    result_payload: Dict[str, Any],
) -> None:
    execution_lane = lane_state.get("execution_lane", {})
    if not isinstance(execution_lane, dict):
        return
    result = result_payload.get("result", {})
    result = result if isinstance(result, dict) else {}
    confirmation_id = str(result.get("confirmation_id") or "").strip()
    if confirmation_id:
        execution_lane["latest_confirmation_id"] = confirmation_id
        execution_lane["latest_confirmation_expires_at"] = result.get(
            "confirmation_expires_at"
        )
        execution_lane["latest_confirmation_state"] = str(
            result.get("confirmation_state") or "pending"
        )
        return

    status = str(result_payload.get("status") or "").strip().lower()
    if status in {"completed", "failed", "blocked", "partial"}:
        execution_lane["latest_confirmation_state"] = status


_PROTECTED_PROVIDER_FIELDS = {
    "provider_handle",
    "provider_run_id",
    "provider_session_id",
    "provider_session_key",
    "provider_thread_id",
    "provider_turn_id",
    "run_id",
    "session_key",
    "thread_id",
    "turn_id",
}


def _redact_provider_handles(value: Any) -> Any:
    if isinstance(value, list):
        return [_redact_provider_handles(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: _redact_provider_handles(item)
        for key, item in value.items()
        if str(key).strip().lower() not in _PROTECTED_PROVIDER_FIELDS
        and not str(key).strip().lower().startswith("provider_")
    }


def _contains_provider_handles(value: Any) -> bool:
    if isinstance(value, list):
        return any(_contains_provider_handles(item) for item in value)
    if not isinstance(value, dict):
        return False
    for key, item in value.items():
        normalized = str(key).strip().lower()
        if normalized in _PROTECTED_PROVIDER_FIELDS or normalized.startswith("provider_"):
            return True
        if _contains_provider_handles(item):
            return True
    return False


def _require_successful_execution_proxy(result: Dict[str, Any]) -> None:
    status = result.get("_http_status")
    if isinstance(status, int) and status >= 400:
        raise HTTPException(status_code=status, detail=result.get("error") or "Execution request failed.")
    if result.get("_transport_error"):
        code = str((result.get("error") or {}).get("code") or "")
        status_code = 504 if code == "EXECUTION_SUBSYSTEM_TIMEOUT" else 503
        raise HTTPException(status_code=status_code, detail=result.get("error") or "Execution subsystem unavailable.")


def _record_interaction_lane_state(
    lane_state: Dict[str, Any],
    *,
    interactions_payload: Dict[str, Any] | None = None,
    events_payload: Dict[str, Any] | None = None,
) -> None:
    execution_lane = lane_state.setdefault("execution_lane", {})
    interactions = (interactions_payload or {}).get("items", [])
    if isinstance(interactions, list):
        normalized = [item for item in interactions if isinstance(item, dict)]
        if normalized:
            latest = max(normalized, key=lambda item: int(item.get("sequence") or 0))
            execution_lane["latest_interaction_id"] = latest.get("interaction_id")
            execution_lane["latest_interaction_type"] = latest.get("type")
            execution_lane["latest_interaction_state"] = latest.get("state")
            execution_lane["latest_interaction_version"] = latest.get("version")
            execution_lane["latest_interaction_expires_at"] = latest.get("expires_at")
    if isinstance(events_payload, dict):
        cursor = events_payload.get("next_after_sequence")
        if isinstance(cursor, int) and cursor >= 0:
            execution_lane["last_event_sequence"] = cursor


def _runtime_tool_inventory_items() -> list[dict[str, Any]]:
    getter = getattr(execution_client, "get_tool_inventory", None)
    if not callable(getter):
        return []
    payload = getter() or {}
    if payload.get("_transport_error"):
        return []
    items = payload.get("items", [])
    return [item for item in items if isinstance(item, dict)]


def _runtime_skill_inventory_items(visibility: str | None = None) -> list[dict[str, Any]]:
    getter = getattr(execution_client, "get_skill_inventory", None)
    if not callable(getter):
        return []
    try:
        payload = getter(visibility=visibility) or {}
    except TypeError:
        payload = getter() or {}
    if payload.get("_transport_error"):
        return []
    items = payload.get("items", [])
    rows = [item for item in items if isinstance(item, dict)]
    normalized_visibility = str(visibility or "").strip().lower()
    if normalized_visibility != "user":
        return rows
    filtered: list[dict[str, Any]] = []
    for item in rows:
        inventory_visibility = str(item.get("inventory_visibility") or "").strip().lower()
        workflow_kind = str(item.get("workflow_kind") or "").strip().lower()
        if inventory_visibility == "internal_wrapper":
            continue
        if inventory_visibility == "user_skill":
            filtered.append(item)
            continue
        if workflow_kind in {"multi_step_workflow", "builder_bound"}:
            filtered.append(item)
    return filtered


def _builder_bound_skill_inventory_items(app_id: str) -> list[dict[str, Any]]:
    normalized_app_id = str(app_id or "").strip()
    if not normalized_app_id:
        return []
    builder_store = get_builder_store()
    rows: list[dict[str, Any]] = []
    for binding in builder_store.list_app_skill_bindings(normalized_app_id):
        if not binding.get("enabled"):
            continue
        skill_id = str(binding.get("skill_id") or "").strip()
        if not skill_id:
            continue
        published = builder_store.get_published_skill_definition(
            skill_id=skill_id,
            version=str(binding.get("skill_version") or "").strip() or None,
        )
        if not isinstance(published, dict):
            continue
        rows.append(
            {
                "skill_id": published.get("skill_id") or skill_id,
                "name": published.get("name") or skill_id,
                "version": published.get("version") or binding.get("skill_version"),
                "description": published.get("description") or "",
                "enabled": bool(published.get("enabled", True)),
                "exec_capable": bool(published.get("enabled", True)),
                "exec_kind": "skill",
                "required_tools": published.get("required_tools") or [],
                "required_permissions": published.get("required_permissions") or [],
                "confirmation_mode": binding.get("permission_mode"),
                "result_type": "json",
                "input_schema": published.get("input_schema") or {},
                "output_schema": published.get("output_schema") or {},
                "inventory_source": "builder_bound",
            }
        )
    return rows


def _combined_skill_inventory_items(
    app_id: str | None = None,
    runtime_visibility: str | None = None,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in _runtime_skill_inventory_items(visibility=runtime_visibility):
        skill_id = str(item.get("skill_id") or "").strip()
        if not skill_id:
            continue
        merged[skill_id] = dict(item)
        merged[skill_id].setdefault("inventory_source", "runtime")
    if app_id:
        for item in _builder_bound_skill_inventory_items(app_id):
            skill_id = str(item.get("skill_id") or "").strip()
            if not skill_id:
                continue
            merged[skill_id] = {**merged.get(skill_id, {}), **item}
    return list(merged.values())


def _exec_skill_inventory_items(app_id: str | None = None) -> list[dict[str, Any]]:
    return _combined_skill_inventory_items(app_id=app_id, runtime_visibility="user")


def _exec_tool_inventory_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in _runtime_tool_inventory_items():
        tool_id = str(item.get("tool_id") or "").strip()
        if not tool_id:
            continue
        skill_id = _resolve_runtime_exec_skill_for_tool(tool_id)
        if not skill_id:
            continue
        runtime_skill = _runtime_skill_entry(skill_id)
        merged = dict(item)
        if isinstance(runtime_skill, dict):
            merged["description"] = runtime_skill.get("description") or merged.get("description") or ""
            merged["input_schema"] = runtime_skill.get("input_schema") or {}
            merged["output_schema"] = runtime_skill.get("output_schema") or {}
            merged["required_permissions"] = runtime_skill.get("required_permissions") or []
            merged["confirmation_mode"] = runtime_skill.get("confirmation_mode") or ""
            merged["exec_binding_skill_id"] = skill_id
        artifact_picker = merged.get("artifact_picker")
        if not isinstance(artifact_picker, dict):
            artifact_picker = None
        if artifact_picker and isinstance(merged.get("input_schema"), dict):
            schema_properties = merged["input_schema"].get("properties", {})
            picker_field_name = str(artifact_picker.get("field_name") or "artifactIds").strip() or "artifactIds"
            if isinstance(schema_properties, dict) and picker_field_name in schema_properties:
                merged["artifact_picker"] = {
                    "enabled": True,
                    "field_name": picker_field_name,
                    "selection_mode": str(artifact_picker.get("selection_mode") or "multiple"),
                    "allowed_artifact_types": artifact_picker.get("allowed_artifact_types") or [],
                    "allowed_mime_types": artifact_picker.get("allowed_mime_types") or [],
                    "eligible_for": artifact_picker.get("eligible_for"),
                    "accepted_artifact_types": artifact_picker.get("accepted_artifact_types")
                    or artifact_picker.get("allowed_artifact_types")
                    or [],
                    "required_consumption_mode": artifact_picker.get("required_consumption_mode"),
                    "max_artifact_count": artifact_picker.get("max_artifact_count"),
                }
        items.append(merged)
    return items


def _runtime_skill_entry(skill_id: str, app_id: str | None = None) -> Dict[str, Any] | None:
    normalized = str(skill_id or "").strip()
    if not normalized:
        return None
    for item in _combined_skill_inventory_items(app_id):
        if str(item.get("skill_id") or "").strip() == normalized:
            return item
    return None


def _runtime_tool_entry(tool_id: str) -> Dict[str, Any] | None:
    normalized = str(tool_id or "").strip()
    if not normalized:
        return None
    for item in _runtime_tool_inventory_items():
        if str(item.get("tool_id") or "").strip() == normalized:
            return item
    return None


def _normalize_exec_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _resolve_runtime_tool_id(tool_id: str) -> str | None:
    normalized = str(tool_id or "").strip()
    if not normalized:
        return None
    if _runtime_tool_entry(normalized):
        return normalized
    legacy_match = LEGACY_EXEC_SKILL_TO_TOOL.get(normalized)
    if legacy_match and _runtime_tool_entry(legacy_match):
        return legacy_match
    normalized_alias = _normalize_exec_identifier(normalized)
    for item in _runtime_tool_inventory_items():
        candidate_id = str(item.get("tool_id") or "").strip()
        if not candidate_id:
            continue
        aliases = {
            candidate_id,
            candidate_id.removeprefix("adapter."),
            _normalize_exec_identifier(candidate_id),
            _normalize_exec_identifier(candidate_id.removeprefix("adapter.")),
            _normalize_exec_identifier(str(item.get("name") or "")),
        }
        if normalized in aliases or normalized_alias in aliases:
            return candidate_id
    return None


def _resolve_runtime_exec_skill_for_tool(tool_id: str, app_id: str | None = None) -> str | None:
    normalized_tool_id = str(tool_id or "").strip()
    if not normalized_tool_id:
        return None
    for item in _combined_skill_inventory_items(app_id):
        required_tools = item.get("required_tools", [])
        if (
            isinstance(required_tools, list)
            and len(required_tools) == 1
            and str(required_tools[0] or "").strip() == normalized_tool_id
        ):
            return str(item.get("skill_id") or "").strip() or None
    return None


def _effective_skill_policy(
    skill_id: str,
    runtime_skill: Dict[str, Any] | None = None,
    app_id: str | None = None,
) -> Dict[str, Any]:
    policy = get_execution_skill_policy(skill_id)
    if policy.get("supported"):
        return policy
    required_permissions = runtime_skill.get("required_permissions", []) if isinstance(runtime_skill, dict) else []
    confirmation_mode = str(runtime_skill.get("confirmation_mode") or "").strip().lower() if isinstance(runtime_skill, dict) else ""
    read_only = bool(required_permissions) and all(
        isinstance(scope, str) and scope.endswith(".read") for scope in required_permissions
    )
    return {
        "supported": runtime_skill is not None,
        "supported_skill_ids": sorted(
            str(item.get("skill_id") or "").strip()
            for item in _combined_skill_inventory_items(app_id)
            if str(item.get("skill_id") or "").strip()
        ),
        "requires_approved_content": False,
        "read_only": read_only,
        "review_required": confirmation_mode == "require_confirmation",
        "required_all": [],
        "required_any_of": [],
    }


def _exec_summary_text(
    skill_id: str,
    submit_result: Dict[str, Any],
    approved_snapshot: Dict[str, Any] | None = None,
    execution_intent: Dict[str, Any] | None = None,
) -> str:
    login_requirement = _resolve_notebooklm_login_requirement(submit_result)
    if login_requirement:
        return (
            f"Login to NotebookLM is required before retrying `{skill_id}`. "
            f"Run `{login_requirement['login_command']}` or use the NotebookLM login action, then retry the last @exec request."
        )
    if isinstance(submit_result.get("error"), dict):
        return f"Execution request for `{skill_id}` failed."
    status = str(submit_result.get("status") or submit_result.get("state") or "submitted").strip()
    execution_id = str(submit_result.get("execution_id") or "").strip()
    result_payload = submit_result.get("result")
    result_payload = result_payload if isinstance(result_payload, dict) else {}
    background_status = str(result_payload.get("status") or result_payload.get("state") or "").strip()
    task_id = str(result_payload.get("task_id") or "").strip()
    execution_mode = str((execution_intent or {}).get("execution_mode") or "").strip().lower()
    approved_suffix = ""
    if isinstance(approved_snapshot, dict):
        revision_id = str(approved_snapshot.get("revision_id") or "").strip()
        approved_content_id = str(approved_snapshot.get("approved_content_id") or "").strip()
        if revision_id:
            approved_suffix = f" Using approved revision `{revision_id}`."
        elif approved_content_id:
            approved_suffix = f" Using approved content `{approved_content_id}`."
    suffix = f" Execution id: {execution_id}." if execution_id else ""
    task_suffix = f" Provider task id: {task_id}." if task_id else ""
    if execution_mode == "async":
        background_label = background_status or "submitted"
        return (
            f"Background job submitted for `{skill_id}` with status `{background_label}`."
            f"{approved_suffix}{suffix}{task_suffix}"
        )
    if status.lower() in {"submitted", "queued", "running"}:
        return f"Execution submitted for `{skill_id}`.{approved_suffix}{suffix}"
    return f"Execution request for `{skill_id}` is {status}.{approved_suffix}{suffix}"


def _safe_filename_stem(value: str, fallback: str = "chat-export") -> str:
    stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(value or "").strip())
    stem = stem.strip("-_")
    return stem[:80] or fallback


def _humanize_label(value: str, fallback: str = "Chat Export") -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return fallback
    parts = [segment for segment in re.split(r"[-_\s]+", normalized) if segment]
    if not parts:
        return fallback
    return " ".join(part[:1].upper() + part[1:] for part in parts)[:80]


def _derive_chat_export_display_name(
    *,
    session: dict[str, Any],
    explicit_filename: str | None,
    extension: str,
) -> str:
    explicit_stem = Path(str(explicit_filename or "").strip()).stem
    if explicit_stem:
        label = _humanize_label(explicit_stem, "Chat Export")
        return f"Chat Export - {label}.{extension}"
    session_title = str(session.get("title") or "").strip()
    if session_title:
        label = _humanize_label(session_title[:60], "Chat Export")
        return f"Chat Export - {label}.{extension}"
    return f"Chat Export.{extension}"


def _derive_reviewed_artifact_display_name(snapshot: dict[str, Any]) -> str:
    content_text = str(snapshot.get("content_text") or "").strip()
    preview = re.sub(r"\s+", " ", content_text)[:40].strip()
    label = _humanize_label(preview, "Reviewed Chat")
    return f"Reviewed Chat - {label}.md"


def _render_reviewed_chat_artifact_content(snapshot: dict[str, Any]) -> str:
    revision_id = str(snapshot.get("revision_id") or "").strip()
    source_message_id = str(snapshot.get("source_message_id") or "").strip()
    content_text = str(snapshot.get("content_text") or "").strip()
    header_lines = ["# Reviewed Chat Content", ""]
    if revision_id:
        header_lines.append(f"- Revision: `{revision_id}`")
    if source_message_id:
        header_lines.append(f"- Source message: `{source_message_id}`")
    if len(header_lines) > 2:
        header_lines.append("")
    header_lines.extend([content_text, ""])
    return "\n".join(header_lines)


def _absolutize_local_path(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    candidate = Path(normalized)
    if candidate.is_absolute():
        return str(candidate.resolve())
    repo_root = Path(__file__).resolve().parents[3]
    candidates = [
        Path.cwd() / candidate,
        repo_root / candidate,
        repo_root / "ragenius_execution_subsystem" / candidate,
    ]
    for resolved in candidates:
        if resolved.exists():
            return str(resolved.resolve())
    return str((repo_root / "ragenius_execution_subsystem" / candidate).resolve())


def _normalize_artifact_inventory_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row.pop("path", None)
        row.pop("file_path", None)
        consumption = item.get("consumption")
        if isinstance(consumption, dict):
            row["consumption"] = {
                "default_mode": consumption.get("default_mode"),
                "supported_modes": list(consumption.get("supported_modes") or []),
            }
        normalized_rows.append(row)
    return normalized_rows


def _build_session_artifact_open_url(
    *,
    session_id: str,
    app_id: str,
    user_id: str,
    artifact_id: str,
) -> str:
    return (
        f"/sessions/{session_id}/artifacts/{artifact_id}/file"
        f"?app_id={app_id}&user_id={user_id}"
    )


def _build_session_artifact_preview_url(
    *,
    session_id: str,
    app_id: str,
    user_id: str,
    artifact_id: str,
) -> str:
    return (
        f"/sessions/{session_id}/artifacts/{artifact_id}/preview"
        f"?app_id={app_id}&user_id={user_id}"
    )


def _artifact_is_previewable(item: dict[str, Any]) -> bool:
    mime_type = str(item.get("mime_type") or "").strip().lower()
    file_path = str(item.get("file_path") or item.get("path") or "").strip().lower()
    if mime_type.startswith("text/") or mime_type in {"application/pdf", "application/json"}:
        return True
    return file_path.endswith((".md", ".txt", ".pdf", ".json", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4"))


def _artifact_default_consumption(artifact_type: str) -> dict[str, Any] | None:
    normalized = str(artifact_type or "").strip()
    if normalized in {"agent_output", "chat_export", "notebooklm_report"}:
        return {
            "default_mode": "file_backed",
            "supported_modes": ["file_backed", "inline_text", "metadata_only"],
        }
    return None


def _artifact_type_label(artifact_type: str) -> str:
    explicit = {
        "chat_export": "Chat Export",
        "session_upload": "Session Upload",
        "notebooklm_report": "NotebookLM Report",
        "notebooklm_slide_deck": "NotebookLM Slide Deck",
        "notebooklm_video": "NotebookLM Video",
        "notebooklm_answer": "NotebookLM Answer",
        "google_drive_export": "Drive Export",
        "gmail_draft": "Gmail Draft",
        "file_inventory": "File Inventory",
    }
    normalized = str(artifact_type or "").strip()
    if normalized in explicit:
        return explicit[normalized]
    parts = [segment for segment in normalized.replace("-", "_").split("_") if segment]
    return " ".join(part.capitalize() for part in parts) or "Artifact"


def _artifact_source_kind(item: dict[str, Any]) -> str | None:
    artifact_type = str(item.get("artifact_type") or "").strip()
    source_skill_id = str(item.get("source_skill_id") or "").strip()
    source_tool_id = str(item.get("source_tool_id") or "").strip()
    if artifact_type == "chat_export":
        return "chat_export"
    if source_skill_id or source_tool_id:
        return "execution"
    if artifact_type == "session_upload":
        return "upload"
    return None


def _artifact_source_label(item: dict[str, Any]) -> str | None:
    source_skill_id = str(item.get("source_skill_id") or "").strip()
    source_tool_id = str(item.get("source_tool_id") or "").strip()
    provider_origin = str(item.get("provider_origin") or "").strip()
    artifact_type_label = _artifact_type_label(str(item.get("artifact_type") or "").strip())
    if source_skill_id:
        return f"Generated by {source_skill_id}"
    if source_tool_id:
        return f"Generated by {source_tool_id}"
    if provider_origin == "notebooklm":
        return f"Produced by {artifact_type_label}"
    if str(item.get("artifact_type") or "").strip() == "chat_export":
        return "Created from selected chat messages"
    return None


def _artifact_file_info(item: dict[str, Any]) -> dict[str, Any]:
    display_name = str(item.get("display_name") or "").strip()
    extension = Path(display_name).suffix.lower() if display_name else ""
    size_bytes = item.get("size_bytes")
    return {
        "has_file": bool(str(item.get("artifact_id") or "").strip()),
        "extension": extension or None,
        "size_bytes": size_bytes if isinstance(size_bytes, int) else None,
    }


def _normalize_session_artifact_item(
    *,
    session_id: str,
    app_id: str,
    user_id: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    artifact_id = str(item.get("artifact_id") or "").strip()
    preview_url = (
        _build_session_artifact_preview_url(
            session_id=session_id,
            app_id=app_id,
            user_id=user_id,
            artifact_id=artifact_id,
        )
        if artifact_id and _artifact_is_previewable(item)
        else None
    )
    open_url = (
        _build_session_artifact_open_url(
            session_id=session_id,
            app_id=app_id,
            user_id=user_id,
            artifact_id=artifact_id,
        )
        if artifact_id
        else None
    )
    delete_url = (
        f"/sessions/{session_id}/artifacts/{artifact_id}?app_id={app_id}&user_id={user_id}"
        if artifact_id
        else None
    )
    file_info = _artifact_file_info(item)
    source_kind = _artifact_source_kind(item)
    source_label = _artifact_source_label(item)
    return {
        **item,
        "session_id": str(item.get("session_id") or session_id).strip() or session_id,
        "app_id": str(item.get("app_id") or app_id).strip() or app_id,
        "artifact_type_label": _artifact_type_label(str(item.get("artifact_type") or "").strip()),
        "summary": str(item.get("summary") or "").strip() or None,
        "preview_url": preview_url,
        "open_url": open_url,
        "routes": {
            "open": open_url,
            "preview": preview_url,
            "delete": delete_url,
        },
        "capabilities": {
            "can_open": bool(open_url and file_info["has_file"]),
            "can_preview": bool(preview_url and file_info["has_file"]),
            "can_delete": bool(delete_url),
            "can_reuse": bool(item.get("eligible_consumers") or item.get("consumption")),
        },
        "file_info": file_info,
        "provenance": {
            "source_kind": source_kind,
            "source_label": source_label,
            "source_session_id": str(item.get("session_id") or session_id).strip() or session_id,
            "source_message_id": str(item.get("created_by_turn_id") or "").strip() or None,
            "source_execution_id": str(item.get("created_by_execution_id") or "").strip() or None,
        },
        "debug": {
            "artifact_id": artifact_id,
        },
    }


def _enrich_execution_result_artifacts(
    *,
    session_id: str,
    app_id: str,
    user_id: str,
    submit_result: Dict[str, Any],
) -> Dict[str, Any]:
    result_payload = submit_result.get("result")
    if not isinstance(result_payload, dict):
        return submit_result
    raw_artifacts = result_payload.get("artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        return submit_result

    artifact_ids = [
        str(item.get("artifact_id") or "").strip()
        for item in raw_artifacts
        if isinstance(item, dict) and str(item.get("artifact_id") or "").strip()
    ]
    inventory_by_id: dict[str, dict[str, Any]] = {}
    if artifact_ids:
        try:
            inventory_payload = execution_client.get_artifact_inventory(
                app_id=app_id,
                session_id=session_id,
                artifact_type=None,
                eligible_for=None,
                status="ready",
            ) or {}
            inventory_items = _normalize_artifact_inventory_items(
                [item for item in inventory_payload.get("items", []) if isinstance(item, dict)]
            )
            for item in inventory_items:
                artifact_id = str(item.get("artifact_id") or "").strip()
                if artifact_id:
                    inventory_by_id[artifact_id] = item
        except Exception:
            inventory_by_id = {}

    enriched_artifacts: list[dict[str, Any]] = []
    for raw_item in raw_artifacts:
        if not isinstance(raw_item, dict):
            continue
        artifact_id = str(raw_item.get("artifact_id") or "").strip()
        inventory_item = inventory_by_id.get(artifact_id, {})
        merged = {**raw_item, **inventory_item}
        artifact_type = str(merged.get("artifact_type") or raw_item.get("artifact_type") or "").strip()
        if artifact_type and not isinstance(merged.get("consumption"), dict):
            consumption = _artifact_default_consumption(artifact_type)
            if consumption:
                merged["consumption"] = consumption
        if not merged.get("eligible_consumers") and artifact_type == "agent_output":
            merged["eligible_consumers"] = ["execution_composer", "agent_context"]
        enriched_artifacts.append(
            _normalize_session_artifact_item(
                session_id=session_id,
                app_id=app_id,
                user_id=user_id,
                item=merged,
            )
            if artifact_id
            else merged
        )

    return {
        **submit_result,
        "result": {
            **result_payload,
            "artifacts": enriched_artifacts,
        },
    }


def _resolve_session_artifact(
    *,
    app_id: str,
    session_id: str,
    artifact_id: str,
) -> dict[str, Any] | None:
    payload = execution_client.get_artifact_inventory(
        app_id=app_id,
        session_id=session_id,
        artifact_type=None,
        eligible_for=None,
        status="ready",
    ) or {}
    items = _normalize_artifact_inventory_items(
        [item for item in payload.get("items", []) if isinstance(item, dict)]
    )
    return next(
        (item for item in items if str(item.get("artifact_id") or "").strip() == artifact_id),
        None,
    )


def _normalize_artifact_id_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    normalized = str(value or "").strip()
    return [normalized] if normalized else []


def _artifact_picker_field_specs(
    *,
    inventory_target: Dict[str, Any] | None,
    overrides: Dict[str, Any],
) -> dict[str, dict[str, Any]]:
    field_specs: dict[str, dict[str, Any]] = {}
    artifact_picker = (
        inventory_target.get("artifact_picker")
        if isinstance(inventory_target, dict)
        else None
    )
    if isinstance(artifact_picker, dict) and artifact_picker.get("enabled", True):
        field_name = str(artifact_picker.get("field_name") or "artifactIds").strip()
        if field_name:
            field_specs[field_name] = artifact_picker
    if "artifactIds" in overrides and "artifactIds" not in field_specs:
        field_specs["artifactIds"] = {"field_name": "artifactIds"}
    return field_specs


def _resolve_artifact_consumption_mode(
    *,
    artifact: dict[str, Any],
    picker_spec: dict[str, Any],
) -> str | None:
    consumption = artifact.get("consumption") if isinstance(artifact.get("consumption"), dict) else {}
    supported_modes = [
        str(item).strip()
        for item in (consumption.get("supported_modes") or [])
        if str(item).strip()
    ]
    default_mode = str(consumption.get("default_mode") or "").strip()
    required_mode = str(picker_spec.get("required_consumption_mode") or "").strip()
    if required_mode:
        if supported_modes and required_mode not in supported_modes:
            artifact_id = str(artifact.get("artifact_id") or "").strip()
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Artifact `{artifact_id}` does not support required consumption mode "
                    f"`{required_mode}`."
                ),
            )
        return required_mode
    return default_mode or None


def _build_execution_artifact_ref(
    *,
    artifact: dict[str, Any],
    field_name: str,
    picker_spec: dict[str, Any],
) -> dict[str, Any]:
    consumption = artifact.get("consumption") if isinstance(artifact.get("consumption"), dict) else {}
    resolved_mode = _resolve_artifact_consumption_mode(
        artifact=artifact,
        picker_spec=picker_spec,
    )
    artifact_id = str(artifact.get("artifact_id") or "").strip()
    return {
        "artifact_id": artifact_id,
        "field_name": field_name,
        "display_name": str(artifact.get("display_name") or artifact_id).strip() or artifact_id,
        "artifact_type": str(artifact.get("artifact_type") or "").strip() or None,
        "mime_type": str(artifact.get("mime_type") or "").strip() or None,
        "consumption": {
            "default_mode": consumption.get("default_mode"),
            "supported_modes": list(consumption.get("supported_modes") or []),
            "resolved_mode": resolved_mode,
        },
    }


def _mapped_artifact_field_value(
    *,
    field_name: str,
    artifact_refs: list[dict[str, Any]],
    original_was_list: bool,
) -> Any:
    if field_name == "artifactIds":
        values = [str(ref.get("artifact_id") or "").strip() for ref in artifact_refs]
    else:
        values = []
        for ref in artifact_refs:
            resolved_mode = str(ref.get("consumption", {}).get("resolved_mode") or "").strip()
            if resolved_mode == "file_backed":
                values.append(str(ref.get("artifact_id") or "").strip())
            else:
                values.append(str(ref.get("artifact_id") or "").strip())
    values = [value for value in values if value]
    if original_was_list:
        return values
    return values[0] if values else ""


def _attach_resolved_artifact_refs(
    *,
    app_id: str,
    session_id: str,
    inventory_target: Dict[str, Any] | None,
    overrides: Dict[str, Any],
) -> Dict[str, Any]:
    field_specs = _artifact_picker_field_specs(
        inventory_target=inventory_target,
        overrides=overrides,
    )
    if not field_specs:
        return overrides

    resolved_refs: list[dict[str, Any]] = []
    reuse_fields: dict[str, list[str]] = {}
    mapped_field_values: dict[str, Any] = {}
    for field_name, picker_spec in field_specs.items():
        raw_field_value = overrides.get(field_name)
        artifact_ids = _normalize_artifact_id_values(raw_field_value)
        if not artifact_ids:
            continue
        reuse_fields[field_name] = artifact_ids
        field_refs: list[dict[str, Any]] = []
        for artifact_id in artifact_ids:
            artifact = _resolve_session_artifact(
                app_id=app_id,
                session_id=session_id,
                artifact_id=artifact_id,
            )
            if artifact is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Artifact `{artifact_id}` was not found in this session.",
                )
            field_refs.append(
                _build_execution_artifact_ref(
                    artifact=artifact,
                    field_name=field_name,
                    picker_spec=picker_spec,
                )
            )
        resolved_refs.extend(field_refs)
        mapped_field_values[field_name] = _mapped_artifact_field_value(
            field_name=field_name,
            artifact_refs=field_refs,
            original_was_list=isinstance(raw_field_value, list),
        )

    if not resolved_refs:
        return overrides

    enriched = dict(overrides)
    for field_name, mapped_value in mapped_field_values.items():
        if mapped_value != "" and mapped_value != []:
            enriched[field_name] = mapped_value
    existing_refs = enriched.get("artifactRefs")
    enriched["artifactRefs"] = [
        *(existing_refs if isinstance(existing_refs, list) else []),
        *resolved_refs,
    ]
    enriched["artifact_reuse"] = {
        "fields": reuse_fields,
        "artifact_count": len(resolved_refs),
    }
    return enriched


def _normalize_exec_overrides_for_skill(skill_id: str, overrides: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(overrides or {})
    if skill_id in {"gmail_create_draft", "gmail_create_draft_with_attachments", "gmail_send_message"}:
        recipients = normalized.get("to")
        if isinstance(recipients, list):
            normalized["to"] = ", ".join(
                str(item).strip() for item in recipients if str(item).strip()
            )
    return normalized


def _structured_execution_request(payload: ChatRequest) -> Dict[str, Any]:
    request_payload = payload.execution_request
    return request_payload if isinstance(request_payload, dict) else {}


def _coerce_list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _agent_artifact_refs_from_request(payload: ChatRequest) -> list[dict[str, Any]]:
    request_payload = _structured_execution_request(payload)
    return _coerce_list_of_dicts(
        request_payload.get("artifact_refs")
        if "artifact_refs" in request_payload
        else request_payload.get("artifactRefs")
    )


def _agent_expected_outputs_from_request(payload: ChatRequest) -> list[dict[str, Any]]:
    request_payload = _structured_execution_request(payload)
    return _coerce_list_of_dicts(
        request_payload.get("expected_outputs")
        if "expected_outputs" in request_payload
        else request_payload.get("expectedOutputs")
    )


def _agent_interaction_requirements_from_request(
    payload: ChatRequest,
) -> dict[str, Any] | None:
    request_payload = _structured_execution_request(payload)
    value = request_payload.get("interaction_requirements")
    if value is None:
        value = request_payload.get("interactionRequirements")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise HTTPException(
            status_code=400,
            detail="interaction_requirements must be an object.",
        )
    if set(value) - {"transport", "style", "allowed_types", "required_types"}:
        raise HTTPException(status_code=400, detail="Unknown interaction requirement field.")
    transport = value.get("transport")
    if transport is not None and str(transport or "").strip() != "interactive":
        raise HTTPException(
            status_code=400,
            detail="interaction_requirements.transport must be interactive.",
        )
    normalized: dict[str, Any] = {}
    if transport is not None:
        normalized["transport"] = "interactive"
    style = value.get("style")
    if style is not None:
        normalized_style = str(style or "").strip()
        if normalized_style not in {"structured", "chat"}:
            raise HTTPException(
                status_code=400,
                detail="interaction_requirements.style must be structured or chat.",
            )
        normalized["style"] = normalized_style
    for field_name in ("allowed_types", "required_types"):
        field_value = value.get(field_name)
        if field_value is None:
            continue
        if not isinstance(field_value, list):
            raise HTTPException(
                status_code=400,
                detail=f"interaction_requirements.{field_name} must be a list.",
            )
        interaction_types = [str(item or "").strip() for item in field_value]
        if (
            len(set(interaction_types)) != len(interaction_types)
            or any(item not in {"clarification", "selection"} for item in interaction_types)
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"interaction_requirements.{field_name} must contain unique "
                    "clarification or selection values."
                ),
            )
        normalized[field_name] = interaction_types
    if normalized.get("style") == "chat" and (
        normalized.get("allowed_types") or normalized.get("required_types")
    ):
        raise HTTPException(
            status_code=400,
            detail="Chat-level interaction cannot advertise typed interactions.",
        )
    if (
        normalized.get("style") != "chat"
        and not normalized.get("allowed_types")
        and not normalized.get("required_types")
    ):
        raise HTTPException(
            status_code=400,
            detail="At least one allowed or required interaction type is needed.",
        )
    return normalized


def _agent_skill_ref_from_request(payload: ChatRequest) -> dict[str, str] | None:
    request_payload = _structured_execution_request(payload)
    value = request_payload.get("agent_skill_ref")
    if value is None:
        value = request_payload.get("agentSkillRef")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail="agent_skill_ref must be an object.")
    agent_skill_id = str(value.get("agent_skill_id") or value.get("agentSkillId") or "").strip()
    approved_fingerprint = str(
        value.get("approved_fingerprint") or value.get("approvedFingerprint") or ""
    ).strip()
    if not agent_skill_id or not approved_fingerprint:
        raise HTTPException(
            status_code=400,
            detail="agent_skill_ref requires agent_skill_id and approved_fingerprint.",
        )
    return {
        "agent_skill_id": agent_skill_id,
        "approved_fingerprint": approved_fingerprint,
    }


def _safe_agent_output_display_name(value: str) -> str:
    normalized = " ".join(str(value or "").strip().split())
    normalized = normalized.replace("\\", "-").replace("/", "-").replace(":", "-")
    normalized = "".join(ch for ch in normalized if ch.isprintable() and ch not in '<>"|?*')
    normalized = normalized.strip(" .-_")
    if not normalized:
        return "openclaw-result.md"
    if not Path(normalized).suffix:
        normalized = f"{normalized}.md"
    return normalized[:100]


def _infer_agent_output_display_name(agent_query: str) -> str | None:
    text = " ".join(str(agent_query or "").strip().split())
    if not text:
        return None
    action_match = re.search(
        r"\b(?:create|write|save|export|produce|generate|prepare)\s+"
        r"(?:a|an|the)?\s*(?:file|artifact|document|output)?\s*"
        r"(?:named|called|titled|as)?\s*"
        r"[\"“”']?([^\"“”']{1,80}?\.(?:md|markdown|txt|pdf|json))\b",
        text,
        flags=re.IGNORECASE,
    )
    if action_match:
        return _safe_agent_output_display_name(action_match.group(1))
    quoted = re.findall(r'["“”\']([^"“”\']{1,80}?\.(?:md|markdown|txt|pdf|json))["“”\']', text, flags=re.IGNORECASE)
    if quoted:
        return _safe_agent_output_display_name(quoted[-1])
    title_match = re.search(
        r"\b(?:titled|named|called|title)\s+[\"“”']([^\"“”']{1,80})[\"“”']",
        text,
        flags=re.IGNORECASE,
    )
    if title_match:
        return _safe_agent_output_display_name(title_match.group(1))
    return None


def _agent_expected_outputs_for_openclaw(
    *,
    payload: ChatRequest,
    agent_query: str,
) -> list[dict[str, Any]]:
    expected_outputs = _agent_expected_outputs_from_request(payload)
    inferred_display_name = _infer_agent_output_display_name(agent_query)
    if expected_outputs:
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(expected_outputs):
            row = dict(item)
            if index == 0 and inferred_display_name and not str(row.get("display_name") or "").strip():
                row["display_name"] = inferred_display_name
            normalized.append(row)
        return normalized
    if not inferred_display_name:
        return []
    return [
        {
            "output_id": "agent_answer",
            "display_name": inferred_display_name,
            "media_type": "text/markdown",
            "required": True,
            "persist_as_artifact": True,
            "artifact_type": "agent_output",
        }
    ]


def _render_chat_export_content(messages: list[dict[str, Any]], export_format: str) -> str:
    normalized_format = str(export_format or "md").strip().lower()
    blocks: list[str] = []
    for index, message in enumerate(messages, start=1):
        role = "Assistant" if str(message.get("role") or "") == "assistant" else "User"
        content = str(message.get("content") or "").strip()
        if normalized_format == "txt":
            blocks.append(f"[{index}] {role}\n{content}")
        else:
            blocks.append(f"## {index}. {role}\n\n{content}")
    return "\n\n".join(blocks).strip()


def _execution_output_text(result: Dict[str, Any]) -> str:
    result_payload = result.get("result")
    if not isinstance(result_payload, dict):
        return ""
    return str(result_payload.get("output_text") or "").strip()


def _append_execution_output(summary: str, result: Dict[str, Any]) -> str:
    output_text = _execution_output_text(result)
    return f"{summary}\n\n{output_text}" if output_text else summary


def _execution_confirmation_summary_text(execution_id: str, result: Dict[str, Any]) -> str:
    normalized_execution_id = str(execution_id or "").strip()
    login_requirement = _resolve_notebooklm_login_requirement(result)
    if login_requirement:
        return (
            f"Login to NotebookLM is required before confirming `{normalized_execution_id}` further. "
            f"Run `{login_requirement['login_command']}` or use the NotebookLM login action, then retry confirmation."
        )
    if isinstance(result.get("error"), dict):
        message = str(result["error"].get("message") or "").strip()
        return message or f"Execution `{normalized_execution_id}` failed after confirmation."
    status = str(result.get("status") or result.get("state") or "unknown").strip()
    if status == "completed":
        return _append_execution_output(
            f"Execution `{normalized_execution_id}` confirmed and completed.",
            result,
        )
    if status == "pending_confirmation":
        return f"Execution `{normalized_execution_id}` is still pending confirmation."
    return f"Execution `{normalized_execution_id}` confirmed and is now {status}."


def _record_async_lane_state(
    lane_state: Dict[str, Any],
    *,
    execution_intent: Dict[str, Any],
    submit_result: Dict[str, Any],
) -> None:
    execution_lane = lane_state.setdefault("execution_lane", {})
    execution_mode = str(execution_intent.get("execution_mode") or "sync").strip().lower()
    execution_lane["latest_execution_mode"] = execution_mode
    result_payload = submit_result.get("result")
    result_payload = result_payload if isinstance(result_payload, dict) else {}
    task_id = str(result_payload.get("task_id") or "").strip()
    task_status = str(result_payload.get("status") or result_payload.get("state") or "").strip()
    if execution_mode == "async":
        if task_id:
            execution_lane["latest_async_task_id"] = task_id
        if task_status:
            execution_lane["latest_async_task_status"] = task_status
    else:
        execution_lane.pop("latest_async_task_id", None)
        execution_lane.pop("latest_async_task_status", None)


def _extract_execution_error(payload: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    direct_error = payload.get("error")
    if isinstance(direct_error, dict):
        return direct_error
    body = payload.get("body")
    if isinstance(body, dict):
        body_error = body.get("error")
        if isinstance(body_error, dict):
            return body_error
    return None


def _resolve_notebooklm_login_requirement(payload: Dict[str, Any] | None) -> Dict[str, Any] | None:
    error_payload = _extract_execution_error(payload)
    if not isinstance(error_payload, dict):
        return None
    code = str(error_payload.get("code") or "").strip().upper()
    message = str(error_payload.get("message") or "").strip()
    suggested_action = str(error_payload.get("suggested_action") or "").strip()
    details = error_payload.get("details")
    detail_error = ""
    if isinstance(details, dict):
        detail_error = str(details.get("error") or "").strip()
    detail_text = " ".join(filter(None, [message, suggested_action, detail_error])).lower()
    auth_required = code in {"NOTEBOOKLM_AUTH_FAILED", "NOTEBOOKLM_AUTH_REQUIRED"} or (
        code == "NOTEBOOKLM_BRIDGE_FAILED"
        and (
            "storage file not found" in detail_text
            or "login" in detail_text
            or "authentication" in detail_text
            or "unauthorized" in detail_text
        )
    )
    if not auth_required:
        return None
    return {
        "provider": "notebooklm",
        "auth_required": True,
        "login_command": "python -m notebooklm login",
        "reason_code": code,
        "message": message or "NotebookLM login is required.",
    }


def _record_login_requirement(
    lane_state: Dict[str, Any],
    *,
    result_payload: Dict[str, Any],
) -> None:
    execution_lane = lane_state.setdefault("execution_lane", {})
    login_requirement = _resolve_notebooklm_login_requirement(result_payload)
    if login_requirement:
        execution_lane["latest_login_requirement"] = login_requirement
    else:
        execution_lane.pop("latest_login_requirement", None)


def _launch_notebooklm_login() -> Dict[str, Any]:
    python_command = str(os.getenv("NOTEBOOKLM_PYTHON_COMMAND") or sys.executable).strip() or sys.executable
    command = [python_command, "-m", "notebooklm", "login"]
    creation_flags = 0
    if os.name == "nt":
        creation_flags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    subprocess.Popen(
        command,
        cwd=str(Path.cwd()),
        creationflags=creation_flags,
        close_fds=False if os.name == "nt" else True,
    )
    return {
        "ok": True,
        "command": " ".join(command),
        "python_command": python_command,
    }


def _refresh_async_lane_state_from_status(
    lane_state: Dict[str, Any],
    *,
    status_result: Dict[str, Any],
) -> None:
    execution_lane = lane_state.setdefault("execution_lane", {})
    result_payload = status_result.get("result")
    result_payload = result_payload if isinstance(result_payload, dict) else {}
    task_id = str(result_payload.get("task_id") or "").strip()
    task_status = str(result_payload.get("status") or result_payload.get("state") or "").strip()
    if task_id:
        execution_lane["latest_async_task_id"] = task_id
        execution_lane["latest_execution_mode"] = "async"
    if task_status and execution_lane.get("latest_execution_mode") == "async":
        execution_lane["latest_async_task_status"] = task_status
    _record_login_requirement(lane_state, result_payload=status_result)


def _artifact_kind_for_skill(skill_id: str) -> str | None:
    normalized = str(skill_id or "").strip()
    if normalized == "notebooklm_generate_video":
        return "video"
    if normalized == "notebooklm_generate_report":
        return "report"
    if normalized == "notebooklm_generate_slide_deck":
        return "slide_deck"
    return None


def _agent_exec_summary_text(
    submit_result: Dict[str, Any],
    *,
    provider_label: str = "Codex",
    agent_skill_hint: str | None = None,
) -> str:
    def _shorten(value: Any, limit: int = 220) -> str:
        text = " ".join(str(value or "").strip().split())
        if not text:
            return ""
        if len(text) <= limit:
            return text
        return f"{text[: max(0, limit - 1)].rstrip()}…"

    def _render_user_summary(result_payload: Dict[str, Any]) -> str:
        user_summary = result_payload.get("user_summary")
        user_summary = user_summary if isinstance(user_summary, dict) else {}
        title = str(user_summary.get("title") or "").strip()
        subtitle = str(user_summary.get("subtitle") or "").strip()
        preview = _shorten(user_summary.get("preview") or "", 240)
        if not title:
            return ""
        heading = f"{title} ({subtitle})" if subtitle else title
        return f"{heading} {preview}".strip() if preview else heading

    status = str(submit_result.get("status") or "").strip().lower()
    if status == "pending_confirmation":
        result_payload = submit_result.get("result")
        result_payload = result_payload if isinstance(result_payload, dict) else {}
        risk_class = str(result_payload.get("risk_class") or "agent_external_write").strip()
        risk_label = risk_class.removeprefix("agent_").replace("_", " ")
        skill_text = f" using `{agent_skill_hint}`" if str(agent_skill_hint or "").strip() else ""
        return (
            f"{provider_label} agent request{skill_text} requires confirmation before proceeding "
            f"because it is classified as `{risk_label}`."
        )
    if status == "queued":
        execution_id = str(submit_result.get("execution_id") or "").strip()
        suffix = f" Execution id: {execution_id}." if execution_id else ""
        return f"{provider_label} agent request is queued.{suffix}"
    if status == "running":
        execution_id = str(submit_result.get("execution_id") or "").strip()
        suffix = f" Execution id: {execution_id}." if execution_id else ""
        return f"{provider_label} agent request is running.{suffix}"

    error_payload = submit_result.get("error")
    if isinstance(error_payload, dict):
        error_code = str(error_payload.get("code") or "").strip()
        if error_code == "PERMISSION_BLOCKED":
            return f"{provider_label} agent request is blocked by policy because it appears destructive."
        message = str(error_payload.get("message") or "").strip()
        return message or f"{provider_label} agent request failed."

    result_payload = submit_result.get("result")
    result_payload = result_payload if isinstance(result_payload, dict) else {}
    if status in {"partial", "failed"}:
        summary = str(result_payload.get("summary") or "").strip()
        diagnostics = result_payload.get("diagnostics")
        diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
        failure_message = str(diagnostics.get("failure_message") or "").strip()
        detail = summary or failure_message
        if status == "partial":
            return (
                f"{provider_label} agent request completed with warnings."
                f"{f' {detail}' if detail else ''}"
            )
        return (
            f"{provider_label} agent request failed."
            f"{f' {detail}' if detail else ''}"
        )
    user_summary_text = _render_user_summary(result_payload)
    if user_summary_text:
        return user_summary_text
    final_message = str(result_payload.get("final_message") or "").strip()
    if final_message:
        return final_message
    output_text = _execution_output_text(submit_result)
    if output_text:
        return output_text

    execution_id = str(submit_result.get("execution_id") or "").strip()
    suffix = f" Execution id: {execution_id}." if execution_id else ""
    return f"{provider_label} agent request completed.{suffix}"


def _maybe_poll_async_provider_task(
    *,
    session_id: str,
    app_id: str,
    requested_execution_id: str,
    lane_state: Dict[str, Any],
) -> Dict[str, Any] | None:
    execution_lane = lane_state.get("execution_lane", {})
    if not isinstance(execution_lane, dict):
        return None
    if str(execution_lane.get("latest_execution_mode") or "").strip().lower() != "async":
        return None
    if str(execution_lane.get("latest_execution_id") or "").strip() != requested_execution_id:
        return None
    skill_id = str(execution_lane.get("latest_execution_request_skill_id") or "").strip()
    artifact_kind = _artifact_kind_for_skill(skill_id)
    task_id = str(execution_lane.get("latest_async_task_id") or "").strip()
    latest_result = execution_lane.get("latest_status_result")
    if not isinstance(latest_result, dict):
        latest_result = execution_lane.get("latest_execution_result")
    latest_result = latest_result if isinstance(latest_result, dict) else {}
    latest_payload = latest_result.get("result")
    latest_payload = latest_payload if isinstance(latest_payload, dict) else {}
    notebook_id = str(latest_payload.get("notebook_id") or latest_payload.get("notebookId") or "").strip()
    if not (artifact_kind and task_id and notebook_id):
        return None

    poll_result = execution_client.submit_skill(
        session_id=session_id,
        app_id=app_id,
        skill_id="notebooklm_poll_artifact_task",
        input_payload={
            "notebookId": notebook_id,
            "taskId": task_id,
            "artifactKind": artifact_kind,
        },
    )
    provider_result = poll_result.get("result")
    provider_result = provider_result if isinstance(provider_result, dict) else {}
    return {
        **poll_result,
        "execution_id": requested_execution_id,
        "provider_poll_execution_id": poll_result.get("execution_id"),
        "status": str(provider_result.get("status") or provider_result.get("state") or poll_result.get("status") or "unknown"),
        "result": provider_result,
    }


def _handle_normal_chat_turn(
    *,
    session_id: str,
    payload: ChatRequest,
    builder_context: Dict[str, Any],
    session: Dict[str, Any],
) -> Dict[str, Any]:
    effective_domain = payload.domain or builder_context["adapter_json"].get("domain") or "general"
    runtime_state = session_repo.get_runtime_state(session_id)
    state: Dict[str, Any] = {
        "session_id": session_id,
        "collection_id": payload.app_id,
        "domain": effective_domain,
        "user_id": payload.user_id,
        "planner_mode": builder_context.get("planner_mode", "legacy"),
        "instruction_understanding_mode": builder_context.get("instruction_understanding_mode", "hybrid_shadow"),
        "config_version": session["config_version"],
        "adapter_version": session["adapter_version"],
        "template_version": session["template_version"],
        "user_query": payload.user_query,
        "attached_artifact_refs": [
            ref
            for ref in (payload.artifact_refs or [])
            if isinstance(ref, dict) and str(ref.get("artifact_id") or "").strip()
        ],
        "turn_input_type": "text_query",
        "session_upload_event_ids": [],
        "pending_upload_analysis": False,
        "chat_history": chat_repo.history(session_id),
        "session_uploads": session_repo.list_uploads(session_id),
        "config_json": builder_context["config_json"],
        "adapter_json": builder_context["adapter_json"],
        "template_registry": builder_context["template_registry"],
        "workflow_progress": runtime_state.get("workflow_progress", {}),
        "session_execution_state": runtime_state.get("session_execution_state", {}),
        "intermediate_outputs": runtime_state.get("intermediate_outputs", []),
        "assembly_state": runtime_state.get("assembly_state", {}),
        "session_lane_state": runtime_state.get("session_lane_state", {}),
    }
    return run_chat_pipeline(
        state,
        session_repo=session_repo,
        chat_repo=chat_repo,
        planner_repo=planner_repo,
        retrieval_repo=retrieval_repo,
    )


def _handle_exec_status_turn(
    *,
    session_id: str,
    payload: ChatRequest,
    route: ExecRouteDecision,
) -> Dict[str, Any]:
    if route.error:
        raise HTTPException(status_code=400, detail=route.error)
    execution_id = str(route.execution_id or "").strip()
    result = execution_client.get_execution_status(
        execution_id,
        app_id=payload.app_id,
        session_id=session_id,
    )
    runtime_state = session_repo.get_runtime_state(session_id)
    lane_state = _session_lane_state(runtime_state)
    polled_result = _maybe_poll_async_provider_task(
        session_id=session_id,
        app_id=payload.app_id,
        requested_execution_id=execution_id,
        lane_state=lane_state,
    )
    if polled_result is not None:
        result = polled_result
    result = _enrich_execution_result_artifacts(
        session_id=session_id,
        app_id=payload.app_id,
        user_id=payload.user_id,
        submit_result=result,
    )
    lane_state["execution_lane"]["latest_execution_id"] = execution_id
    lane_state["execution_lane"]["latest_status_result"] = result
    _record_confirmation_lane_state(lane_state, result_payload=result)
    _refresh_async_lane_state_from_status(lane_state, status_result=result)
    runtime_state["session_lane_state"] = lane_state
    session_repo.set_runtime_state(session_id, runtime_state)
    chat_repo.append(
        session_id,
        "user",
        payload.user_query,
        retrieval_summary={"execution_override": True, "command": "status", "execution_id": execution_id},
    )
    latest_status = str(result.get("status") or result.get("state") or "unknown").strip()
    error_payload = result.get("error") if isinstance(result.get("error"), dict) else {}
    error_message = str(error_payload.get("message") or "").strip()
    login_requirement = _resolve_notebooklm_login_requirement(result)
    if login_requirement:
        summary_text = (
            f"Login to NotebookLM is required before refreshing `{execution_id}` further. "
            f"Run `{login_requirement['login_command']}` or use the NotebookLM login action, then retry status refresh."
        )
    elif error_message:
        summary_text = f"Execution status for `{execution_id}` could not be loaded: {error_message}"
    else:
        summary_text = _append_execution_output(
            f"Execution status for `{execution_id}` is {latest_status}.",
            result,
        )
    chat_repo.append(
        session_id,
        "assistant",
        summary_text,
        retrieval_summary={
            "execution_override": True,
            "command": "status",
            "execution_id": execution_id,
            "execution_status_result": result,
        },
    )
    return {
        "content": summary_text,
        "citations": [],
        "missing_infoTypes": [],
        "workflow_progress": runtime_state.get("workflow_progress", {}),
        "session_execution_state": runtime_state.get("session_execution_state", {}),
        "session_lane_state": lane_state,
        "execution_override": {
            "command": "status",
            "execution_id": execution_id,
            "status_result": result,
        },
    }


def _handle_exec_skill_turn(
    *,
    session_id: str,
    payload: ChatRequest,
    route: ExecRouteDecision,
) -> Dict[str, Any]:
    if route.error:
        raise HTTPException(status_code=400, detail=route.error)
    skill_id = str(route.skill_id or "").strip()
    if not skill_id:
        raise HTTPException(status_code=400, detail="Missing skill id.")
    runtime_skill = _runtime_skill_entry(skill_id, payload.app_id)
    skill_policy = _effective_skill_policy(skill_id, runtime_skill, payload.app_id)
    if not skill_policy.get("supported"):
        supported = ", ".join(skill_policy.get("supported_skill_ids") or [])
        raise HTTPException(
            status_code=400,
            detail=f"Unknown exec skill `{skill_id}`. Supported skills: {supported}.",
        )
    return _execute_exec_skill_target(
        session_id=session_id,
        payload=payload,
        route=route,
        skill_id=skill_id,
        skill_policy=skill_policy,
        inventory_target=runtime_skill,
        display_command="skill",
        display_target_id=skill_id,
    )


def _handle_exec_tool_turn(
    *,
    session_id: str,
    payload: ChatRequest,
    route: ExecRouteDecision,
) -> Dict[str, Any]:
    if route.error:
        raise HTTPException(status_code=400, detail=route.error)
    requested_tool_id = str(route.tool_id or "").strip()
    if not requested_tool_id:
        raise HTTPException(status_code=400, detail="Missing tool id.")
    resolved_tool_id = _resolve_runtime_tool_id(requested_tool_id)
    runtime_tool = _runtime_tool_entry(resolved_tool_id) if resolved_tool_id else None
    if runtime_tool is None:
        available = ", ".join(
            sorted(
                str(item.get("tool_id") or "").strip()
                for item in _runtime_tool_inventory_items()
                if str(item.get("tool_id") or "").strip()
            )
        )
        raise HTTPException(
            status_code=400,
            detail=f"Unknown exec tool `{requested_tool_id}`. Supported tools: {available}.",
        )
    tool_id = str(runtime_tool.get("tool_id") or resolved_tool_id or requested_tool_id).strip()
    if not bool(runtime_tool.get("exec_capable", False)) or not bool(runtime_tool.get("enabled", False)):
        raise HTTPException(status_code=400, detail=f"Tool `{tool_id}` is not executable.")
    mapped_skill_id = _resolve_runtime_exec_skill_for_tool(tool_id, payload.app_id)
    if not mapped_skill_id:
        raise HTTPException(
            status_code=400,
            detail=f"No runnable runtime skill mapping is available for tool `{tool_id}`.",
        )
    runtime_skill = _runtime_skill_entry(mapped_skill_id, payload.app_id)
    skill_policy = _effective_skill_policy(mapped_skill_id, runtime_skill, payload.app_id)
    return _execute_exec_skill_target(
        session_id=session_id,
        payload=payload,
        route=route,
        skill_id=mapped_skill_id,
        skill_policy=skill_policy,
        inventory_target=runtime_tool,
        display_command="tool",
        display_target_id=tool_id,
    )


def _execute_exec_skill_target(
    *,
    session_id: str,
    payload: ChatRequest,
    route: ExecRouteDecision,
    skill_id: str,
    skill_policy: Dict[str, Any],
    inventory_target: Dict[str, Any] | None,
    display_command: str,
    display_target_id: str,
) -> Dict[str, Any]:
    overrides = _normalize_exec_overrides_for_skill(skill_id, dict(route.parsed_args or {}))
    approved_content_id = (
        overrides.pop("approvedContentId", None)
        or overrides.pop("approved_content_id", None)
    )
    runtime_state = session_repo.get_runtime_state(session_id)
    snapshot = resolve_approved_snapshot(
        session_id=session_id,
        session_repo=session_repo,
        chat_repo=chat_repo,
        approved_content_id=str(approved_content_id).strip() if approved_content_id else None,
        create_from_latest_message=False,
    )
    if approved_content_id and snapshot is None:
        raise HTTPException(
            status_code=400,
            detail=f"Approved content `{approved_content_id}` was not found for this session.",
        )
    if snapshot is None and skill_policy.get("requires_approved_content") and "instructions" not in overrides:
        raise HTTPException(
            status_code=400,
            detail="No approved content is available for this session and no explicit instructions were provided.",
        )
    if get_execution_skill_policy(skill_id).get("supported"):
        validation_error = validate_execution_skill_request(
            skill_id,
            overrides=overrides,
            approved_snapshot=snapshot,
        )
        if validation_error:
            raise HTTPException(status_code=400, detail=validation_error)
    overrides = _attach_resolved_artifact_refs(
        app_id=payload.app_id,
        session_id=session_id,
        inventory_target=inventory_target,
        overrides=overrides,
    )
    execution_intent = build_execution_intent(
        session_repo,
        session_id=session_id,
        skill_id=skill_id,
        command_text=route.raw_args,
        approved_snapshot=snapshot,
        overrides=overrides,
    )
    submit_result = execution_client.submit_skill(
        session_id=session_id,
        app_id=payload.app_id,
        skill_id=skill_id,
        input_payload=execution_intent.get("mapped_input", {}),
    )
    lane_state = _session_lane_state(runtime_state)
    if snapshot is not None:
        lane_state["content_lane"]["latest_approved_content_id"] = snapshot.get("approved_content_id")
        lane_state["content_lane"]["latest_revision_id"] = snapshot.get("revision_id")
    lane_state["execution_lane"]["latest_execution_intent_id"] = execution_intent.get("execution_intent_id")
    lane_state["execution_lane"]["latest_execution_request_skill_id"] = skill_id
    lane_state["execution_lane"]["latest_execution_request_query"] = payload.user_query
    lane_state["execution_lane"]["latest_execution_result"] = submit_result
    _record_confirmation_lane_state(lane_state, result_payload=submit_result)
    _record_login_requirement(lane_state, result_payload=submit_result)
    _record_async_lane_state(
        lane_state,
        execution_intent=execution_intent,
        submit_result=submit_result,
    )
    if submit_result.get("execution_id"):
        lane_state["execution_lane"]["latest_execution_id"] = submit_result.get("execution_id")
    runtime_state["session_lane_state"] = lane_state
    session_repo.set_runtime_state(session_id, runtime_state)
    chat_repo.append(
        session_id,
        "user",
        payload.user_query,
        retrieval_summary={"execution_override": True, "command": display_command, "target_id": display_target_id, "skill_id": skill_id},
    )
    summary_target = display_target_id if display_command == "tool" else skill_id
    summary_text = _exec_summary_text(summary_target, submit_result, snapshot, execution_intent)
    chat_repo.append(
        session_id,
        "assistant",
        summary_text,
        retrieval_summary={"execution_override": True, "command": display_command, "target_id": display_target_id, "skill_id": skill_id},
    )
    return {
        "content": summary_text,
        "citations": [],
        "missing_infoTypes": [],
        "workflow_progress": runtime_state.get("workflow_progress", {}),
        "session_execution_state": runtime_state.get("session_execution_state", {}),
        "session_lane_state": lane_state,
        "execution_override": {
            "command": display_command,
            "target_id": display_target_id,
            "skill_id": skill_id,
            "approved_content_id": snapshot.get("approved_content_id") if snapshot else None,
            "approved_revision_id": snapshot.get("revision_id") if snapshot else None,
            "skill_policy": skill_policy,
            "inventory_target": inventory_target,
            "execution_intent": execution_intent,
            "submit_result": submit_result,
            "login_requirement": _resolve_notebooklm_login_requirement(submit_result),
        },
    }


def _handle_exec_agent_turn(
    *,
    session_id: str,
    payload: ChatRequest,
    route: ExecRouteDecision,
) -> Dict[str, Any]:
    if route.error:
        raise HTTPException(status_code=400, detail=route.error)
    command = str(route.command or "codex").strip().lower()
    structured_request = _structured_execution_request(payload)
    structured_backend = str(structured_request.get("agent_backend") or "").strip()
    if structured_backend and structured_backend not in {"codex_cli", "openclaw_cli"}:
        raise HTTPException(status_code=400, detail="Unsupported structured Agent backend.")
    agent_backend = (
        structured_backend
        or str(route.agent_backend or "").strip()
        or ("openclaw_cli" if command == "openclaw" else "codex_cli")
    )
    structured_execution_mode = str(structured_request.get("execution_mode") or "").strip().lower()
    if structured_execution_mode and structured_execution_mode not in {"sync", "async"}:
        raise HTTPException(status_code=400, detail="Unsupported structured execution mode.")
    execution_mode = structured_execution_mode or str(route.execution_mode or "sync").strip() or "sync"
    agent_skill_ref = _agent_skill_ref_from_request(payload)
    provider_label = "OpenClaw" if agent_backend == "openclaw_cli" else "Codex"
    agent_query = str(route.agent_query or "").strip()
    if not agent_query:
        raise HTTPException(status_code=400, detail=f"Missing {provider_label} request.")
    runtime_state = session_repo.get_runtime_state(session_id)
    lane_state = _session_lane_state(runtime_state)
    snapshot = resolve_approved_snapshot(
        session_id=session_id,
        session_repo=session_repo,
        chat_repo=chat_repo,
        approved_content_id=None,
        create_from_latest_message=False,
    )
    context_payload: Dict[str, Any] = {
        "execution_mode": execution_mode,
    }
    if snapshot is not None:
        context_payload["approved_content"] = {
            "approved_content_id": snapshot.get("approved_content_id"),
            "revision_id": snapshot.get("revision_id"),
            "content_text": snapshot.get("content_text"),
        }
    artifact_refs = _agent_artifact_refs_from_request(payload)
    expected_outputs = (
        _agent_expected_outputs_for_openclaw(payload=payload, agent_query=agent_query)
        if agent_backend == "openclaw_cli"
        else _agent_expected_outputs_from_request(payload)
    )
    interaction_requirements = _agent_interaction_requirements_from_request(payload)
    submit_result = execution_client.submit_agent(
        session_id=session_id,
        app_id=payload.app_id,
        agent_query=agent_query,
        agent_backend=agent_backend,
        agent_skill_hint=str(route.agent_skill_hint or "").strip() or None,
        agent_skill_ref=agent_skill_ref,
        approved_content_id=snapshot.get("approved_content_id") if snapshot else None,
        approved_revision_id=snapshot.get("revision_id") if snapshot else None,
        artifact_refs=artifact_refs,
        expected_outputs=expected_outputs,
        interaction_requirements=interaction_requirements,
        context_payload=context_payload,
        execution_mode=execution_mode,
    )
    submit_result = _enrich_execution_result_artifacts(
        session_id=session_id,
        app_id=payload.app_id,
        user_id=payload.user_id,
        submit_result=submit_result,
    )
    if snapshot is not None:
        lane_state["content_lane"]["latest_approved_content_id"] = snapshot.get("approved_content_id")
        lane_state["content_lane"]["latest_revision_id"] = snapshot.get("revision_id")
    lane_state["execution_lane"]["latest_execution_request_skill_id"] = (
        f"{agent_backend}:{agent_skill_ref['agent_skill_id']}"
        if agent_skill_ref
        else f"{agent_backend}:{route.agent_skill_hint}"
        if str(route.agent_skill_hint or "").strip()
        else agent_backend
    )
    lane_state["execution_lane"]["latest_execution_request_query"] = payload.user_query
    lane_state["execution_lane"]["latest_execution_result"] = submit_result
    _record_confirmation_lane_state(lane_state, result_payload=submit_result)
    lane_state["execution_lane"]["latest_execution_mode"] = execution_mode
    lane_state["execution_lane"]["latest_agent_backend"] = agent_backend
    _record_login_requirement(lane_state, result_payload=submit_result)
    if submit_result.get("execution_id"):
        lane_state["execution_lane"]["latest_execution_id"] = submit_result.get("execution_id")
    runtime_state["session_lane_state"] = lane_state
    session_repo.set_runtime_state(session_id, runtime_state)
    retrieval_summary = {
        "execution_override": True,
        "command": command,
        "target_id": agent_backend,
        "skill_id": lane_state["execution_lane"]["latest_execution_request_skill_id"],
        "agent_skill_hint": str(route.agent_skill_hint or "").strip() or None,
        "agent_skill_ref": agent_skill_ref,
        "agent_backend": agent_backend,
    }
    chat_repo.append(session_id, "user", payload.user_query, retrieval_summary=retrieval_summary)
    assistant_retrieval_summary = {
        **retrieval_summary,
        "execution_submit_result": submit_result,
    }
    summary_text = _agent_exec_summary_text(
        submit_result,
        provider_label=provider_label,
        agent_skill_hint=str(route.agent_skill_hint or "").strip() or None,
    )
    chat_repo.append(session_id, "assistant", summary_text, retrieval_summary=assistant_retrieval_summary)
    return {
        "content": summary_text,
        "citations": [],
        "missing_infoTypes": [],
        "workflow_progress": runtime_state.get("workflow_progress", {}),
        "session_execution_state": runtime_state.get("session_execution_state", {}),
        "session_lane_state": lane_state,
        "execution_override": {
            "command": command,
            "target_id": agent_backend,
            "skill_id": lane_state["execution_lane"]["latest_execution_request_skill_id"],
            "agent_query": agent_query,
            "agent_skill_hint": str(route.agent_skill_hint or "").strip() or None,
            "agent_skill_ref": agent_skill_ref,
            "agent_backend": agent_backend,
            "approved_content_id": snapshot.get("approved_content_id") if snapshot else None,
            "approved_revision_id": snapshot.get("revision_id") if snapshot else None,
            "submit_result": submit_result,
        },
    }


def _handle_exec_turn(
    *,
    session_id: str,
    payload: ChatRequest,
    route: ExecRouteDecision,
) -> Dict[str, Any]:
    if route.command == "status":
        return _handle_exec_status_turn(session_id=session_id, payload=payload, route=route)
    if route.command == "tool":
        return _handle_exec_tool_turn(session_id=session_id, payload=payload, route=route)
    if route.command == "skill":
        return _handle_exec_skill_turn(session_id=session_id, payload=payload, route=route)
    if route.command in {"codex", "openclaw"}:
        return _handle_exec_agent_turn(session_id=session_id, payload=payload, route=route)
    raise HTTPException(status_code=400, detail=route.error or "Unsupported exec command.")


def _load_builder_source(app_id: str) -> Dict[str, Any]:
    builder_store = get_builder_store()
    app_record = builder_store.get_application(app_id)
    if app_record is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return {
        "builder_store": builder_store,
        "app": app_record,
        "settings": builder_store.get_settings(app_id) or {},
        "instructions": builder_store.get_instructions(app_id) or {},
        "documents": builder_store.list_documents(app_id),
    }


def _instruction_understanding_mode(settings: Dict[str, Any]) -> str:
    config_settings = settings.get("config_settings", {}) if isinstance(settings, dict) else {}
    mode = str((config_settings or {}).get("instruction_understanding_mode") or "").strip().lower()
    return mode if mode in {"parser_only", "hybrid_shadow", "hybrid_active"} else "hybrid_shadow"


def _planner_mode(settings: Dict[str, Any]) -> str:
    config_settings = settings.get("config_settings", {}) if isinstance(settings, dict) else {}
    mode = str((config_settings or {}).get("planner_mode") or "").strip().lower()
    return mode if mode in {"legacy", "hybrid_shadow", "hybrid_active"} else "legacy"


def _build_builder_runtime_components(
    *,
    app_record: Dict[str, Any],
    settings: Dict[str, Any],
    instructions: Dict[str, Any],
    documents: list[Dict[str, Any]],
) -> Dict[str, Any]:
    instruction_text = str(instructions.get("content") or "")
    config_json = derive_builder_config_json(app_record, settings, instructions)
    adapter_json = derive_builder_adapter_json(app_record, config_json)
    reviewer_state = {
        "config_json": config_json,
        "adapter_json": adapter_json,
        "template_registry": {
            "builder_app": app_record,
            "builder_instructions": instruction_text,
            "builder_documents": documents,
        },
    }
    return {
        "config_json": config_json,
        "adapter_json": adapter_json,
        "reviewer_state": reviewer_state,
        "instruction_text": instruction_text,
    }


def _build_instruction_understanding_reviewer_for_app(
    *,
    app_record: Dict[str, Any],
    settings: Dict[str, Any],
    instructions: Dict[str, Any],
    documents: list[Dict[str, Any]],
):
    components = _build_builder_runtime_components(
        app_record=app_record,
        settings=settings,
        instructions=instructions,
        documents=documents,
    )
    return build_instruction_understanding_reviewer(components["reviewer_state"])


def _build_instruction_understanding_compiler_for_app(
    *,
    app_record: Dict[str, Any],
    settings: Dict[str, Any],
    instructions: Dict[str, Any],
    documents: list[Dict[str, Any]],
):
    components = _build_builder_runtime_components(
        app_record=app_record,
        settings=settings,
        instructions=instructions,
        documents=documents,
    )
    return build_instruction_understanding_compiler(components["reviewer_state"])


def _build_instruction_understanding_reviser_for_app(
    *,
    app_record: Dict[str, Any],
    settings: Dict[str, Any],
    instructions: Dict[str, Any],
    documents: list[Dict[str, Any]],
):
    components = _build_builder_runtime_components(
        app_record=app_record,
        settings=settings,
        instructions=instructions,
        documents=documents,
    )
    return build_instruction_understanding_reviser(components["reviewer_state"])


def _normalize_understanding_payload(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "record": None,
            "latest_attempt": None,
            "review": None,
            "status": {},
            "cache_status": None,
            "stale_reasons": [],
        }
    if "record" in payload:
        return {
            "record": payload.get("record"),
            "latest_attempt": payload.get("latest_attempt"),
            "review": payload.get("review"),
            "status": payload.get("status", {}),
            "cache_status": payload.get("cache_status"),
            "stale_reasons": payload.get("stale_reasons", []),
        }
    return {
        "record": payload.get("compiled"),
        "latest_attempt": payload.get("latest_attempt"),
        "review": payload.get("review"),
        "status": payload.get("status", {}),
        "cache_status": payload.get("cache_status") or payload.get("status", {}).get("cache_status"),
        "stale_reasons": payload.get("stale_reasons", []) or payload.get("status", {}).get("stale_reasons", []),
    }


def _compose_builder_context(
    *,
    app_record: Dict[str, Any],
    settings: Dict[str, Any],
    instructions: Dict[str, Any],
    documents: list[Dict[str, Any]],
    config_json: Dict[str, Any],
    adapter_json: Dict[str, Any],
    understanding: Dict[str, Any] | None,
) -> Dict[str, Any]:
    normalized_understanding = _normalize_understanding_payload(understanding)
    instruction_text = str(instructions.get("content") or "")
    planner_mode = _planner_mode(settings)
    instruction_understanding_mode = _instruction_understanding_mode(settings)
    return {
        "app": app_record,
        "settings": settings,
        "instructions": instructions,
        "documents": documents,
        "instruction_understanding": normalized_understanding,
        "instruction_understanding_status": normalized_understanding.get("status", {}),
        "planner_mode": planner_mode,
        "instruction_understanding_mode": instruction_understanding_mode,
        "config_json": config_json,
        "adapter_json": adapter_json,
        "template_registry": {
            "builder_app": app_record,
            "builder_instructions": instruction_text,
            "builder_instruction_uri": instructions.get("uri"),
            "builder_documents": documents,
            "builder_settings": settings.get("config_settings", {}),
            "builder_settings_schema": settings.get("config_schema", {}),
            "compiled_instruction_understanding": (
                normalized_understanding.get("record", {}).get("compiled_contract", {})
                if isinstance(normalized_understanding.get("record"), dict)
                else {}
            ),
            "instruction_understanding_status": {
                "cache_status": normalized_understanding.get("status", {}).get("cache_status"),
                "stale_reasons": normalized_understanding.get("status", {}).get("stale_reasons", []),
            },
            "planner_mode": planner_mode,
            "instruction_understanding_mode": instruction_understanding_mode,
        },
    }


def _load_compiled_instruction_understanding_for_builder(
    *,
    source: Dict[str, Any],
    allow_prepare: bool,
    include_reviewer: bool,
) -> Dict[str, Any]:
    builder_store = source["builder_store"]
    compiler = _build_instruction_understanding_compiler_for_app(
        app_record=source["app"],
        settings=source["settings"],
        instructions=source["instructions"],
        documents=source["documents"],
    )
    reviewer = None
    if include_reviewer:
        reviewer = _build_instruction_understanding_reviewer_for_app(
            app_record=source["app"],
            settings=source["settings"],
            instructions=source["instructions"],
            documents=source["documents"],
        )
    compiler_mode = _instruction_understanding_mode(source["settings"])
    semantic_compiler_enabled = compiler_mode != "parser_only" and compiler is not None
    detail = load_instruction_understanding_detail(
        app_id=source["app"]["id"],
        builder_store=builder_store,
        repo=instruction_understanding_repo,
        semantic_compiler_version=SEMANTIC_COMPILER_VERSION if semantic_compiler_enabled else None,
        semantic_compile_prompt_version=SEMANTIC_COMPILE_PROMPT_VERSION if semantic_compiler_enabled else None,
    )
    if allow_prepare and not isinstance(detail.get("compiled"), dict):
        return prepare_instruction_understanding(
            app_id=source["app"]["id"],
            instructions=source["instructions"],
            documents=source["documents"],
            repo=instruction_understanding_repo,
            snapshot_root=builder_store.db_path.parent / "instruction_understanding",
            semantic_compiler=compiler if compiler_mode != "parser_only" else None,
            reviewer=reviewer,
        )
    return detail


def _load_builder_context_common(app_id: str, *, read_only: bool) -> Dict[str, Any]:
    source = _load_builder_source(app_id)
    components = _build_builder_runtime_components(
        app_record=source["app"],
        settings=source["settings"],
        instructions=source["instructions"],
        documents=source["documents"],
    )
    understanding = _load_compiled_instruction_understanding_for_builder(
        source=source,
        allow_prepare=False,
        include_reviewer=not read_only,
    )
    return _compose_builder_context(
        app_record=source["app"],
        settings=source["settings"],
        instructions=source["instructions"],
        documents=source["documents"],
        config_json=components["config_json"],
        adapter_json=components["adapter_json"],
        understanding=understanding,
    )


def _load_builder_context(app_id: str) -> Dict[str, Any]:
    return _load_builder_context_common(app_id, read_only=False)


def _load_builder_readonly_context(app_id: str) -> Dict[str, Any]:
    return _load_builder_context_common(app_id, read_only=True)


def _instruction_understanding_preview(understanding: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = understanding if isinstance(understanding, dict) else {}
    record = payload.get("record") if isinstance(payload.get("record"), dict) else None
    latest_attempt = payload.get("latest_attempt") if isinstance(payload.get("latest_attempt"), dict) else None
    review = payload.get("review") if isinstance(payload.get("review"), dict) else None
    status = payload.get("status") if isinstance(payload.get("status"), dict) else {}
    compiled_contract = record.get("compiled_contract") if isinstance(record, dict) and isinstance(record.get("compiled_contract"), dict) else {}
    hybrid_runtime_model = (
        compiled_contract.get("hybrid_instruction_runtime_model")
        if isinstance(compiled_contract.get("hybrid_instruction_runtime_model"), dict)
        else {}
    )
    semantic_compile_attached = bool((record.get("metadata") or {}).get("semantic_compile_attached")) if isinstance(record, dict) else False
    semantic_compile_valid = bool((record.get("metadata") or {}).get("semantic_compile_valid")) if isinstance(record, dict) else False
    latest_attempt_errors = []
    if isinstance(latest_attempt, dict):
        validation = ((latest_attempt.get("compiled_contract") or {}).get("semantic_compile") or {}).get("validation") or {}
        latest_attempt_errors = list(validation.get("errors") or [])
    compile_required = not isinstance(record, dict) or (semantic_compile_attached and not semantic_compile_valid)
    return {
        "compiled_id": record.get("id") if isinstance(record, dict) else None,
        "compiled_status": status.get("compiled_status") or (record.get("compiled_status") if isinstance(record, dict) else None),
        "review_id": review.get("id") if isinstance(review, dict) else None,
        "review_status": status.get("review_status") or (review.get("review_status") if isinstance(review, dict) else "not_reviewed"),
        "cache_status": payload.get("cache_status") or status.get("cache_status"),
        "stale_reasons": payload.get("stale_reasons") or status.get("stale_reasons", []),
        "semantic_compile_attached": semantic_compile_attached,
        "semantic_compile_valid": semantic_compile_valid,
        "primary_service_mode": hybrid_runtime_model.get("primary_service_mode"),
        "approval_id": payload.get("approval", {}).get("id") if isinstance(payload.get("approval"), dict) else None,
        "revision_id": payload.get("revision", {}).get("id") if isinstance(payload.get("revision"), dict) else None,
        "compile_required": compile_required,
        "latest_attempt_id": latest_attempt.get("id") if isinstance(latest_attempt, dict) else None,
        "latest_attempt_semantic_compile_valid": bool((latest_attempt.get("metadata") or {}).get("semantic_compile_valid")) if isinstance(latest_attempt, dict) else None,
        "latest_attempt_validation_errors": latest_attempt_errors,
    }


def _workflow_steps(workflow: Dict[str, Any] | None) -> list[Dict[str, Any]]:
    if not isinstance(workflow, dict):
        return []
    steps = workflow.get("steps", [])
    if not isinstance(steps, list):
        return []
    return sorted(
        [step for step in steps if isinstance(step, dict)],
        key=lambda step: int(step.get("order") or 9999),
    )


def _load_instruction_workflows(app_id: str) -> list[Dict[str, Any]]:
    source = _load_builder_source(app_id)
    active_compiled = instruction_understanding_repo.get_active_compiled(app_id)
    compiled_contract = active_compiled.get("compiled_contract", {}) if isinstance(active_compiled, dict) else {}
    if isinstance(compiled_contract, dict):
        workflows = compiled_contract.get("instruction_workflows", [])
        if isinstance(workflows, list) and workflows:
            return workflows
    builder_instructions = str(source["instructions"].get("content") or "")
    return _extract_instruction_workflows(builder_instructions)


def _normalize_workflow_scope_id(scope_id: Any) -> str | None:
    normalized = str(scope_id or "").strip()
    if not normalized:
        return None
    if normalized.startswith("workflow:"):
        return normalized.split(":", 1)[1].strip() or None
    return normalized


def _workflow_runtime_hint_from_summary(summary: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = summary if isinstance(summary, dict) else {}
    session_execution_state = payload.get("session_execution_state", {})
    if not isinstance(session_execution_state, dict):
        session_execution_state = {}
    primary_scope = payload.get("primary_scope", {})
    if not isinstance(primary_scope, dict):
        primary_scope = {}
    active_step_scope = payload.get("active_step_scope", {})
    if not isinstance(active_step_scope, dict):
        active_step_scope = {}

    workflow_id = None
    if str(session_execution_state.get("primary_scope_type") or "").strip() == "workflow":
        workflow_id = _normalize_workflow_scope_id(session_execution_state.get("primary_scope_id"))
    if workflow_id is None and str(primary_scope.get("scope_type") or "").strip() == "workflow":
        workflow_id = _normalize_workflow_scope_id(primary_scope.get("scope_id"))

    workflow_title = (
        str(session_execution_state.get("primary_scope_title") or "").strip()
        or str(primary_scope.get("title") or "").strip()
        or None
    )
    current_order = session_execution_state.get("active_step_order")
    if current_order is None:
        current_order = active_step_scope.get("step_order")
    current_title = (
        str(session_execution_state.get("active_step_title") or "").strip()
        or str(active_step_scope.get("title") or "").strip()
        or None
    )
    active_step_scope_id = (
        str(session_execution_state.get("active_step_scope_id") or "").strip()
        or str(active_step_scope.get("scope_id") or "").strip()
        or None
    )
    active_service_block_type = str(session_execution_state.get("active_service_block_type") or "").strip() or None
    active_service_block_id = str(session_execution_state.get("active_service_block_id") or "").strip() or None
    active_service_block_title = str(session_execution_state.get("active_service_block_title") or "").strip() or None
    execution_status = str(session_execution_state.get("execution_status") or "").strip() or None
    active_execution_mode = str(session_execution_state.get("active_execution_mode") or "").strip() or None
    bundled_execution_completed = bool(session_execution_state.get("bundled_execution_completed"))

    has_signal = any(
        (
            workflow_id,
            workflow_title,
            current_order is not None,
            current_title,
            active_step_scope_id,
            active_service_block_id,
            active_service_block_title,
            execution_status,
            active_execution_mode,
            bundled_execution_completed,
        )
    )
    if not has_signal:
        return {}
    return {
        "workflow_id": workflow_id,
        "workflow_title": workflow_title,
        "current_step_order": current_order,
        "current_step_title": current_title,
        "active_step_scope_id": active_step_scope_id,
        "active_service_block_type": active_service_block_type,
        "active_service_block_id": active_service_block_id,
        "active_service_block_title": active_service_block_title,
        "execution_status": execution_status,
        "active_execution_mode": active_execution_mode,
        "bundled_execution_completed": bundled_execution_completed,
    }


def _latest_workflow_runtime_hint(message_history: list[Dict[str, Any]] | None) -> Dict[str, Any]:
    history = message_history if isinstance(message_history, list) else []
    for item in reversed(history):
        if not isinstance(item, dict) or str(item.get("role") or "").strip() != "assistant":
            continue
        summary = item.get("retrievalSummary")
        if not isinstance(summary, dict):
            summary = item.get("retrieval_summary")
        hint = _workflow_runtime_hint_from_summary(summary if isinstance(summary, dict) else {})
        if hint and any(
            (
                hint.get("workflow_id"),
                hint.get("current_step_order") is not None,
                hint.get("active_step_scope_id"),
                hint.get("current_step_title"),
                hint.get("active_service_block_id"),
                hint.get("active_service_block_title"),
                hint.get("workflow_title"),
            )
        ):
            return hint
    return {}


def _configured_task_models_payload(config_json: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = config_json if isinstance(config_json, dict) else {}
    meta = payload.get("meta", {}) if isinstance(payload.get("meta"), dict) else {}
    llm_settings = meta.get("llm_settings", {}) if isinstance(meta.get("llm_settings"), dict) else {}
    resolved: Dict[str, Any] = {}
    for task in USER_VISIBLE_TASKS:
        config = resolve_task_model(llm_settings, task)
        if config is None:
            continue
        resolved[task] = {
            "provider": config.get("provider"),
            "model": config.get("model"),
            "temperature": config.get("temperature"),
        }
    return resolved


def _latest_task_model_diagnostics(message_history: list[Dict[str, Any]] | None) -> Dict[str, Any]:
    history = message_history if isinstance(message_history, list) else []
    for item in reversed(history):
        if not isinstance(item, dict) or str(item.get("role") or "").strip() != "assistant":
            continue
        summary = item.get("retrievalSummary")
        if not isinstance(summary, dict):
            summary = item.get("retrieval_summary")
        if not isinstance(summary, dict):
            continue
        diagnostics = summary.get("task_model_diagnostics", {})
        if isinstance(diagnostics, dict) and diagnostics:
            selected = diagnostics.get("selected_task_models", {})
            if isinstance(selected, dict) and selected:
                return selected
    return {}


def _workflow_status_payload(
    app_id: str,
    workflow_progress: Dict[str, Any] | None,
    *,
    runtime_state: Dict[str, Any] | None = None,
    message_history: list[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    progress = workflow_progress if isinstance(workflow_progress, dict) else {}
    runtime_payload = runtime_state if isinstance(runtime_state, dict) else {}
    runtime_hint = _workflow_runtime_hint_from_summary(
        {"session_execution_state": runtime_payload.get("session_execution_state", {})}
    )
    message_hint = _latest_workflow_runtime_hint(message_history)
    effective_hint = message_hint or runtime_hint

    workflow_id = (
        str(effective_hint.get("workflow_id") or "").strip()
        or str(progress.get("workflow_id") or "").strip()
    )
    has_module_or_step_signal = any(
        (
            effective_hint.get("current_step_order") is not None,
            effective_hint.get("current_step_title"),
            effective_hint.get("active_step_scope_id"),
            effective_hint.get("active_service_block_id"),
            effective_hint.get("active_service_block_title"),
        )
    )
    if not workflow_id and not has_module_or_step_signal:
        return {}
    steps: list[Dict[str, Any]] = []
    workflow = None
    for candidate in _load_instruction_workflows(app_id):
        if str(candidate.get("id") or "").strip() == workflow_id:
            workflow = candidate
            steps = _workflow_steps(candidate)
            break

    current_order = effective_hint.get("current_step_order")
    if current_order is None:
        current_order = progress.get("step_order")
    current_step = None
    next_step = None
    if current_order is not None:
        for step in steps:
            if int(step.get("order") or -1) == int(current_order):
                current_step = step
            if int(step.get("order") or -1) == int(current_order) + 1:
                next_step = step
    if bool(effective_hint.get("bundled_execution_completed")):
        next_step = None

    active_service_block_type = str(effective_hint.get("active_service_block_type") or "").strip() or None
    active_service_block_id = str(effective_hint.get("active_service_block_id") or "").strip() or None
    active_service_block_title = str(effective_hint.get("active_service_block_title") or "").strip() or None
    current_step_order = current_order
    current_step_title = (
        effective_hint.get("current_step_title")
        or progress.get("step_title")
        or (current_step.get("title") if isinstance(current_step, dict) else None)
    )
    current_step_resource = progress.get("resource_file") or (
        current_step.get("resource_file") if isinstance(current_step, dict) else None
    )
    if active_service_block_type == "followup_module" and active_service_block_title:
        current_step_order = None
        current_step_title = active_service_block_title
        current_step_resource = None
        next_step = None

    return {
        "workflow_id": workflow_id or None,
        "workflow_title": (
            effective_hint.get("workflow_title")
            or progress.get("workflow_title")
            or (workflow.get("title") if isinstance(workflow, dict) else None)
        ),
        "current_step": {
            "order": current_step_order,
            "title": current_step_title,
            "resource_file": current_step_resource,
        }
        if current_step_order is not None
        or current_step_title
        or current_step_resource
        else None,
        "next_step": {
            "order": next_step.get("order"),
            "title": next_step.get("title"),
            "resource_file": next_step.get("resource_file"),
        }
        if isinstance(next_step, dict)
        else None,
        "execution_status": effective_hint.get("execution_status"),
        "active_execution_mode": effective_hint.get("active_execution_mode"),
        "bundled_execution_completed": bool(effective_hint.get("bundled_execution_completed")),
        "active_step_scope_id": effective_hint.get("active_step_scope_id"),
        "active_service_block_type": active_service_block_type,
        "active_service_block_id": active_service_block_id,
        "active_service_block_title": active_service_block_title,
    }


def _message_workflow_status_payload(app_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
    if str(message.get("role") or "").strip() != "assistant":
        return {}
    summary = message.get("retrievalSummary")
    if not isinstance(summary, dict):
        summary = message.get("retrieval_summary")
    summary = summary if isinstance(summary, dict) else {}
    workflow_progress = summary.get("workflow_progress", {})
    session_execution_state = summary.get("session_execution_state", {})
    return _workflow_status_payload(
        app_id,
        workflow_progress if isinstance(workflow_progress, dict) else {},
        runtime_state={
            "session_execution_state": session_execution_state
            if isinstance(session_execution_state, dict)
            else {}
        },
        message_history=[message],
    )


def _require_session_scope(
    session_id: str,
    *,
    app_id: str,
    user_id: str,
) -> Dict[str, Any]:
    session = session_repo.get(session_id)
    if (
        session is None
        or session.get("collection_id") != app_id
        or session.get("user_id") != user_id
    ):
        raise HTTPException(status_code=404, detail="Session not found.")
    return session


def _advance_workflow_progress(app_id: str, workflow_progress: Dict[str, Any] | None) -> Dict[str, Any]:
    progress = dict(workflow_progress or {})
    workflow_id = str(progress.get("workflow_id") or "").strip()
    if not workflow_id:
        return progress

    workflow = None
    for candidate in _load_instruction_workflows(app_id):
        if str(candidate.get("id") or "").strip() == workflow_id:
            workflow = candidate
            break
    if not isinstance(workflow, dict):
        return progress

    steps = _workflow_steps(workflow)
    if not steps:
        return progress

    current_order = progress.get("step_order")
    next_step = None
    if current_order is None:
        next_step = steps[0]
    else:
        for step in steps:
            if int(step.get("order") or -1) == int(current_order) + 1:
                next_step = step
                break
    if next_step is None:
        return progress

    return {
        "workflow_id": workflow.get("id"),
        "workflow_title": workflow.get("title"),
        "step_order": next_step.get("order"),
        "step_title": next_step.get("title"),
        "resource_file": next_step.get("resource_file"),
    }


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    _ = get_settings()
    return {"status": "ok"}


@app.get("/apps")
async def list_builder_applications():
    builder_store = get_builder_store()
    apps = builder_store.list_applications()
    return {"applications": apps}


@app.get("/apps/{app_id}")
async def get_builder_application(app_id: str):
    builder_store = get_builder_store()
    app_record = builder_store.get_application(app_id)
    if app_record is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return {
        **app_record,
        "runtime_source": "builder",
        "instruction_source": "builder.instructions.md + builder.settings",
    }


@app.get("/apps/{app_id}/documents")
async def list_builder_documents(app_id: str, x_role: str = Depends(require_admin)):
    _ = x_role
    builder_store = get_builder_store()
    app_record = builder_store.get_application(app_id)
    if app_record is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return {"app_id": app_id, "documents": builder_store.list_documents(app_id)}


@app.get("/apps/{app_id}/instructions")
async def get_builder_instructions(app_id: str, x_role: str = Depends(require_admin)):
    _ = x_role
    builder_store = get_builder_store()
    app_record = builder_store.get_application(app_id)
    if app_record is None:
        raise HTTPException(status_code=404, detail="Application not found")

    instructions = builder_store.get_instructions(app_id)
    if instructions is None:
        raise HTTPException(status_code=404, detail="Instructions not found")

    settings = builder_store.get_settings(app_id) or {}
    derived = _load_builder_readonly_context(app_id)
    return {
        "app_id": app_id,
        "instructions": instructions,
        "settings": settings.get("config_settings", {}),
        "settings_schema": settings.get("config_schema", {}),
        "derived_config_json": derived["config_json"],
        "derived_adapter_json": derived["adapter_json"],
        "instruction_understanding_status": derived.get("instruction_understanding_status", {}),
        "instruction_understanding_preview": _instruction_understanding_preview(
            derived.get("instruction_understanding")
        ),
        "planner_mode": derived.get("planner_mode"),
        "instruction_understanding_mode": derived.get("instruction_understanding_mode"),
        "runtime_source": "builder",
    }


@app.get("/apps/{app_id}/runtime")
async def get_builder_runtime(app_id: str, x_role: str = Depends(require_admin)):
    _ = x_role
    builder_store = get_builder_store()
    app_record = builder_store.get_application(app_id)
    if app_record is None:
        raise HTTPException(status_code=404, detail="Application not found")

    context = _load_builder_readonly_context(app_id)
    config_json = context["config_json"]
    adapter_json = context["adapter_json"]
    meta = config_json.get("meta", {}) if isinstance(config_json, dict) else {}
    llm_settings = meta.get("llm_settings", {}) if isinstance(meta, dict) else {}
    models = llm_settings.get("models", {}) if isinstance(llm_settings, dict) else {}

    return {
        "app_id": app_id,
        "app_name": app_record.get("name"),
        "runtime_source": "builder",
        "provider": llm_settings.get("provider"),
        "models": models if isinstance(models, dict) else {},
        "configured_task_models": _configured_task_models_payload(config_json),
        "temperature": llm_settings.get("temperature"),
        "domain": adapter_json.get("domain"),
        "template_registry_keys": sorted(context["template_registry"].keys()),
        "instruction_understanding_status": context.get("instruction_understanding_status", {}),
        "instruction_understanding_preview": _instruction_understanding_preview(
            context.get("instruction_understanding")
        ),
        "planner_mode": context.get("planner_mode"),
        "instruction_understanding_mode": context.get("instruction_understanding_mode"),
        "config_summary": {
            "goal_count": len(config_json.get("goals", []) or []),
            "style_rule_count": len(config_json.get("style_rules", []) or []),
            "safety_rule_count": len(config_json.get("safety_rules", []) or []),
            "retrieval_rule_count": len(config_json.get("retrieval_rules", []) or []),
        },
        "adapter_summary": {
            "intent_override_count": len(adapter_json.get("intent_overrides", []) or []),
            "guardrail_count": len(adapter_json.get("llm_guardrails_append", []) or []),
            "retrieval_defaults": adapter_json.get("retrieval_defaults", {}),
        },
        "config_json": config_json,
        "adapter_json": adapter_json,
    }


@app.get("/apps/{app_id}/instruction-understanding")
async def get_instruction_understanding_detail(app_id: str, x_role: str = Depends(require_admin)):
    _ = x_role
    builder_store = get_builder_store()
    app_record = builder_store.get_application(app_id)
    if app_record is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return load_instruction_understanding_detail(
        app_id=app_id,
        builder_store=builder_store,
        repo=instruction_understanding_repo,
    )


@app.post("/apps/{app_id}/instruction-understanding/recompile")
async def recompile_instruction_understanding(app_id: str, x_role: str = Depends(require_admin)):
    _ = x_role
    source = _load_builder_source(app_id)
    compiler = _build_instruction_understanding_compiler_for_app(
        app_record=source["app"],
        settings=source["settings"],
        instructions=source["instructions"],
        documents=source["documents"],
    )
    compiler_mode = _instruction_understanding_mode(source["settings"])
    result = force_recompile_instruction_understanding(
        app_id=app_id,
        builder_store=source["builder_store"],
        repo=instruction_understanding_repo,
        snapshot_root=source["builder_store"].db_path.parent / "instruction_understanding",
        semantic_compiler=compiler if compiler_mode != "parser_only" else None,
        semantic_compiler_version=SEMANTIC_COMPILER_VERSION,
    )
    return {
        "app_id": app_id,
        "compiled": result.get("record"),
        "attempt_record": result.get("attempt_record"),
        "latest_attempt": result.get("latest_attempt"),
        "review": result.get("review"),
        "status": result.get("status", {}),
        "cache_status": result.get("cache_status"),
        "stale_reasons": result.get("stale_reasons", []),
        "instruction_understanding_preview": _instruction_understanding_preview(result),
    }


@app.post("/apps/{app_id}/instruction-understanding/review")
async def review_instruction_understanding_endpoint(app_id: str, x_role: str = Depends(require_admin)):
    _ = x_role
    source = _load_builder_source(app_id)
    reviewer = _build_instruction_understanding_reviewer_for_app(
        app_record=source["app"],
        settings=source["settings"],
        instructions=source["instructions"],
        documents=source["documents"],
    )
    if reviewer is None:
        raise HTTPException(status_code=409, detail="Instruction understanding reviewer is not available")
    result = force_review_instruction_understanding(
        app_id=app_id,
        builder_store=source["builder_store"],
        repo=instruction_understanding_repo,
        reviewer=reviewer,
    )
    return {
        "app_id": app_id,
        "compiled": result.get("record"),
        "review": result.get("review"),
        "status": result.get("status", {}),
        "cache_status": result.get("cache_status"),
        "stale_reasons": result.get("stale_reasons", []),
    }


@app.post("/apps/{app_id}/instruction-understanding/approve-findings")
async def approve_instruction_understanding_endpoint(
    app_id: str,
    payload: ApprovalRequest,
    x_role: str = Depends(require_admin),
):
    _ = x_role
    builder_store = get_builder_store()
    app_record = builder_store.get_application(app_id)
    if app_record is None:
        raise HTTPException(status_code=404, detail="Application not found")
    try:
        result = approve_instruction_understanding_findings(
            app_id=app_id,
            repo=instruction_understanding_repo,
            approved_findings=payload.approved_findings,
            approver=payload.approver,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "app_id": app_id,
        "compiled": result.get("record"),
        "review": result.get("review"),
        "approval": result.get("approval"),
    }


@app.post("/apps/{app_id}/instruction-understanding/revise")
async def revise_instruction_understanding_endpoint(app_id: str, x_role: str = Depends(require_admin)):
    _ = x_role
    source = _load_builder_source(app_id)
    reviser = _build_instruction_understanding_reviser_for_app(
        app_record=source["app"],
        settings=source["settings"],
        instructions=source["instructions"],
        documents=source["documents"],
    )
    if reviser is None:
        raise HTTPException(status_code=409, detail="Instruction understanding reviser is not available")
    try:
        result = revise_instruction_understanding(
            app_id=app_id,
            repo=instruction_understanding_repo,
            reviser=reviser,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "app_id": app_id,
        "compiled": result.get("record"),
        "review": result.get("review"),
        "approval": result.get("approval"),
        "revision": result.get("revision"),
        "validation": result.get("validation"),
    }


@app.post("/apps/{app_id}/documents/ingest")
async def ingest_builder_documents(
    app_id: str,
    background_tasks: BackgroundTasks,
    payload: BuilderIngestPayload | None = None,
    x_role: str = Depends(require_admin),
):
    _ = x_role
    builder_store = get_builder_store()
    app_record = builder_store.get_application(app_id)
    if app_record is None:
        raise HTTPException(status_code=404, detail="Application not found")

    run = enqueue_builder_ingestion(
        app_id,
        payload.document_ids if payload else None,
        repo=ingestion_repo,
        background_tasks=background_tasks,
    )
    return {"run_id": run["id"], "status": run["status"], "document_count": run["document_count"]}


@app.get("/apps/{app_id}/ingestion_runs/{run_id}")
async def get_builder_ingestion_status(app_id: str, run_id: str, x_role: str = Depends(require_admin)):
    _ = x_role
    run = ingestion_repo.get_run(run_id)
    if run is None or run["collection_id"] != app_id:
        raise HTTPException(status_code=404, detail="Ingestion run not found")
    return run


@app.post("/sessions/{session_id}/chat")
async def chat(session_id: str, payload: ChatRequest):
    builder_context = _load_builder_context(payload.app_id)

    try:
        session = session_repo.get_or_create(
            session_id,
            collection_id=payload.app_id,
            user_id=payload.user_id,
            title=None,
            config_version=payload.config_version,
            adapter_version=payload.adapter_version,
            template_version=payload.template_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not session.get("title") and payload.user_query.strip():
        session = session_repo.set_title(session_id, _derive_session_title(payload.user_query)) or session

    route = parse_exec_turn(payload.user_query)
    if route.is_exec_turn:
        return await run_in_threadpool(
            _handle_exec_turn,
            session_id=session_id,
            payload=payload,
            route=route,
        )
    return _handle_normal_chat_turn(
        session_id=session_id,
        payload=payload,
        builder_context=builder_context,
        session=session,
    )


@app.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, app_id: str, user_id: str):
    session = session_repo.get(session_id)
    if session is None:
        return {"session_id": session_id, "messages": [], "workflow_status": {}}
    if session["collection_id"] != app_id or session["user_id"] != user_id:
        raise HTTPException(status_code=400, detail="Session identity mismatch.")
    stored_history = chat_repo.history(session_id)
    history = [
        {
            **message,
            "workflow_status": _message_workflow_status_payload(app_id, message),
        }
        if str(message.get("role") or "").strip() == "assistant"
        else message
        for message in stored_history
    ]
    context = _load_builder_readonly_context(app_id)
    return {
        "session_id": session_id,
        "messages": history,
        "session_lane_state": session.get("runtime_state", {}).get("session_lane_state", {}),
        "workflow_status": _workflow_status_payload(
            app_id,
            session.get("workflow_progress", {}),
            runtime_state=session.get("runtime_state", {}),
            message_history=history,
        ),
        "model_diagnostics": {
            "configured_task_models": _configured_task_models_payload(context.get("config_json", {})),
            "latest_turn_task_models": _latest_task_model_diagnostics(history),
        },
        "session_uploads": _public_session_uploads(session_repo.list_uploads(session_id)),
        "approved_content": session_repo.list_approved_content(session_id),
    }


@app.get("/sessions/{session_id}/artifacts")
async def list_session_artifacts(
    session_id: str,
    app_id: str,
    user_id: str,
    artifact_type: str | None = None,
    eligible_for: str | None = None,
):
    _require_session_scope(session_id, app_id=app_id, user_id=user_id)
    payload = execution_client.get_artifact_inventory(
        app_id=app_id,
        session_id=session_id,
        artifact_type=artifact_type,
        eligible_for=eligible_for,
        status="ready",
    ) or {}
    if payload.get("_transport_error"):
        error_payload = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        warning = str(error_payload.get("message") or "Execution subsystem is unavailable.").strip()
        return {
            "session_id": session_id,
            "items": [],
            "warning": warning,
        }
    items = payload.get("items", [])
    return {
        "session_id": session_id,
        "items": [
            _normalize_session_artifact_item(
                session_id=session_id,
                app_id=app_id,
                user_id=user_id,
                item=item,
            )
            for item in _normalize_artifact_inventory_items(
                [item for item in items if isinstance(item, dict)]
            )
        ],
    }


@app.get("/sessions/{session_id}/artifacts/{artifact_id}/preview")
async def preview_session_artifact_file(
    session_id: str,
    artifact_id: str,
    app_id: str,
    user_id: str,
):
    _require_session_scope(session_id, app_id=app_id, user_id=user_id)
    result = await run_in_threadpool(
        execution_client.get_artifact_file,
        app_id=app_id,
        session_id=session_id,
        artifact_id=artifact_id,
        preview=True,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=int(result.get("_http_status") or 502), detail="Artifact file is unavailable.")
    headers = {}
    if result.get("content_disposition"):
        headers["Content-Disposition"] = str(result["content_disposition"])
    return Response(content=result.get("content") or b"", media_type=result.get("content_type"), headers=headers)


@app.get("/sessions/{session_id}/artifacts/{artifact_id}/file")
async def open_session_artifact_file(
    session_id: str,
    artifact_id: str,
    app_id: str,
    user_id: str,
):
    _require_session_scope(session_id, app_id=app_id, user_id=user_id)
    result = await run_in_threadpool(
        execution_client.get_artifact_file,
        app_id=app_id,
        session_id=session_id,
        artifact_id=artifact_id,
        preview=False,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=int(result.get("_http_status") or 502), detail="Artifact file is unavailable.")
    headers = {}
    if result.get("content_disposition"):
        headers["Content-Disposition"] = str(result["content_disposition"])
    return Response(content=result.get("content") or b"", media_type=result.get("content_type"), headers=headers)


@app.delete("/sessions/{session_id}/artifacts/{artifact_id}")
async def delete_session_artifact(
    session_id: str,
    artifact_id: str,
    app_id: str,
    user_id: str,
):
    _require_session_scope(session_id, app_id=app_id, user_id=user_id)
    result = await run_in_threadpool(
        execution_client.delete_artifact,
        app_id=app_id,
        session_id=session_id,
        artifact_id=artifact_id,
    )
    if isinstance(result.get("error"), dict):
        error = result["error"]
        raise HTTPException(
            status_code=int(result.get("_http_status") or 502),
            detail={
                "code": str(error.get("code") or "ARTIFACT_DELETE_FAILED"),
                "message": str(error.get("message") or "Artifact could not be deleted."),
            },
        )
    return {"deleted": True, "artifact_id": artifact_id}


@app.get("/exec/tools")
async def list_exec_tools(app_id: str | None = None):
    return {"items": _exec_tool_inventory_items()}


@app.get("/exec/skills")
async def list_exec_skills(app_id: str | None = None, visibility: str | None = None):
    runtime_visibility = visibility or "user"
    return {"items": _combined_skill_inventory_items(app_id=app_id, runtime_visibility=runtime_visibility)}


@app.post("/sessions/{session_id}/prepare")
async def prepare_session(session_id: str, payload: SessionPrepareRequest):
    try:
        session = session_repo.get_or_create(
            session_id,
            collection_id=payload.app_id,
            user_id=payload.user_id,
            config_version=payload.config_version,
            adapter_version=payload.adapter_version,
            template_version=payload.template_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"session": session}


@app.get("/sessions/{session_id}/exec/agent-skills")
async def list_session_agent_skills(
    session_id: str,
    app_id: str,
    user_id: str,
    backend: str,
):
    _require_session_scope(session_id, app_id=app_id, user_id=user_id)
    if backend not in {"codex_cli", "openclaw_cli"}:
        raise HTTPException(status_code=422, detail="Unsupported Agent backend.")
    payload = execution_client.get_agent_skill_inventory(
        app_id=app_id,
        backend=backend,
    ) or {}
    if payload.get("_transport_error") or isinstance(payload.get("error"), dict):
        error_payload = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        raise HTTPException(
            status_code=int(payload.get("_http_status") or 502),
            detail=str(error_payload.get("message") or "Agent Skill inventory is unavailable."),
        )
    public_fields = (
        "agent_skill_id",
        "approved_fingerprint",
        "availability",
        "backend",
        "description",
        "display_name",
        "provider_skill_name",
    )
    raw_items = payload.get("items", [])
    items = [
        {key: item.get(key) for key in public_fields}
        for item in raw_items
        if isinstance(item, dict) and item.get("backend") == backend
    ] if isinstance(raw_items, list) else []
    return {
        "inventory_revision": payload.get("inventory_revision"),
        "items": items,
        "projection_status": str(payload.get("projection_status") or "unavailable"),
    }


@app.get("/sessions/{session_id}/approved-content")
async def list_approved_content(session_id: str, app_id: str, user_id: str):
    session = session_repo.get(session_id)
    if session is None:
        return {"session_id": session_id, "approved_content": []}
    if session["collection_id"] != app_id or session["user_id"] != user_id:
        raise HTTPException(status_code=400, detail="Session identity mismatch.")
    return {
        "session_id": session_id,
        "approved_content": session_repo.list_approved_content(session_id),
        "latest": session_repo.get_latest_approved_content(session_id),
    }


@app.post("/sessions/{session_id}/approved-content")
async def create_session_approved_content(session_id: str, payload: ApprovedContentCreateRequest):
    _require_session_scope(
        session_id,
        app_id=payload.app_id,
        user_id=payload.user_id,
    )
    snapshot = None
    if payload.content_text and str(payload.content_text).strip():
        snapshot = create_approved_snapshot(
            session_repo,
            session_id=session_id,
            content_text=str(payload.content_text).strip(),
            artifact_refs=payload.artifact_refs or [],
            target_refs=payload.target_refs or {},
        )
    elif payload.message_id and str(payload.message_id).strip():
        snapshot = create_snapshot_from_message_id(
            session_id=session_id,
            message_id=str(payload.message_id).strip(),
            session_repo=session_repo,
            chat_repo=chat_repo,
        )
    elif payload.use_latest_assistant_message:
        snapshot = create_snapshot_from_latest_assistant_message(
            session_id=session_id,
            session_repo=session_repo,
            chat_repo=chat_repo,
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide content_text, message_id, or use_latest_assistant_message=true.",
        )
    if snapshot is None:
        raise HTTPException(
            status_code=400,
            detail="Unable to create approved content from the requested source.",
        )
    runtime_state = session_repo.get_runtime_state(session_id)
    lane_state = _session_lane_state(runtime_state)
    lane_state["content_lane"]["latest_approved_content_id"] = snapshot.get("approved_content_id")
    lane_state["content_lane"]["latest_revision_id"] = snapshot.get("revision_id")
    runtime_state["session_lane_state"] = lane_state
    session_repo.set_runtime_state(session_id, runtime_state)
    reviewed_at = datetime.now(timezone.utc).isoformat()
    source_message_id = str(snapshot.get("source_message_id") or "").strip()
    source_message_ids = [source_message_id] if source_message_id else []
    revision_id = str(snapshot.get("revision_id") or "").strip()
    artifact_name = f"{_safe_filename_stem(revision_id or source_message_id or session_id, 'reviewed-chat')}.md"
    artifact_display_name = _derive_reviewed_artifact_display_name(snapshot)
    reviewed_artifact: dict[str, Any] | None = None
    reviewed_artifact_result: dict[str, Any] | None = None
    reviewed_artifact_error: str | None = None
    snapshot_content_hash = str(snapshot.get("content_hash") or "").strip() or content_hash_for(
        str(snapshot.get("content_text") or "")
    )
    try:
        existing_artifact: dict[str, Any] | None = None
        inventory_getter = getattr(execution_client, "get_artifact_inventory", None)
        if callable(inventory_getter):
            inventory_payload = inventory_getter(
                app_id=payload.app_id,
                session_id=session_id,
                artifact_type="chat_export",
                status="ready",
            ) or {}
            inventory_items = inventory_payload.get("items", []) if isinstance(inventory_payload, dict) else []
            for item in inventory_items:
                if not isinstance(item, dict):
                    continue
                item_source_ids = [str(value or "").strip() for value in item.get("source_message_ids", [])]
                item_content_hash = str(item.get("content_hash") or "").strip()
                if (source_message_id and source_message_id in item_source_ids) or (
                    snapshot_content_hash and item_content_hash == snapshot_content_hash
                ):
                    existing_artifact = item
                    break
        if existing_artifact is not None:
            updater = getattr(execution_client, "update_artifact_metadata", None)
            artifact_id = str(existing_artifact.get("artifact_id") or "").strip()
            metadata_patch = {
                "reviewed": True,
                "reviewed_at": reviewed_at,
                "reviewed_by": payload.user_id,
                "review_source": "user_marked_reviewed",
                "source_message_ids": source_message_ids,
                "content_hash": snapshot_content_hash,
            }
            if artifact_id and callable(updater):
                artifact_payload = updater(
                    app_id=payload.app_id,
                    artifact_id=artifact_id,
                    metadata=metadata_patch,
                )
                artifact_payload = artifact_payload if isinstance(artifact_payload, dict) else {}
                reviewed_artifact_result = {
                    "status": "completed",
                    "updated_existing_artifact": True,
                    "result": artifact_payload,
                }
            else:
                artifact_payload = {
                    **existing_artifact,
                    **metadata_patch,
                }
                reviewed_artifact_result = {
                    "status": "completed",
                    "reused_existing_artifact": True,
                    "result": artifact_payload,
                }
        else:
            reviewed_artifact_result = execution_client.submit_skill(
                session_id=session_id,
                app_id=payload.app_id,
                skill_id="save_chat_export_artifact",
                input_payload={
                    "name": artifact_name,
                    "displayName": artifact_display_name,
                    "content": _render_reviewed_chat_artifact_content(snapshot),
                    "format": "md",
                    "messageCount": 1,
                    "sessionId": session_id,
                    "reviewed": True,
                    "reviewedAt": reviewed_at,
                    "reviewedBy": payload.user_id,
                    "reviewSource": "user_marked_reviewed",
                    "sourceMessageIds": source_message_ids,
                    "contentHash": snapshot_content_hash,
                },
            )
            artifact_payload = reviewed_artifact_result.get("result") if isinstance(reviewed_artifact_result, dict) else {}
            artifact_payload = artifact_payload if isinstance(artifact_payload, dict) else {}
        artifact_id = str(artifact_payload.get("artifact_id") or "").strip()
        normalized_item = _normalize_session_artifact_item(
            session_id=session_id,
            app_id=payload.app_id,
            user_id=payload.user_id,
            item={
                **artifact_payload,
                "artifact_id": artifact_id,
                "artifact_type": str(artifact_payload.get("artifact_type") or "chat_export").strip() or "chat_export",
                "display_name": str(artifact_payload.get("display_name") or artifact_display_name).strip() or artifact_display_name,
                "summary": str(artifact_payload.get("summary") or "Reviewed chat content saved for reuse.").strip(),
                "reviewed": True,
                "reviewed_at": reviewed_at,
                "reviewed_by": payload.user_id,
                "review_source": "user_marked_reviewed",
                "source_message_ids": source_message_ids,
                "content_hash": snapshot_content_hash,
                "consumption": {
                    "default_mode": "file_backed",
                    "supported_modes": ["file_backed", "inline_text", "metadata_only"],
                },
                "eligible_consumers": ["execution_composer", "future_markdown_processors"],
                "path": _absolutize_local_path(str(artifact_payload.get("path") or "").strip()) or artifact_payload.get("path"),
                "file_path": _absolutize_local_path(str(artifact_payload.get("file_path") or "").strip()) or artifact_payload.get("file_path"),
            },
        ) if artifact_id else {}
        reviewed_artifact = normalized_item if normalized_item else {
            "artifact_id": artifact_id or None,
            "artifact_type": "chat_export",
            "display_name": artifact_display_name,
            "reviewed": True,
            "reviewed_at": reviewed_at,
            "reviewed_by": payload.user_id,
            "review_source": "user_marked_reviewed",
            "source_message_ids": source_message_ids,
            "content_hash": snapshot_content_hash,
        }
    except Exception as error:
        reviewed_artifact_error = str(error)
    if reviewed_artifact and reviewed_artifact.get("artifact_id"):
        reviewed_artifact_name = str(reviewed_artifact.get("display_name") or artifact_display_name).strip()
        if isinstance(reviewed_artifact_result, dict) and reviewed_artifact_result.get("updated_existing_artifact"):
            summary_text = f"Marked existing artifact `{reviewed_artifact_name}` as reviewed."
        else:
            summary_text = f"Marked reviewed and saved `{reviewed_artifact_name}` for reuse."
    else:
        summary_text = f"Marked reviewed as revision `{snapshot.get('revision_id')}`."
    if reviewed_artifact_error:
        summary_text = f"{summary_text} Artifact creation warning: {reviewed_artifact_error}"
    return {
        "session_id": session_id,
        "approved_content": snapshot,
        "session_lane_state": lane_state,
        "summary_text": summary_text,
        "reviewed_artifact": reviewed_artifact,
        "reviewed_artifact_result": reviewed_artifact_result,
        "reviewed_artifact_error": reviewed_artifact_error,
    }


@app.post("/sessions/{session_id}/integrations/notebooklm/login")
async def launch_session_notebooklm_login(session_id: str, payload: IntegrationActionRequest):
    session = session_repo.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["collection_id"] != payload.app_id or session["user_id"] != payload.user_id:
        raise HTTPException(status_code=400, detail="Session identity mismatch.")
    login_result = _launch_notebooklm_login()
    runtime_state = session_repo.get_runtime_state(session_id)
    lane_state = _session_lane_state(runtime_state)
    lane_state.setdefault("execution_lane", {})["latest_login_launch"] = {
        "provider": "notebooklm",
        "command": login_result.get("command"),
    }
    runtime_state["session_lane_state"] = lane_state
    session_repo.set_runtime_state(session_id, runtime_state)
    summary_text = (
        "NotebookLM login launched. Complete sign-in in the opened browser, then retry the last @exec request."
    )
    chat_repo.append(
        session_id,
        "assistant",
        summary_text,
        retrieval_summary={
            "execution_override": True,
            "command": "login",
            "provider": "notebooklm",
        },
    )
    return {
        "content": summary_text,
        "session_lane_state": lane_state,
        "login_result": login_result,
    }


@app.get("/sessions/{session_id}/uploads")
async def list_session_uploads(session_id: str, app_id: str, user_id: str):
    session = session_repo.get(session_id)
    if session is None:
        return {"session_id": session_id, "uploads": []}
    if session["collection_id"] != app_id or session["user_id"] != user_id:
        raise HTTPException(status_code=400, detail="Session identity mismatch.")
    return {"session_id": session_id, "uploads": _public_session_uploads(session_repo.list_uploads(session_id))}


def _public_session_uploads(uploads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    public_keys = ("id", "session_id", "filename", "mime_type", "size_bytes", "sha256", "created_at")
    return [
        {key: upload[key] for key in public_keys if key in upload}
        for upload in uploads
    ]


@app.get("/sessions/{session_id}/uploads/duplicate-report")
async def legacy_upload_duplicate_report(session_id: str, app_id: str, user_id: str):
    _require_session_scope(session_id, app_id=app_id, user_id=user_id)
    return await run_in_threadpool(
        _artifact_upload_service().legacy_duplicate_report,
        app_id=app_id,
        session_id=session_id,
        user_id=user_id,
    )


def _agent_input_max_bytes() -> int:
    return int(os.getenv("RAGENIUS_AGENT_INPUT_MAX_BYTES") or "536870912")


def _artifact_upload_service() -> ArtifactUploadService:
    return ArtifactUploadService(
        session_repo,
        execution_client,
        max_bytes=_agent_input_max_bytes(),
    )


async def _artifact_upload_cleanup_loop() -> None:
    interval = max(
        60, int(os.getenv("RAGENIUS_UPLOAD_CLEANUP_INTERVAL_SECONDS") or "3600")
    )
    while True:
        await asyncio.sleep(interval)
        await _run_artifact_upload_cleanup_once()


async def _run_artifact_upload_cleanup_once() -> None:
    try:
        await run_in_threadpool(_artifact_upload_service().cleanup_expired)
    except Exception as exc:
        print(f"[artifact-upload-cleanup] cleanup failed: {exc}", file=sys.stderr)


def _analyze_canonical_upload(
    operation: Dict[str, Any],
    *,
    builder_context: Dict[str, Any],
    session: Dict[str, Any],
) -> Dict[str, Any]:
    filename = str(operation.get("filename") or "upload.bin")
    mime_type = str(operation.get("normalized_mime_type") or operation.get("mime_type") or "")
    suffix = Path(filename).suffix.lower()
    extractable = (
        mime_type.startswith("text/")
        or suffix in {".md", ".txt", ".json", ".csv", ".yaml", ".yml", ".pdf"}
    )
    analysis_limit = int(os.getenv("RAGENIUS_UPLOAD_ANALYSIS_MAX_BYTES") or "33554432")
    staged_path = Path(str(operation.get("file_path") or ""))
    content = b""
    if extractable and int(operation.get("size_bytes") or 0) <= analysis_limit:
        content = staged_path.read_bytes()
    text_content = _extract_session_upload_text(filename, mime_type, content) if content else ""
    upload_event = {
        "id": str(operation["upload_operation_id"]),
        "session_id": str(operation["session_id"]),
        "filename": filename,
        "mime_type": mime_type,
        "size_bytes": int(operation.get("size_bytes") or 0),
        "sha256": str(operation.get("sha256") or ""),
        "text_content": text_content,
        "created_at": operation.get("created_at"),
    }
    runtime_state = session_repo.get_runtime_state(str(operation["session_id"]))
    state: Dict[str, Any] = {
        "session_id": operation["session_id"],
        "collection_id": operation["app_id"],
        "domain": builder_context["adapter_json"].get("domain") or "general",
        "user_id": operation["user_id"],
        "planner_mode": builder_context.get("planner_mode", "legacy"),
        "instruction_understanding_mode": builder_context.get("instruction_understanding_mode", "hybrid_shadow"),
        "config_version": session["config_version"],
        "adapter_version": session["adapter_version"],
        "template_version": session["template_version"],
        "user_query": _upload_analysis_query(filename),
        "turn_input_type": "session_upload",
        "session_upload_event_ids": [upload_event["id"]],
        "pending_upload_analysis": True,
        "chat_history": chat_repo.history(str(operation["session_id"])),
        "session_uploads": [*session_repo.list_uploads(str(operation["session_id"])), upload_event],
        "config_json": builder_context["config_json"],
        "adapter_json": builder_context["adapter_json"],
        "template_registry": builder_context["template_registry"],
        "workflow_progress": runtime_state.get("workflow_progress", {}),
        "session_execution_state": runtime_state.get("session_execution_state", {}),
        "intermediate_outputs": runtime_state.get("intermediate_outputs", []),
        "assembly_state": runtime_state.get("assembly_state", {}),
        "session_lane_state": runtime_state.get("session_lane_state", {}),
    }
    response = run_chat_pipeline(
        state,
        session_repo=session_repo,
        chat_repo=chat_repo,
        planner_repo=planner_repo,
        retrieval_repo=retrieval_repo,
    )
    response["session_id"] = operation["session_id"]
    return response


@app.post("/sessions/{session_id}/artifacts/uploads", status_code=201)
async def upload_canonical_session_artifact(
    session_id: str,
    app_id: str = Form(...),
    user_id: str = Form(...),
    upload_operation_id: str = Form(...),
    analysis_mode: str = Form("none"),
    file: UploadFile = File(...),
):
    session = _require_session_scope(session_id, app_id=app_id, user_id=user_id)
    operation_id = str(upload_operation_id or "").strip()
    if not operation_id or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", operation_id):
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_UPLOAD_OPERATION_ID",
            "message": "Upload operation id is invalid.",
        })
    if analysis_mode not in {"none", "normal_query"}:
        raise HTTPException(status_code=422, detail={
            "code": "INVALID_UPLOAD_ANALYSIS_MODE",
            "message": "Upload analysis mode is invalid.",
        })
    builder_context = _load_builder_context(app_id) if analysis_mode == "normal_query" else None
    analysis = None
    if builder_context is not None:
        analysis = lambda operation: _analyze_canonical_upload(
            operation,
            builder_context=builder_context,
            session=session,
        )
    try:
        return await run_in_threadpool(
            _artifact_upload_service().upload,
            app_id=app_id,
            session_id=session_id,
            user_id=user_id,
            upload_operation_id=operation_id,
            filename=file.filename or "upload.bin",
            mime_type=file.content_type,
            source=file.file,
            analysis=analysis,
            analysis_mode=analysis_mode,
        )
    except ValueError as exc:
        message = str(exc)
        status = 413 if "maximum" in message.lower() else 409
        raise HTTPException(status_code=status, detail={
            "code": "ARTIFACT_UPLOAD_REJECTED",
            "message": message,
        }) from exc


@app.post("/sessions/{session_id}/artifacts/uploads/{upload_operation_id}/retry")
async def retry_canonical_session_artifact(
    session_id: str,
    upload_operation_id: str,
    app_id: str,
    user_id: str,
):
    session = _require_session_scope(session_id, app_id=app_id, user_id=user_id)
    operation = session_repo.get_upload_operation(
        app_id=app_id,
        session_id=session_id,
        user_id=user_id,
        upload_operation_id=upload_operation_id,
    )
    analysis = None
    if (
        operation
        and operation.get("status") != "ready"
        and operation.get("analysis_mode") == "normal_query"
    ):
        builder_context = _load_builder_context(app_id)
        analysis = lambda retry_operation: _analyze_canonical_upload(
            retry_operation,
            builder_context=builder_context,
            session=session,
        )
    try:
        return await run_in_threadpool(
            _artifact_upload_service().retry,
            app_id=app_id,
            session_id=session_id,
            user_id=user_id,
            upload_operation_id=upload_operation_id,
            analysis=analysis,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={
            "code": "UPLOAD_OPERATION_NOT_FOUND",
            "message": "Upload operation is unavailable.",
        }) from exc


def _prepare_execution_upload(app_id: str, session_id: str, upload_id: str) -> Dict[str, Any]:
    session = session_repo.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session upload not found.")
    user_id = str(session.get("user_id") or "")
    upload = session_repo.get_upload(session_id, upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Session upload not found.")
    result = _artifact_upload_service().import_legacy_upload(
        app_id=app_id, session_id=session_id, user_id=user_id, upload_id=upload_id,
    )
    if result.get("status") != "ready" or not isinstance(result.get("artifact"), dict):
        raise HTTPException(status_code=410, detail={
            "code": str(result.get("error_code") or "LEGACY_UPLOAD_UNAVAILABLE"),
            "message": "Session upload is no longer available.",
        })
    public_upload = {
        key: upload[key]
        for key in ("id", "session_id", "filename", "mime_type", "size_bytes", "sha256", "created_at")
        if key in upload
    }
    return {
        "upload": public_upload,
        "artifact": result["artifact"],
        "preparation_status": "ready",
        "reused_existing_artifact": bool(result.get("reused_existing_artifact")),
    }


@app.post("/sessions/{session_id}/execution-inputs", status_code=201)
async def upload_execution_input(
    session_id: str,
    app_id: str = Form(...),
    user_id: str = Form(...),
    file: UploadFile = File(...),
):
    _require_session_scope(session_id, app_id=app_id, user_id=user_id)
    try:
        upload = await run_in_threadpool(
            session_repo.add_upload_stream,
            session_id,
            filename=file.filename or "upload.bin",
            mime_type=file.content_type,
            source=file.file,
            max_bytes=_agent_input_max_bytes(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    return await run_in_threadpool(_prepare_execution_upload, app_id, session_id, upload["id"])


@app.post("/sessions/{session_id}/uploads/{upload_id}/prepare-for-execution")
async def prepare_existing_execution_input(
    session_id: str,
    upload_id: str,
    app_id: str,
    user_id: str,
):
    _require_session_scope(session_id, app_id=app_id, user_id=user_id)
    return await run_in_threadpool(_prepare_execution_upload, app_id, session_id, upload_id)


@app.post("/sessions/{session_id}/uploads")
async def upload_session_artifact(
    session_id: str,
    app_id: str = Form(...),
    user_id: str = Form(...),
    file: UploadFile = File(...),
):
    builder_context = _load_builder_context(app_id)
    try:
        session = session_repo.get_or_create(
            session_id,
            collection_id=app_id,
            user_id=user_id,
            title=None,
            config_version=1,
            adapter_version=1,
            template_version=1,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    content = await file.read()
    text_content = _extract_session_upload_text(file.filename or "upload.bin", file.content_type, content)
    upload = session_repo.add_upload(
        session_id,
        filename=file.filename or "upload.bin",
        mime_type=file.content_type,
        content=content,
        text_content=text_content,
    )
    runtime_state = session_repo.get_runtime_state(session_id)
    state: Dict[str, Any] = {
        "session_id": session_id,
        "collection_id": app_id,
        "domain": builder_context["adapter_json"].get("domain") or "general",
        "user_id": user_id,
        "planner_mode": builder_context.get("planner_mode", "legacy"),
        "instruction_understanding_mode": builder_context.get("instruction_understanding_mode", "hybrid_shadow"),
        "config_version": session["config_version"],
        "adapter_version": session["adapter_version"],
        "template_version": session["template_version"],
        "user_query": _upload_analysis_query(upload["filename"]),
        "turn_input_type": "session_upload",
        "session_upload_event_ids": [upload["id"]],
        "pending_upload_analysis": True,
        "chat_history": chat_repo.history(session_id),
        "session_uploads": session_repo.list_uploads(session_id),
        "config_json": builder_context["config_json"],
        "adapter_json": builder_context["adapter_json"],
        "template_registry": builder_context["template_registry"],
        "workflow_progress": runtime_state.get("workflow_progress", {}),
        "session_execution_state": runtime_state.get("session_execution_state", {}),
        "intermediate_outputs": runtime_state.get("intermediate_outputs", []),
        "assembly_state": runtime_state.get("assembly_state", {}),
        "session_lane_state": runtime_state.get("session_lane_state", {}),
    }
    response = run_chat_pipeline(
        state,
        session_repo=session_repo,
        chat_repo=chat_repo,
        planner_repo=planner_repo,
        retrieval_repo=retrieval_repo,
    )
    response["session_id"] = session_id
    response["upload"] = {
        "id": upload["id"],
        "filename": upload["filename"],
        "mime_type": upload["mime_type"],
        "size_bytes": upload["size_bytes"],
        "created_at": upload["created_at"],
        "has_text_content": bool(str(upload.get("text_content") or "").strip()),
    }
    return response


@app.post("/sessions/{session_id}/exports")
async def export_session_messages(session_id: str, payload: SessionExportRequest):
    session = _require_session_scope(
        session_id,
        app_id=payload.app_id,
        user_id=payload.user_id,
    )
    normalized_ids = [str(message_id or "").strip() for message_id in payload.message_ids]
    normalized_ids = [message_id for message_id in normalized_ids if message_id]
    if not normalized_ids:
        raise HTTPException(status_code=400, detail="Select at least one message to export.")
    export_format = str(payload.format or "md").strip().lower()
    if export_format not in {"md", "txt"}:
        raise HTTPException(status_code=400, detail="Export format must be md or txt.")

    history = chat_repo.history(session_id)
    messages_by_id = {
        str(message.get("id") or "").strip(): message for message in history if str(message.get("id") or "").strip()
    }
    selected_messages: list[dict[str, Any]] = []
    for message_id in normalized_ids:
        message = messages_by_id.get(message_id)
        if message is None:
            raise HTTPException(status_code=400, detail=f"Message `{message_id}` was not found in this session.")
        selected_messages.append(message)

    rendered_content = _render_chat_export_content(selected_messages, export_format)
    selected_source_message_ids = [
        str(message.get("id") or "").strip()
        for message in selected_messages
        if str(message.get("id") or "").strip()
    ]
    selected_content_hash = (
        content_hash_for(str(selected_messages[0].get("content") or ""))
        if len(selected_messages) == 1
        else content_hash_for(rendered_content)
    )
    filename_stem = _safe_filename_stem(payload.filename or f"{session_id}-chat-export")
    extension = "md" if export_format == "md" else "txt"
    artifact_name = f"{filename_stem}.{extension}"
    artifact_display_name = _derive_chat_export_display_name(
        session=session,
        explicit_filename=payload.filename,
        extension=extension,
    )
    export_result = execution_client.submit_skill(
        session_id=session_id,
        app_id=payload.app_id,
        skill_id="save_chat_export_artifact",
        input_payload={
            "name": artifact_name,
            "displayName": artifact_display_name,
            "content": rendered_content,
            "format": export_format,
            "messageCount": len(selected_messages),
            "sessionId": session_id,
            "sourceMessageIds": selected_source_message_ids,
            "contentHash": selected_content_hash,
        },
    )
    export_payload = export_result.get("result")
    export_payload = export_payload if isinstance(export_payload, dict) else {}
    artifact_id = str(export_payload.get("artifact_id") or "").strip()
    artifact_display_name = str(export_payload.get("display_name") or artifact_display_name).strip() or artifact_display_name
    metadata_path = _absolutize_local_path(str(export_payload.get("path") or "").strip())
    file_path = _absolutize_local_path(str(export_payload.get("file_path") or "").strip())
    summary_text = (
        f"Saved {len(selected_messages)} selected message(s) as `{artifact_display_name}`."
    )
    return {
        "session_id": session_id,
        "summary_text": summary_text,
        "export_result": export_result,
        "export_artifact": {
            "artifact_id": artifact_id or None,
            "name": artifact_name,
            "display_name": artifact_display_name,
            "file_path": file_path or None,
            "metadata_path": metadata_path or None,
            "open_url": _build_session_artifact_open_url(
                session_id=session_id,
                app_id=payload.app_id,
                user_id=payload.user_id,
                artifact_id=artifact_id,
            ) if artifact_id else None,
        },
    }


@app.patch("/sessions/{session_id}")
async def update_session(session_id: str, payload: SessionUpdateRequest):
    session = session_repo.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["collection_id"] != payload.app_id or session["user_id"] != payload.user_id:
        raise HTTPException(status_code=400, detail="Session identity mismatch.")
    updated = session
    if payload.title is not None:
        updated = session_repo.set_title(session_id, payload.title) or updated
    if payload.pinned is not None or payload.archived is not None:
        updated = session_repo.set_flags(
            session_id,
            pinned=payload.pinned,
            archived=payload.archived,
        ) or updated
    if updated is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session": updated}


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str, app_id: str, user_id: str):
    session = session_repo.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["collection_id"] != app_id or session["user_id"] != user_id:
        raise HTTPException(status_code=400, detail="Session identity mismatch.")
    deleted = session_repo.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": True, "session_id": session_id}


@app.post("/sessions/{session_id}/workflow/advance")
async def advance_session_workflow(session_id: str, payload: SessionWorkflowActionRequest):
    session = session_repo.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["collection_id"] != payload.app_id or session["user_id"] != payload.user_id:
        raise HTTPException(status_code=400, detail="Session identity mismatch.")

    current_progress = session.get("workflow_progress", {}) if isinstance(session, dict) else {}
    next_progress = _advance_workflow_progress(payload.app_id, current_progress)
    updated = session_repo.set_workflow_progress(session_id, next_progress or current_progress)
    if updated is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "workflow_status": _workflow_status_payload(payload.app_id, updated.get("workflow_progress", {})),
    }


@app.get("/sessions/{session_id}/executions/{execution_id}")
async def get_session_execution_status(
    session_id: str,
    execution_id: str,
    app_id: str,
    user_id: str,
):
    _require_session_scope(session_id, app_id=app_id, user_id=user_id)
    result = await run_in_threadpool(
        execution_client.get_execution_status,
        execution_id,
        app_id=app_id,
        session_id=session_id,
    )
    result = _enrich_execution_result_artifacts(
        session_id=session_id,
        app_id=app_id,
        user_id=user_id,
        submit_result=result,
    )
    runtime_state = session_repo.get_runtime_state(session_id)
    lane_state = _session_lane_state(runtime_state)
    lane_state["execution_lane"]["latest_execution_id"] = execution_id
    lane_state["execution_lane"]["latest_status_result"] = result
    _record_confirmation_lane_state(lane_state, result_payload=result)
    _refresh_async_lane_state_from_status(lane_state, status_result=result)
    runtime_state["session_lane_state"] = lane_state
    session_repo.set_runtime_state(session_id, runtime_state)
    return {"status_result": result, "session_lane_state": lane_state}


@app.post("/sessions/{session_id}/executions/{execution_id}/confirm")
async def confirm_session_execution(session_id: str, execution_id: str, payload: SessionExecutionConfirmRequest):
    _require_session_scope(
        session_id,
        app_id=payload.app_id,
        user_id=payload.user_id,
    )

    runtime_state = session_repo.get_runtime_state(session_id)
    lane_state = _session_lane_state(runtime_state)
    execution_lane = lane_state["execution_lane"]
    confirmation_id = ""
    if str(execution_lane.get("latest_execution_id") or "").strip() == execution_id:
        confirmation_id = str(
            execution_lane.get("latest_confirmation_id") or ""
        ).strip()
    if not confirmation_id:
        status_result = execution_client.get_execution_status(
            execution_id,
            app_id=payload.app_id,
            session_id=session_id,
        )
        _record_confirmation_lane_state(
            lane_state,
            result_payload=status_result,
        )
        confirmation_id = str(
            execution_lane.get("latest_confirmation_id") or ""
        ).strip()
    if not confirmation_id:
        raise HTTPException(
            status_code=409,
            detail="No pending server-issued confirmation is available.",
        )

    result = await run_in_threadpool(
        execution_client.confirm_execution,
        execution_id,
        app_id=payload.app_id,
        confirmation_id=confirmation_id,
        session_id=session_id,
    )
    result = _enrich_execution_result_artifacts(
        session_id=session_id,
        app_id=payload.app_id,
        user_id=payload.user_id,
        submit_result=result,
    )
    lane_state["execution_lane"]["latest_execution_id"] = execution_id
    lane_state["execution_lane"]["latest_status_result"] = result
    lane_state["execution_lane"]["latest_execution_result"] = result
    _record_confirmation_lane_state(lane_state, result_payload=result)
    _record_login_requirement(lane_state, result_payload=result)
    _refresh_async_lane_state_from_status(lane_state, status_result=result)
    runtime_state["session_lane_state"] = lane_state
    session_repo.set_runtime_state(session_id, runtime_state)

    summary_text = _execution_confirmation_summary_text(execution_id, result)
    chat_repo.append(
        session_id,
        "assistant",
        summary_text,
        retrieval_summary={
            "execution_override": True,
            "command": "confirm",
            "execution_id": execution_id,
            "execution_status_result": result,
        },
    )
    return {
        "content": summary_text,
        "citations": [],
        "missing_infoTypes": [],
        "workflow_progress": runtime_state.get("workflow_progress", {}),
        "session_execution_state": runtime_state.get("session_execution_state", {}),
        "session_lane_state": lane_state,
        "execution_override": {
            "command": "confirm",
            "execution_id": execution_id,
            "status_result": result,
        },
    }


@app.get("/sessions/{session_id}/executions/{execution_id}/interactions")
async def list_session_agent_interactions(
    session_id: str,
    execution_id: str,
    app_id: str,
    user_id: str,
):
    _require_session_scope(session_id, app_id=app_id, user_id=user_id)
    result = await run_in_threadpool(
        execution_client.get_agent_interactions,
        execution_id,
        app_id=app_id,
        session_id=session_id,
    )
    _require_successful_execution_proxy(result)
    public_result = _redact_provider_handles(result)
    runtime_state = session_repo.get_runtime_state(session_id)
    lane_state = _session_lane_state(runtime_state)
    lane_state["execution_lane"]["latest_execution_id"] = execution_id
    _record_interaction_lane_state(lane_state, interactions_payload=public_result)
    runtime_state["session_lane_state"] = lane_state
    session_repo.set_runtime_state(session_id, runtime_state)
    return {**public_result, "session_lane_state": lane_state}


@app.get("/sessions/{session_id}/executions/{execution_id}/chat-session")
async def get_session_agent_chat(
    session_id: str, execution_id: str, app_id: str, user_id: str,
):
    _require_session_scope(session_id, app_id=app_id, user_id=user_id)
    result = await run_in_threadpool(
        execution_client.get_agent_chat_session, execution_id,
        app_id=app_id, session_id=session_id,
    )
    _require_successful_execution_proxy(result)
    return _redact_provider_handles(result)


@app.post("/sessions/{session_id}/executions/{execution_id}/follow-ups")
async def submit_session_agent_follow_up(
    session_id: str, execution_id: str, payload: dict,
):
    app_id = str(payload.get("app_id") or "")
    user_id = str(payload.get("user_id") or "")
    _require_session_scope(session_id, app_id=app_id, user_id=user_id)
    result = await run_in_threadpool(
        execution_client.submit_agent_follow_up, execution_id,
        app_id=app_id, session_id=session_id,
        expected_session_version=int(payload.get("expected_session_version") or 0),
        idempotency_key=str(payload.get("idempotency_key") or ""),
        kind=str(payload.get("kind") or ""),
        text=payload.get("text"),
    )
    _require_successful_execution_proxy(result)
    return _redact_provider_handles(result)


@app.post("/sessions/{session_id}/executions/{execution_id}/end-chat-session")
async def end_session_agent_chat(
    session_id: str, execution_id: str, payload: dict,
):
    app_id = str(payload.get("app_id") or "")
    user_id = str(payload.get("user_id") or "")
    _require_session_scope(session_id, app_id=app_id, user_id=user_id)
    persist_final_output = payload.get("persist_final_output") is True
    chat_session = None
    if persist_final_output:
        chat_session = await run_in_threadpool(
            execution_client.get_agent_chat_session, execution_id,
            app_id=app_id, session_id=session_id,
        )
        _require_successful_execution_proxy(chat_session)
    result = await run_in_threadpool(
        execution_client.end_agent_chat_session, execution_id,
        app_id=app_id, session_id=session_id,
        expected_session_version=int(payload.get("expected_session_version") or 0),
    )
    _require_successful_execution_proxy(result)
    public_result = _redact_provider_handles(result)
    final_output = str((chat_session or {}).get("latest_output_text") or "").strip()
    if persist_final_output and final_output:
        existing = next((
            message for message in reversed(chat_repo.history(session_id))
            if message.get("role") == "assistant"
            and message.get("retrievalSummary", {}).get("command") == "agent_chat_final"
            and message.get("retrievalSummary", {}).get("execution_id") == execution_id
        ), None)
        final_message = existing or chat_repo.append(
            session_id,
            "assistant",
            final_output,
            retrieval_summary={
                "execution_override": True,
                "command": "agent_chat_final",
                "execution_id": execution_id,
            },
        )
        public_result["final_message"] = final_message
    return public_result


@app.get("/sessions/{session_id}/executions/{execution_id}/events")
async def list_session_agent_events(
    session_id: str,
    execution_id: str,
    app_id: str,
    user_id: str,
    after_sequence: int = 0,
    limit: int = 100,
):
    _require_session_scope(session_id, app_id=app_id, user_id=user_id)
    result = await run_in_threadpool(
        execution_client.get_agent_events,
        execution_id,
        app_id=app_id,
        session_id=session_id,
        after_sequence=after_sequence,
        limit=limit,
    )
    _require_successful_execution_proxy(result)
    public_result = _redact_provider_handles(result)
    runtime_state = session_repo.get_runtime_state(session_id)
    lane_state = _session_lane_state(runtime_state)
    lane_state["execution_lane"]["latest_execution_id"] = execution_id
    _record_interaction_lane_state(lane_state, events_payload=public_result)
    runtime_state["session_lane_state"] = lane_state
    session_repo.set_runtime_state(session_id, runtime_state)
    return {**public_result, "session_lane_state": lane_state}


@app.post("/sessions/{session_id}/executions/{execution_id}/interactions/{interaction_id}/responses")
async def respond_session_agent_interaction(
    session_id: str,
    execution_id: str,
    interaction_id: str,
    payload: SessionAgentInteractionResponseRequest,
):
    _require_session_scope(session_id, app_id=payload.app_id, user_id=payload.user_id)
    if _contains_provider_handles(payload.response):
        raise HTTPException(status_code=422, detail="Provider identifiers are not accepted.")
    result = await run_in_threadpool(
        execution_client.respond_agent_interaction,
        execution_id,
        interaction_id,
        app_id=payload.app_id,
        session_id=session_id,
        expected_version=payload.expected_version,
        idempotency_key=payload.idempotency_key,
        response=payload.response,
    )
    _require_successful_execution_proxy(result)
    public_result = _redact_provider_handles(result)
    runtime_state = session_repo.get_runtime_state(session_id)
    lane_state = _session_lane_state(runtime_state)
    execution_lane = lane_state["execution_lane"]
    execution_lane["latest_execution_id"] = execution_id
    execution_lane["latest_interaction_id"] = interaction_id
    execution_lane["latest_interaction_state"] = (
        "responded" if public_result.get("outcome") in {"applied", "duplicate"}
        else str(public_result.get("outcome") or "unknown")
    )
    runtime_state["session_lane_state"] = lane_state
    session_repo.set_runtime_state(session_id, runtime_state)
    return {**public_result, "session_lane_state": lane_state}


@app.post("/sessions/{session_id}/executions/{execution_id}/cancel")
async def cancel_session_agent_execution(
    session_id: str,
    execution_id: str,
    payload: IntegrationActionRequest,
):
    _require_session_scope(session_id, app_id=payload.app_id, user_id=payload.user_id)
    result = await run_in_threadpool(
        execution_client.cancel_agent_execution,
        execution_id,
        app_id=payload.app_id,
        session_id=session_id,
    )
    _require_successful_execution_proxy(result)
    public_result = _redact_provider_handles(result)
    runtime_state = session_repo.get_runtime_state(session_id)
    lane_state = _session_lane_state(runtime_state)
    execution_lane = lane_state["execution_lane"]
    execution_lane["latest_execution_id"] = execution_id
    execution_lane["latest_execution_status"] = str(public_result.get("status") or "unknown")
    runtime_state["session_lane_state"] = lane_state
    session_repo.set_runtime_state(session_id, runtime_state)
    return {**public_result, "session_lane_state": lane_state}


@app.get("/apps/{app_id}/sessions")
async def list_app_sessions(app_id: str, user_id: str, include_archived: bool = False):
    builder_store = get_builder_store()
    app_record = builder_store.get_application(app_id)
    if app_record is None:
        raise HTTPException(status_code=404, detail="Application not found")
    sessions = session_repo.list_for_app_user(app_id, user_id, include_archived=include_archived)
    enriched = []
    for session in sessions:
        enriched.append(
            {
                **session,
                "workflow_status": _workflow_status_payload(
                    app_id,
                    session.get("workflow_progress", {}),
                    runtime_state=session.get("runtime_state", {}),
                ),
            }
        )
    return {"app_id": app_id, "sessions": enriched}
