# Codex Plugin Skill Discovery and Activation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Discover enabled Codex plugin skills only from administrator-approved broad directories, govern them through Builder, and invoke approved selections with deterministic namespaced Codex references.

**Architecture:** Execution subsystem treats `codex plugin list --json` as bounded inventory input, canonicalizes each reported local plugin path, and admits it only when contained by an approved `plugin_inventory` source. Filesystem inspection remains authoritative for skill manifests and fingerprints. A new `provider_skill_reference` flows through Builder catalog state and the synchronized execution projection; Codex prompt construction uses that trusted reference while `ragenius_app_skeleton` continues selecting only by opaque `agent_skill_id`.

**Tech Stack:** Node.js 20+, TypeScript, Fastify, Zod, Prisma/PostgreSQL, Python 3, Flask, SQLite, Node test runner, pytest, Codex CLI 0.146.0 or later.

## Global Constraints

- `codex plugin list --json` is advisory inventory, never an authorization source.
- Only canonical plugin paths contained by administrator-configured broad local directories are eligible.
- Discovery and execution use the same Codex executable, Codex home, and `runtime_target_id`.
- Plugin installation, upgrade, removal, enablement, and authentication remain out of scope.
- `provider_skill_name` remains the manifest name; `provider_skill_reference` is the provider-native activation identity without a leading `$`.
- Standalone sources default `provider_skill_reference` to `provider_skill_name`.
- Plugin references use `<plugin-name>:<skill-name>` and prompt construction alone adds `$`.
- `ragenius_app_skeleton` submits `agent_skill_id` and never constructs a provider reference.
- No protected locator or canonical filesystem path may enter user-facing APIs.
- Existing OpenClaw behavior remains unchanged except for schema-compatible reference backfill.
- Use TDD for every behavior change and commit after each independently testable milestone.

---

## File Map

### Execution Subsystem

- Create `ragenius_execution_subsystem/src/core/agent-skills/codex-plugin-inventory.ts`: bounded Codex plugin process invocation, response parsing, and normalized inventory types.
- Modify `ragenius_execution_subsystem/src/config/env.ts`: inventory timeout and output-byte limits.
- Modify `ragenius_execution_subsystem/src/config/runtime-config.ts`: source discovery mode and Codex inventory runtime settings.
- Modify `ragenius_execution_subsystem/src/app.ts`: inject the configured Codex executable and inventory limits into discovery.
- Modify `ragenius_execution_subsystem/src/core/agent-skills/agent-skill-types.ts`: canonical reference fields and source kind.
- Modify `ragenius_execution_subsystem/src/core/agent-skills/codex-agent-skill-discovery.ts`: plugin inventory filtering, canonical containment, namespaced identity, and fingerprinting.
- Modify `ragenius_execution_subsystem/src/core/agent-skills/openclaw-agent-skill-discovery.ts`: schema-compatible unqualified reference projection.
- Modify `ragenius_execution_subsystem/src/api/schemas/agent-skill.schema.ts`: projection compatibility schema.
- Modify `ragenius_execution_subsystem/src/api/routes/agent-skills.routes.ts`: trusted public inventory projection.
- Modify `ragenius_execution_subsystem/src/core/agent-skills/prisma-agent-skill-projection-store.ts`: reference persistence mapping.
- Modify `ragenius_execution_subsystem/src/core/agent-skills/agent-skill-selection-service.ts`: reference-preserving revalidation.
- Modify `ragenius_execution_subsystem/src/core/agents/agent-provider-context.ts`: provider selection reference.
- Modify `ragenius_execution_subsystem/src/core/agents/codex-prompt-builder.ts`: namespaced explicit activation.
- Modify `ragenius_execution_subsystem/src/core/agent-skills/agent-skill-activation-evidence.ts`: provider-reference evidence semantics.
- Modify `ragenius_execution_subsystem/scripts/smoke-codex-agent-skill.ts`: namespaced smoke input and assertions.
- Create `ragenius_execution_subsystem/prisma/migrations/20260809_codex_plugin_skill_reference/migration.sql`: projection column and backfill.

### Builder

- Modify `ragenius_builder/flask_scaffold/storage.py`: SQLite catalog migration, identity, refresh, serialization, and projection fields.
- Modify `ragenius_builder/flask_scaffold/app.py`: discovery response validation and public administrator serialization.
- Modify `ragenius_builder/flask_scaffold/templates/agent_skills.html`: administrator-visible canonical reference.
- Modify `ragenius_builder/flask_scaffold/templates/agent_skill_detail.html`: administrator-visible canonical reference and plugin metadata.
- Modify `ragenius_builder/flask_scaffold/agent_skill_projection.py`: projection digest includes the new field automatically; tests pin it.

