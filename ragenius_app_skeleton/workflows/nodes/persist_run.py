"""Persistence node.

Input contract:
- state includes planner/retrieval/answer artifacts

Output contract:
- state unchanged; side-effect persistence in real implementation
"""

from __future__ import annotations

import copy

from backend.app.llm_context_optimization import (
    build_or_refresh_chat_summary,
    finalize_task_model_diagnostics,
)

from ..graph_state import GraphState


def _append_unique(values: list[str], candidate: str | None) -> None:
    normalized = str(candidate or "").strip()
    if normalized and normalized not in values:
        values.append(normalized)


def _selected_resource_summary(state: GraphState) -> dict:
    turn_execution_plan = state.get("turn_execution_plan", {})
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
        collection = state.get(collection_key, [])
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


def _layered_scope_summary(session_execution_state: dict) -> dict:
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


def _summarize_execution_actions(turn_execution_plan: dict) -> dict:
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


def _respond_to_user_style(turn_execution_plan: dict) -> dict:
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


def _build_runtime_state(state: GraphState) -> dict:
    workflow_progress = state.get("workflow_progress", {})
    session_execution_state = state.get("session_execution_state", {})
    intermediate_outputs = state.get("intermediate_outputs", [])
    assembly_state = state.get("assembly_state", {})
    return {
        "workflow_progress": workflow_progress if isinstance(workflow_progress, dict) else {},
        "session_execution_state": session_execution_state if isinstance(session_execution_state, dict) else {},
        "intermediate_outputs": [item for item in intermediate_outputs if isinstance(item, dict)]
        if isinstance(intermediate_outputs, list)
        else [],
        "assembly_state": assembly_state if isinstance(assembly_state, dict) else {},
    }


def _build_retrieval_summary(state: GraphState, final: dict) -> dict:
    raw_evidence = state.get("raw_evidence", []) or []
    debug_trace = state.get("retrieval_debug_trace", {}) or {}
    citations = final.get("citations", []) if isinstance(final, dict) else []

    route = debug_trace.get("route", {}) if isinstance(debug_trace, dict) else {}
    domains = debug_trace.get("domains", {}) if isinstance(debug_trace, dict) else {}
    turn_execution_plan = state.get("turn_execution_plan", {}) if isinstance(state.get("turn_execution_plan"), dict) else {}
    session_execution_state = (
        state.get("session_execution_state", {})
        if isinstance(state.get("session_execution_state"), dict)
        else {}
    )
    workflow_progress = state.get("workflow_progress", {}) if isinstance(state.get("workflow_progress"), dict) else {}
    answer_generation_meta = (
        state.get("answer_generation_meta", {})
        if isinstance(state.get("answer_generation_meta"), dict)
        else {}
    )
    presentation_policy = state.get("presentation_policy", {}) if isinstance(state.get("presentation_policy"), dict) else {}
    visible_outputs = state.get("visible_outputs", []) if isinstance(state.get("visible_outputs"), list) else []
    hidden_outputs = state.get("hidden_outputs", []) if isinstance(state.get("hidden_outputs"), list) else []
    execution_artifacts = state.get("execution_artifacts", []) if isinstance(state.get("execution_artifacts"), list) else []
    tool_results = state.get("tool_results", []) if isinstance(state.get("tool_results"), list) else []
    selected_resource_summary = _selected_resource_summary(state)
    assembly_state = state.get("assembly_state", {}) if isinstance(state.get("assembly_state"), dict) else {}
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
    source_keys = []
    instruction_count = 0
    knowledge_count = 0
    template_count = 0
    session_upload_count = 0
    instruction_titles = []
    knowledge_titles = []
    template_titles = []
    session_upload_titles = []
    seen_instruction_titles = set()
    seen_knowledge_titles = set()
    seen_template_titles = set()
    seen_session_upload_titles = set()
    for item in raw_evidence:
        if not isinstance(item, dict):
            continue
        source_keys.append(item.get("doc_id") or item.get("title") or "unknown")
        title = str(item.get("title") or item.get("doc_id") or "Document")
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
    top_titles = []
    seen_titles = set()
    for item in raw_evidence:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("doc_id") or "Document")
        if title not in seen_titles:
            seen_titles.add(title)
            top_titles.append(title)
        if len(top_titles) >= 3:
            break

    return {
        "retrieved_count": len(raw_evidence),
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
        "instruction_resource": state.get("instruction_resource"),
        "instruction_block_title": state.get("selected_instruction_block", {}).get("title")
        if isinstance(state.get("selected_instruction_block"), dict)
        else None,
        "instruction_block_type": state.get("selected_instruction_block", {}).get("block_type")
        if isinstance(state.get("selected_instruction_block"), dict)
        else None,
        "instruction_block_response_hint": state.get("selected_instruction_block", {}).get("response_hint")
        if isinstance(state.get("selected_instruction_block"), dict)
        else None,
        "instruction_resource_load_plan": state.get("instruction_resource_load_plan", [])
        if isinstance(state.get("instruction_resource_load_plan"), list)
        else [],
        "instruction_resource_context_summary": [
            {
                "filename": item.get("filename"),
                "load_strategy": item.get("load_strategy"),
                "source_kind": item.get("source_kind"),
                "section_titles": item.get("section_titles", []),
            }
            for item in state.get("instruction_resource_context", [])
            if isinstance(item, dict)
        ]
        if isinstance(state.get("instruction_resource_context"), list)
        else [],
        "instruction_module_title": state.get("instruction_module", {}).get("title")
        if isinstance(state.get("instruction_module"), dict)
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
        "presentation_mode": presentation_policy.get("mode"),
        "answer_source": answer_generation_meta.get("source"),
        "answer_llm_error": answer_generation_meta.get("llm_error"),
        "task_model_diagnostics": finalize_task_model_diagnostics(state),
        "turn_execution_plan": turn_execution_plan,
        "workflow_progress": workflow_progress,
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
        "intermediate_output_count": len(state.get("intermediate_outputs", []))
        if isinstance(state.get("intermediate_outputs"), list)
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
    }


