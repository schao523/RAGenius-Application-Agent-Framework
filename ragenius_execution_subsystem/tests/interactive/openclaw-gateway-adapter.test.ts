import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { ExecuteAgentRequest } from "../../src/api/schemas/execution-request.schema.js";
import type { AgentPolicyDecision } from "../../src/core/agents/agent-policy.js";
import type { AgentProviderExecutionContext } from "../../src/core/agents/agent-provider-context.js";
import {
  OpenClawGatewayAdapter,
  type OpenClawGatewayConnection,
  type OpenClawGatewayConnectionFactory
} from "../../src/core/interactive/openclaw-gateway-adapter.js";
import {
  buildOpenClawInteractiveSessionKey,
  OpenClawGatewayEventTracker
} from "../../src/core/interactive/openclaw-gateway-events.js";
import {
  buildOpenClawConnectParams,
  createOpenClawGatewayRequest,
  OpenClawGatewayClient,
  redactOpenClawGatewayDiagnostic
} from "../../src/core/interactive/openclaw-gateway-client.js";
import type {
  ClaimedInteraction,
  InteractiveProviderEvent
} from "../../src/core/interactive/interactive-agent-adapter.js";

const request: ExecuteAgentRequest = {
  request_type: "execute_agent",
  app_id: "app_001",
  session_id: "session_001",
  agent_backend: "openclaw_cli",
  agent_query: "Create a report."
};

const policy: AgentPolicyDecision = {
  matchedTerms: [],
  mode: "auto_allow",
  networkAccess: "deny",
  permissionScope: "agent.workspace_write",
  providerStateAccess: "scoped_write",
  providerStateLabels: ["openclaw_agent_state"],
  reason: "Test policy.",
  riskClass: "agent_workspace_write",
  workspaceAccess: "scoped_write"
};

const providerContext: AgentProviderExecutionContext = {
  execution_id: "execution_001",
  authorization: {
    permission_scope: "agent.workspace_write",
    policy_fingerprint: "policy-fingerprint",
    state: "not_required"
  },
  operation_plan: [],
  resolved_artifacts: [],
  expected_outputs: []
};

class FakeGatewayConnection implements OpenClawGatewayConnection {
  readonly requests: Array<{ method: string; params?: unknown }> = [];
  readonly hello = {
    protocolVersion: 4,
    serverVersion: "2026.6.8",
    scopes: ["operator.admin", "operator.approvals"]
  };
  execPolicy = { security: "allowlist", ask: "on-miss", askFallback: "deny" };
  agentRequestCount = 0;
  waitResponse: Record<string, unknown> = {
    runId: "run-001", status: "error", error: "aborted", stopReason: "aborted"
  };
  private eventHandler?: (event: Record<string, unknown>) => Promise<void>;
  private gapHandler?: (gap: { actual: number; expected: number }) => Promise<void>;
  private closeHandler?: (error?: Error) => Promise<void>;

  async request(method: string, params?: unknown): Promise<unknown> {
    this.requests.push({ method, params });
    if (method === "config.get") {
      return { config: { tools: { exec: this.execPolicy } } };
    }
    if (method === "agent") {
      this.agentRequestCount += 1;
      return { runId: `run-${String(this.agentRequestCount).padStart(3, "0")}`, sessionId: "provider-session-001", status: "accepted" };
    }
    if (method === "exec.approval.resolve") return { ok: true };
    if (method === "chat.abort") return { ok: true };
    if (method === "agent.wait") {
      return this.waitResponse;
    }
    if (method === "sessions.list") return { sessions: [] };
    throw new Error(`Unexpected Gateway method: ${method}`);
  }

  onEvent(handler: (event: Record<string, unknown>) => Promise<void>): void {
    this.eventHandler = handler;
  }

  onGap(handler: (gap: { actual: number; expected: number }) => Promise<void>): void {
    this.gapHandler = handler;
  }

  onClose(handler: (error?: Error) => Promise<void>): void {
    this.closeHandler = handler;
  }

