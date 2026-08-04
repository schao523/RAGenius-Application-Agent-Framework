import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

import type { ResolvedAgentArtifact } from "./agent-artifact-resolver.js";
import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";
import {
  planAgentExpectedOutputs,
  type PlannedAgentExpectedOutput
} from "./agent-expected-output-planner.js";
import type {
  CodexCliArtifactSummary,
  CodexOutputVerification,
  CodexStagedArtifact
} from "./codex-cli-types.js";

export type CodexRunWorkspace = {
  root_absolute_path: string;
  inputs_absolute_path: string;
  outputs_absolute_path: string;
};

export type CodexPlannedExpectedOutput = PlannedAgentExpectedOutput & {
  workspace_relative_path: string;
};

function assertSafeExecutionId(executionId: string): string {
  const normalized = executionId.trim();
  if (!/^[A-Za-z0-9_-]+$/.test(normalized)) {
    throw new Error(`Unsafe Codex execution id: ${executionId}`);
  }
  return normalized;
}

function assertContained(root: string, candidate: string): string {
  const resolvedRoot = path.resolve(root);
  const resolvedCandidate = path.resolve(candidate);
  if (
    resolvedCandidate !== resolvedRoot &&
    !resolvedCandidate.startsWith(`${resolvedRoot}${path.sep}`)
  ) {
    throw new Error("Codex workspace path resolves outside the current run.");
  }
  return resolvedCandidate;
}

