# Agent Skill Discovery And Activation Design

Date: 2026-08-04

## Status

Execution-subsystem design implementing the responsibilities in
`docs/agent-skill-discovery-selection-contract.md`.

The cross-subsystem contract is authoritative. Existing lifecycle, policy,
confirmation, workspace, artifact, process-supervision, and provider contracts
remain unchanged except where this design explicitly adds Agent-skill identity
to their inputs and evidence.

## Objective

Provide provider-neutral services that:

- inspect administrator-configured Codex and OpenClaw skill sources;
- normalize and fingerprint discovered skills;
- return only app-bound, currently selectable skills;
- resolve a structured Agent-skill selection before policy and confirmation;
- revalidate the exact approved fingerprint before provider invocation;
- project the selection into a provider-specific prompt;
- report bounded activation evidence without trusting model text.

## Existing Extension Points

The current subsystem already has the required execution foundation:

- `src/api/schemas/execution-request.schema.ts` parses `execute_agent`
  requests with `agent_backend` and legacy `agent_skill_hint`.
- `src/app.ts` constructs provider services and registers Codex and OpenClaw
  providers in `ExecutionEngine`.
- `ExecutionEngine.execute` classifies policy, creates the immutable operation
  plan, handles confirmation, resolves artifacts, and invokes a provider.
- `AgentExecutionQueue` executes async work through the same engine.
- Codex and OpenClaw providers already own workspace setup, bounded process
  execution, output verification, and normalized results.
- `/v1/skills/inventory` is an executable RAGenius skill inventory and must not
  be reused for Agent skills.

The main structural change is a provider-neutral Agent-skill service injected
into `ExecutionEngine` and new Agent-skill routes. Provider implementations
remain responsible only for discovery details and activation projection.

## Components

### Provider-neutral types

Add `src/core/agent-skills/agent-skill-types.ts` for contract-aligned types:

- source inspection request;
- discovered catalog candidate;
- projected governance record;
- public selectable inventory item;
- `AgentSkillRef`;
- resolved selection;
- activation evidence;
- stable error codes.

These types are distinct from executable skill definitions in
`src/core/skills`.

### `AgentSkillDiscoveryService`

The discovery service selects an adapter by backend, validates the source
request against server-side runtime ceilings, runs bounded inspection, and
returns normalized candidates plus a summary.

```ts
interface AgentSkillDiscoveryAdapter {
  readonly backend: "codex_cli" | "openclaw_cli";
  discover(input: AgentSkillDiscoveryInput): Promise<AgentSkillDiscoveryResult>;
  inspect(input: AgentSkillInspectionInput): Promise<AgentSkillInspectionResult>;
}
```

Discovery and inspection are administrator operations. They never create
Builder approval state.

### `AgentSkillGovernanceProjectionStore`

Add a persistent store separate from `BuilderSkillClient` and executable skill
storage. It atomically accepts complete revisioned snapshots published by
Builder and serves the active trusted read model locally.

It supports:

- accepting one complete Builder projection with monotonic revision checks;
- listing projected records for one app and backend;
- resolving one projected `agent_skill_id` for one app;
- exposing active projection revision, digest, and synchronization metadata;
- retaining bounded superseded revision metadata for diagnostics.

Normal inventory and execution never make a network call to Builder. Builder
availability therefore does not affect already synchronized Agent skills.

### Projection persistence

Add Prisma-backed models equivalent to:

```ts
type AgentSkillProjectionRevision = {
  builder_instance_id: string;
  revision: number;
  digest: string;
  generated_at: string;
  received_at: string;
  status: "active" | "superseded";
};

type ProjectedAgentSkillGovernance = {
  builder_instance_id: string;
  revision: number;
  app_id: string;
  agent_skill_id: string;
  backend: "codex_cli" | "openclaw_cli";
  runtime_target_id: string;
  source_id: string;
  protected_locator_ref: string;
  provider_skill_name: string;
  provider_skill_reference: string;
  display_name: string;
  description: string;
  current_fingerprint: string;
  approved_fingerprint: string;
  source_enabled: boolean;
  approval_state: "approved" | "revoked" | "superseded";
  binding_enabled: boolean;
  model_visible: boolean;
  user_invocable: boolean;
  direct_tool_dispatch: boolean;
};
```

