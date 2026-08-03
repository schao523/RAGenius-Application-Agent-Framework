from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from ragenius_app_skeleton.backend.app.chat_repos import ChatRepo, SessionRepo
from ragenius_app_skeleton.backend.app.exec_router import parse_exec_turn
from ragenius_app_skeleton.backend.app.main import app
import ragenius_app_skeleton.backend.app.main as app_main


def _builder_context() -> dict:
    return {
        "planner_mode": "legacy",
        "instruction_understanding_mode": "hybrid_shadow",
        "config_json": {},
        "adapter_json": {"domain": "general"},
        "template_registry": {},
    }


def _db_path() -> Path:
    root = Path(tempfile.gettempdir()) / "ragenius_app_tests" / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root / "runtime_state.db"


def _install_temp_repos(monkeypatch):
    db_path = _db_path()
    session_repo = SessionRepo(db_path=db_path)
    chat_repo = ChatRepo(db_path=db_path)
    monkeypatch.setattr(app_main, "session_repo", session_repo)
    monkeypatch.setattr(app_main, "chat_repo", chat_repo)
    monkeypatch.setattr(app_main, "_load_builder_context", lambda _app_id: _builder_context())
    return session_repo, chat_repo


def test_parse_exec_openclaw_turn():
    decision = parse_exec_turn('@exec openclaw "Reply with OK."')

    assert decision.is_exec_turn is True
    assert decision.command == "openclaw"
    assert decision.agent_backend == "openclaw_cli"
    assert decision.agent_query == "Reply with OK."


def test_parse_exec_async_openclaw_turn():
    decision = parse_exec_turn('@exec async openclaw "Reply with OK."')

    assert decision.command == "openclaw"
    assert decision.execution_mode == "async"
    assert decision.agent_backend == "openclaw_cli"


def test_parse_exec_openclaw_missing_request():
    decision = parse_exec_turn("@exec openclaw")

    assert decision.is_exec_turn is True
    assert decision.command == "openclaw"
    assert "Missing OpenClaw request" in str(decision.error)


def test_normal_turn_without_exec_prefix_uses_existing_chat_pipeline(monkeypatch):
    _install_temp_repos(monkeypatch)
    calls = []

    def fake_run_chat_pipeline(*args, **kwargs):
        state = args[0]
        calls.append(state["user_query"])
        return {
            "content": "normal-path",
            "workflow_progress": {},
            "session_execution_state": {},
        }

    monkeypatch.setattr(app_main, "run_chat_pipeline", fake_run_chat_pipeline)
    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": "Revise the introduction to be friendlier.",
        },
    )
    assert response.status_code == 200
    assert calls == ["Revise the introduction to be friendlier."]
    assert response.json()["content"] == "normal-path"
    assert response.headers["content-type"].startswith("application/json; charset=utf-8")


def test_exec_skill_turn_submits_execution_intent(monkeypatch):
    session_repo, chat_repo = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    chat_repo.append("session-1", "assistant", "Explain the tool in a friendly way")

    class FakeExecutionClient:
        def submit_skill(self, **kwargs):
            return {
                "status": "completed",
                "execution_id": "execution_123",
                "result": {"status": "completed"},
            }

        def get_execution_status(self, execution_id: str, **_scope):
            return {"execution_id": execution_id, "status": "completed"}

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    approve_response = client.post(
        "/sessions/session-1/approved-content",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "use_latest_assistant_message": True,
        },
    )
    assert approve_response.status_code == 200
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": '@exec skill notebooklm_generate_video notebookTitle="GPT Application Designer" waitForCompletion=false',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_override"]["command"] == "skill"
    assert payload["execution_override"]["approved_revision_id"].startswith("rev_")
    assert payload["execution_override"]["execution_intent"]["mapped_input"]["notebookTitle"] == "GPT Application Designer"
    assert payload["session_lane_state"]["content_lane"]["latest_approved_content_id"].startswith("ac_")
    assert payload["session_lane_state"]["execution_lane"]["latest_execution_id"] == "execution_123"
    assert "Using approved revision" in payload["content"]
    assert session_repo.get_latest_approved_content("session-1") is not None


def test_exec_tool_turn_resolves_runtime_skill_and_submits_execution(monkeypatch):
    session_repo, chat_repo = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    chat_repo.append("session-1", "assistant", "Explain the tool in a friendly way")
    captured = {}

    class FakeExecutionClient:
        def get_tool_inventory(self):
            return {
                "items": [
                    {
                        "tool_id": "adapter.notebooklm.generate_video",
                        "exec_capable": True,
                        "enabled": True,
                    }
                ]
            }

        def get_skill_inventory(self):
            return {
                "items": [
                    {
                        "skill_id": "notebooklm_generate_video",
                        "required_tools": ["adapter.notebooklm.generate_video"],
                        "required_permissions": ["external_api.write"],
                        "confirmation_mode": "require_confirmation",
                    }
                ]
            }

        def submit_skill(self, **kwargs):
            captured.update(kwargs)
            return {
                "status": "completed",
                "execution_id": "execution_tool_123",
                "result": {"status": "completed"},
            }

        def get_execution_status(self, execution_id: str, **_scope):
            return {"execution_id": execution_id, "status": "completed"}

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    approve_response = client.post(
        "/sessions/session-1/approved-content",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "use_latest_assistant_message": True,
        },
    )
    assert approve_response.status_code == 200
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": '@exec tool adapter.notebooklm.generate_video notebookTitle="GPT Application Designer" waitForCompletion=false',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert captured["skill_id"] == "notebooklm_generate_video"
    assert payload["execution_override"]["command"] == "tool"
    assert payload["execution_override"]["target_id"] == "adapter.notebooklm.generate_video"
    assert payload["execution_override"]["skill_id"] == "notebooklm_generate_video"
    assert payload["execution_override"]["execution_intent"]["mapped_input"]["notebookTitle"] == "GPT Application Designer"


def test_exec_tool_turn_resolves_selected_artifacts_before_submit(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    captured = {}

    class FakeExecutionClient:
        def get_tool_inventory(self):
            return {
                "items": [
                    {
                        "tool_id": "mcp.gmail.create_draft_with_attachments",
                        "name": "Gmail Create Draft With Attachments",
                        "exec_capable": True,
                        "enabled": True,
                        "artifact_picker": {
                            "enabled": True,
                            "field_name": "artifactIds",
                            "required_consumption_mode": "binary_payload",
                        },
                    }
                ]
            }

        def get_skill_inventory(self):
            return {
                "items": [
                    {
                        "skill_id": "gmail_create_draft_with_attachments",
                        "required_tools": ["mcp.gmail.create_draft_with_attachments"],
                        "required_permissions": ["external_api.write"],
                        "confirmation_mode": "require_confirmation",
                    }
                ]
            }

        def get_artifact_inventory(self, **kwargs):
            captured["artifact_query"] = kwargs
            return {
                "items": [
                    {
                        "artifact_id": "artifact_pdf",
                        "app_id": "app-1",
                        "session_id": "session-1",
                        "display_name": "Execution Summary.pdf",
                        "artifact_type": "google_drive_export",
                        "mime_type": "application/pdf",
                        "file_path": "storage/artifacts/app-1/export.pdf",
                        "path": "storage/artifacts/app-1/artifact_pdf.json",
                        "status": "ready",
                        "consumption": {
                            "default_mode": "binary_payload",
                            "supported_modes": ["binary_payload", "file_backed", "metadata_only"],
                        },
                    }
                ]
            }

        def submit_skill(self, **kwargs):
            captured["submit"] = kwargs
            return {
                "status": "completed",
                "execution_id": "execution_gmail_123",
                "result": {"status": "completed"},
            }

        def get_execution_status(self, execution_id: str, **_scope):
            return {"execution_id": execution_id, "status": "completed"}

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": (
                '@exec tool mcp.gmail.create_draft_with_attachments '
                'to="alice@example.com" subject="Review" body="See attached" '
                "artifactIds='[\"artifact_pdf\"]'"
            ),
        },
    )

    assert response.status_code == 200
    submitted_input = captured["submit"]["input_payload"]
    assert submitted_input["artifactIds"] == ["artifact_pdf"]
    assert submitted_input["artifactRefs"][0]["artifact_id"] == "artifact_pdf"
    assert submitted_input["artifactRefs"][0]["field_name"] == "artifactIds"
    assert submitted_input["artifactRefs"][0]["display_name"] == "Execution Summary.pdf"
    assert submitted_input["artifactRefs"][0]["consumption"]["resolved_mode"] == "binary_payload"
    assert submitted_input["artifact_reuse"]["fields"]["artifactIds"] == ["artifact_pdf"]
    assert captured["artifact_query"] == {
        "app_id": "app-1",
        "session_id": "session-1",
        "artifact_type": None,
        "eligible_for": None,
        "status": "ready",
    }
    payload = response.json()
    mapped_input = payload["execution_override"]["execution_intent"]["mapped_input"]
    assert mapped_input["artifactRefs"][0]["artifact_id"] == "artifact_pdf"


