"""Adapter C2 node: validate/retry adapter draft.

Input contract:
- state["adapter_draft"]
- state["adapter_draft_version"]

Output contract:
- validated adapter draft remains in state
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from backend.app.adapter_repo import InMemoryAdapterRepo
from backend.schemas import validate_adapter_json
from ..graph_state import GraphState
from .load_or_generate_adapter_c1 import load_prompt
from backend.openai_tools import get_openai_tools


def run(
    state: GraphState,
    llm_generate_adapter: Optional[Callable[[str, list, Dict], Dict]] = None,
    repo: Optional[InMemoryAdapterRepo] = None,
    max_retries: int = 2,
) -> GraphState:
    """Validate adapter draft and retry generation up to max_retries."""
    if llm_generate_adapter is None:
        llm_generate_adapter = state.get("_llm_generate_adapter")
    repo = repo or InMemoryAdapterRepo()
    collection_id = state.get("collection_id")
    if not collection_id:
        raise ValueError("collection_id is required for C2.")

    adapter_json = state.get("adapter_draft")
    if adapter_json is None:
        raise ValueError("adapter_draft is required for C2.")

    draft_version = state.get("adapter_draft_version") or repo.next_draft_version(collection_id)

    attempts = 0
    while True:
        try:
            validate_adapter_json(adapter_json)
            draft = repo.save_draft(collection_id, adapter_json=adapter_json, version=draft_version)
            state["adapter_draft"] = draft.adapter_json
            state["adapter_draft_version"] = draft.version
            return state
        except Exception:
            if attempts >= max_retries:
                raise
            if llm_generate_adapter is None:
                raise
            attempts += 1
            prompt = load_prompt()
            tools = [t for t in get_openai_tools(include_optional=False) if t["name"] == "generate_adapter_draft"]
            context = {
                "collection_id": collection_id,
                "domain": state.get("domain", "general"),
                "config_json": state.get("config_json", {}),
            }
            adapter_json = llm_generate_adapter(prompt, tools, context)
