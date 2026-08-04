# RAGenius App Skeleton v3 Prioritized Rollout Plan

**Goal:** Turn the remaining `ragenius_app_skeleton` content/execution v3 work into a rollout-oriented plan, grouped by release criticality rather than implementation order.

**Scope:** One user-visible session with dual linked lanes, additive `@exec` routing, explicit approved-content snapshots, deterministic execution-intent mapping, and backward-compatible normal non-`@exec` behavior.

**Current baseline already implemented**
- additive `@exec skill` and `@exec status` routing in the backend
- explicit approved-content creation and selection
- approved revision binding in execution confirmations
- compact execution-lane status card in the chat UI
- regression protection for ordinary non-`@exec` turns

---

## Must-Have Before Broader Rollout

These items close correctness, safety, and operational gaps that would otherwise make broader usage risky.

### 1. Explicit execution-status refresh flow in the UI

**Why this is must-have**
- `@exec status` exists, but the UI should make its effect obvious and reload-safe.
- Long-running skills like NotebookLM generation need an easy “refresh status” path.

**Deliverables**
- Add a small `Refresh Execution Status` action near the execution-lane card.
- When the latest execution id exists, allow the UI to issue `@exec status <execution_id>` intentionally.
- Update the execution-lane card immediately from the returned lane state and status result.

**Files**
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\App.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/App.jsx:1)
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ExecutionLaneStatusCard.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ExecutionLaneStatusCard.jsx:1)
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/main.py:1) only if a more explicit status payload is needed

**Acceptance**
- User can refresh latest execution status without reading back through transcript history.
- Card clearly reflects updated status and execution id.

### 2. Explicit “approve this reply” action on assistant messages

**Why this is must-have**
- `Approve Latest Reply` is useful but not sufficient when a session has several candidate replies.
- Approval must be precise and traceable.

**Deliverables**
- Add per-message approval action on assistant messages.
- Reuse the existing backend approval endpoint with `message_id`.
- Keep latest-reply approval as a convenience action, not the only path.

**Files**
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ChatMessageCard.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ChatMessageCard.jsx:1)
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\App.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/App.jsx:1)

**Acceptance**
- User can approve a specific older assistant reply directly.
- Selected approved revision and execution-lane card stay in sync.

### 3. Skill policy classification for approval requirements

**Why this is must-have**
- Not every `@exec` operation should require approved content.
- Approval requirements should be explicit and deterministic rather than incidental.

**Deliverables**
- Introduce an app-side rule set for execution skills:
  - `requires_approved_content`
  - `read_only`
  - `review_required`
- Apply those rules before building execution intent.
- Keep `@exec status` outside approval requirements.

**Files**
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\execution_intent_service.py](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/execution_intent_service.py:1)
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/main.py:1)
- Create or modify a small policy module if needed

**Acceptance**
- Skills that require approved content fail clearly when none is selected.
- Read-only/status operations are still allowed without approval.

### 4. End-to-end regression coverage for the approval-selection-execution loop

**Why this is must-have**
- This is the core v3 behavior. It needs stable regression coverage before wider rollout.

**Tests to add**
- approve a specific assistant reply
- select a non-latest approved revision
- submit `@exec skill ...`
- verify selected `approvedContentId` is used
- refresh execution status
- reload session and preserve selected approved revision plus execution-lane card state

**Files**
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\tests\test_chat_exec_routing.py](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py:1)
- Add frontend tests around message approval and execution-lane refresh

**Acceptance**
- The dual-lane flow is covered across backend and frontend.
- Non-`@exec` turns remain unchanged.

---

## Should-Have

These are not blockers for careful rollout, but they materially improve usability, diagnosability, and operator confidence.

### 5. Better execution summaries and transcript affordances

**Deliverables**
- Show clearer assistant/system summaries for:
  - approval created
  - selected revision changed
  - execution submitted
  - execution status refreshed
- Make execution-related assistant messages visually distinct from ordinary content responses.

