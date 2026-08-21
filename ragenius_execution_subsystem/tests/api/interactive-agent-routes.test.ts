import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

import { buildApp, type AppServices } from "../../src/app.js";
import type { ExecuteAgentRequest } from "../../src/api/schemas/execution-request.schema.js";
import { getEnv } from "../../src/config/env.js";
import { buildRuntimeConfig } from "../../src/config/runtime-config.js";
import type { AgentPolicyDecision } from "../../src/core/agents/agent-policy.js";
import type { AgentProviderExecutionContext } from "../../src/core/agents/agent-provider-context.js";
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
import { InteractiveAgentSessionManager } from "../../src/core/interactive/interactive-agent-session-manager.js";
import { InteractiveCapabilityService } from "../../src/core/interactive/interactive-capability-service.js";
import { InMemoryAgentSessionStore } from "../../src/core/interactive/agent-session-store.js";
import type { AgentInteractionCapabilities, ExecutionScope } from "../../src/core/interactive/interactive-agent-types.js";

const apps: Array<ReturnType<typeof buildApp>> = [];
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
  agent_query: "Ask for approval."
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
const policy = {
  matchedTerms: [], mode: "auto_allow", networkAccess: "deny",
  permissionScope: "agent.read", providerStateAccess: "none",
  providerStateLabels: [], reason: "Test.", riskClass: "agent_read_only",
  workspaceAccess: "read_only"
} satisfies AgentPolicyDecision;
const providerContext = {
  execution_id: scope.executionId,
  authorization: { permission_scope: "agent.read", policy_fingerprint: "test", state: "not_required" },
  operation_plan: [], resolved_artifacts: [], expected_outputs: []
} satisfies AgentProviderExecutionContext;

class RouteTestAdapter implements InteractiveAgentAdapter {
  readonly backend = "codex_cli" as const;
  respondCount = 0;
  followUpCount = 0;
  chatLevel = false;
  private emit?: (event: InteractiveProviderEvent) => Promise<void>;

  async preflight() {
    return {
      available: true,
      capabilities: { ...capabilities, chatLevelInteraction: this.chatLevel },
      protocolVersion: "test-v1",
      transport: "codex_app_server" as const
    };
  }
  async start(input: InteractiveStartInput): Promise<ProviderSessionHandle> {
    this.emit = input.emit;
    return { providerRunRef: "run-1", providerSessionRef: "session-1", providerTurnRef: "turn-1", protectedHandle: {} };
  }
  async respond(_handle: ProviderSessionHandle, _claim: ClaimedInteraction) {
    this.respondCount += 1;
  }
  async cancel() { return { cancelled: true }; }
  async reconcile() { return { state: "running" as const }; }
  async sendFollowUp(handle: ProviderSessionHandle) {
    this.followUpCount += 1;
    return { ...handle, providerRunRef: "run-2", providerTurnRef: "run-2" };
  }
  async requestApproval(): Promise<void> {
    assert.ok(this.emit);
    await this.emit({
      type: "interaction_requested",
      payload: { command_summary: "Create one report." },
      interaction: {
        allowsFreeText: false,
        expiresAt: new Date(Date.now() + 60_000),
        interactionId: "interaction_001",
        options: [],
        policyBindingHash: "protected-policy-hash",
        prompt: "Allow creating one report?",
        providerCorrelationRef: "protected-provider-request",
        type: "approval"
      }
    });
  }
  async complete(): Promise<void> {
    assert.ok(this.emit);
    await this.emit({ type: "run_completed", payload: { status: "completed", summary: "Ready." } });
  }
}

async function createHarness(scopes = ["execution"], chatLevel = false) {
  const executionStore = new InMemoryExecutionStore();
  const agentSessionStore = new InMemoryAgentSessionStore();
  const agentInteractionStore = new InMemoryAgentInteractionStore();
  const agentEventStore = new InMemoryAgentEventStore();
  const agentChatTurnStore = new InMemoryAgentChatTurnStore(agentSessionStore);
  const adapter = new RouteTestAdapter();
  adapter.chatLevel = chatLevel;
  const interactiveSessionManager = new InteractiveAgentSessionManager({
    capabilityService: new InteractiveCapabilityService([adapter]),
    chatTurnStore: agentChatTurnStore,
    eventStore: agentEventStore,
    executionStore,
    interactionStore: agentInteractionStore,
    sessionStore: agentSessionStore
  });
  const runtimeConfig = buildRuntimeConfig(getEnv({
    RAGENIUS_EXECUTION_SERVICE_AUTH_REQUIRED: "true",
    RAGENIUS_EXECUTION_SERVICE_CREDENTIALS_JSON: JSON.stringify([{
      service_id: "ragenius_app", token: "test-token", scopes
    }])
  }));
  const app = buildApp({
    executionStore,
    agentSessionStore,
    agentInteractionStore,
    agentEventStore,
    agentChatTurnStore,
    interactiveSessionManager
  } as unknown as Partial<AppServices>, runtimeConfig);
  apps.push(app);
  await app.ready();
  await executionStore.save({
    executionId: scope.executionId,
    request,
    result: {
      execution_id: scope.executionId, status: "running", result_type: "json",
      result: {}, files: [], errors: [], logs_summary: "Running."
    }
  });
  await interactiveSessionManager.start({
    policy, providerContext, request, requiredInteractionTypes: ["approval"], scope
  });
  await adapter.requestApproval();
  return { adapter, agentEventStore, agentInteractionStore, app, executionStore };
}

function auth() { return { authorization: "Bearer test-token" }; }
function scopeQuery(sessionId = scope.sessionId) {
  return `app_id=${scope.appId}&session_id=${sessionId}`;
}
function approvalResponse(extraResponse: Record<string, unknown> = {}) {
  return {
    expected_version: 1,
    idempotency_key: "response-key-1",
    response: { kind: "approval", decision: "allow_once", ...extraResponse }
  };
}

