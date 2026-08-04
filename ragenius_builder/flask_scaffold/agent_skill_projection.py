from __future__ import annotations

import datetime
import hashlib
import json
from typing import Any, Dict, Protocol


class ProjectionClient(Protocol):
    def publish_governance_projection(self, payload: Dict[str, Any]) -> Dict[str, Any]: ...


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def compute_agent_skill_projection_digest(payload: Dict[str, Any]) -> str:
    unsigned = {key: value for key, value in payload.items() if key != "digest"}
    unsigned["items"] = sorted(
        unsigned.get("items", []), key=_canonical_json
    )
    digest = hashlib.sha256(_canonical_json(unsigned).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _generated_at_for_revision(revision: int) -> str:
    generated = datetime.datetime.fromtimestamp(
        revision / 1000, tz=datetime.timezone.utc
    )
    return generated.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_agent_skill_projection(store: Any, builder_instance_id: str) -> Dict[str, Any]:
    state = store.configure_agent_skill_projection(builder_instance_id)
    items = sorted(store.list_agent_skill_projection_items(), key=_canonical_json)
    payload = {
        "builder_instance_id": builder_instance_id,
        "revision": int(state["local_revision"]),
        "generated_at": _generated_at_for_revision(int(state["local_revision"])),
        "items": items,
    }
    payload["digest"] = compute_agent_skill_projection_digest(payload)
    return payload


def _response_error(response: Dict[str, Any]) -> tuple[str, str]:
    error = response.get("body", {}).get("error", {})
    return (
        str(error.get("code") or "AGENT_SKILL_PROJECTION_SYNC_FAILED"),
        str(error.get("message") or "Execution subsystem rejected the projection."),
    )


def synchronize_agent_skill_projection(
    store: Any,
    client: ProjectionClient,
    builder_instance_id: str,
) -> Dict[str, Any]:
    payload = build_agent_skill_projection(store, builder_instance_id)
    store.mark_agent_skill_projection_attempt()
    response = client.publish_governance_projection(payload)
    if not response.get("ok"):
        code, message = _response_error(response)
        return store.mark_agent_skill_projection_failed(code=code, message=message)

    acknowledgment = response.get("body", {})
    expected = (
        payload["builder_instance_id"],
        payload["revision"],
        payload["digest"],
    )
    observed = (
        acknowledgment.get("builder_instance_id"),
        acknowledgment.get("revision"),
        acknowledgment.get("digest"),
    )
    if observed != expected:
        return store.mark_agent_skill_projection_failed(
            code="AGENT_SKILL_PROJECTION_ACK_MISMATCH",
            message="Execution acknowledgment did not match instance, revision, and digest.",
        )
    return store.mark_agent_skill_projection_synchronized(
        builder_instance_id=payload["builder_instance_id"],
        revision=payload["revision"],
        digest=payload["digest"],
    )
