import assert from "node:assert/strict";
import test from "node:test";

import {
  assertSafeWorkspaceRelativePath,
  buildOpenClawReadFileScript,
  buildOpenClawStageInputScript,
  stageResolvedAgentArtifactsForOpenClaw,
  stageBinaryInputWithVerifiedBase64,
  verifyOpenClawOutputs
} from "../../src/core/agents/openclaw-workspace.js";
import type { ResolvedAgentArtifact } from "../../src/core/agents/agent-artifact-resolver.js";

test("rejects unsafe workspace paths", () => {
  assert.throws(() => assertSafeWorkspaceRelativePath("../secret.txt"));
  assert.throws(() => assertSafeWorkspaceRelativePath("/absolute.txt"));
  assert.throws(() => assertSafeWorkspaceRelativePath("C:/absolute.txt"));
  assert.equal(
    assertSafeWorkspaceRelativePath("outputs/result.md"),
    "outputs/result.md"
  );
});

test("marks required missing output as failed", async () => {
  const result = await verifyOpenClawOutputs({
    workspaceRoot: "/home/openclaw/.openclaw/workspace",
    expectedOutputs: [
      {
        output_id: "out",
        purpose: "answer",
        display_name: "result.md",
        media_type: "text/markdown",
        required: true,
        workspace_relative_path: "outputs/result.md",
        persist_as_artifact: true
      }
    ],
    inspectFile: async () => ({ exists: false })
  });

  assert.equal(result[0]?.verified, false);
  assert.equal(result[0]?.failure_code, "missing_output");
});

test("verifies required output when size and hash match", async () => {
  const result = await verifyOpenClawOutputs({
    workspaceRoot: "/home/openclaw/.openclaw/workspace",
    expectedOutputs: [
      {
        output_id: "out",
        purpose: "answer",
        display_name: "result.md",
        media_type: "text/markdown",
        required: true,
        workspace_relative_path: "outputs/result.md",
        persist_as_artifact: true,
        min_size_bytes: 1,
        expected_sha256: "abc"
      }
    ],
    inspectFile: async () => ({ exists: true, size_bytes: 10, sha256: "abc" })
  });

  assert.equal(result[0]?.verified, true);
  assert.equal(result[0]?.size_bytes, 10);
});

test("binary staging rejects hash mismatch", async () => {
  await assert.rejects(() =>
    stageBinaryInputWithVerifiedBase64({
      inputId: "input_1",
      bytes: Buffer.from("hello"),
      workspaceRoot: "/home/openclaw/.openclaw/workspace",
      workspaceRelativePath: "inputs/file.bin",
      transfer: async () => ({
        exists: true,
        size_bytes: 5,
        sha256: "wrong"
      })
    })
  );
});

test("builds OpenClaw WSL scripts without positional path arguments", () => {
  const stageScript = buildOpenClawStageInputScript(
    "/home/openclaw/.openclaw/workspace/inputs/artifact_1-Notes.md"
  );
  const readScript = buildOpenClawReadFileScript(
    "/home/openclaw/.openclaw/workspace/outputs/result's.md"
  );

  assert.doesNotMatch(stageScript, /\$1/);
  assert.match(
    stageScript,
    /dirname '\/home\/openclaw\/\.openclaw\/workspace\/inputs\/artifact_1-Notes\.md'/
  );
  assert.match(
    stageScript,
    /base64 -d > '\/home\/openclaw\/\.openclaw\/workspace\/inputs\/artifact_1-Notes\.md'/
  );
  assert.doesNotMatch(readScript, /\$1/);
  assert.match(readScript, /base64 -w 0 '\/home\/openclaw\/\.openclaw\/workspace\/outputs\/result'\\''s\.md'/);
});

test("rejects unsafe OpenClaw workspace absolute paths in WSL scripts", () => {
  assert.throws(() => buildOpenClawStageInputScript(""));
  assert.throws(() => buildOpenClawStageInputScript("relative/path.md"));
  assert.throws(() => buildOpenClawReadFileScript(""));
});

test("stages resolved inline text artifacts as verified workspace files", async () => {
  const transfers: Array<{
    workspaceAbsolutePath: string;
    expectedSizeBytes: number;
    expectedSha256: string;
  }> = [];

  const staged = await stageResolvedAgentArtifactsForOpenClaw({
    workspaceRoot: "/home/openclaw/.openclaw/workspace",
    artifacts: [
      {
        artifact_id: "artifact_1",
        artifact_type: "chat_export",
        display_name: "Notes.md",
        app_id: "app_001",
        status: "ready",
        role: "source",
        requested_reuse_mode: "inline_text",
        consumption: {
          default_mode: "file_backed",
          supported_modes: ["file_backed", "inline_text"],
          resolved_mode: "inline_text"
        },
        payload: {
          text_content: "# Notes",
          metadata: {},
          mime_type: "text/markdown"
        },
        provenance: { provider_origin: "local" }
      } satisfies ResolvedAgentArtifact
    ],
    transfer: async (input) => {
      transfers.push({
        workspaceAbsolutePath: input.workspaceAbsolutePath,
        expectedSizeBytes: input.expectedSizeBytes,
        expectedSha256: input.expectedSha256
      });
      return {
        exists: true,
        size_bytes: input.expectedSizeBytes,
        sha256: input.expectedSha256
      };
    }
  });

  assert.equal(staged.length, 1);
  assert.equal(staged[0]?.input_id, "artifact_1");
  assert.equal(staged[0]?.source_kind, "artifact");
  assert.equal(staged[0]?.encoding, "utf8");
  assert.equal(staged[0]?.workspace_relative_path, "inputs/artifact_1-Notes.md");
  assert.equal(
    transfers[0]?.workspaceAbsolutePath,
    "/home/openclaw/.openclaw/workspace/inputs/artifact_1-Notes.md"
  );
});

test("represents metadata-only resolved artifacts without staging bytes", async () => {
  let transferCalled = false;
  const staged = await stageResolvedAgentArtifactsForOpenClaw({
    workspaceRoot: "/home/openclaw/.openclaw/workspace",
    artifacts: [
      {
        artifact_id: "artifact_2",
        artifact_type: "file_inventory",
        display_name: "Inventory.json",
        app_id: "app_001",
        status: "ready",
        role: "context",
        requested_reuse_mode: "metadata_only",
        consumption: {
          default_mode: "metadata_only",
          supported_modes: ["metadata_only"],
          resolved_mode: "metadata_only"
        },
        payload: {
          metadata: { item_count: 2 },
          mime_type: "application/json"
        },
        provenance: { provider_origin: "local" }
      } satisfies ResolvedAgentArtifact
    ],
    transfer: async () => {
      transferCalled = true;
      return { exists: false };
    }
  });

  assert.equal(transferCalled, false);
  assert.equal(staged.length, 1);
  assert.equal(staged[0]?.input_id, "artifact_2");
  assert.equal(staged[0]?.workspace_relative_path, undefined);
  assert.deepEqual(staged[0]?.metadata, { item_count: 2 });
});
