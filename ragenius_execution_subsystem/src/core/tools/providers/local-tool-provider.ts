import fs from "node:fs/promises";
import path from "node:path";

import { AppError } from "../../errors/app-error.js";

import type { ToolDefinition } from "../tool.types.js";
import { ArtifactStore } from "./artifact-store.js";
import { FilePolicy } from "./file-policy.js";

function applyUnifiedDiff(original: string, patch: string): string {
  const originalLines = original.split("\n");
  const patchLines = patch.replace(/\r\n/g, "\n").split("\n");
  const result: string[] = [];

  let originalIndex = 0;
  let patchIndex = 0;
  while (patchIndex < patchLines.length && !patchLines[patchIndex]?.startsWith("@@")) {
    patchIndex += 1;
  }

  if (patchIndex >= patchLines.length) {
    throw new AppError({
      code: "PATCH_INVALID",
      message: "Patch is not a supported unified diff.",
      errorClass: "validation",
      httpStatus: 400,
      recoverable: true,
      suggestedAction: "Provide a supported unified diff patch."
    });
  }

  while (patchIndex < patchLines.length) {
    const header = patchLines[patchIndex] ?? "";
    const match = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(header);
    if (!match) {
      throw new AppError({
        code: "PATCH_INVALID",
        message: "Patch hunk header is invalid.",
        errorClass: "validation",
        httpStatus: 400,
        recoverable: true,
        suggestedAction: "Provide a valid unified diff patch."
      });
    }

    const startOld = Number(match[1]) - 1;
    result.push(...originalLines.slice(originalIndex, startOld));
    originalIndex = startOld;
    patchIndex += 1;

    while (patchIndex < patchLines.length && !patchLines[patchIndex]?.startsWith("@@")) {
      const line = patchLines[patchIndex] ?? "";
      if (line === "" && patchIndex === patchLines.length - 1) {
        patchIndex += 1;
        continue;
      }
      if (line.startsWith("\\")) {
        patchIndex += 1;
        continue;
      }
      const marker = line[0];
      const content = line.slice(1);
      if (marker === " ") {
        if (originalLines[originalIndex] !== content) {
          throw new AppError({
            code: "PATCH_APPLY_FAILED",
            message: "Patch context did not match the target file.",
            errorClass: "validation",
            httpStatus: 400,
            recoverable: true,
            suggestedAction: "Refresh the file content and generate a new patch."
          });
        }
        result.push(content);
        originalIndex += 1;
      } else if (marker === "-") {
        if (originalLines[originalIndex] !== content) {
          throw new AppError({
            code: "PATCH_APPLY_FAILED",
            message: "Patch removal did not match the target file.",
            errorClass: "validation",
            httpStatus: 400,
            recoverable: true,
            suggestedAction: "Refresh the file content and generate a new patch."
          });
        }
        originalIndex += 1;
      } else if (marker === "+") {
        result.push(content);
      } else {
        throw new AppError({
          code: "PATCH_INVALID",
          message: "Patch line is not supported.",
          errorClass: "validation",
          httpStatus: 400,
          recoverable: true,
          suggestedAction: "Provide a valid unified diff patch."
        });
      }
      patchIndex += 1;
    }
  }

  result.push(...originalLines.slice(originalIndex));
  return result.join("\n");
}

export class PhaseOneLocalToolProvider {
  readonly providerType = "local" as const;

  constructor(
    private readonly filePolicy: FilePolicy,
    private readonly artifactStore: ArtifactStore
  ) {}

