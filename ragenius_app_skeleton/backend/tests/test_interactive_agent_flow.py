from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ragenius_app_skeleton.backend.app.chat_repos import SessionRepo
from ragenius_app_skeleton.backend.app.main import app
import ragenius_app_skeleton.backend.app.main as app_main


def _session(monkeypatch, tmp_path: Path) -> SessionRepo:
    repo = SessionRepo(db_path=tmp_path / "runtime_state.db")
    repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    monkeypatch.setattr(app_main, "session_repo", repo)
    return repo


def test_codex_approval_then_clarification_then_completion_survives_refresh(monkeypatch, tmp_path):
    repo = _session(monkeypatch, tmp_path)

    class FakeExecutionClient:
        stage = "approval"

        def get_agent_interactions(self, execution_id, **_scope):
            if self.stage == "completed":
                return {"execution_id": execution_id, "items": []}
            interaction_type = self.stage
            return {
                "execution_id": execution_id,
                "items": [{
                    "interaction_id": f"interaction_{interaction_type}",
                    "type": interaction_type,
                    "state": "pending",
                    "version": 1,
                    "sequence": 1 if interaction_type == "approval" else 2,
                    "prompt": "Approve once?" if interaction_type == "approval" else "Which title?",
                    "options": [],
                    "allows_free_text": interaction_type == "clarification",
                    "expires_at": "2099-01-01T00:00:00Z",
                }],
            }

        def get_agent_events(self, execution_id, **_scope):
            sequence = 1 if self.stage == "approval" else 2 if self.stage == "clarification" else 3
            return {"execution_id": execution_id, "items": [], "next_after_sequence": sequence}

        def respond_agent_interaction(self, execution_id, interaction_id, **values):
            if self.stage == "approval":
                assert values["response"] == {"kind": "approval", "decision": "allow_once"}
                self.stage = "clarification"
            else:
                assert values["response"] == {"kind": "clarification", "text": "Study Notes"}
                self.stage = "completed"
            return {"execution_id": execution_id, "interaction_id": interaction_id, "outcome": "applied"}

    execution_client = FakeExecutionClient()
    monkeypatch.setattr(app_main, "execution_client", execution_client)
    client = TestClient(app)
    scope = {"app_id": "app-1", "user_id": "user-1"}
    base = "/sessions/session-1/executions/execution-1"

    approval = client.get(f"{base}/interactions", params=scope)
    assert approval.status_code == 200
    assert approval.json()["items"][0]["type"] == "approval"
    approved = client.post(
        f"{base}/interactions/interaction_approval/responses",
        json={
            **scope,
            "expected_version": 1,
            "idempotency_key": "approval-response",
            "response": {"kind": "approval", "decision": "allow_once"},
        },
    )
    assert approved.status_code == 200

    # A fresh client represents an app refresh while the execution is waiting.
    refreshed = TestClient(app).get(f"{base}/interactions", params=scope)
    assert refreshed.json()["items"][0]["type"] == "clarification"
    clarified = client.post(
        f"{base}/interactions/interaction_clarification/responses",
        json={
            **scope,
            "expected_version": 1,
            "idempotency_key": "clarification-response",
            "response": {"kind": "clarification", "text": "Study Notes"},
        },
    )
    assert clarified.status_code == 200
    assert client.get(f"{base}/interactions", params=scope).json()["items"] == []
    lane = repo.get_runtime_state("session-1")["session_lane_state"]["execution_lane"]
    assert lane["latest_interaction_id"] == "interaction_clarification"
    assert "prompt" not in lane


def test_openclaw_waiting_execution_can_be_cancelled(monkeypatch, tmp_path):
    repo = _session(monkeypatch, tmp_path)

    class FakeExecutionClient:
        def cancel_agent_execution(self, execution_id, **scope):
            assert scope == {"app_id": "app-1", "session_id": "session-1"}
            return {"execution_id": execution_id, "cancelled": True, "status": "cancelled"}

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    response = TestClient(app).post(
        "/sessions/session-1/executions/execution-openclaw/cancel",
        json={"app_id": "app-1", "user_id": "user-1"},
    )

    assert response.status_code == 200
    assert response.json()["cancelled"] is True
    lane = repo.get_runtime_state("session-1")["session_lane_state"]["execution_lane"]
    assert lane["latest_execution_status"] == "cancelled"


def test_openclaw_chat_follow_up_is_scoped_and_redacts_provider_refs(monkeypatch, tmp_path):
    _session(monkeypatch, tmp_path)

    class FakeExecutionClient:
        def get_agent_chat_session(self, execution_id, **scope):
            assert scope == {"app_id": "app-1", "session_id": "session-1"}
            return {
                "execution_id": execution_id,
                "state": "ready_for_follow_up",
                "session_version": 2,
                "provider_session_ref": "must-not-leak",
                "turns": [],
            }

        def submit_agent_follow_up(self, execution_id, **values):
            assert values == {
                "app_id": "app-1", "session_id": "session-1",
                "expected_session_version": 2,
                "idempotency_key": "follow-up-1", "kind": "reply",
                "text": "Use title two.",
            }
            return {"execution_id": execution_id, "outcome": "accepted"}

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    base = "/sessions/session-1/executions/execution-openclaw"
    scope = {"app_id": "app-1", "user_id": "user-1"}
    session = client.get(f"{base}/chat-session", params=scope)
    assert session.status_code == 200
    assert "provider_session_ref" not in session.json()

    response = client.post(
        f"{base}/follow-ups",
        json={
            **scope,
            "expected_session_version": 2,
            "idempotency_key": "follow-up-1",
            "kind": "reply",
            "text": "Use title two.",
        },
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == "accepted"


def test_openclaw_chat_follow_up_rejects_wrong_user_before_provider_contact(monkeypatch, tmp_path):
    _session(monkeypatch, tmp_path)

    class FakeExecutionClient:
        def submit_agent_follow_up(self, *_args, **_values):
            raise AssertionError("provider must not be contacted")

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    response = TestClient(app).post(
        "/sessions/session-1/executions/execution-openclaw/follow-ups",
        json={
            "app_id": "app-1", "user_id": "another-user",
            "expected_session_version": 2,
            "idempotency_key": "follow-up-1", "kind": "continue",
        },
    )
    assert response.status_code == 404
