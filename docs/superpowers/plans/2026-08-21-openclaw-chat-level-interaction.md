# OpenClaw Chat-Level Interaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Apply superpowers:test-driven-development to every behavior change and superpowers:verification-before-completion before integration.

**Goal:** Add a governed OpenClaw chat-level continuation channel that preserves one provider session across multiple bounded Agent runs while keeping typed interactions, policy confirmation, and subsystem ownership unchanged.

**Architecture:** Extend the existing durable `AgentSession` lifecycle with an idle `ready_for_follow_up` state and a separately persisted `AgentChatTurn` ledger. The execution subsystem remains authoritative for session scope, serialization, idempotency, expiry, and recovery; OpenClaw supplies same-session continuity. Builder publishes administrator-reviewed `interaction_channel` metadata into the trusted projection. The app proxies scoped APIs and renders a dedicated follow-up panel rather than interpreting Agent prose as typed interaction.

**Tech Stack:** TypeScript, Fastify, Zod, Prisma/PostgreSQL, OpenClaw Gateway RPC, Python/FastAPI, React/Vitest, Flask/SQLite.

**Specs:** `docs/openclaw-chat-level-interaction-contract-addendum.md` and `docs/superpowers/specs/2026-08-21-openclaw-chat-level-interaction-design.md`.

**Completion status (2026-08-21):** Tasks 1 through 7 are implemented and
committed. Task 8 automated and live CL-01 through CL-28 acceptance passed for
OpenClaw `2026.6.8` and the approved TaskFlow fingerprint. Final local review
completed; the evidence commit and branch integration remain.

## Global Constraints

- Keep typed `AgentInteractionRecord` handling unchanged; never parse prose into approval, clarification, or selection records.
- Keep the one-shot OpenClaw provider unchanged and chat-level continuation disabled by default.
- Preserve full `{app_id, session_id, execution_id}` scoping and service authentication on every request.
- Persist no Gateway credential, raw protected handle, reasoning trace, secret, or unbounded provider response.
- Enforce one active run with a durable conditional claim; process-local maps are not sufficient.
- Treat provider idempotency as supplemental evidence, not the RAGenius idempotency authority.
- Fail closed on stale versions, policy escalation, changed artifacts or skill, ambiguous delivery, unsupported provider version, and missing local session state.
- Keep the corrected OpenClaw WSL staging root and exact-package containment behavior intact.
- Existing TaskFlow approval must be explicitly reviewed and republished with `interaction_channel: chat_level`; do not silently upgrade prior approvals.

---

### Task 1: Durable Chat Session And Turn Persistence

**Files:**
- Modify: `ragenius_execution_subsystem/prisma/schema.prisma`
- Create: `ragenius_execution_subsystem/prisma/migrations/20260821_openclaw_chat_turns/migration.sql`
- Modify: `ragenius_execution_subsystem/src/core/interactive/interactive-agent-types.ts`
- Modify: `ragenius_execution_subsystem/src/core/interactive/agent-session-store.ts`
- Modify: `ragenius_execution_subsystem/src/core/interactive/prisma-agent-session-store.ts`
- Create: `ragenius_execution_subsystem/src/core/interactive/agent-chat-turn-store.ts`
- Create: `ragenius_execution_subsystem/src/core/interactive/prisma-agent-chat-turn-store.ts`
- Modify: `ragenius_execution_subsystem/tests/interactive/interactive-stores.test.ts`

- [ ] Write failing tests for idle expiry, monotonic turn sequence, scoped reads, expected-version claim, one-active-run exclusion, same-key replay, and `delivery_unknown` persistence.
- [ ] Run `npm test -- tests/interactive/interactive-stores.test.ts` and confirm the new cases fail.
- [ ] Add `ready_for_follow_up` plus session version, turn sequence, idle expiry, and active-turn lease fields.
- [ ] Add `AgentChatTurn` with unique session/sequence and session/idempotency constraints, bounded request summary, acknowledgement state, provider run ref, normalized result, and timestamps.
- [ ] Implement in-memory and Prisma conditional claims without persisting user secrets or raw handles.
- [ ] Run the focused tests and `npx prisma validate`.
- [ ] Commit as `feat: persist agent chat continuation turns`.

