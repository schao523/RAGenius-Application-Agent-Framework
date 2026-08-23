import { randomUUID } from "node:crypto";

import {
  buildOpenClawRunWorkspaceRoot,
  inspectOpenClawWorkspaceFileViaWsl,
  stageResolvedAgentArtifactsForOpenClaw,
  transferOpenClawFileViaWsl,
  transferOpenClawInputViaWsl,
  verifyOpenClawOutputs
} from "../agents/openclaw-workspace.js";
import { normalizeOpenClawOptions } from "../agents/openclaw-options.js";
import { buildOpenClawPrompt } from "../agents/openclaw-prompt-builder.js";
import type {
  OpenClawExpectedOutput,
  OpenClawStagedInput,
  OpenClawVerificationResult
} from "../agents/openclaw-cli-types.js";

import type {
  ClaimedInteraction,
  ClaimedChatFollowUp,
  InteractiveAgentAdapter,
  InteractivePreflightInput,
  InteractivePreflightResult,
  InteractiveProviderEvent,
  InteractiveStartInput,
  ProviderCancellationResult,
  ProviderReconciliationResult,
  ProviderSessionHandle
} from "./interactive-agent-adapter.js";
import { ProviderSessionUnavailableError } from "./interactive-agent-adapter.js";
import type { AgentSessionRecord, AgentSessionState } from "./interactive-agent-types.js";
import {
  redactOpenClawGatewayDiagnostic,
  type OpenClawGatewayHello
} from "./openclaw-gateway-client.js";
import {
  buildOpenClawInteractiveSessionKey,
  isRecord,
  numberField,
  recordField,
  stringField
} from "./openclaw-gateway-events.js";

export interface OpenClawGatewayInteractiveConfig {
  agentId: string;
  chatLevelEnabled: boolean;
  chatIdleTtlMs: number;
  credential?: string;
  credentialEnv: string;
  enabled: boolean;
  gatewayUrl: string;
  interactionTtlMs: number;
  maxMessageBytes: number;
  reconnectBaseDelayMs: number;
  reconnectMaxAttempts: number;
  rpcTimeoutMs: number;
  supportedVersions: string[];
  workspaceRoot: string;
  wslDistro: string;
}

export interface OpenClawGatewayConnection {
  readonly hello: OpenClawGatewayHello;
  request(method: string, params?: unknown): Promise<unknown>;
  onEvent(handler: (event: Record<string, unknown>) => Promise<void>): void;
  onGap(handler: (gap: { actual: number; expected: number }) => Promise<void>): void;
  onClose(handler: (error?: Error) => Promise<void>): void;
  reconnect(): Promise<OpenClawGatewayHello>;
  close(): Promise<void>;
}

export interface OpenClawGatewayConnectionFactory {
  connect(): Promise<OpenClawGatewayConnection>;
}

export interface PreparedOpenClawGatewayRun {
  expectedOutputs: OpenClawExpectedOutput[];
  prompt: string;
  sessionKey: string;
  workspaceRoot: string;
}

export interface OpenClawGatewayAdapterDependencies {
  prepareRun?(input: {
    input: InteractiveStartInput;
    sessionKey: string;
  }): Promise<PreparedOpenClawGatewayRun>;
  verifyRun?(input: {
    expectedOutputs: OpenClawExpectedOutput[];
    workspaceRoot: string;
  }): Promise<OpenClawVerificationResult[]>;
}

type PendingApproval = {
  interactionId: string;
  providerApprovalId: string;
};

type OpenClawProtectedHandle = {
  chatLevelInteraction: boolean;
  emit: (event: InteractiveProviderEvent) => Promise<void>;
  expectedOutputs: OpenClawExpectedOutput[];
  messageText: string;
  messageTruncated: boolean;
  pendingApprovals: Map<string, PendingApproval>;
  policyBindingHash: string;
  runId: string;
  sessionKey: string;
  state: AgentSessionState;
  workspaceRoot: string;
};

