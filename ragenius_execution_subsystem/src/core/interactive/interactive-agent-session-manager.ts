import { randomUUID } from "node:crypto";

import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";
import type { NormalizedExecutionResult } from "../../api/schemas/common-response.schema.js";
import { providerInteractionRequestSchema } from "../../api/schemas/interactive-agent.schema.js";
import type { AgentPolicyDecision } from "../agents/agent-policy.js";
import type { AgentProviderExecutionContext } from "../agents/agent-provider-context.js";
import {
  planAgentExpectedOutputs,
  type PlannedAgentExpectedOutput
} from "../agents/agent-expected-output-planner.js";
import type { PersistedAgentOutputArtifact } from "../agents/agent-output-artifact-persister.js";
import type { AgentSkillRecoveryClass } from "../agent-skills/agent-skill-types.js";
import type { ExecutionStore } from "../execution/execution-store.js";

import type { AgentEventStore } from "./agent-event-store.js";
import type { AgentChatTurnStore } from "./agent-chat-turn-store.js";
import type { AgentInteractionStore } from "./agent-interaction-store.js";
import type { AgentSessionStore } from "./agent-session-store.js";
import type {
  InteractiveAgentAdapter,
  InteractiveProviderEvent,
  ProviderSessionHandle
} from "./interactive-agent-adapter.js";
import { ProviderSessionUnavailableError } from "./interactive-agent-adapter.js";
import type { InteractiveCapabilityService } from "./interactive-capability-service.js";
import type {
  AgentInteractionType,
  AgentSessionRecord,
  ExecutionScope
} from "./interactive-agent-types.js";

export interface StartInteractiveAgentInput {
  policy: AgentPolicyDecision;
  providerContext: AgentProviderExecutionContext;
  request: ExecuteAgentRequest;
  inferredInteractionTypes?: AgentInteractionType[];
  requiredChatLevelInteraction?: boolean;
  requiredInteractionTypes: AgentInteractionType[];
  requiredOccurrenceTypes?: AgentInteractionType[];
  requiredRecoveryClass?: AgentSkillRecoveryClass;
  scope: ExecutionScope;
}

export type StartInteractiveAgentResult =
  | { agentSession: AgentSessionRecord; started: true }
  | {
      failureCode:
        | "EXECUTION_NOT_RUNNING"
        | "INTERACTIVE_ADAPTER_UNAVAILABLE"
        | "INTERACTIVE_CAPABILITY_UNAVAILABLE";
      reason: string;
      started: false;
    };

export interface RespondToInteractionInput extends ExecutionScope {
  expectedVersion: number;
  idempotencyKey: string;
  interactionId: string;
  now?: Date;
  responseSummary: Record<string, unknown>;
}

export type RespondToInteractionResult = {
  outcome: "resolved" | "replay" | "conflict" | "expired" | "not_found";
};

export interface AgentChatFollowUpInput extends ExecutionScope {
  expectedSessionVersion: number;
  idempotencyKey: string;
  kind: "reply" | "continue" | "revise" | "graceful_cancel";
  text?: string;
}

export type AgentChatFollowUpResult = {
  outcome: "accepted" | "replay" | "active" | "closed" | "stale" | "not_ready" | "not_found" | "delivery_unknown" | "provider_session_unavailable" | "requires_new_execution";
};

interface ActiveProviderSession {
  adapter: InteractiveAgentAdapter;
  expiryTimers: Map<string, NodeJS.Timeout>;
  handle: ProviderSessionHandle;
  finalResponseText: string;
  finalResponseTruncated: boolean;
  inferredInteractionTypes: AgentInteractionType[];
  request: ExecuteAgentRequest;
  requiredOccurrenceTypes: Set<AgentInteractionType>;
  scope: ExecutionScope;
}

const MAX_NORMALIZED_PROVIDER_EVENT_BYTES = 65_536;
const MAX_FINAL_RESPONSE_BYTES = 65_536;
const PROVIDER_EVENT_TYPES = new Set<InteractiveProviderEvent["type"]>([
  "error",
  "warning",
  "run_started",
  "progress",
  "message_delta",
  "message_completed",
  "tool_started",
  "tool_completed",
  "interaction_requested",
  "run_completed",
  "run_cancelled"
]);

