# Composer Session Upload To Execution Artifact Design

## Purpose

Execution Composer must let a user upload or select a current-session file and
use it as an Agent input without entering a Windows path, WSL path, artifact id,
or provider-specific staging path.

The selected approach is **prepare on selection**:

1. a file remains an app-owned session upload until selected in Composer;
2. selection prepares one immutable, session-scoped execution artifact;
3. Composer submits the resulting `artifact_ref`;
4. the execution subsystem stages the artifact for Codex or OpenClaw only when
   the confirmed execution runs.

This design extends, rather than replaces:

- `docs/agent-mode-artifact-creation-reuse-contract.md`
- `docs/agent-mode-artifact-creation-reuse-design.md`
- `docs/agent-execution-lifecycle-evidence-contract.md`

Builder is not involved. This is an end-user session workflow between
`ragenius_app_skeleton` and `ragenius_execution_subsystem`.

## Scope

In scope:

- upload from Execution Composer;
- selection of an existing current-session upload;
- authenticated transfer from the app backend to the execution subsystem;
- immutable execution-artifact persistence and idempotent preparation;
- binary-safe, bounded staging for Codex and OpenClaw;
- preparation status, retry, removal, and compatibility UX;
- session ownership and integrity verification.

Out of scope:

- direct browser-to-execution-subsystem upload;
- arbitrary Windows or WSL path entry;
- cross-session file selection;
- app-wide media libraries;
- Builder-managed uploads;
- automatic publishing to an external provider;
- bypassing Agent execution confirmation.

## Product Rules

- The UI says **Upload or select file**, not "promote artifact."
- Uploading or preparing a file is not approval to publish, send, or mutate an
  external system.
- A prepared artifact is backend-neutral. Codex/OpenClaw staging is ephemeral
  and execution-specific.
- The browser sends file bytes only to the app backend. Execution service
  credentials never reach the browser.
- User prompt text must not contain local source paths. The provider prompt
  receives only execution-managed staged paths.
- Preparation is lazy. Files never selected for Agent use are not copied into
  the execution artifact store.

## User Experience

### Composer Input Section

Agent mode adds an **Input files** section:

```text
Input files
[ Upload file ] [ Select session file ]

How_Governed_AI_Professional_Assistants_Work.mp4
video/mp4 | 9.4 MiB | Ready for OpenClaw
[Remove]
```

The section supports:

- upload a new file;
- select one or more existing session uploads;
- show filename, MIME type, size, and preparation state;
- remove a selection without deleting the underlying upload or artifact;
- explain incompatibility with the selected backend;
- retry a failed preparation.

Preparation states are:

- `uploading`: browser is sending a new file to the app backend;
- `preparing`: app and execution subsystem are creating/verifying the artifact;
- `ready`: an execution artifact id and supported reuse mode are available;
- `failed`: preparation failed and can be retried when recoverable.

Composer must disable Run while a selected file is `uploading` or `preparing`,
or when any selected file is incompatible or failed. Text-only Agent runs remain
available when no file is selected.

### Selection And Submission

Selecting an upload immediately starts preparation. On success, frontend state
stores the returned execution artifact metadata and builds:

```json
{
  "artifact_id": "artifact_123",
  "role": "attachment",
  "reuse_mode": "file_backed"
}
```

The transcript may show the display name, but must not embed the upload id,
artifact id, app storage path, or provider staging path in user prompt text.

For an external action, the confirmation UI shows:

- operation and target;
- selected filename, MIME type, and size;
- Agent backend and selected Agent skill;
- external-write warning.

Preparation does not satisfy or consume execution confirmation.

## Ownership Model

There are two records with different owners:

1. `SessionUpload` is owned by `ragenius_app_skeleton` and supports chat/session
   workflows.
2. `StoredArtifactRecord` is owned by `ragenius_execution_subsystem` and is the
   only file input accepted by Agent execution.

The prepared artifact is an immutable snapshot, not a live reference to the app
upload path. Deleting or replacing the app upload after preparation cannot
change bytes already approved for execution.

The execution artifact adds source metadata to the existing record:

```ts
type SessionUploadArtifactOrigin = {
  provider_origin: "session_upload";
  source_upload_id: string;
  content_hash: string; // sha256:<lowercase hex>
  artifact_type: "session_upload";
};
```

