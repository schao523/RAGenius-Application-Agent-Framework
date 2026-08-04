# Artifact UX And Execution Contract

## Goal

Define a first-class artifact contract for RAGenius that:

- keeps `artifact_id` as the stable internal handle
- stops using `artifact_id` as the primary user-facing label
- makes artifacts understandable and reusable from execution turns
- supports chaining artifacts into later tool and skill runs without requiring users to know raw ids

This contract covers:

- `ragenius_execution_subsystem` artifact persistence and execution results
- `ragenius_app_skeleton` execution-turn rendering and composer UX
- policy rules for artifact reuse across tools such as Gmail attachment flows

## Current Reality

The current system already has a generic app-scoped artifact store in:

- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\providers\artifact-store.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/tools/providers/artifact-store.ts:1)
- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\tools\tool-registry.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/tools/tool-registry.ts:1)

Current first-class artifact types actually used in runtime flows are:

- `chat_export`
- `google_drive_export`
- `file_inventory`

There are also provider-side outputs that are artifact-like but not yet normalized into app-scoped stored artifacts:

- NotebookLM `report`
- NotebookLM `slide_deck`
- NotebookLM `video`

Current problems:

- execution turns often surface `artifact_id` and raw paths instead of human-meaningful labels
- users cannot easily reuse artifacts in later execution turns without understanding ids
- artifact-producing turns and artifact-consuming turns are not strongly connected in the UI
- provider outputs and persisted app artifacts are not consistently modeled the same way

## Design Principles

1. `artifact_id` is internal, stable, and machine-facing.
2. The user-facing concept is an `artifact object`, not an id string.
3. Every artifact shown in the UI must have a human-readable label.
4. Execution turns that create artifacts must expose direct next actions.
5. Execution turns that consume artifacts must use picker-based selection, not id entry.
6. Artifacts remain app-scoped and must not leak across `app_id`.
7. Provider outputs that should be reusable must be normalized into the same artifact contract.

## Artifact Classes

The system should distinguish three classes.

### 1. Stored App Artifact

Persisted under the local app-scoped artifact store.

Examples:

- chat export markdown
- downloaded Google Drive file content
- file inventory report
- future persisted NotebookLM outputs

Characteristics:

- has stable `artifact_id`
- has app-scoped storage path
- may have `file_path`
- can be referenced by later executions

### 2. Provider Output

Returned by an external provider but not yet persisted as an app artifact.

Examples:

- NotebookLM generation task status
- transient download path from a provider

Characteristics:

- may have provider-native task ids
- not necessarily reusable by later executions
- should not be presented to users as if it were already an app artifact

### 3. Artifact Reference

A user-facing reference to a stored artifact when selecting or displaying it in execution UX.

Characteristics:

- includes label, type, source turn, and actions
- may contain `artifact_id` internally
- should be the default UI shape used by composer and execution turns

## Canonical Stored Artifact Contract

All stored artifacts should normalize to this shape at execution and app boundaries:

```json
{
  "artifact_id": "artifact_1780704681245",
  "artifact_type": "chat_export",
  "display_name": "session-1780484369031-chat-export.md",
  "summary": "Chat export from 1 selected message",
  "app_id": "2302c77b-3d82-4650-bd15-e0ff9c0faab7",
  "created_at": "2026-06-06T10:15:00Z",
  "created_by_execution_id": "execution_2c85a09e83af",
  "created_by_turn_id": "message_assistant_123",
  "source_tool_id": "save_artifact",
  "source_skill_id": "save_chat_export_artifact",
  "provider_origin": "local",
  "mime_type": "text/markdown",
  "size_bytes": 1423,
  "path": "D:\\GitHub\\Codex-RAGenius-System\\ragenius_execution_subsystem\\storage\\artifacts\\...\\artifact_1780704681245.json",
  "file_path": "D:\\GitHub\\Codex-RAGenius-System\\ragenius_execution_subsystem\\storage\\artifacts\\...\\artifact_1780704681245-session-1780484369031-chat-export.md",
  "status": "ready"
}
```

