import { createHash, randomUUID } from "node:crypto";
import fs from "node:fs/promises";
import { createWriteStream } from "node:fs";
import path from "node:path";
import { Readable, Transform } from "node:stream";
import { pipeline } from "node:stream/promises";

import { AppError } from "../errors/app-error.js";
import {
  ArtifactStore,
  type StoredArtifactRecord
} from "../tools/providers/artifact-store.js";

export type SessionUploadArtifactImportInput = {
  appId: string;
  sessionId: string;
  sourceUploadId: string;
  displayName: string;
  mimeType?: string;
  declaredSizeBytes: number;
  declaredSha256: string;
  stream: NodeJS.ReadableStream;
};

export type SessionUploadArtifactImportResult = {
  artifact: Omit<StoredArtifactRecord, "content">;
  reusedExistingArtifact: boolean;
};

export type SessionUploadArtifactImporterOptions = {
  artifactRootDir: string;
  maxBytes: number;
  allowedMimeTypes: string[];
  tempRetentionHours: number;
};

function importError(input: {
  code: string;
  message: string;
  httpStatus: number;
  suggestedAction: string;
}): AppError {
  return new AppError({
    ...input,
    errorClass: "validation",
    recoverable: true
  });
}

function normalizeSha256(value: string): string {
  return String(value || "").trim().toLowerCase();
}

function normalizeMimeType(value: string | undefined): string {
  return String(value || "application/octet-stream")
    .split(";", 1)[0]!
    .trim()
    .toLowerCase();
}

function assertSafeIdentifier(value: string, label: string): string {
  const normalized = String(value || "").trim();
  if (!normalized || !/^[A-Za-z0-9._-]+$/.test(normalized)) {
    throw importError({
      code: "EXECUTION_INPUT_INTEGRITY_MISMATCH",
      message: `${label} is invalid.`,
      httpStatus: 400,
      suggestedAction: "Retry with a valid session upload reference."
    });
  }
  return normalized;
}

export class SessionUploadArtifactImporter {
  private readonly locks = new Map<string, Promise<void>>();

  constructor(
    private readonly artifactStore: ArtifactStore,
    private readonly options: SessionUploadArtifactImporterOptions
  ) {}

  private tempRoot(): string {
    return path.resolve(this.options.artifactRootDir, ".session-upload-imports");
  }

  private async withLock<T>(key: string, operation: () => Promise<T>): Promise<T> {
    const previous = this.locks.get(key) ?? Promise.resolve();
    let release!: () => void;
    const current = new Promise<void>((resolve) => {
      release = resolve;
    });
    const queued = previous.then(() => current);
    this.locks.set(key, queued);
    await previous;
    try {
      return await operation();
    } finally {
      release();
      if (this.locks.get(key) === queued) {
        this.locks.delete(key);
      }
    }
  }

