"""Ingestion orchestration calling rag_subsystem.process_files."""

from __future__ import annotations

import inspect
import re
import uuid
from io import BytesIO
from typing import Callable, Iterable, List, Optional

from fastapi import BackgroundTasks

from shared.rag_env import configure_default_rag_env

from .builder_store import get_builder_store
from .ingestion_repo import IngestionRepo

configure_default_rag_env()

try:
    from rag_subsystem import process_files as _process_files  # type: ignore
except Exception:  # pragma: no cover
    _process_files = None

RAG_PROCESS_FN: Optional[Callable] = _process_files

_MAX_TEXT_LEN = 12_000
_MIN_PRINTABLE_RATIO = 0.85


def _collapse_ws(text: str) -> str:
    return " ".join(text.replace("\x00", " ").split())


def _is_mostly_printable(text: str) -> bool:
    if not text:
        return True
    printable = sum(1 for c in text if c.isprintable() or c in "\r\n\t")
    return (printable / len(text)) >= _MIN_PRINTABLE_RATIO


def _extract_pdf_text(content: bytes) -> str:
    text_candidates: list[str] = []

    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(BytesIO(content))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        cleaned = _collapse_ws(text)
        if cleaned:
            text_candidates.append(cleaned)
    except Exception:
        pass

    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(BytesIO(content)) as pdf:
            text = "\n".join((page.extract_text() or "") for page in pdf.pages)
        cleaned = _collapse_ws(text)
        if cleaned:
            text_candidates.append(cleaned)
    except Exception:
        pass

    if not text_candidates:
        return ""
    best = max(text_candidates, key=len)
    return best[:_MAX_TEXT_LEN]


def _extract_text_for_document(content: bytes | str, content_type: str) -> str:
    ctype = (content_type or "").lower()
    if isinstance(content, str):
        return _collapse_ws(content)[:_MAX_TEXT_LEN]

    if "pdf" in ctype:
        extracted = _extract_pdf_text(content)
        if extracted:
            return extracted
        return "[PDF text extraction failed]"

    text = content.decode("utf-8", errors="ignore")
    text = _collapse_ws(text)
    if not _is_mostly_printable(text):
        return "[Non-text document; no extractable UTF-8 text]"
    if re.search(r"(?:endobj|stream|\/FlateDecode|xref)", text, flags=re.IGNORECASE):
        return "[Binary-like content omitted]"
    return text[:_MAX_TEXT_LEN]


def _default_process_files(*, documents, config=None, store=None, embed_client=None, router=None):
    if RAG_PROCESS_FN is None:
        raise RuntimeError("rag_subsystem.process_files is required for ingestion.")
    if config is None:
        try:
            from rag_subsystem import DEFAULT_PROCESS_CONFIG  # type: ignore

            config = DEFAULT_PROCESS_CONFIG
        except Exception:
            # Leave as None if subsystem does not expose default config.
            config = None
    # Match rag_subsystem sealed contract by calling only supported kwargs.
    candidate_kwargs = {
        "documents": documents,
        "config": config,
        "store": store,
        "embed_client": embed_client,
        "router": router,
    }

    sig = inspect.signature(RAG_PROCESS_FN)
    accepts_var_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    if accepts_var_kwargs:
        return RAG_PROCESS_FN(**candidate_kwargs)

    allowed = {name for name in sig.parameters.keys()}
    filtered_kwargs = {k: v for k, v in candidate_kwargs.items() if k in allowed}
    return RAG_PROCESS_FN(**filtered_kwargs)


def enqueue_ingestion(collection_id: str, files: Iterable, repo: IngestionRepo, background_tasks: BackgroundTasks) -> dict:
    files = list(files)
    run = repo.create_run(collection_id, document_count=len(files))
    background_tasks.add_task(run_ingestion, run["id"], collection_id, files, repo)
    return run


def enqueue_builder_ingestion(
    app_id: str,
    document_ids: list[str] | None,
    repo: IngestionRepo,
    background_tasks: BackgroundTasks,
) -> dict:
    builder_store = get_builder_store()
    if document_ids:
        documents = [builder_store.get_document(app_id, doc_id) for doc_id in document_ids]
        selected = [doc for doc in documents if doc is not None and doc.get("file_path")]
    else:
        selected = [doc for doc in builder_store.list_documents(app_id) if doc.get("file_path")]

    run = repo.create_run(app_id, document_count=len(selected))
    background_tasks.add_task(run_builder_ingestion, run["id"], app_id, selected, repo)
    return run


def run_ingestion(run_id: str, collection_id: str, files: List, repo: IngestionRepo):
    app_id = collection_id
    repo.update_status(run_id, "running")
    try:
        documents = []
        for f in files:
            content = f.file.read() if hasattr(f, "file") else f.read()
            content_type = getattr(f, "content_type", "application/octet-stream")
            text_content = _extract_text_for_document(content, content_type)
            if not text_content:
                text_content = "[No text extracted from document]"
            doc_id = str(uuid.uuid4())
            documents.append(
                {
                    "doc_id": doc_id,
                    "filename": getattr(f, "filename", "document"),
                    "content": content,
                    "content_type": content_type,
                    "blocks": [
                        {
                            "type": "text",
                            "text": text_content,
                            "metadata": {
                                "app_id": app_id,
                                "filename": getattr(f, "filename", "document"),
                                "content_type": getattr(f, "content_type", "application/octet-stream"),
                            },
                        }
                    ],
                }
            )
        result = _default_process_files(
            documents=documents,
            config=None,
            store=None,
            embed_client=None,
            router=None,
        )
        repo.update_status(
            run_id,
            "success",
            debug_trace=result.get("debug_trace") if isinstance(result, dict) else None,
            document_count=len(documents),
        )
    except Exception as exc:
        repo.update_status(run_id, "failed", debug_trace={"error": str(exc)})


def run_builder_ingestion(run_id: str, app_id: str, documents: List[dict], repo: IngestionRepo):
    repo.update_status(run_id, "running")
    try:
        from ragenius_builder.flask_scaffold.rag_stub import ingest_uploaded_file  # type: ignore
    except Exception as exc:  # pragma: no cover
        repo.update_status(run_id, "failed", debug_trace={"error": f"Builder ingestion bridge unavailable: {exc}"})
        return

    ingested_ids: list[str] = []
    for doc in documents:
        if not doc or not doc.get("file_path"):
            continue
        ingest_uploaded_file(app_id, doc, config=None, store=None)
        ingested_ids.append(str(doc.get("id")))

    repo.update_status(
        run_id,
        "success",
        debug_trace={"ingested_document_ids": ingested_ids},
        document_count=len(ingested_ids),
    )
