import type { FastifyPluginAsync, FastifyRequest } from "fastify";

import { hasServiceScope } from "../auth/service-auth.js";
import {
  agentEventQuerySchema,
  agentChatFollowUpBodySchema,
  agentInteractionLaunchBodySchema,
  agentInteractionResponseBodySchema,
  endAgentChatSessionBodySchema,
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
    presentation: record.presentation
      ? {
          ...(record.presentation.completionLabel
            ? { completion_label: record.presentation.completionLabel }
            : {}),
          ...(record.presentation.launchAvailable !== undefined
            ? { launch_available: record.presentation.launchAvailable }
            : {}),
          ...(record.presentation.targetHost
            ? { target_host: record.presentation.targetHost }
            : {}),
          ...(record.presentation.targetLabel
            ? { target_label: record.presentation.targetLabel }
            : {})
        }
      : null,
    prompt: record.prompt,
    resolved_at: record.resolvedAt?.toISOString() ?? null,
    sequence: record.sequence,
    state: record.state,
    type: record.type,
    updated_at: record.updatedAt.toISOString(),
    version: record.version
  };
}

const PROTECTED_EVENT_PAYLOAD_KEYS = /^(?:credential|policy_binding_hash|provider_correlation_ref|provider_event_ref|provider_run_ref|provider_session_ref|provider_turn_ref|run_id|runid|secret|session_key|sessionkey|token)$/i;

function publicEventPayload(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(publicEventPayload);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .filter(([key]) => !PROTECTED_EVENT_PAYLOAD_KEYS.test(key))
      .map(([key, child]) => [key, publicEventPayload(child)])
  );
}

function expectedResponseKind(type: AgentInteractionRecord["type"]): AgentInteractionResponseBody["response"]["kind"] {
  if (type === "approval") return "approval";
  if (type === "selection") return "selection";
  if (type === "clarification") return "clarification";
  return "user_action";
}

