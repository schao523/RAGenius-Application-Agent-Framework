import fs from "node:fs/promises";
import path from "node:path";

import { AppError } from "../../errors/app-error.js";

export interface FileToolPolicyConfig {
  allowedRoots: string[];
  mutationRoots?: string[];
  maxReadBytes: number;
  maxWriteBytes?: number;
  maxPatchBytes?: number;
}

export class FilePolicy {
  constructor(private readonly config: FileToolPolicyConfig) {}

  resolveReadablePath(inputPath: string): string {
    const resolved = path.resolve(inputPath);
    const allowed = this.isAllowedUnderRoots(resolved, this.config.allowedRoots);

    if (!allowed) {
      throw new AppError({
        code: "FILESYSTEM_PATH_NOT_ALLOWED",
        message: "File path is outside allowed roots.",
        errorClass: "permission",
        httpStatus: 403,
        recoverable: true,
        details: { path: resolved },
        suggestedAction: "Use a path under a configured allowed root."
      });
    }

    return resolved;
  }

  resolveWritablePath(inputPath: string): string {
    const resolved = path.resolve(inputPath);
    const allowed = this.isAllowedUnderRoots(
      resolved,
      this.config.mutationRoots ?? []
    );

    if (!allowed) {
      throw new AppError({
        code: "FILESYSTEM_PATH_NOT_ALLOWED",
        message: "Filesystem path is outside configured mutation roots.",
        errorClass: "permission",
        httpStatus: 403,
        recoverable: false,
        details: { path: resolved },
        suggestedAction: "Use a path under a configured mutation root."
      });
    }

    return resolved;
  }

  async assertExistingWritableTextFile(inputPath: string): Promise<string> {
    const resolved = this.resolveWritablePath(inputPath);
    let stat;
    try {
      stat = await fs.stat(resolved);
    } catch {
      throw new AppError({
        code: "FILESYSTEM_TARGET_INVALID",
        message: "Mutation target must be an existing file.",
        errorClass: "validation",
        httpStatus: 400,
        recoverable: true,
        details: { path: resolved },
        suggestedAction: "Provide an existing file path within mutation roots."
      });
    }

    if (!stat.isFile()) {
      throw new AppError({
        code: "FILESYSTEM_TARGET_INVALID",
        message: "Mutation target must be an existing file.",
        errorClass: "validation",
        httpStatus: 400,
        recoverable: true,
        details: { path: resolved },
        suggestedAction: "Provide an existing file path within mutation roots."
      });
    }

    return resolved;
  }

  get maxWriteBytes(): number {
    return this.config.maxWriteBytes ?? 65536;
  }

  get maxPatchBytes(): number {
    return this.config.maxPatchBytes ?? 32768;
  }

  private isAllowedUnderRoots(resolvedPath: string, roots: string[]): boolean {
    return roots.some((root) => resolvedPath.startsWith(path.resolve(root)));
  }
}
