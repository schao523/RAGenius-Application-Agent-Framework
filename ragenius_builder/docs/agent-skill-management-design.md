# Agent Skill Management Design

Date: 2026-08-04

## Status

Subsystem design for the Builder responsibilities defined by
`docs/agent-skill-discovery-selection-contract.md`.

This document is not a replacement for that contract. If this design and the
cross-subsystem contract disagree, the contract is authoritative.

## Objective

Add an administrator-only Builder workflow for registering approved Agent-skill
sources, reviewing discovered Codex and OpenClaw skills, approving exact content
fingerprints, and binding approved skills to RAGenius applications.

Builder remains a control plane. It does not scan provider directories itself,
invoke provider skills for end-user work, or decide runtime eligibility without
execution-subsystem evidence.

## Existing Extension Points

The current Builder Flask application already provides useful patterns:

- `flask_scaffold/storage.py` initializes SQLite tables and owns persistence
  helpers.
- `skills`, `skill_versions`, and `app_skill_bindings` model executable RAGenius
  skill packages.
- `flask_scaffold/app.py` exposes JSON APIs and server-rendered administrator
  pages.
- `skills_list.html`, `skill_detail.html`, and `app_detail.html` provide the
  visual conventions for catalog and app-binding management.

Agent skills must not reuse `skills`, `skill_versions`, or
`app_skill_bindings`. Those tables encode imported package versions,
publication states, permission modes, and executable workflow semantics that do
not apply to provider-owned instruction skills.

## Architecture

Builder adds one bounded Agent Skill administration module with three layers:

1. Storage persists sources, catalog snapshots, approvals, app bindings, and
   audit events.
2. A service client asks the execution subsystem to discover and inspect
   provider skills.
3. Administrator pages and APIs manage governance state and display execution
   subsystem evidence.

The module may initially live in the existing Flask files, but its storage and
service-client functions should be grouped under Agent-skill-specific names so
they can be extracted later without changing the API.

## Persistence Model

### `agent_skill_sources`

| Column | Type | Rules |
| --- | --- | --- |
| `id` | TEXT | Primary key, opaque UUID |
| `backend` | TEXT | `codex_cli` or `openclaw_cli` |
| `source_kind` | TEXT | `codex_directory` or `openclaw_agent_inventory` |
| `display_name` | TEXT | Administrator-facing name |
| `runtime_target_id` | TEXT | Execution-configured runtime target |
| `protected_locator_ref` | TEXT | Opaque reference understood by execution subsystem |
| `precedence` | INTEGER | Deterministic ordering, lower value wins |
| `enabled` | INTEGER | Boolean |
| `created_at` | TEXT | UTC ISO-8601 |
| `updated_at` | TEXT | UTC ISO-8601 |

`protected_locator_ref` is selected from execution-configured source options and
is not returned by ordinary user-facing APIs. For a Codex directory source it
refers to a locator registered in execution-subsystem configuration; Builder
does not submit or persist the path. For an OpenClaw source it identifies an
execution-configured agent inventory.

The database should enforce a uniqueness constraint over
`(backend, runtime_target_id, protected_locator_ref)`.

### `agent_skill_catalog`

| Column | Type | Rules |
| --- | --- | --- |
| `id` | TEXT | `agent_skill_id`, opaque stable UUID |
| `backend` | TEXT | Provider backend |
| `runtime_target_id` | TEXT | Runtime target used for discovery |
| `source_id` | TEXT | Foreign key to `agent_skill_sources` |
| `provider_skill_name` | TEXT | Provider-native name |
| `display_name` | TEXT | Normalized display label |
| `description` | TEXT | Normalized description |
| `content_fingerprint` | TEXT | Algorithm-qualified digest |
| `discovery_status` | TEXT | Contract-defined status |
| `model_visible` | INTEGER | Boolean |
| `user_invocable` | INTEGER | Boolean |
| `direct_tool_dispatch` | INTEGER | Boolean |
| `missing_requirements_json` | TEXT | Normalized requirements object |
| `provider_metadata_json` | TEXT | Redacted diagnostic metadata |
| `discovered_at` | TEXT | First discovery time |
| `last_seen_at` | TEXT | Most recent successful sighting |
| `updated_at` | TEXT | Most recent record update |

The logical identity uniqueness constraint is
`(backend, runtime_target_id, source_id, provider_skill_name)`. A fingerprint
change updates the existing catalog row; it does not create a new logical
skill.

Provider metadata stored here must already be redacted by the execution
subsystem. Builder must not persist credential values, unrestricted environment
variables, or raw provider state.

### `agent_skill_approvals`

