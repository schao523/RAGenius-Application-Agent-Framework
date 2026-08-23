# Interactive Agent Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a governed, provider-neutral interactive Agent channel with Codex app-server support and capability-gated OpenClaw Gateway support.

**Architecture:** The execution subsystem persists Agent sessions, interactions, and normalized events, then delegates protocol translation to interactive provider adapters. The app proxies scoped interaction APIs and renders a generic interaction card. Builder publishes administrator-reviewed interaction requirements through the existing trusted skill projection.

**Tech Stack:** TypeScript, Fastify, Zod, Prisma/PostgreSQL, Node child processes and WebSocket client, Python/FastAPI, React/Vitest, Flask/SQLite.

## Global Constraints

- Preserve `pending_confirmation` as pre-execution policy confirmation.
- Add `waiting_for_interaction` and terminal `cancelled`; timeout remains `failed`.
- Never parse prose or terminal output as authorization.
- Never accept passwords, OTPs, cookies, or tokens through an interaction.
- Initial approvals support only `allow_once`, `deny`, and `cancel_execution`.
- Existing one-shot Codex and OpenClaw providers remain autonomous fallbacks.
- Interactive requirements fail closed when the selected adapter lacks capability.
- Preserve complete `{app_id, session_id, execution_id}` scope and service authentication.
- Preserve corrected OpenClaw per-run WSL staging containment.
- Use dedicated interactive tests; do not repurpose RAGenius skill execution tests as the primary unit suite.
- OpenClaw 2026.6.8 external approval mediation requires effective
  `security: allowlist`, `ask: on-miss`, `askFallback: deny`, and a protected
  credential with both `operator.admin` and `operator.approvals`.
- Keep normal one-shot operation on `security: full` until the interactive
  OpenClaw adapter passes acceptance; use a deliberate temporary approval-test
  profile during development.

---

### Task 1: Provider-Neutral Schemas And Persistence

**Files:**
- Modify: `ragenius_execution_subsystem/prisma/schema.prisma`
- Create: `ragenius_execution_subsystem/prisma/migrations/20260813_interactive_agent_sessions/migration.sql`
- Create: `ragenius_execution_subsystem/src/core/interactive/interactive-agent-types.ts`
- Create: `ragenius_execution_subsystem/src/core/interactive/agent-session-store.ts`
- Create: `ragenius_execution_subsystem/src/core/interactive/prisma-agent-session-store.ts`
- Create: `ragenius_execution_subsystem/src/core/interactive/agent-interaction-store.ts`
- Create: `ragenius_execution_subsystem/src/core/interactive/prisma-agent-interaction-store.ts`
- Create: `ragenius_execution_subsystem/src/core/interactive/agent-event-store.ts`
- Create: `ragenius_execution_subsystem/src/core/interactive/prisma-agent-event-store.ts`
- Test: `ragenius_execution_subsystem/tests/interactive/interactive-stores.test.ts`

**Interfaces:**
- Produces: `AgentSessionStore`, `AgentInteractionStore`, `AgentEventStore` and the exact record types from `docs/interactive-agent-execution-contract.md`.
- Consumes: existing execution scope and Prisma client patterns.

- [x] **Step 1: Write failing in-memory store tests**

Cover one active session per execution, monotonically increasing interaction/event sequences, scoped reads, atomic interaction claim by version, duplicate idempotency replay, expiry, and multiple interactions in one execution.

- [x] **Step 2: Run the focused tests and confirm missing-module failures**

Run: `npm test -- tests/interactive/interactive-stores.test.ts`

- [x] **Step 3: Add the shared types and in-memory stores**

Use these core signatures:

```ts
interface AgentInteractionStore {
  create(input: CreateAgentInteractionInput): Promise<AgentInteractionRecord>;
  list(scope: ExecutionScope): Promise<AgentInteractionRecord[]>;
  claim(input: ClaimAgentInteractionInput): Promise<InteractionClaimResult>;
  resolve(input: ResolveAgentInteractionInput): Promise<AgentInteractionRecord>;
  cancelPending(scope: ExecutionScope, now: Date): Promise<number>;
}
```

- [x] **Step 4: Add Prisma tables and migration**

Create `agent_sessions`, `agent_interactions`, and `agent_execution_events` with foreign keys to `executions`, unique execution/sequence constraints, scope indexes, expiry indexes, and cascade deletion. Store provider references in non-public columns and response summaries as JSON.

