# Unified Upload And Artifact UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the visible session-upload/preparation split with one idempotent upload flow whose successful result is a session-scoped execution artifact shown once in Artifact Library and selectable from Execution Composer.

**Architecture:** `ragenius_app_skeleton` remains the browser upload boundary and owns transient streamed staging plus optional normal-query analysis. `ragenius_execution_subsystem` remains the canonical artifact byte owner and adds session-local content deduplication, tombstoned deletion, and active-execution protection. Both chat and Composer use one frontend transport and one app endpoint; the app delegates canonical storage operations with its scoped service credential.

**Tech Stack:** Python 3, FastAPI, SQLite, TypeScript, Fastify, Zod, Prisma/PostgreSQL, React, Vitest, Node test runner.

**Global Constraints:** Preserve exact `app_id`/`session_id`/`user_id` scoping; stream rather than buffer large files; never expose staging paths; do not automatically delete legacy uploads; do not change provider workspace staging; keep old endpoints temporarily as compatibility delegates; use stable `upload_operation_id` for every retry.

---

## Reference Documents

- `D:/GitHub/Codex-RAGenius-System/docs/superpowers/specs/2026-08-11-unified-upload-artifact-ux-design.md`
- `D:/GitHub/Codex-RAGenius-System/docs/agent-mode-artifact-creation-reuse-contract.md`
- `D:/GitHub/Codex-RAGenius-System/docs/superpowers/specs/2026-08-10-composer-session-upload-execution-artifact-design.md`

## File Structure

### Execution subsystem

- Modify `ragenius_execution_subsystem/src/core/tools/providers/artifact-store.ts`: add content-identity lookup and tombstoned deletion while keeping stored artifact records provider-neutral.
- Modify `ragenius_execution_subsystem/src/core/artifacts/session-upload-artifact-importer.ts`: make imports idempotent by source operation and session-local content identity.
- Modify `ragenius_execution_subsystem/src/core/execution/execution-store.ts`: expose an active artifact-reference query.
- Modify `ragenius_execution_subsystem/src/core/execution/prisma-execution-store.ts`: query queued/running request payloads for an exact scoped artifact reference.
- Modify `ragenius_execution_subsystem/src/api/routes/artifacts.routes.ts`: enforce active-use protection and return idempotent tombstoned deletion results.
- Modify `ragenius_execution_subsystem/src/api/routes/artifact-imports.routes.ts`: return `reused_existing_artifact` and canonical metadata.
- Modify `ragenius_execution_subsystem/prisma/schema.prisma`: add only indexes required by the active-reference implementation; do not create a second artifact ownership model.
- Modify dedicated tests under `ragenius_execution_subsystem/tests/artifacts` and `ragenius_execution_subsystem/tests/api`.

### App backend

- Create `ragenius_app_skeleton/backend/app/artifact_upload_service.py`: orchestrate stream staging, import, retry, optional analysis, cleanup, and normalized responses.
- Modify `ragenius_app_skeleton/backend/app/chat_repos.py`: persist operation identity and lifecycle state; add exact-scope lookup, retry, deletion, and expiry operations.
- Modify `ragenius_app_skeleton/backend/app/execution_subsystem_client.py`: expose canonical import/delete calls and preserve safe error codes.
- Modify `ragenius_app_skeleton/backend/app/execution_input_service.py`: delegate legacy preparation to the unified upload service.
- Modify `ragenius_app_skeleton/backend/app/main.py`: add unified upload/retry/delete routes and retain legacy route delegates.
- Add or modify focused tests under `ragenius_app_skeleton/backend/tests`.

### App frontend

- Create `ragenius_app_skeleton/frontend/src/artifactUploadClient.js`: one upload/retry client with progress events and safe error normalization.
- Create `ragenius_app_skeleton/frontend/src/components/ArtifactUploadControl.jsx`: shared chat/Composer upload UI.
- Create `ragenius_app_skeleton/frontend/src/components/ArtifactUploadControl.test.jsx`.
- Modify `ragenius_app_skeleton/frontend/src/App.jsx`: use canonical artifact inventory and remove visible session-upload inventory.
- Modify `ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx`: select ready artifacts and remove preparation controls.
- Modify `ArtifactLibrary`, Composer, and app integration tests.

## Milestone 1: Canonical Artifact Lifecycle