### Contracts and Operations

- Modify `docs/agent-skill-discovery-selection-contract.md`: canonical reference and plugin inventory trust rules.
- Modify `ragenius_execution_subsystem/docs/agent-skill-discovery-activation-design.md`: runtime implementation and configuration.
- Modify `ragenius_builder/docs/agent-skill-management-design.md`: catalog persistence and Builder review behavior.
- Modify `ragenius_execution_subsystem/docs/codex-agent-skill-activation-test-results.md`: real namespaced invocation evidence.
- Modify `ragenius_execution_subsystem/.env.example`: broad-directory source example and inventory bounds.

---

### Task 1: Align Contracts and Shared Types

**Files:**
- Modify: `docs/superpowers/specs/2026-08-09-codex-plugin-skill-discovery-activation-design.md`
- Modify: `docs/agent-skill-discovery-selection-contract.md`
- Modify: `ragenius_execution_subsystem/docs/agent-skill-discovery-activation-design.md`
- Modify: `ragenius_builder/docs/agent-skill-management-design.md`
- Modify: `ragenius_execution_subsystem/src/core/agent-skills/agent-skill-types.ts`
- Modify: `ragenius_execution_subsystem/src/core/agent-skills/openclaw-agent-skill-discovery.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/agent-provider-context.ts`
- Test: `ragenius_execution_subsystem/tests/agent-skills/agent-skill-selection-service.test.ts`
- Test: `ragenius_execution_subsystem/tests/agent-skills/openclaw-agent-skill-discovery.test.ts`
- Test: `ragenius_execution_subsystem/tests/agent-skills/agent-skill-projection-store.test.ts`

**Interfaces:**
- Consumes: approved design `docs/superpowers/specs/2026-08-09-codex-plugin-skill-discovery-activation-design.md`.
- Produces: `provider_skill_reference: string` on catalog candidates, projected governance, resolved selections, provider selections, and operation-plan selection metadata.

- [ ] **Step 1: Write the failing selection test**

Add a projected Codex skill whose manifest name and invocation reference differ:

```ts
const pluginSkill = {
  ...record,
  provider_skill_name: "systematic-debugging",
  provider_skill_reference: "superpowers:systematic-debugging"
};

assert.equal(
  resolved?.provider_skill_reference,
  "superpowers:systematic-debugging"
);
```

Also assert a legacy record without the field resolves to
`provider_skill_name` during the compatibility window.

- [ ] **Step 2: Run the focused test and verify failure**

Run:

```powershell
cd ragenius_execution_subsystem
npm test -- agent-skill-selection-service.test.ts
```

Expected: TypeScript compilation or assertion failure because
`provider_skill_reference` is not represented or propagated.

- [ ] **Step 3: Add the shared reference field**

Add the field to these types:

```ts
interface AgentSkillCatalogCandidate {
  provider_skill_name: string;
  provider_skill_reference: string;
}

interface ResolvedAgentSkillSelection {
  provider_skill_name: string;
  provider_skill_reference: string;
}

interface ProjectedAgentSkillGovernance {
  provider_skill_name: string;
  provider_skill_reference: string;
}
```

Add the same required field to `AgentSkillProviderSelection`. Add
`"codex_plugin_inventory"` to `AgentSkillSourceKind`. Keep
`provider_skill_name` available for manifest inspection and provider-specific
compatibility logic.

Add `precedence: number` to `AgentSkillSourceOption`. OpenClaw discovery must
set `provider_skill_reference` equal to `provider_skill_name`; do not change
its `/skill-name` prompt guidance. Update the shared in-memory projection test
fixtures to include the unqualified compatibility reference.

- [ ] **Step 4: Update the three governing documents**

Specify all of the following explicitly:

```text
Standalone reference = provider_skill_name
Plugin reference = plugin.name + ":" + provider_skill_name
Stable identity = backend + runtime_target_id + source_id + provider_skill_reference
Leading "$" is prompt syntax and is never persisted
App clients select agent_skill_id and cannot submit provider_skill_reference
```

Clarify in the approved specification that configured source precedence is an
explicit nonnegative integer, lower values win, and equal-precedence overlap
fails closed. This resolves the specification's existing reference to source
precedence without changing the approved trust model.

- [ ] **Step 5: Run typecheck and the focused test**

Run:

```powershell
cd ragenius_execution_subsystem
npm run typecheck
npm test -- agent-skill-selection-service.test.ts openclaw-agent-skill-discovery.test.ts agent-skill-projection-store.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add docs/superpowers/specs/2026-08-09-codex-plugin-skill-discovery-activation-design.md docs/agent-skill-discovery-selection-contract.md ragenius_execution_subsystem/docs/agent-skill-discovery-activation-design.md ragenius_builder/docs/agent-skill-management-design.md ragenius_execution_subsystem/src/core/agent-skills/agent-skill-types.ts ragenius_execution_subsystem/src/core/agent-skills/openclaw-agent-skill-discovery.ts ragenius_execution_subsystem/src/core/agents/agent-provider-context.ts ragenius_execution_subsystem/tests/agent-skills/agent-skill-selection-service.test.ts ragenius_execution_subsystem/tests/agent-skills/openclaw-agent-skill-discovery.test.ts ragenius_execution_subsystem/tests/agent-skills/agent-skill-projection-store.test.ts
git commit -m "docs: define canonical agent skill references"
```

### Task 2: Add Bounded Codex Plugin Inventory

**Files:**
- Create: `ragenius_execution_subsystem/src/core/agent-skills/codex-plugin-inventory.ts`
- Create: `ragenius_execution_subsystem/tests/agent-skills/codex-plugin-inventory.test.ts`
- Modify: `ragenius_execution_subsystem/src/config/env.ts`
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Test: `ragenius_execution_subsystem/tests/config/runtime-config.test.ts`

**Interfaces:**
- Consumes: configured `CODEX_CLI_COMMAND` and process supervisor.
- Produces:

```ts
interface CodexPluginInventoryEntry {
  plugin_id: string;
  name: string;
  marketplace_name?: string;
  version?: string;
  source_path: string;
}

interface CodexPluginInventoryReader {
  list(): Promise<CodexPluginInventoryEntry[]>;
}
```

- [ ] **Step 1: Write parser and process failure tests**

Cover the observed response envelope:

```json
{
  "installed": [{
    "pluginId": "superpowers@openai-curated",
    "name": "superpowers",
    "marketplaceName": "openai-curated",
    "version": "11c74d6b",
    "installed": true,
    "enabled": true,
    "source": {"source": "local", "path": "C:\\approved\\superpowers"}
  }],
  "available": []
}
```

Assertions must prove disabled, not-installed, non-local, blank-path, malformed,
oversized, timed-out, and nonzero-exit cases are rejected or filtered with
stable codes.

- [ ] **Step 2: Run the new test and verify failure**

Run:

```powershell
cd ragenius_execution_subsystem
npm test -- codex-plugin-inventory.test.ts
```

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement the bounded reader**

Use `runSupervisedProcess` with exact arguments:

```ts
await runSupervisedProcess({
  command: config.command,
  args: ["plugin", "list", "--json"],
  timeoutMs: config.timeoutMs,
  maxStdoutBytes: config.maxStdoutBytes,
  maxStderrBytes: config.maxStderrBytes
});
```

Parse with strict Zod schemas. Return only installed, enabled, local entries.
Map failures to:

```text
AGENT_SKILL_PLUGIN_INVENTORY_TIMEOUT
AGENT_SKILL_PLUGIN_INVENTORY_EXIT_FAILED
AGENT_SKILL_PLUGIN_INVENTORY_OUTPUT_LIMIT
AGENT_SKILL_PLUGIN_INVENTORY_INVALID
```

Do not return `marketplaceSource` or arbitrary CLI fields.

- [ ] **Step 4: Add runtime configuration**

Add defaults:

```text
CODEX_AGENT_SKILL_INVENTORY_TIMEOUT_MS=15000
CODEX_AGENT_SKILL_INVENTORY_MAX_STDOUT_BYTES=1048576
CODEX_AGENT_SKILL_INVENTORY_MAX_STDERR_BYTES=65536
```

Extend each source option with:

```ts
discovery_mode: z.enum(["directory", "plugin_inventory"]).default("directory"),
precedence: z.number().int().nonnegative().default(100)
```

Lower numeric precedence wins. Array order breaks no ties: if one canonical
plugin path is contained by two matching roots with equal precedence,
discovery rejects that plugin as ambiguous. Return the configured precedence
and `source_kind="codex_plugin_inventory"` in source options so Builder stores
the execution-owned value rather than inventing different precedence.

Construct the inventory reader with `runtimeConfig.providers.codexCli.command`
in `app.ts`, ensuring discovery and execution share the executable.

- [ ] **Step 5: Run focused configuration and inventory tests**

Run:

```powershell
cd ragenius_execution_subsystem
npm test -- codex-plugin-inventory.test.ts runtime-config.test.ts
```

Expected: PASS, including default `directory` compatibility.

- [ ] **Step 6: Commit**

```powershell
git add ragenius_execution_subsystem/src/core/agent-skills/codex-plugin-inventory.ts ragenius_execution_subsystem/tests/agent-skills/codex-plugin-inventory.test.ts ragenius_execution_subsystem/src/config/env.ts ragenius_execution_subsystem/src/config/runtime-config.ts ragenius_execution_subsystem/src/app.ts ragenius_execution_subsystem/tests/config/runtime-config.test.ts
git commit -m "feat(execution): read bounded Codex plugin inventory"
```

### Task 3: Discover Contained Plugin Skills

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/agent-skills/codex-agent-skill-discovery.ts`
- Modify: `ragenius_execution_subsystem/tests/agent-skills/codex-agent-skill-discovery.test.ts`
- Test: `ragenius_execution_subsystem/tests/api/agent-skill-routes.test.ts`

**Interfaces:**
- Consumes: `CodexPluginInventoryReader.list()` and source
  `discovery_mode`.
- Produces: contained `AgentSkillCatalogCandidate` records with canonical
  `provider_skill_reference` and redacted plugin metadata.

- [ ] **Step 1: Add failing plugin discovery tests**

Use a fake inventory reader and temporary plugin trees. Cover:

```ts
assert.equal(skill.provider_skill_name, "systematic-debugging");
assert.equal(
  skill.provider_skill_reference,
  "superpowers:systematic-debugging"
);
assert.deepEqual(skill.provider_metadata, {
  plugin_id: "superpowers@openai-curated",
  plugin_name: "superpowers",
  marketplace_name: "openai-curated",
  version: "11c74d6b"
});
```

Also test:

- plugin source outside the approved broad root is omitted with
  `AGENT_SKILL_SOURCE_NOT_ALLOWED`;
- a junction or symlink escape is rejected;
- two plugins may contain the same manifest name because references differ;
- duplicate canonical references are invalid;
- `sites/skills/.../SKILL.md` succeeds when limits are measured from each
  accepted plugin skill root rather than from the broad cache root;
- standalone directory discovery still returns an unqualified reference.

- [ ] **Step 2: Run discovery tests and verify failure**

Run:

```powershell
cd ragenius_execution_subsystem
npm test -- codex-agent-skill-discovery.test.ts
```

Expected: FAIL on missing plugin inventory behavior and reference fields.

- [ ] **Step 3: Split source enumeration from package inspection**

Refactor only within the adapter:

```ts
private async skillPackagesForSource(
  source: CodexAgentSkillSourceConfig
): Promise<Array<{
  plugin?: CodexPluginInventoryEntry;
  skillDirectory: string;
}>>;
```

For `directory`, retain the existing walk. For `plugin_inventory`, call the
reader once, canonicalize both broad root and plugin source with `fs.realpath`,
filter by `isContained`, and walk only accepted plugin roots for `SKILL.md`.
Before walking, compare every configured plugin-inventory root that contains
the canonical plugin path. Admit it only for the unique lowest-precedence
source; emit `AGENT_SKILL_SOURCE_AMBIGUOUS` when the lowest precedence is tied.

- [ ] **Step 4: Build collision-safe candidates**

Set:

```ts
const providerSkillReference = plugin
  ? `${plugin.name}:${manifest.name}`
  : manifest.name;