export class InteractiveAgentSessionManager {
  private readonly capabilityService: InteractiveCapabilityService;
  private readonly chatTurnStore: AgentChatTurnStore | undefined;
  private readonly eventStore: AgentEventStore;
  private readonly executionStore: ExecutionStore;
  private readonly interactionStore: AgentInteractionStore;
  private readonly persistFinalResponse: ((input: {
    executionId: string;
    output: PlannedAgentExpectedOutput;
    request: ExecuteAgentRequest;
    text: string;
  }) => Promise<PersistedAgentOutputArtifact>) | undefined;
  private readonly idleTtlMs: number;
  private readonly sessionStore: AgentSessionStore;
  private readonly active = new Map<string, ActiveProviderSession>();
  private readonly idleTimers = new Map<string, NodeJS.Timeout>();

  constructor(options: {
    capabilityService: InteractiveCapabilityService;
    chatTurnStore?: AgentChatTurnStore;
    eventStore: AgentEventStore;
    executionStore: ExecutionStore;
    idleTtlMs?: number;
    interactionStore: AgentInteractionStore;
    persistFinalResponse?: (input: {
      executionId: string;
      output: PlannedAgentExpectedOutput;
      request: ExecuteAgentRequest;
      text: string;
    }) => Promise<PersistedAgentOutputArtifact>;
    sessionStore: AgentSessionStore;
  }) {
    this.capabilityService = options.capabilityService;
    this.chatTurnStore = options.chatTurnStore;
    this.eventStore = options.eventStore;
    this.executionStore = options.executionStore;
    this.idleTtlMs = options.idleTtlMs ?? 900_000;
    this.interactionStore = options.interactionStore;
    this.persistFinalResponse = options.persistFinalResponse;
    this.sessionStore = options.sessionStore;
  }

  async followUp(input: AgentChatFollowUpInput): Promise<AgentChatFollowUpResult> {
    if (!this.chatTurnStore) return { outcome: "not_ready" };
    if (input.text && requiresNewExecution(input.text)) {
      return { outcome: "requires_new_execution" };
    }
    const session = await this.sessionStore.getByExecution(input);
    const active = this.active.get(input.executionId);
    if (!session) return { outcome: "not_found" };
    if (["completed", "cancelled", "failed"].includes(session.state)) {
      return { outcome: "closed" };
    }
    const activeSession = active ?? await this.restoreIdleSession(session);
    if (!activeSession) return { outcome: "not_found" };
    if (!session.capabilitySnapshot.chatLevelInteraction || !activeSession.adapter.sendFollowUp) {
      return { outcome: "not_ready" };
    }
    const message = followUpMessage(input);
    const claim = await this.chatTurnStore.claim({
      ...input,
      agentSessionId: session.agentSessionId,
      now: new Date(),
      requestSummary: { kind: input.kind, ...(input.text ? { text: input.text } : {}) }
    });
    if (claim.outcome !== "claimed" || !claim.record) {
      return {
        outcome: claim.outcome === "claimed" ? "not_ready" : claim.outcome
      };
    }
    this.clearIdleExpiry(input.executionId);
    await this.eventStore.append({
      ...input,
      occurredAt: new Date(),
      payload: { chat_turn_id: claim.record.chatTurnId, kind: claim.record.kind, sequence: claim.record.sequence },
      type: "chat_follow_up_claimed"
    });
    try {
      activeSession.handle = await activeSession.adapter.sendFollowUp(activeSession.handle, {
        idempotencyKey: input.idempotencyKey,
        kind: input.kind,
        message,
        sequence: claim.record.sequence
      });
      await this.chatTurnStore.update(input, claim.record.chatTurnId, {
        acknowledgementState: "acknowledged",
        providerRunRef: activeSession.handle.providerRunRef,
        state: "running"
      });
      await this.sessionStore.update(
        { ...input, agentSessionId: session.agentSessionId },
        {
          providerRunRef: activeSession.handle.providerRunRef,
          providerTurnRef: activeSession.handle.providerTurnRef
        }
      );
      await this.executionStore.transition({
        scope: input,
        from: ["ready_for_follow_up"],
        result: stateResult(input.executionId, "running", "Agent follow-up started.")
      });
      await this.eventStore.append({
        ...input,
        occurredAt: new Date(),
        payload: { chat_turn_id: claim.record.chatTurnId, sequence: claim.record.sequence },
        type: "chat_follow_up_acknowledged"
      });
      return { outcome: "accepted" };
    } catch (error) {
      if (error instanceof ProviderSessionUnavailableError) {
        await this.chatTurnStore.update(input, claim.record.chatTurnId, {
          acknowledgementState: "unacknowledged",
          completedAt: new Date(),
          normalizedResult: { failure_code: "PROVIDER_SESSION_UNAVAILABLE" },
          state: "failed"
        });
        await this.failExecution(
          input,
          "PROVIDER_SESSION_UNAVAILABLE",
          "The provider session is unavailable; replacement continuation was refused."
        );
        return { outcome: "provider_session_unavailable" };
      }
      await this.chatTurnStore.update(input, claim.record.chatTurnId, {
        acknowledgementState: "ambiguous",
        state: "delivery_unknown"
      });
      await this.eventStore.append({
        ...input,
        occurredAt: new Date(),
        payload: { chat_turn_id: claim.record.chatTurnId, sequence: claim.record.sequence },
        type: "chat_follow_up_delivery_unknown"
      });
      return { outcome: "delivery_unknown" };
    }
  }

