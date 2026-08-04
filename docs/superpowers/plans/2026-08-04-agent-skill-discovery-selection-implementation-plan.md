# Agent Skill Discovery And Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Builder administrators discover, approve, synchronize, and bind provider-native Codex and OpenClaw instruction skills so users can select and invoke them safely from RAGenius Execution Composer without requiring Builder during normal execution.

**Architecture:** Builder owns governance and publishes a complete monotonic snapshot to the execution subsystem. The execution subsystem atomically persists that projection, serves app-scoped inventory locally, revalidates the installed skill fingerprint before invocation, and projects the resolved skill into Codex or OpenClaw. `ragenius_app_skeleton` remains a thin session-scoped inventory proxy and structured selection UI.

**Tech Stack:** TypeScript 5, Node.js 20+, Fastify 5, Zod 3, Prisma 6/PostgreSQL, Python 3, Flask/SQLite, FastAPI/Pydantic, React 18, Node test runner, unittest/pytest, Vitest.

## Global Constraints

- Agent skills and executable RAGenius skills use separate types, tables, APIs, inventories, and UI labels.
- Builder is required for discovery, approval, binding, and synchronization, but not after execution acknowledges a projection.
- Auto is represented by omission of `agent_skill_ref` and remains usable without a projection.
- Explicit selection is one opaque `agent_skill_id` plus `approved_fingerprint`; it never contains a source path.
- Explicit resolution fails closed and never falls back to Auto.
- The active projection is atomic, monotonic, idempotent, persistent, and non-expiring solely because Builder is offline.
- Provider availability and the complete approved skill fingerprint are revalidated immediately before invocation.
- Skill approval never weakens Agent policy, confirmation, artifact, workspace, network, provider-state, process-supervision, or output-verification rules.
- Preserve the corrected OpenClaw per-run WSL staging path when adding discovery or shared supervision.
- Do not add Agent-skill tests to `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`.
- Do not modify `ragenius_app`; integrated runtime changes belong only in `ragenius_app_skeleton`.
- Keep legacy `agent_skill_hint` temporarily; when both reference and hint are present, they must resolve to the same skill.
- Use test fixtures and mocked subprocess runners for automated tests; real Codex and OpenClaw commands run only in explicit smoke-test tasks.
- Do not alter unrelated dirty files in the existing worktree.

---

## Reference Documents

- `D:/GitHub/Codex-RAGenius-System/docs/agent-skill-discovery-selection-contract.md`
- `D:/GitHub/Codex-RAGenius-System/ragenius_builder/docs/agent-skill-management-design.md`
- `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/docs/agent-skill-discovery-activation-design.md`
- `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/docs/agent-skill-execution-composer-design.md`
- `D:/GitHub/Codex-RAGenius-System/docs/agent-execution-lifecycle-evidence-contract.md`
- `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/docs/openclaw-execution-contract.md`

## File Structure

### Execution subsystem

- `src/core/agent-skills/agent-skill-types.ts`: provider-neutral source, projection, selection, inventory, and activation types.
- `src/core/agent-skills/agent-skill-projection-store.ts`: store interface and in-memory implementation.
- `src/core/agent-skills/prisma-agent-skill-projection-store.ts`: atomic PostgreSQL implementation.
- `src/core/agent-skills/agent-skill-discovery-service.ts`: adapter registry and bounded discovery orchestration.
- `src/core/agent-skills/codex-agent-skill-discovery.ts`: contained Windows directory inspection and fingerprinting.
- `src/core/agent-skills/openclaw-agent-skill-discovery.ts`: OpenClaw JSON inventory and contained WSL package inspection.
- `src/core/agent-skills/agent-skill-selection-service.ts`: local projection resolution plus provider revalidation.
- `src/core/agent-skills/agent-skill-activation-evidence.ts`: normalized process-observation evidence.
- `src/api/schemas/agent-skill.schema.ts`: administrative projection/discovery and inventory query schemas.
- `src/api/routes/agent-skills.routes.ts`: source options, discovery, inspection, projection publication, and inventory routes.
- `prisma/migrations/20260804_agent_skill_governance_projection/migration.sql`: projection tables and indexes.

### Builder

- `flask_scaffold/agent_skill_execution_client.py`: scoped discovery and projection HTTP client.
- `flask_scaffold/agent_skill_projection.py`: deterministic complete snapshot and digest generation.
- `flask_scaffold/storage.py`: separate Agent-skill governance and projection-state tables.
- `flask_scaffold/app.py`: administrator JSON/HTML routes.
- `flask_scaffold/templates/agent_skills.html`: source, catalog, review, and synchronization status.
- `flask_scaffold/templates/app_detail.html`: per-app Agent-skill bindings.

### App skeleton

