import assert from "node:assert/strict";
import test from "node:test";

import {
  assertSafeWorkspaceRelativePath,
  stageBinaryInputWithVerifiedBase64,
  verifyOpenClawOutputs
} from "../../src/core/agents/openclaw-workspace.js";

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
