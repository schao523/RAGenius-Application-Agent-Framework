# Codex Interactive Skill, Plugin, And MCP Interactions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task with review checkpoints.

**Goal:** Extend Codex Interactive Agent mode so MCP servers, instruction skills, and plugin guidance can request bounded provider-neutral interactions, while preserving secrets, policy scope, same-turn continuation, and authoritative operation outcomes.

**Architecture:** Keep the existing durable `AgentSession` and `AgentInteraction` state machine. Add version-gated Codex protocol decoders and managed dynamic tools at the execution boundary, persist only safe presentation metadata, retain provider request bindings and launch targets in protected process memory, proxy launches through scoped no-store service routes, and evaluate required operation evidence before terminal execution state is written. Builder remains unchanged and OpenClaw behavior remains untouched.

**Tech Stack:** TypeScript 5, Fastify 5, Zod 3, Prisma 6/PostgreSQL, Node test runner, Python/FastAPI, React 18, Vitest/Testing Library.

**Spec:** [`docs/codex-mcp-elicitation-interaction-addendum.md`](../../codex-mcp-elicitation-interaction-addendum.md)

## Global Constraints

- [ ] Keep all five new runtime settings disabled or empty by default.
- [ ] Do not add Gmail-specific, skill-specific, or plugin-specific adapter branches.
- [ ] Do not infer interactions from assistant prose.
- [ ] Never persist or log raw elicitation schemas, `_meta`, full authentication URLs, credentials, tokens, cookies, OTPs, provider request ids, or verifier internals.
- [ ] Keep `allowed_types` and `required_types` request metadata limited to `clarification` and `selection`; authentication and manual actions are runtime-driven.
- [ ] Do not add Builder schema, publication, or Composer skill-label changes in this milestone.
- [ ] Do not change OpenClaw capabilities, Gateway handling, staging, or follow-up behavior.
- [ ] Keep one provider response per interaction by using the existing version and idempotency claims.
- [ ] Preserve the current process-loss rule: a pending provider request is not resumable after execution-subsystem restart.
- [ ] Use test-driven development for every task: add a failing test, run it, implement the minimum change, rerun focused tests, then commit.

## Task 1: Add Fail-Closed Runtime Configuration

**Files:**