def test_exec_tool_turn_rejects_artifact_outside_current_session(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )

    class FakeExecutionClient:
        def get_tool_inventory(self):
            return {
                "items": [
                    {
                        "tool_id": "mcp.gmail.create_draft_with_attachments",
                        "exec_capable": True,
                        "enabled": True,
                        "artifact_picker": {
                            "enabled": True,
                            "field_name": "artifactIds",
                            "required_consumption_mode": "binary_payload",
                        },
                    }
                ]
            }

        def get_skill_inventory(self):
            return {
                "items": [
                    {
                        "skill_id": "gmail_create_draft_with_attachments",
                        "required_tools": ["mcp.gmail.create_draft_with_attachments"],
                    }
                ]
            }

        def get_artifact_inventory(self, **kwargs):
            return {"items": []}

        def submit_skill(self, **kwargs):
            raise AssertionError("submit_skill should not be called for an unresolved artifact")

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": (
                '@exec tool mcp.gmail.create_draft_with_attachments '
                'to="alice@example.com" subject="Review" body="See attached" '
                "artifactIds='[\"artifact_missing\"]'"
            ),
        },
    )

    assert response.status_code == 400
    assert "Artifact `artifact_missing` was not found in this session." in response.json()["detail"]


def test_exec_tool_turn_maps_file_backed_artifact_field_to_file_path(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    captured = {}

    class FakeExecutionClient:
        def get_tool_inventory(self):
            return {
                "items": [
                    {
                        "tool_id": "adapter.notebooklm.add_source_file",
                        "exec_capable": True,
                        "enabled": True,
                        "artifact_picker": {
                            "enabled": True,
                            "field_name": "filePath",
                            "required_consumption_mode": "file_backed",
                        },
                    }
                ]
            }

        def get_skill_inventory(self):
            return {
                "items": [
                    {
                        "skill_id": "notebooklm_add_source_file",
                        "required_tools": ["adapter.notebooklm.add_source_file"],
                    }
                ]
            }

        def get_artifact_inventory(self, **kwargs):
            return {
                "items": [
                    {
                        "artifact_id": "artifact_export",
                        "app_id": "app-1",
                        "session_id": "session-1",
                        "display_name": "Chat Export.md",
                        "artifact_type": "chat_export",
                        "mime_type": "text/markdown",
                        "file_path": "storage/artifacts/app-1/chat_export/chat-export.md",
                        "status": "ready",
                        "consumption": {
                            "default_mode": "file_backed",
                            "supported_modes": ["file_backed", "inline_text", "metadata_only"],
                        },
                    }
                ]
            }

        def submit_skill(self, **kwargs):
            captured["submit"] = kwargs
            return {
                "status": "completed",
                "execution_id": "execution_file_123",
                "result": {"status": "completed"},
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": (
                '@exec tool adapter.notebooklm.add_source_file notebookTitle="GPT Application Designer" '
                'filePath="artifact_export"'
            ),
        },
    )

    assert response.status_code == 200
    submitted_input = captured["submit"]["input_payload"]
    assert submitted_input["filePath"] == "artifact_export"
    assert submitted_input["artifactRefs"][0]["artifact_id"] == "artifact_export"
    assert "file_path" not in submitted_input["artifactRefs"][0]
    assert submitted_input["artifactRefs"][0]["consumption"]["resolved_mode"] == "file_backed"
    assert submitted_input["artifact_reuse"]["fields"]["filePath"] == ["artifact_export"]


def test_exec_tool_turn_accepts_shorthand_tool_alias(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    captured = {}

    class FakeExecutionClient:
        def get_tool_inventory(self):
            return {
                "items": [
                    {
                        "tool_id": "adapter.notebooklm.list_notebooks",
                        "name": "NotebookLM List Notebooks",
                        "exec_capable": True,
                        "enabled": True,
                    }
                ]
            }

        def get_skill_inventory(self):
            return {
                "items": [
                    {
                        "skill_id": "notebooklm_list_notebooks",
                        "required_tools": ["adapter.notebooklm.list_notebooks"],
                        "required_permissions": ["external_api.read"],
                        "confirmation_mode": "no_confirmation",
                    }
                ]
            }

        def submit_skill(self, **kwargs):
            captured.update(kwargs)
            return {
                "status": "completed",
                "execution_id": "execution_list_123",
                "result": {"items": []},
            }

        def get_execution_status(self, execution_id: str, **_scope):
            return {"execution_id": execution_id, "status": "completed"}

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": "@exec tool notebooklm_list_notebooks",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert captured["skill_id"] == "notebooklm_list_notebooks"
    assert payload["execution_override"]["command"] == "tool"
    assert payload["execution_override"]["target_id"] == "adapter.notebooklm.list_notebooks"


def test_exec_codex_turn_submits_agent_execution(monkeypatch):
    session_repo, chat_repo = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    chat_repo.append("session-1", "assistant", "Approved content candidate")
    captured = {}

    class FakeExecutionClient:
        def submit_agent(self, **kwargs):
            captured.update(kwargs)
            return {
                "status": "completed",
                "execution_id": "execution_codex_123",
                "result": {
                    "backend": "codex_cli",
                    "final_message": "Codex agent request was accepted by the Phase 1 stub backend.",
                    "user_summary": {
                        "status": "completed",
                        "title": "NotebookLM question answered",
                        "subtitle": "GPT Application Designer",
                        "preview": "Learning GPT design offers transformative advantages.",
                    },
                },
            }

        def get_execution_status(self, execution_id: str, **_scope):
            return {"execution_id": execution_id, "status": "completed"}

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    approve_response = client.post(
        "/sessions/session-1/approved-content",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "use_latest_assistant_message": True,
        },
    )
    assert approve_response.status_code == 200
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": '@exec codex use notebooklm "Generate a quiz from the approved content."',
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert captured["agent_backend"] == "codex_cli"
    assert captured["agent_query"] == "Generate a quiz from the approved content."
    assert captured["agent_skill_hint"] == "notebooklm"
    assert captured["approved_content_id"].startswith("ac_")
    assert payload["execution_override"]["command"] == "codex"
    assert payload["execution_override"]["target_id"] == "codex_cli"
    assert payload["execution_override"]["agent_skill_hint"] == "notebooklm"
    assert payload["session_lane_state"]["execution_lane"]["latest_execution_id"] == "execution_codex_123"
    assert payload["session_lane_state"]["execution_lane"]["latest_execution_request_skill_id"] == "codex_cli:notebooklm"
    assert payload["content"] == (
        "NotebookLM question answered (GPT Application Designer) "
        "Learning GPT design offers transformative advantages."
    )


