import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { ExecuteAgentRequest } from "../../src/api/schemas/execution-request.schema.js";
import type { AgentPolicyDecision } from "../../src/core/agents/agent-policy.js";
import type { AgentProviderExecutionContext } from "../../src/core/agents/agent-provider-context.js";
import type { AgentProvider } from "../../src/core/agents/agent-provider.js";
import { ExecutionEngine } from "../../src/core/execution/execution-engine.js";
import { InMemoryExecutionStore } from "../../src/core/execution/execution-store.js";
import { InMemoryAgentEventStore } from "../../src/core/interactive/agent-event-store.js";
import { InMemoryAgentChatTurnStore } from "../../src/core/interactive/agent-chat-turn-store.js";
import { InMemoryAgentInteractionStore } from "../../src/core/interactive/agent-interaction-store.js";
import type {
  ClaimedInteraction,
  InteractiveAgentAdapter,
  InteractiveProviderEvent,
  InteractiveStartInput,
  ProviderSessionHandle
} from "../../src/core/interactive/interactive-agent-adapter.js";
import { ProviderSessionUnavailableError } from "../../src/core/interactive/interactive-agent-adapter.js";
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
  readonly followUps: string[] = [];
  cancelled = false;
  providerSessionUnavailable = false;
  respondError: Error | null = null;
  capabilityOverrides: Partial<AgentInteractionCapabilities> = {};
  available = true;
  onStart?: (input: InteractiveStartInput) => void;
  private emit?: (event: InteractiveProviderEvent) => Promise<void>;

  async preflight() {
    return {
      available: this.available,
      capabilities: { ...capabilities, ...this.capabilityOverrides },
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

  async respond(_handle: ProviderSessionHandle, claim: ClaimedInteraction) {
    if (this.respondError) throw this.respondError;
    this.responses.push(claim.interactionId);
    if (claim.responseSummary.decision === "cancel_execution") {
      await this.emit?.({ type: "run_cancelled", payload: { status: "aborted" } });
    }
  }

  async cancel() {
    this.cancelled = true;
    return { cancelled: true };
  }

  async reconcile() {
    return { state: "running" as const };
  }

  async sendFollowUp(handle: ProviderSessionHandle, claim: { idempotencyKey: string; message: string }) {
    this.followUps.push(claim.message);
    if (this.providerSessionUnavailable) {
      throw new ProviderSessionUnavailableError("Provider session was deleted.");
    }
    return { ...handle, providerRunRef: "run-follow-up", providerTurnRef: "run-follow-up" };
  }

  async send(event: InteractiveProviderEvent): Promise<void> {
    assert.ok(this.emit);
    await this.emit(event);
  }
}

async function createHarness(
  initialStatus: "running" | "pending_confirmation" = "running",
  idleTtlMs = 900_000
) {
  const executionStore = new InMemoryExecutionStore();
  const sessionStore = new InMemoryAgentSessionStore();
  const interactionStore = new InMemoryAgentInteractionStore();
  const eventStore = new InMemoryAgentEventStore();
  const adapter = new FakeAdapter();
  const persistedResponses: Array<{
    executionId: string;
    text: string;
    outputId: string;
  }> = [];
  const chatTurnStore = new InMemoryAgentChatTurnStore(sessionStore);
  await executionStore.save({
    executionId: scope.executionId,
    request,
    result: stateResult(initialStatus)
  });
  const manager = new InteractiveAgentSessionManager({
    capabilityService: new InteractiveCapabilityService([adapter]),
    chatTurnStore,
    eventStore,
    executionStore,
    interactionStore,
    idleTtlMs,
    persistFinalResponse: async (input) => {
      persistedResponses.push({
        executionId: input.executionId,
        outputId: input.output.output_id,
        text: input.text
      });
      return {
        artifact_id: "artifact_interactive_output",
        artifact_type: "agent_output" as const,
        display_name: input.output.display_name,
        mime_type: input.output.media_type
      };
    },
    sessionStore
  });
  return {
    adapter,
    chatTurnStore,
    eventStore,
    executionStore,
    interactionStore,
    manager,
    persistedResponses,
    sessionStore
  };
}

describe("interactive Agent session manager", () => {
  it("fails completion when an explicitly required interaction was not observed", async () => {
    const harness = await createHarness();
    await harness.manager.start({
      policy,
      providerContext,
      request,
      requiredInteractionTypes: ["selection"],
      requiredOccurrenceTypes: ["selection"],
      scope
    });

    await harness.adapter.send({
      type: "run_completed",
      payload: { status: "completed", summary: "Answered without asking." }
    });

    const result = await harness.executionStore.get(scope);
    assert.equal(result?.status, "failed");
    assert.equal(result?.errors?.[0]?.code, "REQUIRED_INTERACTION_NOT_OBSERVED");
    assert.equal(harness.adapter.cancelled, true);
  });

  it("allows completion after the explicitly required interaction was observed", async () => {
    const harness = await createHarness();
    await harness.manager.start({
      policy,
      providerContext,
      request,
      requiredInteractionTypes: ["selection"],
      requiredOccurrenceTypes: ["selection"],
      scope
    });
    await harness.adapter.send(interactionEvent("interaction-selection", "selection"));
    const interaction = (await harness.interactionStore.list(scope))[0]!;
    await harness.manager.respond({
      ...scope,
      expectedVersion: interaction.version,
      idempotencyKey: "selection-response",
      interactionId: interaction.interactionId,
      responseSummary: { kind: "selection", option_ids: ["markdown"] }
    });
    await harness.adapter.send({
      type: "run_completed",
      payload: { status: "completed", summary: "Answered after asking." }
    });

    assert.equal((await harness.executionStore.get(scope))?.status, "completed");
  });

  it("rejects provider completion while an interaction is still unresolved", async () => {
    const harness = await createHarness();
    await harness.manager.start({
      policy,
      providerContext,
      request,
      requiredInteractionTypes: ["selection"],
      requiredOccurrenceTypes: ["selection"],
      scope
    });
    await harness.adapter.send(interactionEvent("interaction-selection", "selection"));

    await harness.adapter.send({
      type: "run_completed",
      payload: { status: "completed", summary: "Provider stopped waiting." }
    });

    const result = await harness.executionStore.get(scope);
    assert.equal(result?.status, "failed");
    assert.equal(result?.errors?.[0]?.code, "PROVIDER_COMPLETED_WITH_PENDING_INTERACTION");
  });

  it("rejects protected values in interaction presentation before persistence", async () => {
    const harness = await createHarness();
    await harness.manager.start({
      policy,
      providerContext,
      request,
      requiredInteractionTypes: [],
      scope
    });

    await harness.adapter.send({
      ...interactionEvent("interaction-auth", "authentication_handoff"),
      interaction: {
        ...interactionEvent("interaction-auth", "authentication_handoff").interaction!,
        presentation: {
          launchAvailable: true,
          targetLabel: "Unsafe sign-in",
          url: "https://accounts.example.test/?token=secret"
        } as never
      }
    });
    assert.deepEqual(await harness.interactionStore.list(scope), []);
    const result = await harness.executionStore.get(scope);
    assert.equal(result?.status, "failed");
    assert.equal(result?.errors?.[0]?.code, "INVALID_PROVIDER_INTERACTION");
  });

  it("returns an unverified authentication handoff to pending for retry", async () => {
    const harness = await createHarness();
    harness.adapter.capabilityOverrides = {
      interactionTypes: [...capabilities.interactionTypes, "authentication_handoff"]
    };
    harness.adapter.respondError = new Error("AUTHENTICATION_HANDOFF_NOT_VERIFIED");
    await harness.manager.start({
      policy,
      providerContext,
      request,
      requiredInteractionTypes: ["authentication_handoff"],
      scope
    });
    await harness.adapter.send(interactionEvent("interaction-auth", "authentication_handoff"));
    const interaction = (await harness.interactionStore.list(scope))[0]!;

    const response = await harness.manager.respond({
      ...scope,
      expectedVersion: interaction.version,
      idempotencyKey: "auth-attempt-1",
      interactionId: interaction.interactionId,
      responseSummary: { kind: "user_action", outcome: "completed" }
    });

    assert.equal(response.outcome, "verification_failed");
    const retryable = (await harness.interactionStore.list(scope))[0]!;
    assert.equal(retryable.state, "pending");
    assert.equal(retryable.version, 3);
    assert.equal((await harness.executionStore.get(scope))?.status, "waiting_for_interaction");
  });

  it("returns the accumulated final response without creating an artifact when saving is off", async () => {
    const harness = await createHarness();
    await harness.manager.start({
      policy,
      providerContext,
      request,
      inferredInteractionTypes: ["selection"],
      requiredInteractionTypes: ["selection"],
      scope
    });
    await harness.adapter.send({ type: "message_delta", payload: { delta: "Plain " } });
    await harness.adapter.send({ type: "message_delta", payload: { delta: "answer" } });
    await harness.adapter.send({
      type: "run_completed",
      payload: { status: "completed", summary: "Answered." }
    });

    const result = await harness.executionStore.get(scope);
    assert.equal(result?.status, "completed");
    assert.equal((result?.result as Record<string, unknown>)?.output_text, "Plain answer");
    assert.deepEqual((result?.result as Record<string, unknown>)?.artifacts, []);
    assert.deepEqual(
      (result?.result as Record<string, unknown>)?.interaction_requirements,
      { inferred_types: ["selection"] }
    );
    assert.deepEqual(harness.persistedResponses, []);
  });

  it("persists the accumulated final response when reusable output is requested", async () => {
    const harness = await createHarness();
    const saveRequest: ExecuteAgentRequest = {
      ...request,
      expected_outputs: [{
        output_id: "agent_output",
        artifact_type: "agent_output",
        media_type: "text/markdown",
        persist_as_artifact: true,
        required: false
      }]
    };
    await harness.manager.start({
      policy,
      providerContext: { ...providerContext, expected_outputs: saveRequest.expected_outputs ?? [] },
      request: saveRequest,
      requiredInteractionTypes: ["selection"],
      scope
    });
    await harness.adapter.send({ type: "message_delta", payload: { delta: "# Answer\n" } });
    await harness.adapter.send({ type: "message_delta", payload: { delta: "Markdown selected." } });
    await harness.adapter.send({
      type: "run_completed",
      payload: { status: "completed", summary: "Answered." }
    });

    assert.deepEqual(harness.persistedResponses, [{
      executionId: scope.executionId,
      outputId: "agent_output",
      text: "# Answer\nMarkdown selected."
    }]);
    const result = await harness.executionStore.get(scope);
    assert.deepEqual((result?.result as Record<string, unknown>)?.artifacts, [{
      artifact_id: "artifact_interactive_output",
      artifact_type: "agent_output",
      display_name: "agent_output.md",
      mime_type: "text/markdown"
    }]);
  });

  it("keeps a chat-capable OpenClaw session ready and starts a same-session follow-up", async () => {
    const harness = await createHarness();
    harness.adapter.capabilityOverrides = {
      chatLevelInteraction: true,
      exactlyOnceFollowUp: false,
      sameSessionContinuation: true,
      structuredWaitSignal: false
    };
    await harness.manager.start({ policy, providerContext, request, requiredInteractionTypes: [], scope });
    await harness.adapter.send({ type: "run_completed", payload: { summary: "Choose a title." } });

    assert.equal((await harness.executionStore.get(scope))?.status, "ready_for_follow_up");
    const session = await harness.sessionStore.getByExecution(scope);
    const result = await harness.manager.followUp({
      ...scope,
      expectedSessionVersion: session?.sessionVersion ?? 0,
      idempotencyKey: "follow-up-001",
      kind: "reply",
      text: "Use the second title."
    });

    assert.equal(result.outcome, "accepted");
    assert.deepEqual(harness.adapter.followUps, ["Use the second title."]);
    assert.equal((await harness.executionStore.get(scope))?.status, "running");
    assert.equal((await harness.sessionStore.getByExecution(scope))?.providerRunRef, "run-follow-up");
  });

  it("preserves an idle chat session during orderly shutdown", async () => {
    const harness = await createHarness();
    harness.adapter.capabilityOverrides = { chatLevelInteraction: true };
    await harness.manager.start({ policy, providerContext, request, requiredInteractionTypes: [], scope });
    await harness.adapter.send({ type: "run_completed", payload: { status: "completed" } });

    await harness.manager.shutdown();

    assert.equal((await harness.sessionStore.getByExecution(scope))?.state, "ready_for_follow_up");
    assert.equal((await harness.executionStore.get(scope))?.status, "ready_for_follow_up");
    assert.equal(harness.adapter.cancelled, false);
  });

  it("fails closed without ambiguous delivery when the provider session is unavailable", async () => {
    const harness = await createHarness();
    harness.adapter.capabilityOverrides = { chatLevelInteraction: true };
    await harness.manager.start({ policy, providerContext, request, requiredInteractionTypes: [], scope });
    await harness.adapter.send({ type: "run_completed", payload: { status: "completed" } });
    const session = await harness.sessionStore.getByExecution(scope);
    harness.adapter.providerSessionUnavailable = true;

    const result = await harness.manager.followUp({
      ...scope,
      expectedSessionVersion: session?.sessionVersion ?? 0,
      idempotencyKey: "missing-provider-session",
      kind: "continue"
    });

    assert.equal(result.outcome, "provider_session_unavailable");
    assert.equal((await harness.sessionStore.getByExecution(scope))?.state, "failed");
    assert.equal((await harness.executionStore.get(scope))?.status, "failed");
  });

  it("closes an idle chat session after its bounded TTL", async () => {
    const harness = await createHarness("running", 20);
    harness.adapter.capabilityOverrides = { chatLevelInteraction: true };
    await harness.manager.start({ policy, providerContext, request, requiredInteractionTypes: [], scope });
    await harness.adapter.send({ type: "run_completed", payload: { status: "completed" } });
    assert.ok((await harness.sessionStore.getByExecution(scope))?.idleExpiresAt);

    await new Promise((resolve) => setTimeout(resolve, 60));

    assert.equal((await harness.sessionStore.getByExecution(scope))?.state, "completed");
    assert.equal((await harness.executionStore.get(scope))?.status, "completed");
  });

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

  it("allocates one agent session id before starting the provider", async () => {
    const harness = await createHarness();
    let providerAgentSessionId = "";
    harness.adapter.onStart = (input) => {
      providerAgentSessionId = input.agentSessionId;
    };

    const result = await harness.manager.start({
      policy, providerContext, request, requiredInteractionTypes: [], scope
    });

    assert.equal(result.started, true);
    assert.match(providerAgentSessionId, /^agent_session_[a-f0-9]+$/);
    assert.equal(
      (await harness.sessionStore.getByExecution(scope))?.agentSessionId,
      providerAgentSessionId
    );
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

  it("does not restore running state after provider-confirmed cancel_execution", async () => {
    const harness = await createHarness();
    await harness.manager.start({
      policy, providerContext, request, requiredInteractionTypes: ["approval"], scope
    });
    await harness.adapter.send(interactionEvent("interaction-cancel", "approval"));

    const result = await harness.manager.respond({
      ...scope,
      expectedVersion: 1,
      idempotencyKey: "response-cancel",
      interactionId: "interaction-cancel",
      responseSummary: { decision: "cancel_execution", kind: "approval" }
    });

    assert.equal(result.outcome, "resolved");
    assert.equal((await harness.executionStore.get(scope))?.status, "cancelled");
    assert.equal((await harness.sessionStore.getByExecution(scope))?.state, "cancelled");
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

  it("fails closed when chat-level interaction is required but disabled", async () => {
    const harness = await createHarness();
    const result = await harness.manager.start({
      request,
      policy,
      providerContext,
      requiredChatLevelInteraction: true,
      requiredInteractionTypes: [],
      scope
    });

    assert.equal(result.started, false);
    assert.equal(result.failureCode, "INTERACTIVE_CAPABILITY_UNAVAILABLE");
    assert.match(result.reason, /chat-level interaction/);
  });

  it("fails closed when reviewed recovery exceeds adapter guarantees", async () => {
    const harness = await createHarness();
    harness.adapter.capabilityOverrides = { sameTurnResume: false };

    const result = await harness.manager.start({
      request,
      policy,
      providerContext,
      requiredInteractionTypes: ["approval"],
      requiredRecoveryClass: "turn_resumable",
      scope
    });

    assert.equal(result.started, false);
    assert.equal(result.failureCode, "INTERACTIVE_CAPABILITY_UNAVAILABLE");
    assert.match(result.reason, /same-turn recovery/);
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

  it("authoritatively cancels a chat session that became idle before cancellation", async () => {
    const harness = await createHarness();
    harness.adapter.capabilityOverrides = { chatLevelInteraction: true };
    await harness.manager.start({ policy, providerContext, request, requiredInteractionTypes: [], scope });
    await harness.adapter.send({ type: "run_completed", payload: { status: "completed" } });

    const result = await harness.manager.cancel(scope);

    assert.equal(result.cancelled, true);
    assert.equal((await harness.sessionStore.getByExecution(scope))?.state, "cancelled");
    assert.equal((await harness.executionStore.get(scope))?.status, "cancelled");
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
