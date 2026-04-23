"""
Integration stubs for the `rag_subsystem` API.

These functions simulate the ingestion and retrieval hooks used by the RAG
platform.  In a production system these would be provided by the underlying
embedding/vector store implementation.  They accept the same arguments that
the design specification expects, but they do not attempt to perform any
embedding, storage or retrieval.  Instead they log their inputs and return
simple placeholder values so that the rest of the application can be wired
and tested without a running RAG subsystem.

Important: Do not modify the function signatures – these are part of a
stable contract.  The platform will call these with `config_settings` and
other parameters derived from the Application context.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


def process_files(
    documents: Iterable[Any],
    config: Dict[str, Any],
    store: Any,
    embed_client: Any,
    router: Any,
) -> None:
    """Pretend to process a batch of documents for ingestion.

    This stub simply iterates over the provided documents and logs their
    filenames.  In a real implementation this would tokenize the content,
    generate embeddings and write them into the vector store.  The `config`
    argument contains the user‑defined configuration settings for the
    application.  The additional arguments `store`, `embed_client` and
    `router` are passed through as opaque handles and are not used here.
    """
    # Ingest each document one by one.  We deliberately avoid touching the
    # documents' contents to respect the black‑box nature of the RAG subsystem.
    for doc in documents:
        try:
            filename = getattr(doc, "filename", None) or getattr(doc, "name", "<unknown>")
            print(f"[rag_stub] Ingesting document: {filename}")
        except Exception as exc:
            print(f"[rag_stub] Failed to inspect document: {exc}")
    # No return value is required by the specification.
    return None


def retrieve_data(
    query_text: str,
    top_k: int,
    filters: Optional[Dict[str, Any]],
    config: Dict[str, Any],
    store: Any,
    embed_client: Any,
    router: Any,
) -> List[Dict[str, Any]]:
    """Pretend to retrieve data for a user query.

    This stub logs the query and returns a fixed set of dummy results.  The
    results contain citation structures to demonstrate how the UI can bind
    to the returned data.  `filters` must include an `app_id` key to ensure
    isolation between applications; any additional filters from the user are
    ignored.

    Returns:
        A list of result dictionaries.  Each result contains a `text` field
        representing the answer and a `citations` field containing a list of
        references (here just placeholder paths and line numbers).
    """
    app_id = filters.get("app_id") if filters else None
    print(f"[rag_stub] Running retrieve_data for app_id={app_id}, query='{query_text}', top_k={top_k}")
    # Generate predictable dummy results.  Real implementations would score
    # passages from the vector store and return the top_k most relevant.
    results: List[Dict[str, Any]] = []
    for i in range(top_k):
        results.append(
            {
                "rank": i + 1,
                "text": f"This is a placeholder answer {i + 1} for query '{query_text}'.",
                "citations": [
                    {
                        "doc_id": f"doc-{app_id}-{i}",
                        "file_path": f"/apps/{app_id}/docs/doc-{i}.md",
                        "snippet": f"Excerpt from document {i}...",
                    }
                ],
                "debug": {
                    "score": 0.0,
                    "metadata": {},
                },
            }
        )
    return results