def test_exec_openclaw_turn_submits_agent_execution(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    captured = {}

    class FakeExecutionClient:
        def submit_agent(self, **kwargs):
            captured.update(kwargs)
            return {
                "status": "completed",
                "execution_id": "execution_openclaw_123",
                "result": {
                    "backend": "openclaw_cli",
                    "summary": "OpenClaw completed.",
                },
            }

        def get_execution_status(self, execution_id: str, **_scope):
            return {"execution_id": execution_id, "status": "completed"}

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": '@exec openclaw "Reply with OK."',
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert captured["agent_backend"] == "openclaw_cli"
    assert captured["agent_query"] == "Reply with OK."
    assert payload["execution_override"]["command"] == "openclaw"
    assert payload["execution_override"]["target_id"] == "openclaw_cli"
    assert payload["execution_override"]["agent_backend"] == "openclaw_cli"
    assert payload["session_lane_state"]["execution_lane"]["latest_execution_id"] == "execution_openclaw_123"
    assert payload["session_lane_state"]["execution_lane"]["latest_agent_backend"] == "openclaw_cli"
    assert payload["session_lane_state"]["execution_lane"]["latest_execution_request_skill_id"] == "openclaw_cli"


def test_exec_openclaw_turn_passes_structured_artifact_refs_and_expected_outputs(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    captured = {}

    class FakeExecutionClient:
        def submit_agent(self, **kwargs):
            captured.update(kwargs)
            return {
                "status": "completed",
                "execution_id": "execution_openclaw_artifact_123",
                "result": {
                    "backend": "openclaw_cli",
                    "summary": "OpenClaw completed.",
                },
            }

        def get_execution_status(self, execution_id: str, **_scope):
            return {"execution_id": execution_id, "status": "completed"}

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": '@exec openclaw "Create a reusable study note."',
            "execution_request": {
                "artifact_refs": [
                    {
                        "artifact_id": "artifact_chat_1",
                        "role": "source",
                        "reuse_mode": "inline_text",
                        "display_name": "Study notes.md",
                        "mime_type": "text/markdown",
                    }
                ],
                "expected_outputs": [
                    {
                        "output_id": "agent_answer",
                        "display_name": "agent-answer.md",
                        "media_type": "text/markdown",
                        "required": True,
                        "persist_as_artifact": True,
                    }
                ],
            },
        },
    )

    assert response.status_code == 200
    assert captured["agent_backend"] == "openclaw_cli"
    assert captured["agent_query"] == "Create a reusable study note."
    assert captured["artifact_refs"][0]["artifact_id"] == "artifact_chat_1"
    assert captured["artifact_refs"][0]["reuse_mode"] == "inline_text"
    assert captured["expected_outputs"][0]["output_id"] == "agent_answer"
    assert captured["expected_outputs"][0]["persist_as_artifact"] is True


def test_exec_openclaw_turn_enriches_persisted_agent_output_artifacts(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    captured_inventory = {}

    class FakeExecutionClient:
        def submit_agent(self, **kwargs):
            return {
                "status": "completed",
                "execution_id": "execution_openclaw_artifact_123",
                "result": {
                    "backend": "openclaw_cli",
                    "summary": "OpenClaw completed.",
                    "artifacts": [
                        {
                            "artifact_id": "artifact_agent_1",
                            "artifact_type": "agent_output",
                            "display_name": "Study Guide.md",
                            "mime_type": "text/markdown",
                            "verified": True,
                        }
                    ],
                },
            }

        def get_artifact_inventory(self, **kwargs):
            captured_inventory.update(kwargs)
            return {
                "items": [
                    {
                        "artifact_id": "artifact_agent_1",
                        "artifact_type": "agent_output",
                        "display_name": "Study Guide.md",
                        "mime_type": "text/markdown",
                        "status": "ready",
                        "summary": "Agent output from OpenClaw.",
                        "path": "storage/artifacts/app-1/agent_output/artifact_agent_1.json",
                        "file_path": "storage/artifacts/app-1/agent_output/artifact_agent_1-Study-Guide.md",
                        "consumption": {
                            "default_mode": "file_backed",
                            "supported_modes": ["file_backed", "inline_text", "metadata_only"],
                        },
                        "eligible_consumers": ["execution_composer", "agent_context"],
                    }
                ]
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": '@exec openclaw "Create Study Guide.md from the selected notes."',
        },
    )

    assert response.status_code == 200
    payload = response.json()
    artifacts = payload["execution_override"]["submit_result"]["result"]["artifacts"]
    assert captured_inventory["app_id"] == "app-1"
    assert captured_inventory["session_id"] == "session-1"
    assert artifacts[0]["artifact_id"] == "artifact_agent_1"
    assert artifacts[0]["display_name"] == "Study Guide.md"
    assert artifacts[0]["routes"]["open"] == "/sessions/session-1/artifacts/artifact_agent_1/file?app_id=app-1&user_id=user-1"
    assert artifacts[0]["routes"]["preview"] == "/sessions/session-1/artifacts/artifact_agent_1/preview?app_id=app-1&user_id=user-1"
    assert artifacts[0]["capabilities"]["can_reuse"] is True
    history = app_main.chat_repo.history("session-1")
    assistant_turn = history[-1]
    stored_artifacts = assistant_turn["retrievalSummary"]["execution_submit_result"]["result"]["artifacts"]
    assert stored_artifacts[0]["routes"]["open"] == artifacts[0]["routes"]["open"]


def test_exec_openclaw_turn_derives_expected_output_filename_from_query(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    captured = {}

    class FakeExecutionClient:
        def submit_agent(self, **kwargs):
            captured.update(kwargs)
            return {
                "status": "completed",
                "execution_id": "execution_openclaw_named_output_123",
                "result": {"backend": "openclaw_cli", "summary": "OpenClaw completed."},
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": '@exec openclaw "Read the selected artifact and create Study Questions.md"',
            "execution_request": {
                "artifact_refs": [
                    {
                        "artifact_id": "artifact_chat_1",
                        "role": "source",
                        "reuse_mode": "inline_text",
                    }
                ]
            },
        },
    )

    assert response.status_code == 200
    assert captured["expected_outputs"][0]["output_id"] == "agent_answer"
    assert captured["expected_outputs"][0]["display_name"] == "Study Questions.md"
    assert captured["expected_outputs"][0]["media_type"] == "text/markdown"
    assert captured["expected_outputs"][0]["required"] is True
    assert captured["expected_outputs"][0]["persist_as_artifact"] is True


def test_exec_codex_turn_surfaces_confirmation_required_summary(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )

    class FakeExecutionClient:
        def submit_agent(self, **kwargs):
            return {
                "status": "pending_confirmation",
                "execution_id": "execution_codex_pending_123",
                "result": {
                    "required_confirmation": True,
                    "tool_id": "codex_cli",
                    "permission_scope": "agent.external_write",
                    "risk_class": "agent_external_write",
                    "workspace_access": "none",
                    "network_access": "allowlisted",
                    "confirmation_id": "confirmation_codex_123",
                    "confirmation_expires_at": "2026-07-24T00:15:00.000Z",
                    "confirmation_state": "pending",
                },
            }

        def get_execution_status(self, execution_id: str, **_scope):
            return {"execution_id": execution_id, "status": "pending_confirmation"}

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": '@exec codex use notebooklm "Generate a study video for Micah 2."',
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_override"]["command"] == "codex"
    assert payload["session_lane_state"]["execution_lane"]["latest_execution_id"] == "execution_codex_pending_123"
    assert (
        payload["session_lane_state"]["execution_lane"]["latest_confirmation_id"]
        == "confirmation_codex_123"
    )
    assert (
        payload["session_lane_state"]["execution_lane"]["latest_confirmation_state"]
        == "pending"
    )
    assert "requires confirmation" in payload["content"].lower()
    assert "`external write`" in payload["content"].lower()


def test_exec_codex_turn_surfaces_blocked_policy_summary(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )

    class FakeExecutionClient:
        def submit_agent(self, **kwargs):
            return {
                "error": {
                    "code": "PERMISSION_BLOCKED",
                    "message": "Codex agent execution is blocked by policy.",
                    "recoverable": False,
                    "suggested_action": "Use a non-destructive request or adjust the agent policy.",
                    "details": {
                        "permission_scope": "agent.destructive",
                    },
                },
                "_http_status": 403,
            }

        def get_execution_status(self, execution_id: str, **_scope):
            return {"execution_id": execution_id, "status": "failed"}

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": '@exec codex "Delete the NotebookLM notebook."',
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_override"]["command"] == "codex"
    assert "blocked by policy" in payload["content"].lower()
    assert "destructive" in payload["content"].lower()


