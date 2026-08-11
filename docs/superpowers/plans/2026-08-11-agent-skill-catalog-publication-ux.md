# Agent Skill Catalog And Publication UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Organize Builder’s discovered Agent skills by enabled/disabled source and replace ambiguous immediate synchronization UX with reviewed, compare-and-set publication of one complete governance revision to execution.

**Architecture:** `ragenius_builder` remains the administrator control plane and stores discovery history, local governance state, a redacted last-published baseline, and draft/publish status. Existing mutations only advance the local revision. A publication service builds and diffs the complete canonical snapshot, verifies the reviewed revision, then uses the existing Builder credential to atomically publish to `ragenius_execution_subsystem`. `ragenius_app_skeleton` never calls Builder; Composer refreshes execution’s trusted inventory on bounded user/lifecycle events.

**Tech Stack:** Python 3, Flask, SQLite, Jinja, TypeScript/React, Vitest, existing Builder execution client and execution projection APIs.

**Global Constraints:** Keep all governance endpoints administrator-only; never expose protected locator paths or credentials; retain disabled source history; never imply a draft restriction is runtime-effective; keep the previous execution revision active on failure; preserve the existing legacy synchronize endpoint as a temporary delegate; do not add push infrastructure.

---

## Reference Documents

- `D:/GitHub/Codex-RAGenius-System/docs/superpowers/specs/2026-08-11-agent-skill-catalog-publication-ux-design.md`
- `D:/GitHub/Codex-RAGenius-System/docs/agent-skill-discovery-selection-contract.md`
- `D:/GitHub/Codex-RAGenius-System/ragenius_builder/docs/agent-skill-management-design.md`
- `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/docs/agent-skill-discovery-activation-design.md`
- `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/docs/agent-skill-execution-composer-design.md`

## File Structure

### Builder persistence and services

- Modify `ragenius_builder/flask_scaffold/storage.py`: add redacted published snapshot persistence, deterministic source-impact queries, and explicit draft/published state helpers.
- Create `ragenius_builder/flask_scaffold/agent_skill_publication.py`: canonicalize snapshots, compute deterministic diffs, validate expected revision, publish, and record success/failure.
- Modify `ragenius_builder/flask_scaffold/agent_skill_projection.py`: delegate legacy synchronization through the publication service without duplicating projection logic.
- Modify `ragenius_builder/flask_scaffold/agent_skill_execution_client.py` only if a typed publication result is needed; retain the existing service-auth boundary.

### Builder routes and UI

- Modify `ragenius_builder/flask_scaffold/app.py`: add catalog-view filtering, source-impact review, publication preview, and compare-and-set publication routes.
- Modify `ragenius_builder/flask_scaffold/templates/agent_skills.html`: render source-backed tabs and explicit draft/published banners.
- Create `ragenius_builder/flask_scaffold/templates/agent_skill_source_disable_review.html`: review affected skills/bindings/apps before a local source toggle.
- Create `ragenius_builder/flask_scaffold/templates/agent_skill_publication_review.html`: show deterministic changes and publish the reviewed revision.
- Modify focused Builder tests under `ragenius_builder/flask_scaffold/tests`.

### App inventory refresh

- Modify `ragenius_app_skeleton/frontend/src/App.jsx`: refresh trusted execution inventory while Composer is open on the approved lifecycle events.
- Modify `ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx`: expose manual refresh and backend-change refresh without reading Builder.
- Modify `App.test.jsx` and `ExecutionComposer.test.jsx`.

## Milestone 1: Catalog Views And Source Impact

### Task 1: Add deterministic catalog/source queries

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/storage.py`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/tests/test_agent_skill_management.py`

- [ ] **Step 1: Write failing storage tests**

Test active catalog excludes disabled sources, enabled-source filtering returns only that source, disabled catalog retains full records/history, and source impact returns counts plus sorted affected app identities.

Add these storage boundaries:

```python
def list_agent_skill_catalog_view(
    self, *, view: str, source_id: str | None = None
) -> list[dict]: ...

def get_agent_skill_source_impact(self, source_id: str) -> dict:
    # discovered_skill_count, approved_current_fingerprint_count,
    # enabled_binding_count, affected_apps
    ...
```

`approved_current_fingerprint_count` counts only the latest approval whose fingerprint equals current content. `enabled_binding_count` counts enabled bindings, including those still active in the last published revision.

