import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { ExecuteAgentRequest } from "../../src/api/schemas/execution-request.schema.js";
import type { AgentPolicyDecision } from "../../src/core/agents/agent-policy.js";
import type { AgentProviderExecutionContext } from "../../src/core/agents/agent-provider-context.js";
import type { AgentProvider } from "../../src/core/agents/agent-provider.js";
import { ExecutionEngine } from "../../src/core/execution/execution-engine.js";
import { InMemoryExecutionStore } from "../../src/core/execution/execution-store.js";
import { InMemoryAgentEventStore } from "../../src/core/interactive/agent-event-store.js";
import { InMemoryAgentInteractionStore } from "../../src/core/interactive/agent-interaction-store.js";
import type {
  InteractiveAgentAdapter,
  InteractiveProviderEvent,
  InteractiveStartInput,
  ProviderSessionHandle
} from "../../src/core/interactive/interactive-agent-adapter.js";
import { InteractiveCapabilityService } from "../../src/core/interactive/interactive-capability-service.js";
import { InteractiveAgentSessionManager } from "../../src/core/interactive/interactive-agent-session-manager.js";
import { InMemoryAgentSessionStore } from "../../src/core/interactive/agent-session-store.js";
import type {
  AgentInteractionCapabilities,
  AgentInteractionType,
  ExecutionScope
} from "../../src/core/interactive/interactive-agent-types.js";

const scope: ExecutionScope = {
  appId: "app_001",
  executionId: "execution_001",
  sessionId: "session_001"
};

const request: ExecuteAgentRequest = {
  request_type: "execute_agent",
  app_id: scope.appId,
  session_id: scope.sessionId,
  agent_backend: "codex_cli",
  agent_query: "Complete the task and ask when a decision is required."
};

const capabilities: AgentInteractionCapabilities = {
  cancellation: true,
  eventReplay: "none",
  interactionTypes: ["approval", "clarification", "selection"],
  protocolTransport: true,
  reconnectReconciliation: false,
  sameSessionContinuation: true,
  sameTurnResume: true
};

const policy: AgentPolicyDecision = {
  matchedTerms: [],
  mode: "auto_allow",
  networkAccess: "deny",
  permissionScope: "agent.read",
  providerStateAccess: "none",
  providerStateLabels: [],
  reason: "Read-only request.",
  riskClass: "agent_read_only",
  workspaceAccess: "read_only"
};

const providerContext: AgentProviderExecutionContext = {
  execution_id: scope.executionId,
  authorization: {
    permission_scope: "agent.read",
    policy_fingerprint: "policy-test",
    state: "not_required"
  },
  operation_plan: [],
  resolved_artifacts: [],
  expected_outputs: []
};

class FakeAdapter implements InteractiveAgentAdapter {
  readonly backend = "codex_cli" as const;
  readonly responses: string[] = [];
  cancelled = false;
  available = true;
  onStart?: (input: InteractiveStartInput) => void;
  private emit?: (event: InteractiveProviderEvent) => Promise<void>;

  async preflight() {
    return {
      available: this.available,
      capabilities,
      protocolVersion: "test-v1",
      ...(!this.available
        ? { reason: "Interactive transport is unavailable." }
        : {}),
      transport: "codex_app_server" as const
    };
  }

  async start(input: InteractiveStartInput): Promise<ProviderSessionHandle> {
    this.emit = input.emit;
    this.onStart?.(input);
    return {
      providerRunRef: "run-1",
      providerSessionRef: "provider-session-1",
      providerTurnRef: "turn-1",
      protectedHandle: { process: "not-public" }
    };
  }

  async respond(_handle: ProviderSessionHandle, claim: { interactionId: string }) {
    this.responses.push(claim.interactionId);
  }

  async cancel() {
    this.cancelled = true;
    return { cancelled: true };
  }

  async reconcile() {
    return { state: "running" as const };
  }

  async send(event: InteractiveProviderEvent): Promise<void> {
    assert.ok(this.emit);
    await this.emit(event);
  }
}

async function createHarness(initialStatus: "running" | "pending_confirmation" = "running") {
  const executionStore = new InMemoryExecutionStore();
  const sessionStore = new InMemoryAgentSessionStore();
  const interactionStore = new InMemoryAgentInteractionStore();
  const eventStore = new InMemoryAgentEventStore();
  const adapter = new FakeAdapter();
  await executionStore.save({
    executionId: scope.executionId,
    request,
    result: stateResult(initialStatus)
  });
  const manager = new InteractiveAgentSessionManager({
    capabilityService: new InteractiveCapabilityService([adapter]),
    eventStore,
    executionStore,
    interactionStore,
    sessionStore
  });
  return { adapter, eventStore, executionStore, interactionStore, manager, sessionStore };
}

