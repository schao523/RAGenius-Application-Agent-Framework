"""JSON file-backed vector store for local persistence."""
from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from .base import VectorStore
from ..schemas import Chunk


def _cosine(a: List[float], b: List[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"Embedding dimension mismatch: query={len(a)} chunk={len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1e-9
    norm_b = math.sqrt(sum(x * x for x in b)) or 1e-9
    return dot / (norm_a * norm_b)


class JsonFileVectorStore(VectorStore):
    """Persistent local vector store using a JSON file."""

    def __init__(self, path: str):
        self.path = Path(path)
        self._items: List[Chunk] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._items = []
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        items = raw.get("items", [])
        self._items = [Chunk(**item) for item in items]

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

    def upsert(self, chunks: Sequence[Chunk]) -> None:
        existing = {c.chunk_id: c for c in self._items}
        for chunk in chunks:
            existing[chunk.chunk_id] = chunk
        self._items = list(existing.values())
        self._save()

    def semantic_search(
        self, query_embedding: List[float], namespace: str, top_k: int, app_id: str | None = None
    ) -> List[Tuple[Chunk, float]]:
        scored = [
            (chunk, _cosine(query_embedding, chunk.embedding))
            for chunk in self._items
            if chunk.namespace == namespace and (app_id is None or chunk.metadata.get("app_id") == app_id)
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def metadata_search(
        self, filters: Dict[str, Any], namespace: str, top_k: int, app_id: str | None = None
    ) -> List[Tuple[Chunk, float]]:
        results: List[Tuple[Chunk, float]] = []
        for chunk in self._items:
            if chunk.namespace != namespace:
                continue
            if app_id is not None and chunk.metadata.get("app_id") != app_id:
                continue
            if all(chunk.metadata.get(k) == v for k, v in filters.items()):
                results.append((chunk, 1.0))
        return results[:top_k]

    def delete_by_doc_id(self, doc_id: str, app_id: str | None = None) -> None:
        self._items = [
            c
            for c in self._items
            if not (c.doc_id == doc_id and (app_id is None or c.metadata.get("app_id") == app_id))
        ]
        self._save()
