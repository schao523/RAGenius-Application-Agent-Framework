import { randomUUID } from "node:crypto";

import type {
  ClaimedInteraction,
  InteractiveAgentAdapter,
  InteractivePreflightInput,
  InteractivePreflightResult,
  InteractiveProviderEvent,
  InteractiveStartInput,
  ProviderCancellationResult,
  ProviderReconciliationResult,
  ProviderSessionHandle
} from "./interactive-agent-adapter.js";
import {
  CodexAppServerCodec,
  isRecord,
  recordValue,
  stringValue
} from "./codex-app-server-codec.js";
import {
  parseRageniusInteractionToolCall,
  rageniusInteractionToolSpec
} from "./codex-interaction-tool.js";
import {
  createCodexRunWorkspace,
  stageCodexArtifacts
} from "../agents/codex-workspace.js";
import type { CodexStagedArtifact } from "../agents/codex-cli-types.js";

export interface CodexAppServerInteractiveConfig {
  enabled: boolean;
  command: string;
  initializationTimeoutMs: number;
  interactionTtlMs: number;
  maxDeltaBytes: number;
  maxLineBytes: number;
  maxStderrBytes: number;
  runRoot: string;
  supportedVersions: string[];
}

export interface CodexVersionInfo {
  available: boolean;
  reason?: string;
  version?: string;
}

export interface CodexAppServerTransport {
  request(method: string, params?: unknown): Promise<unknown>;
  notify(method: string, params?: unknown): Promise<void>;
  respond(id: string | number, result: unknown): Promise<void>;
  onMessage(handler: (message: Record<string, unknown>) => Promise<void>): void;
  onClose(handler: (error?: Error) => Promise<void>): void;
  close(): Promise<void>;
  isClosed?(): boolean;
}

export interface CodexAppServerTransportFactory {
  versionInfo(): Promise<CodexVersionInfo>;
  create(): Promise<CodexAppServerTransport>;
}

type PendingProviderRequest = {
  options: Array<{ id: string; label: string }>;
  requestId: string | number;
  type: "approval" | "clarification" | "selection";
};

type CodexProtectedHandle = {
  emit: (event: InteractiveProviderEvent) => Promise<void>;
  messageDelta: string;
  messageDeltaTruncated: boolean;
  messageQueue: Promise<void>;
  pending: Map<string, PendingProviderRequest>;
  state: "running" | "cancelled" | "completed" | "failed";
  terminalWaiters: Array<(state: CodexProtectedHandle["state"]) => void>;
  transport: CodexAppServerTransport;
};

const CODEX_CAPABILITIES = {
  cancellation: true,
  eventReplay: "none" as const,
  interactionTypes: ["approval", "clarification", "selection"] as const,
  protocolTransport: true,
  reconnectReconciliation: false,
  sameSessionContinuation: true,
  sameTurnResume: true
};

export class CodexAppServerAdapter implements InteractiveAgentAdapter {
  readonly backend = "codex_cli" as const;
  private readonly codec: CodexAppServerCodec;

  constructor(
    private readonly config: CodexAppServerInteractiveConfig,
    private readonly factory: CodexAppServerTransportFactory
  ) {
    this.codec = new CodexAppServerCodec({
      maxDeltaBytes: config.maxDeltaBytes,
      maxLineBytes: config.maxLineBytes
    });
  }

