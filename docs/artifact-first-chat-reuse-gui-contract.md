# Artifact-First Chat Reuse GUI Contract

## Purpose

RAGenius should expose one primary user-facing reuse path for chat session contents: reusable artifacts.

The current UI has two overlapping paths:

- `Approve This Reply` creates approved content and feeds `approvedContentId` into `@exec`.
- `Select Export` / `Save Selected Chat` creates a chat export artifact that can be reused through Artifact Library and Execution Composer.

This contract defines the target GUI behavior for converging those paths into an artifact-first reuse model while preserving backward compatibility for existing execution plumbing.

## Product Principle

Anything a user wants to reuse from a chat session should become a session artifact.

Artifacts are the visible, inspectable, reusable unit. Approved content may remain as legacy execution-engine plumbing during migration, but it should not remain a separate first-class user-facing path once artifact reuse fully covers the workflow.

## Scope

Applies to:

- `ragenius_app_skeleton` chat UI
- Chat turn reuse controls
- Artifact Library reuse controls
- Execution Composer artifact selection
- Approved Content panel migration

Does not apply to:

- Builder admin workflows
- RAG ingestion or retrieval internals
- Cross-session artifact libraries
- Long-term storage redesign

## Target User Flow

1. User selects one or more chat turns.
2. User clicks `Create Reuse Artifact`.
3. System creates a named chat artifact with source message provenance.
4. Confirmation turn shows clear artifact actions.
5. User clicks `Use in Execution Composer` or opens Artifact Library.
6. Execution Composer opens with compatible artifact(s) preselected when possible.
7. Execution submits artifact references instead of requiring manual content copying or raw ids.

## Chat Turn Controls

### Current Controls

- `Select Export`
- `Approve This Reply`
- `Inspect`
- `Sources`

### Target Controls

- `Select for Reuse`
- `Mark Reviewed` only when review/trust semantics are needed
- `Inspect`
- `Sources`

Rules:

- `Select for Reuse` toggles whether a message is included in the next reusable chat artifact.
- `Mark Reviewed` must not create a separate visible approved-content object long term.
- If review is needed, it should set artifact metadata such as `reviewed: true`, `reviewed_by`, and `reviewed_at`.
- User-facing controls should not expose `approvedContentId`.

## Bottom Action Bar

### Current Control

- `Save Selected Chat (n)`

### Target Control

- `Create Reuse Artifact (n)`

Rules:

- Disabled when no chat turns are selected.
- Creates a `chat_export` artifact by default.
- Uses a human-friendly artifact name based on selected message content.
- Clears selected messages after successful artifact creation.
- Shows a confirmation turn or inline confirmation with explicit artifact actions.

## Artifact Creation Confirmation

After creating a chat reuse artifact, the GUI must show:

- Artifact display name
- Artifact type label, for example `Chat Export`
- Short summary
- `Open Artifact`
- `Use in Execution Composer`
- `View in Artifact Library`

Debug-only details such as `artifact_id`, metadata path, and filesystem path must stay behind inspector/details views.

## Artifact Library

Artifact Library is the central reuse surface.

It must:

- Show current-session artifacts only by default.
- Show human-friendly names instead of raw artifact ids.
- Show badges for `Chat Export`, `Reviewed`, `File backed`, `Inline text`, or other reuse modes.
- Show recommended next steps when a compatible tool or skill exists.
- Open Execution Composer with the selected artifact carried forward.
- Provide explicit actions: `Preview`, `Open Saved File`, `Use in Composer`, `Delete`.

It must not:

- Require users to copy artifact ids manually.
- Open raw filesystem paths directly from frontend code.
- Mix artifacts from other sessions in the default view.

## Execution Composer

Execution Composer is the main artifact consumption surface.

It must:

- Show artifact selectors for fields that support artifact reuse.
- Show selected artifacts with a visible `Remove` action.
- Show available compatible artifacts.
- Show incompatible artifacts separately with reasons.
- Show reuse mode clearly, for example `file backed`, `inline text`, `metadata only`, or `binary payload`.
- Submit artifact references through the agreed execution contract, not raw pasted content unless the selected reuse mode requires inline text.

It should:

- Preselect an artifact when opened from Artifact Library recommendation.
- Keep optional arguments scrollable and reachable.
- Avoid covering the chat transcript or Approved Content/legacy panels.

## Approved Content Migration

Approved Content remains useful as a compatibility layer but should be demoted in the GUI.

### Short-Term Rules

- Keep existing `approvedContentId` support for old `@exec` flows.
- Do not remove backend routes or execution request fields until artifact reuse fully covers the same cases.
- Hide or collapse the Approved Content panel when artifact-first reuse is enabled.
- Preserve `Approve This Reply` only if it creates or marks a reuse artifact.

### Target Rules

- `Approve This Reply` is replaced by `Mark Reviewed` on a selected reuse artifact.
- Reviewed chat content is represented as artifact metadata.
- Execution Composer consumes reviewed artifacts the same way it consumes unreviewed artifacts, with review status visible as a badge.
- `approvedContentId` becomes legacy/internal and is not part of the normal GUI.

## Artifact Metadata For Reviewed Chat

Reviewed chat artifacts should include:

```ts
type ReviewedChatArtifactMetadata = {
  artifact_type: "chat_export";
  display_name: string;
  summary: string;
  source_message_ids: string[];
  reviewed: boolean;
  reviewed_at?: string;
  reviewed_by?: string;
  review_source?: "user_marked_reviewed" | "legacy_approve_reply";
  consumption: {
    default_mode: "file_backed" | "inline_text" | "metadata_only";
    supported_modes: string[];
  };
};
```

## Naming Rules

Chat reuse artifacts should use friendly names based on summarized content, not artifact ids.

Recommended format:

```text
Chat Export - <short content summary>.md
```

Examples:

- `Chat Export - Bible observation questions.md`
- `Chat Export - GPT design benefits answer.md`
- `Reviewed Chat - NotebookLM source instructions.md`

Rules:

- Keep names concise.
- Avoid raw ids in primary labels.
- Preserve source ids in metadata/debug views.
- Deduplicate names with a short suffix when needed.

## Compatibility Requirements

- Existing sessions with approved content must still load.
- Existing `@exec ... approvedContentId=...` commands must still work during migration.
- Existing chat export artifacts must still appear in Artifact Library.
- Existing artifact selectors must continue to support `artifactIds`, `artifactRefs`, and field-specific artifact picker metadata.

## Non-Goals

- Do not redesign `rag_subsystem`.
- Do not move chat flows into Builder.
- Do not create app-wide artifact mixing in the default session library.
- Do not require immediate removal of approved-content database/API support.

## Acceptance Criteria

- A user can reuse chat content without seeing both `Approve This Reply` and `Save Selected Chat` as competing concepts.
- A user can create a reuse artifact from selected chat turns.
- A user can see, open, preview, delete, and reuse that artifact from Artifact Library.
- A user can open Execution Composer from a recommended artifact action and see the artifact preselected when compatible.
- A user can remove a selected artifact before submitting execution.
- Approved/reviewed status is visible as artifact metadata or badge, not as a separate required panel.
- Legacy approved-content execution still works until explicitly removed.

