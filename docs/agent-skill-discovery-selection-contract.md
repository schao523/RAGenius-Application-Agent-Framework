# Agent Skill Discovery And Selection Contract

Date: 2026-08-04

## Status

Normative cross-subsystem contract for discovering, approving, binding,
selecting, validating, and activating instruction skills used by Agent
execution backends.

This contract extends:

- `docs/agent-execution-lifecycle-evidence-contract.md`
- `docs/agent-mode-artifact-creation-reuse-contract.md`
- `docs/openclaw-agent-execution-integration-contract.md`
- `ragenius_execution_subsystem/docs/openclaw-execution-contract.md`

Those contracts remain authoritative for execution lifecycle, confirmation,
policy, artifacts, provider process management, and result verification. This
contract is authoritative for Agent-skill catalog, approval, binding,
selection, and activation semantics.

## Purpose

Execution Composer should let a user select an administrator-approved Codex or
OpenClaw instruction skill without remembering or typing its provider name.

The feature must not:

- confuse instruction skills with executable RAGenius skills;
- expose arbitrary host or WSL filesystem paths to end users;
- treat discovery, installation, or eligibility as administrator approval;
- allow a selected skill to weaken Agent policy or confirmation;
- silently fall back to automatic skill selection when an explicit selection
  is unavailable;
- trust a model claim as proof that a selected skill was activated.

## Scope

This contract applies to:

- administrator-configured Codex skill directories;
- OpenClaw skills visible to a configured OpenClaw agent;
- Builder discovery review and approval;
- per-application Agent-skill bindings;
- app-facing Agent-skill inventory;
- Execution Composer Agent-skill selection;
- execution-time resolution, revalidation, activation, and evidence;
- change detection and re-approval.

This contract does not define:

- creating or editing instruction skills;
- automatic skill installation or publication;
- direct OpenClaw tool-dispatch skills;
- selecting more than one Agent skill per execution;
- changing Codex or OpenClaw provider permissions;
- RAGenius executable skill definitions or workflows;
- cross-application sharing of app-owned data.

## Terminology

**Agent skill** means a provider-native instruction package, normally rooted at
a `SKILL.md` file, that teaches Codex or OpenClaw how to perform a class of
tasks.

**RAGenius skill** means a Builder-published executable skill invoked through
`request_type = "execute_skill"`. It is a different resource type.

**Agent-skill source** means an administrator-configured discovery boundary,
such as a contained Codex directory or a configured OpenClaw agent inventory.

**Discovered skill** means a provider skill reported by an authoritative
discovery adapter. Discovery is not approval.

**Approved skill** means a discovered skill whose exact reviewed fingerprint
has been approved by a Builder administrator.

**App binding** means permission for one approved Agent skill to appear and be
selected for one RAGenius application.

**Auto** means no explicit Agent skill is selected. Auto is represented by the
absence of an Agent-skill reference, not by a synthetic approved skill.

## Product Rules

1. Agent skills and RAGenius skills must use separate catalogs and APIs.
2. Builder is the control plane for sources, review, approval, enablement, and
   app binding.
3. The execution subsystem is authoritative for provider discovery, runtime
   availability, selection validation, activation projection, and evidence.
4. `ragenius_app_skeleton` only displays app-bound inventory and submits a
   structured selection.
5. A provider skill name is a hint to a provider, not an authorization
   credential.
6. Approval applies to an exact content fingerprint.
7. Any reviewed content change invalidates the approval until re-reviewed.
8. Explicit selection fails closed. It must never degrade to Auto silently.
9. Skill approval does not grant filesystem, network, credential, external
   write, or destructive permissions.
10. The existing Agent policy and confirmation lifecycle remains authoritative.

## Subsystem Responsibilities

### `ragenius_builder`

Builder owns:

