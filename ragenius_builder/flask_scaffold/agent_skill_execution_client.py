from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict


class AgentSkillExecutionClient:
    def __init__(self, base_url: str, service_token: str, *, timeout_seconds: float = 30.0) -> None:
        if not service_token.strip():
            raise ValueError("Agent skill administration requires a dedicated service token")
        self.base_url = base_url.rstrip("/")
        self.service_token = service_token.strip()
        self.timeout_seconds = timeout_seconds

    def _json_request(
        self,
        *,
        path: str,
        method: str = "GET",
        payload: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            url=f"{self.base_url}{path}",
            data=body,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.service_token}",
                **({"Content-Type": "application/json"} if body is not None else {}),
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                return {
                    "ok": True,
                    "status_code": response.getcode(),
                    "body": json.loads(raw) if raw else {},
                }
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {"error": {"code": "INVALID_EXECUTION_RESPONSE", "message": raw[:1024]}}
            return {"ok": False, "status_code": exc.code, "body": parsed}
        except (urllib.error.URLError, TimeoutError) as exc:
            reason = getattr(exc, "reason", exc)
            return {
                "ok": False,
                "status_code": None,
                "body": {
                    "error": {
                        "code": "EXECUTION_SUBSYSTEM_UNAVAILABLE",
                        "message": str(reason),
                    }
                },
            }

    def get_source_options(self) -> Dict[str, Any]:
        return self._json_request(path="/v1/admin/agent-skills/source-options")

    def discover(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._json_request(
            path="/v1/admin/agent-skills/discover", method="POST", payload=payload
        )

    def inspect(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._json_request(
            path="/v1/admin/agent-skills/inspect", method="POST", payload=payload
        )

    def publish_governance_projection(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._json_request(
            path="/v1/admin/agent-skills/governance-projection",
            method="PUT",
            payload=payload,
        )
