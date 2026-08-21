import type {
  AgentChatTurnClaimResult,
  AgentChatTurnStore,
  ClaimAgentChatTurnInput
} from "./agent-chat-turn-store.js";
import type { AgentChatTurnRecord, ExecutionScope } from "./interactive-agent-types.js";

interface AgentChatTurnRow {
  acknowledgementState: string;
  agentSessionId: string;
  appId: string;
  completedAt: Date | null;
  createdAt: Date;
  executionId: string;
  id: string;
  idempotencyKey: string;
  kind: string;
  normalizedResult: unknown;
  providerRunRef: string | null;
  requestSummary: unknown;
  sequence: number;
  sessionId: string;
  state: string;
  updatedAt: Date;
}

interface AgentSessionClaimRow {
  activeChatTurnId: string | null;
  id: string;
  sessionVersion: number;
  state: string;
  turnSequence: number;
}

interface AgentChatTurnTransaction {
  agentChatTurn: {
    create(args: { data: Record<string, unknown> }): Promise<AgentChatTurnRow>;
    findFirst(args: { where: Record<string, unknown> }): Promise<AgentChatTurnRow | null>;
    findMany(args: { orderBy: Record<string, unknown>; where: Record<string, unknown> }): Promise<AgentChatTurnRow[]>;
  };
  agentSession: {
    findFirst(args: { where: Record<string, unknown> }): Promise<AgentSessionClaimRow | null>;
    updateMany(args: { data: Record<string, unknown>; where: Record<string, unknown> }): Promise<{ count: number }>;
  };
}

export interface AgentChatTurnPrismaClient extends AgentChatTurnTransaction {
  $transaction<T>(callback: (transaction: AgentChatTurnTransaction) => Promise<T>): Promise<T>;
}

export class PrismaAgentChatTurnStore implements AgentChatTurnStore {
  constructor(private readonly prisma: AgentChatTurnPrismaClient) {}

  async claim(input: ClaimAgentChatTurnInput): Promise<AgentChatTurnClaimResult> {
    return this.prisma.$transaction(async (tx) => {
      const where = scopeWhere(input);
      const replay = await tx.agentChatTurn.findFirst({
        where: { ...where, agentSessionId: input.agentSessionId, idempotencyKey: input.idempotencyKey }
      });
      if (replay) return { outcome: "replay", record: toRecord(replay) };
      const session = await tx.agentSession.findFirst({
        where: { ...where, id: input.agentSessionId }
      });
      if (!session) return { outcome: "not_found" };
      if (session.state !== "ready_for_follow_up") {
        return { outcome: session.activeChatTurnId ? "active" : "not_ready" };
      }
      if (session.sessionVersion !== input.expectedSessionVersion) return { outcome: "stale" };
      const chatTurnId = `agent_chat_turn_${randomUUID().replaceAll("-", "")}`;
      const sequence = session.turnSequence + 1;
      const claimed = await tx.agentSession.updateMany({
        where: {
          ...where,
          activeChatTurnId: null,
          id: input.agentSessionId,
          sessionVersion: input.expectedSessionVersion,
          state: "ready_for_follow_up"
        },
        data: {
          activeChatTurnId: chatTurnId,
          sessionVersion: { increment: 1 },
          state: "running",
          turnSequence: { increment: 1 }
        }
      });
      if (claimed.count !== 1) return { outcome: "active" };
      const row = await tx.agentChatTurn.create({
        data: {
          acknowledgementState: "unacknowledged",
          agentSessionId: input.agentSessionId,
          appId: input.appId,
          executionId: input.executionId,
          id: chatTurnId,
          idempotencyKey: input.idempotencyKey,
          kind: input.kind,
          requestSummary: input.requestSummary,
          sequence,
          sessionId: input.sessionId,
          state: "claimed"
        }
      });
      return { outcome: "claimed", record: toRecord(row) };
    });
  }

  async getByIdempotency(scope: ExecutionScope, idempotencyKey: string): Promise<AgentChatTurnRecord | null> {
    const row = await this.prisma.agentChatTurn.findFirst({ where: { ...scopeWhere(scope), idempotencyKey } });
    return row ? toRecord(row) : null;
  }

  async list(scope: ExecutionScope): Promise<AgentChatTurnRecord[]> {
    const rows = await this.prisma.agentChatTurn.findMany({
      where: scopeWhere(scope),
      orderBy: { sequence: "asc" }
    });
    return rows.map(toRecord);
  }
}

function scopeWhere(scope: ExecutionScope): Record<string, unknown> {
  return { appId: scope.appId, executionId: scope.executionId, sessionId: scope.sessionId };
}

function toRecord(row: AgentChatTurnRow): AgentChatTurnRecord {
  return {
    acknowledgementState: row.acknowledgementState as AgentChatTurnRecord["acknowledgementState"],
    agentSessionId: row.agentSessionId,
    appId: row.appId,
    chatTurnId: row.id,
    completedAt: row.completedAt,
    createdAt: row.createdAt,
    executionId: row.executionId,
    idempotencyKey: row.idempotencyKey,
    kind: row.kind as AgentChatTurnRecord["kind"],
    normalizedResult: row.normalizedResult as Record<string, unknown> | null,
    providerRunRef: row.providerRunRef,
    requestSummary: row.requestSummary as Record<string, unknown>,
    sequence: row.sequence,
    sessionId: row.sessionId,
    state: row.state as AgentChatTurnRecord["state"],
    updatedAt: row.updatedAt
  };
}
import { randomUUID } from "node:crypto";