| Column | Type | Rules |
| --- | --- | --- |
| `id` | TEXT | Primary key |
| `agent_skill_id` | TEXT | Foreign key to catalog |
| `approved_fingerprint` | TEXT | Exact reviewed fingerprint |
| `state` | TEXT | `approved`, `revoked`, or `superseded` |
| `review_notes` | TEXT | Optional administrator notes |
| `approved_by` | TEXT | Administrator identity |
| `approved_at` | TEXT | UTC ISO-8601 |
| `updated_at` | TEXT | UTC ISO-8601 |

Only one `approved` record may be effective for a catalog entry. Approval of a
new fingerprint marks the previous approval `superseded` in the same
transaction. A changed catalog fingerprint makes the previous approval stale
without deleting its audit history.

### `app_agent_skill_bindings`

| Column | Type | Rules |
| --- | --- | --- |
| `id` | TEXT | Primary key |
| `app_id` | TEXT | Foreign key to applications |
| `agent_skill_id` | TEXT | Foreign key to catalog |
| `enabled` | INTEGER | Boolean |
| `created_by` | TEXT | Administrator identity |
| `created_at` | TEXT | UTC ISO-8601 |
| `updated_at` | TEXT | UTC ISO-8601 |

The table has a uniqueness constraint over `(app_id, agent_skill_id)`. It does
not duplicate Agent execution policy. Existing Agent policy and confirmation
remain execution-subsystem concerns.

### `agent_skill_audit_events`

Audit records are append-only and contain:

- event id and UTC timestamp;
- administrator or service actor id;
- action;
- affected source, skill, approval, binding, and app ids when applicable;
- before and after state as bounded redacted JSON;
- request correlation id when available.

At minimum, source changes, discovery refreshes, approvals, revocations,
enablement changes, and app-binding changes are audited.

### `agent_skill_projection_state`

Builder maintains one synchronization state row:

| Column | Type | Rules |
| --- | --- | --- |
| `builder_instance_id` | TEXT | Stable operator-configured publisher identity |
| `local_revision` | INTEGER | Monotonically increasing governance revision |
| `published_revision` | INTEGER | Last execution-acknowledged revision |
| `published_digest` | TEXT | Digest acknowledged for that revision |
| `sync_status` | TEXT | `synchronized`, `pending`, or `failed` |
| `last_attempt_at` | TEXT | Optional UTC ISO-8601 |
| `last_success_at` | TEXT | Optional UTC ISO-8601 |
| `last_error_code` | TEXT | Optional bounded code |
| `last_error_message` | TEXT | Optional bounded administrator message |

Every governance mutation that can change runtime authorization increments
`local_revision` and sets `sync_status = pending` in the same SQLite
transaction. Discovery metadata changes that do not alter an approval, source
enablement, or app binding need not publish until they affect the projected
runtime state.

`builder_instance_id` is supplied through Builder configuration and persisted
with projection state. Revision generation uses
`max(previous_revision + 1, current_utc_epoch_milliseconds)` so database restore
or rapid consecutive writes cannot reuse an acknowledged revision. Changing the
publisher identity is an operator-controlled trust rotation, not an ordinary UI
operation.

The projection state is not an execution authorization source by itself. It
tracks whether execution has acknowledged Builder's latest complete snapshot.

## Derived Governance State

Builder computes a display state without rewriting historical approvals:

- `approved`: current fingerprint has an active approval;
- `changed_pending_review`: an approval exists, but its fingerprint differs;
- `pending_review`: discovered but never approved;
- `revoked`: latest governing decision is revoked;
- `unavailable`: current discovery status is not `available`;
- `source_disabled`: source is disabled.

An app binding is effective only when all of the following are true:

- source is enabled;
- catalog status is `available`;
- current fingerprint is approved;
- approval is active;
- binding is enabled;
- provider capability flags satisfy the MVP selection rules.

This derived state is informative. The execution subsystem revalidates it at
request and execution time.

## Execution-Subsystem Client

Builder adds a dedicated service-authenticated client rather than importing
execution-subsystem code.

The client uses a Builder-specific credential with `agent_skills:admin` scope.
It must not reuse the app runtime credential in production.

Builder calls the execution subsystem for discovery and governance publication
only. The execution subsystem never calls Builder during ordinary inventory,
selection, confirmation, queued execution, or provider invocation.

### Source options

`GET /v1/admin/agent-skills/source-options`

Builder uses this endpoint to populate allowed source choices. Returned options
contain an opaque locator reference, backend, runtime target, and redacted
display label, never the underlying path.

### Discovery request

`POST /v1/admin/agent-skills/discover`

```json
{
  "source_id": "source_...",
  "backend": "codex_cli",
  "source_kind": "codex_directory",
  "runtime_target_id": "codex-local-default",
  "protected_locator_ref": "codex-source-ref-1"
}
```

