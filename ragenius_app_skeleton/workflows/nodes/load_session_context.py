"""Load session context node.

Input contract:
- Requires at minimum one of: session_id or (collection_id + user_id)

Output contract:
- Ensures identity fields exist in state
- Ensures version fields placeholders are present for downstream nodes
"""

from __future__ import annotations

from ..graph_state import GraphState


def _normalize_runtime_state(payload):
    if not isinstance(payload, dict):
        return {
            "workflow_progress": {},
            "session_execution_state": {},
            "intermediate_outputs": [],
            "assembly_state": {},
        }
    if any(
        key in payload
        for key in ("workflow_progress", "session_execution_state", "intermediate_outputs", "assembly_state")
    ):
        workflow_progress = payload.get("workflow_progress", {})
        session_execution_state = payload.get("session_execution_state", {})
        intermediate_outputs = payload.get("intermediate_outputs", [])
        assembly_state = payload.get("assembly_state", {})
    else:
        workflow_progress = payload
        session_execution_state = {}
        intermediate_outputs = []
        assembly_state = {}
    return {
        "workflow_progress": workflow_progress if isinstance(workflow_progress, dict) else {},
        "session_execution_state": session_execution_state if isinstance(session_execution_state, dict) else {},
        "intermediate_outputs": intermediate_outputs if isinstance(intermediate_outputs, list) else [],
        "assembly_state": assembly_state if isinstance(assembly_state, dict) else {},
    }


def run(state: GraphState) -> GraphState:
    """Load/freeze session context when repositories are provided via state deps."""
    session_repo = state.get("_session_repo")
    if session_repo is not None and state.get("session_id"):
        session = session_repo.get(state["session_id"])
        if session is not None:
            state["collection_id"] = session["collection_id"]
            state["user_id"] = session["user_id"]
            state["config_version"] = session["config_version"]
            state["adapter_version"] = session["adapter_version"]
            state["template_version"] = session["template_version"]
            runtime_state = _normalize_runtime_state(session.get("runtime_state") or session.get("workflow_progress") or {})
            if not isinstance(state.get("workflow_progress"), dict) or not state.get("workflow_progress"):
                state["workflow_progress"] = runtime_state.get("workflow_progress", {})
            if not isinstance(state.get("session_execution_state"), dict) or not state.get("session_execution_state"):
                state["session_execution_state"] = runtime_state.get("session_execution_state", {})
            if not isinstance(state.get("intermediate_outputs"), list) or not state.get("intermediate_outputs"):
                state["intermediate_outputs"] = runtime_state.get("intermediate_outputs", [])
            if not isinstance(state.get("assembly_state"), dict) or not state.get("assembly_state"):
                state["assembly_state"] = runtime_state.get("assembly_state", {})

    state.setdefault("domain", "general")
    state.setdefault("chat_history", [])
    state.setdefault("workflow_progress", {})
    state.setdefault("session_execution_state", {})
    state.setdefault("intermediate_outputs", [])
    state.setdefault("assembly_state", {})
    return state
