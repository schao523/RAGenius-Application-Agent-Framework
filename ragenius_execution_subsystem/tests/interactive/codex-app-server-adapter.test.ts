import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { ExecuteAgentRequest } from "../../src/api/schemas/execution-request.schema.js";
import type { AgentPolicyDecision } from "../../src/core/agents/agent-policy.js";
import type { AgentProviderExecutionContext } from "../../src/core/agents/agent-provider-context.js";
import {
  CodexAppServerAdapter,
  type CodexAppServerTransport,
  type CodexAppServerTransportFactory
} from "../../src/core/interactive/codex-app-server-adapter.js";
import {
  CodexAppServerCodec,
  CodexProtocolError
} from "../../src/core/interactive/codex-app-server-codec.js";
import {
  parseRageniusInteractionToolCall,
  rageniusInteractionToolSpec
} from "../../src/core/interactive/codex-interaction-tool.js";
import type {
  ClaimedInteraction,
  InteractiveProviderEvent
} from "../../src/core/interactive/interactive-agent-adapter.js";

const request: ExecuteAgentRequest = {
  request_type: "execute_agent",
  app_id: "app_001",
  session_id: "session_001",
  agent_backend: "codex_cli",
  agent_query: "Create a report and ask which format to use."
};
const policy: AgentPolicyDecision = {
  matchedTerms: [],
  mode: "auto_allow",
  networkAccess: "deny",
  permissionScope: "agent.workspace_write",
  providerStateAccess: "none",
  providerStateLabels: [],
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

class FakeTransport implements CodexAppServerTransport {
  readonly notifications: Array<{ method: string; params?: unknown }> = [];
  readonly requests: Array<{ method: string; params?: unknown }> = [];
  readonly responses: Array<{ id: string | number; result: unknown }> = [];
  closed = false;
  private handler?: (message: Record<string, unknown>) => Promise<void>;
  private closeHandler?: (error?: Error) => Promise<void>;

  async request(method: string, params?: unknown): Promise<unknown> {
    this.requests.push({ method, params });
    if (method === "initialize") {
      return { userAgent: "codex-cli/0.146.0", platformFamily: "windows" };
    }
    if (method === "thread/start") {
      return { thread: { id: "thread-1" } };
    }
    if (method === "turn/start") {
      return { turn: { id: "turn-1", status: "inProgress" } };
    }
    if (method === "turn/interrupt") return {};
    throw new Error(`Unexpected request: ${method}`);
  }

  async notify(method: string, params?: unknown): Promise<void> {
    this.notifications.push({ method, params });
  }

  async respond(id: string | number, result: unknown): Promise<void> {
    this.responses.push({ id, result });
  }

  onMessage(handler: (message: Record<string, unknown>) => Promise<void>): void {
    this.handler = handler;
  }

  onClose(handler: (error?: Error) => Promise<void>): void {
    this.closeHandler = handler;
  }

  async close(): Promise<void> { this.closed = true; }
  isClosed(): boolean { return this.closed; }

  async emit(message: Record<string, unknown>): Promise<void> {
    assert.ok(this.handler);
    await this.handler(message);
  }

  async emitConcurrent(messages: Record<string, unknown>[]): Promise<void> {
    assert.ok(this.handler);
    await Promise.all(messages.map((message) => this.handler!(message)));
  }

  async disconnect(error = new Error("provider disconnected")): Promise<void> {
    this.closed = true;
    await this.closeHandler?.(error);
  }
}

class FakeFactory implements CodexAppServerTransportFactory {
  readonly transport = new FakeTransport();
  version = "0.146.0";
  async versionInfo() { return { available: true, version: this.version }; }
  async create() { return this.transport; }
}

describe("Codex app-server codec", () => {
  it("frames correlated JSON-RPC messages and notifications", () => {
    const codec = new CodexAppServerCodec({ maxLineBytes: 1024 });
    assert.equal(codec.encodeRequest(7, "initialize", { clientInfo: { name: "RAGenius" } }),
      '{"jsonrpc":"2.0","id":7,"method":"initialize","params":{"clientInfo":{"name":"RAGenius"}}}\n');
    assert.deepEqual(codec.decode('{"jsonrpc":"2.0","id":7,"result":{"ok":true}}\n'), {
      jsonrpc: "2.0", id: 7, result: { ok: true }
    });
    assert.deepEqual(codec.decode('{"method":"turn/started","params":{"threadId":"t1"}}'), {
      method: "turn/started", params: { threadId: "t1" }
    });
  });

  it("rejects malformed and oversized protocol lines", () => {
    const codec = new CodexAppServerCodec({ maxLineBytes: 20 });
    assert.throws(() => codec.decode("not-json"), CodexProtocolError);
    assert.throws(() => codec.decode(JSON.stringify({ value: "x".repeat(30) })), /maximum/);
  });

  it("bounds message deltas and ignores raw reasoning methods", () => {
    const codec = new CodexAppServerCodec({ maxLineBytes: 1024, maxDeltaBytes: 5 });
    assert.deepEqual(codec.normalizeNotification({
      method: "item/agentMessage/delta",
      params: { delta: "1234567", itemId: "item-1" }
    }), {
      type: "message_delta",
      payload: { delta: "34567", truncated: true }
    });
    assert.equal(codec.normalizeNotification({
      method: "item/reasoning/textDelta", params: { delta: "secret reasoning" }
    }), null);
    assert.deepEqual(codec.normalizeNotification({ method: "future/method", params: {} }), {
      type: "warning",
      payload: { code: "CODEX_UNKNOWN_METHOD", method: "future/method" }
    });
  });
});

describe("RAGenius Codex interaction tool", () => {
  it("defines and validates bounded clarification and selection calls", () => {
    assert.equal(rageniusInteractionToolSpec.name, "ragenius_request_input");
    assert.deepEqual(parseRageniusInteractionToolCall({
      question: "Choose a format.",
      options: ["Markdown", "PDF"],
      allows_free_text: false
    }), {
      allowsFreeText: false,
      options: [
        { id: "option-1", label: "Markdown" },
        { id: "option-2", label: "PDF" }
      ],
      prompt: "Choose a format.",
      type: "selection"
    });
    assert.throws(() => parseRageniusInteractionToolCall({
      question: "x".repeat(2001)
    }));
    assert.throws(() => parseRageniusInteractionToolCall({
      question: "Enter your password or API key."
    }), /secret/i);
  });
});

describe("Codex app-server adapter", () => {
  it("fails preflight when disabled or outside the supported version", async () => {
    const factory = new FakeFactory();
    const disabled = new CodexAppServerAdapter(config({ enabled: false }), factory);
    assert.equal((await disabled.preflight(preflightInput())).available, false);

    factory.version = "0.147.0";
    const unsupported = new CodexAppServerAdapter(config(), factory);
    const result = await unsupported.preflight(preflightInput());
    assert.equal(result.available, false);
    assert.match(result.reason ?? "", /0\.147\.0/);
  });

  it("initializes, starts a scoped thread and turn, and normalizes events", async () => {
    const factory = new FakeFactory();
    const adapter = new CodexAppServerAdapter(config(), factory);
    const events: InteractiveProviderEvent[] = [];
    const handle = await adapter.start({
      ...preflightInput(),
      capabilities: capabilities(),
      protocolVersion: "0.146.0",
      emit: async (event: InteractiveProviderEvent) => { events.push(event); }
    });

    assert.equal(handle.providerSessionRef, "thread-1");
    assert.equal(handle.providerTurnRef, "turn-1");
    assert.deepEqual(factory.transport.requests.map((item) => item.method), [
      "initialize", "thread/start", "turn/start"
    ]);
    assert.equal(factory.transport.notifications[0]?.method, "initialized");
    const threadParams = factory.transport.requests[1]?.params as Record<string, unknown>;
    assert.equal(threadParams.approvalsReviewer, "user");
    assert.equal(threadParams.ephemeral, true);
    assert.equal((threadParams.dynamicTools as Array<{ name: string }>)[0]?.name, "ragenius_request_input");
    assert.match(String(threadParams.cwd), /codex-interactive-tests[\\/]execution_001$/);

    await factory.transport.emit({
      method: "turn/started", params: { threadId: "thread-1", turn: { id: "turn-1" } }
    });
    await factory.transport.emit({
      method: "item/agentMessage/delta", params: { delta: "Work" }
    });
    await factory.transport.emit({
      method: "item/agentMessage/delta", params: { delta: "ing" }
    });
    await factory.transport.emit({
      method: "turn/completed", params: { threadId: "thread-1", turn: { id: "turn-1", status: "completed" } }
    });
    assert.deepEqual(events.map((event) => event.type), [
      "run_started", "message_delta", "run_completed"
    ]);
    assert.equal(events[1]?.payload.delta, "Working");
  });

  it("maps multiple approvals and resolves only one-time decisions", async () => {
    const factory = new FakeFactory();
    const adapter = new CodexAppServerAdapter(config(), factory);
    const events: InteractiveProviderEvent[] = [];
    const handle = await adapter.start({
      ...preflightInput(), capabilities: capabilities(), protocolVersion: "0.146.0",
      emit: async (event: InteractiveProviderEvent) => { events.push(event); }
    });
    for (const [id, itemId] of [[41, "item-1"], [42, "item-2"]] as const) {
      await factory.transport.emit({
        id,
        method: "item/commandExecution/requestApproval",
        params: {
          command: "Set-Content report.md ok", cwd: "D:/workspace", itemId,
          threadId: "thread-1", turnId: "turn-1"
        }
      });
    }
    assert.equal(events.filter((event) => event.type === "interaction_requested").length, 2);

    await adapter.respond(handle, claim(events[0]!.interaction!.interactionId, "allow_once"));
    await adapter.respond(handle, claim(events[1]!.interaction!.interactionId, "deny"));
    assert.deepEqual(factory.transport.responses, [
      { id: 41, result: { decision: "accept" } },
      { id: 42, result: { decision: "decline" } }
    ]);
  });

  it("maps a dynamic selection call and resumes it with validated content", async () => {
    const factory = new FakeFactory();
    const adapter = new CodexAppServerAdapter(config(), factory);
    const events: InteractiveProviderEvent[] = [];
    const handle = await adapter.start({
      ...preflightInput(), capabilities: capabilities(), protocolVersion: "0.146.0",
      emit: async (event: InteractiveProviderEvent) => { events.push(event); }
    });
    await factory.transport.emit({
      id: "tool-1",
      method: "item/tool/call",
      params: {
        arguments: { question: "Choose.", options: ["Alpha", "Beta"] },
        callId: "call-1", threadId: "thread-1", tool: "ragenius_request_input", turnId: "turn-1"
      }
    });
    assert.equal(events[0]?.interaction?.type, "selection");
    await adapter.respond(handle, selectionClaim(events[0]!.interaction!.interactionId));
    assert.deepEqual(factory.transport.responses[0], {
      id: "tool-1",
      result: { success: true, contentItems: [{ type: "inputText", text: "Beta" }] }
    });
  });

  it("declines provider permission expansion without offering it to the user", async () => {
    const factory = new FakeFactory();
    const adapter = new CodexAppServerAdapter(config(), factory);
    const events: InteractiveProviderEvent[] = [];
    await adapter.start({
      ...preflightInput(), capabilities: capabilities(), protocolVersion: "0.146.0",
      emit: async (event) => { events.push(event); }
    });
    await factory.transport.emit({
      id: 55,
      method: "item/permissions/requestApproval",
      params: { permissions: ["network"], reason: "Upload data." }
    });
    assert.deepEqual(factory.transport.responses, [
      { id: 55, result: { decision: "decline" } }
    ]);
    assert.equal(events.some((event) => event.type === "interaction_requested"), false);
    assert.equal(events.at(-1)?.payload.code, "CODEX_PERMISSION_EXPANSION_BLOCKED");
  });

  it("rejects dynamic questions that request secret input", async () => {
    const factory = new FakeFactory();
    const adapter = new CodexAppServerAdapter(config(), factory);
    const events: InteractiveProviderEvent[] = [];
    await adapter.start({
      ...preflightInput(), capabilities: capabilities(), protocolVersion: "0.146.0",
      emit: async (event) => { events.push(event); }
    });
    await factory.transport.emit({
      id: "tool-secret",
      method: "item/tool/call",
      params: {
        arguments: { question: "Enter your API token." },
        tool: "ragenius_request_input"
      }
    });
    assert.equal(events.length, 0);
    assert.deepEqual(factory.transport.responses[0], {
      id: "tool-secret",
      result: {
        success: false,
        contentItems: [{ type: "inputText", text: "Invalid bounded RAGenius input request." }]
      }
    });
  });

  it("serializes provider requests before terminal events and fails on disconnect", async () => {
    const factory = new FakeFactory();
    const adapter = new CodexAppServerAdapter(config(), factory);
    const events: InteractiveProviderEvent[] = [];
    const handle = await adapter.start({
      ...preflightInput(), capabilities: capabilities(), protocolVersion: "0.146.0",
      emit: async (event) => {
        if (event.type === "interaction_requested") {
          await new Promise((resolve) => setTimeout(resolve, 10));
        }
        events.push(event);
      }
    });
    await factory.transport.emitConcurrent([
      {
        id: 61,
        method: "item/commandExecution/requestApproval",
        params: { command: "echo ok" }
      },
      {
        method: "turn/completed",
        params: { turn: { id: "turn-1", status: "completed" } }
      }
    ]);
    assert.deepEqual(events.map((event) => event.type), [
      "interaction_requested", "run_completed"
    ]);

    const secondFactory = new FakeFactory();
    const secondEvents: InteractiveProviderEvent[] = [];
    const secondAdapter = new CodexAppServerAdapter(config(), secondFactory);
    const secondHandle = await secondAdapter.start({
      ...preflightInput(), capabilities: capabilities(), protocolVersion: "0.146.0",
      emit: async (event) => { secondEvents.push(event); }
    });
    await secondFactory.transport.disconnect();
    assert.equal((await secondAdapter.reconcile(secondHandle)).state, "failed");
    assert.equal(secondEvents.at(-1)?.type, "run_completed");
    assert.equal(secondEvents.at(-1)?.payload.status, "failed");
    assert.ok(handle.providerTurnRef);
  });

  it("waits for the terminal interrupted event and fails reconciliation after disconnect", async () => {
    const factory = new FakeFactory();
    const adapter = new CodexAppServerAdapter(config(), factory);
    const handle = await adapter.start({
      ...preflightInput(), capabilities: capabilities(), protocolVersion: "0.146.0",
      emit: async () => undefined
    });
    const cancellation = adapter.cancel(handle);
    assert.deepEqual(factory.transport.requests.at(-1), {
      method: "turn/interrupt", params: { threadId: "thread-1", turnId: "turn-1" }
    });
    let settled = false;
    void cancellation.then(() => { settled = true; });
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(settled, false);
    await factory.transport.emit({
      method: "turn/completed",
      params: { threadId: "thread-1", turn: { id: "turn-1", status: "interrupted" } }
    });
    assert.equal((await cancellation).cancelled, true);
    await factory.transport.close();
    assert.equal((await adapter.reconcile(handle)).state, "failed");
  });
});

function config(overrides: Partial<ConstructorParameters<typeof CodexAppServerAdapter>[0]> = {}) {
  return {
    enabled: true,
    command: "codex",
    initializationTimeoutMs: 5000,
    interactionTtlMs: 60000,
    maxDeltaBytes: 4096,
    maxLineBytes: 65536,
    maxStderrBytes: 65536,
    runRoot: ".test_tmp/codex-interactive-tests",
    supportedVersions: ["0.146.0"],
    ...overrides
  };
}

function capabilities() {
  return {
    cancellation: true,
    eventReplay: "none" as const,
    interactionTypes: ["approval", "clarification", "selection"] as Array<
      "approval" | "clarification" | "selection"
    >,
    protocolTransport: true,
    reconnectReconciliation: false,
    sameSessionContinuation: true,
    sameTurnResume: true
  };
}

function preflightInput() {
  return {
    policy,
    providerContext,
    request,
    requiredInteractionTypes: ["approval", "selection"] as Array<
      "approval" | "selection"
    >,
    scope: { appId: request.app_id, executionId: "execution_001", sessionId: request.session_id }
  };
}

function claim(interactionId: string, decision: "allow_once" | "deny"): ClaimedInteraction {
  return {
    idempotencyKey: `key-${interactionId}`,
    interactionId,
    responseSummary: { kind: "approval", decision },
    interaction: interactionRecord(interactionId, "approval")
  };
}

function selectionClaim(interactionId: string): ClaimedInteraction {
  return {
    idempotencyKey: `key-${interactionId}`,
    interactionId,
    responseSummary: { kind: "selection", option_ids: ["option-2"] },
    interaction: interactionRecord(interactionId, "selection", [
      { id: "option-1", label: "Alpha" }, { id: "option-2", label: "Beta" }
    ])
  };
}

function interactionRecord(
  interactionId: string,
  type: "approval" | "selection",
  options: Array<{ id: string; label: string }> = []
) {
  const now = new Date();
  return {
    agentSessionId: "agent-session-1", allowsFreeText: false,
    appId: request.app_id, createdAt: now, executionId: "execution_001",
    expiresAt: new Date(now.getTime() + 60000), interactionId, options,
    policyBindingHash: "policy-fingerprint", prompt: "Resolve.",
    providerCorrelationRef: `codex:${interactionId}`, resolvedAt: null,
    responseSummary: null, secretInput: false as const, sequence: 1,
    sessionId: request.session_id, state: "resolving" as const, type,
    updatedAt: now, version: 2
  };
}
