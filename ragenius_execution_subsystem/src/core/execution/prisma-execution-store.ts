import {
  executionRequestSchema,
  type ExecutionRequest
} from "../../api/schemas/execution-request.schema.js";
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
  ExecutionScope,
  ListRecentExecutionsInput,
  ExecutionRecord,
  ExecutionStore,
  SaveExecutionRecordInput
  ,TransitionExecutionInput
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

  async get(scope: ExecutionScope): Promise<ExecutionRecord | null> {
    const row = await this.prisma.execution.findFirst({
      where: {
        appId: scope.appId,
        id: scope.executionId,
        sessionId: scope.sessionId
      }
    });

    if (!row) {
      return null;
    }

    return this.toExecutionRecord(row);
  }

  async transition(input: TransitionExecutionInput): Promise<boolean> {
    if (!this.prisma.execution.updateMany) {
      throw new Error("Prisma execution transitions are not configured.");
    }
    const update = await this.prisma.execution.updateMany({
      where: {
        id: input.scope.executionId,
        appId: input.scope.appId,
        sessionId: input.scope.sessionId,
        status: { in: input.from }
      },
      data: {
        status: input.result.status,
        resultType: input.result.result_type,
        result: input.result.result,
        executionProvenance: input.result.execution_provenance,
        executionMetadata: input.result.execution_metadata,
        files: input.result.files,
        errors: input.result.errors,
        logsSummary: input.result.logs_summary,
        ...(input.result.status === "running" ? { startedAt: new Date() } : {}),
        ...(["completed", "failed", "partial", "blocked"].includes(input.result.status)
          ? { completedAt: new Date() }
          : {})
      }
    });
    if (update.count !== 1) {
      return false;
    }
    await this.prisma.executionLog.createMany({
      data: [{
        executionId: input.scope.executionId,
        level: input.result.status === "failed" ? "error" : "info",
        eventType: "status_transition",
        message: input.result.logs_summary,
        summary: null
      }]
    });
    return true;
  }

  async getLogs(scope: ExecutionScope): Promise<ExecutionLogEntry[]> {
    if (!(await this.get(scope))) {
      return [];
    }

    const rows = await this.prisma.executionLog.findMany({
      where: { executionId: scope.executionId },
      orderBy: { createdAt: "asc" }
    });

    return rows.map((row) => ({
      created_at: row.createdAt.toISOString(),
      execution_id: row.executionId,
      level: row.level as "info" | "error",
      message: row.message
    }));
  }

  async getRequest(scope: ExecutionScope): Promise<ExecutionRequest | null> {
    const row = await this.prisma.execution.findFirst({
      where: {
        appId: scope.appId,
        id: scope.executionId,
        sessionId: scope.sessionId
      }
    });

    return (row?.requestPayload as ExecutionRequest | null) ?? null;
  }

  async hasActiveArtifactReference(input: {
    appId: string;
    sessionId: string;
    artifactId: string;
  }): Promise<boolean> {
    const rows = await this.prisma.execution.findMany({
      orderBy: { updatedAt: "asc" },
      where: {
        appId: input.appId,
        sessionId: input.sessionId,
        status: {
          in: ["queued", "running", "pending_confirmation", "waiting_for_interaction"]
        }
      }
    });
    return rows.some((row) => {
      const parsed = executionRequestSchema.safeParse(row.requestPayload);
      return parsed.success &&
        parsed.data.request_type === "execute_agent" &&
        parsed.data.artifact_refs?.some((ref) => ref.artifact_id === input.artifactId) === true;
    });
  }

  async listRecent(input: ListRecentExecutionsInput): Promise<ExecutionRecord[]> {
    const rows = await this.prisma.execution.findMany({
      orderBy: { updatedAt: "desc" },
      take: Math.max(input.limit * 5, input.limit, 20),
      where: {
        appId: input.appId,
        sessionId: input.sessionId
      }
    });

    return rows
      .map((row) => this.toExecutionRecord(row))
      .filter(
        (record) =>
          record.app_id === input.appId &&
          record.session_id === input.sessionId
      )
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

  async listByStatuses(
    statuses: NormalizedExecutionResult["status"][]
  ): Promise<ExecutionRecord[]> {
    const rows = await this.prisma.execution.findMany({
      orderBy: { updatedAt: "asc" },
      where: { status: { in: statuses } }
    });
    return rows.map((row) => this.toExecutionRecord(row));
  }
}
