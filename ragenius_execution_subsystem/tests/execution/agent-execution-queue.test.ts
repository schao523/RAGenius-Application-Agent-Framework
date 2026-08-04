import assert from "node:assert/strict";
import test from "node:test";

import type { ExecuteAgentRequest } from "../../src/api/schemas/execution-request.schema.js";
import { AgentExecutionQueue } from "../../src/core/execution/agent-execution-queue.js";
import { InMemoryExecutionStore } from "../../src/core/execution/execution-store.js";

const request: ExecuteAgentRequest = {
  request_type: "execute_agent",
  app_id: "app_001",
  session_id: "session_001",
  agent_backend: "codex_cli",
  agent_query: "Summarize this."
};

function deferred(): { promise: Promise<void>; resolve: () => void } {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => { resolve = done; });
  return { promise, resolve };
}

test("enqueue returns queued before deferred execution completes", async () => {
  const store = new InMemoryExecutionStore();
  const gate = deferred();
  const queue = new AgentExecutionQueue(store, async (queuedRequest, options) => {
    await gate.promise;
    const result = {
      execution_id: options.executionId,
      status: "completed" as const,
      result_type: "json" as const,
      result: {}, files: [], errors: [], logs_summary: "Complete."
    };
    await store.save({ executionId: options.executionId, request: queuedRequest, result });
    return result;
  });

  const queued = await queue.enqueue({ executionId: "execution_001", request });
  assert.equal(queued.status, "queued");
  queue.start();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal((await store.get({ appId: "app_001", sessionId: "session_001", executionId: "execution_001" }))?.status, "running");
  gate.resolve();
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal((await store.get({ appId: "app_001", sessionId: "session_001", executionId: "execution_001" }))?.status, "completed");
});

test("bounded concurrency and duplicate enqueue invoke each execution once", async () => {
  const store = new InMemoryExecutionStore();
  const gate = deferred();
  let active = 0;
  let maximum = 0;
  const calls = new Map<string, number>();
  const queue = new AgentExecutionQueue(store, async (_request, options) => {
    active += 1;
    maximum = Math.max(maximum, active);
    calls.set(options.executionId, (calls.get(options.executionId) ?? 0) + 1);
    await gate.promise;
    active -= 1;
    return { status: "completed", result_type: "json", result: {}, files: [], errors: [], logs_summary: "Complete." };
  }, 1);
  await Promise.all([
    queue.enqueue({ executionId: "execution_001", request }),
    queue.enqueue({ executionId: "execution_001", request }),
    queue.enqueue({ executionId: "execution_002", request })
  ]);
  queue.start();
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(maximum, 1);
  assert.equal(calls.get("execution_001"), 1);
  gate.resolve();
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(calls.get("execution_002"), 1);
});

test("restart reconciliation fails queued and running records", async () => {
  const store = new InMemoryExecutionStore();
  const queue = new AgentExecutionQueue(store, async () => {
    throw new Error("not invoked");
  });
  await queue.enqueue({ executionId: "execution_001", request });
  const count = await queue.reconcileInterrupted();
  const record = await store.get({ appId: "app_001", sessionId: "session_001", executionId: "execution_001" });
  assert.equal(count, 1);
  assert.equal(record?.status, "failed");
  assert.equal(record?.errors[0]?.code, "AGENT_EXECUTION_INTERRUPTED");
});
