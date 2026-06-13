# RAGenius App Skeleton Execution-Turn UX Tuning Plan

Date: 2026-06-04
Scope: `ragenius_app_skeleton` frontend UX for execution turns
Primary apps affected:
- `ragenius_app_skeleton/frontend`

## Goal

Improve execution-turn UX so that:
- top-of-chat execution status takes much less vertical space
- execution turns inspect differently from normal content turns
- the side panel stays a single shared inspector region
- execution actions feel distinct from content-turn actions
- ordinary non-execution chat behavior stays intact

## Current Problems

1. The top chat area is too tall.
- `SessionHeader`
- `Current step`
- `ApprovedContentPanel`
- `ExecutionLaneStatusCard`

These stack into a large persistent block before the transcript begins.

2. `ExecutionLaneStatusCard` mixes two jobs.
- compact always-visible session status
- detailed execution inspection

That makes the component too large for its placement.

3. Execution turns still use the normal inspector.
- `RuntimeInspector` is retrieval/content oriented
- execution turns do not need citation-first or scope-first inspection
- the `Inspect` action on execution turns therefore feels wrong

4. Transcript actions are too uniform.
- content turns and execution turns expose nearly the same affordances
- execution turns should foreground execution-specific actions instead

## UX Principles

1. Keep one side panel region.
- do not create a second persistent execution inspector area
- switch inspector content by turn type

2. Keep execution summary compact by default.
- one-line or one-row summary at the top
- details only on demand

3. Execution turns should look and behave differently from content turns.
- different badges
- different quick actions
- different side-panel tabs

4. Do not regress ordinary content workflows.
- normal content-turn inspect behavior must stay intact
- workflow step visibility must remain available

## Proposed UX Model

### A. Replace the large top execution card with a compact execution summary bar

Current:
- full `ExecutionLaneStatusCard` grid is always visible

Target:
- compact horizontal bar or dense two-row card showing only:
  - selected approved revision
  - last execution target
  - latest status
  - async task badge if present

Recommended compact fields:
- `Revision: rev_...`
- `Last exec: notebooklm_list_notebooks`
- `Status: completed | running | failed`
- optional `Async`

Recommended actions:
- `Details`
- `Refresh`
- `Retry`
- `Login` only when auth-required

Move these out of always-visible default state:
- execution path
- fallback used
- provider task id
- provider task status
- logs summary
- provenance/tool/provider lists

These belong in the side inspector, not the top session chrome.

### B. Keep the side panel, but split inspector content by turn type

Current:
- `RuntimeInspector` handles all assistant turns

Target:
- keep one shared side panel container
- route to different inspector content depending on selected turn classification

Recommended components:
- `RuntimeInspector` for normal content turns
- new `ExecutionInspector` for execution turns
- optional `ApprovalInspector` later for approval events

Detection source:
- use `message.retrievalSummary.execution_override`
- use `message.retrievalSummary.approval_event`
- keep existing `classifyAssistantTurn` logic aligned with routing

### C. Execution turn transcript actions should be specialized

Current assistant actions:
- `Inspect`
- `Sources`
- `Approve This Reply`
- export selection

Target for execution turns:
- `Execution Details`
- `Refresh Status`
- `Retry`
- `Login to NotebookLM` when applicable

Hide for execution turns:
- `Sources`
- `Approve This Reply`

Normal content turns should keep:
- `Inspect`
- `Sources`
- `Approve This Reply`

Approval-event turns should prefer:
- `View Revision`
- possibly `Select for @exec`

### D. Reduce top-of-page vertical stacking

Recommended top-of-chat order:
1. `SessionHeader`
2. compact workflow/current-step strip
3. compact approved-content + execution summary strip
4. transcript

Specific tuning:
- keep `Current step` visible but denser
- collapse `ApprovedContentPanel` by default when a selection already exists
- keep “Approve Latest Reply” accessible, but not in a large expanded card unless needed

## Concrete Implementation Plan

### Phase 1: Compact execution summary

Files:
- [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ExecutionLaneStatusCard.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ExecutionLaneStatusCard.jsx:1)
- [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\App.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/App.jsx:1)

Changes:
- replace the current always-visible metric grid with a compact summary row
- move the existing details grid content behind a secondary action
- preserve auth/login, refresh, and retry behavior

Acceptance:
- execution section above transcript is substantially shorter
- common execution state is still visible at a glance

### Phase 2: Add dedicated execution inspector in the same side panel region

