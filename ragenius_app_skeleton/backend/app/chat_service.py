"""Chat pipeline execution using LangGraph workflow."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

try:
    from workflows.graph import build_graph
except ModuleNotFoundError:  # pragma: no cover
    from ragenius_app_skeleton.workflows.graph import build_graph

from .chat_repos import ChatRepo, RetrievalRepo, SessionRepo
from .llm_runtime import build_task_binding, configured_task_models, maybe_build_task_callable
from .llm_context_optimization import (
    context_optimization_mode,
    finalize_task_model_diagnostics,
    normal_query_optimization_eligible,
)
from .planner_repo import InMemoryPlannerRepo

_GRAPH = None


def _graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


def _default_llm_planner(_prompt: str, _tools: list, context: Dict[str, Any]) -> Dict[str, Any]:
    query = str(context.get("user_query", ""))
    app_id = str(context.get("app_id") or context.get("collection_id") or "").strip()
    return {
        "intentType": "qa",
        "confidence": 0.85,
        "steps": [{"id": "1", "title": "Retrieve evidence", "goal": "Answer query", "reasoning": None}],
        "infoTypes": ["fact"],
        "retrievalPlan": {"query_text": query, "top_k": 3, "filters": {"app_id": app_id} if app_id else {}, "explanation": None},
        "systemInstructionSummary": {"fromConfigPdf": [], "fromAdapter": [], "fromTemplate": []},
        "normalizedQuery": query,
        "contextualQuery": query,
    }


def _default_llm_answer(_prompt: str, _tools: list, context: Dict[str, Any]) -> Dict[str, Any]:
    evidence = context.get("compressed_evidence", [])
    citation = {
        "docId": str(evidence[0].get("doc_id", "doc-unknown")) if evidence else "doc-unknown",
        "title": str(evidence[0].get("title", "Reference")) if evidence else "Reference",
        "snippet": str(evidence[0].get("snippet", "No snippet")) if evidence else "No snippet",
        "score": float(evidence[0].get("score", 0.5)) if evidence else 0.5,
        "location": evidence[0].get("location") if evidence else None,
        "version": evidence[0].get("version") if evidence else None,
    }
    return {
        "content": "Here is the best answer based on retrieved evidence.",
        "citations": [citation],
        "missing_infoTypes": [],
    }


def _summarize_execution_actions(turn_execution_plan: dict) -> Dict[str, Any]:
    actions = turn_execution_plan.get("actions", []) if isinstance(turn_execution_plan, dict) else []
    normalized_actions = [item for item in actions if isinstance(item, dict)]
    action_types = [
        str(item.get("action_type") or "").strip()
        for item in normalized_actions
        if str(item.get("action_type") or "").strip()
    ]
    primary_action_type = action_types[0] if action_types else None
    return {
        "primary_action_type": primary_action_type,
        "action_types": action_types,
        "action_count": len(normalized_actions),
        "action_type": primary_action_type,
    }


def _respond_to_user_style(turn_execution_plan: dict) -> Dict[str, Any]:
    actions = turn_execution_plan.get("actions", []) if isinstance(turn_execution_plan, dict) else []
    if not isinstance(actions, list):
        return {}
    for item in actions:
        if not isinstance(item, dict):
            continue
        if str(item.get("action_type") or "").strip() != "respond_to_user":
            continue
        params = item.get("params", {})
        if not isinstance(params, dict):
            return {}
        response_style = params.get("response_style", {})
        return response_style if isinstance(response_style, dict) else {}
    return {}


def _resource_requests_by_role(turn_execution_plan: dict, resource_role: str) -> list[dict]:
    requests = turn_execution_plan.get("resource_requests", []) if isinstance(turn_execution_plan, dict) else []
    return [
        item
        for item in requests
        if isinstance(item, dict) and str(item.get("resource_role") or "").strip() == resource_role
    ]


def _request_query(requests: list[dict], fallback_query: str | None) -> str | None:
    for item in requests:
        query_text = str(item.get("query_text") or "").strip()
        if query_text:
            return query_text
        purpose = str(item.get("purpose") or "").strip()
        if purpose:
            return purpose
    filenames = [str(item.get("filename") or "").strip() for item in requests if str(item.get("filename") or "").strip()]
    if filenames:
        return " | ".join(filenames)
    return fallback_query


def _request_context_hints(requests: list[dict], fallback_hints: list[str]) -> list[str]:
    hints: list[str] = []
    for item in requests:
        for raw_hint in item.get("context_hints", []) or []:
            hint = str(raw_hint or "").strip()
            if hint and hint not in hints:
                hints.append(hint)
        filename = str(item.get("filename") or "").strip()
        if filename and filename not in hints:
            hints.append(filename)
        resource_id = str(item.get("resource_id") or "").strip()
        if resource_id and resource_id not in hints:
            hints.append(resource_id)
        load_strategy = str(item.get("load_strategy_hint") or "").strip()
        if load_strategy and load_strategy not in hints:
            hints.append(load_strategy)
    if hints:
        return hints
    return [str(item).strip() for item in fallback_hints if str(item).strip()]


def _append_unique(values: list[str], candidate: str | None) -> None:
    normalized = str(candidate or "").strip()
    if normalized and normalized not in values:
        values.append(normalized)


def _resource_context_titles(result: Dict[str, Any], collection_key: str) -> list[str]:
    collection = result.get(collection_key, [])
    if not isinstance(collection, list):
        return []
    titles: list[str] = []
    for item in collection:
        if not isinstance(item, dict):
            continue
        candidate = (
            str(item.get("title") or "").strip()
            or str(item.get("filename") or "").strip()
            or str(item.get("resource_id") or "").strip()
        )
        if candidate:
            _append_unique(titles, candidate)
    return titles


def _merge_direct_resource_counts(
    result: Dict[str, Any],
    *,
    collection_key: str,
    existing_count: int,
    existing_titles: list[str],
    top_titles: list[str],
    seen_top_titles: set[str],
    source_keys: list[str],
) -> tuple[int, list[str], int]:
    if existing_count > 0:
        return existing_count, existing_titles, 0
    direct_titles = _resource_context_titles(result, collection_key)
    for title in direct_titles:
        _append_unique(existing_titles, title)
        if title not in seen_top_titles and len(top_titles) < 3:
            seen_top_titles.add(title)
            top_titles.append(title)
        if title and title not in source_keys:
            source_keys.append(title)
    return len(direct_titles), existing_titles, len(direct_titles)


def _selected_resource_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    turn_execution_plan = result.get("turn_execution_plan", {}) if isinstance(result.get("turn_execution_plan"), dict) else {}
    requests = turn_execution_plan.get("resource_requests", []) if isinstance(turn_execution_plan, dict) else []
    selected_resources: list[dict] = []
    selected_resource_filenames: list[str] = []
    selected_resource_kinds: list[str] = []

    def add_entry(entry: dict) -> None:
        filename = str(entry.get("filename") or "").strip() or None
        resource_kind = str(entry.get("resource_kind") or "").strip() or None
        normalized = {
            "filename": filename,
            "resource_kind": resource_kind,
            "binding_id": str(entry.get("binding_id") or "").strip() or None,
            "dependency_group_id": str(entry.get("dependency_group_id") or "").strip() or None,
            "artifact_role": str(entry.get("artifact_role") or "").strip() or None,
        }
        if not any(normalized.values()):
            return
        if normalized not in selected_resources:
            selected_resources.append(normalized)
        _append_unique(selected_resource_filenames, filename)
        _append_unique(selected_resource_kinds, resource_kind)

    for item in requests:
        if isinstance(item, dict):
            add_entry(item)
    for collection_key in ("instruction_resource_context", "template_resource_context"):
        collection = result.get(collection_key, [])
        if not isinstance(collection, list):
            continue
        for item in collection:
            if isinstance(item, dict):
                add_entry(item)

    return {
        "selected_resources": selected_resources,
        "selected_resource_filenames": selected_resource_filenames,
        "selected_resource_kinds": selected_resource_kinds,
    }


def _layered_scope_summary(session_execution_state: Dict[str, Any]) -> Dict[str, Any]:
    procedure_step_activation = (
        session_execution_state.get("procedure_step_activation", {})
        if isinstance(session_execution_state.get("procedure_step_activation"), dict)
        else {}
    )
    primary_support_module_activation = (
        session_execution_state.get("primary_support_module_activation", {})
        if isinstance(session_execution_state.get("primary_support_module_activation"), dict)
        else {}
    )
    active_step_scope_id = str(session_execution_state.get("active_step_scope_id") or "").strip() or None
    active_step_scope = (
        {
            "scope_id": active_step_scope_id,
            "scope_type": str(procedure_step_activation.get("step_scope_type") or "step").strip() or "step",
            "title": str(procedure_step_activation.get("step_title") or "").strip() or None,
            "step_order": procedure_step_activation.get("step_order"),
        }
        if active_step_scope_id
        else None
    )
    primary_support_module_scope_id = (
        str(session_execution_state.get("primary_support_module_id") or "").strip()
        or str(primary_support_module_activation.get("support_module_id") or "").strip()
        or None
    )
    primary_support_module_scope = (
        {
            "scope_id": primary_support_module_scope_id,
            "scope_type": "module",
            "title": str(session_execution_state.get("primary_support_module_title") or primary_support_module_activation.get("title") or "").strip() or None,
            "step_scope_id": str(primary_support_module_activation.get("step_scope_id") or active_step_scope_id or "").strip() or None,
        }
        if primary_support_module_scope_id
        else None
    )
    return {
        "active_step_scope": active_step_scope,
        "active_step_scope_id": active_step_scope_id,
        "primary_support_module_scope": primary_support_module_scope,
        "primary_support_module_scope_id": primary_support_module_scope_id,
    }


def _request_provenance_summary(turn_execution_plan: dict) -> list[dict]:
    requests = turn_execution_plan.get("resource_requests", []) if isinstance(turn_execution_plan, dict) else []
    groups: list[dict] = []
    group_index: dict[tuple[str | None, str | None, str | None], dict] = {}
    for item in requests:
        if not isinstance(item, dict):
            continue
        source_layer = str(item.get("source_layer") or "").strip() or None
        step_scope_id = str(item.get("step_scope_id") or "").strip() or None
        support_module_id = str(item.get("support_module_id") or "").strip() or None
        if not any((source_layer, step_scope_id, support_module_id)):
            continue
        key = (source_layer, step_scope_id, support_module_id)
        current = group_index.get(key)
        if current is None:
            current = {
                "source_layer": source_layer,
                "step_scope_id": step_scope_id,
                "support_module_id": support_module_id,
                "filenames": [],
                "request_count": 0,
            }
            group_index[key] = current
            groups.append(current)
        filename = str(item.get("filename") or "").strip()
        if filename and filename not in current["filenames"]:
            current["filenames"].append(filename)
        current["request_count"] += 1
    return groups


def _build_retrieval_summary(result: Dict[str, Any], final_answer: Dict[str, Any]) -> Dict[str, Any]:
    raw_evidence = result.get("raw_evidence", []) or []
    debug_trace = result.get("retrieval_debug_trace", {}) or {}
    citations = final_answer.get("citations", []) if isinstance(final_answer, dict) else []
    route = debug_trace.get("route", {}) if isinstance(debug_trace, dict) else {}
    domains = debug_trace.get("domains", {}) if isinstance(debug_trace, dict) else {}
    turn_execution_plan = result.get("turn_execution_plan", {}) if isinstance(result.get("turn_execution_plan"), dict) else {}
    session_execution_state = (
        result.get("session_execution_state", {})
        if isinstance(result.get("session_execution_state"), dict)
        else {}
    )
    answer_generation_meta = (
        result.get("answer_generation_meta", {})
        if isinstance(result.get("answer_generation_meta"), dict)
        else {}
    )
    presentation_policy = result.get("presentation_policy", {}) if isinstance(result.get("presentation_policy"), dict) else {}
    visible_outputs = result.get("visible_outputs", []) if isinstance(result.get("visible_outputs"), list) else []
    hidden_outputs = result.get("hidden_outputs", []) if isinstance(result.get("hidden_outputs"), list) else []
    execution_artifacts = result.get("execution_artifacts", []) if isinstance(result.get("execution_artifacts"), list) else []
    tool_results = result.get("tool_results", []) if isinstance(result.get("tool_results"), list) else []
    selected_resource_summary = _selected_resource_summary(result)
    assembly_state = result.get("assembly_state", {}) if isinstance(result.get("assembly_state"), dict) else {}
    task_model_diagnostics = (
        result.get("task_model_diagnostics", {})
        if isinstance(result.get("task_model_diagnostics"), dict)
        else {}
    )
    output_artifact_targets = session_execution_state.get("output_artifact_targets", []) if isinstance(session_execution_state, dict) else []
    if not isinstance(output_artifact_targets, list) or not output_artifact_targets:
        output_artifact_targets = assembly_state.get("target_outputs", []) if isinstance(assembly_state.get("target_outputs"), list) else []
    primary_scope = turn_execution_plan.get("primary_scope", {}) if isinstance(turn_execution_plan.get("primary_scope"), dict) else {}
    secondary_scopes = turn_execution_plan.get("secondary_scopes", []) if isinstance(turn_execution_plan.get("secondary_scopes"), list) else []
    action_summary = _summarize_execution_actions(turn_execution_plan)
    response_style = _respond_to_user_style(turn_execution_plan)
    layered_scope_summary = _layered_scope_summary(session_execution_state)
    request_provenance_summary = _request_provenance_summary(turn_execution_plan)
    instruction_requests = _resource_requests_by_role(turn_execution_plan, "instruction_source")
    template_requests = _resource_requests_by_role(turn_execution_plan, "output_template")
    active_execution_mode = (
        str(session_execution_state.get("active_execution_mode") or "").strip()
        if isinstance(session_execution_state, dict)
        else ""
    ) or (
        str(turn_execution_plan.get("active_execution_mode") or "").strip()
        if isinstance(turn_execution_plan, dict)
        else ""
    ) or None
    active_bundled_step_ids = (
        [
            str(item).strip()
            for item in session_execution_state.get("active_bundled_step_ids", []) or []
            if str(item).strip()
        ]
        if isinstance(session_execution_state, dict) and session_execution_state.get("active_bundled_step_ids") is not None
        else []
    )
    if not active_bundled_step_ids:
        active_bundled_step_ids = (
            [
                str(item).strip()
                for item in turn_execution_plan.get("active_bundled_step_ids", []) or []
                if str(item).strip()
            ]
            if isinstance(turn_execution_plan, dict)
            else []
        )
    bundled_entry_step_id = (
        str(session_execution_state.get("bundled_entry_step_id") or "").strip()
        if isinstance(session_execution_state, dict)
        else ""
    ) or (
        str(turn_execution_plan.get("bundled_entry_step_id") or "").strip()
        if isinstance(turn_execution_plan, dict)
        else ""
    ) or None
    bundled_execution_completed = (
        bool(session_execution_state.get("bundled_execution_completed"))
        if isinstance(session_execution_state, dict) and "bundled_execution_completed" in session_execution_state
        else bool(turn_execution_plan.get("bundled_execution_completed"))
        if isinstance(turn_execution_plan, dict)
        else False
    )

    source_keys = []
    top_titles = []
    seen_titles = set()
    instruction_titles = []
    knowledge_titles = []
    template_titles = []
    session_upload_titles = []
    seen_instruction_titles = set()
    seen_knowledge_titles = set()
    seen_template_titles = set()
    seen_session_upload_titles = set()
    instruction_count = 0
    knowledge_count = 0
    template_count = 0
    session_upload_count = 0
    for item in raw_evidence:
        if not isinstance(item, dict):
            continue
        source_keys.append(item.get("doc_id") or item.get("title") or "unknown")
        title = str(item.get("title") or item.get("doc_id") or "Document")
        if title not in seen_titles and len(top_titles) < 3:
            seen_titles.add(title)
            top_titles.append(title)
        retrieval_domain = str(item.get("retrieval_domain") or "").strip()
        if retrieval_domain == "instruction_source":
            instruction_count += 1
            if title not in seen_instruction_titles and len(instruction_titles) < 3:
                seen_instruction_titles.add(title)
                instruction_titles.append(title)
        elif retrieval_domain == "knowledge_source":
            knowledge_count += 1
            if title not in seen_knowledge_titles and len(knowledge_titles) < 3:
                seen_knowledge_titles.add(title)
                knowledge_titles.append(title)
        elif retrieval_domain == "output_template":
            template_count += 1
            if title not in seen_template_titles and len(template_titles) < 3:
                seen_template_titles.add(title)
                template_titles.append(title)
        elif retrieval_domain == "session_upload":
            session_upload_count += 1
            if title not in seen_session_upload_titles and len(session_upload_titles) < 3:
                seen_session_upload_titles.add(title)
                session_upload_titles.append(title)

    direct_loaded_count = 0
    instruction_count, instruction_titles, added = _merge_direct_resource_counts(
        result,
        collection_key="instruction_resource_context",
        existing_count=instruction_count,
        existing_titles=instruction_titles,
        top_titles=top_titles,
        seen_top_titles=seen_titles,
        source_keys=source_keys,
    )
    direct_loaded_count += added
    template_count, template_titles, added = _merge_direct_resource_counts(
        result,
        collection_key="template_resource_context",
        existing_count=template_count,
        existing_titles=template_titles,
        top_titles=top_titles,
        seen_top_titles=seen_titles,
        source_keys=source_keys,
    )
    direct_loaded_count += added

    return {
        "retrieved_count": len(raw_evidence) + direct_loaded_count,
        "instruction_retrieved_count": instruction_count,
        "knowledge_retrieved_count": knowledge_count,
        "template_retrieved_count": template_count,
        "session_upload_retrieved_count": session_upload_count,
        "citation_count": len(citations) if isinstance(citations, list) else 0,
        "source_count": len({key for key in source_keys if key}),
        "top_titles": top_titles,
        "instruction_titles": instruction_titles,
        "knowledge_titles": knowledge_titles,
        "template_titles": template_titles,
        "session_upload_titles": session_upload_titles,
        "route_language": route.get("language"),
        "route_model": route.get("model"),
        "route_namespace": route.get("namespace"),
        "instruction_route": domains.get("instruction_source", {}).get("route", {})
        if isinstance(domains.get("instruction_source"), dict)
        else {},
        "knowledge_route": domains.get("knowledge_source", {}).get("route", {})
        if isinstance(domains.get("knowledge_source"), dict)
        else {},
        "template_route": domains.get("output_template", {}).get("route", {})
        if isinstance(domains.get("output_template"), dict)
        else {},
        "session_upload_route": domains.get("session_upload", {}).get("route", {})
        if isinstance(domains.get("session_upload"), dict)
        else {},
        "instruction_query": _request_query(
            instruction_requests,
            None,
        ),
        "instruction_context_hints": _request_context_hints(
            instruction_requests,
            [],
        ),
        "instruction_executed_queries": domains.get("instruction_source", {}).get("executed_queries", [])
        if isinstance(domains.get("instruction_source"), dict)
        else [],
        "knowledge_executed_queries": domains.get("knowledge_source", {}).get("executed_queries", [])
        if isinstance(domains.get("knowledge_source"), dict)
        else [],
        "template_query": _request_query(
            template_requests,
            None,
        ),
        "template_context_hints": _request_context_hints(
            template_requests,
            [],
        ),
        "template_executed_queries": domains.get("output_template", {}).get("executed_queries", [])
        if isinstance(domains.get("output_template"), dict)
        else [],
        "session_upload_executed_queries": domains.get("session_upload", {}).get("executed_queries", [])
        if isinstance(domains.get("session_upload"), dict)
        else [],
        "instruction_attempt_count": domains.get("instruction_source", {}).get("attempt_count", 0)
        if isinstance(domains.get("instruction_source"), dict)
        else 0,
        "knowledge_attempt_count": domains.get("knowledge_source", {}).get("attempt_count", 0)
        if isinstance(domains.get("knowledge_source"), dict)
        else 0,
        "template_attempt_count": domains.get("output_template", {}).get("attempt_count", 0)
        if isinstance(domains.get("output_template"), dict)
        else 0,
        "session_upload_attempt_count": domains.get("session_upload", {}).get("attempt_count", 0)
        if isinstance(domains.get("session_upload"), dict)
        else 0,
        "knowledge_retry_triggered": domains.get("knowledge_source", {}).get("weak_retry_triggered", False)
        if isinstance(domains.get("knowledge_source"), dict)
        else False,
        "instruction_resource": result.get("instruction_resource"),
        "instruction_block_title": result.get("selected_instruction_block", {}).get("title")
        if isinstance(result.get("selected_instruction_block"), dict)
        else None,
        "instruction_block_type": result.get("selected_instruction_block", {}).get("block_type")
        if isinstance(result.get("selected_instruction_block"), dict)
        else None,
        "instruction_block_response_hint": result.get("selected_instruction_block", {}).get("response_hint")
        if isinstance(result.get("selected_instruction_block"), dict)
        else None,
        "instruction_resource_load_plan": result.get("instruction_resource_load_plan", [])
        if isinstance(result.get("instruction_resource_load_plan"), list)
        else [],
        "instruction_resource_context_summary": [
            {
                "filename": item.get("filename"),
                "load_strategy": item.get("load_strategy"),
                "source_kind": item.get("source_kind"),
                "section_titles": item.get("section_titles", []),
            }
            for item in result.get("instruction_resource_context", [])
            if isinstance(item, dict)
        ]
        if isinstance(result.get("instruction_resource_context"), list)
        else [],
        "instruction_module_title": result.get("instruction_module", {}).get("title")
        if isinstance(result.get("instruction_module"), dict)
        else None,
        "action_type": action_summary["action_type"],
        "primary_action_type": action_summary["primary_action_type"],
        "action_types": action_summary["action_types"],
        "action_count": action_summary["action_count"],
        "turn_intent": turn_execution_plan.get("turn_intent"),
        "is_generation_request": bool(response_style.get("is_generation_request")),
        "generation_subtype": response_style.get("generation_subtype"),
        "is_out_of_scope": bool(response_style.get("is_out_of_scope")),
        "retrieval_bypassed": bool(debug_trace.get("retrieval_bypassed")) if isinstance(debug_trace, dict) else False,
        "retrieval_bypass_reason": debug_trace.get("bypass_reason") if isinstance(debug_trace, dict) else None,
        "primary_scope": primary_scope,
        "primary_scope_id": primary_scope.get("scope_id"),
        "primary_scope_type": primary_scope.get("scope_type"),
        "active_step_scope": layered_scope_summary["active_step_scope"],
        "active_step_scope_id": layered_scope_summary["active_step_scope_id"],
        "primary_support_module_scope": layered_scope_summary["primary_support_module_scope"],
        "primary_support_module_scope_id": layered_scope_summary["primary_support_module_scope_id"],
        "secondary_scope_ids": [
            str(item.get("scope_id") or "").strip()
            for item in secondary_scopes
            if isinstance(item, dict) and str(item.get("scope_id") or "").strip()
        ],
        "request_provenance_summary": request_provenance_summary,
        "active_execution_mode": active_execution_mode,
        "active_bundled_step_ids": active_bundled_step_ids,
        "bundled_entry_step_id": bundled_entry_step_id,
        "bundled_execution_completed": bundled_execution_completed,
        "presentation_mode": presentation_policy.get("mode"),
        "answer_source": answer_generation_meta.get("source"),
        "answer_llm_error": answer_generation_meta.get("llm_error"),
        "turn_execution_plan": turn_execution_plan,
        "session_execution_state": session_execution_state,
        "active_binding_ids": session_execution_state.get("active_binding_ids", [])
        if isinstance(session_execution_state, dict)
        else [],
        "active_dependency_group_ids": session_execution_state.get("active_dependency_group_ids", [])
        if isinstance(session_execution_state, dict)
        else [],
        "active_artifact_roles": session_execution_state.get("active_artifact_roles", [])
        if isinstance(session_execution_state, dict)
        else [],
        "artifact_gate_status": session_execution_state.get("artifact_gate_status", {})
        if isinstance(session_execution_state, dict)
        else {},
        "output_artifact_targets": output_artifact_targets,
        "active_session_upload_ids": session_execution_state.get("active_session_upload_ids", [])
        if isinstance(session_execution_state, dict)
        else [],
        "selected_resources": selected_resource_summary["selected_resources"],
        "selected_resource_filenames": selected_resource_summary["selected_resource_filenames"],
        "selected_resource_kinds": selected_resource_summary["selected_resource_kinds"],
        "intermediate_output_count": len(result.get("intermediate_outputs", []))
        if isinstance(result.get("intermediate_outputs"), list)
        else 0,
        "assembly_state": assembly_state,
        "visible_output_count": len(visible_outputs),
        "visible_outputs": [
            {
                "output_id": item.get("output_id"),
                "output_type": item.get("output_type"),
                "visibility": item.get("visibility"),
                "has_content": bool(str(item.get("content") or "").strip()),
            }
            for item in visible_outputs
            if isinstance(item, dict)
        ],
        "hidden_output_count": len(hidden_outputs),
        "execution_artifact_count": len(execution_artifacts),
        "execution_artifacts": [
            {
                "artifact_id": item.get("artifact_id"),
                "artifact_type": item.get("artifact_type"),
                "source_action_id": item.get("source_action_id"),
            }
            for item in execution_artifacts
            if isinstance(item, dict)
        ],
        "tool_result_count": len(tool_results),
        "tool_results": [
            {
                "artifact_id": item.get("artifact_id"),
                "artifact_type": item.get("artifact_type"),
                "source_action_id": item.get("source_action_id"),
            }
            for item in tool_results
            if isinstance(item, dict)
        ],
        "workflow_progress": result.get("workflow_progress", {})
        if isinstance(result.get("workflow_progress"), dict)
        else {},
        "hybrid_planner_decision_packet": result.get("hybrid_planner_decision_packet", {})
        if isinstance(result.get("hybrid_planner_decision_packet"), dict)
        else {},
        "hybrid_planner_shadow_output": result.get("hybrid_planner_shadow_output", {})
        if isinstance(result.get("hybrid_planner_shadow_output"), dict)
        else {},
        "task_model_diagnostics": task_model_diagnostics,
    }


def _bundled_execution_summary(retrieval_summary: Dict[str, Any]) -> Dict[str, Any]:
    active_execution_mode = str(retrieval_summary.get("active_execution_mode") or "").strip() or None
    active_bundled_step_ids = [
        str(item).strip()
        for item in retrieval_summary.get("active_bundled_step_ids", []) or []
        if str(item).strip()
    ]
    bundled_entry_step_id = str(retrieval_summary.get("bundled_entry_step_id") or "").strip() or None
    active_step_scope = (
        retrieval_summary.get("active_step_scope", {})
        if isinstance(retrieval_summary.get("active_step_scope"), dict)
        else {}
    )
    return {
        "enabled": active_execution_mode == "bundled",
        "active_execution_mode": active_execution_mode,
        "active_bundled_step_ids": active_bundled_step_ids,
        "bundled_entry_step_id": bundled_entry_step_id,
        "bundled_execution_completed": bool(retrieval_summary.get("bundled_execution_completed")),
        "active_step_scope_id": str(retrieval_summary.get("active_step_scope_id") or "").strip() or None,
        "active_step_scope_title": str(active_step_scope.get("title") or "").strip() or None,
    }


def run_chat_pipeline(
    state: Dict[str, Any],
    *,
    session_repo: SessionRepo,
    chat_repo: ChatRepo,
    planner_repo: InMemoryPlannerRepo,
    retrieval_repo: RetrievalRepo,
    llm_planner: Optional[Callable[[str, list, Dict[str, Any]], Dict[str, Any]]] = None,
    llm_answer: Optional[Callable[[str, list, Dict[str, Any]], Dict[str, Any]]] = None,
    llm_evidence_analysis: Optional[Callable[[str, list, Dict[str, Any]], Dict[str, Any]]] = None,
    retrieve_fn: Optional[Callable[[str, int, dict], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run the LangGraph user-query pipeline and persist artifacts."""
    state = dict(state)
    state["_context_optimization_eligible"] = normal_query_optimization_eligible(state)
    state["_context_optimization_mode"] = context_optimization_mode()
    state["_context_optimization_diagnostics"] = {"calls": []}
    state["_turn_token_accounting"] = {"calls": [], "call_count": 0, "turn_estimated_outbound_tokens": 0}
    state["_session_repo"] = session_repo
    state["_chat_repo"] = chat_repo
    state["_planner_repo"] = planner_repo
    state["_retrieval_repo"] = retrieval_repo
    planner_binding = build_task_binding(state, "planner")
    planner_diag = dict(planner_binding.get("diagnostics", {}))
    if llm_planner is not None:
        planner_diag["selected_source"] = "override"
        planner_diag.pop("fallback_reason", None)
    state["_llm_planner"] = llm_planner or planner_binding.get("callable") or _default_llm_planner
    planner_mode = str(state.get("planner_mode") or "legacy").strip().lower()
    planner_hybrid_binding = build_task_binding(state, "planner_hybrid")
    planner_hybrid_diag = dict(planner_hybrid_binding.get("diagnostics", {}))
    if planner_mode not in {"hybrid_shadow", "hybrid_active"}:
        planner_hybrid_diag["selected_source"] = "disabled"
        planner_hybrid_diag.pop("fallback_reason", None)
    state["_llm_planner_hybrid"] = (
        planner_hybrid_binding.get("callable")
        if planner_mode in {"hybrid_shadow", "hybrid_active"}
        else None
    )
    answer_binding = build_task_binding(state, "answer_generation")
    answer_diag = dict(answer_binding.get("diagnostics", {}))
    if llm_answer is not None:
        answer_diag["selected_source"] = "override"
        answer_diag.pop("fallback_reason", None)
    state["_llm_answer"] = llm_answer or answer_binding.get("callable") or _default_llm_answer
    evidence_binding = build_task_binding(state, "evidence_analysis")
    evidence_diag = dict(evidence_binding.get("diagnostics", {}))
    if llm_evidence_analysis is not None:
        evidence_diag["selected_source"] = "override"
        evidence_diag.pop("fallback_reason", None)
    state["_llm_evidence_analysis"] = llm_evidence_analysis or evidence_binding.get("callable")
    state["_task_model_diagnostics"] = {
        "configured_task_models": configured_task_models(state),
        "selected_task_models": {
            "planner": planner_diag,
            "planner_hybrid": planner_hybrid_diag,
            "answer_generation": answer_diag,
            "evidence_analysis": evidence_diag,
        },
    }
    if retrieve_fn is not None:
        state["_retrieve_fn"] = retrieve_fn

    result = _graph().invoke(state)
    diagnostic_state = {**state, **result}
    task_model_diagnostics = finalize_task_model_diagnostics(diagnostic_state)
    result["task_model_diagnostics"] = task_model_diagnostics
    final_answer = result.get("final_answer")
    if not isinstance(final_answer, dict):
        raise RuntimeError("Pipeline did not produce final_answer.")
    retrieval_summary = _build_retrieval_summary(result, final_answer)
    response = dict(final_answer)
    response["retrieval_summary"] = retrieval_summary
    response["bundled_execution"] = _bundled_execution_summary(retrieval_summary)
    response["workflow_progress"] = result.get("workflow_progress", {})
    response["turn_execution_plan"] = retrieval_summary.get("turn_execution_plan", {})
    response["session_execution_state"] = retrieval_summary.get("session_execution_state", {})
    response["hybrid_planner_decision_packet"] = retrieval_summary.get("hybrid_planner_decision_packet", {})
    response["hybrid_planner_shadow_output"] = retrieval_summary.get("hybrid_planner_shadow_output", {})
    response["task_model_diagnostics"] = retrieval_summary.get("task_model_diagnostics", {})
    return response
