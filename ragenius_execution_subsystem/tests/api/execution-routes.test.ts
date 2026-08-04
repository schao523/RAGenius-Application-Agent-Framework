import assert from "node:assert/strict";
import test from "node:test";

import { buildApp } from "../../src/app.js";
import { getEnv } from "../../src/config/env.js";
import { buildRuntimeConfig } from "../../src/config/runtime-config.js";
import type { AgentProvider } from "../../src/core/agents/agent-provider.js";
import { ExecutionEngine } from "../../src/core/execution/execution-engine.js";
import { InMemoryExecutionStore } from "../../src/core/execution/execution-store.js";

function deferred(): { promise: Promise<void>; resolve: () => void } {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => { resolve = done; });
  return { promise, resolve };
}

test("async Agent submission returns queued before provider completion", async () => {
  const gate = deferred();
  let providerCalls = 0;
  const provider: AgentProvider = {
    backend: "codex_cli",
    async execute() {
      providerCalls += 1;
      await gate.promise;
      return { status: "completed", summary: "Complete." };
    }
  };
  const store = new InMemoryExecutionStore();
  const engine = new ExecutionEngine({
    agentProviders: new Map([["codex_cli", provider]]),
    executionStore: store
  });
  const runtimeConfig = buildRuntimeConfig(getEnv({
    AGENT_ASYNC_EXECUTION_ENABLED: "true",
    AGENT_ASYNC_CONCURRENCY: "1"
  }));
  const app = buildApp({ executionEngine: engine, executionStore: store }, runtimeConfig);
  await app.ready();

  const response = await app.inject({
    method: "POST",
    url: "/v1/executions",
    payload: {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "session_001",
      agent_backend: "codex_cli",
      agent_query: "Summarize this.",
      execution_options: { mode: "async" }
    }
  });
  const queued = response.json() as { execution_id: string; status: string };

  assert.equal(response.statusCode, 202);
  assert.equal(queued.status, "queued");
  assert.equal(providerCalls, 1);
  gate.resolve();
  await new Promise((resolve) => setTimeout(resolve, 20));

  const status = await app.inject({
    method: "GET",
    url: `/v1/executions/${queued.execution_id}?app_id=app_001&session_id=session_001`
  });
  assert.equal(status.json().status, "completed");
  assert.equal(providerCalls, 1);
  await app.close();
});

test("explicit async Agent submission is rejected when disabled", async () => {
  const app = buildApp();
  const response = await app.inject({
    method: "POST",
    url: "/v1/executions",
    payload: {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "session_001",
      agent_backend: "codex_cli",
      agent_query: "Summarize this.",
      execution_options: { mode: "async" }
    }
  });

  assert.equal(response.statusCode, 409);
  assert.equal(response.json().error.code, "AGENT_ASYNC_DISABLED");
  await app.close();
});