### Task 1: Add session-local content identity and tombstones

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/tools/providers/artifact-store.ts`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/artifacts/artifact-store.test.ts`

- [ ] **Step 1: Write failing content-reuse and tombstone tests**

Cover same `{app_id, session_id, sha256, size_bytes, normalized MIME}` returning one ready record, different sessions returning different records, deleted records being excluded from list/resolve/reuse, and repeated scoped deletion succeeding without leaking another scope.

Use this provider-neutral API shape:

```ts
export interface ArtifactContentIdentity {
  appId: string;
  sessionId: string;
  sha256: string;
  sizeBytes: number;
  mediaType: string;
}

findReadyByContentIdentity(
  identity: ArtifactContentIdentity
): Promise<StoredArtifactRecord | null>;

markDeletedScoped(input: {
  appId: string;
  sessionId: string;
  artifactId: string;
}): Promise<{ deleted: boolean }>;
```

- [ ] **Step 2: Run the focused test and confirm RED**

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm run build
node --experimental-test-isolation=none --test dist/tests/artifacts/artifact-store.test.js
```

- [ ] **Step 3: Implement content lookup and tombstoned deletion**

Normalize MIME with trim/lowercase. Persist `status: "deleted"` and `deleted_at`; remove canonical bytes only after the metadata tombstone is durable. Ensure ordinary `list`, `resolve`, preview, and download paths require `status === "ready"`.

- [ ] **Step 4: Re-run the focused test and confirm GREEN**

- [ ] **Step 5: Commit**

```powershell
git add ragenius_execution_subsystem/src/core/tools/providers/artifact-store.ts ragenius_execution_subsystem/tests/artifacts/artifact-store.test.ts
git commit -m "feat(execution): add artifact content identity and tombstones"
```

### Task 2: Make session-upload import content-idempotent

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/artifacts/session-upload-artifact-importer.ts`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/api/routes/artifact-imports.routes.ts`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/artifacts/session-upload-artifact-importer.test.ts`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/api/artifact-import-routes.test.ts`

- [ ] **Step 1: Add failing tests for operation and content retries**

Assert that five retries of one source operation produce one artifact; a second operation with identical scoped content reuses it; a hash match with different size/MIME does not; another session never reuses it. Require this safe response field:

```ts
interface SessionUploadImportResult {
  artifact: StoredArtifactRecord;
  reused_existing_artifact: boolean;
}
```

- [ ] **Step 2: Run focused importer/API tests and confirm RED**

```powershell
npm run build
node --experimental-test-isolation=none --test dist/tests/artifacts/session-upload-artifact-importer.test.js dist/tests/api/artifact-import-routes.test.js
```

- [ ] **Step 3: Implement ordered idempotency**

Resolve by `source_upload_id` first, then by verified content identity, then store new bytes. Do not trust a client hash without recomputing/validating streamed bytes. Add alternate display names only as bounded aliases; do not create another visible record.

- [ ] **Step 4: Re-run tests and commit**

```powershell
git add ragenius_execution_subsystem/src/core/artifacts/session-upload-artifact-importer.ts ragenius_execution_subsystem/src/api/routes/artifact-imports.routes.ts ragenius_execution_subsystem/tests/artifacts/session-upload-artifact-importer.test.ts ragenius_execution_subsystem/tests/api/artifact-import-routes.test.ts
git commit -m "feat(execution): deduplicate scoped upload artifacts"
```

### Task 3: Block deletion while an execution actively references an artifact

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/execution/execution-store.ts`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/core/execution/prisma-execution-store.ts`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/src/api/routes/artifacts.routes.ts`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/api/artifact-file-routes.test.ts`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/tests/execution/prisma-execution-store.test.ts`

- [ ] **Step 1: Add failing store and route tests**

Add this exact interface:

```ts
hasActiveArtifactReference(input: {
  appId: string;
  sessionId: string;
  artifactId: string;
}): Promise<boolean>;
```

Queued/running (including awaiting confirmation if represented as queued) requests whose persisted `requestPayload.artifact_refs` contain the id must block. Completed/failed/cancelled requests must not block. The route returns HTTP 409 with stable code `ARTIFACT_IN_USE`.

- [ ] **Step 2: Run focused tests and confirm RED**