- `backend/app/execution_subsystem_client.py`: inventory and structured reference transport.
- `backend/app/main.py`: session-scoped inventory proxy and chat submission.
- `frontend/src/App.jsx`: scoped Agent-skill inventory state.
- `frontend/src/components/ExecutionComposer.jsx`: backend-sensitive Agent Skill picker.
- `frontend/src/components/ExecutionInspector.jsx`: normalized activation evidence display if the component exists; otherwise keep rendering in the current inspector owner.

---

## Milestone 1: Trust Boundary And Persistent Projection

### Task 1: Add Scoped Service Credentials

**Files:**
- Modify: `ragenius_execution_subsystem/src/config/env.ts`
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`
- Modify: `ragenius_execution_subsystem/src/api/auth/service-auth.ts`
- Modify: `ragenius_execution_subsystem/src/types/fastify.d.ts`
- Test: `ragenius_execution_subsystem/tests/api/service-auth.test.ts`

**Interfaces:**
- Produces: `ExecutionPrincipal { serviceId: string; scopes: string[]; type: "service" }`
- Produces: `requireServiceScope(request, reply, scope): boolean`
- Preserves: legacy single-token development authentication.

- [ ] **Step 1: Write failing scope tests**

Add tests proving an app credential with `agent_skills:read` cannot call a route requiring `agent_skills:admin`, while a Builder credential can:

```ts
const credentials = [
  { service_id: "ragenius_app", token: "app-token", scopes: ["execution", "agent_skills:read"] },
  { service_id: "ragenius_builder", token: "builder-token", scopes: ["agent_skills:admin"] }
];

assert.equal(appResponse.statusCode, 403);
assert.equal(builderResponse.statusCode, 200);
assert.deepEqual(builderPrincipal.scopes, ["agent_skills:admin"]);
```

- [ ] **Step 2: Run the tests and verify failure**

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test -- service-auth.test.ts
```

Expected: FAIL because the current principal has no caller-specific scopes.

- [ ] **Step 3: Implement credential parsing and scope enforcement**

Add `RAGENIUS_EXECUTION_SERVICE_CREDENTIALS_JSON` with strict Zod parsing. Match bearer tokens with `timingSafeEqual`, attach the matching service id/scopes, and export:

```ts
export function hasServiceScope(request: FastifyRequest, scope: string): boolean {
  return request.executionPrincipal?.scopes.includes(scope) === true;
}
```

Keep `RAGENIUS_EXECUTION_SERVICE_TOKEN` as development compatibility only, mapped to the configured legacy service id and `execution` scope.

- [ ] **Step 4: Verify focused and full execution tests**

```powershell
npm test -- service-auth.test.ts
npm run typecheck
```

Expected: PASS; malformed credential JSON fails startup validation.

- [ ] **Step 5: Commit the trust-boundary change**

```powershell
git add ragenius_execution_subsystem/src/config ragenius_execution_subsystem/src/api/auth ragenius_execution_subsystem/src/types ragenius_execution_subsystem/tests/api/service-auth.test.ts
git commit -m "feat(execution): add scoped service credentials"
```

### Task 2: Add Projection Types And PostgreSQL Schema

**Files:**
- Create: `ragenius_execution_subsystem/src/core/agent-skills/agent-skill-types.ts`
- Create: `ragenius_execution_subsystem/src/core/agent-skills/agent-skill-projection-store.ts`
- Create: `ragenius_execution_subsystem/src/core/agent-skills/prisma-agent-skill-projection-store.ts`
- Modify: `ragenius_execution_subsystem/prisma/schema.prisma`
- Create: `ragenius_execution_subsystem/prisma/migrations/20260804_agent_skill_governance_projection/migration.sql`
- Create: `ragenius_execution_subsystem/tests/agent-skills/agent-skill-projection-store.test.ts`
- Create: `ragenius_execution_subsystem/tests/agent-skills/prisma-agent-skill-projection-store.test.ts`

**Interfaces:**
- Produces: `AgentSkillGovernanceProjection`, `ProjectedAgentSkillGovernance`, `AgentSkillProjectionStore`.
- Consumes: Prisma transaction support.

- [ ] **Step 1: Define failing store contract tests**

Cover atomic replacement, idempotency, rollback rejection, digest conflict, app/backend lookup, and persistence:

```ts
await store.publish(snapshot(42, "sha256:a", [codexBinding]));
await store.publish(snapshot(42, "sha256:a", [codexBinding]));
await assert.rejects(() => store.publish(snapshot(41, "sha256:b", [])), /REVISION_ROLLBACK/);
await assert.rejects(() => store.publish(snapshot(42, "sha256:c", [])), /REVISION_CONFLICT/);
assert.deepEqual(await store.listForApp("app-1", "codex_cli"), [codexBinding]);
```

- [ ] **Step 2: Run focused tests and verify failure**

```powershell
npm test -- agent-skill-projection-store.test.ts
```

Expected: FAIL because the types and stores do not exist.

- [ ] **Step 3: Add Prisma models and migration**