The active revision and all its items become visible in one database
transaction. Readers never combine records from two revisions. Snapshot items
are internal trusted records; public serializers omit locator references and
governance diagnostics.

### `AgentSkillSelectionService`

The selection service owns inventory filtering, structured reference
resolution, legacy hint resolution, runtime inspection, and execution-time
revalidation.

It returns a resolved immutable selection:

```ts
type ResolvedAgentSkillSelection = {
  agent_skill_id: string;
  backend: "codex_cli" | "openclaw_cli";
  runtime_target_id: string;
  source_id: string;
  provider_skill_name: string;
  provider_skill_reference: string;
  display_name: string;
  approved_fingerprint: string;
  observed_fingerprint: string;
  resolved_at: string;
  activation_method:
    | "codex_explicit_reference"
    | "codex_prompt_guidance"
    | "openclaw_prompt_guidance";
};
```

The service does not classify permissions and cannot weaken an Agent policy.

## Runtime Configuration

### Governance publisher

Execution pins the trusted Builder publisher identity and snapshot bounds:

```text
AGENT_SKILL_TRUSTED_BUILDER_INSTANCE_ID=builder-primary
AGENT_SKILL_PROJECTION_MAX_ITEMS=10000
AGENT_SKILL_PROJECTION_MAX_BYTES=8388608
```

The configured identity must match Builder's `builder_instance_id`. Rotating
the trusted publisher requires an explicit configuration change and service
restart; a publication request cannot rotate trust. Revisions are monotonically
increasing integers and are persisted with the active projection.

### Codex ceilings

Add an execution-owned registry of administrator-selectable Codex sources plus
maximum inspection bounds:

```text
CODEX_AGENT_SKILL_SOURCES_JSON=[{"protected_locator_ref":"codex-source-ref-1","display_name":"Local Codex Skills","runtime_target_id":"codex-local-default","path":"C:\\Users\\User\\.codex\\skills"}]
CODEX_AGENT_SKILL_MAX_DEPTH=6
CODEX_AGENT_SKILL_MAX_FILES=512
CODEX_AGENT_SKILL_MAX_FILE_BYTES=1048576
CODEX_AGENT_SKILL_MAX_TOTAL_BYTES=16777216
```

Builder selects `protected_locator_ref`; it never sends or persists the path as
discovery input. The reference resolves to a path only through execution-owned
configuration. The canonical source and every inspected file must remain under
the configured source root after resolving symlinks and junctions. A Builder
administrator cannot add or expand a host path through an API request.

### OpenClaw ceilings

OpenClaw discovery is restricted to configured tuples:

```text
OPENCLAW_AGENT_SKILL_ALLOWED_TARGETS_JSON=[{"runtime_target_id":"openclaw-main","wsl_distro":"OpenClawGateway","agent_id":"main"}]
```

Each allowed target also has an opaque `protected_locator_ref` returned to
Builder with a redacted display label. The WSL distro, executable, and agent id
come from execution configuration, not from an administrator or end-user
request. CLI output limits and timeouts reuse the provider's bounded process
supervision.

### Caching

Discovery results may be cached by source and provider state for a short
configured TTL. Cache entries are optimization only. Explicit execution always
performs a bounded inspection sufficient to confirm identity, availability,
and fingerprint.

## Codex Discovery Adapter

### Discovery algorithm

For a validated source root:

1. resolve the root to a canonical absolute path;
2. enumerate descendants with bounded depth, file count, and byte limits;
3. identify directories containing a regular `SKILL.md` file;
4. reject symlinks, junctions, or resolved files outside the source root;
5. parse the supported frontmatter and normalize name and description;
6. calculate the content fingerprint;
7. return one candidate per valid skill directory;
8. return invalid entries with a bounded reason rather than aborting unrelated
   valid entries.

The provider skill name is the validated manifest name when present; otherwise
it is the containing directory name. Names must satisfy the Codex skill naming
rules and be unique within one source result.

### Fingerprint

The Codex fingerprint is:

```text
sha256:v1:<hex digest>
```