def test_export_session_messages_returns_export_file_metadata(monkeypatch):
    session_repo, chat_repo = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    chat_repo.append("session-1", "assistant", "Export me")
    captured = {}

    class FakeExecutionClient:
        def submit_skill(self, **kwargs):
            captured.update(kwargs)
            return {
                "status": "completed",
                "execution_id": "execution_export_123",
                "result": {
                    "artifact_id": "artifact_123",
                    "artifact_type": "chat_export",
                    "path": "D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/storage/artifacts/app-1/chat_export/artifact_123.json",
                    "file_path": "D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/storage/artifacts/app-1/chat_export/artifact_123-session-1-chat-export.md",
                },
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    history = chat_repo.history("session-1")
    message_id = history[-1]["id"]

    response = client.post(
        "/sessions/session-1/exports",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "message_ids": [message_id],
            "format": "md",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert captured["skill_id"] == "save_chat_export_artifact"
    assert payload["export_artifact"]["artifact_id"] == "artifact_123"
    assert payload["export_artifact"]["file_path"].endswith(".md")
    assert payload["export_artifact"]["metadata_path"].endswith(".json")


def test_exec_skills_inventory_returns_builder_bound_skills_and_user_facing_runtime_workflows(monkeypatch):
    _install_temp_repos(monkeypatch)
    captured_visibility = []

    class FakeExecutionClient:
        def get_skill_inventory(self, visibility=None):
            captured_visibility.append(visibility)
            return {
                "items": [
                    {
                        "skill_id": "video_director_skill",
                        "name": "Video Director Skill",
                        "enabled": True,
                        "exec_capable": True,
                        "inventory_visibility": "user_skill",
                        "workflow_kind": "multi_step_workflow",
                        "required_tools": ["content_transform_adapter"],
                        "required_permissions": ["external_api.write"],
                        "input_schema": {"type": "object", "properties": {"brief": {"type": "string"}}},
                        "output_schema": {"type": "object", "properties": {}},
                    },
                    {
                        "skill_id": "notebooklm_generate_video",
                        "name": "NotebookLM Generate Video",
                        "enabled": True,
                        "exec_capable": True,
                        "inventory_visibility": "internal_wrapper",
                        "required_tools": ["adapter.notebooklm.generate_video"],
                        "required_permissions": ["external_api.write"],
                        "input_schema": {"type": "object", "properties": {}},
                        "output_schema": {"type": "object", "properties": {}},
                    }
                ]
            }

    class FakeBuilderStore:
        def list_app_skill_bindings(self, app_id: str):
            assert app_id == "app-1"
            return [
                {
                    "skill_id": "notebooklm-video-generator",
                    "skill_version": "1.0",
                    "permission_mode": "require_confirmation",
                    "enabled": True,
                }
            ]

        def get_published_skill_definition(self, *, skill_id: str, version: str | None = None):
            assert skill_id == "notebooklm-video-generator"
            assert version == "1.0"
            return {
                "skill_id": "notebooklm-video-generator",
                "name": "NotebookLM Video Generator",
                "version": "1.0",
                "description": "Published builder skill.",
                "enabled": True,
                "required_tools": ["adapter.notebooklm.generate_video"],
                "required_permissions": ["external_api.write"],
                "input_schema": {"type": "object", "properties": {"instructions": {"type": "string"}}},
                "output_schema": {"type": "object", "properties": {}},
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    monkeypatch.setattr(app_main, "get_builder_store", lambda: FakeBuilderStore())
    client = TestClient(app)

    response = client.get("/exec/skills?app_id=app-1")

    assert response.status_code == 200
    items = response.json()["items"]
    skill_ids = {item["skill_id"] for item in items}
    assert captured_visibility == ["user"]


def test_exec_tools_inventory_preserves_artifact_picker_hints(monkeypatch):
    _install_temp_repos(monkeypatch)

    class FakeExecutionClient:
        def get_tool_inventory(self):
            return {
                "items": [
                    {
                        "tool_id": "mcp.gmail.create_draft_with_attachments",
                        "name": "Gmail Create Draft With Attachments",
                        "exec_capable": True,
                        "enabled": True,
                        "artifact_picker": {
                            "enabled": True,
                            "field_name": "artifactIds",
                            "selection_mode": "multiple",
                            "allowed_artifact_types": ["google_drive_export", "chat_export"],
                            "allowed_mime_types": ["application/pdf", "text/plain"],
                            "eligible_for": "attachments",
                            "accepted_artifact_types": ["google_drive_export", "chat_export"],
                            "required_consumption_mode": "binary_payload",
                            "max_artifact_count": 5,
                        },
                    }
                ]
            }

        def get_skill_inventory(self, visibility=None):
            return {
                "items": [
                    {
                        "skill_id": "gmail_create_draft_with_attachments",
                        "required_tools": ["mcp.gmail.create_draft_with_attachments"],
                        "required_permissions": ["external_api.write", "artifact.read"],
                        "confirmation_mode": "require_confirmation",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "to": {"type": "string"},
                                "subject": {"type": "string"},
                                "body": {"type": "string"},
                                "artifactIds": {"type": "array", "items": {"type": "string"}},
                            },
                            "required": ["to", "subject", "body", "artifactIds"],
                        },
                        "output_schema": {"type": "object", "properties": {}},
                    }
                ]
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)

    response = client.get("/exec/tools")

    assert response.status_code == 200
    payload = response.json()
    item = payload["items"][0]
    assert item["exec_binding_skill_id"] == "gmail_create_draft_with_attachments"
    assert item["artifact_picker"]["enabled"] is True
    assert item["artifact_picker"]["field_name"] == "artifactIds"
    assert item["artifact_picker"]["allowed_artifact_types"] == ["google_drive_export", "chat_export"]
    assert item["artifact_picker"]["accepted_artifact_types"] == ["google_drive_export", "chat_export"]
    assert item["artifact_picker"]["required_consumption_mode"] == "binary_payload"
    assert item["artifact_picker"]["max_artifact_count"] == 5


def test_exec_tools_inventory_preserves_non_artifact_ids_picker_field(monkeypatch):
    _install_temp_repos(monkeypatch)

    class FakeExecutionClient:
        def get_tool_inventory(self):
            return {
                "items": [
                    {
                        "tool_id": "adapter.notebooklm.add_source_file",
                        "name": "NotebookLM Add Source File",
                        "exec_capable": True,
                        "enabled": True,
                        "artifact_picker": {
                            "enabled": True,
                            "field_name": "filePath",
                            "selection_mode": "single",
                            "allowed_artifact_types": ["chat_export"],
                            "required_consumption_mode": "file_backed",
                        },
                    }
                ]
            }

        def get_skill_inventory(self, visibility=None):
            return {
                "items": [
                    {
                        "skill_id": "notebooklm_add_source_file",
                        "required_tools": ["adapter.notebooklm.add_source_file"],
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "notebookTitle": {"type": "string"},
                                "filePath": {"type": "string"},
                            },
                            "required": ["notebookTitle", "filePath"],
                        },
                    }
                ]
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)

    response = client.get("/exec/tools")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["exec_binding_skill_id"] == "notebooklm_add_source_file"
    assert item["artifact_picker"]["enabled"] is True
    assert item["artifact_picker"]["field_name"] == "filePath"
    assert item["artifact_picker"]["selection_mode"] == "single"
    assert item["artifact_picker"]["accepted_artifact_types"] == ["chat_export"]
    assert item["artifact_picker"]["required_consumption_mode"] == "file_backed"


