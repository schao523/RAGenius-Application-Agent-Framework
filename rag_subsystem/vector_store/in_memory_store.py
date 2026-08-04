"""In-memory vector store for testing."""
from __future__ import annotations
import math
import re
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
    # CJK fallback: use 2-char shingles
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


class InMemoryVectorStore(VectorStore):
    def __init__(self) -> None:
        self._items: List[Chunk] = []

    def upsert(self, chunks: Sequence[Chunk]) -> None:
        existing = {c.chunk_id: c for c in self._items}
        for chunk in chunks:
            existing[chunk.chunk_id] = chunk
        self._items = list(existing.values())

    def semantic_search(
        self,
        query_embedding: List[float],
        namespace: str,
        top_k: int,
        app_id: str | None = None,
        doc_filter: Dict[str, Any] | None = None,
    ) -> List[Tuple[Chunk, float]]:
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
        self._items = [
            c
            for c in self._items
            if not (c.doc_id == doc_id and (app_id is None or c.metadata.get("app_id") == app_id))
        ]
