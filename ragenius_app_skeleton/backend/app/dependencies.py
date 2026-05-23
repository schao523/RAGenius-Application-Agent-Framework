"""Dependency placeholders for FastAPI routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException


def require_admin(x_role: Annotated[str | None, Header()] = None) -> str:
    """TODO: Replace header-based role check with real authN/authZ integration."""
    if x_role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return x_role


def get_settings() -> dict:
    """TODO: Replace with typed settings model loaded from env/config files."""
    return {}