  async start(input: StartInteractiveAgentInput): Promise<StartInteractiveAgentResult> {
    const execution = await this.executionStore.get(input.scope);
    if (execution?.status !== "running") {
      return {
        failureCode: "EXECUTION_NOT_RUNNING",
        reason: "Interactive execution can start only after pre-run confirmation and queue claim.",
        started: false
      };
    }
    const decision = await this.capabilityService.preflight(input);
    if (!decision.available) {
      await this.failExecution(input.scope, decision.failureCode, decision.reason);
      return { ...decision, started: false };
    }

    const bufferedEvents: InteractiveProviderEvent[] = [];
    const agentSessionId = `agent_session_${randomUUID().replaceAll("-", "")}`;
    let consumeEvents = false;
    const emit = async (event: InteractiveProviderEvent): Promise<void> => {
      if (!consumeEvents) {
        bufferedEvents.push(event);
        return;
      }
      if (!this.active.has(input.scope.executionId)) return;
      await this.consumeEvent(input.scope, event);
    };
    const handle = await decision.adapter.start({
      ...input,
      agentSessionId,
      capabilities: decision.preflight.capabilities,
      emit,
      protocolVersion: decision.preflight.protocolVersion
    });
    const agentSession = await this.sessionStore.create({
      ...input.scope,
      agentSessionId,
      backend: input.request.agent_backend,
      capabilitySnapshot: decision.preflight.capabilities,
      continuationMode: decision.preflight.capabilities.sameTurnResume
        ? "same_turn"
        : "same_session_new_turn",
      protocolVersion: decision.preflight.protocolVersion,
      policyBindingHash: input.providerContext.authorization.policy_fingerprint,
      providerRunRef: handle.providerRunRef,
      providerSessionRef: handle.providerSessionRef,
      providerTurnRef: handle.providerTurnRef,
      state: "running",
      transport: decision.preflight.transport
    });
    this.active.set(input.scope.executionId, {
      adapter: decision.adapter,
      expiryTimers: new Map(),
      finalResponseText: "",
      finalResponseTruncated: false,
      handle,
      inferredInteractionTypes: [...(input.inferredInteractionTypes ?? [])],
      request: input.request,
      requiredOccurrenceTypes: new Set(input.requiredOccurrenceTypes ?? []),
      scope: input.scope
    });
    await this.eventStore.append({
      ...input.scope,
      occurredAt: new Date(),
      payload: {
        agent_session_id: agentSession.agentSessionId,
        backend: agentSession.backend,
        transport: agentSession.transport
      },
      type: "session_started"
    });
    consumeEvents = true;
    for (const event of bufferedEvents) {
      await this.consumeEvent(input.scope, event);
    }
    return { agentSession, started: true };
  }