const BASE_CAPABILITIES = {
  chatLevelInteraction: false,
  cancellation: true,
  eventReplay: "none" as const,
  interactionTypes: [] as Array<"approval">,
  protocolTransport: true,
  reconnectReconciliation: true,
  sameSessionContinuation: true,
  sameTurnResume: true,
  structuredWaitSignal: false,
  exactlyOnceFollowUp: false
};

export class OpenClawGatewayAdapter implements InteractiveAgentAdapter {
  readonly backend = "openclaw_cli" as const;
  private connectionPromise: Promise<OpenClawGatewayConnection> | null = null;
  private readonly activeByRun = new Map<string, OpenClawProtectedHandle>();
  private readonly activeBySession = new Map<string, OpenClawProtectedHandle>();
  private readonly seenApprovalEvents = new Set<string>();
  private reconnecting = false;

  constructor(
    private readonly config: OpenClawGatewayInteractiveConfig,
    private readonly factory: OpenClawGatewayConnectionFactory,
    private readonly dependencies: OpenClawGatewayAdapterDependencies = {}
  ) {}

  async preflight(input: InteractivePreflightInput): Promise<InteractivePreflightResult> {
    const base = {
      capabilities: {
        ...BASE_CAPABILITIES,
        chatLevelInteraction: this.config.chatLevelEnabled,
        interactionTypes: [...BASE_CAPABILITIES.interactionTypes]
      },
      protocolVersion: "unknown",
      transport: "openclaw_gateway" as const
    };
    if (!this.config.enabled) {
      return { ...base, available: false, reason: "OpenClaw interactive Gateway is disabled." };
    }
    if (!this.config.credential) {
      return {
        ...base,
        available: false,
        reason: `OpenClaw Gateway credential is missing from ${this.config.credentialEnv}.`
      };
    }

    let connection: OpenClawGatewayConnection;
    try {
      connection = await this.connection();
    } catch (error) {
      return { ...base, available: false, reason: this.safeMessage(error) };
    }
    const version = connection.hello.serverVersion;
    const versioned = { ...base, protocolVersion: version };
    if (!this.config.supportedVersions.includes(version)) {
      return {
        ...versioned,
        available: false,
        reason: `OpenClaw Gateway version ${version} is not supported.`
      };
    }

    const missingTypes = input.requiredInteractionTypes.filter((type) => type !== "approval");
    if (missingTypes.length > 0) {
      return {
        ...versioned,
        available: false,
        reason: `OpenClaw Gateway lacks required interactions: ${missingTypes.join(", ")}.`
      };
    }
    const requiredScopes = ["operator.admin", "operator.approvals"];
    const missingScopes = requiredScopes.filter((scope) => !connection.hello.scopes.includes(scope));
    let approvalFailure = missingScopes.length > 0
      ? `OpenClaw Gateway credential lacks required scopes: ${missingScopes.join(", ")}.`
      : "";
    if (!approvalFailure) {
      try {
        const effectivePolicy = readEffectiveExecPolicy(await connection.request("config.get", {}));
        const policyFailures = [
          effectivePolicy.security === "allowlist" ? "" : "security must be allowlist",
          effectivePolicy.ask === "on-miss" ? "" : "ask must be on-miss",
          effectivePolicy.askFallback === "deny" ? "" : "askFallback must be deny"
        ].filter(Boolean);
        if (policyFailures.length > 0) {
          approvalFailure = `OpenClaw approval policy is incompatible: ${policyFailures.join("; ")}.`;
        }
      } catch (error) {
        approvalFailure = `OpenClaw approval policy could not be inspected: ${this.safeMessage(error)}`;
      }
    }
    const capabilities = {
      ...versioned.capabilities,
      interactionTypes: approvalFailure ? [] : ["approval" as const]
    };
    if (input.requiredInteractionTypes.includes("approval") && approvalFailure) {
      return { ...versioned, capabilities, available: false, reason: approvalFailure };
    }
    return { ...versioned, capabilities, available: true };
  }

