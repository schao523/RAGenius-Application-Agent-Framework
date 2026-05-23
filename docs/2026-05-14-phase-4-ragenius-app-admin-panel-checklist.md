# Phase 4: RAGenius App Admin Panel Checklist

Date: 2026-05-14

Target:
- `ragenius_app/frontend/src/App.jsx`

Goal:
- add an `Instruction Understanding` admin tab to the existing RAGenius app control surface
- wire it to the instruction-understanding lifecycle backend already implemented in `ragenius_app_skeleton/backend/app`

## Phase 4 Scope

1. Introduce `app_id` into the admin control surface
- add `App ID` input alongside existing `Collection ID`, `Session ID`, and `User ID`
- use `app_id` only for instruction-understanding lifecycle routes
- preserve current collection-based controls for chat/upload/config/adapter

2. Add `Instruction Understanding` tab
- place alongside `Chat`, `Upload`, `Config`, `Adapter`
- first slice is read-only plus manual refresh

3. Implement read-only lifecycle viewer
- fetch `GET /apps/{app_id}/instruction-understanding`
- render:
  - `compiled_status`
  - `review_status`
  - `cache_status`
  - `stale_reasons`
  - compiled record metadata
  - semantic compile attached/valid flags
  - review findings
  - review summary markdown
  - approval state if present
  - revision state if present

4. Preserve explicit recompute semantics
- on initial load, read from detail route only
- no implicit recompile/review on tab open
- expose a `Refresh` button only in first slice

5. Follow-up action slice
- add buttons for:
  - `Recompile`
  - `Review`
  - `Approve Findings`
  - `Revise`
- refresh detail after successful mutation

6. Add approval input UI
- approver text input
- JSON textarea for approved findings payload

7. Add revision viewer
- show revision status
- changed ids
- preserved ids
- validation payload

8. Improve display semantics
- make stale reasons prominent
- highlight lifecycle state transitions
- separate compiled/review/approval/revision sections visually

## Implementation Order

1. Add checklist file
2. Add `app_id` input to control surface
3. Add read-only `Instruction Understanding` tab
4. Add fetch + refresh logic
5. Render lifecycle sections
6. Verify with frontend build
7. Add action buttons in second slice
8. Add approval/revision inputs in later slice

## First Slice Deliverable

Deliver:
- `App ID` field
- `Instruction Understanding` tab
- read-only lifecycle panel
- `Refresh` button
- loading/error states
- no mutation actions yet

## Verification

Primary:
- `npm run build` in `ragenius_app/frontend`

Manual behavior expectations:
- tab renders without breaking existing tabs
- missing `App ID` shows a clear prompt instead of making a request
- detail route payload renders even when review/approval/revision are absent
- stale states are visible

## Follow-up Slice

After first slice is stable:
- implement `Recompile`, `Review`, `Approve Findings`, `Revise`
- decide whether to port the same lifecycle panel into the separate Builder GUI afterward
