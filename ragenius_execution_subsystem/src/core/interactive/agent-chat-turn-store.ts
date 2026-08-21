import { randomUUID } from "node:crypto";

import type { AgentSessionStore } from "./agent-session-store.js";
import type {
  AgentChatFollowUpKind,
  AgentChatTurnRecord,
  ExecutionScope
} from "./interactive-agent-types.js";

export interface ClaimAgentChatTurnInput extends ExecutionScope {
  agentSessionId: string;
  expectedSessionVersion: number;
  idempotencyKey: string;
  kind: AgentChatFollowUpKind;
  now: Date;
  requestSummary: Record<string, unknown>;
}

export type AgentChatTurnClaimResult = {
  outcome: "claimed" | "replay" | "active" | "stale" | "not_ready" | "not_found";
  record?: AgentChatTurnRecord;
};

export interface AgentChatTurnStore {
  claim(input: ClaimAgentChatTurnInput): Promise<AgentChatTurnClaimResult>;
  getByIdempotency(scope: ExecutionScope, idempotencyKey: string): Promise<AgentChatTurnRecord | null>;
  list(scope: ExecutionScope): Promise<AgentChatTurnRecord[]>;
  update(
    scope: ExecutionScope,
    chatTurnId: string,
    input: Partial<Pick<AgentChatTurnRecord,
      "acknowledgementState" | "completedAt" | "normalizedResult" | "providerRunRef" | "state">>
  ): Promise<AgentChatTurnRecord | null>;
}

export class InMemoryAgentChatTurnStore implements AgentChatTurnStore {
  private readonly records = new Map<string, AgentChatTurnRecord>();

  constructor(private readonly sessions: AgentSessionStore) {}

  async claim(input: ClaimAgentChatTurnInput): Promise<AgentChatTurnClaimResult> {
    const replay = await this.getByIdempotency(input, input.idempotencyKey);
    if (replay) return { outcome: "replay", record: replay };
    const session = await this.sessions.get({ ...input, agentSessionId: input.agentSessionId });
    if (!session) return { outcome: "not_found" };
    if (session.state !== "ready_for_follow_up") {
      return { outcome: session.activeChatTurnId ? "active" : "not_ready" };
    }
    if (session.sessionVersion !== input.expectedSessionVersion) return { outcome: "stale" };
    const chatTurnId = `agent_chat_turn_${randomUUID().replaceAll("-", "")}`;
    const sequence = session.turnSequence + 1;
    const updated = await this.sessions.update(
      { ...input, agentSessionId: input.agentSessionId },
      {
        activeChatTurnId: chatTurnId,
        sessionVersion: session.sessionVersion + 1,
        state: "running",
        turnSequence: sequence
      }
    );
    if (!updated) return { outcome: "not_found" };
    const record: AgentChatTurnRecord = {
      ...input,
      acknowledgementState: "unacknowledged",
      chatTurnId,
      completedAt: null,
      createdAt: input.now,
      normalizedResult: null,
      providerRunRef: null,
      sequence,
      state: "claimed",
      updatedAt: input.now
    };
    this.records.set(chatTurnId, record);
    return { outcome: "claimed", record: clone(record) };
  }

  async getByIdempotency(scope: ExecutionScope, idempotencyKey: string): Promise<AgentChatTurnRecord | null> {
    const record = [...this.records.values()].find((candidate) =>
      candidate.appId === scope.appId &&
      candidate.executionId === scope.executionId &&
      candidate.sessionId === scope.sessionId &&
      candidate.idempotencyKey === idempotencyKey
    );
    return record ? clone(record) : null;
  }

  async list(scope: ExecutionScope): Promise<AgentChatTurnRecord[]> {
    return [...this.records.values()]
      .filter((record) => record.appId === scope.appId && record.executionId === scope.executionId && record.sessionId === scope.sessionId)
      .sort((left, right) => left.sequence - right.sequence)
      .map(clone);
  }

  async update(
    scope: ExecutionScope,
    chatTurnId: string,
    input: Partial<Pick<AgentChatTurnRecord,
      "acknowledgementState" | "completedAt" | "normalizedResult" | "providerRunRef" | "state">>
  ): Promise<AgentChatTurnRecord | null> {
    const current = this.records.get(chatTurnId);
    if (!current || current.appId !== scope.appId || current.executionId !== scope.executionId || current.sessionId !== scope.sessionId) {
      return null;
    }
    const updated = { ...current, ...input, updatedAt: new Date() };
    this.records.set(chatTurnId, updated);
    return clone(updated);
  }
}

function clone(record: AgentChatTurnRecord): AgentChatTurnRecord {
  return {
    ...record,
    normalizedResult: record.normalizedResult ? { ...record.normalizedResult } : null,
    requestSummary: { ...record.requestSummary }
  };
}
