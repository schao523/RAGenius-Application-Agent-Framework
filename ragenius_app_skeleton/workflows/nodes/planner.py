"""Node E: planner with function calling create_planner_output."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Protocol

from backend.openai_tools import get_openai_tools
from backend.app.llm_context_optimization import build_planner_context, compact_hybrid_decision_packet, optimize_context_for_state
from backend.schemas import validate_planner_output

from ..graph_state import GraphState
from ..runtime_models import (
    InstructionScopeSelection,
    InstructionResourceLoadPlan,
    PrimarySupportModuleActivation,
    PresentationPolicy,
    ProcedureStepActivation,
    RetrievalDomainPlan,
    ResourceRequest,
    SessionExecutionState,
    TurnAction,
    TurnActionPlan,
    TurnExecutionPlan,
    to_plain_dict,
)

PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"
PROMPT_INTENT = PROMPT_DIR / "planner_intent_prompt.txt"
PROMPT_STEPS = PROMPT_DIR / "planner_steps_prompt.txt"
PROMPT_RETRIEVAL = PROMPT_DIR / "planner_retrievalplan_prompt.txt"
PROMPT_FALLBACK = PROMPT_DIR / "planner_fallback_prompt.txt"
HYBRID_PLANNER_SYSTEM_PROMPT = (
    "You are the planner-routing model for a compiled application contract. "
    "You are not interpreting raw instructions. Choose only among the supplied candidates and ids. "
    "Return JSON only. Do not invent workflows, roles, modules, steps, resources, or ids."
)
HYBRID_PLANNER_TOOL = {
    "name": "create_hybrid_planner_decision",
    "parameters": {
        "type": "object",
        "properties": {
            "intent_label": {"type": "string"},
            "confidence": {"type": "number"},
            "continue_current_scope": {"type": "boolean"},
            "selected_role_id": {"type": ["string", "null"]},
            "selected_workflow_id": {"type": ["string", "null"]},
            "selected_support_module_ids": {"type": "array", "items": {"type": "string"}},
            "selected_followup_module_ids": {"type": "array", "items": {"type": "string"}},
            "selected_supplementary_workflow_id": {"type": ["string", "null"]},
            "module_sequence": {"type": "array", "items": {"type": "string"}},
            "clarification_status": {"type": "object"},
            "next_action": {"type": "object"},
            "reasoning_summary": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "intent_label",
            "confidence",
            "continue_current_scope",
            "selected_role_id",
            "selected_workflow_id",
            "selected_support_module_ids",
            "selected_followup_module_ids",
            "selected_supplementary_workflow_id",
            "module_sequence",
            "clarification_status",
            "next_action",
            "reasoning_summary",
        ],
    },
}


class PlannerRepoProtocol(Protocol):
    def save(self, session_id: str, user_query: str, planner_output: Dict[str, Any]) -> Dict[str, Any]:
        ...


def _read_prompt(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8", errors="ignore")


def _build_main_prompt(state: GraphState) -> str:
    intent_prompt = _read_prompt(PROMPT_INTENT)
    steps_prompt = _read_prompt(PROMPT_STEPS)
    retrieval_prompt = _read_prompt(PROMPT_RETRIEVAL)

    adapter_json = state.get("adapter_json", {})
    intent_overrides = adapter_json.get("intent_overrides", [])
    skeleton_mapping = adapter_json.get("step_skeleton_mapping", {})

    return "\n\n".join(
        [
            intent_prompt,
            "Adapter intent_overrides:\n" + json.dumps(intent_overrides, ensure_ascii=False, indent=2),
            steps_prompt,
            "Adapter step_skeleton_mapping:\n" + json.dumps(skeleton_mapping, ensure_ascii=False, indent=2),
            retrieval_prompt,
        ]
    )


def _build_fallback_prompt(state: GraphState) -> str:
    fallback_prompt = _read_prompt(PROMPT_FALLBACK)
    return "\n\n".join(
        [
            fallback_prompt,
            "User query:\n" + str(state.get("user_query", "")),
        ]
    )


def _default_planner_output(state: GraphState) -> Dict[str, Any]:
    query = str(state.get("user_query", ""))
    app_id = str(state.get("collection_id") or "").strip()
    return {
        "intentType": "qa",
        "confidence": 0.8,
        "steps": [{"id": "1", "title": "Retrieve", "goal": "Answer", "reasoning": None}],
        "infoTypes": ["fact"],
        "retrievalPlan": {
            "query_text": query,
            "top_k": 3,
            "filters": {"app_id": app_id} if app_id else {},
            "explanation": None,
        },
        "systemInstructionSummary": {"fromConfigPdf": [], "fromAdapter": [], "fromTemplate": []},
        "normalizedQuery": query,
        "contextualQuery": query,
    }


def _call_planner(
    llm_planner: Callable[[str, list, Dict[str, Any]], Dict[str, Any]],
    prompt: str,
    state: GraphState,
) -> Dict[str, Any]:
    tools = [t for t in get_openai_tools(include_optional=False) if t["name"] == "create_planner_output"]
    context = {
        "user_query": state.get("user_query"),
        "turn_input_type": state.get("turn_input_type"),
        "session_upload_event_ids": state.get("session_upload_event_ids", []),
        "chat_history": state.get("chat_history", []),
        "session_uploads": state.get("session_uploads", []),
        "app_id": state.get("collection_id"),
        "collection_id": state.get("collection_id"),
        "config_json": state.get("config_json", {}),
        "adapter_json": state.get("adapter_json", {}),
        "template_registry": state.get("template_registry", {}),
    }
    optimized = optimize_context_for_state(
        state,
        task="planner",
        prompt=prompt,
        tools=tools,
        full_context=context,
        compact_context=build_planner_context(state),
    )
    return llm_planner(prompt, tools, optimized.context)


def _stringify_instruction_summary_item(item: Any) -> str | None:
    if isinstance(item, str):
        text = item.strip()
        return text or None
    if isinstance(item, dict):
        alias_intent = str(item.get("alias_intent") or "").strip()
        mapped_intent = str(item.get("maps_to_base_intent") or "").strip()
        triggers = [
            str(trigger).strip()
            for trigger in item.get("triggers", []) or item.get("triggers_from_config", []) or []
            if str(trigger).strip()
        ]
        parts = []
        if alias_intent:
            parts.append(alias_intent)
        if mapped_intent and mapped_intent != alias_intent:
            parts.append(f"maps_to:{mapped_intent}")
        if triggers:
            parts.append(f"triggers:{', '.join(triggers)}")
        if parts:
            return " | ".join(parts)
        try:
            return json.dumps(item, ensure_ascii=False, sort_keys=True)
        except Exception:
            return str(item)
    if item is None:
        return None
    text = str(item).strip()
    return text or None


def _normalize_planner_output(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    summary = payload.get("systemInstructionSummary")
    if not isinstance(summary, dict):
        return payload
    normalized_summary = dict(summary)
    for key in ("fromConfigPdf", "fromAdapter", "fromTemplate"):
        values = normalized_summary.get(key, [])
        if not isinstance(values, list):
            values = [values]
        normalized_values = []
        for item in values:
            text = _stringify_instruction_summary_item(item)
            if text:
                normalized_values.append(text)
        normalized_summary[key] = normalized_values
    payload["systemInstructionSummary"] = normalized_summary
    return payload


def _compiled_hybrid_runtime_model(state: GraphState) -> dict[str, Any]:
    registry = state.get("template_registry", {}) or {}
    compiled = registry.get("compiled_instruction_understanding", {}) or {}
    if not isinstance(compiled, dict):
        return {}
    hybrid = compiled.get("hybrid_instruction_runtime_model", {})
    return hybrid if isinstance(hybrid, dict) else {}


def _build_hybrid_turn_decision_packet(state: GraphState) -> dict[str, Any]:
    hybrid = _compiled_hybrid_runtime_model(state)
    session_state = state.get("session_execution_state", {}) or {}
    workflow_progress = state.get("workflow_progress", {}) or {}
    procedures = hybrid.get("instruction_procedures", []) or hybrid.get("procedures", []) or []
    steps = hybrid.get("procedure_steps", []) or []
    return {
        "task": "turn_intent_and_next_action_inference",
        "app": {
            "app_id": state.get("collection_id"),
            "app_name": (state.get("template_registry", {}) or {}).get("builder_app", {}).get("name"),
            "mission": (hybrid.get("global_app_contract", {}) or {}).get("mission"),
            "objective": (hybrid.get("global_app_contract", {}) or {}).get("objective"),
            "constraints": list((hybrid.get("global_app_contract", {}) or {}).get("constraints", []) or []),
            "security_rules": list((hybrid.get("global_app_contract", {}) or {}).get("security_rules", []) or []),
            "boundaries": list((hybrid.get("global_app_contract", {}) or {}).get("boundaries", []) or []),
        },
        "interaction_logic": [
            {
                "logic_id": item.get("logic_id"),
                "scope": item.get("scope"),
                "summary_rules": [rule.get("expression") for rule in item.get("rules", []) if isinstance(rule, dict) and str(rule.get("expression") or "").strip()],
            }
            for item in hybrid.get("interaction_logic_blocks", []) or []
            if isinstance(item, dict)
        ],
        "session_state": {
            "active_role_id": session_state.get("active_role_id"),
            "active_workflow_id": workflow_progress.get("workflow_id") or session_state.get("active_workflow"),
            "active_service_block_id": session_state.get("active_service_block_id"),
            "active_service_block_type": session_state.get("active_service_block_type"),
            "active_step_id": session_state.get("active_step_scope_id"),
            "active_execution_mode": session_state.get("active_execution_mode"),
            "active_module_queue": list(session_state.get("active_module_queue", []) or []),
            "current_module_index": int(session_state.get("current_module_index") or 0),
            "filled_slots": dict((session_state.get("clarification_gate_status") or {}).get("filled_slots_map", {}) or {}),
            "waiting_for_user": str(session_state.get("execution_status") or "") == "waiting_user",
            "prior_output_roles": list(session_state.get("output_artifact_targets", []) or []),
            "supplementary_workflow_active": str(session_state.get("active_service_block_type") or "") == "supplementary_workflow",
        },
        "conversation": {
            "last_assistant_message": (_conversation_assistant_messages(state) or [None])[-1],
            "latest_user_message": str(state.get("user_query") or ""),
            "recent_summary": str(state.get("workflow_progress") or ""),
        },
        "candidates": {
            "roles": list(hybrid.get("role_profiles", []) or []),
            "workflows": [
                item for item in (hybrid.get("instruction_service_blocks", []) or hybrid.get("service_blocks", []) or [])
                if isinstance(item, dict) and str(item.get("block_type") or "").strip() in {"primary_workflow", "entry_mode"}
            ],
            "support_modules": [
                item for item in (hybrid.get("instruction_service_blocks", []) or hybrid.get("service_blocks", []) or [])
                if isinstance(item, dict) and str(item.get("block_type") or "").strip() == "support_module"
            ],
            "followup_modules": [
                item for item in (hybrid.get("instruction_service_blocks", []) or hybrid.get("service_blocks", []) or [])
                if isinstance(item, dict) and str(item.get("block_type") or "").strip() == "followup_module"
            ],
            "supplementary_workflows": [
                item for item in (hybrid.get("instruction_service_blocks", []) or hybrid.get("service_blocks", []) or [])
                if isinstance(item, dict) and str(item.get("block_type") or "").strip() == "supplementary_workflow"
            ],
            "reachable_steps": [item for item in steps if isinstance(item, dict)],
            "procedures": [item for item in procedures if isinstance(item, dict)],
        },
        "routing_rules": list(hybrid.get("routing_rules", []) or []),
        "module_orchestration": hybrid.get("module_orchestration", {}) or {},
        "clarification_gate": (hybrid.get("clarification_gate_rules", []) or [None])[0] or {},
        "required_output": {
            "classify_intent": True,
            "select_role": True,
            "select_target_scope": True,
            "decide_continue_or_switch": True,
            "decide_clarification_complete": True,
            "decide_next_execution_unit": True,
        },
    }


def _call_hybrid_planner_shadow(
    llm_planner_hybrid: Callable[[str, list, Dict[str, Any]], Dict[str, Any]],
    packet: Dict[str, Any],
    state: GraphState,
) -> Dict[str, Any]:
    prompt = "\n\n".join(
        [
            HYBRID_PLANNER_SYSTEM_PROMPT,
            "Task: infer user-turn intent and decide the next planner action using the compiled application contract.",
            "Return JSON only using the provided tool schema.",
        ]
    )
    tools = [HYBRID_PLANNER_TOOL]
    optimized = optimize_context_for_state(
        state,
        task="planner_hybrid",
        prompt=prompt,
        tools=tools,
        full_context={"decision_packet": packet},
        compact_context={"decision_packet": compact_hybrid_decision_packet(packet)},
    )
    return llm_planner_hybrid(prompt, tools, optimized.context)


def _enforce_app_scoped_retrieval(state: GraphState, planner_output: Dict[str, Any]) -> Dict[str, Any]:
    fixed = dict(planner_output)
    retrieval_plan = dict(fixed.get("retrievalPlan", {}) or {})
    filters = retrieval_plan.get("filters", {})
    if not isinstance(filters, dict):
        filters = {}

    app_id = str(state.get("collection_id") or "").strip()
    if app_id:
        filters["app_id"] = app_id

    retrieval_plan["filters"] = filters
    if "top_k" not in retrieval_plan:
        retrieval_plan["top_k"] = 3
    fixed["retrievalPlan"] = retrieval_plan
    return fixed


def _combined_query_text(state: GraphState, planner_output: Dict[str, Any]) -> str:
    return " ".join(
        [
            str(state.get("user_query", "")),
            str(planner_output.get("normalizedQuery", "")),
            str(planner_output.get("contextualQuery", "")),
        ]
    ).lower()


def _chat_history_messages(state: GraphState, role: str | None = None) -> list[str]:
    history = state.get("chat_history", [])
    if not isinstance(history, list):
        return []
    messages: list[str] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        if role is not None and str(item.get("role") or "").strip().lower() != role:
            continue
        content = str(item.get("content") or "").strip()
        if content:
            messages.append(content)
    return messages


def _conversation_user_messages(state: GraphState, current_query: str) -> list[str]:
    messages = _chat_history_messages(state, role="user")
    current = str(current_query or "").strip()
    if current:
        messages.append(current)
    return messages


def _explicit_current_user_query(state: GraphState, current_query: str = "") -> str:
    explicit = str(state.get("user_query") or "").strip()
    if explicit:
        return explicit
    return str(current_query or "").strip()


def _conversation_assistant_messages(state: GraphState) -> list[str]:
    return _chat_history_messages(state, role="assistant")


def _workflow_steps(workflow: Dict[str, Any]) -> list[Dict[str, Any]]:
    steps = workflow.get("steps", [])
    if not isinstance(steps, list):
        return []
    return sorted(
        [step for step in steps if isinstance(step, dict)],
        key=lambda step: int(step.get("order") or 9999),
    )


def _derive_step_keywords(step: Dict[str, Any]) -> list[str]:
    keywords = []
    for field in ("keywords",):
        values = step.get(field, [])
        if isinstance(values, list):
            keywords.extend(str(v or "").strip().lower() for v in values if str(v or "").strip())

    title = str(step.get("title", "")).strip().lower()
    resource = str(step.get("resource_file") or step.get("primary_resource") or "").strip().lower()
    if title:
        keywords.append(title)
        for token in title.replace("(", " ").replace(")", " ").split("/"):
            token = " ".join(token.split()).strip().lower()
            if token:
                keywords.append(token)
    if resource:
        keywords.append(resource)
        stem = Path(resource).stem.lower()
        keywords.append(stem)
        keywords.append(stem.replace("_", " "))

    return sorted({token for token in keywords if token})


def _looks_like_step_advance(query: str) -> bool:
    markers = [
        "下一步",
        "下一個",
        "下一阶段",
        "下一階段",
        "接下來",
        "接著",
        "繼續",
        "然后",
        "然後",
        "move on",
        "next step",
        "continue",
        "proceed",
    ]
    return any(marker in query for marker in markers)


def _has_audience_signal(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    return any(marker in lowered for marker in AUDIENCE_SIGNAL_MARKERS)


def _has_topic_signal(text: str) -> bool:
    candidate = str(text or "").strip()
    if not candidate:
        return False
    lowered = candidate.lower()
    if any(marker.lower() in lowered for marker in TOPIC_SIGNAL_MARKERS):
        return True
    return _query_specifies_passage(candidate)


def _has_goal_signal(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    return any(marker in lowered for marker in GOAL_SIGNAL_MARKERS)


def _query_specifies_passage(query: str) -> bool:
    text = str(query or "")
    if not text.strip():
        return False
    if re.search(r"\d+\s*[:：]\s*\d+", text):
        return True
    if "章" in text or "節" in text:
        return True
    if re.search(r"(書|福音|詩篇|前書|後書)", text):
        return True
    return False


def _query_requests_scripture_study(query: str) -> bool:
    text = str(query or "").strip().lower()
    if not text:
        return False
    if _query_specifies_passage(query):
        return True
    return any(
        token in text
        for token in (
            "查經",
            "查经",
            "查考",
            "經文",
            "经文",
            "scripture",
            "bible study",
        )
    )


AUDIENCE_SIGNAL_MARKERS = [
    "audience",
    "受眾",
    "受众",
    "對象",
    "对象",
    "給",
    "给",
    "for ",
    "同工",
    "慕道友",
    "領袖",
    "领袖",
    "牧者",
    "家長",
    "家长",
    "父母",
    "學生",
    "学生",
    "青少年",
    "兒童",
    "儿童",
    "leaders",
    "leader",
    "pastors",
    "pastor",
    "parents",
    "students",
    "youth",
    "teachers",
]

TOPIC_SIGNAL_MARKERS = [
    "主題",
    "主题",
    "theme",
    "topic",
    "經文",
    "经文",
    "scripture",
    "passage",
]

GOAL_SIGNAL_MARKERS = [
    "goal",
    "目標",
    "目标",
    "目的",
    "幫助",
    "帮助",
    "讓",
    "让",
    "為了",
    "为了",
]


GENERATION_INTENT_MARKERS = [
    "prompt",
    "提示詞",
    "提示词",
    "生成",
    "產生",
    "优化",
    "優化",
    "改寫",
    "改写",
    "重寫",
    "重写",
    "精煉",
    "精炼",
    "修訂",
    "修订",
    "写一份",
    "寫一份",
    "設計一份",
    "设计一份",
    "整理成",
    "準備一份",
    "准备一份",
    "給我一份",
    "给我一份",
    "請生成",
    "请生成",
    "查經材料",
    "查经材料",
    "討論材料",
    "讨论材料",
    "講章",
    "讲章",
    "教案",
    "課程",
    "课程",
    "分享稿",
    "大綱",
    "大纲",
    "generate",
    "create",
    "produce",
    "draft",
    "write",
    "prepare",
    "optimize",
    "optimise",
    "refine",
    "revise",
    "rewrite",
    "improve",
    "outline",
    "discussion guide",
    "lesson plan",
    "study material",
]

STRUCTURED_BRIEF_MARKERS = [
    "用途",
    "目標",
    "目标",
    "基本資料",
    "基本资料",
    "輸出要求",
    "输出要求",
    "語氣與風格",
    "语气与风格",
    "purpose",
    "objective",
    "background",
    "output requirements",
    "tone",
    "audience",
    "duration",
]

GENERAL_OUT_OF_SCOPE_MARKERS = [
    "python",
    "pydantic",
    "dataclass",
    "javascript",
    "typescript",
    "react",
    "sql",
    "weather",
    "天氣",
    "天气",
    "股票",
    "股價",
    "股价",
    "量子",
    "quantum",
    "crawler",
    "爬蟲",
    "爬虫",
    "resume",
    "履歷",
    "简历",
]


def _app_scope_phrases(state: GraphState) -> list[str]:
    phrases: list[str] = []
    registry = state.get("template_registry", {}) or {}
    runtime_model = state.get("instruction_runtime_model", {}) or {}

    for text in (
        state.get("full_instruction_text"),
        registry.get("builder_instructions"),
    ):
        if isinstance(text, str) and text.strip():
            phrases.extend(re.findall(r"[A-Za-z][A-Za-z\s-]{2,}|[\u4e00-\u9fff]{2,}", text))

    for collection in (
        registry.get("instruction_workflows", []),
        registry.get("instruction_modules", []),
        registry.get("instruction_blocks", []),
        registry.get("builder_documents", []),
        state.get("instruction_scope_candidates", []),
        runtime_model.get("mode_rules", []),
        runtime_model.get("support_modules", []),
    ):
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            for key in ("title", "workflow_name", "objective", "notes"):
                value = str(item.get(key) or "").strip()
                if value:
                    phrases.append(value)
            for key in ("filename", "primary_resource"):
                value = Path(str(item.get(key) or "").strip()).stem
                if value:
                    phrases.append(value)
            for key in ("triggers", "keywords", "activation_triggers", "activation_signals"):
                values = item.get(key, [])
                if isinstance(values, list):
                    phrases.extend(str(value).strip() for value in values if str(value).strip())

    primary_objectives = runtime_model.get("primary_objectives", [])
    if isinstance(primary_objectives, list):
        phrases.extend(str(item).strip() for item in primary_objectives if str(item).strip())
    return list(dict.fromkeys(phrase for phrase in phrases if phrase))


def _scope_tokens(state: GraphState) -> set[str]:
    tokens: set[str] = set()
    for phrase in _app_scope_phrases(state):
        for part in re.split(r"[^\w\u4e00-\u9fff]+", str(phrase or "").lower()):
            token = part.strip()
            if len(token) >= 2:
                tokens.add(token)
    return tokens


def _has_generation_intent(
    user_text: str,
    chat_history: list[dict[str, Any]] | None,
    instruction_context: dict[str, Any] | None,
) -> bool:
    _ = (chat_history, instruction_context)
    query = str(user_text or "").strip().lower()
    if not query:
        return False
    if any(marker.lower() in query for marker in GENERATION_INTENT_MARKERS):
        return True
    return bool(
        re.search(
            r"(ç”Ÿæˆ|ç”¢ç”Ÿ|å¯«|è®¾è®¡|è¨­è¨ˆ|æ•´ç†|å‡†å¤‡|æº–å‚™|create|generate|produce|draft|write).{0,12}"
            r"(ææ–™|æ•™æ¡ˆ|è¬›ç« |è®²ç« |èª²ç¨‹|è¯¾ç¨‹|å¤§ç¶±|å¤§çº²|guide|plan|outline|material)",
            query,
            flags=re.IGNORECASE,
        )
    )


def _looks_like_structured_generation_brief(
    user_text: str,
    chat_history: list[dict[str, Any]] | None,
    instruction_context: dict[str, Any] | None,
) -> bool:
    _ = (chat_history, instruction_context)
    text = str(user_text or "").strip()
    if not text:
        return False
    lowered = text.lower()
    marker_hits = sum(1 for marker in STRUCTURED_BRIEF_MARKERS if marker.lower() in lowered)
    numbered_sections = len(re.findall(r"(?m)^\s*\d+\.\s+", text))
    colon_fields = len(re.findall(r"(?m)^[^\n:ï¼š]{1,20}[:ï¼š]\s*.+$", text))
    bullet_lines = len(re.findall(r"(?m)^\s*[-*â€¢]\s+", text))
    return marker_hits >= 2 or numbered_sections >= 2 or colon_fields >= 3 or (marker_hits >= 1 and bullet_lines >= 2)


def _is_app_scoped_query(
    user_text: str,
    instruction_context: dict[str, Any],
    session_state: dict[str, Any],
    state: GraphState,
) -> bool:
    query = str(user_text or "").strip()
    if not query:
        return True
    if isinstance(session_state, dict):
        if any(
            str(session_state.get(key) or "").strip()
            for key in ("active_mode", "active_workflow", "active_step_title")
        ):
            return True
    workflow_progress = state.get("workflow_progress", {}) or {}
    if isinstance(workflow_progress, dict) and any(
        str(workflow_progress.get(key) or "").strip()
        for key in ("workflow_id", "workflow_title", "step_title")
    ):
        return True

    lowered = query.lower()
    scope_phrases = _app_scope_phrases(state)
    for phrase in scope_phrases:
        candidate = str(phrase or "").strip().lower()
        if not candidate:
            continue
        if candidate in lowered:
            return True

    if _query_specifies_passage(query):
        return True
    if _has_generation_intent(query, state.get("chat_history", []), instruction_context):
        return any(
            token in query
            for token in ("ç¶“", "ç»", "è–ç¶“", "åœ£ç»", "æŸ¥ç¶“", "æŸ¥ç»", "è¬›ç« ", "è®²ç« ", "æ•™æ¡ˆ", "å°çµ„", "å°ç»„")
        )
    foreign_marker_hit = any(marker in lowered for marker in GENERAL_OUT_OF_SCOPE_MARKERS)
    if foreign_marker_hit:
        query_tokens = {
            token
            for token in re.split(r"[^\w\u4e00-\u9fff]+", lowered)
            if len(token.strip()) >= 2
            for token in [token.strip()]
        }
        if query_tokens & _scope_tokens(state):
            return True
        return False
    return True


def _classify_pre_routing_turn(state: GraphState, planner_output: Dict[str, Any]) -> Dict[str, Any]:
    user_text = str(
        planner_output.get("normalizedQuery")
        or planner_output.get("contextualQuery")
        or state.get("user_query")
        or ""
    ).strip()
    instruction_context = state.get("global_instruction_context", {}) or {}
    session_state = state.get("session_execution_state", {}) or {}
    has_generation_intent = _has_generation_intent(
        user_text,
        state.get("chat_history", []),
        instruction_context,
    )
    app_scoped = _is_app_scoped_query(user_text, instruction_context, session_state, state)
    if not app_scoped:
        return {
            "turn_intent": "general_out_of_scope_question",
            "skip_workflow_selection": True,
            "is_generation_request": False,
            "generation_subtype": None,
            "is_app_scoped": False,
        }
    if has_generation_intent:
        structured = _looks_like_structured_generation_brief(
            user_text,
            state.get("chat_history", []),
            instruction_context,
        )
        if _default_workflow_prefers_interactive_entry(state):
            return {
                "turn_intent": None,
                "skip_workflow_selection": False,
                "is_generation_request": True,
                "generation_subtype": "structured" if structured else "freeform",
                "is_app_scoped": True,
            }
        return {
            "turn_intent": "structured_generation_brief" if structured else "freeform_generation_request",
            "skip_workflow_selection": True,
            "is_generation_request": True,
            "generation_subtype": "structured" if structured else "freeform",
            "is_app_scoped": True,
        }
    return {
        "turn_intent": None,
        "skip_workflow_selection": False,
        "is_generation_request": False,
        "generation_subtype": None,
        "is_app_scoped": True,
    }


def _find_step_by_order(steps: list[Dict[str, Any]], order: int | None) -> Dict[str, Any] | None:
    if order is None:
        return None
    for step in steps:
        step_order = step.get("order")
        if step_order is None:
            continue
        if int(step_order) == int(order):
            return step
    return None


def _procedure_step_definition_for_scope(state: GraphState, step_scope_id: str) -> Dict[str, Any] | None:
    target = str(step_scope_id or "").strip()
    if not target:
        return None
    runtime_model = state.get("instruction_runtime_model", {}) or {}
    for item in runtime_model.get("procedure_steps", []) or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("step_id") or "").strip() == target:
            return item
    hybrid = _compiled_hybrid_runtime_model(state)
    for item in hybrid.get("procedure_steps", []) or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("step_id") or "").strip() == target:
            return item
    return None


def _matching_clarification_gate_rule(
    state: GraphState,
    current_step_definition: Dict[str, Any] | None,
    next_step_definition: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    if not isinstance(current_step_definition, dict) or not current_step_definition:
        return None
    if not isinstance(next_step_definition, dict) or not next_step_definition:
        return None
    hybrid = _compiled_hybrid_runtime_model(state)
    clarification_step_id = str(current_step_definition.get("step_id") or "").strip()
    completion_step_id = str(next_step_definition.get("step_id") or "").strip()
    procedure_id = str(current_step_definition.get("procedure_id") or "").strip()
    for item in hybrid.get("clarification_gate_rules", []) or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("clarification_step_id") or "").strip() != clarification_step_id:
            continue
        if procedure_id and str(item.get("procedure_id") or "").strip() not in {"", procedure_id}:
            continue
        expected_completion_step_id = str(item.get("completion_step_id") or "").strip()
        if expected_completion_step_id and expected_completion_step_id != completion_step_id:
            continue
        return item
    return None


def _clarification_gate_satisfied_from_session_state(state: GraphState, gate_rule: Dict[str, Any] | None) -> bool:
    session_state = state.get("session_execution_state", {}) or {}
    gate_status = session_state.get("clarification_gate_status", {}) if isinstance(session_state, dict) else {}
    filled_slots_map = gate_status.get("filled_slots_map", {}) if isinstance(gate_status, dict) else {}
    if not isinstance(filled_slots_map, dict):
        filled_slots_map = {}
    filled_slot_names = {
        str(name).strip()
        for name, value in filled_slots_map.items()
        if str(name).strip() and bool(value)
    }
    effective_filled_slot_names = _effective_clarification_slot_names(filled_slot_names)
    if not isinstance(gate_rule, dict):
        gate_rule = {}
    slot_policy = gate_rule.get("slot_policy", {})
    if not isinstance(slot_policy, dict):
        slot_policy = {}
    mode = str(slot_policy.get("mode") or "").strip() or "threshold"
    if mode == "explicit_required_slots":
        required_slots = [
            str(item).strip()
            for item in slot_policy.get("required_slots", []) or []
            if str(item).strip()
        ]
        return bool(required_slots) and all(slot in filled_slot_names for slot in required_slots)
    minimum_filled_slots = slot_policy.get("minimum_filled_slots")
    if minimum_filled_slots is None:
        minimum_filled_slots = gate_rule.get("minimum_filled_slots")
    if minimum_filled_slots is None and isinstance(gate_status, dict):
        minimum_filled_slots = gate_status.get("minimum_filled_slots")
    try:
        threshold = int(minimum_filled_slots or 0)
    except (TypeError, ValueError):
        threshold = 0
    if threshold <= 0 and filled_slot_names:
        threshold = 3
    return len(effective_filled_slot_names) >= threshold if threshold > 0 else False


def _clarification_slot_signal_map(state: GraphState, current_query: str) -> Dict[str, bool]:
    session_state = state.get("session_execution_state", {}) or {}
    gate_status = session_state.get("clarification_gate_status", {}) or {}
    filled_slots_map = gate_status.get("filled_slots_map", {}) if isinstance(gate_status, dict) else {}
    merged: Dict[str, bool] = {}
    if isinstance(filled_slots_map, dict):
        for name, value in filled_slots_map.items():
            cleaned_name = str(name).strip()
            if cleaned_name and bool(value):
                merged[cleaned_name] = True
    explicit_messages = _chat_history_messages(state, role="user")
    current_explicit_query = _explicit_current_user_query(state, current_query)
    if current_explicit_query:
        explicit_messages.append(current_explicit_query)
    for message in explicit_messages:
        if _has_topic_signal(message):
            merged["theme"] = True
        if _query_specifies_passage(message):
            merged["passage"] = True
        if _has_audience_signal(message):
            merged["audience"] = True
        if _has_goal_signal(message):
            merged["goal"] = True
    return merged


def _workflow_for_step_scope_id(state: GraphState, step_scope_id: str) -> Dict[str, Any] | None:
    target_step_scope_id = str(step_scope_id or "").strip()
    if not target_step_scope_id:
        return None
    registry = state.get("template_registry", {}) or {}
    workflows = registry.get("instruction_workflows", [])
    if not isinstance(workflows, list):
        return None
    for workflow in workflows:
        if not isinstance(workflow, dict):
            continue
        for step in _workflow_steps(workflow):
            if str(step.get("step_scope_id") or "").strip() == target_step_scope_id:
                return workflow
    return None


def _effective_clarification_slot_names(slot_names: set[str]) -> set[str]:
    effective: set[str] = set()
    for item in slot_names:
        cleaned = str(item).strip().lower()
        if not cleaned:
            continue
        if cleaned in {"theme", "topic", "passage", "scripture", "content"}:
            effective.add("content")
            continue
        effective.add(cleaned)
    return effective


def _clarification_targets_satisfied(
    state: GraphState,
    current_query: str,
) -> bool:
    filled_slot_names = {
        str(name).strip()
        for name, value in _clarification_slot_signal_map(state, current_query).items()
        if str(name).strip() and bool(value)
    }
    effective_filled_slot_names = _effective_clarification_slot_names(filled_slot_names)
    return len(effective_filled_slot_names) >= 3


def _current_turn_answers_clarification_prompt(state: GraphState, current_query: str) -> bool:
    assistant_messages = _conversation_assistant_messages(state)
    if not assistant_messages:
        return False
    last_assistant = assistant_messages[-1].lower()
    query = str(current_query or "").strip()
    if not query:
        return False
    if any(token in last_assistant for token in ("經文", "经文", "主題", "主题", "scripture", "passage", "theme", "topic")):
        return _has_topic_signal(query)
    if any(token in last_assistant for token in ("受眾", "受众", "對象", "对象", "audience", "給誰", "给谁")):
        return _has_audience_signal(query)
    return False


def _should_enter_bundled_followup_step(
    state: GraphState,
    workflow: Dict[str, Any],
    current_step: Dict[str, Any] | None,
    current_query: str,
) -> Dict[str, Any] | None:
    if not isinstance(current_step, dict) or not current_step:
        return None
    steps = _workflow_steps(workflow)
    current_order = current_step.get("order")
    if current_order is None:
        return None
    next_step = _find_step_by_order(steps, int(current_order) + 1)
    if not isinstance(next_step, dict) or not next_step:
        return None
    current_step_definition = _procedure_step_definition_for_scope(
        state,
        str(current_step.get("step_scope_id") or "").strip(),
    )
    next_step_definition = _procedure_step_definition_for_scope(
        state,
        str(next_step.get("step_scope_id") or "").strip(),
    )
    if str((current_step_definition or {}).get("execution_mode") or "").strip() != "interactive":
        return None
    if str((next_step_definition or {}).get("execution_mode") or "").strip() != "bundled":
        return None
    clarification_gate_rule = _matching_clarification_gate_rule(
        state,
        current_step_definition,
        next_step_definition,
    )
    if _clarification_gate_satisfied_from_session_state(state, clarification_gate_rule):
        return next_step
    if _clarification_targets_satisfied(state, current_query):
        return next_step
    if not _current_turn_answers_clarification_prompt(state, current_query):
        return None
    return next_step




def _find_matching_step(steps: list[Dict[str, Any]], query: str) -> Dict[str, Any] | None:
    best_step = None
    best_score = 0
    for step in steps:
        score = 0
        for keyword in _derive_step_keywords(step):
            if keyword and keyword in query:
                score = max(score, len(keyword))
        if score > best_score:
            best_score = score
            best_step = step
    return best_step


def _select_instruction_workflow(state: GraphState, planner_output: Dict[str, Any]) -> Dict[str, Any] | None:
    registry = state.get("template_registry", {}) or {}
    hybrid_selected_workflow = _hybrid_active_selected_workflow(state)
    if isinstance(hybrid_selected_workflow, dict):
        return hybrid_selected_workflow
    if _hybrid_active_should_stay_logic_only(state, _hybrid_active_module_queue(state)):
        return None

    workflows = registry.get("instruction_workflows", [])
    if not isinstance(workflows, list) or not workflows:
        return None

    semantic_default_workflow = _semantic_default_instruction_workflow(state)
    if isinstance(semantic_default_workflow, dict):
        return semantic_default_workflow

    query = _combined_query_text(state, planner_output)
    if not query.strip():
        query = ""

    best_workflow = None
    best_score = 0
    for workflow in workflows:
        if not isinstance(workflow, dict):
            continue
        score = 0
        for keyword in workflow.get("triggers", []) or []:
            token = str(keyword or "").strip().lower()
            if token and token in query:
                score = max(score, len(token))
        if score > best_score:
            best_score = score
            best_workflow = workflow

    if best_workflow is not None:
        return best_workflow

    workflow_progress = state.get("workflow_progress", {}) or {}
    current_workflow_id = str(workflow_progress.get("workflow_id") or "").strip()
    if current_workflow_id:
        for workflow in workflows:
            if str(workflow.get("id") or "").strip() == current_workflow_id:
                return workflow
    supplementary_workflow = _supplementary_instruction_workflow_for_query(state, query)
    if isinstance(supplementary_workflow, dict):
        return supplementary_workflow
    default_workflow = _default_instruction_workflow(state)
    if isinstance(default_workflow, dict):
        return default_workflow
    return None


def _semantic_default_instruction_workflow(state: GraphState) -> Dict[str, Any] | None:
    registry = state.get("template_registry", {}) or {}
    workflows = registry.get("instruction_workflows", [])
    if not isinstance(workflows, list) or not workflows:
        return None
    hybrid = _compiled_hybrid_runtime_model(state)
    default_workflow_id = str(hybrid.get("default_workflow_id") or "").strip()
    if not default_workflow_id:
        return None
    return _instruction_workflow_by_reference(state, default_workflow_id)


def _default_workflow_prefers_interactive_entry(state: GraphState) -> bool:
    workflow = _semantic_default_instruction_workflow(state) or _default_instruction_workflow(state)
    if not isinstance(workflow, dict):
        return False
    steps = _workflow_steps(workflow)
    if not steps:
        return False
    first_step = steps[0]
    step_scope_id = str(first_step.get("step_scope_id") or "").strip()
    if not step_scope_id:
        return False
    step_definition = _procedure_step_definition_for_scope(state, step_scope_id) or {}
    if not isinstance(step_definition, dict):
        return False
    if str(step_definition.get("execution_mode") or "").strip() != "interactive":
        return False
    step_order = _normalize_int_like(step_definition.get("order"))
    return step_order in {0, 1, None}


def _instruction_step_block_for_workflow_step(
    state: GraphState,
    workflow_id: str,
    step_order: int | None,
) -> Dict[str, Any] | None:
    target_workflow_id = str(workflow_id or "").strip()
    if not target_workflow_id or step_order is None:
        return None
    for block in _instruction_blocks(state):
        if str(block.get("block_type") or "").strip() != "step":
            continue
        if str(block.get("linked_mode_id") or "").strip() != target_workflow_id:
            continue
        if _normalize_int_like(block.get("linked_step_order")) != step_order:
            continue
        return block
    return None


def _gate_step_threshold_from_block_text(block_text: str) -> int | None:
    text = str(block_text or "").strip()
    if not text:
        return None
    match = re.search(r"[>=≥]\s*(\d+)", text)
    if match:
        try:
            return int(match.group(1))
        except (TypeError, ValueError):
            return None
    return None


def _estimated_gate_slot_names(state: GraphState, current_query: str) -> set[str]:
    return {
        str(name).strip()
        for name, value in _clarification_slot_signal_map(state, current_query).items()
        if str(name).strip() and bool(value)
    }


def _collapse_control_gate_step(
    state: GraphState,
    workflow: Dict[str, Any] | None,
    selected_step: Dict[str, Any] | None,
    current_query: str,
) -> Dict[str, Any] | None:
    if not isinstance(workflow, dict) or not isinstance(selected_step, dict) or not selected_step:
        return selected_step
    step_order = _normalize_int_like(selected_step.get("order"))
    if step_order != 0:
        return selected_step
    workflow_id = str(workflow.get("id") or "").strip()
    step_title = str(selected_step.get("title") or "").strip().lower()
    step_scope_id = str(selected_step.get("step_scope_id") or "").strip()
    step_definition = _procedure_step_definition_for_scope(state, step_scope_id) or {}
    block = _instruction_step_block_for_workflow_step(state, workflow_id, 0)
    gate_text = " ".join(
        item
        for item in (
            str(selected_step.get("title") or "").strip(),
            str(step_definition.get("title") or "").strip(),
            str((block or {}).get("title") or "").strip(),
            str((block or {}).get("body_text") or "").strip(),
        )
        if item
    ).lower()
    if not (
        "input gate" in gate_text
        or "輸入完整度判斷" in gate_text
        or ("if" in gate_text and "else" in gate_text and "step 1" in gate_text and "step 2" in gate_text)
    ):
        return selected_step
    steps = _workflow_steps(workflow)
    clarification_step = _find_step_by_order(steps, 1)
    core_step = _find_step_by_order(steps, 2)
    if not isinstance(clarification_step, dict) or not isinstance(core_step, dict):
        return selected_step
    threshold = _gate_step_threshold_from_block_text(str((block or {}).get("body_text") or ""))
    if threshold is None:
        threshold = 3
    filled_slots = _estimated_gate_slot_names(state, current_query)
    effective_filled_slots = _effective_clarification_slot_names(filled_slots)
    resolved_step = core_step if len(effective_filled_slots) >= threshold else clarification_step
    resolved_step_scope_id = str(resolved_step.get("step_scope_id") or "").strip()
    if resolved_step_scope_id:
        state["_control_gate_resolved_step_scope_id"] = resolved_step_scope_id
    state["_clarification_gate_minimum_filled_slots"] = threshold
    return resolved_step


def _select_instruction_module(
    state: GraphState,
    planner_output: Dict[str, Any],
    workflow: Dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    hybrid_selected_module = _hybrid_active_selected_instruction_module(state)
    if isinstance(hybrid_selected_module, dict):
        workflow = workflow or _select_instruction_workflow(state, planner_output)
        query = _combined_query_text(state, planner_output)
        return _collapse_control_gate_step(state, workflow, hybrid_selected_module, query)

    workflow = workflow or _select_instruction_workflow(state, planner_output)
    if isinstance(workflow, dict):
        steps = _workflow_steps(workflow)
        if steps:
            query = _combined_query_text(state, planner_output)
            matched_step = _find_matching_step(steps, query)
            if matched_step is not None:
                return _collapse_control_gate_step(state, workflow, matched_step, query)

            workflow_progress = state.get("workflow_progress", {}) or {}
            current_workflow_id = str(workflow_progress.get("workflow_id") or "").strip()
            workflow_id = str(workflow.get("id") or "").strip()
            if current_workflow_id and _identifier_equivalent(current_workflow_id, workflow_id):
                current_order = workflow_progress.get("step_order")
                if _looks_like_step_advance(query):
                    current_step = _find_step_by_order(steps, int(current_order)) if current_order is not None else None
                    if current_step is not None:
                        next_step = _find_step_by_order(steps, int(current_step.get("order") or 0) + 1)
                        if next_step is not None:
                            return _collapse_control_gate_step(state, workflow, next_step, query)
                current_step = _find_step_by_order(steps, int(current_order)) if current_order is not None else None
                bundled_followup_step = _should_enter_bundled_followup_step(state, workflow, current_step, query)
                if bundled_followup_step is not None:
                    return _collapse_control_gate_step(state, workflow, bundled_followup_step, query)
                if current_step is not None:
                    return _collapse_control_gate_step(state, workflow, current_step, query)

            if _query_specifies_passage(query):
                return _collapse_control_gate_step(state, workflow, steps[0], query)
            hybrid = _compiled_hybrid_runtime_model(state)
            default_workflow_id = str(hybrid.get("default_workflow_id") or "").strip()
            workflow_id = str(workflow.get("id") or "").strip()
            if steps and (
                (default_workflow_id and _identifier_equivalent(default_workflow_id, workflow_id))
                or bool(_hybrid_active_selected_role_id(state))
            ):
                return _collapse_control_gate_step(state, workflow, steps[0], query)
            return None

    module_step = _module_owned_active_step_selection(state)
    if isinstance(module_step, dict):
        return module_step

    registry = state.get("template_registry", {}) or {}
    modules = registry.get("instruction_modules", [])
    if not isinstance(modules, list) or not modules:
        return None

    query = _combined_query_text(state, planner_output)
    if not query.strip():
        return None

    best_module = None
    best_score = 0
    for module in modules:
        if not isinstance(module, dict):
            continue
        score = 0
        for keyword in module.get("keywords", []) or []:
            token = str(keyword or "").strip().lower()
            if token and token in query:
                score = max(score, len(token))
        if score > best_score:
            best_score = score
            best_module = module

    return best_module


def _module_owned_active_step_selection(state: GraphState) -> Dict[str, Any] | None:
    session_state = state.get("session_execution_state", {}) or {}
    if not isinstance(session_state, dict):
        return None
    service_block_id = (
        str(session_state.get("active_service_block_id") or "").strip()
        or str(session_state.get("primary_support_module_id") or "").strip()
    )
    if not service_block_id:
        return None
    service_block = _service_block_by_id(state, service_block_id)
    if not isinstance(service_block, dict) or not service_block:
        return None
    procedure = _procedure_for_service_block_id(state, service_block_id)
    if not isinstance(procedure, dict) or not procedure:
        return None
    steps = _ordered_procedure_steps(state, str(procedure.get("procedure_id") or "").strip())
    if not steps:
        return None
    active_step_scope_id = str(session_state.get("active_step_scope_id") or "").strip()
    selected_step = None
    if active_step_scope_id:
        selected_step = next(
            (
                item
                for item in steps
                if str(item.get("step_id") or "").strip() == active_step_scope_id
            ),
            None,
        )
    if isinstance(selected_step, dict):
        query_text = str(state.get("user_query") or "").strip()
        if _looks_like_step_advance(query_text):
            current_order = _normalize_int_like(selected_step.get("order"))
            if current_order is not None:
                next_step = next(
                    (
                        item
                        for item in steps
                        if _normalize_int_like(item.get("order")) == current_order + 1
                    ),
                    None,
                )
                if isinstance(next_step, dict):
                    selected_step = next_step
    if not isinstance(selected_step, dict):
        selected_step = steps[0]
    step_id = str(selected_step.get("step_id") or "").strip()
    resource_refs = [
        str(item or "").strip()
        for item in selected_step.get("resource_refs", []) or []
        if str(item or "").strip()
    ]
    support_module_id = (
        str(service_block.get("block_id") or "").strip()
        if str(service_block.get("block_type") or "").strip() == "support_module"
        else ""
    )
    return {
        "step_scope_id": step_id,
        "order": _normalize_int_like(selected_step.get("order")),
        "title": str(selected_step.get("title") or "").strip() or None,
        "resource_file": resource_refs[0] if resource_refs else None,
        "primary_resource": resource_refs[0] if resource_refs else None,
        "execution_mode": str(selected_step.get("execution_mode") or "").strip() or None,
        "bundled_step_ids": [
            str(item or "").strip()
            for item in selected_step.get("bundled_step_ids", []) or []
            if str(item or "").strip()
        ],
        "bundled_resource_refs": [
            str(item or "").strip()
            for item in selected_step.get("bundled_resource_refs", []) or []
            if str(item or "").strip()
        ],
        "activation": {
            "direct_resource_files": list(resource_refs),
            "primary_support_module_id": support_module_id or None,
            "primary_support_module_title": str(service_block.get("title") or "").strip() or None,
        },
    }


def _shadow_target_step_selection(state: GraphState) -> Dict[str, Any] | None:
    planner_mode = str(state.get("planner_mode") or "").strip().lower()
    if planner_mode != "hybrid_active":
        return None
    shadow_output = state.get("hybrid_planner_shadow_output", {}) or {}
    if not isinstance(shadow_output, dict):
        return None
    next_action = shadow_output.get("next_action", {})
    if not isinstance(next_action, dict):
        return None
    target_step_id = str(next_action.get("target_step_id") or "").strip()
    if not target_step_id:
        return None
    step_definition = _procedure_step_definition_for_scope(state, target_step_id) or {}
    if not isinstance(step_definition, dict) or not step_definition:
        return None
    procedure_id = str(step_definition.get("procedure_id") or "").strip()
    procedure = _procedure_for_id(state, procedure_id) if procedure_id else None
    service_block_id = str(procedure.get("service_block_id") or "").strip() if isinstance(procedure, dict) else ""
    service_block = _service_block_by_id(state, service_block_id) if service_block_id else None
    block_type = str(service_block.get("block_type") or "").strip() if isinstance(service_block, dict) else ""
    resource_refs = [
        str(item or "").strip()
        for item in step_definition.get("resource_refs", []) or []
        if str(item or "").strip()
    ]
    bundled_resource_refs = [
        str(item or "").strip()
        for item in step_definition.get("bundled_resource_refs", []) or []
        if str(item or "").strip()
    ]
    selected_step = {
        "step_scope_id": target_step_id,
        "order": _normalize_int_like(step_definition.get("order")),
        "title": str(step_definition.get("title") or "").strip() or None,
        "resource_file": resource_refs[0] if resource_refs else None,
        "primary_resource": resource_refs[0] if resource_refs else None,
        "execution_mode": str(step_definition.get("execution_mode") or "").strip() or None,
        "bundled_step_ids": [
            str(item or "").strip()
            for item in step_definition.get("bundled_step_ids", []) or []
            if str(item or "").strip()
        ],
        "bundled_resource_refs": bundled_resource_refs,
        "activation": {
            "direct_resource_files": list(bundled_resource_refs or resource_refs),
            "primary_support_module_id": service_block_id if block_type == "support_module" else None,
            "primary_support_module_title": (
                str(service_block.get("title") or "").strip() or None
                if block_type == "support_module" and isinstance(service_block, dict)
                else None
            ),
        },
    }
    workflow = _workflow_for_step_scope_id(state, target_step_id)
    target_order = _normalize_int_like(selected_step.get("order"))
    if isinstance(workflow, dict) and target_order is not None and target_order > 0:
        gate_step = _find_step_by_order(_workflow_steps(workflow), 0)
        if isinstance(gate_step, dict):
            resolved_step = _collapse_control_gate_step(
                state,
                workflow,
                gate_step,
                _explicit_current_user_query(state),
            )
            resolved_order = _normalize_int_like((resolved_step or {}).get("order"))
            if (
                isinstance(resolved_step, dict)
                and resolved_order is not None
                and resolved_order < target_order
            ):
                return resolved_step
    return selected_step


def _instruction_blocks(state: GraphState) -> list[Dict[str, Any]]:
    registry = state.get("template_registry", {}) or {}
    blocks = registry.get("instruction_blocks", [])
    if not isinstance(blocks, list):
        return []
    return [block for block in blocks if isinstance(block, dict)]


def _instruction_units(state: GraphState) -> list[Dict[str, Any]]:
    registry = state.get("template_registry", {}) or {}
    units = registry.get("instruction_units", [])
    if not isinstance(units, list):
        return []
    return [unit for unit in units if isinstance(unit, dict)]


def _instruction_heading_tree(state: GraphState) -> list[Dict[str, Any]]:
    registry = state.get("template_registry", {}) or {}
    tree = registry.get("instruction_heading_tree", [])
    if not isinstance(tree, list):
        return []
    return [node for node in tree if isinstance(node, dict)]


def _instruction_service_blocks(state: GraphState) -> list[Dict[str, Any]]:
    runtime_model = state.get("instruction_runtime_model", {}) or {}
    blocks = runtime_model.get("instruction_service_blocks", [])
    if not isinstance(blocks, list):
        return []
    return [block for block in blocks if isinstance(block, dict)]


def _instruction_procedures(state: GraphState) -> list[Dict[str, Any]]:
    runtime_model = state.get("instruction_runtime_model", {}) or {}
    procedures = runtime_model.get("instruction_procedures", [])
    if not isinstance(procedures, list):
        return []
    return [procedure for procedure in procedures if isinstance(procedure, dict)]


def _procedure_for_id(state: GraphState, procedure_id: str) -> Dict[str, Any] | None:
    target = str(procedure_id or "").strip()
    if not target:
        return None
    for procedure in _instruction_procedures(state):
        if _identifier_equivalent(procedure.get("procedure_id"), target):
            return procedure
    return None


def _identifier_prefix_and_suffix(value: Any) -> tuple[str, str]:
    text = str(value or "").strip().lower()
    if ":" not in text:
        return "", text
    prefix, suffix = text.split(":", 1)
    return prefix.strip(), suffix.strip()


def _identifier_equivalent(left: Any, right: Any) -> bool:
    left_text = str(left or "").strip()
    right_text = str(right or "").strip()
    if not left_text or not right_text:
        return False
    if left_text.lower() == right_text.lower():
        return True

    left_variants = _scope_candidate_variants(left_text)
    right_variants = _scope_candidate_variants(right_text)
    if left_variants & right_variants:
        return True

    left_prefix, left_suffix = _identifier_prefix_and_suffix(left_text)
    right_prefix, right_suffix = _identifier_prefix_and_suffix(right_text)
    if left_prefix and right_prefix and left_prefix == right_prefix:
        left_slug = _normalize_slug(left_suffix)
        right_slug = _normalize_slug(right_suffix)
        if left_slug and right_slug and (
            left_slug == right_slug
            or left_slug.startswith(right_slug)
            or right_slug.startswith(left_slug)
        ):
            return True
        left_section = _normalize_section_name(left_suffix)
        right_section = _normalize_section_name(right_suffix)
        if left_section and right_section and (
            left_section == right_section
            or left_section.startswith(right_section)
            or right_section.startswith(left_section)
        ):
            return True
    return False


def _service_block_by_id(state: GraphState, block_id: str) -> Dict[str, Any] | None:
    target = str(block_id or "").strip()
    if not target:
        return None
    for block in _instruction_service_blocks(state):
        if str(block.get("block_id") or "").strip() == target:
            return block
    for block in _instruction_service_blocks(state):
        block_id_value = str(block.get("block_id") or "").strip()
        block_title_value = str(block.get("title") or "").strip()
        if _identifier_equivalent(block_id_value, target) or _identifier_equivalent(block_title_value, target):
            return block
    return None


def _service_block_heading_targets(service_block: Dict[str, Any]) -> set[str]:
    targets: set[str] = set()
    for value in (
        service_block.get("block_id"),
        service_block.get("title"),
    ):
        text = str(value or "").strip()
        if not text:
            continue
        targets.add(text)
        targets.add(_normalize_section_name(text))
        slug = _normalize_slug(text)
        if slug:
            targets.update(
                {
                    slug,
                    f"followup_module:{slug}",
                    f"primary_workflow:{slug}",
                    f"support_module:{slug}",
                    f"phase:{slug}",
                    f"output:{slug}",
                    f"starter:{slug}",
                    f"artifact_gate:{slug}",
                }
            )
    return {item for item in targets if str(item or "").strip()}


def _heading_node_targets(node: Dict[str, Any]) -> set[str]:
    title = str(node.get("title") or "").strip()
    normalized_title = str(node.get("normalized_title") or "").strip()
    targets: set[str] = set()
    for value in (title, normalized_title):
        text = str(value or "").strip()
        if not text:
            continue
        targets.add(text)
        targets.add(_normalize_section_name(text))
        slug = _normalize_slug(text)
        if slug:
            targets.update(
                {
                    slug,
                    f"followup_module:{slug}",
                    f"primary_workflow:{slug}",
                    f"support_module:{slug}",
                    f"phase:{slug}",
                    f"output:{slug}",
                    f"starter:{slug}",
                    f"artifact_gate:{slug}",
                }
            )
    return {item for item in targets if str(item or "").strip()}


def _descendant_heading_scope_markers_for_service_block(state: GraphState, service_block: Dict[str, Any]) -> list[str]:
    heading_tree = _instruction_heading_tree(state)
    if not heading_tree:
        return []

    service_targets = _service_block_heading_targets(service_block)
    matched_nodes: list[Dict[str, Any]] = []

    def _visit(nodes: list[Dict[str, Any]]) -> None:
        for node in nodes or []:
            if not isinstance(node, dict):
                continue
            node_targets = _heading_node_targets(node)
            if node_targets and any(
                _identifier_equivalent(node_target, service_target)
                for node_target in node_targets
                for service_target in service_targets
            ):
                matched_nodes.append(node)
            _visit(node.get("children", []) or [])

    _visit(heading_tree)
    if not matched_nodes:
        return []

    descendants: list[str] = []

    def _collect(node: Dict[str, Any], *, include_self: bool) -> None:
        if include_self:
            for value in (
                node.get("title"),
                node.get("normalized_title"),
            ):
                text = str(value or "").strip()
                if text:
                    _append_unique(descendants, text)
        for child in node.get("children", []) or []:
            if not isinstance(child, dict):
                continue
            _collect(child, include_self=True)

    for node in matched_nodes:
        _collect(node, include_self=False)

    return descendants


def _service_block_for_workflow(state: GraphState, workflow: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(workflow, dict) or not workflow:
        return None
    workflow_titles = [
        str(workflow.get("workflow_name") or "").strip(),
        str(workflow.get("title") or "").strip(),
    ]
    normalized_titles = {_normalize_section_name(title) for title in workflow_titles if title}
    if not normalized_titles:
        return None

    for procedure in _instruction_procedures(state):
        procedure_title = _normalize_section_name(str(procedure.get("title") or "").strip())
        if procedure_title and any(
            candidate == procedure_title or candidate in procedure_title or procedure_title in candidate
            for candidate in normalized_titles
        ):
            block = _service_block_by_id(state, str(procedure.get("service_block_id") or "").strip())
            if isinstance(block, dict):
                return block

    for block in _instruction_service_blocks(state):
        block_title = _normalize_section_name(str(block.get("title") or "").strip())
        if block_title and any(
            candidate == block_title or candidate in block_title or block_title in candidate
            for candidate in normalized_titles
        ):
            return block
    return None


def _default_instruction_workflow(state: GraphState) -> Dict[str, Any] | None:
    registry = state.get("template_registry", {}) or {}
    workflows = registry.get("instruction_workflows", [])
    if not isinstance(workflows, list) or not workflows:
        return None

    default_titles = {
        _normalize_section_name(str(procedure.get("title") or "").strip())
        for procedure in _instruction_procedures(state)
        if bool(procedure.get("is_default"))
    }
    if not default_titles:
        return None

    for workflow in workflows:
        if not isinstance(workflow, dict):
            continue
        workflow_title = _normalize_section_name(
            str(workflow.get("workflow_name") or workflow.get("title") or "").strip()
        )
        if workflow_title and workflow_title in default_titles:
            return workflow
    return None


def _instruction_workflow_by_reference(state: GraphState, workflow_ref: Any) -> Dict[str, Any] | None:
    target = str(workflow_ref or "").strip()
    if not target:
        return None
    target_prefix, target_suffix = _identifier_prefix_and_suffix(target)
    target_slug = _normalize_slug(target_suffix or target)
    target_section = _normalize_section_name(target_suffix or target)
    registry = state.get("template_registry", {}) or {}
    workflows = registry.get("instruction_workflows", [])
    if isinstance(workflows, list):
        for workflow in workflows:
            if not isinstance(workflow, dict):
                continue
            workflow_id = str(workflow.get("id") or "").strip()
            workflow_title = str(workflow.get("workflow_name") or workflow.get("title") or "").strip()
            workflow_id_prefix, workflow_id_suffix = _identifier_prefix_and_suffix(workflow_id)
            workflow_id_slug = _normalize_slug(workflow_id_suffix or workflow_id)
            workflow_id_section = _normalize_section_name(workflow_id_suffix or workflow_id)
            workflow_title_slug = _normalize_slug(workflow_title)
            workflow_title_section = _normalize_section_name(workflow_title)
            if (
                workflow_id == target
                or _identifier_equivalent(workflow_id, target)
                or (workflow_title and _identifier_equivalent(workflow_title, target))
                or (target_slug and workflow_id_slug and target_slug == workflow_id_slug)
                or (target_section and workflow_id_section and target_section == workflow_id_section)
                or (target_slug and workflow_title_slug and target_slug == workflow_title_slug)
                or (target_section and workflow_title_section and target_section == workflow_title_section)
            ):
                return workflow
    service_block = _service_block_by_id(state, target)
    if not isinstance(service_block, dict) or not service_block:
        return None
    block_type = str(service_block.get("block_type") or "").strip()
    if block_type not in {"primary_workflow", "supplementary_workflow"}:
        return None
    block_id = str(service_block.get("block_id") or "").strip()
    if not block_id:
        return None
    workflow_id = target_suffix or block_id.split(":", 1)[-1].strip() or block_id
    workflow_title = str(service_block.get("title") or "").strip() or workflow_id
    procedure = _procedure_for_service_block_id(state, block_id)
    procedure_id = str((procedure or {}).get("procedure_id") or "").strip()
    synthesized_steps: list[Dict[str, Any]] = []
    if procedure_id:
        for step in _ordered_procedure_steps(state, procedure_id):
            if not isinstance(step, dict):
                continue
            resource_refs = [
                str(item or "").strip()
                for item in step.get("resource_refs", []) or []
                if str(item or "").strip()
            ]
            synthesized_steps.append(
                {
                    "order": _normalize_int_like(step.get("order")),
                    "title": str(step.get("title") or "").strip() or None,
                    "step_scope_id": str(step.get("step_id") or "").strip() or None,
                    "resource_file": resource_refs[0] if resource_refs else None,
                }
            )
    return {
        "id": workflow_id,
        "title": workflow_title,
        "workflow_name": workflow_title,
        "steps": synthesized_steps,
    }


def _hybrid_active_selected_workflow(state: GraphState) -> Dict[str, Any] | None:
    planner_mode = str(state.get("planner_mode") or "").strip().lower()
    if planner_mode != "hybrid_active":
        return None
    shadow_output = state.get("hybrid_planner_shadow_output", {}) or {}
    if not isinstance(shadow_output, dict):
        return None
    selected_workflow_id = str(shadow_output.get("selected_workflow_id") or "").strip()
    if not selected_workflow_id:
        next_action = shadow_output.get("next_action", {})
        if isinstance(next_action, dict):
            selected_workflow_id = str(
                next_action.get("target_workflow_id")
                or next_action.get("target_service_block_id")
                or ""
            ).strip()
    workflow = _instruction_workflow_by_reference(state, selected_workflow_id)
    if isinstance(workflow, dict):
        return workflow

    if _hybrid_active_should_stay_logic_only(state, _hybrid_active_module_queue(state)):
        return None

    selected_role_id = str(shadow_output.get("selected_role_id") or "").strip()
    if not selected_role_id:
        return None
    hybrid = _compiled_hybrid_runtime_model(state)
    role_profiles = hybrid.get("role_profiles", []) or []
    if not isinstance(role_profiles, list):
        return None
    role_profile = next(
        (
            item
            for item in role_profiles
            if isinstance(item, dict)
            and str(item.get("role_id") or "").strip() == selected_role_id
        ),
        None,
    )
    if not isinstance(role_profile, dict):
        return None
    for workflow_ref in (
        list(role_profile.get("permitted_workflows", []) or [])
        + list(role_profile.get("allowed_workflow_ids", []) or [])
    ):
        workflow = _instruction_workflow_by_reference(state, workflow_ref)
        if isinstance(workflow, dict):
            return workflow
    return None


def _hybrid_active_selected_role_id(state: GraphState) -> str | None:
    planner_mode = str(state.get("planner_mode") or "").strip().lower()
    if planner_mode != "hybrid_active":
        return None
    shadow_output = state.get("hybrid_planner_shadow_output", {}) or {}
    if not isinstance(shadow_output, dict):
        return None
    selected_role_id = str(shadow_output.get("selected_role_id") or "").strip()
    return selected_role_id or None


def _hybrid_active_module_queue(state: GraphState) -> list[str]:
    planner_mode = str(state.get("planner_mode") or "").strip().lower()
    if planner_mode != "hybrid_active":
        return []
    shadow_output = state.get("hybrid_planner_shadow_output", {}) or {}
    if not isinstance(shadow_output, dict):
        shadow_output = {}
    module_sequence = [
        str(item).strip()
        for item in shadow_output.get("module_sequence", []) or []
        if str(item).strip()
    ]
    support_module_ids = [
        str(item).strip()
        for item in shadow_output.get("selected_support_module_ids", []) or []
        if str(item).strip()
    ]
    followup_module_ids = [
        str(item).strip()
        for item in shadow_output.get("selected_followup_module_ids", []) or []
        if str(item).strip()
    ]
    next_action = shadow_output.get("next_action", {})
    next_action_module_queue = [
        str(item).strip()
        for item in next_action.get("module_queue", []) or []
        if str(item).strip()
    ] if isinstance(next_action, dict) else []
    candidate_ids = module_sequence or support_module_ids or followup_module_ids or next_action_module_queue
    raw_selected_routing_rule_id = str(shadow_output.get("selected_routing_rule_id") or "").strip()
    effective_selected_routing_rule_id = _hybrid_active_selected_routing_rule_id(state) or ""
    logic_block = _hybrid_active_selected_interaction_logic_block(state)
    primary_logic_module_targets = _logic_block_primary_module_targets(logic_block)
    on_demand_module_targets = _logic_block_on_demand_module_targets(logic_block)
    if (
        candidate_ids
        and effective_selected_routing_rule_id
        and raw_selected_routing_rule_id
        and effective_selected_routing_rule_id != raw_selected_routing_rule_id
        and not primary_logic_module_targets
    ):
        candidate_ids = []
    if primary_logic_module_targets:
        if not candidate_ids:
            candidate_ids = primary_logic_module_targets
    elif candidate_ids and on_demand_module_targets and set(candidate_ids).issubset(set(on_demand_module_targets)):
        candidate_ids = []
    if not candidate_ids:
        if isinstance(logic_block, dict):
            candidate_ids = [
                str(item).strip()
                for item in logic_block.get("subordinate_modules", []) or []
                if str(item).strip()
            ]
            if not candidate_ids:
                candidate_ids = primary_logic_module_targets
    if not candidate_ids:
        selected_role_id = _hybrid_active_selected_role_id(state) or ""
        if selected_role_id:
            hybrid = _compiled_hybrid_runtime_model(state)
            role_profiles = hybrid.get("role_profiles", []) or []
            role_profile = next(
                (
                    item
                    for item in role_profiles
                    if isinstance(item, dict)
                    and str(item.get("role_id") or "").strip() == selected_role_id
                ),
                None,
            )
            if isinstance(role_profile, dict):
                candidate_ids = [
                    str(item).strip()
                    for item in (
                        list(role_profile.get("permitted_modules", []) or [])
                        + list(role_profile.get("allowed_module_ids", []) or [])
                    )
                    if str(item).strip()
                ]

    queued_followup_ids = _queued_followup_service_block_ids(state)
    if queued_followup_ids:
        ordered: list[str] = []
        seen: set[str] = set()
        for item in queued_followup_ids:
            if item and item not in seen:
                seen.add(item)
                ordered.append(item)
        for item in candidate_ids:
            if item and item not in seen:
                seen.add(item)
                ordered.append(item)
        return [
            _canonical_service_block_candidate_id(state, item, fallback_to_sole_support_module=True)
            for item in ordered
        ]
    return [
        _canonical_service_block_candidate_id(state, item, fallback_to_sole_support_module=True)
        for item in candidate_ids
    ]


def _hybrid_active_target_service_block_ids(state: GraphState) -> list[str]:
    planner_mode = str(state.get("planner_mode") or "").strip().lower()
    if planner_mode != "hybrid_active":
        return []
    shadow_output = state.get("hybrid_planner_shadow_output", {}) or {}
    if not isinstance(shadow_output, dict):
        return []
    gate_resolved_this_turn = bool(str(state.get("_control_gate_resolved_step_scope_id") or "").strip())
    candidate_ids: list[str] = []

    next_action = shadow_output.get("next_action", {})
    if isinstance(next_action, dict):
        target_service_block_id = str(next_action.get("target_service_block_id") or "").strip()
        if target_service_block_id:
            candidate_ids.append(target_service_block_id)

    for key in ("selected_followup_module_ids", "selected_support_module_ids", "module_sequence"):
        values = shadow_output.get(key, []) or []
        if not isinstance(values, list):
            continue
        candidate_ids.extend(str(item).strip() for item in values if str(item).strip())

    if isinstance(next_action, dict):
        candidate_ids.extend(
            str(item).strip() for item in next_action.get("module_queue", []) or [] if str(item).strip()
        )
    logic_block = _hybrid_active_selected_interaction_logic_block(state)
    raw_selected_routing_rule_id = str(shadow_output.get("selected_routing_rule_id") or "").strip()
    effective_selected_routing_rule_id = _hybrid_active_selected_routing_rule_id(state) or ""
    primary_logic_module_targets = _logic_block_primary_module_targets(logic_block)
    on_demand_module_targets = _logic_block_on_demand_module_targets(logic_block)
    if (
        candidate_ids
        and effective_selected_routing_rule_id
        and raw_selected_routing_rule_id
        and effective_selected_routing_rule_id != raw_selected_routing_rule_id
        and not primary_logic_module_targets
    ):
        candidate_ids = []
    if primary_logic_module_targets:
        if not candidate_ids:
            candidate_ids.extend(primary_logic_module_targets)
    elif candidate_ids and on_demand_module_targets and set(candidate_ids).issubset(set(on_demand_module_targets)):
        candidate_ids = []
    if not candidate_ids:
        if isinstance(logic_block, dict):
            candidate_ids.extend(
                str(item).strip()
                for item in logic_block.get("subordinate_modules", []) or []
                if str(item).strip()
            )
            if not candidate_ids:
                candidate_ids.extend(primary_logic_module_targets)

    seen: set[str] = set()
    ordered: list[str] = []
    for item in candidate_ids:
        if item and item not in seen:
            canonical_id = _canonical_service_block_candidate_id(state, item, fallback_to_sole_support_module=True)
            block = _service_block_by_id(state, canonical_id)
            if (
                gate_resolved_this_turn
                and isinstance(block, dict)
                and str(block.get("block_type") or "").strip() == "followup_module"
            ):
                continue
            if (
                isinstance(block, dict)
                and str(block.get("block_type") or "").strip() == "followup_module"
                and not _followup_module_should_activate_for_turn(state, canonical_id)
            ):
                continue
            seen.add(item)
            ordered.append(canonical_id)
    return ordered


def _canonical_service_block_candidate_id(
    state: GraphState,
    candidate_id: str,
    *,
    fallback_to_sole_support_module: bool = False,
) -> str:
    target = str(candidate_id or "").strip()
    if not target:
        return target
    block = _service_block_by_id(state, target)
    if isinstance(block, dict):
        canonical_block_id = str(block.get("block_id") or "").strip()
        canonical_block_type = str(block.get("block_type") or "").strip()
        if canonical_block_id and canonical_block_type == "support_module":
            return canonical_block_id
    candidate_prefix, _candidate_suffix = _identifier_prefix_and_suffix(target)
    if fallback_to_sole_support_module:
        if candidate_prefix and candidate_prefix not in {"module", "support_module", "followup_module"}:
            return target
        support_blocks = [
            item
            for item in _instruction_service_blocks(state)
            if str(item.get("block_type") or "").strip() == "support_module"
        ]
        if len(support_blocks) == 1:
            canonical_block_id = str(support_blocks[0].get("block_id") or "").strip()
            if canonical_block_id:
                return canonical_block_id
    return target


def _interaction_logic_blocks(state: GraphState) -> list[Dict[str, Any]]:
    hybrid = _compiled_hybrid_runtime_model(state)
    blocks = hybrid.get("interaction_logic_blocks", []) or []
    if not isinstance(blocks, list):
        return []
    return [item for item in blocks if isinstance(item, dict)]


def _interaction_logic_block_by_id(state: GraphState, block_id: str) -> Dict[str, Any] | None:
    target = str(block_id or "").strip()
    if not target:
        return None
    for block in _interaction_logic_blocks(state):
        for candidate in (
            block.get("block_id"),
            block.get("logic_id"),
            block.get("title"),
        ):
            if _identifier_equivalent(candidate, target):
                return block
    return None


def _logic_block_primary_module_targets(block: Dict[str, Any] | None) -> list[str]:
    if not isinstance(block, dict):
        return []
    ordered: list[str] = []
    seen: set[str] = set()
    for item in block.get("subordinate_modules", []) or []:
        module_id = str(item).strip()
        if module_id and module_id not in seen:
            seen.add(module_id)
            ordered.append(module_id)
    subordinate_target = block.get("subordinate_target")
    if isinstance(subordinate_target, dict):
        target_type = str(subordinate_target.get("target_type") or "").strip()
        target_id = str(subordinate_target.get("target_id") or "").strip()
        if target_id and target_type in {"module", "support_module", "followup_module"} and target_id not in seen:
            seen.add(target_id)
            ordered.append(target_id)
    for key in ("target_module_id", "module_id"):
        module_id = str(block.get(key) or "").strip()
        if module_id and module_id not in seen:
            seen.add(module_id)
            ordered.append(module_id)
    return ordered


def _logic_block_on_demand_module_targets(block: Dict[str, Any] | None) -> list[str]:
    if not isinstance(block, dict):
        return []
    ordered: list[str] = []
    seen: set[str] = set()
    for item in block.get("support_modules_on_demand", []) or []:
        module_id = str(item).strip()
        if module_id and module_id not in seen:
            seen.add(module_id)
            ordered.append(module_id)
    return ordered


def _hybrid_active_should_stay_logic_only(state: GraphState, module_queue: list[str]) -> bool:
    planner_mode = str(state.get("planner_mode") or "").strip().lower()
    if planner_mode != "hybrid_active":
        return False
    logic_block = _hybrid_active_selected_interaction_logic_block(state)
    if not isinstance(logic_block, dict):
        return False
    if _logic_block_primary_module_targets(logic_block):
        return False
    if module_queue:
        return False
    return bool(_logic_block_on_demand_module_targets(logic_block))


def _routing_rule_target_logic_block(state: GraphState, rule_id: str) -> Dict[str, Any] | None:
    hybrid = _compiled_hybrid_runtime_model(state)
    rules = hybrid.get("routing_rules", []) or []
    if not isinstance(rules, list):
        return None
    target_rule_id = str(rule_id or "").strip()
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if str(rule.get("rule_id") or "").strip() != target_rule_id:
            continue
        target = str(
            rule.get("target")
            or rule.get("target_service_block_id")
            or rule.get("target_logic_block_id")
            or rule.get("target_id")
            or rule.get("target_interaction_logic_id")
            or ""
        ).strip()
        return _interaction_logic_block_by_id(state, target)
    return None


def _fallback_interaction_logic_block_from_query(state: GraphState) -> Dict[str, Any] | None:
    selected_rule = _fallback_routing_rule_from_query(state)
    if not isinstance(selected_rule, dict):
        return None
    target = str(
        selected_rule.get("target")
        or selected_rule.get("target_service_block_id")
        or selected_rule.get("target_logic_block_id")
        or selected_rule.get("target_id")
        or selected_rule.get("target_interaction_logic_id")
        or ""
    ).strip()
    return _interaction_logic_block_by_id(state, target)


def _fallback_routing_rule_from_query(state: GraphState) -> Dict[str, Any] | None:
    hybrid = _compiled_hybrid_runtime_model(state)
    rules = hybrid.get("routing_rules", []) or []
    if not isinstance(rules, list):
        return None
    query = " ".join(_conversation_user_messages(state, str(state.get("user_query") or ""))).lower()
    best_rule: Dict[str, Any] | None = None
    best_score = 0
    fallback_rule: Dict[str, Any] | None = None
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        trigger_keywords = [
            str(item).strip().lower()
            for item in rule.get("trigger_keywords", []) or []
            if str(item).strip()
        ]
        if not trigger_keywords:
            fallback_rule = fallback_rule or rule
            continue
        score = 0
        for keyword in trigger_keywords:
            if keyword and keyword in query:
                score = max(score, len(keyword))
        if score > best_score:
            best_score = score
            best_rule = rule
    return best_rule or fallback_rule


def _routing_rule_by_id(state: GraphState, rule_id: str) -> Dict[str, Any] | None:
    hybrid = _compiled_hybrid_runtime_model(state)
    rules = hybrid.get("routing_rules", []) or []
    if not isinstance(rules, list):
        return None
    target = str(rule_id or "").strip()
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        if str(rule.get("rule_id") or "").strip() == target:
            return rule
    return None


def _routing_rule_match_score(state: GraphState, rule: Dict[str, Any] | None) -> int:
    if not isinstance(rule, dict):
        return 0
    query = " ".join(_conversation_user_messages(state, str(state.get("user_query") or ""))).lower()
    if not query.strip():
        return 0
    best_score = 0
    for keyword in rule.get("trigger_keywords", []) or []:
        token = str(keyword or "").strip().lower()
        if token and token in query:
            best_score = max(best_score, len(token))
    return best_score


def _hybrid_active_selected_interaction_logic_block(state: GraphState) -> Dict[str, Any] | None:
    planner_mode = str(state.get("planner_mode") or "").strip().lower()
    if planner_mode != "hybrid_active":
        return None
    shadow_output = state.get("hybrid_planner_shadow_output", {}) or {}
    if not isinstance(shadow_output, dict):
        shadow_output = {}
    selected_routing_rule_id = _hybrid_active_selected_routing_rule_id(state)
    if selected_routing_rule_id:
        block = _routing_rule_target_logic_block(state, selected_routing_rule_id)
        if isinstance(block, dict):
            return block
    next_action = shadow_output.get("next_action", {})
    if isinstance(next_action, dict):
        target_service_block_id = str(next_action.get("target_service_block_id") or "").strip()
        block = _interaction_logic_block_by_id(state, target_service_block_id)
        if isinstance(block, dict):
            return block
    return _fallback_interaction_logic_block_from_query(state)


def _queued_followup_service_block_ids(state: GraphState) -> list[str]:
    session_state = state.get("session_execution_state", {}) or {}
    if not isinstance(session_state, dict):
        return []
    if not bool(session_state.get("bundled_execution_completed")):
        return []
    candidate_ids: list[str] = []
    primary_support_module_id = str(session_state.get("primary_support_module_id") or "").strip()
    if primary_support_module_id:
        candidate_ids.append(primary_support_module_id)
    candidate_ids.extend(
        str(item).strip()
        for item in session_state.get("active_module_queue", []) or []
        if str(item).strip()
    )
    ordered: list[str] = []
    seen: set[str] = set()
    for block_id in candidate_ids:
        if not block_id or block_id in seen:
            continue
        block = _service_block_by_id(state, block_id)
        if not isinstance(block, dict):
            continue
        if str(block.get("block_type") or "").strip() != "followup_module":
            continue
        seen.add(block_id)
        ordered.append(block_id)
    if ordered:
        return ordered
    query = str(state.get("user_query") or "").strip()
    query_lower = query.lower()
    refinement_markers = ("優化", "优化", "optimize", "optimise", "refine", "improve")
    if not query or not (
        _looks_like_refinement_followup(state, query)
        or any(marker in query or marker in query_lower for marker in refinement_markers)
    ):
        return []
    followup_blocks = [
        item
        for item in _instruction_service_blocks(state)
        if isinstance(item, dict) and str(item.get("block_type") or "").strip() == "followup_module"
    ]
    if len(followup_blocks) == 1:
        block_id = str(followup_blocks[0].get("block_id") or "").strip()
        return [block_id] if block_id else []
    return ordered


def _shadow_followup_service_block_ids(state: GraphState) -> list[str]:
    planner_mode = str(state.get("planner_mode") or "").strip().lower()
    if planner_mode != "hybrid_active":
        return []
    shadow_output = state.get("hybrid_planner_shadow_output", {}) or {}
    if not isinstance(shadow_output, dict):
        return []
    candidate_ids: list[str] = []
    next_action = shadow_output.get("next_action", {})
    if isinstance(next_action, dict):
        target_service_block_id = str(next_action.get("target_service_block_id") or "").strip()
        if target_service_block_id:
            candidate_ids.append(target_service_block_id)
        candidate_ids.extend(
            str(item).strip() for item in next_action.get("module_queue", []) or [] if str(item).strip()
        )
    for key in ("selected_followup_module_ids", "module_sequence"):
        values = shadow_output.get(key, []) or []
        if not isinstance(values, list):
            continue
        candidate_ids.extend(str(item).strip() for item in values if str(item).strip())
    ordered: list[str] = []
    seen: set[str] = set()
    for candidate_id in candidate_ids:
        canonical_id = _canonical_service_block_candidate_id(
            state,
            candidate_id,
            fallback_to_sole_support_module=True,
        )
        if not canonical_id or canonical_id in seen:
            continue
        block = _service_block_by_id(state, canonical_id)
        if not isinstance(block, dict):
            continue
        if str(block.get("block_type") or "").strip() != "followup_module":
            continue
        seen.add(canonical_id)
        ordered.append(canonical_id)
    return ordered


def _followup_module_should_activate_for_turn(state: GraphState, block_id: str) -> bool:
    canonical_id = _canonical_service_block_candidate_id(
        state,
        str(block_id or "").strip(),
        fallback_to_sole_support_module=True,
    )
    if not canonical_id:
        return False
    block = _service_block_by_id(state, canonical_id)
    if not isinstance(block, dict):
        return False
    if str(block.get("block_type") or "").strip() != "followup_module":
        return False
    query = str(state.get("user_query") or "").strip()
    next_action = state.get("hybrid_planner_shadow_output", {}) or {}
    next_action = next_action.get("next_action", {}) if isinstance(next_action, dict) else {}
    explicit_shadow_followups = set(_shadow_followup_service_block_ids(state))
    queued_followups = set(_queued_followup_service_block_ids(state))
    explicit_action_type = str(next_action.get("action_type") or "").strip().lower() if isinstance(next_action, dict) else ""
    if canonical_id in explicit_shadow_followups and explicit_action_type == "select_followup_module":
        return True
    lowered = query.lower()
    explicit_refinement_markers = (
        "優化",
        "优化",
        "改寫",
        "改写",
        "重寫",
        "重写",
        "精煉",
        "精炼",
        "修訂",
        "修订",
        "調整",
        "调整",
        "完善",
        "潤飾",
        "润饰",
        "refine",
        "revise",
        "rewrite",
        "improve",
        "optimize",
        "optimise",
        "polish",
        "shorten",
        "expand",
    )
    explicit_target_markers = (
        "prompt",
        "draft",
        "version",
        "output",
        "answer",
        "response",
        "material",
        "outline",
        "plan",
        "這份",
        "这份",
        "此",
        "這個",
        "这个",
        "上一版",
        "上一輪",
        "上一轮",
        "剛才",
        "刚才",
        "上面的",
        "前一版",
    )
    followup_turn = (
        _looks_like_refinement_followup(state, query)
        or _looks_like_option_selection_followup(state, query)
        or (
            any(marker.lower() in lowered for marker in explicit_refinement_markers)
            and any(marker.lower() in lowered for marker in explicit_target_markers)
        )
    )
    if not followup_turn:
        return False
    return canonical_id in explicit_shadow_followups or canonical_id in queued_followups


def _hybrid_active_selected_routing_rule_id(state: GraphState) -> str | None:
    planner_mode = str(state.get("planner_mode") or "").strip().lower()
    if planner_mode != "hybrid_active":
        return None
    shadow_output = state.get("hybrid_planner_shadow_output", {}) or {}
    if not isinstance(shadow_output, dict):
        shadow_output = {}
    selected_routing_rule_id = str(shadow_output.get("selected_routing_rule_id") or "").strip()
    fallback_rule = _fallback_routing_rule_from_query(state)
    if selected_routing_rule_id:
        selected_rule = _routing_rule_by_id(state, selected_routing_rule_id)
        selected_score = _routing_rule_match_score(state, selected_rule)
        fallback_score = _routing_rule_match_score(state, fallback_rule)
        if fallback_score > 0 and fallback_score > selected_score:
            fallback_rule_id = str(fallback_rule.get("rule_id") or "").strip() if isinstance(fallback_rule, dict) else ""
            if fallback_rule_id:
                return fallback_rule_id
        return selected_routing_rule_id
    if isinstance(fallback_rule, dict):
        fallback_rule_id = str(fallback_rule.get("rule_id") or "").strip()
        if fallback_rule_id:
            return fallback_rule_id
    session_state = state.get("session_execution_state", {}) or {}
    if isinstance(session_state, dict):
        persisted_rule_id = str(session_state.get("selected_routing_rule_id") or "").strip()
        if persisted_rule_id:
            return persisted_rule_id
    return None


def _hybrid_active_primary_support_module(state: GraphState, module_queue: list[str]) -> tuple[str | None, str | None]:
    if not module_queue:
        return None, None
    for candidate in module_queue:
        primary_module_id = str(candidate or "").strip()
        if not primary_module_id:
            continue
        canonical_block = _service_block_by_id(state, primary_module_id)
        if isinstance(canonical_block, dict):
            canonical_block_id = str(canonical_block.get("block_id") or "").strip() or primary_module_id
            canonical_title = str(canonical_block.get("title") or "").strip() or None
            canonical_block_type = str(canonical_block.get("block_type") or "").strip()
            if canonical_block_type == "support_module":
                return canonical_block_id, canonical_title
            if canonical_block_type == "followup_module":
                if _followup_module_should_activate_for_turn(state, canonical_block_id):
                    return canonical_block_id, canonical_title
                continue
        support_module = _support_module_rule_map(state).get(primary_module_id)
        if isinstance(support_module, dict):
            return primary_module_id, str(support_module.get("title") or "").strip() or None
        hybrid = _compiled_hybrid_runtime_model(state)
        for item in hybrid.get("instruction_service_blocks", []) or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("block_id") or "").strip() != primary_module_id:
                continue
            if str(item.get("block_type") or "").strip() == "followup_module":
                if _followup_module_should_activate_for_turn(state, primary_module_id):
                    return primary_module_id, str(item.get("title") or "").strip() or None
                break
            return primary_module_id, str(item.get("title") or "").strip() or None
    return None, None


def _hybrid_active_selected_instruction_module(state: GraphState) -> Dict[str, Any] | None:
    module_owned_step = _module_owned_active_step_selection(state)
    if isinstance(module_owned_step, dict):
        return module_owned_step
    shadow_target_step = _shadow_target_step_selection(state)
    if isinstance(shadow_target_step, dict):
        return shadow_target_step
    registry = state.get("template_registry", {}) or {}
    modules = registry.get("instruction_modules", [])
    if not isinstance(modules, list) or not modules:
        return None
    module_queue = _hybrid_active_module_queue(state)
    if not module_queue:
        return None
    target_ids = {str(item).strip() for item in module_queue if str(item).strip()}
    if not target_ids:
        return None
    for module in modules:
        if not isinstance(module, dict):
            continue
        if str(module.get("id") or "").strip() in target_ids:
            return module
    return None


def _hybrid_active_selected_service_block(state: GraphState) -> Dict[str, Any] | None:
    for block_id in _hybrid_active_target_service_block_ids(state):
        block = _service_block_by_id(state, block_id)
        if (
            isinstance(block, dict)
            and block
            and (
                str(block.get("block_type") or "").strip() != "followup_module"
                or _followup_module_should_activate_for_turn(state, block_id)
            )
        ):
            return block
    for block_id in _queued_followup_service_block_ids(state):
        block = _service_block_by_id(state, block_id)
        if (
            isinstance(block, dict)
            and block
            and _followup_module_should_activate_for_turn(state, block_id)
        ):
            return block
    return None


def _supplementary_instruction_workflow_for_query(
    state: GraphState,
    query: str,
) -> Dict[str, Any] | None:
    if not _query_requests_scripture_study(query):
        return None
    registry = state.get("template_registry", {}) or {}
    workflows = registry.get("instruction_workflows", [])
    if not isinstance(workflows, list):
        return None
    for workflow in workflows:
        if not isinstance(workflow, dict):
            continue
        block = _service_block_for_workflow(state, workflow)
        if not isinstance(block, dict) or str(block.get("block_type") or "").strip() != "supplementary_workflow":
            continue
        workflow_text = " ".join(
            [
                str(workflow.get("workflow_name") or "").strip(),
                str(workflow.get("title") or "").strip(),
                str(block.get("title") or "").strip(),
                str(block.get("body_text") or "").strip(),
            ]
        ).lower()
        if any(token in workflow_text for token in ("bible", "scripture", "查經", "查经", "經文", "经文")):
            return workflow
    return None


def _active_service_block(
    state: GraphState,
    selected_workflow: Dict[str, Any] | None,
    selected_block: Dict[str, Any] | None,
    selected_step: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    hybrid_selected_block = _hybrid_active_selected_service_block(state)
    if isinstance(hybrid_selected_block, dict) and str(hybrid_selected_block.get("block_type") or "").strip() in {
        "primary_workflow",
        "supplementary_workflow",
        "followup_module",
        "support_module",
    }:
        return hybrid_selected_block

    workflow_block = _service_block_for_workflow(state, selected_workflow)
    if isinstance(workflow_block, dict) and str(workflow_block.get("block_type") or "").strip() in {
        "primary_workflow",
        "supplementary_workflow",
        "followup_module",
        "support_module",
    }:
        return workflow_block

    if isinstance(selected_block, dict) and selected_block:
        block_title = _normalize_section_name(str(selected_block.get("title") or "").strip())
        linked_workflow = _normalize_section_name(str(selected_block.get("linked_workflow") or "").strip())
        for block in _instruction_service_blocks(state):
            block_type = str(block.get("block_type") or "").strip()
            block_title_candidate = _normalize_section_name(str(block.get("title") or "").strip())
            if block_type == "entry_mode" and block_title and block_title_candidate == block_title:
                return block
            if linked_workflow and block_title_candidate == linked_workflow:
                return block
    return workflow_block


def _normalized_service_block_type(block: Dict[str, Any] | None) -> str | None:
    if not isinstance(block, dict):
        return None
    block_type = str(block.get("block_type") or "").strip() or None
    if block_type == "mode":
        return "entry_mode"
    return block_type


def _select_instruction_block(
    state: GraphState,
    selected_workflow: Dict[str, Any] | None,
    selected_module: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    blocks = _instruction_blocks(state)
    if not blocks:
        return None

    if isinstance(selected_module, dict):
        step_order = selected_module.get("order")
        workflow_id = str(selected_workflow.get("id") or "").strip() if isinstance(selected_workflow, dict) else ""
        step_title = str(selected_module.get("title") or "").strip()
        for block in blocks:
            if str(block.get("block_type") or "") != "step":
                continue
            if workflow_id and str(block.get("linked_mode_id") or "").strip() == workflow_id and block.get("linked_step_order") == step_order:
                return block
            if step_title and str(block.get("linked_step_title") or "").strip() == step_title:
                return block

    if isinstance(selected_workflow, dict):
        workflow_id = str(selected_workflow.get("id") or "").strip()
        workflow_title = str(selected_workflow.get("title") or "").strip()
        for block in blocks:
            if str(block.get("block_type") or "") != "mode":
                continue
            if workflow_id and str(block.get("linked_mode_id") or "").strip() == workflow_id:
                return block
            if workflow_title and str(block.get("title") or "").strip() == workflow_title:
                return block

    return None


def _runtime_resource_map(state: GraphState) -> dict[str, Dict[str, Any]]:
    runtime_model = state.get("instruction_runtime_model", {}) or {}
    resources = runtime_model.get("instruction_resources", [])
    if not isinstance(resources, list):
        return {}
    resource_map: dict[str, Dict[str, Any]] = {}
    for resource in resources:
        if isinstance(resource, dict):
            resource_id = str(resource.get("resource_id") or "").strip()
            if resource_id:
                resource_map[resource_id] = resource
    return resource_map


def _runtime_resources_by_domain(state: GraphState, domain: str) -> list[Dict[str, Any]]:
    return [
        resource
        for resource in _runtime_resource_map(state).values()
        if str(resource.get("domain") or "") == domain
    ]


def _runtime_resource_by_filename(state: GraphState, filename: str) -> Dict[str, Any] | None:
    normalized_filename = str(filename or "").strip().lower()
    if not normalized_filename:
        return None
    normalized_stem = Path(normalized_filename).stem.lower()
    for resource in _runtime_resource_map(state).values():
        resource_filename = str(resource.get("filename") or "").strip()
        if not resource_filename:
            continue
        if resource_filename.lower() == normalized_filename:
            return resource
        if Path(resource_filename).stem.lower() == normalized_stem:
            return resource
    return None


def _support_module_rule_map(state: GraphState) -> dict[str, Dict[str, Any]]:
    runtime_model = state.get("instruction_runtime_model", {}) or {}
    modules = runtime_model.get("support_modules", [])
    if not isinstance(modules, list):
        return {}
    module_map: dict[str, Dict[str, Any]] = {}
    for module in modules:
        if not isinstance(module, dict):
            continue
        module_id = str(module.get("module_id") or "").strip()
        if module_id:
            module_map[module_id] = module
    return module_map


def _followup_module_rule_map(state: GraphState) -> dict[str, Dict[str, Any]]:
    runtime_model = state.get("instruction_runtime_model", {}) or {}
    modules = runtime_model.get("followup_modules", [])
    if not isinstance(modules, list):
        return {}
    module_map: dict[str, Dict[str, Any]] = {}
    for module in modules:
        if not isinstance(module, dict):
            continue
        for candidate in (
            str(module.get("module_id") or "").strip(),
            str(module.get("block_id") or "").strip(),
        ):
            if candidate:
                module_map[candidate] = module
    return module_map


def _followup_module_explicit_resource_files(state: GraphState, module_id: str) -> list[str]:
    target = str(module_id or "").strip()
    module = _followup_module_rule_map(state).get(target)
    if not isinstance(module, dict) and target:
        seen_modules: list[Dict[str, Any]] = []
        for candidate in _followup_module_rule_map(state).values():
            if not isinstance(candidate, dict) or candidate in seen_modules:
                continue
            seen_modules.append(candidate)
            for value in (
                candidate.get("module_id"),
                candidate.get("block_id"),
                candidate.get("title"),
            ):
                if _identifier_equivalent(value, target):
                    module = candidate
                    break
            if isinstance(module, dict):
                break
    if not isinstance(module, dict):
        return []
    explicit_files: list[str] = []
    for filename in module.get("resource_refs", []) or []:
        cleaned = str(filename or "").strip()
        if cleaned and cleaned not in explicit_files:
            explicit_files.append(cleaned)
    for step in module.get("step_sequence", []) or []:
        if not isinstance(step, dict):
            continue
        for filename in step.get("resource_refs", []) or []:
            cleaned = str(filename or "").strip()
            if cleaned and cleaned not in explicit_files:
                explicit_files.append(cleaned)
    return explicit_files


def _procedure_for_service_block_id(state: GraphState, block_id: str) -> Dict[str, Any] | None:
    target = str(block_id or "").strip()
    if not target:
        return None
    for procedure in _instruction_procedures(state):
        if _identifier_equivalent(procedure.get("service_block_id"), target):
            return procedure
    return None


def _ordered_procedure_steps(state: GraphState, procedure_id: str) -> list[Dict[str, Any]]:
    target = str(procedure_id or "").strip()
    if not target:
        return []
    runtime_model = state.get("instruction_runtime_model", {}) or {}
    steps = runtime_model.get("procedure_steps", []) or []
    if not isinstance(steps, list):
        return []
    ordered = [
        item
        for item in steps
        if isinstance(item, dict) and _identifier_equivalent(item.get("procedure_id"), target)
    ]
    return sorted(ordered, key=lambda item: int(item.get("order") or 9999))


def _activation_for_service_block(
    state: GraphState,
    service_block: Dict[str, Any] | None,
) -> Dict[str, Any]:
    if not isinstance(service_block, dict) or not service_block:
        return {}
    block_id = str(service_block.get("block_id") or "").strip()
    block_type = str(service_block.get("block_type") or "").strip()
    block_title = str(service_block.get("title") or "").strip() or None
    if not block_id:
        return {}

    payload: Dict[str, Any] = {
        "active_service_block_id": block_id,
        "active_service_block_type": block_type or None,
        "active_service_block_title": block_title,
    }
    if block_type == "support_module":
        payload["primary_support_module_id"] = block_id
        payload["primary_support_module_title"] = block_title

    procedure = _procedure_for_service_block_id(state, block_id)
    if isinstance(procedure, dict):
        steps = _ordered_procedure_steps(state, str(procedure.get("procedure_id") or "").strip())
        if steps:
            first_step = steps[0]
            step_scope_id = str(first_step.get("step_id") or "").strip() or None
            step_order = _normalize_int_like(first_step.get("order"))
            step_title = str(first_step.get("title") or "").strip() or None
            execution_mode = str(first_step.get("execution_mode") or "").strip() or None
            bundled_step_ids = [
                str(item).strip()
                for item in first_step.get("bundled_step_ids", []) or []
                if str(item).strip()
            ]
            if step_scope_id:
                payload["active_step_scope_id"] = step_scope_id
                payload["procedure_step_activation"] = to_plain_dict(
                    ProcedureStepActivation(
                        step_scope_id=step_scope_id,
                        step_order=step_order,
                        step_title=step_title,
                        primary_support_module_id=block_id if block_type == "support_module" else None,
                    )
                )
                if block_type == "support_module":
                    payload["primary_support_module_activation"] = to_plain_dict(
                        PrimarySupportModuleActivation(
                            support_module_id=block_id,
                            support_module_title=block_title,
                            step_scope_id=step_scope_id,
                        )
                    )
            if execution_mode:
                payload["active_execution_mode"] = execution_mode
            if bundled_step_ids:
                payload["active_bundled_step_ids"] = bundled_step_ids
                payload["bundled_entry_step_id"] = bundled_step_ids[0]
                payload["bundled_execution_completed"] = False
    return payload


def _phase_resource_bindings(state: GraphState) -> list[Dict[str, Any]]:
    runtime_model = state.get("instruction_runtime_model", {}) or {}
    bindings = runtime_model.get("phase_resource_bindings", [])
    if not isinstance(bindings, list):
        return []
    return [binding for binding in bindings if isinstance(binding, dict)]


def _dependency_group_map(state: GraphState) -> dict[str, Dict[str, Any]]:
    runtime_model = state.get("instruction_runtime_model", {}) or {}
    groups = runtime_model.get("dependency_groups", [])
    if not isinstance(groups, list):
        return {}
    group_map: dict[str, Dict[str, Any]] = {}
    for group in groups:
        if not isinstance(group, dict):
            continue
        group_id = str(group.get("group_id") or "").strip()
        if group_id:
            group_map[group_id] = group
    return group_map


def _explicit_command_markers(text: str) -> list[str]:
    return [match.lower() for match in re.findall(r"(?<!\w)(/[a-z0-9_]+)", str(text or "").lower())]


def _normalize_int_like(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _normalize_section_name(text: str) -> str:
    normalized = str(text or "").strip().lower()
    normalized = normalized.rstrip("ã€‚ï¼Ž.;:ï¼š。．：")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _continuation_binding_ids(state: GraphState) -> set[str]:
    session_state = state.get("session_execution_state", {}) or {}
    if not isinstance(session_state, dict):
        return set()
    active_ids = {
        str(item or "").strip()
        for item in session_state.get("active_binding_ids", []) or []
        if str(item or "").strip()
    }
    if not active_ids:
        return set()
    query = str(state.get("user_query") or "").strip()
    if not query:
        return active_ids
    if (
        _looks_context_dependent(query)
        or _looks_like_step_advance(query)
        or _looks_like_refinement_followup(state, query)
        or _looks_like_option_selection_followup(state, query)
    ):
        return active_ids
    return set()


def _scope_candidate_variants(value: Any) -> set[str]:
    text = str(value or "").strip().lower()
    if not text:
        return set()
    slug = _normalize_slug(text)
    variants = {text, slug, _normalize_section_name(text)}
    prefixes = (
        "module",
        "support_module",
        "followup_module",
        "primary_workflow",
        "supplementary_workflow",
        "phase",
        "output",
        "starter",
        "artifact_gate",
        "workflow",
        "mode",
        "generic",
        "step",
    )
    variants.update({f"{prefix}:{slug}" for prefix in prefixes if slug})
    if ":" in text:
        _prefix, suffix = text.split(":", 1)
        suffix_variants = {
            suffix.strip(),
            _normalize_slug(suffix),
            _normalize_section_name(suffix),
        }
        variants.update({item for item in suffix_variants if item})
        for prefix in prefixes:
            for item in suffix_variants:
                if item:
                    variants.add(f"{prefix}:{item}")
    return {item for item in variants if item}



def _binding_scope_matches(
    binding: Dict[str, Any],
    state: GraphState,
    selected_workflow: Dict[str, Any] | None,
    selected_module: Dict[str, Any] | None,
) -> bool:
    scope_id = str(binding.get("scope_id") or "").strip().lower()
    if not scope_id:
        return True
    session_state = state.get("session_execution_state", {}) or {}
    candidates: set[str] = set()
    for value in (
        session_state.get("active_mode") if isinstance(session_state, dict) else "",
        session_state.get("active_workflow") if isinstance(session_state, dict) else "",
        session_state.get("active_service_block_id") if isinstance(session_state, dict) else "",
        session_state.get("active_service_block_title") if isinstance(session_state, dict) else "",
        session_state.get("primary_support_module_id") if isinstance(session_state, dict) else "",
        session_state.get("primary_support_module_title") if isinstance(session_state, dict) else "",
        state.get("workflow_progress", {}).get("workflow_id") if isinstance(state.get("workflow_progress"), dict) else "",
        state.get("workflow_progress", {}).get("workflow_title") if isinstance(state.get("workflow_progress"), dict) else "",
        selected_workflow.get("id") if isinstance(selected_workflow, dict) else "",
        selected_workflow.get("title") if isinstance(selected_workflow, dict) else "",
        selected_workflow.get("workflow_name") if isinstance(selected_workflow, dict) else "",
        selected_module.get("title") if isinstance(selected_module, dict) else "",
        selected_module.get("module_id") if isinstance(selected_module, dict) else "",
        selected_module.get("id") if isinstance(selected_module, dict) else "",
        selected_module.get("block_id") if isinstance(selected_module, dict) else "",
    ):
        candidates.update(_scope_candidate_variants(value))
    for value in _hybrid_active_target_service_block_ids(state):
        candidates.update(_scope_candidate_variants(value))
    for value in _queued_followup_service_block_ids(state):
        candidates.update(_scope_candidate_variants(value))
    if isinstance(session_state, dict):
        for value in session_state.get("active_module_queue", []) or []:
            candidates.update(_scope_candidate_variants(value))

    has_selected_scope = bool(candidates)
    trigger_type = str(binding.get("trigger_type") or "").strip().lower()
    if scope_id not in candidates:
        if not has_selected_scope and trigger_type in {"starter", "artifact_gate", "command_trigger"}:
            return True
        return False
    step_order = binding.get("step_order")
    if step_order is None:
        return True
    active_step_order = None
    if isinstance(selected_module, dict):
        active_step_order = selected_module.get("order")
    elif isinstance(session_state, dict):
        active_step_order = session_state.get("active_step_order")
    normalized_active_step_order = _normalize_int_like(active_step_order)
    normalized_binding_step_order = _normalize_int_like(step_order)
    if normalized_active_step_order is None or normalized_binding_step_order is None:
        return active_step_order == step_order
    return normalized_active_step_order == normalized_binding_step_order


def _binding_signal_matches(
    binding: Dict[str, Any],
    query: str,
    explicit_commands: list[str],
    forced_turn_intent: str | None,
) -> bool:
    trigger_signals = [
        str(signal or "").strip().lower()
        for signal in binding.get("trigger_signals", []) or []
        if str(signal or "").strip()
    ]
    if str(binding.get("trigger_type") or "").strip() == "command_trigger":
        return bool(set(trigger_signals) & set(explicit_commands))
    if forced_turn_intent in {"structured_generation_brief", "freeform_generation_request"} and any(
        token in query for token in trigger_signals
    ):
        return True
    if not trigger_signals:
        return True
    return any(signal in query for signal in trigger_signals)


def _artifact_filename_matches(filename: str, patterns: list[str]) -> bool:
    target = Path(str(filename or "").strip()).name.lower()
    if not target:
        return False
    for pattern in patterns:
        candidate = Path(str(pattern or "").strip()).name.lower()
        if candidate and candidate == target:
            return True
    return False


def _artifact_gate_status(
    binding: Dict[str, Any],
    state: GraphState,
) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
    contract = binding.get("artifact_contract", {}) or {}
    artifact_role = str(contract.get("artifact_role") or "").strip()
    binding_id = str(binding.get("binding_id") or "").strip()
    patterns = [
        str(pattern or "").strip()
        for pattern in contract.get("filename_patterns", []) or []
        if str(pattern or "").strip()
    ]
    uploads = _session_uploads(state)
    matched_uploads = [
        upload
        for upload in uploads
        if _artifact_filename_matches(str(upload.get("filename") or ""), patterns)
    ]
    session_state = state.get("session_execution_state", {}) or {}
    prior_status = {}
    if isinstance(session_state, dict) and artifact_role:
        artifact_gate_status = session_state.get("artifact_gate_status", {}) or {}
        if isinstance(artifact_gate_status, dict):
            if binding_id:
                candidate = artifact_gate_status.get(binding_id, {}) or {}
                if isinstance(candidate, dict):
                    prior_status = candidate
            if not prior_status:
                candidate = artifact_gate_status.get(artifact_role, {}) or {}
                if isinstance(candidate, dict):
                    candidate_binding_id = str(candidate.get("binding_id") or "").strip()
                    if not candidate_binding_id or candidate_binding_id == binding_id:
                        prior_status = candidate
    if not matched_uploads and bool(prior_status.get("satisfied")):
        prior_upload_ids = [
            str(item or "").strip()
            for item in prior_status.get("matched_upload_ids", []) or []
            if str(item or "").strip()
        ]
        prior_filenames = [
            str(item or "").strip()
            for item in prior_status.get("matched_filenames", []) or []
            if str(item or "").strip()
        ]
        matched_uploads = [
            {
                "id": prior_upload_ids[index] if index < len(prior_upload_ids) else "",
                "filename": prior_filenames[index] if index < len(prior_filenames) else "",
            }
            for index in range(max(len(prior_upload_ids), len(prior_filenames)))
        ]
    status = {
        "artifact_role": artifact_role or None,
        "required_for_progression": bool(contract.get("required_for_progression")),
        "matched_upload_ids": [str(upload.get("id") or "").strip() for upload in matched_uploads if str(upload.get("id") or "").strip()],
        "matched_filenames": [str(upload.get("filename") or "").strip() for upload in matched_uploads if str(upload.get("filename") or "").strip()],
        "satisfied": bool(matched_uploads),
        "missing_artifact_prompt": str(contract.get("missing_artifact_prompt") or "").strip() or None,
        "binding_id": binding_id or None,
    }
    if prior_status and not status["missing_artifact_prompt"]:
        status["missing_artifact_prompt"] = str(prior_status.get("missing_artifact_prompt") or "").strip() or None
    return status, matched_uploads


def _match_phase_resource_bindings(
    state: GraphState,
    planner_output: Dict[str, Any],
    selected_workflow: Dict[str, Any] | None,
    selected_module: Dict[str, Any] | None,
    forced_turn_intent: str | None,
) -> list[Dict[str, Any]]:
    query = _combined_query_text(state, planner_output)
    explicit_commands = _explicit_command_markers(query)
    continuation_ids = _continuation_binding_ids(state)
    matched: list[Dict[str, Any]] = []
    for binding in _phase_resource_bindings(state):
        trigger_type = str(binding.get("trigger_type") or "").strip()
        if trigger_type in {"command_trigger", "artifact_gate"}:
            continue
        if not _binding_scope_matches(binding, state, selected_workflow, selected_module):
            continue
        selected_step_scope_id = (
            str(selected_module.get("step_scope_id") or "").strip()
            if isinstance(selected_module, dict)
            else ""
        )
        selected_step_resources = (
            bool(str(selected_module.get("resource_file") or selected_module.get("primary_resource") or "").strip())
            or bool(
                [
                    str(item).strip()
                    for item in (
                        selected_module.get("activation", {}).get("direct_resource_files", [])
                        if isinstance(selected_module.get("activation"), dict)
                        else []
                    )
                    if str(item).strip()
                ]
            )
        ) if isinstance(selected_module, dict) else False
        binding_scope_id = str(binding.get("scope_id") or "").strip().lower()
        if (
            selected_step_scope_id
            and selected_step_resources
            and binding.get("step_order") is None
            and binding_scope_id.startswith("phase:")
        ):
            continue
        binding_id = str(binding.get("binding_id") or "").strip()
        if not _binding_signal_matches(binding, query, explicit_commands, forced_turn_intent) and binding_id not in continuation_ids:
            continue
        matched.append(binding)
    return sorted(matched, key=lambda item: int(item.get("priority") or 100))


def _match_command_bindings(
    state: GraphState,
    planner_output: Dict[str, Any],
) -> list[Dict[str, Any]]:
    query = _combined_query_text(state, planner_output)
    explicit_commands = _explicit_command_markers(query)
    if not explicit_commands:
        return []
    matched: list[Dict[str, Any]] = []
    for binding in _phase_resource_bindings(state):
        if str(binding.get("trigger_type") or "").strip() != "command_trigger":
            continue
        if _binding_signal_matches(binding, query, explicit_commands, None):
            matched.append(binding)
    return sorted(matched, key=lambda item: int(item.get("priority") or 100))


def _match_artifact_gate_bindings(
    state: GraphState,
    planner_output: Dict[str, Any],
    selected_workflow: Dict[str, Any] | None,
    selected_module: Dict[str, Any] | None,
    forced_turn_intent: str | None,
) -> list[Dict[str, Any]]:
    query = _combined_query_text(state, planner_output)
    explicit_commands = _explicit_command_markers(query)
    continuation_ids = _continuation_binding_ids(state)
    matched: list[Dict[str, Any]] = []
    for binding in _phase_resource_bindings(state):
        if str(binding.get("trigger_type") or "").strip() != "artifact_gate":
            continue
        if not _binding_scope_matches(binding, state, selected_workflow, selected_module):
            continue
        binding_id = str(binding.get("binding_id") or "").strip()
        if not _binding_signal_matches(binding, query, explicit_commands, forced_turn_intent) and binding_id not in continuation_ids:
            continue
        matched.append(binding)
    return sorted(matched, key=lambda item: int(item.get("priority") or 100))


def _resource_role_for_kind(resource_kind: str, resource: Dict[str, Any] | None) -> str:
    if isinstance(resource, dict):
        domain = str(resource.get("domain") or "").strip()
        if domain:
            return domain
    mapping = {
        "template_resource": "output_template",
        "artifact_template": "output_template",
        "schema_anchor": "output_template",
        "instruction_resource": "instruction_source",
        "rubric_resource": "instruction_source",
        "output_format_guide": "instruction_source",
        "resource_index": "instruction_source",
    }
    return mapping.get(str(resource_kind or "").strip(), "instruction_source")


def _expand_dependency_group_requests(
    state: GraphState,
    binding: Dict[str, Any],
    defaults: Dict[str, Any],
) -> list[Dict[str, Any]]:
    group_map = _dependency_group_map(state)
    resource_map = _runtime_resource_map(state)
    requests: list[Dict[str, Any]] = []
    for group_id in binding.get("dependency_groups", []) or []:
        group = group_map.get(str(group_id))
        if not group:
            continue
        for resource_id in group.get("resource_ids", []) or []:
            resource = resource_map.get(str(resource_id))
            filename = str(resource.get("filename") or "").strip() if isinstance(resource, dict) else ""
            requests.append(
                to_plain_dict(
                    ResourceRequest(
                        filename=filename or None,
                        resource_id=str(resource_id or "").strip() or None,
                        resource_role=_resource_role_for_kind(defaults.get("resource_kind"), resource),
                        binding_id=defaults.get("binding_id"),
                        resource_kind=defaults.get("resource_kind"),
                        dependency_group_id=str(group_id or "").strip() or None,
                        artifact_role=defaults.get("artifact_role"),
                        required_for_progression=bool(defaults.get("required_for_progression")),
                        purpose=defaults.get("purpose"),
                        query_text=defaults.get("query_text"),
                        context_hints=list(defaults.get("context_hints", [])),
                        objective=defaults.get("objective"),
                        stage_label=defaults.get("stage_label"),
                        request_reason=defaults.get("request_reason"),
                        load_strategy_hint=_instruction_load_strategy_for_state(state, filename) if filename else None,
                        required=True,
                    )
                )
            )
    return requests


def _derive_binding_activation(
    state: GraphState,
    planner_output: Dict[str, Any],
    selected_workflow: Dict[str, Any] | None,
    selected_module: Dict[str, Any] | None,
    forced_turn_intent: str | None,
) -> Dict[str, Any]:
    matched_bindings = []
    matched_bindings.extend(
        _match_phase_resource_bindings(state, planner_output, selected_workflow, selected_module, forced_turn_intent)
    )
    matched_bindings.extend(_match_command_bindings(state, planner_output))
    matched_bindings.extend(
        _match_artifact_gate_bindings(state, planner_output, selected_workflow, selected_module, forced_turn_intent)
    )

    resource_map = _runtime_resource_map(state)
    active_binding_ids: list[str] = []
    active_dependency_group_ids: list[str] = []
    active_artifact_roles: list[str] = []
    artifact_gate_status: dict[str, Any] = {}
    binding_requests: list[Dict[str, Any]] = []
    seen_request_keys: set[tuple[str, str, str]] = set()
    stage_label = (
        str(selected_module.get("title") or "").strip()
        if isinstance(selected_module, dict)
        else str(selected_workflow.get("title") or "").strip()
        if isinstance(selected_workflow, dict)
        else None
    )
    query_text = str(planner_output.get("retrievalPlan", {}).get("query_text") or state.get("user_query") or "").strip() or None

    for binding in matched_bindings:
        binding_id = str(binding.get("binding_id") or "").strip()
        if binding_id:
            _append_unique(active_binding_ids, binding_id)
        contract = binding.get("artifact_contract", {}) or {}
        artifact_role = str(contract.get("artifact_role") or "").strip() or None
        if artifact_role:
            _append_unique(active_artifact_roles, artifact_role)
        defaults = {
            "binding_id": binding_id or None,
            "resource_kind": (
                str((binding.get("resource_kinds") or [None])[0] or "").strip() or None
            ),
            "artifact_role": artifact_role,
            "required_for_progression": bool(contract.get("required_for_progression")),
            "purpose": "template_support"
            if _resource_role_for_kind(str((binding.get("resource_kinds") or [None])[0] or ""), None) == "output_template"
            else "instruction_support",
            "query_text": query_text,
            "context_hints": [],
            "objective": str(binding.get("objective") or "").strip() or None,
            "stage_label": stage_label,
            "request_reason": str(binding.get("activation_reason") or "").strip() or "phase_resource_binding",
        }
        if binding.get("dependency_groups"):
            for group_id in binding.get("dependency_groups", []) or []:
                _append_unique(active_dependency_group_ids, str(group_id or "").strip())
            for request in _expand_dependency_group_requests(state, binding, defaults):
                key = (
                    str(request.get("binding_id") or ""),
                    str(request.get("dependency_group_id") or ""),
                    str(request.get("filename") or request.get("resource_id") or ""),
                )
                if key not in seen_request_keys:
                    seen_request_keys.add(key)
                    binding_requests.append(request)
        for index, resource_id in enumerate(binding.get("resource_ids", []) or []):
            resource = resource_map.get(str(resource_id))
            if not resource:
                continue
            resource_kind_values = binding.get("resource_kinds", []) or []
            resource_kind = str(
                resource_kind_values[index] if index < len(resource_kind_values) else defaults.get("resource_kind") or ""
            ).strip() or None
            filename = str(resource.get("filename") or "").strip()
            request = to_plain_dict(
                ResourceRequest(
                    filename=filename or None,
                    resource_id=str(resource_id or "").strip() or None,
                    resource_role=_resource_role_for_kind(resource_kind or "", resource),
                    binding_id=binding_id or None,
                    resource_kind=resource_kind,
                    artifact_role=artifact_role,
                    required_for_progression=bool(contract.get("required_for_progression")),
                    purpose="template_support" if str(resource.get("domain") or "") == "output_template" else "instruction_support",
                    query_text=query_text,
                    objective=str(binding.get("objective") or "").strip() or None,
                    stage_label=stage_label,
                    request_reason=str(binding.get("activation_reason") or "").strip() or "phase_resource_binding",
                    load_strategy_hint=_instruction_load_strategy_for_state(state, filename) if filename else None,
                    required=True,
                )
            )
            key = (
                str(request.get("binding_id") or ""),
                str(request.get("dependency_group_id") or ""),
                str(request.get("filename") or request.get("resource_id") or ""),
            )
            if key not in seen_request_keys:
                seen_request_keys.add(key)
                binding_requests.append(request)
        if str(binding.get("trigger_type") or "").strip() == "artifact_gate":
            status, matched_uploads = _artifact_gate_status(binding, state)
            if binding_id:
                artifact_gate_status[binding_id] = status
            elif artifact_role:
                artifact_gate_status[artifact_role] = status
            for upload in matched_uploads:
                request = to_plain_dict(
                    ResourceRequest(
                        filename=str(upload.get("filename") or "").strip() or None,
                        resource_id=str(upload.get("id") or "").strip() or None,
                        resource_role="knowledge_source",
                        binding_id=binding_id or None,
                        artifact_role=artifact_role,
                        required_for_progression=bool(contract.get("required_for_progression")),
                        purpose="session_upload",
                        query_text=query_text,
                        objective=str(binding.get("objective") or "").strip() or None,
                        stage_label=stage_label,
                        request_reason=str(binding.get("activation_reason") or "").strip() or "artifact_gate_binding",
                        required=True,
                    )
                )
                key = (
                    str(request.get("binding_id") or ""),
                    str(request.get("dependency_group_id") or ""),
                    str(request.get("filename") or request.get("resource_id") or ""),
                )
                if key not in seen_request_keys:
                    seen_request_keys.add(key)
                    binding_requests.append(request)

    return {
        "binding_requests": binding_requests,
        "active_binding_ids": active_binding_ids,
        "active_dependency_group_ids": active_dependency_group_ids,
        "active_artifact_roles": active_artifact_roles,
        "artifact_gate_status": artifact_gate_status,
    }


def _derive_binding_activation_for_scope_id(
    state: GraphState,
    scope_id: str,
    *,
    stage_label: str | None = None,
    query_text: str | None = None,
    include_descendant_scope_bindings: bool = True,
    strict_scope_id_match: bool = False,
) -> Dict[str, Any]:
    target_scope_id = str(scope_id or "").strip()
    if not target_scope_id:
        return {
            "binding_requests": [],
            "active_binding_ids": [],
            "active_dependency_group_ids": [],
            "active_artifact_roles": [],
            "artifact_gate_status": {},
        }

    target_scope_variants = _scope_candidate_variants(target_scope_id)
    matched_bindings = []
    for item in _phase_resource_bindings(state):
        binding_scope_id = str(item.get("scope_id") or "").strip()
        if not binding_scope_id:
            continue
        if strict_scope_id_match:
            if binding_scope_id == target_scope_id:
                matched_bindings.append(item)
            continue
        if _identifier_equivalent(binding_scope_id, target_scope_id):
            matched_bindings.append(item)
            continue
        if _scope_candidate_variants(binding_scope_id) & target_scope_variants:
            matched_bindings.append(item)

    service_block = _service_block_by_id(state, target_scope_id)
    if include_descendant_scope_bindings and isinstance(service_block, dict):
        service_block_id = str(service_block.get("block_id") or "").strip()
        descendant_binding_markers: list[str] = []
        if service_block_id:
            for unit in _instruction_units(state):
                parent_block_id = str(unit.get("parent_block_id") or "").strip()
                declared_binding_id = str(unit.get("declared_binding_id") or "").strip()
                if not parent_block_id or not declared_binding_id:
                    continue
                if not _identifier_equivalent(parent_block_id, service_block_id):
                    continue
                _append_unique(descendant_binding_markers, declared_binding_id)
        for marker in _descendant_heading_scope_markers_for_service_block(state, service_block):
            _append_unique(descendant_binding_markers, marker)
        if descendant_binding_markers:
            seen_binding_ids = {
                str(item.get("binding_id") or "").strip()
                for item in matched_bindings
                if isinstance(item, dict)
            }
            for item in _phase_resource_bindings(state):
                binding_id = str(item.get("binding_id") or "").strip()
                binding_scope_id = str(item.get("scope_id") or "").strip()
                binding_title = str(item.get("title") or "").strip()
                if not binding_id or binding_id in seen_binding_ids:
                    continue
                if any(
                    _identifier_equivalent(candidate, marker)
                    for candidate in (binding_id, binding_scope_id, binding_title)
                    if candidate
                    for marker in descendant_binding_markers
                ):
                    matched_bindings.append(item)
                    seen_binding_ids.add(binding_id)
    resource_map = _runtime_resource_map(state)
    active_binding_ids: list[str] = []
    active_dependency_group_ids: list[str] = []
    active_artifact_roles: list[str] = []
    artifact_gate_status: dict[str, Any] = {}
    binding_requests: list[Dict[str, Any]] = []
    seen_request_keys: set[tuple[str, str, str]] = set()

    for binding in matched_bindings:
        binding_id = str(binding.get("binding_id") or "").strip()
        if binding_id:
            _append_unique(active_binding_ids, binding_id)
        contract = binding.get("artifact_contract", {}) or {}
        artifact_role = str(contract.get("artifact_role") or "").strip() or None
        if artifact_role:
            _append_unique(active_artifact_roles, artifact_role)
        defaults = {
            "binding_id": binding_id or None,
            "resource_kind": (
                str((binding.get("resource_kinds") or [None])[0] or "").strip() or None
            ),
            "artifact_role": artifact_role,
            "required_for_progression": bool(contract.get("required_for_progression")),
            "purpose": "template_support"
            if _resource_role_for_kind(str((binding.get("resource_kinds") or [None])[0] or ""), None) == "output_template"
            else "instruction_support",
            "query_text": query_text,
            "context_hints": [],
            "objective": str(binding.get("objective") or "").strip() or None,
            "stage_label": stage_label,
            "request_reason": str(binding.get("activation_reason") or "").strip() or "phase_resource_binding",
        }
        if binding.get("dependency_groups"):
            for group_id in binding.get("dependency_groups", []) or []:
                _append_unique(active_dependency_group_ids, str(group_id or "").strip())
            for request in _expand_dependency_group_requests(state, binding, defaults):
                key = (
                    str(request.get("binding_id") or ""),
                    str(request.get("dependency_group_id") or ""),
                    str(request.get("filename") or request.get("resource_id") or ""),
                )
                if key not in seen_request_keys:
                    seen_request_keys.add(key)
                    binding_requests.append(request)
        for index, resource_id in enumerate(binding.get("resource_ids", []) or []):
            resource = resource_map.get(str(resource_id))
            if not resource:
                continue
            resource_kind_values = binding.get("resource_kinds", []) or []
            resource_kind = str(
                resource_kind_values[index] if index < len(resource_kind_values) else defaults.get("resource_kind") or ""
            ).strip() or None
            filename = str(resource.get("filename") or "").strip()
            request = to_plain_dict(
                ResourceRequest(
                    filename=filename or None,
                    resource_id=str(resource_id or "").strip() or None,
                    resource_role=_resource_role_for_kind(resource_kind or "", resource),
                    binding_id=binding_id or None,
                    resource_kind=resource_kind,
                    artifact_role=artifact_role,
                    required_for_progression=bool(contract.get("required_for_progression")),
                    purpose="template_support" if str(resource.get("domain") or "") == "output_template" else "instruction_support",
                    query_text=query_text,
                    objective=str(binding.get("objective") or "").strip() or None,
                    stage_label=stage_label,
                    request_reason=str(binding.get("activation_reason") or "").strip() or "phase_resource_binding",
                    load_strategy_hint=_instruction_load_strategy_for_state(state, filename) if filename else None,
                    required=True,
                )
            )
            key = (
                str(request.get("binding_id") or ""),
                str(request.get("dependency_group_id") or ""),
                str(request.get("filename") or request.get("resource_id") or ""),
            )
            if key not in seen_request_keys:
                seen_request_keys.add(key)
                binding_requests.append(request)

    return {
        "binding_requests": binding_requests,
        "active_binding_ids": active_binding_ids,
        "active_dependency_group_ids": active_dependency_group_ids,
        "active_artifact_roles": active_artifact_roles,
        "artifact_gate_status": artifact_gate_status,
    }


def _select_support_resources(state: GraphState, query: str) -> list[Dict[str, Any]]:
    runtime_model = state.get("instruction_runtime_model", {}) or {}
    support_modules = runtime_model.get("support_modules", [])
    resource_map = _runtime_resource_map(state)
    selected: list[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    if not isinstance(support_modules, list):
        return selected

    for module in support_modules:
        if not isinstance(module, dict):
            continue
        triggers = [str(item or "").strip().lower() for item in module.get("activation_triggers", []) or []]
        if triggers and not any(trigger and trigger in query for trigger in triggers):
            continue
        for resource_id in module.get("resource_ids", []) or []:
            resource = resource_map.get(str(resource_id))
            if resource and resource["resource_id"] not in seen_ids:
                seen_ids.add(resource["resource_id"])
                selected.append(resource)
    return selected


def _is_layered_procedure_workflow(workflow: Dict[str, Any] | None) -> bool:
    if not isinstance(workflow, dict) or not workflow:
        return False
    return any(
        isinstance(step, dict) and (step.get("step_scope_id") or step.get("activation"))
        for step in _workflow_steps(workflow)
    )


def _layered_scope_context(
    state: GraphState,
    selected_workflow: Dict[str, Any] | None,
    selected_module: Dict[str, Any] | None,
) -> Dict[str, Any]:
    if not isinstance(selected_module, dict) or not selected_module:
        return {}

    step_scope_id = str(selected_module.get("step_scope_id") or "").strip()
    if not step_scope_id:
        return {}

    runtime_model = state.get("instruction_runtime_model", {}) or {}
    procedure_steps = [
        item
        for item in runtime_model.get("procedure_steps", []) or []
        if isinstance(item, dict)
    ]
    procedure_step_definition = next(
        (
            item
            for item in procedure_steps
            if str(item.get("step_id") or "").strip() == step_scope_id
        ),
        {},
    )
    normalized_step_definition = procedure_step_definition
    if str(procedure_step_definition.get("execution_mode") or "").strip() == "bundled":
        bundled_step_ids = [
            str(item or "").strip()
            for item in procedure_step_definition.get("bundled_step_ids", []) or []
            if str(item or "").strip()
        ]
        if not bundled_step_ids:
            procedure_id = str(procedure_step_definition.get("procedure_id") or "").strip()
            normalized_step_definition = next(
                (
                    item
                    for item in procedure_steps
                    if str(item.get("procedure_id") or "").strip() == procedure_id
                    and step_scope_id
                    in [
                        str(member or "").strip()
                        for member in item.get("bundled_step_ids", []) or []
                        if str(member or "").strip()
                    ]
                ),
                procedure_step_definition,
            )
    workflow_title = (
        str(selected_workflow.get("workflow_name") or selected_workflow.get("title") or "").strip()
        if isinstance(selected_workflow, dict)
        else ""
    )
    workflow_slug_source = (
        str(selected_workflow.get("title") or selected_workflow.get("workflow_name") or "workflow")
        if isinstance(selected_workflow, dict)
        else "workflow"
    )
    activation = selected_module.get("activation", {}) if isinstance(selected_module.get("activation"), dict) else {}
    execution_mode = (
        "bundled"
        if str(
            normalized_step_definition.get("execution_mode")
            or selected_module.get("execution_mode")
            or ""
        ).strip() == "bundled"
        else None
    )
    bundled_step_ids = [
        str(item or "").strip()
        for item in (
            normalized_step_definition.get("bundled_step_ids")
            or selected_module.get("bundled_step_ids", [])
            or []
        )
        if str(item or "").strip()
    ]
    step_resource_refs = [
        str(item or "").strip()
        for item in normalized_step_definition.get("resource_refs", []) or []
        if str(item or "").strip()
    ]
    bundled_resource_refs = [
        str(item or "").strip()
        for item in (
            normalized_step_definition.get("bundled_resource_refs")
            or selected_module.get("bundled_resource_refs", [])
            or []
        )
        if str(item or "").strip()
    ]
    activation_direct_resource_files = [
        str(item or "").strip()
        for item in activation.get("direct_resource_files", []) or []
        if str(item or "").strip()
    ]
    planner_mode = str(state.get("planner_mode") or "").strip().lower()
    if execution_mode == "bundled" and bundled_resource_refs:
        direct_resource_files = bundled_resource_refs
    elif step_resource_refs and (planner_mode == "hybrid_active" or not activation_direct_resource_files):
        direct_resource_files = step_resource_refs
    else:
        direct_resource_files = activation_direct_resource_files
    if execution_mode == "bundled" and not direct_resource_files and step_resource_refs:
        direct_resource_files = step_resource_refs
    if not direct_resource_files:
        primary_resource = str(selected_module.get("resource_file") or selected_module.get("primary_resource") or "").strip()
        if primary_resource:
            direct_resource_files.append(primary_resource)

    support_module_id = str(activation.get("primary_support_module_id") or "").strip() or None
    support_module_title = str(activation.get("primary_support_module_title") or "").strip() or None
    support_module = _support_module_rule_map(state).get(support_module_id or "")
    support_resources: list[Dict[str, Any]] = []
    if isinstance(support_module, dict):
        if not support_module_title:
            support_module_title = str(support_module.get("title") or "").strip() or None
        for resource_id in support_module.get("resource_ids", []) or []:
            resource = _runtime_resource_map(state).get(str(resource_id or "").strip())
            if resource:
                support_resources.append(resource)
    else:
        for filename in activation.get("support_resource_files", []) or []:
            resource = _runtime_resource_by_filename(state, str(filename or "").strip())
            if resource:
                support_resources.append(resource)

    direct_resource_ids = [
        str(resource.get("resource_id") or "").strip()
        for resource in (_runtime_resource_by_filename(state, filename) for filename in direct_resource_files)
        if isinstance(resource, dict) and str(resource.get("resource_id") or "").strip()
    ]
    support_resource_ids = [
        str(resource.get("resource_id") or "").strip()
        for resource in support_resources
        if str(resource.get("resource_id") or "").strip()
    ]

    return {
        "primary_scope": to_plain_dict(
            InstructionScopeSelection(
                scope_id=f"workflow:{_normalize_slug(workflow_slug_source)}",
                scope_type="workflow",
                title=workflow_title or None,
                reason="selected_procedure_workflow",
            )
        ),
        "active_step_scope_id": step_scope_id,
        "active_execution_mode": execution_mode,
        "active_bundled_step_ids": bundled_step_ids if execution_mode == "bundled" else [],
        "bundled_execution_completed": False,
        "bundled_entry_step_id": (
            bundled_step_ids[0]
            if execution_mode == "bundled" and bundled_step_ids
            else (step_scope_id if execution_mode == "bundled" else None)
        ),
        "direct_resource_files": direct_resource_files,
        "support_resources": support_resources,
        "primary_support_module_id": support_module_id,
        "primary_support_module_title": support_module_title,
        "procedure_step_activation": to_plain_dict(
            ProcedureStepActivation(
                step_scope_id=step_scope_id,
                step_order=_normalize_int_like(selected_module.get("order")),
                step_title=str(selected_module.get("title") or "").strip() or None,
                resource_ids=direct_resource_ids,
                primary_support_module_id=support_module_id,
            )
        ),
        "primary_support_module_activation": (
            to_plain_dict(
                PrimarySupportModuleActivation(
                    support_module_id=support_module_id,
                    support_module_title=support_module_title,
                    resource_ids=support_resource_ids,
                    step_scope_id=step_scope_id,
                )
            )
            if support_module_id
            else None
        ),
    }


def _append_unique(items: list[str], value: str) -> None:
    cleaned = str(value or "").strip()
    if cleaned and cleaned not in items:
        items.append(cleaned)


def _record_request_provenance(
    provenance_map: dict[str, Dict[str, Any]],
    *,
    filename: str | None = None,
    resource_id: str | None = None,
    source_layer: str | None = None,
    step_scope_id: str | None = None,
    support_module_id: str | None = None,
) -> None:
    payload = {
        "source_layer": source_layer,
        "step_scope_id": step_scope_id,
        "support_module_id": support_module_id,
    }
    cleaned_filename = str(filename or "").strip()
    cleaned_resource_id = str(resource_id or "").strip()
    if cleaned_filename:
        provenance_map[f"filename:{cleaned_filename.lower()}"] = payload
    if cleaned_resource_id:
        provenance_map[f"resource_id:{cleaned_resource_id.lower()}"] = payload


def _request_provenance(
    execution_context: Dict[str, Any],
    *,
    filename: str | None = None,
    resource_id: str | None = None,
) -> Dict[str, Any]:
    provenance_map = (
        execution_context.get("resource_request_provenance", {})
        if isinstance(execution_context.get("resource_request_provenance"), dict)
        else {}
    )
    cleaned_filename = str(filename or "").strip().lower()
    cleaned_resource_id = str(resource_id or "").strip().lower()
    if cleaned_filename and f"filename:{cleaned_filename}" in provenance_map:
        return dict(provenance_map[f"filename:{cleaned_filename}"])
    if cleaned_resource_id and f"resource_id:{cleaned_resource_id}" in provenance_map:
        return dict(provenance_map[f"resource_id:{cleaned_resource_id}"])
    return {}


def _binding_can_supply_resource_request(request: Dict[str, Any]) -> bool:
    binding_id = str(request.get("binding_id") or "").strip().lower()
    return not binding_id.startswith("phase:")


def _followup_module_resource_requests(
    state: GraphState,
    module_id: str,
    module_title: str | None,
) -> list[dict]:
    requests: list[dict] = []
    seen: set[tuple[str, str]] = set()
    query_text = str(state.get("user_query") or "").strip() or None
    stage_label = str(module_title or "").strip() or None
    for filename in _followup_module_explicit_resource_files(state, module_id):
        resource = _runtime_resource_by_filename(state, filename)
        if not isinstance(resource, dict):
            continue
        domain = str(resource.get("domain") or "").strip()
        role = domain or "instruction_source"
        key = (role, str(resource.get("filename") or "").strip())
        if not key[1] or key in seen:
            continue
        seen.add(key)
        requests.append(
            to_plain_dict(
                ResourceRequest(
                    filename=key[1],
                    resource_id=str(resource.get("resource_id") or "").strip() or None,
                    resource_role=role,
                    purpose="template_support" if role == "output_template" else "instruction_support",
                    query_text=query_text,
                    objective=stage_label,
                    stage_label=stage_label,
                    request_reason="followup_module_explicit_resource",
                    load_strategy_hint=_instruction_load_strategy_for_state(state, key[1]),
                    source_layer="support_module",
                    support_module_id=module_id or None,
                    required=True,
                )
            )
        )
    if requests:
        return requests
    binding_activation = _derive_binding_activation_for_scope_id(
        state,
        module_id,
        stage_label=stage_label,
        query_text=query_text,
        include_descendant_scope_bindings=True,
        strict_scope_id_match=False,
    )
    for request in binding_activation.get("binding_requests", []):
        if not isinstance(request, dict):
            continue
        filename = str(request.get("filename") or "").strip()
        role = str(request.get("resource_role") or "").strip()
        key = (role, filename)
        if not filename or key in seen:
            continue
        if role not in {"instruction_source", "output_template"}:
            continue
        seen.add(key)
        normalized_request = dict(request)
        normalized_request["request_reason"] = str(
            normalized_request.get("request_reason") or "followup_module_binding_resource"
        )
        normalized_request["support_module_id"] = module_id or None
        normalized_request["required"] = True
        requests.append(normalized_request)
    return requests


def _merge_filename_filters(filters: dict, filenames: list[str]) -> dict:
    if not filenames:
        return filters
    merged = dict(filters)
    existing = merged.get("filename")
    if not existing:
        if len(filenames) == 1:
            merged["filename"] = filenames[0]
        else:
            merged["filename_in"] = filenames
        return merged

    values = [existing] if isinstance(existing, str) else list(existing) if isinstance(existing, list) else []
    values = [value for value in values if value]
    for filename in filenames:
        if filename not in values:
            values.append(filename)
    if len(values) == 1:
        merged["filename"] = values[0]
    else:
        merged.pop("filename", None)
        merged["filename_in"] = values
    return merged


def _recent_user_history_text(state: GraphState) -> str:
    history = state.get("chat_history", [])
    if not isinstance(history, list):
        return ""
    recent_user_messages = []
    for item in reversed(history):
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "").strip().lower() != "user":
            continue
        content = str(item.get("content") or "").strip()
        if content:
            recent_user_messages.append(content)
        if len(recent_user_messages) >= 2:
            break
    return " ".join(reversed(recent_user_messages)).strip()


def _recent_assistant_history_text(state: GraphState, limit: int = 2) -> str:
    history = state.get("chat_history", [])
    if not isinstance(history, list):
        return ""
    recent_assistant_messages = []
    for item in reversed(history):
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "").strip().lower() != "assistant":
            continue
        content = str(item.get("content") or "").strip()
        if content:
            recent_assistant_messages.append(content)
        if len(recent_assistant_messages) >= limit:
            break
    return " ".join(reversed(recent_assistant_messages)).strip()


def _split_query_fragments(query: str) -> list[str]:
    fragments = [
        piece.strip()
        for piece in re.split(r"[ï¼Œ,ã€‚ï¼›;ã€\n]+|(?:\s+(?:and|or|with|about|vs)\s+)|(?:ä»¥åŠ|ä¸¦ä¸”|è€Œä¸”|åŒæ™‚)", query)
        if piece and piece.strip()
    ]
    return [fragment for fragment in fragments if len(fragment) >= 2]


def _looks_context_dependent(query: str) -> bool:
    markers = [
        "é€™å€‹",
        "é‚£å€‹",
        "é€™æ®µ",
        "é‚£æ®µ",
        "å®ƒ",
        "ä»–",
        "å¥¹",
        "ç¬¬",
        "ä¸Šé¢",
        "å‰é¢",
        "å‰›æ‰",
        "this",
        "that",
        "it",
        "above",
        "previous",
    ]
    lowered = query.lower()
    return any(marker in query or marker in lowered for marker in markers)


def _looks_like_refinement_followup(state: GraphState, query: str) -> bool:
    lowered = str(query or "").strip().lower()
    if not lowered:
        return False

    refinement_markers = [
        "優化",
        "优化",
        "改寫",
        "改写",
        "重寫",
        "重写",
        "精煉",
        "精炼",
        "修訂",
        "修订",
        "調整",
        "调整",
        "完善",
        "潤飾",
        "润饰",
        "refine",
        "revise",
        "rewrite",
        "improve",
        "optimize",
        "optimise",
        "polish",
        "shorten",
        "expand",
    ]
    target_markers = [
        "prompt",
        "draft",
        "version",
        "output",
        "answer",
        "response",
        "material",
        "outline",
        "plan",
        "這份",
        "这份",
        "此",
        "這個",
        "这个",
        "上一版",
        "上一輪",
        "上一轮",
        "剛才",
        "刚才",
        "上面的",
        "前一版",
    ]
    has_refinement = any(marker.lower() in lowered for marker in refinement_markers)
    has_target = any(marker.lower() in lowered for marker in target_markers)
    if not (has_refinement and has_target):
        return False
    return bool(_recent_assistant_history_text(state, limit=1))


def _looks_like_option_selection_followup(state: GraphState, query: str) -> bool:
    text = " ".join(str(query or "").split()).strip()
    if not text:
        return False
    compact = text.upper().replace(" ", "")
    option_only = bool(re.fullmatch(r"[A-Z](?:[+/、,，]\s*[A-Z])+", compact))
    if not option_only:
        return False
    assistant_text = _recent_assistant_history_text(state, limit=1).lower()
    if not assistant_text:
        return False
    if any(marker in assistant_text for marker in ["請選", "请选", "choose", "select", "option", "方向"]):
        return True
    return bool(re.search(r"(?:^|[\s(（])a(?:[\s).、：:])", assistant_text))


def _dedupe_queries(candidates: list[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for item in candidates:
        text = " ".join(str(item or "").split()).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _session_uploads(state: GraphState) -> list[Dict[str, Any]]:
    uploads = state.get("session_uploads", [])
    if not isinstance(uploads, list):
        return []
    return [item for item in uploads if isinstance(item, dict)]


def _session_upload_map(state: GraphState) -> dict[str, Dict[str, Any]]:
    uploads = _session_uploads(state)
    return {
        str(item.get("id") or "").strip(): item
        for item in uploads
        if str(item.get("id") or "").strip()
    }


def _upload_filename_variants(upload: Dict[str, Any]) -> list[str]:
    filename = Path(str(upload.get("filename") or "").strip())
    variants = []
    if filename.name:
        variants.append(filename.name.lower())
    if filename.stem:
        variants.append(filename.stem.lower())
        variants.append(filename.stem.lower().replace("_", " "))
        variants.append(filename.stem.lower().replace("-", " "))
    return [variant for variant in variants if variant]


def _query_mentions_upload(query: str, upload: Dict[str, Any]) -> bool:
    lowered = query.lower()
    return any(variant and variant in lowered for variant in _upload_filename_variants(upload))


def _select_previous_upload(uploads: list[Dict[str, Any]], active_upload_ids: list[str]) -> list[Dict[str, Any]]:
    if not uploads:
        return []
    if active_upload_ids:
        active_id = active_upload_ids[-1]
        active_index = next(
            (index for index, upload in enumerate(uploads) if str(upload.get("id") or "").strip() == active_id),
            None,
        )
        if active_index is not None:
            if active_index > 0:
                return [uploads[active_index - 1]]
            return [uploads[0]]
    if len(uploads) >= 2:
        return [uploads[-2]]
    return uploads[-1:]


def _selected_session_uploads(state: GraphState, planner_output: Dict[str, Any]) -> list[Dict[str, Any]]:
    upload_map = _session_upload_map(state)
    uploads = list(upload_map.values())
    if not upload_map:
        return []
    selected_event_ids = {
        str(item or "").strip()
        for item in state.get("session_upload_event_ids", []) or []
        if str(item or "").strip()
    }
    if selected_event_ids:
        matched = [upload for upload in uploads if str(upload.get("id") or "").strip() in selected_event_ids]
        if matched:
            return matched
    query = _combined_query_text(state, planner_output)
    filename_matches = [upload for upload in uploads if _query_mentions_upload(query, upload)]
    if filename_matches:
        return filename_matches[-1:]
    markers = [
        "upload",
        "uploaded",
        "artifact",
        "file",
        "markdown",
        "md file",
        "analyze",
        "analyse",
        "review",
        "inspect",
        "this file",
        "this artifact",
        "this upload",
        "ä¸Šå‚³",
        "æª”æ¡ˆ",
        "æ–‡ä»¶",
        "ç”¢å‡º",
        "æˆå“",
        "åˆ†æž",
        "æª¢æŸ¥",
        "å¯©æŸ¥",
        "é€™å€‹æª”æ¡ˆ",
        "é€™ä»½æª”æ¡ˆ",
        "é€™å€‹æˆå“",
        "uploaded one",
        "review this",
        "analyze this",
        "analyse this",
        "compare this",
        "compare with template",
        "compare against template",
        "with the template",
        "against the template",
        "uploaded artifact",
        "uploaded file",
        "ä¸Šå‚³çš„",
        "æ¯”å°",
        "æ¯”è¼ƒ",
        "æ¨¡æ¿",
        "ç¯„æœ¬",
        "é€™ä»½",
        "é€™å€‹",
        "å®ƒ",
    ]
    latest_markers = [
        "latest",
        "newest",
        "most recent",
        "recent upload",
        "last upload",
        "æœ€æ–°",
        "æœ€è¿‘",
        "å‰›ä¸Šå‚³",
    ]
    first_markers = [
        "first upload",
        "earliest",
        "oldest",
        "first one",
        "ç¬¬ä¸€å€‹",
        "æœ€æ—©",
    ]
    previous_markers = [
        "previous upload",
        "previous one",
        "older upload",
        "earlier upload",
        "the older one",
        "ä¸Šä¸€å€‹",
        "å‰ä¸€å€‹",
        "ä¹‹å‰ä¸Šå‚³",
        "è¼ƒæ—©",
    ]
    active_upload_ids = [
        str(item or "").strip()
        for item in ((state.get("session_execution_state") or {}).get("active_session_upload_ids", []) if isinstance(state.get("session_execution_state"), dict) else [])
        if str(item or "").strip()
    ]
    latest_upload = uploads[-1:]
    if any(marker in query for marker in latest_markers):
        return latest_upload
    if any(marker in query for marker in first_markers):
        return uploads[:1]
    if any(marker in query for marker in previous_markers):
        previous_upload = _select_previous_upload(uploads, active_upload_ids)
        if previous_upload:
            return previous_upload
    if active_upload_ids and any(marker in query for marker in markers):
        matched_active = [upload_map[item] for item in active_upload_ids if item in upload_map]
        if matched_active:
            return matched_active
    if any(marker in query for marker in markers):
        return latest_upload
    if latest_upload and any(marker in query for marker in ("this", "that", "it", "é€™å€‹", "é€™ä»½", "å®ƒ")):
        return latest_upload
    return []


def _build_knowledge_query_plan(state: GraphState, planner_output: Dict[str, Any], plan_query_text: str) -> dict:
    user_query = str(state.get("user_query") or "").strip()
    normalized_query = str(planner_output.get("normalizedQuery") or "").strip()
    contextual_query = str(planner_output.get("contextualQuery") or "").strip()
    history_text = _recent_user_history_text(state)

    primary_query = plan_query_text or contextual_query or normalized_query or user_query
    always_variants: list[str] = []
    if contextual_query and contextual_query != primary_query:
        always_variants.append(contextual_query)
    if normalized_query and normalized_query not in {primary_query, contextual_query}:
        always_variants.append(normalized_query)
    if user_query and user_query not in {primary_query, contextual_query, normalized_query}:
        always_variants.append(user_query)

    query_fragments = _split_query_fragments(primary_query)
    if len(query_fragments) > 1:
        always_variants.extend(query_fragments)

    if _looks_context_dependent(primary_query) and history_text:
        always_variants.append(f"{history_text} {primary_query}".strip())

    fallback_queries: list[str] = []
    if query_fragments:
        fallback_queries.extend(sorted(query_fragments, key=len, reverse=True)[:2])
    if history_text and user_query:
        fallback_queries.append(f"{history_text} {user_query}".strip())
    if normalized_query:
        fallback_queries.append(normalized_query)
    if user_query:
        fallback_queries.append(user_query)

    query_variants = [variant for variant in _dedupe_queries(always_variants) if variant.lower() != primary_query.lower()]
    fallback_queries = [
        variant
        for variant in _dedupe_queries(fallback_queries)
        if variant.lower() not in {primary_query.lower(), *[item.lower() for item in query_variants]}
    ]
    return {
        "primary_query": primary_query,
        "query_variants": query_variants,
        "fallback_queries": fallback_queries,
        "retry_on_weak_results": bool(query_variants or fallback_queries),
    }


def _build_instruction_query_plan(
    state: GraphState,
    planner_output: Dict[str, Any],
    selected_workflow: Dict[str, Any] | None,
    selected_module: Dict[str, Any] | None,
    action_type: str,
) -> dict:
    user_query = str(state.get("user_query") or "").strip()
    normalized_query = str(planner_output.get("normalizedQuery") or "").strip()
    contextual_query = str(planner_output.get("contextualQuery") or "").strip()
    history_text = _recent_user_history_text(state)
    workflow_title = (
        str(selected_workflow.get("workflow_name") or selected_workflow.get("title") or "").strip()
        if isinstance(selected_workflow, dict)
        else ""
    )
    step_title = str(selected_module.get("title") or "").strip() if isinstance(selected_module, dict) else ""
    step_keywords = _derive_step_keywords(selected_module) if isinstance(selected_module, dict) else []
    runtime_model = state.get("instruction_runtime_model", {}) or {}
    primary_objective = ""
    if isinstance(runtime_model.get("primary_objectives"), list) and runtime_model["primary_objectives"]:
        primary_objective = str(runtime_model["primary_objectives"][0] or "").strip()

    stage_label = step_title or workflow_title or action_type
    objective = step_title or primary_objective or workflow_title or action_type
    primary_query_parts = [
        "instruction guidance",
        f"action {action_type}",
        f"workflow {workflow_title}" if workflow_title else "",
        f"step {step_title}" if step_title else "",
        f"objective {objective}" if objective else "",
    ]
    primary_query = " ".join(part for part in primary_query_parts if part).strip()

    query_variants = _dedupe_queries(
        [
            f"{workflow_title} {step_title} guidance".strip() if (workflow_title or step_title) else "",
            f"{step_title} guidance".strip() if step_title else "",
            f"{action_type} guidance {step_title}".strip() if step_title else "",
            f"{action_type} guidance {workflow_title}".strip() if workflow_title else "",
            " ".join(step_keywords[:3]).strip(),
        ]
    )
    context_hints = _dedupe_queries(
        [
            contextual_query,
            normalized_query,
            user_query,
            history_text,
        ]
    )
    fallback_queries = _dedupe_queries(
        [
            f"{step_title} {user_query}".strip() if step_title and user_query else "",
            f"{workflow_title} {normalized_query}".strip() if workflow_title and normalized_query else "",
        ]
    )
    query_variants = [variant for variant in query_variants if variant.lower() != primary_query.lower()]
    context_hints = [hint for hint in context_hints if hint.lower() != primary_query.lower()]
    fallback_queries = [
        fallback
        for fallback in fallback_queries
        if fallback.lower() not in {primary_query.lower(), *[item.lower() for item in query_variants], *[item.lower() for item in context_hints]}
    ]
    return {
        "primary_query": primary_query,
        "query_variants": query_variants,
        "context_hints": context_hints,
        "fallback_queries": fallback_queries,
        "objective": objective or None,
        "stage_label": stage_label or None,
    }


def _instruction_load_strategy(filename: str) -> str:
    lowered = str(filename or "").strip().lower()
    if lowered.endswith(".pdf"):
        return "vector_retrieve"
    return "section_filter"


def _builder_documents(state: GraphState) -> list[Dict[str, Any]]:
    registry = state.get("template_registry", {}) or {}
    documents = registry.get("builder_documents", [])
    if not isinstance(documents, list):
        return []
    return [item for item in documents if isinstance(item, dict)]


def _builder_document_for_filename(state: GraphState, filename: str) -> Dict[str, Any] | None:
    target = Path(str(filename or "").strip()).name.lower()
    for document in _builder_documents(state):
        candidate = Path(str(document.get("filename") or "").strip()).name.lower()
        if candidate and candidate == target:
            return document
    return None


def _instruction_load_strategy_for_state(state: GraphState, filename: str) -> str:
    lowered = str(filename or "").strip().lower()
    if lowered.endswith(".pdf"):
        return "vector_retrieve"
    if lowered.endswith(".md"):
        document = _builder_document_for_filename(state, filename)
        size_bytes = int(document.get("size_bytes") or 0) if isinstance(document, dict) else 0
        if size_bytes <= 0 or size_bytes <= 12_000:
            return "inline_full"
        return "section_filter"
    return "section_filter"


def _infer_action_type(
    state: GraphState,
    planner_output: Dict[str, Any],
    selected_workflow: Dict[str, Any] | None,
    selected_module: Dict[str, Any] | None,
    forced_turn_intent: str | None = None,
) -> str:
    if forced_turn_intent in {
        "structured_generation_brief",
        "freeform_generation_request",
        "app_scoped_question",
        "general_out_of_scope_question",
    }:
        return "answer"
    query = _combined_query_text(state, planner_output)
    if _looks_like_step_advance(query):
        return "advance_step"
    if selected_workflow or selected_module:
        return "guide"
    if str(planner_output.get("intentType") or "").lower() in {"qa", "question_answering"}:
        return "answer"
    return "clarify"


def _infer_turn_intent(
    state: GraphState,
    planner_output: Dict[str, Any],
    action_type: str,
    selected_workflow: Dict[str, Any] | None,
    selected_module: Dict[str, Any] | None,
    forced_turn_intent: str | None = None,
) -> str:
    if forced_turn_intent:
        return forced_turn_intent
    if str(state.get("turn_input_type") or "").strip() == "session_upload":
        return "analyze_upload"
    query = str(planner_output.get("normalizedQuery") or planner_output.get("contextualQuery") or state.get("user_query") or "").strip()
    if action_type == "advance_step":
        return "advance"
    if action_type == "answer":
        return "answer"
    workflow_progress = state.get("workflow_progress", {}) if isinstance(state.get("workflow_progress"), dict) else {}
    if action_type == "guide":
        if selected_module is not None and workflow_progress.get("step_order") and not _query_specifies_passage(query):
            return "answer_prior_questions"
        if selected_module is not None and not _query_specifies_passage(query):
            return "answer_prior_questions"
        if selected_module is not None:
            return "start"
        if selected_workflow is not None:
            return "start"
    return "unknown"


def _build_primary_scope(
    active_service_block: Dict[str, Any] | None,
    selected_workflow: Dict[str, Any] | None,
    selected_module: Dict[str, Any] | None,
    selected_block: Dict[str, Any] | None,
    selected_step: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    if isinstance(selected_block, dict) and selected_block:
        selected_block_type = str(selected_block.get("block_type") or "").strip()
        if selected_block_type == "mode" and not isinstance(selected_step, dict):
            activation_triggers = selected_block.get("activation_triggers", [])
            response_hint = str(selected_block.get("response_hint") or "").strip()
            if (isinstance(activation_triggers, list) and activation_triggers) or response_hint:
                return to_plain_dict(
                    InstructionScopeSelection(
                        scope_id=str(selected_block.get("block_id") or "").strip() or "scope:unknown",
                        scope_type=selected_block_type,
                        title=str(selected_block.get("title") or "").strip() or None,
                        reason="selected_instruction_block",
                    )
                )
    if isinstance(active_service_block, dict) and active_service_block:
        block_type = str(active_service_block.get("block_type") or "").strip()
        if block_type in {"primary_workflow", "supplementary_workflow", "followup_module"}:
            return to_plain_dict(
                InstructionScopeSelection(
                    scope_id=f"workflow:{_normalize_slug(str(active_service_block.get('title') or active_service_block.get('block_id') or 'workflow'))}",
                    scope_type="workflow",
                    title=str(active_service_block.get("title") or "").strip() or None,
                    reason="selected_service_block_workflow",
                )
            )
        if block_type == "support_module":
            return to_plain_dict(
                InstructionScopeSelection(
                    scope_id=str(active_service_block.get("block_id") or "").strip() or "scope:unknown",
                    scope_type="module",
                    title=str(active_service_block.get("title") or "").strip() or None,
                    reason="selected_service_block_module",
                )
            )
    if isinstance(selected_block, dict) and selected_block:
        return to_plain_dict(
            InstructionScopeSelection(
                scope_id=str(selected_block.get("block_id") or "").strip() or "scope:unknown",
                scope_type=str(selected_block.get("block_type") or "generic"),
                title=str(selected_block.get("title") or "").strip() or None,
                reason="selected_instruction_block",
            )
        )
    if isinstance(selected_module, dict) and selected_module:
        return to_plain_dict(
            InstructionScopeSelection(
                scope_id=f"module:{_normalize_slug(str(selected_module.get('title') or 'module'))}",
                scope_type="module",
                title=str(selected_module.get("title") or "").strip() or None,
                reason="selected_instruction_module",
            )
        )
    if isinstance(selected_workflow, dict) and selected_workflow:
        return to_plain_dict(
            InstructionScopeSelection(
                scope_id=f"workflow:{_normalize_slug(str(selected_workflow.get('title') or 'workflow'))}",
                scope_type="workflow",
                title=str(selected_workflow.get("title") or "").strip() or None,
                reason="selected_instruction_workflow",
            )
        )
    return None


def _normalize_slug(text: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "_", str(text or "").strip().lower()).strip("_") or "scope"


def _build_secondary_scopes(state: GraphState, primary_scope: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    candidates = state.get("instruction_scope_candidates", [])
    if not isinstance(candidates, list):
        return []
    selected: List[Dict[str, Any]] = []
    primary_id = str(primary_scope.get("scope_id") or "").strip() if isinstance(primary_scope, dict) else ""
    for item in candidates:
        if not isinstance(item, dict):
            continue
        scope_type = str(item.get("scope_type") or "").strip()
        scope_id = str(item.get("scope_id") or "").strip()
        if not scope_id or scope_id == primary_id:
            continue
        if scope_type != "response_logic":
            continue
        selected.append(
            to_plain_dict(
                InstructionScopeSelection(
                    scope_id=scope_id,
                    scope_type="response_logic",
                    title=str(item.get("title") or "").strip() or None,
                    reason="response_logic_scope_candidate",
                )
            )
        )
        if len(selected) >= 1:
            break
    return selected


def _build_active_step_scope(layered_context: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(layered_context, dict):
        return None
    activation = layered_context.get("procedure_step_activation", {})
    if not isinstance(activation, dict):
        return None
    step_scope_id = str(layered_context.get("active_step_scope_id") or activation.get("step_scope_id") or "").strip()
    if not step_scope_id:
        return None
    step_title = str(activation.get("step_title") or "").strip() or None
    step_order = _normalize_int_like(activation.get("step_order"))
    payload: Dict[str, Any] = {
        "scope_id": step_scope_id,
        "scope_type": "step",
        "title": step_title,
        "reason": "selected_procedure_step",
    }
    if step_order is not None:
        payload["step_order"] = step_order
    return payload


def _build_primary_support_module_scope(layered_context: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(layered_context, dict):
        return None
    support_module_id = str(layered_context.get("primary_support_module_id") or "").strip()
    if not support_module_id:
        return None
    payload: Dict[str, Any] = {
        "scope_id": support_module_id,
        "scope_type": "module",
        "title": str(layered_context.get("primary_support_module_title") or "").strip() or None,
        "reason": "selected_primary_support_module",
    }
    step_scope_id = str(layered_context.get("active_step_scope_id") or "").strip()
    if step_scope_id:
        payload["step_scope_id"] = step_scope_id
    return payload


def _build_resource_requests(
    state: GraphState,
    execution_context: Dict[str, Any],
    selected_block: Dict[str, Any] | None = None,
    primary_resource: str | None = None,
) -> List[Dict[str, Any]]:
    requests: List[Dict[str, Any]] = []
    instruction_plan = (
        execution_context.get("instruction_retrieval", {})
        if isinstance(execution_context.get("instruction_retrieval"), dict)
        else {}
    )
    template_plan = (
        execution_context.get("template_retrieval", {})
        if isinstance(execution_context.get("template_retrieval"), dict)
        else {}
    )
    knowledge_plan = (
        execution_context.get("knowledge_retrieval", {})
        if isinstance(execution_context.get("knowledge_retrieval"), dict)
        else {}
    )
    instruction_load_plan = execution_context.get("instruction_resource_load_plan", [])
    for item in instruction_load_plan or []:
        if not isinstance(item, dict):
            continue
        provenance = _request_provenance(
            execution_context,
            filename=str(item.get("filename") or "").strip() or None,
            resource_id=str(item.get("resource_id") or "").strip() or None,
        )
        requests.append(
            to_plain_dict(
                ResourceRequest(
                    filename=str(item.get("filename") or "").strip() or None,
                    resource_id=str(item.get("resource_id") or "").strip() or None,
                    resource_role=item.get("resource_role") or "instruction_source",
                    purpose="instruction_support",
                    query_text=str(instruction_plan.get("query_text") or "").strip() or None,
                    context_hints=[
                        str(hint).strip()
                        for hint in instruction_plan.get("context_hints", []) or []
                        if str(hint).strip()
                    ],
                    objective=str(instruction_plan.get("objective") or "").strip() or None,
                    stage_label=str(instruction_plan.get("stage_label") or "").strip() or None,
                    request_reason="instruction_load_plan",
                    load_strategy_hint=item.get("load_strategy"),
                    source_layer=provenance.get("source_layer"),
                    step_scope_id=provenance.get("step_scope_id"),
                    support_module_id=provenance.get("support_module_id"),
                    required=True,
                )
            )
        )
    template_load_plan = execution_context.get("template_resource_load_plan", [])
    for item in template_load_plan or []:
        if not isinstance(item, dict):
            continue
        provenance = _request_provenance(
            execution_context,
            filename=str(item.get("filename") or "").strip() or None,
            resource_id=str(item.get("resource_id") or "").strip() or None,
        )
        requests.append(
            to_plain_dict(
                ResourceRequest(
                    filename=str(item.get("filename") or "").strip() or None,
                    resource_id=str(item.get("resource_id") or "").strip() or None,
                    resource_role=item.get("resource_role") or "output_template",
                    purpose="template_support",
                    query_text=str(template_plan.get("query_text") or "").strip() or None,
                    context_hints=[
                        str(hint).strip()
                        for hint in template_plan.get("context_hints", []) or []
                        if str(hint).strip()
                    ],
                    objective=str(template_plan.get("objective") or "").strip() or None,
                    stage_label=str(template_plan.get("stage_label") or "").strip() or None,
                    request_reason="template_load_plan",
                    load_strategy_hint=item.get("load_strategy"),
                    source_layer=provenance.get("source_layer"),
                    step_scope_id=provenance.get("step_scope_id"),
                    support_module_id=provenance.get("support_module_id"),
                    required=True,
                )
            )
        )
    existing_request_filenames = {
        str(item.get("filename") or "").strip()
        for item in requests
        if isinstance(item, dict) and str(item.get("filename") or "").strip()
    }
    for filename in execution_context.get("response_style", {}).get("output_artifact_targets", []) or []:
        artifact_filename = str(filename or "").strip()
        if not artifact_filename or artifact_filename in existing_request_filenames:
            continue
        runtime_resource = _runtime_resource_by_filename(state, artifact_filename)
        provenance = _request_provenance(
            execution_context,
            filename=artifact_filename,
            resource_id=str(runtime_resource.get("resource_id") or "").strip() or None if isinstance(runtime_resource, dict) else None,
        )
        requests.append(
            to_plain_dict(
                ResourceRequest(
                    filename=artifact_filename,
                    resource_id=str(runtime_resource.get("resource_id") or "").strip() or None if isinstance(runtime_resource, dict) else None,
                    resource_role="output_artifact",
                    purpose="output_target",
                    query_text=str(template_plan.get("query_text") or instruction_plan.get("query_text") or "").strip() or None,
                    context_hints=[
                        str(hint).strip()
                        for hint in (
                            template_plan.get("context_hints")
                            or instruction_plan.get("context_hints")
                            or []
                        )
                        if str(hint).strip()
                    ],
                    objective=str(template_plan.get("objective") or instruction_plan.get("objective") or "").strip() or None,
                    stage_label=str(template_plan.get("stage_label") or instruction_plan.get("stage_label") or "").strip() or None,
                    request_reason="output_artifact_target",
                    source_layer=provenance.get("source_layer"),
                    step_scope_id=provenance.get("step_scope_id"),
                    support_module_id=provenance.get("support_module_id"),
                    required=True,
                )
            )
        )
        existing_request_filenames.add(artifact_filename)
    for filename in knowledge_plan.get("filename_filters", []) or []:
        provenance = _request_provenance(
            execution_context,
            filename=str(filename or "").strip() or None,
        )
        requests.append(
            to_plain_dict(
                ResourceRequest(
                    filename=str(filename or "").strip() or None,
                    resource_role="knowledge_source",
                    purpose="knowledge_grounding",
                    query_text=str(knowledge_plan.get("query_text") or "").strip() or None,
                    context_hints=[
                        str(hint).strip()
                        for hint in knowledge_plan.get("context_hints", []) or []
                        if str(hint).strip()
                    ],
                    objective=str(knowledge_plan.get("objective") or "").strip() or None,
                    stage_label=str(knowledge_plan.get("stage_label") or "").strip() or None,
                    request_reason="knowledge_filename_filter",
                    load_strategy_hint="vector_retrieve",
                    source_layer=provenance.get("source_layer"),
                    step_scope_id=provenance.get("step_scope_id"),
                    support_module_id=provenance.get("support_module_id"),
                    required=True,
                )
            )
        )
    if not requests:
        block = selected_block if isinstance(selected_block, dict) else state.get("selected_instruction_block", {})
        if isinstance(block, dict):
            for filename in block.get("referenced_resources", []) or []:
                resource_name = str(filename or "").strip()
                if not resource_name:
                    continue
                provenance = _request_provenance(
                    execution_context,
                    filename=resource_name,
                )
                requests.append(
                    to_plain_dict(
                        ResourceRequest(
                            filename=resource_name,
                            resource_role="instruction_source",
                            purpose="instruction_support",
                            query_text=str(instruction_plan.get("query_text") or "").strip() or None,
                            context_hints=[
                                str(hint).strip()
                                for hint in instruction_plan.get("context_hints", []) or []
                                if str(hint).strip()
                            ],
                            objective=str(block.get("objective") or instruction_plan.get("objective") or "").strip() or None,
                            stage_label=str(instruction_plan.get("stage_label") or "").strip() or None,
                            request_reason="selected_block_referenced_resource",
                            source_layer=provenance.get("source_layer"),
                            step_scope_id=provenance.get("step_scope_id"),
                            support_module_id=provenance.get("support_module_id"),
                            required=True,
                        )
                    )
                )
        if not requests:
            resolved_primary_resource = str(primary_resource or state.get("instruction_resource") or "").strip()
            if resolved_primary_resource:
                provenance = _request_provenance(
                    execution_context,
                    filename=resolved_primary_resource,
                )
                requests.append(
                    to_plain_dict(
                        ResourceRequest(
                            filename=resolved_primary_resource,
                            resource_role="instruction_source",
                            purpose="instruction_support",
                            query_text=str(instruction_plan.get("query_text") or "").strip() or None,
                            context_hints=[
                                str(hint).strip()
                                for hint in instruction_plan.get("context_hints", []) or []
                                if str(hint).strip()
                            ],
                            objective=str(instruction_plan.get("objective") or "").strip() or None,
                            stage_label=str(instruction_plan.get("stage_label") or "").strip() or None,
                            request_reason="primary_instruction_resource",
                            source_layer=provenance.get("source_layer"),
                            step_scope_id=provenance.get("step_scope_id"),
                            support_module_id=provenance.get("support_module_id"),
                            required=True,
                        )
                    )
                )
    for upload_id in execution_context.get("selected_session_upload_ids", []) or []:
        requests.append(
            to_plain_dict(
                ResourceRequest(
                    resource_id=upload_id,
                    resource_role="knowledge_source",
                    purpose="session_upload",
                    query_text=str(knowledge_plan.get("query_text") or "").strip() or None,
                    context_hints=[
                        str(hint).strip()
                        for hint in knowledge_plan.get("context_hints", []) or []
                        if str(hint).strip()
                    ],
                    objective=str(knowledge_plan.get("objective") or "").strip() or None,
                    stage_label=str(knowledge_plan.get("stage_label") or "").strip() or None,
                    request_reason="selected_session_upload",
                    required=True,
                )
            )
        )
    for request in execution_context.get("binding_resource_requests", []) or []:
        if isinstance(request, dict) and _binding_can_supply_resource_request(request):
            requests.append(dict(request))
    return requests


def _sync_resource_load_plans_from_turn_requests(state: GraphState) -> None:
    turn_execution_plan = state.get("turn_execution_plan", {}) or {}
    if not isinstance(turn_execution_plan, dict):
        return
    requests = turn_execution_plan.get("resource_requests", [])
    if not isinstance(requests, list):
        return

    instruction_plan: list[dict] = []
    template_plan: list[dict] = []
    seen_instruction_keys: set[tuple[str, str, str]] = set()
    seen_template_keys: set[tuple[str, str, str]] = set()

    for item in requests:
        if not isinstance(item, dict):
            continue
        resource_role = str(item.get("resource_role") or "").strip()
        if resource_role not in {"instruction_source", "output_template"}:
            continue
        filename = str(item.get("filename") or "").strip()
        resource_id = str(item.get("resource_id") or "").strip()
        if not filename and not resource_id:
            continue
        key = (resource_role, filename, resource_id)
        if resource_role == "instruction_source" and key in seen_instruction_keys:
            continue
        if resource_role == "output_template" and key in seen_template_keys:
            continue

        runtime_resource = None
        if filename:
            runtime_resource = _runtime_resource_by_filename(state, filename)
        if not isinstance(runtime_resource, dict) and resource_id:
            runtime_resource = _runtime_resource_map(state).get(resource_id)

        normalized = {
            "resource_id": resource_id or (str(runtime_resource.get("resource_id") or "").strip() if isinstance(runtime_resource, dict) else None),
            "filename": filename or (str(runtime_resource.get("filename") or "").strip() if isinstance(runtime_resource, dict) else None),
            "resource_role": resource_role,
            "load_strategy": str(item.get("load_strategy_hint") or "").strip()
            or _instruction_load_strategy_for_state(
                state,
                filename or (str(runtime_resource.get("filename") or "").strip() if isinstance(runtime_resource, dict) else ""),
            ),
            "reason": str(item.get("request_reason") or "").strip() or "resource_request",
            "size_hint": None,
            "document_id": (
                runtime_resource.get("document_id")
                if isinstance(runtime_resource, dict)
                else None
            ),
        }
        if resource_role == "instruction_source":
            seen_instruction_keys.add(key)
            instruction_plan.append(normalized)
        else:
            seen_template_keys.add(key)
            template_plan.append(normalized)

    state["instruction_resource_load_plan"] = instruction_plan
    state["template_resource_load_plan"] = template_plan
    if isinstance(state.get("session_execution_state"), dict):
        state["session_execution_state"]["active_instruction_resources"] = [
            str(item.get("filename") or "").strip()
            for item in instruction_plan
            if str(item.get("filename") or "").strip()
        ]
        state["session_execution_state"]["active_template_resources"] = [
            str(item.get("filename") or "").strip()
            for item in template_plan
            if str(item.get("filename") or "").strip()
        ]


def _build_actions(
    state: GraphState,
    execution_context: Dict[str, Any],
    selected_block: Dict[str, Any] | None = None,
    primary_resource: str | None = None,
) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    requests = _build_resource_requests(
        state,
        execution_context,
        selected_block,
        primary_resource,
    )
    knowledge_plan = (
        execution_context.get("knowledge_retrieval", {})
        if isinstance(execution_context.get("knowledge_retrieval"), dict)
        else {}
    )
    response_style = (
        execution_context.get("response_style", {})
        if isinstance(execution_context.get("response_style"), dict)
        else {}
    )
    request_count = len(execution_context.get("instruction_resource_load_plan", []) or []) + len(execution_context.get("template_resource_load_plan", []) or [])
    if request_count == 0:
        block = selected_block if isinstance(selected_block, dict) else state.get("selected_instruction_block", {})
        if isinstance(block, dict) and (block.get("referenced_resources") or primary_resource or state.get("instruction_resource")):
            request_count = 1
    if request_count or (execution_context.get("knowledge_retrieval", {}) or {}).get("enabled") or (execution_context.get("selected_session_upload_ids", []) or []):
        actions.append(
            to_plain_dict(
                TurnAction(
                    action_id="action:prepare_resources",
                    action_type="load_resource",
                    target="prepared_inputs",
                    output_key="prepared_inputs",
                    visibility="internal_only",
                    params={
                        "request_count": len(requests),
                        "resource_roles": [
                            str(item.get("resource_role") or "").strip()
                            for item in requests
                            if str(item.get("resource_role") or "").strip()
                        ],
                    },
                )
            )
        )
    if isinstance(knowledge_plan, dict) and knowledge_plan.get("enabled"):
        actions.append(
            to_plain_dict(
                TurnAction(
                    action_id="action:retrieve_knowledge",
                    action_type="retrieve_knowledge",
                    target="rag_subsystem",
                    output_key="knowledge_evidence",
                    visibility="internal_only",
                    params={
                        "query_text": knowledge_plan.get("query_text"),
                        "query_variants": knowledge_plan.get("query_variants", []),
                        "fallback_queries": knowledge_plan.get("fallback_queries", []),
                        "context_hints": knowledge_plan.get("context_hints", []),
                        "objective": knowledge_plan.get("objective"),
                        "stage_label": knowledge_plan.get("stage_label"),
                        "retry_on_weak_results": bool(knowledge_plan.get("retry_on_weak_results")),
                    },
                )
            )
        )
    output_targets = [
        str(item).strip()
        for item in (response_style.get("output_artifact_targets", []) if isinstance(response_style, dict) else [])
        if str(item).strip()
    ]
    if output_targets:
        actions.append(
            to_plain_dict(
                TurnAction(
                    action_id="action:assemble_output",
                    action_type="assemble_output",
                    target="output_artifact_assembler",
                    output_key="assembled_output_artifacts",
                    visibility="internal_only",
                    params={
                        "target_outputs": output_targets,
                        "source_output_key": "final_answer",
                    },
                )
            )
        )
        actions.append(
            to_plain_dict(
                TurnAction(
                    action_id="action:validate_output",
                    action_type="validate_output",
                    target="output_artifact_validator",
                    output_key="output_validation",
                    visibility="internal_only",
                    params={
                        "target_outputs": output_targets,
                        "validation_scope": "output_artifacts",
                        "source_output_key": "final_answer",
                    },
                )
            )
        )
    actions.append(
        to_plain_dict(
            TurnAction(
                action_id="action:respond_to_user",
                action_type="respond_to_user",
                target="assistant_response",
                output_key="final_answer",
                visibility="user_visible",
                params={
                    "response_style": response_style,
                    "action_type": execution_context.get("action_type"),
                },
            )
        )
    )
    actions.append(
        to_plain_dict(
            TurnAction(
                action_id="action:update_session_state",
                action_type="update_session_state",
                target="session_execution_state",
                output_key="session_execution_state",
                visibility="internal_only",
                params={
                    "state_update_keys": sorted(
                        [
                            str(key).strip()
                            for key in (execution_context.get("state_updates", {}) or {}).keys()
                            if str(key).strip()
                        ]
                    ),
                },
            )
        )
    )
    return actions


def _build_presentation_policy(
    state: GraphState,
    execution_context: Dict[str, Any],
    turn_intent: str,
) -> Dict[str, Any]:
    hints = state.get("presentation_policy", {})
    if not isinstance(hints, dict):
        hints = {}
    mode = "full_output"
    if turn_intent in {"start", "answer_prior_questions"}:
        mode = "question_only"
    elif turn_intent == "finalize":
        mode = "final_output"
    elif turn_intent == "structured_generation_brief":
        mode = "final_output"
    return to_plain_dict(
        PresentationPolicy(
            mode=mode,
            show_intermediate_outputs=bool(execution_context.get("response_style", {}).get("show_intermediate_outputs", False)),
            summarize_hidden_outputs=bool(hints.get("may_show_step_summaries")),
            hide_reasoning_artifacts=True,
            include_citations_when_available=True,
        )
    )


def _build_turn_execution_plan(
    state: GraphState,
    planner_output: Dict[str, Any],
    selected_workflow: Dict[str, Any] | None,
    selected_module: Dict[str, Any] | None,
    selected_block: Dict[str, Any] | None,
    selected_step: Dict[str, Any] | None,
    execution_context: Dict[str, Any],
    primary_resource: str,
) -> Dict[str, Any]:
    action_type = str(execution_context.get("action_type") or "").strip()
    turn_intent = _infer_turn_intent(
        state,
        planner_output,
        action_type,
        selected_workflow,
        selected_module,
        str(execution_context.get("forced_turn_intent") or "").strip() or None,
    )
    primary_scope = (
        execution_context.get("primary_scope")
        if isinstance(execution_context.get("primary_scope"), dict)
        else None
    )
    active_service_block = _active_service_block(state, selected_workflow, selected_block, selected_step)
    if not primary_scope:
        primary_scope = _build_primary_scope(active_service_block, selected_workflow, selected_module, selected_block, selected_step)
    layered_context = execution_context if isinstance(execution_context, dict) else {}
    active_step_scope = _build_active_step_scope(layered_context)
    if active_step_scope is None and isinstance(selected_module, dict):
        fallback_step_scope_id = str(selected_module.get("step_scope_id") or "").strip()
        if fallback_step_scope_id:
            fallback_scope: Dict[str, Any] = {
                "scope_id": fallback_step_scope_id,
                "scope_type": "step",
                "title": str(selected_module.get("title") or "").strip() or None,
                "reason": "selected_procedure_step_fallback",
            }
            fallback_step_order = _normalize_int_like(selected_module.get("order"))
            if fallback_step_order is not None:
                fallback_scope["step_order"] = fallback_step_order
            active_step_scope = fallback_scope
    active_execution_mode = str(execution_context.get("active_execution_mode") or "").strip() or None
    active_bundled_step_ids = [
        str(item).strip()
        for item in execution_context.get("active_bundled_step_ids", []) or []
        if str(item).strip()
    ]
    bundled_entry_step_id = str(execution_context.get("bundled_entry_step_id") or "").strip() or None
    if isinstance(selected_module, dict):
        fallback_scope_id = str(selected_module.get("step_scope_id") or "").strip()
        if fallback_scope_id:
            fallback_definition = _procedure_step_definition_for_scope(state, fallback_scope_id) or {}
            if str(fallback_definition.get("execution_mode") or "").strip() == "bundled":
                fallback_bundled_ids_seed = [
                    str(item).strip()
                    for item in fallback_definition.get("bundled_step_ids", []) or []
                    if str(item).strip()
                ]
                if not fallback_bundled_ids_seed:
                    procedure_id = str(fallback_definition.get("procedure_id") or "").strip()
                    runtime_model = state.get("instruction_runtime_model", {}) or {}
                    procedure_steps = [
                        item
                        for item in runtime_model.get("procedure_steps", []) or []
                        if isinstance(item, dict)
                    ]
                    fallback_definition = next(
                        (
                            item
                            for item in procedure_steps
                            if str(item.get("procedure_id") or "").strip() == procedure_id
                            and fallback_scope_id
                            in [
                                str(member).strip()
                                for member in item.get("bundled_step_ids", []) or []
                                if str(member).strip()
                            ]
                        ),
                        fallback_definition,
                    )
            fallback_mode = str(fallback_definition.get("execution_mode") or "").strip()
            fallback_bundled_ids = [
                str(item).strip()
                for item in fallback_definition.get("bundled_step_ids", []) or []
                if str(item).strip()
            ]
            if active_execution_mode is None and fallback_mode == "bundled":
                active_execution_mode = "bundled"
            if not active_bundled_step_ids and fallback_bundled_ids:
                active_bundled_step_ids = fallback_bundled_ids
            if bundled_entry_step_id is None and active_execution_mode == "bundled":
                bundled_entry_step_id = (
                    active_bundled_step_ids[0] if active_bundled_step_ids else fallback_scope_id
                )
    primary_support_module_scope = _build_primary_support_module_scope(layered_context)
    secondary_scopes = _build_secondary_scopes(state, primary_scope)
    llm_reason_summary = None
    steps = planner_output.get("steps", [])
    if isinstance(steps, list) and steps:
        llm_reason_summary = " | ".join(
            str(step.get("title") or "").strip()
            for step in steps
            if isinstance(step, dict) and str(step.get("title") or "").strip()
        ) or None
    return to_plain_dict(
        TurnExecutionPlan(
            turn_intent=turn_intent,
            active_service_block_type=str(execution_context.get("active_service_block_type") or "").strip() or None,
            active_service_block_id=str(execution_context.get("active_service_block_id") or "").strip() or None,
            active_service_block_title=str(execution_context.get("active_service_block_title") or "").strip() or None,
            active_execution_mode=active_execution_mode,
            active_bundled_step_ids=active_bundled_step_ids,
            bundled_execution_completed=bool(execution_context.get("bundled_execution_completed")),
            bundled_entry_step_id=bundled_entry_step_id,
            primary_scope=InstructionScopeSelection(**primary_scope) if isinstance(primary_scope, dict) else None,
            active_step_scope=InstructionScopeSelection(**active_step_scope) if isinstance(active_step_scope, dict) else None,
            primary_support_module_scope=InstructionScopeSelection(**primary_support_module_scope)
            if isinstance(primary_support_module_scope, dict)
            else None,
            secondary_scopes=[InstructionScopeSelection(**item) for item in secondary_scopes if isinstance(item, dict)],
            resource_requests=[ResourceRequest(**item) for item in _build_resource_requests(state, execution_context, selected_block, primary_resource)],
            actions=[TurnAction(**item) for item in _build_actions(state, execution_context, selected_block, primary_resource)],
            presentation_policy=PresentationPolicy(**_build_presentation_policy(state, execution_context, turn_intent)),
            state_updates=dict(execution_context.get("state_updates", {}) or {}),
            llm_reason_summary=llm_reason_summary,
        )
    )


def _session_upload_ids_from_execution_plan(plan: Dict[str, Any]) -> List[str]:
    requests = plan.get("resource_requests", []) if isinstance(plan, dict) else []
    if not isinstance(requests, list):
        return []
    selected: List[str] = []
    for item in requests:
        if not isinstance(item, dict):
            continue
        if str(item.get("purpose") or "").strip() != "session_upload":
            continue
        resource_id = str(item.get("resource_id") or "").strip()
        if resource_id:
            selected.append(resource_id)
    return list(dict.fromkeys(selected))


def _build_execution_context(
    state: GraphState,
    planner_output: Dict[str, Any],
    selected_workflow: Dict[str, Any] | None,
    selected_module: Dict[str, Any] | None,
    selected_block: Dict[str, Any] | None,
    selected_step: Dict[str, Any] | None,
    primary_resource: str,
    forced_turn_intent: str | None = None,
    pre_routing: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    query_text = str(planner_output.get("contextualQuery") or planner_output.get("normalizedQuery") or state.get("user_query") or "").strip()
    retrieval_plan = planner_output.get("retrievalPlan", {}) if isinstance(planner_output, dict) else {}
    plan_filters = retrieval_plan.get("filters", {}) if isinstance(retrieval_plan, dict) else {}
    if not isinstance(plan_filters, dict):
        plan_filters = {}

    runtime_model = state.get("instruction_runtime_model", {}) or {}
    active_service_block = _active_service_block(state, selected_workflow, selected_block, selected_step)
    layered_context = _layered_scope_context(state, selected_workflow, selected_module)
    support_resources = (
        list(layered_context.get("support_resources", []))
        if layered_context
        else _select_support_resources(state, query_text.lower())
    )
    primary_resource_id = Path(primary_resource).stem.lower() if primary_resource else ""
    primary_runtime_resource = _runtime_resource_map(state).get(primary_resource_id)

    instruction_resource_ids: list[str] = []
    instruction_filenames: list[str] = []
    instruction_resource_load_plan: list[dict] = []
    template_resource_load_plan: list[dict] = []
    template_resource_ids: list[str] = []
    template_filenames: list[str] = []
    knowledge_filenames: list[str] = []
    output_artifact_targets: list[str] = []
    resource_request_provenance: dict[str, Dict[str, Any]] = {}
    active_service_block_type = str(active_service_block.get("block_type") or "").strip() if isinstance(active_service_block, dict) else ""
    active_service_block_id = str(active_service_block.get("block_id") or "").strip() if isinstance(active_service_block, dict) else ""
    active_service_block_title = str(active_service_block.get("title") or "").strip() if isinstance(active_service_block, dict) else ""
    followup_block_active = bool(
        active_service_block_type == "followup_module"
        and active_service_block_id
        and _followup_module_should_activate_for_turn(state, active_service_block_id)
    )

    def add_runtime_resource_to_plans(
        resource: Dict[str, Any] | None,
        *,
        reason: str,
        source_layer: str | None,
        step_scope_id: str | None = None,
        support_module_id: str | None = None,
    ) -> None:
        if not isinstance(resource, dict):
            return
        domain = str(resource.get("domain") or "")
        resource_id = str(resource.get("resource_id") or "").strip()
        filename = str(resource.get("filename") or "").strip()
        if not filename and domain != "output_artifact":
            return
        _record_request_provenance(
            resource_request_provenance,
            filename=filename or None,
            resource_id=resource_id or None,
            source_layer=source_layer,
            step_scope_id=step_scope_id,
            support_module_id=support_module_id,
        )
        if domain == "instruction_source":
            _append_unique(instruction_resource_ids, resource_id)
            _append_unique(instruction_filenames, filename)
            instruction_resource_load_plan.append(
                {
                    "resource_id": resource_id or None,
                    "filename": filename,
                    "resource_role": domain,
                    "load_strategy": _instruction_load_strategy_for_state(state, filename),
                    "reason": reason,
                    "size_hint": None,
                    "document_id": resource.get("document_id"),
                }
            )
        elif domain == "output_template":
            _append_unique(template_resource_ids, resource_id)
            _append_unique(template_filenames, filename)
            template_resource_load_plan.append(
                {
                    "resource_id": resource_id or None,
                    "filename": filename,
                    "resource_role": domain,
                    "load_strategy": _instruction_load_strategy_for_state(state, filename),
                    "reason": reason,
                    "size_hint": None,
                    "document_id": resource.get("document_id"),
                }
            )
        elif domain == "knowledge_source":
            _append_unique(knowledge_filenames, filename)
        elif domain == "output_artifact":
            _append_unique(output_artifact_targets, filename)

    if followup_block_active:
        for request in _followup_module_resource_requests(
            state,
            active_service_block_id,
            active_service_block_title or None,
        ):
            add_runtime_resource_to_plans(
                _runtime_resource_by_filename(state, str(request.get("filename") or "").strip()),
                reason=str(request.get("request_reason") or "followup_module_explicit_resource"),
                source_layer="support_module",
                support_module_id=active_service_block_id,
            )
    elif primary_runtime_resource:
        add_runtime_resource_to_plans(
            primary_runtime_resource,
            reason="primary_selected_resource",
            source_layer="procedure_step" if layered_context else "direct_query",
            step_scope_id=layered_context.get("active_step_scope_id"),
        )

    if layered_context and not followup_block_active:
        primary_filename = str(primary_runtime_resource.get("filename") or "").strip() if primary_runtime_resource else ""
        for filename in layered_context.get("direct_resource_files", []) or []:
            cleaned_filename = str(filename or "").strip()
            if not cleaned_filename or cleaned_filename == primary_filename:
                continue
            add_runtime_resource_to_plans(
                _runtime_resource_by_filename(state, cleaned_filename),
                reason="primary_selected_resource",
                source_layer="procedure_step",
                step_scope_id=layered_context.get("active_step_scope_id"),
            )

    primary_support_module_id = str(layered_context.get("primary_support_module_id") or "").strip() if layered_context else ""
    planner_mode = str(state.get("planner_mode") or "").strip().lower()
    step_scoped_module_owned_resources = bool(
        planner_mode == "hybrid_active"
        and layered_context
        and str(layered_context.get("active_step_scope_id") or "").strip()
        and [
            str(item or "").strip()
            for item in layered_context.get("direct_resource_files", []) or []
            if str(item or "").strip()
        ]
        and primary_support_module_id
    )
    if not followup_block_active and not step_scoped_module_owned_resources:
        for resource in support_resources:
            add_runtime_resource_to_plans(
                resource,
                reason="support_selected_resource",
                source_layer="support_module" if layered_context else "direct_query",
                step_scope_id=layered_context.get("active_step_scope_id"),
                support_module_id=layered_context.get("primary_support_module_id"),
            )

    if not output_artifact_targets:
        for resource in _runtime_resources_by_domain(state, "output_artifact"):
            _append_unique(output_artifact_targets, str(resource.get("filename") or ""))

    selected_session_uploads = _selected_session_uploads(state, planner_output)
    selected_session_upload_ids = [str(item.get("id") or "").strip() for item in selected_session_uploads if str(item.get("id") or "").strip()]

    action_type = _infer_action_type(state, planner_output, selected_workflow, selected_module, forced_turn_intent)
    instruction_query_plan = _build_instruction_query_plan(
        state,
        planner_output,
        selected_workflow,
        selected_module,
        action_type,
    )
    knowledge_query_plan = _build_knowledge_query_plan(
        state,
        planner_output,
        str(retrieval_plan.get("query_text") or query_text or "").strip(),
    )
    instruction_retrieval = RetrievalDomainPlan(
        enabled=bool([item for item in instruction_resource_load_plan if item.get("load_strategy") == "vector_retrieve"]),
        resource_ids=instruction_resource_ids,
        filename_filters=instruction_filenames,
        query_text=instruction_query_plan["primary_query"] or None,
        context_hints=instruction_query_plan["context_hints"],
        objective=instruction_query_plan["objective"],
        stage_label=instruction_query_plan["stage_label"],
        query_variants=instruction_query_plan["query_variants"],
        fallback_queries=instruction_query_plan["fallback_queries"],
        retry_on_weak_results=bool(
            instruction_query_plan["query_variants"]
            or instruction_query_plan["context_hints"]
            or instruction_query_plan["fallback_queries"]
        ),
    )
    template_retrieval = RetrievalDomainPlan(
        enabled=bool([item for item in template_resource_load_plan if item.get("load_strategy") == "vector_retrieve"]),
        resource_ids=template_resource_ids,
        filename_filters=template_filenames,
        query_text=instruction_query_plan["primary_query"] or None,
        context_hints=instruction_query_plan["context_hints"],
        objective=instruction_query_plan["objective"],
        stage_label=instruction_query_plan["stage_label"],
        query_variants=instruction_query_plan["query_variants"],
        fallback_queries=instruction_query_plan["fallback_queries"],
        retry_on_weak_results=bool(
            instruction_query_plan["query_variants"]
            or instruction_query_plan["context_hints"]
            or instruction_query_plan["fallback_queries"]
        ),
    )
    knowledge_retrieval = RetrievalDomainPlan(
        enabled=bool(retrieval_plan.get("query_text")) or bool(knowledge_filenames),
        resource_ids=[str(resource.get("resource_id") or "").strip() for resource in support_resources if str(resource.get("domain")) == "knowledge_source"],
        filename_filters=knowledge_filenames,
        query_text=knowledge_query_plan["primary_query"] or None,
        query_variants=knowledge_query_plan["query_variants"],
        fallback_queries=knowledge_query_plan["fallback_queries"],
        retry_on_weak_results=knowledge_query_plan["retry_on_weak_results"],
    )
    binding_activation = _derive_binding_activation(
        state,
        planner_output,
        selected_workflow,
        selected_module,
        forced_turn_intent,
    )

    session_execution_state = state.get("session_execution_state", {}) or {}
    next_clarification_gate_status = (
        dict(session_execution_state.get("clarification_gate_status", {}) or {})
        if isinstance(session_execution_state, dict)
        else {}
    )
    next_clarification_gate_status["filled_slots_map"] = _clarification_slot_signal_map(state, query_text)
    minimum_filled_slots = state.get("_clarification_gate_minimum_filled_slots")
    if minimum_filled_slots is None and isinstance(next_clarification_gate_status, dict):
        minimum_filled_slots = next_clarification_gate_status.get("minimum_filled_slots")
    try:
        minimum_filled_slots = int(minimum_filled_slots) if minimum_filled_slots is not None else None
    except (TypeError, ValueError):
        minimum_filled_slots = None
    if minimum_filled_slots is not None and minimum_filled_slots > 0:
        next_clarification_gate_status["minimum_filled_slots"] = minimum_filled_slots
    elif "minimum_filled_slots" in next_clarification_gate_status:
        next_clarification_gate_status.pop("minimum_filled_slots", None)
    active_service_block = _active_service_block(state, selected_workflow, selected_block, selected_step)
    primary_scope = layered_context.get("primary_scope")
    if not primary_scope:
        primary_scope = _build_primary_scope(active_service_block, selected_workflow, selected_module, selected_block, selected_step)
    primary_scope_id = (
        str(primary_scope.get("scope_id") or "").strip() or None
        if isinstance(primary_scope, dict)
        else None
    )
    primary_scope_type = (
        str(primary_scope.get("scope_type") or "").strip() or None
        if isinstance(primary_scope, dict)
        else None
    )
    primary_scope_title = (
        str(primary_scope.get("title") or "").strip() or None
        if isinstance(primary_scope, dict)
        else None
    )
    active_service_block_type = _normalized_service_block_type(active_service_block)
    active_service_block_id = (
        str(active_service_block.get("block_id") or "").strip() or None
        if isinstance(active_service_block, dict)
        else None
    )
    active_service_block_title = (
        str(active_service_block.get("title") or "").strip() or None
        if isinstance(active_service_block, dict)
        else None
    )
    workflow_id = str(selected_workflow.get("id") or "").strip() if isinstance(selected_workflow, dict) else ""
    workflow_title = (
        str(selected_workflow.get("workflow_name") or selected_workflow.get("title") or "").strip()
        if isinstance(selected_workflow, dict)
        else ""
    )
    step_order = selected_module.get("order") if isinstance(selected_module, dict) else None
    step_title = selected_module.get("title") if isinstance(selected_module, dict) else None
    execution_status = "guiding" if action_type in {"guide", "advance_step"} else "answering"
    session_active_execution_mode = str(layered_context.get("active_execution_mode") or "").strip() or None
    session_active_bundled_step_ids = [
        str(item).strip()
        for item in layered_context.get("active_bundled_step_ids", []) or []
        if str(item).strip()
    ]
    session_bundled_entry_step_id = str(layered_context.get("bundled_entry_step_id") or "").strip() or None
    session_active_step_scope_id = str(layered_context.get("active_step_scope_id") or "").strip() or None
    if isinstance(selected_module, dict):
        fallback_scope_id = str(selected_module.get("step_scope_id") or "").strip()
        if fallback_scope_id:
            session_active_step_scope_id = session_active_step_scope_id or fallback_scope_id
            fallback_definition = _procedure_step_definition_for_scope(state, fallback_scope_id) or {}
            if str(fallback_definition.get("execution_mode") or "").strip() == "bundled":
                fallback_bundled_ids_seed = [
                    str(item).strip()
                    for item in fallback_definition.get("bundled_step_ids", []) or []
                    if str(item).strip()
                ]
                if not fallback_bundled_ids_seed:
                    procedure_id = str(fallback_definition.get("procedure_id") or "").strip()
                    runtime_model = state.get("instruction_runtime_model", {}) or {}
                    procedure_steps = [
                        item
                        for item in runtime_model.get("procedure_steps", []) or []
                        if isinstance(item, dict)
                    ]
                    fallback_definition = next(
                        (
                            item
                            for item in procedure_steps
                            if str(item.get("procedure_id") or "").strip() == procedure_id
                            and fallback_scope_id
                            in [
                                str(member).strip()
                                for member in item.get("bundled_step_ids", []) or []
                                if str(member).strip()
                            ]
                        ),
                        fallback_definition,
                    )
            fallback_mode = str(fallback_definition.get("execution_mode") or "").strip()
            fallback_bundled_ids = [
                str(item).strip()
                for item in fallback_definition.get("bundled_step_ids", []) or []
                if str(item).strip()
            ]
            if session_active_execution_mode is None and fallback_mode == "bundled":
                session_active_execution_mode = "bundled"
            if not session_active_bundled_step_ids and fallback_bundled_ids:
                session_active_bundled_step_ids = fallback_bundled_ids
            if session_bundled_entry_step_id is None and session_active_execution_mode == "bundled":
                session_bundled_entry_step_id = (
                    session_active_bundled_step_ids[0] if session_active_bundled_step_ids else fallback_scope_id
                )
    bundled_execution_completed = bool(layered_context.get("bundled_execution_completed"))
    if not bundled_execution_completed and session_active_execution_mode == "bundled":
        bundled_execution_completed = action_type in {"guide", "answer", "advance_step"}

    next_execution_state = to_plain_dict(
        SessionExecutionState(
            active_mode=workflow_id or session_execution_state.get("active_mode"),
            active_workflow=workflow_title or session_execution_state.get("active_workflow"),
            active_step_order=step_order if step_order is not None else session_execution_state.get("active_step_order"),
            active_step_title=step_title or session_execution_state.get("active_step_title"),
            active_execution_mode=session_active_execution_mode,
            active_bundled_step_ids=session_active_bundled_step_ids,
            bundled_execution_completed=bundled_execution_completed,
            bundled_entry_step_id=session_bundled_entry_step_id,
            active_service_block_type=active_service_block_type,
            active_service_block_id=active_service_block_id,
            active_service_block_title=active_service_block_title,
            primary_scope_id=primary_scope_id,
            primary_scope_type=primary_scope_type,
            primary_scope_title=primary_scope_title,
            active_step_scope_id=session_active_step_scope_id,
            primary_support_module_id=layered_context.get("primary_support_module_id"),
            primary_support_module_title=layered_context.get("primary_support_module_title"),
            clarification_gate_status=next_clarification_gate_status,
            procedure_step_activation=layered_context.get("procedure_step_activation"),
            primary_support_module_activation=layered_context.get("primary_support_module_activation"),
            execution_status=execution_status,
            last_input_type=str(state.get("turn_input_type") or "").strip() or "text_query",
            active_instruction_resources=instruction_filenames,
            active_support_resources=knowledge_filenames,
            active_template_resources=template_filenames,
            active_session_upload_ids=selected_session_upload_ids,
            output_artifact_targets=output_artifact_targets,
            last_turn_action=action_type,
            active_binding_ids=binding_activation.get("active_binding_ids", []),
            active_dependency_group_ids=binding_activation.get("active_dependency_group_ids", []),
            active_artifact_roles=binding_activation.get("active_artifact_roles", []),
            artifact_gate_status=binding_activation.get("artifact_gate_status", {}),
            active_scope_ids=[
                value
                for value in [
                    str(primary_scope.get("scope_id") or "").strip() if isinstance(primary_scope, dict) else "",
                    str(layered_context.get("active_step_scope_id") or "").strip(),
                    str(layered_context.get("primary_support_module_id") or "").strip(),
                ]
                if value
            ],
            workflow_progress=state.get("workflow_progress", {}) or {},
        )
    )

    state_updates = {
        "instruction_resource_filters": _merge_filename_filters({}, instruction_filenames),
        "template_resource_filters": _merge_filename_filters({}, template_filenames),
        "knowledge_retrieval_filters": _merge_filename_filters(dict(plan_filters), knowledge_filenames),
        "session_execution_state": next_execution_state,
        "selected_instruction_block": dict(selected_block) if isinstance(selected_block, dict) else {},
        "selected_instruction_block_text": str(selected_block.get("body_text") or "").strip() if isinstance(selected_block, dict) else "",
        "instruction_resource_load_plan": instruction_resource_load_plan,
        "template_resource_load_plan": template_resource_load_plan,
    }

    return {
        "forced_turn_intent": forced_turn_intent,
        "action_type": action_type,
        "instruction_retrieval": to_plain_dict(instruction_retrieval),
        "knowledge_retrieval": to_plain_dict(knowledge_retrieval),
        "template_retrieval": to_plain_dict(template_retrieval),
        "instruction_resource_load_plan": instruction_resource_load_plan,
        "template_resource_load_plan": template_resource_load_plan,
        "primary_scope": primary_scope,
        "active_service_block_type": active_service_block_type,
        "active_service_block_id": active_service_block_id,
        "active_service_block_title": active_service_block_title,
        "active_execution_mode": layered_context.get("active_execution_mode"),
        "active_bundled_step_ids": list(layered_context.get("active_bundled_step_ids", []) or []),
        "bundled_execution_completed": bundled_execution_completed,
        "bundled_entry_step_id": layered_context.get("bundled_entry_step_id"),
        "active_step_scope_id": layered_context.get("active_step_scope_id"),
        "primary_support_module_id": layered_context.get("primary_support_module_id"),
        "primary_support_module_title": layered_context.get("primary_support_module_title"),
        "procedure_step_activation": layered_context.get("procedure_step_activation"),
        "primary_support_module_activation": layered_context.get("primary_support_module_activation"),
        "resource_request_provenance": resource_request_provenance,
        "binding_resource_requests": binding_activation.get("binding_requests", []),
        "selected_session_upload_ids": selected_session_upload_ids,
        "response_style": {
            "mode": str(selected_workflow.get("title") or "") if isinstance(selected_workflow, dict) else None,
            "instruction_guided": bool(selected_workflow or selected_module),
            "is_generation_request": bool((pre_routing or {}).get("is_generation_request")),
            "generation_subtype": (pre_routing or {}).get("generation_subtype"),
            "is_out_of_scope": str(forced_turn_intent or "").strip() == "general_out_of_scope_question",
            "instruction_block_title": str(selected_block.get("title") or "").strip() if isinstance(selected_block, dict) else None,
            "instruction_block_type": str(selected_block.get("block_type") or "").strip() if isinstance(selected_block, dict) else None,
            "use_instruction_block_only": bool(selected_block) and not instruction_resource_load_plan,
            "output_artifact_targets": output_artifact_targets,
            "use_session_upload_evidence": bool(selected_session_upload_ids),
            "session_upload_ids": selected_session_upload_ids,
        },
        "state_updates": state_updates,
    }


def _build_turn_action_plan(execution_context: Dict[str, Any]) -> Dict[str, Any]:
    return to_plain_dict(
        TurnActionPlan(
            action_type=execution_context.get("action_type"),
            instruction_retrieval=RetrievalDomainPlan(**(execution_context.get("instruction_retrieval", {}) or {})),
            knowledge_retrieval=RetrievalDomainPlan(**(execution_context.get("knowledge_retrieval", {}) or {})),
            template_retrieval=RetrievalDomainPlan(**(execution_context.get("template_retrieval", {}) or {})),
            instruction_resource_load_plan=[
                InstructionResourceLoadPlan(**item)
                for item in execution_context.get("instruction_resource_load_plan", []) or []
                if isinstance(item, dict)
            ],
            template_resource_load_plan=[
                InstructionResourceLoadPlan(**item)
                for item in execution_context.get("template_resource_load_plan", []) or []
                if isinstance(item, dict)
            ],
            response_style=dict(execution_context.get("response_style", {}) or {}),
            state_updates=dict(execution_context.get("state_updates", {}) or {}),
        )
    )


def run(
    state: GraphState,
    llm_planner: Optional[Callable[[str, list, Dict[str, Any]], Dict[str, Any]]] = None,
    persist_fn: Optional[Callable[[GraphState, Dict[str, Any]], None]] = None,
    repo: Optional[PlannerRepoProtocol] = None,
) -> GraphState:
    """Plan user request and produce PlannerOutput + retrievalPlan.

    Required state input:
    - user_query, config_json, adapter_json, template_registry
    """
    if llm_planner is None:
        llm_planner = state.get("_llm_planner")
    llm_planner_hybrid = state.get("_llm_planner_hybrid")

    if llm_planner is None:
        def _default_llm(prompt: str, tools: list, context: Dict[str, Any]) -> Dict[str, Any]:
            _ = (prompt, tools, context)
            return _default_planner_output(state)
        llm_planner = _default_llm

    for key in ("user_query", "config_json", "adapter_json", "template_registry"):
        if key not in state:
            raise ValueError(f"{key} is required for planner node.")

    try:
        planner_output = _call_planner(llm_planner, _build_main_prompt(state), state)
    except Exception:
        planner_output = _default_planner_output(state)
    planner_output = _normalize_planner_output(planner_output)
    planner_output = _enforce_app_scoped_retrieval(state, planner_output)
    validate_planner_output(planner_output)

    if float(planner_output.get("confidence", 0.0)) < 0.6:
        try:
            planner_output = _call_planner(llm_planner, _build_fallback_prompt(state), state)
        except Exception:
            planner_output = _default_planner_output(state)
        planner_output = _normalize_planner_output(planner_output)
        planner_output = _enforce_app_scoped_retrieval(state, planner_output)
        validate_planner_output(planner_output)

    state["planner_output"] = planner_output
    state["retrieval_plan"] = planner_output["retrievalPlan"]
    hybrid_runtime_model = _compiled_hybrid_runtime_model(state)
    if hybrid_runtime_model:
        hybrid_packet = _build_hybrid_turn_decision_packet(state)
        state["hybrid_planner_decision_packet"] = hybrid_packet
        if callable(llm_planner_hybrid):
            try:
                state["hybrid_planner_shadow_output"] = _call_hybrid_planner_shadow(llm_planner_hybrid, hybrid_packet, state)
            except Exception:
                state["hybrid_planner_shadow_output"] = {}
    pre_routing = _classify_pre_routing_turn(state, planner_output)
    state["turn_routing_classification"] = pre_routing

    selected_workflow = None
    selected_module = None
    selected_block = None
    if not bool(pre_routing.get("skip_workflow_selection")):
        selected_workflow = _select_instruction_workflow(state, planner_output)
        if selected_workflow is not None:
            state["instruction_workflow"] = selected_workflow
        selected_module = _select_instruction_module(state, planner_output, selected_workflow)
        selected_block = _select_instruction_block(state, selected_workflow, selected_module)
    else:
        state["instruction_workflow"] = {}
        state["selected_instruction_block"] = {}
        state["selected_instruction_block_text"] = ""
        state["instruction_resource"] = ""
        state["instruction_resource_filters"] = {}
        if str(pre_routing.get("turn_intent") or "").strip() == "general_out_of_scope_question":
            state["instruction_module"] = {}
            state["instruction_step"] = {}
        else:
            selected_module = _select_instruction_module(state, planner_output, None)
            selected_block = _select_instruction_block(state, None, selected_module)
    if selected_block is not None:
        state["selected_instruction_block"] = selected_block
        state["selected_instruction_block_text"] = str(selected_block.get("body_text") or "").strip()
    if selected_module is not None:
        state["instruction_module"] = selected_module
        state["instruction_step"] = selected_module
        primary_resource = str(
            selected_module.get("resource_file")
            or selected_module.get("primary_resource")
            or ""
        ).strip()
        if primary_resource:
            state["instruction_resource"] = primary_resource
            state["instruction_resource_filters"] = {"filename": primary_resource}
        if selected_workflow is not None:
            state["workflow_progress"] = {
                "workflow_id": selected_workflow.get("id"),
                "workflow_title": selected_workflow.get("title"),
                "step_order": selected_module.get("order"),
                "step_title": selected_module.get("title"),
                "resource_file": primary_resource,
            }
    else:
        primary_resource = ""
        if selected_workflow is not None:
            state["workflow_progress"] = {
                "workflow_id": selected_workflow.get("id"),
                "workflow_title": selected_workflow.get("title"),
                "step_order": None,
                "step_title": None,
                "resource_file": None,
            }

    execution_context = _build_execution_context(
        state,
        planner_output,
        selected_workflow,
        selected_module,
        selected_block,
        selected_module,
        primary_resource,
        str(pre_routing.get("turn_intent") or "").strip() or None,
        pre_routing,
    )
    turn_action_plan = _build_turn_action_plan(execution_context)
    state["turn_action_plan"] = turn_action_plan
    state["turn_execution_plan"] = _build_turn_execution_plan(
        state,
        planner_output,
        selected_workflow,
        selected_module,
        selected_block,
        selected_module,
        execution_context,
        primary_resource,
    )
    hybrid_selected_role_id = _hybrid_active_selected_role_id(state)
    hybrid_module_queue = _hybrid_active_module_queue(state)
    hybrid_selected_routing_rule_id = _hybrid_active_selected_routing_rule_id(state)
    hybrid_logic_block = _hybrid_active_selected_interaction_logic_block(state)
    hybrid_primary_support_module_id, hybrid_primary_support_module_title = _hybrid_active_primary_support_module(
        state,
        hybrid_module_queue,
    )
    hybrid_logic_only_scope = _hybrid_active_should_stay_logic_only(state, hybrid_module_queue)
    if hybrid_selected_role_id and isinstance(state.get("turn_execution_plan"), dict):
        state["turn_execution_plan"]["selected_role_id"] = hybrid_selected_role_id
    if hybrid_selected_routing_rule_id and isinstance(state.get("turn_execution_plan"), dict):
        state["turn_execution_plan"]["selected_routing_rule_id"] = hybrid_selected_routing_rule_id
    if hybrid_module_queue and isinstance(state.get("turn_execution_plan"), dict):
        state["turn_execution_plan"]["active_module_queue"] = list(hybrid_module_queue)
        state["turn_execution_plan"]["current_module_index"] = 0
    if hybrid_primary_support_module_id and isinstance(state.get("turn_execution_plan"), dict):
        state["turn_execution_plan"]["primary_support_module_scope"] = {
            "scope_id": hybrid_primary_support_module_id,
            "scope_type": "module",
            "title": hybrid_primary_support_module_title,
            "reason": "selected_primary_support_module",
        }
    elif hybrid_logic_only_scope and isinstance(state.get("turn_execution_plan"), dict):
        for key in (
            "primary_support_module_scope",
            "active_step_scope",
            "active_service_block_id",
            "active_service_block_type",
            "active_service_block_title",
            "primary_scope",
            "primary_scope_id",
            "primary_scope_type",
            "primary_scope_title",
        ):
            state["turn_execution_plan"].pop(key, None)
        logic_scope_id = str(
            (hybrid_logic_block or {}).get("logic_id")
            or (hybrid_logic_block or {}).get("block_id")
            or ""
        ).strip()
        logic_scope_title = str((hybrid_logic_block or {}).get("title") or "").strip() or None
        if logic_scope_id:
            state["turn_execution_plan"]["primary_scope"] = {
                "scope_id": logic_scope_id,
                "scope_type": "mode",
                "title": logic_scope_title,
                "reason": "selected_routing_logic",
            }
    state["presentation_policy"] = state["turn_execution_plan"].get("presentation_policy", state.get("presentation_policy", {}))
    execution_plan_state_updates = (
        state["turn_execution_plan"].get("state_updates", {})
        if isinstance(state.get("turn_execution_plan"), dict)
        else {}
    )
    state["session_execution_state"] = execution_plan_state_updates.get(
        "session_execution_state",
        state.get("session_execution_state", {}),
    )
    if hybrid_selected_role_id and isinstance(state.get("session_execution_state"), dict):
        state["session_execution_state"]["active_role_id"] = hybrid_selected_role_id
    if hybrid_selected_routing_rule_id and isinstance(state.get("session_execution_state"), dict):
        state["session_execution_state"]["selected_routing_rule_id"] = hybrid_selected_routing_rule_id
    if hybrid_module_queue and isinstance(state.get("session_execution_state"), dict):
        state["session_execution_state"]["active_module_queue"] = list(hybrid_module_queue)
        state["session_execution_state"]["current_module_index"] = 0
    if hybrid_primary_support_module_id and isinstance(state.get("session_execution_state"), dict):
        state["session_execution_state"]["primary_support_module_id"] = hybrid_primary_support_module_id
        state["session_execution_state"]["primary_support_module_title"] = hybrid_primary_support_module_title
    elif hybrid_logic_only_scope and isinstance(state.get("session_execution_state"), dict):
        for key in (
            "primary_support_module_id",
            "primary_support_module_title",
            "active_service_block_id",
            "active_service_block_type",
            "active_service_block_title",
            "active_step_scope_id",
            "procedure_step_activation",
            "primary_support_module_activation",
            "active_execution_mode",
            "active_bundled_step_ids",
            "bundled_entry_step_id",
        ):
            state["session_execution_state"].pop(key, None)
        logic_scope_id = str(
            (hybrid_logic_block or {}).get("logic_id")
            or (hybrid_logic_block or {}).get("block_id")
            or ""
        ).strip()
        logic_scope_title = str((hybrid_logic_block or {}).get("title") or "").strip() or None
        if logic_scope_id:
            state["session_execution_state"]["primary_scope_id"] = logic_scope_id
            state["session_execution_state"]["primary_scope_type"] = "mode"
            state["session_execution_state"]["primary_scope_title"] = logic_scope_title
            state["session_execution_state"]["active_mode"] = logic_scope_id
            state["session_execution_state"]["active_workflow"] = logic_scope_title
            state["session_execution_state"]["active_step_order"] = None
            state["session_execution_state"]["active_step_title"] = logic_scope_title
    hybrid_primary_support_block = (
        _service_block_by_id(state, hybrid_primary_support_module_id)
        if hybrid_primary_support_module_id
        else None
    )
    if isinstance(hybrid_primary_support_block, dict):
        block_id = str(hybrid_primary_support_block.get("block_id") or "").strip() or hybrid_primary_support_module_id
        block_title = str(hybrid_primary_support_block.get("title") or "").strip() or hybrid_primary_support_module_title
        block_type = str(hybrid_primary_support_block.get("block_type") or "").strip()
        is_followup_module = block_type == "followup_module"
        support_block_activation = _activation_for_service_block(state, hybrid_primary_support_block)
        support_block_binding_activation = _derive_binding_activation_for_scope_id(
            state,
            block_id,
            stage_label=block_title or None,
            query_text=str(state.get("user_query") or "").strip() or None,
            include_descendant_scope_bindings=not bool(support_block_activation.get("active_step_scope_id")),
            strict_scope_id_match=bool(support_block_activation.get("active_step_scope_id")),
        )
        if isinstance(state.get("turn_execution_plan"), dict):
            existing_active_step_scope = (
                state["turn_execution_plan"].get("active_step_scope", {})
                if isinstance(state["turn_execution_plan"].get("active_step_scope"), dict)
                else {}
            )
            existing_step_scope_id = str(existing_active_step_scope.get("scope_id") or "").strip()
            support_step_scope_id = str(support_block_activation.get("active_step_scope_id") or "").strip()
            preserve_existing_step_scope = bool(
                not is_followup_module
                and existing_step_scope_id
                and support_step_scope_id
                and existing_step_scope_id != support_step_scope_id
            )
            for key, value in support_block_activation.items():
                if value is not None and value != [] and value != {}:
                    if preserve_existing_step_scope and key in {
                        "active_step_scope_id",
                        "procedure_step_activation",
                        "active_execution_mode",
                        "active_bundled_step_ids",
                        "bundled_entry_step_id",
                        "bundled_execution_completed",
                    }:
                        continue
                    state["turn_execution_plan"][key] = value
            if str(hybrid_primary_support_block.get("block_type") or "").strip() == "support_module":
                state["turn_execution_plan"]["primary_scope"] = {
                    "scope_id": block_id,
                    "scope_type": "module",
                    "title": block_title or None,
                    "reason": "selected_primary_support_module",
                }
            active_step_scope = _build_active_step_scope(support_block_activation)
            if isinstance(active_step_scope, dict) and active_step_scope:
                state["turn_execution_plan"]["active_step_scope"] = active_step_scope
            elif is_followup_module:
                state["turn_execution_plan"].pop("active_step_scope", None)
            existing_requests = (
                state["turn_execution_plan"].get("resource_requests", [])
                if isinstance(state["turn_execution_plan"].get("resource_requests"), list)
                else []
            )
            if is_followup_module:
                existing_requests = [
                    item
                    for item in existing_requests
                    if not (
                        isinstance(item, dict)
                        and str(item.get("resource_role") or "").strip() in {"instruction_source", "output_template"}
                    )
                ]
            seen_request_keys = {
                (
                    str(item.get("binding_id") or ""),
                    str(item.get("dependency_group_id") or ""),
                    str(item.get("filename") or item.get("resource_id") or ""),
                )
                for item in existing_requests
                if isinstance(item, dict)
            }
            for request in support_block_binding_activation.get("binding_requests", []):
                if not isinstance(request, dict):
                    continue
                if not _binding_can_supply_resource_request(request):
                    continue
                key = (
                    str(request.get("binding_id") or ""),
                    str(request.get("dependency_group_id") or ""),
                    str(request.get("filename") or request.get("resource_id") or ""),
                )
                if key not in seen_request_keys:
                    seen_request_keys.add(key)
                    existing_requests.append(request)
            if is_followup_module:
                for request in _followup_module_resource_requests(state, block_id, block_title):
                    key = (
                        str(request.get("binding_id") or ""),
                        str(request.get("dependency_group_id") or ""),
                        str(request.get("filename") or request.get("resource_id") or ""),
                    )
                    if key not in seen_request_keys:
                        seen_request_keys.add(key)
                        existing_requests.append(request)
            state["turn_execution_plan"]["resource_requests"] = existing_requests
            for key in ("active_binding_ids", "active_dependency_group_ids", "active_artifact_roles"):
                existing_values = (
                    state["turn_execution_plan"].get(key, [])
                    if isinstance(state["turn_execution_plan"].get(key), list)
                    else []
                )
                for item in support_block_binding_activation.get(key, []):
                    if item not in existing_values:
                        existing_values.append(item)
                if existing_values:
                    state["turn_execution_plan"][key] = existing_values
            if is_followup_module:
                state["turn_execution_plan"]["active_service_block_title"] = block_title or None
                selected_followup_block = {
                    "block_id": block_id,
                    "block_type": "followup_module",
                    "title": block_title or None,
                    "body_text": "",
                }
                state["selected_instruction_block"] = selected_followup_block
                state["selected_instruction_block_text"] = ""
                state["turn_execution_plan"]["state_updates"]["selected_instruction_block"] = selected_followup_block
                state["turn_execution_plan"]["state_updates"]["selected_instruction_block_text"] = ""
        if isinstance(state.get("session_execution_state"), dict):
            existing_step_scope_id = str(state["session_execution_state"].get("active_step_scope_id") or "").strip()
            support_step_scope_id = str(support_block_activation.get("active_step_scope_id") or "").strip()
            preserve_existing_step_scope = bool(
                not is_followup_module
                and existing_step_scope_id
                and support_step_scope_id
                and existing_step_scope_id != support_step_scope_id
            )
            for key, value in support_block_activation.items():
                if value is not None and value != [] and value != {}:
                    if preserve_existing_step_scope and key in {
                        "active_step_scope_id",
                        "procedure_step_activation",
                        "active_execution_mode",
                        "active_bundled_step_ids",
                        "bundled_entry_step_id",
                        "bundled_execution_completed",
                    }:
                        continue
                    state["session_execution_state"][key] = value
            if is_followup_module:
                for key in (
                    "active_step_scope_id",
                    "procedure_step_activation",
                    "active_execution_mode",
                    "active_bundled_step_ids",
                    "bundled_entry_step_id",
                ):
                    state["session_execution_state"].pop(key, None)
                state["session_execution_state"]["active_step_order"] = None
                state["session_execution_state"]["active_step_title"] = block_title or None
            if block_id and str(hybrid_primary_support_block.get("block_type") or "").strip() == "support_module":
                state["session_execution_state"]["primary_support_module_id"] = block_id
            if block_title and str(hybrid_primary_support_block.get("block_type") or "").strip() == "support_module":
                state["session_execution_state"]["primary_support_module_title"] = block_title
            for key in ("active_binding_ids", "active_dependency_group_ids", "active_artifact_roles"):
                existing_values = (
                    state["session_execution_state"].get(key, [])
                    if isinstance(state["session_execution_state"].get(key), list)
                    else []
                )
                for item in support_block_binding_activation.get(key, []):
                    if item not in existing_values:
                        existing_values.append(item)
                state["session_execution_state"][key] = existing_values
    if isinstance(state.get("session_execution_state"), dict) and isinstance(state.get("turn_execution_plan"), dict):
        final_service_block_type = str(state["session_execution_state"].get("active_service_block_type") or "").strip()
        final_service_block_id = str(state["session_execution_state"].get("active_service_block_id") or "").strip()
        final_service_block_title = str(state["session_execution_state"].get("active_service_block_title") or "").strip()
        if final_service_block_type == "followup_module" and final_service_block_id:
            followup_requests = _followup_module_resource_requests(
                state,
                final_service_block_id,
                final_service_block_title or None,
            )
            if followup_requests:
                existing_requests = (
                    state["turn_execution_plan"].get("resource_requests", [])
                    if isinstance(state["turn_execution_plan"].get("resource_requests"), list)
                    else []
                )
                retained_requests = [
                    item
                    for item in existing_requests
                    if not (
                        isinstance(item, dict)
                        and str(item.get("resource_role") or "").strip() in {"instruction_source", "output_template"}
                    )
                ]
                retained_requests.extend(followup_requests)
                state["turn_execution_plan"]["resource_requests"] = retained_requests
                followup_instruction_load_plan: list[dict] = []
                for request in followup_requests:
                    if not isinstance(request, dict):
                        continue
                    filename = str(request.get("filename") or "").strip()
                    if not filename:
                        continue
                    resource = _runtime_resource_by_filename(state, filename)
                    if not isinstance(resource, dict):
                        continue
                    followup_instruction_load_plan.append(
                        {
                            "resource_id": str(resource.get("resource_id") or "").strip() or None,
                            "filename": filename,
                            "resource_role": str(resource.get("domain") or "").strip() or "instruction_source",
                            "load_strategy": _instruction_load_strategy_for_state(state, filename),
                            "reason": "followup_module_explicit_resource",
                            "size_hint": None,
                            "document_id": resource.get("document_id"),
                        }
                    )
                if followup_instruction_load_plan:
                    state["turn_execution_plan"]["state_updates"]["instruction_resource_load_plan"] = followup_instruction_load_plan
                    state["turn_execution_plan"]["state_updates"]["template_resource_load_plan"] = []
                    state["turn_execution_plan"]["state_updates"]["instruction_resource_filters"] = _merge_filename_filters(
                        {},
                        [str(item.get("filename") or "").strip() for item in followup_instruction_load_plan if str(item.get("filename") or "").strip()],
                    )
                    state["turn_execution_plan"]["state_updates"]["template_resource_filters"] = {}
    selected_session_upload_ids = _session_upload_ids_from_execution_plan(state.get("turn_execution_plan", {}))
    if selected_session_upload_ids and isinstance(state["session_execution_state"], dict):
        state["session_execution_state"]["active_session_upload_ids"] = selected_session_upload_ids
    if primary_resource:
        instruction_filters = execution_plan_state_updates.get("instruction_resource_filters", {})
        if isinstance(instruction_filters, dict) and instruction_filters:
            state["instruction_resource_filters"] = instruction_filters
    selected_block_payload = execution_plan_state_updates.get("selected_instruction_block", {})
    if isinstance(selected_block_payload, dict) and selected_block_payload:
        state["selected_instruction_block"] = selected_block_payload
    selected_block_text = execution_plan_state_updates.get("selected_instruction_block_text")
    if isinstance(selected_block_text, str):
        state["selected_instruction_block_text"] = selected_block_text
    resource_load_plan = execution_plan_state_updates.get("instruction_resource_load_plan", [])
    if isinstance(resource_load_plan, list):
        state["instruction_resource_load_plan"] = resource_load_plan
    template_load_plan = execution_plan_state_updates.get("template_resource_load_plan", [])
    if isinstance(template_load_plan, list):
        state["template_resource_load_plan"] = template_load_plan
    _sync_resource_load_plans_from_turn_requests(state)

    if persist_fn is not None:
        persist_fn(state, planner_output)
    elif repo is not None:
        session_id = state.get("session_id")
        if not session_id:
            raise ValueError("session_id is required to persist planner_outputs via repo.")
        repo.save(session_id=session_id, user_query=state["user_query"], planner_output=planner_output)

    return state

