# Composer Session Upload To Execution Artifact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user upload or select a current-session file in Execution Composer and run Codex or OpenClaw with an immutable, execution-managed, run-scoped copy without typing local paths.

**Architecture:** `ragenius_app_skeleton` owns browser upload, user/session authorization, and the app upload record. It streams a selected upload through a service-authenticated import endpoint; `ragenius_execution_subsystem` verifies and persists one idempotent session-scoped artifact, then stages that artifact into a provider run workspace after execution confirmation. Large files use `file_backed` streaming/copy paths and never pass through in-memory base64.

**Tech Stack:** React 18/Vitest, FastAPI/Python/pytest/httpx, Fastify 5/TypeScript/Node test runner/@fastify/multipart, filesystem artifact storage, Codex CLI, WSL/OpenClaw.

## Global Constraints

- Extend `docs/agent-mode-artifact-creation-reuse-contract.md`; do not introduce a second artifact model.
- Keep all artifact references scoped to exact `{app_id, session_id}`; app routes additionally enforce `user_id`.
- The browser never receives the execution service credential or a server filesystem path.
- The execution import endpoint never accepts a source filesystem path.
- `session_upload` artifacts default to `file_backed` consumption.
- Default maximum Agent input size is exactly `536870912` bytes (`512 MiB`) and is configurable.
- Upload, import, Codex staging, and OpenClaw staging must not buffer the complete video or encode it as base64.
- Persist and compare `sha256:<lowercase hex>` plus exact byte size at every ownership boundary.
- Preparation does not grant external-write permission; publishing remains `agent_external_write` with single-use confirmation.
- Do not add runtime behavior to legacy `ragenius_app` or admin behavior to Builder.
- Preserve the corrected OpenClaw run root: `/home/openclaw/.openclaw/workspace/runs/<execution_id>`.
- Before execution, commit the six existing verified dirty files separately or carry them into an isolated worktree without mixing them into feature commits.

## File Structure

### Execution Subsystem

- Create `src/core/artifacts/session-upload-artifact-importer.ts`: stream validation, hashing, idempotency, temporary-file cleanup, and artifact persistence orchestration.
- Create `src/api/routes/artifact-imports.routes.ts`: authenticated multipart endpoint only.
- Create `tests/artifacts/session-upload-artifact-importer.test.ts`: importer behavior and concurrency.
- Create `tests/api/artifact-import-routes.test.ts`: service scope, multipart validation, and normalized errors.
- Modify `src/core/tools/providers/artifact-store.ts`: source-upload provenance fields, atomic imported-file persistence, and idempotency lookup.
- Modify `src/core/artifacts/artifact-consumption-registry.ts`: reusable `session_upload` definition.
- Modify `src/config/env.ts` and `src/config/runtime-config.ts`: exact import limits.
- Modify `src/app.ts`: importer service construction and route registration.
- Modify `src/core/agents/codex-workspace.ts`: streamed/file-copy staging and streamed hash verification.
- Modify `src/core/agents/openclaw-workspace.ts`: direct trusted WSL file copy for `file_backed` inputs.
- Modify `src/core/agents/openclaw-cli-provider.ts`: pass file-transfer dependency without replacing the corrected run root.
- Modify `package.json`, `package-lock.json`, and `.env.example`: multipart dependency and configuration.

### App Backend

- Create `backend/app/execution_input_service.py`: prepare orchestration and safe error normalization.
- Create `backend/tests/test_execution_input_uploads.py`: app upload, preparation, scope, and retry behavior.
- Modify `backend/app/chat_repos.py`: SHA-256 column migration, streamed upload persistence, scoped lookup, and lazy hash backfill.
- Modify `backend/app/execution_subsystem_client.py`: authenticated streaming multipart import.
- Modify `backend/app/main.py`: Composer upload and prepare-existing-upload routes.
- Modify `backend/requirements.txt`: explicit `httpx` dependency.

### Frontend

