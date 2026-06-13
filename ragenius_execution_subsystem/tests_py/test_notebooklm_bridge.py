from __future__ import annotations

import importlib.util
import os
import shutil
import uuid
from pathlib import Path


def _load_bridge_module():
    bridge_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "notebooklm_bridge.py"
    )
    spec = importlib.util.spec_from_file_location("test_notebooklm_bridge", bridge_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sanitize_proxy_environment_removes_dead_local_proxy(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:9")

    bridge = _load_bridge_module()

    removed = bridge._sanitize_proxy_environment()

    assert set(bridge.REMOVED_PROXY_VARS) >= {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}
    assert removed == []
    assert os.getenv("HTTP_PROXY") is None
    assert os.getenv("HTTPS_PROXY") is None
    assert os.getenv("ALL_PROXY") is None


def test_sanitize_proxy_environment_preserves_valid_proxy(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.example:8080")

    bridge = _load_bridge_module()

    removed = bridge._sanitize_proxy_environment()

    assert removed == []
    assert os.getenv("HTTP_PROXY") == "http://proxy.example:8080"


def test_sanitize_proxy_environment_removes_dead_socks_proxy(monkeypatch):
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:9")

    bridge = _load_bridge_module()

    removed = bridge._sanitize_proxy_environment()

    assert removed == []
    assert os.getenv("ALL_PROXY") is None


def test_sanitize_proxy_environment_honors_allow_system_proxy(monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("NOTEBOOKLM_ALLOW_SYSTEM_PROXY", "true")

    bridge = _load_bridge_module()

    removed = bridge._sanitize_proxy_environment()

    assert removed == []
    assert os.getenv("HTTP_PROXY") == "http://127.0.0.1:9"


def test_resolve_client_from_storage_options_prefers_profile(monkeypatch):
    monkeypatch.setenv("NOTEBOOKLM_AUTH_MODE", "profile")
    monkeypatch.setenv("NOTEBOOKLM_PROFILE", "default")

    bridge = _load_bridge_module()

    options, temp_path = bridge._resolve_client_from_storage_options()

    assert options == {"profile": "default"}
    assert temp_path is None


def test_resolve_client_from_storage_options_uses_storage_path(monkeypatch):
    monkeypatch.setenv("NOTEBOOKLM_AUTH_MODE", "storage_path")
    monkeypatch.setenv("NOTEBOOKLM_STORAGE_PATH", r"C:\Users\User\.notebooklm\profiles\work\storage_state.json")

    bridge = _load_bridge_module()

    options, temp_path = bridge._resolve_client_from_storage_options()

    assert options == {"path": r"C:\Users\User\.notebooklm\profiles\work\storage_state.json"}
    assert temp_path is None


def test_safe_source_filename_uses_requested_title_and_original_extension():
    bridge = _load_bridge_module()

    filename = bridge._safe_source_filename(
        'Reviewed: Micah/Observation?',
        r"storage\artifacts\app\chat_export\artifact_123-session-chat-export.md",
    )

    assert filename == "Reviewed- Micah-Observation-.md"


def test_prepare_titled_upload_path_copies_artifact_to_readable_filename():
    bridge = _load_bridge_module()
    tmp_path = (
        Path(__file__).resolve().parents[1]
        / ".test_tmp"
        / f"notebooklm_bridge_{uuid.uuid4().hex}"
    )
    tmp_path.mkdir(parents=True)
    artifact_file = tmp_path / "artifact_123-session-chat-export.md"
    artifact_file.write_text("# Exported chat", encoding="utf-8")

    try:
        upload_path, temp_upload_dir = bridge._prepare_titled_upload_path(
            str(artifact_file),
            "My Reviewed Source",
        )

        assert Path(upload_path).name == "My Reviewed Source.md"
        assert Path(upload_path).read_text(encoding="utf-8") == "# Exported chat"
        assert Path(upload_path) != artifact_file
    finally:
        if "temp_upload_dir" in locals():
            assert temp_upload_dir is not None
            temp_upload_dir.cleanup()
        shutil.rmtree(tmp_path, ignore_errors=True)