- administrator authentication and authorization;
- Agent-skill source records;
- discovery review UI;
- approval and disable decisions;
- reviewed fingerprint snapshots;
- per-app Agent-skill bindings;
- audit history for administrative changes;
- display of unavailable, changed, or missing requirements.

Builder must not:

- execute Agent skills;
- invoke Codex or OpenClaw for end-user work;
- infer runtime eligibility without execution-subsystem evidence;
- treat a directory path supplied by an ordinary user as approved;
- expose protected source paths in user-facing APIs.

### `ragenius_execution_subsystem`

The execution subsystem owns:

- provider-specific discovery adapters;
- containment and source validation;
- Codex `SKILL.md` metadata and fingerprint inspection;
- OpenClaw skill inventory invocation and normalization;
- execution-time approval and app-binding validation;
- provider-specific activation projection;
- activation evidence and normalized diagnostics;
- fail-closed behavior when selected skill state is stale or unavailable.

The execution subsystem must not:

- create Builder approvals;
- accept a client-provided path as an Agent-skill source;
- expose host or WSL source paths to ordinary users;
- bypass policy because a skill is approved;
- report a skill as activated from model text alone.

### `ragenius_app_skeleton`

The app owns:

- requesting the current app's selectable Agent-skill inventory;
- backend-sensitive Agent Skill picker UX;
- preserving Auto as an explicit choice;
- submitting the selected structured Agent-skill reference;
- showing selection and activation status in execution details.

The app must not:

- scan local files or WSL directories;
- discover provider skills directly;
- submit raw skill paths;
- show skills not bound to the active app;
- reinterpret an unavailable explicit selection as Auto.

## Provider-Neutral Data Contract

### Backend And Source Kinds

```ts
type AgentSkillBackend = "codex_cli" | "openclaw_cli";

type AgentSkillSourceKind =
  | "codex_directory"
  | "openclaw_agent_inventory";
```

### Source Record

```ts
type AgentSkillSource = {
  source_id: string;
  backend: AgentSkillBackend;
  source_kind: AgentSkillSourceKind;
  display_name: string;
  enabled: boolean;
  runtime_target_id: string;
  protected_locator_ref: string;
  precedence: number;
  created_at: string;
  updated_at: string;
};
```

Rules:

- `source_id` is an opaque Builder-owned identifier.
- `runtime_target_id` identifies the configured runtime target, such as a
  Codex runtime profile or OpenClaw agent id.
- `protected_locator_ref` refers to protected configuration. Public inventory
  must not contain the underlying Windows or WSL path.
- Only administrators may create, update, enable, disable, or delete a source.
- Source precedence must be deterministic.

### Discovered Catalog Entry

```ts
type AgentSkillCatalogEntry = {
  agent_skill_id: string;
  backend: AgentSkillBackend;
  runtime_target_id: string;
  source_id: string;
  provider_skill_name: string;
  provider_skill_reference: string;
  display_name: string;
  description: string;
  source_kind: AgentSkillSourceKind;
  source_label: string;
  content_fingerprint: string;
  discovered_at: string;
  last_seen_at: string;
  discovery_status:
    | "available"
    | "ineligible"
    | "disabled_at_provider"
    | "missing"
    | "invalid"
    | "source_unavailable";
  model_visible: boolean;
  user_invocable: boolean;
  direct_tool_dispatch: boolean;
  missing_requirements: {
    bins: string[];
    env: string[];
    config: string[];
    os: string[];
  };
  provider_metadata: Record<string, unknown>;
};
```

Identity rules:

- `agent_skill_id` is an opaque stable catalog id.
- The stable logical identity is the tuple of `backend`, `runtime_target_id`,
  `source_id`, and `provider_skill_reference`.
- `provider_skill_reference` excludes provider prompt syntax such as `$`.
- Standalone and OpenClaw skills use `provider_skill_name`; Codex plugin skills
  use `<plugin-name>:<provider_skill_name>`.
- `content_fingerprint` is not the stable id. It is the reviewed content
  version used to invalidate stale approval.
