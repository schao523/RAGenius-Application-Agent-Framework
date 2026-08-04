"""Shared doc-scoping helpers for vector stores."""
from __future__ import annotations

from typing import Any, Dict, Iterable


def normalize_filename(value: str) -> str:
    return " ".join(str(value or "").strip().split()).lower()


def basename_from_path(path_value: str) -> str:
    value = str(path_value or "").strip()
    if not value:
        return ""
    return value.replace("\\", "/").rsplit("/", 1)[-1].strip()


def chunk_filename_norm(chunk) -> str:
    meta = getattr(chunk, "metadata", {}) or {}
    filename_norm = str(meta.get("filename_norm", "")).strip()
    if filename_norm:
        return normalize_filename(filename_norm)
    filename = str(meta.get("filename", "")).strip()
    if filename:
        return normalize_filename(filename)
    source_name = basename_from_path(meta.get("source_path", ""))
    if source_name:
        return normalize_filename(source_name)
    return ""


def chunk_matches_doc_filter(chunk, doc_filter: Dict[str, Any] | None) -> bool:
    if not doc_filter:
        return True
    expected_doc_id = str(doc_filter.get("doc_id", "")).strip()
    if expected_doc_id and getattr(chunk, "doc_id", None) != expected_doc_id:
        return False

    chunk_name = chunk_filename_norm(chunk)
    filename_in = [normalize_filename(v) for v in (doc_filter.get("filename_in_norm") or []) if str(v).strip()]
    if filename_in and chunk_name not in set(filename_in):
        return False

    filename_norm = str(doc_filter.get("filename_norm", "")).strip()
    if filename_norm and chunk_name != normalize_filename(filename_norm):
        return False
    return True


def normalize_doc_filter(doc_filter: Dict[str, Any] | None) -> Dict[str, Any]:
    raw = dict(doc_filter or {})
    out: Dict[str, Any] = {}
    doc_id = str(raw.get("doc_id", "")).strip()
    if doc_id:
        out["doc_id"] = doc_id

    filename_norm = str(raw.get("filename_norm", "")).strip()
    if filename_norm:
        out["filename_norm"] = normalize_filename(filename_norm)

    filename_in_raw = raw.get("filename_in_norm", [])
    if isinstance(filename_in_raw, str):
        filename_in_vals: Iterable[str] = [filename_in_raw]
    else:
        filename_in_vals = filename_in_raw or []
    normalized = []
    for item in filename_in_vals:
        v = normalize_filename(str(item))
        if v and v not in normalized:
            normalized.append(v)
    if normalized:
        out["filename_in_norm"] = normalized
    return out