```

Use the reference, not the manifest name, in `stableAgentSkillId` and collision
counts. Validate each component with `/^[a-z0-9]+(?:-[a-z0-9]+)*$/`. Keep
canonical paths out of candidates and error messages.

- [ ] **Step 5: Revalidate inspection by canonical reference**

Extend inspection input with optional `provider_skill_reference`. During the
compatibility window, default it to `provider_skill_name`. Require both the
manifest name and reference to match before returning an available candidate.

- [ ] **Step 6: Run discovery and route tests**

Run:

```powershell
cd ragenius_execution_subsystem
npm test -- codex-agent-skill-discovery.test.ts agent-skill-routes.test.ts
```

Expected: PASS with no protected path in serialized responses.

- [ ] **Step 7: Commit**

```powershell
git add ragenius_execution_subsystem/src/core/agent-skills/codex-agent-skill-discovery.ts ragenius_execution_subsystem/tests/agent-skills/codex-agent-skill-discovery.test.ts ragenius_execution_subsystem/tests/api/agent-skill-routes.test.ts
git commit -m "feat(execution): discover contained Codex plugin skills"
```

### Task 4: Persist and Govern References in Builder

**Files:**
- Modify: `ragenius_builder/flask_scaffold/storage.py`
- Modify: `ragenius_builder/flask_scaffold/app.py`
- Modify: `ragenius_builder/flask_scaffold/templates/agent_skills.html`
- Modify: `ragenius_builder/flask_scaffold/templates/agent_skill_detail.html`
- Modify: `ragenius_builder/flask_scaffold/tests/test_agent_skill_management.py`
- Modify: `ragenius_builder/flask_scaffold/tests/test_agent_skill_projection.py`

**Interfaces:**
- Consumes: discovery candidates containing `provider_skill_reference`.
- Produces: Builder catalog rows and projection items preserving the exact
  approved reference.

- [ ] **Step 1: Add failing SQLite migration and identity tests**

Create a pre-feature SQLite database with `provider_skill_name` only, reopen it
through `DatabaseStore`, and assert:

```python
self.assertEqual(
    migrated["provider_skill_reference"],
    migrated["provider_skill_name"],
)
```

Refresh two candidates named `summarizer` with references
`plugin-a:summarizer` and `plugin-b:summarizer`; assert two stable rows remain.
Refresh one reference with a changed fingerprint and assert its id remains
stable while governance becomes `changed_pending_review`.

- [ ] **Step 2: Run Builder tests and verify failure**

Run:

```powershell
cd ragenius_builder/flask_scaffold
python -m unittest tests.test_agent_skill_management tests.test_agent_skill_projection -v
```

Expected: FAIL because the SQLite schema and serializers lack the field.

- [ ] **Step 3: Add the SQLite column and backfill**

For new databases, define:

```sql
provider_skill_reference TEXT NOT NULL
```

For existing databases, inspect `PRAGMA table_info(agent_skill_catalog)`, then
run:

```sql
ALTER TABLE agent_skill_catalog ADD COLUMN provider_skill_reference TEXT;
UPDATE agent_skill_catalog
SET provider_skill_reference = provider_skill_name
WHERE provider_skill_reference IS NULL OR provider_skill_reference = '';
```

Rebuild the table or add an equivalent unique index so logical uniqueness is
`(backend, runtime_target_id, source_id, provider_skill_reference)`. Preserve
ids, approvals, and bindings during any table rebuild.

- [ ] **Step 4: Update refresh and serialization**

Validate nonblank references, use them for lookup and `seen` tracking, and
persist them in insert/update paths. `_public_agent_skill` must expose the
reference to administrators while continuing to omit
`protected_locator_ref` and raw paths.

Allow `source_kind="codex_plugin_inventory"` when the selected execution source
option reports it. Persist the source option's execution-owned precedence and
reject a client-supplied value that differs from that option.

- [ ] **Step 5: Include the reference in trusted projections**

Add:

```python
"provider_skill_reference": row["provider_skill_reference"]
```

to every projection item. Update the canonical digest fixture to its newly
computed exact SHA-256 value rather than weakening the digest assertion.

- [ ] **Step 6: Display the reference in Builder**

Render the canonical reference on catalog list and detail pages for
administrator review. Keep plugin version and marketplace diagnostic-only and
do not render source paths.

- [ ] **Step 7: Run Builder tests**

Run:

```powershell
cd ragenius_builder/flask_scaffold
python -m unittest tests.test_agent_skill_management tests.test_agent_skill_projection -v
```

Expected: PASS, including migration preservation, collision-safe identity,
projection digest, approval, and binding tests.

- [ ] **Step 8: Commit**

```powershell
git add ragenius_builder/flask_scaffold/storage.py ragenius_builder/flask_scaffold/app.py ragenius_builder/flask_scaffold/templates/agent_skills.html ragenius_builder/flask_scaffold/templates/agent_skill_detail.html ragenius_builder/flask_scaffold/tests/test_agent_skill_management.py ragenius_builder/flask_scaffold/tests/test_agent_skill_projection.py
git commit -m "feat(builder): govern Codex plugin skill references"
```

### Task 5: Synchronize and Revalidate References in Execution

**Files:**
- Create: `ragenius_execution_subsystem/prisma/migrations/20260809_codex_plugin_skill_reference/migration.sql`
- Modify: `ragenius_execution_subsystem/prisma/schema.prisma`
- Modify: `ragenius_execution_subsystem/src/api/schemas/agent-skill.schema.ts`
- Modify: `ragenius_execution_subsystem/src/core/agent-skills/prisma-agent-skill-projection-store.ts`
- Modify: `ragenius_execution_subsystem/src/core/agent-skills/agent-skill-selection-service.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/agent-operation-planner.ts`
- Modify: `ragenius_execution_subsystem/tests/agent-skills/prisma-agent-skill-projection-store.test.ts`
- Modify: `ragenius_execution_subsystem/tests/agent-skills/agent-skill-selection-service.test.ts`
- Modify: `ragenius_execution_subsystem/tests/execution/execute-agent.test.ts`

**Interfaces:**
- Consumes: Builder projection items with the new reference.
- Produces: atomically stored, revalidated, immutable execution selection and
  operation-plan metadata.

- [ ] **Step 1: Add failing projection compatibility tests**

Assert a new projection stores and returns
`superpowers:systematic-debugging`. Assert an old projection payload omitting
the field is accepted only by deriving `provider_skill_name`, and that a newly
stored row is never blank.

- [ ] **Step 2: Run projection tests and verify failure**

Run:

```powershell
cd ragenius_execution_subsystem
npm test -- prisma-agent-skill-projection-store.test.ts agent-skill-selection-service.test.ts
```

Expected: FAIL because Prisma and the projection schema lack the field.

- [ ] **Step 3: Add and apply the Prisma migration definition**

Migration SQL:

```sql
ALTER TABLE "projected_agent_skill_governance"
ADD COLUMN "provider_skill_reference" TEXT;