The response contains normalized catalog candidates and a discovery summary.
It does not grant approval and must not return an unrestricted source path.

Builder validates that returned entries match the requested source and backend
before persisting them.

### Refresh transaction

For one source refresh, Builder:

1. records an audit event that discovery started;
2. calls the execution subsystem outside the SQLite write transaction;
3. validates the complete response;
4. begins a transaction;
5. upserts entries by logical identity;
6. preserves stable `agent_skill_id` values;
7. marks previously seen but absent entries `missing`;
8. commits the catalog and one refresh audit event atomically.

If discovery fails, Builder leaves the last successful catalog intact, records
the failure, and displays the source as stale or unavailable. A failed refresh
must not revoke approvals automatically, but unavailable skills are not
selectable.

## Builder APIs

All administrative endpoints require the existing Builder administrator
authorization boundary.

### Sources

- `GET /api/agent-skill-sources`
- `POST /api/agent-skill-sources`
- `PATCH /api/agent-skill-sources/{source_id}`
- `POST /api/agent-skill-sources/{source_id}/discover`

Source creation validates backend/source-kind compatibility and requires a
reference currently returned by the execution subsystem's source-options API.
Builder never accepts a raw host or WSL path in this API. Ordinary responses use
the redacted locator label.

### Catalog and approval

- `GET /api/agent-skills`
- `GET /api/agent-skills/{agent_skill_id}`
- `POST /api/agent-skills/{agent_skill_id}/approve`
- `POST /api/agent-skills/{agent_skill_id}/revoke`

Approval requests include the fingerprint displayed to the administrator. The
write uses compare-and-set semantics: if the current fingerprint differs, the
request fails with `AGENT_SKILL_FINGERPRINT_CHANGED` and requires refresh and
review.

### Application bindings

- `GET /api/apps/{app_id}/agent-skill-bindings`
- `POST /api/apps/{app_id}/agent-skill-bindings`
- `PATCH /api/apps/{app_id}/agent-skill-bindings/{binding_id}`
- `DELETE /api/apps/{app_id}/agent-skill-bindings/{binding_id}`

Creation requires a currently approved fingerprint but does not guarantee the
skill will remain selectable if provider state changes later.

### Governance projection publication

Builder publishes its complete Agent-skill governance read model to:

`PUT /v1/admin/agent-skills/governance-projection`

The request is a complete snapshot, not a sequence of mutation commands:

```json
{
  "builder_instance_id": "builder_...",
  "revision": 42,
  "generated_at": "2026-08-04T00:00:00.000Z",
  "digest": "sha256:...",
  "items": [
    {
      "app_id": "app_...",
      "agent_skill_id": "agent_skill_...",
      "backend": "codex_cli",
      "runtime_target_id": "codex-local-default",
      "source_id": "source_...",
      "protected_locator_ref": "codex-source-ref-1",
      "provider_skill_name": "notebooklm",
      "display_name": "NotebookLM",
      "description": "Use NotebookLM through the configured runtime.",
      "current_fingerprint": "sha256:v1:...",
      "approved_fingerprint": "sha256:v1:...",
      "source_enabled": true,
      "approval_state": "approved",
      "binding_enabled": true,
      "model_visible": true,
      "user_invocable": true,
      "direct_tool_dispatch": false
    }
  ]
}
```

The digest is calculated over a canonical serialization of
`builder_instance_id`, `revision`, and sorted items. Items include both enabled
and disabled/revoked governance records needed for stable runtime diagnostics;
they exclude audit history, administrator identities, raw paths, and provider
secrets.

The execution subsystem validates the full snapshot and atomically activates
it. Its response echoes the accepted instance id, revision, and digest. Builder
marks a revision `synchronized` only when all three values match.

Publication rules:

- same instance, revision, and digest is idempotent success;
- same revision with a different digest is rejected;
- a lower revision is rejected as rollback;
- execution never observes a partially written snapshot;
- a new `builder_instance_id` requires an explicit operator trust rotation in
  execution configuration and cannot replace the active publisher through this
  endpoint;
- failed publication leaves the previous execution projection active and the
  Builder change visibly `pending` or `failed`;
- Builder retries the latest complete snapshot on startup, after relevant
  mutations, and through a manual `Synchronize now` action.

Builder does not claim a restrictive change such as revocation, source disable,
or unbinding is runtime-effective until the corresponding revision is
acknowledged. The UI must warn administrators when the previous execution
projection remains active.

## Administrator UX

Builder adds an `Agent Skills` navigation item separate from `Skills`.

### Sources view

The source view supports:

- add, edit, enable, and disable;
- selection from execution-configured backend and runtime-target options;
- redacted source locator display;
- manual discovery refresh;
- last successful refresh and last error;
- counts by available, changed, unavailable, and missing state.

