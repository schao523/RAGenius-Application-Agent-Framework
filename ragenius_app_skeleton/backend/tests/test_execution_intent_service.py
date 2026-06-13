from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from ragenius_app_skeleton.backend.app.chat_repos import SessionRepo
from ragenius_app_skeleton.backend.app.execution_intent_service import (
    build_execution_intent,
    get_execution_skill_policy,
)


def _db_path() -> Path:
    root = Path(tempfile.gettempdir()) / "ragenius_app_tests" / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root / "runtime_state.db"


def test_build_execution_intent_keeps_snapshot_text_and_notebook_title():
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
    snapshot = session_repo.save_approved_content(
        approved_content_id="ac_1",
        session_id="session-1",
        revision_id="rev_1",
        source_message_id=None,
        content_hash="hash",
        content_text="Explain the tool in a friendly way",
        created_at="2026-06-03T00:00:00+00:00",
    )
    intent = build_execution_intent(
        session_repo,
        session_id="session-1",
        skill_id="notebooklm_generate_video",
        command_text='notebookTitle="GPT Application Designer" waitForCompletion=false',
        approved_snapshot=snapshot,
        overrides={
            "notebookTitle": "GPT Application Designer",
            "waitForCompletion": False,
        },
    )
    assert intent["mapped_input"]["instructions"] == "Explain the tool in a friendly way"
    assert intent["mapped_input"]["notebookTitle"] == "GPT Application Designer"
    assert intent["execution_mode"] == "async"


def test_build_execution_intent_does_not_inject_snapshot_text_for_read_only_listing():
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
    snapshot = session_repo.save_approved_content(
        approved_content_id="ac_1",
        session_id="session-1",
        revision_id="rev_1",
        source_message_id=None,
        content_hash="hash",
        content_text="Explain the tool in a friendly way",
        created_at="2026-06-03T00:00:00+00:00",
    )
    intent = build_execution_intent(
        session_repo,
        session_id="session-1",
        skill_id="notebooklm_list_notebooks",
        command_text="",
        approved_snapshot=snapshot,
        overrides={},
    )

    assert "instructions" not in intent["mapped_input"]
    assert intent["execution_mode"] == "sync"


def test_execution_skill_policy_marks_generation_skill_as_approval_required():
    policy = get_execution_skill_policy("notebooklm_generate_video")

    assert policy["requires_approved_content"] is True
    assert policy["review_required"] is True


def test_execution_skill_policy_allows_read_only_listing_without_approval():
    policy = get_execution_skill_policy("notebooklm_list_notebooks")

    assert policy["requires_approved_content"] is False
    assert policy["read_only"] is True


def test_build_execution_intent_defaults_long_running_video_to_async():
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
    snapshot = session_repo.save_approved_content(
        approved_content_id="ac_1",
        session_id="session-1",
        revision_id="rev_1",
        source_message_id=None,
        content_hash="hash",
        content_text="Explain the tool in a friendly way",
        created_at="2026-06-03T00:00:00+00:00",
    )
    intent = build_execution_intent(
        session_repo,
        session_id="session-1",
        skill_id="notebooklm_generate_video",
        command_text='notebookTitle="GPT Application Designer"',
        approved_snapshot=snapshot,
        overrides={
            "notebookTitle": "GPT Application Designer",
        },
    )

    assert intent["execution_mode"] == "async"
    assert intent["mapped_input"]["waitForCompletion"] is False


def test_build_execution_intent_keeps_sync_for_non_long_running_generation():
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
    snapshot = session_repo.save_approved_content(
        approved_content_id="ac_1",
        session_id="session-1",
        revision_id="rev_1",
        source_message_id=None,
        content_hash="hash",
        content_text="Explain the tool in a friendly way",
        created_at="2026-06-03T00:00:00+00:00",
    )
    intent = build_execution_intent(
        session_repo,
        session_id="session-1",
        skill_id="notebooklm_generate_report",
        command_text='notebookTitle="GPT Application Designer"',
        approved_snapshot=snapshot,
        overrides={
            "notebookTitle": "GPT Application Designer",
        },
    )

    assert intent["execution_mode"] == "sync"
    assert "waitForCompletion" not in intent["mapped_input"]
