import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

import type { FastifyInstance } from "fastify";

import { buildApp } from "../../src/app.js";
import type { ExecutionRequest } from "../../src/api/schemas/execution-request.schema.js";
import { InMemoryExecutionStore } from "../../src/core/execution/execution-store.js";

describe("execution route scope", () => {
  let app: FastifyInstance | undefined;

  afterEach(async () => {
    await app?.close();
    app = undefined;
  });

  it("returns the same not-found response for wrong app and session scopes", async () => {
    const store = new InMemoryExecutionStore();
    const request: ExecutionRequest = {
      request_type: "execute_skill",
      app_id: "app_001",
      session_id: "sess_001",
      skill_id: "video_director_skill",
      input: { duration: 30, prompt: "Explain RAG simply" }
    };
    await store.save({
      executionId: "execution_scoped",
      request,
      result: {
        execution_id: "execution_scoped",
        status: "completed",
        result_type: "json",
        result: {},
        files: [],
        errors: [],
        logs_summary: "Execution completed."
      }
    });
    app = buildApp({ executionStore: store });

    const correctScope = await app.inject({
      method: "GET",
      url: "/v1/executions/execution_scoped?app_id=app_001&session_id=sess_001"
    });
    const correctLogs = await app.inject({
      method: "GET",
      url: "/v1/executions/execution_scoped/logs?app_id=app_001&session_id=sess_001"
    });
    const wrongApp = await app.inject({
      method: "GET",
      url: "/v1/executions/execution_scoped?app_id=app_002&session_id=sess_001"
    });
    const wrongSession = await app.inject({
      method: "GET",
      url: "/v1/executions/execution_scoped?app_id=app_001&session_id=sess_002"
    });
    const unknownExecution = await app.inject({
      method: "GET",
      url: "/v1/executions/execution_unknown?app_id=app_001&session_id=sess_001"
    });
    const wrongScopeLogs = await app.inject({
      method: "GET",
      url: "/v1/executions/execution_scoped/logs?app_id=app_002&session_id=sess_001"
    });
    const missingScope = await app.inject({
      method: "GET",
      url: "/v1/executions/execution_scoped"
    });

    assert.equal(correctScope.statusCode, 200);
    assert.equal(correctLogs.statusCode, 200);
    assert.equal(correctLogs.json().logs.length, 1);
    assert.equal(wrongApp.statusCode, 404);
    assert.deepEqual(wrongApp.json(), wrongSession.json());
    assert.deepEqual(wrongApp.json(), unknownExecution.json());
    assert.deepEqual(wrongApp.json(), wrongScopeLogs.json());
    assert.equal(missingScope.statusCode, 400);
  });

  it("does not confirm an execution outside its app and session scope", async () => {
    const store = new InMemoryExecutionStore();
    await store.save({
      executionId: "execution_pending",
      request: {
        request_type: "execute_skill",
        app_id: "app_001",
        session_id: "sess_001",
        skill_id: "video_director_skill",
        input: { duration: 30, prompt: "Explain RAG simply" }
      },
      result: {
        execution_id: "execution_pending",
        status: "pending_confirmation",
        result_type: "json",
        result: {},
        files: [],
        errors: [],
        logs_summary: "Confirmation required."
      }
    });
    app = buildApp({ executionStore: store });

    const response = await app.inject({
      method: "POST",
      url: "/v1/executions/execution_pending/confirm?app_id=app_001&session_id=sess_002",
      payload: { confirmation_id: "confirmation_missing" }
    });

    assert.equal(response.statusCode, 404);
    assert.equal(response.json().error.code, "EXECUTION_NOT_FOUND");
  });
});
