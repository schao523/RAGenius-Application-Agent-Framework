from __future__ import annotations

import json
import socket
from urllib.parse import parse_qs, urlparse

from ragenius_app_skeleton.backend.app import execution_subsystem_client as client_module
from ragenius_app_skeleton.backend.app.execution_subsystem_client import (
    ExecutionSubsystemClient,
)


class _JsonResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class _BinaryResponse:
    def __init__(self, payload: bytes, headers: dict[str, str]):
        self._payload = payload
        self.headers = headers

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return self._payload


def test_status_and_confirmation_send_service_auth_and_execution_scope(monkeypatch):
    captured = []

    def fake_urlopen(http_request, timeout=None):
        captured.append(http_request)
        assert timeout == 30
        return _JsonResponse({"status": "completed"})

    monkeypatch.setattr(client_module.request, "urlopen", fake_urlopen)
    client = ExecutionSubsystemClient(
        "http://execution.local/v1",
        service_token="service-secret",
    )

    client.get_execution_status(
        "execution_123",
        app_id="app 1",
        session_id="session/1",
    )
    client.confirm_execution(
        "execution_123",
        app_id="app 1",
        confirmation_id="confirmation_123",
        session_id="session/1",
    )
    client.get_execution_logs(
        "execution_123",
        app_id="app 1",
        session_id="session/1",
    )

    assert len(captured) == 3
    for http_request in captured:
        assert http_request.get_header("Authorization") == "Bearer service-secret"
        assert parse_qs(urlparse(http_request.full_url).query) == {
            "app_id": ["app 1"],
            "session_id": ["session/1"],
        }

    assert captured[0].get_method() == "GET"
    assert captured[1].get_method() == "POST"
    assert captured[2].get_method() == "GET"
    assert urlparse(captured[2].full_url).path.endswith(
        "/executions/execution_123/logs"
    )
    assert json.loads(captured[1].data.decode("utf-8")) == {
        "confirmation_id": "confirmation_123"
    }


def test_client_reads_service_token_from_environment(monkeypatch):
    captured = []

    def fake_urlopen(http_request, timeout=None):
        captured.append(http_request)
        return _JsonResponse({"tools": []})

    monkeypatch.setenv("RAGENIUS_EXECUTION_SERVICE_TOKEN", "environment-secret")
    monkeypatch.setattr(client_module.request, "urlopen", fake_urlopen)

    ExecutionSubsystemClient("http://execution.local/v1").get_tool_inventory()

    assert captured[0].get_header("Authorization") == "Bearer environment-secret"


def test_execute_agent_forwards_public_artifact_fields_without_trusted_context(monkeypatch):
    captured = []

    def fake_urlopen(http_request, timeout=None):
        captured.append(http_request)
        return _JsonResponse({"status": "pending_confirmation"})

    monkeypatch.setattr(client_module.request, "urlopen", fake_urlopen)
    client = ExecutionSubsystemClient("http://execution.local/v1")

    client.submit_agent(
        app_id="app_1",
        session_id="session_1",
        agent_query="Add this source.",
        agent_backend="codex_cli",
        artifact_refs=[{
            "artifact_id": "artifact_123",
            "role": "source",
            "reuse_mode": "inline_text",
        }],
        expected_outputs=[{
            "output_id": "study_report",
            "required": True,
        }],
        context_payload={"safe_note": "Use concise language."},
        execution_mode="async",
    )

    payload = json.loads(captured[0].data.decode("utf-8"))
    assert payload["artifact_refs"][0]["artifact_id"] == "artifact_123"
    assert payload["expected_outputs"][0]["output_id"] == "study_report"
    assert payload["context"] == {"safe_note": "Use concise language."}
    assert payload["execution_options"] == {"mode": "async"}
    assert "authorization" not in payload
    assert "resolved_artifacts" not in payload
    assert "operation_plan" not in payload
    assert "policy_fingerprint" not in payload


def test_client_normalizes_response_timeout(monkeypatch):
    def fake_urlopen(_http_request, timeout=None):
        assert timeout == 7
        raise socket.timeout("timed out")

    monkeypatch.setattr(client_module.request, "urlopen", fake_urlopen)
    client = ExecutionSubsystemClient(
        "http://execution.local/v1",
        connect_timeout_seconds=2,
        response_timeout_seconds=7,
    )

    result = client.get_tool_inventory()

    assert result["error"]["code"] == "EXECUTION_SUBSYSTEM_TIMEOUT"
    assert result["error"]["details"]["connect_timeout_seconds"] == 2
    assert result["error"]["details"]["response_timeout_seconds"] == 7
    assert result["_transport_error"] is True


def test_artifact_byte_request_forwards_auth_and_scope(monkeypatch):
    captured = []

    def fake_urlopen(http_request, timeout=None):
        captured.append(http_request)
        return _BinaryResponse(
            b"report bytes",
            {
                "Content-Type": "text/markdown",
                "Content-Disposition": 'inline; filename="report.md"',
            },
        )

    monkeypatch.setattr(client_module.request, "urlopen", fake_urlopen)
    client = ExecutionSubsystemClient(
        "http://execution.local/v1",
        service_token="service-secret",
    )

    result = client.get_artifact_file(
        app_id="app_1",
        session_id="session_1",
        artifact_id="artifact_1",
        preview=True,
    )

    assert result["content"] == b"report bytes"
    assert result["content_type"] == "text/markdown"
    assert captured[0].get_header("Authorization") == "Bearer service-secret"
    assert parse_qs(urlparse(captured[0].full_url).query) == {
        "app_id": ["app_1"],
        "session_id": ["session_1"],
    }