describe("interactive Agent routes", () => {
  it("returns a scoped chat session and accepts a versioned follow-up", async () => {
    const harness = await createHarness(["execution"], true);
    await harness.adapter.complete();
    const session = await harness.app.inject({
      method: "GET", url: `/v1/executions/${scope.executionId}/chat-session?${scopeQuery()}`, headers: auth()
    });
    assert.equal(session.statusCode, 200);
    assert.equal(session.json().state, "ready_for_follow_up");
    assert.equal(session.json().provider_session_ref, undefined);

    const followUp = await harness.app.inject({
      method: "POST", url: `/v1/executions/${scope.executionId}/follow-ups?${scopeQuery()}`, headers: auth(),
      payload: {
        expected_session_version: session.json().session_version,
        idempotency_key: "follow-up-route-001",
        kind: "reply",
        text: "Use the second title."
      }
    });
    assert.equal(followUp.statusCode, 202);
    assert.equal(followUp.json().outcome, "accepted");
    assert.equal(harness.adapter.followUpCount, 1);
  });

  afterEach(async () => Promise.all(apps.splice(0).map((app) => app.close())));

  it("requires service authentication and execution scope", async () => {
    const { app } = await createHarness();
    const unauthenticated = await app.inject({
      method: "GET", url: `/v1/executions/${scope.executionId}/interactions?${scopeQuery()}`
    });
    const missingScope = await app.inject({
      method: "GET", url: `/v1/executions/${scope.executionId}/interactions`, headers: auth()
    });
    assert.equal(unauthenticated.statusCode, 401);
    assert.equal(missingScope.statusCode, 400);
  });

  it("requires the execution service scope", async () => {
    const { app } = await createHarness(["artifacts:write"]);
    const response = await app.inject({
      method: "GET", url: `/v1/executions/${scope.executionId}/interactions?${scopeQuery()}`, headers: auth()
    });
    assert.equal(response.statusCode, 403);
    assert.equal(response.json().error.code, "SERVICE_SCOPE_REQUIRED");
  });

  it("lists scoped interactions without protected provider fields", async () => {
    const { app } = await createHarness();
    const response = await app.inject({
      method: "GET", url: `/v1/executions/${scope.executionId}/interactions?${scopeQuery()}`, headers: auth()
    });
    const wrongScope = await app.inject({
      method: "GET", url: `/v1/executions/${scope.executionId}/interactions?${scopeQuery("session_other")}`, headers: auth()
    });
    assert.equal(response.statusCode, 200);
    assert.equal(response.json().items[0].interaction_id, "interaction_001");
    assert.equal(response.json().items[0].provider_correlation_ref, undefined);
    assert.equal(response.json().items[0].policy_binding_hash, undefined);
    assert.equal(wrongScope.statusCode, 404);
  });

  it("paginates normalized events by cursor", async () => {
    const { app } = await createHarness();
    const response = await app.inject({
      method: "GET",
      url: `/v1/executions/${scope.executionId}/events?${scopeQuery()}&after_sequence=1&limit=1`,
      headers: auth()
    });
    assert.equal(response.statusCode, 200);
    assert.equal(response.json().items.length, 1);
    assert.equal(response.json().items[0].sequence, 2);
    assert.equal(response.json().items[0].type, "interaction_requested");
    assert.equal(response.json().next_after_sequence, 2);
  });

  it("resolves a response once and replays the same idempotency key", async () => {
    const { adapter, app } = await createHarness();
    const options = {
      method: "POST" as const,
      url: `/v1/executions/${scope.executionId}/interactions/interaction_001/responses?${scopeQuery()}`,
      headers: auth(),
      payload: approvalResponse()
    };
    const first = await app.inject(options);
    const replay = await app.inject(options);
    assert.equal(first.statusCode, 200);
    assert.equal(first.json().outcome, "resolved");
    assert.equal(replay.statusCode, 200);
    assert.equal(replay.json().outcome, "replay");
    assert.equal(adapter.respondCount, 1);
  });

  it("rejects stale, mismatched, and secret-shaped responses before provider contact", async () => {
    const staleHarness = await createHarness();
    const url = `/v1/executions/${scope.executionId}/interactions/interaction_001/responses?${scopeQuery()}`;
    const stale = await staleHarness.app.inject({
      method: "POST", url, headers: auth(),
      payload: { ...approvalResponse(), expected_version: 99 }
    });
    assert.equal(stale.statusCode, 409);
    assert.equal(staleHarness.adapter.respondCount, 0);

    const mismatchHarness = await createHarness();
    const mismatch = await mismatchHarness.app.inject({
      method: "POST", url, headers: auth(),
      payload: {
        expected_version: 1, idempotency_key: "mismatch-key",
        response: { kind: "clarification", text: "Proceed." }
      }
    });
    assert.equal(mismatch.statusCode, 409);
    assert.equal(mismatchHarness.adapter.respondCount, 0);

    const secretHarness = await createHarness();
    const secret = await secretHarness.app.inject({
      method: "POST", url, headers: auth(),
      payload: approvalResponse({ token: "do-not-accept" })
    });
    assert.equal(secret.statusCode, 400);
    assert.equal(secretHarness.adapter.respondCount, 0);
  });

  it("cancels the exact scoped execution", async () => {
    const { app, executionStore } = await createHarness();
    const response = await app.inject({
      method: "POST", url: `/v1/executions/${scope.executionId}/cancel?${scopeQuery()}`, headers: auth()
    });
    assert.equal(response.statusCode, 200);
    assert.equal(response.json().cancelled, true);
    assert.equal((await executionStore.get(scope))?.status, "cancelled");
  });
});
