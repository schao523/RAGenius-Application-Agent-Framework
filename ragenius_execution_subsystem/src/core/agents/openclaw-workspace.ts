import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";

import type {
  OpenClawExpectedOutput,
  OpenClawStagedInput,
  OpenClawVerificationResult
} from "./openclaw-cli-types.js";
import type { ResolvedAgentArtifact } from "./agent-artifact-resolver.js";

export type OpenClawFileInspection = {
  exists: boolean;
  size_bytes?: number;
  sha256?: string;
};

export type OpenClawInspectFile = (
  workspaceAbsolutePath: string
) => Promise<OpenClawFileInspection>;

export type VerifyOpenClawOutputsInput = {
  workspaceRoot: string;
  expectedOutputs: OpenClawExpectedOutput[];
  inspectFile: OpenClawInspectFile;
};

export type StageFileResult = {
  input_id: string;
  workspace_relative_path: string;
  workspace_absolute_path: string;
  size_bytes: number;
  sha256: string;
};

export type StageBinaryInput = {
  inputId: string;
  bytes: Buffer;
  workspaceRoot: string;
  workspaceRelativePath: string;
  transfer: (input: {
    base64Chunks: string[];
    workspaceAbsolutePath: string;
    expectedSizeBytes: number;
    expectedSha256: string;
  }) => Promise<OpenClawFileInspection>;
};

export type StageResolvedAgentArtifactsInput = {
  workspaceRoot: string;
  artifacts: ResolvedAgentArtifact[];
  transfer: StageBinaryInput["transfer"];
};

export function assertSafeWorkspaceRelativePath(value: string): string {
  const normalized = value.replace(/\\/g, "/").trim();
  if (
    !normalized ||
    normalized.startsWith("/") ||
    /^[A-Za-z]:\//.test(normalized) ||
    normalized.split("/").includes("..")
  ) {
    throw new Error(`Unsafe OpenClaw workspace-relative path: ${value}`);
  }
  return normalized;
}

export function buildWorkspaceAbsolutePath(root: string, relativePath: string): string {
  const safeRelativePath = assertSafeWorkspaceRelativePath(relativePath);
  return `${root.replace(/\/+$/, "")}/${safeRelativePath}`;
}

export async function verifyOpenClawOutputs(
  input: VerifyOpenClawOutputsInput
): Promise<OpenClawVerificationResult[]> {
  return Promise.all(
    input.expectedOutputs.map(async (output) => {
      const relativePath =
        output.workspace_relative_path ??
        `outputs/${output.output_id}-${output.display_name}`;
      const safeRelativePath = assertSafeWorkspaceRelativePath(relativePath);
      const absolutePath = buildWorkspaceAbsolutePath(
        input.workspaceRoot,
        safeRelativePath
      );
      try {
        const inspected = await input.inspectFile(absolutePath);
        if (!inspected.exists) {
          return failedVerification({
            output,
            safeRelativePath,
            absolutePath,
            failureCode: "missing_output",
            failureMessage: "Required output was not created."
          });
        }
        if (
          typeof output.min_size_bytes === "number" &&
          typeof inspected.size_bytes === "number" &&
          inspected.size_bytes < output.min_size_bytes
        ) {
          return failedVerification({
            output,
            safeRelativePath,
            absolutePath,
            inspected,
            failureCode: "size_below_minimum",
            failureMessage: "Output file is smaller than the required size."
          });
        }
        if (
          output.expected_sha256 &&
          inspected.sha256 &&
          output.expected_sha256 !== inspected.sha256
        ) {
          return failedVerification({
            output,
            safeRelativePath,
            absolutePath,
            inspected,
            failureCode: "hash_mismatch",
            failureMessage: "Output hash did not match expected SHA-256."
          });
        }
        return {
          output_id: output.output_id,
          workspace_relative_path: safeRelativePath,
          workspace_absolute_path: absolutePath,
          required: output.required,
          exists: true,
          verified: true,
          ...(typeof inspected.size_bytes === "number"
            ? { size_bytes: inspected.size_bytes }
            : {}),
          ...(inspected.sha256 ? { sha256: inspected.sha256 } : {}),
          media_type: output.media_type
        };
      } catch (error) {
        return failedVerification({
          output,
          safeRelativePath,
          absolutePath,
          failureCode: "read_failed",
          failureMessage:
            error instanceof Error ? error.message : "Output inspection failed."
        });
      }
    })
  );
}

