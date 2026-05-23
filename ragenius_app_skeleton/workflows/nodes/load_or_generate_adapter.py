"""Adapter orchestrator node for Hybrid Adapter Strategy.

Input contract:
- state["collection_id"]
- state["config_json"]

Output contract:
- state["adapter_json"]
- state["adapter_version"]
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from backend.app.adapter_repo import InMemoryAdapterRepo
from ..graph_state import GraphState
from . import load_or_generate_adapter_c1 as c1
from . import load_or_generate_adapter_c2 as c2
from . import load_or_generate_adapter_c3 as c3


def run(
    state: GraphState,
    llm_generate_adapter: Optional[Callable[[str, list, Dict], Dict]] = None,
    repo: Optional[InMemoryAdapterRepo] = None,
) -> GraphState:
    """Run C1->C2->C3 unless an approved adapter already exists."""
    repo = repo or InMemoryAdapterRepo()
    collection_id = state.get("collection_id")
    if not collection_id:
        raise ValueError("collection_id is required for adapter orchestration.")

    if state.get("adapter_json") and state.get("adapter_version"):
        return state

    approved = repo.get_active_adapter(collection_id)
    if approved is not None:
        state["adapter_json"] = approved.adapter_json
        state["adapter_version"] = approved.version
        return state

    state = c1.run(state, llm_generate_adapter=llm_generate_adapter, repo=repo)
    state = c2.run(state, llm_generate_adapter=llm_generate_adapter, repo=repo)
    state = c3.run(state, repo=repo)
    return state
