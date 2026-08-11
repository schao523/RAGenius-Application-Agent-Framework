import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { buildApp } from "../../src/app.js";
import { ArtifactStore } from "../../src/core/tools/providers/artifact-store.js";
import { InMemoryExecutionStore } from "../../src/core/execution/execution-store.js";
import { ArtifactReferenceCoordinator } from "../../src/core/artifacts/artifact-reference-coordinator.js";

test("blocks deletion while a synchronous provider holds an artifact lease", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "ragenius-artifacts-"));
  const store = new ArtifactStore(root);
  const coordinator = new ArtifactReferenceCoordinator();
  const saved = await store.save("app_001", "session_upload", "source.txt", {}, {
    sessionId: "session_001",
    mimeType: "text/plain",
    fileTextContent: "source"
  });
  const artifactScope = {
    appId: "app_001",
    sessionId: "session_001",
    artifactId: String(saved.artifact_id)
  };
  const release = coordinator.acquire([artifactScope]);
  const app = buildApp({ artifactStore: store, artifactReferenceCoordinator: coordinator });

  const response = await app.inject({
    method: "DELETE",
    url: `/v1/artifacts/${saved.artifact_id}?app_id=app_001&session_id=session_001`
  });

  assert.equal(response.statusCode, 409);
  assert.equal(response.json().error.code, "ARTIFACT_IN_USE");
  assert.equal((await fs.stat(String(saved.file_path))).isFile(), true);
  release();
  await app.close();
});

test("blocks deletion while an active execution references the artifact", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "ragenius-artifacts-"));
  const store = new ArtifactStore(root);
  const executionStore = new InMemoryExecutionStore();
  const saved = await store.save("app_001", "session_upload", "source.txt", {}, {
    sessionId: "session_001",
    mimeType: "text/plain",
    fileTextContent: "source"
  });
  await executionStore.save({
    executionId: "execution_001",
    request: {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "session_001",
      agent_backend: "codex_cli",
      agent_query: "Use the source.",
      artifact_refs: [{
        artifact_id: String(saved.artifact_id),
        role: "source",
        reuse_mode: "file_backed"
      }]
    },
    result: {
      execution_id: "execution_001",
      status: "pending_confirmation",
      result_type: "json",
      result: {},
      files: [],
      errors: [],
      logs_summary: "Awaiting confirmation."
    }
  });
  const app = buildApp({ artifactStore: store, executionStore });

  const response = await app.inject({
    method: "DELETE",
    url: `/v1/artifacts/${saved.artifact_id}?app_id=app_001&session_id=session_001`
  });

  assert.equal(response.statusCode, 409);
  assert.equal(response.json().error.code, "ARTIFACT_IN_USE");
  assert.equal((await fs.stat(String(saved.file_path))).isFile(), true);
  await app.close();
});

test("serves and deletes only session-scoped contained artifact bytes", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "ragenius-artifacts-"));
  const store = new ArtifactStore(root);
  const saved = await store.save("app_001", "agent_output", "report.md", {}, {
    sessionId: "session_001",
    displayName: "report.md",
    mimeType: "text/markdown",
    fileTextContent: "trusted report"
  });
  const app = buildApp({ artifactStore: store });

  const preview = await app.inject({
    method: "GET",
    url: `/v1/artifacts/${saved.artifact_id}/preview?app_id=app_001&session_id=session_001`
  });
  assert.equal(preview.statusCode, 200);
  assert.equal(preview.body, "trusted report");
  assert.match(String(preview.headers["content-disposition"]), /^inline/);

  const wrongSession = await app.inject({
    method: "GET",
    url: `/v1/artifacts/${saved.artifact_id}/download?app_id=app_001&session_id=session_002`
  });
  assert.equal(wrongSession.statusCode, 404);

  const deleted = await app.inject({
    method: "DELETE",
    url: `/v1/artifacts/${saved.artifact_id}?app_id=app_001&session_id=session_001`
  });
  assert.equal(deleted.statusCode, 200);
  assert.equal((await fs.stat(String(saved.file_path)).catch(() => null)), null);
  const tombstone = JSON.parse(await fs.readFile(String(saved.path), "utf-8"));
  assert.equal(tombstone.status, "deleted");
  assert.equal(typeof tombstone.deleted_at, "string");
  assert.equal(tombstone.file_path, undefined);
  const deletedPreview = await app.inject({
    method: "GET",
    url: `/v1/artifacts/${saved.artifact_id}/preview?app_id=app_001&session_id=session_001`
  });
  assert.equal(deletedPreview.statusCode, 404);
  await app.close();
});

test("serves artifact downloads with Unicode display names", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "ragenius-artifacts-"));
  const store = new ArtifactStore(root);
  const saved = await store.save("app_001", "chat_export", "export.md", {}, {
    sessionId: "session_001",
    displayName: "Chat Export - 查考經文.md",
    mimeType: "text/markdown",
    fileTextContent: "trusted Unicode export"
  });
  const app = buildApp({ artifactStore: store });

  const response = await app.inject({
    method: "GET",
    url: `/v1/artifacts/${saved.artifact_id}/download?app_id=app_001&session_id=session_001`
  });

  assert.equal(response.statusCode, 200);
  assert.equal(response.body, "trusted Unicode export");
  const disposition = String(response.headers["content-disposition"]);
  assert.match(disposition, /^attachment; filename="[\x20-\x7e]+";/);
  assert.match(
    disposition,
    /filename\*=UTF-8''Chat%20Export%20-%20%E6%9F%A5%E8%80%83%E7%B6%93%E6%96%87\.md/
  );
  await app.close();
});

test("rejects artifact metadata that points outside the storage root", async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "ragenius-artifacts-"));
  const outside = path.join(await fs.mkdtemp(path.join(os.tmpdir(), "ragenius-outside-")), "secret.txt");
  await fs.writeFile(outside, "secret", "utf8");
  const store = new ArtifactStore(root);
  const saved = await store.save("app_001", "agent_output", "report.md", {}, {
    sessionId: "session_001",
    fileTextContent: "inside"
  });
  const metadata = JSON.parse(await fs.readFile(String(saved.path), "utf8"));
  metadata.file_path = outside;
  await fs.writeFile(String(saved.path), JSON.stringify(metadata), "utf8");
  const app = buildApp({ artifactStore: store });

  const response = await app.inject({
    method: "GET",
    url: `/v1/artifacts/${saved.artifact_id}/download?app_id=app_001&session_id=session_001`
  });
  assert.equal(response.statusCode, 404);
  assert.equal(await fs.readFile(outside, "utf8"), "secret");
  await app.close();
});

test("rejects a contained symlink whose target escapes the storage root", async (t) => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "ragenius-artifacts-"));
  const outside = path.join(await fs.mkdtemp(path.join(os.tmpdir(), "ragenius-outside-")), "secret.txt");
  await fs.writeFile(outside, "secret", "utf8");
  const store = new ArtifactStore(root);
  const saved = await store.save("app_001", "agent_output", "report.md", {}, {
    sessionId: "session_001",
    fileTextContent: "inside"
  });
  try {
    await fs.unlink(String(saved.file_path));
    await fs.symlink(outside, String(saved.file_path), "file");
  } catch (error) {
    t.skip(`Symlink creation is unavailable: ${String(error)}`);
    return;
  }
  const app = buildApp({ artifactStore: store });
  const response = await app.inject({
    method: "GET",
    url: `/v1/artifacts/${saved.artifact_id}/preview?app_id=app_001&session_id=session_001`
  });
  assert.equal(response.statusCode, 404);
  await app.close();
});
