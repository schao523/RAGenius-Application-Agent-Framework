from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from ragenius_app_skeleton.backend.app.chat_repos import SessionRepo


def _db_path() -> Path:
    root = Path(tempfile.gettempdir()) / "ragenius_app_tests" / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root / "runtime_state.db"


def test_runtime_state_stores_dual_lane_without_losing_legacy_fields():
    db_path = _db_path()
    repo = SessionRepo(db_path=db_path)
    repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    repo.set_runtime_state(
        "session-1",
        {
            "workflow_progress": {"workflow_id": "wf-1"},
            "session_execution_state": {"execution_status": "guiding"},
            "session_lane_state": {
                "content_lane": {"latest_approved_content_id": "ac-1"},
                "execution_lane": {"latest_execution_intent_id": "ei-1"},
            },
        },
    )
    runtime_state = repo.get_runtime_state("session-1")
    assert runtime_state["workflow_progress"]["workflow_id"] == "wf-1"
    assert runtime_state["session_execution_state"]["execution_status"] == "guiding"
    assert runtime_state["session_lane_state"]["content_lane"]["latest_approved_content_id"] == "ac-1"
    assert runtime_state["session_lane_state"]["execution_lane"]["latest_execution_intent_id"] == "ei-1"


def test_repo_round_trips_approved_content_and_execution_intent():
    db_path = _db_path()
    repo = SessionRepo(db_path=db_path)
    repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    snapshot = repo.save_approved_content(
        approved_content_id="ac-1",
        session_id="session-1",
        revision_id="rev-1",
        source_message_id="msg-1",
        content_hash="hash-1",
        content_text="approved content",
        created_at="2026-06-03T00:00:00+00:00",
    )
    intent = repo.save_execution_intent(
        execution_intent_id="ei-1",
        session_id="session-1",
        approved_content_id=snapshot["approved_content_id"],
        skill_id="notebooklm_generate_video",
        skill_version=None,
        command_text="notebookTitle=Demo",
        mapped_input={"notebookTitle": "Demo"},
        execution_mode="sync",
        created_at="2026-06-03T00:00:01+00:00",
    )
    assert repo.get_latest_approved_content("session-1")["approved_content_id"] == "ac-1"
    assert repo.get_execution_intent("ei-1")["skill_id"] == "notebooklm_generate_video"
    assert intent["mapped_input"]["notebookTitle"] == "Demo"