- [x] **Step 5: Implement Prisma stores with conditional updates**

Interaction claims must update only records matching pending state, expected version, scope, and unexpired timestamp. Duplicate idempotency keys return the prior resolution rather than contacting a provider twice.

- [x] **Step 6: Test both in-memory and mocked Prisma behavior**

Run: `npm test -- tests/interactive/interactive-stores.test.ts`

- [x] **Step 7: Validate Prisma and commit**

Run: `npx prisma validate`

```text
git add ragenius_execution_subsystem/prisma ragenius_execution_subsystem/src/core/interactive ragenius_execution_subsystem/tests/interactive
git commit -m "feat: persist interactive agent sessions"
```

### Task 2: Interactive Session Manager And Capability Preflight

**Files:**
- Create: `ragenius_execution_subsystem/src/core/interactive/interactive-agent-adapter.ts`
- Create: `ragenius_execution_subsystem/src/core/interactive/interactive-agent-session-manager.ts`
- Create: `ragenius_execution_subsystem/src/core/interactive/interactive-capability-service.ts`
- Modify: `ragenius_execution_subsystem/src/core/execution/execution-engine.ts`
- Modify: `ragenius_execution_subsystem/src/api/schemas/common-response.schema.ts`
- Test: `ragenius_execution_subsystem/tests/interactive/interactive-agent-session-manager.test.ts`

**Interfaces:**
- Consumes: stores from Task 1 and existing `AgentProviderExecutionContext`.
- Produces: `InteractiveAgentAdapter` with `preflight`, `start`, `respond`, `cancel`, and `reconcile`.

- [x] **Step 1: Write failing lifecycle and preflight tests**

Test `running -> waiting_for_interaction -> running -> completed`, multiple interactions, unsupported capability failure, cancellation, expired interaction failure, and preservation of pre-run `pending_confirmation`.

- [x] **Step 2: Run focused tests**

Run: `npm test -- tests/interactive/interactive-agent-session-manager.test.ts`

- [x] **Step 3: Implement adapter and capability interfaces**

```ts
interface InteractiveAgentAdapter {
  readonly backend: AgentBackend;
  preflight(input: InteractivePreflightInput): Promise<InteractivePreflightResult>;
  start(input: InteractiveStartInput): Promise<ProviderSessionHandle>;
  respond(handle: ProviderSessionHandle, claim: ClaimedInteraction): Promise<void>;
  cancel(handle: ProviderSessionHandle): Promise<ProviderCancellationResult>;
  reconcile(handle: ProviderSessionHandle): Promise<ProviderReconciliationResult>;
}
```

- [x] **Step 4: Implement session orchestration**

Persist the provider handle before consuming subsequent events, normalize events through one append-only path, create interactions only from typed adapter events, and transition execution status atomically.

- [x] **Step 5: Extend status normalization**

Add `waiting_for_interaction` and `cancelled` to schemas and active-status recovery logic. Keep timeout and unclean restart behavior consistent with the lifecycle contract.

- [x] **Step 6: Integrate feature-gated interactive dispatch**

Select interactive dispatch only when requested/required capabilities pass preflight. Autonomous requests continue using the existing `AgentProvider.execute` path.

- [x] **Step 7: Run tests and commit**

Run: `npm test -- tests/interactive/interactive-agent-session-manager.test.ts tests/execution/agent-execution-queue.test.ts tests/execution/execution-store.test.ts`

```text
git add ragenius_execution_subsystem/src ragenius_execution_subsystem/tests
git commit -m "feat: orchestrate interactive agent lifecycle"
```

### Task 3: Scoped Interaction, Event, And Cancellation APIs

**Files:**
- Create: `ragenius_execution_subsystem/src/api/schemas/interactive-agent.schema.ts`
- Create: `ragenius_execution_subsystem/src/api/routes/interactive-agent.routes.ts`
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Test: `ragenius_execution_subsystem/tests/api/interactive-agent-routes.test.ts`

**Interfaces:**
- Consumes: session manager and stores from Tasks 1-2.
- Produces: the four service endpoints in the interactive execution contract.

- [x] **Step 1: Write failing route tests**

Cover service authentication, complete scope, event cursor, pending interaction inventory, stale version, duplicate idempotency, wrong response kind, secret-like fields rejection, cancellation, and execution-id enumeration resistance.

- [x] **Step 2: Run focused route tests**