  async execute(
    tool: ToolDefinition,
    input: Record<string, unknown>,
    options?: {
      appId: string;
      sessionId?: string;
      confirmed?: boolean;
      executionId?: string | null;
      skillId?: string;
    }
  ): Promise<Record<string, unknown>> {
    if (tool.id === "read_file") {
      const resolved = this.filePolicy.resolveReadablePath(
        String(input.path ?? "")
      );
      const raw = await fs.readFile(resolved, "utf-8");
      const maxBytes = Number(input.max_bytes ?? 65536);
      const content = raw.slice(0, maxBytes);
      return {
        path: resolved,
        content,
        truncated: raw.length > content.length,
        size_bytes: Buffer.byteLength(raw, "utf-8")
      };
    }

    if (tool.id === "list_files") {
      const resolved = this.filePolicy.resolveReadablePath(
        String(input.path ?? "")
      );
      const includeDirs = input.include_dirs === true;
      const recursive = input.recursive === true;
      const maxDepth = Number(input.depth ?? (recursive ? 10 : 1));
      const entries: Array<Record<string, unknown>> = [];

      const walk = async (currentPath: string, currentDepth: number) => {
        if (currentDepth > maxDepth) {
          return;
        }
        for (const dirent of await fs.readdir(currentPath, {
          withFileTypes: true
        })) {
          const fullPath = path.join(currentPath, dirent.name);
          const stat = await fs.stat(fullPath);
          if (dirent.isDirectory()) {
            if (includeDirs) {
              entries.push({
                path: fullPath,
                name: dirent.name,
                type: "directory",
                modified_at: stat.mtime.toISOString()
              });
            }
            if (recursive || currentDepth < maxDepth) {
              await walk(fullPath, currentDepth + 1);
            }
          } else {
            entries.push({
              path: fullPath,
              name: dirent.name,
              type: "file",
              size_bytes: stat.size,
              modified_at: stat.mtime.toISOString()
            });
          }
        }
      };

      await walk(resolved, 1);
      return {
        path: resolved,
        entries
      };
    }

    if (tool.id === "save_artifact") {
      return this.artifactStore.save(
        options?.appId ?? "app_local",
        String(input.artifact_type ?? "artifact"),
        String(input.name ?? "artifact"),
        input.content ?? {},
        {
          ...(typeof input.display_name === "string" && input.display_name.trim().length > 0
            ? { displayName: input.display_name.trim() }
            : {}),
          ...(typeof options?.sessionId === "string"
            ? { sessionId: options.sessionId }
            : {}),
          ...(typeof options?.executionId === "string"
            ? { executionId: options.executionId }
            : {}),
          sourceToolId: tool.id,
          ...(typeof options?.skillId === "string"
            ? { sourceSkillId: options.skillId }
            : {}),
          ...(input.reviewed === true ? { reviewed: true } : {}),
          ...(typeof input.reviewed_at === "string" && input.reviewed_at.trim().length > 0
            ? { reviewedAt: input.reviewed_at.trim() }
            : {}),
          ...(typeof input.reviewed_by === "string" && input.reviewed_by.trim().length > 0
            ? { reviewedBy: input.reviewed_by.trim() }
            : {}),
          ...(typeof input.review_source === "string" && input.review_source.trim().length > 0
            ? { reviewSource: input.review_source.trim() }
            : {}),
          ...(Array.isArray(input.source_message_ids)
            ? { sourceMessageIds: input.source_message_ids.map((value) => String(value || "").trim()).filter(Boolean) }
            : {}),
          ...(typeof input.content_hash === "string" && input.content_hash.trim().length > 0
            ? { contentHash: input.content_hash.trim() }
            : {})
        }
      );
    }

    if (tool.id === "load_artifact") {
      return this.artifactStore.load(
        options?.appId ?? "app_local",
        String(input.artifact_id ?? "")
      );
    }

    if (tool.id === "write_file") {
      const resolved = await this.filePolicy.assertExistingWritableTextFile(
        String(input.path ?? "")
      );
      const content = String(input.content ?? "");
      if (Buffer.byteLength(content, "utf-8") > this.filePolicy.maxWriteBytes) {
        throw new AppError({
          code: "FILESYSTEM_WRITE_TOO_LARGE",
          message: "Write content exceeds configured maximum size.",
          errorClass: "validation",
          httpStatus: 400,
          recoverable: true,
          suggestedAction: "Reduce the file content size."
        });
      }
      await fs.writeFile(resolved, content, "utf-8");
      return {
        path: resolved,
        bytes_written: Buffer.byteLength(content, "utf-8"),
        updated: true
      };
    }

    if (tool.id === "patch_file") {
      const resolved = await this.filePolicy.assertExistingWritableTextFile(
        String(input.path ?? "")
      );
      const patch = String(input.patch ?? "");
      if (Buffer.byteLength(patch, "utf-8") > this.filePolicy.maxPatchBytes) {
        throw new AppError({
          code: "FILESYSTEM_PATCH_TOO_LARGE",
          message: "Patch content exceeds configured maximum size.",
          errorClass: "validation",
          httpStatus: 400,
          recoverable: true,
          suggestedAction: "Reduce the patch size."
        });
      }
      const raw = await fs.readFile(resolved, "utf-8");
      const next = applyUnifiedDiff(raw, patch);
      await fs.writeFile(resolved, next, "utf-8");
      return {
        path: resolved,
        updated: true,
        summary: "Patched file successfully."
      };
    }

    throw new AppError({
      code: "LOCAL_TOOL_NOT_IMPLEMENTED",
      message: "Local tool is not implemented.",
      errorClass: "tool",
      httpStatus: 502,
      details: { tool_id: tool.id },
      recoverable: false,
      suggestedAction: "Register the required local tool implementation."
    });
  }
}
