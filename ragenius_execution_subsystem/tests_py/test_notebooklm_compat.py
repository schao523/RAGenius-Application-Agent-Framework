from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_compat_module():
    compat_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "notebooklm_compat.py"
    )
    spec = importlib.util.spec_from_file_location("test_notebooklm_compat", compat_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def notebooklm_policy_snapshot():
    import notebooklm._env as notebooklm_env
    import notebooklm.auth as public_auth
    from notebooklm._auth import cookie_policy
    from notebooklm.cli.services.login import cookie_domains

    snapshot = {
        "hosts": notebooklm_env._ALLOWED_BASE_HOSTS,
        "required": cookie_policy.REQUIRED_COOKIE_DOMAINS,
        "allowed": cookie_policy.ALLOWED_COOKIE_DOMAINS,
        "public_required": public_auth.REQUIRED_COOKIE_DOMAINS,
        "public_allowed": public_auth.ALLOWED_COOKIE_DOMAINS,
        "login_required": cookie_domains.REQUIRED_COOKIE_DOMAINS,
    }
    yield notebooklm_env, cookie_policy, public_auth, cookie_domains
    notebooklm_env._ALLOWED_BASE_HOSTS = snapshot["hosts"]
    cookie_policy.REQUIRED_COOKIE_DOMAINS = snapshot["required"]
    cookie_policy.ALLOWED_COOKIE_DOMAINS = snapshot["allowed"]
    public_auth.REQUIRED_COOKIE_DOMAINS = snapshot["public_required"]
    public_auth.ALLOWED_COOKIE_DOMAINS = snapshot["public_allowed"]
    cookie_domains.REQUIRED_COOKIE_DOMAINS = snapshot["login_required"]


def test_activates_exact_renamed_host_across_endpoint_and_cookie_aliases(
    monkeypatch, notebooklm_policy_snapshot
):
    notebooklm_env, cookie_policy, public_auth, cookie_domains = (
        notebooklm_policy_snapshot
    )
    monkeypatch.setenv("NOTEBOOKLM_BASE_URL", " https://notebook.google.com/ ")
    compat = _load_compat_module()

    activated = compat.activate_renamed_host_compatibility()

    assert activated is True
    assert notebooklm_env.get_base_url() == "https://notebook.google.com"
    for domain in {"notebook.google.com", ".notebook.google.com"}:
        assert domain in cookie_policy.REQUIRED_COOKIE_DOMAINS
        assert domain in cookie_policy.ALLOWED_COOKIE_DOMAINS
        assert domain in public_auth.REQUIRED_COOKIE_DOMAINS
        assert domain in public_auth.ALLOWED_COOKIE_DOMAINS
        assert domain in cookie_domains.REQUIRED_COOKIE_DOMAINS


@pytest.mark.parametrize(
    "base_url",
    [None, "", "https://notebooklm.google.com", "https://notebooklm.cloud.google.com"],
)
def test_leaves_supported_and_unset_hosts_unchanged(
    monkeypatch, notebooklm_policy_snapshot, base_url
):
    notebooklm_env, cookie_policy, _, _ = notebooklm_policy_snapshot
    if base_url is None:
        monkeypatch.delenv("NOTEBOOKLM_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("NOTEBOOKLM_BASE_URL", base_url)
    original_hosts = notebooklm_env._ALLOWED_BASE_HOSTS
    original_required = cookie_policy.REQUIRED_COOKIE_DOMAINS
    compat = _load_compat_module()

    activated = compat.activate_renamed_host_compatibility()

    assert activated is False
    assert notebooklm_env._ALLOWED_BASE_HOSTS == original_hosts
    assert cookie_policy.REQUIRED_COOKIE_DOMAINS == original_required


def test_untrusted_host_remains_rejected(monkeypatch, notebooklm_policy_snapshot):
    notebooklm_env, _, _, _ = notebooklm_policy_snapshot
    monkeypatch.setenv("NOTEBOOKLM_BASE_URL", "https://evil.example")
    compat = _load_compat_module()

    activated = compat.activate_renamed_host_compatibility()

    assert activated is False
    with pytest.raises(ValueError, match="NOTEBOOKLM_BASE_URL"):
        notebooklm_env.get_base_url()


def test_renamed_host_uses_navigation_commit_for_stable_playwright_wait(
    monkeypatch, notebooklm_policy_snapshot
):
    import playwright.sync_api as playwright_sync

    calls = []

    def fake_wait_for_url(page, url, **kwargs):
        calls.append((page, url, kwargs))
        return "detected"

    monkeypatch.setattr(playwright_sync.Page, "wait_for_url", fake_wait_for_url)
    monkeypatch.setenv("NOTEBOOKLM_BASE_URL", "https://notebook.google.com")
    compat = _load_compat_module()
    compat.activate_renamed_host_compatibility()

    result = playwright_sync.Page.wait_for_url(
        object(), "https://notebook.google.com/**", timeout=300_000
    )

    assert result == "detected"
    assert calls[0][2]["wait_until"] == "commit"


def test_powershell_wrapper_delegates_to_repository_compat_launcher():
    wrapper_path = (
        Path(__file__).resolve().parents[1] / "scripts" / "notebooklm_with_env.ps1"
    )
    wrapper = wrapper_path.read_text(encoding="utf-8")

    assert "RAGENIUS_NOTEBOOKLM_COMPAT_SCRIPT" in wrapper
    assert "runpy.run_path" in wrapper
    assert "notebooklm_compat.py" in wrapper
