import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { afterEach, describe, it } from "node:test";

import { ArtifactStore } from "../../src/core/tools/providers/artifact-store.js";

const roots = new Set<string>();

function createStore(): { root: string; store: ArtifactStore } {
  const root = path.resolve(".test_tmp", `artifact-store-${randomUUID()}`);
  roots.add(root);
  return { root, store: new ArtifactStore(root) };
}

async function saveUpload(
  store: ArtifactStore,
  overrides: Partial<{
    sessionId: string;
    contentHash: string;
    mimeType: string;
    fileTextContent: string;
  }> = {}
) {
  return store.save("app_1", "session_upload", "notes.txt", {}, {
    sessionId: overrides.sessionId ?? "session_1",
    contentHash: overrides.contentHash ?? `sha256:${"a".repeat(64)}`,
    mimeType: overrides.mimeType ?? "text/plain",
    fileTextContent: overrides.fileTextContent ?? "hello"
  });
}

describe("artifact store lifecycle", () => {
  afterEach(async () => {
    await Promise.all([...roots].map(async (root) => {
      await fs.rm(root, { recursive: true, force: true });
      roots.delete(root);
    }));
  });

  it("finds ready content only inside the exact app and session identity", async () => {
    const { store } = createStore();
    const saved = await saveUpload(store);
    await saveUpload(store, { sessionId: "session_2" });

    const match = await store.findReadyByContentIdentity({
      appId: "app_1",
      sessionId: "session_1",
      sha256: `sha256:${"a".repeat(64)}`,
      sizeBytes: 5,
      mediaType: " TEXT/PLAIN; charset=utf-8 "
    });
    const wrongSession = await store.findReadyByContentIdentity({
      appId: "app_1",
      sessionId: "session_3",
      sha256: `sha256:${"a".repeat(64)}`,
      sizeBytes: 5,
      mediaType: "text/plain"
    });

    assert.equal(match?.artifact_id, saved.artifact_id);
    assert.equal(wrongSession, undefined);
  });

  it("requires matching hash, size, and normalized media type", async () => {
    const { store } = createStore();
    await saveUpload(store);

    for (const identity of [
      { sha256: `sha256:${"b".repeat(64)}`, sizeBytes: 5, mediaType: "text/plain" },
      { sha256: `sha256:${"a".repeat(64)}`, sizeBytes: 6, mediaType: "text/plain" },
      { sha256: `sha256:${"a".repeat(64)}`, sizeBytes: 5, mediaType: "video/mp4" }
    ]) {
      assert.equal(await store.findReadyByContentIdentity({
        appId: "app_1",
        sessionId: "session_1",
        ...identity
      }), undefined);
    }
  });

  it("tombstones metadata, removes bytes, and excludes deleted records", async () => {
    const { store } = createStore();
    const saved = await saveUpload(store);

    const result = await store.markDeletedScoped({
      appId: "app_1",
      sessionId: "session_1",
      artifactId: String(saved.artifact_id)
    });

    assert.deepEqual(result, { deleted: true });
    assert.equal(await fs.stat(String(saved.file_path)).catch(() => null), null);
    assert.equal((await fs.stat(String(saved.path))).isFile(), true);
    assert.equal((await store.list("app_1", { sessionId: "session_1" })).length, 0);
    assert.equal(await store.findReadyByContentIdentity({
      appId: "app_1",
      sessionId: "session_1",
      sha256: `sha256:${"a".repeat(64)}`,
      sizeBytes: 5,
      mediaType: "text/plain"
    }), undefined);
    await assert.rejects(
      store.resolveScopedFile({
        appId: "app_1",
        sessionId: "session_1",
        artifactId: String(saved.artifact_id)
      }),
      /not found/i
    );
  });

  it("makes same-scope deletion idempotent without accepting another session", async () => {
    const { store } = createStore();
    const saved = await saveUpload(store);

    await assert.rejects(
      store.markDeletedScoped({
        appId: "app_1",
        sessionId: "session_2",
        artifactId: String(saved.artifact_id)
      }),
      /not found/i
    );
    assert.deepEqual(await store.markDeletedScoped({
      appId: "app_1",
      sessionId: "session_1",
      artifactId: String(saved.artifact_id)
    }), { deleted: true });
    assert.deepEqual(await store.markDeletedScoped({
      appId: "app_1",
      sessionId: "session_1",
      artifactId: String(saved.artifact_id)
    }), { deleted: false });
  });
});
