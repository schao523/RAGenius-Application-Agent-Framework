import type {
  ConfirmationStorePrismaClient,
  ExecutionConfirmationRow,
} from "../../db/prisma.js";
import type {
  ConfirmationClaimResult,
  ConfirmationRecord,
  ConfirmationScope,
  ConfirmationStore,
  CreateConfirmationInput
} from "./confirmation-store.js";

function asPolicySnapshot(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

export class PrismaConfirmationStore implements ConfirmationStore {
  constructor(private readonly prisma: ConfirmationStorePrismaClient) {}

  async create(input: CreateConfirmationInput): Promise<ConfirmationRecord> {
    const row = await this.prisma.executionConfirmation.create({
      data: {
        id: input.confirmationId,
        executionId: input.executionId,
        appId: input.appId,
        sessionId: input.sessionId,
        policySnapshot: input.policySnapshot,
        expiresAt: input.expiresAt
      }
    });
    return this.toRecord(row);
  }

  async get(scope: ConfirmationScope): Promise<ConfirmationRecord | null> {
    const row = await this.prisma.executionConfirmation.findFirst({
      where: {
        appId: scope.appId,
        executionId: scope.executionId,
        id: scope.confirmationId,
        sessionId: scope.sessionId
      }
    });
    return row ? this.toRecord(row) : null;
  }

  async claim(
    scope: ConfirmationScope,
    now: Date
  ): Promise<ConfirmationClaimResult> {
    const claimed = await this.prisma.executionConfirmation.updateMany({
      where: {
        appId: scope.appId,
        executionId: scope.executionId,
        expiresAt: { gt: now },
        id: scope.confirmationId,
        sessionId: scope.sessionId,
        status: "pending"
      },
      data: {
        consumedAt: now,
        decidedAt: now,
        decision: "approved",
        status: "running"
      }
    });
    if (claimed.count === 1) {
      const record = await this.get(scope);
      if (record) {
        return { outcome: "claimed", record };
      }
    }

    let record = await this.get(scope);
    if (!record) {
      return { outcome: "not_found" };
    }
    if (record.status === "pending" && record.expiresAt.getTime() <= now.getTime()) {
      await this.prisma.executionConfirmation.updateMany({
        where: {
          appId: scope.appId,
          executionId: scope.executionId,
          id: scope.confirmationId,
          sessionId: scope.sessionId,
          status: "pending"
        },
        data: {
          decidedAt: now,
          decision: "expired",
          status: "expired"
        }
      });
      record = (await this.get(scope)) ?? record;
      return { outcome: "expired", record };
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
    await this.prisma.executionConfirmation.updateMany({
      where: {
        appId: scope.appId,
        executionId: scope.executionId,
        id: scope.confirmationId,
        sessionId: scope.sessionId,
        status: "running"
      },
      data: { status, updatedAt: now }
    });
    return this.get(scope);
  }

  private toRecord(row: ExecutionConfirmationRow): ConfirmationRecord {
    return {
      appId: row.appId,
      confirmationId: row.id,
      consumedAt: row.consumedAt,
      createdAt: row.createdAt,
      decidedAt: row.decidedAt,
      decision: row.decision as ConfirmationRecord["decision"],
      executionId: row.executionId,
      expiresAt: row.expiresAt,
      policySnapshot: asPolicySnapshot(row.policySnapshot),
      sessionId: row.sessionId,
      status: row.status as ConfirmationRecord["status"],
      updatedAt: row.updatedAt
    };
  }
}