export async function stageBinaryInputWithVerifiedBase64(
  input: StageBinaryInput
): Promise<StageFileResult> {
  const safeRelativePath = assertSafeWorkspaceRelativePath(
    input.workspaceRelativePath
  );
  const workspaceAbsolutePath = buildWorkspaceAbsolutePath(
    input.workspaceRoot,
    safeRelativePath
  );
  const expectedSha256 = sha256Hex(input.bytes);
  const expectedSizeBytes = input.bytes.byteLength;
  const base64Chunks = chunkString(input.bytes.toString("base64"), 65536);
  const inspected = await input.transfer({
    base64Chunks,
    workspaceAbsolutePath,
    expectedSizeBytes,
    expectedSha256
  });

  if (!inspected.exists) {
    throw new Error("Binary staging failed: staged file does not exist.");
  }
  if (inspected.size_bytes !== expectedSizeBytes) {
    throw new Error("Binary staging failed: staged byte size mismatch.");
  }
  if (inspected.sha256 !== expectedSha256) {
    throw new Error("Binary staging failed: staged SHA-256 mismatch.");
  }

  return {
    input_id: input.inputId,
    workspace_relative_path: safeRelativePath,
    workspace_absolute_path: workspaceAbsolutePath,
    size_bytes: expectedSizeBytes,
    sha256: expectedSha256
  };
}

export async function stageResolvedAgentArtifactsForOpenClaw(
  input: StageResolvedAgentArtifactsInput
): Promise<OpenClawStagedInput[]> {
  const staged: OpenClawStagedInput[] = [];

  for (const artifact of input.artifacts) {
    const mediaType = artifact.payload.mime_type ?? "application/octet-stream";

    if (artifact.requested_reuse_mode === "metadata_only") {
      staged.push({
        input_id: artifact.artifact_id,
        source_kind: "artifact",
        source_ref: { artifact_id: artifact.artifact_id },
        display_name: artifact.display_name,
        media_type: mediaType,
        encoding: "utf8",
        metadata: artifact.payload.metadata
      });
      continue;
    }

    const bytes = await payloadBytesForArtifact(artifact);
    const workspaceRelativePath = `inputs/${artifact.artifact_id}-${sanitizeWorkspaceFileName(
      artifact.display_name
    )}`;
    const stagedFile = await stageBinaryInputWithVerifiedBase64({
      inputId: artifact.artifact_id,
      bytes,
      workspaceRoot: input.workspaceRoot,
      workspaceRelativePath,
      transfer: input.transfer
    });

    staged.push({
      input_id: artifact.artifact_id,
      source_kind: "artifact",
      source_ref: { artifact_id: artifact.artifact_id },
      display_name: artifact.display_name,
      media_type: mediaType,
      encoding: artifact.requested_reuse_mode === "inline_text" ? "utf8" : "binary",
      content_sha256: stagedFile.sha256,
      size_bytes: stagedFile.size_bytes,
      workspace_relative_path: stagedFile.workspace_relative_path,
      metadata: artifact.payload.metadata
    });
  }

  return staged;
}

export async function transferOpenClawInputViaWsl(input: {
  wslDistro: string;
  base64Chunks: string[];
  workspaceAbsolutePath: string;
  expectedSizeBytes: number;
  expectedSha256: string;
}): Promise<OpenClawFileInspection> {
  const script = buildOpenClawStageInputScript(input.workspaceAbsolutePath);
  await spawnWslText({
    wslDistro: input.wslDistro,
    args: ["bash", "-c", script],
    stdin: input.base64Chunks.join("")
  });

  return inspectOpenClawWorkspaceFileViaWsl({
    wslDistro: input.wslDistro,
    workspaceAbsolutePath: input.workspaceAbsolutePath
  });
}

export async function readOpenClawWorkspaceFileViaWsl(input: {
  wslDistro: string;
  workspaceAbsolutePath: string;
}): Promise<Buffer> {
  const result = await spawnWslText({
    wslDistro: input.wslDistro,
    args: ["bash", "-c", buildOpenClawReadFileScript(input.workspaceAbsolutePath)]
  });
  return Buffer.from(result.stdout.trim(), "base64");
}

export function buildOpenClawStageInputScript(
  workspaceAbsolutePath: string
): string {
  const safePath = shellQuoteWorkspaceAbsolutePath(workspaceAbsolutePath);
  return [
    "set -euo pipefail",
    `mkdir -p "$(dirname ${safePath})"`,
    `base64 -d > ${safePath}`
  ].join("; ");
}

export function buildOpenClawReadFileScript(workspaceAbsolutePath: string): string {
  const safePath = shellQuoteWorkspaceAbsolutePath(workspaceAbsolutePath);
  return [
    "set -euo pipefail",
    `base64 -w 0 ${safePath}`
  ].join("; ");
}

