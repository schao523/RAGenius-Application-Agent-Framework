"""Vector store factory and default store resolution."""
from __future__ import annotations

import os
from functools import lru_cache

from .base import VectorStore
from .in_memory_store import InMemoryVectorStore
from .json_file_store import JsonFileVectorStore
from .pgvector_store import PgVectorStore

DEFAULT_LOCAL_PGVECTOR_DSN = "postgresql://ragenius:ragenius@localhost:5433/ragenius"


def _normalize_backend(value: str) -> str:
    return (value or "").strip().lower()


def _default_dsn() -> str:
    return (
        os.getenv("RAG_VECTOR_STORE_DSN")
        or os.getenv("PGVECTOR_DSN")
        or os.getenv("DATABASE_URL")
        or DEFAULT_LOCAL_PGVECTOR_DSN
    )


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _pgvector_bootstrap_enabled() -> bool:
    return _truthy(os.getenv("RAG_PGVECTOR_BOOTSTRAP"), default=True)


def _pgvector_fallback_mode() -> str:
    mode = (os.getenv("RAG_VECTOR_STORE_PGVECTOR_FALLBACK", "error") or "error").strip().lower()
    if mode not in ("error", "in_memory", "json"):
        return "error"
    return mode


def _make_pgvector_store() -> VectorStore:
    try:
        return PgVectorStore(_default_dsn(), bootstrap_schema=_pgvector_bootstrap_enabled())
    except Exception as exc:
        mode = _pgvector_fallback_mode()
        if mode == "in_memory":
            return InMemoryVectorStore()
        if mode == "json":
            path = os.getenv("RAG_VECTOR_STORE_PATH", "rag_subsystem/vector_store.json")
            return JsonFileVectorStore(path)
        raise RuntimeError(
            "Failed to initialize pgvector store and fallback mode is 'error'. "
            "Set RAG_VECTOR_STORE_PGVECTOR_FALLBACK=in_memory|json to fallback."
        ) from exc


def create_vector_store(backend: str | None = None) -> VectorStore:
    resolved = _normalize_backend(backend or os.getenv("RAG_VECTOR_STORE_BACKEND", "pgvector"))
    if resolved in ("pgvector", "postgres", "postgresql"):
        return _make_pgvector_store()
    if resolved in ("json", "json_file"):
        path = os.getenv("RAG_VECTOR_STORE_PATH", "rag_subsystem/vector_store.json")
        return JsonFileVectorStore(path)
    if resolved in ("in_memory", "memory"):
        return InMemoryVectorStore()
    if resolved == "auto":
        has_dsn = bool(os.getenv("RAG_VECTOR_STORE_DSN") or os.getenv("PGVECTOR_DSN") or os.getenv("DATABASE_URL"))
        return _make_pgvector_store() if has_dsn else InMemoryVectorStore()
    raise ValueError(f"Unsupported vector store backend: {resolved}")


@lru_cache(maxsize=1)
def get_default_vector_store() -> VectorStore:
    return create_vector_store()


def clear_default_vector_store_cache() -> None:
    get_default_vector_store.cache_clear()