Run: `npm test -- tests/api/interactive-agent-routes.test.ts`

- [x] **Step 3: Add Zod request and response schemas**

Set exact length limits: prompt 2,000 characters, option label 200, 20 options, clarification response 8,000, idempotency key 128, and event page 200. Reject unrecognized fields in response payloads.

- [x] **Step 4: Implement routes and register them**

Use existing service authentication and execution scope lookup before every store or adapter operation. Return normalized conflicts for stale, expired, already-resolved, and unsupported interactions.

- [x] **Step 5: Run route and scope regression tests**

Run: `npm test -- tests/api/interactive-agent-routes.test.ts tests/execution/execution-scope.test.ts tests/api/execution-routes.test.ts`

- [x] **Step 6: Commit**

```text
git add ragenius_execution_subsystem/src/api ragenius_execution_subsystem/src/app.ts ragenius_execution_subsystem/tests/api
git commit -m "feat: expose scoped agent interaction APIs"
```

### Task 4: Codex App-Server Adapter

**Files:**
- Create: `ragenius_execution_subsystem/src/core/interactive/codex-app-server-codec.ts`
- Create: `ragenius_execution_subsystem/src/core/interactive/codex-app-server-process.ts`
- Create: `ragenius_execution_subsystem/src/core/interactive/codex-app-server-adapter.ts`
- Create: `ragenius_execution_subsystem/src/core/interactive/codex-interaction-tool.ts`
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Test: `ragenius_execution_subsystem/tests/interactive/codex-app-server-adapter.test.ts`
- Test: `ragenius_execution_subsystem/tests/interactive/codex-app-server-live-smoke.test.ts`

**Interfaces:**
- Consumes: `InteractiveAgentAdapter`.
- Produces: `CodexAppServerAdapter` and capability profile.

- [x] **Step 1: Write codec tests with recorded protocol fixtures**

Test initialize, thread/turn ids, event deltas, multiple approval requests, dynamic tool call, malformed JSON, unknown methods, response correlation, and output bounds.

- [x] **Step 2: Implement newline JSON-RPC codec and process wrapper**

Spawn `codex app-server --stdio` without a shell, retain one process per active execution, and integrate the existing process-tree supervisor and bounded stderr handling.

- [x] **Step 3: Write failing adapter lifecycle tests**

Mock a full turn containing approval, dynamic selection, completion, cancellation, provider disconnect, and unsupported schema version.

- [x] **Step 4: Implement start and event normalization**

Send `initialize`, `initialized`, `thread/start`, and `turn/start`. Persist thread/turn refs before resolving subsequent messages. Coalesce message deltas and discard raw reasoning.

- [x] **Step 5: Implement interactions and cancellation**

Map typed approval requests, expose only allow-once/deny/cancel, register `ragenius_request_input`, and send `turn/interrupt` for cancellation.

- [x] **Step 6: Add config and preflight**

Add `CODEX_APP_SERVER_INTERACTIVE_ENABLED`, command, supported version range, interaction TTL, and initialization timeout. Default the feature to disabled.

- [x] **Step 7: Run unit and opt-in live tests**

Run: `npm test -- tests/interactive/codex-app-server-adapter.test.ts`

Opt-in: `CODEX_APP_SERVER_INTERACTIVE_SMOKE=1 npm test -- tests/interactive/codex-app-server-live-smoke.test.ts`

- [x] **Step 8: Commit**

```text
git add ragenius_execution_subsystem/src ragenius_execution_subsystem/tests/interactive
git commit -m "feat: add interactive Codex app-server adapter"
```

### Task 5: OpenClaw Gateway Adapter

**Files:**
- Create: `ragenius_execution_subsystem/src/core/interactive/openclaw-gateway-client.ts`
- Create: `ragenius_execution_subsystem/src/core/interactive/openclaw-gateway-adapter.ts`
- Create: `ragenius_execution_subsystem/src/core/interactive/openclaw-gateway-events.ts`
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Test: `ragenius_execution_subsystem/tests/interactive/openclaw-gateway-adapter.test.ts`
- Test: `ragenius_execution_subsystem/tests/interactive/openclaw-gateway-live-smoke.test.ts`

**Interfaces:**
- Consumes: `InteractiveAgentAdapter`, existing OpenClaw workspace staging, and process-independent WSL path rules.
- Produces: `OpenClawGatewayAdapter` and capability profile.

