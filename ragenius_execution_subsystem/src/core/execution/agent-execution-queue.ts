import type { ExecutionRequest } from "../../api/schemas/execution-request.schema.js";
import type { NormalizedExecutionResult } from "../../api/schemas/common-response.schema.js";

import type { ApprovedConfirmation } from "./confirmation-service.js";
import type { ExecutionRecord, ExecutionScope, ExecutionStore } from "./execution-store.js";

type QueueItem = {
  executionId: string;
  request: ExecutionRequest;
  approvedConfirmation?: ApprovedConfirmation;
};

type QueueExecutor = (
  request: ExecutionRequest,
  options: { executionId: string; approvedConfirmation?: ApprovedConfirmation }
) => Promise<NormalizedExecutionResult>;

function stateResult(
  executionId: string,
  status: "queued" | "running",
  message: string
): NormalizedExecutionResult {
  return {
    execution_id: executionId,
    status,
    result_type: "json",
    result: {},
    files: [],
    errors: [],
    logs_summary: message
  };
}

function interruptedResult(executionId: string): NormalizedExecutionResult {
  return {
    execution_id: executionId,
    status: "failed",
    result_type: "json",
    result: {},
    files: [],
    errors: [{
      code: "AGENT_EXECUTION_INTERRUPTED",
      message: "Agent execution was interrupted before reaching a terminal state.",
      recoverable: true,
      suggested_action: "Retry the agent execution."
    }],
    logs_summary: "Agent execution was interrupted during service restart."
  };
}

export class AgentExecutionQueue {
  private readonly pending: QueueItem[] = [];
  private readonly enqueueOperations = new Map<string, Promise<ExecutionRecord>>();
  private readonly scheduled = new Set<string>();
  private active = 0;
  private started = false;

  constructor(
    private readonly store: ExecutionStore,
    private readonly execute: QueueExecutor,
    private readonly concurrency = 1
  ) {}

  start(): void {
    this.started = true;
    this.drain();
  }

  stop(): void {
    this.started = false;
  }

  async enqueue(item: QueueItem): Promise<ExecutionRecord> {
    const existingOperation = this.enqueueOperations.get(item.executionId);
    if (existingOperation) {
      return existingOperation;
    }
    const operation = this.persistAndSchedule(item).finally(() => {
      this.enqueueOperations.delete(item.executionId);
    });
    this.enqueueOperations.set(item.executionId, operation);
    return operation;
  }

  async reconcileInterrupted(): Promise<number> {
    const interrupted = await this.store.listByStatuses([
      "queued",
      "running",
      "waiting_for_interaction"
    ]);
    let reconciled = 0;
    for (const record of interrupted) {
      const transitioned = await this.store.transition({
        scope: this.scope(record),
        from: ["queued", "running", "waiting_for_interaction"],
        result: interruptedResult(record.execution_id)
      });
      if (transitioned) {
        reconciled += 1;
      }
    }
    return reconciled;
  }

  private async persistAndSchedule(item: QueueItem): Promise<ExecutionRecord> {
    const scope: ExecutionScope = {
      appId: item.request.app_id,
      sessionId: item.request.session_id,
      executionId: item.executionId
    };
    const existing = await this.store.get(scope);
    if (existing && !["pending_confirmation", "queued", "running"].includes(existing.status)) {
      return existing;
    }
    if (!existing) {
      await this.store.save({
        executionId: item.executionId,
        request: item.request,
        result: stateResult(item.executionId, "queued", "Agent execution is queued.")
      });
    } else if (existing.status === "pending_confirmation") {
      await this.store.transition({
        scope,
        from: ["pending_confirmation"],
        result: stateResult(item.executionId, "queued", "Confirmed agent execution is queued.")
      });
    }
    const queuedRecord = (await this.store.get(scope))!;
    if (!this.scheduled.has(item.executionId) && existing?.status !== "running") {
      this.scheduled.add(item.executionId);
      this.pending.push(item);
      this.drain();
    }
    return queuedRecord;
  }

  private drain(): void {
    while (this.started && this.active < this.concurrency && this.pending.length > 0) {
      const item = this.pending.shift()!;
      this.active += 1;
      void this.run(item).finally(() => {
        this.active -= 1;
        this.scheduled.delete(item.executionId);
        this.drain();
      });
    }
  }

  private async run(item: QueueItem): Promise<void> {
    const scope = {
      appId: item.request.app_id,
      sessionId: item.request.session_id,
      executionId: item.executionId
    };
    const claimed = await this.store.transition({
      scope,
      from: ["queued"],
      result: stateResult(item.executionId, "running", "Agent execution is running.")
    });
    if (!claimed) {
      return;
    }
    try {
      await this.execute(item.request, {
        executionId: item.executionId,
        ...(item.approvedConfirmation
          ? { approvedConfirmation: item.approvedConfirmation }
          : {})
      });
    } catch (error) {
      await this.store.transition({
        scope,
        from: ["running"],
        result: {
          ...interruptedResult(item.executionId),
          errors: [{
            code: "AGENT_EXECUTION_FAILED",
            message: error instanceof Error ? error.message : String(error),
            recoverable: true,
            suggested_action: "Inspect execution diagnostics and retry."
          }],
          logs_summary: "Queued agent execution failed."
        }
      });
    }
  }

  private scope(record: ExecutionRecord): ExecutionScope {
    return {
      appId: record.app_id,
      sessionId: record.session_id,
      executionId: record.execution_id
    };
  }
}