It continues to use existing `app_id`, `session_id`, `display_name`,
`mime_type`, `size_bytes`, `file_path`, and `status` fields. No OpenClaw-specific
artifact type is introduced.

## App Backend API

### Upload For Composer

Add a dedicated endpoint rather than invoking the existing upload-analysis chat
pipeline:

```http
POST /sessions/{session_id}/execution-inputs
Content-Type: multipart/form-data

app_id=<app id>
user_id=<user id>
file=<bytes>
```

The endpoint:

1. validates `{app_id, session_id, user_id}`;
2. streams the upload to app-owned session storage through a temporary file;
3. computes SHA-256 and size while streaming;
4. atomically creates the session upload record;
5. prepares it through the execution subsystem;
6. returns both safe upload metadata and the prepared artifact.

It must not load the full file into Python memory or run `run_chat_pipeline`.
The app-owned session upload schema must persist the computed `sha256` value;
existing uploads without a hash compute and store it on their first preparation.

### Prepare Existing Upload

```http
POST /sessions/{session_id}/uploads/{upload_id}/prepare-for-execution
Content-Type: application/json

{
  "app_id": "app_123",
  "user_id": "user_123"
}
```

The app backend validates that the upload belongs to the exact session and that
the session belongs to the supplied app/user. It then streams the server-side
file to the authenticated execution-subsystem import endpoint.

The response shape for both paths is:

```ts
type PreparedExecutionInputResponse = {
  upload: {
    id: string;
    filename: string;
    mime_type?: string;
    size_bytes: number;
    sha256: string;
  };
  artifact: {
    artifact_id: string;
    artifact_type: "session_upload";
    display_name: string;
    mime_type?: string;
    size_bytes: number;
    content_hash: string;
    capabilities: {
      can_reuse: true;
      supported_reuse_modes: string[];
    };
  };
  preparation_status: "ready";
  reused_existing_artifact: boolean;
};
```

## Execution Subsystem Import API

Add a service-authenticated endpoint:

```http
POST /v1/artifact-imports/session-upload
Content-Type: multipart/form-data
Authorization: Bearer <service credential>

app_id=<app id>
session_id=<session id>
source_upload_id=<opaque upload id>
display_name=<basename only>
mime_type=<media type>
declared_size_bytes=<integer>
declared_sha256=sha256:<hex>
file=<stream>
```

The endpoint requires the artifact-write service scope defined by the execution
service authentication contract. It never accepts a source filesystem path.

Import processing:

1. validate fields and configured size/MIME policy;
2. stream to a temporary file inside the artifact-store root;
3. compute size and SHA-256 during transfer;
4. reject a declared/observed mismatch;
5. check idempotency;
6. atomically persist the file and `StoredArtifactRecord`;
7. return the normalized reusable-artifact record.

### Idempotency

The idempotency identity is:

```text
{app_id, session_id, source_upload_id, declared_sha256}
```

- An exact match returns the existing artifact with
  `reused_existing_artifact=true`.
- The same source upload id with a different hash returns
  `SESSION_UPLOAD_CONTENT_CONFLICT`.
- Concurrent identical imports must result in one ready artifact.
- Failed temporary imports leave no visible artifact record.

## Size And Transfer Policy

The previous 25 MiB OpenClaw MVP recommendation is insufficient for video.
Introduce a configurable Agent-input limit with a conservative default of
`512 MiB`. Deployments may raise it after validating disk quotas, HTTP proxy
limits, timeout settings, and provider constraints.

Required transfer behavior:

- browser-to-app and app-to-execution transfers are streamed;
- temporary and final files remain under their subsystem-owned storage roots;
- filenames are reduced to safe basenames;
- partial files use non-addressable temporary names and are removed on failure;
- hashes and sizes are verified at every ownership boundary;
- logs contain identifiers and sizes, never file bytes or credentials.

OpenClaw staging must not convert large files to in-memory base64 chunks. On the
Windows/WSL deployment, the trusted staging bridge resolves the execution-owned
artifact file to a WSL-visible source and performs an argument-safe file copy
into the current run's `inputs/` directory. The agent still receives only the
run-scoped destination path and remains prohibited from using `/mnt/c` or
`/mnt/d` itself.

