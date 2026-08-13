import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { ExecuteAgentRequest } from "../../src/api/schemas/execution-request.schema.js";
import { InMemoryExecutionStore } from "../../src/core/execution/execution-store.js";
import { InMemoryAgentEventStore } from "../../src/core/interactive/agent-event-store.js";
import { InMemoryAgentInteractionStore } from "../../src/core/interactive/agent-interaction-store.js";
import { InMemoryAgentSessionStore } from "../../src/core/interactive/agent-session-store.js";
import { InteractiveCapabilityService } from "../../src/core/interactive/interactive-capability-service.js";
import { InteractiveAgentSessionManager } from "../../src/core/interactive/interactive-agent-session-manager.js";
import type { AgentSessionState, ExecutionScope } from "../../src/core/interactive/interactive-agent-types.js";

const scopes: ExecutionScope[] = [
  { appId: "app_1", executionId: "execution_starting", sessionId: "session_1" },
  { appId: "app_1", executionId: "execution_running", sessionId: "session_1" },
  { appId: "app_1", executionId: "execution_waiting", sessionId: "session_1" },
];

const request = (scope: ExecutionScope): ExecuteAgentRequest => ({
  request_type: "execute_agent",
  app_id: scope.appId,
  session_id: scope.sessionId,
  agent_backend: "codex_cli",
  agent_query: "Continue safely."
});

describe("interactive Agent restart recovery", () => {
  it("fails interrupted durable sessions without replaying pending input", async () => {
    const executionStore = new InMemoryExecutionStore();
    const sessionStore = new InMemoryAgentSessionStore();
    const interactionStore = new InMemoryAgentInteractionStore();
    const eventStore = new InMemoryAgentEventStore();
    for (const [index, scope] of scopes.entries()) {
      const state: AgentSessionState = ["starting", "running", "waiting_for_interaction"][index] as AgentSessionState;
      await executionStore.save({
        executionId: scope.executionId,
        request: request(scope),
        result: result(
          scope.executionId,
          state === "waiting_for_interaction" ? "waiting_for_interaction" : "running"
        )
      });
      await sessionStore.create({
        ...scope,
        agentSessionId: `agent_session_${index}`,
        backend: "codex_cli",
        capabilitySnapshot: {
          cancellation: true,
          eventReplay: "none",
          interactionTypes: ["approval"],
          protocolTransport: true,
          reconnectReconciliation: false,
          sameSessionContinuation: true,
          sameTurnResume: true
        },
        continuationMode: "same_turn",
        protocolVersion: "test-v1",
        providerRunRef: `run_${index}`,
        providerSessionRef: `provider_session_${index}`,
        providerTurnRef: `turn_${index}`,
        state,
        transport: "codex_app_server"
      });
      if (state === "waiting_for_interaction") {
        await interactionStore.create({
          ...scope,
          agentSessionId: `agent_session_${index}`,
          allowsFreeText: false,
          expiresAt: new Date("2099-01-01T00:00:00Z"),
          interactionId: "interaction_waiting",
          options: [{ id: "allow_once", label: "Allow once" }],
          policyBindingHash: "policy-binding",
          prompt: "Allow the operation?",
          providerCorrelationRef: "provider-interaction",
          type: "approval"
        });
      }
    }
    const manager = new InteractiveAgentSessionManager({
      capabilityService: new InteractiveCapabilityService([]),
      eventStore,
      executionStore,
      interactionStore,
      sessionStore
    });

    const recovered = await manager.reconcileInterrupted();

    assert.equal(recovered, 3);
    for (const scope of scopes) {
      assert.equal((await executionStore.get(scope))?.status, "failed");
      assert.equal((await sessionStore.getByExecution(scope))?.state, "failed");
      assert.deepEqual(
        (await eventStore.list({ ...scope, afterSequence: 0, limit: 10 })).map((event) => event.type),
        ["error"]
      );
    }
    assert.equal((await interactionStore.list(scopes[2]!))[0]?.state, "cancelled");
  });

  it("does not alter terminal durable sessions during restart recovery", async () => {
    const executionStore = new InMemoryExecutionStore();
    const sessionStore = new InMemoryAgentSessionStore();
    const scope = { appId: "app_1", executionId: "execution_done", sessionId: "session_1" };
    await executionStore.save({ executionId: scope.executionId, request: request(scope), result: result(scope.executionId, "completed") });
    await sessionStore.create({
      ...scope,
      agentSessionId: "agent_session_done",
      backend: "codex_cli",
      capabilitySnapshot: {
        cancellation: true,
        eventReplay: "none",
        interactionTypes: [],
        protocolTransport: true,
        reconnectReconciliation: false,
        sameSessionContinuation: true,
        sameTurnResume: true
      },
      continuationMode: "same_turn",
      protocolVersion: "test-v1",
      providerRunRef: "run_done",
      providerSessionRef: "provider_done",
      providerTurnRef: "turn_done",
      state: "completed",
      transport: "codex_app_server"
    });
    const manager = new InteractiveAgentSessionManager({
      capabilityService: new InteractiveCapabilityService([]),
      eventStore: new InMemoryAgentEventStore(),
      executionStore,
      interactionStore: new InMemoryAgentInteractionStore(),
      sessionStore
    });

    assert.equal(await manager.reconcileInterrupted(), 0);
    assert.equal((await executionStore.get(scope))?.status, "completed");
  });
});

function result(executionId: string, status: "running" | "waiting_for_interaction" | "completed") {
  return {
    execution_id: executionId,
    status,
    result_type: "json" as const,
    result: {},
    files: [],
    errors: [],
    logs_summary: status
  };
}
