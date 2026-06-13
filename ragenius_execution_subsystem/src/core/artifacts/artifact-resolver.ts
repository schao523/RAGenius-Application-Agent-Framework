import fs from "node:fs/promises";

import { AppError } from "../errors/app-error.js";
import type { StoredArtifactRecord } from "../tools/providers/artifact-store.js";
import type { ArtifactStore } from "../tools/providers/artifact-store.js";

import { getArtifactConsumerSpec } from "./artifact-consumption-registry.js";
import type {
  ArtifactConsumptionMode,
  ResolvedArtifact
} from "./artifact-consumption.types.js";

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function normalizeMetadata(content: unknown): Record<string, unknown> {
  if (isRecord(content)) {
    return content;
  }

  if (typeof content === "string") {
    return { content };
  }

  return {};
}

export class ArtifactResolver {
  constructor(private readonly artifactStore: ArtifactStore) {}

  async resolve(
    appId: string,
    artifactId: string,
    options?: {
      requiredMode?: ArtifactConsumptionMode;
    }
  ): Promise<ResolvedArtifact> {
    const artifact = await this.artifactStore.load(appId, artifactId);
    const spec = getArtifactConsumerSpec(artifact.artifact_type);

    if (!spec) {
      throw new AppError({
        code: "ARTIFACT_TYPE_UNSUPPORTED",
        message: "Artifact type is not supported for normalized consumption.",
        errorClass: "validation",
        httpStatus: 400,
        details: { artifact_id: artifactId, artifact_type: artifact.artifact_type },
        recoverable: true,
        suggestedAction: "Use a supported artifact type."
      });
    }

    const resolvedMode = options?.requiredMode ?? spec.default_consumption_mode;
    if (!spec.supported_consumption_modes.includes(resolvedMode)) {
      throw new AppError({
        code: "ARTIFACT_CONSUMPTION_MODE_UNSUPPORTED",
        message: "Artifact does not support the requested consumption mode.",
        errorClass: "validation",
        httpStatus: 400,
        details: {
          artifact_id: artifactId,
          artifact_type: artifact.artifact_type,
          required_mode: resolvedMode,
          supported_modes: spec.supported_consumption_modes
        },
        recoverable: true,
        suggestedAction: "Use a supported artifact consumption mode."
      });
    }

    const payload = await this.buildPayload(artifact, resolvedMode);

    return {
      artifact_id: artifact.artifact_id,
      artifact_type: artifact.artifact_type,
      display_name: artifact.display_name,
      ...(artifact.summary ? { summary: artifact.summary } : {}),
      app_id: artifact.app_id,
      status: artifact.status,
      consumption: {
        default_mode: spec.default_consumption_mode,
        supported_modes: spec.supported_consumption_modes,
        resolved_mode: resolvedMode
      },
      payload,
      provenance: {
        ...(artifact.created_by_execution_id
          ? { created_by_execution_id: artifact.created_by_execution_id }
          : {}),
        ...(artifact.created_by_turn_id
          ? { created_by_turn_id: artifact.created_by_turn_id }
          : {}),
        ...(artifact.source_tool_id ? { source_tool_id: artifact.source_tool_id } : {}),
        ...(artifact.source_skill_id ? { source_skill_id: artifact.source_skill_id } : {}),
        provider_origin: artifact.provider_origin
      }
    };
  }

  private async buildPayload(
    artifact: StoredArtifactRecord,
    mode: ArtifactConsumptionMode
  ): Promise<ResolvedArtifact["payload"]> {
    const metadata = normalizeMetadata(artifact.content);
    const mimeType =
      typeof artifact.mime_type === "string" && artifact.mime_type.length > 0
        ? artifact.mime_type
        : typeof metadata.mime_type === "string"
          ? metadata.mime_type
          : undefined;

    if (mode === "metadata_only") {
      return {
        ...(mimeType ? { mime_type: mimeType } : {}),
        metadata
      };
    }

    if (mode === "file_backed") {
      if (!artifact.file_path) {
        throw new AppError({
          code: "ARTIFACT_CONSUMPTION_UNAVAILABLE",
          message: "Artifact does not have a reusable file payload.",
          errorClass: "tool",
          httpStatus: 400,
          details: {
            artifact_id: artifact.artifact_id,
            artifact_type: artifact.artifact_type,
            required_mode: mode
          },
          recoverable: true,
          suggestedAction: "Use an artifact with a saved file payload."
        });
      }

      return {
        file_path: artifact.file_path,
        ...(mimeType ? { mime_type: mimeType } : {}),
        metadata
      };
    }

    if (mode === "inline_text") {
      const textContent = await this.resolveInlineText(artifact);
      if (typeof textContent !== "string") {
        throw new AppError({
          code: "ARTIFACT_CONSUMPTION_UNAVAILABLE",
          message: "Artifact does not have reusable inline text content.",
          errorClass: "tool",
          httpStatus: 400,
          details: {
            artifact_id: artifact.artifact_id,
            artifact_type: artifact.artifact_type,
            required_mode: mode
          },
          recoverable: true,
          suggestedAction: "Use an artifact with inline text content."
        });
      }

      return {
        text_content: textContent,
        ...(mimeType ? { mime_type: mimeType } : {}),
        metadata
      };
    }

    const binaryContent = await this.resolveBinaryPayload(artifact);
    if (typeof binaryContent !== "string") {
      throw new AppError({
        code: "ARTIFACT_CONSUMPTION_UNAVAILABLE",
        message: "Artifact does not have reusable binary payload content.",
        errorClass: "tool",
        httpStatus: 400,
        details: {
          artifact_id: artifact.artifact_id,
          artifact_type: artifact.artifact_type,
          required_mode: mode
        },
        recoverable: true,
        suggestedAction: "Use an artifact with reusable binary payload content."
      });
    }

    return {
      binary_content_base64: binaryContent,
      ...(mimeType ? { mime_type: mimeType } : {}),
      metadata
    };
  }

  private async resolveInlineText(
    artifact: StoredArtifactRecord
  ): Promise<string | undefined> {
    const metadata = normalizeMetadata(artifact.content);

    if (typeof metadata.content_markdown === "string") {
      return metadata.content_markdown;
    }

    if (typeof metadata.content === "string") {
      return metadata.content;
    }

    if (typeof artifact.content === "string") {
      return artifact.content;
    }

    if (artifact.file_path) {
      return fs.readFile(artifact.file_path, "utf-8");
    }

    return undefined;
  }

  private async resolveBinaryPayload(
    artifact: StoredArtifactRecord
  ): Promise<string | undefined> {
    const metadata = normalizeMetadata(artifact.content);
    const content = metadata.content;
    const encoding =
      typeof metadata.content_encoding === "string"
        ? String(metadata.content_encoding).toLowerCase()
        : "";

    if (typeof content === "string") {
      if (encoding === "base64") {
        return content;
      }

      return Buffer.from(content, "utf-8").toString("base64");
    }

    if (artifact.file_path) {
      const fileBuffer = await fs.readFile(artifact.file_path);
      return fileBuffer.toString("base64");
    }

    return undefined;
  }
}
