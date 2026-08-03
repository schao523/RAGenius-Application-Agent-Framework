import type { FastifyInstance } from "fastify";
import { randomUUID } from "node:crypto";

import type { ExecutionScope } from "../../core/execution/execution-store.js";
import { executionRequestSchema } from "../schemas/execution-request.schema.js";
import { classifyAgentRequest } from "../../core/agents/agent-policy.js";

function asyncRequested(request: ReturnType<typeof executionRequestSchema.parse>): boolean {
  return request.request_type === "execute_agent" && (
    request.execution_options?.mode === "async" ||
    request.context?.execution_mode === "async"
  );
}

function newExecutionId(): string {
  return `execution_${randomUUID().replace(/-/g, "").slice(0, 12)}`;
}

function readScope(
  query: unknown,
  executionId: string
): ExecutionScope | null {
  const values = (query ?? {}) as {
    app_id?: unknown;
    session_id?: unknown;
  };
  const appId =
    typeof values.app_id === "string" ? values.app_id.trim() : "";
  const sessionId =
    typeof values.session_id === "string" ? values.session_id.trim() : "";

  return appId && sessionId
    ? { appId, executionId, sessionId }
    : null;
}

function missingScopeError() {
  return {
    error: {
      code: "VALIDATION_ERROR",
      message: "app_id and session_id are required.",
      recoverable: true,
      suggested_action: "Resubmit with the execution app and session scope."
    }
  };
}

function executionNotFoundError() {
  return {
    error: {
      code: "EXECUTION_NOT_FOUND",
      message: "Execution record was not found.",
      recoverable: true,
      suggested_action: "Submit a new execution request."
    }
  };
}

