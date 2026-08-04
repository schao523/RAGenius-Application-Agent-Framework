import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { afterEach, describe, it } from "node:test";
import { randomUUID } from "node:crypto";
import { z } from "zod";

import { ArtifactStore } from "../../src/core/tools/providers/artifact-store.js";
import { FilePolicy } from "../../src/core/tools/providers/file-policy.js";
import { PhaseOneLocalToolProvider } from "../../src/core/tools/providers/local-tool-provider.js";

const artifactRoots = new Set<string>();
const writeFileToolDefinition = {
  id: "write_file",
  name: "Write File",
  providerType: "local" as const,
  inputSchema: z.object({
    path: z.string(),
    content: z.string()
  }),
  outputSchema: z.object({
    path: z.string(),
    bytes_written: z.number(),
    updated: z.boolean()
  }),
  permissionScopes: ["filesystem.write"],
  sideEffecting: true
};
const patchFileToolDefinition = {
  id: "patch_file",
  name: "Patch File",
  providerType: "local" as const,
  inputSchema: z.object({
    path: z.string(),
    patch: z.string()
  }),
  outputSchema: z.object({
    path: z.string(),
    updated: z.boolean(),
    summary: z.string()
  }),
  permissionScopes: ["filesystem.patch"],
  sideEffecting: true
};