Add `AgentSkillProjectionRevision`, `ProjectedAgentSkillGovernance`, and singleton `AgentSkillProjectionHead`. Use a transaction to insert the complete revision/items and update the head only after every insert succeeds. Index `(projectionRevisionId, appId, backend)` and `(projectionRevisionId, appId, agentSkillId)`.

The store interface must be:

```ts
export interface AgentSkillProjectionStore {
  publish(snapshot: AgentSkillGovernanceProjection): Promise<ProjectionReceipt>;
  getActiveRevision(): Promise<ProjectionRevisionSummary | null>;
  listForApp(appId: string, backend: AgentSkillBackend): Promise<ProjectedAgentSkillGovernance[]>;
  getForApp(appId: string, agentSkillId: string): Promise<ProjectedAgentSkillGovernance | null>;
}
```

- [ ] **Step 4: Generate Prisma client and verify stores**

```powershell
npx prisma validate
npx prisma generate
npm test -- agent-skill-projection-store.test.ts prisma-agent-skill-projection-store.test.ts
```

Expected: PASS against in-memory and test PostgreSQL stores; a failed transaction leaves the previous head active.

- [ ] **Step 5: Commit projection persistence**

```powershell
git add ragenius_execution_subsystem/prisma ragenius_execution_subsystem/src/core/agent-skills ragenius_execution_subsystem/tests/agent-skills
git commit -m "feat(execution): persist agent skill governance projections"
```

### Task 3: Add Projection Publication And Inventory Routes

**Files:**
- Create: `ragenius_execution_subsystem/src/api/schemas/agent-skill.schema.ts`
- Create: `ragenius_execution_subsystem/src/api/routes/agent-skills.routes.ts`
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Modify: `ragenius_execution_subsystem/src/config/env.ts`
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`
- Create: `ragenius_execution_subsystem/tests/api/agent-skill-routes.test.ts`

**Interfaces:**
- Consumes: `AgentSkillProjectionStore`, scoped service credentials.
- Produces: `PUT /v1/admin/agent-skills/governance-projection` and `GET /v1/agent-skills/inventory`.

- [ ] **Step 1: Write failing API tests**

Test canonical digest validation, trusted Builder identity, item/byte limits, idempotent receipt, empty projection, redaction, and app/backend filtering:

```ts
assert.equal(noProjection.json().projection_status, "unavailable");
assert.deepEqual(noProjection.json().items, []);
assert.equal(publish.statusCode, 200);
assert.equal(inventory.json().items[0].agent_skill_id, "agent-skill-1");
assert.equal("protected_locator_ref" in inventory.json().items[0], false);
```

- [ ] **Step 2: Verify tests fail**

```powershell
npm test -- agent-skill-routes.test.ts
```

- [ ] **Step 3: Implement strict schemas and routes**

Configure:

```text
AGENT_SKILL_TRUSTED_BUILDER_INSTANCE_ID=builder-primary
AGENT_SKILL_PROJECTION_MAX_ITEMS=10000
AGENT_SKILL_PROJECTION_MAX_BYTES=8388608
```

Recompute SHA-256 over canonical sorted projection JSON before calling `store.publish`. Return `inventory_revision` as `<builder_instance_id>:<revision>:<digest>` and `projection_status` as `active` or `unavailable`.

- [ ] **Step 4: Register services/routes and verify**

```powershell
npm test -- agent-skill-routes.test.ts service-auth.test.ts
npm run typecheck
```

Expected: app token can read inventory, Builder token can publish, and neither credential exceeds its scope.

- [ ] **Step 5: Commit API foundation**

```powershell
git add ragenius_execution_subsystem/src/api ragenius_execution_subsystem/src/app.ts ragenius_execution_subsystem/src/config ragenius_execution_subsystem/tests/api/agent-skill-routes.test.ts
git commit -m "feat(execution): publish and serve agent skill governance"
```

## Milestone 2: Provider Discovery And Fingerprinting

### Task 4: Implement Codex Skill Discovery

**Files:**
- Create: `ragenius_execution_subsystem/src/core/agent-skills/agent-skill-discovery-service.ts`
- Create: `ragenius_execution_subsystem/src/core/agent-skills/codex-agent-skill-discovery.ts`
- Modify: `ragenius_execution_subsystem/src/config/env.ts`
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`
- Modify: `ragenius_execution_subsystem/src/api/routes/agent-skills.routes.ts`
- Create: `ragenius_execution_subsystem/tests/agent-skills/codex-agent-skill-discovery.test.ts`

**Interfaces:**
- Produces: `CodexAgentSkillDiscoveryAdapter.discover()` and `.inspect()`.
- Produces: `GET /v1/admin/agent-skills/source-options`, `POST /discover`, and `POST /inspect` for Codex.

- [ ] **Step 1: Create failing contained-discovery tests**

