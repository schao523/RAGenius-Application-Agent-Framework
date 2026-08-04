"""Shared default environment wiring for rag_subsystem-backed apps."""

from __future__ import annotations

import os
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_repo_env_file(*, repo_root: Path | None = None) -> list[str]:
    root = Path(repo_root or _repo_root())
    candidates = [
        root / ".env",
        root / "ragenius_app_skeleton" / ".env",
    ]
    loaded: list[str] = []
    for env_path in candidates:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or os.environ.get(key) is not None:
                continue
            os.environ[key] = value.strip()
            loaded.append(key)
        if loaded:
            break
    return loaded


def configure_default_rag_env() -> None:
    """Set safe local defaults when the caller has not configured rag_subsystem."""
    repo_root = _repo_root()
    shared_state_dir = repo_root / ".shared_state"
    shared_state_dir.mkdir(parents=True, exist_ok=True)
    _load_repo_env_file(repo_root=repo_root)

    os.environ.setdefault("RAG_VECTOR_STORE_BACKEND", "pgvector")
    os.environ.setdefault(
        "RAG_VECTOR_STORE_DSN",
        os.environ.get("DATABASE_URL", "postgresql://ragenius:ragenius@localhost:5433/ragenius"),
    )
    os.environ.setdefault("RAG_VECTOR_STORE_PGVECTOR_FALLBACK", "error")
    os.environ.setdefault("RAG_VECTOR_STORE_PATH", str(shared_state_dir / "rag_vector_store.json"))
    os.environ.setdefault("RAG_PGVECTOR_BOOTSTRAP", "true")
    os.environ.setdefault("RAG_EMBEDDING_BACKEND", "local")
    os.environ.setdefault("RAG_PROCESS_CHUNK_SIZE", "400")
    os.environ.setdefault("RAG_PROCESS_CHUNK_OVERLAP", "60")
    os.environ.setdefault("RAG_PROCESS_SECTION_TOKEN_THRESHOLD", "1200")
    os.environ.setdefault("RAG_PROCESS_MIN_CHUNK_LENGTH", "30")
    os.environ.setdefault("RAG_PROCESS_NEAR_DUP_THRESHOLD", "0.95")
    os.environ.setdefault("RAG_PROCESS_RETRY_UPSERT", "1")
    os.environ.setdefault("RAG_RETRIEVAL_CANDIDATE_K", "50")
    os.environ.setdefault("RAG_RETRIEVAL_FUSION_K", "60")
    os.environ.setdefault("RAG_RETRIEVAL_TOP_K", "10")
    os.environ.setdefault("RAG_RETRIEVAL_SEMANTIC_WEIGHT", "1.0")
    os.environ.setdefault("RAG_RETRIEVAL_METADATA_WEIGHT", "1.0")
    os.environ.setdefault("RAG_RETRIEVAL_MAX_CHUNKS_PER_DOC", "3")
