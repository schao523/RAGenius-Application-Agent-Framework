from __future__ import annotations

import os
import runpy
import sys
from functools import wraps


RENAMED_NOTEBOOK_BASE_URL = "https://notebook.google.com"
RENAMED_NOTEBOOK_HOST = "notebook.google.com"
RENAMED_NOTEBOOK_COOKIE_DOMAINS = frozenset(
    {RENAMED_NOTEBOOK_HOST, f".{RENAMED_NOTEBOOK_HOST}"}
)


def _normalized_base_url(value: str | None) -> str:
    return (value or "").strip().rstrip("/")


def _activate_playwright_navigation_compatibility() -> None:
    try:
        from playwright.sync_api import Page
    except ImportError:
        return

    current = Page.wait_for_url
    if getattr(current, "_ragenius_notebook_host_compat", False):
        return

    @wraps(current)
    def wait_for_url_at_commit(page, url, *args, **kwargs):
        if str(url) == f"{RENAMED_NOTEBOOK_BASE_URL}/**":
            kwargs.setdefault("wait_until", "commit")
        return current(page, url, *args, **kwargs)

    wait_for_url_at_commit._ragenius_notebook_host_compat = True
    Page.wait_for_url = wait_for_url_at_commit


def activate_renamed_host_compatibility(base_url: str | None = None) -> bool:
    requested = _normalized_base_url(
        os.environ.get("NOTEBOOKLM_BASE_URL") if base_url is None else base_url
    )
    if requested != RENAMED_NOTEBOOK_BASE_URL:
        return False

    import notebooklm._env as notebooklm_env
    import notebooklm.auth as public_auth
    from notebooklm._auth import cookie_policy
    from notebooklm.cli.services.login import cookie_domains

    notebooklm_env._ALLOWED_BASE_HOSTS = frozenset(
        {*notebooklm_env._ALLOWED_BASE_HOSTS, RENAMED_NOTEBOOK_HOST}
    )
    required = frozenset(
        {*cookie_policy.REQUIRED_COOKIE_DOMAINS, *RENAMED_NOTEBOOK_COOKIE_DOMAINS}
    )
    allowed = frozenset(
        {*cookie_policy.ALLOWED_COOKIE_DOMAINS, *RENAMED_NOTEBOOK_COOKIE_DOMAINS}
    )
    cookie_policy.REQUIRED_COOKIE_DOMAINS = required
    cookie_policy.ALLOWED_COOKIE_DOMAINS = allowed
    public_auth.REQUIRED_COOKIE_DOMAINS = required
    public_auth.ALLOWED_COOKIE_DOMAINS = allowed
    cookie_domains.REQUIRED_COOKIE_DOMAINS = required
    _activate_playwright_navigation_compatibility()
    return True


def main() -> None:
    activate_renamed_host_compatibility()
    sys.argv = ["notebooklm", *sys.argv[1:]]
    runpy.run_module("notebooklm", run_name="__main__")


if __name__ == "__main__":
    main()