The digest input is a canonical manifest of every regular file in the skill
directory, sorted by normalized forward-slash relative path. Each entry includes
path byte length, path bytes, file byte length, and file bytes. Files outside
the root, links, transient lock files, and provider cache files are excluded by
an explicit versioned rule set.

Including supporting files means an approved `SKILL.md` cannot silently load a
changed script or reference without invalidating approval.

## OpenClaw Discovery Adapter

### Inventory command

Discovery invokes the configured runtime as an argument array, never a shell
string:

```text
wsl -d <distro> --exec <openclaw-command> skills list --agent <agent-id> --json
```

The adapter validates JSON and normalizes provider fields including name,
description, eligibility, disabled state, model visibility, missing
requirements, and source label.

For MVP selection, a skill is `available` only when it is eligible, not
disabled, model visible, and not direct-tool-dispatch-only. Other entries remain
visible to Builder with a reason.

### Inspection and fingerprint

Inventory metadata alone is insufficient for content approval. For each skill,
the adapter uses the configured OpenClaw inspection command to obtain the
provider-resolved skill location and metadata, then passes the location to a
small WSL inspection helper.

The helper:

- accepts arguments through `wsl --exec`, not interpolated shell text;
- canonicalizes the resolved skill directory;
- requires it to remain under an execution-configured OpenClaw skill root;
- rejects links escaping that root;
- applies bounded file and byte limits;
- returns normalized metadata and a `sha256:v1` canonical directory digest.

No Windows path conversion is used for OpenClaw skill inspection. The helper
must not reuse or alter the existing per-run workspace staging root.

If a provider-bundled skill cannot expose inspectable content under an allowed
root, it is reported `invalid` for approval purposes rather than approved from
inventory metadata alone.

## Administrative APIs

Register a separate route module under `/v1/admin/agent-skills`.

### `GET /v1/admin/agent-skills/source-options`

Returns the execution-configured source references, display labels, backends,
and runtime target ids available for Builder registration. It omits actual host
and WSL paths. This is the only source from which Builder may choose a
`protected_locator_ref`.

### `POST /v1/admin/agent-skills/discover`

Accepts the contract source identity and protected locator reference. Requires
service authentication and an administrator-service identity. It returns:

```json
{
  "source_id": "source_...",
  "backend": "codex_cli",
  "runtime_target_id": "codex-local-default",
  "discovered_at": "2026-08-04T00:00:00.000Z",
  "complete": true,
  "items": [],
  "errors": []
}
```

`complete` is false when the source could not be enumerated fully. Builder must
not mark absent entries missing from an incomplete result.

### `POST /v1/admin/agent-skills/inspect`

Performs a fresh bounded inspection for one source and provider name. This is
used before Builder approval and for administrator diagnostics. It returns the
current fingerprint and redacted evidence.

### `PUT /v1/admin/agent-skills/governance-projection`

Accepts Builder's complete governance snapshot. The route:

1. requires `agent_skills:admin` service scope;
2. validates the complete bounded payload before opening a transaction;
3. recomputes the canonical digest and requires an exact match;
4. requires the configured or previously initialized `builder_instance_id`;
5. rejects a lower revision;
6. treats the same revision and digest as idempotent success;
7. rejects the same revision with a different digest;
8. inserts the new revision and items, supersedes the old revision, and changes
   the active pointer atomically;
9. returns the accepted instance id, revision, digest, item count, and receive
   time.

The first accepted snapshot initializes the configured Builder instance.
Replacing it requires an operator to change
`AGENT_SKILL_TRUSTED_BUILDER_INSTANCE_ID` and restart through the normal
configuration process; it is never inferred from a publish request. Snapshot
count and byte limits prevent an authenticated caller from exhausting storage.

The previous active projection remains usable if publication validation or the
database transaction fails.

Builder may batch source, approval, and binding edits as a local draft. Those
edits have no effect here until Builder publishes one complete projection.
Execution does not read Builder's draft database and never applies partial
governance mutations. A failed request, stale revision, digest mismatch, or
publisher mismatch preserves the prior active pointer.

## App-facing Inventory API

Register:

`GET /v1/agent-skills/inventory?app_id=<id>&backend=<backend>`

The execution subsystem:

