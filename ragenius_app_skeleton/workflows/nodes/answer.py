"""Node I: answer_generation.

Generic presentation node for the LLM-first runner.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from backend.openai_tools import get_openai_tools
from backend.schemas import validate_final_answer

from ..graph_state import GraphState

PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"
PROMPT_ANSWER = PROMPT_DIR / "answer_generation_system_prompt.txt"
PROMPT_SAFE = PROMPT_DIR / "safe_answer_prompt.txt"
DEFAULT_EMPTY_ANSWER = "No answer text was generated. Please retry with a more specific question."
logger = logging.getLogger(__name__)


def _read_prompt(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8", errors="ignore")


def _build_effective_system_prompt(base_prompt: str, global_instruction_context: Dict[str, Any]) -> str:
    if not isinstance(global_instruction_context, dict) or not global_instruction_context:
        return base_prompt
    serialized = json.dumps(global_instruction_context, ensure_ascii=False, indent=2)
    return (
        f"{base_prompt.rstrip()}\n\n"
        "GLOBAL ALWAYS-ON APPLICATION INSTRUCTION CONTEXT:\n"
        "Treat this as stable application-level behavior that applies every turn.\n"
        f"{serialized}\n"
    )


def _call_answer_llm(
    llm_answer: Callable[[str, list, Dict[str, Any]], Dict[str, Any]],
    prompt: str,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    tools = [t for t in get_openai_tools(include_optional=False) if t["name"] == "create_final_answer"]
    output = llm_answer(prompt, tools, context)
    if hasattr(output, "model_dump"):
        output = output.model_dump()
    elif hasattr(output, "dict"):
        output = output.dict()
    elif isinstance(output, str):
        output = json.loads(output)
    if not isinstance(output, dict):
        raise ValueError("llm_answer must return a dict.")
    return output


def _ensure_non_empty_content(final_answer: Dict[str, Any]) -> Dict[str, Any]:
    content = final_answer.get("content")
    if isinstance(content, str) and content.strip():
        return final_answer
    fixed = dict(final_answer)
    fixed["content"] = DEFAULT_EMPTY_ANSWER
    return fixed


def _fallback_final_answer(context: Dict[str, Any]) -> Dict[str, Any]:
    evidence = (
        context.get("knowledge_evidence", [])
        or context.get("session_upload_evidence", [])
        or context.get("compressed_evidence", [])
    )
    top = evidence[0] if isinstance(evidence, list) and evidence else {}
    return {
        "content": "Here is the answer based on available evidence.",
        "citations": [
            {
                "docId": str(top.get("doc_id", "doc-unknown")),
                "title": str(top.get("title", "Reference")),
                "snippet": str(top.get("snippet", "No snippet")),
                "score": float(top.get("score", 0.5) or 0.5),
                "location": top.get("location"),
                "version": top.get("version"),
            }
        ],
        "missing_infoTypes": [],
    }


def _direct_instruction_block_answer(context: Dict[str, Any]) -> Dict[str, Any] | None:
    turn_action_plan = context.get("turn_action_plan", {}) if isinstance(context.get("turn_action_plan"), dict) else {}
    response_style = turn_action_plan.get("response_style", {}) if isinstance(turn_action_plan.get("response_style"), dict) else {}
    selected_block = context.get("selected_instruction_block", {}) if isinstance(context.get("selected_instruction_block"), dict) else {}
    if str(turn_action_plan.get("action_type") or "").strip() != "guide":
        return None
    if not bool(response_style.get("use_instruction_block_only")):
        return None
    response_hint = str(selected_block.get("response_hint") or "").strip()
    if not response_hint:
        return None
    cleaned = response_hint.strip("「」\"'")
    if not cleaned:
        return None
    return {
        "content": cleaned,
        "citations": [],
        "missing_infoTypes": [],
    }


def _direct_visible_output_answer(context: Dict[str, Any]) -> Dict[str, Any] | None:
    visible_outputs = context.get("visible_outputs", [])
    if not isinstance(visible_outputs, list) or not visible_outputs:
        return None
    contents = []
    for item in visible_outputs:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if content:
            contents.append(content)
    if not contents:
        return None
    return {
        "content": "\n\n".join(contents),
        "citations": [],
        "missing_infoTypes": [],
    }


def _direct_general_llm_answer(
    llm_answer: Callable[[str, list, Dict[str, Any]], Dict[str, Any]],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    prompt = (
        "The user's turn is outside the scope of the selected application. "
        "Answer the user directly as a general-purpose assistant. "
        "Do not rely on application-specific instructions, workflows, or retrieval evidence."
    )
    direct_context = {
        "user_query": context.get("user_query", ""),
        "chat_history": context.get("chat_history", []),
    }
    return _call_answer_llm(llm_answer, prompt, direct_context)


def run(
    state: GraphState,
    llm_answer: Optional[Callable[[str, list, Dict[str, Any]], Dict[str, Any]]] = None,
) -> GraphState:
    """Generate final answer from instruction scope, prepared inputs, and execution state."""
    if llm_answer is None:
        llm_answer = state.get("_llm_answer")

    if llm_answer is None:
        def _default_llm_answer(_prompt: str, _tools: list, context: Dict[str, Any]) -> Dict[str, Any]:
            return _fallback_final_answer(context)
        llm_answer = _default_llm_answer

    context = {
        "user_query": state.get("user_query", ""),
        "chat_history": state.get("chat_history", []),
        "planner_output": state.get("planner_output", {}),
        "evidence_analysis": state.get("evidence_analysis", {}),
        "compressed_evidence": state.get("compressed_evidence", []),
        "prepared_inputs": state.get("prepared_inputs", {}),
        "instruction_evidence": state.get("compressed_instruction_evidence", []),
        "selected_instruction_block": state.get("selected_instruction_block", {}),
        "selected_instruction_block_text": state.get("selected_instruction_block_text", ""),
        "instruction_resource_load_plan": state.get("instruction_resource_load_plan", []),
        "instruction_resource_context": state.get("instruction_resource_context", []),
        "template_resource_load_plan": state.get("template_resource_load_plan", []),
        "template_resource_context": state.get("template_resource_context", []),
        "global_instruction_context": state.get("global_instruction_context", {}),
        "knowledge_evidence": state.get("compressed_knowledge_evidence", []),
        "template_evidence": state.get("compressed_template_evidence", []),
        "session_upload_evidence": state.get("compressed_session_upload_evidence", []),
        "adapter_json": state.get("adapter_json", {}),
        "config_json": state.get("config_json", {}),
        "template_registry": state.get("template_registry", {}),
        "turn_execution_plan": state.get("turn_execution_plan", {}),
        "turn_action_plan": state.get("turn_action_plan", {}),
        "session_execution_state": state.get("session_execution_state", {}),
        "presentation_policy": state.get("presentation_policy", {}),
        "visible_outputs": state.get("visible_outputs", []),
        "hidden_outputs": state.get("hidden_outputs", []),
        "execution_artifacts": state.get("execution_artifacts", []),
    }
    turn_execution_plan = context.get("turn_execution_plan", {}) if isinstance(context.get("turn_execution_plan"), dict) else {}
    turn_intent = str(turn_execution_plan.get("turn_intent") or "").strip()

    if turn_intent == "general_out_of_scope_question":
        llm_error = None
        try:
            final_answer = _direct_general_llm_answer(llm_answer, context)
            answer_source = "general_llm_direct"
        except Exception as exc:
            llm_error = f"{type(exc).__name__}: {exc}"
            logger.exception("General out-of-scope LLM call failed; using fallback path.")
            answer_source = "fallback_generic_general"
            final_answer = _fallback_final_answer(context)
        final_answer = _ensure_non_empty_content(final_answer)
        validate_final_answer(final_answer)
        state["final_answer"] = final_answer
        state["answer_generation_meta"] = {"source": answer_source, "llm_error": llm_error}
        return state

    direct_instruction_answer = _direct_instruction_block_answer(context)
    if direct_instruction_answer is not None:
        state["final_answer"] = direct_instruction_answer
        state["answer_generation_meta"] = {"source": "direct_instruction_block", "llm_error": None}
        return state

    direct_visible_answer = _direct_visible_output_answer(context)
    if direct_visible_answer is not None:
        state["final_answer"] = direct_visible_answer
        state["answer_generation_meta"] = {"source": "visible_outputs", "llm_error": None}
        return state

    answer_prompt = _build_effective_system_prompt(
        _read_prompt(PROMPT_ANSWER),
        context.get("global_instruction_context", {}),
    )
    answer_source = "llm"
    llm_error = None
    try:
        final_answer = _call_answer_llm(llm_answer, answer_prompt, context)
    except Exception as exc:
        llm_error = f"{type(exc).__name__}: {exc}"
        logger.exception("Answer LLM call failed; using fallback path.")
        fallback_direct = _direct_visible_output_answer(context)
        if fallback_direct is not None:
            answer_source = "fallback_visible_outputs"
            final_answer = fallback_direct
        else:
            answer_source = "fallback_generic"
            final_answer = _fallback_final_answer(context)
    final_answer = _ensure_non_empty_content(final_answer)
    validate_final_answer(final_answer)

    missing = final_answer.get("missing_infoTypes", [])
    if isinstance(missing, list) and len(missing) > 0:
        safe_prompt = _build_effective_system_prompt(
            _read_prompt(PROMPT_SAFE),
            context.get("global_instruction_context", {}),
        )
        safe_context = dict(context)
        safe_context["missing_infoTypes"] = missing
        safe_context["previous_answer"] = final_answer
        try:
            final_answer = _call_answer_llm(llm_answer, safe_prompt, safe_context)
            answer_source = "llm_safe"
        except Exception as exc:
            llm_error = f"{type(exc).__name__}: {exc}"
            logger.exception("Safe-answer LLM call failed; using generic fallback.")
            answer_source = "fallback_generic_safe"
            final_answer = _fallback_final_answer(context)
        final_answer = _ensure_non_empty_content(final_answer)
        validate_final_answer(final_answer)

    state["final_answer"] = final_answer
    state["answer_generation_meta"] = {"source": answer_source, "llm_error": llm_error}
    return state
