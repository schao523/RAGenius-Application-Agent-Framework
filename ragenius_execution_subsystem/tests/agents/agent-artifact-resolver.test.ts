import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { afterEach, describe, it } from "node:test";

import { AgentArtifactResolver } from "../../src/core/agents/agent-artifact-resolver.js";
import { ArtifactStore } from "../../src/core/tools/providers/artifact-store.js";

const artifactRoots = new Set<string>();

function createArtifactRoot(): string {
  const root = path.resolve(
    `D:/GitHub/Codex-RAGenius-System/outputs/test-agent-artifact-resolver-${randomUUID()}`
  );
  artifactRoots.add(root);
  return root;
}

async function cleanupArtifactRoot(root: string): Promise<void> {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try {
      await fs.rm(root, { recursive: true, force: true });
      return;
    } catch (error) {
      if (
        !(error && typeof error === "object" && "code" in error) ||
        (error as { code?: string }).code !== "EPERM" ||
        attempt === 4
      ) {
        if (
          error &&
          typeof error === "object" &&
          "code" in error &&
          (error as { code?: string }).code === "EPERM"
        ) {
          return;
        }
        throw error;
      }
      await new Promise((resolve) => setTimeout(resolve, 50 * (attempt + 1)));
    }
  }
}

function hasAppErrorCode(code: string): (error: unknown) => boolean {
  return (error: unknown): boolean => {
    if (!error || typeof error !== "object" || !("code" in error)) {
      return false;
    }
    return (error as { code?: unknown }).code === code;
  };
}

describe("agent artifact resolver", () => {
  afterEach(async () => {
    await Promise.all(
      [...artifactRoots].map(async (root) => {
        await cleanupArtifactRoot(root);
        artifactRoots.delete(root);
      })
    );
  });

  it("resolves session-owned text artifacts for agent input", async () => {
    const store = new ArtifactStore(createArtifactRoot());
    const saved = await store.save(
      "app_alpha",
      "chat_export",
      "notes.md",
      { content: "# Notes" },
      { sessionId: "session_a" }
    );

    const resolver = new AgentArtifactResolver(store);
    const resolved = await resolver.resolve({
      appId: "app_alpha",
      sessionId: "session_a",
      backend: "openclaw_cli",
      refs: [
        {
          artifact_id: String(saved.artifact_id),
          role: "source",
          reuse_mode: "inline_text"
        }
      ]
    });

    assert.equal(resolved.length, 1);
    assert.equal(resolved[0]?.artifact_id, saved.artifact_id);
    assert.equal(resolved[0]?.role, "source");
    assert.equal(resolved[0]?.consumption.resolved_mode, "inline_text");
    assert.equal(resolved[0]?.payload.text_content, "# Notes");
    assert.equal(resolved[0]?.payload.inline_truncated, false);
  });

  it("rejects artifacts from another session", async () => {
    const store = new ArtifactStore(createArtifactRoot());
    const saved = await store.save(
      "app_alpha",
      "chat_export",
      "notes.md",
      { content: "# Notes" },
      { sessionId: "session_a" }
    );

    const resolver = new AgentArtifactResolver(store);
    await assert.rejects(
      resolver.resolve({
        appId: "app_alpha",
        sessionId: "session_b",
        backend: "openclaw_cli",
        refs: [
          {
            artifact_id: String(saved.artifact_id),
            role: "source",
            reuse_mode: "inline_text"
          }
        ]
      }),
      hasAppErrorCode("ARTIFACT_SESSION_MISMATCH")
    );
  });

  it("rejects artifacts from another app", async () => {
    const store = new ArtifactStore(createArtifactRoot());
    const saved = await store.save(
      "app_alpha",
      "chat_export",
      "notes.md",
      { content: "# Notes" },
      { sessionId: "session_a" }
    );

    const resolver = new AgentArtifactResolver(store);
    await assert.rejects(
      resolver.resolve({
        appId: "app_beta",
        sessionId: "session_a",
        backend: "openclaw_cli",
        refs: [
          {
            artifact_id: String(saved.artifact_id),
            role: "source",
            reuse_mode: "inline_text"
          }
        ]
      }),
      hasAppErrorCode("ARTIFACT_NOT_FOUND")
    );
  });

  it("rejects backend-unsupported reuse modes", async () => {
    const store = new ArtifactStore(createArtifactRoot());
    const saved = await store.save(
      "app_alpha",
      "chat_export",
      "notes.md",
      { content: "# Notes" },
      { sessionId: "session_a" }
    );

    const resolver = new AgentArtifactResolver(store);
    await assert.rejects(
      resolver.resolve({
        appId: "app_alpha",
        sessionId: "session_a",
        backend: "codex_cli",
        refs: [
          {
            artifact_id: String(saved.artifact_id),
            role: "attachment",
            reuse_mode: "binary_payload"
          }
        ]
      }),
      hasAppErrorCode("AGENT_ARTIFACT_MODE_UNSUPPORTED")
    );
  });

  it("truncates inline text and marks the payload", async () => {
    const store = new ArtifactStore(createArtifactRoot());
    const saved = await store.save(
      "app_alpha",
      "chat_export",
      "large.md",
      { content: "abcdef" },
      { sessionId: "session_a" }
    );

    const resolver = new AgentArtifactResolver(store, { maxInlineTextBytes: 3 });
    const resolved = await resolver.resolve({
      appId: "app_alpha",
      sessionId: "session_a",
      backend: "openclaw_cli",
      refs: [
        {
          artifact_id: String(saved.artifact_id),
          role: "source",
          reuse_mode: "inline_text"
        }
      ]
    });

    assert.equal(resolved[0]?.payload.text_content, "abc");
    assert.equal(resolved[0]?.payload.inline_truncated, true);
    assert.equal(resolved[0]?.payload.original_inline_bytes, 6);
  });

  it("does not read artifact bytes for metadata-only reuse", async () => {
    const store = new ArtifactStore(createArtifactRoot());
    const saved = await store.save(
      "app_alpha",
      "chat_export",
      "metadata.md",
      { content: "# Metadata only" },
      { sessionId: "session_a" }
    );

    const resolver = new AgentArtifactResolver(store);
    const resolved = await resolver.resolve({
      appId: "app_alpha",
      sessionId: "session_a",
      backend: "openclaw_cli",
      refs: [
        {
          artifact_id: String(saved.artifact_id),
          role: "context",
          reuse_mode: "metadata_only"
        }
      ]
    });

    assert.equal(resolved[0]?.consumption.resolved_mode, "metadata_only");
    assert.equal(resolved[0]?.payload.text_content, undefined);
    assert.equal(resolved[0]?.payload.binary_content_base64, undefined);
    assert.ok(resolved[0]?.payload.metadata);
  });
});
