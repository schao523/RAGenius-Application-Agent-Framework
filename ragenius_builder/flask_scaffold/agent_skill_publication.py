from __future__ import annotations

import json
from typing import Any, Dict

from agent_skill_projection import build_agent_skill_projection


class PublicationRevisionStale(ValueError):
    code = "PUBLICATION_REVISION_STALE"

    def __init__(self, expected_revision: int, current_revision: int) -> None:
        super().__init__(
            f"Reviewed revision {expected_revision} is stale; current revision is {current_revision}."
        )
        self.expected_revision = expected_revision
        self.current_revision = current_revision


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _redact_projection(projection: Dict[str, Any]) -> Dict[str, Any]:
    sources: dict[str, dict] = {}
    skills: dict[str, dict] = {}
    bindings: list[dict] = []
    for item in projection.get("items", []):
        source_id = str(item["source_id"])
        skill_id = str(item["agent_skill_id"])
        sources[source_id] = {
            "source_id": source_id,
            "enabled": bool(item["source_enabled"]),
        }
        skills[skill_id] = {
            "agent_skill_id": skill_id,
            "source_id": source_id,
            "provider_skill_reference": str(
                item.get("provider_skill_reference") or item["provider_skill_name"]
            ),
            "current_fingerprint": str(item["current_fingerprint"]),
            "approved_fingerprint": item.get("approved_fingerprint"),
            "approval_state": str(item["approval_state"]),
        }
        bindings.append(
            {
                "app_id": str(item["app_id"]),
                "agent_skill_id": skill_id,
                "enabled": bool(item["binding_enabled"]),
            }
        )
    return {
        "sources": sorted(sources.values(), key=_canonical_json),
        "skills": sorted(skills.values(), key=_canonical_json),
        "bindings": sorted(bindings, key=_canonical_json),
    }


def _diff_records(
    before_records: list[dict],
    after_records: list[dict],
    *,
    identity_fields: tuple[str, ...],
) -> list[dict]:
    def identity(record: dict) -> tuple[str, ...]:
        return tuple(str(record[field]) for field in identity_fields)

    before = {identity(record): record for record in before_records}
    after = {identity(record): record for record in after_records}
    changes = []
    for record_id in sorted(set(before) | set(after)):
        previous = before.get(record_id)
        current = after.get(record_id)
        if previous == current:
            continue
        change = "added" if previous is None else "removed" if current is None else "changed"
        identity_values = dict(zip(identity_fields, record_id))
        changes.append(
            {
                **identity_values,
                "change": change,
                "before": previous,
                "after": current,
            }
        )
    return changes