Use temporary fixtures for a valid skill, malformed frontmatter, duplicate name, supporting-file change, symlink/junction escape, depth limit, file limit, and byte limit. Assert:

```ts
assert.match(first.content_fingerprint, /^sha256:v1:[a-f0-9]{64}$/);
assert.notEqual(first.content_fingerprint, afterReferenceEdit.content_fingerprint);
await assert.rejects(() => adapter.inspect(escapeInput), /AGENT_SKILL_SOURCE_NOT_ALLOWED/);
```

- [ ] **Step 2: Run and confirm failure**

```powershell
npm test -- codex-agent-skill-discovery.test.ts
```

- [ ] **Step 3: Implement bounded canonical inspection**

Parse `CODEX_AGENT_SKILL_SOURCES_JSON` into opaque source refs. Resolve every root/file with `realpath`, reject links outside the root, sort normalized relative paths, and hash length-prefixed path/file bytes as `sha256:v1:<hex>`. Never return the configured path in route responses.

- [ ] **Step 4: Verify adapter and route behavior**

```powershell
npm test -- codex-agent-skill-discovery.test.ts agent-skill-routes.test.ts
npm run typecheck
```

- [ ] **Step 5: Commit Codex discovery**

```powershell
git add ragenius_execution_subsystem/src/core/agent-skills ragenius_execution_subsystem/src/config ragenius_execution_subsystem/src/api/routes/agent-skills.routes.ts ragenius_execution_subsystem/tests/agent-skills
git commit -m "feat(execution): discover and fingerprint Codex skills"
```

### Task 5: Implement OpenClaw Skill Discovery

**Files:**
- Create: `ragenius_execution_subsystem/src/core/agent-skills/openclaw-agent-skill-discovery.ts`
- Modify: `ragenius_execution_subsystem/src/core/agent-skills/agent-skill-discovery-service.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/openclaw-workspace.ts`
- Modify: `ragenius_execution_subsystem/src/config/env.ts`
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`
- Create: `ragenius_execution_subsystem/tests/agent-skills/openclaw-agent-skill-discovery.test.ts`
- Modify: `ragenius_execution_subsystem/tests/agents/openclaw-workspace.test.ts`

**Interfaces:**
- Produces: `OpenClawAgentSkillDiscoveryAdapter.discover()` and `.inspect()`.
- Reuses: argument-array WSL runner and corrected per-run staging containment.

- [ ] **Step 1: Write failing JSON/WSL tests**

Mock `wsl -d <distro> --exec openclaw skills list --agent <id> --json`. Cover eligible, disabled, model-hidden, direct-dispatch-only, malformed JSON, timeout, package root escape, and deterministic package fingerprint.

```ts
assert.equal(eligible.discovery_status, "available");
assert.equal(disabled.discovery_status, "disabled_at_provider");
assert.equal(toolOnly.direct_tool_dispatch, true);
assert.equal(toolOnly.discovery_status, "ineligible");
```

- [ ] **Step 2: Run and confirm failure**

```powershell
npm test -- openclaw-agent-skill-discovery.test.ts openclaw-workspace.test.ts
```

- [ ] **Step 3: Implement adapter without shell interpolation**

Parse `OPENCLAW_AGENT_SKILL_ALLOWED_TARGETS_JSON`. Use WSL argument arrays for inventory, provider info, `readlink -f`, bounded `find`, `wc`, and `sha256sum`. Require every effective skill file to remain under the configured provider skill root. Do not reuse or rewrite the run workspace path.

- [ ] **Step 4: Verify discovery and existing staging regression**

```powershell
npm test -- openclaw-agent-skill-discovery.test.ts openclaw-workspace.test.ts openclaw-cli-provider.test.ts
npm run typecheck
```

Expected: all existing OpenClaw per-run staging tests remain unchanged and pass.

- [ ] **Step 5: Commit OpenClaw discovery**

```powershell
git add ragenius_execution_subsystem/src/core/agent-skills ragenius_execution_subsystem/src/core/agents/openclaw-workspace.ts ragenius_execution_subsystem/src/config ragenius_execution_subsystem/tests/agent-skills ragenius_execution_subsystem/tests/agents/openclaw-workspace.test.ts
git commit -m "feat(execution): discover and fingerprint OpenClaw skills"
```

## Milestone 3: Selection, Confirmation, And Activation

### Task 6: Add Structured Selection Resolution

**Files:**
- Modify: `ragenius_execution_subsystem/src/api/schemas/execution-request.schema.ts`
- Create: `ragenius_execution_subsystem/src/core/agent-skills/agent-skill-selection-service.ts`
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Create: `ragenius_execution_subsystem/tests/agent-skills/agent-skill-selection-service.test.ts`
- Modify: `ragenius_execution_subsystem/tests/execution/execute-agent.test.ts`

**Interfaces:**
- Produces: `agent_skill_ref?: { agent_skill_id: string; approved_fingerprint: string }`.
- Produces: `resolve(request): Promise<ResolvedAgentSkillSelection | null>`.
- Consumes: active projection store and backend discovery adapter inspection.

- [ ] **Step 1: Write failing resolution tests**

Cover Auto, exact reference, backend mismatch, missing projection, stale fingerprint, unbound/revoked/disabled record, provider drift, unique legacy hint, ambiguous hint, and matching/mismatching combined fields.

```ts
assert.equal(await service.resolve(autoRequest), null);
await assert.rejects(() => service.resolve(staleRequest), /AGENT_SKILL_FINGERPRINT_CHANGED/);
await assert.rejects(() => service.resolve(missingProjection), /AGENT_SKILL_PROJECTION_UNAVAILABLE/);
```

- [ ] **Step 2: Run and confirm failure**

```powershell
npm test -- agent-skill-selection-service.test.ts execute-agent.test.ts
```

- [ ] **Step 3: Implement schema and fail-closed resolver**

Use the active projection as authorization, then call the matching discovery adapter's `inspect` to compare observed and approved fingerprints. Never resolve a global provider name outside the active app projection.

- [ ] **Step 4: Verify compatibility**

```powershell
npm test -- agent-skill-selection-service.test.ts execute-agent.test.ts dry-run.test.ts
npm run typecheck
```

Expected: existing Auto Agent requests still work without a projection.

- [ ] **Step 5: Commit selection resolution**

```powershell
git add ragenius_execution_subsystem/src/api/schemas/execution-request.schema.ts ragenius_execution_subsystem/src/core/agent-skills ragenius_execution_subsystem/src/app.ts ragenius_execution_subsystem/tests
git commit -m "feat(execution): resolve approved agent skill selections"
```

### Task 7: Bind Selection To Policy, Confirmation, And Async Execution

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/execution/execution-engine.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/agent-policy.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/agent-operation-planner.ts`
- Modify: `ragenius_execution_subsystem/src/core/execution/execution-store.ts`
- Modify: `ragenius_execution_subsystem/src/core/execution/agent-execution-queue.ts`
- Modify: `ragenius_execution_subsystem/tests/execution/execute-agent.test.ts`
- Modify: `ragenius_execution_subsystem/tests/execution/confirmation-state-machine.test.ts`
- Modify: `ragenius_execution_subsystem/tests/execution/agent-execution-queue.test.ts`