1. reads the active persistent governance projection locally;
2. filters for app, backend, enabled binding, enabled source, and exact approved
   current fingerprint;
3. performs cached availability checks with a bounded freshness window;
4. removes unavailable, changed, disabled, or unbound entries;
5. returns public fields only.

```json
{
  "items": [
    {
      "agent_skill_id": "agent_skill_...",
      "backend": "codex_cli",
      "display_name": "NotebookLM",
      "description": "Use NotebookLM through the configured runtime.",
      "provider_skill_name": "notebooklm",
      "approved_fingerprint": "sha256:v1:...",
      "availability": "available"
    }
  ],
  "inventory_revision": "builder_...:42:sha256:..."
}
```

The response omits source paths, locator references, missing environment names,
and unrestricted provider metadata. Service authentication protects the route;
the app backend never exposes the service token to the browser.

If no active projection exists, inventory returns an empty list plus
`projection_status = "unavailable"`. Auto remains valid because it has no
explicit Agent-skill authorization dependency. Any explicit reference or legacy
hint fails with `AGENT_SKILL_PROJECTION_UNAVAILABLE`.

An acknowledged active projection does not expire merely because Builder is
offline. Its `generated_at` and `received_at` values are diagnostics, not a TTL.
It remains authoritative until a newer revision is atomically activated or an
operator explicitly clears it. Provider availability and content fingerprint
are still freshly revalidated before invocation, so local skill drift fails
closed even while Builder is offline.

## Execution Request Schema

Add the provider-neutral structured reference:

```ts
const agentSkillRefSchema = z.object({
  agent_skill_id: z.string().trim().min(1),
  approved_fingerprint: z.string().trim().min(1)
}).strict();
```

`execute_agent` accepts optional `agent_skill_ref`. It temporarily retains
optional `agent_skill_hint` for compatibility. If both are present, both are
resolved and must identify the same backend skill; otherwise validation fails.

An absent reference means Auto. The string `auto` is not a valid
`agent_skill_id`.

## Selection Resolution

### Structured reference

Before policy classification, the engine:

1. resolves the app-bound authorization from the active local projection;
2. requires request backend, authorized backend, and provider backend to match;
3. compares the client fingerprint with the projected approved fingerprint;
4. freshly inspects the provider skill;
5. requires provider availability and exact observed fingerprint equality;
6. attaches the resolved selection to the internal request context.

The client fingerprint is optimistic concurrency evidence, not authorization.
The synchronized governance projection and current provider inspection remain
authoritative.

### Legacy hint

For `agent_skill_hint`, the selection service lists effective app-bound skills
for the request backend and performs a case-insensitive exact match against the
provider name and approved aliases. It succeeds only for one unique match.

No match returns `AGENT_SKILL_NOT_APPROVED`. Multiple matches return
`AGENT_SKILL_AMBIGUOUS`. A legacy hint never resolves a global installed skill
outside the active app binding.

When a structured reference and hint are both supplied, the structured
reference is resolved authoritatively and the hint must uniquely resolve to the
same `agent_skill_id`. The hint cannot redirect or override the reference.

### Policy and confirmation ordering

Resolved skill identity is added to the Agent request policy input before
`classifyAgentRequest`, operation planning, and confirmation snapshot creation.
The immutable operation plan includes:

- `agent_skill_id`;
- backend and runtime target;
- provider skill name;
- approved and observed fingerprint;
- activation strategy.

This ensures confirmation binds the selected skill content. Confirmation fails
with the existing policy-changed behavior if selection identity changes.

### Async revalidation

The queue persists the structured reference and approved fingerprint, not a
resolved filesystem location. When a worker executes the request, the engine
repeats local projection resolution and provider inspection before policy
snapshot comparison and invocation.

A synchronized revoked binding, disabled source, changed fingerprint, or
unavailable provider fails the queued run closed. It is never converted to
Auto. A queued run may continue to use the last active projection while Builder
is offline; an administrator change becomes authoritative only after execution
acknowledges its published revision.

## Provider Activation

### Codex

The final Codex activation method is gated by a real CLI comparison using the
same executable, home, arguments, sandbox, and prompt envelope as production.
The test must compare an explicit provider-supported reference, when available,
with ordinary prompt guidance and verify the exact effective `SKILL.md` load.