No source is auto-approved after creation or refresh.

### Catalog review view

The catalog view supports filtering by backend, source, approval state,
availability, and name. Each detail page displays normalized metadata,
requirements, provider capability flags, current fingerprint, approved
fingerprint, collision warnings, last seen time, and bounded provider evidence.

Approval and re-approval are explicit administrator actions. Re-approval must
show that content changed and require confirmation of the new fingerprint.

### App binding view

The application detail page gets a separate `Agent Skills` section. It lists
approved skills by backend and allows an administrator to bind or unbind them.
Changed, revoked, unavailable, or disabled skills remain visible to the
administrator with a reason but cannot be newly enabled.

### Synchronization status

The Agent Skills administration surface shows local revision, active execution
revision, last successful synchronization, and the latest bounded error. After
an approval, revocation, source enablement change, or binding mutation, it shows
whether that exact change is pending or active in execution.

`Synchronize now` republishes the latest complete snapshot. It does not perform
discovery and does not create approvals.

## Error Handling

Builder maps execution-subsystem errors to stable administrator-facing states:

- `AGENT_SKILL_SOURCE_NOT_ALLOWED`: source is outside the runtime allowlist;
- `AGENT_SKILL_SOURCE_UNAVAILABLE`: provider or source cannot be inspected;
- `AGENT_SKILL_DISCOVERY_INVALID`: provider output did not satisfy the schema;
- `AGENT_SKILL_FINGERPRINT_CHANGED`: approval compare-and-set failed;
- `AGENT_SKILL_BACKEND_MISMATCH`: source and backend are inconsistent;
- `EXECUTION_SUBSYSTEM_UNAVAILABLE`: retain the last catalog and show stale
  status.

Error messages shown in HTML must not contain protected paths, credentials, or
raw provider output. Full bounded diagnostics belong in server logs and audit
metadata accessible only to administrators.

## Security

- Builder administrator authorization protects all mutation endpoints.
- Builder-to-execution and execution-to-Builder runtime calls use service
  authentication.
- CSRF protection applies to server-rendered mutation forms.
- Locators are never accepted from ordinary app users.
- Discovery results are schema validated and treated as untrusted input.
- Provider metadata is allowlisted before persistence and rendering.
- Runtime projection publication uses a Builder-specific scoped credential.
- Builder exposes no runtime authorization read endpoint; execution serves
  ordinary requests from its own persistent projection.
- A source disable, revocation, or unbinding takes effect without app restart
  after execution acknowledges the new projection revision.

## Testing

### Storage tests

- migrations preserve existing executable-skill records;
- logical identity upsert preserves `agent_skill_id`;
- fingerprint change derives `changed_pending_review`;
- re-approval supersedes the previous approval atomically;
- duplicate app bindings are rejected;
- deletion and application cascade behavior is explicit and tested;
- audit events are append-only.

### Service tests

- discovery success, malformed response, timeout, and service-auth failure;
- missing entries are marked only after a successful complete refresh;
- stale catalog remains available to administrators after refresh failure;
- compare-and-set approval rejects a changed fingerprint;
- projection serialization is deterministic;
- same revision and digest is an idempotent synchronization success;
- failed publication remains visibly pending and retries the latest snapshot;
- a mutation is marked synchronized only after matching execution
  acknowledgment;
- Builder restart resumes an unsynchronized revision.

### UI and route tests

- only administrators can mutate sources, approvals, and bindings;
- source paths and provider secrets are absent from rendered pages and public
  JSON;
- changed skills require re-review;
- unavailable skills cannot be bound or enabled;
- Agent Skills remain visually and semantically separate from executable
  RAGenius Skills.

## Rollout

1. Add tables and storage tests without changing existing skill behavior.
2. Add the execution-subsystem client and mocked discovery route tests.
3. Add source and catalog administrator APIs.
4. Add approval and app-binding APIs.
5. Add projection state, deterministic snapshot generation, and publication.
6. Add administrator pages and synchronization status.

The feature remains hidden from ordinary users until execution-subsystem and
app-skeleton designs are implemented and their contract tests pass.

## Acceptance Criteria

- An administrator can configure only execution-approved sources.
- Discovery never creates an approval or app binding.
- Approval is tied to the exact reviewed fingerprint.
- Changed content becomes non-selectable until re-approved.
- A skill can be bound independently to different applications.
- Ordinary APIs do not expose source paths or provider state.
- Builder can be stopped after a projection is acknowledged without preventing
  selection or execution of the synchronized skills.
- Unsynchronized governance changes are clearly distinguished from the active
  execution revision.
- Existing executable RAGenius skill workflows remain unchanged.
