import assert from "node:assert/strict";
import { createHash, randomUUID } from "node:crypto";
import { createReadStream } from "node:fs";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { executeAgentRequestSchema } from "../src/api/schemas/execution-request.schema.js";
import { SessionUploadArtifactImporter } from "../src/core/artifacts/session-upload-artifact-importer.js";
import { buildCodexPrompt } from "../src/core/agents/codex-prompt-builder.js";
import { buildOpenClawPrompt } from "../src/core/agents/openclaw-prompt-builder.js";
import type { AgentProviderExecutionContext } from "../src/core/agents/agent-provider-context.js";
import type { NormalizedOpenClawProviderOptions } from "../src/core/agents/openclaw-cli-types.js";
import { ArtifactStore } from "../src/core/tools/providers/artifact-store.js";

const binaryInMemoryLimit = 25 * 1024 * 1024;
const fixtureSize = binaryInMemoryLimit + (1024 * 1024);
const chunk = Buffer.alloc(1024 * 1024, 0x5a);
const root = await fs.mkdtemp(path.join(os.tmpdir(), "ragenius-agent-input-smoke-"));
const sourcePath = path.join(root, "fixture.mp4");

try {
  const handle = await fs.open(sourcePath, "w");
  const hash = createHash("sha256");
  try {
    for (let offset = 0; offset < fixtureSize; offset += chunk.length) {
      await handle.write(chunk);
      hash.update(chunk);
    }
  } finally {
    await handle.close();
  }
  const sha256 = `sha256:${hash.digest("hex")}`;
  const artifactRoot = path.join(root, "artifacts");
  const importer = new SessionUploadArtifactImporter(new ArtifactStore(artifactRoot), {
    artifactRootDir: artifactRoot,
    maxBytes: 512 * 1024 * 1024,
    allowedMimeTypes: ["video/mp4"],
    tempRetentionHours: 24
  });
  const importOnce = () => importer.import({
    appId: "app_smoke",
    sessionId: "session_smoke",
    sourceUploadId: "upload_smoke",
    displayName: "fixture.mp4",
    mimeType: "video/mp4",
    declaredSizeBytes: fixtureSize,
    declaredSha256: sha256,
    stream: createReadStream(sourcePath)
  });
  const first = await importOnce();
  const second = await importOnce();
  assert.equal(first.artifact.artifact_id, second.artifact.artifact_id);
  assert.equal(second.reusedExistingArtifact, true);
  const artifactId = String(first.artifact.artifact_id || "").trim();
  assert.ok(artifactId);

  const requestBase = {
    request_type: "execute_agent" as const,
    app_id: "app_smoke",
    session_id: "session_smoke",
    agent_query: "Inspect the selected video.",
    artifact_refs: [{
      artifact_id: artifactId,
      role: "attachment" as const,
      reuse_mode: "file_backed" as const
    }],
    execution_options: { dry_run: true }
  };
  const codexRequest = executeAgentRequestSchema.parse({ ...requestBase, agent_backend: "codex_cli" });
  const openClawRequest = executeAgentRequestSchema.parse({ ...requestBase, agent_backend: "openclaw_cli" });
  const context: AgentProviderExecutionContext = {
    execution_id: `execution_${randomUUID()}`,
    authorization: {
      state: "not_required",
      permission_scope: "agent.read_only",
      policy_fingerprint: "a".repeat(64)
    },
    operation_plan: [{
      operation_id: "inspect_input",
      kind: "read",
      description: "Inspect the selected video.",
      required: true,
      minimum_verification: "process_observed"
    }],
    resolved_artifacts: [],
    expected_outputs: []
  };
  const codexPrompt = buildCodexPrompt({
    request: codexRequest,
    context,
    stagedArtifacts: [{
      artifact_id: artifactId,
      display_name: "fixture.mp4",
      role: "attachment",
      reuse_mode: "file_backed",
      workspace_relative_path: "inputs/fixture.mp4",
      media_type: "video/mp4",
      size_bytes: fixtureSize,
      sha256
    }]
  });
  const openClawOptions: NormalizedOpenClawProviderOptions = {
    execution_mode: "read_only",
    staged_inputs: [{
      input_id: artifactId,
      source_kind: "artifact",
      source_ref: { artifact_id: artifactId },
      display_name: "fixture.mp4",
      media_type: "video/mp4",
      encoding: "binary",
      content_sha256: sha256,
      size_bytes: fixtureSize,
      workspace_relative_path: "inputs/fixture.mp4"
    }],
    expected_outputs: []
  };
  const openClawPrompt = buildOpenClawPrompt({
    request: openClawRequest,
    workspaceRoot: "/home/openclaw/.openclaw/workspace/runs/execution_smoke",
    options: openClawOptions
  });
  assert.doesNotMatch(codexPrompt, new RegExp(sourcePath.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"));
  assert.doesNotMatch(openClawPrompt, /[A-Z]:\\|\/mnt\/[a-z]\//i);
  assert.match(codexPrompt, /inputs\/fixture\.mp4/);
  assert.match(openClawPrompt, /\/runs\/execution_smoke\/inputs\/fixture\.mp4/);
  console.log(`Agent input smoke passed: ${artifactId} (${fixtureSize} bytes)`);
} finally {
  await fs.rm(root, { recursive: true, force: true });
}
