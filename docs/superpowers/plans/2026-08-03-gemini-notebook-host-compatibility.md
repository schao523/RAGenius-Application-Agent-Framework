# Gemini Notebook Host Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow RAGenius NotebookLM commands to use Google's renamed `notebook.google.com` host without modifying global Python packages.

**Architecture:** A small Python launcher applies an exact-host compatibility expansion to `notebooklm-py` private endpoint and cookie allowlists, then executes the normal module. The existing PowerShell TLS wrapper calls this launcher and preserves arguments and exit status.

**Tech Stack:** Python 3.14, pytest, PowerShell, notebooklm-py 0.7.3+.

## Global Constraints

- Activate only for `NOTEBOOKLM_BASE_URL=https://notebook.google.com` after trimming whitespace and a trailing slash.
- Never add arbitrary hosts to authenticated endpoint or cookie allowlists.
- Never edit global `site-packages` or persist credentials in the repository.
- Preserve native package behavior when compatibility is inactive.
- Do not commit from the existing dirty worktree unless explicitly requested.

---

### Task 1: Compatibility Launcher

**Files:**
- Create: `ragenius_execution_subsystem/scripts/notebooklm_compat.py`
- Create: `ragenius_execution_subsystem/tests_py/test_notebooklm_compat.py`

**Interfaces:**
- Produces: `activate_renamed_host_compatibility(base_url: str | None = None) -> bool` and `main() -> None`.

- [x] Write tests proving exact-host activation updates endpoint and cookie aliases.
- [x] Write tests proving unset and legacy hosts are no-ops and an untrusted host remains rejected by the package.
- [x] Run the tests and verify they fail because the launcher does not exist.
- [x] Implement the minimum launcher and rerun the tests to green.

### Task 2: Wrapper And Configuration

**Files:**
- Modify: `ragenius_execution_subsystem/scripts/notebooklm_with_env.ps1`
- Modify: `ragenius_execution_subsystem/.env.example`
- Modify: `ragenius_execution_subsystem/README.md`

**Interfaces:**
- Consumes: `notebooklm_compat.py` and `NOTEBOOKLM_BASE_URL`.

- [x] Replace direct `run_module` bootstrap with delegation to the repository launcher while retaining trust-store injection.
- [x] Document the exact renamed-host environment value and temporary nature of the workaround.
- [x] Run Python tests, TypeScript regression tests, and wrapper help/auth checks.

### Task 3: Live Read-Only Validation

- [x] Run `auth check --test --json` and require `token_fetch: true`.
- [x] Run `list --json` and require the Testing notebook to be present.
- [x] Leave the external-write Codex smoke test as the next explicit acceptance step.
