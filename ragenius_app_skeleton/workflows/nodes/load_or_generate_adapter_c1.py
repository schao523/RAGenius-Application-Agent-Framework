"""Adapter C1 node: generate adapter draft.

Input contract:
- state["config_json"]
- state["collection_id"]

Output contract:
- state["adapter_draft"]
- state["adapter_draft_version"]
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Optional

from backend.app.adapter_repo import InMemoryAdapterRepo
from backend.openai_tools import get_openai_tools
from ..graph_state import GraphState

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "adapter_generation_prompt.txt"


def load_prompt() -> str:
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"Prompt file not found: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8", errors="ignore")


def run(
    state: GraphState,
    llm_generate_adapter: Optional[Callable[[str, list, Dict], Dict]] = None,
    repo: Optional[InMemoryAdapterRepo] = None,
) -> GraphState:
    """Generate adapter draft using prompt + function-calling schema."""
    if llm_generate_adapter is None:
        llm_generate_adapter = state.get("_llm_generate_adapter")
    if llm_generate_adapter is None:
        raise RuntimeError("llm_generate_adapter callable is required for C1.")
    if "config_json" not in state:
        raise ValueError("config_json is required for C1.")

    collection_id = state.get("collection_id")
    if not collection_id:
        raise ValueError("collection_id is required for C1.")

    repo = repo or InMemoryAdapterRepo()

    prompt = load_prompt()
    tools = [t for t in get_openai_tools(include_optional=False) if t["name"] == "generate_adapter_draft"]
    context = {
        "collection_id": collection_id,
        "domain": state.get("domain", "general"),
        "config_json": state.get("config_json", {}),
    }

    adapter_json = llm_generate_adapter(prompt, tools, context)
    draft = repo.save_draft(collection_id, adapter_json=adapter_json)
    state["adapter_draft"] = draft.adapter_json
    state["adapter_draft_version"] = draft.version
    return state
