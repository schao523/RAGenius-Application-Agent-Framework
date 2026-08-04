"""Hashing helpers."""
from __future__ import annotations
import hashlib


def compute_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
