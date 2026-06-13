# Artifact Consumption And Reuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generic artifact-consumption contract and resolver so later execution turns can reuse artifacts safely and consistently.

**Architecture:** Introduce a resolver and per-type consumption metadata in `ragenius_execution_subsystem`, then migrate current consumers to use it before broadening artifact reuse in the app. Keep the existing artifact creation and visibility work intact and layer consumption logic on top.

**Tech Stack:** TypeScript, Fastify, Zod, current artifact store, current execution workflow engine, React frontend picker/inspector UX.

**Current implementation note:** The execution subsystem resolver and Gmail `artifactIds` flow are already present. The app backend now resolves selected session artifacts before execution submission, enriches `execution_intent.mapped_input` with `artifactRefs` and `artifact_reuse`, and maps file-backed non-`artifactIds` fields to resolved `file_path` values.

---

## File Structure

### Execution Subsystem

- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\artifact-store.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/tools/providers/artifact-store.ts:1)
  - preserve raw storage record compatibility
- Create: `ragenius_execution_subsystem/src/core/artifacts/artifact-consumption.types.ts`
  - shared resolver/result types
- Create: `ragenius_execution_subsystem/src/core/artifacts/artifact-consumption-registry.ts`
  - artifact-type consumption metadata
- Create: `ragenius_execution_subsystem/src/core/artifacts/artifact-resolver.ts`
  - generic artifact resolution logic
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\mcp-tool-provider.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/tools/providers/mcp-tool-provider.ts:1)
  - migrate Gmail attachment flow to resolver
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\api\routes\tools.routes.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/api/routes/tools.routes.ts:1)
  - expose optional consumer hints to the app
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\config\policy-config.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/config/policy-config.ts:1)
  - keep explicit allowed artifact types, optionally align naming/hints

### App

- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/main.py:1)
  - preserve and proxy artifact-consumer hints if needed
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ExecutionComposer.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx:1)
  - show consumption-mode-aware artifact picker hints
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ExecutionInspector.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ExecutionInspector.jsx:1)
  - show resolved reuse mode when present

### Tests

- Modify: `ragenius_execution_subsystem/tests/tools/mcp-tool-provider.test.ts`
- Modify: `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`
- Create or modify: `ragenius_execution_subsystem/tests/artifacts/*.test.ts`
- Modify: `ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionComposer.test.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionInspector.test.jsx`

## Phase A: Resolver Contract At The Source

### Task A.1: Add shared artifact-consumption types - COMPLETE

Files:

- Create: `ragenius_execution_subsystem/src/core/artifacts/artifact-consumption.types.ts`

Deliver:

- `ArtifactConsumptionMode`
- `ArtifactResolvedPayload`
- `ResolvedArtifact`
- `ArtifactConsumerSpec`

Acceptance:

- all downstream code can type against one resolver contract

Status:

- implemented in `ragenius_execution_subsystem/src/core/artifacts/artifact-consumption.types.ts`

### Task A.2: Add artifact-type consumption registry - COMPLETE

Files:

- Create: `ragenius_execution_subsystem/src/core/artifacts/artifact-consumption-registry.ts`

Deliver:

- metadata for:
  - `chat_export`
  - `google_drive_export`
  - `file_inventory`
  - `notebooklm_report`
  - `notebooklm_slide_deck`
  - `notebooklm_video`

Acceptance:

- artifact types explicitly declare default and supported consumption modes

Status:

- implemented in `ragenius_execution_subsystem/src/core/artifacts/artifact-consumption-registry.ts`

## Phase B: Generic Artifact Resolver

### Task B.1: Implement resolver service - COMPLETE

Files:

- Create: `ragenius_execution_subsystem/src/core/artifacts/artifact-resolver.ts`
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\artifact-store.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/tools/providers/artifact-store.ts:1)

Resolver responsibilities:

- load stored artifact
- look up artifact-type rules
- choose resolved consumption mode
- normalize output fields:
  - `file_path`
  - `text_content`
  - `binary_content_base64`
  - `metadata`

Acceptance:

- one call returns a reusable resolved artifact object
- no consumer has to parse raw records ad hoc

