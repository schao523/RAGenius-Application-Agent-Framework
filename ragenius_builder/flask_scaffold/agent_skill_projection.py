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
    state, snapshot_items = store.read_agent_skill_projection_snapshot(builder_instance_id)
    items = sorted(snapshot_items, key=_canonical_json)
    payload = {
        "builder_instance_id": builder_instance_id,
        "revision": int(state["local_revision"]),
        "generated_at": _generated_at_for_revision(int(state["local_revision"])),
        "items": items,
    }
    payload["digest"] = compute_agent_skill_projection_digest(payload)
    return payload


def synchronize_agent_skill_projection(
    store: Any,
    client: ProjectionClient,
    builder_instance_id: str,
) -> Dict[str, Any]:
    # Local import avoids a module cycle while keeping this compatibility API thin.
    from agent_skill_publication import publish_agent_skill_revision

    state = store.configure_agent_skill_projection(builder_instance_id)
    result = publish_agent_skill_revision(
        store=store,
        execution_client=client,
        builder_instance_id=builder_instance_id,
        expected_local_revision=int(state["local_revision"]),
        actor_id="legacy-agent-skill-synchronizer",
        correlation_id=f"legacy-sync:{state['local_revision']}",
    )
    return result["projection_state"]
