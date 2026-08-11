import fs from "node:fs";
import type { FastifyInstance, FastifyReply } from "fastify";

function scope(request: { query: unknown; params: unknown }): {
  appId: string;
  sessionId: string;
  artifactId: string;
} | null {
  const query = (request.query ?? {}) as Record<string, unknown>;
  const params = (request.params ?? {}) as Record<string, unknown>;
  const appId = String(query.app_id ?? "").trim();
  const sessionId = String(query.session_id ?? "").trim();
  const artifactId = String(params.artifact_id ?? "").trim();
  return appId && sessionId && artifactId ? { appId, sessionId, artifactId } : null;
}

function notFound(reply: FastifyReply) {
  return reply.status(404).send({
    error: {
      code: "ARTIFACT_NOT_FOUND",
      message: "Artifact was not found.",
      recoverable: false,
      suggested_action: "Refresh the scoped artifact inventory."
    }
  });
}

function inUse(reply: FastifyReply) {
  return reply.status(409).send({
    error: {
      code: "ARTIFACT_IN_USE",
      message: "Artifact is in use by an active execution.",
      recoverable: true,
      suggested_action: "Wait for the execution to finish, then retry deletion."
    }
  });
}

function contentDisposition(kind: "inline" | "attachment", name: string): string {
  const asciiFallback = name
    .replace(/[^\x20-\x7e]/g, "_")
    .replace(/[\\"\r\n]/g, "_") || "artifact";
  const encodedName = encodeURIComponent(name)
    .replace(/['()*]/g, (character) =>
      `%${character.charCodeAt(0).toString(16).toUpperCase()}`);
  return `${kind}; filename="${asciiFallback}"; filename*=UTF-8''${encodedName}`;
}

export async function registerArtifactRoutes(app: FastifyInstance): Promise<void> {
  const serve = async (
    request: { query: unknown; params: unknown },
    reply: FastifyReply,
    disposition: "inline" | "attachment"
  ) => {
    const scoped = scope(request);
    if (!scoped) {
      return notFound(reply);
    }
    try {
      const artifact = await app.services.artifactStore.resolveScopedFile(scoped);
      reply.header("content-type", artifact.mime_type ?? "application/octet-stream");
      reply.header("content-length", String(artifact.size_bytes));
      reply.header("content-disposition", contentDisposition(disposition, artifact.display_name));
      return reply.send(fs.createReadStream(artifact.absolute_path));
    } catch {
      return notFound(reply);
    }
  };

  app.get("/artifacts/:artifact_id/preview", (request, reply) =>
    serve(request, reply, "inline"));
  app.get("/artifacts/:artifact_id/download", (request, reply) =>
    serve(request, reply, "attachment"));
  app.delete("/artifacts/:artifact_id", async (request, reply) => {
    const scoped = scope(request);
    if (!scoped) {
      return notFound(reply);
    }
    try {
      if (await app.services.executionStore.hasActiveArtifactReference(scoped)) {
        return inUse(reply);
      }
      const result = await app.services.artifactStore.markDeletedScoped(scoped);
      return reply.status(200).send({
        deleted: true,
        already_deleted: !result.deleted,
        artifact_id: scoped.artifactId
      });
    } catch {
      return notFound(reply);
    }
  });
}
