# Agent Skill Discovery And Selection Verification

Use this checklist after configuring administrator-approved Codex and OpenClaw skill sources. Record no tokens, cookies, local protected paths, or provider credentials in committed evidence.

## Automated Gates

- [x] Execution: Prisma validate/generate, TypeScript typecheck, and full tests pass.
- [x] Builder: full `unittest` discovery passes.
- [x] App backend: full `pytest` suite passes.
- [x] App frontend: full Vitest suite and production build pass.

## Configuration

- [ ] Set distinct app and Builder service credentials in `RAGENIUS_EXECUTION_SERVICE_CREDENTIALS_JSON`.
- [ ] Give the app credential `agent_skills:read` and `artifacts:write`, and give the Builder credential `agent_skills:admin`.
- [ ] Set matching `AGENT_SKILL_TRUSTED_BUILDER_INSTANCE_ID` and `RAGENIUS_BUILDER_INSTANCE_ID` values.
- [ ] Configure only administrator-approved Codex directories and OpenClaw WSL targets.
- [ ] Enable asynchronous Agent execution and the provider CLI being tested.

## Synchronized Read Model

- [ ] Discover one read-only Codex skill and one read-only OpenClaw skill in Builder.
- [ ] Inspect each complete package fingerprint, approve that exact fingerprint, and bind it to one test app.
- [ ] Synchronize and record the acknowledged Builder instance, revision, and digest.
- [ ] Stop Builder and confirm Composer still lists both approved skills for the bound app.
- [ ] Run each selected skill asynchronously and record execution id, terminal status, and normalized activation evidence.
- [ ] Restart Builder, revoke or unbind one skill, synchronize, then stop Builder again.
- [ ] Confirm the revoked skill disappears without restarting the app or execution subsystem.
- [ ] Replay its old explicit id/fingerprint and confirm execution fails closed without Auto fallback.

## Isolation And Drift

- [ ] Confirm the bound skill is absent from a second app.
- [ ] Confirm app/browser responses contain no protected locator, Windows path, WSL package root, or provider metadata.
- [ ] Modify a supporting file in a test skill after approval.
- [ ] Confirm explicit execution fails with fingerprint drift before provider invocation.
- [ ] Restore the package, rediscover, explicitly approve the new fingerprint, synchronize, and retest.
- [ ] Confirm selection survives artifact input and expected-output composition.
- [ ] Confirm switching app, session, user, or backend resets selection to Auto.

## Live Smoke Command

Run once for each provider after Builder synchronization. Builder may be stopped for this test.

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
$env:AGENT_SKILL_SMOKE_BASE_URL = "http://127.0.0.1:3001/v1"
$env:AGENT_SKILL_SMOKE_SERVICE_TOKEN = "replace-app-token"
$env:AGENT_SKILL_SMOKE_APP_ID = "replace-app-id"
$env:AGENT_SKILL_SMOKE_SESSION_ID = "agent-skill-smoke"
$env:AGENT_SKILL_SMOKE_BACKEND = "codex_cli"
$env:AGENT_SKILL_SMOKE_ID = "replace-agent-skill-id"
$env:AGENT_SKILL_SMOKE_FINGERPRINT = "replace-approved-fingerprint"
$env:AGENT_SKILL_SMOKE_QUERY = "Read the selected skill instructions and return a concise summary. Do not write files or use the network."
npx tsx scripts/smoke-agent-skill-selection.ts
```

For a confirmed write test, set `AGENT_SKILL_SMOKE_AUTO_CONFIRM=true` only after reviewing the request. Repeat with `AGENT_SKILL_SMOKE_BACKEND=openclaw_cli` and the synchronized OpenClaw id/fingerprint.

## Evidence Record

Record outside committed configuration when it may contain local identifiers:

- Date and operator
- Execution, Builder, Codex, and OpenClaw versions
- Sanitized source/target labels
- Projection revision and digest prefix
- Selected skill ids and approved fingerprint prefixes
- Confirmation behavior
- Execution ids and terminal states
- Activation status and evidence level
- Drift, revocation, isolation, and offline-Builder outcomes
- Residual provider diagnostic limitations

## Acceptance Evidence: 2026-08-04

- Execution `0.1.0`, Codex CLI `0.146.0`, and OpenClaw `2026.6.8` were tested from the isolated feature worktree.
- Builder synchronized revision `1785832908957` and execution acknowledged the exact digest.
- Builder was stopped before both provider executions. Codex execution `execution_c2821c56e227` completed with `process_observed` evidence using `codex_explicit_reference`.
- OpenClaw execution `execution_4edcc35b320b` completed with `process_observed` evidence using `openclaw_prompt_guidance`.
- A synchronized OpenClaw revocation advanced the projection, removed the skill from inventory, and old explicit replay returned `409 AGENT_SKILL_NOT_BOUND`.
- A second app received zero bound Codex skills, and public inventory contained no protected locator or provider path.
- A disposable package change after approval returned `409 AGENT_SKILL_FINGERPRINT_CHANGED` before provider invocation.
- Live discovery exposed sequential OpenClaw package inspection as a timeout risk; bounded concurrency of four was added with regression coverage.
- Live publication exposed millisecond-scale Builder revisions exceeding PostgreSQL `INTEGER`; persistence was widened to `BIGINT` while API summaries remain JSON-safe numbers.
- Conservative policy matching treats write terms inside negated phrases as write risk. The smoke query therefore uses purely read-oriented wording; this is safe but may cause additional confirmations.