def _build_changes(baseline: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
    source_changes = _diff_records(
        baseline["sources"], current["sources"], identity_fields=("source_id",)
    )
    approval_changes = _diff_records(
        baseline["skills"], current["skills"], identity_fields=("agent_skill_id",)
    )
    binding_changes = _diff_records(
        baseline["bindings"],
        current["bindings"],
        identity_fields=("app_id", "agent_skill_id"),
    )

    affected_skill_ids = {
        change["agent_skill_id"] for change in approval_changes
    }
    affected_source_ids = {change["source_id"] for change in source_changes}
    skill_sources = {
        record["agent_skill_id"]: record["source_id"]
        for record in baseline["skills"] + current["skills"]
    }
    affected_skill_ids.update(
        skill_id
        for skill_id, source_id in skill_sources.items()
        if source_id in affected_source_ids
    )
    affected_apps = {
        change["app_id"] for change in binding_changes
    }
    affected_apps.update(
        binding["app_id"]
        for binding in baseline["bindings"] + current["bindings"]
        if binding["agent_skill_id"] in affected_skill_ids
    )
    return {
        "sources": source_changes,
        "approvals": approval_changes,
        "bindings": binding_changes,
        "affected_apps": sorted(affected_apps),
    }


def _change_counts(changes: Dict[str, Any]) -> Dict[str, int]:
    return {
        "source_changes": len(changes["sources"]),
        "approval_changes": len(changes["approvals"]),
        "binding_changes": len(changes["bindings"]),
        "affected_app_count": len(changes["affected_apps"]),
    }


def build_publication_preview(*, store: Any, builder_instance_id: str) -> Dict[str, Any]:
    projection = build_agent_skill_projection(store, builder_instance_id)
    state = store.get_agent_skill_projection_state()
    current = _redact_projection(projection)
    baseline = store.get_published_agent_skill_snapshot()
    baseline_reconstructed = False
    if baseline is None and (
        state.get("published_revision") == state.get("local_revision")
        and state.get("published_digest") == projection["digest"]
        and state.get("published_revision") is not None
    ):
        baseline = current
        baseline_reconstructed = True
    baseline_available = baseline is not None
    changes = _build_changes(
        baseline or {"sources": [], "skills": [], "bindings": []}, current
    )
    has_changes = any(
        changes[collection] for collection in ("sources", "approvals", "bindings")
    )
    if state.get("sync_status") == "failed":
        preview_state = "publish_failed"
    elif not has_changes and baseline_available:
        preview_state = "published"
    else:
        preview_state = "draft_changes"
    return {
        "state": preview_state,
        "local_revision": int(state["local_revision"]),
        "published_revision": state.get("published_revision"),
        "published_digest": state.get("published_digest"),
        "current_digest": projection["digest"],
        "baseline_available": baseline_available,
        "baseline_reconstructed": baseline_reconstructed,
        "full_replacement": not baseline_available,
        "last_success_at": state.get("last_success_at"),
        "last_error": (
            {
                "code": state.get("last_error_code"),
                "message": state.get("last_error_message"),
            }
            if state.get("last_error_code")
            else None
        ),
        "changes": changes,
        "counts": _change_counts(changes),
    }


def _response_error(response: Dict[str, Any]) -> tuple[str, str]:
    error = response.get("body", {}).get("error", {})
    return (
        str(error.get("code") or "AGENT_SKILL_PROJECTION_PUBLICATION_FAILED")[:128],
        str(error.get("message") or "Execution subsystem rejected the publication.")[:1024],
    )


def _record_outcome(
    *,
    store: Any,
    action: str,
    actor_id: str,
    correlation_id: str,
    revision: int,
    counts: Dict[str, int],
    outcome: str,
    error_code: str | None = None,
) -> None:
    details: Dict[str, Any] = {
        "local_revision": revision,
        "outcome": outcome,
        "counts": counts,
    }
    if error_code:
        details["error_code"] = error_code
    store.record_agent_skill_publication_event(
        action=action,
        actor_id=actor_id,
        details=details,
        correlation_id=correlation_id,
    )


def publish_agent_skill_revision(
    *,
    store: Any,
    execution_client: Any,
    builder_instance_id: str,
    expected_local_revision: int,
    actor_id: str,
    correlation_id: str,
) -> Dict[str, Any]:
    preview = build_publication_preview(
        store=store, builder_instance_id=builder_instance_id
    )
    current_revision = int(preview["local_revision"])
    if int(expected_local_revision) != current_revision:
        raise PublicationRevisionStale(int(expected_local_revision), current_revision)

    projection = build_agent_skill_projection(store, builder_instance_id)
    if int(projection["revision"]) != current_revision:
        raise PublicationRevisionStale(int(expected_local_revision), int(projection["revision"]))
    redacted_snapshot = _redact_projection(projection)
    counts = preview["counts"]
    store.mark_agent_skill_projection_attempt()
    _record_outcome(
        store=store,
        action="agent_skill.publication_attempted",
        actor_id=actor_id,
        correlation_id=correlation_id,
        revision=current_revision,
        counts=counts,
        outcome="attempted",
    )

    try:
        response = execution_client.publish_governance_projection(projection)
    except Exception as exc:
        response = {
            "ok": False,
            "body": {
                "error": {
                    "code": "EXECUTION_SUBSYSTEM_UNAVAILABLE",
                    "message": str(exc)[:1024],
                }
            },
        }

    if response.get("ok"):
        acknowledgment = response.get("body", {})
        expected = (
            projection["builder_instance_id"],
            projection["revision"],
            projection["digest"],
        )
        observed = (
            acknowledgment.get("builder_instance_id"),
            acknowledgment.get("revision"),
            acknowledgment.get("digest"),
        )
        if observed != expected:
            response = {
                "ok": False,
                "body": {
                    "error": {
                        "code": "AGENT_SKILL_PROJECTION_ACK_MISMATCH",
                        "message": "Execution acknowledgment did not match instance, revision, and digest.",
                    }
                },
            }

    if not response.get("ok"):
        code, message = _response_error(response)
        projection_state = store.mark_agent_skill_projection_failed(
            code=code, message=message
        )
        _record_outcome(
            store=store,
            action="agent_skill.publication_failed",
            actor_id=actor_id,
            correlation_id=correlation_id,
            revision=current_revision,
            counts=counts,
            outcome="failed",
            error_code=code,
        )
        return {
            **preview,
            "ok": False,
            "state": "publish_failed",
            "error": {"code": code, "message": message},
            "projection_state": projection_state,
        }

    projection_state = store.mark_agent_skill_projection_published(
        builder_instance_id=projection["builder_instance_id"],
        revision=projection["revision"],
        digest=projection["digest"],
        redacted_snapshot=redacted_snapshot,
    )
    _record_outcome(
        store=store,
        action="agent_skill.publication_succeeded",
        actor_id=actor_id,
        correlation_id=correlation_id,
        revision=current_revision,
        counts=counts,
        outcome="published",
    )
    return {
        **preview,
        "ok": True,
        "state": "published",
        "published_revision": projection["revision"],
        "published_digest": projection["digest"],
        "projection_state": projection_state,
    }
