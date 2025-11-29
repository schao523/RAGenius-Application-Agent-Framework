"""Utility metrics helpers."""
from __future__ import annotations
import time
from contextlib import contextmanager
from typing import Dict


@contextmanager
def timer(metrics: Dict[str, float], key: str):
    start = time.time()
    try:
        yield
    finally:
        metrics[key] = time.time() - start
