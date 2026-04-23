"""Thin wrappers that delegate to the real rag_subsystem package.

These helpers intentionally avoid re-implementing RAG logic. They simply
forward calls with the parameters expected by the application so that the
rag_subsystem library can handle ingestion and retrieval behavior.
"""

from inspect import signature

from rag_subsystem import process_files as _rag_process_files, retrieve_data as _rag_retrieve_data


def _allowed_kwargs(func, **kwargs):
    """Return kwargs filtered to parameters accepted by ``func``."""
    params = signature(func).parameters
    return {key: value for key, value in kwargs.items() if key in params}


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
        config=config,
        store=store,
        embed_client=embed_client,
        router=router,
    )
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
        config=config,
        store=store,
        embed_client=embed_client,
        router=router,
    )
    return _rag_retrieve_data(**kwargs)