UPDATE "projected_agent_skill_governance"
SET "provider_skill_reference" = "provider_skill_name"
WHERE "provider_skill_reference" IS NULL;

ALTER TABLE "projected_agent_skill_governance"
ALTER COLUMN "provider_skill_reference" SET NOT NULL;
```

Map it in Prisma as:

```prisma
providerSkillReference String @map("provider_skill_reference")
```

- [ ] **Step 4: Add bounded projection compatibility parsing**

Define a strict `projectedAgentSkillGovernanceWireSchema` that accepts the
optional compatibility field, then normalize into a separate required internal
schema:

```ts
provider_skill_reference:
  item.provider_skill_reference ?? item.provider_skill_name
```

The transformed internal type must require the field. In the projection route,
parse the wire payload, compute and compare the digest over that parsed wire
shape, then call `normalizeProjectedAgentSkillGovernance` before storage.
Legacy payloads therefore retain their original digest and are normalized only
after verification.

- [ ] **Step 5: Persist and revalidate the exact reference**

Map the field in `GovernanceRow`, `toGovernance`, and `itemData`. Pass both
name and reference to runtime inspection. Reject execution with
`AGENT_SKILL_IDENTITY_CHANGED` if the observed reference differs, even when
the manifest name and fingerprint match.

- [ ] **Step 6: Bind the reference into authorization state**

Include `provider_skill_reference` in the immutable operation plan and policy
fingerprint input so confirmation for an unqualified standalone skill cannot
authorize a namespaced plugin skill.

- [ ] **Step 7: Generate Prisma client and run focused tests**

Run:

```powershell
cd ragenius_execution_subsystem
npx prisma validate
npx prisma generate
npm test -- prisma-agent-skill-projection-store.test.ts agent-skill-selection-service.test.ts execute-agent.test.ts
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add ragenius_execution_subsystem/prisma ragenius_execution_subsystem/src/api/schemas/agent-skill.schema.ts ragenius_execution_subsystem/src/core/agent-skills/prisma-agent-skill-projection-store.ts ragenius_execution_subsystem/src/core/agent-skills/agent-skill-selection-service.ts ragenius_execution_subsystem/src/core/agents/agent-operation-planner.ts ragenius_execution_subsystem/tests/agent-skills/prisma-agent-skill-projection-store.test.ts ragenius_execution_subsystem/tests/agent-skills/agent-skill-selection-service.test.ts ragenius_execution_subsystem/tests/execution/execute-agent.test.ts
git commit -m "feat(execution): synchronize plugin skill references"
```

### Task 6: Invoke the Canonical Reference and Normalize Evidence

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/agents/codex-prompt-builder.ts`
- Modify: `ragenius_execution_subsystem/src/core/agent-skills/agent-skill-activation-evidence.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/codex-cli-provider.ts`
- Modify: `ragenius_execution_subsystem/tests/agents/codex-prompt-builder.test.ts`
- Modify: `ragenius_execution_subsystem/tests/agents/agent-skill-activation-evidence.test.ts`
- Modify: `ragenius_execution_subsystem/tests/agents/codex-cli-provider.test.ts`
- Modify: `ragenius_execution_subsystem/scripts/smoke-codex-agent-skill.ts`

