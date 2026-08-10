import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { Readable } from "node:stream";
import { afterEach, describe, it } from "node:test";

import { SessionUploadArtifactImporter } from "../../src/core/artifacts/session-upload-artifact-importer.js";
import { AppError } from "../../src/core/errors/app-error.js";
import { ArtifactStore } from "../../src/core/tools/providers/artifact-store.js";

const roots = new Set<string>();

function createRoot(): string {
  const root = path.resolve(".test_tmp", `session-upload-import-${randomUUID()}`);
  roots.add(root);
  return root;
}

function digest(value: string): string {
  return `sha256:${createHash("sha256").update(value).digest("hex")}`;
}

function createImporter(root: string, overrides: Partial<{
  maxBytes: number;
  allowedMimeTypes: string[];
  tempRetentionHours: number;
}> = {}): SessionUploadArtifactImporter {
  return new SessionUploadArtifactImporter(new ArtifactStore(root), {
    artifactRootDir: root,
    maxBytes: overrides.maxBytes ?? 1024,
    allowedMimeTypes: overrides.allowedMimeTypes ?? ["video/mp4", "text/plain"],
    tempRetentionHours: overrides.tempRetentionHours ?? 24
  });
}

function input(overrides: Partial<Parameters<SessionUploadArtifactImporter["import"]>[0]> = {}) {
  const value = "video-bytes";
  return {
    appId: "app_1",
    sessionId: "session_1",
    sourceUploadId: "upload_1",
    displayName: "video.mp4",
    mimeType: "video/mp4",
    declaredSizeBytes: Buffer.byteLength(value),
    declaredSha256: digest(value),
    stream: Readable.from([Buffer.from("video-"), Buffer.from("bytes")]),
    ...overrides
  };
}

async function expectCode(operation: Promise<unknown>, code: string): Promise<void> {
  await assert.rejects(operation, (error: unknown) => {
    assert.ok(error instanceof AppError);
    assert.equal(error.code, code);
    return true;
  });
}

describe("session upload artifact importer", () => {
  afterEach(async () => {
    await Promise.all([...roots].map(async (root) => {
      await fs.rm(root, { recursive: true, force: true });
      roots.delete(root);
    }));
  });

  it("streams a verified video into a ready session_upload artifact", async () => {
    const root = createRoot();
    const result = await createImporter(root).import(input());

    assert.equal(result.reusedExistingArtifact, false);
    assert.equal(result.artifact.artifact_type, "session_upload");
    assert.equal(result.artifact.provider_origin, "session_upload");
    assert.equal(result.artifact.source_upload_id, "upload_1");
    assert.equal(result.artifact.content_hash, digest("video-bytes"));
    assert.equal(result.artifact.size_bytes, 11);
    assert.equal(await fs.readFile(String(result.artifact.file_path), "utf-8"), "video-bytes");
  });

  it("returns the same artifact for an exact idempotent retry", async () => {
    const importer = createImporter(createRoot());
    const first = await importer.import(input());
    const second = await importer.import(input());

    assert.equal(second.reusedExistingArtifact, true);
    assert.equal(second.artifact.artifact_id, first.artifact.artifact_id);
  });

  it("rejects reuse of a source upload id with different content", async () => {
    const importer = createImporter(createRoot());
    await importer.import(input());

    await expectCode(importer.import(input({
      declaredSizeBytes: 5,
      declaredSha256: digest("other"),
      stream: Readable.from([Buffer.from("other")])
    })), "SESSION_UPLOAD_CONTENT_CONFLICT");
  });

  it("rejects declared size and hash mismatches", async () => {
    const importer = createImporter(createRoot());
    await expectCode(
      importer.import(input({ declaredSizeBytes: 12 })),
      "EXECUTION_INPUT_INTEGRITY_MISMATCH"
    );
    await expectCode(
      importer.import(input({ sourceUploadId: "upload_2", declaredSha256: digest("wrong") })),
      "EXECUTION_INPUT_INTEGRITY_MISMATCH"
    );
  });

  it("rejects inputs above the configured maximum", async () => {
    const importer = createImporter(createRoot(), { maxBytes: 10 });
    await expectCode(importer.import(input()), "EXECUTION_INPUT_TOO_LARGE");
  });

  it("rejects media types outside the allowlist", async () => {
    const importer = createImporter(createRoot());
    await expectCode(
      importer.import(input({ mimeType: "application/x-msdownload" })),
      "EXECUTION_INPUT_MEDIA_TYPE_NOT_ALLOWED"
    );
  });

  it("serializes concurrent identical imports to one artifact", async () => {
    const importer = createImporter(createRoot());
    const [first, second] = await Promise.all([
      importer.import(input()),
      importer.import(input())
    ]);

    assert.equal(first.artifact.artifact_id, second.artifact.artifact_id);
    assert.equal([first.reusedExistingArtifact, second.reusedExistingArtifact].filter(Boolean).length, 1);
  });

  it("removes expired temporary files and preserves recent ones", async () => {
    const root = createRoot();
    const tempRoot = path.join(root, ".session-upload-imports");
    await fs.mkdir(tempRoot, { recursive: true });
    const expired = path.join(tempRoot, "expired.tmp");
    const recent = path.join(tempRoot, "recent.tmp");
    await fs.writeFile(expired, "old");
    await fs.writeFile(recent, "new");
    const old = new Date(Date.now() - 2 * 60 * 60 * 1000);
    await fs.utimes(expired, old, old);

    await createImporter(root, { tempRetentionHours: 1 }).cleanupExpiredTemporaryFiles();

    await assert.rejects(fs.stat(expired), { code: "ENOENT" });
    assert.equal((await fs.stat(recent)).isFile(), true);
  });
});
