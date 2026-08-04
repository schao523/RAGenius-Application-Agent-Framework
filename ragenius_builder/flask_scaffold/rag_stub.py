"""Thin wrappers that delegate to the real rag_subsystem package.

These helpers intentionally avoid re-implementing RAG logic. They simply
forward calls with the parameters expected by the application so that the
rag_subsystem library can handle ingestion and retrieval behavior.
"""

from inspect import signature
import os
from pathlib import Path
import sys
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from shared.rag_env import configure_default_rag_env

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional dependency
    PdfReader = None

configure_default_rag_env()

from rag_subsystem import (
    process_files as _rag_process_files,
    retrieve_data as _rag_retrieve_data,
    get_default_vector_store as _rag_get_default_vector_store,
)
from rag_subsystem.config import ProcessConfig, RetrievalConfig
from rag_subsystem.language_detect import detect_language as _rag_detect_language


def _strip_surrogates(value: str) -> str:
    # Remove unpaired UTF-16 surrogate code points that break UTF-8 encoding.
    return "".join(ch for ch in value if not (0xD800 <= ord(ch) <= 0xDFFF))


def _sanitize_for_utf8(value: Any):
    if isinstance(value, str):
        return _strip_surrogates(value)
    if isinstance(value, list):
        return [_sanitize_for_utf8(item) for item in value]
    if isinstance(value, dict):
        return {str(_sanitize_for_utf8(k)): _sanitize_for_utf8(v) for k, v in value.items()}
    return value


def _allowed_kwargs(func, **kwargs):
    """Return kwargs filtered to parameters accepted by ``func``."""
    params = signature(func).parameters
    return {key: value for key, value in kwargs.items() if key in params}


def _env_int(name: str, default: int) -> int:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def get_global_process_config() -> ProcessConfig:
    """Build a global rag_subsystem process config from environment variables."""
    return ProcessConfig(
        chunk_size=_env_int("RAG_PROCESS_CHUNK_SIZE", 400),
        chunk_overlap=_env_int("RAG_PROCESS_CHUNK_OVERLAP", 60),
        section_token_threshold=_env_int("RAG_PROCESS_SECTION_TOKEN_THRESHOLD", 1200),
        min_chunk_length=_env_int("RAG_PROCESS_MIN_CHUNK_LENGTH", 30),
        near_dup_threshold=_env_float("RAG_PROCESS_NEAR_DUP_THRESHOLD", 0.95),
        retry_upsert=_env_int("RAG_PROCESS_RETRY_UPSERT", 1),
    )


def get_global_retrieval_config() -> RetrievalConfig:
    """Build a global rag_subsystem retrieval config from environment variables."""
    return RetrievalConfig(
        candidate_k=_env_int("RAG_RETRIEVAL_CANDIDATE_K", 50),
        fusion_k=_env_int("RAG_RETRIEVAL_FUSION_K", 60),
        top_k=_env_int("RAG_RETRIEVAL_TOP_K", 10),
        semantic_weight=_env_float("RAG_RETRIEVAL_SEMANTIC_WEIGHT", 1.0),
        metadata_weight=_env_float("RAG_RETRIEVAL_METADATA_WEIGHT", 1.0),
        max_chunks_per_doc=_env_int("RAG_RETRIEVAL_MAX_CHUNKS_PER_DOC", 3),
    )


def process_files(documents, config, store, embed_client=None, router=None):
    """Delegate ingestion to rag_subsystem.process_files.

    The function signature matches the upstream contract so callers do not
    change. All arguments are forwarded verbatim, keeping app_id scoping and
    store references intact for the subsystem to honor retry/backoff and
    status updates.
    """

    kwargs = _allowed_kwargs(
        _rag_process_files,
        documents=documents,
        store=store,
        embed_client=embed_client,
        router=router,
    )
    if config is not None and not isinstance(config, dict):
        kwargs["config"] = config
    return _rag_process_files(**kwargs)


def retrieve_data(query_text, top_k, filters, config, store, embed_client=None, router=None):
    """Delegate retrieval to rag_subsystem.retrieve_data.

    Calls pass through directly so the subsystem can execute searches,
    enforce timeouts, and format results consistent with the v3.5 spec.
    """

    kwargs = _allowed_kwargs(
        _rag_retrieve_data,
        query_text=query_text,
        top_k=top_k,
        filters=filters,
        store=store,
        embed_client=embed_client,
        router=router,
    )
    if config is not None and not isinstance(config, dict):
        kwargs["config"] = config
    return _rag_retrieve_data(**kwargs)


def _read_uploaded_text(file_path: str, mime_type: str | None = None) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".pdf" or (mime_type or "").lower() == "application/pdf":
        if PdfReader is None:
            raise RuntimeError("PDF ingestion requires pypdf. Install with: python -m pip install pypdf")
        reader = PdfReader(str(path))
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
        return "\n\n".join([p for p in pages if p]).strip()

    text_like_exts = {".txt", ".md", ".csv", ".tsv", ".json", ".html", ".htm", ".xml"}
    if suffix in text_like_exts or (mime_type or "").startswith("text/"):
        # Prefer UTF-8, then common Chinese encodings to avoid data loss.
        for enc in ("utf-8", "utf-8-sig", "cp950", "big5", "gb18030"):
            try:
                return path.read_text(encoding=enc)
            except UnicodeDecodeError:
                continue
        # Last resort: avoid hard failure but keep deterministic behavior.
        return path.read_text(encoding="utf-8", errors="ignore")

    raise RuntimeError(f"Unsupported file type for scaffold ingestion: {suffix or mime_type or 'unknown'}")


def ingest_uploaded_file(app_id: str, doc: dict, config=None, store=None):
    """Convert uploaded file into rag_subsystem document blocks and ingest."""
    file_path = doc.get("file_path")
    if not file_path:
        raise RuntimeError("Missing file_path on document")

    text = _sanitize_for_utf8(_read_uploaded_text(file_path, doc.get("mime_type")))
    if not text.strip():
        raise RuntimeError("No extractable text found in uploaded file")
    detected_language = _sanitize_for_utf8(_rag_detect_language(text))

    metadata = _sanitize_for_utf8(
        {
            "app_id": app_id,
            "filename": doc.get("filename"),
            "mime_type": doc.get("mime_type"),
            "language": detected_language or doc.get("language") or "en",
            "tags": doc.get("tags") or [],
        }
    )

    documents = [
        {
            "doc_id": doc["id"],
            "blocks": [
                {
                    "type": "text",
                    "text": text,
                    "metadata": metadata,
                }
            ],
        }
    ]
    results = process_files(
        documents=documents,
        config=config or get_global_process_config(),
        store=store,
        embed_client=None,
        router=None,
    )
    inserted_total = sum(int(getattr(r, "inserted", 0)) for r in (results or []))
    if inserted_total <= 0:
        raise RuntimeError(
            "Ingestion produced zero chunks. Check embedding runtime/model availability "
            "(RAG_EMBEDDING_BACKEND, local model files, and dependencies)."
        )
    return {
        "results": results,
        "inserted_total": inserted_total,
        "detected_language": detected_language or doc.get("language") or "en",
    }


def delete_document_chunks(doc_id: str, app_id: str, store=None):
    """Delete a document's vectors from rag_subsystem's vector store."""
    resolved_store = store or _rag_get_default_vector_store()
    return resolved_store.delete_by_doc_id(doc_id, app_id=app_id)