**Interfaces:**
- Consumes: `AgentSkillSelectionService.resolve`.
- Produces: selection identity in immutable operation plan and confirmation fingerprint.

- [ ] **Step 1: Add failing lifecycle tests**

Assert resolution occurs before policy snapshot creation, changing fingerprint invalidates confirmation, revocation synchronized while queued fails before provider invocation, and Builder offline does not affect an unchanged active projection.

```ts
assert.equal(policySnapshot.operation_plan.agent_skill_id, "agent-skill-1");
assert.equal(providerCalls.length, 0);
assert.equal(revokedResult.errors?.[0]?.code, "AGENT_SKILL_NOT_BOUND");
```

- [ ] **Step 2: Run and verify failure**

```powershell
npm test -- execute-agent.test.ts confirmation-state-machine.test.ts agent-execution-queue.test.ts
```

- [ ] **Step 3: Integrate resolver before classification**

Resolve selection at the start of the `execute_agent` branch. Add its immutable identity to policy input and operation plan. Persist only the request reference; async workers call the same resolver again when execution starts.

- [ ] **Step 4: Verify full lifecycle**

```powershell
npm test -- execute-agent.test.ts confirmation-state-machine.test.ts agent-execution-queue.test.ts execution-scope.test.ts
npm run typecheck
```

- [ ] **Step 5: Commit lifecycle binding**

```powershell
git add ragenius_execution_subsystem/src/core/execution ragenius_execution_subsystem/src/core/agents/agent-policy.ts ragenius_execution_subsystem/src/core/agents/agent-operation-planner.ts ragenius_execution_subsystem/tests/execution
git commit -m "feat(execution): bind agent skill selection to lifecycle policy"
```

### Task 8: Project Provider Activation And Normalize Evidence

**Files:**
- Create: `ragenius_execution_subsystem/src/core/agent-skills/agent-skill-activation-evidence.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/agent-provider-context.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/codex-prompt-builder.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/codex-cli-provider.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/codex-cli-bridge.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/openclaw-prompt-builder.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/openclaw-cli-provider.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/agent-result-finalizer.ts`
- Create: `ragenius_execution_subsystem/tests/agents/agent-skill-activation-evidence.test.ts`
- Modify: `ragenius_execution_subsystem/tests/agents/codex-prompt-builder.test.ts`
- Modify: `ragenius_execution_subsystem/tests/agents/openclaw-cli-provider.test.ts`
- Create: `ragenius_execution_subsystem/scripts/smoke-codex-agent-skill.ts`
- Create: `ragenius_execution_subsystem/docs/codex-agent-skill-activation-test-results.md`