  async start(input: InteractiveStartInput): Promise<ProviderSessionHandle> {
    const connection = await this.connection();
    const sessionKey = buildOpenClawInteractiveSessionKey({
      appId: input.scope.appId,
      sessionId: input.scope.sessionId,
      agentSessionId: input.agentSessionId
    });
    const prepared = this.dependencies.prepareRun
      ? await this.dependencies.prepareRun({ input, sessionKey })
      : await this.prepareRun(input, sessionKey);
    if (prepared.sessionKey !== sessionKey) {
      throw new Error("OpenClaw run preparation changed the canonical session key.");
    }
    const response = await connection.request("agent", {
      message: prepared.prompt,
      agentId: this.config.agentId,
      sessionKey,
      deliver: false,
      idempotencyKey: input.scope.executionId
    });
    const runId = stringField(response, "runId");
    if (!runId) throw new Error("OpenClaw Gateway agent response omitted runId.");
    const state: OpenClawProtectedHandle = {
      chatLevelInteraction: Boolean(input.capabilities.chatLevelInteraction),
      emit: input.emit,
      expectedOutputs: prepared.expectedOutputs,
      messageText: "",
      messageTruncated: false,
      pendingApprovals: new Map(),
      policyBindingHash: input.providerContext.authorization.policy_fingerprint,
      runId,
      sessionKey,
      state: "running",
      workspaceRoot: prepared.workspaceRoot
    };
    this.activeByRun.set(runId, state);
    for (const key of providerSessionAliases(sessionKey, this.config.agentId)) {
      this.activeBySession.set(key, state);
    }
    return {
      providerRunRef: runId,
      providerSessionRef: sessionKey,
      providerTurnRef: runId,
      protectedHandle: state
    };
  }

  async sendFollowUp(
    handle: ProviderSessionHandle,
    claim: ClaimedChatFollowUp
  ): Promise<ProviderSessionHandle> {
    const state = protectedHandle(handle);
    if (!state.chatLevelInteraction) throw new Error("OpenClaw chat-level continuation is disabled.");
    if (state.state !== "completed") throw new Error("OpenClaw session already has an active run.");
    const connection = await this.connection();
    await assertProviderSessionExists(connection, state.sessionKey, this.config.agentId);
    const response = await connection.request("agent", {
      message: claim.message,
      agentId: this.config.agentId,
      sessionKey: state.sessionKey,
      deliver: false,
      idempotencyKey: claim.idempotencyKey
    });
    const runId = stringField(response, "runId");
    if (!runId) throw new Error("OpenClaw Gateway follow-up response omitted runId.");
    this.activeByRun.delete(state.runId);
    state.runId = runId;
    state.messageText = "";
    state.messageTruncated = false;
    state.state = "running";
    this.activeByRun.set(runId, state);
    for (const key of providerSessionAliases(state.sessionKey, this.config.agentId)) {
      this.activeBySession.set(key, state);
    }
    return handleFor(state);
  }

  async restore(
    session: AgentSessionRecord,
    emit: (event: InteractiveProviderEvent) => Promise<void>
  ): Promise<ProviderSessionHandle> {
    if (!this.config.chatLevelEnabled) throw new Error("OpenClaw chat-level continuation is disabled.");
    if (session.protocolVersion && !this.config.supportedVersions.includes(session.protocolVersion)) {
      throw new Error(`OpenClaw Gateway version ${session.protocolVersion} is not supported.`);
    }
    if (!session.providerSessionRef || !session.policyBindingHash) {
      throw new Error("OpenClaw idle session lacks durable recovery references.");
    }
    const connection = await this.connection();
    await assertProviderSessionExists(
      connection,
      session.providerSessionRef,
      this.config.agentId
    );
    const runId = session.providerRunRef || session.providerTurnRef || `idle:${session.agentSessionId}`;
    const state: OpenClawProtectedHandle = {
      chatLevelInteraction: true,
      emit,
      expectedOutputs: [],
      messageText: "",
      messageTruncated: false,
      pendingApprovals: new Map(),
      policyBindingHash: session.policyBindingHash,
      runId,
      sessionKey: session.providerSessionRef,
      state: "completed",
      workspaceRoot: buildOpenClawRunWorkspaceRoot(this.config.workspaceRoot, session.executionId)
    };
    for (const key of providerSessionAliases(state.sessionKey, this.config.agentId)) {
      this.activeBySession.set(key, state);
    }
    return handleFor(state);
  }

