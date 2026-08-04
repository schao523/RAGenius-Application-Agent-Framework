from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict


class ExecutionSubsystemClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def _json_request(self, *, path: str, method: str = "GET", payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        body = None
        headers = {}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url=f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request) as response:
                raw = response.read().decode("utf-8")
                return {
                    "ok": True,
                    "status_code": response.getcode(),
                    "body": json.loads(raw) if raw else {},
                }
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return {
                "ok": False,
                "status_code": exc.code,
                "body": parsed,
            }
        except urllib.error.URLError as exc:
            return {
                "ok": False,
                "status_code": None,
                "body": {
                    "error": {
                        "code": "EXECUTION_SUBSYSTEM_UNAVAILABLE",
                        "message": str(exc.reason),
                    }
                },
            }

    def execute_skill(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._json_request(path="/v1/executions", method="POST", payload=payload)

    def get_runtime_readyz(self) -> Dict[str, Any]:
        return self._json_request(path="/readyz", method="GET")

    def get_mcp_provider_status(self) -> Dict[str, Any]:
        return self._json_request(path="/v1/tools/providers/mcp/status", method="GET")

    def get_runtime_integrations(self) -> Dict[str, Any]:
        return self._json_request(path="/v1/runtime/integrations", method="GET")

    def get_tool_inventory(self) -> Dict[str, Any]:
        return self._json_request(path="/v1/tools/inventory", method="GET")

    def refresh_mcp_provider(self, provider_id: str) -> Dict[str, Any]:
        return self._json_request(
            path="/v1/tools/discover/mcp",
            method="POST",
            payload={"provider_id": provider_id},
        )

    def get_recent_execution_diagnostics(
        self,
        *,
        limit: int = 10,
        used_fallback: bool | None = None,
        execution_path: str | None = None,
    ) -> Dict[str, Any]:
        query = [f"limit={int(limit)}"]
        if used_fallback is not None:
            query.append(f"used_fallback={'true' if used_fallback else 'false'}")
        if execution_path:
            query.append(f"execution_path={execution_path}")
        return self._json_request(
            path=f"/v1/executions/diagnostics/recent?{'&'.join(query)}",
            method="GET",
        )