`session_upload` artifacts therefore default to `file_backed` consumption.
`binary_payload` remains available only where an existing consumer explicitly
requires it and the configured in-memory binary limit permits it.

Codex staging likewise uses a streamed or filesystem copy into the Codex run
workspace. Agents must not receive the original app-upload path.

## Error Contract

Stable error codes include:

- `SESSION_UPLOAD_NOT_FOUND`
- `SESSION_UPLOAD_SCOPE_MISMATCH`
- `SESSION_UPLOAD_FILE_UNAVAILABLE`
- `EXECUTION_INPUT_TOO_LARGE`
- `EXECUTION_INPUT_MEDIA_TYPE_NOT_ALLOWED`
- `EXECUTION_INPUT_INTEGRITY_MISMATCH`
- `SESSION_UPLOAD_CONTENT_CONFLICT`
- `EXECUTION_ARTIFACT_IMPORT_UNAVAILABLE`
- `EXECUTION_ARTIFACT_IMPORT_FAILED`
- `AGENT_BACKEND_ARTIFACT_INCOMPATIBLE`

The app maps these to short Composer messages and preserves detailed diagnostics
for the inspector. Retrying must reuse the same upload id and hash.

## Cleanup And Retention

- Removing a file from Composer changes selection only.
- Deleting an app session upload does not silently delete a prepared execution
  artifact that may be referenced by an execution record.
- Deleting a prepared artifact uses the existing scoped artifact deletion API.
- Run-scoped provider staging remains subject to existing run retention.
- Orphaned temporary imports are removed on startup and by periodic cleanup.
- Coordinated session-retention cleanup is a future lifecycle feature and is
  not required for the first implementation.

## Security

- The browser cannot choose `app_id`/`session_id` independently of the active
  session accepted by the app backend.
- The execution subsystem independently enforces artifact app/session scope.
- Source paths are server-private and never accepted from or returned to the
  browser.
- Symlinks and paths escaping either storage root are rejected.
- MIME type is advisory; extension and optional content sniffing may tighten
  policy but must not replace hash/size verification.
- Executable file types are denied by default for the first implementation.
- Preparing a file grants no network or external-write permission.
- External publishing remains `agent_external_write` and requires a fresh,
  single-use confirmation.

## Implementation Boundaries

### `ragenius_app_skeleton`

- owns upload UX, session-upload records, user scope, and promotion orchestration;
- never writes directly into execution artifact storage;
- never exposes execution service credentials to the frontend.

### `ragenius_execution_subsystem`

- owns import validation, immutable artifact persistence, compatibility,
  resolution, provider staging, and integrity evidence;
- accepts only authenticated streams and structured metadata;
- remains authoritative for execution policy and confirmation.

### `ragenius_builder`

- no runtime dependency and no changes for this feature.

## Verification

Required automated coverage:

- Composer upload and existing-upload selection;
- Run disabled during preparation and enabled when ready;
- exact app/user/session ownership checks;
- successful idempotent import and concurrent duplicate handling;
- hash, size, path, symlink, MIME, and configured-limit rejection;
- interrupted upload/import cleanup;
- Codex and OpenClaw artifact-ref submission without source paths in prompts;
- large binary staging without full-file buffering or base64 transfer;
- confirmation remains required for external publishing;
- provider staging hash matches the prepared artifact hash.

Required live smoke test:

1. upload the 9,891,671-byte MP4 from Composer;
2. verify it becomes one session-scoped execution artifact;
3. select Codex and verify staged input access without the Windows source path;
4. select OpenClaw and verify staged input access without `/mnt/c` or `/mnt/d` in
   the Agent prompt;
5. confirm a YouTube publication request;
6. verify either a provider-backed video id/URL or a precise downstream provider
   denial. A generated status report alone is not publication success.

## Acceptance Criteria

- A user can upload or select a current-session file entirely within Composer.
- The user never types or sees a local/provider staging path.
- Selection produces one immutable, reusable, session-scoped execution artifact.
- Duplicate preparation is idempotent.
- Codex and OpenClaw receive only run-scoped staged paths.
- Large binary transfer is bounded, streamed, integrity-checked, and cleaned up
  on failure.
- External writes still require single-use confirmation and provider evidence.
