from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import main as app_main
from backend.app.chat_repos import SessionRepo
from backend.app.main import app


class FakeExecutionClient:
    def __init__(self) -> None:
        self.import_calls = 0

    def import_session_upload(self, **_kwargs):
        self.import_calls += 1
        return {
            "artifact": {
                "artifact_id": "artifact-1",
                "artifact_type": "session_upload",
                "display_name": "notes.txt",
                "mime_type": "text/plain",
                "size_bytes": 5,
                "status": "ready",
            },
            "reused_existing_artifact": self.import_calls > 1,
        }


def setup_runtime(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("RAGENIUS_APP_UPLOADS_DIR", str(tmp_path / "uploads"))
    repo = SessionRepo(db_path=tmp_path / "state.db")
    repo.get_or_create(
        "session-1", collection_id="app-1", user_id="user-1",
        config_version=1, adapter_version=1, template_version=1,
    )
    execution = FakeExecutionClient()
    monkeypatch.setattr(app_main, "session_repo", repo)
    monkeypatch.setattr(app_main, "execution_client", execution)
    return repo, execution, TestClient(app)


def test_unified_upload_and_retry_are_idempotent_and_path_safe(tmp_path, monkeypatch):
    _, execution, client = setup_runtime(tmp_path, monkeypatch)
    response = client.post(
        "/sessions/session-1/artifacts/uploads",
        data={
            "app_id": "app-1", "user_id": "user-1",
            "upload_operation_id": "upload-op-1", "analysis_mode": "none",
        },
        files={"file": ("notes.txt", b"notes", "text/plain")},
    )
    retry = client.post(
        "/sessions/session-1/artifacts/uploads/upload-op-1/retry",
        params={"app_id": "app-1", "user_id": "user-1"},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "ready"
    assert response.json()["artifact"]["artifact_id"] == "artifact-1"
    assert "file_path" not in str(response.json())
    assert retry.status_code == 200
    assert retry.json()["artifact"]["artifact_id"] == "artifact-1"
    assert execution.import_calls == 1


def test_unified_upload_validates_scope_mode_and_operation_identity(tmp_path, monkeypatch):
    _, _, client = setup_runtime(tmp_path, monkeypatch)
    wrong_scope = client.post(
        "/sessions/session-1/artifacts/uploads",
        data={
            "app_id": "app-1", "user_id": "other-user",
            "upload_operation_id": "upload-op-1", "analysis_mode": "none",
        },
        files={"file": ("notes.txt", b"notes", "text/plain")},
    )
    invalid_mode = client.post(
        "/sessions/session-1/artifacts/uploads",
        data={
            "app_id": "app-1", "user_id": "user-1",
            "upload_operation_id": "upload-op-2", "analysis_mode": "unsafe",
        },
        files={"file": ("notes.txt", b"notes", "text/plain")},
    )

    assert wrong_scope.status_code == 404
    assert invalid_mode.status_code == 422


def test_normal_query_upload_returns_analysis_result(tmp_path, monkeypatch):
    _, _, client = setup_runtime(tmp_path, monkeypatch)
    monkeypatch.setattr(app_main, "_load_builder_context", lambda _app_id: {"config_json": {}})
    monkeypatch.setattr(
        app_main,
        "_analyze_canonical_upload",
        lambda operation, **_kwargs: {
            "session_id": operation["session_id"],
            "content": "Upload analyzed.",
            "retrieval_summary": {"turn_input_type": "session_upload"},
        },
    )

    response = client.post(
        "/sessions/session-1/artifacts/uploads",
        data={
            "app_id": "app-1", "user_id": "user-1",
            "upload_operation_id": "upload-op-analysis", "analysis_mode": "normal_query",
        },
        files={"file": ("notes.txt", b"notes", "text/plain")},
    )

    assert response.status_code == 201
    assert response.json()["analysis_result"]["content"] == "Upload analyzed."


def test_legacy_duplicate_report_is_scoped_and_read_only(tmp_path, monkeypatch):
    repo, _, client = setup_runtime(tmp_path, monkeypatch)
    repo.add_upload(
        "session-1", filename="first.txt", mime_type="text/plain",
        content=b"same", text_content="same",
    )
    repo.add_upload(
        "session-1", filename="second.txt", mime_type="text/plain",
        content=b"same", text_content="same",
    )

    response = client.get(
        "/sessions/session-1/uploads/duplicate-report",
        params={"app_id": "app-1", "user_id": "user-1"},
    )
    wrong_scope = client.get(
        "/sessions/session-1/uploads/duplicate-report",
        params={"app_id": "app-1", "user_id": "other-user"},
    )

    assert response.status_code == 200
    assert response.json()["duplicate_bytes"] == 4
    assert len(repo.list_uploads("session-1")) == 2
    assert wrong_scope.status_code == 404


def test_delete_preserves_artifact_in_use_conflict(tmp_path, monkeypatch):
    _, _, client = setup_runtime(tmp_path, monkeypatch)

    class InUseExecutionClient(FakeExecutionClient):
        def delete_artifact(self, **_kwargs):
            return {
                "_http_status": 409,
                "error": {
                    "code": "ARTIFACT_IN_USE",
                    "message": "Artifact is in use by an active execution.",
                },
            }

    monkeypatch.setattr(app_main, "execution_client", InUseExecutionClient())
    response = client.delete(
        "/sessions/session-1/artifacts/artifact-1",
        params={"app_id": "app-1", "user_id": "user-1"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ARTIFACT_IN_USE"