- Same-name skills from different sources remain distinct catalog entries.
- Provider precedence may choose one effective entry at runtime, but Builder
  must retain source identity and show collisions to administrators.
- Public user inventory must not expose source paths, credential names, raw
  environment values, or unrestricted provider metadata.

### Approval Record

```ts
type AgentSkillApproval = {
  approval_id: string;
  agent_skill_id: string;
  approved_fingerprint: string;
  state:
    | "approved"
    | "disabled"
    | "changed_pending_review"
    | "revoked";
  approved_by: string;
  approved_at: string;
  reviewed_source: string;
  review_notes?: string;
  updated_at: string;
};
```

Rules:

- Approval is valid only when `approved_fingerprint` exactly equals the current
  discovered `content_fingerprint`.
- A changed fingerprint transitions effective state to
  `changed_pending_review`; it does not update approval automatically.
- A missing or unavailable skill does not delete approval history.
- Re-approval creates an auditable approval event.

### Application Binding

```ts
type AppAgentSkillBinding = {
  binding_id: string;
  app_id: string;
  agent_skill_id: string;
  enabled: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
};
```

Rules:

- Bindings are app-scoped.
- A binding is selectable only while the source, catalog entry, approval, and
  binding are all enabled and current.
- Binding one skill to one app must not expose it to another app.
- Existing Builder `app_skill_bindings` for executable RAGenius skills must not
  be reused without an explicit resource-type discriminator. Separate storage
  is preferred for the MVP.

## Discovery Contract

### Codex Discovery

Codex discovery uses only administrator-configured `codex_directory` sources.

The execution subsystem must:

1. resolve the configured source root;
2. verify that it is an allowed directory;
3. discover `SKILL.md` files to a bounded depth;
4. reject any resolved skill path that escapes the configured root;
5. parse required frontmatter fields without executing skill content;
6. calculate a deterministic fingerprint over the complete reviewed skill
   package or the exact bounded files included by the approved fingerprint
   algorithm;
7. report invalid, duplicate, and colliding entries explicitly;
8. return normalized metadata without public absolute paths.

Symlink traversal must fail closed unless a specific resolved target root was
approved by an administrator. A broad permission to follow arbitrary symlinks
is forbidden.

The fingerprint algorithm and included-file rules must be versioned so an
algorithm change does not masquerade as a content change.

### OpenClaw Discovery

OpenClaw discovery uses the provider CLI as the authoritative inventory for the
configured agent:

```text
wsl -d <configured-distro> --exec openclaw skills list --agent <agent-id> --json
```

The execution subsystem must normalize at least:

- `name`;
- `description`;
- `eligible`;
- `disabled`;
- `modelVisible`;
- `userInvocable`;
- `commandVisible`;
- `source`;
- `bundled`;
- missing requirements.

Builder does not need to scan OpenClaw WSL directories independently. OpenClaw
owns its source precedence and agent-visible inventory.

The MVP selectable set requires:

```text
eligible = true
disabled = false
modelVisible = true
direct_tool_dispatch = false
```

`userInvocable` and `commandVisible` remain visible to administrators. They are
not sufficient approval and do not replace `modelVisible` for the MVP prompt
activation method.

The adapter must derive or obtain a stable content fingerprint for the exact
effective skill. If OpenClaw inventory does not return one, the adapter may use
a contained provider inspection command or a provider-owned immutable version
identifier. It must not invent a fingerprint from description text alone.

### Discovery Is Read-Only

Discovery must not:

- install, update, enable, disable, or delete skills;
- modify Codex, OpenClaw, Builder, or app configuration;
- trigger skill execution;
- load secrets into responses;
- approve or bind a discovered skill automatically.

Discovery failures must preserve the last catalog snapshot for administrator
inspection while marking it stale or unavailable. Stale entries are not
selectable unless runtime revalidation confirms the approved fingerprint.

## User-Facing Inventory Contract