**Interfaces:**
- Consumes: resolved immutable selection in provider context.
- Produces: contract-defined `AgentSkillActivation` result.

- [ ] **Step 1: Run the real Codex activation comparison before choosing syntax**

Run the same read-only test skill and request through the production Codex executable/home twice: once using `$<provider_skill_name> <request>` and once using ordinary explicit guidance. Capture JSONL and verify the exact effective `SKILL.md` read event. The smoke script exits nonzero unless one method has process-observed evidence.

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
$env:CODEX_AGENT_SKILL_SMOKE_NAME = "ragenius-execution"
npx tsx scripts/smoke-codex-agent-skill.ts
```

Record executable version, arguments, method outcomes, observed skill label, duration, and chosen method in the results document. Do not implement Codex projection until this test passes.

- [ ] **Step 2: Write failing prompt/evidence tests for the chosen Codex method and OpenClaw guidance**

Assert prompts contain the canonical provider name but no protected path. Assert model text alone yields `evidence_level="agent_reported"`, while a validated bridge/session trace yields `process_observed`.

- [ ] **Step 3: Implement provider projection and evidence normalization**

Use exactly:

```ts
type AgentSkillActivation = {
  requested_agent_skill_id?: string;
  requested_provider_skill_name?: string;
  resolved_agent_skill_id?: string;
  resolved_provider_skill_name?: string;
  resolved_fingerprint?: string;
  activation_method: "auto" | "codex_explicit_reference" | "codex_prompt_guidance" | "openclaw_prompt_guidance";
  activation_status: "not_requested" | "projected" | "process_observed" | "not_observed" | "failed";
  evidence_level: "none" | "agent_reported" | "process_observed";
  evidence_summary?: string;
};
```

Validate Codex events and bounded OpenClaw session trace containment before claiming process observation.

- [ ] **Step 4: Verify provider regressions**

```powershell
npm test -- agent-skill-activation-evidence.test.ts codex-prompt-builder.test.ts codex-cli-provider.test.ts openclaw-cli-provider.test.ts
npm run typecheck
```

- [ ] **Step 5: Commit activation and evidence**

```powershell
git add ragenius_execution_subsystem/src/core/agent-skills ragenius_execution_subsystem/src/core/agents ragenius_execution_subsystem/tests/agents ragenius_execution_subsystem/scripts/smoke-codex-agent-skill.ts ragenius_execution_subsystem/docs/codex-agent-skill-activation-test-results.md
git commit -m "feat(execution): activate selected agent skills with evidence"
```

## Milestone 4: Builder Governance And Synchronization

### Task 9: Add Builder Agent-Skill Persistence And Projection Publisher

**Files:**
- Modify: `ragenius_builder/flask_scaffold/storage.py`
- Create: `ragenius_builder/flask_scaffold/agent_skill_execution_client.py`
- Create: `ragenius_builder/flask_scaffold/agent_skill_projection.py`
- Create: `ragenius_builder/flask_scaffold/tests/test_agent_skill_management.py`
- Create: `ragenius_builder/flask_scaffold/tests/test_agent_skill_projection.py`

**Interfaces:**
- Consumes: execution source-options/discover/inspect/projection APIs.
- Produces: separate source/catalog/approval/binding/audit/projection-state storage methods.

- [x] **Step 1: Write failing storage and publisher tests**

Cover stable catalog identity, fingerprint change, compare-and-set approval, unique app binding, audit events, monotonic revision, canonical digest, idempotent acknowledgment, failed synchronization, and restart retry.

```python
self.assertEqual(changed["governance_state"], "changed_pending_review")
self.assertGreater(snapshot["revision"], previous_revision)
self.assertEqual(store.get_agent_skill_projection_state()["sync_status"], "pending")
```

- [x] **Step 2: Run tests and verify failure**

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_builder
python -m unittest discover -s flask_scaffold/tests -p "test_agent_skill_*.py" -v
```

- [x] **Step 3: Implement tables, storage methods, canonical snapshot, and HTTP client**

Add the five governance tables plus `agent_skill_projection_state`. Every runtime-affecting mutation increments `max(previous + 1, utc_epoch_ms)` and marks pending in the same transaction. Publish a complete sorted snapshot with SHA-256 digest and mark synchronized only after instance/revision/digest acknowledgment.

- [x] **Step 4: Verify Builder persistence in isolation**

```powershell
python -m unittest discover -s flask_scaffold/tests -p "test_agent_skill_*.py" -v
python -m unittest discover -s flask_scaffold/tests -p "test_skill_management.py" -v
```

Expected: existing executable skill storage remains unchanged.

- [x] **Step 5: Commit Builder governance core**