- Modify `frontend/src/components/ExecutionComposer.jsx`: upload/select controls and preparation states.
- Modify `frontend/src/components/ExecutionComposer.test.jsx`: component-level UX and submission coverage.
- Modify `frontend/src/App.jsx`: endpoint calls, inventory refresh, and Composer props.
- Modify `frontend/src/App.test.jsx`: app integration and exact structured `artifact_refs`.

### Documentation

- Modify `docs/agent-mode-artifact-creation-reuse-contract.md`: import API and session-upload origin addendum.
- Modify `docs/agent-mode-artifact-creation-reuse-design.md`: final data flow and provider staging behavior.
- Modify `ragenius_execution_subsystem/docs/service-authentication-guide.md`: add the artifact-import scope and credential example.

---

### Task 1: Execution Artifact Import Core

**Files:**
- Create: `ragenius_execution_subsystem/src/core/artifacts/session-upload-artifact-importer.ts`
- Modify: `ragenius_execution_subsystem/src/core/tools/providers/artifact-store.ts`
- Modify: `ragenius_execution_subsystem/src/core/artifacts/artifact-consumption-registry.ts`
- Modify: `ragenius_execution_subsystem/src/config/env.ts`
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`
- Test: `ragenius_execution_subsystem/tests/artifacts/session-upload-artifact-importer.test.ts`

**Interfaces:**
- Consumes: Node `Readable`, configured artifact-store root, and existing `ArtifactStore` containment rules.
- Produces:

```ts
export type SessionUploadArtifactImportInput = {
  appId: string;
  sessionId: string;
  sourceUploadId: string;
  displayName: string;
  mimeType?: string;
  declaredSizeBytes: number;
  declaredSha256: string;
  stream: NodeJS.ReadableStream;
};

export type SessionUploadArtifactImportResult = {
  artifact: Omit<StoredArtifactRecord, "content">;
  reusedExistingArtifact: boolean;
};

