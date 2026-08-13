import { randomUUID } from "node:crypto";

import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";
import type { NormalizedExecutionResult } from "../../api/schemas/common-response.schema.js";
import type { AgentPolicyDecision } from "../agents/agent-policy.js";
import type { AgentProviderExecutionContext } from "../agents/agent-provider-context.js";
import type { ExecutionStore } from "../execution/execution-store.js";

import type { AgentEventStore } from "./agent-event-store.js";
import type { AgentInteractionStore } from "./agent-interaction-store.js";
import type { AgentSessionStore } from "./agent-session-store.js";
import type {
  InteractiveAgentAdapter,
  InteractiveProviderEvent,
  ProviderSessionHandle
} from "./interactive-agent-adapter.js";
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
  requiredInteractionTypes: AgentInteractionType[];
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

interface ActiveProviderSession {
  adapter: InteractiveAgentAdapter;
  handle: ProviderSessionHandle;
}

export class InteractiveAgentSessionManager {
  private readonly capabilityService: InteractiveCapabilityService;
  private readonly eventStore: AgentEventStore;
  private readonly executionStore: ExecutionStore;
  private readonly interactionStore: AgentInteractionStore;
  private readonly sessionStore: AgentSessionStore;
  private readonly active = new Map<string, ActiveProviderSession>();

  constructor(options: {
    capabilityService: InteractiveCapabilityService;
    eventStore: AgentEventStore;
    executionStore: ExecutionStore;
    interactionStore: AgentInteractionStore;
    sessionStore: AgentSessionStore;
  }) {
    this.capabilityService = options.capabilityService;
    this.eventStore = options.eventStore;
    this.executionStore = options.executionStore;
    this.interactionStore = options.interactionStore;
    this.sessionStore = options.sessionStore;
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
    let consumeEvents = false;
    const emit = async (event: InteractiveProviderEvent): Promise<void> => {
      if (!consumeEvents) {
        bufferedEvents.push(event);
        return;
      }
      await this.consumeEvent(input.scope, event);
    };
    const handle = await decision.adapter.start({
      ...input,
      capabilities: decision.preflight.capabilities,
      emit,
      protocolVersion: decision.preflight.protocolVersion
    });
    const agentSession = await this.sessionStore.create({
      ...input.scope,
      agentSessionId: `agent_session_${randomUUID().replaceAll("-", "")}`,
      backend: input.request.agent_backend,
      capabilitySnapshot: decision.preflight.capabilities,
      continuationMode: decision.preflight.capabilities.sameTurnResume
        ? "same_turn"
        : "same_session_new_turn",
      protocolVersion: decision.preflight.protocolVersion,
      providerRunRef: handle.providerRunRef,
      providerSessionRef: handle.providerSessionRef,
      providerTurnRef: handle.providerTurnRef,
      state: "running",
      transport: decision.preflight.transport
    });
    this.active.set(input.scope.executionId, {
      adapter: decision.adapter,
      handle
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
      await this.failExecution(
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
    await this.eventStore.append({
      ...input,
      interactionId: input.interactionId,
      occurredAt: now,
      payload: { interaction_type: claim.record.type },
      type: "interaction_resolved"
    });
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
      await this.updateSessionState(scope, "cancelled");
      await this.eventStore.append({
        ...scope,
        occurredAt: new Date(),
        payload: {},
        type: "run_cancelled"
      });
      await this.executionStore.transition({
        scope,
        from: ["running", "waiting_for_interaction"],
        result: stateResult(scope.executionId, "cancelled", "Agent execution was cancelled.")
      });
      this.active.delete(scope.executionId);
      return { cancelled: true };
    }
    await this.failExecution(
      scope,
      "AGENT_CANCELLATION_UNCONFIRMED",
      "Provider cancellation could not be confirmed."
    );
    return { cancelled: false };
  }

  private async consumeEvent(
    scope: ExecutionScope,
    event: InteractiveProviderEvent
  ): Promise<void> {
    if (event.type === "interaction_requested") {
      if (!event.interaction) {
        await this.failExecution(
          scope,
          "INVALID_PROVIDER_INTERACTION",
          "The provider emitted an interaction event without a typed interaction."
        );
        return;
      }
      const interaction = await this.interactionStore.create({
        ...scope,
        agentSessionId: (await this.requireSession(scope)).agentSessionId,
        ...event.interaction
      });
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
      await this.updateSessionState(scope, status === "failed" ? "failed" : "completed");
      await this.executionStore.transition({
        scope,
        from: ["running", "waiting_for_interaction"],
        result: {
          ...stateResult(scope.executionId, status, summary(event.payload)),
          result: { ...event.payload }
        }
      });
      this.active.delete(scope.executionId);
    } else if (event.type === "run_cancelled") {
      await this.updateSessionState(scope, "cancelled");
      await this.executionStore.transition({
        scope,
        from: ["running", "waiting_for_interaction"],
        result: stateResult(scope.executionId, "cancelled", "Agent execution was cancelled.")
      });
      this.active.delete(scope.executionId);
    }
  }

  private async failExecution(scope: ExecutionScope, code: string, message: string): Promise<void> {
    const session = await this.sessionStore.getByExecution(scope);
    if (session) await this.updateSessionState(scope, "failed");
    await this.executionStore.transition({
      scope,
      from: ["running", "waiting_for_interaction"],
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
    this.active.delete(scope.executionId);
  }

  private async requireSession(scope: ExecutionScope): Promise<AgentSessionRecord> {
    const session = await this.sessionStore.getByExecution(scope);
    if (!session) throw new Error("Interactive Agent session was not persisted.");
    return session;
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
