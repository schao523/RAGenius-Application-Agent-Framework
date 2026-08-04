"""Approved-content snapshot helpers for execution-bound app flows."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from .chat_repos import ChatRepo, SessionRepo


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_hash_for(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def create_approved_snapshot(
    session_repo: SessionRepo,
    *,
    session_id: str,
    content_text: str,
    source_message_id: str | None = None,
    artifact_refs: list[dict[str, Any]] | None = None,
    target_refs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    created_at = _utcnow()
    snapshot = session_repo.save_approved_content(
        approved_content_id=f"ac_{uuid.uuid4().hex[:12]}",
        session_id=session_id,
        revision_id=f"rev_{uuid.uuid4().hex[:8]}",
        source_message_id=source_message_id,
        content_hash=content_hash_for(content_text),
        content_text=str(content_text or ""),
        artifact_refs=artifact_refs or [],
        target_refs=target_refs or {},
        created_at=created_at,
    )
    return snapshot


def create_snapshot_from_latest_assistant_message(
    *,
    session_id: str,
    session_repo: SessionRepo,
    chat_repo: ChatRepo,
) -> dict[str, Any] | None:
    history = chat_repo.history(session_id)
    assistant_messages = [item for item in history if str(item.get("role") or "").strip() == "assistant"]
    if not assistant_messages:
        return None
    latest = assistant_messages[-1]
    content_text = str(latest.get("content") or "").strip()
    if not content_text:
        return None
    return create_approved_snapshot(
        session_repo,
        session_id=session_id,
        content_text=content_text,
        source_message_id=str(latest.get("id") or "").strip() or None,
    )


def create_snapshot_from_message_id(
    *,
    session_id: str,
    message_id: str,
    session_repo: SessionRepo,
    chat_repo: ChatRepo,
) -> dict[str, Any] | None:
    target_id = str(message_id or "").strip()
    if not target_id:
        return None
    history = chat_repo.history(session_id)
    message = next((item for item in history if str(item.get("id") or "").strip() == target_id), None)
    if not isinstance(message, dict):
        return None
    if str(message.get("role") or "").strip() != "assistant":
        return None
    content_text = str(message.get("content") or "").strip()
    if not content_text:
        return None
    return create_approved_snapshot(
        session_repo,
        session_id=session_id,
        content_text=content_text,
        source_message_id=target_id,
    )


def resolve_approved_snapshot(
    *,
    session_id: str,
    session_repo: SessionRepo,
    chat_repo: ChatRepo,
    approved_content_id: str | None = None,
    create_from_latest_message: bool = False,
) -> dict[str, Any] | None:
    if approved_content_id:
        snapshot = session_repo.get_approved_content(approved_content_id)
        if snapshot and snapshot.get("session_id") == session_id:
            return snapshot
        return None
    snapshot = session_repo.get_latest_approved_content(session_id)
    if snapshot is not None:
        return snapshot
    if create_from_latest_message:
        return create_snapshot_from_latest_assistant_message(
            session_id=session_id,
            session_repo=session_repo,
            chat_repo=chat_repo,
        )
    return None
