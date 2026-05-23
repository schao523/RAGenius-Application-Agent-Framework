"""Process files pipeline (ingestion)."""
from __future__ import annotations
from typing import Iterable, List
from .config import ProcessConfig, DEFAULT_PROCESS_CONFIG
from .normalize import normalize_documents
from .chunking import chunk_blocks
from .quality_filter import filter_chunks
from .embedding import embed_text
from .embedding_router import route
from .language_detect import detect_language
from .schemas import Chunk, IngestResult
from .utils.logging import logger
from .vector_store.factory import get_default_vector_store


def _require_app_id(metadata: dict) -> str:
    app_id = str((metadata or {}).get("app_id", "")).strip()
    if not app_id:
        raise ValueError("metadata.app_id is required for ingestion")
    return app_id


def _basename_from_path(path_value: str) -> str:
    value = str(path_value or "").strip()
    if not value:
        return ""
    # Handle Windows and POSIX separators regardless of current OS.
    return value.replace("\\", "/").rsplit("/", 1)[-1].strip()


def _normalize_filename_for_filter(filename: str) -> str:
    value = " ".join(str(filename or "").strip().split())
    return value.lower()


def _ensure_filename_metadata(metadata: dict) -> dict:
    out = dict(metadata or {})
    filename = str(out.get("filename", "")).strip()
    if not filename:
        filename = _basename_from_path(out.get("source_path", ""))
    if not filename:
        # Last fallback keeps per-doc filterability when filename/source_path is absent.
        filename = _basename_from_path(out.get("doc_id", ""))
    if filename:
        out["filename"] = filename
        out["filename_norm"] = _normalize_filename_for_filter(filename)
    return out


def process_files(documents: Iterable[dict], config: ProcessConfig = DEFAULT_PROCESS_CONFIG, store=None) -> List[IngestResult]:
    if store is None:
        store = get_default_vector_store()
    results: List[IngestResult] = []
    blocks = normalize_documents(documents)
    app_doc_pairs = {(block.doc_id, _require_app_id(block.metadata)) for block in blocks}
    for doc_id, app_id in app_doc_pairs:
        store.delete_by_doc_id(doc_id, app_id=app_id)

    chunks_raw = chunk_blocks(blocks, config.chunk_size, config.chunk_overlap, config.section_token_threshold)
    filtered_chunks, skip_counts = filter_chunks(chunks_raw, config)

    prepared_chunks: List[Chunk] = []
    for idx, chunk_data in enumerate(filtered_chunks):
        try:
            metadata = _ensure_filename_metadata(chunk_data.get("metadata", {}))
            language = detect_language(chunk_data["text"])
            route_info = route(language)
            app_id = _require_app_id(metadata)
            embedding = embed_text(chunk_data["text"], route_info.model)
            chunk = Chunk(
                doc_id=chunk_data["doc_id"],
                chunk_id=f"{chunk_data['doc_id']}::{idx}",
                text=chunk_data["text"],
                section_path=chunk_data.get("section_path"),
                order=chunk_data.get("order", idx),
                language=route_info.language,
                embedding_model=route_info.model,
                namespace=f"{app_id}:{route_info.namespace}",
                embedding=embedding,
                metadata=metadata,
                hash=chunk_data["hash"],
            )
            prepared_chunks.append(chunk)
        except Exception as exc:  # skip embedding failures
            logger.warning("Embedding failed for chunk %s: %s", chunk_data.get("doc_id"), exc)
            continue

    if store is not None:
        attempts = 0
        while True:
            try:
                store.upsert(prepared_chunks)
                break
            except Exception as exc:
                attempts += 1
                if attempts > config.retry_upsert:
                    raise
                logger.warning("Upsert failed, retrying once: %s", exc)

    doc_ids = {c.doc_id for c in prepared_chunks}
    for doc_id in doc_ids:
        inserted = sum(1 for c in prepared_chunks if c.doc_id == doc_id)
        results.append(
            IngestResult(
                doc_id=doc_id,
                inserted=inserted,
                skipped_too_short_count=skip_counts["skipped_too_short_count"],
                skipped_boilerplate_count=skip_counts["skipped_boilerplate_count"],
                skipped_near_dup_count=skip_counts["skipped_near_dup_count"],
            )
        )
    return results
