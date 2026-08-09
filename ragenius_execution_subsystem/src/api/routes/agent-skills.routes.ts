import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";

import { hasServiceScope } from "../auth/service-auth.js";
import {
  agentSkillGovernanceProjectionSchema,
  agentSkillInventoryQuerySchema,
  computeAgentSkillProjectionDigest
} from "../schemas/agent-skill.schema.js";
import {
  AgentSkillProjectionError
} from "../../core/agent-skills/agent-skill-projection-store.js";
import { AppError } from "../../core/errors/app-error.js";
import { z } from "zod";

const discoveryRequestSchema = z.object({
  backend: z.enum(["codex_cli", "openclaw_cli"]),
  protected_locator_ref: z.string().trim().min(1),
  runtime_target_id: z.string().trim().min(1),
  source_id: z.string().trim().min(1)
}).strict();

const inspectionRequestSchema = discoveryRequestSchema.extend({
  provider_skill_name: z.string().trim().min(1)
}).strict();

function requireScope(
  request: FastifyRequest,
  reply: FastifyReply,
  scope: string
): boolean {
  if (hasServiceScope(request, scope)) return true;
  void reply.status(403).send({
    error: {
      code: "SERVICE_SCOPE_REQUIRED",
      message: `Service scope ${scope} is required.`,
      recoverable: false,
      suggested_action: "Use the configured service credential for this operation."
    }
  });
  return false;
}

function projectionError(error: AgentSkillProjectionError): AppError {
  return new AppError({
    code: error.code,
    message: "Agent skill governance projection was rejected.",
    errorClass: "validation",
    httpStatus: 409,
    recoverable: true,
    suggestedAction: "Publish a newer complete projection with a consistent digest."
  });
}

export async function registerAgentSkillRoutes(
  app: FastifyInstance
): Promise<void> {
  app.get("/admin/agent-skills/source-options", async (request, reply) => {
    if (!requireScope(request, reply, "agent_skills:admin")) return;
    return { items: app.services.agentSkillDiscoveryService.sourceOptions() };
  });

  app.post("/admin/agent-skills/discover", async (request, reply) => {
    if (!requireScope(request, reply, "agent_skills:admin")) return;
    const input = discoveryRequestSchema.parse(request.body);
    const { backend, ...discoveryInput } = input;
    return app.services.agentSkillDiscoveryService.discover(
      backend,
      discoveryInput
    );
  });

  app.post("/admin/agent-skills/inspect", async (request, reply) => {
    if (!requireScope(request, reply, "agent_skills:admin")) return;
    const input = inspectionRequestSchema.parse(request.body);
    const { backend, ...inspectionInput } = input;
    return app.services.agentSkillDiscoveryService.inspect(
      backend,
      inspectionInput
    );
  });

  app.put("/admin/agent-skills/governance-projection", async (request, reply) => {
    if (!requireScope(request, reply, "agent_skills:admin")) return;
    const config = app.services.runtimeConfig.agentSkills.projection;
    const payloadBytes = Buffer.byteLength(JSON.stringify(request.body), "utf8");
    if (payloadBytes > config.maxBytes) {
      throw new AppError({
        code: "AGENT_SKILL_PROJECTION_TOO_LARGE",
        message: "Agent skill governance projection exceeds the byte limit.",
        errorClass: "validation",
        httpStatus: 413,
        recoverable: true,
        suggestedAction: "Reduce the projection size and retry."
      });
    }
    const projection = agentSkillGovernanceProjectionSchema.parse(request.body);
    if (projection.items.length > config.maxItems) {
      throw new AppError({
        code: "AGENT_SKILL_PROJECTION_TOO_LARGE",
        message: "Agent skill governance projection exceeds the item limit.",
        errorClass: "validation",
        httpStatus: 413,
        recoverable: true,
        suggestedAction: "Reduce the projection item count and retry."
      });
    }
    if (projection.builder_instance_id !== config.trustedBuilderInstanceId) {
      throw new AppError({
        code: "UNTRUSTED_BUILDER_INSTANCE",
        message: "Builder instance is not trusted for projection publication.",
        errorClass: "permission",
        httpStatus: 403,
        recoverable: false,
        suggestedAction: "Use the configured trusted Builder instance."
      });
    }
    const computedDigest = computeAgentSkillProjectionDigest(projection);
    if (projection.digest !== computedDigest) {
      throw new AppError({
        code: "AGENT_SKILL_PROJECTION_DIGEST_MISMATCH",
        message: "Agent skill governance projection digest does not match its content.",
        errorClass: "validation",
        httpStatus: 400,
        recoverable: true,
        suggestedAction: "Recompute the canonical projection digest and retry."
      });
    }
    try {
      return await app.services.agentSkillProjectionStore.publish({
        ...projection,
        items: projection.items.map((item) => ({
          ...item,
          provider_skill_reference:
            item.provider_skill_reference ?? item.provider_skill_name
        }))
      });
    } catch (error) {
      if (error instanceof AgentSkillProjectionError) {
        throw projectionError(error);
      }
      throw error;
    }
  });

  app.get("/agent-skills/inventory", async (request, reply) => {
    if (!requireScope(request, reply, "agent_skills:read")) return;
    const query = agentSkillInventoryQuerySchema.parse(request.query);
    const active = await app.services.agentSkillProjectionStore.getActiveRevision();
    if (!active) {
      return {
        inventory_revision: null,
        items: [],
        projection_status: "unavailable"
      };
    }
    const projected = await app.services.agentSkillProjectionStore.listForApp(
      query.app_id,
      query.backend
    );
    const items = projected
      .filter((item) =>
        item.approval_state === "approved" &&
        item.approved_fingerprint === item.current_fingerprint &&
        item.binding_enabled &&
        item.source_enabled &&
        item.model_visible &&
        !item.direct_tool_dispatch
      )
      .map((item) => ({
        agent_skill_id: item.agent_skill_id,
        approved_fingerprint: item.approved_fingerprint,
        availability: "available" as const,
        backend: item.backend,
        description: item.description,
        display_name: item.display_name,
        provider_skill_name: item.provider_skill_name
      }));
    return {
      inventory_revision: `${active.builder_instance_id}:${active.revision}:${active.digest}`,
      items,
      projection_status: "active"
    };
  });
}