- Modify: `ragenius_execution_subsystem/src/config/env.ts`
- Modify: `ragenius_execution_subsystem/src/config/provider-config.ts`
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`
- Modify: `ragenius_execution_subsystem/tests/config/runtime-config.test.ts`
- Create: `ragenius_execution_subsystem/src/core/interactive/codex-managed-auth-targets.ts`
- Create: `ragenius_execution_subsystem/tests/interactive/codex-managed-auth-targets.test.ts`

### Steps

- [ ] Add failing tests proving these defaults:

  ```text
  CODEX_MCP_ELICITATION_ENABLED=false
  CODEX_INTERACTIVE_AUTH_HANDOFF_ENABLED=false
  CODEX_INTERACTIVE_USER_ACTION_ENABLED=false
  CODEX_MCP_AUTH_ALLOWED_HOSTS_JSON=[]
  CODEX_MANAGED_AUTH_TARGETS_JSON=[]
  ```

- [ ] Add tests that reject malformed JSON, duplicate target ids, wildcard hosts, uppercase/non-ASCII hosts, URL user-info, non-HTTPS URLs, URL fragments, and targets whose `allowedHosts` do not include the launch URL host.
- [ ] Define `CodexManagedAuthenticationTarget` and a Zod parser that accepts only the approved `https_url` and `provider_window` variants.
- [ ] Normalize host names once at configuration load and expose immutable arrays from `CodexAppServerProviderConfig`.
- [ ] Add a verifier registry interface:

  ```ts
  export interface ManagedAuthenticationVerifier {
    readonly id: string;
    verify(input: ManagedAuthenticationVerificationInput): Promise<{
      verified: boolean;
      diagnosticCode?: string;
    }>;
  }
  ```

- [ ] Treat a configured target as disabled unless its `verifierId` exists in the injected trusted registry. Do not ship a verifier that trusts user acknowledgement or model prose.
- [ ] Run:

  ```powershell
  cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
  npm run build
  node --experimental-test-isolation=none --test-concurrency=1 --test dist/tests/config/runtime-config.test.js dist/tests/interactive/codex-managed-auth-targets.test.js
  ```

- [ ] Commit: `feat: add Codex interactive handoff configuration`

## Task 2: Persist Safe Interaction Presentation Metadata

**Files:**

- Modify: `ragenius_execution_subsystem/prisma/schema.prisma`
- Create: `ragenius_execution_subsystem/prisma/migrations/20260825_agent_interaction_presentation/migration.sql`
- Modify: `ragenius_execution_subsystem/src/core/interactive/interactive-agent-types.ts`
- Modify: `ragenius_execution_subsystem/src/core/interactive/interactive-agent-adapter.ts`
- Modify: `ragenius_execution_subsystem/src/core/interactive/agent-interaction-store.ts`
- Modify: `ragenius_execution_subsystem/src/core/interactive/prisma-agent-interaction-store.ts`
- Modify: `ragenius_execution_subsystem/src/core/interactive/interactive-agent-session-manager.ts`
- Modify: `ragenius_execution_subsystem/src/api/routes/interactive-agent.routes.ts`
- Modify: `ragenius_execution_subsystem/tests/interactive/interactive-agent-session-manager.test.ts`
- Modify: `ragenius_execution_subsystem/tests/api/interactive-agent-routes.test.ts`

### Steps

- [ ] Add failing store and route tests for an optional provider-neutral presentation object:

  ```ts
  type AgentInteractionPresentation = {
    targetLabel?: string;
    targetHost?: string;
    completionLabel?: string;
    launchAvailable?: boolean;
  };
  ```

- [ ] Add nullable `presentation Json?` to `AgentInteraction`; write the additive migration without changing existing rows.
- [ ] Extend `ProviderInteractionRequest` and `AgentInteractionRecord`; validate bounded labels and exact host values before persistence.
- [ ] Serialize the object as `presentation` in the execution API. Confirm public payloads still omit provider ids and protected launch values.
- [ ] Add a redaction regression test using a presentation object containing attempted `url`, `token`, and `providerRequestId` keys; reject the record instead of silently persisting those keys.
- [ ] Run Prisma validation and focused tests:

  ```powershell
  cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
  npx prisma validate
  npx prisma generate
  npm run build
  node --experimental-test-isolation=none --test-concurrency=1 --test dist/tests/interactive/interactive-agent-session-manager.test.js dist/tests/api/interactive-agent-routes.test.js
  ```

- [ ] Commit: `feat: persist safe Agent interaction presentation`

## Task 3: Decode And Classify MCP Elicitation

**Files:**

- Create: `ragenius_execution_subsystem/src/core/interactive/codex-mcp-elicitation.ts`
- Create: `ragenius_execution_subsystem/tests/interactive/codex-mcp-elicitation.test.ts`
- Modify: `ragenius_execution_subsystem/src/core/interactive/codex-app-server-codec.ts`

### Steps

- [ ] Build fixtures from generated Codex `0.146.0` bindings for `form`, `openai/form`, and `url` modes.
- [ ] Add failing tests for zero-field and one-boolean approval, one-enum selection, one-bounded-string clarification, and approved HTTPS authentication URL.
- [ ] Add rejection tests for secrets, multiple fields, arrays, numbers, nested objects, multi-select, unknown widgets, oversized prompts/options, scope mismatch, non-HTTPS URLs, URL user-info, and unapproved hosts.
- [ ] Implement `decodeCodexMcpElicitation(params, context)` returning the addendum's `NormalizedMcpElicitation` and a bounded public diagnostic on rejection.
- [ ] Require an authorization-bound active operation before classifying zero-field or boolean forms as approval. Bind against `threadId`, `turnId`, and `policy_binding_hash`.
- [ ] Keep the raw URL and property binding only in the returned protected structure. Public presentation contains label/host only.
- [ ] Implement exact response translators for accept, decline, cancel, selected enum value, and clarification text.
- [ ] Run:

  ```powershell
  cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
  npm run build
  node --experimental-test-isolation=none --test-concurrency=1 --test dist/tests/interactive/codex-mcp-elicitation.test.js
  ```

- [ ] Commit: `feat: decode bounded Codex MCP elicitation`

## Task 4: Add Managed Authentication And User-Action Tools

**Files:**

- Modify: `ragenius_execution_subsystem/src/core/interactive/codex-interaction-tool.ts`
- Modify: `ragenius_execution_subsystem/tests/interactive/codex-app-server-adapter.test.ts`
- Create: `ragenius_execution_subsystem/tests/interactive/codex-managed-interaction-tools.test.ts`

### Steps

- [ ] Add failing tests for the exact `ragenius_request_authentication_handoff` and `ragenius_request_user_action` schemas from the addendum.
- [ ] Export dynamic tool specs conditionally: input is always available for permitted clarification/selection; auth is available only with the auth feature flag and at least one eligible registry target; user action is available only with its feature flag.
- [ ] Parse authentication requests by target id only. Reject model-provided URLs, application paths, executable names, verifier ids, or extra fields.
- [ ] Reuse the existing secret-request detector across prompt, instruction, completion label, and option text.
- [ ] Generate trusted turn guidance listing only eligible target ids and administrator-defined labels.
- [ ] Normalize tool calls to `authentication_handoff` and `user_action_required` with protected response bindings and safe presentation metadata.
- [ ] Test that disabled flags remove both tool definitions and their turn guidance.
- [ ] Run:

  ```powershell
  cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
  npm run build
  node --experimental-test-isolation=none --test-concurrency=1 --test dist/tests/interactive/codex-managed-interaction-tools.test.js dist/tests/interactive/codex-app-server-adapter.test.js
  ```

- [ ] Commit: `feat: add managed Codex interaction tools`

## Task 5: Integrate Elicitation With The Codex App-Server Adapter

**Files:**

- Modify: `ragenius_execution_subsystem/src/core/interactive/codex-app-server-adapter.ts`
- Modify: `ragenius_execution_subsystem/src/core/interactive/interactive-agent-adapter.ts`
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Modify: `ragenius_execution_subsystem/tests/interactive/codex-app-server-adapter.test.ts`
- Modify: `ragenius_execution_subsystem/tests/interactive/interactive-agent-session-manager.test.ts`

### Steps

- [ ] Extend `PendingProviderRequest` to the addendum's response-binding union and include a protected launch target when applicable.
- [ ] Compute Codex capability advertisement from version plus enabled features; do not advertise auth or user-action support when disabled or ineligible.
- [ ] Add a failing adapter test where `mcpServer/elicitation/request` pauses the turn, emits one `interaction_requested`, accepts one response, and resumes the same JSON-RPC request exactly once.
- [ ] Add accept/deny/cancel tests for approval; selected-value and free-text translation tests; authentication-completed/cancelled tests; managed tool completion/cancellation tests.
- [ ] For managed authentication completion, invoke the trusted verifier before returning tool success. On a failed check, return the interaction to pending with a bumped version and bounded diagnostic when the request remains live; otherwise fail with `AUTHENTICATION_HANDOFF_NOT_VERIFIED`.
- [ ] For user action completion, send a bounded tool result that explicitly says the user reported completion and that Codex must verify observable state. Never present acknowledgement as external-write authorization.
- [ ] Decline unsupported or unsafe MCP elicitation with the documented code and no raw request data in events.
- [ ] Ensure cancellation and expiry answer the live provider request before interrupting the exact turn.
- [ ] Run:

  ```powershell
  cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
  npm run build
  node --experimental-test-isolation=none --test-concurrency=1 --test dist/tests/interactive/codex-app-server-adapter.test.js dist/tests/interactive/interactive-agent-session-manager.test.js
  ```

- [ ] Commit: `feat: mediate Codex app-server elicitation`

## Task 6: Add Scoped Single-Use Authentication Launch

**Files:**

- Modify: `ragenius_execution_subsystem/src/core/interactive/interactive-agent-adapter.ts`
- Modify: `ragenius_execution_subsystem/src/core/interactive/interactive-agent-session-manager.ts`
- Modify: `ragenius_execution_subsystem/src/api/schemas/interactive-agent.schema.ts`
- Modify: `ragenius_execution_subsystem/src/api/routes/interactive-agent.routes.ts`
- Modify: `ragenius_execution_subsystem/tests/api/interactive-agent-routes.test.ts`
- Modify: `ragenius_execution_subsystem/tests/interactive/interactive-agent-security.test.ts`

### Steps

- [ ] Add a protected adapter/session-manager method that returns a launch target only for the active pending `authentication_handoff` and matching interaction version.
- [ ] Add `POST /executions/:execution_id/interactions/:interaction_id/launch` with required execution-service authentication, app/session scope, expected version, and no body-supplied URL.
- [ ] Revalidate state, expiry, HTTPS scheme, exact host allowlist, and protected target binding at every launch.
- [ ] Mark each issued launch ticket single-use and short-lived in process memory. Launching does not resolve the interaction.
- [ ] Return `{ launch_url, expires_at }` with `Cache-Control: no-store`, `Pragma: no-cache`, and no URL in access logs or event payloads.
- [ ] Add tests for wrong app/session/execution/interaction/version, resolved/expired interaction, replayed ticket, blocked redirect host, and service-token failure.
- [ ] For `provider_window`, return a typed non-URL launch instruction for the trusted app backend rather than accepting a model-selected application.
- [ ] Run:

  ```powershell
  cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
  npm run build
  node --experimental-test-isolation=none --test-concurrency=1 --test dist/tests/api/interactive-agent-routes.test.js dist/tests/interactive/interactive-agent-security.test.js
  ```

- [ ] Commit: `feat: add scoped Agent authentication launch`

## Task 7: Proxy And Render Authentication And Manual Actions

**Files:**

- Modify: `ragenius_app_skeleton/backend/app/execution_subsystem_client.py`
- Modify: `ragenius_app_skeleton/backend/app/main.py`
- Modify: `ragenius_app_skeleton/backend/tests/test_execution_subsystem_client.py`
- Modify: `ragenius_app_skeleton/backend/tests/test_interactive_agent_flow.py`
- Modify: `ragenius_app_skeleton/frontend/src/components/AgentInteractionCard.jsx`
- Create: `ragenius_app_skeleton/frontend/src/components/AgentInteractionCard.test.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/App.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/App.test.jsx`

### Steps

- [ ] Add a scoped app route matching the addendum. It validates `app_id`, `user_id`, execution, interaction, and expected version before calling the execution client.
- [ ] Keep the execution-service response no-store. For HTTPS targets, return an immediate redirect without persisting or logging the URL. For trusted provider-window targets, return only the approved typed action.
- [ ] Add frontend state and callback for launch; never place `launch_url` in React state, local storage, chat history, or query strings.
- [ ] Update `AgentInteractionCard`:
  - show approved target label/host and **Open sign-in** for authentication;
  - show **Authentication completed** and **Cancel**;
  - show bounded instruction plus configured completion label for manual action;
  - show a persistent warning that credentials, OTPs, and recovery codes belong only in the provider window;
  - disable controls after resolution, expiry, or terminal execution.
- [ ] Add component tests for every interaction type, launch errors, refresh restoration, cancellation, and absence of secret-entry fields.
- [ ] Confirm the interaction panel remains outside the fixed-height transcript and does not reduce normal chat space when absent.
- [ ] Run:

  ```powershell
  cd D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend
  python -m pytest tests/test_execution_subsystem_client.py tests/test_interactive_agent_flow.py

  cd D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend
  npm test -- AgentInteractionCard.test.jsx App.test.jsx
  npm run build
  ```

- [ ] Commit: `feat: render Codex authentication handoffs`

## Task 8: Make Required Operation Outcomes Authoritative

**Files:**

- Modify: `ragenius_execution_subsystem/src/core/interactive/codex-app-server-codec.ts`
- Create: `ragenius_execution_subsystem/src/core/interactive/codex-interactive-result-evaluator.ts`
- Modify: `ragenius_execution_subsystem/src/core/interactive/codex-app-server-adapter.ts`
- Modify: `ragenius_execution_subsystem/src/core/interactive/interactive-agent-session-manager.ts`
- Create: `ragenius_execution_subsystem/tests/interactive/codex-interactive-result-evaluator.test.ts`
- Modify: `ragenius_execution_subsystem/tests/interactive/codex-app-server-adapter.test.ts`
- Modify: `ragenius_execution_subsystem/tests/interactive/interactive-agent-session-manager.test.ts`

### Steps

- [ ] Extend the codec's public MCP item projection with bounded tool name, status, error code, and non-secret operation evidence; continue dropping arguments, results, auth material, and metadata.
- [ ] Track MCP tool outcomes in the protected Codex handle and correlate them to the confirmed operation plan using explicit operation ids when available.
- [ ] Implement a pure evaluator that returns operation verification records and a terminal override. Required blocked, denied, cancelled, failed, or unevidenced operations produce `MCP_OPERATION_BLOCKED` or the existing verification failure code.
- [ ] Treat assistant prose as diagnostic output only. A successful `turn/completed` notification must not override failed required-operation evidence.
- [ ] Feed the evaluator result into the session manager before it transitions the execution. Preserve final assistant text in the failed result for diagnosis.
- [ ] Add the original regression: an MCP send returns `permission_denied`, then `turn/completed`; assert execution status `failed`, no completion evidence, and no persisted output claiming success.
- [ ] Add success, optional-tool-failure, multi-operation partial, duplicate-item, and truncated-event tests.
- [ ] Run:

  ```powershell
  cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
  npm run build
  node --experimental-test-isolation=none --test-concurrency=1 --test dist/tests/interactive/codex-interactive-result-evaluator.test.js dist/tests/interactive/codex-app-server-adapter.test.js dist/tests/interactive/interactive-agent-session-manager.test.js
  ```

- [ ] Commit: `fix: preserve blocked Codex operation outcomes`

## Task 9: Complete Recovery, Security, And Compatibility Regression Coverage

**Files:**

- Modify: `ragenius_execution_subsystem/tests/interactive/interactive-agent-recovery.test.ts`
- Modify: `ragenius_execution_subsystem/tests/interactive/interactive-agent-security.test.ts`
- Modify: `ragenius_execution_subsystem/tests/api/interactive-agent-routes.test.ts`
- Modify: `ragenius_execution_subsystem/tests/interactive/codex-app-server-live-smoke.test.ts`
- Modify: `ragenius_app_skeleton/backend/tests/test_interactive_agent_flow.py`
- Modify: `ragenius_app_skeleton/frontend/src/App.test.jsx`

### Steps

- [ ] Verify process loss marks persisted pending MCP/managed interactions cancelled or expired and fails execution with `AGENT_EXECUTION_INTERRUPTED`; no synthetic provider response is generated.
- [ ] Verify duplicate response, stale version, concurrent interactions, late provider resolution, cancellation race, and expiry remain single-use and scope-isolated.
- [ ] Add log/event snapshots proving raw URL, query string, schema, `_meta`, token-like values, and provider request ids are absent.
- [ ] Re-run existing clarification/selection/approval tests with every new flag disabled to prove backward compatibility.
- [ ] Re-run existing OpenClaw interactive and chat-level tests unchanged.
- [ ] Run the complete subsystem suites:

  ```powershell
  cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
  npm test
  npm run lint
  npm run typecheck

  cd D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend
  python -m pytest

  cd D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend
  npm test
  npm run build
  ```

- [ ] Commit: `test: harden Codex interactive handoffs`

## Task 10: Roll Out Capabilities And Record Live Evidence

**Files:**

- Modify: `ragenius_execution_subsystem/start-ragenius-execution-subsystem.ps1`
- Create: `ragenius_execution_subsystem/docs/codex-interactive-skill-plugin-mcp-runbook.md`
- Create: `ragenius_execution_subsystem/docs/codex-interactive-mcp-live-results-2026-08-25.md`
- Modify: `docs/codex-mcp-elicitation-interaction-addendum.md`

### Steps

- [ ] Document each environment variable, exact JSON shape, restart requirement, service-auth prerequisite, and rollback procedure. Keep startup defaults disabled and do not embed tokens or target URLs in the script.
- [ ] Add a startup validation section showing how to inspect effective capability advertisement without exposing protected configuration.
- [ ] Run the live matrix in order, enabling only the capability under test:
  1. Gmail MCP approval accept: exactly one uniquely identified message sent.
  2. Gmail MCP approval deny: no message sent; status failed/blocked.
  3. Gmail MCP approval cancel: no message sent; execution cancelled.
  4. Approved URL handoff: browser launch, external sign-in, trusted non-mutating verifier success, same-turn resume.
  5. Unknown/blocked target: no browser/application launch.
  6. Managed instruction-skill auth target with an installed real verifier.
  7. Computer Use manual action: completion acknowledgement followed by provider-observed verification.
  8. Duplicate response: one provider response and at most one external write.
- [ ] Record execution ids, timestamps, normalized statuses, interaction types, evidence, absence of duplicates, and sanitized failure diagnostics. Do not record addresses, tokens, auth URLs, cookies, or message bodies beyond a test marker.
- [ ] Enable each production capability only after its relevant live row passes. Leave managed authentication disabled if no concrete verifier is installed.
- [ ] Mark the addendum implementation status and link the evidence document; do not weaken any normative rule based on a failed test.
- [ ] Perform final review:

  ```powershell
  cd D:\GitHub\Codex-RAGenius-System
  git diff --check
  git status --short
  ```

- [ ] Commit: `docs: record Codex interactive handoff rollout`

## Completion Criteria

- [ ] Supported MCP elicitation produces one durable provider-neutral interaction and resumes the same Codex turn exactly once.
- [ ] Instruction skills and plugin guidance can request only administrator-approved authentication targets or bounded manual actions through managed tools.
- [ ] No RAGenius UI accepts credentials or secrets.
- [ ] Full authentication URLs remain protected, scoped, no-store, and single-use.
- [ ] A blocked required MCP operation cannot produce authoritative `completed` status.
- [ ] Existing one-shot Agent, Codex clarification/selection, OpenClaw interactive/chat, artifact, and execution confirmation flows remain passing.
- [ ] Builder has no new runtime dependency or schema change.
- [ ] Live acceptance evidence exists for every capability enabled in production.