export async function inspectOpenClawWorkspaceFileViaWsl(input: {
  wslDistro: string;
  workspaceAbsolutePath: string;
}): Promise<OpenClawFileInspection> {
  const exists = await spawnWslText({
    wslDistro: input.wslDistro,
    args: ["test", "-f", input.workspaceAbsolutePath],
    allowNonZeroExit: true
  });
  if (exists.exitCode !== 0) {
    return { exists: false };
  }
  const size = await spawnWslText({
    wslDistro: input.wslDistro,
    args: ["wc", "-c", input.workspaceAbsolutePath]
  });
  const hash = await spawnWslText({
    wslDistro: input.wslDistro,
    args: ["sha256sum", input.workspaceAbsolutePath]
  });
  const sizeBytes = Number.parseInt(size.stdout.trim().split(/\s+/)[0] ?? "", 10);
  const sha256 = hash.stdout.trim().split(/\s+/)[0] ?? "";
  return {
    exists: true,
    ...(Number.isFinite(sizeBytes)
      ? { size_bytes: sizeBytes }
      : {}),
    ...(sha256 ? { sha256 } : {})
  };
}

function failedVerification(input: {
  output: OpenClawExpectedOutput;
  safeRelativePath: string;
  absolutePath: string;
  inspected?: OpenClawFileInspection;
  failureCode: NonNullable<OpenClawVerificationResult["failure_code"]>;
  failureMessage: string;
}): OpenClawVerificationResult {
  return {
    output_id: input.output.output_id,
    workspace_relative_path: input.safeRelativePath,
    workspace_absolute_path: input.absolutePath,
    required: input.output.required,
    exists: input.inspected?.exists ?? false,
    verified: false,
    ...(typeof input.inspected?.size_bytes === "number"
      ? { size_bytes: input.inspected.size_bytes }
      : {}),
    ...(input.inspected?.sha256 ? { sha256: input.inspected.sha256 } : {}),
    media_type: input.output.media_type,
    failure_code: input.failureCode,
    failure_message: input.failureMessage
  };
}

function sha256Hex(bytes: Buffer): string {
  return createHash("sha256").update(bytes).digest("hex");
}

function chunkString(value: string, chunkSize: number): string[] {
  const chunks: string[] = [];
  for (let index = 0; index < value.length; index += chunkSize) {
    chunks.push(value.slice(index, index + chunkSize));
  }
  return chunks;
}

async function spawnWslText(input: {
  wslDistro: string;
  args: string[];
  allowNonZeroExit?: boolean;
  stdin?: string;
}): Promise<{ exitCode: number | null; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn("wsl", ["-d", input.wslDistro, ...input.args], {
      windowsHide: true,
      stdio: [typeof input.stdin === "string" ? "pipe" : "ignore", "pipe", "pipe"]
    });
    const stdoutChunks: Buffer[] = [];
    const stderrChunks: Buffer[] = [];
    child.stdout?.on("data", (chunk: Buffer) => stdoutChunks.push(chunk));
    child.stderr?.on("data", (chunk: Buffer) => stderrChunks.push(chunk));
    child.on("error", reject);
    if (typeof input.stdin === "string" && child.stdin) {
      child.stdin.end(input.stdin);
    }
    child.on("close", (exitCode) => {
      const stdout = Buffer.concat(stdoutChunks).toString("utf8");
      const stderr = Buffer.concat(stderrChunks).toString("utf8");
      if (exitCode !== 0 && input.allowNonZeroExit !== true) {
        reject(
          new Error(
            `WSL file inspection failed with exit code ${exitCode}: ${stderr}`
          )
        );
        return;
      }
      resolve({ exitCode, stdout, stderr });
    });
  });
}

async function payloadBytesForArtifact(
  artifact: ResolvedAgentArtifact
): Promise<Buffer> {
  if (typeof artifact.payload.text_content === "string") {
    return Buffer.from(artifact.payload.text_content, "utf-8");
  }

  if (typeof artifact.payload.binary_content_base64 === "string") {
    return Buffer.from(artifact.payload.binary_content_base64, "base64");
  }

  if (typeof artifact.payload.file_path === "string") {
    return fs.readFile(artifact.payload.file_path);
  }

  throw new Error(
    `Resolved artifact ${artifact.artifact_id} does not contain reusable bytes.`
  );
}

function sanitizeWorkspaceFileName(value: string): string {
  const baseName = path.basename(String(value || "").trim()) || "artifact";
  return baseName.replace(/[<>:"/\\|?*\u0000-\u001F]/g, "-").trim() || "artifact";
}

function shellQuoteWorkspaceAbsolutePath(value: string): string {
  const normalized = String(value || "").trim();
  if (!normalized || !normalized.startsWith("/") || normalized.includes("\0")) {
    throw new Error(`Unsafe OpenClaw workspace-absolute path: ${value}`);
  }
  return `'${normalized.replace(/'/g, "'\\''")}'`;
}
