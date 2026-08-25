import type {
  AgentInteractionStore,
  ClaimAgentInteractionInput,
  CreateAgentInteractionInput,
  InteractionClaimResult,
  ReleaseAgentInteractionInput,
  ResolveAgentInteractionInput
} from "./agent-interaction-store.js";
import type {
  AgentInteractionOption,
  AgentInteractionPresentation,
  AgentInteractionRecord,
  ExecutionScope
} from "./interactive-agent-types.js";

interface InteractionSequenceRow {
  lastInteractionSeq: number;
}

export interface AgentInteractionRow {
  agentSessionId: string;
  allowsFreeText: boolean;
  appId: string;
  createdAt: Date;
  executionId: string;
  expiresAt: Date;
  id: string;
  idempotencyKey: string | null;
  options: unknown;
  presentation: unknown;
  policyBindingHash: string;
  prompt: string;
  providerCorrelationRef: string;
  resolvedAt: Date | null;
  responseSummary: unknown;
  secretInput: boolean;
  sequence: number;
  sessionId: string;
  state: string;
  type: string;
  updatedAt: Date;
  version: number;
}

interface AgentInteractionTransactionClient {
  agentInteraction: {
    create(args: { data: Record<string, unknown> }): Promise<AgentInteractionRow>;
    findFirst(args: { where: Record<string, unknown> }): Promise<AgentInteractionRow | null>;
    findMany(args: {
      orderBy: { sequence: "asc" | "desc" };
      where: Record<string, unknown>;
    }): Promise<AgentInteractionRow[]>;
    updateMany(args: {
      data: Record<string, unknown>;
      where: Record<string, unknown>;
    }): Promise<{ count: number }>;
  };
  agentSession: {
    findFirst(args: { where: Record<string, unknown> }): Promise<{ id: string } | null>;
    update(args: {
      data: Record<string, unknown>;
      where: { executionId: string };
    }): Promise<InteractionSequenceRow>;
  };
}

export interface AgentInteractionPrismaClient
  extends AgentInteractionTransactionClient {
  $transaction<T>(
    callback: (tx: AgentInteractionTransactionClient) => Promise<T>
  ): Promise<T>;
}

export class PrismaAgentInteractionStore implements AgentInteractionStore {
  constructor(private readonly prisma: AgentInteractionPrismaClient) {}

  async create(input: CreateAgentInteractionInput): Promise<AgentInteractionRecord> {
    return this.prisma.$transaction(async (tx) => {
      const session = await tx.agentSession.findFirst({ where: scopeWhere(input) });
      if (!session || session.id !== input.agentSessionId) {
        throw new Error("Agent session does not match interaction scope.");
      }
      const counter = await tx.agentSession.update({
        where: { executionId: input.executionId },
        data: { lastInteractionSeq: { increment: 1 } }
      });
      const row = await tx.agentInteraction.create({
        data: {
          id: input.interactionId,
          executionId: input.executionId,
          agentSessionId: input.agentSessionId,
          appId: input.appId,
          sessionId: input.sessionId,
          sequence: counter.lastInteractionSeq,
          type: input.type,
          state: "pending",
          prompt: input.prompt,
          options: input.options,
          presentation: input.presentation,
          allowsFreeText: input.allowsFreeText,
          secretInput: false,
          providerCorrelationRef: input.providerCorrelationRef,
          policyBindingHash: input.policyBindingHash,
          version: 1,
          expiresAt: input.expiresAt
        }
      });
      return toRecord(row);
    });
  }

  async list(scope: ExecutionScope): Promise<AgentInteractionRecord[]> {
    const rows = await this.prisma.agentInteraction.findMany({
      where: scopeWhere(scope),
      orderBy: { sequence: "asc" }
    });
    return rows.map(toRecord);
  }

