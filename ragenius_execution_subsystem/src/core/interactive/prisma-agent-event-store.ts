import type {
  AgentEventStore,
  AppendAgentEventInput,
  ListAgentEventsInput
} from "./agent-event-store.js";
import type {
  AgentExecutionEvent,
  ExecutionScope
} from "./interactive-agent-types.js";

interface EventSequenceRow {
  lastEventSeq: number;
}

export interface AgentEventRow {
  appId: string;
  executionId: string;
  interactionId: string | null;
  occurredAt: Date;
  payload: unknown;
  providerEventRef: string | null;
  sequence: number;
  sessionId: string;
  type: string;
}

interface AgentEventTransactionClient {
  agentExecutionEvent: {
    create(args: { data: Record<string, unknown> }): Promise<AgentEventRow>;
    findFirst(args: { where: Record<string, unknown> }): Promise<AgentEventRow | null>;
    findMany(args: {
      orderBy: { sequence: "asc" | "desc" };
      take: number;
      where: Record<string, unknown>;
    }): Promise<AgentEventRow[]>;
  };
  agentSession: {
    findFirst(args: { where: Record<string, unknown> }): Promise<{ id: string } | null>;
    update(args: {
      data: Record<string, unknown>;
      where: { executionId: string };
    }): Promise<EventSequenceRow>;
  };
}

export interface AgentEventPrismaClient extends AgentEventTransactionClient {
  $transaction<T>(callback: (tx: AgentEventTransactionClient) => Promise<T>): Promise<T>;
}

export class PrismaAgentEventStore implements AgentEventStore {
  constructor(private readonly prisma: AgentEventPrismaClient) {}

  async append(input: AppendAgentEventInput): Promise<AgentExecutionEvent> {
    if (input.providerEventRef) {
      const duplicate = await this.findByProviderRef(input, input.providerEventRef);
      if (duplicate) {
        return toRecord(duplicate);
      }
    }
    try {
      return await this.prisma.$transaction(async (tx) => {
        const session = await tx.agentSession.findFirst({ where: scopeWhere(input) });
        if (!session) {
          throw new Error("Agent session does not match event scope.");
        }
        const counter = await tx.agentSession.update({
          where: { executionId: input.executionId },
          data: { lastEventSeq: { increment: 1 } }
        });
        const row = await tx.agentExecutionEvent.create({
          data: {
            executionId: input.executionId,
            appId: input.appId,
            sessionId: input.sessionId,
            sequence: counter.lastEventSeq,
            type: input.type,
            providerEventRef: input.providerEventRef,
            interactionId: input.interactionId,
            payload: input.payload,
            occurredAt: input.occurredAt
          }
        });
        return toRecord(row);
      });
    } catch (error) {
      if (input.providerEventRef && isUniqueConstraintError(error)) {
        const duplicate = await this.findByProviderRef(input, input.providerEventRef);
        if (duplicate) {
          return toRecord(duplicate);
        }
      }
      throw error;
    }
  }

  async list(input: ListAgentEventsInput): Promise<AgentExecutionEvent[]> {
    const rows = await this.prisma.agentExecutionEvent.findMany({
      where: {
        ...scopeWhere(input),
        sequence: { gt: input.afterSequence }
      },
      orderBy: { sequence: "asc" },
      take: input.limit
    });
    return rows.map(toRecord);
  }

  private findByProviderRef(
    scope: ExecutionScope,
    providerEventRef: string
  ): Promise<AgentEventRow | null> {
    return this.prisma.agentExecutionEvent.findFirst({
      where: { ...scopeWhere(scope), providerEventRef }
    });
  }
}

function scopeWhere(scope: ExecutionScope): Record<string, unknown> {
  return {
    appId: scope.appId,
    executionId: scope.executionId,
    sessionId: scope.sessionId
  };
}

function isUniqueConstraintError(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    error.code === "P2002"
  );
}

function asPayload(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function toRecord(row: AgentEventRow): AgentExecutionEvent {
  return {
    appId: row.appId,
    executionId: row.executionId,
    ...(row.interactionId ? { interactionId: row.interactionId } : {}),
    occurredAt: row.occurredAt,
    payload: asPayload(row.payload),
    ...(row.providerEventRef ? { providerEventRef: row.providerEventRef } : {}),
    sequence: row.sequence,
    sessionId: row.sessionId,
    type: row.type as AgentExecutionEvent["type"]
  };
}