- [ ] **Step 2: Run the focused test and confirm RED**

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold
python -m pytest tests/test_agent_skill_management.py -q
```

- [ ] **Step 3: Implement deterministic queries**

Reuse `_agent_skill_catalog_from_row`; do not erase `source_disabled` rows. Sort sources by case-folded display name then id, and skills by backend, display name, provider reference, then id. Return app id/name only, never source locators.

- [ ] **Step 4: Re-run and commit**

```powershell
git add ragenius_builder/flask_scaffold/storage.py ragenius_builder/flask_scaffold/tests/test_agent_skill_management.py
git commit -m "feat(builder): add source-aware agent skill catalog queries"
```

### Task 2: Render source tabs and disabled history

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/app.py`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/templates/agent_skills.html`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/tests/test_agent_skill_management.py`

- [ ] **Step 1: Add failing page tests**

Cover `/agent-skills?catalog_view=active`, `source:<source_id>`, and `disabled`. Assert bounded counts, active tab state, backend/source labels, source-specific discovery action, disabled rows grouped by source, and disabled approval/reapproval/binding controls carrying a textual reason.

- [ ] **Step 2: Run tests and confirm RED**

```powershell
python -m pytest tests/test_agent_skill_management.py -q
```

- [ ] **Step 3: Implement server-backed accessible tabs**

Use ordinary links with `aria-current="page"`; preserve `catalog_view` through refresh actions. Tabs wrap at narrow widths. Keep read-only fingerprint, approval, binding, and audit details visible for disabled sources. Add server-side guards to approval, reapproval, and binding-enable mutations so a disabled source is rejected even if an administrator bypasses the disabled controls. Do not hide disabled records by deleting them from API/storage.

- [ ] **Step 4: Re-run and commit**

```powershell
git add ragenius_builder/flask_scaffold/app.py ragenius_builder/flask_scaffold/templates/agent_skills.html ragenius_builder/flask_scaffold/tests/test_agent_skill_management.py
git commit -m "feat(builder): organize agent skills by source tabs"
```

### Task 3: Add source-disable impact review

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/app.py`
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/templates/agent_skill_source_disable_review.html`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/tests/test_agent_skill_management.py`

- [ ] **Step 1: Add failing GET/POST tests**

Add `GET /agent-skill-sources/<source_id>/disable-review`. It must show discovered/current-approved/enabled-binding counts, affected apps, current publication state, and the exact action `Disable source in draft`. Test source/app scoping, administrator authorization, and stale local revision rejection.

- [ ] **Step 2: Run and confirm RED**

- [ ] **Step 3: Implement reviewed local toggle**

The confirmation form posts `expected_local_revision` to the existing source toggle mutation. Recheck the revision and enabled state before changing the source. Increment local revision and render:

```text
Disabled in Builder; still active in the published execution revision.
```

when the source existed in the published snapshot. Re-enable uses the same draft semantics and must not auto-publish.

- [ ] **Step 4: Re-run and commit**

```powershell
git add ragenius_builder/flask_scaffold/app.py ragenius_builder/flask_scaffold/templates/agent_skill_source_disable_review.html ragenius_builder/flask_scaffold/tests/test_agent_skill_management.py
git commit -m "feat(builder): review agent skill source disable impact"
```

## Milestone 2: Reviewable Atomic Publication

### Task 4: Persist a redacted published snapshot baseline

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/storage.py`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/tests/test_agent_skill_projection.py`

- [ ] **Step 1: Add failing migration/state tests**

Add nullable `published_snapshot_json TEXT` to `agent_skill_projection_state` through the existing additive SQLite migration pattern. Test old database migration, deterministic JSON round trip, malformed snapshot rejection with `PUBLISHED_SNAPSHOT_INVALID`, and failed publication retaining the prior snapshot. For an upgraded database with no snapshot, reconstruct the baseline only when `local_revision == published_revision` and the current canonical projection matches `published_digest`; otherwise return an explicit `baseline_unavailable` full-replacement preview rather than inventing an empty historical baseline.

Add methods:

```python
def get_published_agent_skill_snapshot(self) -> dict: ...

