import assert from "node:assert/strict";
import test from "node:test";

import {
  assertSafeWorkspaceRelativePath,
  assertResolvedPathContained,
  buildOpenClawRunWorkspaceRoot,
  buildOpenClawRunCleanupScript,
  buildOpenClawReadFileScript,
  buildOpenClawWslExecArgs,
  stageResolvedAgentArtifactsForOpenClaw,
  stageBinaryInputWithVerifiedBase64,
  transferOpenClawInputViaWsl,
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

test("derives and contains per-execution run workspaces", () => {
  const runRoot = buildOpenClawRunWorkspaceRoot(
    "/home/openclaw/.openclaw/workspace",
    "execution_001"
  );
  assert.equal(
    runRoot,
    "/home/openclaw/.openclaw/workspace/runs/execution_001"
  );
  assert.equal(
    assertResolvedPathContained(runRoot, `${runRoot}/outputs/result.md`),
    `${runRoot}/outputs/result.md`
  );
  assert.throws(() =>
    assertResolvedPathContained(
      runRoot,
      "/home/openclaw/.openclaw/workspace/runs/execution_000/outputs/result.md"
    )
  );
  assert.throws(() =>
    buildOpenClawRunWorkspaceRoot(
      "/home/openclaw/.openclaw/workspace",
      "../execution_001"
    )
  );
});

test("builds bounded cleanup for old run directories only", () => {
  const script = buildOpenClawRunCleanupScript({
    workspaceRoot: "/home/openclaw/.openclaw/workspace",
    currentExecutionId: "execution_001",
    retentionHours: 24
  });
  assert.match(script, /workspace\/runs/);
  assert.match(script, /-mmin \+1440/);
  assert.match(script, /! -name 'execution_001'/);
  assert.match(script, /-mindepth 1 -maxdepth 1 -type d/);
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

test("builds OpenClaw read scripts without positional path arguments", () => {
  const readScript = buildOpenClawReadFileScript(
    "/home/openclaw/.openclaw/workspace/outputs/result's.md"
  );

  assert.doesNotMatch(readScript, /\$1/);
  assert.match(readScript, /base64 -w 0 '\/home\/openclaw\/\.openclaw\/workspace\/outputs\/result'\\''s\.md'/);
});

test("uses WSL exec mode so command arguments are not pre-expanded", () => {
  assert.deepEqual(
    buildOpenClawWslExecArgs("OpenClawGateway", [
      "readlink",
      "-f",
      "--",
      "/home/openclaw/.openclaw/workspace/runs/execution_001/inputs"
    ]),
    [
      "-d",
      "OpenClawGateway",
      "--exec",
      "readlink",
      "-f",
      "--",
      "/home/openclaw/.openclaw/workspace/runs/execution_001/inputs"
    ]
  );
});

test("stages inputs with direct WSL commands and TypeScript containment", async () => {
  const runRoot = "/home/openclaw/.openclaw/workspace/runs/execution_001";
  const target = `${runRoot}/inputs/file.bin`;
  const calls: Array<{ args: string[]; stdin?: string }> = [];
  const payload = Buffer.from("OpenClaw staging probe", "utf8");
  const expectedSha256 = "7402a30cd5428b51111e419de3863d5ee73a41ea1b747a0e97a70f614c23266f";

  const result = await transferOpenClawInputViaWsl({
    wslDistro: "OpenClawGateway",
    base64Chunks: [payload.toString("base64")],
    workspaceAbsolutePath: target,
    allowedWorkspaceRoot: runRoot,
    expectedSizeBytes: payload.byteLength,
    expectedSha256,
    runWsl: async (input) => {
      calls.push({
        args: input.args,
        ...(typeof input.stdin === "string" ? { stdin: input.stdin } : {})
      });
      if (input.args[0] === "readlink") {
        return {
          exitCode: 0,
          stdout: `${input.args.at(-1)}\n`,
          stderr: ""
        };
      }
      if (input.args[0] === "test") {
        return { exitCode: 0, stdout: "", stderr: "" };
      }
      if (input.args[0] === "wc") {
        return { exitCode: 0, stdout: `${payload.byteLength} ${target}\n`, stderr: "" };
      }
      if (input.args[0] === "sha256sum") {
        return { exitCode: 0, stdout: `${expectedSha256} ${target}\n`, stderr: "" };
      }
      return { exitCode: 0, stdout: "", stderr: "" };
    }
  });

  assert.deepEqual(calls[0]?.args, ["mkdir", "-p", "--", `${runRoot}/inputs`]);
  assert.deepEqual(calls[1]?.args, ["readlink", "-f", "--", `${runRoot}/inputs`]);
  assert.equal(calls[2]?.args[0], "python3");
  assert.equal(calls[2]?.args.at(-1), target);
  assert.equal(calls[2]?.stdin, payload.toString("base64"));
  assert.equal(calls.some((call) => call.args.includes("bash")), false);
  assert.equal(result.exists, true);
  assert.equal(result.size_bytes, payload.byteLength);
  assert.equal(result.sha256, expectedSha256);
});

test("rejects a canonical staged input parent outside the current run", async () => {
  await assert.rejects(
    transferOpenClawInputViaWsl({
      wslDistro: "OpenClawGateway",
      base64Chunks: [""],
      workspaceAbsolutePath:
        "/home/openclaw/.openclaw/workspace/runs/execution_001/inputs/file.bin",
      allowedWorkspaceRoot:
        "/home/openclaw/.openclaw/workspace/runs/execution_001",
      expectedSizeBytes: 0,
      expectedSha256: "empty",
      runWsl: async (input) => ({
        exitCode: 0,
        stdout:
          input.args[0] === "readlink"
            ? "/home/openclaw/.openclaw/workspace/runs/execution_other/inputs\n"
            : "",
        stderr: ""
      })
    }),
    /outside the current run/
  );
});

test("rejects unsafe OpenClaw workspace absolute paths before WSL invocation", async () => {
  let invoked = false;
  await assert.rejects(
    transferOpenClawInputViaWsl({
      wslDistro: "OpenClawGateway",
      base64Chunks: [""],
      workspaceAbsolutePath: "relative/path.md",
      expectedSizeBytes: 0,
      expectedSha256: "empty",
      runWsl: async () => {
        invoked = true;
        return { exitCode: 0, stdout: "", stderr: "" };
      }
    }),
    /Unsafe OpenClaw workspace-absolute path/
  );
  assert.equal(invoked, false);
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

test("stages file-backed artifacts with direct file transfer instead of base64", async () => {
  let base64Called = false;
  let transferredSource = "";
  const staged = await stageResolvedAgentArtifactsForOpenClaw({
    workspaceRoot: "/home/openclaw/.openclaw/workspace/runs/execution_001",
    artifacts: [{
      artifact_id: "artifact_video",
      artifact_type: "session_upload",
      display_name: "video.mp4",
      app_id: "app_001",
      status: "ready",
      role: "attachment",
      requested_reuse_mode: "file_backed",
      consumption: { default_mode: "file_backed", supported_modes: ["file_backed"], resolved_mode: "file_backed" },
      payload: {
        file_path: "D:/uploads/video.mp4",
        metadata: { size_bytes: 11, sha256: "abc123" },
        mime_type: "video/mp4"
      },
      provenance: { provider_origin: "session_upload" }
    } satisfies ResolvedAgentArtifact],
    transfer: async () => {
      base64Called = true;
      return { exists: false };
    },
    transferFile: async (input) => {
      transferredSource = input.sourceWindowsPath;
      return { exists: true, size_bytes: 11, sha256: "abc123" };
    }
  });
  assert.equal(base64Called, false);
  assert.equal(transferredSource, "D:/uploads/video.mp4");
  assert.equal(staged[0]?.workspace_relative_path, "inputs/artifact_video-video.mp4");
});
