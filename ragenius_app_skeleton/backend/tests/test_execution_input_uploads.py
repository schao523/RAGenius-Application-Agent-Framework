from __future__ import annotations

import hashlib
import io
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.chat_repos import SessionRepo
from backend.app import main as app_main
from backend.app.main import app


class ChunkedReader(io.BytesIO):
    def __init__(self, value: bytes, chunk_size: int = 3) -> None:
        super().__init__(value)
        self.chunk_size = chunk_size
        self.requested_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.requested_sizes.append(size)
        return super().read(min(size, self.chunk_size) if size >= 0 else self.chunk_size)


class FailingReader(io.BytesIO):
    def read(self, size: int = -1) -> bytes:
        value = super().read(min(size, 3))
        if not value:
            raise OSError("simulated upload failure")
        return value


def make_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SessionRepo:
    monkeypatch.setenv("RAGENIUS_APP_UPLOADS_DIR", str(tmp_path / "uploads"))
    return SessionRepo(db_path=tmp_path / "state.db")


def test_add_upload_stream_hashes_chunks_and_normalizes_basename(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, monkeypatch)
    source = ChunkedReader(b"video-bytes")

    upload = repo.add_upload_stream(
        "session-1",
        filename="../unsafe/video.mp4",
        mime_type="video/mp4",
        source=source,
        max_bytes=100,
    )

    assert upload["filename"] == "video.mp4"
    assert upload["size_bytes"] == 11
    assert upload["sha256"] == f"sha256:{hashlib.sha256(b'video-bytes').hexdigest()}"
    assert Path(upload["file_path"]).read_bytes() == b"video-bytes"
    assert source.requested_sizes and all(size == 1024 * 1024 for size in source.requested_sizes)


def test_add_upload_stream_enforces_limit_and_removes_partial_files(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="maximum"):
        repo.add_upload_stream(
            "session-1",
            filename="large.mp4",
            mime_type="video/mp4",
            source=ChunkedReader(b"too-large"),
            max_bytes=4,
        )
    assert list((tmp_path / "uploads").rglob("*")) in ([], [tmp_path / "uploads" / "session-1"])

    with pytest.raises(OSError, match="simulated"):
        repo.add_upload_stream(
            "session-1",
            filename="broken.mp4",
            mime_type="video/mp4",
            source=FailingReader(b"partial"),
            max_bytes=100,
        )
    assert not list((tmp_path / "uploads" / "session-1").glob("*.tmp"))


def test_upload_lookup_is_session_scoped_and_backfills_missing_hash(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, monkeypatch)
    upload = repo.add_upload(
        "session-1",
        filename="notes.txt",
        mime_type="text/plain",
        content=b"notes",
        text_content="notes",
    )
    assert repo.get_upload("other-session", upload["id"]) is None
    assert repo.get_upload("session-1", upload["id"])["sha256"].startswith("sha256:")

    with sqlite3.connect(tmp_path / "state.db") as connection:
        connection.execute("UPDATE uploads SET sha256 = NULL WHERE id = ?", (upload["id"],))
        connection.commit()
    backfilled = repo.ensure_upload_sha256("session-1", upload["id"])
    assert backfilled["sha256"] == f"sha256:{hashlib.sha256(b'notes').hexdigest()}"


def test_get_upload_rejects_symlink_file(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, monkeypatch)
    upload = repo.add_upload(
        "session-1",
        filename="notes.txt",
        mime_type="text/plain",
        content=b"notes",
        text_content="notes",
    )
    target = Path(upload["file_path"])
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"outside")
    target.unlink()
    try:
        target.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"Symlink creation unavailable: {exc}")
    assert repo.get_upload("session-1", upload["id"]) is None


def test_composer_upload_prepares_without_running_chat_pipeline(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, monkeypatch)
    repo.get_or_create("session-1", collection_id="app-1", user_id="user-1", config_version=1, adapter_version=1, template_version=1)
    calls = []

    class FakeExecutionClient:
        def import_session_upload(self, **kwargs):
            calls.append(kwargs)
            return {
                "preparation_status": "ready",
                "reused_existing_artifact": False,
                "artifact": {
                    "artifact_id": "artifact-video",
                    "artifact_type": "session_upload",
                    "display_name": "video.mp4",
                    "status": "ready",
                },
            }

    monkeypatch.setattr(app_main, "session_repo", repo)
    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    monkeypatch.setattr(app_main, "run_chat_pipeline", lambda *_args, **_kwargs: pytest.fail("chat pipeline called"))
    response = TestClient(app).post(
        "/sessions/session-1/execution-inputs",
        data={"app_id": "app-1", "user_id": "user-1"},
        files={"file": ("video.mp4", b"video-bytes", "video/mp4")},
    )
    assert response.status_code == 201
    assert response.json()["artifact"]["artifact_id"] == "artifact-video"
    assert calls[0]["sha256"].startswith("sha256:")
    assert "file_path" not in response.json()["upload"]


def test_prepare_existing_upload_enforces_scope_and_is_idempotent(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, monkeypatch)
    repo.get_or_create("session-1", collection_id="app-1", user_id="user-1", config_version=1, adapter_version=1, template_version=1)
    upload = repo.add_upload("session-1", filename="notes.txt", mime_type="text/plain", content=b"notes", text_content="notes")

    class FakeExecutionClient:
        def import_session_upload(self, **_kwargs):
            return {
                "preparation_status": "ready",
                "reused_existing_artifact": True,
                "artifact": {"artifact_id": "artifact-1", "artifact_type": "session_upload", "status": "ready"},
            }

    monkeypatch.setattr(app_main, "session_repo", repo)
    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    denied = client.post(
        f"/sessions/session-1/uploads/{upload['id']}/prepare-for-execution",
        params={"app_id": "app-1", "user_id": "other-user"},
    )
    ready = client.post(
        f"/sessions/session-1/uploads/{upload['id']}/prepare-for-execution",
        params={"app_id": "app-1", "user_id": "user-1"},
    )
    assert denied.status_code == 404
    assert ready.status_code == 200
    assert ready.json()["reused_existing_artifact"] is True


def test_session_upload_http_responses_do_not_expose_server_paths(tmp_path, monkeypatch):
    repo = make_repo(tmp_path, monkeypatch)
    repo.get_or_create(
        "session-1", collection_id="app-1", user_id="user-1",
        config_version=1, adapter_version=1, template_version=1,
    )
    repo.add_upload(
        "session-1", filename="notes.txt", mime_type="text/plain",
        content=b"private notes", text_content="private notes",
    )
    monkeypatch.setattr(app_main, "session_repo", repo)
    monkeypatch.setattr(app_main, "_load_builder_readonly_context", lambda _app_id: {"config_json": {}})
    client = TestClient(app)

    messages = client.get(
        "/sessions/session-1/messages",
        params={"app_id": "app-1", "user_id": "user-1"},
    )
    uploads = client.get(
        "/sessions/session-1/uploads",
        params={"app_id": "app-1", "user_id": "user-1"},
    )

    assert messages.status_code == 200
    assert uploads.status_code == 200
    for upload in [*messages.json()["session_uploads"], *uploads.json()["uploads"]]:
        assert upload["filename"] == "notes.txt"
        assert upload["sha256"].startswith("sha256:")
        assert "file_path" not in upload
        assert "text_content" not in upload
