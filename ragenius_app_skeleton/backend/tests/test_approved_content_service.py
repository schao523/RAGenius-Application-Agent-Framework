from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from ragenius_app_skeleton.backend.app.approved_content_service import (
    content_hash_for,
    create_approved_snapshot,
    create_snapshot_from_message_id,
    create_snapshot_from_latest_assistant_message,
)
from ragenius_app_skeleton.backend.app.chat_repos import ChatRepo, SessionRepo


def _db_path() -> Path:
    root = Path(tempfile.gettempdir()) / "ragenius_app_tests" / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root / "runtime_state.db"


def test_content_hash_for_is_stable():
    assert content_hash_for("hello") == content_hash_for("hello")
    assert len(content_hash_for("hello")) == 64


def test_create_snapshot_from_latest_assistant_message():
    db_path = _db_path()
    session_repo = SessionRepo(db_path=db_path)
    chat_repo = ChatRepo(db_path=db_path)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    assistant = chat_repo.append("session-1", "assistant", "Approved content body")
    snapshot = create_snapshot_from_latest_assistant_message(
        session_id="session-1",
        session_repo=session_repo,
        chat_repo=chat_repo,
    )
    assert snapshot is not None
    assert snapshot["source_message_id"] == assistant["id"]
    assert snapshot["content_text"] == "Approved content body"


def test_create_approved_snapshot_round_trips_from_repo():
    db_path = _db_path()
    session_repo = SessionRepo(db_path=db_path)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    snapshot = create_approved_snapshot(
        session_repo,
        session_id="session-1",
        content_text="Explain the workflow",
    )
    loaded = session_repo.get_approved_content(snapshot["approved_content_id"])
    assert loaded is not None
    assert loaded["content_text"] == "Explain the workflow"


def test_create_snapshot_from_specific_message_id():
    db_path = _db_path()
    session_repo = SessionRepo(db_path=db_path)
    chat_repo = ChatRepo(db_path=db_path)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    chat_repo.append("session-1", "assistant", "First answer")
    target = chat_repo.append("session-1", "assistant", "Second answer")
    snapshot = create_snapshot_from_message_id(
        session_id="session-1",
        message_id=target["id"],
        session_repo=session_repo,
        chat_repo=chat_repo,
    )
    assert snapshot is not None
    assert snapshot["source_message_id"] == target["id"]
    assert snapshot["content_text"] == "Second answer"
