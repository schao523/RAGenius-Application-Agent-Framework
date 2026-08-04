"""JSON file-backed vector store for local persistence."""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from .base import VectorStore
from .doc_filter import chunk_matches_doc_filter, normalize_doc_filter
from ..schemas import Chunk


def _cosine(a: List[float], b: List[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"Embedding dimension mismatch: query={len(a)} chunk={len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1e-9
    norm_b = math.sqrt(sum(x * x for x in b)) or 1e-9
    return dot / (norm_a * norm_b)


def _tokens(text: str) -> List[str]:
    raw = str(text or "").lower()
    words = re.findall(r"[a-z0-9_]+", raw)
    if words:
        return words
    return [raw[i : i + 2] for i in range(max(0, len(raw) - 1))]


def _lexical_score(query: str, text: str) -> float:
    q = str(query or "").strip().lower()
    t = str(text or "").lower()
    if not q or not t:
        return 0.0
    score = 0.0
    if q in t:
        score += 3.0
    qt = set(_tokens(q))
    tt = set(_tokens(t))
    if qt and tt:
        score += len(qt & tt) / max(1.0, len(qt))
    return score


class JsonFileVectorStore(VectorStore):
    """Persistent local vector store using a JSON file."""

    def __init__(self, path: str):
        self.path = Path(path)
        self._items: List[Chunk] = []
        self._last_mtime_ns: int | None = None
        self._load()

    def _read_mtime_ns(self) -> int | None:
        try:
            return self.path.stat().st_mtime_ns
        except FileNotFoundError:
            return None

    def _load(self) -> None:
        if not self.path.exists():
            self._items = []
            self._last_mtime_ns = None
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        items = raw.get("items", [])
        self._items = [Chunk(**item) for item in items]
        self._last_mtime_ns = self._read_mtime_ns()

    def _reload_if_changed(self) -> None:
        current_mtime_ns = self._read_mtime_ns()
        if current_mtime_ns == self._last_mtime_ns:
            return
        self._load()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"items": [asdict(chunk) for chunk in self._items]}
        with tempfile.NamedTemporaryFile(
            "w",
            delete=False,
            encoding="utf-8",
            dir=str(self.path.parent),
            suffix=".tmp",
        ) as tmp:
            json.dump(payload, tmp, ensure_ascii=False, indent=2)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, self.path)
        self._last_mtime_ns = self._read_mtime_ns()

    def upsert(self, chunks: Sequence[Chunk]) -> None:
        self._reload_if_changed()
        existing = {c.chunk_id: c for c in self._items}
        for chunk in chunks:
            existing[chunk.chunk_id] = chunk
        self._items = list(existing.values())
        self._save()

    def semantic_search(
        self,
        query_embedding: List[float],
        namespace: str,
        top_k: int,
        app_id: str | None = None,
        doc_filter: Dict[str, Any] | None = None,
    ) -> List[Tuple[Chunk, float]]:
        self._reload_if_changed()
        normalized_doc_filter = normalize_doc_filter(doc_filter)
        scored = [
            (chunk, _cosine(query_embedding, chunk.embedding))
            for chunk in self._items
            if chunk.namespace == namespace
            and (app_id is None or chunk.metadata.get("app_id") == app_id)
            and chunk_matches_doc_filter(chunk, normalized_doc_filter)
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def metadata_search(
        self,
        filters: Dict[str, Any],
        namespace: str,
        top_k: int,
        app_id: str | None = None,
        doc_filter: Dict[str, Any] | None = None,
    ) -> List[Tuple[Chunk, float]]:
        self._reload_if_changed()
        normalized_doc_filter = normalize_doc_filter(doc_filter)
        results: List[Tuple[Chunk, float]] = []
        for chunk in self._items:
            if chunk.namespace != namespace:
                continue
            if app_id is not None and chunk.metadata.get("app_id") != app_id:
                continue
            if not chunk_matches_doc_filter(chunk, normalized_doc_filter):
                continue
            if all(chunk.metadata.get(k) == v for k, v in filters.items()):
                results.append((chunk, 1.0))
        return results[:top_k]

    def lexical_search(
        self,
        query_text: str,
        namespace: str,
        top_k: int,
        app_id: str | None = None,
        doc_filter: Dict[str, Any] | None = None,
    ) -> List[Tuple[Chunk, float]]:
        self._reload_if_changed()
        normalized_doc_filter = normalize_doc_filter(doc_filter)
        scored = []
        for chunk in self._items:
            if chunk.namespace != namespace:
                continue
            if app_id is not None and chunk.metadata.get("app_id") != app_id:
                continue
            if not chunk_matches_doc_filter(chunk, normalized_doc_filter):
                continue
            s = _lexical_score(query_text, chunk.text)
            if s > 0:
                scored.append((chunk, s))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def delete_by_doc_id(self, doc_id: str, app_id: str | None = None) -> None:
        self._reload_if_changed()
        self._items = [
            c
            for c in self._items
            if not (c.doc_id == doc_id and (app_id is None or c.metadata.get("app_id") == app_id))
        ]
        self._save()
