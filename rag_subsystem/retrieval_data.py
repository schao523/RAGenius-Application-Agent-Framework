"""Retrieval pipeline implementation."""
from __future__ import annotations
from typing import Any, Dict, List, Tuple
from .config import RetrievalConfig, DEFAULT_RETRIEVAL_CONFIG
from .language_detect import detect_language
from .embedding_router import route
from .embedding import embed_text, _embedding_backend
from .metadata_extract import extract_metadata
from .schemas import RetrievalResult, RetrievalCandidate, ValidationError
from .utils.logging import logger
from .utils.metrics import timer
from .vector_store.doc_filter import normalize_doc_filter
from .vector_store.factory import get_default_vector_store


def _validate_query(query_text: str) -> None:
    if not query_text or not query_text.strip():
        raise ValidationError(path="query", msg="Query text is required")


def _require_app_id(filters: Dict[str, str]) -> str:
    app_id = str((filters or {}).get("app_id", "")).strip()
    if not app_id:
        raise ValidationError(path="filters.app_id", msg="app_id is required for retrieval isolation")
    return app_id


def _normalize_filename_for_filter(value: str) -> str:
    return " ".join(str(value or "").strip().split()).lower()


def _as_filename_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if "," in raw:
            return [p.strip() for p in raw.split(",") if p.strip()]
        return [raw]
    if isinstance(value, (list, tuple, set)):
        out = []
        for item in value:
            s = str(item).strip()
            if s:
                out.append(s)
        return out
    s = str(value).strip()
    return [s] if s else []


def _split_query_filters(filters: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, Any]]:
    metadata_filters: Dict[str, str] = {}
    raw = dict(filters or {})

    doc_filter_raw: Dict[str, Any] = {}
    if "doc_id" in raw:
        doc_filter_raw["doc_id"] = raw.pop("doc_id")

    filename_norm = str(raw.pop("filename_norm", "") or "").strip()
    filename = str(raw.pop("filename", "") or "").strip()
    filename_in = _as_filename_list(raw.pop("filename_in", None))

    if filename_norm:
        doc_filter_raw["filename_norm"] = filename_norm
    elif filename:
        doc_filter_raw["filename_norm"] = _normalize_filename_for_filter(filename)

    if filename_in:
        doc_filter_raw["filename_in_norm"] = [_normalize_filename_for_filter(v) for v in filename_in]

    for key, value in raw.items():
        if value is None:
            continue
        text = str(value).strip()
        if text:
            metadata_filters[key] = text

    return metadata_filters, normalize_doc_filter(doc_filter_raw)


def _rrf(rank: int, k: int) -> float:
    return 1.0 / (k + rank)


def _fusion(
    semantic: List[Tuple[RetrievalCandidate, int]],
    metadata: List[Tuple[RetrievalCandidate, int]],
    lexical: List[Tuple[RetrievalCandidate, int]],
    fusion_k: int,
    semantic_weight: float,
    metadata_weight: float,
    lexical_weight: float,
) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for cand, rank in semantic:
        scores[cand.chunk.chunk_id] = scores.get(cand.chunk.chunk_id, 0.0) + (_rrf(rank + 1, fusion_k) * semantic_weight)
    for cand, rank in metadata:
        scores[cand.chunk.chunk_id] = scores.get(cand.chunk.chunk_id, 0.0) + (_rrf(rank + 1, fusion_k) * metadata_weight)
    for cand, rank in lexical:
        scores[cand.chunk.chunk_id] = scores.get(cand.chunk.chunk_id, 0.0) + (_rrf(rank + 1, fusion_k) * lexical_weight)
    return scores


def _source_map(
    semantic: List[Tuple[RetrievalCandidate, int]],
    metadata: List[Tuple[RetrievalCandidate, int]],
    lexical: List[Tuple[RetrievalCandidate, int]],
) -> Dict[str, str]:
    source_map: Dict[str, str] = {}
    semantic_ids = {cand.chunk.chunk_id for cand, _ in semantic}
    metadata_ids = {cand.chunk.chunk_id for cand, _ in metadata}
    lexical_ids = {cand.chunk.chunk_id for cand, _ in lexical}
    all_ids = semantic_ids | metadata_ids | lexical_ids
    for chunk_id in all_ids:
        in_sem = chunk_id in semantic_ids
        in_meta = chunk_id in metadata_ids
        in_lex = chunk_id in lexical_ids
        if sum(1 for b in (in_sem, in_meta, in_lex) if b) > 1:
            source_map[chunk_id] = "hybrid"
        elif in_sem:
            source_map[chunk_id] = "semantic"
        elif in_lex:
            source_map[chunk_id] = "lexical"
        else:
            source_map[chunk_id] = "metadata"
    return source_map


def _select_best_versions(candidates: List[RetrievalCandidate]) -> List[RetrievalCandidate]:
    # Keep chunk-level ranking; do not collapse all chunks into a single hit per doc_id.
    # App/version isolation is enforced elsewhere, and callers usually want top chunks.
    return candidates