### Task 2: Provider-Neutral Chat Session Lifecycle

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/interactive/interactive-agent-adapter.ts`
- Modify: `ragenius_execution_subsystem/src/core/interactive/interactive-agent-session-manager.ts`
- Modify: `ragenius_execution_subsystem/src/api/schemas/common-response.schema.ts`
- Modify: `ragenius_execution_subsystem/src/core/execution/execution-store.ts`
- Modify: `ragenius_execution_subsystem/tests/interactive/interactive-agent-session-manager.test.ts`
- Modify: `ragenius_execution_subsystem/tests/interactive/interactive-agent-recovery.test.ts`

- [ ] Write failing lifecycle tests for `running -> ready_for_follow_up -> running`, replay, concurrent rejection, graceful cancellation, end, expiry, restart recovery, and ambiguous delivery.
- [ ] Extend the adapter with optional `sendFollowUp(handle, claim)` and chat capability metadata without changing typed `respond`.
- [ ] Implement atomic claim-before-provider-contact, acknowledgement recording, run-ref replacement, terminal turn recording, idle closure, and local-authoritative end/cancel behavior.
- [ ] Rehydrate compatible idle sessions after restart; keep active irreconcilable runs blocked as `delivery_unknown` rather than reporting success.
- [ ] Run focused lifecycle, recovery, execution-store, and queue tests.
- [ ] Commit as `feat: orchestrate durable agent chat sessions`.

### Task 3: OpenClaw Same-Session Follow-Up Adapter

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/interactive/openclaw-gateway-adapter.ts`
- Modify: `ragenius_execution_subsystem/src/core/interactive/openclaw-gateway-events.ts`
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`
- Modify: `ragenius_execution_subsystem/tests/interactive/openclaw-gateway-adapter.test.ts`
- Modify: `ragenius_execution_subsystem/tests/interactive/openclaw-gateway-live-smoke.test.ts`

- [ ] Write failing adapter tests for stable session/new run routing, old-run alias removal, same-key acknowledgement replay, `status: ok` plus `stopReason: stop`, timeout ambiguity, cancellation, and reconnect reconciliation.
- [ ] Make the protected OpenClaw handle session-stable and run-mutable; retain exact session aliases while an idle chat session is open.
- [ ] Implement `sendFollowUp` with the canonical session key, turn-specific provider idempotency key, bounded prompt, and validated run id.
- [ ] Normalize completed runs to idle continuation only when the capability is active; preserve existing one-shot terminal behavior otherwise.
- [ ] Add disabled-by-default exact-version configuration and preflight advertisement.
- [ ] Run unit tests and the opt-in Gateway smoke test.
- [ ] Commit as `feat: continue OpenClaw runs in one session`.

### Task 4: Scoped Chat Session APIs And Security

**Files:**
- Modify: `ragenius_execution_subsystem/src/api/schemas/interactive-agent.schema.ts`
- Modify: `ragenius_execution_subsystem/src/api/routes/interactive-agent.routes.ts`
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Modify: `ragenius_execution_subsystem/tests/api/interactive-agent-routes.test.ts`
- Modify: `ragenius_execution_subsystem/tests/interactive/interactive-agent-security.test.ts`

- [ ] Write failing route tests for session reads, follow-up kinds, text bounds, stale version, replay, concurrent turn, wrong scope, closed/expired state, policy escalation, delivery unknown, end, and cancellation.
- [ ] Add the contract endpoints for `chat-session`, `follow-ups`, and `end-chat-session` using strict Zod bodies and the existing execution service scope.
- [ ] Return only normalized public session and turn fields; never expose provider session/run refs.
- [ ] Ensure enumeration resistance and stable error codes from the contract.
- [ ] Run route, scope, service-auth, and security regression tests.
- [ ] Commit as `feat: expose scoped agent chat APIs`.

### Task 5: Builder Interaction-Channel Governance

**Files:**
- Modify: `ragenius_builder/flask_scaffold/storage.py`
- Modify: `ragenius_builder/flask_scaffold/app.py`
- Modify: `ragenius_builder/flask_scaffold/templates/agent_skill_detail.html`
- Modify: `ragenius_builder/flask_scaffold/tests/test_agent_skill_management.py`
- Modify: `ragenius_builder/flask_scaffold/tests/test_agent_skill_projection.py`
- Modify: `ragenius_builder/flask_scaffold/tests/test_agent_skill_publication.py`
- Modify: `ragenius_execution_subsystem/prisma/schema.prisma`
- Modify: `ragenius_execution_subsystem/src/api/schemas/agent-skill.schema.ts`
- Modify: `ragenius_execution_subsystem/src/core/agent-skills/agent-skill-types.ts`
- Modify: `ragenius_execution_subsystem/src/core/agent-skills/prisma-agent-skill-projection-store.ts`

- [ ] Write failing Builder tests for `none | typed | chat_level`, fingerprint-bound review, publication, synchronized projection, and invalid backend/channel combinations.
- [ ] Add an additive SQLite migration/default of `none`; require explicit administrator review for `chat_level`.
- [ ] Publish `interaction_channel` through the signed/synchronized trusted read model and add it to the execution projection schema/store.
- [ ] Make runtime selection require approved fingerprint, app binding, enabled source, published projection, OpenClaw backend, and compatible live preflight.
- [ ] Run Builder management/publication/projection tests and execution projection tests.
- [ ] Commit as `feat: govern agent interaction channels`.

### Task 6: App Proxy And Dedicated Follow-Up UX

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/main.py`
- Modify: `ragenius_app_skeleton/backend/app/execution_client.py`
- Modify: `ragenius_app_skeleton/backend/tests/test_execution_integration.py`
- Create: `ragenius_app_skeleton/frontend/src/components/AgentChatFollowUpPanel.jsx`
- Create: `ragenius_app_skeleton/frontend/src/components/AgentChatFollowUpPanel.test.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionLaneStatusCard.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/App.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/App.test.jsx`