export class SessionUploadArtifactImporter {
  import(input: SessionUploadArtifactImportInput): Promise<SessionUploadArtifactImportResult>;
  cleanupExpiredTemporaryFiles(): Promise<void>;
}
```

- Adds `source_upload_id?: string` to `StoredArtifactRecord` and `sourceUploadId?: string` to `ArtifactStore.save` options.
- Adds `ArtifactStore.findSessionUploadImport({appId, sessionId, sourceUploadId})`.

- [ ] **Step 1: Write importer tests before implementation**

Cover a successful `video/mp4` stream, exact idempotent retry, same upload id with different hash, size/hash mismatch, maximum-size rejection, MIME rejection, concurrent identical calls returning one artifact id, and temporary-file cleanup. Use a chunked custom `Readable`, not one complete video `Buffer`, for the success test.

```ts
const stream = Readable.from([Buffer.from("video-"), Buffer.from("bytes")]);
const result = await importer.import({
  appId: "app_1",
  sessionId: "session_1",
  sourceUploadId: "upload_1",
  displayName: "video.mp4",
  mimeType: "video/mp4",
  declaredSizeBytes: 11,
  declaredSha256: `sha256:${createHash("sha256").update("video-bytes").digest("hex")}`,
  stream
});
assert.equal(result.artifact.artifact_type, "session_upload");
assert.equal(result.artifact.provider_origin, "session_upload");
assert.equal(result.artifact.source_upload_id, "upload_1");
```

- [ ] **Step 2: Run the new test and verify RED**

Run from `ragenius_execution_subsystem`:

```powershell
npm run build
node --experimental-test-isolation=none --test-concurrency=1 --test dist/tests/artifacts/session-upload-artifact-importer.test.js
```

Expected: compilation fails because the importer and source-upload store APIs do not exist.

- [ ] **Step 3: Add exact runtime configuration**

Add:

```ts
AGENT_INPUT_MAX_BYTES: z.coerce.number().int().positive().default(536870912),
AGENT_INPUT_ALLOWED_MIME_TYPES: z.string().default("video/mp4,application/pdf,text/plain,text/markdown,application/octet-stream"),
AGENT_INPUT_TEMP_RETENTION_HOURS: z.coerce.number().int().positive().default(24),
AGENT_BINARY_IN_MEMORY_MAX_BYTES: z.coerce.number().int().positive().default(26214400),
```

Expose them as `runtimeConfig.artifactImports` with `maxBytes`, normalized `allowedMimeTypes`, `tempRetentionHours`, and `binaryInMemoryMaxBytes`.

- [ ] **Step 4: Implement store provenance and idempotent import**

Register `session_upload` with default `file_backed` and supported modes `file_backed`, `binary_payload`, and `metadata_only`. Stream to a non-addressable temp file under the artifact root, hash while writing, compare declared values, serialize identical imports through a keyed in-process lock, atomically persist the final file/metadata, and remove temp files in `finally`.

Return these stable errors through `AppError`: `EXECUTION_INPUT_TOO_LARGE`, `EXECUTION_INPUT_MEDIA_TYPE_NOT_ALLOWED`, `EXECUTION_INPUT_INTEGRITY_MISMATCH`, and `SESSION_UPLOAD_CONTENT_CONFLICT`.

- [ ] **Step 5: Run importer tests and existing artifact tests**

```powershell
npm run build
node --experimental-test-isolation=none --test-concurrency=1 --test dist/tests/artifacts/session-upload-artifact-importer.test.js dist/tests/artifacts/artifact-resolver.test.js dist/tests/agents/agent-artifact-resolver.test.js
```

Expected: all pass and the ready artifact's stored bytes match the declared hash.

- [ ] **Step 6: Commit Task 1**

```powershell
git add ragenius_execution_subsystem/src/core/artifacts ragenius_execution_subsystem/src/core/tools/providers/artifact-store.ts ragenius_execution_subsystem/src/config ragenius_execution_subsystem/tests/artifacts/session-upload-artifact-importer.test.ts
git commit -m "feat(execution): import session uploads as artifacts"
```

### Task 2: Authenticated Multipart Import Route

**Files:**
- Create: `ragenius_execution_subsystem/src/api/routes/artifact-imports.routes.ts`
- Create: `ragenius_execution_subsystem/tests/api/artifact-import-routes.test.ts`
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Modify: `ragenius_execution_subsystem/src/config/runtime-config.ts`
- Modify: `ragenius_execution_subsystem/package.json`
- Modify: `ragenius_execution_subsystem/package-lock.json`

**Interfaces:**
- Consumes: `SessionUploadArtifactImporter.import` from Task 1 and `hasServiceScope`.
- Produces: `POST /v1/artifact-imports/session-upload`, requiring scope `artifacts:write`.

- [ ] **Step 1: Install and register multipart support**

Run from `ragenius_execution_subsystem`:

```powershell
npm install @fastify/multipart@^9
```

Register multipart with `limits.files = 1`, `limits.fields = 8`, and `limits.fileSize = runtimeConfig.artifactImports.maxBytes` before registering the route.

- [ ] **Step 2: Write failing route tests**

Tests must cover no credential (`401`), credential without `artifacts:write` (`403`), malformed fields (`400`), oversized multipart (`413` or normalized `EXECUTION_INPUT_TOO_LARGE`), valid import (`201`), and exact retry (`200`, `reused_existing_artifact=true`). Build multipart test bodies with Fastify injection and a fixed boundary so no browser client is involved.

```ts
assert.equal(response.statusCode, 201);
const body = response.json();
assert.equal(body.preparation_status, "ready");
assert.equal(body.reused_existing_artifact, false);
assert.equal(body.artifact.artifact_type, "session_upload");
assert.equal(body.artifact.display_name, "video.mp4");
```

- [ ] **Step 3: Run route tests and verify RED**

```powershell
npm run build
node --experimental-test-isolation=none --test-concurrency=1 --test dist/tests/api/artifact-import-routes.test.js
```

Expected: route is `404`.

- [ ] **Step 4: Implement the scoped route**

Parse exactly one file plus `app_id`, `session_id`, `source_upload_id`, `display_name`, `mime_type`, `declared_size_bytes`, and `declared_sha256`. Do not accept `file_path`. Reject requests before reading bytes when `hasServiceScope(request, "artifacts:write")` is false.

Return only normalized artifact metadata; omit `path`, `file_path`, and temporary paths.

- [ ] **Step 5: Wire importer lifecycle into `AppServices`**

Add `sessionUploadArtifactImporter` to `AppServices`, construct it from `artifactStore` plus `runtimeConfig.artifactImports`, invoke `cleanupExpiredTemporaryFiles()` during startup, and register the route under `/v1`.

- [ ] **Step 6: Run route, auth, and artifact file tests**

```powershell
npm run build
node --experimental-test-isolation=none --test-concurrency=1 --test dist/tests/api/artifact-import-routes.test.js dist/tests/api/service-auth.test.js dist/tests/api/artifact-file-routes.test.js
```

- [ ] **Step 7: Commit Task 2**

```powershell
git add ragenius_execution_subsystem/package.json ragenius_execution_subsystem/package-lock.json ragenius_execution_subsystem/src/app.ts ragenius_execution_subsystem/src/api/routes/artifact-imports.routes.ts ragenius_execution_subsystem/tests/api/artifact-import-routes.test.ts
git commit -m "feat(execution): expose session upload import API"
```

### Task 3: Streamed App Session Upload Persistence

**Files:**
- Modify: `ragenius_app_skeleton/backend/app/chat_repos.py`
- Create: `ragenius_app_skeleton/backend/tests/test_execution_input_uploads.py`

**Interfaces:**
- Produces:

```python
SessionRepo.add_upload_stream(
    session_id: str,
    *,
    filename: str,
    mime_type: str | None,
    source: BinaryIO,
    max_bytes: int,
) -> dict[str, Any]