export const registerInteractiveAgentRoutes: FastifyPluginAsync = async (app) => {
  app.get("/executions/:execution_id/chat-session", async (request, reply) => {
    requireExecutionScope(request);
    const executionId = (request.params as { execution_id: string }).execution_id;
    const scope = scopeFrom(executionId, request.query);
    const execution = await app.services.executionStore.get(scope);
    if (!execution) throw executionNotFound();
    const session = await app.services.agentSessionStore.getByExecution(scope);
    if (!session) throw executionNotFound();
    const turns = (await app.services.agentChatTurnStore.list(scope)).slice(-100);
    const executionResult = execution.result && typeof execution.result === "object"
      ? execution.result as Record<string, unknown>
      : {};
    return reply.status(200).send({
      agent_session_id: session.agentSessionId,
      execution_id: executionId,
      idle_expires_at: session.idleExpiresAt?.toISOString() ?? null,
      latest_output_text: typeof executionResult.output_text === "string"
        ? executionResult.output_text
        : "",
      session_version: session.sessionVersion,
      state: session.state,
      turn_sequence: session.turnSequence,
      turns: turns.map((turn) => ({
        acknowledgement_state: turn.acknowledgementState,
        chat_turn_id: turn.chatTurnId,
        completed_at: turn.completedAt?.toISOString() ?? null,
        created_at: turn.createdAt.toISOString(),
        kind: turn.kind,
        result: turn.normalizedResult,
        sequence: turn.sequence,
        state: turn.state
      }))
    });
  });

  app.post("/executions/:execution_id/follow-ups", async (request, reply) => {
    requireExecutionScope(request);
    const executionId = (request.params as { execution_id: string }).execution_id;
    const scope = scopeFrom(executionId, request.query);
    if (!await app.services.executionStore.get(scope)) throw executionNotFound();
    const body = agentChatFollowUpBodySchema.parse(request.body);
    const result = await app.services.interactiveSessionManager.followUp({
      ...scope,
      expectedSessionVersion: body.expected_session_version,
      idempotencyKey: body.idempotency_key,
      kind: body.kind,
      ...(body.text ? { text: body.text } : {})
    });
    if (result.outcome === "not_found") throw executionNotFound();
    if (!["accepted", "replay"].includes(result.outcome)) {
      const codes = {
        active: "CHAT_RUN_ALREADY_ACTIVE",
        closed: "CHAT_SESSION_CLOSED",
        delivery_unknown: "CHAT_FOLLOW_UP_DELIVERY_UNKNOWN",
        not_ready: "CHAT_SESSION_NOT_READY",
        provider_session_unavailable: "CHAT_PROVIDER_SESSION_UNAVAILABLE",
        requires_new_execution: "CHAT_FOLLOW_UP_REQUIRES_NEW_EXECUTION",
        stale: "CHAT_SESSION_VERSION_STALE"
      } as const;
      const outcome = result.outcome as keyof typeof codes;
      throw conflict(codes[outcome] ?? "CHAT_SESSION_NOT_READY", `Chat follow-up is ${result.outcome.replaceAll("_", " ")}.`);
    }
    return reply.status(result.outcome === "accepted" ? 202 : 200).send({
      execution_id: executionId,
      outcome: result.outcome
    });
  });

  app.post("/executions/:execution_id/end-chat-session", async (request, reply) => {
    requireExecutionScope(request);
    const executionId = (request.params as { execution_id: string }).execution_id;
    const scope = scopeFrom(executionId, request.query);
    if (!await app.services.executionStore.get(scope)) throw executionNotFound();
    const body = endAgentChatSessionBodySchema.parse(request.body);
    const result = await app.services.interactiveSessionManager.endChatSession(
      scope,
      body.expected_session_version
    );
    if (result.outcome === "not_found") throw executionNotFound();
    if (!result.ended) throw conflict("CHAT_SESSION_NOT_READY", "Chat session cannot be ended in its current state.");
    return reply.status(200).send({ ended: true, execution_id: executionId, status: "completed" });
  });

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
        payload: publicEventPayload(event.payload),
        sequence: event.sequence,
        type: event.type
      })),
      next_after_sequence:
        events.at(-1)?.sequence ?? query.after_sequence
    });
  });

  app.post(
    "/executions/:execution_id/interactions/:interaction_id/launch",
    async (request, reply) => {
      requireExecutionScope(request);
      const params = request.params as { execution_id: string; interaction_id: string };
      const scope = scopeFrom(params.execution_id, request.query);
      if (!await app.services.executionStore.get(scope)) throw executionNotFound();
      const body = agentInteractionLaunchBodySchema.parse(request.body);
      const result = await app.services.interactiveSessionManager.launchInteraction({
        ...scope,
        expectedVersion: body.expected_version,
        interactionId: params.interaction_id
      });
      if (result.outcome === "not_found") throw executionNotFound();
      if (result.outcome === "expired") {
        throw conflict("INTERACTION_EXPIRED", "The interaction has expired.");
      }
      if (result.outcome !== "issued") {
        throw conflict("INTERACTION_LAUNCH_UNAVAILABLE", "Authentication launch is not available.");
      }
      reply.header("Cache-Control", "no-store");
      reply.header("Pragma", "no-cache");
      if (result.launch.kind === "https_url") {
        return reply.status(200).send({
          expires_at: result.launch.expiresAt.toISOString(),
          launch_url: result.launch.launchUrl
        });
      }
      return reply.status(200).send({
        application: result.launch.application,
        expires_at: result.launch.expiresAt.toISOString(),
        kind: "provider_window",
        provider: result.launch.provider
      });
    }
  );

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
      if (result.outcome === "verification_failed") {
        throw conflict(
          "AUTHENTICATION_HANDOFF_NOT_VERIFIED",
          "Authentication could not be verified. Complete sign-in and retry."
        );
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