The production-equivalent comparison completed on 2026-08-04 with Codex CLI
`0.146.0`. Both methods produced a process-observed read of the exact selected
`SKILL.md`; the MVP selects the provider-supported explicit reference. The
Codex prompt starts with:

```text
$notebooklm
Selected Agent skill: notebooklm
Use the installed Codex skill named `notebooklm` for this task.
Follow its instructions, but do not extend the approved RAGenius operation plan.
```

The bridge projects this reference without weakening the rest of the prompt
envelope. Normalized evidence records `codex_explicit_reference`. Ordinary
guidance remains a tested design fallback, but runtime execution must not
silently change activation method for one request.

Neither method includes the source path. Existing NotebookLM runtime guidance
remains conditional on the resolved skill's provider name during the
compatibility period; policy must not depend on the free-text hint.

### OpenClaw

The OpenClaw prompt builder receives the same resolved selection and emits:

```text
Selected Agent skill: spike
Use the installed OpenClaw skill named `spike` for this task.
Follow its instructions, but do not extend the approved RAGenius operation plan.
```

Ordinary prompt guidance is the MVP activation strategy. Direct slash command
or tool dispatch is intentionally deferred because prompt guidance composes with
the existing workspace, artifact, output, and final-response instructions and
was verified against the real CLI.

## Activation Evidence

Normalized provider results add the contract-defined shape:

```ts
type AgentSkillActivation = {
  requested_agent_skill_id?: string;
  requested_provider_skill_name?: string;
  resolved_agent_skill_id?: string;
  resolved_provider_skill_name?: string;
  resolved_fingerprint?: string;
  activation_method:
    | "auto"
    | "codex_explicit_reference"
    | "codex_prompt_guidance"
    | "openclaw_prompt_guidance";
  activation_status:
    | "not_requested"
    | "projected"
    | "process_observed"
    | "not_observed"
    | "failed";
  evidence_level: "none" | "agent_reported" | "process_observed";
  evidence_summary?: string;
};
```

Provider-specific diagnostics may retain a redacted provider-relative skill
file label and observation source. Absolute host and WSL paths may appear only
in bounded administrator diagnostics.

Process observation is provider specific:

- Codex: parse structured bridge events for an observed read/load of the
  resolved skill package.
- OpenClaw: use the provider-returned session file reference, validate its
  containment under the configured agent state root, and parse a bounded tail
  for the resolved skill load/read event.

Model-produced `activated_skills`, prose, or output files are at most
`agent_reported` evidence and do not set `activation_status=process_observed` by
themselves. A task may still complete when activation cannot be observed, but
the result states `activation_status=not_observed`; policy or output verification
failures remain authoritative.

## Stable Errors

- `AGENT_SKILL_NOT_FOUND`
- `AGENT_SKILL_NOT_APPROVED`
- `AGENT_SKILL_NOT_BOUND`
- `AGENT_SKILL_BACKEND_MISMATCH`
- `AGENT_SKILL_FINGERPRINT_CHANGED`
- `AGENT_SKILL_UNAVAILABLE`
- `AGENT_SKILL_AMBIGUOUS`
- `AGENT_SKILL_SOURCE_NOT_ALLOWED`
- `AGENT_SKILL_DISCOVERY_INVALID`
- `AGENT_SKILL_PROJECTION_UNAVAILABLE`

Selection and authorization errors are validation or permission errors with
bounded details and a retry action. Infrastructure failures preserve the
existing error classifier semantics.

## Security And Process Constraints

- Extend service authentication to distinguish scoped callers. The app service
  credential receives execution and `agent_skills:read` scope; the Builder
  credential receives `agent_skills:admin` scope.
  Existing single-token configuration remains a development compatibility mode
  but must not expose administrator routes in production.
- `/v1/admin/agent-skills/*` requires `agent_skills:admin`; app-facing inventory
  requires `agent_skills:read`.
- Governance publication validates instance id, monotonic revision, canonical
  digest, item count, and payload byte limits before atomic activation.
- Normal inventory, selection, confirmation, queue execution, and provider
  invocation make no call to Builder.
