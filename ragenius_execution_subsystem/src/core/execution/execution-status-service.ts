import type {
  ExecutionLogEntry,
  ExecutionRecord,
  ExecutionScope,
  ExecutionStore,
  ListRecentExecutionsInput
} from "./execution-store.js";
import type { ExecutionRequest } from "../../api/schemas/execution-request.schema.js";

export class ExecutionStatusService {
  constructor(private readonly store: ExecutionStore) {}

  async get(scope: ExecutionScope): Promise<ExecutionRecord | null> {
    return this.store.get(scope);
  }

  async getLogs(scope: ExecutionScope): Promise<ExecutionLogEntry[]> {
    return this.store.getLogs(scope);
  }

  async getRequest(scope: ExecutionScope): Promise<ExecutionRequest | null> {
    return this.store.getRequest(scope);
  }

  async listRecent(input: ListRecentExecutionsInput): Promise<ExecutionRecord[]> {
    return this.store.listRecent(input);
  }

  async getRecentDiagnostics(input: ListRecentExecutionsInput): Promise<{
    items: ExecutionRecord[];
    summary: {
      total_executions: number;
      fallback_executions: number;
      by_execution_path: Record<string, number>;
      by_provider: Record<string, number>;
      by_tool: Record<string, number>;
    };
  }> {
    const items = await this.store.listRecent(input);
    const byExecutionPath: Record<string, number> = {};
    const byProvider: Record<string, number> = {};
    const byTool: Record<string, number> = {};
    let fallbackExecutions = 0;

    for (const item of items) {
      const metadata = item.execution_metadata;
      if (metadata?.used_fallback) {
        fallbackExecutions += 1;
      }
      for (const executionPath of metadata?.execution_paths ?? []) {
        byExecutionPath[executionPath] = (byExecutionPath[executionPath] ?? 0) + 1;
      }
      for (const providerId of metadata?.provider_ids ?? []) {
        byProvider[providerId] = (byProvider[providerId] ?? 0) + 1;
      }
      for (const toolId of metadata?.tool_ids ?? []) {
        byTool[toolId] = (byTool[toolId] ?? 0) + 1;
      }
    }

    return {
      items,
      summary: {
        total_executions: items.length,
        fallback_executions: fallbackExecutions,
        by_execution_path: byExecutionPath,
        by_provider: byProvider,
        by_tool: byTool,
      },
    };
  }
}