def test_list_session_artifacts_returns_execution_subsystem_inventory(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    captured = {}

    class FakeExecutionClient:
        def get_artifact_inventory(self, **kwargs):
            captured.update(kwargs)
            return {
                "items": [
                    {
                        "artifact_id": "artifact_123",
                        "artifact_type": "google_drive_export",
                        "display_name": "Execution Summary.pdf",
                        "mime_type": "application/pdf",
                        "status": "ready",
                        "summary": "Google Drive export: Execution Summary.pdf",
                        "path": "storage/artifacts/app-1/google_drive_export/artifact_123.json",
                        "file_path": "storage/artifacts/app-1/google_drive_export/artifact_123-Execution-Summary.pdf",
                        "consumption": {
                            "default_mode": "binary_payload",
                            "supported_modes": ["binary_payload", "file_backed", "metadata_only"],
                        },
                        "eligible_consumers": ["gmail_attachments", "export"],
                    }
                ]
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)

    response = client.get(
        "/sessions/session-1/artifacts",
        params={"app_id": "app-1", "user_id": "user-1", "eligible_for": "attachments"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert captured == {
        "app_id": "app-1",
        "session_id": "session-1",
        "artifact_type": None,
        "eligible_for": "attachments",
        "status": "ready",
    }
    assert payload["items"][0]["artifact_id"] == "artifact_123"
    assert payload["items"][0]["session_id"] == "session-1"
    assert payload["items"][0]["app_id"] == "app-1"
    assert payload["items"][0]["artifact_type_label"] == "Drive Export"
    assert "file_path" not in payload["items"][0]
    assert "path" not in payload["items"][0]
    assert payload["items"][0]["preview_url"] == "/sessions/session-1/artifacts/artifact_123/preview?app_id=app-1&user_id=user-1"
    assert payload["items"][0]["routes"]["preview"] == "/sessions/session-1/artifacts/artifact_123/preview?app_id=app-1&user_id=user-1"
    assert payload["items"][0]["consumption"]["default_mode"] == "binary_payload"
    assert payload["items"][0]["consumption"]["supported_modes"] == [
        "binary_payload",
        "file_backed",
        "metadata_only",
    ]
    assert payload["items"][0]["open_url"] == "/sessions/session-1/artifacts/artifact_123/file?app_id=app-1&user_id=user-1"
    assert payload["items"][0]["routes"]["open"] == "/sessions/session-1/artifacts/artifact_123/file?app_id=app-1&user_id=user-1"
    assert payload["items"][0]["capabilities"] == {
        "can_open": True,
        "can_preview": True,
        "can_delete": True,
        "can_reuse": True,
    }
    assert payload["items"][0]["file_info"] == {
        "has_file": True,
        "extension": ".pdf",
        "size_bytes": None,
    }
    assert payload["items"][0]["provenance"]["source_kind"] is None
    assert payload["items"][0]["provenance"]["source_session_id"] == "session-1"
    assert payload["items"][0]["debug"]["artifact_id"] == "artifact_123"


def test_list_session_artifacts_degrades_when_execution_subsystem_is_unavailable(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )

    class FakeExecutionClient:
        def get_artifact_inventory(self, **kwargs):
            return {
                "error": {
                    "code": "EXECUTION_SUBSYSTEM_UNAVAILABLE",
                    "message": "Execution subsystem is unavailable.",
                },
                "_transport_error": True,
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)

    response = client.get(
        "/sessions/session-1/artifacts",
        params={"app_id": "app-1", "user_id": "user-1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["warning"] == "Execution subsystem is unavailable."


def test_list_session_artifacts_rejects_missing_session_before_inventory_call(monkeypatch):
    _install_temp_repos(monkeypatch)

    class FakeExecutionClient:
        def get_artifact_inventory(self, **kwargs):
            raise AssertionError("inventory must not be called for a missing session")

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)

    response = client.get(
        "/sessions/missing-session/artifacts",
        params={"app_id": "app-1", "user_id": "user-1"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found."


def test_list_session_artifacts_rejects_mismatched_scope_before_inventory_call(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )

    class FakeExecutionClient:
        def get_artifact_inventory(self, **kwargs):
            raise AssertionError("inventory must not be called for a mismatched session")

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)

    response = client.get(
        "/sessions/session-1/artifacts",
        params={"app_id": "app-1", "user_id": "other-user"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found."


def test_exec_tools_inventory_degrades_when_execution_subsystem_is_unavailable(monkeypatch):
    _install_temp_repos(monkeypatch)

    class FakeExecutionClient:
        def get_tool_inventory(self):
            return {
                "error": {
                    "code": "EXECUTION_SUBSYSTEM_UNAVAILABLE",
                    "message": "Execution subsystem is unavailable.",
                },
                "_transport_error": True,
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)

    response = client.get("/exec/tools")

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_open_session_artifact_file_proxies_execution_subsystem_bytes(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    captured = {}

    class FakeExecutionClient:
        def get_artifact_file(self, **kwargs):
            captured.update(kwargs)
            return {
                "ok": True,
                "content": b"artifact-content",
                "content_type": "application/pdf",
                "content_disposition": 'attachment; filename="Execution Summary.pdf"',
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)

    response = client.get(
        "/sessions/session-1/artifacts/artifact_123/file",
        params={"app_id": "app-1", "user_id": "user-1"},
    )

    assert response.status_code == 200
    assert response.content == b"artifact-content"
    assert "Execution Summary.pdf" in response.headers.get("content-disposition", "")
    assert captured == {
        "app_id": "app-1",
        "session_id": "session-1",
        "artifact_id": "artifact_123",
        "preview": False,
    }


def test_preview_session_artifact_file_proxies_inline_bytes(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    class FakeExecutionClient:
        def get_artifact_file(self, **kwargs):
            return {
                "ok": True,
                "content": b"# preview",
                "content_type": "text/markdown",
                "content_disposition": 'inline; filename="preview.md"',
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    response = client.get(
        "/sessions/session-1/artifacts/artifact_123/preview",
        params={"app_id": "app-1", "user_id": "user-1"},
    )

    assert response.status_code == 200
    assert response.content == b"# preview"
    assert "inline" in response.headers.get("content-disposition", "")


def test_delete_session_artifact_proxies_scoped_delete(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    captured = {}

    class FakeExecutionClient:
        def delete_artifact(self, **kwargs):
            captured.update(kwargs)
            return {"deleted": True, "artifact_id": "artifact_123"}

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    response = client.delete(
        "/sessions/session-1/artifacts/artifact_123",
        params={"app_id": "app-1", "user_id": "user-1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["deleted"] is True
    assert captured == {
        "app_id": "app-1",
        "session_id": "session-1",
        "artifact_id": "artifact_123",
    }


def test_exec_tools_inventory_returns_only_directly_executable_tools(monkeypatch):
    _install_temp_repos(monkeypatch)

    class FakeExecutionClient:
        def get_tool_inventory(self):
            return {
                "items": [
                    {
                        "tool_id": "adapter.notebooklm.list_notebooks",
                        "name": "NotebookLM List Notebooks",
                        "enabled": True,
                        "exec_capable": True,
                        "input_schema": {"type": "object", "properties": {}},
                    },
                    {
                        "tool_id": "write_file",
                        "name": "Write File",
                        "enabled": True,
                        "exec_capable": True,
                        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
                    },
                ]
            }

        def get_skill_inventory(self):
            return {
                "items": [
                    {
                        "skill_id": "notebooklm_list_notebooks",
                        "name": "NotebookLM List Notebooks",
                        "enabled": True,
                        "exec_capable": True,
                        "required_tools": ["adapter.notebooklm.list_notebooks"],
                        "required_permissions": ["external_api.read"],
                        "input_schema": {"type": "object", "properties": {}},
                        "output_schema": {"type": "object", "properties": {}},
                    }
                ]
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)

    response = client.get("/exec/tools")

    assert response.status_code == 200
    items = response.json()["items"]
    tool_ids = {item["tool_id"] for item in items}
    assert "adapter.notebooklm.list_notebooks" in tool_ids
    assert "write_file" not in tool_ids


def test_exec_tools_inventory_ignores_app_scope(monkeypatch):
    _install_temp_repos(monkeypatch)

    class FakeExecutionClient:
        def get_tool_inventory(self):
            return {
                "items": [
                    {
                        "tool_id": "adapter.notebooklm.list_notebooks",
                        "name": "NotebookLM List Notebooks",
                        "enabled": True,
                        "exec_capable": True,
                        "input_schema": {"type": "object", "properties": {}},
                    },
                    {
                        "tool_id": "write_file",
                        "name": "Write File",
                        "enabled": True,
                        "exec_capable": True,
                        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
                    },
                ]
            }

        def get_skill_inventory(self):
            return {
                "items": [
                    {
                        "skill_id": "notebooklm_list_notebooks",
                        "name": "NotebookLM List Notebooks",
                        "enabled": True,
                        "exec_capable": True,
                        "required_tools": ["adapter.notebooklm.list_notebooks"],
                        "required_permissions": ["external_api.read"],
                        "input_schema": {"type": "object", "properties": {}},
                        "output_schema": {"type": "object", "properties": {}},
                    }
                ]
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)

    unscoped = client.get("/exec/tools")
    scoped = client.get("/exec/tools?app_id=app-1")

    assert unscoped.status_code == 200
    assert scoped.status_code == 200
    assert unscoped.json() == scoped.json()


def test_exec_tools_inventory_inherits_schema_and_description_from_exec_skill(monkeypatch):
    _install_temp_repos(monkeypatch)

    class FakeExecutionClient:
        def get_tool_inventory(self):
            return {
                "items": [
                    {
                        "tool_id": "adapter.notebooklm.generate_report",
                        "name": "NotebookLM Generate Report",
                        "enabled": True,
                        "exec_capable": True,
                        "description": "",
                        "input_schema": {},
                        "output_schema": {},
                    }
                ]
            }

        def get_skill_inventory(self):
            return {
                "items": [
                    {
                        "skill_id": "notebooklm_generate_report",
                        "name": "NotebookLM Generate Report",
                        "description": "Generate a notebook report.",
                        "enabled": True,
                        "exec_capable": True,
                        "required_tools": ["adapter.notebooklm.generate_report"],
                        "required_permissions": ["external_api.write"],
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "notebookTitle": {"type": "string"},
                                "instructions": {"type": "string"},
                                "audience": {"type": "string"},
                            },
                            "required": ["instructions"],
                        },
                        "output_schema": {"type": "object", "properties": {}},
                    }
                ]
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)

    response = client.get("/exec/tools")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["tool_id"] == "adapter.notebooklm.generate_report"
    assert item["description"] == "Generate a notebook report."
    assert item["exec_binding_skill_id"] == "notebooklm_generate_report"
    assert item["input_schema"]["required"] == ["instructions"]
    assert "notebookTitle" in item["input_schema"]["properties"]


def test_exec_tools_inventory_prefers_exec_skill_schema_over_raw_mcp_schema(monkeypatch):
    class FakeExecutionClient:
        def get_tool_inventory(self):
            return {
                "items": [
                    {
                        "tool_id": "mcp.gmail.create_draft",
                        "name": "Gmail Create Draft",
                        "enabled": True,
                        "exec_capable": True,
                        "description": "Raw MCP schema",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "to": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "subject": {"type": "string"},
                                "body": {"type": "string"},
                            },
                            "required": ["to", "subject", "body"],
                        },
                        "output_schema": {"type": "object", "properties": {}},
                    }
                ]
            }

        def get_skill_inventory(self, visibility=None):
            return {
                "items": [
                    {
                        "skill_id": "gmail_create_draft",
                        "name": "Gmail Create Draft",
                        "description": "Create a Gmail draft through the Gmail MCP provider.",
                        "enabled": True,
                        "exec_capable": True,
                        "required_tools": ["mcp.gmail.create_draft"],
                        "required_permissions": ["external_api.write"],
                        "confirmation_mode": "require_confirmation",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "to": {"type": "string"},
                                "subject": {"type": "string"},
                                "body": {"type": "string"},
                            },
                            "required": ["to", "subject", "body"],
                        },
                        "output_schema": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                            },
                        },
                    }
                ]
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)

    response = client.get("/exec/tools")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["tool_id"] == "mcp.gmail.create_draft"
    assert item["exec_binding_skill_id"] == "gmail_create_draft"
    assert item["description"] == "Create a Gmail draft through the Gmail MCP provider."
    assert item["confirmation_mode"] == "require_confirmation"
    assert item["input_schema"]["properties"]["to"]["type"] == "string"


def test_exec_tool_turn_normalizes_gmail_recipient_arrays(monkeypatch):
    session_repo, chat_repo = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    chat_repo.append("session-1", "assistant", "Draft a message")
    captured = {}

    class FakeExecutionClient:
        def get_tool_inventory(self):
            return {
                "items": [
                    {
                        "tool_id": "mcp.gmail.create_draft",
                        "name": "Gmail Create Draft",
                        "enabled": True,
                        "exec_capable": True,
                    }
                ]
            }

        def get_skill_inventory(self, visibility=None):
            return {
                "items": [
                    {
                        "skill_id": "gmail_create_draft",
                        "name": "Gmail Create Draft",
                        "enabled": True,
                        "exec_capable": True,
                        "required_tools": ["mcp.gmail.create_draft"],
                        "required_permissions": ["external_api.write"],
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "to": {"type": "string"},
                                "subject": {"type": "string"},
                                "body": {"type": "string"},
                            },
                            "required": ["to", "subject", "body"],
                        },
                    }
                ]
            }

        def submit_skill(self, **kwargs):
            captured.update(kwargs)
            return {
                "status": "pending_confirmation",
                "execution_id": "execution_gmail_123",
                "result": {"required_confirmation": True},
            }

        def get_execution_status(self, execution_id: str, **_scope):
            return {"execution_id": execution_id, "status": "pending_confirmation"}

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)

    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": '@exec tool mcp.gmail.create_draft to=\'["alice@example.com","bob@example.com"]\' subject="Hello" body="Draft content"',
        },
    )

    assert response.status_code == 200
    assert captured["skill_id"] == "gmail_create_draft"
    assert captured["input_payload"]["to"] == "alice@example.com, bob@example.com"


