"""Adapter C3 node: admin approval gate.

Input contract:
- state["collection_id"]
- optional state["adapter_draft"]

Output contract:
- state["adapter_json"] and state["adapter_version"] only when approved
- otherwise raises PendingAdapterApproval
"""

from __future__ import annotations

from backend.app.adapter_repo import InMemoryAdapterRepo
from ..graph_state import GraphState


class PendingAdapterApproval(RuntimeError):
    """Raised when no approved adapter is available for answering."""


def run(state: GraphState, repo: InMemoryAdapterRepo | None = None) -> GraphState:
    """Resolve approved adapter and block when only draft exists."""
    repo = repo or InMemoryAdapterRepo()
    collection_id = state.get("collection_id")
    if not collection_id:
        raise ValueError("collection_id is required for C3.")

    approved = repo.get_active_adapter(collection_id)
    if approved is not None:
        state["adapter_json"] = approved.adapter_json
        state["adapter_version"] = approved.version
        return state

    draft = repo.get_draft(collection_id)
    if draft is not None:
        raise PendingAdapterApproval(
            f"Adapter draft v{draft.version} pending admin approval for collection {collection_id}."
        )

    raise PendingAdapterApproval(f"No adapter available for collection {collection_id}.")
