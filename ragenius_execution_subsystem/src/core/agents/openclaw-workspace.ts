import { createHash } from "node:crypto";
import { spawn } from "node:child_process";

import type {
  OpenClawExpectedOutput,
  OpenClawVerificationResult
} from "./openclaw-cli-types.js";

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
}): Promise<{ exitCode: number | null; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn("wsl", ["-d", input.wslDistro, ...input.args], {
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"]
    });
    const stdoutChunks: Buffer[] = [];
    const stderrChunks: Buffer[] = [];
    child.stdout.on("data", (chunk: Buffer) => stdoutChunks.push(chunk));
    child.stderr.on("data", (chunk: Buffer) => stderrChunks.push(chunk));
    child.on("error", reject);
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