- [x] **Step 1: Write Gateway RPC and event fixture tests**

Cover connection authentication, request ids, canonical session key, run ids,
sequenced run events, unsequenced approval events, gap detection, `agent.wait`,
approval requested/resolved, and token redaction. Deduplicate approval events by
`{approval_id, event_kind}` while retaining normal sequence-gap handling for
events that carry a Gateway sequence.

- [x] **Step 2: Implement authenticated Gateway client**

Use a subsystem-owned WebSocket connection, explicit request timeouts, bounded messages, reconnect backoff, sequence tracking, and event routing by canonical session key/run id.

- [x] **Step 3: Implement session start and continuation**

Generate a key from `{app_id, session_id, agent_session_id}` without execution id. Stage and verify each provider run independently even when runs share a session.

- [x] **Step 4: Implement approval preflight and credential isolation**

Advertise approval only when preflight confirms OpenClaw 2026.6.8, effective
`security: allowlist`, `ask: on-miss`, `askFallback: deny`, and both
`operator.admin` and `operator.approvals`. Keep the credential server-side,
redact it from diagnostics, and return a precise capability failure for every
missing prerequisite. Record that `operator.admin` is a provider visibility
constraint, not permission for RAGenius to expose arbitrary admin operations.

- [x] **Step 5: Implement approval resolution and cancellation mapping**

Map only allow-once/deny. Atomically claim the interaction before calling
`exec.approval.resolve`; duplicate RAGenius idempotency keys return the stored
outcome without another provider call. Treat provider `{ok:true}` for a
duplicate resolution as provider idempotence, not a second transition. Use
exact run-scoped `chat.abort` for cancellation and confirm with `agent.wait`.

- [x] **Step 6: Implement expiry and reconciliation**

Use `sessions.list` and `agent.wait` after reconnect. Treat event gaps as
reconciliation triggers, not replay. Expire an approval when the provider
returns `decision: null` or its authoritative expiry passes; do not require an
`exec.approval.resolved` event. Do not advertise clarification or selection.

- [x] **Step 7: Add disabled-by-default configuration**

Add `OPENCLAW_GATEWAY_INTERACTIVE_ENABLED`, WSL distro, URL, external approval
credential env reference, supported version range, RPC timeout, and interaction
TTL. Never log the credential value. Preflight must not mutate OpenClaw policy.

- [x] **Step 8: Run tests and live smoke**

Automated fixtures and the opt-in live smoke harness are complete. The
installed Gateway was confirmed at `2026.6.8`. On 2026-08-13, the live
continuation/cancellation smoke and the administrator-gated approval matrix
passed using a server-side credential with `operator.admin` and
`operator.approvals`. The credential value was not logged or persisted in
the repository.

Run: `npm test -- tests/interactive/openclaw-gateway-adapter.test.ts tests/agents/openclaw-workspace.test.ts`

Opt-in continuation/cancel: `OPENCLAW_GATEWAY_INTERACTIVE_SMOKE=1 npm test -- tests/interactive/openclaw-gateway-live-smoke.test.ts`

Approval smoke runs only under the administrator-enabled temporary
`allowlist/on-miss/deny` profile. It covers allow-once execution exactly once,
deny without execution, one-second expiry returning `decision: null`, duplicate
RAGenius response suppression, one resolved event despite provider-idempotent
duplicate resolve calls, wrong-session filtering, and credential-scope failure.
The test also exposed and fixed OpenClaw's approval-event normalization from
the submitted RAGenius key to `agent:<agent_id>:<RAGenius key>`. After the
matrix, policy restoration to `full/on-miss/deny` was verified and a harmless
one-shot exec returned `RAGENIUS_NORMAL_PROFILE_OK`.

- [x] **Step 9: Commit**

```text
git add ragenius_execution_subsystem/src ragenius_execution_subsystem/tests/interactive
git commit -m "feat: add interactive OpenClaw Gateway adapter"
```

### Task 6: Builder Interaction Capability Governance

**Files:**
- Modify: `ragenius_builder/flask_scaffold/agent_skill_publication.py`
- Modify: `ragenius_builder/flask_scaffold/agent_skill_projection.py`
- Modify: `ragenius_builder/flask_scaffold/app.py`
- Modify: `ragenius_execution_subsystem/src/api/schemas/agent-skill.schema.ts`
- Modify: `ragenius_execution_subsystem/src/core/agent-skills/agent-skill-types.ts`
- Test: `ragenius_builder/flask_scaffold/tests/test_agent_skill_publication.py`
- Test: `ragenius_builder/flask_scaffold/tests/test_agent_skill_projection.py`
- Test: `ragenius_execution_subsystem/tests/agent-skills/agent-skill-projection-store.test.ts`