  async respond(input: RespondToInteractionInput): Promise<RespondToInteractionResult> {
    const now = input.now ?? new Date();
    const claim = await this.interactionStore.claim({ ...input, now });
    if (claim.outcome === "not_found") return { outcome: "not_found" };
    if (claim.outcome === "replay") return { outcome: "replay" };
    if (claim.outcome === "conflict") return { outcome: "conflict" };
    if (claim.outcome === "expired") {
      await this.failAndTerminate(
        input,
        "AGENT_INTERACTION_EXPIRED",
        "The pending Agent interaction expired before it was resolved."
      );
      return { outcome: "expired" };
    }
    const active = this.active.get(input.executionId);
    if (!active) {
      await this.failExecution(
        input,
        "AGENT_EXECUTION_INTERRUPTED",
        "The provider session is not available to resolve this interaction."
      );
      return { outcome: "conflict" };
    }
    await active.adapter.respond(active.handle, {
      idempotencyKey: input.idempotencyKey,
      interaction: claim.record,
      interactionId: input.interactionId,
      responseSummary: input.responseSummary
    });
    await this.interactionStore.resolve({
      ...input,
      now,
      responseSummary: input.responseSummary
    });
    this.clearInteractionExpiry(input.executionId, input.interactionId);
    await this.eventStore.append({
      ...input,
      interactionId: input.interactionId,
      occurredAt: now,
      payload: { interaction_type: claim.record.type },
      type: "interaction_resolved"
    });
    if (input.responseSummary.decision === "cancel_execution") {
      return { outcome: "resolved" };
    }
    const unresolved = (await this.interactionStore.list(input)).some(
      (interaction) => interaction.state === "pending" || interaction.state === "resolving"
    );
    if (!unresolved) {
      await this.updateSessionState(input, "running");
      await this.executionStore.transition({
        scope: input,
        from: ["waiting_for_interaction"],
        result: stateResult(input.executionId, "running", "Agent execution resumed.")
      });
    }
    return { outcome: "resolved" };
  }

  async cancel(scope: ExecutionScope): Promise<{ cancelled: boolean }> {
    const session = await this.sessionStore.getByExecution(scope);
    const active = this.active.get(scope.executionId);
    if (!session || !active) return { cancelled: false };
    await this.interactionStore.cancelPending(scope, new Date());
    const cancellation = await active.adapter.cancel(active.handle);
    let cancelled = cancellation.cancelled;
    if (!cancelled) {
      const reconciliation = await active.adapter.reconcile(active.handle);
      cancelled = reconciliation.state === "cancelled";
    }
    if (cancelled) {
      if ((await this.executionStore.get(scope))?.status === "cancelled") {
        this.clearActive(scope.executionId);
        return { cancelled: true };
      }
      await this.updateSessionState(scope, "cancelled");
      await this.eventStore.append({
        ...scope,
        occurredAt: new Date(),
        payload: {},
        type: "run_cancelled"
      });
      await this.executionStore.transition({
        scope,
        from: ["ready_for_follow_up", "running", "waiting_for_interaction"],
        result: stateResult(scope.executionId, "cancelled", "Agent execution was cancelled.")
      });
      this.clearActive(scope.executionId);
      return { cancelled: true };
    }
    await this.failExecution(
      scope,
      "AGENT_CANCELLATION_UNCONFIRMED",
      "Provider cancellation could not be confirmed."
    );
    return { cancelled: false };
  }

  async endChatSession(
    scope: ExecutionScope,
    expectedSessionVersion: number
  ): Promise<{ ended: boolean; outcome: "ended" | "not_found" | "stale" | "not_ready" }> {
    const session = await this.sessionStore.getByExecution(scope);
    if (!session) return { ended: false, outcome: "not_found" };
    if (session.sessionVersion !== expectedSessionVersion) return { ended: false, outcome: "stale" };
    if (session.state !== "ready_for_follow_up" || session.activeChatTurnId) {
      return { ended: false, outcome: "not_ready" };
    }
    await this.sessionStore.update(
      { ...scope, agentSessionId: session.agentSessionId },
      { sessionVersion: session.sessionVersion + 1, state: "completed" }
    );
    await this.executionStore.transition({
      scope,
      from: ["ready_for_follow_up"],
      result: stateResult(scope.executionId, "completed", "Agent chat session ended.")
    });
    await this.eventStore.append({
      ...scope,
      occurredAt: new Date(),
      payload: { reason: session.idleExpiresAt && session.idleExpiresAt.getTime() <= Date.now() ? "idle_expired" : "user_ended" },
      type: "chat_session_closed"
    });
    this.clearActive(scope.executionId);
    this.clearIdleExpiry(scope.executionId);
    return { ended: true, outcome: "ended" };
  }