```powershell
npm run build
node --experimental-test-isolation=none --test dist/tests/execution/prisma-execution-store.test.js dist/tests/api/artifact-file-routes.test.js
```

- [ ] **Step 3: Implement exact-scope lookup and route guard**

Use the existing `Execution.requestPayload` rather than duplicating references in a new table for MVP. Fetch only active rows for the exact app/session, parse through the existing execution request schema, and compare exact artifact ids. Keep the in-memory implementation behaviorally equivalent.

- [ ] **Step 4: Re-run tests and commit**

```powershell
git add ragenius_execution_subsystem/src/core/execution ragenius_execution_subsystem/src/api/routes/artifacts.routes.ts ragenius_execution_subsystem/tests/api/artifact-file-routes.test.ts ragenius_execution_subsystem/tests/execution/prisma-execution-store.test.ts
git commit -m "feat(execution): protect active artifact references"
```

## Milestone 2: Unified App Upload State Machine

### Task 4: Persist stable upload operations and retry state

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/chat_repos.py`
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/tests/test_artifact_upload_repository.py`

- [ ] **Step 1: Add failing repository migration/lifecycle tests**

Extend the existing uploads table additively with nullable migration columns:

```text
upload_operation_id, app_id, user_id, status, artifact_id,
content_sha256, size_bytes, normalized_mime_type,
error_code, retryable, staging_expires_at, deleted_at
```

Enforce a unique index on `(app_id, session_id, upload_operation_id)` when the operation id is non-null. Test create/get/update, same-operation idempotency, exact-scope rejection, ready mapping, failed retry, expiry, and immediate failed-staging deletion.

- [ ] **Step 2: Run the test and confirm RED**

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton
python -m pytest backend/tests/test_artifact_upload_repository.py -q
```

- [ ] **Step 3: Implement additive SQLite migration and repository methods**

Add typed dictionary-returning methods named `get_upload_operation`, `create_upload_operation`, `update_upload_operation`, `delete_upload_operation`, and `list_expired_upload_operations`. Preserve legacy rows with null operation ids and existing file paths.

- [ ] **Step 4: Re-run and commit**

```powershell
git add ragenius_app_skeleton/backend/app/chat_repos.py ragenius_app_skeleton/backend/tests/test_artifact_upload_repository.py
git commit -m "feat(app): persist unified artifact upload operations"
```

### Task 5: Implement upload orchestration, retry, and cleanup

**Files:**
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/artifact_upload_service.py`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/execution_subsystem_client.py`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/execution_input_service.py`
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/tests/test_artifact_upload_service.py`

- [ ] **Step 1: Add failing service tests**

Cover streaming hash/size, safe basename handling, successful import, import failure preserving retryable staging, retry without receiving browser bytes again, content reuse response, optional analysis callback, staging cleanup only after import plus analysis, and 24-hour expiry.

Implement around these values:

```python
@dataclass(frozen=True)
class ArtifactUploadResult:
    upload_operation_id: str
    status: Literal["ready", "failed"]
    artifact: dict | None
    reused_existing_artifact: bool
    error_code: str | None
    retryable: bool
```

- [ ] **Step 2: Run the test and confirm RED**

```powershell
python -m pytest backend/tests/test_artifact_upload_service.py -q
```

- [ ] **Step 3: Implement the service**

Stream in bounded chunks to an opaque app-owned path, calculate SHA-256 concurrently, call the execution import client with the existing `artifacts:write` credential, and normalize transport/provider failures to bounded codes. `retry()` must begin from the stored failed phase. Add `cleanup_expired_staging(now)` for startup and a bounded periodic invocation; do not delete legacy rows.

- [ ] **Step 4: Re-run and commit**

```powershell
git add ragenius_app_skeleton/backend/app/artifact_upload_service.py ragenius_app_skeleton/backend/app/execution_subsystem_client.py ragenius_app_skeleton/backend/app/execution_input_service.py ragenius_app_skeleton/backend/tests/test_artifact_upload_service.py
git commit -m "feat(app): orchestrate canonical artifact uploads"
```

### Task 6: Add unified routes and compatibility delegates

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/main.py`
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/tests/test_artifact_upload_routes.py`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/tests/test_execution_input_uploads.py`

- [ ] **Step 1: Add failing route tests for the approved API**

