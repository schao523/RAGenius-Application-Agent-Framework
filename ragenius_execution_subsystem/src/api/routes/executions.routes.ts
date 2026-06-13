import type { FastifyInstance } from "fastify";

export async function registerExecutionRoutes(
  app: FastifyInstance
): Promise<void> {
  app.post("/executions", async (request, reply) => {
    const result = await app.services.executionEngine.execute(request.body);

    if (result.status === "pending_confirmation") {
      return reply.status(202).send(result);
    }

    if (result.status === "failed") {
      const error = result.errors[0];
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
      execution_path?: string;
      limit?: string | number;
      used_fallback?: string;
    };
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
      usedFallback
    });

    return reply.status(200).send({
      filters: {
        execution_path: executionPath ?? null,
        limit,
        used_fallback: usedFallback ?? null
      },
      items: diagnostics.items,
      summary: diagnostics.summary
    });
  });

  app.get("/executions/:execution_id", async (request, reply) => {
    const executionId = (request.params as { execution_id: string }).execution_id;
    const record = await app.services.executionStatusService.get(executionId);

    if (!record) {
      return reply.status(404).send({
        error: {
          code: "EXECUTION_NOT_FOUND",
          message: "Execution record was not found.",
          recoverable: true,
          suggested_action: "Submit a new execution request."
        }
      });
    }

    return reply.status(200).send(record);
  });

  app.get("/executions/:execution_id/logs", async (request, reply) => {
    const executionId = (request.params as { execution_id: string }).execution_id;
    const record = await app.services.executionStatusService.get(executionId);

    if (!record) {
      return reply.status(404).send({
        error: {
          code: "EXECUTION_NOT_FOUND",
          message: "Execution record was not found.",
          recoverable: true,
          suggested_action: "Submit a new execution request."
        }
      });
    }

    return reply.status(200).send({
      execution_id: executionId,
      logs: await app.services.executionStatusService.getLogs(executionId)
    });
  });

  app.post("/executions/:execution_id/confirm", async (request, reply) => {
    const executionId = (request.params as { execution_id: string }).execution_id;
    const body = (request.body ?? {}) as { approved?: boolean };

    if (body.approved !== true) {
      return reply.status(400).send({
        error: {
          code: "VALIDATION_ERROR",
          message: "approved must be true for confirmation.",
          recoverable: true,
          suggested_action: "Resubmit with approved=true."
        }
      });
    }

    const originalRequest =
      await app.services.executionStatusService.getRequest(executionId);
    if (!originalRequest) {
      return reply.status(404).send({
        error: {
          code: "EXECUTION_NOT_FOUND",
          message: "Execution record was not found.",
          recoverable: true,
          suggested_action: "Submit a new execution request."
        }
      });
    }

    const result = await app.services.executionEngine.execute(
      {
        ...originalRequest,
        execution_options: {
          ...(originalRequest.execution_options ?? {}),
          require_confirmation: true
        }
      },
      { executionId }
    );

    if (result.status === "failed") {
      return reply.status(500).send({
        error: result.errors[0]
      });
    }

    return reply.status(200).send(result);
  });
}
