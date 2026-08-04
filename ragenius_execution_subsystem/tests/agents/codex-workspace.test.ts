import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  cleanupCodexRunWorkspaces,
  createCodexRunWorkspace,
  planCodexExpectedOutputs,
  stageCodexArtifacts,
  verifyCodexOutputArtifacts
} from "../../src/core/agents/codex-workspace.js";
import type { ResolvedAgentArtifact } from "../../src/core/agents/agent-artifact-resolver.js";

async function withTempDir(
  run: (root: string) => Promise<void>
): Promise<void> {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "ragenius-codex-workspace-"));
  try {
    await run(root);
  } finally {
    await fs.rm(root, { recursive: true, force: true });
  }
}

function artifact(
  overrides: Partial<ResolvedAgentArtifact> = {}
): ResolvedAgentArtifact {
  return {
    artifact_id: "artifact_123",
    artifact_type: "session_export",
    display_name: "Approved notes.md",
    app_id: "app_001",
    status: "ready",
    role: "source",
    requested_reuse_mode: "inline_text",
    consumption: {
      default_mode: "inline_text",
      supported_modes: ["inline_text", "file_backed", "metadata_only"],
      resolved_mode: "inline_text"
    },
    payload: {
      text_content: "Approved session content.",
      metadata: {}
    },
    provenance: { provider_origin: "ragenius_app" },
    ...overrides
  };
}

test("stages inline text with a verified generated relative path", async () => {
  await withTempDir(async (runRoot) => {
    const workspace = await createCodexRunWorkspace({
      runRoot,
      executionId: "execution_123"
    });
    const staged = await stageCodexArtifacts({
      workspace,
      artifacts: [artifact()]
    });

    assert.match(
      staged[0]!.workspace_relative_path!,
      /^inputs\/artifact_123-Approved notes\.md$/
    );
    assert.equal(staged[0]!.size_bytes, 25);
    assert.equal(
      staged[0]!.sha256,
      createHash("sha256").update("Approved session content.").digest("hex")
    );
    assert.equal("workspace_absolute_path" in staged[0]!, false);
    assert.equal(
      await fs.readFile(
        path.join(workspace.root_absolute_path, staged[0]!.workspace_relative_path!),
        "utf8"
      ),
      "Approved session content."
    );
  });
});

test("copies file-backed bytes and rejects a declared hash mismatch", async () => {
  await withTempDir(async (runRoot) => {
    const sourcePath = path.join(runRoot, "source.bin");
    await fs.writeFile(sourcePath, Buffer.from([0, 1, 2, 255]));
    const workspace = await createCodexRunWorkspace({
      runRoot,
      executionId: "execution_123"
    });

    await assert.rejects(
      stageCodexArtifacts({
        workspace,
        artifacts: [artifact({
          requested_reuse_mode: "file_backed",
          consumption: {
            default_mode: "file_backed",
            supported_modes: ["file_backed"],
            resolved_mode: "file_backed"
          },
          payload: {
            file_path: sourcePath,
            metadata: { sha256: "0".repeat(64), size_bytes: 4 }
          }
        })]
      }),
      /hash does not match/i
    );
  });
});

test("does not create bytes for metadata-only artifacts", async () => {
  await withTempDir(async (runRoot) => {
    const workspace = await createCodexRunWorkspace({
      runRoot,
      executionId: "execution_123"
    });
    const staged = await stageCodexArtifacts({
      workspace,
      artifacts: [artifact({
        requested_reuse_mode: "metadata_only",
        consumption: {
          default_mode: "metadata_only",
          supported_modes: ["metadata_only"],
          resolved_mode: "metadata_only"
        },
        payload: { metadata: { title: "Approved notes" } }
      })]
    });

    assert.equal(staged[0]?.workspace_relative_path, undefined);
    assert.deepEqual(await fs.readdir(workspace.inputs_absolute_path), []);
  });
});

test("rejects unsafe execution ids", async () => {
  await withTempDir(async (runRoot) => {
    await assert.rejects(
      createCodexRunWorkspace({ runRoot, executionId: "../escape" }),
      /unsafe Codex execution id/i
    );
  });
});

test("rejects symlink file-backed sources", async (t) => {
  await withTempDir(async (runRoot) => {
    const sourcePath = path.join(runRoot, "source.txt");
    const linkPath = path.join(runRoot, "source-link.txt");
    await fs.writeFile(sourcePath, "secret");
    try {
      await fs.symlink(sourcePath, linkPath, "file");
    } catch (error) {
      t.skip(`Symlinks are unavailable: ${String(error)}`);
      return;
    }
    const workspace = await createCodexRunWorkspace({
      runRoot,
      executionId: "execution_123"
    });

    await assert.rejects(
      stageCodexArtifacts({
        workspace,
        artifacts: [artifact({
          requested_reuse_mode: "file_backed",
          consumption: {
            default_mode: "file_backed",
            supported_modes: ["file_backed"],
            resolved_mode: "file_backed"
          },
          payload: { file_path: linkPath, metadata: {} }
        })]
      }),
      /symlink/i
    );
  });
});