  async claim(input: ClaimAgentInteractionInput): Promise<InteractionClaimResult> {
    const claimed = await this.prisma.agentInteraction.updateMany({
      where: {
        ...scopeWhere(input),
        id: input.interactionId,
        state: "pending",
        version: input.expectedVersion,
        expiresAt: { gt: input.now }
      },
      data: {
        idempotencyKey: input.idempotencyKey,
        responseSummary: input.responseSummary,
        state: "resolving",
        version: { increment: 1 }
      }
    });
    if (claimed.count === 1) {
      const record = await this.get(input);
      if (record) {
        return { outcome: "claimed", record: toRecord(record) };
      }
    }
    let record = await this.get(input);
    if (!record) {
      return { outcome: "not_found", record: null };
    }
    if (record.idempotencyKey === input.idempotencyKey) {
      return { outcome: "replay", record: toRecord(record) };
    }
    if (record.state === "pending" && record.expiresAt.getTime() <= input.now.getTime()) {
      await this.prisma.agentInteraction.updateMany({
        where: {
          ...scopeWhere(input),
          id: input.interactionId,
          state: "pending",
          version: record.version
        },
        data: { state: "expired", version: { increment: 1 } }
      });
      record = (await this.get(input)) ?? record;
      return { outcome: "expired", record: toRecord(record) };
    }
    return { outcome: "conflict", record: toRecord(record) };
  }

  async resolve(input: ResolveAgentInteractionInput): Promise<AgentInteractionRecord | null> {
    const updated = await this.prisma.agentInteraction.updateMany({
      where: {
        ...scopeWhere(input),
        id: input.interactionId,
        idempotencyKey: input.idempotencyKey,
        state: "resolving"
      },
      data: {
        resolvedAt: input.now,
        responseSummary: input.responseSummary,
        state: "resolved",
        version: { increment: 1 }
      }
    });
    const row = await this.get(input);
    if (!row) {
      return null;
    }
    if (
      updated.count === 1 ||
      (row.state === "resolved" && row.idempotencyKey === input.idempotencyKey)
    ) {
      return toRecord(row);
    }
    return null;
  }

  async release(input: ReleaseAgentInteractionInput): Promise<AgentInteractionRecord | null> {
    const updated = await this.prisma.agentInteraction.updateMany({
      where: {
        ...scopeWhere(input),
        id: input.interactionId,
        idempotencyKey: input.idempotencyKey,
        state: "resolving"
      },
      data: {
        idempotencyKey: null,
        responseSummary: null,
        state: "pending",
        updatedAt: input.now,
        version: { increment: 1 }
      }
    });
    if (updated.count !== 1) return null;
    const row = await this.get(input);
    return row ? toRecord(row) : null;
  }

  async cancelPending(scope: ExecutionScope, now: Date): Promise<number> {
    const result = await this.prisma.agentInteraction.updateMany({
      where: {
        ...scopeWhere(scope),
        state: { in: ["pending", "resolving"] }
      },
      data: {
        state: "cancelled",
        updatedAt: now,
        version: { increment: 1 }
      }
    });
    return result.count;
  }

  private get(scope: ExecutionScope & { interactionId: string }): Promise<AgentInteractionRow | null> {
    return this.prisma.agentInteraction.findFirst({
      where: { ...scopeWhere(scope), id: scope.interactionId }
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

function asOptions(value: unknown): AgentInteractionOption[] {
  return Array.isArray(value) ? (value as AgentInteractionOption[]) : [];
}

function asSummary(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : null;
}

function asPresentation(value: unknown): AgentInteractionPresentation | null {
  return typeof value === "object" && value !== null
    ? (value as AgentInteractionPresentation)
    : null;
}

function toRecord(row: AgentInteractionRow): AgentInteractionRecord {
  return {
    agentSessionId: row.agentSessionId,
    allowsFreeText: row.allowsFreeText,
    appId: row.appId,
    createdAt: row.createdAt,
    executionId: row.executionId,
    expiresAt: row.expiresAt,
    interactionId: row.id,
    options: asOptions(row.options),
    presentation: asPresentation(row.presentation),
    policyBindingHash: row.policyBindingHash,
    prompt: row.prompt,
    providerCorrelationRef: row.providerCorrelationRef,
    resolvedAt: row.resolvedAt,
    responseSummary: asSummary(row.responseSummary),
    secretInput: false,
    sequence: row.sequence,
    sessionId: row.sessionId,
    state: row.state as AgentInteractionRecord["state"],
    type: row.type as AgentInteractionRecord["type"],
    updatedAt: row.updatedAt,
    version: row.version
  };
}
