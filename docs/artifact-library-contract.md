# Artifact Library Contract And Implementation Plan

## Purpose

The Artifact Library is the user-facing inventory of reusable artifacts for a single chat session. It exists to let a user inspect, open, reuse, and delete artifacts produced or attached within that session.

## Scope

- Primary scope: current session only
- Isolation boundary: `app_id` and `session_id`
- No cross-session artifacts in the default library view
- No app-wide artifact mixing in the session library

## User-Facing Principles

- Show human-friendly names, not raw ids
- Make actions explicit
- Open artifacts through backend routes, never through raw filesystem paths
- Keep debug details available, but out of the main UX
- Support artifact reuse in Execution Composer without manual id copying

## Artifact Record Shape

Every user-visible artifact returned to the app should conform to this shape:

```ts
type SessionArtifact = {
  artifact_id: string;
  session_id: string;
  app_id: string;
  artifact_type: string;
  artifact_type_label: string;
  display_name: string;
  summary?: string;
  mime_type?: string;
  created_at: string;
  created_by_execution_id?: string | null;
  created_by_turn_id?: string | null;

  provenance?: {
    source_kind?: "chat_export" | "execution" | "upload" | "manual" | "external_tool";
    source_label?: string;
    source_session_id?: string;
    source_message_id?: string | null;
    source_execution_id?: string | null;
  };

  consumption?: {
    default_mode?: string;
    supported_modes?: string[];
  };

  eligible_consumers?: string[];

  routes: {
    open: string;
    preview?: string | null;
    delete: string;
  };

  capabilities: {
    can_open: boolean;
    can_preview: boolean;
    can_delete: boolean;
    can_reuse: boolean;
  };

  file_info?: {
    has_file: boolean;
    extension?: string;
    size_bytes?: number | null;
  };

  debug?: {
    artifact_id: string;
    file_path?: string | null;
    metadata_path?: string | null;
  };
};
```

## API Contract

### `GET /sessions/{session_id}/artifacts`

- Returns only artifacts belonging to that session
- Enforces `app_id` and `user_id`
- Returns normalized user-facing records
- Default sort: newest first

Response:

```json
{
  "session_id": "session-123",
  "items": []
}
```

### `GET /sessions/{session_id}/artifacts/{artifact_id}/file`

- Opens or downloads the artifact through backend streaming
- Must verify the artifact belongs to the session and app

### `GET /sessions/{session_id}/artifacts/{artifact_id}/preview`

- Inline preview when supported
- Must verify the artifact belongs to the session and app

### `DELETE /sessions/{session_id}/artifacts/{artifact_id}`

- Deletes only session-owned artifact metadata and file(s)
- Must verify the artifact belongs to the session and app

## Frontend Contract

- The main library list shows:
  - `display_name`
  - `artifact_type_label`
  - `summary`
  - `created_at`
- The main list does not show raw `artifact_id`
- `artifact_id` appears only in inspector, details, or debug
- `Open File` and `Preview` use backend routes resolved against `baseUrl`
- No `file:///...` fallback in normal UX
- Default sort is server-provided order; client should not reorder alphabetically unless explicitly requested

## Naming Contract

- `display_name` is mandatory for all user-visible artifacts
- Names should be based on user intent or output summary, not opaque ids
- Prefer concise semantic titles:
  - `Chat export - Identify Relationships discussion`
  - `NotebookLM answer - GPT Application Designer`
  - `Gmail draft - Test message to Alice`
- Avoid primary names like:
  - `artifact_1780704681245`
  - `session-1780484369031-chat-export.md`
- Internal storage filenames may remain technical; `display_name` is the UX title

## Artifact Type Labeling

Stable type to friendly label mapping:

- `chat_export` -> `Chat Export`
- `session_upload` -> `Session Upload`
- `notebooklm_answer` -> `NotebookLM Answer`
- `google_drive_export` -> `Drive Export`
- `gmail_draft` -> `Gmail Draft`

## Reuse Contract

Artifacts returned by the library must include enough reuse metadata for Execution Composer:

- whether reusable
- default reuse mode
- supported reuse modes
- eligible consumer targets

## Failure Contract

If metadata exists but the file does not:

- artifact remains listable
- `capabilities.can_open` becomes `false`
- `capabilities.can_preview` becomes `false`
- UI shows `File unavailable`
- details surface explains the missing file state

## Implementation Plan

### Phase 1: Backend Session Scoping

1. Add session provenance to artifact creation records if missing.
2. Add execution-subsystem inventory filtering by `session_id`.
3. Patch `GET /sessions/{session_id}/artifacts` in `ragenius_app_skeleton` to request only current-session artifacts.
4. Patch artifact open, preview, and delete resolution to enforce session ownership, not just `app_id`.

### Phase 2: Backend Response Normalization

1. Introduce a normalizer that builds the `SessionArtifact` response shape.
2. Add:
   - `artifact_type_label`
   - `routes`
   - `capabilities`
   - `file_info`
   - `provenance`
3. Return backend route paths only, not filesystem URLs.
4. Default server-side sorting to newest first.

### Phase 3: Frontend URL And Action Fixes

1. Remove `file:///...` fallback from visible artifact actions.
2. Always resolve artifact route paths against `baseUrl`.
3. Make `Open File`, `Preview`, `Use In Next Step`, and `Delete` explicit buttons or actions.
4. Ensure action clicks do not bubble into unrelated navigation.

### Phase 4: Frontend UX Cleanup

1. Stop showing raw `artifact_id` in the main list.
2. Show:
   - `display_name`
   - friendly type
   - summary
   - created time
3. Move raw ids and file paths into details or inspect only.
4. Stop client-side alphabetical resorting by `display_name`; respect backend newest-first order.

### Phase 5: Naming Improvements

1. Add a shared naming helper for artifact creation.
2. Generate semantic `display_name` values from:
   - export intent
   - execution target
   - user query summary
   - tool or provider context
3. Keep storage filenames separate from display names.
4. Backfill legacy artifacts at read-time when only technical names exist.

### Phase 6: Reuse Integration

1. Ensure library artifacts include reuse hints from the execution subsystem.
2. Wire `Use In Next Step` into Execution Composer using artifact object data, not copied ids.
3. Show suggested reuse mode in composer.
4. Keep artifact reuse session-safe by default.

### Phase 7: Missing File Behavior

1. Detect file existence during normalization.
2. Disable open and preview when missing.
3. Show user-facing unavailable status.
4. Keep debug explanation in details.

### Phase 8: Tests

Backend tests:

- session-scoped artifact listing
- no cross-session leakage
- open, preview, and delete enforcement
- missing file handling
- normalized response shape

Frontend tests:

- no raw id in main library list
- absolute backend URL resolution
- no `file:///` fallback for normal actions
- newest-first ordering preserved
- explicit actions work
- reuse action populates composer

### Phase 9: Legacy Compatibility

1. Support old artifact metadata without breaking reads.
2. Read-time normalization for:
   - missing `display_name`
   - relative file paths
   - missing provenance fields
3. Optional later migration to rewrite old metadata in place.

## Recommended Implementation Order

1. Backend session scoping
2. Backend normalized contract
3. Frontend open and preview URL fix
4. Frontend library UX cleanup
5. Reuse integration
6. Naming improvements
7. Missing-file handling
8. Tests
9. Legacy cleanup