  async preflight(input: InteractivePreflightInput): Promise<InteractivePreflightResult> {
    const base = {
      capabilities: {
        ...CODEX_CAPABILITIES,
        interactionTypes: [...CODEX_CAPABILITIES.interactionTypes]
      },
      protocolVersion: "unknown",
      transport: "codex_app_server" as const
    };
    if (!this.config.enabled) {
      return { ...base, available: false, reason: "Codex interactive app-server is disabled." };
    }
    const version = await this.factory.versionInfo();
    if (!version.available || !version.version) {
      return {
        ...base,
        available: false,
        reason: version.reason ?? "Codex app-server is unavailable."
      };
    }
    if (!this.config.supportedVersions.includes(version.version)) {
      return {
        ...base,
        available: false,
        protocolVersion: version.version,
        reason: `Codex app-server version ${version.version} is not supported.`
      };
    }
    const missing = input.requiredInteractionTypes.filter(
      (type) => !CODEX_CAPABILITIES.interactionTypes.includes(
        type as (typeof CODEX_CAPABILITIES.interactionTypes)[number]
      )
    );
    return missing.length > 0
      ? {
          ...base,
          available: false,
          protocolVersion: version.version,
          reason: `Codex app-server lacks required interactions: ${missing.join(", ")}.`
        }
      : { ...base, available: true, protocolVersion: version.version };
  }

  async start(input: InteractiveStartInput): Promise<ProviderSessionHandle> {
    const transport = await this.factory.create();
    const protectedHandle: CodexProtectedHandle = {
      emit: input.emit,
      messageDelta: "",
      messageDeltaTruncated: false,
      messageQueue: Promise.resolve(),
      pending: new Map(),
      state: "running",
      terminalWaiters: [],
      transport
    };
    transport.onMessage((message) => this.enqueueMessage(protectedHandle, input, message));
    transport.onClose((error) => this.enqueueDisconnect(protectedHandle, error));
    try {
      const workspace = await createCodexRunWorkspace({
        executionId: input.scope.executionId,
        runRoot: this.config.runRoot
      });
      const stagedArtifacts = await stageCodexArtifacts({
        workspace,
        artifacts: input.providerContext.resolved_artifacts
      });
      await transport.request("initialize", {
        clientInfo: { name: "RAGenius", title: "RAGenius Execution Subsystem", version: "0.1.0" },
        capabilities: { experimentalApi: true }
      });
      await transport.notify("initialized", {});
      const threadResponse = recordValue(await transport.request("thread/start", {
        approvalPolicy: "on-request",
        approvalsReviewer: "user",
        cwd: workspace.root_absolute_path,
        dynamicTools: [rageniusInteractionToolSpec],
        ephemeral: true,
        experimentalRawEvents: false,
        sandbox: sandboxFor(input.policy.workspaceAccess)
      }));
      const threadId = stringValue(recordValue(threadResponse.thread).id);
      if (!threadId) throw new Error("Codex thread/start did not return a thread id.");
      const turnResponse = recordValue(await transport.request("turn/start", {
        threadId,
        input: [{
          type: "text",
          text: buildInteractiveTurnText(input, stagedArtifacts)
        }]
      }));
      const turnId = stringValue(recordValue(turnResponse.turn).id);
      if (!turnId) throw new Error("Codex turn/start did not return a turn id.");
      return {
        providerRunRef: turnId,
        providerSessionRef: threadId,
        providerTurnRef: turnId,
        protectedHandle
      };
    } catch (error) {
      await transport.close();
      throw error;
    }
  }

  async respond(handle: ProviderSessionHandle, claim: ClaimedInteraction): Promise<void> {
    const state = protectedHandle(handle);
    const pending = state.pending.get(claim.interactionId);
    if (!pending) throw new Error("Codex provider interaction is no longer pending.");
    if (pending.type === "approval") {
      const decision = stringValue(claim.responseSummary.decision);
      const codexDecision = decision === "allow_once"
        ? "accept"
        : decision === "cancel_execution"
          ? "cancel"
          : decision === "deny"
            ? "decline"
            : "";
      if (!codexDecision) throw new Error("Unsupported Codex approval decision.");
      await state.transport.respond(pending.requestId, { decision: codexDecision });
    } else {
      const text = interactionResponseText(pending, claim.responseSummary);
      await state.transport.respond(pending.requestId, {
        success: true,
        contentItems: [{ type: "inputText", text }]
      });
    }
    state.pending.delete(claim.interactionId);
  }

