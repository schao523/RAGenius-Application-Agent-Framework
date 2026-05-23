# RAGenius App Instruction Understanding Observability Design

**Date:** 2026-05-07  
**Status:** Approved-for-planning design spec  
**Scope:** `ragenius_app_skeleton` app-side admin/runtime observability and control for compiled instruction understanding and advisory review.

## Goal

Expose compiled instruction-understanding state and advisory review details directly in `ragenius_app`, and add explicit backend control endpoints for forced recompilation and re-review.

The design must:
- reuse the existing app admin surfaces instead of inventing a second diagnostics UI
- keep compiled understanding as the runtime authority
- keep LLM review advisory only
- avoid triggering compile/review work from ordinary page loads
- reduce duplicate backend context/status assembly where these new endpoints overlap with existing admin routes

## Non-goals

This design must not:
- move admin ownership away from `ragenius_builder`
- redesign the turn-level runtime inspector into a global app diagnostics console
- rework parser/planner contracts again
- change `rag_subsystem` retrieval behavior
- require auto-review on every `GET` request

## Existing Surfaces

The current app already provides the right base surfaces.

### Frontend

- [App.jsx](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\App.jsx)
  - admin tabs:
    - `Documents`
    - `Instructions`
    - `Runtime`
- [InstructionsPanel.jsx](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\InstructionsPanel.jsx)
  - loads `GET /apps/{app_id}/instructions`
- [RuntimePanel.jsx](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\RuntimePanel.jsx)
  - loads `GET /apps/{app_id}/runtime`
- [RuntimeInspector.jsx](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\RuntimeInspector.jsx)
  - per-turn execution diagnostics only

### Backend

- [main.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py)
  - `GET /apps/{app_id}/instructions`
  - `GET /apps/{app_id}/runtime`
- [instruction_understanding_service.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\instruction_understanding_service.py)
  - compile, cache, review, and status lifecycle
- [chat_repos.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\chat_repos.py)
  - persistence for compiled understanding and review records

## Problem Statement

The backend now persists:
- compiled understanding
- review status
- review findings
- review summary

But the app-side admin UI does not expose those artifacts clearly. Current gaps:

1. `Instructions` and `Runtime` views expose status only indirectly or partially.
2. There is no explicit app-side endpoint to:
- force recompilation
- force re-review without recompilation
- fetch a full understanding-detail payload
3. The current backend context-loading path is good enough for ordinary reads, but the new control paths should not duplicate overlapping understanding assembly logic.

## Recommended Approach

Extend the existing `Instructions` and `Runtime` admin tabs, and add explicit app-side admin endpoints for instruction-understanding detail and force actions.

This is preferable to:
- overloading `RuntimeInspector` with app-level state
- adding a brand new top-level admin tab

Reasoning:
- the current app already distinguishes app-level admin surfaces from per-turn inspection
- instruction understanding is app-level metadata, not turn-level state
- the existing tabs already have the right mental model:
  - `Instructions` = source plus interpretation
  - `Runtime` = effective operational summary

## Backend Design

### New endpoints

Add these admin-only endpoints in [main.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py).

#### 1. `GET /apps/{app_id}/instruction-understanding`

Purpose:
- return a full app-side inspection payload for compiled understanding and review

Response shape:
- `app_id`
- `compiled_status`
- `review_status`
- `cache_status`
- `stale_reasons`
- `instruction_source_hash`
- `parser_contract_version`
- `binding_logic_version`
- `resource_catalog_hash`
- `compiled_record_meta`
  - `compiled_at`
  - `compile_duration_ms`
  - `instruction_source_version`
  - `instruction_uri`
  - `metadata`
- `review_record_meta`
  - `reviewed_at`
  - `review_model`
  - `review_prompt_version`
  - `review_confidence`
- `review_summary_md`
- `review_findings`
- `review_recommendations`

Behavior:
- read persisted state only
- do not force recompilation
- do not force review
- if cache is stale, report staleness but do not rebuild on this endpoint

#### 2. `POST /apps/{app_id}/instruction-understanding/recompile`

Purpose:
- force recompilation of instruction understanding for the app

Behavior:
- load current builder instructions/documents
- compile a new authoritative record regardless of hot-cache state
- if a reviewer is available, run review immediately after compile
- return the same detail payload shape as the `GET` detail endpoint

#### 3. `POST /apps/{app_id}/instruction-understanding/review`

Purpose:
- force re-review of the current active compiled record without recompilation

Behavior:
- require an active compiled record
- if no compiled record exists, return `409`
- if no reviewer is available, return `409` with a structured error detail
- persist a new active review record
- return the same detail payload shape as the `GET` detail endpoint

### Shared backend helpers

Add a small shared helper layer in [main.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py) or [instruction_understanding_service.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\instruction_understanding_service.py):

- `load_instruction_understanding_detail(...)`
  - reads active compiled/review records and current cache evaluation
  - assembles the detail payload once
- `force_recompile_instruction_understanding(...)`
  - wraps the compile + optional review flow for the new endpoint
- `force_review_instruction_understanding(...)`
  - wraps explicit review against the active compiled record

This prevents each endpoint from hand-assembling overlapping status/detail logic.

### Existing endpoint adjustments

Keep existing endpoints, but strengthen their payloads:

#### `GET /apps/{app_id}/instructions`

Continue to return:
- instructions content
- settings
- derived config
- derived adapter

