from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from ragenius_app_skeleton.backend.app.chat_repos import ChatRepo, SessionRepo
from ragenius_app_skeleton.backend.app.main import app
import ragenius_app_skeleton.backend.app.main as app_main


def _install_session(monkeypatch):
    root = Path(tempfile.gettempdir()) / "ragenius_app_tests" / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / "runtime_state.db"
    session_repo = SessionRepo(db_path=db_path)
    monkeypatch.setattr(app_main, "session_repo", session_repo)
    monkeypatch.setattr(app_main, "chat_repo", ChatRepo(db_path=db_path))
    session_repo.get_or_create(
        "session_1",
        collection_id="app_1",
        user_id="user_1",
        title=None,
        config_version=1,
        adapter_version=1,
        template_version=1,
    )


def test_session_artifact_handlers_proxy_bytes_and_delete(monkeypatch):
    _install_session(monkeypatch)
    calls = []

    class FakeExecutionClient:
        def get_artifact_file(self, **kwargs):
            calls.append(("get", kwargs))
            return {
                "ok": True,
                "content": b"trusted bytes",
                "content_type": "text/markdown",
                "content_disposition": 'inline; filename="report.md"',
            }

        def delete_artifact(self, **kwargs):
            calls.append(("delete", kwargs))
            return {"deleted": True, "artifact_id": kwargs["artifact_id"]}

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)

    preview = client.get(
        "/sessions/session_1/artifacts/artifact_1/preview",
        params={"app_id": "app_1", "user_id": "user_1"},
    )
    deleted = client.delete(
        "/sessions/session_1/artifacts/artifact_1",
        params={"app_id": "app_1", "user_id": "user_1"},
    )

    assert preview.status_code == 200
    assert preview.content == b"trusted bytes"
    assert deleted.json() == {"deleted": True, "artifact_id": "artifact_1"}
    assert calls == [
        ("get", {
            "app_id": "app_1",
            "session_id": "session_1",
            "artifact_id": "artifact_1",
            "preview": True,
        }),
        ("delete", {
            "app_id": "app_1",
            "session_id": "session_1",
            "artifact_id": "artifact_1",
        }),
    ]


def test_session_scope_is_checked_before_artifact_proxy(monkeypatch):
    _install_session(monkeypatch)

    class FakeExecutionClient:
        def get_artifact_file(self, **_kwargs):
            raise AssertionError("execution subsystem must not be called for wrong user scope")

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    response = TestClient(app).get(
        "/sessions/session_1/artifacts/artifact_1/file",
        params={"app_id": "app_1", "user_id": "wrong_user"},
    )
    assert response.status_code == 404
