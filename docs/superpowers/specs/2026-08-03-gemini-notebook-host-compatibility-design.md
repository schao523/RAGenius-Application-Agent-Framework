# Gemini Notebook Host Compatibility Design

## Status

Approved for implementation on 2026-08-03.

## Problem

Google redirects this account from `notebooklm.google.com` to the renamed personal-product host `notebook.google.com`. `notebooklm-py` 0.7.3 and 0.8.0rc1 reject that host in their endpoint and cookie allowlists, so browser login can succeed while CLI login detection waits for five minutes and never persists usable authentication.

## Decision

RAGenius will provide a repository-controlled Python launcher shim. When and only when `NOTEBOOKLM_BASE_URL` is exactly `https://notebook.google.com`, the shim adds `notebook.google.com` to the installed package's endpoint allowlist and adds dotted and non-dotted forms to its required and allowed cookie-domain sets. It then invokes the installed `notebooklm` module normally.

The existing PowerShell wrapper remains responsible for selecting Python and injecting Windows trust-store support. It delegates CLI execution to the shim. Unset, legacy personal, enterprise, malformed, and untrusted endpoint values receive no compatibility expansion and remain subject to `notebooklm-py` validation.

## Boundaries

- Do not edit global `site-packages`.
- Do not copy authentication files into the repository.
- Do not weaken validation for arbitrary Google or non-Google hosts.
- Keep the workaround removable when upstream supports `notebook.google.com`.
- Preserve all existing NotebookLM CLI arguments and exit codes.

## Verification

- Unit tests prove exact-host activation, no-op behavior, and fail-closed behavior.
- Existing NotebookLM bridge tests remain green.
- Live validation requires `token_fetch: true` and a successful read-only notebook listing.
- The Codex/NotebookLM live smoke remains the final external-write acceptance gate.