def _apply_doc_diversity_cap(candidates: List[RetrievalCandidate], max_chunks_per_doc: int) -> List[RetrievalCandidate]:
    if max_chunks_per_doc <= 0:
        return candidates
    per_doc: Dict[str, int] = {}
    selected: List[RetrievalCandidate] = []
    for cand in candidates:
        doc_id = cand.chunk.doc_id
        taken = per_doc.get(doc_id, 0)
        if taken >= max_chunks_per_doc:
            continue
        selected.append(cand)
        per_doc[doc_id] = taken + 1
    return selected


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
    filters: Dict[str, Any] | None = None,
    config: RetrievalConfig = DEFAULT_RETRIEVAL_CONFIG,
    store=None,
) -> RetrievalResult:
    if store is None:
        store = get_default_vector_store()
    original_filters = dict(filters or {})
    filters = filters or {}
    debug: Dict[str, any] = {"timing": {}}
    with timer(debug["timing"], "validate"):
        _validate_query(query_text)
    with timer(debug["timing"], "metadata_extract"):
        extracted_filters, meta_info = extract_metadata(query_text)
    merged_filters: Dict[str, Any] = {**extracted_filters, **filters}
    app_id = _require_app_id(merged_filters)
    merged_filters["app_id"] = app_id
    metadata_filters, doc_filter = _split_query_filters(merged_filters)
    metadata_filters["app_id"] = app_id
    with timer(debug["timing"], "language_detect"):
        language = detect_language(query_text)
    with timer(debug["timing"], "routing"):
        route_info = route(language)
    scoped_namespace = f"{app_id}:{route_info.namespace}"
    with timer(debug["timing"], "embed"):
        query_embedding = embed_text(query_text, route_info.model)

    semantic_candidates: List[Tuple[RetrievalCandidate, int]] = []
    metadata_candidates: List[Tuple[RetrievalCandidate, int]] = []
    lexical_candidates: List[Tuple[RetrievalCandidate, int]] = []

    with timer(debug["timing"], "metadata_search"):
        if store:
            meta_results = store.metadata_search(
                metadata_filters,
                scoped_namespace,
                config.candidate_k,
                app_id=app_id,
                doc_filter=doc_filter,
            )
        else:
            meta_results = []
        for chunk, score in meta_results:
            metadata_candidates.append(
                (
                    RetrievalCandidate(chunk=chunk, score=score, source="metadata"),
                    len(metadata_candidates),
                )
            )
    with timer(debug["timing"], "semantic_search"):
        try:
            if store:
                sem_results = store.semantic_search(
                    query_embedding,
                    scoped_namespace,
                    config.candidate_k,
                    app_id=app_id,
                    doc_filter=doc_filter,
                )
            else:
                sem_results = []
        except Exception as exc:
            sem_results = []
            debug["semantic_search_error"] = str(exc)
            logger.warning("Semantic search failed, using metadata-only candidates: %s", exc)
        for chunk, score in sem_results:
            semantic_candidates.append(
                (
                    RetrievalCandidate(chunk=chunk, score=score, source="semantic"),
                    len(semantic_candidates),
                )
            )
    with timer(debug["timing"], "lexical_search"):
        if store and hasattr(store, "lexical_search"):
            lex_results = store.lexical_search(
                query_text,
                scoped_namespace,
                config.lexical_candidate_k,
                app_id=app_id,
                doc_filter=doc_filter,
            )
        else:
            lex_results = []
        for chunk, score in lex_results:
            lexical_candidates.append(
                (
                    RetrievalCandidate(chunk=chunk, score=score, source="lexical"),
                    len(lexical_candidates),
                )
            )

    fusion_scores = _fusion(
        semantic_candidates,
        metadata_candidates,
        lexical_candidates,
        config.fusion_k,
        semantic_weight=config.semantic_weight,
        metadata_weight=config.metadata_weight,
        lexical_weight=config.lexical_weight,
    )
    sources = _source_map(semantic_candidates, metadata_candidates, lexical_candidates)
    ranked_ids = sorted(fusion_scores.items(), key=lambda x: x[1], reverse=True)
    ranked_candidates: List[RetrievalCandidate] = []
    rank_lookup = {cid: score for cid, score in ranked_ids}
    all_candidates: Dict[str, RetrievalCandidate] = {}
    for cand, _ in semantic_candidates + metadata_candidates + lexical_candidates:
        existing = all_candidates.get(cand.chunk.chunk_id)
        if existing is None or existing.source != "semantic":
            all_candidates[cand.chunk.chunk_id] = cand
    for chunk_id, _ in ranked_ids:
        chosen = all_candidates[chunk_id]
        ranked_candidates.append(RetrievalCandidate(chunk=chosen.chunk, score=chosen.score, source=sources[chunk_id]))
    ranked_candidates = _select_best_versions(ranked_candidates)
    ranked_candidates = _apply_doc_diversity_cap(ranked_candidates, config.max_chunks_per_doc)
    final_results = ranked_candidates[:top_k]

    debug.update(
        {
            "semantic_candidates": [(c.chunk.chunk_id, s) for c, s in semantic_candidates],
            "metadata_candidates": [(c.chunk.chunk_id, s) for c, s in metadata_candidates],
            "lexical_candidates": [(c.chunk.chunk_id, s) for c, s in lexical_candidates],
            "fusion_scores": rank_lookup,
            "language": language,
            "route": {**route_info.__dict__, "namespace": scoped_namespace},
            "embedding_backend": _embedding_backend(),
            "original_filters": original_filters,
            "filters": merged_filters,
            "normalized_metadata_filters": metadata_filters,
            "normalized_doc_filter": doc_filter,
            "semantic_pre_scoped": bool(doc_filter),
            "weights": {
                "semantic": config.semantic_weight,
                "metadata": config.metadata_weight,
                "lexical": config.lexical_weight,
            },
            "max_chunks_per_doc": config.max_chunks_per_doc,
        }
    )

    return RetrievalResult(query=query_text, results=final_results, debug=debug)
