"""Embedding utilities with deterministic hashing-backed vectors."""
from __future__ import annotations
import hashlib
from typing import List


def embed_text(text: str, model: str) -> List[float]:
    seed = hashlib.sha256((model + "::" + text).encode("utf-8")).digest()
    # produce 8 floats deterministic between 0 and 1
    return [int.from_bytes(seed[i : i + 4], "big") % 1000 / 1000.0 for i in range(0, 32, 4)]