Test `POST /sessions/{session_id}/artifacts/uploads`, retry, and delete with exact app/user/session scope. Assert `analysis_mode` accepts only `none|normal_query`, duplicate operation ids are idempotent, active-use deletion maps to 409, already-deleted maps to success, and responses contain no private path.

- [ ] **Step 2: Run tests and confirm RED**

```powershell
python -m pytest backend/tests/test_artifact_upload_routes.py backend/tests/test_execution_input_uploads.py -q
```

- [ ] **Step 3: Implement routes and legacy delegates**

Make current `/sessions/{id}/uploads`, `/execution-inputs`, and `/uploads/{upload_id}/prepare-for-execution` delegate to the service where their contracts permit. Keep old response shapes for existing callers during this milestone. Normal query passes its existing extraction/analysis operation; Composer uses `analysis_mode=none`.

- [ ] **Step 4: Re-run tests and commit**

```powershell
git add ragenius_app_skeleton/backend/app/main.py ragenius_app_skeleton/backend/tests/test_artifact_upload_routes.py ragenius_app_skeleton/backend/tests/test_execution_input_uploads.py
git commit -m "feat(app): expose unified artifact upload API"
```

## Milestone 3: One Frontend Artifact Experience

### Task 7: Build the shared upload transport and control

**Files:**
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/artifactUploadClient.js`
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/artifactUploadClient.test.js`
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ArtifactUploadControl.jsx`
- Create: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ArtifactUploadControl.test.jsx`

- [ ] **Step 1: Add failing client/component tests**

Test stable operation id generation, XHR byte progress, uploading/preparing/ready/failed phases, same-operation retry, cancellation before staging completes, safe error messages, and no raw JSON rendering.

Use this client boundary:

```js
uploadArtifact({ baseUrl, sessionId, appId, userId, file,
  operationId, analysisMode, onProgress, signal })
retryArtifactUpload({ baseUrl, sessionId, appId, userId, operationId })
```

- [ ] **Step 2: Run tests and confirm RED**

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend
npm test -- artifactUploadClient.test.js ArtifactUploadControl.test.jsx
```

- [ ] **Step 3: Implement transport and accessible stacked UI**

Use `XMLHttpRequest.upload.onprogress` because Fetch does not expose upload byte progress. Generate one `crypto.randomUUID()` operation id per selected file and retain it across retry. Render filename, MIME, formatted size, current phase, Retry/Delete/Cancel actions, and an `aria-live` status.

- [ ] **Step 4: Re-run and commit**

```powershell
git add ragenius_app_skeleton/frontend/src/artifactUploadClient.js ragenius_app_skeleton/frontend/src/artifactUploadClient.test.js ragenius_app_skeleton/frontend/src/components/ArtifactUploadControl.jsx ragenius_app_skeleton/frontend/src/components/ArtifactUploadControl.test.jsx
git commit -m "feat(frontend): add shared artifact upload control"
```

### Task 8: Replace normal-chat session uploads with canonical artifacts

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/App.jsx`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/App.test.jsx`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ArtifactLibrary.jsx`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ArtifactLibrary.test.jsx`

- [ ] **Step 1: Add failing integration tests**

Assert normal chat uses `ArtifactUploadControl` with `analysisMode="normal_query"`, successful upload refreshes Artifact Library once, the old Session files/chips are absent, delete confirms then removes the row, failed state stays locally retryable, and an in-use 409 is explained without removing the artifact.

- [ ] **Step 2: Run tests and confirm RED**

```powershell
npm test -- App.test.jsx ArtifactLibrary.test.jsx
```

- [ ] **Step 3: Implement canonical inventory updates**

Replace `sessionUploadsBySession` as a visible inventory with artifact-list refresh/update. Keep only private legacy state needed for compatibility. After ready, merge by `artifact_id`; after deletion, unselect it everywhere and refresh. Do not show artifact ids or paths outside inspector details.

- [ ] **Step 4: Re-run and commit**

```powershell
git add ragenius_app_skeleton/frontend/src/App.jsx ragenius_app_skeleton/frontend/src/App.test.jsx ragenius_app_skeleton/frontend/src/components/ArtifactLibrary.jsx ragenius_app_skeleton/frontend/src/components/ArtifactLibrary.test.jsx
git commit -m "feat(frontend): unify chat uploads with Artifact Library"
```

### Task 9: Simplify Composer to upload/select/unselect artifacts

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/components/ExecutionComposer.test.jsx`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/App.jsx`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/frontend/src/App.test.jsx`