**Interfaces:**
- Produces: synchronized `AgentSkillInteractionPolicy` included in reviewed fingerprints and projections.

- [x] **Step 1: Write failing publication and projection tests**

Test defaults to autonomous/one-shot/not-resumable, administrator-reviewed changes, fingerprint invalidation, projection round trip, and rejection of unsupported values.

- [x] **Step 2: Implement Builder fields and validation**

Add interaction requirement, supported types, required transport, and recovery class to the existing governance resource rather than creating another catalog.

- [x] **Step 3: Extend execution projection validation and preflight**

Published requirements may raise capability/risk and must fail closed when the active provider cannot satisfy them.

- [x] **Step 4: Run Builder and execution tests**

Run Builder: `python -m pytest flask_scaffold/tests/test_agent_skill_publication.py flask_scaffold/tests/test_agent_skill_projection.py`

Run execution: `npm test -- tests/agent-skills/agent-skill-projection-store.test.ts tests/agent-skills/agent-skill-selection-service.test.ts`

Implemented the reviewed policy on immutable Builder approval records and in
the synchronized projection. Legacy approvals normalize to
`autonomous`/`one_shot`/`not_resumable`; inconsistent transport, interaction
type, and recovery combinations fail validation. Execution preflight rejects
published recovery requirements that the active adapter cannot satisfy. The
Builder focused governance/API suite passed 49 tests, the execution focused
suite passed 34 tests, Prisma validation passed, and the full execution suite
and lint passed on 2026-08-13.

- [x] **Step 5: Commit**

```text
git add ragenius_builder/flask_scaffold ragenius_execution_subsystem/src ragenius_execution_subsystem/tests/agent-skills
git commit -m "feat: govern agent interaction capabilities"
```