def test_confirm_session_execution_returns_updated_status(monkeypatch):
    session_repo, chat_repo = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )

    class FakeExecutionClient:
        def get_execution_status(self, execution_id: str, **_scope):
            return {
                "execution_id": execution_id,
                "status": "pending_confirmation",
                "result": {
                    "confirmation_id": "confirmation_123",
                    "confirmation_state": "pending",
                },
            }

        def confirm_execution(self, execution_id: str, **_scope):
            assert execution_id == "execution_123"
            assert _scope["confirmation_id"] == "confirmation_123"
            return {
                "execution_id": execution_id,
                "status": "completed",
                "result": {
                    "id": "draft_123",
                    "status": "draft_created",
                    "artifacts": [
                        {
                            "artifact_id": "artifact_123",
                            "artifact_type": "agent_output",
                            "display_name": "report.md",
                        }
                    ],
                },
            }

        def get_artifact_inventory(self, **_scope):
            return {
                "items": [
                    {
                        "artifact_id": "artifact_123",
                        "artifact_type": "agent_output",
                        "display_name": "report.md",
                        "session_id": "session-1",
                        "app_id": "app-1",
                        "status": "ready",
                        "file_path": __file__,
                    }
                ]
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)

    response = client.post(
        "/sessions/session-1/executions/execution_123/confirm",
        json={
            "app_id": "app-1",
            "user_id": "user-1",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "confirmed and completed" in payload["content"].lower()
    assert payload["execution_override"]["command"] == "confirm"
    assert payload["execution_override"]["execution_id"] == "execution_123"
    assert payload["execution_override"]["status_result"]["status"] == "completed"
    artifact = payload["execution_override"]["status_result"]["result"]["artifacts"][0]
    assert artifact["routes"]["open"].startswith(
        "/sessions/session-1/artifacts/artifact_123/file"
    )
    assert artifact["capabilities"]["can_open"] is True
    persisted = chat_repo.history("session-1")[-1]["retrievalSummary"]
    assert persisted["execution_status_result"]["result"]["artifacts"][0][
        "artifact_id"
    ] == "artifact_123"
    assert payload["session_lane_state"]["execution_lane"]["latest_execution_id"] == "execution_123"


def test_confirm_session_execution_rejects_mismatched_scope_before_confirm(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )

    class FakeExecutionClient:
        def confirm_execution(self, execution_id: str, **_scope):
            raise AssertionError("confirmation must not run for a mismatched session")

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)

    response = client.post(
        "/sessions/session-1/executions/execution_123/confirm",
        json={
            "app_id": "app-1",
            "user_id": "other-user",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Session not found."


def test_export_session_messages_saves_selected_chat_content(monkeypatch):
    session_repo, chat_repo = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    user_message = chat_repo.append("session-1", "user", "What is RAG?")
    assistant_message = chat_repo.append("session-1", "assistant", "RAG stands for retrieval-augmented generation.")
    captured = {}

    class FakeExecutionClient:
        def submit_skill(self, **kwargs):
            captured.update(kwargs)
            return {
                "status": "completed",
                "execution_id": "execution_export_123",
                "result": {
                    "artifact_id": "artifact_123",
                    "artifact_type": "chat_export",
                    "path": "artifacts/chat-export.md",
                    "file_path": "artifacts/chat-export-file.md",
                },
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)

    response = client.post(
        "/sessions/session-1/exports",
        json={
            "app_id": "app-1",
            "user_id": "user-1",
            "message_ids": [user_message["id"], assistant_message["id"]],
            "format": "md",
            "filename": "bible-study",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary_text"] == "Saved 2 selected message(s) as `Chat Export - Bible Study.md`."
    assert captured["skill_id"] == "save_chat_export_artifact"
    assert captured["input_payload"]["name"] == "bible-study.md"
    assert captured["input_payload"]["displayName"] == "Chat Export - Bible Study.md"
    assert "## 1. User" in captured["input_payload"]["content"]
    assert "## 2. Assistant" in captured["input_payload"]["content"]
    assert payload["export_artifact"]["display_name"] == "Chat Export - Bible Study.md"
    assert payload["export_artifact"]["metadata_path"].startswith("D:")
    assert payload["export_artifact"]["file_path"].startswith("D:")


def test_exec_async_video_turn_persists_background_job_state(monkeypatch):
    session_repo, chat_repo = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    chat_repo.append("session-1", "assistant", "Explain the tool in a friendly way")
    captured = {}

    class FakeExecutionClient:
        def submit_skill(self, **kwargs):
            captured.update(kwargs)
            return {
                "status": "completed",
                "execution_id": "execution_async_123",
                "result": {
                    "status": "submitted",
                    "task_id": "task_video_123",
                    "artifact_kind": "video",
                },
            }

        def get_execution_status(self, execution_id: str, **_scope):
            return {"execution_id": execution_id, "status": "completed"}

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    approve_response = client.post(
        "/sessions/session-1/approved-content",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "use_latest_assistant_message": True,
        },
    )
    assert approve_response.status_code == 200

    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": '@exec skill notebooklm_generate_video notebookTitle="GPT Application Designer"',
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert captured["input_payload"]["waitForCompletion"] is False
    assert payload["execution_override"]["execution_intent"]["execution_mode"] == "async"
    assert payload["session_lane_state"]["execution_lane"]["latest_execution_mode"] == "async"
    assert payload["session_lane_state"]["execution_lane"]["latest_async_task_id"] == "task_video_123"
    assert payload["session_lane_state"]["execution_lane"]["latest_async_task_status"] == "submitted"
    assert "background job" in payload["content"].lower()


def test_exec_skill_turn_marks_notebooklm_login_required(monkeypatch):
    session_repo, chat_repo = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    chat_repo.append("session-1", "assistant", "Explain the tool in a friendly way")

    class FakeExecutionClient:
        def submit_skill(self, **kwargs):
            return {
                "status_code": 500,
                "transport_ok": False,
                "body": {
                    "ok": False,
                    "error": {
                        "code": "NOTEBOOKLM_AUTH_REQUIRED",
                        "message": "NotebookLM login is required.",
                        "recoverable": True,
                        "suggested_action": "Run 'python -m notebooklm login' and retry.",
                    },
                },
            }

        def get_execution_status(self, execution_id: str, **_scope):
            return {"execution_id": execution_id, "status": "completed"}

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    approve_response = client.post(
        "/sessions/session-1/approved-content",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "use_latest_assistant_message": True,
        },
    )
    assert approve_response.status_code == 200
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": '@exec skill notebooklm_generate_video notebookTitle="GPT Application Designer"',
        },
    )
    assert response.status_code == 200
    payload = response.json()
    login_requirement = payload["session_lane_state"]["execution_lane"]["latest_login_requirement"]
    assert login_requirement["auth_required"] is True
    assert login_requirement["provider"] == "notebooklm"
    assert login_requirement["login_command"] == "python -m notebooklm login"
    assert payload["session_lane_state"]["execution_lane"]["latest_execution_request_query"].startswith(
        "@exec skill notebooklm_generate_video"
    )
    assert "login to notebooklm" in payload["content"].lower()


def test_exec_skill_without_approved_content_returns_400(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )

    class FakeExecutionClient:
        def submit_skill(self, **kwargs):
            raise AssertionError("submit_skill should not be called when approval is missing")

        def get_execution_status(self, execution_id: str, **_scope):
            return {"execution_id": execution_id, "status": "completed"}

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": '@exec skill notebooklm_generate_video notebookTitle="GPT Application Designer" waitForCompletion=false',
        },
    )
    assert response.status_code == 400
    assert "No approved content is available" in response.json()["detail"]