SessionRepo.get_upload(session_id: str, upload_id: str) -> dict[str, Any] | None
SessionRepo.ensure_upload_sha256(session_id: str, upload_id: str) -> dict[str, Any]
```

- Returned upload records include `sha256` formatted as `sha256:<hex>`.

- [ ] **Step 1: Write repository tests**

Test chunked persistence, 512 MiB configurable enforcement with a small test limit, safe basename normalization, exact SHA-256, scoped lookup, existing-upload lazy hash backfill, partial-file cleanup, and unchanged byte-oriented `add_upload` behavior.

- [ ] **Step 2: Run tests and verify RED**

```powershell
python -m pytest ragenius_app_skeleton/backend/tests/test_execution_input_uploads.py -q
```

Expected: missing `add_upload_stream` and `sha256` column behavior.

- [ ] **Step 3: Migrate SQLite safely**

Add nullable `sha256 TEXT` to the uploads DDL and use `PRAGMA table_info(uploads)` plus:

```sql
ALTER TABLE uploads ADD COLUMN sha256 TEXT
```

Existing rows remain valid and are backfilled only when prepared.

- [ ] **Step 4: Implement streamed persistence**

Read `1024 * 1024` byte chunks, reject once cumulative bytes exceed `max_bytes`, hash each chunk, flush and close before `os.replace`, then insert the DB row. Ensure both temporary and final files remain under `uploads_dir / session_id` and reject symlinks on lookup/preparation.

- [ ] **Step 5: Run repository tests**

```powershell
python -m pytest ragenius_app_skeleton/backend/tests/test_execution_input_uploads.py -q
```

- [ ] **Step 6: Commit Task 3**

```powershell
git add ragenius_app_skeleton/backend/app/chat_repos.py ragenius_app_skeleton/backend/tests/test_execution_input_uploads.py
git commit -m "feat(app): persist hashed execution input uploads"
```

### Task 4: App Preparation Client And Routes

**Files:**
- Create: `ragenius_app_skeleton/backend/app/execution_input_service.py`
- Modify: `ragenius_app_skeleton/backend/app/execution_subsystem_client.py`
- Modify: `ragenius_app_skeleton/backend/app/main.py`
- Modify: `ragenius_app_skeleton/backend/requirements.txt`
- Modify: `ragenius_app_skeleton/backend/tests/test_execution_input_uploads.py`
- Modify: `ragenius_app_skeleton/backend/tests/test_execution_subsystem_client.py`

**Interfaces:**
- Consumes: Task 2 import endpoint and Task 3 repository methods.
- Produces:

```python
ExecutionSubsystemClient.import_session_upload(
    *, app_id: str, session_id: str, source_upload_id: str,
    display_name: str, mime_type: str | None, size_bytes: int,
    sha256: str, file_path: str,
) -> dict[str, Any]
```

- Produces app routes:
  - `POST /sessions/{session_id}/execution-inputs`
  - `POST /sessions/{session_id}/uploads/{upload_id}/prepare-for-execution`

- [ ] **Step 1: Add explicit streaming HTTP dependency**

Add `httpx>=0.27,<1` to `backend/requirements.txt`. Use `httpx.Client.stream`/multipart file objects; never call `Path.read_bytes()`.

- [ ] **Step 2: Write failing client tests**

Use `httpx.MockTransport` to assert the Authorization header, multipart field names, streamed file body, timeout normalization, and preservation of execution-subsystem error codes.

- [ ] **Step 3: Write failing app-route tests**

Test new upload plus prepare, existing upload plus prepare, wrong user (`404`), wrong app (`404`), missing upload (`404`), recoverable import failure (`502` with stable detail), and idempotent retry returning the same artifact id. Assert the Composer endpoint does not invoke `run_chat_pipeline`.

- [ ] **Step 4: Run backend tests and verify RED**

```powershell
python -m pytest ragenius_app_skeleton/backend/tests/test_execution_input_uploads.py ragenius_app_skeleton/backend/tests/test_execution_subsystem_client.py -q
```

- [ ] **Step 5: Implement preparation orchestration**

`execution_input_service.py` must validate the repository path is a regular contained file, ensure/backfill SHA-256, call `import_session_upload`, and map the response to:

```python
{
    "upload": safe_upload_metadata,
    "artifact": safe_artifact_metadata,
    "preparation_status": "ready",
    "reused_existing_artifact": bool(result.get("reused_existing_artifact")),
}
```

Never include `file_path` in an HTTP response.

- [ ] **Step 6: Implement the two FastAPI routes**

The direct Composer upload uses `UploadFile.file` with `add_upload_stream` through `run_in_threadpool`, then immediately prepares it. The existing-upload route calls `_require_session_scope` before looking up the upload. Read the app-side maximum from `RAGENIUS_AGENT_INPUT_MAX_BYTES`, defaulting to `536870912`.

- [ ] **Step 7: Run backend tests**

```powershell
python -m pytest ragenius_app_skeleton/backend/tests/test_execution_input_uploads.py ragenius_app_skeleton/backend/tests/test_execution_subsystem_client.py ragenius_app_skeleton/backend/tests/test_session_artifact_proxy.py -q
```

- [ ] **Step 8: Commit Task 4**

```powershell
git add ragenius_app_skeleton/backend/app/execution_input_service.py ragenius_app_skeleton/backend/app/execution_subsystem_client.py ragenius_app_skeleton/backend/app/main.py ragenius_app_skeleton/backend/requirements.txt ragenius_app_skeleton/backend/tests
git commit -m "feat(app): prepare session uploads for Agent execution"
```

### Task 5: Large File Provider Staging

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/agents/codex-workspace.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/openclaw-workspace.ts`
- Modify: `ragenius_execution_subsystem/src/core/agents/openclaw-cli-provider.ts`
- Modify: `ragenius_execution_subsystem/src/core/artifacts/artifact-resolver.ts`
- Test: `ragenius_execution_subsystem/tests/agents/codex-workspace.test.ts`
- Test: `ragenius_execution_subsystem/tests/agents/openclaw-workspace.test.ts`
- Test: `ragenius_execution_subsystem/tests/agents/openclaw-cli-provider.test.ts`

