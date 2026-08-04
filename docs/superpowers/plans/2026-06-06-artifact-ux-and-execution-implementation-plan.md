# Artifact UX And Execution Implementation Plan

**Goal:** Implement the artifact UX contract so RAGenius treats artifacts as reusable user-facing objects rather than opaque ids, while preserving the current app-scoped artifact store and policy enforcement model.

**Primary Repos/Areas:**

- `ragenius_execution_subsystem`
- `ragenius_app_skeleton`

**Contract Source:**

- [2026-06-06-artifact-ux-and-execution-contract.md](D:/GitHub/Codex-RAGenius-System/docs/superpowers/plans/2026-06-06-artifact-ux-and-execution-contract.md:1)

## Scope

This plan covers:

- normalized artifact metadata
- artifact naming and storage naming behavior
- execution result `result.artifacts[]`
- execution-turn artifact rendering
- artifact picker UX for execution inputs
- provider-output normalization for reusable outputs

This plan does not require:

- changing `artifact_id` generation
- redesigning storage away from the filesystem
- enabling cross-app artifact reuse

## Current State

Current artifact persistence:

- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\artifact-store.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/tools/providers/artifact-store.ts:1)

Current artifact tools:

- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\tool-registry.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/tools/tool-registry.ts:1)

Current artifact-producing skills:

- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\skills\sample-skills.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/skills/sample-skills.ts:1)

Current app-side artifact rendering:

- [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\App.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/App.jsx:1)
- [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ChatMessageCard.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ChatMessageCard.jsx:1)
- [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ExecutionInspector.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ExecutionInspector.jsx:1)

Current artifact policy seam:

- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\config\policy-config.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/config/policy-config.ts:1)

## Desired End State

Users should see:

- `proposal.pdf`
- `GPT-Application-Designer-notebook-answer.md`
- `session-1780484369031-chat-export.md`

not:

- `artifact_1780704681245`

Execution turns that create artifacts should show:

- compact artifact cards
- direct actions like `Open`, `Inspect`, `Use In Next Step`

Execution turns that consume artifacts should use:

- picker-based selection
- policy-filtered eligible artifacts

Reusable provider outputs should appear as:

- normal app-scoped artifacts in `result.artifacts[]`

## Phase 1: Normalize Stored Artifact Metadata

### Objective

Extend the artifact store and artifact-producing result shapes to carry user-facing metadata and standardized `result.artifacts[]`.

### Execution Subsystem Tasks

#### Task 1.1: Extend artifact-store metadata contract

Update:

- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\artifact-store.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/tools/providers/artifact-store.ts:1)

Add support for:

- `display_name`
- `storage_file_name`
- `summary`
- `app_id`
- `created_at`
- `created_by_execution_id`
- `created_by_turn_id`
- `source_tool_id`
- `source_skill_id`
- `provider_origin`
- `mime_type`
- `size_bytes`
- `status`

Acceptance:

- saved artifact metadata JSON contains those fields when available
- old fields remain present for compatibility

#### Task 1.2: Add naming helper

Create a helper near the artifact store or in a small utility module to:

- derive `display_name`
- derive `storage_file_name`
- sanitize filesystem names
- apply typed fallbacks

Rules must follow the artifact naming contract:

- semantic display name
- file-safe storage name
- deterministic fallback when semantic naming is not possible

Acceptance:

- chat export, drive export, and file inventory all get stable semantic `display_name`
- sanitized storage filenames preserve the semantic stem

#### Task 1.3: Normalize artifact-producing execution results

Update artifact-producing skills/tool paths so results include:

```json
{
  "result": {
    "artifacts": [...]
  }
}
```

Likely targets:

- `save_chat_export_artifact`
- `google_drive_download_file`
- `file_inventory`

Acceptance:

- existing top-level result fields remain for migration
- `result.artifacts[0]` becomes the preferred normalized artifact object

### Tests

Update or add tests in:

- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\execution\execute-skill.test.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/execution/execute-skill.test.ts:1)
- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\tests\tools\local-tool-provider.test.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/tools/local-tool-provider.test.ts:1)

Verify:

- normalized artifact metadata
- naming behavior
- `result.artifacts[]`

## Phase 2: Artifact-Aware Execution Turn Rendering

### Objective

Show artifact objects in execution turns instead of raw ids and paths.

### App Frontend Tasks

#### Task 2.1: Add artifact extraction helper

Update:

- [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\App.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/App.jsx:1)

Add a helper that:

- reads `execution_submit_result.result.artifacts`
- falls back to older export fields during migration
- emits a normalized frontend artifact reference array

Acceptance:

- execution turns can consume one common artifact list shape

#### Task 2.2: Render artifact cards/chips on execution turns

Update:

- [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ChatMessageCard.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ChatMessageCard.jsx:1)

Show:

- artifact display name
- artifact type
- summary when available
- `Open`
- `Inspect`
- `Use In Next Step`

Acceptance:

- main transcript shows semantic labels, not raw ids
- `Open Export` behavior is generalized into artifact actions

#### Task 2.3: Extend execution inspector artifact details

Update:

- [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ExecutionInspector.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ExecutionInspector.jsx:1)

Show:

- display name
- artifact type
- source execution / source turn
- mime type
- size
- file path
- raw `artifact_id`

