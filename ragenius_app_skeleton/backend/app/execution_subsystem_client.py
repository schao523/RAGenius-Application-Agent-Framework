"""HTTP client for the RAGenius execution subsystem."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlencode
from urllib import error, request


def _base_url() -> str:
    return str(os.getenv("RAGENIUS_EXECUTION_SUBSYSTEM_URL") or "http://127.0.0.1:3001/v1").rstrip("/")


class ExecutionSubsystemClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or _base_url()).rstrip("/")

    def _json_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = None
        headers = {"Content-Type": "application/json"}
        if payload is not None:
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
            with request.urlopen(http_request) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            try:
                parsed = json.loads(raw) if raw else {}
            except Exception:
                parsed = {"error": {"code": "HTTP_ERROR", "message": raw or str(exc)}}
            parsed.setdefault("_http_status", exc.code)
            return parsed
        except (error.URLError, OSError) as exc:
            return {
                "error": {
                    "code": "EXECUTION_SUBSYSTEM_UNAVAILABLE",
                    "message": "Execution subsystem is unavailable.",
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
        require_confirmation: bool = False,
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
                "execution_options": {
                    "require_confirmation": require_confirmation,
                },
            },
        )

    def submit_agent(
        self,
        *,
        session_id: str,
        app_id: str,
        agent_query: str,
        agent_skill_hint: str | None = None,
        approved_content_id: str | None = None,
        approved_revision_id: str | None = None,
        context_payload: dict[str, Any] | None = None,
        require_confirmation: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "request_type": "execute_agent",
            "agent_backend": "codex_cli",
            "app_id": app_id,
            "session_id": session_id,
            "agent_query": agent_query,
            "execution_options": {
                "require_confirmation": require_confirmation,
            },
        }
        if agent_skill_hint:
            payload["agent_skill_hint"] = agent_skill_hint
        if approved_content_id:
            payload["approved_content_id"] = approved_content_id
        if approved_revision_id:
            payload["approved_revision_id"] = approved_revision_id
        if context_payload:
            payload["context"] = context_payload
        return self._json_request("POST", "/executions", payload)

    def get_execution_status(self, execution_id: str) -> dict[str, Any]:
        return self._json_request("GET", f"/executions/{execution_id}")

    def confirm_execution(self, execution_id: str) -> dict[str, Any]:
        return self._json_request(
            "POST",
            f"/executions/{execution_id}/confirm",
            {"approved": True},
        )

    def get_tool_inventory(self) -> dict[str, Any]:
        return self._json_request("GET", "/tools/inventory")

    def get_skill_inventory(self, *, visibility: str | None = None) -> dict[str, Any]:
        return self._json_request("GET", "/skills/inventory", query={"visibility": visibility})

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
