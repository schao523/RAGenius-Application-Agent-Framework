"""Thin wrappers around rag_subsystem's default vector-store factory."""

from __future__ import annotations

from shared.rag_env import configure_default_rag_env

configure_default_rag_env()


def get_rag_store():
    """Return rag_subsystem's cached default vector store."""
    from rag_subsystem import get_default_vector_store  # type: ignore

    return get_default_vector_store()


def reset_rag_store() -> None:
    """Clear rag_subsystem's cached default store for tests."""
    from rag_subsystem.vector_store.factory import clear_default_vector_store_cache  # type: ignore

    clear_default_vector_store_cache()