  async respond(handle: ProviderSessionHandle, claim: ClaimedInteraction): Promise<void> {
    const state = protectedHandle(handle);
    const pending = state.pendingApprovals.get(claim.interactionId);
    if (!pending) throw new Error("OpenClaw provider interaction is no longer pending.");
    const decision = stringField(claim.responseSummary, "decision");
    if (decision !== "allow_once" && decision !== "deny" && decision !== "cancel_execution") {
      throw new Error("Unsupported OpenClaw approval response.");
    }
    const connection = await this.connection();
    const response = await connection.request("exec.approval.resolve", {
      id: pending.providerApprovalId,
      decision: decision === "allow_once" ? "allow-once" : "deny"
    });
    if (isRecord(response) && response.ok === false) {
      throw new Error("OpenClaw Gateway rejected the approval response.");
    }
    state.pendingApprovals.delete(claim.interactionId);
    if (decision === "cancel_execution") {
      await connection.request("chat.abort", {
        sessionKey: state.sessionKey,
        agentId: this.config.agentId,
        runId: state.runId
      });
      const wait = await connection.request("agent.wait", {
        runId: state.runId,
        timeoutMs: this.config.rpcTimeoutMs
      });
      const status = providerWaitStatus(wait);
      if (status !== "aborted" && status !== "cancelled") {
        throw new Error("OpenClaw cancellation was not confirmed by agent.wait.");
      }
      state.state = "cancelled";
      await state.emit({ type: "run_cancelled", payload: { status } });
      this.removeActive(state);
    }
  }

  async cancel(handle: ProviderSessionHandle): Promise<ProviderCancellationResult> {
    const state = protectedHandle(handle);
    const connection = await this.connection();
    for (const pending of state.pendingApprovals.values()) {
      await connection.request("exec.approval.resolve", {
        id: pending.providerApprovalId,
        decision: "deny"
      });
    }
    state.pendingApprovals.clear();
    await connection.request("chat.abort", {
      sessionKey: state.sessionKey,
      agentId: this.config.agentId,
      runId: state.runId
    });
    const wait = await connection.request("agent.wait", {
      runId: state.runId,
      timeoutMs: this.config.rpcTimeoutMs
    });
    const status = providerWaitStatus(wait);
    const cancelled = status === "aborted" || status === "cancelled";
    if (cancelled) {
      state.state = "cancelled";
      this.removeActive(state);
    }
    return {
      cancelled,
      ...(cancelled ? {} : { diagnostics: { status: status || "unknown" } })
    };
  }

  async reconcile(handle: ProviderSessionHandle): Promise<ProviderReconciliationResult> {
    const state = protectedHandle(handle);
    const connection = await this.connection();
    await connection.request("sessions.list", {});
    const wait = await connection.request("agent.wait", {
      runId: state.runId,
      timeoutMs: this.config.rpcTimeoutMs
    });
    const status = providerWaitStatus(wait);
    state.state = reconciledState(status, state.state);
    return { state: state.state, diagnostics: { provider_status: status || "unknown" } };
  }

  private async connection(): Promise<OpenClawGatewayConnection> {
    if (!this.connectionPromise) {
      this.connectionPromise = this.factory.connect().then((connection) => {
        connection.onEvent((event) => this.consumeGatewayEvent(event));
        connection.onGap((gap) => this.consumeGap(gap));
        connection.onClose((error) => this.consumeDisconnect(error));
        return connection;
      }).catch((error) => {
        this.connectionPromise = null;
        throw error;
      });
    }
    return this.connectionPromise;
  }

