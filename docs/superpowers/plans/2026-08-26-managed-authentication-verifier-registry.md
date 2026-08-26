# Managed Authentication Verifier Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a trusted managed-authentication verifier registry and verify Codex Gmail authentication through a non-mutating probe on the exact live Codex thread.

**Architecture:** The execution composition root installs immutable trusted verifier implementations. `CodexAppServerAdapter` supplies a restricted same-thread MCP verification facade, and the Gmail verifier checks `codex_apps` before calling the fixed read-only `gmail.get_profile` tool. Runtime configuration can reference verifier ids but cannot define verifier behavior.

**Tech Stack:** TypeScript, Node.js, Zod, Codex app-server JSON-RPC, Node test runner

**Spec:** `docs/superpowers/specs/2026-08-26-managed-authentication-verifier-registry-design.md`

## Global Constraints

- Keep all runtime behavior in `ragenius_execution_subsystem`.
- Do not use `GMAIL_MCP_ACCESS_TOKEN` to verify Codex authentication.
- Bind every verification operation to the protected active Codex `threadId`.
- Do not log or persist MCP profile content, credentials, URLs, or raw provider errors.
- Keep authentication handoff disabled unless both the feature flag and an eligible managed target are configured.
- Do not permit runtime-loaded verifier code, commands, server names, tools, or probe arguments.

---

### Task 1: Immutable Trusted Verifier Registry

**Files:**
- Create: `ragenius_execution_subsystem/src/core/interactive/managed-authentication-verifier-registry.ts`
- Create: `ragenius_execution_subsystem/tests/interactive/managed-authentication-verifier-registry.test.ts`
- Modify: `ragenius_execution_subsystem/src/core/interactive/codex-managed-auth-targets.ts`

**Interfaces:**
- Consumes: existing `ManagedAuthenticationVerifier`.
- Produces: `ManagedAuthenticationVerifierRegistry`, `ManagedAuthenticationVerificationContext`, and bounded Codex MCP verification facade types.

- [ ] **Step 1: Write failing tests for unique registration, duplicate rejection, blank-id rejection, lookup, and read-only map exposure.**
- [ ] **Step 2: Run `npm test -- managed-authentication-verifier-registry.test.ts` and confirm failure because the registry does not exist.**
- [ ] **Step 3: Implement the minimal immutable registry and verification context types.**
- [ ] **Step 4: Re-run the focused test and confirm it passes.**
- [ ] **Step 5: Commit the registry deliverable.**

### Task 2: Codex Gmail Same-Thread Verifier

**Files:**
- Create: `ragenius_execution_subsystem/src/core/interactive/codex-gmail-authentication-verifier.ts`
- Create: `ragenius_execution_subsystem/tests/interactive/codex-gmail-authentication-verifier.test.ts`

**Interfaces:**
- Consumes: `ManagedAuthenticationVerifier` and `ManagedAuthenticationVerificationContext` from Task 1.
- Produces: `CodexGmailAuthenticationVerifier` with id `codex-apps-gmail-auth`.

- [ ] **Step 1: Write failing tests for successful `codex_apps`/`gmail.get_profile` verification and exact fixed probe arguments.**
- [ ] **Step 2: Add failing tests for unavailable context, missing server, unauthenticated status, missing tool, provider error, malformed result, and thrown transport errors.**
- [ ] **Step 3: Run `npm test -- codex-gmail-authentication-verifier.test.ts` and confirm failures because the verifier does not exist.**
- [ ] **Step 4: Implement the verifier with bounded diagnostics and no propagation of provider content.**
- [ ] **Step 5: Re-run both verifier test files and confirm they pass.**
- [ ] **Step 6: Commit the Gmail verifier deliverable.**

### Task 3: Protected Codex MCP Verification Facade

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/interactive/codex-app-server-adapter.ts`
- Modify: `ragenius_execution_subsystem/tests/interactive/codex-app-server-adapter.test.ts`

**Interfaces:**
- Consumes: the verification context from Task 1.
- Produces: a facade that invokes `mcpServerStatus/list` and `mcpServer/tool/call` with the protected active `threadId`.

- [ ] **Step 1: Write a failing adapter test asserting the verifier receives `backend: "codex_cli"` and that both MCP requests use the protected thread id.**
- [ ] **Step 2: Write failing tests asserting an absent thread, malformed status response, and MCP error result fail closed with bounded diagnostics.**
- [ ] **Step 3: Run `npm test -- codex-app-server-adapter.test.ts` and confirm the new assertions fail.**
- [ ] **Step 4: Build the restricted facade in the adapter and pass it to verifier calls without exposing the raw transport.**
- [ ] **Step 5: Re-run adapter and managed-authentication tests and confirm they pass.**
- [ ] **Step 6: Commit the protected-facade deliverable.**

### Task 4: Production Composition And Safe Defaults

**Files:**
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Modify: `ragenius_execution_subsystem/tests/app.test.ts`
- Modify: `ragenius_execution_subsystem/tests/config/runtime-config.test.ts`

**Interfaces:**
- Consumes: `ManagedAuthenticationVerifierRegistry` and `CodexGmailAuthenticationVerifier`.
- Produces: a production `CodexAppServerAdapter` configured with the trusted registry map.

- [ ] **Step 1: Write a failing composition test showing `codex-apps-gmail-auth` makes a matching configured target eligible.**
- [ ] **Step 2: Write a failing regression test showing absent feature flag or absent target still suppresses authentication handoff.**
- [ ] **Step 3: Run the focused app/config tests and confirm the registration assertion fails.**
- [ ] **Step 4: Register the Gmail verifier in `createApp` and pass the registry map to the adapter.**
- [ ] **Step 5: Re-run focused composition, config, and adapter tests.**
- [ ] **Step 6: Commit the production wiring deliverable.**

### Task 5: Documentation And Verification

**Files:**
- Modify: `ragenius_execution_subsystem/docs/codex-interactive-agent-operations.md`
- Modify: `ragenius_execution_subsystem/docs/codex-interactive-mcp-live-results-2026-08-25.md`
- Modify: `docs/docs-inventory.md`

**Interfaces:**
- Consumes: completed implementation and test evidence.
- Produces: operator configuration guidance and a live Gmail acceptance checklist.

- [ ] **Step 1: Document the built-in verifier id, required managed target, safe defaults, and the rule that verifiers are per credential domain rather than per tool.**
- [ ] **Step 2: Record the sanitized feasibility evidence and leave live handoff acceptance pending until explicitly run.**
- [ ] **Step 3: Run focused verifier and adapter tests.**
- [ ] **Step 4: Run `npm test`, `npm run typecheck`, and `npm run lint` in `ragenius_execution_subsystem`.**
- [ ] **Step 5: Review `git diff --check`, `git status --short`, and the final diff for secret or profile-data leakage.**
- [ ] **Step 6: Commit the documentation and verification evidence.**
