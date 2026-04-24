"""Retrieval pipeline implementation."""
from __future__ import annotations
from typing import Dict, List, Tuple
from .config import RetrievalConfig, DEFAULT_RETRIEVAL_CONFIG
from .language_detect import detect_language
from .embedding_router import route
from .embedding import embed_text
from .metadata_extract import extract_metadata
from .schemas import RetrievalResult, RetrievalCandidate, ValidationError
from .utils.logging import logger
from .utils.metrics import timer
from .vector_store.factory import get_default_vector_store


def _validate_query(query_text: str) -> None:
    if not query_text or not query_text.strip():
        raise ValidationError(path="query", msg="Query text is required")


def _require_app_id(filters: Dict[str, str]) -> str:
    app_id = str((filters or {}).get("app_id", "")).strip()
    if not app_id:
        raise ValidationError(path="filters.app_id", msg="app_id is required for retrieval isolation")
    return app_id


def _rrf(rank: int, k: int) -> float:
    return 1.0 / (k + rank)


def _fusion(
    semantic: List[Tuple[RetrievalCandidate, int]], metadata: List[Tuple[RetrievalCandidate, int]], fusion_k: int
) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for cand, rank in semantic:
        scores[cand.chunk.chunk_id] = scores.get(cand.chunk.chunk_id, 0.0) + _rrf(rank + 1, fusion_k)
    for cand, rank in metadata:
        scores[cand.chunk.chunk_id] = scores.get(cand.chunk.chunk_id, 0.0) + _rrf(rank + 1, fusion_k)
    return scores


def _select_best_versions(candidates: List[RetrievalCandidate]) -> List[RetrievalCandidate]:
    grouped: Dict[str, RetrievalCandidate] = {}
    for cand in candidates:
        doc_key = cand.chunk.doc_id
        existing = grouped.get(doc_key)
        if existing is None:
            grouped[doc_key] = cand
            continue
        new_version = cand.chunk.metadata.get("version", "0.0.0")
        old_version = existing.chunk.metadata.get("version", "0.0.0")
        if _compare_semver(new_version, old_version) > 0:
            grouped[doc_key] = cand
        elif _compare_semver(new_version, old_version) == 0:
            if cand.chunk.metadata.get("updated_at", "") > existing.chunk.metadata.get("updated_at", ""):
                grouped[doc_key] = cand
    return list(grouped.values())


def _compare_semver(a: str, b: str) -> int:
    def parse(v: str) -> Tuple[int, int, int]:
        parts = (v or "0.0.0").split(".")
        parts = [int(p) if p.isdigit() else 0 for p in (parts + ["0", "0", "0"])[:3]]
        return parts[0], parts[1], parts[2]

    pa, pb = parse(a), parse(b)
    return (pa > pb) - (pa < pb)


def retrieve_data(
    query_text: str,
    top_k: int = 10,
    filters: Dict[str, str] | None = None,
    config: RetrievalConfig = DEFAULT_RETRIEVAL_CONFIG,
    store=None,
) -> RetrievalResult:
    if store is None:
        store = get_default_vector_store()
    filters = filters or {}
    debug: Dict[str, any] = {"timing": {}}
    with timer(debug["timing"], "validate"):
        _validate_query(query_text)
    with timer(debug["timing"], "metadata_extract"):
        extracted_filters, meta_info = extract_metadata(query_text)
    merged_filters = {**extracted_filters, **filters}
    app_id = _require_app_id(merged_filters)
    merged_filters["app_id"] = app_id
    with timer(debug["timing"], "language_detect"):
        language = detect_language(query_text)
    with timer(debug["timing"], "routing"):
        route_info = route(language)
    scoped_namespace = f"{app_id}:{route_info.namespace}"
    with timer(debug["timing"], "embed"):
        query_embedding = embed_text(query_text, route_info.model)

    semantic_candidates: List[Tuple[RetrievalCandidate, int]] = []
    metadata_candidates: List[Tuple[RetrievalCandidate, int]] = []

    with timer(debug["timing"], "metadata_search"):
        if store:
            meta_results = store.metadata_search(merged_filters, scoped_namespace, config.candidate_k, app_id=app_id)
        else:
            meta_results = []
        for rank, (chunk, score) in enumerate(meta_results):
            metadata_candidates.append((RetrievalCandidate(chunk=chunk, score=score, source="metadata"), rank))
    with timer(debug["timing"], "semantic_search"):
        try:
            if store:
                sem_results = store.semantic_search(query_embedding, scoped_namespace, config.candidate_k, app_id=app_id)
            else:
                sem_results = []
        except Exception as exc:
            sem_results = []
            debug["semantic_search_error"] = str(exc)
            logger.warning("Semantic search failed, using metadata-only candidates: %s", exc)
        for rank, (chunk, score) in enumerate(sem_results):
            semantic_candidates.append((RetrievalCandidate(chunk=chunk, score=score, source="semantic"), rank))

    fusion_scores = _fusion(semantic_candidates, metadata_candidates, config.fusion_k)
    ranked_ids = sorted(fusion_scores.items(), key=lambda x: x[1], reverse=True)
    ranked_candidates: List[RetrievalCandidate] = []
    rank_lookup = {cid: score for cid, score in ranked_ids}
    all_candidates = {cand.chunk.chunk_id: cand for cand, _ in semantic_candidates + metadata_candidates}
    for chunk_id, _ in ranked_ids:
        ranked_candidates.append(all_candidates[chunk_id])
    ranked_candidates = _select_best_versions(ranked_candidates)
    final_results = ranked_candidates[:top_k]

    debug.update(
        {
            "semantic_candidates": [(c.chunk.chunk_id, s) for c, s in semantic_candidates],
            "metadata_candidates": [(c.chunk.chunk_id, s) for c, s in metadata_candidates],
            "fusion_scores": rank_lookup,
            "language": language,
            "route": {**route_info.__dict__, "namespace": scoped_namespace},
            "filters": merged_filters,
        }
    )

    return RetrievalResult(query=query_text, results=final_results, debug=debug)