  private async consumeGatewayEvent(frame: Record<string, unknown>): Promise<void> {
    const eventName = stringField(frame, "event");
    const payload = recordField(frame, "payload");
    if (eventName === "agent") {
      await this.consumeAgentEvent(payload);
      return;
    }
    if (eventName === "exec.approval.requested") {
      await this.consumeApprovalRequested(payload);
      return;
    }
    if (eventName === "exec.approval.resolved") {
      this.consumeApprovalResolved(payload);
    }
  }

  private async consumeAgentEvent(payload: Record<string, unknown>): Promise<void> {
    const runId = stringField(payload, "runId");
    const state = this.activeByRun.get(runId);
    if (!state) return;
    const stream = stringField(payload, "stream");
    const data = recordField(payload, "data");
    const providerEventRef = `openclaw:${runId}:${numberField(payload, "seq") ?? randomUUID()}`;
    if (stream === "lifecycle") {
      const phase = stringField(data, "phase");
      if (phase === "start") {
        await state.emit({ type: "run_started", payload: { run_id: runId }, providerEventRef });
      } else if (["end", "complete", "completed", "error"].includes(phase)) {
        const verificationResults = await this.verifyRun(state);
        const requiredFailure = verificationResults.some((result) => result.required && !result.verified);
        const failed = phase === "error" || requiredFailure;
        const providerError = phase === "error"
          ? this.safeMessage(
              stringField(data, "error")
              || stringField(data, "errorMessage")
              || stringField(data, "message")
              || "OpenClaw provider failed."
            ).slice(0, 2048)
          : "";
        state.state = failed ? "failed" : "completed";
        await state.emit({
          type: "run_completed",
          payload: {
            status: failed ? "failed" : "completed",
            verification_results: verificationResults,
            output_text: state.messageText,
            output_truncated: state.messageTruncated,
            ...(requiredFailure ? { failure_code: "missing_output" } : {}),
            ...(providerError
              ? {
                  failure_code: "OPENCLAW_PROVIDER_ERROR",
                  summary: providerError
                }
              : {})
          },
          providerEventRef
        });
        if (state.chatLevelInteraction && !failed) {
          this.activeByRun.delete(state.runId);
        } else {
          this.removeActive(state);
        }
      }
      return;
    }
    if (stream === "assistant") {
      const delta = stringField(data, "delta") || stringField(data, "text");
      if (delta) {
        const combined = `${state.messageText}${delta}`;
        if (Buffer.byteLength(combined, "utf8") > this.config.maxMessageBytes) {
          state.messageText = Buffer.from(combined, "utf8")
            .subarray(-this.config.maxMessageBytes)
            .toString("utf8");
          state.messageTruncated = true;
        } else {
          state.messageText = combined;
        }
        await state.emit({ type: "message_delta", payload: { delta }, providerEventRef });
      }
    }
  }

  private async consumeApprovalRequested(payload: Record<string, unknown>): Promise<void> {
    const providerApprovalId = stringField(payload, "id");
    const request = recordField(payload, "request");
    const sessionKey = stringField(request, "sessionKey");
    const state = this.activeBySession.get(sessionKey);
    if (!providerApprovalId || !state) return;
    const dedupeKey = `${providerApprovalId}:requested`;
    if (this.seenApprovalEvents.has(dedupeKey)) return;
    this.seenApprovalEvents.add(dedupeKey);
    const interactionId = `openclaw_approval_${providerApprovalId.replace(/[^A-Za-z0-9_-]/g, "_")}`;
    state.pendingApprovals.set(interactionId, { interactionId, providerApprovalId });
    const expiresAtMs = numberField(payload, "expiresAtMs") ?? Date.now() + this.config.interactionTtlMs;
    const command = stringField(request, "command");
    await state.emit({
      type: "interaction_requested",
      payload: {
        command: command.slice(0, 2048),
        cwd: stringField(request, "cwd").slice(0, 1024)
      },
      providerEventRef: `openclaw-approval:${providerApprovalId}:requested`,
      interaction: {
        allowsFreeText: false,
        expiresAt: new Date(expiresAtMs),
        interactionId,
        options: [
          { id: "allow_once", label: "Allow once" },
          { id: "deny", label: "Deny" }
        ],
        policyBindingHash: state.policyBindingHash,
        prompt: command ? `Allow OpenClaw to run: ${command.slice(0, 1000)}` : "Allow this OpenClaw operation?",
        providerCorrelationRef: providerApprovalId,
        type: "approval"
      }
    });
  }

