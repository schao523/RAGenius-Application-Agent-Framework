"""HTTP client for the RAGenius execution subsystem."""

from __future__ import annotations

import json
import os
import socket
import httpx
from typing import Any
from urllib.parse import urlencode
from urllib import error, request


def _base_url() -> str:
    return str(os.getenv("RAGENIUS_EXECUTION_SUBSYSTEM_URL") or "http://127.0.0.1:3001/v1").rstrip("/")


def _service_token() -> str | None:
    value = str(os.getenv("RAGENIUS_EXECUTION_SERVICE_TOKEN") or "").strip()
    return value or None


class ExecutionSubsystemClient:
    def __init__(
        self,
        base_url: str | None = None,
        service_token: str | None = None,
        connect_timeout_seconds: float | None = None,
        response_timeout_seconds: float | None = None,
        http_transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (base_url or _base_url()).rstrip("/")
        self.service_token = service_token if service_token is not None else _service_token()
        self.connect_timeout_seconds = connect_timeout_seconds or float(
            os.getenv("RAGENIUS_EXECUTION_CONNECT_TIMEOUT_SECONDS") or "5"
        )
        self.response_timeout_seconds = response_timeout_seconds or float(
            os.getenv("RAGENIUS_EXECUTION_RESPONSE_TIMEOUT_SECONDS") or "30"
        )
        self.http_transport = http_transport

    def import_session_upload(
        self,
        *,
        app_id: str,
        session_id: str,
        source_upload_id: str,
        display_name: str,
        mime_type: str | None,
        size_bytes: int,
        sha256: str,
        file_path: str,
    ) -> dict[str, Any]:
        headers = {}
        if self.service_token:
            headers["Authorization"] = f"Bearer {self.service_token}"
        data = {
            "app_id": app_id,
            "session_id": session_id,
            "source_upload_id": source_upload_id,
            "display_name": display_name,
            "mime_type": mime_type or "application/octet-stream",
            "declared_size_bytes": str(size_bytes),
            "declared_sha256": sha256,
        }
        url = f"{self.base_url}/artifact-imports/session-upload"
        timeout = httpx.Timeout(
            self.response_timeout_seconds,
            connect=self.connect_timeout_seconds,
        )
        try:
            with open(file_path, "rb") as source:
                with httpx.Client(transport=self.http_transport, timeout=timeout) as client:
                    response = client.post(
                        url,
                        headers=headers,
                        data=data,
                        files={"file": (display_name, source, mime_type or "application/octet-stream")},
                    )
            try:
                result = response.json()
            except ValueError:
                result = {"error": {"code": "HTTP_ERROR", "message": response.text or "Invalid execution subsystem response."}}
            if response.status_code >= 400:
                result.setdefault("_http_status", response.status_code)
            return result
        except httpx.TimeoutException as exc:
            return {
                "error": {
                    "code": "EXECUTION_SUBSYSTEM_TIMEOUT",
                    "message": "Execution subsystem did not respond within the API timeout.",
                    "details": {"url": url, "error": str(exc)},
                },
                "_transport_error": True,
            }
        except (httpx.RequestError, OSError) as exc:
            return {
                "error": {
                    "code": "EXECUTION_SUBSYSTEM_UNAVAILABLE",
                    "message": "Execution subsystem is unavailable.",
                    "details": {"url": url, "error": str(exc)},
                },
                "_transport_error": True,
            }

    def _json_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = None
        headers = {}
        if self.service_token:
            headers["Authorization"] = f"Bearer {self.service_token}"
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        url = f"{self.base_url}{path}"
        if query:
            query_string = urlencode(
                {
                    key: value
                    for key, value in query.items()
                    if value is not None and str(value).strip() != ""
                }
            )
            if query_string:
                url = f"{url}?{query_string}"
        http_request = request.Request(
            url,
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with request.urlopen(http_request, timeout=self.response_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            try:
                parsed = json.loads(raw) if raw else {}
            except Exception:
                parsed = {"error": {"code": "HTTP_ERROR", "message": raw or str(exc)}}
            parsed.setdefault("_http_status", exc.code)
            return parsed
        except (socket.timeout, TimeoutError) as exc:
            return {
                "error": {
                    "code": "EXECUTION_SUBSYSTEM_TIMEOUT",
                    "message": "Execution subsystem did not respond within the API timeout.",
                    "details": {
                        "url": url,
                        "connect_timeout_seconds": self.connect_timeout_seconds,
                        "response_timeout_seconds": self.response_timeout_seconds,
                        "error": str(exc),
                    },
                },
                "_transport_error": True,
            }
        except (error.URLError, OSError) as exc:
            return {
                "error": {
                    "code": "EXECUTION_SUBSYSTEM_UNAVAILABLE",
                    "message": "Execution subsystem is unavailable.",
                    "details": {"url": url, "error": str(exc)},
                },
                "_transport_error": True,
            }

    def _binary_request(
        self,
        path: str,
        *,
        query: dict[str, Any],
    ) -> dict[str, Any]:
        headers = {}
        if self.service_token:
            headers["Authorization"] = f"Bearer {self.service_token}"
        url = f"{self.base_url}{path}?{urlencode(query)}"
        http_request = request.Request(url, headers=headers, method="GET")
        try:
            with request.urlopen(http_request, timeout=self.response_timeout_seconds) as response:
                response_headers = {
                    str(key).lower(): str(value)
                    for key, value in response.headers.items()
                }
                return {
                    "ok": True,
                    "content": response.read(),
                    "content_type": response_headers.get("content-type", "application/octet-stream"),
                    "content_disposition": response_headers.get("content-disposition"),
                }
        except error.HTTPError as exc:
            return {
                "error": {
                    "code": "ARTIFACT_NOT_FOUND" if exc.code == 404 else "HTTP_ERROR",
                    "message": "Artifact bytes could not be loaded.",
                },
                "_http_status": exc.code,
            }
        except (socket.timeout, TimeoutError, error.URLError, OSError) as exc:
            return {
                "error": {
                    "code": "EXECUTION_SUBSYSTEM_UNAVAILABLE",
                    "message": "Execution subsystem artifact service is unavailable.",
                    "details": {"url": url, "error": str(exc)},
                },
                "_transport_error": True,
            }
    def submit_skill(
        self,
        *,
        session_id: str,
        app_id: str,
        skill_id: str,
        input_payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._json_request(
            "POST",
            "/executions",
            {
                "request_type": "execute_skill",
                "app_id": app_id,
                "session_id": session_id,
                "skill_id": skill_id,
                "input": input_payload,
            },
        )

    def submit_agent(
        self,
        *,
        session_id: str,
        app_id: str,
        agent_query: str,
        agent_backend: str = "codex_cli",
        agent_skill_hint: str | None = None,
        agent_skill_ref: dict[str, str] | None = None,
        approved_content_id: str | None = None,
        approved_revision_id: str | None = None,
        artifact_refs: list[dict[str, Any]] | None = None,
        expected_outputs: list[dict[str, Any]] | None = None,
        interaction_requirements: dict[str, Any] | None = None,
        context_payload: dict[str, Any] | None = None,
        execution_mode: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "request_type": "execute_agent",
            "agent_backend": agent_backend,
            "app_id": app_id,
            "session_id": session_id,
            "agent_query": agent_query,
        }
        if agent_skill_hint:
            payload["agent_skill_hint"] = agent_skill_hint
        if agent_skill_ref:
            payload["agent_skill_ref"] = agent_skill_ref
        if approved_content_id:
            payload["approved_content_id"] = approved_content_id
        if approved_revision_id:
            payload["approved_revision_id"] = approved_revision_id
        if artifact_refs:
            payload["artifact_refs"] = artifact_refs
        if expected_outputs:
            payload["expected_outputs"] = expected_outputs
        if interaction_requirements:
            payload["interaction_requirements"] = interaction_requirements
        if context_payload:
            payload["context"] = context_payload
        if str(execution_mode or "").strip():
            payload["execution_options"] = {"mode": str(execution_mode).strip().lower()}
        return self._json_request("POST", "/executions", payload)

    def get_execution_status(
        self,
        execution_id: str,
        *,
        app_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        return self._json_request(
            "GET",
            f"/executions/{execution_id}",
            query={"app_id": app_id, "session_id": session_id},
        )

    def confirm_execution(
        self,
        execution_id: str,
        *,
        app_id: str,
        confirmation_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        return self._json_request(
            "POST",
            f"/executions/{execution_id}/confirm",
            {"confirmation_id": confirmation_id},
            query={"app_id": app_id, "session_id": session_id},
        )

    def get_execution_logs(
        self,
        execution_id: str,
        *,
        app_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        return self._json_request(
            "GET",
            f"/executions/{execution_id}/logs",
            query={"app_id": app_id, "session_id": session_id},
        )

    def get_agent_interactions(
        self,
        execution_id: str,
        *,
        app_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        return self._json_request(
            "GET",
            f"/executions/{execution_id}/interactions",
            query={"app_id": app_id, "session_id": session_id},
        )

    def get_agent_chat_session(self, execution_id: str, *, app_id: str, session_id: str) -> dict[str, Any]:
        return self._json_request(
            "GET", f"/executions/{execution_id}/chat-session",
            query={"app_id": app_id, "session_id": session_id},
        )

    def submit_agent_follow_up(
        self, execution_id: str, *, app_id: str, session_id: str,
        expected_session_version: int, idempotency_key: str, kind: str,
        text: str | None = None,
    ) -> dict[str, Any]:
        body = {
            "expected_session_version": expected_session_version,
            "idempotency_key": idempotency_key,
            "kind": kind,
        }
        if text:
            body["text"] = text
        return self._json_request(
            "POST", f"/executions/{execution_id}/follow-ups", body,
            query={"app_id": app_id, "session_id": session_id},
        )

    def end_agent_chat_session(
        self, execution_id: str, *, app_id: str, session_id: str,
        expected_session_version: int,
    ) -> dict[str, Any]:
        return self._json_request(
            "POST", f"/executions/{execution_id}/end-chat-session",
            {"expected_session_version": expected_session_version},
            query={"app_id": app_id, "session_id": session_id},
        )

    def get_agent_events(
        self,
        execution_id: str,
        *,
        app_id: str,
        session_id: str,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        return self._json_request(
            "GET",
            f"/executions/{execution_id}/events",
            query={
                "app_id": app_id,
                "session_id": session_id,
                "after_sequence": after_sequence,
                "limit": limit,
            },
        )

    def respond_agent_interaction(
        self,
        execution_id: str,
        interaction_id: str,
        *,
        app_id: str,
        session_id: str,
        expected_version: int,
        idempotency_key: str,
        response: dict[str, Any],
    ) -> dict[str, Any]:
        return self._json_request(
            "POST",
            f"/executions/{execution_id}/interactions/{interaction_id}/responses",
            {
                "expected_version": expected_version,
                "idempotency_key": idempotency_key,
                "response": response,
            },
            query={"app_id": app_id, "session_id": session_id},
        )

    def cancel_agent_execution(
        self,
        execution_id: str,
        *,
        app_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        return self._json_request(
            "POST",
            f"/executions/{execution_id}/cancel",
            query={"app_id": app_id, "session_id": session_id},
        )

    def get_tool_inventory(self) -> dict[str, Any]:
        return self._json_request("GET", "/tools/inventory")

    def get_skill_inventory(self, *, visibility: str | None = None) -> dict[str, Any]:
        return self._json_request("GET", "/skills/inventory", query={"visibility": visibility})

    def get_agent_skill_inventory(self, *, app_id: str, backend: str) -> dict[str, Any]:
        return self._json_request(
            "GET",
            "/agent-skills/inventory",
            query={"app_id": app_id, "backend": backend},
        )

    def get_artifact_inventory(
        self,
        *,
        app_id: str,
        session_id: str | None = None,
        artifact_type: str | None = None,
        eligible_for: str | None = None,
        status: str | None = "ready",
    ) -> dict[str, Any]:
        return self._json_request(
            "GET",
            "/artifacts",
            query={
                "app_id": app_id,
                "session_id": session_id,
                "artifact_type": artifact_type,
                "eligible_for": eligible_for,
                "status": status,
            },
        )

    def update_artifact_metadata(
        self,
        *,
        app_id: str,
        artifact_id: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        return self._json_request(
            "PATCH",
            f"/artifacts/{artifact_id}",
            {
                "app_id": app_id,
                "metadata": metadata,
            },
        )

    def get_artifact_file(
        self,
        *,
        app_id: str,
        session_id: str,
        artifact_id: str,
        preview: bool = False,
    ) -> dict[str, Any]:
        suffix = "preview" if preview else "download"
        return self._binary_request(
            f"/artifacts/{artifact_id}/{suffix}",
            query={"app_id": app_id, "session_id": session_id},
        )

    def delete_artifact(
        self,
        *,
        app_id: str,
        session_id: str,
        artifact_id: str,
    ) -> dict[str, Any]:
        return self._json_request(
            "DELETE",
            f"/artifacts/{artifact_id}",
            query={"app_id": app_id, "session_id": session_id},
        )
