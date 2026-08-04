from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from ragenius_app_skeleton.backend.app.chat_repos import ChatRepo, SessionRepo
from ragenius_app_skeleton.backend.app.main import app
import ragenius_app_skeleton.backend.app.main as app_main


def _install_temp_repos(monkeypatch):
    root = Path(tempfile.gettempdir()) / "ragenius_agent_skill_inventory_tests" / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    db_path = root / "runtime_state.db"
    session_repo = SessionRepo(db_path=db_path)
    chat_repo = ChatRepo(db_path=db_path)
    monkeypatch.setattr(app_main, "session_repo", session_repo)
    monkeypatch.setattr(app_main, "chat_repo", chat_repo)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    return session_repo


def test_inventory_requires_exact_session_scope_and_allowlists_public_fields(monkeypatch):
    _install_temp_repos(monkeypatch)
    captured = {}

    class FakeExecutionClient:
        def get_agent_skill_inventory(self, **kwargs):
            captured.update(kwargs)
            return {
                "inventory_revision": "builder-1:42:sha256:opaque",
                "projection_status": "active",
                "items": [
                    {
                        "agent_skill_id": "agent-skill-1",
                        "approved_fingerprint": "sha256:v1:abc",
                        "availability": "available",
                        "backend": "codex_cli",
                        "description": "Use approved research instructions.",
                        "display_name": "Research Papers",
                        "provider_skill_name": "research-paper-finder",
                        "protected_locator_ref": "must-not-leak",
                        "provider_metadata": {"path": "C:\\private\\SKILL.md"},
                    }
                ],
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)

    response = client.get(
        "/sessions/session-1/exec/agent-skills",
        params={"app_id": "app-1", "user_id": "user-1", "backend": "codex_cli"},
    )
    wrong_user = client.get(
        "/sessions/session-1/exec/agent-skills",
        params={"app_id": "app-1", "user_id": "other", "backend": "codex_cli"},
    )

    assert response.status_code == 200
    assert captured == {"app_id": "app-1", "backend": "codex_cli"}
    assert response.json()["items"] == [
        {
            "agent_skill_id": "agent-skill-1",
            "approved_fingerprint": "sha256:v1:abc",
            "availability": "available",
            "backend": "codex_cli",
            "description": "Use approved research instructions.",
            "display_name": "Research Papers",
            "provider_skill_name": "research-paper-finder",
        }
    ]
    assert wrong_user.status_code == 404


def test_inventory_validates_backend_and_preserves_unavailable_projection(monkeypatch):
    _install_temp_repos(monkeypatch)

    class FakeExecutionClient:
        def get_agent_skill_inventory(self, **_kwargs):
            return {
                "inventory_revision": None,
                "items": [],
                "projection_status": "unavailable",
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)

    unavailable = client.get(
        "/sessions/session-1/exec/agent-skills",
        params={"app_id": "app-1", "user_id": "user-1", "backend": "openclaw_cli"},
    )
    invalid = client.get(
        "/sessions/session-1/exec/agent-skills",
        params={"app_id": "app-1", "user_id": "user-1", "backend": "shell"},
    )

    assert unavailable.status_code == 200
    assert unavailable.json() == {
        "inventory_revision": None,
        "items": [],
        "projection_status": "unavailable",
    }
    assert invalid.status_code == 422