### Task 7: App Backend Interaction Proxy And Lane State

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/execution_subsystem_client.py`
- Modify: `ragenius_app_skeleton/backend/app/main.py`
- Modify: `ragenius_app_skeleton/backend/app/chat_repos.py`
- Test: `ragenius_app_skeleton/backend/tests/test_execution_subsystem_client.py`
- Test: `ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py`
- Test: `ragenius_app_skeleton/backend/tests/test_session_execution_state_rehydration.py`

**Interfaces:**
- Consumes: Task 3 service APIs.
- Produces: user/session-scoped app APIs and rehydratable interaction lane state.

- [x] **Step 1: Write failing client and ownership tests**

Cover list interactions/events, respond, cancel, bearer service auth, session-owner rejection, cross-app rejection, duplicate response, and provider handle redaction.

- [x] **Step 2: Add execution-subsystem client methods**

Implement bounded timeouts for list/respond/cancel. Forward complete scope and service credential; never forward user-supplied provider identifiers.

- [x] **Step 3: Add scoped app routes**

Use `/sessions/{session_id}/executions/{execution_id}/interactions`, response, events, and cancel routes. Verify authenticated ownership before calling the execution subsystem.

- [x] **Step 4: Extend execution lane state**

Persist latest normalized interaction id/type/state/version/expiry and last event sequence. Do not persist raw prompts containing provider secrets or use lane state as authorization.

- [x] **Step 5: Run backend tests and commit**

Run: `python -m pytest backend/tests/test_execution_subsystem_client.py backend/tests/test_chat_exec_routing.py backend/tests/test_session_execution_state_rehydration.py`

```text
git add ragenius_app_skeleton/backend
git commit -m "feat: proxy interactive agent sessions"
```

The app now proxies interaction listing, normalized event pagination,
idempotent responses, and cancellation only after validating the app/user
session owner. Downstream conflict and availability status is preserved,
provider-handle fields are rejected or redacted, and the durable lane stores
only the latest normalized interaction metadata plus the event cursor. The
focused Task 7 suite passed 69 tests and the full app backend suite passed 123
tests with one skip on 2026-08-13.

### Task 8: Execution Composer And Interaction UX

**Files:**
- Create: `ragenius_app_skeleton/frontend/src/components/AgentInteractionCard.jsx`
- Create: `ragenius_app_skeleton/frontend/src/components/AgentInteractionCard.test.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionLaneStatusCard.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionLaneStatusCard.test.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionInspector.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionInspector.test.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/App.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/App.test.jsx`

**Interfaces:**
- Consumes: app backend interaction/event APIs.
- Produces: generic interaction rendering and response/cancellation actions.

- [x] **Step 1: Write failing interaction-card tests**

Test allow-once/deny/cancel wording, clarification text limits, selection options, auth handoff with no secret input, expiry, submitting state, duplicate click suppression, stale refresh, and inaccessible provider details.

- [x] **Step 2: Implement the generic card**

Render from normalized `type`, `options`, `allows_free_text`, state, and expiry. Approval cards explain exact one-time scope. Authentication cards provide launch instructions and only Completed/Cancel actions.

- [x] **Step 3: Integrate polling and event cursor**

While status is queued, running, or waiting, poll scoped status/interactions/events. Use event `after_sequence`; stop on terminal status. Refresh after stale-version conflict instead of retrying the response automatically.

- [x] **Step 4: Add cancellation UX**

Show Cancel only for active executions. Disable it after submission and display authoritative cancellation/cleanup result.

- [x] **Step 5: Run frontend tests and build**

Run: `npm test -- AgentInteractionCard.test.jsx ExecutionLaneStatusCard.test.jsx ExecutionInspector.test.jsx App.test.jsx`

Run: `npm run build`

- [x] **Step 6: Commit**

```text
git add ragenius_app_skeleton/frontend/src
git commit -m "feat: add interactive agent UX"
```

The execution lane now renders one provider-neutral interaction card for
approval, clarification, selection, authentication handoff, and user-action
requests. Responses carry the server-issued version plus a client idempotency
key; stale conflicts trigger refresh rather than automatic replay. Scoped
interaction and event polling continues while the execution is active, and
cancellation uses the authoritative backend result. Authentication never
renders a credential field. The focused suite passed 73 tests, the complete
frontend suite passed 151 tests, and the production build passed on
2026-08-13.

### Task 9: Recovery, Security, And End-To-End Acceptance

**Files:**
- Create: `ragenius_execution_subsystem/tests/interactive/interactive-agent-recovery.test.ts`
- Create: `ragenius_execution_subsystem/tests/interactive/interactive-agent-security.test.ts`
- Create: `ragenius_app_skeleton/backend/tests/test_interactive_agent_flow.py`
- Create: `ragenius_app_skeleton/frontend/src/components/InteractiveAgentFlow.test.jsx`
- Modify: `ragenius_execution_subsystem/docs/security.md`
- Modify: `ragenius_execution_subsystem/docs/api-contract.md`
- Modify: `ragenius_execution_subsystem/.env.example`
- Modify: `ragenius_execution_subsystem/start-ragenius-execution-subsystem.ps1`

**Interfaces:**
- Verifies all preceding tasks as one deployable feature behind disabled flags.

- [x] **Step 1: Add recovery and attack-path tests**

Cover restart with running/waiting records, provider event spoofing, prompt-injection attempts to authorize actions, wrong interaction version, cross-session access, replayed decisions, oversized events, secret-shaped authentication payloads, and cancellation races.

- [x] **Step 2: Add end-to-end mocked flows**

Test Codex approval then clarification then completion, OpenClaw approval then cancellation, app refresh while waiting, and explicit failure when a selected skill requires unsupported OpenClaw clarification.

- [x] **Step 3: Update startup and operational documentation**

Document disabled-by-default flags, provider preflight diagnostics, the
OpenClaw external scope constraint, interaction TTL, fallback behavior, and
safe rollback. Define two explicit operational profiles: normal one-shot uses
`security: full`; interactive approval acceptance temporarily uses
`security: allowlist`, `ask: on-miss`, and `askFallback: deny`. Profile changes
are administrator actions outside RAGenius and require a Gateway restart plus
effective-policy verification.

- [x] **Step 4: Run subsystem suites**

Execution subsystem:

```text
npm run build
npm run lint
npm run typecheck
npm test
npx prisma validate
```

App backend: `python -m pytest backend/tests`

App frontend: `npm test && npm run build`

Builder: `python -m pytest flask_scaffold/tests`

- [x] **Step 5: Run live acceptance in increasing risk order**

1. Codex read-only two-turn continuation.
2. Codex dynamic selection.
3. Codex disposable workspace allow-once approval.
4. Codex cancellation.
5. OpenClaw read-only continuation.
6. OpenClaw cancellation.
7. OpenClaw disposable command allow-once, deny, and expiry only after an
   administrator activates the temporary approval-test profile and verifies
   the external credential scopes.
8. Restore the normal one-shot profile after acceptance until the interactive
   adapter is enabled for users, then verify current one-shot smoke behavior.

Task 9 acceptance combined fresh Codex initialization/read-only evidence with
the earlier same-branch Codex interaction and OpenClaw approval/cancellation
matrix. The fresh OpenClaw completion/cancellation rerun passed after the local
Gateway token was read with approved WSL access and held only in the test
process environment. An earlier token-mismatch result was sandbox error text,
not credential drift; no policy or credential was changed. See
`ragenius_execution_subsystem/docs/interactive-agent-acceptance-results-2026-08-13.md`.

- [x] **Step 6: Record evidence and commit**

Store redacted execution ids, versions, status transitions, interaction ids, verification results, and limitations in a dated acceptance document.

```text
git add ragenius_execution_subsystem ragenius_app_skeleton ragenius_builder docs
git commit -m "test: verify interactive agent execution end to end"
```

### Task 10: Disposable OpenClaw Request-Input Protocol Feasibility

This task starts only after Tasks 1-9 establish the base interactive execution
channel. It remains experimental and separate from the production OpenClaw
Gateway adapter.

**Files:**
- Modify: `ragenius_execution_subsystem/tests/fixtures/openclaw-yield-feasibility/`
- Create: `ragenius_execution_subsystem/tests/interactive/openclaw-request-input-feasibility.test.ts`
- Modify: `ragenius_execution_subsystem/docs/openclaw-ragenius-request-input-feasibility-spec.md`
- Modify: `ragenius_execution_subsystem/docs/interactive-agent-feasibility-results-2026-08-13.md`

**Interfaces:**
- Consumes: the scoped interaction persistence and APIs from Tasks 1-3 and the
  OpenClaw Gateway transport from Task 5.
- Produces: feasibility evidence only. It must not enable or advertise
  OpenClaw `clarification` or `selection` capabilities.

- [x] **Step 1: Implement disposable typed request persistence**

Register a reviewed local `ragenius_request_input` test tool and plugin-owned
Gateway methods. Persist bounded typed requests with trusted session/run/tool
identity, expiry, binding nonce hash, and no secret or authorization fields.
Keep the plugin outside administrator-approved production plugin directories.

- [ ] **Step 2: Verify single-use resolution and idempotency**

Resolve valid selection and free-text requests through the scoped execution
API. Prove that replaying the same idempotency key returns the original outcome
without another continuation run, while a second logical resolution fails
closed.

- [x] **Step 3: Verify cancellation and expiry**

Cancel the exact pending interaction and let another request expire. Confirm no
late response can continue either request, no answer is inferred, and pending
state is removed or terminally marked.

- [x] **Step 4: Verify Gateway/plugin restart behavior**

Restart while a request is pending. Reconcile durable state if independently
supported; otherwise prove explicit fail-closed interruption. Never synthesize
or replay a user response after restart.

- [ ] **Step 5: Verify concurrent isolation and repeated yield**

Run two scoped sessions concurrently and two sequential requests in one
plugin-owned sub-agent session. Responses must continue only the matching
session and request, using one stable session key with distinct provider run
ids for each `same_session_new_turn` continuation.

- [ ] **Step 6: Run the complete feasibility matrix and clean up**

Execute RI-01 through RI-23 from the feasibility specification. Record bounded
redacted evidence, delete disposable sessions and plugin state, uninstall the
test plugin, restart the Gateway, and verify the normal execution policy and
Gateway health.

- [x] **Step 7: Apply the capability gate**

If every required gate passes, write a separate production plugin contract,
design, and implementation plan for approval. If any required gate fails,
retain OpenClaw clarification and selection as unsupported. Do not combine the
experimental plugin with the base interactive implementation in either case.

Task 10 result (2026-08-13): the disposable typed selection path passed live,
and bounded persistence, expiry, cancellation, restart interruption, scoped
isolation, and security checks passed locally. Same-key replay after a recorded
continuation passed, but the provider-call/durable-commit crash window remains
unproven, and overlapping resolutions are not serialized before provider
dispatch. Cross-runtime locking, several live reconnect/concurrency/repeated-
yield cases, and unsupported-version checks also remain incomplete. The full
production gate did not pass. OpenClaw clarification and selection remain
unsupported; no production plugin capability was added. Disposable sessions,
state, plugin installation, and configuration changes were cleaned up.

## Rollout Gate

Enable Codex interactive mode first after Tasks 1-4 and 7-9 pass. Enable
OpenClaw session/cancellation after Task 5 acceptance. Keep OpenClaw approvals
disabled until Task 5 reproduces the completed administrator-gated live
approval evidence through the production adapter. Keep normal OpenClaw policy
at `security: full` until that gate passes. Keep OpenClaw clarification
unavailable until a separate managed-tool specification, feasibility test, and
production implementation plan are approved after Task 10 passes.

### Task 11: Explicit Composer Interaction Requirements

**Goal:** Add a visible Interactive Agent Composer mode that selects managed
interactive transport without relying on prompt inference or an approved Agent
Skill, while retaining advanced required-interaction guarantees.

**Files:**
- Modify: `ragenius_execution_subsystem/src/api/schemas/execution-request.schema.ts`
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Modify: `ragenius_execution_subsystem/src/core/execution/execution-engine.ts`
- Modify: `ragenius_execution_subsystem/src/core/interactive/interactive-agent-session-manager.ts`
- Modify: `ragenius_app_skeleton/backend/app/execution_subsystem_client.py`
- Modify: `ragenius_app_skeleton/backend/app/main.py`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/App.jsx`
- Test: focused schema, execution-engine, session-manager, backend-client,
  Composer, and app-routing tests.

