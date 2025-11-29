"""Embedding router selecting model and namespace by language."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class EmbeddingRoute:
    language: str
    model: str
    namespace: str


def route(language: str) -> EmbeddingRoute:
    lang = language.lower()
    if lang.startswith("zh"):
        return EmbeddingRoute(language="zh", model="bge-large-zh", namespace="zh:bge-large-zh")
    return EmbeddingRoute(language="en", model="e5-large", namespace="en:e5-large")