**Interfaces:**
- Consumes: trusted `AgentSkillProviderSelection.provider_skill_reference`.
- Produces: exact `$<reference>` prompt prefix and normalized activation
  evidence that does not require a shell read for provider-resolved references.

- [ ] **Step 1: Add failing prompt tests**

For a plugin selection assert:

```ts
assert.match(prompt, /^\$superpowers:systematic-debugging\b/);
assert.doesNotMatch(prompt, /^\$systematic-debugging\b/);
```

For a standalone selection assert the existing `$notebooklm` behavior remains.
Assert user-provided `agent_skill_hint` cannot replace the resolved reference.

- [ ] **Step 2: Add failing evidence tests**

With a successful provider run, selected canonical reference, and no command
event, assert:

```ts
assert.equal(result.activation_status, "activated");
assert.equal(result.evidence_level, "provider_reference_resolved");
```

With provider failure, assert `not_observed`. Preserve `process_observed` when
structured provider events independently identify the selected skill package.

- [ ] **Step 3: Run focused tests and verify failure**

Run:

```powershell
cd ragenius_execution_subsystem
npm test -- codex-prompt-builder.test.ts agent-skill-activation-evidence.test.ts codex-cli-provider.test.ts
```

Expected: FAIL because prompts still use `provider_skill_name` and evidence
requires a `SKILL.md` read.

- [ ] **Step 4: Project only the trusted reference**

Change explicit prompt construction to:

```ts
[`$${selection.provider_skill_reference}`]
```

Keep compatibility guidance and special integrations keyed by
`provider_skill_name`; for example, NotebookLM wrapper behavior must still
activate from manifest name `notebooklm`.

- [ ] **Step 5: Add provider-reference evidence**

Extend the evidence-level union with `provider_reference_resolved`. Emit it
only when all conditions hold:

```text
activation_method == codex_explicit_reference
provider_skill_reference is nonblank
provider run completed successfully
the prompt was built from the immutable resolved selection
no stronger process_observed evidence exists
```

Never infer it from model-produced `activated_skills` alone.

- [ ] **Step 6: Update the smoke script**

Add:

```text
CODEX_AGENT_SKILL_SMOKE_REFERENCE=superpowers:systematic-debugging
CODEX_AGENT_SKILL_SMOKE_NAME=systematic-debugging
```

Require the explicit method to succeed and report either
`provider_reference_resolved` or stronger `process_observed` evidence. Record
the exact generated first prompt line in the JSON summary. Remove the ordinary
guidance fallback as a pass condition, though it may remain a diagnostic
comparison.

- [ ] **Step 7: Run focused tests**

Run:

```powershell
cd ragenius_execution_subsystem
npm test -- codex-prompt-builder.test.ts agent-skill-activation-evidence.test.ts codex-cli-provider.test.ts
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add ragenius_execution_subsystem/src/core/agents/codex-prompt-builder.ts ragenius_execution_subsystem/src/core/agent-skills/agent-skill-activation-evidence.ts ragenius_execution_subsystem/src/core/agents/codex-cli-provider.ts ragenius_execution_subsystem/tests/agents/codex-prompt-builder.test.ts ragenius_execution_subsystem/tests/agents/agent-skill-activation-evidence.test.ts ragenius_execution_subsystem/tests/agents/codex-cli-provider.test.ts ragenius_execution_subsystem/scripts/smoke-codex-agent-skill.ts
git commit -m "feat(execution): invoke namespaced Codex plugin skills"
```

### Task 7: Complete Rollout Verification and Operational Documentation

**Files:**
- Modify: `ragenius_execution_subsystem/docs/codex-agent-skill-activation-test-results.md`
- Modify: `ragenius_execution_subsystem/.env.example`
- Test: `ragenius_execution_subsystem/tests/api/agent-skill-routes.test.ts`
- Test: `ragenius_builder/flask_scaffold/tests/test_agent_skill_management.py`
- Test: `ragenius_app_skeleton/backend/tests/test_agent_skill_inventory.py`

**Interfaces:**
- Consumes: all preceding milestones and a configured real Codex runtime.
- Produces: migration/runbook instructions, full regression evidence, and a
  real namespaced activation record.

- [ ] **Step 1: Add public-boundary regression assertions**

Assert execution public inventory and the app proxy contain only approved
public fields. `provider_skill_reference`, canonical paths,
`protected_locator_ref`, and provider metadata must all remain absent. Builder
administrator APIs and pages are the only UI surfaces that display the
canonical reference.

- [ ] **Step 2: Run all subsystem suites before the live smoke test**