  async shutdown(): Promise<void> {
    const activeSessions = [...this.active.values()];
    await Promise.all(activeSessions.map(async (active) => {
      const session = await this.sessionStore.getByExecution(active.scope);
      if (session?.state === "ready_for_follow_up") {
        this.clearActive(active.scope.executionId);
        return;
      }
      await this.interactionStore.cancelPending(active.scope, new Date());
      await this.failExecution(
        active.scope,
        "AGENT_EXECUTION_INTERRUPTED",
        "Interactive Agent execution stopped during service shutdown."
      );
      try {
        await active.adapter.cancel(active.handle);
      } catch {
        // Provider cleanup is best effort after the durable execution is failed.
      }
    }));
  }

  async reconcileInterrupted(): Promise<number> {
    const interrupted = await this.sessionStore.listNonTerminal();
    for (const session of interrupted) {
      const scope: ExecutionScope = {
        appId: session.appId,
        executionId: session.executionId,
        sessionId: session.sessionId
      };
      const now = new Date();
      if (session.state === "ready_for_follow_up" && session.capabilitySnapshot.chatLevelInteraction) {
        const restored = await this.restoreIdleSession(session);
        if (restored) {
          if (session.idleExpiresAt) {
            this.scheduleIdleExpiry(scope, session.sessionVersion, session.idleExpiresAt);
          }
          continue;
        }
      }
      await this.interactionStore.cancelPending(scope, now);
      await this.sessionStore.update(
        { ...scope, agentSessionId: session.agentSessionId },
        { state: "failed" }
      );
      await this.eventStore.append({
        ...scope,
        occurredAt: now,
        payload: {
          code: "AGENT_EXECUTION_INTERRUPTED",
          message: "Interactive Agent execution was interrupted by a service restart."
        },
        type: "error"
      });
      await this.executionStore.transition({
        scope,
        from: ["running", "waiting_for_interaction"],
        result: {
          ...stateResult(
            scope.executionId,
            "failed",
            "Interactive Agent execution was interrupted by a service restart."
          ),
          errors: [{
            code: "AGENT_EXECUTION_INTERRUPTED",
            message: "Interactive Agent execution was interrupted by a service restart.",
            recoverable: true,
            suggested_action: "Retry the Agent execution. No prior response was replayed."
          }]
        }
      });
    }
    return interrupted.length;
  }