test("retention cleanup keeps the current execution workspace", async () => {
  await withTempDir(async (runRoot) => {
    const current = await createCodexRunWorkspace({
      runRoot,
      executionId: "execution_current"
    });
    const stale = await createCodexRunWorkspace({
      runRoot,
      executionId: "execution_stale"
    });
    const old = new Date("2026-08-01T00:00:00.000Z");
    await fs.utimes(stale.root_absolute_path, old, old);

    await cleanupCodexRunWorkspaces({
      runRoot,
      currentExecutionId: "execution_current",
      retentionHours: 24,
      now: new Date("2026-08-03T00:00:00.000Z")
    });

    assert.equal((await fs.stat(current.root_absolute_path)).isDirectory(), true);
    await assert.rejects(fs.stat(stale.root_absolute_path), { code: "ENOENT" });
  });
});

test("verifies a reported Codex output inside the outputs directory", async () => {
  await withTempDir(async (runRoot) => {
    const workspace = await createCodexRunWorkspace({
      runRoot,
      executionId: "execution_123"
    });
    const content = "# Verified report\n";
    const relativePath = "outputs/study-report.md";
    await fs.writeFile(path.join(workspace.root_absolute_path, relativePath), content);

    const verified = await verifyCodexOutputArtifacts({
      workspace,
      expectedOutputs: [{
        output_id: "agent_output",
        display_name: "agent_output.md",
        media_type: "text/markdown",
        required: false,
        persist_as_artifact: true,
        artifact_type: "agent_output"
      }],
      reportedArtifacts: [{
        path: relativePath,
        media_type: "text/markdown"
      }]
    });

    assert.equal(verified[0]?.verified, true);
    assert.equal(verified[0]?.workspace_relative_path, relativePath);
    assert.equal(verified[0]?.size_bytes, Buffer.byteLength(content));
    assert.equal(
      verified[0]?.sha256,
      createHash("sha256").update(content).digest("hex")
    );
  });
});

test("plans one deterministic contained path for Codex prompting and verification", () => {
  const outputs = planCodexExpectedOutputs({
    request_type: "execute_agent",
    app_id: "app_001",
    session_id: "session_001",
    agent_backend: "codex_cli",
    agent_query: "Create a report.",
    expected_outputs: [{
      output_id: "agent_output",
      display_name: "Study Report.md",
      persist_as_artifact: true
    }]
  });

  assert.equal(
    outputs[0]?.workspace_relative_path,
    "outputs/agent_output-Study Report.md"
  );
});

test("treats an out-of-contract reported path as missing instead of resolving it", async () => {
  await withTempDir(async (runRoot) => {
    const workspace = await createCodexRunWorkspace({
      runRoot,
      executionId: "execution_123"
    });
    await fs.mkdir(path.join(workspace.root_absolute_path, "reports"));
    await fs.writeFile(
      path.join(workspace.root_absolute_path, "reports", "study-report.md"),
      "# Wrong location\n"
    );

    const verified = await verifyCodexOutputArtifacts({
      workspace,
      expectedOutputs: [{
        output_id: "agent_output",
        display_name: "study-report.md",
        media_type: "text/markdown",
        required: false,
        persist_as_artifact: true,
        artifact_type: "agent_output",
        workspace_relative_path: "outputs/agent_output-study-report.md"
      }],
      reportedArtifacts: [{ path: "reports/study-report.md" }]
    });

    assert.equal(verified[0]?.verified, false);
    assert.equal(verified[0]?.failure_code, "missing_output");
    assert.equal(
      verified[0]?.workspace_relative_path,
      "outputs/agent_output-study-report.md"
    );
  });
});

test("rejects reported Codex outputs outside the outputs directory", async () => {
  await withTempDir(async (runRoot) => {
    const workspace = await createCodexRunWorkspace({
      runRoot,
      executionId: "execution_123"
    });

    await assert.rejects(
      verifyCodexOutputArtifacts({
        workspace,
        expectedOutputs: [{
          output_id: "agent_output",
          display_name: "agent_output.md",
          media_type: "text/markdown",
          required: false,
          persist_as_artifact: true,
          artifact_type: "agent_output"
        }],
        reportedArtifacts: [{ path: "../escaped.md" }]
      }),
      /outputs directory/i
    );
  });
});
