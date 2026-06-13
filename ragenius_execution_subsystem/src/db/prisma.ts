import { PrismaClient } from "@prisma/client";

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

export interface PrismaClientLike {
  $connect(): Promise<void>;
  $disconnect(): Promise<void>;
}

export interface ExecutionStorePrismaClient extends PrismaClientLike {
  execution: {
    findUnique(args: { where: { id: string } }): Promise<ExecutionRow | null>;
    findMany(args: {
      orderBy: { updatedAt: "asc" | "desc" };
      take: number;
    }): Promise<ExecutionRow[]>;
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

let prismaClient: PrismaClient | undefined;

export function createPrismaClient(): ExecutionStorePrismaClient {
  if (!prismaClient) {
    prismaClient = new PrismaClient();
  }

  return prismaClient as unknown as ExecutionStorePrismaClient;
}
