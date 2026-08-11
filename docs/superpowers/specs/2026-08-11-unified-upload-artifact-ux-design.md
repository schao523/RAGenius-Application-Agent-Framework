# Unified Upload And Artifact UX Design

## Purpose

RAGenius must present an uploaded file as one user-visible, reusable artifact
regardless of whether the upload starts from normal chat or Execution Composer.
The current separation between app-owned session uploads and execution-owned
artifacts leaks an internal transfer boundary into the UX, creates duplicate
files on retry, and makes deletion unclear.

The selected model is **one visible artifact with transient app staging**:

1. the browser uploads bytes to `ragenius_app_skeleton`;
2. the app streams, hashes, and temporarily stages the bytes;
3. the app imports the file into `ragenius_execution_subsystem` immediately;
4. the execution artifact becomes the canonical user-visible file;
5. the app retains only bounded analysis text and an artifact mapping after
   staging bytes are no longer required.

This design supersedes the user-visible two-tier flow in
`2026-08-10-composer-session-upload-execution-artifact-design.md`. It does not
change the subsystem ownership boundary: browser credentials remain app-owned,
artifact bytes remain execution-owned after import, and providers receive only
run-scoped staged paths.

## Goals

- Show every successful upload exactly once in Artifact Library.
- Use the same upload behavior from normal chat and Agent Composer.
- Make upload, preparation, selection, and deletion states understandable.
- Retry without creating another upload or artifact.
- Reuse an existing session-scoped artifact for identical bytes.
- Preserve historical execution evidence after a user deletes an artifact.
- Keep large video transfer streamed and bounded.
- Remove raw internal ids, paths, and JSON errors from ordinary UI.

## Non-Goals

- Cross-session or app-wide artifact sharing.
- Direct browser upload to the execution subsystem.
- Automatic external publication of uploaded content.
- Artifact version graphs or restoration of deleted bytes.
- Batch file upload in the first implementation.
- Automatic destructive cleanup of existing duplicate runtime data.

## Product Model

### One Visible File Type

The UI uses **Artifact** for an uploaded file. It does not expose “session
upload,” “promotion,” or “prepared upload.” A successful upload appears in
Artifact Library with:

- display filename;
- MIME type and formatted size;
- upload time;
- status;
- supported reuse modes;
- actions appropriate to its status.

The internal app staging record is not listed in Artifact Library, normal chat,
or Composer selectors.

### Artifact States

The frontend normalizes the lifecycle to:

- `uploading`: browser-to-app transfer is active;
- `preparing`: app-to-execution import and integrity verification are active;
- `ready`: the canonical execution artifact can be selected and reused;
- `failed`: the same staged upload can be retried when recoverable;
- `deleting`: scoped deletion is in progress;
- `deleted`: no longer listed or reusable.

Only `ready` artifacts can be submitted to Agent execution. A failed row remains
visible in the current page state with a short error, **Retry**, and **Delete**.

## User Experience

### Shared Upload Control

Normal chat and Agent Composer use the same `Upload artifact` interaction and
the same app endpoint. The normal chat panel uses a stacked layout so the file
input, help text, progress, and actions cannot overlap at narrow widths.

```text
Upload artifact
[ Choose file ]
Files are available to this chat and Agent execution.

How_Governed_AI_Professional_Assistants_Work.mp4
video/mp4 | 9.4 MiB | Preparing
[ Cancel ]
```

Composer does not contain a separate `Select session file` control. Its input
section selects ready artifacts from Artifact Library and may open the shared
upload control inline.

### Artifact Library

Artifact Library is the canonical inventory. Uploaded artifacts appear there
immediately after successful import. Rows show filename, type, size, time, and
status; artifact ids and storage paths remain inspector-only.

Ready rows provide:

- **Use in Composer**;
- **Preview** when supported;
- **Delete artifact**.

Composer selections use **Unselect**, not **Remove preparation**. Deletion is a
separate destructive action with confirmation.

### Progress And Errors

The browser shows byte progress when the transport exposes it; otherwise it
shows determinate phase changes (`Uploading`, then `Preparing`). Large files
must not appear idle while transfer is active.

User-facing errors are normalized messages such as:

- “Execution storage is unavailable. Retry this upload.”
- “This file is larger than the configured upload limit.”
- “Your session no longer has access to this artifact.”

Raw response JSON is available only in inspector diagnostics.

## Architecture And Data Flow

### App Ingress

`ragenius_app_skeleton` remains the only browser upload boundary. A unified
multipart endpoint accepts `{app_id, session_id, user_id, file}` and:

1. validates exact session ownership;
2. streams to a non-addressable app staging file;
3. computes SHA-256 and size while writing;
4. creates one staging record with a stable `upload_operation_id`;
5. imports bytes to execution using the app service credential;
6. stores the returned `artifact_id` and safe artifact metadata;
7. runs normal-query extraction/analysis when requested;
8. removes app staging bytes after import and required extraction complete.

The normal-query and Composer callers differ only in post-upload behavior:
normal query may start upload analysis, while Composer selects the returned
artifact. They do not use different persistence models.

### Retry Identity

The browser creates one opaque `upload_operation_id` before transfer and reuses
it for retries. App persistence enforces uniqueness by
`{app_id, session_id, upload_operation_id}`.

After app staging succeeds, a retry must call preparation for that existing
record. It must not resend browser bytes unless the original staging record is
unavailable. The app response returns safe staging status even when execution
import fails, allowing the frontend to retry the correct phase.