### Required Fields

- `artifact_id`
- `artifact_type`
- `display_name`
- `app_id`
- `created_at`
- `status`

### Optional Fields

- `summary`
- `created_by_execution_id`
- `created_by_turn_id`
- `source_tool_id`
- `source_skill_id`
- `provider_origin`
- `mime_type`
- `size_bytes`
- `path`
- `file_path`

## User-Facing Artifact Reference Contract

This is the contract that execution turns and composer pickers should consume:

```json
{
  "artifact_id": "artifact_1780704681245",
  "display_name": "session-1780484369031-chat-export.md",
  "artifact_type": "chat_export",
  "summary": "Chat export from 1 selected message",
  "created_at": "2026-06-06T10:15:00Z",
  "created_by_execution_id": "execution_2c85a09e83af",
  "created_by_turn_id": "message_assistant_123",
  "mime_type": "text/markdown",
  "size_bytes": 1423,
  "status": "ready",
  "actions": {
    "open": true,
    "inspect": true,
    "reuse": true,
    "attach": false
  }
}
```

This is what should be rendered in the UI by default, instead of raw `artifact_id`.

## Artifact Naming Contract

Artifacts should carry three distinct naming concepts.

### 1. Internal Stable Handle

- `artifact_id`

Rules:

- machine-facing only
- opaque and stable
- never the primary user-facing label

### 2. User-Facing Display Name

- `display_name`

Rules:

- primary label used in execution turns, artifact pickers, and inspector summaries
- based on the task result, target object, or content topic
- should be readable without knowing internal ids
- should usually include a useful extension when file-backed

Examples:

- `GPT-Application-Designer-notebook-answer.md`
- `Micah-2-study-guide.md`
- `proposal.pdf`
- `session-1780484369031-chat-export.md`

### 3. Storage File Name

- file-safe version of `display_name`, optionally prefixed by `artifact_id`

Rules:

- filesystem-safe
- deterministic
- can include `artifact_id` for uniqueness
- should preserve the visible semantic name after the prefix

Example:

- `artifact_1780704681245-session-1780484369031-chat-export.md`

## Naming Rules

### Primary Rule

The visible artifact name should be derived from a short normalized summary of the user intent or execution result, not from a raw id.

### Recommended Naming Formula

Use:

- `<target-or-topic>-<result-or-purpose>.<ext>`

Examples:

- `GPT-Application-Designer-notebook-answer.md`
- `Micah-2-study-guide.md`
- `project-proposal-drive-export.pdf`
- `gmail-draft-attachment.pdf`

### Preferred Naming Inputs

Use these, in priority order:

1. explicit caller-provided semantic name
2. result target plus operation summary
3. summarized user query intent
4. deterministic typed fallback

### Raw Query Rule

Do not use the full raw user query directly as the file or display name.

Reasons:

- too long
- noisy
- inconsistent across retries
- may contain unsafe filename characters
- often includes unnecessary scaffolding words

Instead:

- summarize the query into a short intent phrase
- combine it with target context and artifact type

### Length Rule

Suggested limits:

- `display_name`: target under 80 characters when possible
- storage filename stem: target under 120 characters when possible before sanitization/prefixing

If a generated name is too long:

- keep the most useful target/topic words
- keep the suffix / extension
- truncate the middle or tail deterministically

### Sanitization Rule

The artifact store must sanitize storage filenames for filesystem safety, but sanitization must not erase the semantic meaning of the display name.

Preferred pattern:

- preserve `display_name` in metadata
- generate a sanitized `storage_file_name` separately

### Fallback Rule

If no good semantic summary exists, use a typed fallback:

- `chat-export.md`
- `drive-export.pdf`
- `file-inventory.json`
- `notebooklm-report.pdf`