**Interfaces:**
- Consumes: resolved `file_backed` artifact paths owned by the execution artifact store.
- Produces file-copy staging with exact post-copy size/SHA-256 evidence.

- [ ] **Step 1: Add failing streamed-staging tests**

For Codex, instrument `fs.readFile` or inject a copy implementation so a multi-chunk `file_backed` fixture fails if the complete source/destination is read into memory. For OpenClaw, assert `file_backed` invokes a `transferFile` dependency and never calls the base64 transfer dependency. Retain existing small `binary_payload` tests.

- [ ] **Step 2: Run provider tests and verify RED**

```powershell
npm run build
node --experimental-test-isolation=none --test-concurrency=1 --test dist/tests/agents/codex-workspace.test.js dist/tests/agents/openclaw-workspace.test.js dist/tests/agents/openclaw-cli-provider.test.js
```

- [ ] **Step 3: Stream Codex staging**

For `file_backed`, validate the source with `lstat`/`realpath`, use `fs.copyFile` with exclusive destination semantics, and compute destination hash through `createReadStream`. Do not call `artifactBytes` or `fs.readFile` for this mode. Keep inline text bounded and enforce `binaryInMemoryMaxBytes` before decoding base64.

- [ ] **Step 4: Add trusted WSL file transfer**

Define:

```ts
export type OpenClawFileTransfer = (input: {
  sourceWindowsPath: string;
  workspaceAbsolutePath: string;
  allowedWorkspaceRoot: string;
  expectedSizeBytes: number;
  expectedSha256: string;
}) => Promise<OpenClawFileInspection>;
```

The default implementation resolves the execution-owned Windows source with `wslpath`, creates/canonicalizes the run-scoped destination parent, invokes `cp -- <source> <destination>` through argument arrays, and verifies destination size/hash. The Agent prompt receives only `<run_workspace_root>/inputs/...`; it never receives the WSL-visible source path.

- [ ] **Step 5: Preserve corrected run-root behavior**

In `openclaw-cli-provider.ts`, continue passing the current value from `buildOpenClawRunWorkspaceRoot`. Do not substitute the shared workspace root when adding `transferFile`. Add a regression assertion that the destination includes `/runs/execution_001/inputs/`.

- [ ] **Step 6: Run provider and resolver tests**

```powershell
npm run build
node --experimental-test-isolation=none --test-concurrency=1 --test dist/tests/agents/codex-workspace.test.js dist/tests/agents/openclaw-workspace.test.js dist/tests/agents/openclaw-cli-provider.test.js dist/tests/artifacts/artifact-resolver.test.js
```

- [ ] **Step 7: Commit Task 5**

```powershell
git add ragenius_execution_subsystem/src/core/agents ragenius_execution_subsystem/src/core/artifacts/artifact-resolver.ts ragenius_execution_subsystem/tests/agents ragenius_execution_subsystem/tests/artifacts/artifact-resolver.test.ts
git commit -m "feat(execution): stream large Agent input staging"
```

### Task 6: Execution Composer Upload And Selection UX