  private consumeApprovalResolved(payload: Record<string, unknown>): void {
    const providerApprovalId = stringField(payload, "id");
    if (!providerApprovalId) return;
    const dedupeKey = `${providerApprovalId}:resolved`;
    if (this.seenApprovalEvents.has(dedupeKey)) return;
    this.seenApprovalEvents.add(dedupeKey);
    for (const state of this.activeByRun.values()) {
      for (const [interactionId, pending] of state.pendingApprovals) {
        if (pending.providerApprovalId === providerApprovalId) {
          state.pendingApprovals.delete(interactionId);
        }
      }
    }
  }

  private async consumeGap(gap: { actual: number; expected: number }): Promise<void> {
    for (const state of this.activeByRun.values()) {
      await state.emit({
        type: "warning",
        payload: { code: "OPENCLAW_EVENT_GAP", ...gap }
      });
      await this.reconcile(handleFor(state));
    }
  }

  private async consumeDisconnect(error?: Error): Promise<void> {
    if (this.reconnecting || this.activeByRun.size === 0) return;
    this.reconnecting = true;
    try {
      const connection = await this.connection();
      await connection.reconnect();
      for (const state of this.activeByRun.values()) {
        await this.reconcile(handleFor(state));
      }
    } catch (reconnectError) {
      for (const state of this.activeByRun.values()) {
        state.state = "failed";
        await state.emit({
          type: "run_completed",
          payload: {
            status: "failed",
            failure_code: "OPENCLAW_GATEWAY_DISCONNECTED",
            message: this.safeMessage(reconnectError ?? error)
          }
        });
      }
      this.activeByRun.clear();
      this.activeBySession.clear();
    } finally {
      this.reconnecting = false;
    }
  }

  private async prepareRun(
    input: InteractiveStartInput,
    sessionKey: string
  ): Promise<PreparedOpenClawGatewayRun> {
    const workspaceRoot = buildOpenClawRunWorkspaceRoot(
      this.config.workspaceRoot,
      input.scope.executionId
    );
    const normalized = normalizeOpenClawOptions({
      request: input.request,
      executionId: input.scope.executionId
    });
    let stagedArtifacts: OpenClawStagedInput[] = [];
    if (input.providerContext.resolved_artifacts.length > 0) {
      stagedArtifacts = await stageResolvedAgentArtifactsForOpenClaw({
        workspaceRoot,
        artifacts: input.providerContext.resolved_artifacts,
        transfer: (transferInput) => transferOpenClawInputViaWsl({
          wslDistro: this.config.wslDistro,
          allowedWorkspaceRoot: workspaceRoot,
          ...transferInput
        }),
        transferFile: (transferInput) => transferOpenClawFileViaWsl({
          wslDistro: this.config.wslDistro,
          ...transferInput
        })
      });
    }
    const options = {
      ...normalized,
      staged_inputs: [...normalized.staged_inputs, ...stagedArtifacts]
    };
    return {
      expectedOutputs: options.expected_outputs,
      prompt: buildOpenClawPrompt({
        request: input.request,
        workspaceRoot,
        options,
        ...(input.providerContext.agent_skill_selection
          ? { selection: input.providerContext.agent_skill_selection }
          : {})
      }),
      sessionKey,
      workspaceRoot
    };
  }