def mark_agent_skill_projection_published(
    self, *, builder_instance_id: str, revision: int,
    digest: str, redacted_snapshot: dict
) -> dict: ...
```

- [ ] **Step 2: Run and confirm RED**

```powershell
python -m pytest tests/test_agent_skill_projection.py -q
```

- [ ] **Step 3: Implement snapshot persistence**

Serialize with sorted keys and compact separators. Store only source ids/enabled state, stable skill ids/provider references/fingerprints/approval state, and app ids/binding flags. Explicitly exclude `protected_locator_ref`, paths, credentials, tokens, and raw provider output. Keep `mark_agent_skill_projection_synchronized` as a compatibility wrapper only.

- [ ] **Step 4: Re-run and commit**

```powershell
git add ragenius_builder/flask_scaffold/storage.py ragenius_builder/flask_scaffold/tests/test_agent_skill_projection.py
git commit -m "feat(builder): persist published agent skill baseline"
```

### Task 5: Build deterministic preview and compare-and-set publication service

**Files:**
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/agent_skill_publication.py`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/agent_skill_projection.py`
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/tests/test_agent_skill_publication.py`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/tests/test_agent_skill_projection.py`

- [ ] **Step 1: Add failing service tests**

Cover no changes, source enable/disable, approval/reapproval/revocation, binding add/remove/enable, affected apps, deterministic ordering, stale expected revision, successful acknowledgment, transport failure, digest mismatch, and unchanged active runtime on failure.

Use these boundaries:

```python
def build_publication_preview(*, store, builder_instance_id: str) -> dict: ...

def publish_agent_skill_revision(
    *, store, execution_client, builder_instance_id: str,
    expected_local_revision: int, actor_id: str,
    correlation_id: str
) -> dict: ...
```

- [ ] **Step 2: Run tests and confirm RED**

```powershell
python -m pytest tests/test_agent_skill_publication.py tests/test_agent_skill_projection.py -q
```

- [ ] **Step 3: Implement canonicalization, diff, and publication**

Build one full runtime snapshot using the existing projection builder, derive a separate redacted baseline, compare by stable source id, `agent_skill_id`, and `(app_id, agent_skill_id)` binding identity, then publish only after `expected_local_revision == current local_revision`. Record attempt audit before the call and success/failure audit after it. Never update published revision/snapshot until execution acknowledges the same revision and digest.

- [ ] **Step 4: Delegate legacy synchronization**

Change `synchronize_agent_skill_projection` to call the new publication service with the current revision. Preserve its legacy result shape for callers, but do not maintain a second publication implementation.

- [ ] **Step 5: Re-run and commit**

```powershell
git add ragenius_builder/flask_scaffold/agent_skill_publication.py ragenius_builder/flask_scaffold/agent_skill_projection.py ragenius_builder/flask_scaffold/tests/test_agent_skill_publication.py ragenius_builder/flask_scaffold/tests/test_agent_skill_projection.py
git commit -m "feat(builder): add reviewed agent skill publication service"
```

### Task 6: Expose preview/publication APIs and review UI

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/app.py`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/templates/agent_skills.html`
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/templates/agent_skill_publication_review.html`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/tests/test_agent_skill_management.py`
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/tests/test_agent_skill_publication_routes.py`

- [ ] **Step 1: Add failing API and page tests**

Test:

```http
GET /api/agent-skills/publication-preview
POST /api/agent-skills/publications
{"expected_local_revision": 42}
```

Require administrator authorization, bounded/redacted payloads, stale revision HTTP 409 with `PUBLICATION_REVISION_STALE`, failed publication preserving draft state, and successful revision/digest acknowledgment. Test that the page says `Published`, `Draft changes`, or `Publish failed`, never `synchronized`.

- [ ] **Step 2: Run and confirm RED**

```powershell
python -m pytest tests/test_agent_skill_publication_routes.py tests/test_agent_skill_management.py -q
```

- [ ] **Step 3: Implement routes and review page**

Replace the visible `Synchronize now` control with `Review & Publish Changes`. The review page lists local/published revisions, source/approval/binding diffs, affected applications, availability changes, and last success. Its confirmation posts the reviewed revision and reads `Publish revision N`. Use `aria-live` for result status and restore focus to the action after navigation.

- [ ] **Step 4: Keep the legacy API as a delegate**

`POST /api/agent-skills/synchronize` calls the same publication service with current revision and is marked deprecated in response metadata. Builder templates and JavaScript must not call it.

- [ ] **Step 5: Re-run and commit**

```powershell
git add ragenius_builder/flask_scaffold/app.py ragenius_builder/flask_scaffold/templates/agent_skills.html ragenius_builder/flask_scaffold/templates/agent_skill_publication_review.html ragenius_builder/flask_scaffold/tests/test_agent_skill_management.py ragenius_builder/flask_scaffold/tests/test_agent_skill_publication_routes.py
git commit -m "feat(builder): add agent skill publication review UX"
```

## Milestone 3: Trusted App Inventory Refresh

