import { randomUUID } from "node:crypto";

import type {
  ClaimedInteraction,
  InteractiveAgentAdapter,
  InteractivePreflightInput,
  InteractivePreflightResult,
  InteractiveProviderEvent,
  InteractiveStartInput,
  ProviderCancellationResult,
  ProviderInteractionLaunch,
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
  buildRageniusDynamicToolSpecs,
  buildRageniusManagedInteractionGuidance,
  parseRageniusAuthenticationHandoffToolCall,
  parseRageniusInteractionToolCall,
  parseRageniusUserActionToolCall,
  rageniusAuthenticationHandoffToolSpec,
  rageniusInteractionToolSpec,
  rageniusUserActionToolSpec,
  type ManagedInteractionToolRequest
} from "./codex-interaction-tool.js";
import {
  decodeCodexMcpElicitation,
  McpElicitationDecodeError,
  translateMcpElicitationResponse,
  type NormalizedMcpElicitation
} from "./codex-mcp-elicitation.js";
import {
  eligibleManagedAuthenticationTargets,
  type CodexManagedAuthenticationTarget,
  type ManagedAuthenticationVerifier
} from "./codex-managed-auth-targets.js";
import {
  createCodexRunWorkspace,
  stageCodexArtifacts
} from "../agents/codex-workspace.js";
import type { CodexStagedArtifact } from "../agents/codex-cli-types.js";
import type { AgentInteractionType } from "./interactive-agent-types.js";
import {
  evaluateCodexInteractiveOperations,
  type CodexMcpToolOutcome
} from "./codex-interactive-result-evaluator.js";
import type { AgentOperationPlanItem } from "../agents/agent-provider-context.js";

export interface CodexAppServerInteractiveConfig {
  authHandoffEnabled?: boolean;
  enabled: boolean;
  command: string;
  initializationTimeoutMs: number;
  interactionTtlMs: number;
  managedAuthTargets?: readonly CodexManagedAuthenticationTarget[];
  maxDeltaBytes: number;
  maxLineBytes: number;
  maxStderrBytes: number;
  mcpAuthAllowedHosts?: readonly string[];
  mcpElicitationEnabled?: boolean;
  runRoot: string;
  supportedVersions: string[];
  userActionEnabled?: boolean;
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
  kind: "approval" | "input" | "mcp" | "managed_authentication" | "managed_user_action";
  managedRequest?: ManagedInteractionToolRequest;
  mcpRequest?: NormalizedMcpElicitation;
  options: Array<{ id: string; label: string }>;
  requestId: string | number;
  type: "approval" | "clarification" | "selection" | "authentication_handoff" | "user_action_required";
  verificationTarget?: CodexManagedAuthenticationTarget;
};