export async function registerExecutionRoutes(
  app: FastifyInstance
): Promise<void> {
  app.post("/executions", async (request, reply) => {
    const parsedRequest = executionRequestSchema.parse(request.body);
    if (asyncRequested(parsedRequest)) {
      if (!app.services.runtimeConfig.agentAsync.enabled) {
        return reply.status(409).send({
          error: {
            code: "AGENT_ASYNC_DISABLED",
            message: "Asynchronous Agent execution is disabled.",
            recoverable: true,
            suggested_action: "Enable AGENT_ASYNC_EXECUTION_ENABLED or submit synchronously."
          }
        });
      }
      if (parsedRequest.request_type === "execute_agent") {
        const policy = classifyAgentRequest(parsedRequest, {
          notebookLmProfile:
            app.services.runtimeConfig.providers.notebooklm.profile ?? "default"
        });
        if (policy.mode === "auto_allow" && parsedRequest.execution_options?.dry_run !== true) {
          const queued = await app.services.agentExecutionQueue.enqueue({
            executionId: newExecutionId(),
            request: parsedRequest
          });
          return reply.status(202).send(queued);
        }
      }
    }
    const result = await app.services.executionEngine.execute(parsedRequest);

    if (result.status === "pending_confirmation") {
      return reply.status(202).send(result);
    }

    if (result.status === "failed") {
      const error = result.errors[0];
      if (!error) {
        return reply.status(200).send(result);
      }
      const statusCode =
        error?.code === "SKILL_NOT_FOUND"
          ? 404
          : error?.code === "PERMISSION_BLOCKED"
            ? 403
            : error?.code === "VALIDATION_ERROR"
              ? 400
              : 500;

      return reply.status(statusCode).send({
        error
      });
    }

    return reply.status(200).send(result);
  });

  app.get("/executions/diagnostics/recent", async (request, reply) => {
    const query = (request.query ?? {}) as {
      app_id?: string;
      execution_path?: string;
      limit?: string | number;
      session_id?: string;
      used_fallback?: string;
    };
    const scope = readScope(query, "diagnostics");
    if (!scope) {
      return reply.status(400).send(missingScopeError());
    }
    const rawLimit =
      typeof query.limit === "number"
        ? query.limit
        : Number.parseInt(String(query.limit ?? "10"), 10);
    const limit =
      Number.isFinite(rawLimit) && rawLimit > 0
        ? Math.min(rawLimit, 50)
        : 10;
    const usedFallback =
      query.used_fallback === "true"
        ? true
        : query.used_fallback === "false"
          ? false
          : undefined;
    const executionPath =
      typeof query.execution_path === "string" && query.execution_path.length > 0
        ? query.execution_path
        : undefined;

    const diagnostics = await app.services.executionStatusService.getRecentDiagnostics({
      appId: scope.appId,
      executionPath:
        executionPath as
          | "local"
          | "api"
          | "rag_adapter"
          | "adapter"
          | "mcp"
          | "rest_fallback"
          | undefined,
      limit,
      sessionId: scope.sessionId,
      usedFallback
    });

    return reply.status(200).send({
      filters: {
        app_id: scope.appId,
        execution_path: executionPath ?? null,
        limit,
        session_id: scope.sessionId,
        used_fallback: usedFallback ?? null
      },
      items: diagnostics.items,
      summary: diagnostics.summary
    });
  });

  app.get("/executions/:execution_id", async (request, reply) => {
    const executionId = (request.params as { execution_id: string }).execution_id;
    const scope = readScope(request.query, executionId);
    if (!scope) {
      return reply.status(400).send(missingScopeError());
    }
    const record = await app.services.executionStatusService.get(scope);

    if (!record) {
      return reply.status(404).send(executionNotFoundError());
    }

    return reply.status(200).send(record);
  });

  app.get("/executions/:execution_id/logs", async (request, reply) => {
    const executionId = (request.params as { execution_id: string }).execution_id;
    const scope = readScope(request.query, executionId);
    if (!scope) {
      return reply.status(400).send(missingScopeError());
    }
    const record = await app.services.executionStatusService.get(scope);

    if (!record) {
      return reply.status(404).send(executionNotFoundError());
    }

    return reply.status(200).send({
      execution_id: executionId,
      logs: await app.services.executionStatusService.getLogs(scope)
    });
  });

  app.post("/executions/:execution_id/confirm", async (request, reply) => {
    const executionId = (request.params as { execution_id: string }).execution_id;
    const scope = readScope(request.query, executionId);
    if (!scope) {
      return reply.status(400).send(missingScopeError());
    }
    const body = (request.body ?? {}) as { confirmation_id?: unknown };
    const confirmationId =
      typeof body.confirmation_id === "string"
        ? body.confirmation_id.trim()
        : "";

    if (!confirmationId) {
      return reply.status(400).send({
        error: {
          code: "VALIDATION_ERROR",
          message: "confirmation_id is required.",
          recoverable: true,
          suggested_action:
            "Use the server-issued confirmation_id from the pending execution."
        }
      });
    }

    const confirmationScope = {
      ...scope,
      confirmationId
    };
    const claim =
      await app.services.confirmationService.claim(confirmationScope);
    if (claim.outcome === "not_found") {
      return reply.status(404).send(executionNotFoundError());
    }
    if (claim.outcome === "expired") {
      return reply.status(409).send({
        error: {
          code: "CONFIRMATION_EXPIRED",
          message: "Execution confirmation has expired.",
          recoverable: true,
          suggested_action: "Submit the execution again for confirmation."
        }
      });
    }
    if (claim.outcome === "claimed" && !claim.record.consumedAt) {
      return reply.status(409).send({
        error: {
          code: "CONFIRMATION_STATE_INVALID",
          message: "Claimed confirmation does not have a confirmation timestamp.",
          recoverable: true,
          suggested_action: "Submit the execution again for confirmation."
        }
      });
    }
    if (claim.outcome === "terminal") {
      const existing = await app.services.executionStatusService.get(scope);
      return existing
        ? reply.status(200).send(existing)
        : reply.status(404).send(executionNotFoundError());
    }
    if (claim.outcome === "running") {
      const existing = await app.services.executionStatusService.get(scope);
      return reply.status(202).send({
        ...(existing ?? {
          execution_id: executionId,
          result_type: "json",
          result: {},
          files: [],
          errors: [],
          logs_summary: "Execution is already running."
        }),
        status: existing?.status === "queued" ? "queued" : "running",
        result: {
          ...(existing?.result ?? {}),
          ...app.services.confirmationService.metadata(claim.record)
        }
      });
    }

    const originalRequest =
      await app.services.executionStatusService.getRequest(scope);
    if (!originalRequest) {
      await app.services.confirmationService.finish(
        confirmationScope,
        "failed"
      );
      return reply.status(404).send(executionNotFoundError());
    }


    if (asyncRequested(originalRequest)) {
      if (!app.services.runtimeConfig.agentAsync.enabled) {
        await app.services.confirmationService.finish(confirmationScope, "failed");
        return reply.status(409).send({
          error: {
            code: "AGENT_ASYNC_DISABLED",
            message: "Asynchronous Agent execution is disabled.",
            recoverable: true,
            suggested_action: "Enable AGENT_ASYNC_EXECUTION_ENABLED and resubmit."
          }
        });
      }
      const queued = await app.services.agentExecutionQueue.enqueue({
        executionId,
        request: originalRequest,
        approvedConfirmation: {
          confirmationId,
          confirmedAt: claim.record.consumedAt!.toISOString(),
          policySnapshot: claim.record.policySnapshot
        }
      });
      return reply.status(202).send(queued);
    }

    let result;
    try {
      result = await app.services.executionEngine.execute(
        originalRequest,
        {
          approvedConfirmation: {
            confirmationId,
            confirmedAt: claim.record.consumedAt!.toISOString(),
            policySnapshot: claim.record.policySnapshot
          },
          executionId
        }
      );
    } catch (error) {
      await app.services.confirmationService.finish(
        confirmationScope,
        "failed"
      );
      throw error;
    }

    await app.services.confirmationService.finish(
      confirmationScope,
      result.status === "completed" ? "completed" : "failed"
    );

    if (result.status === "failed") {
      if (result.errors.length === 0) {
        return reply.status(200).send(result);
      }
      return reply.status(500).send({
        error: result.errors[0]
      });
    }

    return reply.status(200).send(result);
  });
}