function safeFileName(value: string): string {
  const baseName = path.basename(value.trim()) || "artifact";
  const withoutControls = Array.from(baseName, (character) =>
    character.charCodeAt(0) < 32 ? "-" : character
  ).join("");
  return withoutControls.replace(/[<>:"/\\|?*]/g, "-").trim() || "artifact";
}

function safeArtifactId(value: string): string {
  const normalized = value.replace(/[^A-Za-z0-9_-]/g, "-");
  return normalized || "artifact";
}

export function planCodexExpectedOutputs(
  request: ExecuteAgentRequest
): CodexPlannedExpectedOutput[] {
  return planAgentExpectedOutputs({ request }).map((output) => ({
    ...output,
    workspace_relative_path:
      `outputs/${safeArtifactId(output.output_id)}-${safeFileName(output.display_name)}`
  }));
}

function stagedRole(
  role: ResolvedAgentArtifact["role"]
): CodexStagedArtifact["role"] {
  return role === "template" ? "reference" : role;
}

async function artifactBytes(artifact: ResolvedAgentArtifact): Promise<Buffer> {
  if (artifact.requested_reuse_mode === "inline_text") {
    if (typeof artifact.payload.text_content !== "string") {
      throw new Error(`Artifact ${artifact.artifact_id} has no inline text.`);
    }
    return Buffer.from(artifact.payload.text_content, "utf8");
  }
  if (artifact.requested_reuse_mode === "binary_payload") {
    if (typeof artifact.payload.binary_content_base64 !== "string") {
      throw new Error(`Artifact ${artifact.artifact_id} has no binary payload.`);
    }
    return Buffer.from(artifact.payload.binary_content_base64, "base64");
  }
  if (artifact.requested_reuse_mode === "file_backed") {
    const sourcePath = artifact.payload.file_path;
    if (!sourcePath) {
      throw new Error(`Artifact ${artifact.artifact_id} has no file path.`);
    }
    const sourceStat = await fs.lstat(sourcePath);
    if (sourceStat.isSymbolicLink()) {
      throw new Error(`Artifact ${artifact.artifact_id} source is a symlink.`);
    }
    if (!sourceStat.isFile()) {
      throw new Error(`Artifact ${artifact.artifact_id} source is not a file.`);
    }
    return fs.readFile(sourcePath);
  }
  throw new Error(`Artifact ${artifact.artifact_id} has no reusable bytes.`);
}

function declaredNumber(metadata: Record<string, unknown>, key: string): number | undefined {
  const value = metadata[key];
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function declaredString(metadata: Record<string, unknown>, key: string): string | undefined {
  const value = metadata[key];
  return typeof value === "string" && value.trim() ? value.trim().toLowerCase() : undefined;
}

export async function createCodexRunWorkspace(input: {
  runRoot: string;
  executionId: string;
}): Promise<CodexRunWorkspace> {
  const executionId = assertSafeExecutionId(input.executionId);
  const root = assertContained(input.runRoot, path.join(input.runRoot, executionId));
  const inputs = assertContained(root, path.join(root, "inputs"));
  const outputs = assertContained(root, path.join(root, "outputs"));
  await fs.mkdir(inputs, { recursive: true });
  await fs.mkdir(outputs, { recursive: true });
  return {
    root_absolute_path: root,
    inputs_absolute_path: inputs,
    outputs_absolute_path: outputs
  };
}

export async function stageCodexArtifacts(input: {
  workspace: CodexRunWorkspace;
  artifacts: ResolvedAgentArtifact[];
}): Promise<CodexStagedArtifact[]> {
  const staged: CodexStagedArtifact[] = [];
  for (const artifact of input.artifacts) {
    const base: CodexStagedArtifact = {
      artifact_id: artifact.artifact_id,
      role: stagedRole(artifact.role),
      reuse_mode: artifact.requested_reuse_mode,
      display_name: artifact.display_name,
      ...(artifact.payload.mime_type
        ? { media_type: artifact.payload.mime_type }
        : {})
    };
    if (artifact.requested_reuse_mode === "metadata_only") {
      staged.push(base);
      continue;
    }

    const relativePath = `inputs/${safeArtifactId(artifact.artifact_id)}-${safeFileName(artifact.display_name)}`;
    const destination = assertContained(
      input.workspace.root_absolute_path,
      path.join(input.workspace.root_absolute_path, ...relativePath.split("/"))
    );
    const bytes = await artifactBytes(artifact);
    await fs.writeFile(destination, bytes, { flag: "wx" });
    const written = await fs.readFile(destination);
    const sizeBytes = written.byteLength;
    const sha256 = createHash("sha256").update(written).digest("hex");
    const expectedSize = declaredNumber(artifact.payload.metadata, "size_bytes");
    const expectedHash = declaredString(artifact.payload.metadata, "sha256");
    if (expectedSize !== undefined && expectedSize !== sizeBytes) {
      throw new Error(`Artifact ${artifact.artifact_id} staged size does not match.`);
    }
    if (expectedHash && expectedHash !== sha256) {
      throw new Error(`Artifact ${artifact.artifact_id} staged hash does not match.`);
    }
    staged.push({
      ...base,
      size_bytes: sizeBytes,
      sha256,
      workspace_relative_path: relativePath
    });
  }
  return staged;
}

function reportedOutputFor(
  expected: PlannedAgentExpectedOutput,
  reportedArtifacts: CodexCliArtifactSummary[],
  index: number
): CodexCliArtifactSummary | undefined {
  return (
    reportedArtifacts.find((artifact) => artifact.output_id === expected.output_id) ??
    (reportedArtifacts.length === 1 ? reportedArtifacts[0] : reportedArtifacts[index])
  );
}

function safeOutputPath(workspace: CodexRunWorkspace, value: string): {
  relativePath: string;
  absolutePath: string;
} {
  const relativePath = value.trim().replaceAll("\\", "/");
  if (
    !relativePath.startsWith("outputs/") ||
    path.isAbsolute(relativePath) ||
    relativePath.split("/").some((segment) => segment === "..")
  ) {
    throw new Error("Codex output path must remain inside the outputs directory.");
  }
  return {
    relativePath,
    absolutePath: assertContained(
      workspace.outputs_absolute_path,
      path.join(workspace.root_absolute_path, ...relativePath.split("/"))
    )
  };
}

export async function verifyCodexOutputArtifacts(input: {
  workspace: CodexRunWorkspace;
  expectedOutputs: Array<PlannedAgentExpectedOutput | CodexPlannedExpectedOutput>;
  reportedArtifacts: CodexCliArtifactSummary[];
}): Promise<CodexOutputVerification[]> {
  const outputRoot = await fs.realpath(input.workspace.outputs_absolute_path);
  return Promise.all(input.expectedOutputs.map(async (expected, index) => {
    const reported = reportedOutputFor(expected, input.reportedArtifacts, index);
    const plannedPath = "workspace_relative_path" in expected
      ? expected.workspace_relative_path
      : reported?.path;
    if (!plannedPath) {
      return {
        output_id: expected.output_id,
        display_name: expected.display_name,
        media_type: expected.media_type,
        workspace_relative_path: "",
        workspace_absolute_path: "",
        required: expected.required,
        exists: false,
        verified: false,
        failure_code: "missing_output" as const,
        failure_message: "Codex did not report a workspace output path."
      };
    }
    const resolved = safeOutputPath(input.workspace, plannedPath);
    try {
      const stat = await fs.lstat(resolved.absolutePath);
      if (stat.isSymbolicLink() || !stat.isFile()) {
        throw new Error("Codex output is not a regular file.");
      }
      const realPath = await fs.realpath(resolved.absolutePath);
      assertContained(outputRoot, realPath);
      const bytes = await fs.readFile(realPath);
      const sizeBytes = bytes.byteLength;
      const sha256 = createHash("sha256").update(bytes).digest("hex");
      const expectedHash = expected.expected_sha256?.toLowerCase();
      const reportedHash = reported?.sha256?.toLowerCase();
      const minimum = expected.min_size_bytes ?? 1;
      const base = {
        output_id: expected.output_id,
        display_name:
          reported?.display_name ??
          reported?.name ??
          expected.display_name ??
          path.basename(resolved.relativePath),
        media_type: reported?.media_type ?? expected.media_type,
        workspace_relative_path: resolved.relativePath,
        workspace_absolute_path: realPath,
        required: expected.required,
        exists: true,
        size_bytes: sizeBytes,
        sha256
      };
      if (sizeBytes < minimum) {
        return {
          ...base,
          verified: false,
          failure_code: (sizeBytes === 0 ? "empty_output" : "size_below_minimum") as "empty_output" | "size_below_minimum",
          failure_message: "Codex output is smaller than the required minimum."
        };
      }
      if ((expectedHash && expectedHash !== sha256) || (reportedHash && reportedHash !== sha256)) {
        return {
          ...base,
          verified: false,
          failure_code: "hash_mismatch" as const,
          failure_message: "Codex output hash does not match the declared value."
        };
      }
      if (
        typeof reported?.size_bytes === "number" &&
        reported.size_bytes !== sizeBytes
      ) {
        return {
          ...base,
          verified: false,
          failure_code: "read_failed" as const,
          failure_message: "Codex output size does not match the declared value."
        };
      }
      return { ...base, verified: true };
    } catch (error) {
      if (error && typeof error === "object" && "code" in error && error.code === "ENOENT") {
        return {
          output_id: expected.output_id,
          display_name: expected.display_name,
          media_type: expected.media_type,
          workspace_relative_path: resolved.relativePath,
          workspace_absolute_path: resolved.absolutePath,
          required: expected.required,
          exists: false,
          verified: false,
          failure_code: "missing_output" as const,
          failure_message: "Codex reported an output that does not exist."
        };
      }
      throw error;
    }
  }));
}

export async function cleanupCodexRunWorkspaces(input: {
  runRoot: string;
  currentExecutionId: string;
  retentionHours: number;
  now?: Date;
}): Promise<void> {
  const current = assertSafeExecutionId(input.currentExecutionId);
  if (!Number.isInteger(input.retentionHours) || input.retentionHours <= 0) {
    throw new Error("Codex run retention hours must be a positive integer.");
  }
  await fs.mkdir(input.runRoot, { recursive: true });
  const threshold = (input.now ?? new Date()).getTime() - input.retentionHours * 60 * 60 * 1000;
  for (const entry of await fs.readdir(input.runRoot, { withFileTypes: true })) {
    if (!entry.isDirectory() || entry.name === current) {
      continue;
    }
    const candidate = assertContained(input.runRoot, path.join(input.runRoot, entry.name));
    const stat = await fs.lstat(candidate);
    if (!stat.isSymbolicLink() && stat.mtimeMs < threshold) {
      await fs.rm(candidate, { recursive: true, force: true });
    }
  }
}