def test_exec_skill_with_unknown_skill_id_returns_400(monkeypatch):
    _install_temp_repos(monkeypatch)
    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": "@exec skill unknown_skill",
        },
    )

    assert response.status_code == 400
    assert "Unknown exec skill" in response.json()["detail"]


def test_exec_tool_with_unknown_tool_id_returns_400(monkeypatch):
    _install_temp_repos(monkeypatch)

    class FakeExecutionClient:
        def get_tool_inventory(self):
            return {"items": []}

        def get_skill_inventory(self):
            return {"items": []}

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": "@exec tool adapter.notebooklm.unknown",
        },
    )

    assert response.status_code == 400
    assert "Unknown exec tool" in response.json()["detail"]


def test_exec_skill_with_invalid_approved_content_id_returns_400(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )

    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": '@exec skill notebooklm_generate_video approvedContentId="ac_missing" notebookTitle="GPT Application Designer"',
        },
    )

    assert response.status_code == 400
    assert "Approved content `ac_missing` was not found for this session." == response.json()["detail"]


def test_exec_skill_rejects_wrong_session_approved_content_id(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    session_repo.get_or_create(
        "session-2",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    foreign_snapshot = session_repo.save_approved_content(
        approved_content_id="ac_foreign",
        session_id="session-2",
        revision_id="rev_foreign",
        source_message_id=None,
        content_hash="hash",
        content_text="foreign content",
        created_at="2026-06-03T00:00:00+00:00",
    )

    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": f'@exec skill notebooklm_generate_video approvedContentId="{foreign_snapshot["approved_content_id"]}" notebookTitle="GPT Application Designer"',
        },
    )

    assert response.status_code == 400
    assert f'Approved content `{foreign_snapshot["approved_content_id"]}` was not found for this session.' == response.json()["detail"]


def test_exec_status_turn_does_not_invoke_normal_chat_pipeline(monkeypatch):
    _, chat_repo = _install_temp_repos(monkeypatch)

    def fail_run_chat_pipeline(*args, **kwargs):
        raise AssertionError("normal chat pipeline should not be used for @exec status")

    class FakeExecutionClient:
        def submit_skill(self, **kwargs):
            raise AssertionError("submit_skill should not be called for @exec status")

        def get_execution_status(self, execution_id: str, **_scope):
            return {
                "execution_id": execution_id,
                "status": "completed",
                "result": {
                    "artifacts": [
                        {
                            "artifact_id": "artifact_123",
                            "artifact_type": "agent_output",
                            "display_name": "report.md",
                        }
                    ]
                },
            }

        def get_artifact_inventory(self, **_scope):
            return {
                "items": [
                    {
                        "artifact_id": "artifact_123",
                        "artifact_type": "agent_output",
                        "display_name": "report.md",
                        "session_id": "session-1",
                        "app_id": "app-1",
                        "status": "ready",
                        "file_path": __file__,
                    }
                ]
            }

    monkeypatch.setattr(app_main, "run_chat_pipeline", fail_run_chat_pipeline)
    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": "@exec status execution_123",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_override"]["command"] == "status"
    assert payload["execution_override"]["status_result"]["execution_id"] == "execution_123"
    artifact = payload["execution_override"]["status_result"]["result"]["artifacts"][0]
    assert artifact["routes"]["open"].startswith(
        "/sessions/session-1/artifacts/artifact_123/file"
    )
    assert payload["content"] == "Execution status for `execution_123` is completed."
    persisted = chat_repo.history("session-1")[-1]["retrievalSummary"]
    assert persisted["execution_status_result"]["result"]["artifacts"][0][
        "artifact_id"
    ] == "artifact_123"


def test_exec_status_turn_surfaces_execution_lookup_error(monkeypatch):
    _install_temp_repos(monkeypatch)

    def fail_run_chat_pipeline(*args, **kwargs):
        raise AssertionError("normal chat pipeline should not be used for @exec status")

    class FakeExecutionClient:
        def submit_skill(self, **kwargs):
            raise AssertionError("submit_skill should not be called for @exec status")

        def get_execution_status(self, execution_id: str, **_scope):
            return {
                "error": {
                    "code": "EXECUTION_NOT_FOUND",
                    "message": "Execution record was not found.",
                },
                "_http_status": 404,
            }

    monkeypatch.setattr(app_main, "run_chat_pipeline", fail_run_chat_pipeline)
    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": "@exec status execution_123",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["content"] == (
        "Execution status for `execution_123` could not be loaded: Execution record was not found."
    )


