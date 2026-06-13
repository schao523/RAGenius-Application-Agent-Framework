"""Deterministic execution-intent builders for explicit execution turns."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .chat_repos import SessionRepo


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


_READ_ONLY_SKILL_IDS = {
    "notebooklm_list_notebooks",
    "notebooklm_list_sources",
    "notebooklm_existing_notebook_ask",
    "notebooklm_ask",
}

_ASYNC_DEFAULT_SKILL_IDS = {
    "notebooklm_generate_video",
}

_EXECUTION_SKILL_POLICIES: dict[str, dict[str, Any]] = {
    "notebooklm_list_notebooks": {
        "requires_approved_content": False,
        "read_only": True,
        "review_required": False,
        "required_all": [],
        "required_any_of": [],
    },
    "notebooklm_list_sources": {
        "requires_approved_content": False,
        "read_only": True,
        "review_required": False,
        "required_all": [],
        "required_any_of": [["notebookId", "notebookTitle"]],
    },
    "notebooklm_existing_notebook_ask": {
        "requires_approved_content": False,
        "read_only": True,
        "review_required": False,
        "required_all": ["question"],
        "required_any_of": [["notebookId", "notebookTitle"]],
    },
    "notebooklm_poll_artifact_task": {
        "requires_approved_content": False,
        "read_only": True,
        "review_required": False,
        "required_all": ["taskId", "artifactKind"],
        "required_any_of": [["notebookId", "notebookTitle"]],
    },
    "notebooklm_generate_report": {
        "requires_approved_content": True,
        "read_only": False,
        "review_required": True,
        "required_all": [],
        "required_any_of": [["notebookId", "notebookTitle"]],
    },
    "notebooklm_generate_slide_deck": {
        "requires_approved_content": True,
        "read_only": False,
        "review_required": True,
        "required_all": [],
        "required_any_of": [["notebookId", "notebookTitle"]],
    },
    "notebooklm_generate_video": {
        "requires_approved_content": True,
        "read_only": False,
        "review_required": True,
        "required_all": [],
        "required_any_of": [["notebookId", "notebookTitle"]],
    },
    "notebooklm_add_source_text": {
        "requires_approved_content": False,
        "read_only": False,
        "review_required": True,
        "required_all": ["title", "content"],
        "required_any_of": [["notebookId", "notebookTitle"]],
    },
    "notebooklm_add_source_url": {
        "requires_approved_content": False,
        "read_only": False,
        "review_required": True,
        "required_all": ["url"],
        "required_any_of": [["notebookId", "notebookTitle"]],
    },
    "notebooklm_add_source_file": {
        "requires_approved_content": False,
        "read_only": False,
        "review_required": True,
        "required_all": ["filePath"],
        "required_any_of": [["notebookId", "notebookTitle"]],
    },
}


def get_execution_skill_policy(skill_id: str) -> dict[str, Any]:
    normalized = str(skill_id or "").strip()
    policy = _EXECUTION_SKILL_POLICIES.get(normalized)
    if policy is None:
        return {
            "supported": False,
            "requires_approved_content": False,
            "read_only": False,
            "review_required": False,
            "required_all": [],
            "required_any_of": [],
            "supported_skill_ids": sorted(_EXECUTION_SKILL_POLICIES),
        }
    return {
        "supported": True,
        "supported_skill_ids": sorted(_EXECUTION_SKILL_POLICIES),
        **policy,
    }


def validate_execution_skill_request(
    skill_id: str,
    *,
    overrides: dict[str, Any] | None = None,
    approved_snapshot: dict[str, Any] | None = None,
) -> str | None:
    policy = get_execution_skill_policy(skill_id)
    if not policy.get("supported"):
        supported = ", ".join(policy.get("supported_skill_ids") or [])
        return f"Unknown exec skill `{skill_id}`. Supported skills: {supported}."

    effective_input = dict(overrides or {})
    if (
        approved_snapshot is not None
        and policy.get("requires_approved_content")
        and "instructions" not in effective_input
    ):
        effective_input["instructions"] = approved_snapshot.get("content_text", "")

    for field in policy.get("required_all", []):
        value = effective_input.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            return f"Skill `{skill_id}` requires `{field}`."

    for fields in policy.get("required_any_of", []):
        if not any(
            value is not None and (not isinstance(value, str) or bool(value.strip()))
            for value in (effective_input.get(field) for field in fields)
        ):
            return f"Skill `{skill_id}` requires one of: {', '.join(fields)}."

    return None


def build_execution_intent(
    session_repo: SessionRepo,
    *,
    session_id: str,
    skill_id: str,
    command_text: str,
    approved_snapshot: dict[str, Any] | None,
    overrides: dict[str, Any] | None = None,
    skill_version: str | None = None,
) -> dict[str, Any]:
    mapped_input = dict(overrides or {})
    policy = get_execution_skill_policy(skill_id)
    if (
        approved_snapshot is not None
        and policy.get("requires_approved_content")
        and "instructions" not in mapped_input
    ):
        mapped_input["instructions"] = approved_snapshot.get("content_text", "")
    explicit_execution_mode = str(mapped_input.get("execution_mode") or "").strip().lower()
    if (
        skill_id in _ASYNC_DEFAULT_SKILL_IDS
        and "waitForCompletion" not in mapped_input
        and explicit_execution_mode not in {"sync", "async"}
    ):
        mapped_input["waitForCompletion"] = False
        mapped_input["execution_mode"] = "async"
        explicit_execution_mode = "async"
    elif explicit_execution_mode == "async" and "waitForCompletion" not in mapped_input:
        mapped_input["waitForCompletion"] = False
    elif explicit_execution_mode == "sync" and "waitForCompletion" not in mapped_input:
        mapped_input["waitForCompletion"] = True

    execution_mode = (
        "async"
        if mapped_input.get("waitForCompletion") is False or explicit_execution_mode == "async"
        else "sync"
    )
    return session_repo.save_execution_intent(
        execution_intent_id=f"ei_{uuid.uuid4().hex[:12]}",
        session_id=session_id,
        approved_content_id=approved_snapshot.get("approved_content_id") if approved_snapshot else None,
        skill_id=skill_id,
        skill_version=skill_version,
        command_text=command_text,
        mapped_input=mapped_input,
        execution_mode=execution_mode,
        created_at=_utcnow(),
    )
