"""Quality filtering for chunks."""
from __future__ import annotations
import re
from typing import Dict, List, Tuple
from .config import ProcessConfig

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _tokenize_for_quality(text: str) -> List[str]:
    stripped = text or ""
    if _CJK_RE.search(stripped):
        return [ch for ch in stripped if not ch.isspace()]
    return stripped.split()


def _is_boilerplate(text: str, patterns: List[str]) -> bool:
    lowered = text.strip().lower()
    return any(re.search(pat, lowered) for pat in patterns)


def _jaccard_similarity(a: str, b: str) -> float:
    set_a = set(_tokenize_for_quality(a))
    set_b = set(_tokenize_for_quality(b))
    if not set_a and not set_b:
        return 1.0
    return len(set_a & set_b) / max(1, len(set_a | set_b))


def filter_chunks(chunks: List[dict], config: ProcessConfig) -> Tuple[List[dict], Dict[str, int]]:
    kept: List[dict] = []
    skipped_too_short = 0
    skipped_boilerplate = 0
    skipped_near_dup = 0

    for chunk in chunks:
        text = chunk["text"].strip()
        token_count = len(_tokenize_for_quality(text))
        if token_count < config.min_chunk_length:
            skipped_too_short += 1
            continue
        if _is_boilerplate(text, config.boilerplate_patterns):
            skipped_boilerplate += 1
            continue
        duplicate_found = False
        for prior in kept:
            if _jaccard_similarity(text, prior["text"].strip()) >= config.near_dup_threshold:
                duplicate_found = True
                break
        if duplicate_found:
            skipped_near_dup += 1
            continue
        kept.append(chunk)
    return kept, {
        "skipped_too_short_count": skipped_too_short,
        "skipped_boilerplate_count": skipped_boilerplate,
        "skipped_near_dup_count": skipped_near_dup,
    }
