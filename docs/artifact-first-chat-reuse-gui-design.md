# Artifact-First Chat Reuse GUI Design

## Source Contract

This design implements the GUI direction in `docs/artifact-first-chat-reuse-gui-contract.md`.

The core UX decision is: reusable chat session content should become artifacts. The GUI should stop presenting `Approve This Reply` and `Save Selected Chat` as two competing reuse paths.

## Design Goals

- Give users one mental model: select chat content, create a reuse artifact, use that artifact in execution.
- Keep artifact creation, inspection, and execution consumption visible and explicit.
- Demote Approved Content to legacy compatibility unless review/trust status is needed.
- Preserve existing `approvedContentId` support while migrating the GUI to artifact-first reuse.
- Avoid layouts where Execution Composer hides the chat transcript, Artifact Library, or legacy approval context.

## Current GUI Problems

### Duplicate Reuse Concepts

Current chat cards expose:

- `Select Export`
- `Approve This Reply`

Both are ways to reuse assistant content. One creates an artifact; the other creates approved content. Users must understand two concepts even though both operate on chat session contents.

### Split Reuse Destinations

Artifacts are visible in Artifact Library and Execution Composer. Approved Content appears in its own panel and is passed implicitly to `@exec` as `approvedContentId`.

This makes execution inputs harder to inspect because artifact reuse is explicit while approved-content reuse is hidden behind selection state.

### Layout Competition

Execution Composer is a large panel. It must not be nested inside the sticky chat input area or otherwise cover the transcript and top session panels.

## Target Information Architecture

### Primary Reuse Surface

Artifact Library becomes the primary inventory of reusable session outputs.

It owns:

- Viewing reusable chat exports
- Opening and previewing artifacts
- Deleting artifacts
- Starting Execution Composer with a selected artifact
- Showing review status as metadata or badge

### Primary Consumption Surface

Execution Composer becomes the primary place where artifacts are attached to execution arguments.

It owns:

- Showing eligible artifacts for a field
- Showing incompatible artifacts and reasons
- Showing selected artifacts
- Removing selected artifacts
- Submitting artifact references to execution

### Legacy Compatibility Surface

Approved Content should be collapsed or hidden from the default chat view once artifact-first reuse is enabled.

It may remain available behind a small legacy/debug disclosure while old sessions and old `@exec approvedContentId=...` commands are still supported.

## Chat Turn Design

### Assistant Turn Actions

Replace:

```text
Select Export | Approve This Reply | Inspect | Sources
```

With:

```text
Select for Reuse | Mark Reviewed | Inspect | Sources
```

### Action Behavior

`Select for Reuse`

- Toggles the turn into the selected reuse set.
- Selected state label becomes `Selected for Reuse`.
- Works for user turns and assistant turns when those turns have stable message ids.
- Does not create an artifact immediately.

`Mark Reviewed`

- Available on assistant turns.
- Creates or updates a reviewed chat artifact.
- Does not expose `approvedContentId`.
- May be hidden behind a secondary menu later if review is uncommon.

`Inspect`

- Opens the right-side inspector.
- Unchanged.

`Sources`

- Opens source tab in the inspector.
- Unchanged.

### Reviewed State

When a turn or artifact has been reviewed, show a compact badge:

```text
Reviewed
```

Do not show raw review metadata in the card. Details belong in Artifact Library details or inspector.

## Bottom Action Bar Design

### Current

```text
Ask | Run Tool or Skill | Hide Artifact Library | Save Selected Chat (n)
```

### Target

```text
Ask | Run Tool or Skill | Hide Artifact Library | Create Reuse Artifact (n)
```

### Button States

`Create Reuse Artifact (0)`

- Disabled.
- Tooltip or helper text: `Select one or more chat turns to create a reusable artifact.`

`Create Reuse Artifact (n)`

- Enabled.
- Creates a `chat_export` artifact from selected turns.
- Clears selected turns on success.

`Creating Reuse Artifact...`

- Loading state while export request is active.

## Artifact Creation Confirmation

After successful creation, append a compact execution-style assistant turn or inline status block.

### Confirmation Copy

```text
Created reuse artifact: Chat Export - Bible observation questions.md
Chat export from 2 selected messages.
```

### Confirmation Actions

Show explicit buttons:

- `Use in Execution Composer`
- `View in Artifact Library`
- `Open Artifact`
- `Inspect Details`

### Debug Placement

The main confirmation must not show:

- `artifact_id`
- raw filesystem path
- metadata file path

Those remain in inspector/details only.

## Artifact Library Design

### Header

```text
Artifact Library
Reusable artifacts for this session.
```

Show count:

```text
3 items
```

### Artifact Card

Each artifact card should show:

- Display name
- Type badge, for example `Chat Export`
- Optional `Reviewed` badge
- Reuse mode badge, for example `File backed`
- Summary
- Created time
- Recommended next step if compatible tools exist

Example:

```text
Chat Export - Bible observation questions.md
Chat Export | Reviewed | File backed | Created 2026/06/12 17:30
Chat export from 2 selected messages.

Use in Composer | Preview | Open Saved File | Delete
Recommended: NotebookLM Add Source File
```

### Artifact Card Actions

`Use in Composer`

- Opens Execution Composer.
- Carries the selected artifact as `initialArtifactSuggestion`.
- Chooses a compatible target when a recommended target exists.

`Preview`

- Uses backend preview route.
- Shows unsupported preview state if not available.

`Open Saved File`

- Uses backend file route.
- Never opens raw `file:///` paths from frontend code.

`Delete`

- Confirms deletion.
- Removes the artifact from the current-session library after success.

## Execution Composer Design

### Layout

Execution Composer should render as a separate panel below the chat card, not inside the sticky chat input area.

Required behavior:

- Chat transcript remains visible and scrollable.
- Top session context remains reachable.
- Artifact Library can stay open below or near the composer.
- Composer itself has an internal vertical scroll for long argument forms.

### Artifact Field

For artifact-aware fields, show:

```text
File Path *
Required consumption mode: file backed
Accepted artifact types: chat_export
Maximum artifacts: 1

Selected artifact
Chat Export - Bible observation questions.md (file backed)  Remove

Available artifacts
Select Chat Export - Bible observation questions.md

Unavailable artifacts
Drive Export - slides.pdf
Not selectable: Accepted artifact types: chat_export
```

### Empty Compatible State

If no compatible artifact is available:

```text
Available artifacts
No compatible artifacts are loaded for this field.
Required artifact type: chat_export. Required reuse mode: file backed.
Open Artifact Library and choose a compatible recommended next step, or create a compatible artifact in this session.
```

### Selected Artifact Removal

Every selected artifact must have a visible `Remove` action.

Removing should:

- Clear the field value for single-select fields.
- Remove only that artifact for multi-select fields.
- Leave the artifact in Artifact Library.

## Approved Content Migration Design

### Phase 1: Rename And Demote

- Hide the always-visible Approved Content panel by default.
- Add a compact legacy disclosure when approved content exists:

```text
Legacy approved content selected for @exec
Show
```

- Keep the underlying selected approved content state.

### Phase 2: Convert Approval UX

Replace `Approve This Reply` with `Mark Reviewed`.

`Mark Reviewed` should:

- Create a reviewed chat artifact if no artifact exists for the selected turn.
- Or update the matching chat artifact metadata with `reviewed: true`.
- Continue to populate legacy approved-content state only if compatibility requires it.

### Phase 3: Artifact-Only Default

- Remove Approved Content from default user-facing workflow.
- Keep `approvedContentId` support in parser/submission as legacy.
- Inspector may still show legacy approved-content ids for debugging.

## Data Flow

### Create Reuse Artifact

```text
ChatMessageCard Select for Reuse
-> selectedExportMessageIds state
-> Create Reuse Artifact button
-> POST /sessions/{session_id}/exports
-> save_artifact / chat_export
-> refresh Artifact Library
-> append confirmation turn
```

### Use Artifact In Composer

```text
ArtifactLibrary Use in Composer
-> set artifactSuggestionForComposer
-> set preferred target id if recommendation exists
-> open ExecutionComposer
-> artifact-aware field resolves compatibility
-> user submits
-> @exec command includes artifactRefs/artifactIds
```

### Mark Reviewed

```text
ChatMessageCard Mark Reviewed
-> create/update reviewed chat artifact
-> optional legacy approved-content write
-> refresh Artifact Library
-> show Reviewed badge
```

## Copy Changes