```powershell
git add ragenius_builder/flask_scaffold/storage.py ragenius_builder/flask_scaffold/agent_skill_execution_client.py ragenius_builder/flask_scaffold/agent_skill_projection.py ragenius_builder/flask_scaffold/tests
git commit -m "feat(builder): persist and synchronize agent skill governance"
```

### Task 10: Add Builder Administrator APIs And GUI

**Files:**
- Modify: `ragenius_builder/flask_scaffold/app.py`
- Modify: `ragenius_builder/flask_scaffold/templates/base.html`
- Create: `ragenius_builder/flask_scaffold/templates/agent_skills.html`
- Create: `ragenius_builder/flask_scaffold/templates/agent_skill_detail.html`
- Modify: `ragenius_builder/flask_scaffold/templates/app_detail.html`
- Modify: `ragenius_builder/flask_scaffold/tests/test_agent_skill_management.py`

**Interfaces:**
- Produces: source/discovery/approval/revocation/binding/synchronize routes from the Builder design.
- Consumes: Task 9 storage/client/publisher.

- [x] **Step 1: Add failing route and rendering tests**

Test administrator-only mutations, source option selection without raw paths, discovery refresh, fingerprint compare-and-set, app binding, redaction, pending synchronization warning, and `Synchronize now` acknowledgment.

- [x] **Step 2: Run and verify failure**

```powershell
python -m unittest discover -s flask_scaffold/tests -p "test_agent_skill_management.py" -v
```

- [x] **Step 3: Implement APIs and server-rendered pages**

Keep `Skills` and `Agent Skills` separate in navigation. Render current/approved fingerprint, requirements, collisions, governance state, binding state, local revision, active execution revision, last success, and bounded error. Never render `protected_locator_ref` or raw provider paths to ordinary users.

- [x] **Step 4: Verify Builder routes and existing app pages**

```powershell
python -m unittest discover -s flask_scaffold/tests -p "test_agent_skill_management.py" -v
python -m unittest discover -s flask_scaffold/tests -p "test_skill_management.py" -v
```

- [x] **Step 5: Commit Builder administration UX**

```powershell
git add ragenius_builder/flask_scaffold/app.py ragenius_builder/flask_scaffold/templates ragenius_builder/flask_scaffold/tests/test_agent_skill_management.py
git commit -m "feat(builder): manage and bind agent skills"
```

## Milestone 5: App Inventory And Composer Selection

### Task 11: Add Session-Scoped App Backend Transport

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/execution_subsystem_client.py`
- Modify: `ragenius_app_skeleton/backend/app/main.py`
- Modify: `ragenius_app_skeleton/backend/app/exec_router.py`
- Modify: `ragenius_app_skeleton/backend/tests/test_execution_subsystem_client.py`
- Create: `ragenius_app_skeleton/backend/tests/test_agent_skill_inventory.py`
- Modify: `ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py`

**Interfaces:**
- Produces: `GET /sessions/{session_id}/exec/agent-skills`.
- Produces: `ExecutionSubsystemClient.get_agent_skill_inventory` and `submit_agent(..., agent_skill_ref=...)`.

- [x] **Step 1: Add failing backend tests**

Test session/app/user mismatch, backend validation, public field allowlist, unavailable projection, opaque inventory revision, structured submission, matching legacy combination, and no Builder call.

```python
assert captured["agent_skill_ref"] == {
    "agent_skill_id": "agent-skill-1",
    "approved_fingerprint": "sha256:v1:abc",
}
```

- [x] **Step 2: Run and verify failure**

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton
python -m pytest backend/tests/test_execution_subsystem_client.py backend/tests/test_agent_skill_inventory.py backend/tests/test_chat_exec_routing.py -q
```

- [x] **Step 3: Implement transport and scope checks**

Call `_require_session_scope` before inventory lookup. Allowlist only contract public fields. Preserve typed `@exec codex use <name>` and add equivalent OpenClaw legacy parsing, but treat Composer's structured request as authoritative.

- [x] **Step 4: Verify backend execution regressions**

```powershell
python -m pytest backend/tests/test_execution_subsystem_client.py backend/tests/test_agent_skill_inventory.py backend/tests/test_chat_exec_routing.py backend/tests/test_exec_router.py -q
```

- [x] **Step 5: Commit app backend transport**

```powershell
git add ragenius_app_skeleton/backend/app ragenius_app_skeleton/backend/tests
git commit -m "feat(app): proxy scoped agent skill inventory"
```

### Task 12: Add Backend-Sensitive Composer Picker And Evidence UX

**Files:**
- Modify: `ragenius_app_skeleton/frontend/src/App.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionComposer.test.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/App.test.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionInspector.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionInspector.test.jsx`

**Interfaces:**
- Consumes: session-scoped public inventory and normalized activation evidence.
- Produces: Composer `args.agentSkillRef` and backend-specific picker.

- [ ] **Step 1: Write failing UI tests**

