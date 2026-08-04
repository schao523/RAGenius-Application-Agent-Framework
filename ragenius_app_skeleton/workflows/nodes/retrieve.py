"""Node F: rag_retrieve.

Calls rag_subsystem.retrieve_data using retrieval_plan fields only.
Stores raw results and debug trace in graph state.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
import re
from typing import Callable, Dict, List, Optional, Tuple

from ..graph_state import GraphState


def _default_retrieve(query_text: str, top_k: int, filters: dict) -> Dict:
    try:
        from rag_subsystem import retrieve_data  # type: ignore
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError("rag_subsystem.retrieve_data is required for retrieval.") from exc
    return retrieve_data(query_text=query_text, top_k=top_k, filters=filters)


def _candidate_to_evidence(candidate) -> Dict:
    """Normalize rag_subsystem RetrievalCandidate into evidence dict."""
    chunk = getattr(candidate, "chunk", None)
    if chunk is None and isinstance(candidate, dict):
        chunk = candidate.get("chunk")

    if chunk is None:
        return {}

    if is_dataclass(chunk):
        chunk_obj = asdict(chunk)
    elif isinstance(chunk, dict):
        chunk_obj = chunk
    else:
        chunk_obj = {
            "doc_id": getattr(chunk, "doc_id", None),
            "text": getattr(chunk, "text", ""),
            "metadata": getattr(chunk, "metadata", {}) or {},
            "chunk_id": getattr(chunk, "chunk_id", None),
        }

    score = getattr(candidate, "score", None)
    if score is None and isinstance(candidate, dict):
        score = candidate.get("score")

    metadata = chunk_obj.get("metadata", {}) or {}
    return {
        "doc_id": chunk_obj.get("doc_id"),
        "title": metadata.get("title") or chunk_obj.get("doc_id") or "Document",
        "snippet": chunk_obj.get("text", ""),
        "score": float(score or 0.0),
        "metadata": metadata,
        "version": metadata.get("version"),
        "location": chunk_obj.get("section_path"),
        "chunk_id": chunk_obj.get("chunk_id"),
    }


def _normalize_result(result) -> tuple[list, dict | None]:
    """Support both dict result shape and dataclass RetrievalResult shape."""
    if isinstance(result, dict):
        return result.get("results", []), result.get("debug_trace") or result.get("debug")

    # rag_subsystem RetrievalResult dataclass/object
    results = getattr(result, "results", None)
    debug = getattr(result, "debug", None)
    if results is None:
        raise ValueError("retrieve_fn returned unsupported result shape.")
    normalized = []
    for item in results:
        ev = _candidate_to_evidence(item)
        if ev:
            normalized.append(ev)
    return normalized, debug


def _plan_filters(plan: dict) -> dict:
    filters = plan.get("filters", {}) if isinstance(plan, dict) else {}
    return dict(filters or {}) if isinstance(filters, dict) else {}


def _merge_filename_filter(filters: dict, filenames: List[str]) -> dict:
    merged = dict(filters)
    cleaned = list(
        dict.fromkeys(str(name or "").strip() for name in filenames if str(name or "").strip())
    )
    if not cleaned:
        return merged
    if len(cleaned) == 1:
        merged["filename"] = cleaned[0]
        return merged
    merged.pop("filename", None)
    merged["filename_in"] = cleaned
    return merged


def _legacy_instruction_filenames(state: GraphState) -> List[str]:
    resource_filters = state.get("instruction_resource_filters", {})
    if not isinstance(resource_filters, dict):
        return []
    filename = resource_filters.get("filename")
    if isinstance(filename, str) and filename.strip():
        return [filename.strip()]
    filename_in = resource_filters.get("filename_in")
    if isinstance(filename_in, list):
        return [str(item).strip() for item in filename_in if str(item).strip()]
    return []


def _resource_requests_from_plan(state: GraphState) -> list[dict]:
    plan = state.get("turn_execution_plan", {})
    if not isinstance(plan, dict):
        return []
    requests = plan.get("resource_requests", [])
    if not isinstance(requests, list):
        return []
    return [item for item in requests if isinstance(item, dict)]


def _resource_requests_for_role(state: GraphState, resource_role: str) -> list[dict]:
    return [
        item
        for item in _resource_requests_from_plan(state)
        if str(item.get("resource_role") or "").strip() == resource_role
    ]


def _session_execution_state(state: GraphState) -> dict:
    session_state = state.get("session_execution_state", {})
    return session_state if isinstance(session_state, dict) else {}


def _active_binding_ids(state: GraphState) -> list[str]:
    session_state = _session_execution_state(state)
    binding_ids = session_state.get("active_binding_ids", [])
    if not isinstance(binding_ids, list):
        return []
    return [str(item).strip() for item in binding_ids if str(item).strip()]


def _initial_artifact_gate_status(state: GraphState) -> dict:
    session_state = _session_execution_state(state)
    status = session_state.get("artifact_gate_status", {})
    return dict(status) if isinstance(status, dict) else {}


def _request_match_score(item: dict, query_text: str, available_filenames: set[str]) -> int:
    score = 0
    filename = Path(str(item.get("filename") or "").strip()).name
    if filename and filename.lower() in available_filenames:
        score += 10
    haystack = " ".join(
        [
            filename,
            str(item.get("query_text") or ""),
            str(item.get("objective") or ""),
            str(item.get("request_reason") or ""),
            str(item.get("purpose") or ""),
        ]
    ).lower()
    for token in _tokenize(query_text):
        if token in haystack:
            score += 1
    if str(item.get("resource_kind") or "").strip():
        score += 1
    return score


def _resolved_resource_requests_for_role(state: GraphState, resource_role: str) -> list[dict]:
    requests = _resource_requests_for_role(state, resource_role)
    active_binding_ids = set(_active_binding_ids(state))
    if active_binding_ids:
        filtered_requests: list[dict] = []
        for item in requests:
            binding_id = str(item.get("binding_id") or "").strip()
            if binding_id and binding_id not in active_binding_ids:
                continue
            filtered_requests.append(item)
        requests = filtered_requests
    if len(requests) <= 1:
        return requests

    document_map = _builder_document_map(state)
    available_filenames = set(document_map.keys())
    query_text = str(state.get("user_query") or state.get("retrieval_plan", {}).get("query_text") or "").strip()
    resolved: list[dict] = []
    grouped: dict[str, list[dict]] = {}

    for item in requests:
        binding_id = str(item.get("binding_id") or "").strip()
        if not binding_id:
            resolved.append(item)
            continue
        grouped.setdefault(binding_id, []).append(item)

    for binding_id, items in grouped.items():
        if len(items) == 1:
            resolved.extend(items)
            continue
        if any(str(item.get("dependency_group_id") or "").strip() for item in items):
            resolved.extend(items)
            continue
        ranked = sorted(
            enumerate(items),
            key=lambda pair: (
                -_request_match_score(pair[1], query_text, available_filenames),
                len(Path(str(pair[1].get("filename") or "").strip()).name),
                pair[0],
            ),
        )
        resolved.append(ranked[0][1])

    return resolved


def _resolved_resource_requests(state: GraphState) -> list[dict]:
    requests = _resource_requests_from_plan(state)
    if not requests:
        return []

    active_binding_ids = set(_active_binding_ids(state))
    ordered_resolved: list[dict] = []
    seen: set[int] = set()
    resource_roles = list(
        dict.fromkeys(
            str(item.get("resource_role") or "").strip()
            for item in requests
            if str(item.get("resource_role") or "").strip()
        )
    )

    for resource_role in resource_roles:
        for item in _resolved_resource_requests_for_role(state, resource_role):
            item_id = id(item)
            if item_id in seen:
                continue
            seen.add(item_id)
            ordered_resolved.append(item)

    for item in requests:
        if id(item) in seen:
            continue
        if str(item.get("resource_role") or "").strip():
            continue
        binding_id = str(item.get("binding_id") or "").strip()
        if active_binding_ids and binding_id and binding_id not in active_binding_ids:
            continue
        seen.add(id(item))
        ordered_resolved.append(item)

    return ordered_resolved


def _artifact_gate_status(state: GraphState) -> tuple[dict, Optional[str]]:
    status = _initial_artifact_gate_status(state)
    uploads = state.get("session_uploads", [])
    upload_ids = set()
    upload_names = set()
    upload_roles = set()
    if isinstance(uploads, list):
        for upload in uploads:
            if not isinstance(upload, dict):
                continue
            upload_id = str(upload.get("id") or "").strip()
            if upload_id:
                upload_ids.add(upload_id)
            filename = Path(str(upload.get("filename") or "").strip()).name.lower()
            if filename:
                upload_names.add(filename)
            artifact_role = str(upload.get("artifact_role") or "").strip()
            if artifact_role:
                upload_roles.add(artifact_role)

    blocked = False
    for item in _resolved_resource_requests(state):
        if not bool(item.get("required_for_progression")):
            continue
        artifact_role = str(item.get("artifact_role") or "").strip() or Path(str(item.get("filename") or "").strip()).stem
        resource_id = str(item.get("resource_id") or "").strip()
        filename = Path(str(item.get("filename") or "").strip()).name.lower()
        present = False
        if resource_id and resource_id in upload_ids:
            present = True
        elif filename and filename in upload_names:
            present = True
        elif artifact_role and artifact_role in upload_roles:
            present = True
        status[artifact_role] = {
            "status": "ready" if present else "blocked",
            "reason": None if present else "missing_required_artifact",
            "binding_id": str(item.get("binding_id") or "").strip() or None,
            "required_for_progression": True,
            "filename": Path(str(item.get("filename") or "").strip()).name or None,
        }
        if not present:
            blocked = True
    return status, "missing_required_artifact" if blocked else None


def _action_params_from_execution_plan(state: GraphState, action_type: str) -> list[dict]:
    plan = state.get("turn_execution_plan", {})
    if not isinstance(plan, dict):
        return []
    actions = plan.get("actions", [])
    if not isinstance(actions, list):
        return []
    params_list: list[dict] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        if str(action.get("action_type") or "").strip() != action_type:
            continue
        params = action.get("params", {})
        if isinstance(params, dict):
            params_list.append(params)
    return params_list


def _load_plan_from_resource_requests(
    resource_requests: list[dict],
    *,
    resource_role: str,
) -> list[dict]:
    load_plan: list[dict] = []
    seen: dict[tuple[str, str, str], dict] = {}
    for item in resource_requests:
        if str(item.get("resource_role") or "").strip() != resource_role:
            continue
        filename = Path(str(item.get("filename") or "").strip()).name
        resource_id = str(item.get("resource_id") or "").strip() or None
        if not filename and not resource_id:
            continue
        load_strategy = str(item.get("load_strategy_hint") or "").strip() or (
            "vector_retrieve" if resource_role == "knowledge_source" else "inline_full"
        )
        key = (filename.lower(), resource_id or "", load_strategy.lower())
        step_scope_id = str(item.get("step_scope_id") or "").strip() or None
        if key in seen:
            existing = seen[key]
            bundled_step_scope_ids = existing.setdefault("bundled_step_scope_ids", [])
            if step_scope_id and step_scope_id not in bundled_step_scope_ids:
                bundled_step_scope_ids.append(step_scope_id)
            continue
        entry = {
            "filename": filename or None,
            "resource_id": resource_id,
            "resource_role": resource_role,
            "load_strategy": load_strategy,
            "binding_id": str(item.get("binding_id") or "").strip() or None,
            "dependency_group_id": str(item.get("dependency_group_id") or "").strip() or None,
            "resource_kind": str(item.get("resource_kind") or "").strip() or None,
            "artifact_role": str(item.get("artifact_role") or "").strip() or None,
            "required_for_progression": bool(item.get("required_for_progression")),
            "source_layer": str(item.get("source_layer") or "").strip() or None,
            "step_scope_id": step_scope_id,
            "support_module_id": str(item.get("support_module_id") or "").strip() or None,
            "bundled_step_scope_ids": [step_scope_id] if step_scope_id else [],
        }
        seen[key] = entry
        load_plan.append(entry)
    return load_plan


def _session_upload_ids_from_plan(state: GraphState) -> list[str]:
    ids: list[str] = []
    for item in _resource_requests_from_plan(state):
        if str(item.get("purpose") or "").strip() != "session_upload":
            continue
        resource_id = str(item.get("resource_id") or "").strip()
        if resource_id:
            ids.append(resource_id)
    return list(dict.fromkeys(ids))


def _dedupe_queries(queries: List[str]) -> List[str]:
    cleaned: List[str] = []
    seen: set[str] = set()
    for query in queries:
        text = " ".join(str(query or "").split()).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _builder_documents(state: GraphState) -> list[dict]:
    registry = state.get("template_registry", {}) or {}
    documents = registry.get("builder_documents", [])
    if not isinstance(documents, list):
        return []
    return [item for item in documents if isinstance(item, dict)]


def _builder_document_map(state: GraphState) -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    for document in _builder_documents(state):
        filename = Path(str(document.get("filename") or "").strip()).name.lower()
        if filename:
            mapping[filename] = document
    return mapping


def _read_builder_document_text(document: dict) -> str:
    file_path = str(document.get("file_path") or "").strip()
    if not file_path:
        return ""
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _sectionize_markdown(text: str) -> list[dict]:
    content = str(text or "")
    if not content.strip():
        return []
    sections: list[dict] = []
    current_title = ""
    current_lines: list[str] = []
    for raw_line in content.splitlines():
        line = str(raw_line or "")
        stripped = line.strip()
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            if current_lines:
                sections.append({"title": current_title, "text": "\n".join(current_lines).strip()})
            current_title = heading_match.group(2).strip()
            current_lines = []
            continue
        current_lines.append(line)
    if current_lines:
        sections.append({"title": current_title, "text": "\n".join(current_lines).strip()})
    return [section for section in sections if str(section.get("text") or "").strip()]


def _tokenize(text: str) -> list[str]:
    tokens = []
    for part in re.split(r"[^\w\u4e00-\u9fff]+", str(text or "").lower()):
        token = part.strip()
        if len(token) >= 2:
            tokens.append(token)
    return tokens


def _section_filter_text(text: str, context_parts: list[str]) -> tuple[str, list[str]]:
    sections = _sectionize_markdown(text)
    if not sections:
        return text, []
    context_tokens = list(dict.fromkeys(token for part in context_parts for token in _tokenize(part)))
    if not context_tokens:
        top_sections = sections[:2]
        titles = [str(section.get("title") or "").strip() for section in top_sections if str(section.get("title") or "").strip()]
        return "\n\n".join(str(section.get("text") or "") for section in top_sections).strip(), titles

    scored: list[tuple[int, int, dict]] = []
    for index, section in enumerate(sections):
        haystack = f"{section.get('title') or ''}\n{section.get('text') or ''}".lower()
        score = sum(1 for token in context_tokens if token in haystack)
        if score > 0:
            scored.append((score, -index, section))
    if not scored:
        top_sections = sections[:2]
    else:
        top_sections = [item[2] for item in sorted(scored, reverse=True)[:2]]
    titles = [str(section.get("title") or "").strip() for section in top_sections if str(section.get("title") or "").strip()]
    return "\n\n".join(str(section.get("text") or "") for section in top_sections).strip(), titles


def _instruction_context_parts(state: GraphState) -> list[str]:
    parts = [
        str(state.get("user_query") or "").strip(),
        str(state.get("selected_instruction_block_text") or "").strip(),
    ]
    selected_block = state.get("selected_instruction_block", {})
    if isinstance(selected_block, dict):
        parts.extend(
            [
                str(selected_block.get("title") or "").strip(),
                str(selected_block.get("objective") or "").strip(),
                str(selected_block.get("operation_text") or "").strip(),
            ]
        )
    return [part for part in parts if part]


def _effective_instruction_load_plan(state: GraphState) -> list[dict]:
    load_plan = state.get("instruction_resource_load_plan", [])
    if isinstance(load_plan, list) and load_plan:
        return [item for item in load_plan if isinstance(item, dict)]
    return _load_plan_from_resource_requests(
        _resolved_resource_requests_for_role(state, "instruction_source"),
        resource_role="instruction_source",
    )


def _direct_resource_evidence(
    state: GraphState,
    *,
    load_plan_key: str,
    retrieval_domain: str,
    source_label: str,
    context_parts: list[str],
) -> tuple[list, dict | None, list[dict]]:
    load_plan = state.get(load_plan_key, [])
    if load_plan_key == "instruction_resource_load_plan":
        load_plan = _effective_instruction_load_plan(state)
    elif load_plan_key == "template_resource_load_plan":
        if not isinstance(load_plan, list) or not load_plan:
            load_plan = _load_plan_from_resource_requests(
                _resolved_resource_requests_for_role(state, "output_template"),
                resource_role="output_template",
            )
    if not isinstance(load_plan, list) or not load_plan:
        return [], None, []
    document_map = _builder_document_map(state)
    evidence: list = []
    loaded_resources: list[dict] = []
    resource_context: list[dict] = []

    for entry in load_plan:
        if not isinstance(entry, dict):
            continue
        strategy = str(entry.get("load_strategy") or "").strip()
        if strategy == "vector_retrieve":
            continue
        filename = Path(str(entry.get("filename") or "").strip()).name
        if not filename:
            continue
        document = document_map.get(filename.lower())
        if not isinstance(document, dict):
            continue
        full_text = _read_builder_document_text(document)
        if not full_text.strip():
            continue
        used_titles: list[str] = []
        snippet = full_text
        if strategy == "section_filter":
            snippet, used_titles = _section_filter_text(full_text, context_parts)
        evidence.append(
            {
                "doc_id": str(entry.get("document_id") or document.get("id") or filename),
                "title": filename,
                "snippet": snippet.strip() or full_text.strip(),
                "score": 1.0,
                "metadata": {
                    "title": filename,
                    "source": source_label,
                    "resource_role": entry.get("resource_role"),
                    "load_strategy": strategy,
                    "document_id": document.get("id"),
                    "section_titles": used_titles,
                    "binding_id": entry.get("binding_id"),
                    "dependency_group_id": entry.get("dependency_group_id"),
                    "resource_kind": entry.get("resource_kind"),
                    "artifact_role": entry.get("artifact_role"),
                    "required_for_progression": bool(entry.get("required_for_progression")),
                    "source_layer": entry.get("source_layer"),
                    "step_scope_id": entry.get("step_scope_id"),
                    "support_module_id": entry.get("support_module_id"),
                    "bundled_step_scope_ids": entry.get("bundled_step_scope_ids", []),
                },
                "version": None,
                "location": document.get("file_path"),
                "chunk_id": f"instruction:{filename}",
                "retrieval_domain": retrieval_domain,
                "retrieval_query": str(state.get("user_query") or ""),
                "retrieval_attempt": 0,
            }
        )
        loaded_resources.append(
            {
                "filename": filename,
                "load_strategy": strategy,
                "document_id": document.get("id"),
                "section_titles": used_titles,
                "binding_id": entry.get("binding_id"),
                "dependency_group_id": entry.get("dependency_group_id"),
                "resource_kind": entry.get("resource_kind"),
                "source_layer": entry.get("source_layer"),
                "step_scope_id": entry.get("step_scope_id"),
                "support_module_id": entry.get("support_module_id"),
                "bundled_step_scope_ids": entry.get("bundled_step_scope_ids", []),
            }
        )
        resource_context.append(
            {
                "filename": filename,
                "document_id": document.get("id"),
                "resource_role": entry.get("resource_role"),
                "load_strategy": strategy,
                "section_titles": used_titles,
                "content": (snippet.strip() or full_text.strip())[:12000],
                "source_kind": "builder_direct_load",
                "binding_id": entry.get("binding_id"),
                "dependency_group_id": entry.get("dependency_group_id"),
                "resource_kind": entry.get("resource_kind"),
                "artifact_role": entry.get("artifact_role"),
                "required_for_progression": bool(entry.get("required_for_progression")),
                "source_layer": entry.get("source_layer"),
                "step_scope_id": entry.get("step_scope_id"),
                "support_module_id": entry.get("support_module_id"),
                "bundled_step_scope_ids": entry.get("bundled_step_scope_ids", []),
            }
        )
    if not evidence:
        return [], None, resource_context
    return evidence, {
        "route": {"model": "direct_load", "namespace": "builder_documents", "language": None},
        "executed_queries": [item.get("filename") for item in loaded_resources],
        "attempt_count": len(loaded_resources),
        "weak_retry_triggered": False,
        "loaded_resources": loaded_resources,
    }, resource_context


def _direct_instruction_resource_evidence(state: GraphState) -> tuple[list, dict | None, list[dict]]:
    return _direct_resource_evidence(
        state,
        load_plan_key="instruction_resource_load_plan",
        retrieval_domain="instruction_source",
        source_label="instruction_resource",
        context_parts=_instruction_context_parts(state),
    )


def _template_context_parts(state: GraphState) -> list[str]:
    parts = [
        str(state.get("user_query") or "").strip(),
        str(state.get("selected_instruction_block_text") or "").strip(),
    ]
    selected_block = state.get("selected_instruction_block", {})
    if isinstance(selected_block, dict):
        parts.extend(
            [
                str(selected_block.get("title") or "").strip(),
                str(selected_block.get("objective") or "").strip(),
                str(selected_block.get("operation_text") or "").strip(),
            ]
        )
    return [part for part in parts if part]


def _direct_template_resource_evidence(state: GraphState) -> tuple[list, dict | None, list[dict]]:
    return _direct_resource_evidence(
        state,
        load_plan_key="template_resource_load_plan",
        retrieval_domain="output_template",
        source_label="template_resource",
        context_parts=_template_context_parts(state),
    )


def _instruction_resource_context_from_evidence(raw_evidence: list, existing: list[dict] | None = None) -> list[dict]:
    context: list[dict] = list(existing or [])
    seen = {
        (
            str(item.get("filename") or "").lower(),
            str(item.get("load_strategy") or "").lower(),
            str(item.get("source_kind") or "").lower(),
        )
        for item in context
        if isinstance(item, dict)
    }
    for item in raw_evidence:
        if not isinstance(item, dict):
            continue
        if str(item.get("retrieval_domain") or "").strip() != "instruction_source":
            continue
        metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
        filename = str(item.get("title") or metadata.get("title") or "").strip()
        if not filename:
            continue
        load_strategy = str(metadata.get("load_strategy") or "vector_retrieve").strip()
        source_kind = "builder_direct_load" if load_strategy in {"inline_full", "section_filter"} else "retrieved_instruction_chunk"
        key = (filename.lower(), load_strategy.lower(), source_kind.lower())
        if key in seen:
            continue
        seen.add(key)
        context.append(
            {
                "filename": filename,
                "document_id": metadata.get("document_id"),
                "resource_role": metadata.get("resource_role"),
                "load_strategy": load_strategy,
                "section_titles": metadata.get("section_titles", []) if isinstance(metadata.get("section_titles"), list) else [],
                "content": str(item.get("snippet") or "").strip(),
                "source_kind": source_kind,
                "binding_id": metadata.get("binding_id"),
                "dependency_group_id": metadata.get("dependency_group_id"),
                "resource_kind": metadata.get("resource_kind"),
                "artifact_role": metadata.get("artifact_role"),
                "required_for_progression": bool(metadata.get("required_for_progression")),
                "source_layer": metadata.get("source_layer"),
                "step_scope_id": metadata.get("step_scope_id"),
                "support_module_id": metadata.get("support_module_id"),
                "bundled_step_scope_ids": metadata.get("bundled_step_scope_ids", [])
                if isinstance(metadata.get("bundled_step_scope_ids"), list)
                else [],
            }
        )
    return context


def _template_resource_context_from_evidence(raw_evidence: list, existing: list[dict] | None = None) -> list[dict]:
    context: list[dict] = list(existing or [])
    seen = {
        (
            str(item.get("filename") or "").lower(),
            str(item.get("load_strategy") or "").lower(),
            str(item.get("source_kind") or "").lower(),
        )
        for item in context
        if isinstance(item, dict)
    }
    for item in raw_evidence:
        if not isinstance(item, dict):
            continue
        if str(item.get("retrieval_domain") or "").strip() != "output_template":
            continue
        metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
        filename = str(item.get("title") or metadata.get("title") or "").strip()
        if not filename:
            continue
        load_strategy = str(metadata.get("load_strategy") or "vector_retrieve").strip()
        source_kind = "builder_direct_load" if load_strategy in {"inline_full", "section_filter"} else "retrieved_template_chunk"
        key = (filename.lower(), load_strategy.lower(), source_kind.lower())
        if key in seen:
            continue
        seen.add(key)
        context.append(
            {
                "filename": filename,
                "document_id": metadata.get("document_id"),
                "resource_role": metadata.get("resource_role"),
                "load_strategy": load_strategy,
                "section_titles": metadata.get("section_titles", []) if isinstance(metadata.get("section_titles"), list) else [],
                "content": str(item.get("snippet") or "").strip(),
                "source_kind": source_kind,
                "binding_id": metadata.get("binding_id"),
                "dependency_group_id": metadata.get("dependency_group_id"),
                "resource_kind": metadata.get("resource_kind"),
                "artifact_role": metadata.get("artifact_role"),
                "required_for_progression": bool(metadata.get("required_for_progression")),
                "source_layer": metadata.get("source_layer"),
                "step_scope_id": metadata.get("step_scope_id"),
                "support_module_id": metadata.get("support_module_id"),
                "bundled_step_scope_ids": metadata.get("bundled_step_scope_ids", [])
                if isinstance(metadata.get("bundled_step_scope_ids"), list)
                else [],
            }
        )
    return context


def _debug_resource_requests_for_domain(state: GraphState, retrieval_domain: str) -> list[dict]:
    role_map = {
        "instruction_source": "instruction_source",
        "knowledge_source": "knowledge_source",
        "output_template": "output_template",
    }
    resource_role = role_map.get(str(retrieval_domain or "").strip())
    if not resource_role:
        return []
    requests = _resolved_resource_requests_for_role(state, resource_role)
    return [dict(item) for item in requests if isinstance(item, dict)]


def _domain_calls(state: GraphState) -> List[Tuple[str, str, int, dict, List[str], bool]]:
    if "retrieval_plan" not in state:
        raise ValueError("retrieval_plan is required for retrieve node.")

    plan = state["retrieval_plan"]
    top_k = plan.get("top_k")
    if top_k is None:
        raise ValueError("retrieval_plan must include top_k.")

    execution_plan_calls = _domain_calls_from_execution_plan(state)
    if execution_plan_calls:
        return execution_plan_calls

    calls: List[Tuple[str, str, int, dict]] = []
    turn_action_plan = state.get("turn_action_plan", {}) or {}
    instruction_plan = turn_action_plan.get("instruction_retrieval", {}) if isinstance(turn_action_plan, dict) else {}
    knowledge_plan = turn_action_plan.get("knowledge_retrieval", {}) if isinstance(turn_action_plan, dict) else {}
    template_plan = turn_action_plan.get("template_retrieval", {}) if isinstance(turn_action_plan, dict) else {}

    if isinstance(instruction_plan, dict) and instruction_plan.get("enabled"):
        query_text = str(instruction_plan.get("query_text") or state.get("user_query") or "").strip()
        if query_text:
            calls.append(
                (
                    "instruction_source",
                    query_text,
                    int(top_k),
                    _merge_filename_filter(
                        _plan_filters(plan),
                        instruction_plan.get("filename_filters", []) if isinstance(instruction_plan.get("filename_filters"), list) else [],
                    ),
                    _dedupe_queries(instruction_plan.get("query_variants", []) if isinstance(instruction_plan.get("query_variants"), list) else [])
                    + _dedupe_queries(instruction_plan.get("context_hints", []) if isinstance(instruction_plan.get("context_hints"), list) else [])
                    + _dedupe_queries(instruction_plan.get("fallback_queries", []) if isinstance(instruction_plan.get("fallback_queries"), list) else []),
                    bool(instruction_plan.get("retry_on_weak_results")),
                )
            )

    if isinstance(knowledge_plan, dict) and knowledge_plan.get("enabled"):
        query_text = str(knowledge_plan.get("query_text") or plan.get("query_text") or "").strip()
        if query_text:
            calls.append(
                (
                    "knowledge_source",
                    query_text,
                    int(top_k),
                    _merge_filename_filter(
                        _plan_filters(plan),
                        knowledge_plan.get("filename_filters", []) if isinstance(knowledge_plan.get("filename_filters"), list) else [],
                    ),
                    _dedupe_queries(knowledge_plan.get("query_variants", []) if isinstance(knowledge_plan.get("query_variants"), list) else [])
                    + _dedupe_queries(knowledge_plan.get("fallback_queries", []) if isinstance(knowledge_plan.get("fallback_queries"), list) else []),
                    bool(knowledge_plan.get("retry_on_weak_results")),
                )
            )

    if isinstance(template_plan, dict) and template_plan.get("enabled"):
        query_text = str(template_plan.get("query_text") or state.get("user_query") or "").strip()
        if query_text:
            calls.append(
                (
                    "output_template",
                    query_text,
                    int(top_k),
                    _merge_filename_filter(
                        _plan_filters(plan),
                        template_plan.get("filename_filters", []) if isinstance(template_plan.get("filename_filters"), list) else [],
                    ),
                    _dedupe_queries(template_plan.get("query_variants", []) if isinstance(template_plan.get("query_variants"), list) else [])
                    + _dedupe_queries(template_plan.get("context_hints", []) if isinstance(template_plan.get("context_hints"), list) else [])
                    + _dedupe_queries(template_plan.get("fallback_queries", []) if isinstance(template_plan.get("fallback_queries"), list) else []),
                    bool(template_plan.get("retry_on_weak_results")),
                )
            )

    if calls:
        return calls

    query_text = str(plan.get("query_text") or "").strip()
    if not query_text:
        raise ValueError("retrieval_plan must include query_text and top_k.")
    filters = _plan_filters(plan)
    legacy_filenames = _legacy_instruction_filenames(state)
    filters = _merge_filename_filter(filters, legacy_filenames)
    return [("knowledge_source", query_text, int(top_k), filters, [], False)]


def _vector_retrieval_requests(state: GraphState, resource_role: str) -> list[dict]:
    return [
        item
        for item in _resolved_resource_requests_for_role(state, resource_role)
        if str(item.get("load_strategy_hint") or "").strip().lower() == "vector_retrieve"
    ]


def _resource_request_domain_call(
    state: GraphState,
    *,
    resource_role: str,
    default_query_text: str,
    default_retry_on_weak_results: bool = False,
) -> list[tuple[str, str, int, dict, list[str], bool]]:
    if "retrieval_plan" not in state:
        return []
    plan = state["retrieval_plan"]
    top_k = plan.get("top_k")
    if top_k is None:
        return []
    requests = _vector_retrieval_requests(state, resource_role)
    if not requests:
        return []

    filename_filters: list[str] = []
    query_texts: list[str] = []
    context_hints: list[str] = []
    fallback_queries: list[str] = []
    retry_on_weak_results = default_retry_on_weak_results
    for item in requests:
        filename = str(item.get("filename") or "").strip()
        if filename:
            filename_filters.append(filename)
        query_text = str(item.get("query_text") or "").strip()
        if query_text:
            query_texts.append(query_text)
        hints = item.get("context_hints")
        if isinstance(hints, list):
            context_hints.extend(str(hint).strip() for hint in hints if str(hint).strip())
        objective = str(item.get("objective") or "").strip()
        if objective:
            context_hints.append(objective)
        request_reason = str(item.get("request_reason") or "").strip()
        if request_reason:
            context_hints.append(request_reason)
        purpose = str(item.get("purpose") or "").strip()
        if purpose:
            context_hints.append(purpose)
        if str(item.get("load_strategy_hint") or "").strip().lower() == "vector_retrieve":
            retry_on_weak_results = True

    query_text = query_texts[0] if query_texts else str(default_query_text or "").strip()
    if not query_text:
        return []
    for variant in query_texts[1:]:
        fallback_queries.append(variant)
    retrieval_domain = (
        "instruction_source"
        if resource_role == "instruction_source"
        else "output_template"
    )
    return [
        (
            retrieval_domain,
            query_text,
            int(top_k),
            _merge_filename_filter(_plan_filters(plan), filename_filters),
            _dedupe_queries(fallback_queries + context_hints),
            bool(retry_on_weak_results),
        )
    ]


def _knowledge_calls_from_execution_plan_actions(state: GraphState) -> list[tuple[str, str, int, dict, list[str], bool]]:
    if "retrieval_plan" not in state:
        return []
    plan = state["retrieval_plan"]
    top_k = plan.get("top_k")
    if top_k is None:
        return []
    requests = _resolved_resource_requests_for_role(state, "knowledge_source")
    filename_filters = [
        str(item.get("filename") or "").strip()
        for item in requests
        if str(item.get("filename") or "").strip()
    ]
    calls: list[tuple[str, str, int, dict, list[str], bool]] = []
    for params in _action_params_from_execution_plan(state, "retrieve_knowledge"):
        query_text = str(params.get("query_text") or plan.get("query_text") or state.get("user_query") or "").strip()
        if not query_text:
            continue
        query_variants = params.get("query_variants", [])
        fallback_queries = params.get("fallback_queries", [])
        context_hints = params.get("context_hints", [])
        objective = str(params.get("objective") or "").strip()
        stage_label = str(params.get("stage_label") or "").strip()
        merged_variants = []
        if isinstance(query_variants, list):
            merged_variants.extend(str(item).strip() for item in query_variants if str(item).strip())
        if isinstance(fallback_queries, list):
            merged_variants.extend(str(item).strip() for item in fallback_queries if str(item).strip())
        if isinstance(context_hints, list):
            merged_variants.extend(str(item).strip() for item in context_hints if str(item).strip())
        if objective:
            merged_variants.append(objective)
        if stage_label:
            merged_variants.append(stage_label)
        params_filters = params.get("filename_filters", [])
        merged_filters = list(filename_filters)
        if isinstance(params_filters, list):
            merged_filters.extend(str(item).strip() for item in params_filters if str(item).strip())
        calls.append(
            (
                "knowledge_source",
                query_text,
                int(top_k),
                _merge_filename_filter(_plan_filters(plan), merged_filters),
                _dedupe_queries(merged_variants),
                bool(params.get("retry_on_weak_results")),
            )
        )
    return calls


def _domain_calls_from_execution_plan(state: GraphState) -> list[tuple[str, str, int, dict, list[str], bool]]:
    calls: list[tuple[str, str, int, dict, list[str], bool]] = []
    calls.extend(
        _resource_request_domain_call(
            state,
            resource_role="instruction_source",
            default_query_text=str(state.get("user_query") or "").strip(),
            default_retry_on_weak_results=True,
        )
    )
    calls.extend(_knowledge_calls_from_execution_plan_actions(state))
    if not any(call[0] == "knowledge_source" for call in calls):
        calls.extend(_knowledge_calls_from_resource_requests(state))
    calls.extend(
        _resource_request_domain_call(
            state,
            resource_role="output_template",
            default_query_text=str(state.get("user_query") or "").strip(),
            default_retry_on_weak_results=True,
        )
    )
    return calls


def _knowledge_calls_from_resource_requests(state: GraphState) -> list[tuple[str, str, int, dict, list[str], bool]]:
    if "retrieval_plan" not in state:
        return []
    plan = state["retrieval_plan"]
    top_k = plan.get("top_k")
    if top_k is None:
        return []
    filename_filters: list[str] = []
    query_texts: list[str] = []
    fallback_queries: list[str] = []
    context_hints: list[str] = []
    for item in _resolved_resource_requests_for_role(state, "knowledge_source"):
        if str(item.get("purpose") or "").strip() == "session_upload":
            continue
        filename = str(item.get("filename") or "").strip()
        if filename:
            filename_filters.append(filename)
        query_text = str(item.get("query_text") or "").strip()
        if query_text:
            query_texts.append(query_text)
        hints = item.get("context_hints")
        if isinstance(hints, list):
            context_hints.extend(str(hint).strip() for hint in hints if str(hint).strip())
        objective = str(item.get("objective") or "").strip()
        if objective:
            context_hints.append(objective)
    if not filename_filters and not query_texts:
        return []
    query_text = query_texts[0] if query_texts else str(plan.get("query_text") or state.get("user_query") or "").strip()
    if not query_text:
        return []
    for variant in query_texts[1:]:
        fallback_queries.append(variant)
    return [
        (
            "knowledge_source",
            query_text,
            int(top_k),
            _merge_filename_filter(_plan_filters(plan), filename_filters),
            _dedupe_queries(fallback_queries + context_hints),
            bool(fallback_queries),
        )
    ]


def _tag_evidence(evidence: list, retrieval_domain: str, *, query_text: str = "", attempt_index: int = 0) -> list:
    tagged = []
    for item in evidence:
        if isinstance(item, dict):
            tagged.append(
                {
                    **item,
                    "retrieval_domain": retrieval_domain,
                    "retrieval_query": query_text,
                    "retrieval_attempt": attempt_index,
                }
            )
        else:
            tagged.append(item)
    return tagged


def _dedupe_evidence(evidence: list) -> list:
    deduped = []
    seen: set[tuple[str, str, str]] = set()
    for item in evidence:
        if not isinstance(item, dict):
            deduped.append(item)
            continue
        key = (
            str(item.get("retrieval_domain") or ""),
            str(item.get("chunk_id") or item.get("doc_id") or ""),
            str(item.get("snippet") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _tokenize_query(text: str) -> list[str]:
    tokens = []
    for part in re.split(r"[^\w\u4e00-\u9fff]+", str(text or "").lower()):
        token = part.strip()
        if len(token) >= 2:
            tokens.append(token)
    return tokens


def _rerank_domain_evidence(evidence: list, attempts: list[dict]) -> list:
    if len(evidence) <= 1:
        return evidence
    query_tokens: list[str] = []
    for attempt in attempts:
        query_tokens.extend(_tokenize_query(attempt.get("query_text") or ""))
    unique_query_tokens = list(dict.fromkeys(query_tokens))

    def rank_key(item: dict) -> tuple[float, float, float]:
        snippet = str(item.get("snippet") or "").lower()
        title = str(item.get("title") or "").lower()
        score = float(item.get("score") or 0.0)
        lexical_hits = sum(1 for token in unique_query_tokens if token and (token in snippet or token in title))
        earlier_attempt_bonus = max(0.0, 5.0 - float(item.get("retrieval_attempt") or 0.0))
        return (
            score + lexical_hits * 0.05 + earlier_attempt_bonus * 0.01,
            float(lexical_hits),
            -float(item.get("retrieval_attempt") or 0.0),
        )

    return sorted(evidence, key=rank_key, reverse=True)


def _choose_primary_debug(attempts: list[dict]) -> dict:
    for attempt in attempts:
        if int(attempt.get("result_count") or 0) > 0 and isinstance(attempt.get("debug_trace"), dict):
            return dict(attempt["debug_trace"])
    for attempt in attempts:
        if isinstance(attempt.get("debug_trace"), dict):
            return dict(attempt["debug_trace"])
    return {}


def _merge_domain_attempts(attempts: list[dict], retry_on_weak_results: bool) -> dict | None:
    if not attempts:
        return None
    merged = _choose_primary_debug(attempts)
    merged["attempts"] = attempts
    merged["executed_queries"] = [attempt.get("query_text") for attempt in attempts]
    merged["attempt_count"] = len(attempts)
    merged["weak_retry_triggered"] = bool(retry_on_weak_results and len(attempts) > 1)
    return merged


def _merge_debug_traces(domain_debug: dict) -> dict | None:
    if not domain_debug:
        return None
    primary = domain_debug.get("knowledge_source") or next(iter(domain_debug.values()))
    if not isinstance(primary, dict):
        primary = {}
    merged = dict(primary)
    merged["domains"] = domain_debug
    return merged


def _merge_domain_debug(existing: dict | None, new_debug: dict | None) -> dict | None:
    if not isinstance(new_debug, dict):
        return existing
    if not isinstance(existing, dict):
        return dict(new_debug)
    merged = dict(existing)
    if "route" not in merged and isinstance(new_debug.get("route"), dict):
        merged["route"] = dict(new_debug["route"])
    existing_queries = list(merged.get("executed_queries", [])) if isinstance(merged.get("executed_queries"), list) else []
    new_queries = list(new_debug.get("executed_queries", [])) if isinstance(new_debug.get("executed_queries"), list) else []
    merged["executed_queries"] = _dedupe_queries(existing_queries + new_queries)
    merged["attempt_count"] = int(merged.get("attempt_count", 0) or 0) + int(new_debug.get("attempt_count", 0) or 0)
    merged["weak_retry_triggered"] = bool(merged.get("weak_retry_triggered") or new_debug.get("weak_retry_triggered"))
    if isinstance(merged.get("attempts"), list) and isinstance(new_debug.get("attempts"), list):
        merged["attempts"] = list(merged["attempts"]) + list(new_debug["attempts"])
    elif isinstance(new_debug.get("attempts"), list):
        merged["attempts"] = list(new_debug["attempts"])
    if isinstance(merged.get("loaded_resources"), list) and isinstance(new_debug.get("loaded_resources"), list):
        merged["loaded_resources"] = list(merged["loaded_resources"]) + list(new_debug["loaded_resources"])
    elif isinstance(new_debug.get("loaded_resources"), list):
        merged["loaded_resources"] = list(new_debug["loaded_resources"])
    return merged


def _session_upload_evidence(state: GraphState) -> tuple[list, dict | None]:
    uploads = state.get("session_uploads", [])
    turn_action_plan = state.get("turn_action_plan", {}) if isinstance(state.get("turn_action_plan"), dict) else {}
    response_style = turn_action_plan.get("response_style", {}) if isinstance(turn_action_plan, dict) else {}
    selected_ids = set(_session_upload_ids_from_plan(state))
    if not selected_ids:
        selected_ids = set(
        str(item or "").strip()
        for item in (response_style.get("session_upload_ids", []) if isinstance(response_style, dict) else [])
        if str(item or "").strip()
        )
    if not selected_ids or not isinstance(uploads, list):
        return [], None
    evidence: list = []
    for upload in uploads:
        if not isinstance(upload, dict):
            continue
        upload_id = str(upload.get("id") or "").strip()
        if upload_id not in selected_ids:
            continue
        text_content = str(upload.get("text_content") or "").strip()
        evidence.append(
            {
                "doc_id": upload_id,
                "title": str(upload.get("filename") or "Session Upload"),
                "snippet": text_content or "[Uploaded file has no extracted text content]",
                "score": 1.0,
                "metadata": {
                    "mime_type": upload.get("mime_type"),
                    "size_bytes": upload.get("size_bytes"),
                    "source": "session_upload",
                },
                "version": None,
                "location": upload.get("file_path"),
                "chunk_id": upload_id,
                "retrieval_domain": "session_upload",
                "retrieval_query": str(state.get("user_query") or ""),
                "retrieval_attempt": 0,
            }
        )
    if not evidence:
        return [], None
    return evidence, {
        "route": {"model": "session_upload", "namespace": "session", "language": None},
        "executed_queries": [item.get("title") for item in evidence],
        "attempt_count": 1,
        "weak_retry_triggered": False,
    }


def _build_prepared_inputs(state: GraphState) -> dict:
    turn_execution_plan = (
        state.get("turn_execution_plan", {})
        if isinstance(state.get("turn_execution_plan"), dict)
        else {}
    )
    return {
        "instruction_resource_context": state.get("instruction_resource_context", [])
        if isinstance(state.get("instruction_resource_context"), list)
        else [],
        "template_resource_context": state.get("template_resource_context", [])
        if isinstance(state.get("template_resource_context"), list)
        else [],
        "knowledge_evidence": [
            item
            for item in state.get("raw_evidence", [])
            if isinstance(item, dict) and str(item.get("retrieval_domain") or "").strip() == "knowledge_source"
        ]
        if isinstance(state.get("raw_evidence"), list)
        else [],
        "session_upload_evidence": [
            item
            for item in state.get("raw_evidence", [])
            if isinstance(item, dict) and str(item.get("retrieval_domain") or "").strip() == "session_upload"
        ]
        if isinstance(state.get("raw_evidence"), list)
        else [],
        "resource_requests": _resolved_resource_requests(state),
        "turn_execution_plan": turn_execution_plan,
        "active_binding_ids": _active_binding_ids(state),
        "artifact_gate_status": _initial_artifact_gate_status(state),
        "bundled_execution": _bundled_execution_context(turn_execution_plan),
    }


def _bundled_execution_context(turn_execution_plan: dict) -> dict:
    if not isinstance(turn_execution_plan, dict):
        return {
            "active_execution_mode": None,
            "bundled_entry_step_id": None,
            "active_bundled_step_ids": [],
        }
    return {
        "active_execution_mode": str(turn_execution_plan.get("active_execution_mode") or "").strip() or None,
        "bundled_entry_step_id": str(turn_execution_plan.get("bundled_entry_step_id") or "").strip() or None,
        "active_bundled_step_ids": [
            str(item).strip()
            for item in turn_execution_plan.get("active_bundled_step_ids", []) or []
            if str(item).strip()
        ],
    }


def _turn_intent(state: GraphState) -> str:
    plan = state.get("turn_execution_plan", {})
    if not isinstance(plan, dict):
        return ""
    return str(plan.get("turn_intent") or "").strip()


def run(
    state: GraphState,
    retrieve_fn: Optional[Callable[[str, int, dict], Dict]] = None,
) -> GraphState:
    """Prepare resources and execute retrieval from planner state."""
    if _turn_intent(state) == "general_out_of_scope_question":
        artifact_gate_status, _ = _artifact_gate_status(state)
        bundled_execution = _bundled_execution_context(state.get("turn_execution_plan", {}))
        state["raw_evidence"] = []
        state["instruction_resource_context"] = []
        state["template_resource_context"] = []
        state["retrieval_debug_trace"] = {
            "route": {"model": "bypassed", "namespace": "general_out_of_scope", "language": None},
            "domains": {},
            "retrieval_bypassed": True,
            "bypass_reason": "general_out_of_scope_question",
            "retrieval_bypass_reason": "general_out_of_scope_question",
            "artifact_gate_status": artifact_gate_status,
            "active_binding_ids": _active_binding_ids(state),
            "resolved_resource_requests": [dict(item) for item in _resolved_resource_requests(state)],
            "bundled_execution": bundled_execution,
        }
        state["compressed_instruction_evidence"] = []
        state["compressed_knowledge_evidence"] = []
        state["compressed_template_evidence"] = []
        state["compressed_session_upload_evidence"] = []
        prepared_inputs = _build_prepared_inputs(state)
        prepared_inputs["artifact_gate_status"] = artifact_gate_status
        state["prepared_inputs"] = prepared_inputs
        return state

    artifact_gate_status, artifact_bypass_reason = _artifact_gate_status(state)
    if artifact_bypass_reason:
        bundled_execution = _bundled_execution_context(state.get("turn_execution_plan", {}))
        state["raw_evidence"] = []
        state["instruction_resource_context"] = []
        state["template_resource_context"] = []
        state["retrieval_debug_trace"] = {
            "route": {"model": "bypassed", "namespace": "artifact_gate", "language": None},
            "domains": {},
            "retrieval_bypassed": True,
            "bypass_reason": artifact_bypass_reason,
            "retrieval_bypass_reason": artifact_bypass_reason,
            "artifact_gate_status": artifact_gate_status,
            "active_binding_ids": _active_binding_ids(state),
            "resolved_resource_requests": [dict(item) for item in _resolved_resource_requests(state)],
            "bundled_execution": bundled_execution,
        }
        state["compressed_instruction_evidence"] = []
        state["compressed_knowledge_evidence"] = []
        state["compressed_template_evidence"] = []
        state["compressed_session_upload_evidence"] = []
        prepared_inputs = _build_prepared_inputs(state)
        prepared_inputs["artifact_gate_status"] = artifact_gate_status
        state["prepared_inputs"] = prepared_inputs
        return state

    retriever = retrieve_fn or state.get("_retrieve_fn") or _default_retrieve
    raw_evidence: list = []
    domain_debug: dict = {}
    direct_instruction_evidence, direct_instruction_debug, instruction_resource_context = _direct_instruction_resource_evidence(state)
    direct_template_evidence, direct_template_debug, template_resource_context = _direct_template_resource_evidence(state)
    if direct_instruction_evidence:
        raw_evidence.extend(direct_instruction_evidence)
    if direct_template_evidence:
        raw_evidence.extend(direct_template_evidence)
    if isinstance(direct_instruction_debug, dict):
        direct_instruction_debug["resource_requests"] = _debug_resource_requests_for_domain(state, "instruction_source")
        domain_debug["instruction_source"] = _merge_domain_debug(domain_debug.get("instruction_source"), direct_instruction_debug)
    if isinstance(direct_template_debug, dict):
        direct_template_debug["resource_requests"] = _debug_resource_requests_for_domain(state, "output_template")
        domain_debug["output_template"] = _merge_domain_debug(domain_debug.get("output_template"), direct_template_debug)
    domain_calls = _domain_calls(state)
    for retrieval_domain, query_text, top_k, filters, query_variants, retry_on_weak_results in domain_calls:
        attempts = []
        queries_to_try = [query_text]
        for variant in query_variants:
            if variant.lower() != query_text.lower():
                queries_to_try.append(variant)

        domain_evidence: list = []
        for index, next_query in enumerate(_dedupe_queries(queries_to_try)):
            if index > 0 and not retry_on_weak_results and retrieval_domain == "knowledge_source":
                break
            result = retriever(next_query, int(top_k), filters)
            evidence, debug_trace = _normalize_result(result)
            tagged = _tag_evidence(evidence, retrieval_domain, query_text=next_query, attempt_index=index)
            domain_evidence.extend(tagged)
            attempts.append(
                {
                    "query_text": next_query,
                    "result_count": len(evidence),
                    "debug_trace": debug_trace,
                }
            )
            if retrieval_domain != "knowledge_source":
                continue
            if len(domain_evidence) > 0:
                continue

        raw_evidence.extend(_rerank_domain_evidence(_dedupe_evidence(domain_evidence), attempts))
        merged_domain_debug = _merge_domain_attempts(attempts, retry_on_weak_results)
        if merged_domain_debug is not None:
            merged_domain_debug["resource_requests"] = _debug_resource_requests_for_domain(state, retrieval_domain)
            domain_debug[retrieval_domain] = _merge_domain_debug(domain_debug.get(retrieval_domain), merged_domain_debug)

    upload_evidence, upload_debug = _session_upload_evidence(state)
    if upload_evidence:
        raw_evidence.extend(upload_evidence)
    if isinstance(upload_debug, dict):
        domain_debug["session_upload"] = upload_debug

    state["raw_evidence"] = _dedupe_evidence(raw_evidence)
    state["instruction_resource_context"] = _instruction_resource_context_from_evidence(
        state["raw_evidence"],
        instruction_resource_context,
    )
    state["template_resource_context"] = _template_resource_context_from_evidence(
        state["raw_evidence"],
        template_resource_context,
    )
    state["retrieval_debug_trace"] = _merge_debug_traces(domain_debug)
    if not isinstance(state["retrieval_debug_trace"], dict):
        state["retrieval_debug_trace"] = {}
    state["retrieval_debug_trace"]["retrieval_bypassed"] = False
    state["retrieval_debug_trace"]["retrieval_bypass_reason"] = None
    state["retrieval_debug_trace"]["artifact_gate_status"] = artifact_gate_status
    state["retrieval_debug_trace"]["active_binding_ids"] = _active_binding_ids(state)
    state["retrieval_debug_trace"]["bundled_execution"] = _bundled_execution_context(
        state.get("turn_execution_plan", {})
    )
    state["retrieval_debug_trace"]["resolved_resource_requests"] = [
        dict(item) for item in _resolved_resource_requests(state)
    ]
    state["compressed_instruction_evidence"] = [
        item for item in state["raw_evidence"]
        if isinstance(item, dict) and str(item.get("retrieval_domain") or "").strip() == "instruction_source"
    ]
    state["compressed_knowledge_evidence"] = [
        item for item in state["raw_evidence"]
        if isinstance(item, dict) and str(item.get("retrieval_domain") or "").strip() == "knowledge_source"
    ]
    state["compressed_template_evidence"] = [
        item for item in state["raw_evidence"]
        if isinstance(item, dict) and str(item.get("retrieval_domain") or "").strip() == "output_template"
    ]
    state["compressed_session_upload_evidence"] = [
        item for item in state["raw_evidence"]
        if isinstance(item, dict) and str(item.get("retrieval_domain") or "").strip() == "session_upload"
    ]
    prepared_inputs = _build_prepared_inputs(state)
    prepared_inputs["artifact_gate_status"] = artifact_gate_status
    state["prepared_inputs"] = prepared_inputs
    return state
