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
  execution_id: string;
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

export interface ExecutionScope {
  appId: string;
  executionId: string;
  sessionId: string;
}

export interface TransitionExecutionInput {
  scope: ExecutionScope;
  from: NormalizedExecutionResult["status"][];
  result: NormalizedExecutionResult;
}

export interface ListRecentExecutionsInput {
  appId: string;
  executionPath?:
    | ToolExecutionProvenance["execution_path"]
    | undefined;
  limit: number;
  sessionId: string;
  usedFallback?: boolean | undefined;
}

export interface ExecutionStore {
  get(scope: ExecutionScope): Promise<ExecutionRecord | null>;
  getLogs(scope: ExecutionScope): Promise<ExecutionLogEntry[]>;
  getRequest(scope: ExecutionScope): Promise<ExecutionRequest | null>;
  listRecent(input: ListRecentExecutionsInput): Promise<ExecutionRecord[]>;
  listByStatuses(
    statuses: NormalizedExecutionResult["status"][]
  ): Promise<ExecutionRecord[]>;
  save(input: SaveExecutionRecordInput): Promise<void>;
  transition(input: TransitionExecutionInput): Promise<boolean>;
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

  async get(scope: ExecutionScope): Promise<ExecutionRecord | null> {
    const record = this.records.get(scope.executionId);
    return record &&
      record.app_id === scope.appId &&
      record.session_id === scope.sessionId
      ? record
      : null;
  }

  async transition(input: TransitionExecutionInput): Promise<boolean> {
    const existing = await this.get(input.scope);
    if (!existing || !input.from.includes(existing.status)) {
      return false;
    }
    const timestamp = new Date().toISOString();
    this.records.set(input.scope.executionId, {
      ...existing,
      ...input.result,
      execution_id: input.scope.executionId,
      updated_at: timestamp
    });
    this.logs.set(input.scope.executionId, [
      ...(this.logs.get(input.scope.executionId) ?? []),
      {
        created_at: timestamp,
        execution_id: input.scope.executionId,
        level: input.result.status === "failed" ? "error" : "info",
        message: input.result.logs_summary
      }
    ]);
    return true;
  }

  async getLogs(scope: ExecutionScope): Promise<ExecutionLogEntry[]> {
    return (await this.get(scope)) ? (this.logs.get(scope.executionId) ?? []) : [];
  }

  async getRequest(scope: ExecutionScope): Promise<ExecutionRequest | null> {
    return (await this.get(scope))
      ? (this.requests.get(scope.executionId) ?? null)
      : null;
  }

  async listRecent(input: ListRecentExecutionsInput): Promise<ExecutionRecord[]> {
    return [...this.records.values()]
      .filter((record) => {
        if (
          record.app_id !== input.appId ||
          record.session_id !== input.sessionId
        ) {
          return false;
        }
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

  async listByStatuses(
    statuses: NormalizedExecutionResult["status"][]
  ): Promise<ExecutionRecord[]> {
    return [...this.records.values()].filter((record) => statuses.includes(record.status));
  }
}
