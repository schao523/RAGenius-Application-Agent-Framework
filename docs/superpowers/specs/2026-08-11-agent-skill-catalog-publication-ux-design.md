# Agent Skill Catalog And Publication UX Design

## Purpose

RAGenius Builder must organize discovered Agent skills by source and make the
difference between local governance edits and runtime-effective publication
explicit. Today, disabling a source leaves its skills mixed into the flat
catalog, and `Synchronize now` does not explain what will change in execution.

The selected model combines **source-grouped catalog tabs** with an explicit
**Review & Publish Changes** workflow. Builder retains disabled-source records
for audit and re-enablement, while the default catalog shows only enabled
sources.

## Goals

- Keep the active catalog focused on enabled sources.
- Preserve disabled-source skills, approvals, bindings, and fingerprints.
- Make source ownership visible for every discovered skill.
- Warn before disabling a source with approved or bound skills.
- Batch governance edits into one atomic runtime publication.
- Show exactly whether a Builder change is draft, published, or failed.
- Refresh app-facing inventory predictably after publication.

## Non-Goals

- Automatic approval or publication.
- Deleting catalog history when a source is disabled.
- Batch approval/binding in the first implementation.
- Provider installation, upgrade, or authentication management.
- Real-time push notifications from Builder to open app browsers.

## Catalog Information Architecture

### Tabs

The Agent Skills page renders accessible server-backed tabs:

1. **Active catalog**: skills from all enabled sources;
2. one tab per enabled source;
3. **Disabled sources**: retained skills grouped by disabled source.

Tab labels include bounded counts. Source tabs include a backend badge such as
`Codex` or `OpenClaw`. Tabs wrap on narrow screens and preserve selection in a
query parameter so refresh/back navigation works.

The active tab is a view filter, not a storage mutation. Catalog APIs continue
to retain and expose governance state to administrators.

### Active Catalog

The default view excludes skills whose source is disabled. It supports name,
backend, governance-state, and availability filters. Each row displays source
label, canonical provider reference, state, and last-seen time.

### Source Tabs

An enabled-source tab displays its discovery status, last refresh, counts, and
skills. Discovery refresh acts only on that source and does not publish
governance changes automatically.

### Disabled Sources

Disabled-source skills remain visible with `source_disabled`. Their detail,
approval history, binding history, fingerprints, and audit evidence remain
readable. New approval, re-approval, and binding-enablement actions are disabled
until the source is enabled again.

Disabling a source never deletes catalog entries or silently revokes historical
approvals. Runtime eligibility becomes false only after the corresponding
governance revision is successfully published.

## Source Enablement UX

### Disable Impact Review

Before disabling a source, Builder shows:

- discovered skill count;
- approved current-fingerprint count;
- enabled binding count;
- affected application names/count;
- current runtime publication state.

The administrator confirms **Disable source in draft**. This changes Builder's
local governance state and increments the local revision, but does not claim
the runtime changed.

Until publication succeeds, affected rows display:

> Disabled in Builder; still active in the published execution revision.

Re-enabling follows the same draft/publication model.

## Explicit Publication Model

### State Language

Builder uses these user-facing states:

- `Published`: execution acknowledged the latest complete Builder snapshot;
- `Draft changes`: local revision is newer than the published revision;
- `Publish failed`: the previous execution revision remains active.

The existing `synchronized` storage state may remain internal for backward
compatibility, but UI copy uses publication language.

### Review And Publish

`Synchronize now` becomes **Review & Publish Changes**. Selecting it opens a
review page or dialog containing:

- local and currently published revisions;
- source enable/disable changes;
- approvals, re-approvals, and revocations;
- binding additions, removals, and enablement changes;
- affected applications;
- skills becoming available or unavailable;
- last successful publication time.

The confirmation action is **Publish revision N**. The request includes the
reviewed local revision. If Builder state changes before submission, the server
rejects the stale confirmation and requires a new review.

### Atomicity And Failure

Builder publishes one complete canonical governance snapshot. Execution
validates and atomically activates it. Partial source, approval, or binding
updates are never runtime-visible.

On failure:

- the previous execution projection remains active;
- Builder retains all draft edits;
- the UI shows a bounded error and **Retry publication**;
- no UI claims a restrictive change is active.

On success, Builder records the acknowledged revision/digest and shows a
success summary.

## Change Summary Data

Builder persists the last successfully published redacted governance snapshot
or an equivalent normalized change baseline. The baseline excludes protected
paths, credentials, administrator secrets, and raw provider output.

The review diff compares the current canonical snapshot against that baseline
by stable `agent_skill_id`, source id, and app binding id. Ordering is
deterministic. A digest-only comparison is insufficient because it cannot
explain affected sources or applications.

## APIs

Existing mutation APIs remain draft-producing. Add read/confirm publication
semantics:

```http
GET /api/agent-skills/publication-preview
```

Returns:

```json
{
  "state": "draft_changes",
  "local_revision": 42,
  "published_revision": 41,
  "changes": {
    "sources": [],
    "approvals": [],
    "bindings": [],
    "affected_apps": []
  }
}
```

```http
POST /api/agent-skills/publications
Content-Type: application/json

{"expected_local_revision": 42}
```

The publish endpoint revalidates the expected revision, builds the complete
snapshot, publishes it through the existing Builder service credential, and
returns acknowledged revision/digest plus a bounded summary.

The legacy synchronize POST may temporarily delegate to the new service for
compatibility, but the Builder UI must use reviewed compare-and-set publication.

## App Inventory Refresh

Execution inventory changes immediately after successful publication. The app
does not call Builder at runtime.

`ragenius_app_skeleton` refreshes Agent Skill inventory:

- whenever Composer opens;
- whenever Agent backend changes;
- when the browser window regains focus while Composer is open;
- when the user selects **Refresh Agent Skills**.

The response `inventory_revision` prevents unnecessary state replacement. This
avoids adding cross-subsystem push infrastructure while ensuring an open app
can observe a newly published revision without a full page reload.

## Accessibility And Responsive Behavior

- Tabs use links or correct tab semantics and expose the active state.
- Counts are text, not color-only indicators.
- Status banners use `aria-live` for publication results.
- Source cards and actions stack at narrow widths.
- Disabled controls include a textual reason.
- Confirmation focus returns to the originating source or publication action.

## Security And Audit

- All Builder mutations and publication endpoints remain administrator-only.
- Publication uses the Builder-specific `agent_skills:admin` service scope.
- Preview and error payloads expose no protected locator paths or tokens.
- Source disable/enable and publication attempts record actor, revision,
  correlation id, outcome, and bounded change counts.
- Failed publication never weakens the active execution projection.

## Testing And Acceptance

- Active catalog excludes disabled-source skills.
- Each enabled source tab contains only that source's skills.
- Disabled sources retain inspectable history and cannot gain new active
  approvals/bindings.
- Disabling a source shows affected approved skills, bindings, and apps before
  confirmation.
- Local disable leaves runtime unchanged until explicit publication.
- Publication preview reports deterministic changes.
- Stale expected revision is rejected without publishing.
- Successful publication atomically updates execution inventory.
- Failed publication retains previous runtime inventory and draft changes.
- Composer refresh observes the new inventory revision without page reload.
- Source labels, counts, states, and controls remain usable on mobile widths.

## Deferred Work

- Bulk approval, revocation, or binding.
- Saved catalog filters and advanced search.
- Scheduled or policy-driven automatic publication.
- Real-time push from Builder to app browsers.
- Catalog deletion and provider lifecycle management.
