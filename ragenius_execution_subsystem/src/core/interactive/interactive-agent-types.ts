export type AgentBackend = "codex_cli" | "openclaw_cli";

export type AgentTransport = "codex_app_server" | "openclaw_gateway";

export type AgentSessionState =
  | "starting"
  | "running"
  | "waiting_for_interaction"
  | "ready_for_follow_up"
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
  | "run_cancelled"
  | "chat_follow_up_claimed"
  | "chat_follow_up_acknowledged"
  | "chat_follow_up_delivery_unknown"
  | "chat_session_closed";

export interface ExecutionScope {
  appId: string;
  executionId: string;
  sessionId: string;
}

export interface AgentInteractionCapabilities {
  chatLevelInteraction?: boolean;
  cancellation: boolean;
  eventReplay: "none" | "bounded" | "documented";
  exactlyOnceFollowUp?: boolean;
  interactionTypes: AgentInteractionType[];
  protocolTransport: boolean;
  reconnectReconciliation: boolean;
  sameSessionContinuation: boolean;
  sameTurnResume: boolean;
  structuredWaitSignal?: boolean;
}

export interface AgentSessionRecord extends ExecutionScope {
  activeChatTurnId: string | null;
  agentSessionId: string;
  backend: AgentBackend;
  capabilitySnapshot: AgentInteractionCapabilities;
  continuationMode: "same_turn" | "same_session_new_turn";
  createdAt: Date;
  idleExpiresAt: Date | null;
  lastEventSeq: number;
  protocolVersion: string;
  policyBindingHash: string;
  providerRunRef: string | null;
  providerSessionRef: string;
  providerTurnRef: string | null;
  sessionVersion: number;
  state: AgentSessionState;
  transport: AgentTransport;
  turnSequence: number;
  updatedAt: Date;
}

export type AgentChatFollowUpKind = "reply" | "continue" | "revise" | "graceful_cancel";
export type AgentChatTurnState =
  | "claimed"
  | "submitted"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "delivery_unknown";

export interface AgentChatTurnRecord extends ExecutionScope {
  acknowledgementState: "unacknowledged" | "acknowledged" | "ambiguous";
  agentSessionId: string;
  chatTurnId: string;
  completedAt: Date | null;
  createdAt: Date;
  idempotencyKey: string;
  kind: AgentChatFollowUpKind;
  normalizedResult: Record<string, unknown> | null;
  providerRunRef: string | null;
  requestSummary: Record<string, unknown>;
  sequence: number;
  state: AgentChatTurnState;
  updatedAt: Date;
}

export interface AgentInteractionOption {
  description?: string;
  id: string;
  label: string;
}

export interface AgentInteractionPresentation {
  completionLabel?: string | undefined;
  launchAvailable?: boolean | undefined;
  targetHost?: string | undefined;
  targetLabel?: string | undefined;
}

export interface AgentInteractionRecord extends ExecutionScope {
  agentSessionId: string;
  allowsFreeText: boolean;
  createdAt: Date;
  expiresAt: Date;
  interactionId: string;
  options: AgentInteractionOption[];
  presentation?: AgentInteractionPresentation | null;
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
