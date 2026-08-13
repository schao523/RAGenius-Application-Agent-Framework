import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";
import type { AgentPolicyDecision } from "../agents/agent-policy.js";
import type { AgentProviderExecutionContext } from "../agents/agent-provider-context.js";

import type {
  AgentBackend,
  AgentInteractionCapabilities,
  AgentInteractionOption,
  AgentInteractionRecord,
  AgentInteractionType,
  AgentSessionState,
  AgentTransport,
  ExecutionScope
} from "./interactive-agent-types.js";

export interface InteractivePreflightInput {
  policy: AgentPolicyDecision;
  providerContext: AgentProviderExecutionContext;
  request: ExecuteAgentRequest;
  requiredInteractionTypes: AgentInteractionType[];
  scope: ExecutionScope;
}

export interface InteractivePreflightResult {
  available: boolean;
  capabilities: AgentInteractionCapabilities;
  protocolVersion: string;
  reason?: string;
  transport: AgentTransport;
}

export interface ProviderSessionHandle {
  providerRunRef: string | null;
  providerSessionRef: string;
  providerTurnRef: string | null;
  protectedHandle: unknown;
}

export interface ProviderInteractionRequest {
  allowsFreeText: boolean;
  expiresAt: Date;
  interactionId: string;
  options: AgentInteractionOption[];
  policyBindingHash: string;
  prompt: string;
  providerCorrelationRef: string;
  type: AgentInteractionType;
}

export type InteractiveProviderEvent = {
  interaction?: ProviderInteractionRequest;
  occurredAt?: Date;
  payload: Record<string, unknown>;
  providerEventRef?: string;
  type:
    | "run_started"
    | "progress"
    | "message_delta"
    | "message_completed"
    | "tool_started"
    | "tool_completed"
    | "interaction_requested"
    | "warning"
    | "error"
    | "run_completed"
    | "run_cancelled";
};

export interface InteractiveStartInput extends InteractivePreflightInput {
  agentSessionId: string;
  capabilities: AgentInteractionCapabilities;
  emit(event: InteractiveProviderEvent): Promise<void>;
  protocolVersion: string;
}

export interface ClaimedInteraction {
  idempotencyKey: string;
  interaction: AgentInteractionRecord;
  interactionId: string;
  responseSummary: Record<string, unknown>;
}

export interface ProviderCancellationResult {
  cancelled: boolean;
  diagnostics?: Record<string, unknown>;
}

export interface ProviderReconciliationResult {
  state: AgentSessionState;
  diagnostics?: Record<string, unknown>;
}

export interface InteractiveAgentAdapter {
  readonly backend: AgentBackend;
  preflight(input: InteractivePreflightInput): Promise<InteractivePreflightResult>;
  start(input: InteractiveStartInput): Promise<ProviderSessionHandle>;
  respond(handle: ProviderSessionHandle, claim: ClaimedInteraction): Promise<void>;
  cancel(handle: ProviderSessionHandle): Promise<ProviderCancellationResult>;
  reconcile(handle: ProviderSessionHandle): Promise<ProviderReconciliationResult>;
}