**Files:**
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/components/ExecutionComposer.test.jsx`

**Interfaces:**
- Consumes props:

```js
sessionUploads = []
onUploadExecutionInput(file) => Promise<PreparedExecutionInputResponse>
onPrepareSessionUpload(uploadId) => Promise<PreparedExecutionInputResponse>
```

- Produces existing Agent submission with prepared artifacts in `args.artifactRefs`.

- [ ] **Step 1: Write failing Composer tests**

Cover Agent-only **Upload file** and **Select session file** controls, `uploading -> preparing -> ready`, automatic selection of the returned artifact, retry after recoverable failure, remove-selection behavior, Run disabled while pending/failed, backend switch reusing the same prepared artifact, and exact `file_backed` ref submission.

```js
expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
  args: expect.objectContaining({
    artifactRefs: [{
      artifact_id: "artifact_video",
      role: "attachment",
      reuse_mode: "file_backed",
    }],
  }),
}));
```

- [ ] **Step 2: Run component tests and verify RED**

Run from `ragenius_app_skeleton/frontend`:

```powershell
npm test -- ExecutionComposer.test.jsx
```

- [ ] **Step 3: Implement focused input state**

Keep `preparedArtifactsByUploadId`, `preparationStateByUploadId`, and local error text inside Composer. Merge prepared artifacts with `artifactInventory` by `artifact_id`, then reuse the existing Agent artifact selector and `buildAgentArtifactRef` path. Do not duplicate submission serialization.

- [ ] **Step 4: Implement the controls and accessible status**

Use a file input labeled **Upload file**, a current-session upload selector, filename/type/size rows, `aria-live="polite"` preparation status, Retry, and Remove. Never render `file_path`, WSL paths, or artifact ids as primary labels.

- [ ] **Step 5: Run component tests**

```powershell
npm test -- ExecutionComposer.test.jsx
```

- [ ] **Step 6: Commit Task 6**

```powershell
git add ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx ragenius_app_skeleton/frontend/src/components/ExecutionComposer.test.jsx
git commit -m "feat(app): upload Agent inputs from Composer"
```

### Task 7: Frontend App Wiring And Structured Submission

**Files:**
- Modify: `ragenius_app_skeleton/frontend/src/App.jsx`
- Modify: `ragenius_app_skeleton/frontend/src/App.test.jsx`

**Interfaces:**
- Consumes: Task 4 app routes and Task 6 Composer props.
- Produces refreshed session uploads/artifacts plus unchanged provider-neutral execution submission.

- [ ] **Step 1: Write failing app integration tests**

Open Composer in a draft session, upload a video, assert session preparation occurs first, assert `POST /sessions/<id>/execution-inputs`, and assert final `/chat` submission contains only the structured artifact ref. Add an existing-upload selection test for `/prepare-for-execution`. Assert the prompt contains neither `C:\\` nor `/mnt/`.

- [ ] **Step 2: Run app tests and verify RED**

```powershell
npm test -- App.test.jsx
```

- [ ] **Step 3: Add endpoint functions and refresh behavior**

Add `uploadExecutionInput(file)` and `prepareSessionUpload(uploadId)` near existing upload/artifact functions. Both send active `app_id`, `session_id`, and `user_id`; update `sessionUploadsBySession`; refresh `GET /sessions/{session_id}/artifacts`; return the normalized preparation response to Composer.

- [ ] **Step 4: Pass Composer props without changing other modes**

Pass `activeSessionUploads`, `uploadExecutionInput`, and `prepareSessionUpload` through `ChatPanel` to `ExecutionComposer`. Keep the existing draft-session preparation fix and the current tool/skill artifact behavior intact.

- [ ] **Step 5: Run frontend tests and build**

```powershell
npm test -- ExecutionComposer.test.jsx App.test.jsx ArtifactLibrary.test.jsx
npm run build
```

- [ ] **Step 6: Commit Task 7**

```powershell
git add ragenius_app_skeleton/frontend/src/App.jsx ragenius_app_skeleton/frontend/src/App.test.jsx
git commit -m "feat(app): wire Composer execution input preparation"
```

### Task 8: Configuration, Contracts, Full Verification, And Live Smoke

**Files:**
- Modify: `ragenius_execution_subsystem/.env.example`
- Modify: `docs/agent-mode-artifact-creation-reuse-contract.md`
- Modify: `docs/agent-mode-artifact-creation-reuse-design.md`
- Modify: `ragenius_execution_subsystem/docs/service-authentication-guide.md`
- Create: `ragenius_execution_subsystem/scripts/smoke-agent-input-upload.ts`

**Interfaces:**
- Consumes all previous tasks.
- Produces deployment instructions, automated smoke coverage, and live evidence.

- [ ] **Step 1: Document exact configuration**

Add:

```dotenv
AGENT_INPUT_MAX_BYTES=536870912
AGENT_INPUT_ALLOWED_MIME_TYPES=video/mp4,application/pdf,text/plain,text/markdown,application/octet-stream
AGENT_INPUT_TEMP_RETENTION_HOURS=24
AGENT_BINARY_IN_MEMORY_MAX_BYTES=26214400
```

Document that the app uses matching `RAGENIUS_AGENT_INPUT_MAX_BYTES=536870912` and that its service credential requires `artifacts:write` in addition to existing execution scopes. Update the `.env.example` app credential to include `scopes:["agent_skills:read","artifacts:write"]`.

- [ ] **Step 2: Update the existing contract and design**

Add the final import request/response, source-upload provenance, idempotency key, no-path rule, preparation states, 512 MiB default, `file_backed` default, streamed provider staging, and confirmation separation. Link the approved specification rather than copying its full prose.

- [ ] **Step 3: Add an automated local smoke script**

The script creates a temporary chunked fixture larger than the in-memory binary limit, imports it twice, verifies one artifact id, submits mocked/dry-run Codex and OpenClaw artifact refs, and confirms no source path appears in provider prompts. It must delete its temporary fixture in `finally`.

- [ ] **Step 4: Run execution subsystem verification**

```powershell
npm run typecheck
npm run lint
npm test
```

- [ ] **Step 5: Run app backend verification**

```powershell
python -m pytest ragenius_app_skeleton/backend/tests -q
```

- [ ] **Step 6: Run app frontend verification**

```powershell
npm test
npm run build
```

Run from `ragenius_app_skeleton/frontend`.

- [ ] **Step 7: Run the real Composer upload smoke test**

With all three subsystems started from the same integrated branch:

1. open a new chat and Agent mode Composer;
2. upload `C:\Users\User\OneDrive\Desktop\How_Governed_AI_Professional_Assistants_Work.mp4`;
3. verify UI size `9,891,671` bytes and status `Ready`;
4. verify Artifact Library contains one `session_upload` artifact after two preparations;
5. run Codex and inspect that its staged path is under `storage/codex-runs/<execution_id>/inputs/`;
6. run OpenClaw and inspect that its staged path is under `/home/openclaw/.openclaw/workspace/runs/<execution_id>/inputs/`;
7. verify both staged hashes match the prepared artifact;
8. confirm a YouTube publishing request and require a provider video id/URL for success; a status markdown file alone is insufficient.

- [ ] **Step 8: Commit Task 8**

```powershell
git add ragenius_execution_subsystem/.env.example ragenius_execution_subsystem/scripts/smoke-agent-input-upload.ts docs ragenius_execution_subsystem/docs
git commit -m "docs: complete Composer Agent input rollout"
```

### Task 9: Review And Branch Integration

**Files:**
- Review all files changed by Tasks 1-8.

**Interfaces:**
- Consumes: complete tested feature branch.
- Produces: reviewed integration into `main` without including local runtime data.

- [ ] **Step 1: Run focused diff review**

```powershell
git diff --check main...HEAD
git diff --stat main...HEAD
git status --short
```

Confirm no `.env`, runtime database, session upload, execution artifact, provider run, or test scratch file is tracked.

- [ ] **Step 2: Request code review**

Use `superpowers:requesting-code-review`. Resolve correctness, security, streaming, and missing-test findings before integration.

- [ ] **Step 3: Re-run full verification after review fixes**

Repeat Task 8 Steps 4-6 and the artifact-preparation portion of the live smoke test.

- [ ] **Step 4: Integrate the isolated branch**

Use `superpowers:finishing-a-development-branch`. Merge the reviewed feature branch into local `main`, rerun focused startup health checks on ports `8011`, `3001`, and `8000`, and retain no development-only worktree processes.

## Plan Self-Review

- Every specification section maps to Tasks 1-9: UX, ownership, APIs, idempotency, streaming, limits, errors, cleanup, security, provider staging, tests, and live evidence.
- Type names are consistent across importer, route, app client, and frontend response handling.
- Large `session_upload` artifacts use `file_backed`; no step routes the MP4 through base64.
- Existing app upload analysis remains backward compatible because Composer receives dedicated endpoints.
- Builder and legacy `ragenius_app` remain untouched.
- Every implementation step names its concrete behavior and verification command.