  private async consumeEvent(
    scope: ExecutionScope,
    event: InteractiveProviderEvent
  ): Promise<void> {
    if (
      !PROVIDER_EVENT_TYPES.has(event.type) ||
      serializedBytes(event.payload) > MAX_NORMALIZED_PROVIDER_EVENT_BYTES
    ) {
      await this.failAndTerminate(
        scope,
        "INVALID_PROVIDER_EVENT",
        "The provider emitted an unsupported or oversized event."
      );
      return;
    }
    const activeSession = this.active.get(scope.executionId);
    if (event.type === "message_delta" && activeSession) {
      appendFinalResponse(activeSession, event.payload.delta);
    }
    if (event.type === "interaction_requested") {
      if (!event.interaction) {
        await this.failAndTerminate(
          scope,
          "INVALID_PROVIDER_INTERACTION",
          "The provider emitted an interaction event without a typed interaction."
        );
        return;
      }
      const parsedInteraction = providerInteractionRequestSchema.safeParse(
        event.interaction
      );
      if (!parsedInteraction.success) {
        await this.failAndTerminate(
          scope,
          "INVALID_PROVIDER_INTERACTION",
          "The provider interaction exceeded the supported schema bounds."
        );
        return;
      }
      const { presentation, ...interactionData } = parsedInteraction.data;
      const interaction = await this.interactionStore.create({
        ...scope,
        agentSessionId: (await this.requireSession(scope)).agentSessionId,
        ...interactionData,
        ...(presentation !== undefined
          ? { presentation }
          : {}),
        options: parsedInteraction.data.options.map((option) => ({
          id: option.id,
          label: option.label,
          ...(option.description ? { description: option.description } : {})
        }))
      });
      if (activeSession) {
        activeSession.finalResponseText = "";
        activeSession.finalResponseTruncated = false;
      }
      this.active.get(scope.executionId)?.requiredOccurrenceTypes.delete(interaction.type);
      this.scheduleInteractionExpiry(scope, interaction.interactionId, interaction.expiresAt);
      await this.eventStore.append({
        ...scope,
        interactionId: interaction.interactionId,
        occurredAt: event.occurredAt ?? new Date(),
        payload: {
          ...event.payload,
          interaction_type: interaction.type
        },
        ...(event.providerEventRef ? { providerEventRef: event.providerEventRef } : {}),
        type: event.type
      });
      await this.updateSessionState(scope, "waiting_for_interaction");
      await this.executionStore.transition({
        scope,
        from: ["running"],
        result: stateResult(
          scope.executionId,
          "waiting_for_interaction",
          "Agent execution is waiting for a user interaction."
        )
      });
      return;
    }

    await this.eventStore.append({
      ...scope,
      occurredAt: event.occurredAt ?? new Date(),
      payload: event.payload,
      ...(event.providerEventRef ? { providerEventRef: event.providerEventRef } : {}),
      type: event.type
    });
    if (event.type === "run_completed") {
      const status = terminalStatus(event.payload.status);
      const pendingInteractions = (await this.interactionStore.list(scope)).filter(
        (interaction) => interaction.state === "pending"
      );
      if (status === "completed" && pendingInteractions.length > 0) {
        await this.failAndTerminate(
          scope,
          "PROVIDER_COMPLETED_WITH_PENDING_INTERACTION",
          "The Agent provider completed while user input was still pending."
        );
        return;
      }
      const missingRequiredInteractions = [
        ...(this.active.get(scope.executionId)?.requiredOccurrenceTypes ?? [])
      ];
      if (status === "completed" && missingRequiredInteractions.length > 0) {
        await this.failAndTerminate(
          scope,
          "REQUIRED_INTERACTION_NOT_OBSERVED",
          `The Agent completed without requesting required interaction types: ${missingRequiredInteractions.join(", ")}.`
        );
        return;
      }
      const session = await this.requireSession(scope);
      if (status === "completed" && session.capabilitySnapshot.chatLevelInteraction) {
        const activeTurnId = session.activeChatTurnId;
        if (activeTurnId && this.chatTurnStore) {
          await this.chatTurnStore.update(scope, activeTurnId, {
            acknowledgementState: "acknowledged",
            completedAt: new Date(),
            normalizedResult: { ...event.payload },
            state: "completed"
          });
        }
        const idleExpiresAt = new Date(Date.now() + this.idleTtlMs);
        await this.sessionStore.update(
          { ...scope, agentSessionId: session.agentSessionId },
          { activeChatTurnId: null, idleExpiresAt, state: "ready_for_follow_up" }
        );
        await this.executionStore.transition({
          scope,
          from: ["running", "waiting_for_interaction"],
          result: {
            ...stateResult(scope.executionId, "ready_for_follow_up", summary(event.payload)),
            result: { ...event.payload }
          }
        });
        this.scheduleIdleExpiry(scope, session.sessionVersion, idleExpiresAt);
        return;
      }
      const outputText = activeSession?.finalResponseText.trim() ?? "";
      const persistenceOutputs = activeSession
        ? planAgentExpectedOutputs({ request: activeSession.request }).filter((output) =>
            output.persist_as_artifact === true &&
            output.required !== true &&
            output.artifact_type === "agent_output"
          )
        : [];
      const artifacts: PersistedAgentOutputArtifact[] = [];
      if (status === "completed" && persistenceOutputs.length > 0) {
        if (!outputText || !this.persistFinalResponse) {
          await this.failExecution(
            scope,
            !outputText ? "AGENT_OUTPUT_EMPTY" : "AGENT_OUTPUT_PERSISTENCE_UNAVAILABLE",
            !outputText
              ? "The interactive Agent completed without a final response to save."
              : "Interactive Agent output persistence is unavailable."
          );
          return;
        }
        try {
          for (const output of persistenceOutputs) {
            artifacts.push(await this.persistFinalResponse({
              executionId: scope.executionId,
              output,
              request: activeSession!.request,
              text: outputText
            }));
          }
        } catch (error) {
          await this.failExecution(
            scope,
            "AGENT_OUTPUT_PERSIST_FAILED",
            error instanceof Error ? error.message : "Interactive Agent output persistence failed."
          );
          return;
        }
      }
      await this.updateSessionState(scope, status === "failed" ? "failed" : "completed");
      await this.executionStore.transition({
        scope,
        from: ["running", "waiting_for_interaction"],
        result: {
          ...stateResult(scope.executionId, status, summary(event.payload)),
          result: {
            ...event.payload,
            output_text: outputText,
            ...(activeSession?.finalResponseTruncated
              ? { output_text_truncated: true }
              : {}),
            artifacts,
            ...(activeSession?.inferredInteractionTypes.length
              ? {
                  interaction_requirements: {
                    inferred_types: activeSession.inferredInteractionTypes
                  }
                }
              : {})
          }
        }
      });
      this.clearActive(scope.executionId);
    } else if (event.type === "run_cancelled") {
      await this.updateSessionState(scope, "cancelled");
      await this.executionStore.transition({
        scope,
        from: ["running", "waiting_for_interaction"],
        result: stateResult(scope.executionId, "cancelled", "Agent execution was cancelled.")
      });
      this.clearActive(scope.executionId);
    }
  }

