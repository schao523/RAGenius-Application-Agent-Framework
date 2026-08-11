from __future__ import annotations

import io
from pathlib import Path

import pytest

from backend.app.artifact_upload_service import ArtifactUploadService
from backend.app.chat_repos import SessionRepo


class FakeExecutionClient:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def import_session_upload(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def make_service(tmp_path: Path, monkeypatch, responses: list[dict]):
    monkeypatch.setenv("RAGENIUS_APP_UPLOADS_DIR", str(tmp_path / "uploads"))
    repo = SessionRepo(db_path=tmp_path / "state.db")
    repo.get_or_create(
        "session-1", collection_id="app-1", user_id="user-1",
        config_version=1, adapter_version=1, template_version=1,
    )
    client = FakeExecutionClient(responses)
    return repo, client, ArtifactUploadService(repo, client, max_bytes=100)


def ready_response(artifact_id: str = "artifact-1", reused: bool = False) -> dict:
    return {
        "reused_existing_artifact": reused,
        "artifact": {
            "artifact_id": artifact_id,
            "artifact_type": "session_upload",
            "display_name": "notes.txt",
            "mime_type": "text/plain",
            "size_bytes": 5,
            "content_hash": "sha256:test",
            "status": "ready",
        },
    }


def test_upload_imports_once_and_removes_staging_bytes(tmp_path, monkeypatch):
    repo, client, service = make_service(tmp_path, monkeypatch, [ready_response()])

    result = service.upload(
        app_id="app-1", session_id="session-1", user_id="user-1",
        upload_operation_id="upload-op-1", filename="notes.txt",
        mime_type="text/plain", source=io.BytesIO(b"notes"),
    )

    assert result["status"] == "ready"
    assert result["artifact"]["artifact_id"] == "artifact-1"
    assert result["reused_existing_artifact"] is False
    assert len(client.calls) == 1
    operation = repo.get_upload_operation(
        app_id="app-1", session_id="session-1", user_id="user-1",
        upload_operation_id="upload-op-1",
    )
    assert operation["status"] == "ready"
    assert not Path(operation["file_path"]).exists()


def test_upload_returns_analysis_before_removing_staging_bytes(tmp_path, monkeypatch):
    repo, _, service = make_service(tmp_path, monkeypatch, [ready_response()])
    observed = {}

    def analyze(operation):
        staged = Path(operation["file_path"])
        observed["bytes"] = staged.read_bytes()
        return {"content": "Upload analyzed.", "retrieval_summary": {"turn_input_type": "session_upload"}}

    result = service.upload(
        app_id="app-1", session_id="session-1", user_id="user-1",
        upload_operation_id="upload-op-analysis", filename="notes.txt",
        mime_type="text/plain", source=io.BytesIO(b"notes"), analysis=analyze,
    )

    assert observed["bytes"] == b"notes"
    assert result["analysis_result"]["content"] == "Upload analyzed."


def test_failed_import_retries_existing_staging_without_browser_bytes(tmp_path, monkeypatch):
    repo, client, service = make_service(tmp_path, monkeypatch, [
        {"error": {"code": "EXECUTION_SUBSYSTEM_UNAVAILABLE", "message": "offline"}},
        ready_response(reused=True),
    ])

    failed = service.upload(
        app_id="app-1", session_id="session-1", user_id="user-1",
        upload_operation_id="upload-op-1", filename="notes.txt",
        mime_type="text/plain", source=io.BytesIO(b"notes"),
    )
    retried = service.retry(
        app_id="app-1", session_id="session-1", user_id="user-1",
        upload_operation_id="upload-op-1",
    )

    assert failed == {
        "upload_operation_id": "upload-op-1", "status": "failed",
        "artifact": None, "reused_existing_artifact": False,
        "error_code": "EXECUTION_SUBSYSTEM_UNAVAILABLE", "retryable": True,
    }
    assert retried["status"] == "ready"
    assert retried["reused_existing_artifact"] is True
    assert len(client.calls) == 2


def test_ready_operation_is_idempotent_and_cleanup_expires_failed_staging(tmp_path, monkeypatch):
    repo, client, service = make_service(tmp_path, monkeypatch, [ready_response()])
    first = service.upload(
        app_id="app-1", session_id="session-1", user_id="user-1",
        upload_operation_id="upload-op-1", filename="notes.txt",
        mime_type="text/plain", source=io.BytesIO(b"notes"),
    )
    second = service.retry(
        app_id="app-1", session_id="session-1", user_id="user-1",
        upload_operation_id="upload-op-1",
    )

    assert second["artifact"]["artifact_id"] == first["artifact"]["artifact_id"]
    assert len(client.calls) == 1

    repo2, _, service2 = make_service(tmp_path / "expired", monkeypatch, [
        {"error": {"code": "EXECUTION_SUBSYSTEM_UNAVAILABLE", "message": "offline"}}
    ])
    service2.upload(
        app_id="app-1", session_id="session-1", user_id="user-1",
        upload_operation_id="upload-op-expired", filename="notes.txt",
        mime_type="text/plain", source=io.BytesIO(b"notes"),
        now="2026-08-10T00:00:00Z", retention_hours=1,
    )
    assert service2.cleanup_expired("2026-08-11T00:00:00Z") == 1
    expired = repo2.get_upload_operation(
        app_id="app-1", session_id="session-1", user_id="user-1",
        upload_operation_id="upload-op-expired",
    )
    assert expired["status"] == "deleted"
    assert expired["retryable"] is False