- [ ] Write failing backend tests proving user/app/session ownership checks before every execution-service call.
- [ ] Add scoped backend proxies for session read, follow-up, end, and existing authoritative cancel.
- [ ] Write failing component/app tests for reply, continue, revise, graceful cancel, active cancellation, end, stale refresh, delivery unknown, expiry, and closed state.
- [ ] Implement a separate follow-up panel shown only for published `chat_level` sessions; do not reuse `AgentInteractionCard` or infer options from prose.
- [ ] Explain in the UI that each follow-up starts a new run in the same OpenClaw session and is not a typed approval.
- [ ] Run focused backend and frontend suites plus build.
- [ ] Commit as `feat: add OpenClaw chat follow-up UX`.

### Task 7: Recovery, Expiry, Audit, And Operational Controls

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/interactive/interactive-agent-session-manager.ts`
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`
- Modify: `ragenius_execution_subsystem/start-ragenius-execution-subsystem.ps1`
- Modify: `ragenius_execution_subsystem/tests/interactive/interactive-agent-recovery.test.ts`
- Modify: `ragenius_execution_subsystem/tests/interactive/interactive-agent-security.test.ts`
- Modify: `ragenius_execution_subsystem/docs/interactive-agent-service-auth-guide.md`

- [ ] Add failing tests for bounded history, idle expiry, restart rehydration, version mismatch, provider deletion/recreation, redaction, shutdown, and unresolved delivery.
- [ ] Add explicit feature flag, exact provider-version allowlist, idle TTL, message bounds, and documented startup examples without enabling production by default.
- [ ] Preserve idle sessions on orderly shutdown while authoritatively cancelling or reconciling active runs.
- [ ] Emit bounded audit events for claims, acknowledgements, outcomes, closure, expiry, cancellation, and recovery decisions.
- [ ] Run recovery/security tests and commit as `feat: harden agent chat recovery`.

### Task 8: Acceptance, Live TaskFlow Publication, And Integration

**Files:**
- Modify: `ragenius_execution_subsystem/docs/openclaw-chat-level-taskflow-test-results-2026-08-21.md`
- Modify: `docs/openclaw-chat-level-interaction-contract-addendum.md` only if evidence changes a normative claim.
- Modify: `docs/superpowers/specs/2026-08-21-openclaw-chat-level-interaction-design.md` only if implementation evidence requires it.

- [ ] Run execution-subsystem unit/integration tests, Prisma validation/generation, Builder tests, app backend tests, frontend tests, and frontend build.
- [ ] Start all three subsystems from the feature worktree with chat-level interaction explicitly enabled only for testing.
- [ ] Re-review TaskFlow as `interaction_channel: chat_level`, publish, synchronize, and confirm the execution projection matches its non-empty approved fingerprint.
- [ ] Execute CL-01 through CL-28, including selection, clarification, review/revision/continue, concurrent submission, idempotent replay, cancellation, restart, disconnect, timeout ambiguity, expiry, wrong scope, and policy escalation.
- [ ] Record exact versions, execution ids, expected/observed results, and sanitized evidence; leave failures visible rather than weakening gates.
- [ ] Keep the feature disabled if any production gate fails.
- [ ] Run `git diff --check`, inspect `git status`, and use superpowers:requesting-code-review plus superpowers:verification-before-completion.
- [ ] Commit final evidence, then use superpowers:finishing-a-development-branch to integrate the branch into `main` only after all gates pass.