Acceptance:

- raw ids are only in detail views

### Tests

Update:

- `App.test.jsx`
- `ChatMessageCard.test.jsx`
- `ExecutionInspector.test.jsx`

Verify:

- artifact cards render from normalized execution results
- actions use semantic names
- fallback compatibility still works

## Phase 3: Composer Artifact Picker

### Objective

Remove manual artifact-id usage from normal execution composition.

### App Backend Tasks

#### Task 3.1: Add artifact inventory endpoint

Add a session/app-scoped endpoint in:

- [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/main.py:1)

Example response:

```json
{
  "items": [
    {
      "artifact_id": "...",
      "display_name": "proposal.pdf",
      "artifact_type": "google_drive_export",
      "mime_type": "application/pdf",
      "status": "ready"
    }
  ]
}
```

Support filters for:

- `app_id`
- `artifact_type`
- policy eligibility

#### Task 3.2: Expose picker hints in tool inventory

For any tool/skill input using `artifactIds`, enrich the exec inventory response with:

- `artifact_picker.enabled`
- selection mode
- allowed types
- allowed mime types

### App Frontend Tasks

#### Task 3.3: Add artifact picker UI

Update:

- [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ExecutionComposer.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx:1)

Behavior:

- render picker for `artifactIds`
- show policy-filtered eligible artifacts only
- support single and multi-select
- show selected artifact chips

Acceptance:

- Gmail attachment flows no longer require raw `artifactIds`
- if no eligible artifacts exist, explain why

### Tests

Backend:

- `test_chat_exec_routing.py`

Frontend:

- `ExecutionComposer.test.jsx`

## Phase 4: Provider Output Normalization

### Objective

Persist reusable provider outputs as stored artifacts when intended for cross-turn reuse.

### Execution Subsystem Tasks

#### Task 4.1: Normalize NotebookLM persisted outputs

Update NotebookLM workflow paths in:

- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\skills\sample-skills.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/skills/sample-skills.ts:1)
- NotebookLM adapter/provider files as needed

When persistence is requested or required, save:

- report
- slide deck
- video

as stored app artifacts, then return them in:

- `result.artifacts[]`

Acceptance:

- reusable NotebookLM outputs look like normal artifact objects in the app

#### Task 4.2: Distinguish provider output vs persisted artifact

Ensure result shapes make this explicit:

- transient provider task/result
- persisted stored artifacts

Acceptance:

- UI does not confuse task status with a reusable artifact

### Tests

Add/extend:

- `execute-skill.test.ts`
- NotebookLM execution tests

## Phase 5: Artifact Library UX

### Objective

Make artifacts discoverable and reusable outside the originating execution turn.

> **Dependency note:** Before implementing broad artifact reuse beyond the current picker flows, follow the companion consumption work:
>
> - [D:\GitHub\Codex-RAGenius-System\docs\superpowers\plans\2026-06-06-artifact-consumption-and-reuse-contract.md](D:/GitHub/Codex-RAGenius-System/docs/superpowers/plans/2026-06-06-artifact-consumption-and-reuse-contract.md:1)
> - [D:\GitHub\Codex-RAGenius-System\docs\superpowers\plans\2026-06-06-artifact-consumption-and-reuse-implementation-plan.md](D:/GitHub/Codex-RAGenius-System/docs/superpowers/plans/2026-06-06-artifact-consumption-and-reuse-implementation-plan.md:1)

### App Tasks

#### Task 5.1: Add recent-artifacts tray or panel

Frontend:

- show recent app-scoped artifacts
- allow filter by type
- allow action: `Reuse In Composer`

#### Task 5.2: Support artifact-origin navigation

Users should be able to jump from an artifact to:

- source execution turn
- source execution details

Acceptance:

- artifacts become part of the app workflow, not isolated terminal outputs

## Policy And Security Requirements

All phases must preserve:

- app-scoped artifact enforcement
- no cross-app leakage
- policy-based type filtering
- outbound attachment eligibility enforcement

Current special case to preserve:

- Gmail attachment flows only accept outbound-eligible artifact types, currently `google_drive_export`

## Delivery Order

1. Phase 1: normalize stored artifact metadata
2. Phase 2: artifact-aware execution-turn rendering
3. Phase 3: composer artifact picker
4. Phase 4: provider output normalization
5. Artifact consumption and reuse contract + resolver
6. Phase 5: artifact library UX

## Verification Checklist

### Phase 1

- artifact metadata JSON includes new naming and provenance fields
- execution results expose `result.artifacts[]`
- old result fields still work

### Phase 2

- export confirmation turn shows semantic artifact card
- drive export turns show semantic artifact labels
- inspector shows both user-facing and raw internal fields

### Phase 3

- Gmail attachment draft flow uses artifact picker
- no manual artifact id entry needed for normal UX
- ineligible artifact types are excluded

### Phase 4

- NotebookLM persisted outputs appear as reusable artifacts
- execution turn shows them as normal artifact objects

### Phase 5

- artifact consumption contract and resolver are in place
- users can find and reuse recent artifacts without reopening the original turn

## Recommendation

Implement Phase 1 and Phase 2 first before any provider normalization work.

That gives immediate UX value:

- semantic names
- artifact cards
- direct actions

without waiting for larger NotebookLM output changes.