Run:

```powershell
cd ragenius_execution_subsystem
npm run lint
npm run typecheck
npm test

cd ../ragenius_builder/flask_scaffold
python -m unittest discover -s tests -v

cd ../../ragenius_app_skeleton
python -m pytest backend/tests/test_agent_skill_inventory.py -q
```

Expected: all commands PASS. Fix regressions within the milestone that
introduced them; do not weaken assertions.

- [ ] **Step 3: Apply the PostgreSQL migration in the test environment**

With the execution subsystem `DATABASE_URL` loaded:

```powershell
cd ragenius_execution_subsystem
npx prisma migrate deploy
npx prisma validate
```

Expected: migration `20260809_codex_plugin_skill_reference` applied and schema
valid.

- [ ] **Step 4: Configure approved broad roots**

Use one entry per administrator-approved broad cache root, for example:

```powershell
$env:CODEX_AGENT_SKILL_SOURCES_JSON = '[{"protected_locator_ref":"codex-plugin-cache-primary","display_name":"Approved Codex Plugin Cache","runtime_target_id":"codex-local-default","path":"C:\\Users\\User\\.codex\\plugins\\cache","discovery_mode":"plugin_inventory"},{"protected_locator_ref":"codex-runtime-cache-primary","display_name":"Approved Codex Runtime Plugins","runtime_target_id":"codex-local-default","path":"C:\\Users\\User\\.cache\\codex-runtimes","discovery_mode":"plugin_inventory"}]'
```

Do not approve `C:\Users\User` or another unnecessarily broad ancestor.

- [ ] **Step 5: Run the real namespaced smoke test**

```powershell
cd ragenius_execution_subsystem
$env:CODEX_AGENT_SKILL_SMOKE_NAME = 'systematic-debugging'
$env:CODEX_AGENT_SKILL_SMOKE_REFERENCE = 'superpowers:systematic-debugging'
$env:CODEX_CLI_COMMAND = 'C:\Users\User\AppData\Local\Programs\OpenAI\Codex\bin\codex.exe'
$env:CODEX_CLI_SANDBOX_MODE = 'read-only'
npm run smoke:codex-agent-skill
```

Expected JSON summary:

```json
{
  "skill_name": "systematic-debugging",
  "skill_reference": "superpowers:systematic-debugging",
  "prompt_first_line": "$superpowers:systematic-debugging",
  "chosen_method": "codex_explicit_reference"
}
```

The run must exit zero and return skill-specific content from the selected
instructions. A generic successful answer is not sufficient.

- [ ] **Step 6: Exercise Builder-to-execution synchronization**

In Builder:

1. create a source from an execution-provided `plugin_inventory` option;
2. discover `superpowers:systematic-debugging`;
3. approve its exact fingerprint;
4. bind it to one test app;
5. synchronize the projection;
6. verify execution inventory lists the opaque `agent_skill_id` for that app;
7. execute it from Composer and inspect the recorded resolved reference.

Expected: no copy of the plugin is created, Builder may be stopped after
synchronization, and execution succeeds from its trusted local projection.

- [ ] **Step 7: Document observed results and compatibility**

Update the test-results document with CLI version, plugin id, reference,
configured source label, containment result, prompt first line, evidence level,
duration, and final status. Do not include access tokens or full protected
paths.

- [ ] **Step 8: Commit**

```powershell
git add ragenius_execution_subsystem/docs/codex-agent-skill-activation-test-results.md ragenius_execution_subsystem/.env.example ragenius_execution_subsystem/tests/api/agent-skill-routes.test.ts ragenius_builder/flask_scaffold/tests/test_agent_skill_management.py ragenius_app_skeleton/backend/tests/test_agent_skill_inventory.py
git commit -m "docs: verify Codex plugin skill rollout"
```

## Completion Gate

The feature is complete only when all conditions are true:

- Builder discovers only enabled CLI-reported plugins contained by approved
  broad roots.
- Two plugins may safely expose the same manifest name under different
  canonical references.
- Builder approval and projection preserve the exact reviewed reference.
- Execution revalidates path containment, identity, and fingerprint before
  consuming confirmation or invoking Codex.
- The generated prompt starts with the synchronized namespaced reference.
- Successful provider-resolved activation does not incorrectly fail because
  Codex did not emit a `SKILL.md` shell read.
- Standalone Codex and existing OpenClaw skill selections remain compatible.
- Public app and execution APIs expose no protected paths.
- All three subsystem test commands pass.
- The real read-only namespaced smoke test exits zero with skill-specific
  evidence.
