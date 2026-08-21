import type {
  AgentInteractionRecord,
  ExecutionScope
} from "./interactive-agent-types.js";

export type CreateAgentInteractionInput = Omit<
  AgentInteractionRecord,
  | "createdAt"
  | "resolvedAt"
  | "responseSummary"
  | "secretInput"
  | "sequence"
  | "state"
  | "updatedAt"
  | "version"
>;

export interface InteractionScope extends ExecutionScope {
  interactionId: string;
}

export interface ClaimAgentInteractionInput extends InteractionScope {
  expectedVersion: number;
  idempotencyKey: string;
  now: Date;
  responseSummary: Record<string, unknown>;
}

export interface ResolveAgentInteractionInput extends InteractionScope {
  idempotencyKey: string;
  now: Date;
  responseSummary: Record<string, unknown>;
}

export type InteractionClaimResult =
  | { outcome: "claimed" | "replay" | "conflict" | "expired"; record: AgentInteractionRecord }
  | { outcome: "not_found"; record: null };

export interface AgentInteractionStore {
  cancelPending(scope: ExecutionScope, now: Date): Promise<number>;
  claim(input: ClaimAgentInteractionInput): Promise<InteractionClaimResult>;
  create(input: CreateAgentInteractionInput): Promise<AgentInteractionRecord>;
  list(scope: ExecutionScope): Promise<AgentInteractionRecord[]>;
  resolve(input: ResolveAgentInteractionInput): Promise<AgentInteractionRecord | null>;
}

interface StoredInteraction {
  idempotencyKey: string | null;
  record: AgentInteractionRecord;
}

export class InMemoryAgentInteractionStore implements AgentInteractionStore {
  private readonly records = new Map<string, StoredInteraction>();
  private readonly executionSequences = new Map<string, number>();

  async create(input: CreateAgentInteractionInput): Promise<AgentInteractionRecord> {
    const existing = this.records.get(input.interactionId);
    if (existing) {
      if (!matchesScope(existing.record, input)) {
        throw new Error("Existing interaction does not match execution scope.");
      }
      return cloneInteraction(existing.record);
    }
    const now = new Date();
    const sequence = (this.executionSequences.get(input.executionId) ?? 0) + 1;
    this.executionSequences.set(input.executionId, sequence);
    const record: AgentInteractionRecord = {
      ...input,
      createdAt: now,
      options: input.options.map((option) => ({ ...option })),
      resolvedAt: null,
      responseSummary: null,
      secretInput: false,
      sequence,
      state: "pending",
      updatedAt: now,
      version: 1
    };
    this.records.set(record.interactionId, { idempotencyKey: null, record });
    return cloneInteraction(record);
  }

  async list(scope: ExecutionScope): Promise<AgentInteractionRecord[]> {
    return [...this.records.values()]
      .map((stored) => stored.record)
      .filter((record) => matchesScope(record, scope))
      .sort((left, right) => left.sequence - right.sequence)
      .map(cloneInteraction);
  }

  async claim(input: ClaimAgentInteractionInput): Promise<InteractionClaimResult> {
    const stored = this.records.get(input.interactionId);
    if (!stored || !matchesScope(stored.record, input)) {
      return { outcome: "not_found", record: null };
    }
    if (stored.idempotencyKey === input.idempotencyKey) {
      return { outcome: "replay", record: cloneInteraction(stored.record) };
    }
    if (
      stored.record.state === "pending" &&
      stored.record.expiresAt.getTime() <= input.now.getTime()
    ) {
      stored.record = {
        ...stored.record,
        state: "expired",
        updatedAt: input.now,
        version: stored.record.version + 1
      };
      return { outcome: "expired", record: cloneInteraction(stored.record) };
    }
    if (
      stored.record.state !== "pending" ||
      stored.record.version !== input.expectedVersion
    ) {
      return { outcome: "conflict", record: cloneInteraction(stored.record) };
    }
    stored.idempotencyKey = input.idempotencyKey;
    stored.record = {
      ...stored.record,
      responseSummary: { ...input.responseSummary },
      state: "resolving",
      updatedAt: input.now,
      version: stored.record.version + 1
    };
    return { outcome: "claimed", record: cloneInteraction(stored.record) };
  }

  async resolve(input: ResolveAgentInteractionInput): Promise<AgentInteractionRecord | null> {
    const stored = this.records.get(input.interactionId);
    if (
      !stored ||
      !matchesScope(stored.record, input) ||
      stored.idempotencyKey !== input.idempotencyKey
    ) {
      return null;
    }
    if (stored.record.state === "resolved") {
      return cloneInteraction(stored.record);
    }
    if (stored.record.state !== "resolving") {
      return null;
    }
    stored.record = {
      ...stored.record,
      resolvedAt: input.now,
      responseSummary: { ...input.responseSummary },
      state: "resolved",
      updatedAt: input.now,
      version: stored.record.version + 1
    };
    return cloneInteraction(stored.record);
  }

  async cancelPending(scope: ExecutionScope, now: Date): Promise<number> {
    let count = 0;
    for (const stored of this.records.values()) {
      if (
        matchesScope(stored.record, scope) &&
        (stored.record.state === "pending" || stored.record.state === "resolving")
      ) {
        stored.record = {
          ...stored.record,
          state: "cancelled",
          updatedAt: now,
          version: stored.record.version + 1
        };
        count += 1;
      }
    }
    return count;
  }
}

function matchesScope(record: ExecutionScope, scope: ExecutionScope): boolean {
  return (
    record.appId === scope.appId &&
    record.executionId === scope.executionId &&
    record.sessionId === scope.sessionId
  );
}

function cloneInteraction(record: AgentInteractionRecord): AgentInteractionRecord {
  return {
    ...record,
    options: record.options.map((option) => ({ ...option })),
    responseSummary: record.responseSummary
      ? { ...record.responseSummary }
      : null
  };
}
