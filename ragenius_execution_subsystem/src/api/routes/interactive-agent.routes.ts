import type { FastifyPluginAsync, FastifyRequest } from "fastify";

import { hasServiceScope } from "../auth/service-auth.js";
import {
  agentEventQuerySchema,
  agentInteractionResponseBodySchema,
  interactiveExecutionScopeQuerySchema,
  type AgentInteractionResponseBody
} from "../schemas/interactive-agent.schema.js";
import { AppError } from "../../core/errors/app-error.js";
import type { AgentInteractionRecord, ExecutionScope } from "../../core/interactive/interactive-agent-types.js";

function routeError(input: {
  code: string;
  httpStatus: number;
  message: string;
  suggestedAction: string;
}): AppError {
  return new AppError({
    ...input,
    errorClass: input.httpStatus === 403 ? "permission" : "validation",
    recoverable: true
  });
}

function requireExecutionScope(request: FastifyRequest): void {
  if (!hasServiceScope(request, "execution")) {
    throw routeError({
      code: "SERVICE_SCOPE_REQUIRED",
      httpStatus: 403,
      message: "The service credential does not grant execution access.",
      suggestedAction: "Use a service credential with the execution scope."
    });
  }
}

function scopeFrom(
  executionId: string,
  query: unknown
): ExecutionScope {
  const parsed = interactiveExecutionScopeQuerySchema.parse(query);
  return {
    appId: parsed.app_id,
    executionId,
    sessionId: parsed.session_id
  };
}

function executionNotFound(): AppError {
  return routeError({
    code: "EXECUTION_NOT_FOUND",
    httpStatus: 404,
    message: "Execution record was not found.",
    suggestedAction: "Refresh the scoped execution state."
  });
}

function conflict(code: string, message: string): AppError {
  return routeError({
    code,
    httpStatus: 409,
    message,
    suggestedAction: "Refresh interactions and use the current pending version."
  });
}

function publicInteraction(record: AgentInteractionRecord): Record<string, unknown> {
  return {
    agent_session_id: record.agentSessionId,
    allows_free_text: record.allowsFreeText,
    created_at: record.createdAt.toISOString(),
    expires_at: record.expiresAt.toISOString(),
    interaction_id: record.interactionId,
    options: record.options.map((option) => ({ ...option })),
    prompt: record.prompt,
    resolved_at: record.resolvedAt?.toISOString() ?? null,
    sequence: record.sequence,
    state: record.state,
    type: record.type,
    updated_at: record.updatedAt.toISOString(),
    version: record.version
  };
}

function expectedResponseKind(type: AgentInteractionRecord["type"]): AgentInteractionResponseBody["response"]["kind"] {
  if (type === "approval") return "approval";
  if (type === "selection") return "selection";
  if (type === "clarification") return "clarification";
  return "user_action";
}

export const registerInteractiveAgentRoutes: FastifyPluginAsync = async (app) => {
  app.get("/executions/:execution_id/interactions", async (request, reply) => {
    requireExecutionScope(request);
    const executionId = (request.params as { execution_id: string }).execution_id;
    const scope = scopeFrom(executionId, request.query);
    if (!await app.services.executionStore.get(scope)) throw executionNotFound();
    const items = await app.services.agentInteractionStore.list(scope);
    return reply.status(200).send({
      execution_id: executionId,
      items: items.map(publicInteraction)
    });
  });

  app.get("/executions/:execution_id/events", async (request, reply) => {
    requireExecutionScope(request);
    const executionId = (request.params as { execution_id: string }).execution_id;
    const query = agentEventQuerySchema.parse(request.query);
    const scope = {
      appId: query.app_id,
      executionId,
      sessionId: query.session_id
    };
    if (!await app.services.executionStore.get(scope)) throw executionNotFound();
    const events = await app.services.agentEventStore.list({
      ...scope,
      afterSequence: query.after_sequence,
      limit: query.limit
    });
    return reply.status(200).send({
      execution_id: executionId,
      items: events.map((event) => ({
        ...(event.interactionId ? { interaction_id: event.interactionId } : {}),
        occurred_at: event.occurredAt.toISOString(),
        payload: event.payload,
        sequence: event.sequence,
        type: event.type
      })),
      next_after_sequence:
        events.at(-1)?.sequence ?? query.after_sequence
    });
  });

  app.post(
    "/executions/:execution_id/interactions/:interaction_id/responses",
    async (request, reply) => {
      requireExecutionScope(request);
      const params = request.params as {
        execution_id: string;
        interaction_id: string;
      };
      const scope = scopeFrom(params.execution_id, request.query);
      if (!await app.services.executionStore.get(scope)) throw executionNotFound();
      const body = agentInteractionResponseBodySchema.parse(request.body);
      const interaction = (await app.services.agentInteractionStore.list(scope))
        .find((item) => item.interactionId === params.interaction_id);
      if (!interaction) throw executionNotFound();
      if (body.response.kind !== expectedResponseKind(interaction.type)) {
        throw conflict(
          "INTERACTION_RESPONSE_KIND_MISMATCH",
          "The response kind does not match the pending interaction."
        );
      }
      if (
        interaction.state === "pending" &&
        interaction.version !== body.expected_version
      ) {
        throw conflict(
          "INTERACTION_VERSION_STALE",
          "The interaction version is stale."
        );
      }
      const result = await app.services.interactiveSessionManager.respond({
        ...scope,
        expectedVersion: body.expected_version,
        idempotencyKey: body.idempotency_key,
        interactionId: params.interaction_id,
        responseSummary: body.response
      });
      if (result.outcome === "not_found") throw executionNotFound();
      if (result.outcome === "conflict") {
        throw conflict("INTERACTION_CONFLICT", "The interaction is no longer pending.");
      }
      if (result.outcome === "expired") {
        throw conflict("INTERACTION_EXPIRED", "The interaction has expired.");
      }
      return reply.status(200).send({
        execution_id: params.execution_id,
        interaction_id: params.interaction_id,
        outcome: result.outcome
      });
    }
  );

  app.post("/executions/:execution_id/cancel", async (request, reply) => {
    requireExecutionScope(request);
    const executionId = (request.params as { execution_id: string }).execution_id;
    const scope = scopeFrom(executionId, request.query);
    if (!await app.services.executionStore.get(scope)) throw executionNotFound();
    const result = await app.services.interactiveSessionManager.cancel(scope);
    if (!result.cancelled) {
      throw conflict(
        "AGENT_CANCELLATION_UNCONFIRMED",
        "Agent cancellation could not be confirmed."
      );
    }
    return reply.status(200).send({
      cancelled: true,
      execution_id: executionId,
      status: "cancelled"
    });
  });
};
