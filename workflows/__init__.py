"""Compatibility package for tests importing `workflows.*` from repo root."""

from ragenius_app_skeleton import workflows as _workflows

__path__ = _workflows.__path__