### Type-Specific Naming Guidance

#### Chat Export

Prefer:

- `<session-or-topic>-chat-export.<ext>`

Examples:

- `session-1780484369031-chat-export.md`
- `Micah-2-reflection-chat-export.md`

#### Google Drive Export

Prefer:

- original remote file name when available
- otherwise `<query-or-target>-drive-export.<ext>`

#### File Inventory

Prefer:

- `<path-or-scope>-file-inventory.json`

#### NotebookLM Persisted Outputs

Prefer:

- `<notebook-title>-report.<ext>`
- `<notebook-title>-slide-deck.<ext>`
- `<notebook-title>-video.<ext>`

### Contract Implications

Stored artifacts should eventually expose:

- `artifact_id`
- `display_name`
- `storage_file_name`
- optional `summary`

The UI should always prefer:

- `display_name`

and only show:

- `artifact_id`

inside debug or inspector details.

## Execution Result Contract

Any execution turn that creates artifacts should expose them in a normalized `artifacts` array.

```json
{
  "execution_id": "execution_2c85a09e83af",
  "status": "completed",
  "result_type": "json",
  "result": {
    "artifacts": [
      {
        "artifact_id": "artifact_1780704681245",
        "artifact_type": "chat_export",
        "display_name": "session-1780484369031-chat-export.md",
        "summary": "Chat export from 1 selected message",
        "file_path": "D:\\...\\session-1780484369031-chat-export.md",
        "mime_type": "text/markdown",
        "status": "ready"
      }
    ]
  }
}
```

Rules:

- `result.artifacts` is the standard place for reusable created artifacts
- legacy top-level fields such as `artifact_id`, `path`, or `file_path` may remain during migration
- UI should prefer `result.artifacts`

## Execution Turn UX Contract

### Artifact-Producing Turns

Execution turns that create artifacts must show:

- concise summary
- artifact chips/cards
- direct actions

Example:

- `Created 1 artifact`
- `Chat Export | session-1780484369031-chat-export.md`
- actions:
  - `Open`
  - `Inspect`
  - `Use In Next Step`

The main transcript must not show only:

- `artifact_1780704681245`

### Artifact-Consuming Turns

Execution turns that need artifacts must not require manual raw ids in normal UX.

Instead:

- composer shows an artifact picker
- picker is filtered by allowed type and app scope
- selected artifacts are shown as chips with label and type

Example:

- `Attachments`
- `proposal.pdf | Google Drive Export`
- `notes.md | Chat Export`

### Inspector

The execution inspector should show:

- artifact label
- artifact type
- source turn / source execution
- open path
- file path
- raw `artifact_id`

But raw `artifact_id` belongs in details, not as the primary visible label.

## Composer Contract

When a tool or skill input schema requires `artifactIds`, the app should expose a typed picker contract:

```json
{
  "artifact_picker": {
    "enabled": true,
    "selection_mode": "single|multiple",
    "allowed_artifact_types": ["google_drive_export"],
    "allowed_mime_types": ["application/pdf", "text/plain", "text/markdown"],
    "app_scoped_only": true
  }
}
```

Rules:

- no manual id entry in normal UX
- artifact selection should use `display_name`
- picker should show source and eligibility
- if no eligible artifacts exist, explain why

## Policy Contract

Artifact policy remains app-scoped and enforced in the execution subsystem.

The current policy seam in:

- [D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\config\policy-config.ts](D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/config/policy-config.ts:1)

should continue to govern:

- outbound-eligible artifact types
- attachment count and size
- allowed mime types
- `artifact_only` source constraints

UI implications:

- the artifact picker must only show eligible artifacts for the selected tool
- a Gmail attachment flow should show only outbound-eligible artifact types
- in current policy, that means `google_drive_export` is eligible and `chat_export` is not

## Provider Output Normalization Contract

Provider outputs should not all remain ad hoc.