The app-facing inventory is provider-neutral:

```ts
type SelectableAgentSkill = {
  agent_skill_id: string;
  backend: AgentSkillBackend;
  provider_skill_name: string;
  display_name: string;
  description: string;
  approved_fingerprint: string;
  availability: "available";
};
```

Request scope:

```text
GET /agent-skills?app_id=<app-id>&backend=<codex_cli|openclaw_cli>
```

The concrete route may differ by subsystem, but the semantics are fixed:

- ordinary users receive only selectable entries bound to the requested app;
- backend is explicit;
- Auto is added by the frontend and is not returned as a catalog entry;
- protected source locations and administrative diagnostics are omitted;
- app identity checks occur before inventory is returned.

Builder administrator inventory may additionally include unavailable entries,
source labels, missing requirements, fingerprints, collisions, and review
state.

## Execution Request Contract

New Composer submissions use a structured Agent-skill reference:

```ts
type AgentSkillRef = {
  agent_skill_id: string;
  approved_fingerprint: string;
};

type ExecuteAgentRequest = {
  request_type: "execute_agent";
  app_id: string;
  session_id: string;
  agent_backend: AgentSkillBackend;
  agent_query: string;
  agent_skill_ref?: AgentSkillRef;
  agent_skill_hint?: string;
  // Existing artifact, output, context, and execution options remain unchanged.
};
```

Rules:

- Auto omits both `agent_skill_ref` and `agent_skill_hint`.
- New UI flows submit `agent_skill_ref`.
- `agent_skill_hint` remains temporarily for backward compatibility with
  existing typed commands and integrations.
- `agent_skill_hint` is never authorization and must resolve uniquely to a
  currently approved, app-bound entry before activation.
- If both fields are present, they must resolve to the same backend skill or
  validation fails.
- The selected entry backend must equal `agent_backend`.
- The client-provided fingerprint is an optimistic-concurrency check. The
  execution subsystem independently loads the authoritative current approval
  and discovery state.
- Raw source paths are forbidden.

The eventual preferred command grammar may include a structured backend skill
selection. This contract does not require users to type provider skill names.

## Execution-Time Validation

Before policy confirmation or provider invocation, the execution subsystem
must validate an explicit Agent-skill selection in this order:

1. request backend matches catalog backend;
2. source exists and is enabled;
3. catalog entry exists and is valid;
4. provider reports the skill available for the configured runtime target;
5. current content fingerprint matches the approved fingerprint;
6. approval state is `approved`;
7. app binding exists and is enabled;
8. provider-specific MVP eligibility rules pass;
9. requested skill does not require an unsupported activation method.

Any failure stops before provider invocation and must not consume a pending
confirmation as a successful run.

Validation must use execution's active, atomically published trusted read
model. Builder owns draft governance, but the app never reads Builder and a
draft mutation is not runtime-effective. Client-provided approval, binding,
eligibility, or path fields are untrusted.

The resolved `agent_skill_id`, backend, runtime target, provider skill name,
and approved fingerprint must be included in the immutable operation plan and
policy/confirmation fingerprint. Confirmation issued for one skill version
must not authorize another version or Auto execution.

## Activation Contract

### Provider-Neutral Rules

- Exactly zero or one Agent skill may be selected in the MVP.
- The provider adapter receives a resolved immutable selection, not an
  arbitrary string.
- Provider prompts use the canonical `provider_skill_reference` from the
  resolved selection. Provider-specific compatibility logic may continue to
  use `provider_skill_name` as the manifest identity.
- User text cannot override the resolved selection.
- The selected skill augments task instructions; it does not override RAGenius
  authorization, staged-input, expected-output, or final-result requirements.
- Provider-specific activation must be deterministic enough to test and must
  not rely solely on semantic auto-selection.

### Codex Activation

