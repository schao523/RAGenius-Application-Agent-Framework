"""Metadata extraction stub."""
from __future__ import annotations
from typing import Dict, Tuple


def extract_metadata(query_text: str) -> Tuple[Dict, Dict]:
    # For deterministic behavior, no NLP; return empty filters and metadata
    return {}, {"query_length": len(query_text)}