Cover Auto, Codex/OpenClaw filtering, hardcoded NotebookLM removal, explicit id/fingerprint submission, backend/session reset, missing projection, inventory failure, artifact/output composition, and activation evidence labels.

```jsx
expect(screen.getByRole("option", { name: "NotebookLM" })).toBeInTheDocument();
await user.selectOptions(screen.getByLabelText("Agent Backend"), "openclaw_cli");
expect(screen.queryByRole("option", { name: "NotebookLM" })).not.toBeInTheDocument();
expect(onSubmit.mock.calls[0][0].args.agentSkillRef.agent_skill_id).toBe("agent-skill-1");
```

- [ ] **Step 2: Run and verify failure**

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend
npm test -- ExecutionComposer.test.jsx App.test.jsx ExecutionInspector.test.jsx
```

- [ ] **Step 3: Implement scoped state and picker**

Store inventory by `(appId, sessionId, userId, backend)`, ignore stale responses, reset selection to Auto on scope/backend changes, and change `buildExecutionRequestForComposer` so a skill reference alone produces structured context. Render `requested`, `activation not observed`, or `process observed` only from normalized evidence.

- [ ] **Step 4: Verify frontend suite and build**

```powershell
npm test -- ExecutionComposer.test.jsx App.test.jsx ExecutionInspector.test.jsx
npm run build
```

- [ ] **Step 5: Commit Composer selection UX**

```powershell
git add ragenius_app_skeleton/frontend/src/App.jsx ragenius_app_skeleton/frontend/src/components
git commit -m "feat(app): select approved agent skills in Composer"
```

## Milestone 6: End-To-End Verification And Rollout

### Task 13: Verify Synchronization, Offline Builder, Drift, And Live Providers

**Files:**
- Create: `docs/agent-skill-discovery-selection-verification-checklist.md`
- Create: `ragenius_execution_subsystem/scripts/smoke-agent-skill-selection.ts`
- Modify: `ragenius_execution_subsystem/.env.example`
- Modify: `ragenius_app_skeleton/.env.example`
- Modify: `ragenius_builder/README.md`
- Modify: `docs/docs-inventory.md`

**Interfaces:**
- Consumes: all previous milestones.
- Produces: reproducible operator setup and acceptance evidence.

- [ ] **Step 1: Run all automated subsystem gates**

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npx prisma validate
npx prisma generate
npm run typecheck
npm test

cd D:\GitHub\Codex-RAGenius-System\ragenius_builder
python -m unittest discover -s flask_scaffold/tests -v

cd D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton
python -m pytest backend/tests -q

cd D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend
npm test
npm run build
```

Expected: every command exits `0` before live provider tests begin.

- [ ] **Step 2: Run the synchronized read-model scenario**

1. Start execution and Builder with distinct scoped credentials and matching Builder instance id.
2. Discover one Codex and one OpenClaw test skill.
3. Approve and bind each to one test app.
4. Synchronize and record the acknowledged revision/digest.
5. Stop Builder.
6. Load Composer inventory and execute both skills asynchronously.
7. Confirm both complete or return provider-level outcomes without Builder connectivity.
8. Restart Builder, revoke one binding, synchronize, stop Builder, and verify the revoked skill disappears and explicit replay fails closed.

- [ ] **Step 3: Run drift and isolation scenarios**

Change a supporting file after approval and verify fingerprint mismatch before provider invocation. Verify the skill is absent from another app, raw paths are absent from browser/API responses, and explicit failures never retry as Auto.

- [ ] **Step 4: Record live Codex/OpenClaw evidence and configuration**

Document versions, commands, projection revision, selected skill ids, confirmation behavior, provider observation status, and any residual diagnostic limitation. Add only non-secret environment examples with dummy tokens.

- [ ] **Step 5: Final regression review and commit**

```powershell
git diff --check
git status --short
git add docs/agent-skill-discovery-selection-verification-checklist.md docs/docs-inventory.md ragenius_builder/README.md ragenius_execution_subsystem/.env.example ragenius_execution_subsystem/scripts/smoke-agent-skill-selection.ts ragenius_app_skeleton/.env.example
git commit -m "docs: verify agent skill discovery and selection rollout"
```

## Completion Gate

The feature is complete only when:

- Builder can discover, review, approve, bind, and synchronize both provider types.
- Execution acknowledges and atomically activates the exact Builder revision/digest.
- Builder can be stopped after synchronization while inventory and explicit execution continue.
- A synchronized revocation or unbinding takes effect without app restart.
- Provider file drift fails before provider invocation.
- Confirmation binds the selected skill id and fingerprint.
- Async worker revalidation uses the current active projection.
- Composer never exposes protected paths and never silently falls back to Auto.
- Codex activation syntax is backed by the recorded real CLI comparison.
- OpenClaw activation retains the corrected WSL staging path and process supervision.
- Existing executable skills, tools, artifacts, Codex Auto, and OpenClaw Auto pass regression tests.