- [x] **Step 1: Add the strict request schema**

Accept bounded unique `allowed_types` and `required_types` arrays containing
only `clarification` and `selection`. Require at least one type across them and
reject approval and unknown fields.

Accept `style: chat` without typed interaction arrays only when runtime
preflight verifies chat-level continuation.

- [x] **Step 2: Merge request and skill requirements**

Use a stable union for capability preflight. Explicit request requirements can
raise but never lower reviewed skill requirements. Route any resulting
interactive requirement through the existing session manager.

- [x] **Step 3: Enforce required interaction observation**

Track required occurrence types in the active execution. Remove a type only
after a valid typed interaction is persisted. Fail terminal completion when a
required type was not observed.

- [x] **Step 4: Forward through the app boundary**

Validate and forward the field unchanged through the app backend and execution
subsystem client. Preserve app/session ownership checks and service auth.

- [x] **Step 5: Add Composer controls**

Offer `Agent` and `Interactive Agent` as visible Composer modes. Interactive
Agent allows both clarification and selection by default, requires neither to
occur, and explains that conversational input does not grant operation
authorization. Keep detailed type requirements out of the primary UX. Disable
typed interaction controls for OpenClaw; submit chat style and label follow-ups
as new runs in the same provider session rather than paused-turn responses.

- [x] **Step 6: Verify**