  async reconnect(): Promise<typeof this.hello> { return this.hello; }
  async close(): Promise<void> { return; }
  async emit(event: Record<string, unknown>): Promise<void> {
    assert.ok(this.eventHandler);
    await this.eventHandler(event);
  }
  async gap(expected: number, actual: number): Promise<void> {
    assert.ok(this.gapHandler);
    await this.gapHandler({ actual, expected });
  }
  async disconnect(error = new Error("Gateway disconnected")): Promise<void> {
    await this.closeHandler?.(error);
  }
}

class FakeGatewayFactory implements OpenClawGatewayConnectionFactory {
  readonly connection = new FakeGatewayConnection();
  connectCount = 0;
  async connect(): Promise<OpenClawGatewayConnection> {
    this.connectCount += 1;
    return this.connection;
  }
}

describe("OpenClaw Gateway protocol helpers", () => {
  it("completes the authenticated challenge handshake without deadlocking RPC responses", async () => {
    const client = new OpenClawGatewayClient({
      credential: "gateway-secret",
      gatewayUrl: "ws://127.0.0.1:18789",
      maxMessageBytes: 65536,
      reconnectBaseDelayMs: 1,
      reconnectMaxAttempts: 1,
      rpcTimeoutMs: 1000,
      scopes: ["operator.admin", "operator.approvals"]
    }, FakeSocket as never);
    await client.connect();
    assert.equal(client.hello.serverVersion, "2026.6.8");
    assert.deepEqual(await client.request("agent.wait", { runId: "run-1" }), {
      runId: "run-1", status: "completed"
    });
    assert.equal(FakeSocket.last.sent.some((frame) => frame.includes("gateway-secret")), true);
    await client.close();
  });

  it("builds authenticated connect and unique correlated request frames", () => {
    assert.deepEqual(buildOpenClawConnectParams({
      credential: "gateway-secret",
      scopes: ["operator.admin", "operator.approvals"]
    }), {
      minProtocol: 4,
      maxProtocol: 4,
      client: {
        id: "gateway-client",
        displayName: "RAGenius Execution Subsystem",
        version: "0.1.0",
        platform: "windows",
        mode: "backend"
      },
      caps: [],
      auth: { token: "gateway-secret" },
      role: "operator",
      scopes: ["operator.admin", "operator.approvals"]
    });
    const first = createOpenClawGatewayRequest("agent.wait", { runId: "run-1" });
    const second = createOpenClawGatewayRequest("agent.wait", { runId: "run-1" });
    assert.equal(first.type, "req");
    assert.notEqual(first.id, second.id);
  });

  it("redacts credentials recursively from diagnostics", () => {
    const redacted = redactOpenClawGatewayDiagnostic({
      message: "Connection failed for gateway-secret",
      nested: { token: "gateway-secret" }
    }, "gateway-secret");
    assert.deepEqual(redacted, {
      message: "Connection failed for [REDACTED]",
      nested: { token: "[REDACTED]" }
    });
  });

  it("uses a stable session key without execution id", () => {
    const key = buildOpenClawInteractiveSessionKey({
      appId: "app_001",
      sessionId: "session_001",
      agentSessionId: "agent_session_001"
    });
    assert.equal(key, "ragenius:app_001:session_001:agent_session_001");
    assert.equal(key.includes("execution"), false);
    assert.throws(() => buildOpenClawInteractiveSessionKey({
      appId: "../app", sessionId: "session", agentSessionId: "agent"
    }), /unsafe/i);
  });

  it("deduplicates sequenced and unsequenced events and detects gaps", () => {
    const tracker = new OpenClawGatewayEventTracker();
    assert.deepEqual(tracker.accept({ type: "event", event: "agent", seq: 7, payload: {} }), {
      accepted: true
    });
    assert.deepEqual(tracker.accept({ type: "event", event: "agent", seq: 7, payload: {} }), {
      accepted: false, duplicate: true
    });
    assert.deepEqual(tracker.accept({ type: "event", event: "agent", seq: 9, payload: {} }), {
      accepted: true, gap: { expected: 8, actual: 9 }
    });
    const approval = {
      type: "event", event: "exec.approval.requested",
      payload: { id: "approval-1", request: {} }
    } as const;
    assert.deepEqual(tracker.accept(approval), { accepted: true });
    assert.deepEqual(tracker.accept(approval), { accepted: false, duplicate: true });
    assert.deepEqual(tracker.accept({
      type: "event", event: "exec.approval.resolved", payload: { id: "approval-1" }
    }), { accepted: true });
  });
});