function createArtifactRoot(): string {
  const root = path.resolve(
    `D:/GitHub/Codex-RAGenius-System/outputs/test-artifacts-${randomUUID()}`
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

describe("local tool provider", () => {
  afterEach(async () => {
    await Promise.all(
      [...artifactRoots].map(async (root) => {
        await cleanupArtifactRoot(root);
        artifactRoots.delete(root);
      })
    );
  });

  it("reads a text file within an allowed root", async () => {
    const provider = new PhaseOneLocalToolProvider(
      new FilePolicy({
        allowedRoots: ["D:/GitHub/Codex-RAGenius-System"],
        maxReadBytes: 4096
      }),
      new ArtifactStore(createArtifactRoot())
    );

    const result = await provider.execute(
      {
        id: "read_file",
        name: "Read File",
        providerType: "local",
        inputSchema: z.object({ path: z.string() }),
        outputSchema: z.object({
          path: z.string(),
          content: z.string(),
          truncated: z.boolean(),
          size_bytes: z.number()
        }),
        permissionScopes: ["filesystem.read"],
        sideEffecting: false
      },
      {
        path: "D:/GitHub/Codex-RAGenius-System/README.md"
      }
    );

    assert.match(result.path as string, /README\.md$/);
    assert.equal(typeof result.content, "string");
  });

  it("stores and loads artifacts within the calling app scope", async () => {
    const provider = new PhaseOneLocalToolProvider(
      new FilePolicy({
        allowedRoots: ["D:/GitHub/Codex-RAGenius-System"],
        maxReadBytes: 4096
      }),
      new ArtifactStore(createArtifactRoot())
    );

    const saved = await provider.execute(
      {
        id: "save_artifact",
        name: "Save Artifact",
        providerType: "local",
        inputSchema: z.object({
          artifact_type: z.string(),
          name: z.string(),
          content: z.unknown()
        }),
        outputSchema: z.object({
          artifact_id: z.string(),
          path: z.string(),
          artifact_type: z.string(),
          file_path: z.string().optional()
        }),
        permissionScopes: ["artifact.write"],
        sideEffecting: true
      },
      {
        artifact_type: "report",
        name: "inventory",
        content: { count: 3 }
      },
      { appId: "app_alpha", sessionId: "session_alpha" }
    );

    assert.match(saved.path as string, /app_alpha/);
    assert.equal(saved.file_path, undefined);
    assert.equal(saved.display_name, "inventory");
    assert.equal(saved.app_id, "app_alpha");
    assert.equal(saved.session_id, "session_alpha");
    assert.equal(saved.provider_origin, "local");
    assert.equal(saved.status, "ready");

    const loaded = await provider.execute(
      {
        id: "load_artifact",
        name: "Load Artifact",
        providerType: "local",
        inputSchema: z.object({
          artifact_id: z.string()
        }),
        outputSchema: z.object({
          artifact_id: z.string(),
          artifact_type: z.string(),
          path: z.string(),
          content: z.unknown()
        }),
        permissionScopes: ["artifact.read"],
        sideEffecting: false
      },
      {
        artifact_id: saved.artifact_id
      },
      { appId: "app_alpha" }
    );

    assert.deepEqual(loaded.content, { count: 3 });
    assert.match(loaded.path as string, /app_alpha/);
    assert.equal(loaded.display_name, "inventory");
    assert.equal(loaded.app_id, "app_alpha");
    assert.equal(loaded.session_id, "session_alpha");
    assert.equal(loaded.provider_origin, "local");
    assert.equal(loaded.status, "ready");
  });

  it("filters artifact inventory by session_id", async () => {
    const artifactRoot = createArtifactRoot();
    const store = new ArtifactStore(artifactRoot);

    await store.save("app_alpha", "chat_export", "alpha.md", { count: 1 }, { sessionId: "session_alpha" });
    await store.save("app_alpha", "chat_export", "beta.md", { count: 2 }, { sessionId: "session_beta" });

    const alphaItems = await store.list("app_alpha", { sessionId: "session_alpha", status: "ready" });
    const betaItems = await store.list("app_alpha", { sessionId: "session_beta", status: "ready" });

    assert.equal(alphaItems.length, 1);
    assert.equal(alphaItems[0]?.session_id, "session_alpha");
    assert.equal(betaItems.length, 1);
    assert.equal(betaItems[0]?.session_id, "session_beta");
  });

  it("does not allow one app to load another app's artifact", async () => {
    const provider = new PhaseOneLocalToolProvider(
      new FilePolicy({
        allowedRoots: ["D:/GitHub/Codex-RAGenius-System"],
        maxReadBytes: 4096
      }),
      new ArtifactStore(createArtifactRoot())
    );

    const saved = await provider.execute(
      {
        id: "save_artifact",
        name: "Save Artifact",
        providerType: "local",
        inputSchema: z.object({
          artifact_type: z.string(),
          name: z.string(),
          content: z.unknown()
        }),
        outputSchema: z.object({
          artifact_id: z.string(),
          path: z.string(),
          artifact_type: z.string(),
          file_path: z.string().optional()
        }),
        permissionScopes: ["artifact.write"],
        sideEffecting: true
      },
      {
        artifact_type: "report",
        name: "inventory",
        content: { count: 3 }
      },
      { appId: "app_alpha" }
    );

    await assert.rejects(
      () =>
        provider.execute(
          {
            id: "load_artifact",
            name: "Load Artifact",
            providerType: "local",
            inputSchema: z.object({
              artifact_id: z.string()
            }),
            outputSchema: z.object({
              artifact_id: z.string(),
              artifact_type: z.string(),
              path: z.string(),
              content: z.unknown()
            }),
            permissionScopes: ["artifact.read"],
            sideEffecting: false
          },
          {
            artifact_id: saved.artifact_id
          },
          { appId: "app_beta" }
        ),
      /Artifact not found/
    );
  });

  it("writes a text file only within mutation roots", async () => {
    const tempRoot = createArtifactRoot();
    const targetPath = path.join(tempRoot, "content.md");
    await fs.mkdir(tempRoot, { recursive: true });
    await fs.writeFile(targetPath, "before", "utf-8");

    const provider = new PhaseOneLocalToolProvider(
      new FilePolicy({
        allowedRoots: [tempRoot],
        mutationRoots: [tempRoot],
        maxReadBytes: 4096,
        maxWriteBytes: 4096,
        maxPatchBytes: 4096
      }),
      new ArtifactStore(createArtifactRoot())
    );

    const result = await provider.execute(
      writeFileToolDefinition,
      { path: targetPath, content: "after" },
      { appId: "app_alpha" }
    );

    assert.equal(result.updated, true);
    assert.equal(await fs.readFile(targetPath, "utf-8"), "after");
  });

  it("applies a unified diff patch within mutation roots", async () => {
    const tempRoot = createArtifactRoot();
    const targetPath = path.join(tempRoot, "content.md");
    await fs.mkdir(tempRoot, { recursive: true });
    await fs.writeFile(targetPath, "alpha\nbeta\n", "utf-8");

    const provider = new PhaseOneLocalToolProvider(
      new FilePolicy({
        allowedRoots: [tempRoot],
        mutationRoots: [tempRoot],
        maxReadBytes: 4096,
        maxWriteBytes: 4096,
        maxPatchBytes: 4096
      }),
      new ArtifactStore(createArtifactRoot())
    );

    const result = await provider.execute(
      patchFileToolDefinition,
      {
        path: targetPath,
        patch: "@@ -1,2 +1,2 @@\n alpha\n-beta\n+gamma\n"
      },
      { appId: "app_alpha" }
    );

    assert.equal(result.updated, true);
    assert.match(String(result.summary), /patched/i);
    assert.equal(await fs.readFile(targetPath, "utf-8"), "alpha\ngamma\n");
  });

  it("loads legacy artifact metadata with relative file paths as absolute file-backed records", async () => {
    const artifactRoot = createArtifactRoot();
    const store = new ArtifactStore(artifactRoot);
    const appId = "app_legacy";
    const artifactDir = path.resolve(artifactRoot, appId, "chat_export");
    await fs.mkdir(artifactDir, { recursive: true });
    const artifactId = "artifact_legacy_1";
    const exportFile = path.resolve(
      artifactRoot,
      appId,
      "chat_export",
      `${artifactId}-session-chat-export.md`
    );
    await fs.writeFile(exportFile, "# legacy artifact", "utf-8");
    const metadataPath = path.resolve(artifactDir, `${artifactId}.json`);
    await fs.writeFile(
      metadataPath,
      JSON.stringify(
        {
          name: "session-chat-export.md",
          content: {
            content: "# legacy artifact",
            format: "md",
          },
          file_path: path.join(
            artifactRoot,
            appId,
            "chat_export",
            `${artifactId}-session-chat-export.md`
          ),
        },
        null,
        2
      ),
      "utf-8"
    );

    const loaded = await store.load(appId, artifactId);

    assert.equal(loaded.display_name, "session-chat-export.md");
    assert.equal(loaded.file_path, exportFile);
    assert.equal(loaded.path, metadataPath);
  });
});
