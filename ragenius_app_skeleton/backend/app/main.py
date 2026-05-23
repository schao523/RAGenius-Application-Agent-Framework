"""Integrated FastAPI backend for the builder-backed RAGenius app runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .builder_runtime import derive_builder_adapter_json, derive_builder_config_json
from .builder_store import get_builder_store
from .chat_repos import ChatRepo, InstructionUnderstandingRepo, RetrievalRepo, SessionRepo
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
from .ingestion_repo import IngestionRepo
from .ingestion_service import enqueue_builder_ingestion
from .llm_runtime import USER_VISIBLE_TASKS, resolve_task_model
from .planner_repo import InMemoryPlannerRepo
from workflows.nodes.load_template_registry import _extract_instruction_workflows

app = FastAPI(title="RAGenius App API")
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


class BuilderIngestPayload(BaseModel):
    document_ids: list[str] | None = None


class SessionUpdateRequest(BaseModel):
    app_id: str
    user_id: str
    title: str | None = None
    pinned: bool | None = None
    archived: bool | None = None


class SessionWorkflowActionRequest(BaseModel):
    app_id: str
    user_id: str


class ApprovalRequest(BaseModel):
    approved_findings: list[dict[str, Any]]
    approver: str | None = None


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
    effective_domain = payload.domain or builder_context["adapter_json"].get("domain") or "general"

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
    }

    return run_chat_pipeline(
        state,
        session_repo=session_repo,
        chat_repo=chat_repo,
        planner_repo=planner_repo,
        retrieval_repo=retrieval_repo,
    )


@app.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, app_id: str, user_id: str):
    session = session_repo.get(session_id)
    if session is None:
        return {"session_id": session_id, "messages": [], "workflow_status": {}}
    if session["collection_id"] != app_id or session["user_id"] != user_id:
        raise HTTPException(status_code=400, detail="Session identity mismatch.")
    history = chat_repo.history(session_id)
    context = _load_builder_readonly_context(app_id)
    return {
        "session_id": session_id,
        "messages": history,
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
        "session_uploads": session_repo.list_uploads(session_id),
    }


@app.get("/sessions/{session_id}/uploads")
async def list_session_uploads(session_id: str, app_id: str, user_id: str):
    session = session_repo.get(session_id)
    if session is None:
        return {"session_id": session_id, "uploads": []}
    if session["collection_id"] != app_id or session["user_id"] != user_id:
        raise HTTPException(status_code=400, detail="Session identity mismatch.")
    return {"session_id": session_id, "uploads": session_repo.list_uploads(session_id)}


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