describe("interactive Agent session manager", () => {
  it("persists the provider handle before processing an early interaction", async () => {
    const harness = await createHarness();
    let persistedDuringEvent = false;
    const createInteraction = harness.interactionStore.create.bind(
      harness.interactionStore
    );
    harness.interactionStore.create = async (input) => {
      persistedDuringEvent = Boolean(await harness.sessionStore.getByExecution(scope));
      return createInteraction(input);
    };
    harness.adapter.onStart = (input) => {
      void input.emit(interactionEvent("interaction-1", "approval"));
    };

    await harness.manager.start({ policy, providerContext, request, requiredInteractionTypes: ["approval"], scope });
    await new Promise((resolve) => setTimeout(resolve, 0));

    assert.equal(persistedDuringEvent, true);
    assert.equal((await harness.executionStore.get(scope))?.status, "waiting_for_interaction");
    assert.equal((await harness.interactionStore.list(scope)).length, 1);
  });

  it("runs through multiple interaction cycles and completes", async () => {
    const harness = await createHarness();
    await harness.manager.start({ policy, providerContext, request, requiredInteractionTypes: ["approval", "clarification"], scope });

    await harness.adapter.send(interactionEvent("interaction-1", "approval"));
    assert.equal((await harness.executionStore.get(scope))?.status, "waiting_for_interaction");
    assert.equal((await harness.manager.respond({
      ...scope,
      expectedVersion: 1,
      idempotencyKey: "response-1",
      interactionId: "interaction-1",
      responseSummary: { decision: "allow_once", kind: "approval" }
    })).outcome, "resolved");
    assert.equal((await harness.executionStore.get(scope))?.status, "running");

    await harness.adapter.send(interactionEvent("interaction-2", "clarification"));
    await harness.manager.respond({
      ...scope,
      expectedVersion: 1,
      idempotencyKey: "response-2",
      interactionId: "interaction-2",
      responseSummary: { kind: "clarification", text: "Use option A." }
    });
    await harness.adapter.send({ type: "run_completed", payload: { summary: "Complete." } });

    assert.equal((await harness.executionStore.get(scope))?.status, "completed");
    assert.deepEqual(harness.adapter.responses, ["interaction-1", "interaction-2"]);
    assert.deepEqual(
      (await harness.eventStore.list({ ...scope, afterSequence: 0, limit: 20 })).map((event) => event.type),
      [
        "session_started",
        "interaction_requested",
        "interaction_resolved",
        "interaction_requested",
        "interaction_resolved",
        "run_completed"
      ]
    );
  });

  it("fails closed when the adapter lacks a required capability", async () => {
    const harness = await createHarness();
    const result = await harness.manager.start({
      request,
      policy,
      providerContext,
      requiredInteractionTypes: ["authentication_handoff"],
      scope
    });

    assert.equal(result.started, false);
    assert.equal(result.failureCode, "INTERACTIVE_CAPABILITY_UNAVAILABLE");
    assert.equal((await harness.executionStore.get(scope))?.status, "failed");
    assert.equal(await harness.sessionStore.getByExecution(scope), null);
  });

  it("cancels pending interactions and reaches terminal cancelled", async () => {
    const harness = await createHarness();
    await harness.manager.start({ policy, providerContext, request, requiredInteractionTypes: ["approval"], scope });
    await harness.adapter.send(interactionEvent("interaction-1", "approval"));

    const result = await harness.manager.cancel(scope);

    assert.equal(result.cancelled, true);
    assert.equal(harness.adapter.cancelled, true);
    assert.equal((await harness.executionStore.get(scope))?.status, "cancelled");
    assert.equal((await harness.interactionStore.list(scope))[0]?.state, "cancelled");
  });

  it("fails without contacting the provider when an interaction expired", async () => {
    const harness = await createHarness();
    await harness.manager.start({ policy, providerContext, request, requiredInteractionTypes: ["approval"], scope });
    await harness.adapter.send(interactionEvent("interaction-1", "approval", new Date(0)));

    const result = await harness.manager.respond({
      ...scope,
      expectedVersion: 1,
      idempotencyKey: "expired-response",
      interactionId: "interaction-1",
      now: new Date(1),
      responseSummary: { decision: "allow_once", kind: "approval" }
    });

    assert.equal(result.outcome, "expired");
    assert.deepEqual(harness.adapter.responses, []);
    assert.equal((await harness.executionStore.get(scope))?.status, "failed");
    assert.equal(harness.adapter.cancelled, true);
  });

  it("expires an unanswered interaction and terminates its provider session", async () => {
    const harness = await createHarness();
    await harness.manager.start({
      policy, providerContext, request, requiredInteractionTypes: ["approval"], scope
    });
    await harness.adapter.send(
      interactionEvent("interaction-expiring", "approval", new Date(Date.now() + 20))
    );

    await new Promise((resolve) => setTimeout(resolve, 60));

    assert.equal((await harness.executionStore.get(scope))?.status, "failed");
    assert.equal(harness.adapter.cancelled, true);
  });

  it("terminates every active provider session during shutdown", async () => {
    const harness = await createHarness();
    await harness.manager.start({
      policy, providerContext, request, requiredInteractionTypes: [], scope
    });

    await harness.manager.shutdown();

    assert.equal(harness.adapter.cancelled, true);
    assert.equal((await harness.executionStore.get(scope))?.status, "failed");
  });

  it("does not consume pre-run pending confirmation", async () => {
    const harness = await createHarness("pending_confirmation");
    const result = await harness.manager.start({ policy, providerContext, request, requiredInteractionTypes: [], scope });

    assert.equal(result.started, false);
    assert.equal(result.failureCode, "EXECUTION_NOT_RUNNING");
    assert.equal((await harness.executionStore.get(scope))?.status, "pending_confirmation");
    assert.equal(await harness.sessionStore.getByExecution(scope), null);
  });

  it("fails closed on an oversized provider interaction", async () => {
    const harness = await createHarness();
    await harness.manager.start({
      policy,
      providerContext,
      request,
      requiredInteractionTypes: ["clarification"],
      scope
    });

    await harness.adapter.send({
      ...interactionEvent("interaction-oversized", "clarification"),
      interaction: {
        ...interactionEvent("interaction-oversized", "clarification").interaction!,
        prompt: "x".repeat(2001)
      }
    });

    assert.equal((await harness.executionStore.get(scope))?.status, "failed");
    assert.equal((await harness.interactionStore.list(scope)).length, 0);
  });

  it("dispatches through the interactive manager only when explicitly selected", async () => {
    const executionStore = new InMemoryExecutionStore();
    const sessionStore = new InMemoryAgentSessionStore();
    const interactionStore = new InMemoryAgentInteractionStore();
    const eventStore = new InMemoryAgentEventStore();
    const adapter = new FakeAdapter();
    const manager = new InteractiveAgentSessionManager({
      capabilityService: new InteractiveCapabilityService([adapter]),
      eventStore,
      executionStore,
      interactionStore,
      sessionStore
    });
    let autonomousCalls = 0;
    const autonomousProvider: AgentProvider = {
      backend: "codex_cli",
      async execute() {
        autonomousCalls += 1;
        return { status: "completed" };
      }
    };
    const engine = new ExecutionEngine({
      agentProviders: new Map([["codex_cli", autonomousProvider]]),
      executionStore,
      interactiveRequirementResolver: () => ({ requiredInteractionTypes: ["approval"] }),
      interactiveSessionManager: manager
    });

    const result = await engine.execute(request, { executionId: scope.executionId });

    assert.equal(result.status, "running");
    assert.equal(autonomousCalls, 0);
    assert.ok(await sessionStore.getByExecution(scope));
  });
});

function interactionEvent(
  interactionId: string,
  type: AgentInteractionType,
  expiresAt = new Date(Date.now() + 60_000)
): InteractiveProviderEvent {
  return {
    type: "interaction_requested",
    interaction: {
      allowsFreeText: type === "clarification",
      expiresAt,
      interactionId,
      options: [],
      policyBindingHash: `policy-${interactionId}`,
      prompt: `Resolve ${interactionId}`,
      providerCorrelationRef: `provider-${interactionId}`,
      type
    },
    payload: {}
  };
}

function stateResult(status: "running" | "pending_confirmation") {
  return {
    execution_id: scope.executionId,
    status,
    result_type: "json" as const,
    result: {},
    files: [],
    errors: [],
    logs_summary: status
  };
}