Codex activation must use a provider-supported explicit skill reference or an
equivalent validated prompt projection. The implementation design must confirm
the exact current Codex CLI behavior with a real CLI test before choosing the
final syntax.

Codex must run with the same runtime home and skill roots used for discovery.
Discovering from one profile and executing against another is forbidden.

### OpenClaw Activation

Observed real CLI tests on 2026-08-04 confirmed both:

```text
/spike <request>
```

and:

```text
Use the installed OpenClaw skill named spike. Read its SKILL.md before acting.
```

caused the configured `main` agent to read the exact effective
`spike/SKILL.md` and follow its output structure.

The MVP should use validated ordinary prompt guidance because it composes with
the existing RAGenius authorization, staged-input, expected-output, and final
response prompt. Direct slash-command and direct-tool-dispatch activation are
out of scope until separately tested with the RAGenius prompt envelope.

## Activation Evidence

Normalized results must distinguish request, resolution, and observation:

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

Rules:

- Model text alone is at most `agent_reported` and cannot produce
  `process_observed`.
- A trusted bridge observation that the exact effective `SKILL.md` was read may
  produce `process_observed`.
- Provider output field `activated_skills` remains advisory unless backed by
  trusted process evidence.
- Public evidence must not expose protected absolute paths.
- Diagnostics may retain a redacted source label and fingerprint.
- The UI must say `requested` or `activation not observed` when activation was
  not independently observed; it must not say `used` as a fact.

Task success remains governed by the Agent lifecycle and operation-evidence
contract. Skill activation evidence does not replace output or external
operation verification.

## Policy And Security Contract

Agent-skill approval and Agent execution authorization are separate decisions.

An approved skill:

- may be selected;
- may contribute instructions;
- does not grant new permissions;
- does not bypass confirmation;
- does not make external provider claims trusted;
- does not make its source code trusted for unrestricted execution.

The execution subsystem must classify the actual request and operation plan
using the existing Agent policy. Skill metadata may raise the minimum risk or
declare required capabilities, but it must never lower policy derived from the
request.

Third-party skills must be treated as untrusted instruction content. Builder
review should show source, fingerprint/version, requirements, provider trust
metadata when available, and change history.

Secrets, tokens, credential paths, and raw environment values must not appear
in catalog, approval, binding, app inventory, execution result, or logs.

## Fail-Closed Error Contract

The execution subsystem should use stable error codes:

```text
AGENT_SKILL_NOT_FOUND
AGENT_SKILL_BACKEND_MISMATCH
AGENT_SKILL_SOURCE_DISABLED
AGENT_SKILL_SOURCE_UNAVAILABLE
AGENT_SKILL_INELIGIBLE
AGENT_SKILL_DISABLED_AT_PROVIDER
AGENT_SKILL_NOT_APPROVED
AGENT_SKILL_NOT_BOUND_TO_APP
AGENT_SKILL_CHANGED
AGENT_SKILL_NAME_AMBIGUOUS
AGENT_SKILL_ACTIVATION_UNSUPPORTED
AGENT_SKILL_ACTIVATION_FAILED
```

Errors must be recoverable when an administrator can refresh discovery,
approve, re-bind, or restore requirements. Suggested actions must not reveal
protected paths to ordinary users.

No explicit-selection error may trigger Auto fallback.

## Refresh, Cache, And Drift

- Discovery may be cached for bounded UX performance.
- Builder must expose the last discovery time and stale status to
  administrators.
- Execution-time validation must not rely solely on an app-facing cached list.
- The current provider identity and fingerprint must be checked before
  invocation.
- A skill disappearing during a queued execution fails that execution before
  provider activation.
- A skill changing after confirmation invalidates the confirmed policy input
  and fails closed; the user must resubmit after administrator re-approval.
- Concurrent discovery refreshes must not create duplicate catalog identities.

## Audit Contract

Builder must retain auditable events for:

- source creation, update, enable, disable, and deletion;
- discovery refresh outcome;
- skill approval, re-approval, disable, and revocation;
- app binding creation, enable, disable, and deletion;
- detected fingerprint changes.
- publication attempts, successes, and failures, including actor, local
  revision, correlation id, outcome, and bounded change counts.

Builder catalog views are source-backed: one active aggregate, one tab per
enabled source, and retained disabled-source history. Disabling or re-enabling
a source changes only the local draft. Approval and binding-enable operations
are rejected while the source is disabled. Runtime authorization changes only
after an administrator reviews and publishes the complete local revision.

The publication preview compares the current canonical projection with the
last execution-acknowledged redacted baseline. The baseline contains only
stable source, Agent-skill, fingerprint, approval, app, and binding fields. It
must exclude protected locators, filesystem paths, credentials, tokens, and
raw provider output. A missing trustworthy baseline produces an explicit
full-replacement preview, never an invented empty history.

Publication is compare-and-set on `expected_local_revision`. Execution must
acknowledge the exact Builder instance, revision, and digest before Builder
updates its published revision or baseline. Stale review, transport failure,
or acknowledgment mismatch leaves the previous execution revision active and
all local edits in draft. The legacy synchronize endpoint may delegate to this
same service temporarily, but new UI and clients use publication APIs.

Execution results must retain:

- selected Agent-skill id;
- backend and runtime target label;
- approved and resolved fingerprint;
- activation method and status;
- bounded activation evidence;
- validation failure code when invocation was blocked.

User-facing results must not expose protected locators.

## Backward Compatibility

- Existing Agent requests without a skill selection continue as Auto.
- Existing `agent_skill_hint = "notebooklm"` remains supported during migration
  only when it resolves to one approved Codex Agent skill bound to the app.
- Existing RAGenius skill inventory and `execute_skill` behavior do not change.
- Existing artifact, confirmation, sync/async, status, and result contracts do
  not change.
- OpenClaw execution without an Agent-skill selection remains supported.

The migration must include an explicit administrator action to approve and bind
previously hardcoded hints. Hardcoded frontend options must be removed only
after the app-facing inventory is available.

## MVP Acceptance Criteria

### Discovery

- Codex returns only skills contained by configured approved source roots.
- OpenClaw discovery uses the configured agent's JSON inventory.
- Invalid, unavailable, ineligible, disabled, and colliding skills are visible
  to administrators with reasons.
- Ordinary user inventory contains no protected source paths.

### Approval And Binding

- Discovery does not auto-approve.
- Approval stores the exact reviewed fingerprint.
- A changed fingerprint blocks selection until re-approved.
- App A binding does not expose the skill to App B.

### Selection

- Composer switches inventory when backend changes.
- Auto submits no Agent-skill reference.
- Explicit selection submits a structured `agent_skill_ref`.
- Missing or stale selection fails without provider invocation or Auto
  fallback.
- Composer refreshes execution's trusted inventory on open, backend change,
  window focus return while open, and explicit user refresh. It does not call
  Builder, and an unchanged `inventory_revision` preserves the current list
  and valid selection.

### Activation

- Codex and OpenClaw adapters project the exact resolved provider skill name.
- Selected-skill metadata is recorded separately from provider claims.
- OpenClaw prompt-guidance activation has a real CLI regression test.
- Direct-tool-dispatch OpenClaw skills are excluded.

### Security And Lifecycle

- Skill approval does not bypass policy or confirmation.
- Sync and async execution apply identical selection validation.
- Queued runs revalidate before invocation.
- Status, diagnostics, and artifacts remain app/session scoped.

## Deferred Work

- multiple selected Agent skills;
- automatic installation or updates;
- ClawHub publication and lifecycle management;
- OpenClaw slash-command and direct tool dispatch;
- Agent-created skill proposals;
- cross-app Agent-skill bindings;
- user-managed skill directories;
- automatic approval based on provider trust metadata;
- distributed discovery workers or multi-instance catalog leases.
