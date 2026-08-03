export type ConfirmationStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "expired";

export type ConfirmationDecision = "pending" | "approved" | "expired";

export interface ConfirmationRecord {
  appId: string;
  confirmationId: string;
  consumedAt: Date | null;
  createdAt: Date;
  decidedAt: Date | null;
  decision: ConfirmationDecision;
  executionId: string;
  expiresAt: Date;
  policySnapshot: Record<string, unknown>;
  sessionId: string;
  status: ConfirmationStatus;
  updatedAt: Date;
}

export interface ConfirmationScope {
  appId: string;
  confirmationId: string;
  executionId: string;
  sessionId: string;
}

export interface CreateConfirmationInput extends ConfirmationScope {
  expiresAt: Date;
  policySnapshot: Record<string, unknown>;
}

export type ConfirmationClaimResult =
  | { outcome: "claimed"; record: ConfirmationRecord }
  | { outcome: "running"; record: ConfirmationRecord }
  | { outcome: "terminal"; record: ConfirmationRecord }
  | { outcome: "expired"; record: ConfirmationRecord }
  | { outcome: "not_found" };

export interface ConfirmationStore {
  claim(
    scope: ConfirmationScope,
    now: Date
  ): Promise<ConfirmationClaimResult>;
  create(input: CreateConfirmationInput): Promise<ConfirmationRecord>;
  finish(
    scope: ConfirmationScope,
    status: "completed" | "failed",
    now: Date
  ): Promise<ConfirmationRecord | null>;
  get(scope: ConfirmationScope): Promise<ConfirmationRecord | null>;
}

export class InMemoryConfirmationStore implements ConfirmationStore {
  private readonly records = new Map<string, ConfirmationRecord>();
  private readonly executionIndex = new Map<string, string>();

  async create(input: CreateConfirmationInput): Promise<ConfirmationRecord> {
    const existingId = this.executionIndex.get(input.executionId);
    if (existingId) {
      const existing = this.records.get(existingId);
      if (existing) {
        return existing;
      }
    }

    const now = new Date();
    const record: ConfirmationRecord = {
      appId: input.appId,
      confirmationId: input.confirmationId,
      consumedAt: null,
      createdAt: now,
      decidedAt: null,
      decision: "pending",
      executionId: input.executionId,
      expiresAt: input.expiresAt,
      policySnapshot: input.policySnapshot,
      sessionId: input.sessionId,
      status: "pending",
      updatedAt: now
    };
    this.records.set(record.confirmationId, record);
    this.executionIndex.set(record.executionId, record.confirmationId);
    return record;
  }

  async get(scope: ConfirmationScope): Promise<ConfirmationRecord | null> {
    return this.getSync(scope);
  }

  private getSync(scope: ConfirmationScope): ConfirmationRecord | null {
    const record = this.records.get(scope.confirmationId);
    return record &&
      record.appId === scope.appId &&
      record.executionId === scope.executionId &&
      record.sessionId === scope.sessionId
      ? record
      : null;
  }

  async claim(
    scope: ConfirmationScope,
    now: Date
  ): Promise<ConfirmationClaimResult> {
    const record = this.getSync(scope);
    if (!record) {
      return { outcome: "not_found" };
    }

    if (record.status === "pending" && record.expiresAt.getTime() <= now.getTime()) {
      const expired: ConfirmationRecord = {
        ...record,
        decidedAt: now,
        decision: "expired",
        status: "expired",
        updatedAt: now
      };
      this.records.set(scope.confirmationId, expired);
      return { outcome: "expired", record: expired };
    }

    if (record.status === "pending") {
      const claimed: ConfirmationRecord = {
        ...record,
        consumedAt: now,
        decidedAt: now,
        decision: "approved",
        status: "running",
        updatedAt: now
      };
      this.records.set(scope.confirmationId, claimed);
      return { outcome: "claimed", record: claimed };
    }

    if (record.status === "running") {
      return { outcome: "running", record };
    }
    if (record.status === "expired") {
      return { outcome: "expired", record };
    }
    return { outcome: "terminal", record };
  }

  async finish(
    scope: ConfirmationScope,
    status: "completed" | "failed",
    now: Date
  ): Promise<ConfirmationRecord | null> {
    const record = this.getSync(scope);
    if (!record || record.status !== "running") {
      return record;
    }
    const completed: ConfirmationRecord = {
      ...record,
      status,
      updatedAt: now
    };
    this.records.set(scope.confirmationId, completed);
    return completed;
  }
}