  private async failExecution(scope: ExecutionScope, code: string, message: string): Promise<void> {
    const session = await this.sessionStore.getByExecution(scope);
    if (session) await this.updateSessionState(scope, "failed");
    await this.executionStore.transition({
      scope,
      from: ["ready_for_follow_up", "running", "waiting_for_interaction"],
      result: {
        ...stateResult(scope.executionId, "failed", message),
        errors: [{
          code,
          message,
          recoverable: true,
          suggested_action: "Inspect interactive execution diagnostics and retry."
        }]
      }
    });
    this.clearActive(scope.executionId);
  }

  private async failAndTerminate(
    scope: ExecutionScope,
    code: string,
    message: string
  ): Promise<void> {
    const active = this.active.get(scope.executionId);
    await this.interactionStore.cancelPending(scope, new Date());
    await this.failExecution(scope, code, message);
    if (!active) return;
    try {
      await active.adapter.cancel(active.handle);
    } catch {
      // The durable failed state is authoritative when provider cleanup also fails.
    }
  }

  private scheduleInteractionExpiry(
    scope: ExecutionScope,
    interactionId: string,
    expiresAt: Date
  ): void {
    const active = this.active.get(scope.executionId);
    if (!active) return;
    this.clearInteractionExpiry(scope.executionId, interactionId);
    const timer = setTimeout(() => {
      void this.expireInteraction(scope, interactionId);
    }, Math.max(0, expiresAt.getTime() - Date.now()));
    timer.unref();
    active.expiryTimers.set(interactionId, timer);
  }

  private async expireInteraction(scope: ExecutionScope, interactionId: string): Promise<void> {
    this.clearInteractionExpiry(scope.executionId, interactionId);
    const interaction = (await this.interactionStore.list(scope)).find(
      (candidate) => candidate.interactionId === interactionId
    );
    if (!interaction || interaction.state !== "pending") return;
    await this.failAndTerminate(
      scope,
      "AGENT_INTERACTION_EXPIRED",
      "The pending Agent interaction expired before it was resolved."
    );
  }

  private clearInteractionExpiry(executionId: string, interactionId: string): void {
    const active = this.active.get(executionId);
    const timer = active?.expiryTimers.get(interactionId);
    if (timer) clearTimeout(timer);
    active?.expiryTimers.delete(interactionId);
  }

  private clearActive(executionId: string): void {
    const active = this.active.get(executionId);
    for (const timer of active?.expiryTimers.values() ?? []) clearTimeout(timer);
    this.active.delete(executionId);
  }

  private scheduleIdleExpiry(
    scope: ExecutionScope,
    sessionVersion: number,
    idleExpiresAt: Date
  ): void {
    this.clearIdleExpiry(scope.executionId);
    const timer = setTimeout(() => {
      void this.endChatSession(scope, sessionVersion);
    }, Math.max(0, idleExpiresAt.getTime() - Date.now()));
    timer.unref();
    this.idleTimers.set(scope.executionId, timer);
  }

