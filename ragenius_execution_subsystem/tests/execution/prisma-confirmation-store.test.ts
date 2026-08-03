import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { PrismaConfirmationStore } from "../../src/core/execution/prisma-confirmation-store.js";
import type {
  ConfirmationStorePrismaClient,
  ExecutionConfirmationRow
} from "../../src/db/prisma.js";

describe("prisma confirmation store", () => {
  it("uses a conditional update to claim a confirmation once", async () => {
    let row: ExecutionConfirmationRow = {
      id: "confirmation_001",
      executionId: "execution_001",
      appId: "app_001",
      sessionId: "sess_001",
      status: "pending",
      decision: "pending",
      policySnapshot: { permission_scope: "agent.external_write" },
      expiresAt: new Date("2026-07-24T00:01:00.000Z"),
      decidedAt: null,
      consumedAt: null,
      createdAt: new Date("2026-07-24T00:00:00.000Z"),
      updatedAt: new Date("2026-07-24T00:00:00.000Z")
    };
    const prisma = {
      executionConfirmation: {
        async create() {
          return row;
        },
        async findFirst(args: {
          where: {
            appId: string;
            executionId: string;
            id: string;
            sessionId: string;
          };
        }) {
          return args.where.appId === row.appId &&
            args.where.executionId === row.executionId &&
            args.where.id === row.id &&
            args.where.sessionId === row.sessionId
            ? row
            : null;
        },
        async updateMany(args: {
          data: Record<string, unknown>;
          where: Record<string, unknown>;
        }) {
          if (
            args.where.appId !== row.appId ||
            args.where.executionId !== row.executionId ||
            args.where.id !== row.id ||
            args.where.sessionId !== row.sessionId ||
            ("status" in args.where && args.where.status !== row.status)
          ) {
            return { count: 0 };
          }
          if (
            "expiresAt" in args.where &&
            row.expiresAt.getTime() <=
              ((args.where.expiresAt as { gt: Date }).gt).getTime()
          ) {
            return { count: 0 };
          }
          row = {
            ...row,
            ...(args.data as Partial<ExecutionConfirmationRow>),
            updatedAt: new Date("2026-07-24T00:00:01.000Z")
          };
          return { count: 1 };
        }
      },
      $connect: async () => undefined,
      $disconnect: async () => undefined
    } satisfies ConfirmationStorePrismaClient;
    const store = new PrismaConfirmationStore(prisma);
    const scope = {
      appId: "app_001",
      confirmationId: "confirmation_001",
      executionId: "execution_001",
      sessionId: "sess_001"
    };

    const first = await store.claim(
      scope,
      new Date("2026-07-24T00:00:00.000Z")
    );
    const second = await store.claim(
      scope,
      new Date("2026-07-24T00:00:00.500Z")
    );
    await store.finish(
      scope,
      "completed",
      new Date("2026-07-24T00:00:01.000Z")
    );
    const repeated = await store.claim(
      scope,
      new Date("2026-07-24T00:00:02.000Z")
    );

    assert.equal(first.outcome, "claimed");
    assert.equal(second.outcome, "running");
    assert.equal(repeated.outcome, "terminal");
    assert.equal(row.status, "completed");
    assert.equal(row.decision, "approved");
    assert.ok(row.consumedAt);
  });
});
