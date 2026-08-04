"""Minimal local .env bootstrap for desktop/dev runs.

This avoids hidden dependence on the caller's shell environment while keeping
production behavior simple: existing environment variables always win.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


DEFAULT_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def _iter_env_lines(env_path: Path) -> Iterable[tuple[str, str]]:
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        yield key, value.strip()


def bootstrap_local_env(*, env_path: Path | None = None) -> list[str]:
    import os

    target = Path(env_path or DEFAULT_ENV_PATH)
    if not target.exists():
        return []
    loaded: list[str] = []
    for key, value in _iter_env_lines(target):
        if os.environ.get(key) is not None:
            continue
        os.environ[key] = value
        loaded.append(key)
    return loaded
