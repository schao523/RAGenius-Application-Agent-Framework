export type AgentBackend = "codex_cli" | "openclaw_cli";

export type AgentTransport = "codex_app_server" | "openclaw_gateway";

export type AgentSessionState =
  | "starting"
  | "running"
  | "waiting_for_interaction"
  | "completed"
  | "failed"
  | "cancelled";

export type AgentInteractionType =
  | "approval"
  | "clarification"
  | "selection"
  | "authentication_handoff"
  | "user_action_required";

export type AgentInteractionState =
  | "pending"
  | "resolving"
  | "resolved"
  | "expired"
  | "cancelled";

export type AgentExecutionEventType =
  | "session_started"
  | "run_started"
  | "progress"
  | "message_delta"
  | "message_completed"
  | "tool_started"
  | "tool_completed"
  | "interaction_requested"
  | "interaction_resolved"
  | "warning"
  | "error"
  | "run_completed"
  | "run_cancelled";

export interface ExecutionScope {
  appId: string;
  executionId: string;
  sessionId: string;
}

export interface AgentInteractionCapabilities {
  cancellation: boolean;
  eventReplay: "none" | "bounded" | "documented";
  interactionTypes: AgentInteractionType[];
  protocolTransport: boolean;
  reconnectReconciliation: boolean;
  sameSessionContinuation: boolean;
  sameTurnResume: boolean;
}

export interface AgentSessionRecord extends ExecutionScope {
  agentSessionId: string;
  backend: AgentBackend;
  capabilitySnapshot: AgentInteractionCapabilities;
  continuationMode: "same_turn" | "same_session_new_turn";
  createdAt: Date;
  lastEventSeq: number;
  protocolVersion: string;
  providerRunRef: string | null;
  providerSessionRef: string;
  providerTurnRef: string | null;
  state: AgentSessionState;
  transport: AgentTransport;
  updatedAt: Date;
}

export interface AgentInteractionOption {
  description?: string;
  id: string;
  label: string;
}

export interface AgentInteractionRecord extends ExecutionScope {
  agentSessionId: string;
  allowsFreeText: boolean;
  createdAt: Date;
  expiresAt: Date;
  interactionId: string;
  options: AgentInteractionOption[];
  policyBindingHash: string;
  prompt: string;
  providerCorrelationRef: string;
  resolvedAt: Date | null;
  responseSummary: Record<string, unknown> | null;
  secretInput: false;
  sequence: number;
  state: AgentInteractionState;
  type: AgentInteractionType;
  updatedAt: Date;
  version: number;
}

export interface AgentExecutionEvent extends ExecutionScope {
  interactionId?: string;
  occurredAt: Date;
  payload: Record<string, unknown>;
  providerEventRef?: string;
  sequence: number;
  type: AgentExecutionEventType;
}
