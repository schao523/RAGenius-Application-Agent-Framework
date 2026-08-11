from __future__ import annotations

import io
from pathlib import Path

import pytest

from backend.app.chat_repos import SessionRepo


def make_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SessionRepo:
    monkeypatch.setenv("RAGENIUS_APP_UPLOADS_DIR", str(tmp_path / "uploads"))
    repo = SessionRepo(db_path=tmp_path / "state.db")
    repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    return repo


def create_operation(repo: SessionRepo, operation_id: str = "upload-op-1") -> dict:
    return repo.add_upload_stream(
        "session-1",
        filename="notes.txt",
        mime_type="text/plain; charset=utf-8",
        source=io.BytesIO(b"notes"),
        max_bytes=100,
        app_id="app-1",
        user_id="user-1",
        upload_operation_id=operation_id,
        staging_expires_at="2026-08-12T00:00:00Z",
    )


def test_upload_operation_is_unique_and_exact_scoped(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, monkeypatch)
    created = create_operation(repo)

    found = repo.get_upload_operation(
        app_id="app-1", session_id="session-1", user_id="user-1",
        upload_operation_id="upload-op-1",
    )
    wrong_user = repo.get_upload_operation(
        app_id="app-1", session_id="session-1", user_id="other-user",
        upload_operation_id="upload-op-1",
    )

    assert found["id"] == created["id"]
    assert found["status"] == "staged"
    assert found["normalized_mime_type"] == "text/plain"
    assert wrong_user is None
    with pytest.raises(ValueError, match="already exists"):
        create_operation(repo)


def test_upload_operation_tracks_ready_and_failed_lifecycle(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, monkeypatch)
    create_operation(repo)

    ready = repo.update_upload_operation(
        app_id="app-1", session_id="session-1", user_id="user-1",
        upload_operation_id="upload-op-1", status="ready",
        artifact_id="artifact-1", error_code=None, retryable=False,
    )
    assert ready["artifact_id"] == "artifact-1"
    assert ready["status"] == "ready"
    assert ready["retryable"] is False

    failed = repo.update_upload_operation(
        app_id="app-1", session_id="session-1", user_id="user-1",
        upload_operation_id="upload-op-1", status="failed",
        artifact_id=None, error_code="EXECUTION_SUBSYSTEM_UNAVAILABLE", retryable=True,
    )
    assert failed["error_code"] == "EXECUTION_SUBSYSTEM_UNAVAILABLE"
    assert failed["retryable"] is True


def test_expired_and_deleted_operations_remove_only_scoped_staging(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, monkeypatch)
    operation = create_operation(repo)
    staging_path = Path(operation["file_path"])

    expired = repo.list_expired_upload_operations("2026-08-13T00:00:00Z")
    assert [item["upload_operation_id"] for item in expired] == ["upload-op-1"]

    assert repo.delete_upload_operation(
        app_id="app-1", session_id="session-1", user_id="user-1",
        upload_operation_id="upload-op-1",
    ) is True
    assert not staging_path.exists()
    deleted = repo.get_upload_operation(
        app_id="app-1", session_id="session-1", user_id="user-1",
        upload_operation_id="upload-op-1",
    )
    assert deleted["status"] == "deleted"
    assert deleted["retryable"] is False
