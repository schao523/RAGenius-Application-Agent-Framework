"""In-memory vector store for testing."""
from __future__ import annotations
import math
from typing import Any, Dict, List, Sequence, Tuple
from .base import VectorStore
from ..schemas import Chunk


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1e-9
    norm_b = math.sqrt(sum(x * x for x in b)) or 1e-9
    return dot / (norm_a * norm_b)


class InMemoryVectorStore(VectorStore):
    def __init__(self) -> None:
        self._items: List[Chunk] = []

    def upsert(self, chunks: Sequence[Chunk]) -> None:
        existing = {(c.doc_id, c.hash): c for c in self._items}
        for chunk in chunks:
            existing[(chunk.doc_id, chunk.hash)] = chunk
        self._items = list(existing.values())

    def semantic_search(self, query_embedding: List[float], namespace: str, top_k: int) -> List[Tuple[Chunk, float]]:
        scored = [
            (chunk, _cosine(query_embedding, chunk.embedding))
            for chunk in self._items
            if chunk.namespace == namespace
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def metadata_search(self, filters: Dict[str, Any], namespace: str, top_k: int) -> List[Tuple[Chunk, float]]:
        results: List[Tuple[Chunk, float]] = []
        for chunk in self._items:
            if chunk.namespace != namespace:
                continue
            if all(chunk.metadata.get(k) == v for k, v in filters.items()):
                results.append((chunk, 1.0))
        return results[:top_k]

    def delete_by_doc_id(self, doc_id: str) -> None:
        self._items = [c for c in self._items if c.doc_id != doc_id]