  private async verifyRun(state: OpenClawProtectedHandle): Promise<OpenClawVerificationResult[]> {
    if (this.dependencies.verifyRun) {
      return this.dependencies.verifyRun({
        expectedOutputs: state.expectedOutputs,
        workspaceRoot: state.workspaceRoot
      });
    }
    return verifyOpenClawOutputs({
      expectedOutputs: state.expectedOutputs,
      workspaceRoot: state.workspaceRoot,
      inspectFile: (workspaceAbsolutePath) => inspectOpenClawWorkspaceFileViaWsl({
        wslDistro: this.config.wslDistro,
        workspaceAbsolutePath,
        allowedWorkspaceRoot: state.workspaceRoot
      })
    });
  }

  private removeActive(state: OpenClawProtectedHandle): void {
    this.activeByRun.delete(state.runId);
    for (const key of providerSessionAliases(state.sessionKey, this.config.agentId)) {
      this.activeBySession.delete(key);
    }
  }

  private safeMessage(error: unknown): string {
    const message = error instanceof Error
      ? error.message
      : String(error ?? "OpenClaw Gateway failed.");
    return String(redactOpenClawGatewayDiagnostic(message, this.config.credential ?? ""));
  }
}

function readEffectiveExecPolicy(value: unknown): {
  ask: string;
  askFallback: string;
  security: string;
} {
  const config = recordField(value, "config");
  const root = Object.keys(config).length > 0 ? config : isRecord(value) ? value : {};
  const exec = recordField(recordField(root, "tools"), "exec");
  return {
    ask: stringField(exec, "ask"),
    askFallback: stringField(exec, "askFallback"),
    security: stringField(exec, "security")
  };
}

function protectedHandle(handle: ProviderSessionHandle): OpenClawProtectedHandle {
  if (!isRecord(handle.protectedHandle)) throw new Error("Invalid OpenClaw provider handle.");
  return handle.protectedHandle as unknown as OpenClawProtectedHandle;
}

function handleFor(state: OpenClawProtectedHandle): ProviderSessionHandle {
  return {
    providerRunRef: state.runId,
    providerSessionRef: state.sessionKey,
    providerTurnRef: state.runId,
    protectedHandle: state
  };
}

function reconciledState(status: string, fallback: AgentSessionState): AgentSessionState {
  if (["aborted", "cancelled"].includes(status)) return "cancelled";
  if (["completed", "ok", "success"].includes(status)) return "completed";
  if (["failed", "error"].includes(status)) return "failed";
  if (["running", "accepted", "pending"].includes(status)) return "running";
  return fallback;
}

function providerWaitStatus(value: unknown): string {
  const error = stringField(value, "error");
  if (error === "aborted" || error === "cancelled") return error;
  return stringField(value, "stopReason") || error || stringField(value, "status");
}

function providerSessionAliases(sessionKey: string, agentId: string): string[] {
  const canonicalPrefix = `agent:${agentId}:`;
  return sessionKey.startsWith(canonicalPrefix)
    ? [sessionKey, sessionKey.slice(canonicalPrefix.length)]
    : [sessionKey, `${canonicalPrefix}${sessionKey}`];
}

async function assertProviderSessionExists(
  connection: OpenClawGatewayConnection,
  sessionKey: string,
  agentId: string
): Promise<void> {
  const listed = await connection.request("sessions.list", {});
  const rawSessions = isRecord(listed) ? listed.sessions : undefined;
  const sessions = Array.isArray(rawSessions) ? rawSessions.filter(isRecord) : [];
  const aliases = new Set(providerSessionAliases(sessionKey, agentId));
  const found = sessions.some((session) => {
    const candidate = stringField(session, "key") || stringField(session, "sessionKey");
    return aliases.has(candidate);
  });
  if (!found) {
    throw new ProviderSessionUnavailableError(
      "OpenClaw provider session is unavailable; refusing replacement continuation."
    );
  }
}
