"""Configuration objects for the RAG subsystem."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ProcessConfig:
    chunk_size: int = 400
    chunk_overlap: int = 60
    section_token_threshold: int = 1200
    min_chunk_length: int = 30
    boilerplate_patterns: List[str] = None
    near_dup_threshold: float = 0.95
    retry_upsert: int = 1

    def __post_init__(self) -> None:
        if self.boilerplate_patterns is None:
            self.boilerplate_patterns = [
                r"^\s*$",
                r"^page \d+ of \d+",
                r"all rights reserved",
                r"copyright",
            ]


@dataclass
class RetrievalConfig:
    candidate_k: int = 50
    fusion_k: int = 60
    top_k: int = 10
    semantic_weight: float = 1.0
    metadata_weight: float = 1.0
    lexical_weight: float = 1.5
    lexical_candidate_k: int = 50
    max_chunks_per_doc: int = 3


DEFAULT_PROCESS_CONFIG = ProcessConfig()
DEFAULT_RETRIEVAL_CONFIG = RetrievalConfig()