  private clearIdleExpiry(executionId: string): void {
    const timer = this.idleTimers.get(executionId);
    if (timer) clearTimeout(timer);
    this.idleTimers.delete(executionId);
  }

  private async requireSession(scope: ExecutionScope): Promise<AgentSessionRecord> {
    const session = await this.sessionStore.getByExecution(scope);
    if (!session) throw new Error("Interactive Agent session was not persisted.");
    return session;
  }

  private async restoreIdleSession(session: AgentSessionRecord): Promise<ActiveProviderSession | null> {
    if (session.state !== "ready_for_follow_up" || !session.policyBindingHash) return null;
    const adapter = this.capabilityService.adapterFor(session.backend);
    if (!adapter?.restore) return null;
    const scope = { appId: session.appId, executionId: session.executionId, sessionId: session.sessionId };
    const emit = async (event: InteractiveProviderEvent): Promise<void> => {
      if (!this.active.has(scope.executionId)) return;
      await this.consumeEvent(scope, event);
    };
    try {
      const request = await this.executionStore.getRequest(scope);
      if (!request || request.request_type !== "execute_agent") return null;
      const handle = await adapter.restore(session, emit);
      const restored = {
        adapter,
        expiryTimers: new Map(),
        finalResponseText: "",
        finalResponseTruncated: false,
        handle,
        inferredInteractionTypes: [],
        request,
        requiredOccurrenceTypes: new Set<AgentInteractionType>(),
        scope
      };
      this.active.set(scope.executionId, restored);
      return restored;
    } catch {
      return null;
    }
  }

  private async updateSessionState(
    scope: ExecutionScope,
    state: AgentSessionRecord["state"]
  ): Promise<void> {
    const session = await this.requireSession(scope);
    await this.sessionStore.update(
      { ...scope, agentSessionId: session.agentSessionId },
      { state }
    );
  }
}

function appendFinalResponse(
  active: Pick<ActiveProviderSession, "finalResponseText" | "finalResponseTruncated">,
  value: unknown
): void {
  if (typeof value !== "string" || value.length === 0) return;
  const bytes = Buffer.from(`${active.finalResponseText}${value}`, "utf8");
  if (bytes.byteLength <= MAX_FINAL_RESPONSE_BYTES) {
    active.finalResponseText = bytes.toString("utf8");
    return;
  }
  active.finalResponseText = bytes
    .subarray(bytes.byteLength - MAX_FINAL_RESPONSE_BYTES)
    .toString("utf8");
  active.finalResponseTruncated = true;
}


function followUpMessage(input: AgentChatFollowUpInput): string {
  if (input.kind === "continue") return input.text?.trim() || "Continue with the current task.";
  if (input.kind === "graceful_cancel") return "Stop remaining work and summarize what has been completed.";
  const text = input.text?.trim();
  if (!text) throw new Error(`${input.kind} requires text.`);
  return text;
}

function requiresNewExecution(text: string): boolean {
  return /\b(?:publish|upload|install|bind|switch\s+skills?|use\s+(?:a\s+)?different\s+skill|add\s+(?:a\s+)?new\s+artifact|delete\s+(?:the\s+)?file|move\s+(?:the\s+)?file|send\b.{0,80}\bto\b)\b/i.test(text);
}

function serializedBytes(value: Record<string, unknown>): number {
  try {
    return Buffer.byteLength(JSON.stringify(value), "utf8");
  } catch {
    return Number.POSITIVE_INFINITY;
  }
}

function terminalStatus(value: unknown): "completed" | "failed" | "partial" {
  return value === "failed" || value === "partial" ? value : "completed";
}

function summary(payload: Record<string, unknown>): string {
  return typeof payload.summary === "string" && payload.summary.trim()
    ? payload.summary
    : "Interactive Agent execution completed."
}

function stateResult(
  executionId: string,
  status: NormalizedExecutionResult["status"],
  logsSummary: string
): NormalizedExecutionResult {
  return {
    execution_id: executionId,
    status,
    result_type: "json",
    result: {},
    files: [],
    errors: [],
    logs_summary: logsSummary
  };
}
