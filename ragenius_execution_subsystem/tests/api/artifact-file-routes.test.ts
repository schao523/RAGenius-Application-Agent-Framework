import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { buildApp } from "../../src/app.js";
import { ArtifactStore } from "../../src/core/tools/providers/artifact-store.js";

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