  async cancel(handle: ProviderSessionHandle): Promise<ProviderCancellationResult> {
    const state = protectedHandle(handle);
    if (!handle.providerTurnRef) return { cancelled: false };
    await state.transport.request("turn/interrupt", {
      threadId: handle.providerSessionRef,
      turnId: handle.providerTurnRef
    });
    const terminalState = await waitForTerminalState(
      state,
      this.config.initializationTimeoutMs
    );
    if (terminalState === "cancelled") return { cancelled: true };
    await state.transport.close();
    return {
      cancelled: false,
      diagnostics: {
        code: "CODEX_INTERRUPT_NOT_CONFIRMED",
        terminal_state: terminalState
      }
    };
  }

  async reconcile(handle: ProviderSessionHandle): Promise<ProviderReconciliationResult> {
    const state = protectedHandle(handle);
    if (state.transport.isClosed?.()) return { state: "failed" };
    return { state: state.state };
  }

  private async consumeMessage(
    state: CodexProtectedHandle,
    input: InteractiveStartInput,
    message: Record<string, unknown>
  ): Promise<void> {
    const method = stringValue(message.method);
    const id = message.id;
    if ((typeof id === "number" || typeof id === "string") && method) {
      await this.consumeServerRequest(state, input, id, method, recordValue(message.params));
      return;
    }
    if (!method) return;
    const event = this.codec.normalizeNotification(message);
    if (!event) return;
    if (event.type === "message_delta") {
      appendMessageDelta(state, event, this.config.maxDeltaBytes);
      return;
    }
    await flushMessageDelta(state);
    if (event.type === "run_completed") state.state = event.payload.status === "failed" ? "failed" : "completed";
    if (event.type === "run_cancelled") state.state = "cancelled";
    await state.emit(event);
    if (event.type === "run_completed" || event.type === "run_cancelled") {
      for (const resolve of state.terminalWaiters.splice(0)) resolve(state.state);
      await state.transport.close();
    }
  }

  private enqueueMessage(
    state: CodexProtectedHandle,
    input: InteractiveStartInput,
    message: Record<string, unknown>
  ): Promise<void> {
    state.messageQueue = state.messageQueue
      .then(() => this.consumeMessage(state, input, message))
      .catch(async (error) => {
        if (state.state === "running") {
          try {
            await failProviderRun(
              state,
              "CODEX_APP_SERVER_PROTOCOL_FAILED",
              error instanceof Error ? error.message : String(error)
            );
          } finally {
            await state.transport.close();
          }
        }
      });
    return state.messageQueue;
  }

  private enqueueDisconnect(
    state: CodexProtectedHandle,
    error?: Error
  ): Promise<void> {
    state.messageQueue = state.messageQueue
      .catch(() => undefined)
      .then(async () => {
        if (state.state !== "running") return;
        await failProviderRun(
          state,
          "CODEX_APP_SERVER_DISCONNECTED",
          error?.message ?? "Codex app-server process disconnected."
        );
      })
      .catch(() => {
        state.state = "failed";
        for (const resolve of state.terminalWaiters.splice(0)) resolve(state.state);
      });
    return state.messageQueue;
  }

