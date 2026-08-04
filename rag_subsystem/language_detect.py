"""Simple language detection."""
from __future__ import annotations
import re


_CHINESE_RE = re.compile("[\u4e00-\u9fff]")


def detect_language(text: str) -> str:
    if _CHINESE_RE.search(text or ""):
        return "zh"
    return "en"