If a provider output is intended to be reusable across execution turns, it must be normalizable into a stored artifact.

Examples:

- NotebookLM generated report -> persistable stored artifact
- NotebookLM slide deck -> persistable stored artifact
- NotebookLM video -> persistable stored artifact

Normalization rule:

- provider-native result can exist
- but reusable outputs should also appear as `result.artifacts[]`

This allows all reusable outputs to share the same UX:

- open
- inspect
- attach if policy allows
- reuse in next execution

## Storage Contract Additions

The current metadata written by the artifact store should be extended to include user-facing metadata:

```json
{
  "name": "session-1780484369031-chat-export.md",
  "display_name": "session-1780484369031-chat-export.md",
  "artifact_type": "chat_export",
  "summary": "Chat export from 1 selected message",
  "app_id": "2302c77b-3d82-4650-bd15-e0ff9c0faab7",
  "created_at": "2026-06-06T10:15:00Z",
  "created_by_execution_id": "execution_2c85a09e83af",
  "created_by_turn_id": "message_assistant_123",
  "source_tool_id": "save_artifact",
  "source_skill_id": "save_chat_export_artifact",
  "mime_type": "text/markdown",
  "size_bytes": 1423,
  "file_path": "D:\\...\\session-1780484369031-chat-export.md",
  "content": "..."
}
```

## Backward Compatibility

During migration:

- keep existing `artifact_id`, `path`, `artifact_type`, and `file_path`
- add `display_name`, `summary`, and provenance metadata
- app frontend should prefer new fields when present
- fallback to old fields only if new metadata is missing

## Implementation Phases

### Phase 1: Normalize Stored Artifact Metadata

Execution subsystem:

- extend artifact store metadata
- return `display_name`, `summary`, `created_at`, provenance fields
- add `result.artifacts[]` to artifact-producing execution results

### Phase 2: Artifact-Aware Execution Turns

App frontend:

- render artifact chips/cards on execution turns
- show `Open`, `Inspect`, `Use In Next Step`
- stop showing raw ids in main transcript

### Phase 3: Composer Artifact Picker

App frontend/backend:

- replace manual `artifactIds` UX with picker-driven selection
- filter by policy eligibility and app scope

### Phase 4: Provider Output Normalization

Execution subsystem:

- normalize reusable NotebookLM outputs into stored artifacts
- return them in `result.artifacts[]`

### Phase 5: Artifact Library UX

App frontend:

- add a reusable artifact browser or tray
- allow browsing recent artifacts by app
- support reuse from outside the originating execution turn

### Phase 6: Artifact Consumption And Reuse

Follow the companion contract and plan:

- [D:\GitHub\Codex-RAGenius-System\docs\superpowers\plans\2026-06-06-artifact-consumption-and-reuse-contract.md](D:/GitHub/Codex-RAGenius-System/docs/superpowers/plans/2026-06-06-artifact-consumption-and-reuse-contract.md:1)
- [D:\GitHub\Codex-RAGenius-System\docs\superpowers\plans\2026-06-06-artifact-consumption-and-reuse-implementation-plan.md](D:/GitHub/Codex-RAGenius-System/docs/superpowers/plans/2026-06-06-artifact-consumption-and-reuse-implementation-plan.md:1)

This phase defines:

- generic artifact resolver behavior
- per-type consumption modes
- per-consumer accepted artifact modes
- the migration path from raw artifact-record parsing to explicit reuse semantics

## Non-Goals

This contract does not require:

- changing the internal `artifact_id` generation scheme
- removing file-system-backed artifact storage
- allowing cross-app artifact reuse
- allowing all artifact types as outbound Gmail attachments

## Recommendation

The system should treat artifacts the same way it treats files in mature developer tools:

- stable internal ids for machines
- meaningful labels and actions for users

The key UX rule is:

- **users should act on artifact objects, not memorize artifact ids**

That is the boundary this contract formalizes.