| Current | Target |
| --- | --- |
| `Select Export` | `Select for Reuse` |
| `Unselect Export` | `Selected for Reuse` or `Unselect Reuse` |
| `Save Selected Chat (n)` | `Create Reuse Artifact (n)` |
| `Saving Export...` | `Creating Reuse Artifact...` |
| `Approve This Reply` | `Mark Reviewed` |
| `Approved Content` | `Legacy Approved Content` when shown |
| `Selected for @exec` | `Legacy selected for @exec` |

## Visual Priority

High priority:

- Chat transcript
- Chat input
- Artifact reuse actions
- Execution Composer

Medium priority:

- Artifact Library
- Inspector
- Review badges

Low priority:

- Raw ids
- filesystem paths
- legacy approved-content details

## Error States

### Artifact Creation Fails

Show:

```text
Unable to create reuse artifact.
<backend detail>
```

Keep selected messages selected so the user can retry.

### Artifact File Missing

Artifact Library card remains visible but shows:

```text
File unavailable
```

Disable `Open Saved File` and `Preview` if the backend reports those capabilities as false.

### No Compatible Artifact For Composer Field

Show the explicit empty compatible state described above.

### Legacy Approved Content Missing

Do not block artifact-based execution. Only show legacy warnings when a user explicitly tries to run an old approved-content flow.

## Accessibility And Interaction Requirements

- Buttons must have descriptive text; no icon-only required actions.
- Artifact selectors must be keyboard reachable.
- Remove buttons must be reachable and clearly tied to the selected artifact label.
- Composer scroll must be internal when its content exceeds viewport height.
- The page must not require horizontal scrolling for normal chat content.

## Implementation Boundaries

Frontend primary files:

- `ragenius_app_skeleton/frontend/src/App.jsx`
- `ragenius_app_skeleton/frontend/src/components/ChatMessageCard.jsx`
- `ragenius_app_skeleton/frontend/src/components/ArtifactLibrary.jsx`
- `ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx`
- `ragenius_app_skeleton/frontend/src/components/ApprovedContentPanel.jsx`

Backend/app-side touchpoints:

- Current chat export endpoint can remain the artifact creation path.
- Approved-content endpoint should remain for compatibility.
- Artifact inventory endpoint remains the source of reusable session artifacts.

Execution subsystem touchpoints:

- Continue to support artifact picker metadata.
- Continue to support `artifactIds`, `artifactRefs`, and field-specific artifact reuse.
- Continue to support `approved_content_id` until deprecated.

## Testing Requirements

Add or update frontend tests for:

- Chat card shows `Select for Reuse`, not `Select Export`.
- Bottom action shows `Create Reuse Artifact (n)`.
- Artifact creation confirmation exposes `Use in Execution Composer`.
- Artifact Library `Use in Composer` opens Composer with artifact suggestion.
- Execution Composer selected artifact shows `Remove`.
- Removing selected artifact clears the field.
- Approved Content panel is hidden/collapsed by default when artifact-first mode is active.
- Legacy approved-content state still works for existing tests or legacy mode.

Add or update backend/app tests for:

- Chat export artifacts include reviewed metadata when created through `Mark Reviewed`.
- Artifact inventory surfaces reviewed badge metadata.
- Existing approved-content APIs remain compatible.

## Rollout Plan

### Step 1: Copy And Layout

- Rename chat reuse labels.
- Rename bottom action.
- Ensure Execution Composer remains outside sticky chat input.

### Step 2: Confirmation Actions

- Add artifact creation confirmation actions.
- Refresh Artifact Library after artifact creation.

### Step 3: Reviewed Artifact Path

- Implement `Mark Reviewed` as reviewed artifact metadata.
- Keep approved-content write only as compatibility bridge.

### Step 4: Approved Content Demotion

- Collapse or hide Approved Content panel by default.
- Show legacy panel only when explicitly opened or when old approved-content state exists.

### Step 5: Cleanup

- Remove user-facing `approvedContentId` language.
- Keep debug visibility in inspector.
- Update docs and tests.

## Open Decisions

- Whether `Mark Reviewed` should be visible on every assistant turn or only in an overflow/details area.
- Whether reviewed artifacts should use `Chat Export - ...` or `Reviewed Chat - ...` as the default naming prefix.
- Whether creating a reviewed artifact from one turn should auto-open Artifact Library or only show confirmation actions.

