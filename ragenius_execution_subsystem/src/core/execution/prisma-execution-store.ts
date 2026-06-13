import type { ExecutionRequest } from "../../api/schemas/execution-request.schema.js";
import type {
  ExecutionMetadata,
  NormalizedError,
  NormalizedExecutionResult,
  ToolExecutionProvenance
} from "../../api/schemas/common-response.schema.js";
import type {
  ExecutionStorePrismaClient
} from "../../db/prisma.js";
import type {
  ExecutionLogEntry,
  ListRecentExecutionsInput,
  ExecutionRecord,
  ExecutionStore,
  SaveExecutionRecordInput
} from "./execution-store.js";
import { persistedSkillIdForRequest } from "./execution-store.js";

function asObjectRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function asRecordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.map((entry) => asObjectRecord(entry))
    : [];
}

function asErrorArray(value: unknown): NormalizedError[] {
  return Array.isArray(value) ? (value as NormalizedError[]) : [];
}

function asExecutionProvenanceArray(
  value: unknown
): ToolExecutionProvenance[] | undefined {
  return Array.isArray(value)
    ? (value as ToolExecutionProvenance[])
    : undefined;
}

function asExecutionMetadata(value: unknown): ExecutionMetadata | undefined {
  return typeof value === "object" && value !== null
    ? (value as ExecutionMetadata)
    : undefined;
}

export class PrismaExecutionStore implements ExecutionStore {
  constructor(private readonly prisma: ExecutionStorePrismaClient) {}

  private toExecutionRecord(row: {
    id: string;
    appId: string;
    createdAt: Date;
    updatedAt: Date;
    requestType: string;
    sessionId: string;
    skillId: string;
    status: string;
    resultType: string | null;
    result: unknown;
    executionProvenance: unknown;
    executionMetadata: unknown;
    files: unknown;
    errors: unknown;
    logsSummary: string | null;
  }): ExecutionRecord {
    return {
      execution_id: row.id,
      app_id: row.appId,
      created_at: row.createdAt.toISOString(),
      updated_at: row.updatedAt.toISOString(),
      request_type: row.requestType as ExecutionRequest["request_type"],
      session_id: row.sessionId,
      skill_id: row.skillId,
      status: row.status as NormalizedExecutionResult["status"],
      result_type: (row.resultType ?? "json") as NormalizedExecutionResult["result_type"],
      result: asObjectRecord(row.result),
      execution_provenance: asExecutionProvenanceArray(row.executionProvenance),
      execution_metadata: asExecutionMetadata(row.executionMetadata),
      files: asRecordArray(row.files),
      errors: asErrorArray(row.errors),
      logs_summary: row.logsSummary ?? ""
    };
  }

  async save(input: SaveExecutionRecordInput): Promise<void> {
    await this.prisma.execution.upsert({
      where: { id: input.executionId },
      create: {
        id: input.executionId,
        requestType: input.request.request_type,
        appId: input.request.app_id,
        sessionId: input.request.session_id,
        skillId: persistedSkillIdForRequest(input.request),
        requestPayload: input.request,
        status: input.result.status,
        resultType: input.result.result_type,
        result: input.result.result,
        executionProvenance: input.result.execution_provenance,
        executionMetadata: input.result.execution_metadata,
        files: input.result.files,
        errors: input.result.errors,
        logsSummary: input.result.logs_summary
      },
      update: {
        requestPayload: input.request,
        status: input.result.status,
        resultType: input.result.result_type,
        result: input.result.result,
        executionProvenance: input.result.execution_provenance,
        executionMetadata: input.result.execution_metadata,
        files: input.result.files,
        errors: input.result.errors,
        logsSummary: input.result.logs_summary
      }
    });

    await this.prisma.executionLog.createMany({
      data: [
        {
          executionId: input.executionId,
          level: input.result.status === "failed" ? "error" : "info",
          eventType: "summary",
          message: input.result.logs_summary,
          summary: null
        }
      ]
    });
  }

  async get(executionId: string): Promise<ExecutionRecord | null> {
    const row = await this.prisma.execution.findUnique({
      where: { id: executionId }
    });

    if (!row) {
      return null;
    }

    return this.toExecutionRecord(row);
  }

  async getLogs(executionId: string): Promise<ExecutionLogEntry[]> {
    const rows = await this.prisma.executionLog.findMany({
      where: { executionId },
      orderBy: { createdAt: "asc" }
    });

    return rows.map((row) => ({
      created_at: row.createdAt.toISOString(),
      execution_id: row.executionId,
      level: row.level as "info" | "error",
      message: row.message
    }));
  }

  async getRequest(executionId: string): Promise<ExecutionRequest | null> {
    const row = await this.prisma.execution.findUnique({
      where: { id: executionId }
    });

    return (row?.requestPayload as ExecutionRequest | null) ?? null;
  }

  async listRecent(input: ListRecentExecutionsInput): Promise<ExecutionRecord[]> {
    const rows = await this.prisma.execution.findMany({
      orderBy: { updatedAt: "desc" },
      take: Math.max(input.limit * 5, input.limit, 20)
    });

    return rows
      .map((row) => this.toExecutionRecord(row))
      .filter((record) => {
        if (
          input.usedFallback !== undefined &&
          record.execution_metadata?.used_fallback !== input.usedFallback
        ) {
          return false;
        }
        if (
          input.executionPath &&
          !record.execution_metadata?.execution_paths.includes(input.executionPath)
        ) {
          return false;
        }
        return true;
      })
      .slice(0, input.limit);
  }
}
