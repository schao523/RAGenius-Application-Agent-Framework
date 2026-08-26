import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { ExecuteAgentRequest } from "../../src/api/schemas/execution-request.schema.js";
import { InMemoryExecutionStore } from "../../src/core/execution/execution-store.js";
import { InMemoryAgentEventStore } from "../../src/core/interactive/agent-event-store.js";
import { InMemoryAgentChatTurnStore } from "../../src/core/interactive/agent-chat-turn-store.js";
import { InMemoryAgentInteractionStore } from "../../src/core/interactive/agent-interaction-store.js";
import { InMemoryAgentSessionStore } from "../../src/core/interactive/agent-session-store.js";
import { InteractiveCapabilityService } from "../../src/core/interactive/interactive-capability-service.js";
import { InteractiveAgentSessionManager } from "../../src/core/interactive/interactive-agent-session-manager.js";
import type { AgentSessionState, ExecutionScope } from "../../src/core/interactive/interactive-agent-types.js";
import type { InteractiveAgentAdapter, ProviderSessionHandle } from "../../src/core/interactive/interactive-agent-adapter.js";

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
  it("rehydrates a compatible idle chat session and accepts a follow-up", async () => {
    const executionStore = new InMemoryExecutionStore();
    const sessionStore = new InMemoryAgentSessionStore();
    const interactionStore = new InMemoryAgentInteractionStore();
    const eventStore = new InMemoryAgentEventStore();
    const chatTurnStore = new InMemoryAgentChatTurnStore(sessionStore);
    const scope = { appId: "app_1", executionId: "execution_idle", sessionId: "session_1" };
    await executionStore.save({ executionId: scope.executionId, request: { ...request(scope), agent_backend: "openclaw_cli" }, result: result(scope.executionId, "ready_for_follow_up") });
    await sessionStore.create({
      ...scope, agentSessionId: "agent_session_idle", backend: "openclaw_cli",
      capabilitySnapshot: {
        cancellation: true, chatLevelInteraction: true, eventReplay: "none",
        interactionTypes: [], protocolTransport: true, reconnectReconciliation: true,
        sameSessionContinuation: true, sameTurnResume: false
      },
      continuationMode: "same_session_new_turn", policyBindingHash: "policy-binding",
      protocolVersion: "2026.6.8", providerRunRef: "run_done",
      providerSessionRef: "session-stable", providerTurnRef: "run_done",
      state: "ready_for_follow_up", transport: "openclaw_gateway"
    });
    const adapter: InteractiveAgentAdapter = {
      backend: "openclaw_cli",
      async preflight() { throw new Error("not used"); },
      async start() { throw new Error("not used"); },
      async respond() { throw new Error("not used"); },
      async cancel() { return { cancelled: true }; },
      async reconcile() { return { state: "completed" }; },
      async restore() {
        return { providerRunRef: "run_done", providerSessionRef: "session-stable", providerTurnRef: "run_done", protectedHandle: {} };
      },
      async sendFollowUp(handle: ProviderSessionHandle) {
        return { ...handle, providerRunRef: "run_next", providerTurnRef: "run_next" };
      }
    };
    const manager = new InteractiveAgentSessionManager({
      capabilityService: new InteractiveCapabilityService([adapter]), chatTurnStore,
      eventStore, executionStore, interactionStore, sessionStore
    });

    await manager.reconcileInterrupted();
    const response = await manager.followUp({
      ...scope, expectedSessionVersion: 1, idempotencyKey: "follow-up-restart",
      kind: "continue"
    });

    assert.equal(response.outcome, "accepted");
    assert.equal((await sessionStore.getByExecution(scope))?.providerRunRef, "run_next");
  });

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
          interactionTypes: ["authentication_handoff"],
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
          options: [],
          presentation: {
            completionLabel: "Authentication completed",
            launchAvailable: true,
            targetHost: "accounts.example.com",
            targetLabel: "Example sign-in"
          },
          policyBindingHash: "policy-binding",
          prompt: "Complete sign-in in the provider window.",
          providerCorrelationRef: "provider-interaction",
          type: "authentication_handoff"
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

function result(executionId: string, status: "running" | "waiting_for_interaction" | "ready_for_follow_up" | "completed") {
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
