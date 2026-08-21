import { PrismaClient } from "@prisma/client";
import type { AgentEventPrismaClient } from "../core/interactive/prisma-agent-event-store.js";
import type { AgentInteractionPrismaClient } from "../core/interactive/prisma-agent-interaction-store.js";
import type { AgentSessionPrismaClient } from "../core/interactive/prisma-agent-session-store.js";

export interface ExecutionRow {
  id: string;
  requestType: string;
  appId: string;
  sessionId: string;
  skillId: string;
  requestPayload: unknown;
  status: string;
  resultType: string | null;
  result: unknown;
  executionProvenance: unknown;
  executionMetadata: unknown;
  files: unknown;
  errors: unknown;
  logsSummary: string | null;
  createdAt: Date;
  updatedAt: Date;
}

export interface ExecutionLogRow {
  executionId: string;
  level: string;
  eventType: string;
  message: string;
  createdAt: Date;
}

export interface ExecutionConfirmationRow {
  id: string;
  executionId: string;
  appId: string;
  sessionId: string;
  status: string;
  decision: string;
  policySnapshot: unknown;
  expiresAt: Date;
  decidedAt: Date | null;
  consumedAt: Date | null;
  createdAt: Date;
  updatedAt: Date;
}

export interface PrismaClientLike {
  $connect(): Promise<void>;
  $disconnect(): Promise<void>;
}

export interface ExecutionStorePrismaClient extends PrismaClientLike {
  execution: {
    findFirst(args: {
      where: { appId: string; id: string; sessionId: string };
    }): Promise<ExecutionRow | null>;
    findMany(args: {
      orderBy: { updatedAt: "asc" | "desc" };
      take?: number;
      where: Record<string, unknown>;
    }): Promise<ExecutionRow[]>;
    updateMany?(args: {
      data: Record<string, unknown>;
      where: Record<string, unknown>;
    }): Promise<{ count: number }>;
    upsert(args: {
      where: { id: string };
      create: Record<string, unknown>;
      update: Record<string, unknown>;
    }): Promise<unknown>;
  };
  executionLog: {
    createMany(args: {
      data: Array<Record<string, unknown>>;
    }): Promise<{ count: number }>;
    findMany(args: {
      where: { executionId: string };
      orderBy: { createdAt: "asc" | "desc" };
    }): Promise<ExecutionLogRow[]>;
  };
}

export interface ConfirmationStorePrismaClient extends PrismaClientLike {
  executionConfirmation: {
    create(args: {
      data: Record<string, unknown>;
    }): Promise<ExecutionConfirmationRow>;
    findFirst(args: {
      where: {
        appId: string;
        executionId: string;
        id: string;
        sessionId: string;
      };
    }): Promise<ExecutionConfirmationRow | null>;
    updateMany(args: {
      data: Record<string, unknown>;
      where: Record<string, unknown>;
    }): Promise<{ count: number }>;
  };
}

let prismaClient: PrismaClient | undefined;

export function createPrismaClient(): ExecutionStorePrismaClient &
  ConfirmationStorePrismaClient &
  AgentSessionPrismaClient &
  AgentInteractionPrismaClient &
  AgentEventPrismaClient {
  if (!prismaClient) {
    prismaClient = new PrismaClient();
  }

  return prismaClient as unknown as ExecutionStorePrismaClient &
    ConfirmationStorePrismaClient &
    AgentSessionPrismaClient &
    AgentInteractionPrismaClient &
    AgentEventPrismaClient;
}