The requested `analysis_mode` is durable operation state. A failed
`normal_query` analysis remains retryable, and retry must reconstruct that
analysis before the operation can become ready. It cannot silently downgrade
to `none` after canonical import succeeds.

### Content Reuse

Within one app/session, an existing ready uploaded artifact with the same
SHA-256, size, and normalized MIME type is reused. The execution subsystem
returns the existing artifact rather than storing another byte copy. Different
filenames may remain aliases in bounded metadata, but Artifact Library shows
one canonical row.

Cross-session and cross-app deduplication is prohibited even when hashes match.

### Normal Query Analysis

The app may retain extracted text and analysis metadata after staging bytes are
removed. Runtime state references the canonical `artifact_id`, not an upload
filesystem path. Binary files with no extractable text still become ready
artifacts and do not force a synthetic text-analysis result.

## API Changes

### Unified Upload

```http
POST /sessions/{session_id}/artifacts/uploads
Content-Type: multipart/form-data

app_id=<app id>
user_id=<user id>
upload_operation_id=<opaque client id>
analysis_mode=none|normal_query
file=<bytes>
```

Successful response:

```json
{
  "upload_operation_id": "upload_op_...",
  "status": "ready",
  "artifact": {
    "artifact_id": "artifact_...",
    "artifact_type": "session_upload",
    "display_name": "video.mp4",
    "mime_type": "video/mp4",
    "size_bytes": 9891671,
    "content_hash": "sha256:..."
  },
  "reused_existing_artifact": false
}
```

When staging succeeds but import fails, the response includes the same
`upload_operation_id`, `status="failed"`, a stable error code, and
`retryable=true`. It never returns a private path.

### Retry

```http
POST /sessions/{session_id}/artifacts/uploads/{upload_operation_id}/retry
```

The app validates app/user/session scope and resumes the failed phase. Exact
retries are idempotent.

### Delete

```http
DELETE /sessions/{session_id}/artifacts/{artifact_id}
```

Deletion requires exact app/user/session scope. The app deletes any internal
staging or analysis mapping and delegates canonical artifact deletion to the
execution subsystem.

If a queued or running execution currently depends on the artifact, deletion
returns `409 ARTIFACT_IN_USE`. Completed executions do not block deletion.
Their immutable execution records retain artifact id, display metadata, hash,
and verification evidence, but deleted bytes cannot be opened or reused.

Deletion is idempotent: an already deleted artifact returns success without
revealing whether it belonged to another scope.

## Persistence

The app staging record stores:

- `upload_operation_id`;
- app/session/user ownership;
- safe filename and MIME type;
- size and SHA-256;
- staging status and bounded error code;
- canonical `artifact_id` when ready;
- extracted text/analysis metadata when applicable;
- timestamps.

Staging file paths remain private and may be nullable after cleanup. The
execution artifact record remains the canonical byte owner.

Failed staging bytes remain available only for a configurable retry window
with a default of 24 hours. Explicit **Delete** removes failed staging
immediately. Startup and periodic cleanup remove expired staging files and mark
their operations non-retryable without creating an artifact.
Cleanup atomically claims an operation only while it is still expired,
retryable, and in `staged|failed`. Preparation uses the reciprocal
compare-and-set transition from `staged|failed` to `preparing`, so cleanup and
retry cannot both claim the same operation regardless of which starts first.
Transient cleanup failures are bounded and do not terminate the periodic loop.

Execution artifact deletion uses a tombstoned/deleted state rather than
removing historical database identity. Ordinary inventory and resolution
exclude deleted artifacts.

Deletion is coordinated with both persisted queued/running/confirmation
references and process-local provider leases. The exclusive deletion guard
spans the active-reference check and tombstone write, preventing a synchronous
provider from losing bytes during execution and preventing a new lease from
starting midway through deletion.

## Existing Data Compatibility

Existing app session uploads remain readable during migration but are hidden
from the normal default inventory. On first access, the app hashes and imports
legacy uploads through the unified path. Hash-identical records in the same
session resolve to one canonical artifact.

No migration automatically deletes legacy files. A bounded cleanup operation
must first report duplicate groups, canonical artifact mappings, and byte
counts. User-confirmed deletion or session retention may then remove redundant
app copies.

## Security And Limits

- The app credential requires `artifacts:write`; credentials never reach the
  browser.
- App and execution independently enforce app/session ownership.
- Upload, import, and provider staging remain streamed and bounded.
- Filenames are safe basenames; source paths are never accepted from clients.
- Hash and size are verified at every storage boundary.
- Executable media remains denied by policy.
- Artifact upload grants no Agent confirmation or external-write authority.

## Testing And Acceptance

- Normal-query and Composer uploads produce the same artifact response.
- One successful upload appears once in Artifact Library and nowhere as a
  separate session upload.
- A failed import followed by five retries creates one staging record and one
  ready artifact.
- Identical bytes in the same session reuse one artifact; another session does
  not.
- Large video upload remains streamed and reports phase progress.
- Composer selects/unselects a ready artifact without deleting it.
- Delete removes the artifact from Library and Composer after confirmation.
- Delete is blocked while a queued/running execution depends on the artifact.
- Completed execution evidence remains inspectable after deletion.
- Raw JSON errors and private paths never appear in ordinary UI.
- Existing legacy uploads remain recoverable through migration.

## Deferred Work

- Multiple concurrent file uploads.
- Cross-session promotion or app-wide libraries.
- Artifact versions and undelete.
- Automated retention-policy administration.
- Direct browser-to-execution upload.