  private async consumeServerRequest(
    state: CodexProtectedHandle,
    input: InteractiveStartInput,
    id: string | number,
    method: string,
    params: Record<string, unknown>
  ): Promise<void> {
    await flushMessageDelta(state);
    if (method === "item/permissions/requestApproval") {
      await state.transport.respond(id, { decision: "decline" });
      await state.emit({
        type: "warning",
        providerEventRef: `${method}:${String(id)}`,
        payload: {
          code: "CODEX_PERMISSION_EXPANSION_BLOCKED",
          message: "Provider permission expansion was denied by the confirmed RAGenius policy."
        }
      });
      return;
    }
    if (isApprovalMethod(method)) {
      const interactionId = newInteractionId();
      state.pending.set(interactionId, { options: [], requestId: id, type: "approval" });
      await state.emit({
        type: "interaction_requested",
        providerEventRef: `${method}:${String(id)}`,
        payload: {
          command_summary: boundedSummary(params.command),
          cwd_label: boundedSummary(params.cwd)
        },
        interaction: {
          allowsFreeText: false,
          expiresAt: new Date(Date.now() + this.config.interactionTtlMs),
          interactionId,
          options: [],
          policyBindingHash: input.providerContext.authorization.policy_fingerprint,
          prompt: approvalPrompt(method, params),
          providerCorrelationRef: `${method}:${String(id)}`,
          type: "approval"
        }
      });
      return;
    }
    if (method === "item/tool/call" && stringValue(params.tool) === rageniusInteractionToolSpec.name) {
      try {
        const parsed = parseRageniusInteractionToolCall(params.arguments);
        const interactionId = newInteractionId();
        state.pending.set(interactionId, {
          options: parsed.options,
          requestId: id,
          type: parsed.type
        });
        await state.emit({
          type: "interaction_requested",
          providerEventRef: `${method}:${String(id)}`,
          payload: {},
          interaction: {
            ...parsed,
            expiresAt: new Date(Date.now() + this.config.interactionTtlMs),
            interactionId,
            policyBindingHash: input.providerContext.authorization.policy_fingerprint,
            providerCorrelationRef: `${method}:${String(id)}`
          }
        });
      } catch {
        await state.transport.respond(id, {
          success: false,
          contentItems: [{ type: "inputText", text: "Invalid bounded RAGenius input request." }]
        });
      }
      return;
    }
    await state.transport.respond(id, {
      error: { code: "UNSUPPORTED_METHOD", message: "RAGenius does not support this provider request." }
    });
  }
}

function buildInteractiveTurnText(
  input: InteractiveStartInput,
  stagedArtifacts: CodexStagedArtifact[]
): string {
  const allowedTypes = [...new Set(
    input.requiredInteractionTypes.filter(
      (type): type is "clarification" | "selection" =>
        type === "clarification" || type === "selection"
    )
  )];
  const requiredTypes = [...new Set(
    (input.requiredOccurrenceTypes ?? []).filter(
      (type): type is "clarification" | "selection" =>
        type === "clarification" || type === "selection"
    )
  )];
  const sections: string[] = [];
  if (allowedTypes.length > 0) sections.push([
    "RAGenius interactive input protocol:",
    `- Allowed interaction types: ${allowedTypes.join(", ")}.`,
    `- Required interaction types for this run: ${requiredTypes.length > 0 ? requiredTypes.join(", ") : "none"}.`,
    "- When user input is needed for an allowed interaction type, you MUST use `ragenius_request_input`.",
    "- Do not ask for that input only in assistant prose.",
    "- Do not call the tool when user input is unnecessary.",
    "- Never request secrets, credentials, tokens, passwords, or one-time codes through this tool."
  ].join("\n"));
  if (stagedArtifacts.length > 0) sections.push([
    "RAGenius selected artifacts:",
    ...stagedArtifacts.map((artifact) =>
      artifact.workspace_relative_path
        ? `- ${artifact.role}: ${artifact.display_name} at ${artifact.workspace_relative_path}`
        : `- ${artifact.role}: ${artifact.display_name} (metadata only)`
    ),
    "Use only these workspace-relative paths. Do not use browser-local or artifact-store paths."
  ].join("\n"));
  sections.push(`User request:\n${input.request.agent_query}`);
  return sections.join("\n\n");
}

async function failProviderRun(
  state: CodexProtectedHandle,
  code: string,
  message: string
): Promise<void> {
  await flushMessageDelta(state);
  state.state = "failed";
  await state.emit({ type: "error", payload: { code, message } });
  await state.emit({
    type: "run_completed",
    payload: { status: "failed", failure_code: code, summary: message }
  });
  for (const resolve of state.terminalWaiters.splice(0)) resolve(state.state);
}