**Files**
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/main.py:1)
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ChatMessageCard.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ChatMessageCard.jsx:1)

### 6. Richer approval history presentation

**Deliverables**
- Show created time for approved revisions.
- Show source message references more clearly.
- Show compact preview and selection marker in a stronger visual way.

**Files**
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ApprovedContentPanel.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ApprovedContentPanel.jsx:1)

### 7. Better validation and failure messages for `@exec skill`

**Deliverables**
- Fail early for malformed `@exec` arguments.
- Show targeted error messages for:
  - unknown skill id
  - missing required inputs
  - invalid approved content id
  - wrong-session approved content id

**Files**
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\exec_router.py](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/exec_router.py:1)
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/main.py:1)

### 8. Provenance and fallback display

**Deliverables**
- Surface skill id, execution id, approved revision, and execution path more explicitly.
- When available from execution responses, show whether the runtime used MCP vs adapter vs fallback.

**Files**
- Modify: app-facing execution summaries and execution-lane card
- Extend UI only as far as current execution response fields support it

### 9. Narrow-layout/mobile polish

**Deliverables**
- Ensure approved-content panel and execution-lane card remain legible on narrow viewports.
- Reduce card density and wrap long ids cleanly.

**Files**
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\App.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/App.jsx:1)

---

## Later Enhancements

These are valuable, but they are not necessary to make the v3 contract usable and safe in the current app skeleton.

### 10. First-class async/background execution UX

**Why later**
- Current tool-level async behavior exists in some skills, but app-level background lifecycle is still a larger architectural addition.

**Possible scope**
- execution submit vs poll separation
- explicit queued/running/completed lifecycle in UI
- background refresh or polling
- better handling of long-running NotebookLM generation

### 11. Additional `@exec` commands

**Possible scope**
- `@exec retry <execution_id>`
- `@exec confirm <execution_id>`
- `@exec cancel <execution_id>` if supported later

**Why later**
- These build on the same execution lane but are not required to stabilize the basic flow.

### 12. Dedicated session-lane API surface

**Possible scope**
- `GET /sessions/{session_id}/lane-state`
- narrower status refresh endpoints
- explicit approved-content selection endpoint if selection becomes shared across clients

**Why later**
- Current `/messages` payload plus chat route is enough for the first rollout.

### 13. Skill discovery and guided execution from runtime inventory

**Possible scope**
- let users browse supported skills/tools from Builder/runtime inventory
- guided `@exec` composition or structured submit forms

**Why later**
- Current explicit `@exec skill <skill_id> ...` path is adequate for the v3 foundation.

### 14. Rich operator/audit views in `ragenius_app`

**Possible scope**
- lane-history timeline
- approved-content to execution mapping audit
- more detailed provenance/fallback cards

**Why later**
- Builder and execution subsystem already carry much of the operator-oriented diagnostics.

---

## Recommended Rollout Order

### Phase A: Rollout blockers
1. Explicit execution-status refresh in the UI
2. Per-message approval actions
3. Skill policy classification for approval requirements
4. End-to-end regression coverage for the full approval/selection/execution loop

### Phase B: Usability hardening
5. Better execution summaries
6. Richer approval history presentation
7. Better `@exec` validation and failure messages
8. Provenance/fallback display
9. Narrow-layout polish

### Phase C: Expanded execution productization
10. Async/background execution UX
11. Additional `@exec` commands
12. Dedicated lane-state API surface
13. Skill discovery/guided execution
14. Rich audit/operator views

---

## Exit Criteria

### Broader rollout readiness
- Users can approve a specific reply, select a revision, run `@exec skill ...`, and refresh execution status without ambiguity.
- Non-`@exec` turns remain backward-compatible.
- Core dual-lane flow is covered by regression tests.
- Approval requirements are deterministic per skill class.

### Post-rollout maturity
- Long-running jobs feel first-class.
- Execution provenance is visible.
- Users do not need transcript archaeology to understand what approved content and execution state are active.
