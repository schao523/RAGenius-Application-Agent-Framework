"""Node G: evidence_postprocess.

Deterministic dedupe + group + compress of raw evidence.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from ..graph_state import GraphState


_MAX_SNIPPET_LEN = 400
_BINARY_PATTERNS = re.compile(r"(?:endobj|stream|\/FlateDecode|\/FontDescriptor|xref)", flags=re.IGNORECASE)


def _sanitize_snippet(snippet: str) -> str:
    text = " ".join(str(snippet or "").replace("\x00", " ").split())
    if not text:
        return ""
    if _BINARY_PATTERNS.search(text):
        return "[Snippet omitted: non-readable extracted content]"
    return text[:_MAX_SNIPPET_LEN]


def _dedupe(raw_evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[Tuple[str, str, str]] = set()
    deduped: List[Dict[str, Any]] = []
    for item in raw_evidence:
        key = (
            str(item.get("doc_id", "")),
            str(item.get("title", "")),
            str(item.get("snippet", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _group_and_compress(deduped: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for item in deduped:
        doc_id = str(item.get("doc_id", ""))
        if not doc_id:
            continue
        score = float(item.get("score", 0.0) or 0.0)
        title = str(item.get("title", ""))
        snippet = _sanitize_snippet(str(item.get("snippet", "")))
        metadata = item.get("metadata", {}) if isinstance(item.get("metadata", {}), dict) else {}

        if doc_id not in grouped:
            grouped[doc_id] = {
                "doc_id": doc_id,
                "title": title,
                "score": score,
                "snippet": snippet,
                "metadata": metadata,
                "snippets": [snippet] if snippet else [],
                "source_count": 1,
                "location": item.get("location"),
                "version": item.get("version"),
                "chunk_id": item.get("chunk_id"),
                "retrieval_domain": item.get("retrieval_domain"),
            }
            continue

        group = grouped[doc_id]
        group["source_count"] = int(group["source_count"]) + 1
        if snippet and snippet not in group["snippets"]:
            group["snippets"].append(snippet)
        if score > float(group.get("score", 0.0)):
            group["score"] = score
            group["title"] = title or group["title"]
            group["location"] = item.get("location")
            group["version"] = item.get("version")
            group["chunk_id"] = item.get("chunk_id")
            group["retrieval_domain"] = item.get("retrieval_domain") or group.get("retrieval_domain")

    compressed: List[Dict[str, Any]] = []
    for doc_id in sorted(grouped.keys()):
        group = grouped[doc_id]
        combined = " | ".join([s for s in group["snippets"][:2] if s])
        group["snippet"] = combined
        compressed.append(group)

    compressed.sort(key=lambda x: (-float(x.get("score", 0.0)), str(x.get("doc_id", ""))))
    return compressed


def _filter_by_domain(raw_evidence: List[Dict[str, Any]], retrieval_domain: str) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for item in raw_evidence:
        if not isinstance(item, dict):
            continue
        if str(item.get("retrieval_domain") or "").strip() == retrieval_domain:
            filtered.append(item)
    return filtered


def run(state: GraphState) -> GraphState:
    """Compress evidence deterministically for downstream analysis/answering."""
    raw = state.get("raw_evidence", [])
    if not isinstance(raw, list):
        raise ValueError("raw_evidence must be a list.")

    deduped = _dedupe(raw)
    state["compressed_evidence"] = _group_and_compress(deduped)
    state["compressed_instruction_evidence"] = _group_and_compress(_dedupe(_filter_by_domain(raw, "instruction_source")))
    state["compressed_knowledge_evidence"] = _group_and_compress(_dedupe(_filter_by_domain(raw, "knowledge_source")))
    state["compressed_template_evidence"] = _group_and_compress(_dedupe(_filter_by_domain(raw, "output_template")))
    state["compressed_session_upload_evidence"] = _group_and_compress(_dedupe(_filter_by_domain(raw, "session_upload")))
    return state
