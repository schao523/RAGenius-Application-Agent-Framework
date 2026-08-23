import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { afterEach, describe, it } from "node:test";

import { AgentOutputArtifactPersister } from "../../src/core/agents/agent-output-artifact-persister.js";
import { ArtifactStore } from "../../src/core/tools/providers/artifact-store.js";
import { ArtifactResolver } from "../../src/core/artifacts/artifact-resolver.js";

const artifactRoots = new Set<string>();

function createArtifactRoot(): string {
  const root = path.resolve(
    `D:/GitHub/Codex-RAGenius-System/outputs/test-agent-output-persister-${randomUUID()}`
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

describe("agent output artifact persister", () => {
  afterEach(async () => {
    await Promise.all(
      [...artifactRoots].map(async (root) => {
        await cleanupArtifactRoot(root);
        artifactRoots.delete(root);
      })
    );
  });

  it("persists verified text outputs as reusable agent_output artifacts", async () => {
    const store = new ArtifactStore(createArtifactRoot());
    const persister = new AgentOutputArtifactPersister(store, {
      readOutputBytes: async () => Buffer.from("# Agent answer", "utf-8")
    });

    const artifact = await persister.persist({
      request: {
        request_type: "execute_agent",
        app_id: "app_001",
        session_id: "session_001",
        agent_backend: "openclaw_cli",
        agent_query: "Create an answer."
      },
      executionId: "execution_001",
      output: {
        output_id: "agent_answer",
        purpose: "answer",
        display_name: "answer.md",
        media_type: "text/markdown",
        required: true,
        persist_as_artifact: true,
        artifact_type: "agent_output",
        artifact_role: "final"
      },
      verification: {
        output_id: "agent_answer",
        workspace_relative_path: "outputs/agent_answer-answer.md",
        workspace_absolute_path:
          "/home/openclaw/.openclaw/workspace/outputs/agent_answer-answer.md",
        required: true,
        exists: true,
        verified: true,
        size_bytes: 14,
        sha256: "abc",
        media_type: "text/markdown"
      }
    });

    assert.equal(artifact.artifact_type, "agent_output");
    assert.equal(artifact.display_name, "answer.md");

    const loaded = await store.load("app_001", artifact.artifact_id);
    assert.equal(loaded.session_id, "session_001");
    assert.equal(loaded.created_by_execution_id, "execution_001");
    assert.equal(loaded.provider_origin, "openclaw_cli");
    assert.equal(loaded.source_skill_id, "openclaw_cli");
    assert.equal(loaded.mime_type, "text/markdown");
    assert.match(String(loaded.file_path), /answer\.md$/);

    const resolved = await new ArtifactResolver(store).resolve(
      "app_001",
      artifact.artifact_id,
      { requiredMode: "inline_text" }
    );
    assert.equal(resolved.payload.text_content, "# Agent answer");
  });

  it("persists binary outputs without changing their bytes", async () => {
    const root = createArtifactRoot();
    const store = new ArtifactStore(root);
    const expectedBytes = Buffer.from([0, 1, 2, 127, 128, 254, 255]);
    const persister = new AgentOutputArtifactPersister(store, {
      readOutputBytes: async () => expectedBytes
    });

    const artifact = await persister.persist({
      request: {
        request_type: "execute_agent",
        app_id: "app_001",
        session_id: "session_001",
        agent_backend: "openclaw_cli",
        agent_query: "Create a binary output."
      },
      executionId: "execution_002",
      output: {
        output_id: "binary_output",
        purpose: "artifact",
        display_name: "output.bin",
        media_type: "application/octet-stream",
        required: true,
        persist_as_artifact: true,
        artifact_type: "agent_output"
      },
      verification: {
        output_id: "binary_output",
        workspace_relative_path: "outputs/output.bin",
        workspace_absolute_path:
          "/home/openclaw/.openclaw/workspace/runs/execution_002/outputs/output.bin",
        required: true,
        exists: true,
        verified: true,
        size_bytes: expectedBytes.byteLength
      }
    });

    const loaded = await store.load("app_001", artifact.artifact_id);
    assert.ok(loaded.file_path);
    assert.deepEqual(await fs.readFile(loaded.file_path), expectedBytes);
    assert.equal(loaded.size_bytes, expectedBytes.byteLength);
  });

  it("persists a captured interactive response without a provider-created file", async () => {
    const store = new ArtifactStore(createArtifactRoot());
    const persister = new AgentOutputArtifactPersister(store, {
      readOutputBytes: async () => {
        throw new Error("Interactive response persistence must not read a workspace file.");
      }
    });

    const artifact = await persister.persistText({
      request: {
        request_type: "execute_agent",
        app_id: "app_001",
        session_id: "session_001",
        agent_backend: "codex_cli",
        agent_query: "Answer after asking for a format."
      },
      executionId: "execution_interactive",
      output: {
        output_id: "agent_output",
        display_name: "agent_output.md",
        media_type: "text/markdown",
        persist_as_artifact: true,
        artifact_type: "agent_output"
      },
      text: "# Answer\nMarkdown selected."
    });

    const loaded = await store.load("app_001", artifact.artifact_id);
    assert.equal(loaded.session_id, "session_001");
    assert.equal(loaded.created_by_execution_id, "execution_interactive");
    assert.equal(loaded.provider_origin, "codex_cli");
    assert.equal(loaded.mime_type, "text/markdown");
    assert.equal(
      (await new ArtifactResolver(store).resolve(
        "app_001",
        artifact.artifact_id,
        { requiredMode: "inline_text" }
      )).payload.text_content,
      "# Answer\nMarkdown selected."
    );
  });

  it("generates collision-resistant ids for concurrent saves", async () => {
    const store = new ArtifactStore(createArtifactRoot());
    const saved = await Promise.all(
      Array.from({ length: 20 }, (_, index) =>
        store.save("app_001", "agent_output", `output-${index}.txt`, {
          index
        })
      )
    );

    assert.equal(new Set(saved.map((item) => item.artifact_id)).size, 20);
  });
});
