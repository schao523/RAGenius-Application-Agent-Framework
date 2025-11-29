"""Base vector store abstraction."""
from __future__ import annotations
from typing import Any, Dict, List, Sequence, Tuple
from ..schemas import Chunk


class VectorStore:
    def upsert(self, chunks: Sequence[Chunk]) -> None:
        raise NotImplementedError

    def semantic_search(self, query_embedding: List[float], namespace: str, top_k: int) -> List[Tuple[Chunk, float]]:
        raise NotImplementedError

    def metadata_search(self, filters: Dict[str, Any], namespace: str, top_k: int) -> List[Tuple[Chunk, float]]:
        raise NotImplementedError

    def delete_by_doc_id(self, doc_id: str) -> None:
        raise NotImplementedError