type CodexProtectedHandle = {
  emit: (event: InteractiveProviderEvent) => Promise<void>;
  messageDelta: string;
  messageDeltaTruncated: boolean;
  messageQueue: Promise<void>;
  mcpOutcomes: CodexMcpToolOutcome[];
  operationPlan: AgentOperationPlanItem[];
  pending: Map<string, PendingProviderRequest>;
  threadId: string | null;
  turnId: string | null;
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
    private readonly factory: CodexAppServerTransportFactory,
    private readonly authenticationVerifiers: ReadonlyMap<string, ManagedAuthenticationVerifier> = new Map()
  ) {
    this.codec = new CodexAppServerCodec({
      maxDeltaBytes: config.maxDeltaBytes,
      maxLineBytes: config.maxLineBytes
    });
  }

  async preflight(input: InteractivePreflightInput): Promise<InteractivePreflightResult> {
    const capabilities = this.capabilities();
    const base = {
      capabilities,
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
      (type) => !capabilities.interactionTypes.includes(type)
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
      mcpOutcomes: [],
      operationPlan: input.providerContext.operation_plan.map((operation) => ({ ...operation })),
      pending: new Map(),
      state: "running",
      threadId: null,
      terminalWaiters: [],
      transport,
      turnId: null
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
        capabilities: {
          experimentalApi: true,
          ...(this.config.mcpElicitationEnabled
            ? { mcpServerOpenaiFormElicitation: true }
            : {})
        }
      });
      await transport.notify("initialized", {});
      const eligibleTargets = this.eligibleTargets();
      const threadResponse = recordValue(await transport.request("thread/start", {
        approvalPolicy: "on-request",
        approvalsReviewer: "user",
        cwd: workspace.root_absolute_path,
        dynamicTools: buildRageniusDynamicToolSpecs({
          inputEnabled: input.requiredInteractionTypes.some(
            (type) => type === "clarification" || type === "selection"
          ),
          authHandoffEnabled: this.config.authHandoffEnabled === true,
          userActionEnabled: this.config.userActionEnabled === true,
          eligibleTargets
        }),
        ephemeral: true,
        experimentalRawEvents: false,
        sandbox: sandboxFor(input.policy.workspaceAccess)
      }));
      const threadId = stringValue(recordValue(threadResponse.thread).id);
      if (!threadId) throw new Error("Codex thread/start did not return a thread id.");
      protectedHandle.threadId = threadId;
      const turnResponse = recordValue(await transport.request("turn/start", {
        threadId,
        input: [{
          type: "text",
          text: buildInteractiveTurnText(
            input,
            stagedArtifacts,
            buildRageniusManagedInteractionGuidance({
              authHandoffEnabled: this.config.authHandoffEnabled === true,
              userActionEnabled: this.config.userActionEnabled === true,
              eligibleTargets
            })
          )
        }]
      }));
      const turnId = stringValue(recordValue(turnResponse.turn).id);
      if (!turnId) throw new Error("Codex turn/start did not return a turn id.");
      protectedHandle.turnId = turnId;
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
    if (pending.kind === "approval") {
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
    } else if (pending.kind === "input") {
      const text = interactionResponseText(pending, claim.responseSummary);
      await state.transport.respond(pending.requestId, {
        success: true,
        contentItems: [{ type: "inputText", text }]
      });
    } else if (pending.kind === "mcp" && pending.mcpRequest) {
      if (
        pending.type === "authentication_handoff" &&
        stringValue(claim.responseSummary.outcome) === "completed"
      ) {
        await this.verifyAuthentication(claim.interaction.executionId, pending);
      }
      await state.transport.respond(
        pending.requestId,
        translateMcpElicitationResponse(pending.mcpRequest, claim.responseSummary)
      );
    } else if (pending.kind === "managed_authentication") {
      const outcome = stringValue(claim.responseSummary.outcome);
      if (outcome === "completed") {
        await this.verifyAuthentication(claim.interaction.executionId, pending);
      }
      await state.transport.respond(pending.requestId, {
        success: outcome === "completed",
        contentItems: [{
          type: "inputText",
          text: outcome === "completed"
            ? "Authentication was verified. Continue the same operation."
            : "The user cancelled authentication. Do not continue the protected operation."
        }]
      });
    } else if (pending.kind === "managed_user_action") {
      const completed = stringValue(claim.responseSummary.outcome) === "completed";
      await state.transport.respond(pending.requestId, {
        success: completed,
        contentItems: [{
          type: "inputText",
          text: completed
            ? "The user reported completion. Verify the observable result before continuing."
            : "The user cancelled the requested action."
        }]
      });
    } else {
      throw new Error("Unsupported Codex interaction response binding.");
    }
    state.pending.delete(claim.interactionId);
  }

  async launchInteraction(
    handle: ProviderSessionHandle,
    interactionId: string
  ): Promise<ProviderInteractionLaunch> {
    const pending = protectedHandle(handle).pending.get(interactionId);
    if (!pending || pending.type !== "authentication_handoff") {
      throw new Error("Authentication launch is not pending.");
    }
    const target = pending.mcpRequest?.protectedLaunchTarget ??
      pending.managedRequest?.protectedLaunchTarget;
    if (!target) throw new Error("Authentication launch target is unavailable.");
    const expiresAt = new Date(Date.now() + 30_000);
    if (target.kind === "provider_window") {
      return {
        application: target.application,
        expiresAt,
        kind: "provider_window",
        provider: target.provider
      };
    }
    const url = new URL(target.url);
    const allowedHosts = pending.verificationTarget?.allowedHosts ??
      this.config.mcpAuthAllowedHosts ?? [];
    if (
      url.protocol !== "https:" ||
      url.username ||
      url.password ||
      url.hash ||
      !allowedHosts.includes(url.hostname)
    ) {
      throw new Error("Authentication launch target failed validation.");
    }
    return { expiresAt, kind: "https_url", launchUrl: url.toString() };
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
    if (event.type === "tool_completed" && isMcpToolPayload(event.payload)) {
      state.mcpOutcomes.push(mcpOutcomeFromPayload(event.payload));
    }
    if (event.type === "run_completed" && state.mcpOutcomes.length > 0) {
      const evaluation = evaluateCodexInteractiveOperations({
        operationPlan: state.operationPlan,
        outcomes: state.mcpOutcomes
      });
      event.payload = {
        ...event.payload,
        status: evaluation.statusOverride,
        operation_verification: evaluation.operationVerification,
        ...(evaluation.failureCode
          ? {
              failure_code: evaluation.failureCode,
              summary: evaluation.failureCode === "MCP_OPERATION_BLOCKED"
                ? "A required MCP operation was blocked."
                : "Required MCP operation evidence is incomplete."
            }
          : {})
      };
    }
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
    if (method === "mcpServer/elicitation/request") {
      await this.consumeMcpElicitation(state, input, id, method, params);
      return;
    }
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
      state.pending.set(interactionId, {
        kind: "approval",
        options: [],
        requestId: id,
        type: "approval"
      });
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
          kind: "input",
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
    if (
      method === "item/tool/call" &&
      stringValue(params.tool) === rageniusAuthenticationHandoffToolSpec.name
    ) {
      await this.consumeManagedToolCall(state, input, id, method, params, "authentication");
      return;
    }
    if (
      method === "item/tool/call" &&
      stringValue(params.tool) === rageniusUserActionToolSpec.name
    ) {
      await this.consumeManagedToolCall(state, input, id, method, params, "user_action");
      return;
    }
    await state.transport.respond(id, {
      error: { code: "UNSUPPORTED_METHOD", message: "RAGenius does not support this provider request." }
    });
  }

  private capabilities(): InteractivePreflightResult["capabilities"] {
    const interactionTypes: AgentInteractionType[] = [...CODEX_CAPABILITIES.interactionTypes];
    if (
      (this.config.authHandoffEnabled || this.config.mcpElicitationEnabled) &&
      this.eligibleTargets().length > 0
    ) {
      interactionTypes.push("authentication_handoff");
    }
    if (this.config.userActionEnabled) interactionTypes.push("user_action_required");
    return { ...CODEX_CAPABILITIES, interactionTypes };
  }

  private eligibleTargets(): readonly CodexManagedAuthenticationTarget[] {
    return eligibleManagedAuthenticationTargets(
      this.config.managedAuthTargets ?? [],
      this.authenticationVerifiers
    );
  }

  private async consumeMcpElicitation(
    state: CodexProtectedHandle,
    input: InteractiveStartInput,
    id: string | number,
    method: string,
    params: Record<string, unknown>
  ): Promise<void> {
    if (!this.config.mcpElicitationEnabled || !state.threadId) {
      await state.transport.respond(id, {
        action: "decline",
        content: null,
        _meta: null
      });
      return;
    }
    try {
      const eligibleTargets = this.eligibleTargets();
      const eligibleAuthHosts = (this.config.mcpAuthAllowedHosts ?? []).filter((host) =>
        eligibleTargets.some((target) => target.allowedHosts.includes(host))
      );
      const decoded = decodeCodexMcpElicitation(params, {
        activeThreadId: state.threadId,
        activeTurnId: state.turnId,
        allowedAuthenticationHosts: eligibleAuthHosts,
        authorizationBound:
          input.providerContext.authorization.state === "confirmed" &&
          input.providerContext.operation_plan.some(
            (operation) => operation.required && operation.kind !== "read"
          ),
        providerRequestId: id
      });
      const verificationTarget = decoded.presentation?.targetHost
        ? eligibleTargets.find((target) =>
            target.allowedHosts.includes(decoded.presentation!.targetHost!)
          )
        : undefined;
      const interactionId = newInteractionId();
      state.pending.set(interactionId, {
        kind: "mcp",
        mcpRequest: decoded,
        options: decoded.options,
        requestId: id,
        type: decoded.interactionType,
        ...(verificationTarget ? { verificationTarget } : {})
      });
      await state.emit({
        type: "interaction_requested",
        providerEventRef: `${method}:${String(id)}`,
        payload: { server_name: decoded.serverName },
        interaction: {
          allowsFreeText: decoded.allowsFreeText,
          expiresAt: new Date(Date.now() + this.config.interactionTtlMs),
          interactionId,
          options: decoded.options,
          ...(decoded.presentation ? { presentation: decoded.presentation } : {}),
          policyBindingHash: input.providerContext.authorization.policy_fingerprint,
          prompt: decoded.prompt,
          providerCorrelationRef: `${method}:${String(id)}`,
          type: decoded.interactionType
        }
      });
    } catch (error) {
      await state.transport.respond(id, { action: "decline", content: null, _meta: null });
      await state.emit({
        type: "warning",
        providerEventRef: `${method}:${String(id)}`,
        payload: {
          code: error instanceof McpElicitationDecodeError
            ? error.code
            : "MCP_ELICITATION_UNSUPPORTED",
          message: "The MCP elicitation request was rejected."
        }
      });
    }
  }

  private async consumeManagedToolCall(
    state: CodexProtectedHandle,
    input: InteractiveStartInput,
    id: string | number,
    method: string,
    params: Record<string, unknown>,
    kind: "authentication" | "user_action"
  ): Promise<void> {
    try {
      const parsed = kind === "authentication"
        ? parseRageniusAuthenticationHandoffToolCall(params.arguments, this.eligibleTargets())
        : parseRageniusUserActionToolCall(params.arguments);
      const responseBinding = parsed.responseBinding;
      const verificationTarget = responseBinding.kind === "managed_authentication"
        ? this.eligibleTargets().find((target) => target.id === responseBinding.targetId)
        : undefined;
      const interactionId = newInteractionId();
      state.pending.set(interactionId, {
        kind: responseBinding.kind,
        managedRequest: parsed,
        options: [],
        requestId: id,
        type: parsed.type,
        ...(verificationTarget ? { verificationTarget } : {})
      });
      await state.emit({
        type: "interaction_requested",
        providerEventRef: `${method}:${String(id)}`,
        payload: {},
        interaction: {
          allowsFreeText: false,
          expiresAt: new Date(Date.now() + this.config.interactionTtlMs),
          interactionId,
          options: [],
          presentation: parsed.presentation,
          policyBindingHash: input.providerContext.authorization.policy_fingerprint,
          prompt: parsed.prompt,
          providerCorrelationRef: `${method}:${String(id)}`,
          type: parsed.type
        }
      });
    } catch (error) {
      await state.transport.respond(id, {
        success: false,
        contentItems: [{
          type: "inputText",
          text: error instanceof Error && error.message.startsWith("AUTHENTICATION_TARGET_NOT_APPROVED")
            ? "AUTHENTICATION_TARGET_NOT_APPROVED"
            : "Invalid managed RAGenius interaction request."
        }]
      });
    }
  }

  private async verifyAuthentication(
    executionId: string,
    pending: PendingProviderRequest
  ): Promise<void> {
    const target = pending.verificationTarget;
    const verifier = target
      ? this.authenticationVerifiers.get(target.verifierId)
      : undefined;
    if (!target || !verifier) throw new Error("AUTHENTICATION_HANDOFF_NOT_VERIFIED");
    const result = await verifier.verify({ executionId, target });
    if (!result.verified) throw new Error("AUTHENTICATION_HANDOFF_NOT_VERIFIED");
  }
}

function isMcpToolPayload(payload: Record<string, unknown>): boolean {
  return payload.item_type === "mcpToolCall" || payload.item_type === "mcp_tool_call";
}

function mcpOutcomeFromPayload(payload: Record<string, unknown>): CodexMcpToolOutcome {
  const rawStatus = stringValue(payload.status);
  const errorCode = stringValue(payload.error_code);
  const status: CodexMcpToolOutcome["status"] =
    rawStatus === "completed" || rawStatus === "success"
      ? "completed"
      : rawStatus === "cancelled"
        ? "cancelled"
        : errorCode === "permission_denied" || rawStatus === "denied"
          ? "denied"
          : "failed";
  return {
    ...(errorCode ? { errorCode } : {}),
    itemId: stringValue(payload.item_id),
    ...(stringValue(payload.operation_id) ? { operationId: stringValue(payload.operation_id) } : {}),
    status,
    toolName: stringValue(payload.tool_name)
  };
}

function buildInteractiveTurnText(
  input: InteractiveStartInput,
  stagedArtifacts: CodexStagedArtifact[],
  managedGuidance = ""
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
  if (managedGuidance) sections.push(managedGuidance);
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
