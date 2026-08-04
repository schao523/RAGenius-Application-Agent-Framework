import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { afterEach, describe, it } from "node:test";

import { ArtifactStore } from "../../src/core/tools/providers/artifact-store.js";
import { ArtifactResolver } from "../../src/core/artifacts/artifact-resolver.js";

const artifactRoots = new Set<string>();

function createArtifactRoot(): string {
  const root = path.resolve(
    `D:/GitHub/Codex-RAGenius-System/outputs/test-artifact-resolver-${randomUUID()}`
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

describe("artifact resolver", () => {
  afterEach(async () => {
    await Promise.all(
      [...artifactRoots].map(async (root) => {
        await cleanupArtifactRoot(root);
        artifactRoots.delete(root);
      })
    );
  });

  it("resolves google_drive_export to binary payload by default", async () => {
    const store = new ArtifactStore(createArtifactRoot());
    const saved = await store.save(
      "app_alpha",
      "google_drive_export",
      "Quarterly Plan.pdf",
      {
        name: "Quarterly Plan.pdf",
        mime_type: "application/pdf",
        content: "cGRmLWNvbnRlbnQ=",
        content_encoding: "base64"
      }
    );

    const resolver = new ArtifactResolver(store);
    const artifactId = String(saved.artifact_id);
    const resolved = await resolver.resolve("app_alpha", artifactId);

    assert.equal(resolved.consumption.default_mode, "binary_payload");
    assert.equal(resolved.consumption.resolved_mode, "binary_payload");
    assert.equal(resolved.payload.binary_content_base64, "cGRmLWNvbnRlbnQ=");
    assert.equal(resolved.payload.mime_type, "application/pdf");
    assert.equal(
      (resolved.payload.metadata as { name?: unknown }).name,
      "Quarterly Plan.pdf"
    );
  });

  it("resolves chat_export to file-backed and inline text modes", async () => {
    const store = new ArtifactStore(createArtifactRoot());
    const saved = await store.save(
      "app_alpha",
      "chat_export",
      "session-chat-export.md",
      {
        content: "# Exported chat",
        message_count: 1
      }
    );

    const resolver = new ArtifactResolver(store);
    const artifactId = String(saved.artifact_id);
    const fileBacked = await resolver.resolve("app_alpha", artifactId);
    assert.equal(fileBacked.consumption.resolved_mode, "file_backed");
    assert.match(String(fileBacked.payload.file_path), /session-chat-export\.md$/);

    const inline = await resolver.resolve("app_alpha", artifactId, {
      requiredMode: "inline_text"
    });
    assert.equal(inline.consumption.resolved_mode, "inline_text");
    assert.equal(inline.payload.text_content, "# Exported chat");
  });

  it("resolves notebooklm_report to file-backed and inline text modes", async () => {
    const store = new ArtifactStore(createArtifactRoot());
    const saved = await store.save(
      "app_alpha",
      "notebooklm_report",
      "GPT-Application-Designer-report.md",
      {
        notebook_id: "nb_1",
        artifact_kind: "report",
        task_id: "task_1",
        status: "completed",
        content_markdown: "# NotebookLM Report"
      },
      {
        fileTextContent: "# NotebookLM Report",
        mimeType: "text/markdown",
        providerOrigin: "notebooklm",
        sourceSkillId: "notebooklm_generate_report"
      }
    );

    const resolver = new ArtifactResolver(store);
    const artifactId = String(saved.artifact_id);
    const fileBacked = await resolver.resolve("app_alpha", artifactId);
    assert.equal(fileBacked.consumption.resolved_mode, "file_backed");
    assert.match(
      String(fileBacked.payload.file_path),
      /GPT-Application-Designer-report\.md$/
    );

    const inline = await resolver.resolve("app_alpha", artifactId, {
      requiredMode: "inline_text"
    });
    assert.equal(inline.consumption.resolved_mode, "inline_text");
    assert.equal(inline.payload.text_content, "# NotebookLM Report");
  });

  it("resolves chat_export to binary payload for attachment reuse", async () => {
    const store = new ArtifactStore(createArtifactRoot());
    const saved = await store.save(
      "app_alpha",
      "chat_export",
      "session-chat-export.md",
      {
        content: "# Exported chat",
        message_count: 1
      }
    );

    const resolver = new ArtifactResolver(store);
    const artifactId = String(saved.artifact_id);
    const resolved = await resolver.resolve("app_alpha", artifactId, {
      requiredMode: "binary_payload"
    });

    assert.equal(resolved.consumption.resolved_mode, "binary_payload");
    assert.equal(
      Buffer.from(String(resolved.payload.binary_content_base64), "base64").toString("utf-8"),
      "# Exported chat"
    );
    assert.equal(resolved.payload.mime_type, "text/markdown");
  });
});
