"""Quality filtering for chunks."""
from __future__ import annotations
import re
from typing import Dict, List, Tuple
from .config import ProcessConfig


def _is_boilerplate(text: str, patterns: List[str]) -> bool:
    lowered = text.strip().lower()
    return any(re.search(pat, lowered) for pat in patterns)


def _jaccard_similarity(a: str, b: str) -> float:
    set_a = set(a.split())
    set_b = set(b.split())
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
        token_count = len(text.split())
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