- All subprocess arguments are passed as arrays without shell interpolation.
- Discovery has lower timeout and output limits than end-user Agent execution.
- Provider output is schema validated before use.
- Realpath containment applies to every inspected Codex file.
- WSL canonical containment applies to every inspected OpenClaw file.
- Fingerprints cover supporting files, not only `SKILL.md`.
- Public inventory and results never expose protected source paths.
- Selecting a skill does not alter workspace, network, provider-state, or
  confirmation policy.
- Existing Codex run-root containment remains unchanged.
- Existing OpenClaw per-run WSL staging path remains unchanged.
- Shared process-tree supervision must wrap discovery without replacing the
  corrected OpenClaw staging path or its containment checks.

## Tests

### Discovery unit tests

- Codex valid skill, invalid frontmatter, collision, depth limit, byte limit,
  symlink escape, and deterministic fingerprint;
- supporting-file change modifies the fingerprint;
- OpenClaw valid JSON, disabled/ineligible/model-hidden entries, malformed JSON,
  timeout, missing requirements, and WSL path escape;
- incomplete discovery is reported explicitly.

### Selection tests

- structured reference resolves only for the active app and backend;
- selection and inventory work with Builder offline after successful publication;
- no active projection returns empty inventory while explicit selection returns
  `AGENT_SKILL_PROJECTION_UNAVAILABLE`;
- stale client fingerprint fails;
- changed observed fingerprint fails;
- revoked, disabled, unavailable, or unbound skill fails;
- no explicit selection remains Auto;
- legacy hint resolves one unique app-bound skill only;
- explicit failure never falls back to Auto.

### Lifecycle tests

- projection activation is atomic and readers never observe mixed revisions;
- same revision and digest is idempotent;
- lower revision and same-revision/different-digest publication fail;
- failed publication preserves the previous active projection;
- active projection does not expire solely because Builder is offline;
- mismatched Builder publisher identity is rejected;
- selected identity is included in dry-run output and operation plan;
- confirmation snapshot changes when skill identity or fingerprint changes;
- async worker revalidates after queueing;
- queued execution fails after revocation or content change;
- provider prompt contains the resolved provider name but no source path;
- activation evidence does not trust model claims;
- the Codex activation method is chosen only after the production-equivalent
  real CLI comparison passes;
- policy and artifact/output verification behavior is unchanged.

### Real smoke tests

- discover and inspect one administrator-approved Codex skill;
- execute it through Composer and observe provider evidence when available;
- discover and inspect one eligible OpenClaw skill;
- execute it through ordinary prompt guidance and observe the skill read in the
  contained session trace;
- mutate a test skill after approval and verify fail-closed behavior;
- disable an app binding in Builder, verify the active inventory is unchanged,
  publish the reviewed revision, and verify it disappears and cannot
  execute;
- stop Builder after publication and verify inventory and execution still
  work.

## Rollout

1. Add provider-neutral types and mocked adapters.
2. Add Codex discovery and fingerprint tests.
3. Add OpenClaw discovery and WSL inspection tests.
4. Add persistent projection schema, atomic publication, and revision tests.
5. Add projection-backed app-facing inventory.
6. Add structured schema and pre-policy selection resolution.
7. Add async revalidation and confirmation fingerprint coverage.
8. Add provider prompt projection and activation evidence.
9. Run mocked integration tests, then real Codex and OpenClaw smoke tests.

The existing free-text hint remains available until the app and Builder have
deployed structured inventory. Its removal requires a later compatibility
decision.

## Acceptance Criteria

- Discovery is bounded by execution-owned allowlists and containment.
- The execution subsystem never creates or infers Builder approval.
- A Builder-acknowledged projection remains usable while Builder is stopped.
- Projection publication is atomic, monotonic, idempotent, and rollback-safe.
- Public inventory contains only current app-bound selectable skills.
- Explicit selection is resolved before policy and bound to confirmation.
- Async execution revalidates immediately before provider invocation.
- Provider prompts use the resolved provider name without exposing paths.
- Activation evidence distinguishes request, resolution, and process
  observation.
- Existing Agent workspace, artifact, policy, confirmation, and process
  supervision contracts remain intact.
