"""Node H: evidence_analysis.

Compares planner_output.infoTypes against compressed_evidence coverage.
Can optionally call LLM with evidence_analysis_prompt via function-calling.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from backend.openai_tools import get_openai_tools

from ..graph_state import GraphState

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "evidence_analysis_prompt.txt"


def _read_prompt() -> str:
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"Prompt file not found: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8", errors="ignore")


def _evidence_text_blob(item: Dict[str, Any]) -> str:
    metadata = item.get("metadata", {}) if isinstance(item.get("metadata", {}), dict) else {}
    return " ".join(
        [
            str(item.get("title", "")),
            str(item.get("snippet", "")),
            str(metadata.get("info_type", "")),
            " ".join(str(x) for x in metadata.get("info_types", []) if isinstance(metadata.get("info_types", []), list)),
            " ".join(str(x) for x in metadata.get("tags", []) if isinstance(metadata.get("tags", []), list)),
        ]
    ).lower()


def _deterministic_analysis(info_types: List[str], evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
    with_evidence: List[str] = []
    missing: List[str] = []
    summary: List[str] = []

    blobs = [_evidence_text_blob(e) for e in evidence]
    for info_type in info_types:
        marker = str(info_type).strip().lower()
        matched = any(marker and marker in blob for blob in blobs)
        if matched:
            with_evidence.append(info_type)
            summary.append(f"{info_type}: present")
        else:
            missing.append(info_type)
            summary.append(f"{info_type}: missing")

    return {
        "infoTypes_with_evidence": with_evidence,
        "infoTypes_missing": missing,
        "evidence_summary": summary,
    }


def run(
    state: GraphState,
    llm_evidence_analysis: Optional[Callable[[str, list, Dict[str, Any]], Dict[str, Any]]] = None,
) -> GraphState:
    """Analyze evidence coverage for planner-required infoTypes."""
    planner_output = state.get("planner_output", {})
    if not isinstance(planner_output, dict):
        raise ValueError("planner_output must be an object.")
    info_types = planner_output.get("infoTypes", [])
    if not isinstance(info_types, list):
        raise ValueError("planner_output.infoTypes must be a list.")

    knowledge_evidence = state.get("compressed_knowledge_evidence", [])
    if knowledge_evidence and not isinstance(knowledge_evidence, list):
        raise ValueError("compressed_knowledge_evidence must be a list when provided.")
    instruction_evidence = state.get("compressed_instruction_evidence", [])
    if instruction_evidence and not isinstance(instruction_evidence, list):
        raise ValueError("compressed_instruction_evidence must be a list when provided.")
    evidence = knowledge_evidence if isinstance(knowledge_evidence, list) and knowledge_evidence else state.get("compressed_evidence", [])
    if not isinstance(evidence, list):
        raise ValueError("compressed_evidence must be a list.")
    turn_action_plan = state.get("turn_action_plan", {}) if isinstance(state.get("turn_action_plan"), dict) else {}
    selected_instruction_block_text = str(state.get("selected_instruction_block_text") or "").strip()
    if (
        str(turn_action_plan.get("action_type") or "").strip() == "guide"
        and selected_instruction_block_text
        and not (isinstance(knowledge_evidence, list) and knowledge_evidence)
    ):
        state["evidence_analysis"] = {
            "infoTypes_with_evidence": list(info_types),
            "infoTypes_missing": [],
            "evidence_summary": ["instruction_block_guided_turn"],
        }
        return state

    if llm_evidence_analysis is None:
        llm_evidence_analysis = state.get("_llm_evidence_analysis")

    if llm_evidence_analysis is None:
        state["evidence_analysis"] = _deterministic_analysis(info_types, evidence)
        return state

    tools = [t for t in get_openai_tools(include_optional=True) if t["name"] == "evidence_analysis"]
    prompt = _read_prompt()
    context = {
        "infoTypes": info_types,
        "compressed_evidence": evidence,
        "knowledge_evidence": evidence,
        "instruction_evidence": instruction_evidence if isinstance(instruction_evidence, list) else [],
    }
    try:
        analysis = llm_evidence_analysis(prompt, tools, context)
    except RuntimeError as exc:
        fallback = _deterministic_analysis(info_types, evidence)
        fallback["evidence_summary"] = list(fallback.get("evidence_summary", [])) + [f"llm_fallback:{exc}"]
        state["evidence_analysis"] = fallback
        return state
    if not isinstance(analysis, dict):
        raise ValueError("llm_evidence_analysis must return a dict.")

    for key in ("infoTypes_with_evidence", "infoTypes_missing", "evidence_summary"):
        analysis.setdefault(key, [])
    state["evidence_analysis"] = analysis
    return state