### Task 7: Refresh execution inventory on approved Composer events

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/App.jsx`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/App.test.jsx`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ExecutionComposer.test.jsx`

- [ ] **Step 1: Add failing refresh tests**

Assert inventory is requested from execution when Composer opens, backend changes, window focus returns while Composer is open, and `Refresh Agent Skills` is selected. Assert focus while Composer is closed does nothing, calls are scoped to current app, and an unchanged `inventory_revision` preserves current selection/list identity.

- [ ] **Step 2: Run and confirm RED**

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend
npm test -- ExecutionComposer.test.jsx App.test.jsx
```

- [ ] **Step 3: Implement bounded lifecycle refresh**

Pass one `onRefreshAgentSkills({ backend, force })` callback from `App` through the Composer owner. Register the `window.focus` listener only while Composer is open and clean it up on close/unmount. On backend change refresh that backend. Manual refresh uses `force: true`; automatic responses replace inventory only when revision changes.

- [ ] **Step 4: Re-run and commit**

```powershell
git add ragenius_app_skeleton/frontend/src/App.jsx ragenius_app_skeleton/frontend/src/App.test.jsx ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx ragenius_app_skeleton/frontend/src/components/ExecutionComposer.test.jsx
git commit -m "feat(frontend): refresh trusted agent skill inventory"
```

## Milestone 4: Documentation, Audit, And End-To-End Verification

### Task 8: Align contracts/designs and verify publication audit

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/docs/agent-skill-discovery-selection-contract.md`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/docs/agent-skill-management-design.md`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/docs/agent-skill-discovery-activation-design.md`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/docs/agent-skill-execution-composer-design.md`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/tests/test_agent_skill_publication.py`

- [ ] **Step 1: Add audit assertions before documentation edits**

Verify source toggle and publication attempts record actor, local revision, correlation id, outcome, and bounded counts. Verify preview/error/audit payloads contain no protected locator, token, secret, raw provider output, or local filesystem path.

- [ ] **Step 2: Run focused audit tests**

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold
python -m pytest tests/test_agent_skill_publication.py tests/test_agent_skill_management.py -q
```

- [ ] **Step 3: Update governing documents**

Document source tabs, retained disabled history, local draft semantics, redacted baseline schema, compare-and-set publication, legacy synchronize deprecation, atomic failure behavior, and execution-only app reads. State explicitly that Builder need not be running for app selection/execution after successful publication.

- [ ] **Step 4: Commit**

```powershell
git add docs/agent-skill-discovery-selection-contract.md ragenius_builder/docs/agent-skill-management-design.md ragenius_execution_subsystem/docs/agent-skill-discovery-activation-design.md ragenius_app_skeleton/docs/agent-skill-execution-composer-design.md ragenius_builder/flask_scaffold/tests/test_agent_skill_publication.py
git commit -m "docs: define reviewed agent skill publication"
```

### Task 9: Run full verification and live smoke

- [ ] **Step 1: Run Builder tests**

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_builder\flask_scaffold
python -m pytest tests -q
```

- [ ] **Step 2: Run app frontend tests/build**

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend
npm test
npm run build
```

- [ ] **Step 3: Run execution projection regression tests/build**

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test
npm run build
```

- [ ] **Step 4: Run live acceptance smoke**

With all three subsystems running: disable one source in draft and verify execution inventory is unchanged; inspect the deterministic preview; publish the reviewed revision; verify execution inventory revision advances atomically; open/focus Composer and verify the disabled source’s skills disappear without a page reload. Re-enable, force one failed publication, verify previous inventory remains active, then retry successfully.

- [ ] **Step 5: Record bounded evidence**

Save only revision ids, digests, counts, route statuses, and UI outcomes in the implementation notes. Do not record source paths, credentials, or provider output.

### Task 10: Request review and integrate

- [ ] **Step 1: Invoke `superpowers:requesting-code-review`**
- [ ] **Step 2: Address verified findings and re-run affected suites**
- [ ] **Step 3: Invoke `superpowers:verification-before-completion`**
- [ ] **Step 4: Invoke `superpowers:finishing-a-development-branch` and integrate after the user-approved strategy**

## Completion Criteria

- Active catalog contains only enabled-source skills and each enabled source has its own tab.
- Disabled-source skills retain inspectable governance history but cannot gain active approval/binding changes.
- Source disable/re-enable is a reviewed local draft mutation, not an implicit runtime update.
- Publication preview is deterministic, redacted, and based on the last acknowledged snapshot.
- Stale confirmations and failed publications cannot change execution’s active revision.
- Successful publication atomically advances execution inventory.
- Composer refreshes that trusted inventory without calling Builder or requiring a full page reload.
- Builder, app, execution tests/builds, and live smoke all pass.