class FakeSocket {
  static last: FakeSocket;
  readonly sent: string[] = [];
  private readonly listeners = new Map<string, Array<(event: { data?: string }) => void>>();

  constructor(_url: string) {
    FakeSocket.last = this;
    queueMicrotask(() => {
      this.dispatch("open", {});
      this.dispatch("message", {
        data: JSON.stringify({ type: "event", event: "connect.challenge", payload: { nonce: "n" } })
      });
    });
  }

  addEventListener(type: string, listener: (event: { data?: string }) => void): void {
    const listeners = this.listeners.get(type) ?? [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  send(data: string): void {
    this.sent.push(data);
    const request = JSON.parse(data) as { id: string; method: string; params?: unknown };
    const payload = request.method === "connect"
      ? {
          protocol: 4,
          server: { version: "2026.6.8" },
          auth: { scopes: ["operator.admin", "operator.approvals"] }
        }
      : { runId: "run-1", status: "completed" };
    queueMicrotask(() => this.dispatch("message", {
      data: JSON.stringify({ type: "res", id: request.id, ok: true, payload })
    }));
  }

  close(): void { this.dispatch("close", {}); }

  private dispatch(type: string, event: { data?: string }): void {
    for (const listener of this.listeners.get(type) ?? []) listener(event);
  }
}

describe("OpenClaw Gateway adapter", () => {
  it("starts a new run for a follow-up in the exact same canonical session", async () => {
    const factory = new FakeGatewayFactory();
    const adapter = new OpenClawGatewayAdapter(config({ chatLevelEnabled: true }), factory, runDependencies());
    const handle = await adapter.start({
      ...preflightInput(), capabilities: { ...capabilities(), chatLevelInteraction: true },
      protocolVersion: "2026.6.8", emit: async () => {}
    });
    await factory.connection.emit({
      type: "event", event: "agent", seq: 1,
      payload: { runId: "run-001", seq: 1, stream: "lifecycle", data: { phase: "end" } }
    });

    const next = await adapter.sendFollowUp(handle, {
      idempotencyKey: "follow-up-001", kind: "reply",
      message: "Use the second title.", sequence: 1
    });

    assert.equal(next.providerRunRef, "run-002");
    assert.equal(next.providerSessionRef, handle.providerSessionRef);
    assert.deepEqual(factory.connection.requests.at(-1), {
      method: "agent",
      params: {
        agentId: "main", deliver: false, idempotencyKey: "follow-up-001",
        message: "Use the second title.", sessionKey: handle.providerSessionRef
      }
    });
  });

  it("fails precise preflight checks for version, scopes, and policy", async () => {
    const factory = new FakeGatewayFactory();
    const disabled = new OpenClawGatewayAdapter(config({ enabled: false }), factory);
    assert.match((await disabled.preflight(preflightInput())).reason ?? "", /disabled/i);

    factory.connection.hello.serverVersion = "2026.6.9";
    const unsupported = new OpenClawGatewayAdapter(config(), factory);
    assert.match((await unsupported.preflight(preflightInput())).reason ?? "", /2026\.6\.9/);

    factory.connection.hello.serverVersion = "2026.6.8";
    factory.connection.hello.scopes = ["operator.admin"];
    const missingScope = new OpenClawGatewayAdapter(config(), factory);
    assert.match((await missingScope.preflight(preflightInput())).reason ?? "", /operator\.approvals/);
    const readOnly = await missingScope.preflight({
      ...preflightInput(), requiredInteractionTypes: []
    });
    assert.equal(readOnly.available, true);
    assert.deepEqual(readOnly.capabilities.interactionTypes, []);

    factory.connection.hello.scopes = ["operator.admin", "operator.approvals"];
    factory.connection.execPolicy = {
      security: "allowlist", ask: "off", askFallback: "deny"
    };
    const incompatiblePolicy = new OpenClawGatewayAdapter(config(), factory);
    assert.match((await incompatiblePolicy.preflight(preflightInput())).reason ?? "", /ask must be on-miss/);
  });

  it("starts a canonical session, routes run events, and verifies its run workspace", async () => {
    const factory = new FakeGatewayFactory();
    const events: InteractiveProviderEvent[] = [];
    const verified: string[] = [];
    const adapter = new OpenClawGatewayAdapter(config(), factory, {
      prepareRun: async ({ sessionKey }) => ({
        expectedOutputs: [], prompt: "Prepared prompt", sessionKey,
        workspaceRoot: "/srv/openclaw/runs/execution_001"
      }),
      verifyRun: async ({ workspaceRoot }) => {
        verified.push(workspaceRoot);
        return [];
      }
    });
    const handle = await adapter.start({
      ...preflightInput(), capabilities: capabilities(), protocolVersion: "2026.6.8",
      emit: async (event) => { events.push(event); }
    });
    assert.equal(handle.providerRunRef, "run-001");
    assert.equal(handle.providerSessionRef, "ragenius:app_001:session_001:agent_session_test");
    const agentRequest = factory.connection.requests.find(({ method }) => method === "agent");
    assert.deepEqual(agentRequest, {
      method: "agent",
      params: {
        agentId: "main", deliver: false, idempotencyKey: "execution_001",
        message: "Prepared prompt",
        sessionKey: "ragenius:app_001:session_001:agent_session_test"
      }
    });

    await factory.connection.emit({
      type: "event", event: "agent", seq: 1,
      payload: { runId: "run-001", seq: 1, stream: "lifecycle", data: { phase: "start" } }
    });
    await factory.connection.emit({
      type: "event", event: "agent", seq: 2,
      payload: { runId: "run-001", seq: 2, stream: "assistant", data: { delta: "Working" } }
    });
    await factory.connection.emit({
      type: "event", event: "agent", seq: 3,
      payload: { runId: "run-001", seq: 3, stream: "lifecycle", data: { phase: "end" } }
    });
    assert.deepEqual(events.map(({ type }) => type), ["run_started", "message_delta", "run_completed"]);
    assert.equal(events.at(-1)?.payload.output_text, "Working");
    assert.deepEqual(verified, ["/srv/openclaw/runs/execution_001"]);
  });

  it("maps approvals to allow-once or deny and ignores wrong-session requests", async () => {
    const factory = new FakeGatewayFactory();
    const events: InteractiveProviderEvent[] = [];
    const adapter = new OpenClawGatewayAdapter(config(), factory, runDependencies());
    const handle = await adapter.start({
      ...preflightInput(), capabilities: capabilities(), protocolVersion: "2026.6.8",
      emit: async (event) => { events.push(event); }
    });
    await factory.connection.emit(approvalEvent("approval-wrong", "ragenius:other:session:agent"));
    await factory.connection.emit(approvalEvent(
      "approval-1",
      `agent:main:${handle.providerSessionRef}`
    ));
    const interaction = events.find(({ type }) => type === "interaction_requested")?.interaction;
    assert.ok(interaction);
    assert.deepEqual(interaction.options.map(({ id }) => id), ["allow_once", "deny"]);
    await adapter.respond(handle, approvalClaim(interaction.interactionId, "allow_once"));
    assert.deepEqual(factory.connection.requests.at(-1), {
      method: "exec.approval.resolve",
      params: { id: "approval-1", decision: "allow-once" }
    });
    await assert.rejects(
      adapter.respond(handle, approvalClaim(interaction.interactionId, "allow_once")),
      /no longer pending/i
    );

    await factory.connection.emit(approvalEvent("approval-2", handle.providerSessionRef));
    const cancelInteraction = events.filter(({ type }) => type === "interaction_requested").at(-1)?.interaction;
    assert.ok(cancelInteraction);
    await adapter.respond(
      handle,
      approvalClaim(cancelInteraction.interactionId, "cancel_execution")
    );
    assert.equal(events.at(-1)?.type, "run_cancelled");
    assert.deepEqual(factory.connection.requests.slice(-3).map(({ method }) => method), [
      "exec.approval.resolve", "chat.abort", "agent.wait"
    ]);
  });

  it("uses exact run cancellation, confirms with agent.wait, and reconciles gaps", async () => {
    const factory = new FakeGatewayFactory();
    const events: InteractiveProviderEvent[] = [];
    const adapter = new OpenClawGatewayAdapter(config(), factory, runDependencies());
    const handle = await adapter.start({
      ...preflightInput(), capabilities: capabilities(), protocolVersion: "2026.6.8",
      emit: async (event) => { events.push(event); }
    });
    await factory.connection.gap(4, 7);
    assert.ok(factory.connection.requests.some(({ method }) => method === "sessions.list"));
    assert.ok(factory.connection.requests.some(({ method }) => method === "agent.wait"));
    assert.equal(events.some(({ type }) => type === "warning"), true);

    factory.connection.waitResponse = {
      runId: "run-001",
      status: "timeout",
      error: "aborted",
      stopReason: "rpc",
      timeoutPhase: "queue",
      providerStarted: false
    };
    assert.equal((await adapter.cancel(handle)).cancelled, true);
    assert.deepEqual(factory.connection.requests.slice(-2), [
      {
        method: "chat.abort",
        params: { agentId: "main", runId: "run-001", sessionKey: handle.providerSessionRef }
      },
      { method: "agent.wait", params: { runId: "run-001", timeoutMs: 5000 } }
    ]);

  });
});

function config(overrides: Record<string, unknown> = {}) {
  return {
    agentId: "main",
    credential: "gateway-secret",
    credentialEnv: "OPENCLAW_GATEWAY_APPROVAL_TOKEN",
    chatLevelEnabled: false,
    enabled: true,
    gatewayUrl: "ws://127.0.0.1:18789",
    interactionTtlMs: 60000,
    maxMessageBytes: 1048576,
    reconnectMaxAttempts: 3,
    reconnectBaseDelayMs: 10,
    rpcTimeoutMs: 5000,
    supportedVersions: ["2026.6.8"],
    workspaceRoot: "/srv/openclaw",
    wslDistro: "OpenClawGateway",
    ...overrides
  };
}

function capabilities() {
  return {
    cancellation: true,
    eventReplay: "none" as const,
    interactionTypes: ["approval"] as Array<"approval">,
    protocolTransport: true,
    reconnectReconciliation: true,
    sameSessionContinuation: true,
    sameTurnResume: true
  };
}

function preflightInput() {
  return {
    agentSessionId: "agent_session_test",
    policy,
    providerContext,
    request,
    requiredInteractionTypes: ["approval"] as Array<"approval">,
    scope: { appId: request.app_id, executionId: "execution_001", sessionId: request.session_id }
  };
}

function runDependencies() {
  return {
    prepareRun: async ({ sessionKey }: { sessionKey: string }) => ({
      expectedOutputs: [], prompt: "Prepared prompt", sessionKey,
      workspaceRoot: "/srv/openclaw/runs/execution_001"
    }),
    verifyRun: async () => []
  };
}

function approvalEvent(id: string, sessionKey: string) {
  return {
    type: "event", event: "exec.approval.requested",
    payload: {
      id, createdAtMs: Date.now(), expiresAtMs: Date.now() + 60000,
      request: { command: "echo ok", cwd: "/srv/openclaw", sessionKey }
    }
  };
}

function approvalClaim(
  interactionId: string,
  decision: "allow_once" | "deny" | "cancel_execution"
): ClaimedInteraction {
  const now = new Date();
  return {
    idempotencyKey: `key-${interactionId}`,
    interactionId,
    responseSummary: { kind: "approval", decision },
    interaction: {
      agentSessionId: "agent_session_test", allowsFreeText: false,
      appId: request.app_id, createdAt: now, executionId: "execution_001",
      expiresAt: new Date(now.getTime() + 60000), interactionId,
      options: [{ id: "allow_once", label: "Allow once" }, { id: "deny", label: "Deny" }],
      policyBindingHash: "policy-fingerprint", prompt: "Approve command?",
      providerCorrelationRef: "openclaw:approval-1", resolvedAt: null,
      responseSummary: null, secretInput: false, sequence: 1,
      sessionId: request.session_id, state: "resolving", type: "approval",
      updatedAt: now, version: 2
    }
  };
}