def run(state: GraphState) -> GraphState:
    """Persist planner/retrieval/chat artifacts when repo deps are provided."""
    planner_repo = state.get("_planner_repo")
    retrieval_repo = state.get("_retrieval_repo")
    chat_repo = state.get("_chat_repo")
    session_repo = state.get("_session_repo")
    turn_input_type = str(state.get("turn_input_type") or "").strip().lower()

    prior_history = state.get("chat_history", []) if isinstance(state.get("chat_history"), list) else []
    final_for_summary = state.get("final_answer", {}) if isinstance(state.get("final_answer"), dict) else {}
    if turn_input_type == "text_query" and len(prior_history) + 2 > 8 and final_for_summary:
        session_execution_state = copy.deepcopy(state.get("session_execution_state")) if isinstance(state.get("session_execution_state"), dict) else {}
        session_execution_state["chat_summary"] = build_or_refresh_chat_summary(
            existing_summary=session_execution_state.get("chat_summary") if isinstance(session_execution_state.get("chat_summary"), dict) else None,
            prior_history=prior_history,
            current_user_message=str(state.get("user_query") or ""),
            current_answer=final_for_summary,
            session_execution_state=session_execution_state,
        )
        state["session_execution_state"] = session_execution_state

    planner_row = None
    if planner_repo is not None and state.get("session_id") and state.get("user_query") and state.get("planner_output"):
        planner_row = planner_repo.save(state["session_id"], state["user_query"], state["planner_output"])

    if retrieval_repo is not None and planner_row is not None:
        retrieval_repo.save(
            planner_row["id"],
            state.get("retrieval_plan", {}),
            len(state.get("raw_evidence", [])),
            state.get("retrieval_debug_trace"),
        )

    if chat_repo is not None and state.get("session_id"):
        if state.get("user_query") and turn_input_type != "session_upload":
            attached_artifact_refs = [
                ref
                for ref in (state.get("attached_artifact_refs") or [])
                if isinstance(ref, dict) and str(ref.get("artifact_id") or "").strip()
            ]
            chat_repo.append(
                state["session_id"],
                "user",
                state["user_query"],
                retrieval_summary=(
                    {"attached_artifact_refs": attached_artifact_refs}
                    if attached_artifact_refs
                    else None
                ),
            )
        final = state.get("final_answer", {})
        if isinstance(final, dict):
            chat_repo.append(
                state["session_id"],
                "assistant",
                str(final.get("content", "")),
                citations=final.get("citations", []),
                missing_info_types=final.get("missing_infoTypes", []),
                retrieval_summary=_build_retrieval_summary(state, final),
            )

    if session_repo is not None and state.get("session_id"):
        runtime_state = _build_runtime_state(state)
        if hasattr(session_repo, "set_runtime_state"):
            session_repo.set_runtime_state(state["session_id"], runtime_state)
        else:
            workflow_progress = runtime_state.get("workflow_progress", {})
            if isinstance(workflow_progress, dict) and workflow_progress:
                session_repo.set_workflow_progress(state["session_id"], workflow_progress)
    return state
