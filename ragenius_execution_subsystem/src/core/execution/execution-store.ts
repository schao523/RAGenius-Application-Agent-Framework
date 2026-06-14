import type {
  ExecuteAgentRequest,
  ExecutionRequest
} from "../../api/schemas/execution-request.schema.js";
import type {
  NormalizedExecutionResult,
  ToolExecutionProvenance
} from "../../api/schemas/common-response.schema.js";

export function persistedSkillIdForRequest(request: ExecutionRequest): string {
  if (request.request_type === "execute_skill") {
    return request.skill_id;
  }

  return persistedAgentSkillIdForRequest(request);
}

function persistedAgentSkillIdForRequest(request: ExecuteAgentRequest): string {
  const backend = strOrEmpty(request.agent_backend);
  const hint = strOrEmpty(request.agent_skill_hint);
  return hint ? `${backend}:${hint}` : backend;
}

function strOrEmpty(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export interface ExecutionLogEntry {
  created_at: string;
  execution_id: string;
  level: "info" | "error";
  message: string;
}

export interface ExecutionRecord extends NormalizedExecutionResult {
  app_id: string;
  created_at: string;
  request_type: ExecutionRequest["request_type"];
  session_id: string;
  skill_id: string;
  updated_at: string;
}

export interface SaveExecutionRecordInput {
  executionId: string;
  request: ExecutionRequest;
  result: NormalizedExecutionResult;
}

export interface ListRecentExecutionsInput {
  executionPath?:
    | ToolExecutionProvenance["execution_path"]
    | undefined;
  limit: number;
  usedFallback?: boolean | undefined;
}

export interface ExecutionStore {
  get(executionId: string): Promise<ExecutionRecord | null>;
  getLogs(executionId: string): Promise<ExecutionLogEntry[]>;
  getRequest(executionId: string): Promise<ExecutionRequest | null>;
  listRecent(input: ListRecentExecutionsInput): Promise<ExecutionRecord[]>;
  save(input: SaveExecutionRecordInput): Promise<void>;
}

export class InMemoryExecutionStore implements ExecutionStore {
  private readonly records = new Map<string, ExecutionRecord>();
  private readonly logs = new Map<string, ExecutionLogEntry[]>();
  private readonly requests = new Map<string, ExecutionRequest>();

  async save(input: SaveExecutionRecordInput): Promise<void> {
    const timestamp = new Date().toISOString();
    const existing = this.records.get(input.executionId);
    const record: ExecutionRecord = {
      ...input.result,
      execution_id: input.executionId,
      app_id: input.request.app_id,
      created_at: existing?.created_at ?? timestamp,
      request_type: input.request.request_type,
      session_id: input.request.session_id,
      skill_id: persistedSkillIdForRequest(input.request),
      updated_at: timestamp
    };

    this.records.set(input.executionId, record);
    this.requests.set(input.executionId, input.request);
    this.logs.set(input.executionId, [
      {
        created_at: timestamp,
        execution_id: input.executionId,
        level: input.result.status === "failed" ? "error" : "info",
        message: input.result.logs_summary
      }
    ]);
  }

  async get(executionId: string): Promise<ExecutionRecord | null> {
    return this.records.get(executionId) ?? null;
  }

  async getLogs(executionId: string): Promise<ExecutionLogEntry[]> {
    return this.logs.get(executionId) ?? [];
  }

  async getRequest(executionId: string): Promise<ExecutionRequest | null> {
    return this.requests.get(executionId) ?? null;
  }

  async listRecent(input: ListRecentExecutionsInput): Promise<ExecutionRecord[]> {
    return [...this.records.values()]
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
      .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
      .slice(0, input.limit);
  }
}