- [ ] **Step 1: Add failing Composer tests**

Assert Composer contains `Upload artifact`, ready Artifact Library choices, and `Unselect`; it must not contain `Select session file`, `Prepare selected file`, `Remove ... preparation`, duplicate upload chips, or failed preparation closures that resend bytes.

- [ ] **Step 2: Run tests and confirm RED**

```powershell
npm test -- ExecutionComposer.test.jsx App.test.jsx
```

- [ ] **Step 3: Integrate the shared control**

Composer uses `analysisMode="none"`. A ready upload is selected by canonical `artifact_id`; failed upload retry reuses its operation id. Deletion remains an explicit confirmed Artifact Library action and automatically unselects deleted refs.

- [ ] **Step 4: Re-run and commit**

```powershell
git add ragenius_app_skeleton/frontend/src/components/ExecutionComposer.jsx ragenius_app_skeleton/frontend/src/components/ExecutionComposer.test.jsx ragenius_app_skeleton/frontend/src/App.jsx ragenius_app_skeleton/frontend/src/App.test.jsx
git commit -m "feat(frontend): simplify Composer artifact inputs"
```

## Milestone 4: Compatibility, Documentation, And Verification

### Task 10: Add lazy legacy import and update governing documentation

**Files:**
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/app/artifact_upload_service.py`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_app_skeleton/backend/tests/test_artifact_upload_service.py`
- Modify: `D:/GitHub/Codex-RAGenius-System/docs/agent-mode-artifact-creation-reuse-contract.md`
- Modify: `D:/GitHub/Codex-RAGenius-System/docs/agent-mode-artifact-creation-reuse-design.md`
- Modify: `D:/GitHub/Codex-RAGenius-System/ragenius_execution_subsystem/docs/service-authentication-guide.md`

- [ ] **Step 1: Add failing legacy compatibility tests**

Test first access hashes/imports a legacy upload, same-session duplicates resolve to one canonical artifact, old bytes are not automatically removed, and a missing legacy file yields a bounded non-retryable result.

- [ ] **Step 2: Implement lazy compatibility and retention reporting**

Add a read-only duplicate report returning groups, canonical mappings, and byte totals. Do not add automatic cleanup. Document `artifacts:write`, tombstone behavior, active-use deletion, operation idempotency, and the superseded two-tier UX.

- [ ] **Step 3: Run complete verification**

```powershell
cd D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem
npm test
npm run build

cd D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton
python -m pytest backend/tests -q

cd D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend
npm test
npm run build
```

- [ ] **Step 4: Run manual acceptance smoke**

Upload one small text file and one video from normal chat and Composer. Verify one Library row per content identity, retry after a simulated execution-service outage, Composer selection, active-execution delete rejection, post-completion deletion, and retained inspector evidence.

- [ ] **Step 5: Commit documentation and compatibility work**

```powershell
git add docs/agent-mode-artifact-creation-reuse-contract.md docs/agent-mode-artifact-creation-reuse-design.md ragenius_execution_subsystem/docs/service-authentication-guide.md ragenius_app_skeleton/backend/app/artifact_upload_service.py ragenius_app_skeleton/backend/tests/test_artifact_upload_service.py
git commit -m "docs: align artifact contracts with unified uploads"
```

### Task 11: Request review and integrate

- [ ] **Step 1: Invoke `superpowers:requesting-code-review`**
- [ ] **Step 2: Address only verified findings and re-run affected suites**
- [ ] **Step 3: Invoke `superpowers:verification-before-completion`**
- [ ] **Step 4: Invoke `superpowers:finishing-a-development-branch` and integrate the feature branch after the user-approved strategy**

## Completion Criteria

- Chat and Composer share one upload endpoint and one control.
- Successful uploads exist only as canonical execution artifacts in user-visible inventory.
- Retries and same-session identical bytes cannot create duplicate artifacts.
- Deleted artifacts are tombstoned, unavailable for reuse, and retained as completed-execution evidence.
- Active execution references block deletion with `ARTIFACT_IN_USE`.
- Legacy uploads remain recoverable without destructive migration.
- Backend, frontend, execution tests, builds, and manual smoke all pass.
