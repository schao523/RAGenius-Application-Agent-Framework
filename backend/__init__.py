"""Compatibility package for tests importing `backend.*` from repo root."""

from ragenius_app_skeleton import backend as _backend

__path__ = _backend.__path__