Run focused tests, execution subsystem build/typecheck, app backend tests,
frontend tests, and frontend production build. Then run a live Codex selection
smoke using a staged artifact.

Implemented on 2026-08-21. The previously failing legacy chat-export artifact
was also staged successfully after separating semantic content identity from
explicit `sha256:` byte integrity. Verification passed: execution subsystem
471 tests with 8 skips, lint, typecheck, and build; app backend 127 tests with
1 skip; app frontend 165 tests and production build. The opt-in live Codex
app-server matrix also passed initialization, bounded read-only completion,
and a real dynamic selection followed by same-turn resume against Codex CLI
`0.146.0`. A three-service UI smoke remains appropriate after restart, but the
provider protocol path is verified.

Post-implementation UX stabilization completed on 2026-08-23. Live
three-service OpenClaw TaskFlow follow-ups and Codex structured interaction
were accepted by the user. A completed `Stop and summarize` turn now persists
its final output idempotently into chat history, closes the chat-level session,
and removes the follow-up composer. Long OpenClaw responses scroll within a
bounded response region while the reply field and actions remain visible.
Release verification passed the app backend suite (130 passed, 1 skipped),
Builder suite (125 passed), frontend suite (184 passed), and frontend
production build. The final commit gate also passed the complete app collection
(556 passed, 1 skipped, 11 subtests) and execution-subsystem build and suite
(480 passed, 8 opt-in live tests skipped).
