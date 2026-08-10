import type { FastifyPluginAsync, FastifyRequest } from "fastify";

import { hasServiceScope } from "../auth/service-auth.js";
import { AppError } from "../../core/errors/app-error.js";
import type { StoredArtifactRecord } from "../../core/tools/providers/artifact-store.js";

type MultipartField = { value?: unknown };

function routeError(input: {
  code: string;
  message: string;
  httpStatus: number;
  suggestedAction: string;
}): AppError {
  return new AppError({
    ...input,
    errorClass: input.httpStatus === 403 ? "permission" : "validation",
    recoverable: true
  });
}

function requireScope(request: FastifyRequest): void {
  if (!hasServiceScope(request, "artifacts:write")) {
    throw routeError({
      code: "SERVICE_SCOPE_REQUIRED",
      message: "The service credential does not grant artifact import access.",
      httpStatus: 403,
      suggestedAction: "Use a service credential with the artifacts:write scope."
    });
  }
}

function fieldValue(fields: Record<string, MultipartField>, name: string): string {
  const value = fields[name]?.value;
  const normalized = typeof value === "string" ? value.trim() : "";
  if (!normalized) {
    throw routeError({
      code: "INVALID_EXECUTION_INPUT_IMPORT",
      message: `Multipart field is required: ${name}`,
      httpStatus: 400,
      suggestedAction: "Send all required session upload metadata before the file part."
    });
  }
  return normalized;
}

function publicArtifact(artifact: Omit<StoredArtifactRecord, "content">): Record<string, unknown> {
  return {
    artifact_id: artifact.artifact_id,
    ...(artifact.session_id ? { session_id: artifact.session_id } : {}),
    artifact_type: artifact.artifact_type,
    display_name: artifact.display_name,
    ...(artifact.summary ? { summary: artifact.summary } : {}),
    app_id: artifact.app_id,
    created_at: artifact.created_at,
    ...(artifact.source_upload_id ? { source_upload_id: artifact.source_upload_id } : {}),
    ...(artifact.content_hash ? { content_hash: artifact.content_hash } : {}),
    provider_origin: artifact.provider_origin,
    ...(artifact.mime_type ? { mime_type: artifact.mime_type } : {}),
    ...(typeof artifact.size_bytes === "number" ? { size_bytes: artifact.size_bytes } : {}),
    status: artifact.status
  };
}

export const registerArtifactImportRoutes: FastifyPluginAsync = async (app) => {
  app.post("/artifact-imports/session-upload", async (request, reply) => {
    requireScope(request);
    if (!request.isMultipart()) {
      throw routeError({
        code: "INVALID_EXECUTION_INPUT_IMPORT",
        message: "Session upload imports require multipart/form-data.",
        httpStatus: 400,
        suggestedAction: "Send metadata fields followed by exactly one file part."
      });
    }

    const file = await request.file();
    if (!file) {
      throw routeError({
        code: "INVALID_EXECUTION_INPUT_IMPORT",
        message: "The multipart request must include one file.",
        httpStatus: 400,
        suggestedAction: "Attach the selected session upload and retry."
      });
    }
    const fields = file.fields as Record<string, MultipartField>;
    const declaredSize = Number(fieldValue(fields, "declared_size_bytes"));
    if (!Number.isSafeInteger(declaredSize) || declaredSize < 0) {
      throw routeError({
        code: "INVALID_EXECUTION_INPUT_IMPORT",
        message: "declared_size_bytes must be a non-negative integer.",
        httpStatus: 400,
        suggestedAction: "Send the exact byte size of the selected upload."
      });
    }

    const result = await app.services.sessionUploadArtifactImporter.import({
      appId: fieldValue(fields, "app_id"),
      sessionId: fieldValue(fields, "session_id"),
      sourceUploadId: fieldValue(fields, "source_upload_id"),
      displayName: fieldValue(fields, "display_name"),
      mimeType: fieldValue(fields, "mime_type"),
      declaredSizeBytes: declaredSize,
      declaredSha256: fieldValue(fields, "declared_sha256"),
      stream: file.file
    });

    return reply.status(result.reusedExistingArtifact ? 200 : 201).send({
      preparation_status: "ready",
      reused_existing_artifact: result.reusedExistingArtifact,
      artifact: publicArtifact(result.artifact)
    });
  });
};