  async import(input: SessionUploadArtifactImportInput): Promise<SessionUploadArtifactImportResult> {
    const appId = assertSafeIdentifier(input.appId, "appId");
    const sessionId = assertSafeIdentifier(input.sessionId, "sessionId");
    const sourceUploadId = assertSafeIdentifier(input.sourceUploadId, "sourceUploadId");
    const declaredSha256 = normalizeSha256(input.declaredSha256);
    const mimeType = normalizeMimeType(input.mimeType);

    if (!/^sha256:[0-9a-f]{64}$/.test(declaredSha256) || !Number.isSafeInteger(input.declaredSizeBytes) || input.declaredSizeBytes < 0) {
      throw importError({
        code: "EXECUTION_INPUT_INTEGRITY_MISMATCH",
        message: "Declared execution input size or SHA-256 is invalid.",
        httpStatus: 400,
        suggestedAction: "Recalculate the upload size and SHA-256, then retry."
      });
    }
    if (input.declaredSizeBytes > this.options.maxBytes) {
      throw importError({
        code: "EXECUTION_INPUT_TOO_LARGE",
        message: "Execution input exceeds the configured maximum size.",
        httpStatus: 413,
        suggestedAction: "Choose a smaller file or increase the configured Agent input limit."
      });
    }
    const allowedMimeTypes = new Set(this.options.allowedMimeTypes.map(normalizeMimeType));
    if (!allowedMimeTypes.has(mimeType)) {
      throw importError({
        code: "EXECUTION_INPUT_MEDIA_TYPE_NOT_ALLOWED",
        message: `Execution input media type is not allowed: ${mimeType}`,
        httpStatus: 415,
        suggestedAction: "Choose a file with an allowed media type."
      });
    }

    const lockKey = `${appId}\u0000${sessionId}\u0000${sourceUploadId}`;
    return this.withLock(lockKey, async () => {
      const existing = await this.artifactStore.findSessionUploadImport({
        appId,
        sessionId,
        sourceUploadId
      });
      if (existing) {
        if (
          existing.content_hash !== declaredSha256 ||
          existing.size_bytes !== input.declaredSizeBytes ||
          normalizeMimeType(String(existing.mime_type || "")) !== mimeType
        ) {
          throw importError({
            code: "SESSION_UPLOAD_CONTENT_CONFLICT",
            message: "The session upload id is already associated with different content.",
            httpStatus: 409,
            suggestedAction: "Use a new upload id for the changed file."
          });
        }
        if (input.stream instanceof Readable) {
          input.stream.resume();
        }
        return { artifact: existing, reusedExistingArtifact: true };
      }

      const tempRoot = this.tempRoot();
      await fs.mkdir(tempRoot, { recursive: true });
      const tempPath = path.join(tempRoot, `${randomUUID()}.tmp`);
      const hash = createHash("sha256");
      let sizeBytes = 0;
      const verifier = new Transform({
        transform: (chunk: Buffer | string, encoding, callback) => {
          const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk, encoding);
          sizeBytes += bytes.byteLength;
          if (sizeBytes > this.options.maxBytes) {
            callback(importError({
              code: "EXECUTION_INPUT_TOO_LARGE",
              message: "Execution input exceeds the configured maximum size.",
              httpStatus: 413,
              suggestedAction: "Choose a smaller file or increase the configured Agent input limit."
            }));
            return;
          }
          hash.update(bytes);
          callback(null, bytes);
        }
      });

      try {
        await pipeline(
          input.stream as Readable,
          verifier,
          createWriteStream(tempPath, { flags: "wx" })
        );
        if ((input.stream as NodeJS.ReadableStream & { truncated?: boolean }).truncated === true) {
          throw importError({
            code: "EXECUTION_INPUT_TOO_LARGE",
            message: "Execution input exceeds the configured maximum size.",
            httpStatus: 413,
            suggestedAction: "Choose a smaller file or increase the configured Agent input limit."
          });
        }
        const actualSha256 = `sha256:${hash.digest("hex")}`;
        if (sizeBytes !== input.declaredSizeBytes || actualSha256 !== declaredSha256) {
          throw importError({
            code: "EXECUTION_INPUT_INTEGRITY_MISMATCH",
            message: "Execution input bytes do not match the declared size or SHA-256.",
            httpStatus: 422,
            suggestedAction: "Upload the file again and retry preparation."
          });
        }

        const contentLockKey = [
          "content",
          appId,
          sessionId,
          actualSha256,
          String(sizeBytes),
          mimeType
        ].join("\u0000");
        return await this.withLock(contentLockKey, async () => {
          const canonical = await this.artifactStore.findReadyByContentIdentity({
            appId,
            sessionId,
            sha256: actualSha256,
            sizeBytes,
            mediaType: mimeType
          });
          if (canonical) {
            return { artifact: canonical, reusedExistingArtifact: true };
          }

          const artifact = await this.artifactStore.save(
            appId,
            "session_upload",
            input.displayName,
            { source_upload_id: sourceUploadId },
            {
              sessionId,
              displayName: input.displayName,
              providerOrigin: "session_upload",
              sourceUploadId,
              mimeType,
              contentHash: actualSha256,
              fileSourcePath: tempPath,
              moveFileSource: true
            }
          );
          return { artifact, reusedExistingArtifact: false };
        });
      } finally {
        await fs.rm(tempPath, { force: true }).catch(() => undefined);
      }
    });
  }

  async cleanupExpiredTemporaryFiles(): Promise<void> {
    const tempRoot = this.tempRoot();
    let entries: string[];
    try {
      entries = await fs.readdir(tempRoot);
    } catch (error) {
      if (error && typeof error === "object" && "code" in error && error.code === "ENOENT") {
        return;
      }
      throw error;
    }
    const cutoff = Date.now() - this.options.tempRetentionHours * 60 * 60 * 1000;
    await Promise.all(entries.map(async (entry) => {
      const candidate = path.join(tempRoot, entry);
      const stat = await fs.lstat(candidate);
      if (stat.isFile() && stat.mtimeMs < cutoff) {
        await fs.rm(candidate, { force: true });
      }
    }));
  }
}