def test_exec_status_turn_polls_async_notebooklm_task_without_resubmission(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    session_repo.set_runtime_state(
        "session-1",
        {
            "session_lane_state": {
                "content_lane": {},
                "execution_lane": {
                    "latest_execution_id": "execution_123",
                    "latest_execution_mode": "async",
                    "latest_execution_request_skill_id": "notebooklm_generate_video",
                    "latest_async_task_id": "task_video_123",
                    "latest_async_task_status": "submitted",
                    "latest_execution_result": {
                        "execution_id": "execution_123",
                        "result": {
                            "notebook_id": "nb_1",
                            "artifact_kind": "video",
                            "task_id": "task_video_123",
                            "status": "submitted",
                        },
                    },
                },
            }
        },
    )
    captured = {"poll_calls": 0}

    def fail_run_chat_pipeline(*args, **kwargs):
        raise AssertionError("normal chat pipeline should not be used for @exec status")

    class FakeExecutionClient:
        def submit_skill(self, **kwargs):
            captured["poll_calls"] += 1
            captured["poll_kwargs"] = kwargs
            return {
                "status": "completed",
                "execution_id": "execution_poll_1",
                "result": {
                    "notebook_id": "nb_1",
                    "artifact_kind": "video",
                    "task_id": "task_video_123",
                    "status": "completed",
                },
                "execution_metadata": {
                    "used_fallback": False,
                    "fallback_count": 0,
                    "execution_paths": ["adapter"],
                    "provider_ids": ["notebooklm"],
                    "tool_ids": ["adapter.notebooklm.poll_artifact_task"],
                },
            }

        def get_execution_status(self, execution_id: str, **_scope):
            return {
                "execution_id": execution_id,
                "status": "completed",
                "result": {
                    "notebook_id": "nb_1",
                    "artifact_kind": "video",
                    "task_id": "task_video_123",
                    "status": "submitted",
                },
            }

    monkeypatch.setattr(app_main, "run_chat_pipeline", fail_run_chat_pipeline)
    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": "@exec status execution_123",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert captured["poll_calls"] == 1
    assert captured["poll_kwargs"]["skill_id"] == "notebooklm_poll_artifact_task"
    assert captured["poll_kwargs"]["input_payload"] == {
        "notebookId": "nb_1",
        "taskId": "task_video_123",
        "artifactKind": "video",
    }
    assert payload["session_lane_state"]["execution_lane"]["latest_async_task_status"] == "completed"
    assert payload["execution_override"]["status_result"]["status"] == "completed"
    assert payload["content"] == "Execution status for `execution_123` is completed."


def test_read_only_exec_skill_can_run_without_approved_content(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )

    class FakeExecutionClient:
        def submit_skill(self, **kwargs):
            return {
                "status": "completed",
                "execution_id": "execution_list_1",
                "result": {"items": []},
            }

        def get_execution_status(self, execution_id: str, **_scope):
            return {"execution_id": execution_id, "status": "completed"}

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": "@exec skill notebooklm_list_notebooks",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_override"]["skill_id"] == "notebooklm_list_notebooks"
    assert payload["execution_override"]["approved_content_id"] is None


def test_exec_skill_rejects_missing_required_inputs(monkeypatch):
    session_repo, chat_repo = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    chat_repo.append("session-1", "assistant", "Explain the tool in a friendly way")

    client = TestClient(app)
    approve_response = client.post(
        "/sessions/session-1/approved-content",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "use_latest_assistant_message": True,
        },
    )
    assert approve_response.status_code == 200
    response = client.post(
        "/sessions/session-1/chat",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "user_query": "@exec skill notebooklm_generate_video",
        },
    )

    assert response.status_code == 400
    assert "requires one of: notebookId, notebookTitle" in response.json()["detail"]


def test_create_and_list_approved_content_endpoints(monkeypatch):
    session_repo, chat_repo = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    assistant = chat_repo.append("session-1", "assistant", "Approved endpoint content")

    class FakeExecutionClient:
        def submit_skill(self, **kwargs):
            return {
                "status": "completed",
                "result": {
                    "artifact_id": "artifact_reviewed_1",
                    "artifact_type": "chat_export",
                    "display_name": kwargs["input_payload"]["displayName"],
                    "path": "storage/artifacts/app-1/chat_export/artifact_reviewed_1.json",
                    "file_path": "storage/artifacts/app-1/chat_export/artifact_reviewed_1-reviewed.md",
                    "reviewed": True,
                    "reviewed_at": kwargs["input_payload"]["reviewedAt"],
                    "reviewed_by": kwargs["input_payload"]["reviewedBy"],
                    "review_source": kwargs["input_payload"]["reviewSource"],
                    "source_message_ids": kwargs["input_payload"]["sourceMessageIds"],
                },
            }

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    create_response = client.post(
        "/sessions/session-1/approved-content",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "message_id": assistant["id"],
        },
    )
    assert create_response.status_code == 200
    response_payload = create_response.json()
    created = response_payload["approved_content"]
    assert "Marked reviewed" in response_payload["summary_text"]
    assert response_payload["reviewed_artifact"]["artifact_id"] == "artifact_reviewed_1"
    assert response_payload["reviewed_artifact"]["reviewed"] is True
    assert response_payload["reviewed_artifact"]["reviewed_by"] == "user-1"
    assert response_payload["reviewed_artifact"]["source_message_ids"] == [assistant["id"]]
    list_response = client.get(
        "/sessions/session-1/approved-content",
        params={"app_id": "app-1", "user_id": "user-1"},
    )
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["latest"]["approved_content_id"] == created["approved_content_id"]
    assert payload["approved_content"][0]["content_text"] == "Approved endpoint content"


def test_mark_reviewed_updates_existing_chat_export_artifact(monkeypatch):
    session_repo, chat_repo = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )
    assistant = chat_repo.append("session-1", "assistant", "Same content already exported")
    calls: list[tuple[str, dict]] = []

    class FakeExecutionClient:
        def get_artifact_inventory(self, **kwargs):
            calls.append(("get_artifact_inventory", kwargs))
            return {
                "items": [
                    {
                        "artifact_id": "artifact_existing",
                        "artifact_type": "chat_export",
                        "display_name": "Chat Export - Same content already exported.md",
                        "session_id": "session-1",
                        "app_id": "app-1",
                        "path": "storage/artifacts/app-1/chat_export/artifact_existing.json",
                        "file_path": "storage/artifacts/app-1/chat_export/artifact_existing.md",
                        "reviewed": False,
                        "source_message_ids": [assistant["id"]],
                    }
                ]
            }

        def update_artifact_metadata(self, **kwargs):
            calls.append(("update_artifact_metadata", kwargs))
            return {
                "artifact_id": kwargs["artifact_id"],
                "artifact_type": "chat_export",
                "display_name": "Chat Export - Same content already exported.md",
                "session_id": "session-1",
                "app_id": "app-1",
                "path": "storage/artifacts/app-1/chat_export/artifact_existing.json",
                "file_path": "storage/artifacts/app-1/chat_export/artifact_existing.md",
                "reviewed": True,
                "reviewed_at": kwargs["metadata"]["reviewed_at"],
                "reviewed_by": kwargs["metadata"]["reviewed_by"],
                "review_source": kwargs["metadata"]["review_source"],
                "source_message_ids": kwargs["metadata"]["source_message_ids"],
            }

        def submit_skill(self, **kwargs):
            raise AssertionError("Mark Reviewed should update the existing export, not create another artifact.")

    monkeypatch.setattr(app_main, "execution_client", FakeExecutionClient())
    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/approved-content",
        json={
            "user_id": "user-1",
            "app_id": "app-1",
            "message_id": assistant["id"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reviewed_artifact"]["artifact_id"] == "artifact_existing"
    assert payload["reviewed_artifact"]["reviewed"] is True
    assert "Marked existing artifact" in payload["summary_text"]
    assert [name for name, _ in calls] == ["get_artifact_inventory", "update_artifact_metadata"]
    update_call = calls[1][1]
    assert update_call["artifact_id"] == "artifact_existing"
    assert update_call["metadata"]["reviewed"] is True
    assert update_call["metadata"]["source_message_ids"] == [assistant["id"]]


def test_notebooklm_login_route_launches_login_and_appends_summary(monkeypatch):
    session_repo, _ = _install_temp_repos(monkeypatch)
    session_repo.get_or_create(
        "session-1",
        collection_id="app-1",
        user_id="user-1",
        config_version=1,
        adapter_version=1,
        template_version=1,
    )

    def fake_launch():
        return {
            "ok": True,
            "command": "python -m notebooklm login",
            "python_command": "python",
        }

    monkeypatch.setattr(app_main, "_launch_notebooklm_login", fake_launch)
    client = TestClient(app)
    response = client.post(
        "/sessions/session-1/integrations/notebooklm/login",
        json={"user_id": "user-1", "app_id": "app-1"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["login_result"]["ok"] is True
    assert payload["login_result"]["command"] == "python -m notebooklm login"
    assert "complete sign-in" in payload["content"].lower()