Status:

- implemented in `ragenius_execution_subsystem/src/core/artifacts/artifact-resolver.ts`

### Task B.2: Add tests for resolver behavior - COMPLETE

Files:

- Create or modify: `ragenius_execution_subsystem/tests/artifacts/artifact-resolver.test.ts`

Cases:

- `google_drive_export` resolves to `binary_payload`
- `chat_export` resolves to `file_backed` and `inline_text`
- `notebooklm_report` resolves to `file_backed` and `inline_text`
- unsupported required mode fails cleanly

Acceptance:

- resolver behavior is explicit and tested

Status:

- covered by `ragenius_execution_subsystem/tests/artifacts/artifact-resolver.test.ts`

## Phase C: Consumer Migration

### Task C.1: Migrate Gmail attachment flow to resolver - COMPLETE

Files:

- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\mcp-tool-provider.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/tools/providers/mcp-tool-provider.ts:1)

Changes:

- replace direct artifact-record parsing in `buildAttachmentAwareDraftInput`
- require `binary_payload` or equivalent resolved payload
- preserve existing policy checks

Acceptance:

- Gmail attachment flow consumes resolved artifacts, not raw store internals
- behavior remains unchanged for valid `google_drive_export`

Status:

- Gmail attachment flow resolves `artifactIds` through `ArtifactResolver` using `binary_payload`
- outbound policy still controls allowed artifact types, MIME types, count, and size

### Task C.2: Add tests for migrated Gmail path - COMPLETE

Files:

- Modify: `ragenius_execution_subsystem/tests/tools/mcp-tool-provider.test.ts`

Cases:

- valid drive export still attaches successfully
- unsupported artifact type still fails by policy
- missing required resolved mode fails with validation/tool error

Status:

- covered by existing MCP provider artifact attachment tests

## Phase D: App UX Alignment

### Task D.1: Surface artifact consumer hints to the app - COMPLETE

Files:

- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\api\routes\tools.routes.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/api/routes/tools.routes.ts:1)
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/main.py:1)

Hints may include:

- `accepted_artifact_types`
- `required_consumption_mode`
- `max_artifact_count`

Acceptance:

- frontend can explain why an artifact is eligible or not

Status:

- tool inventory exposes `artifact_picker`
- app backend preserves picker hints
- frontend filters artifacts by accepted type/MIME and shows required consumption mode

### Task D.2: Improve picker/inspector UX around reuse mode - COMPLETE

Files:

- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ExecutionComposer.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx:1)
- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ExecutionInspector.jsx](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ExecutionInspector.jsx:1)

Behavior:

- picker can show “Used as attachment”, “Used as file”, or “Used as text”
- inspector can display resolved reuse mode when execution details are present

Acceptance:

- artifact reuse is understandable from the UI

Implemented behavior:

- composer shows selected artifact chips and reuse summary
- inspector labels reused artifacts as `Submitted artifact inputs`
- inspector labels execution outputs as `Produced artifacts`
- app error UX creates visible execution-error turns for failed `@exec` submissions

### Task D.3: Resolve selected artifacts before app-side execution submission - COMPLETE

Files:

- Modify: [D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py](D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/main.py:1)
- Modify: `ragenius_app_skeleton/backend/tests/test_chat_exec_routing.py`

Implemented behavior:

- validate selected artifacts against the current session inventory
- reject missing/out-of-session artifacts before provider execution
- enrich `execution_intent.mapped_input` with `artifactRefs`
- enrich `execution_intent.mapped_input` with `artifact_reuse`
- preserve `artifactIds` for Gmail attachment-style flows
- map non-`artifactIds` file-backed picker fields to resolved `file_path`

Acceptance:

- selected artifacts affect actual execution submission, not only UI summaries
- inspector can show request-side artifact reuse even when execution result has no output artifacts
- file-consuming tools can receive a resolved path instead of an artifact id

Status:

- implemented and covered by app backend routing tests

### Task D.4: Add end-to-end browser validation - PARTIAL

Status:

- frontend reachability was verified at `http://127.0.0.1:5173`
- backend API reachability was verified at `http://127.0.0.1:8012`
- full automated click-through was not completed because the current REPL environment does not have Playwright available

Remaining manual validation:

- select artifact from Artifact Library
- open Execution Composer from `Use In Next Step`
- verify compatible target is selected
- run execution
- inspect turn
- confirm `Submitted artifact inputs`, `artifactRefs`, and `artifact_reuse` are visible

## Phase E: Resume Artifact Creation And Visibility Plan

### Task E.1: Update the existing artifact UX plan

Files:

- Modify: [D:\GitHub\Codex-RAGenius-System\docs\superpowers\plans\2026-06-06-artifact-ux-and-execution-contract.md](D:/GitHub/Codex-RAGenius-System/docs/superpowers/plans/2026-06-06-artifact-ux-and-execution-contract.md:1)
- Modify: [D:\GitHub\Codex-RAGenius-System\docs\superpowers\plans\2026-06-06-artifact-ux-and-execution-implementation-plan.md](D:/GitHub/Codex-RAGenius-System/docs/superpowers/plans/2026-06-06-artifact-ux-and-execution-implementation-plan.md:1)

Changes:

- mark Phase 1-4 as already implemented or substantially complete
- make Phase 5 depend on this consumption contract
- preserve the original plan history rather than rewriting it

Acceptance:

- the original artifact plan remains the source of truth for creation/visibility
- reuse work becomes the explicit next dependency

## Policy And Security Requirements

Must preserve:

- app-scoped artifact isolation
- no cross-app leakage
- explicit outbound attachment eligibility
- no accidental enablement of NotebookLM artifacts as Gmail attachments

## Verification Checklist

### Resolver

- artifact types declare supported/default modes
- resolver returns normalized payloads for supported modes
- unsupported required modes fail explicitly

### Consumer Migration

- Gmail attachments still work for `google_drive_export`
- Gmail no longer reads raw artifact records directly

### UX

- picker can explain eligibility at least at a basic level
- inspector can display resolved reuse mode for artifact-consuming turns
- failed artifact reuse submissions appear as execution-error turns
- inspector distinguishes submitted artifact inputs from produced artifacts

### App-Side Submission

- `artifactIds` remains stable for attachment-style consumers
- `artifactRefs` is added before submission
- `artifact_reuse` is added before submission
- non-`artifactIds` file-backed fields map to resolved `file_path`
- missing/out-of-session artifacts fail before provider execution

### Plan Alignment

- original artifact UX plan is preserved
- next implementation work references this contract

## Delivery Order

1. Phase A: shared types and consumption registry - complete
2. Phase B: generic artifact resolver - complete
3. Phase C: migrate current consumer path - complete for Gmail attachment path
4. Phase D: app UX alignment - complete for picker, inspector, app-side submission enrichment, and file-backed field mapping
5. Phase E: resume the original artifact plan with the new dependency documented

## Remaining Work

### Formalize `artifactRefs` in the execution subsystem

Decision needed:

- keep `artifactRefs` as app-side request metadata only
- or promote `artifactRefs` to a first-class execution-subsystem input contract

Recommended next step:

- keep `artifactIds` as the primary compatibility contract for existing tools
- add optional subsystem validation for `artifactRefs` only after at least one additional consumer directly uses it

### Expand field-specific mappings

Current implemented mapping:

- `artifactIds` -> preserve ids
- non-`artifactIds` plus `file_backed` -> resolved `file_path`

Future mappings:

- `inline_text` -> map only to declared text-content fields
- `binary_payload` -> keep behind policy/provider-specific handlers
- `metadata_only` -> map only to tools that explicitly accept metadata objects

### Complete browser click-through validation

Use the running app to validate:

- Artifact Library -> Use In Next Step
- Execution Composer compatible target selection
- execution submission
- Inspector request tab
- execution details showing `Submitted artifact inputs`

## Recommendation

Do not broaden NotebookLM artifact reuse immediately.

First:

- define the resolver
- migrate the current Gmail consumer
- make consumption rules explicit

Then:

- onboard additional consumers and artifact types intentionally