Files:
- new: `frontend/src/components/ExecutionInspector.jsx`
- update:
  - [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\RuntimeInspector.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/RuntimeInspector.jsx:1)
  - [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\App.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/App.jsx:1)

Changes:
- create execution-specific inspector tabs:
  - `Summary`
  - `Request`
  - `Status`
  - `Provenance`
  - `Raw`
- route execution-turn inspector opening to `ExecutionInspector`
- keep same side panel shell and open/close behavior

Execution inspector content:
- command kind
- tool/skill target
- approved revision/content id used
- mapped input
- execution id
- latest status
- async provider task data
- fallback/provenance/error data

Acceptance:
- inspecting an execution turn no longer shows normal retrieval-first details
- the panel still appears in the same place as normal inspect

### Phase 3: Make transcript actions type-specific

Files:
- [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ChatMessageCard.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ChatMessageCard.jsx:1)
- [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\App.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/App.jsx:1)

Changes:
- branch action rendering by assistant turn type
- content turn actions:
  - `Inspect`
  - `Sources`
  - `Approve This Reply`
- execution turn actions:
  - `Execution Details`
  - `Refresh Status`
  - `Retry`
  - `Login to NotebookLM` when applicable
- approval turn actions:
  - `View Revision`
  - optional `Select for @exec`

Acceptance:
- execution turns stop exposing content-specific actions that are irrelevant
- the transcript better communicates turn type through affordances

### Phase 4: Densify approved-content and current-step presentation

Files:
- [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ApprovedContentPanel.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ApprovedContentPanel.jsx:1)
- [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\SessionHeader.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/SessionHeader.jsx:1)
- [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\App.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/App.jsx:1)

Changes:
- collapse approved-content history by default
- keep selected revision summary visible
- move full revision preview/history under expand/reveal
- reduce the visual footprint of the workflow step banner

Acceptance:
- header chrome is shorter
- transcript starts higher on screen

## Suggested Component Structure After Tuning

- `SessionHeader`
  - app title
  - compact workflow step strip
  - global inspect only for latest normal-content turn, or rename to avoid confusion

- `ApprovedContentPanel`
  - compact selected revision summary
  - expandable history/details

- `ExecutionSummaryBar`
  - compact replacement for large execution lane card
  - quick actions only

- `Transcript`
  - type-specific per-turn actions

- `SideInspectorShell`
  - content:
    - `RuntimeInspector`
    - `ExecutionInspector`
    - later `ApprovalInspector`

## Recommended Naming Adjustments

To reduce UX ambiguity:
- rename global top-right `Inspect` in `SessionHeader`
  - current label is too generic
  - recommended:
    - `Inspect Latest Turn`
    - or open latest-turn-type-specific inspector automatically

- rename execution-turn action from `Inspect`
  - use `Execution Details`

## Testing Plan

Frontend tests to add/update:
- `ExecutionLaneStatusCard.test.jsx`
  - compact mode rendering
  - action visibility

- `ChatMessageCard.test.jsx`
  - execution-turn actions differ from content-turn actions

- new `ExecutionInspector.test.jsx`
  - tabs and execution metadata rendering

- `App.test.jsx`
  - correct inspector routing by turn type
  - side panel reuses one container

Manual verification:
- normal content session
- approval-created turn
- execution success turn
- execution async/running turn
- execution error/auth-required turn

## Rollout Order

Recommended order:
1. Phase 2 first enough to separate execution inspect from content inspect
2. Phase 1 compact summary bar
3. Phase 3 transcript action specialization
4. Phase 4 top-area density reduction

Reason:
- wrong inspector content is the most confusing bug
- top-space reduction is the most visible UX improvement

## Risks To Avoid

1. Do not fork the whole page into separate “execution mode” and “content mode”.
- keep one chat session and one inspector region

2. Do not remove current workflow-step visibility entirely.
- reduce footprint, do not hide critical progression state

3. Do not mix content and execution tabs in one generic inspector.
- execution turns should not lead with source/citation-first UI

4. Do not change ordinary non-execution inspect behavior unless explicitly intended.
- this must remain backward-compatible for content turns

## Definition of Done

This slice is complete when:
- the top execution section is compact by default
- execution turns open an execution-specific side inspector
- execution-turn transcript actions differ from content-turn actions
- ordinary content-turn inspect behavior remains intact
- frontend tests cover inspector routing and compact execution chrome