function appendMessageDelta(
  state: CodexProtectedHandle,
  event: InteractiveProviderEvent,
  maxBytes: number
): void {
  const incoming = stringValue(event.payload.delta);
  const combined = Buffer.from(`${state.messageDelta}${incoming}`, "utf8");
  if (combined.byteLength <= maxBytes) {
    state.messageDelta = combined.toString("utf8");
  } else {
    state.messageDelta = combined.subarray(combined.byteLength - maxBytes).toString("utf8");
    state.messageDeltaTruncated = true;
  }
  if (event.payload.truncated === true) state.messageDeltaTruncated = true;
}

async function flushMessageDelta(state: CodexProtectedHandle): Promise<void> {
  if (!state.messageDelta && !state.messageDeltaTruncated) return;
  const delta = state.messageDelta;
  const truncated = state.messageDeltaTruncated;
  state.messageDelta = "";
  state.messageDeltaTruncated = false;
  await state.emit({
    type: "message_delta",
    payload: { delta, ...(truncated ? { truncated: true } : {}) }
  });
}

async function waitForTerminalState(
  state: CodexProtectedHandle,
  timeoutMs: number
): Promise<CodexProtectedHandle["state"] | "timeout"> {
  if (state.state !== "running") return state.state;
  return new Promise((resolve) => {
    const waiter = (terminalState: CodexProtectedHandle["state"]) => {
      clearTimeout(timeout);
      resolve(terminalState);
    };
    const timeout = setTimeout(() => {
      const index = state.terminalWaiters.indexOf(waiter);
      if (index >= 0) state.terminalWaiters.splice(index, 1);
      resolve("timeout");
    }, timeoutMs);
    timeout.unref();
    state.terminalWaiters.push(waiter);
  });
}

function protectedHandle(handle: ProviderSessionHandle): CodexProtectedHandle {
  if (!isRecord(handle.protectedHandle)) throw new Error("Invalid Codex provider handle.");
  return handle.protectedHandle as unknown as CodexProtectedHandle;
}

function sandboxFor(access: AgentPolicyDecisionWorkspaceAccess): "read-only" | "workspace-write" {
  return access === "scoped_write" ? "workspace-write" : "read-only";
}

type AgentPolicyDecisionWorkspaceAccess = "none" | "read_only" | "scoped_write";

function isApprovalMethod(method: string): boolean {
  return [
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval"
  ].includes(method);
}

function approvalPrompt(method: string, params: Record<string, unknown>): string {
  const action = method.includes("fileChange")
    ? "Apply the requested file change?"
    : method.includes("permissions")
      ? "Allow the requested bounded permissions?"
      : "Run the requested command once?";
  const reason = boundedSummary(params.reason);
  return reason ? `${action} ${reason}`.slice(0, 2000) : action;
}

function boundedSummary(value: unknown): string {
  if (typeof value === "string") return value.slice(0, 1000);
  if (Array.isArray(value)) return value.map(String).join(" ").slice(0, 1000);
  return "";
}

function newInteractionId(): string {
  return `interaction_${randomUUID().replaceAll("-", "")}`;
}

function interactionResponseText(
  pending: PendingProviderRequest,
  response: Record<string, unknown>
): string {
  if (pending.type === "clarification") {
    const text = stringValue(response.text).trim();
    if (!text || text.length > 8000) throw new Error("Invalid clarification response.");
    return text;
  }
  const ids = Array.isArray(response.option_ids)
    ? response.option_ids.filter((value): value is string => typeof value === "string")
    : [];
  const labels = ids.map((id) => pending.options.find((option) => option.id === id)?.label)
    .filter((value): value is string => Boolean(value));
  if (labels.length !== ids.length || labels.length === 0) {
    throw new Error("Invalid selection response.");
  }
  return labels.join(", ");
}