Add:
- `instruction_understanding_status`
- `instruction_understanding_preview`
  - small summary only
  - not the full `review_findings`

#### `GET /apps/{app_id}/runtime`

Continue to return runtime summary.

Add:
- `instruction_understanding_status`
- `instruction_understanding_preview`
  - same small summary pattern

These endpoints remain useful for quick summaries. The new detail endpoint is the deep view.

## Frontend Design

### 1. `Instructions` panel

Extend [InstructionsPanel.jsx](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\InstructionsPanel.jsx).

New responsibilities:
- load `GET /apps/{app_id}/instructions` as it does now
- allow explicit load of `GET /apps/{app_id}/instruction-understanding`
- provide force actions:
  - `Refresh Understanding`
  - `Run Review`

Display sections:

#### A. Status summary
- compiled status badge
- review status badge
- cache status badge
- stale reasons
- short hashes/versions

#### B. Review summary
- render `review_summary_md` in readable form
- plain text fallback is acceptable in the first slice if markdown rendering is not already available in the app

#### C. Structured findings
- render the known major buckets if present:
  - `default_workflow_assessment`
  - `classification_findings`
  - `trigger_findings`
  - `step_extraction_findings`
  - `resource_binding_findings`
  - `warnings`
  - `recommendations`
- include a raw JSON fallback block for unknown keys or debugging

#### D. Control row
- `Load Understanding`
- `Refresh Understanding`
- `Run Review`

Constraints:
- ordinary page load must not auto-trigger recompile/review
- controls should be explicit admin actions

### 2. `Runtime` panel

Extend [RuntimePanel.jsx](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\RuntimePanel.jsx).

New responsibilities:
- continue runtime summary behavior
- show compact instruction-understanding status alongside provider/domain/config metrics

Display:
- compact status badges
- short note if review is missing, failed, or stale
- a button or inline action to load the full understanding detail payload

The `Runtime` panel should not duplicate the full findings display. It should link conceptually to the richer `Instructions` panel presentation.

### 3. `RuntimeInspector`

Do not expand [RuntimeInspector.jsx](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\RuntimeInspector.jsx) into an app-level understanding viewer in this slice.

Reason:
- the inspector is correctly scoped to one assistant turn
- instruction understanding is app-level, not message-level

## UX Rules

### Empty states

Support these explicit states:

1. no compiled record
- `No compiled understanding available`

2. compiled exists, no review
- `No review available`

3. review failed
- show `review_status`
- show failure note
- show any saved findings or summary if present

4. stale cache
- show stale reasons clearly
- allow explicit refresh

### Action behavior

- `Load Understanding`
  - reads persisted detail only
- `Refresh Understanding`
  - forces recompile
  - may also re-run auto-review if reviewer exists
- `Run Review`
  - forces a new review only

Buttons must show in-progress states and surface backend errors without leaving the page.

## Cleanup / Hardening

This slice should include one focused backend cleanup:

- centralize understanding-detail payload assembly so:
  - `GET /apps/{app_id}/instructions`
  - `GET /apps/{app_id}/runtime`
  - `GET /apps/{app_id}/instruction-understanding`
  - `POST /apps/{app_id}/instruction-understanding/recompile`
  - `POST /apps/{app_id}/instruction-understanding/review`

do not each recompute overlapping status/detail fragments independently.

This is intentionally narrow. It should not become a larger refactor of unrelated app context loading.

## Error Handling

### Backend

- missing app -> `404`
- missing instructions -> existing behavior
- force review with no compiled record -> `409`
- force review with no reviewer available -> `409` with clear detail
- compile/review failure -> structured error payload, no partial silent success

### Frontend

- show action-level error state inside the panel that triggered it
- do not wipe the last successful payload just because a force action fails

## Testing

### Backend tests

Add or extend tests in:
- [test_builder_chat_integration.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_builder_chat_integration.py)
- [test_instruction_understanding_service.py](C:\Users\User\Documents\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\tests\test_instruction_understanding_service.py)
- new route-focused tests if needed

Required backend coverage:
- detail endpoint returns persisted compiled/review data
- detail endpoint does not trigger compile/review
- force recompile endpoint supersedes prior compiled record
- force recompile endpoint also refreshes review when reviewer exists
- force review endpoint creates a fresh active review without recompiling
- force review endpoint fails cleanly when no compiled record exists
- force review endpoint fails cleanly when no reviewer exists

### Frontend tests

Add targeted component tests for:
- status summary rendering
- empty review state
- failed review state
- force action success
- force action error handling
- findings rendering fallback to raw JSON

## Acceptance Criteria

The design is successful when:

1. an app admin can inspect compiled understanding and advisory review directly from `ragenius_app`
2. an app admin can explicitly force recompilation or re-review without using Builder
3. ordinary admin page loads do not trigger new compile/review work
4. app-level understanding remains clearly separate from turn-level runtime inspection
5. backend status/detail assembly is shared enough to avoid duplicated logic across the new endpoints

## Implementation Notes

- Prefer extending existing components over adding a new admin tab.
- Keep control endpoints admin-only, matching the existing app admin routes.
- Keep the detail payload read-only by default; explicit `POST` endpoints own mutation.
- If markdown rendering would introduce too much new dependency weight, use a readable preformatted rendering for `review_summary_md` in the first slice and upgrade later.
