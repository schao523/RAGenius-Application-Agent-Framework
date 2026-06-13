import type {
  ExecutionMetadata,
  NormalizedError,
  NormalizedExecutionResult,
  ResultType
} from "../../api/schemas/common-response.schema.js";
import type { ToolExecutionProvenance } from "../tools/tool.types.js";

export function normalizeCompletedResult(options: {
  executionId: string | null;
  resultType: ResultType;
  result: Record<string, unknown>;
  executionProvenance?: ToolExecutionProvenance[];
  executionMetadata?: ExecutionMetadata;
  files?: Array<Record<string, unknown>>;
  logsSummary: string;
}): NormalizedExecutionResult {
  return {
    execution_id: options.executionId,
    status: "completed",
    result_type: options.resultType,
    result: options.result,
    ...(options.executionProvenance && options.executionProvenance.length > 0
      ? { execution_provenance: options.executionProvenance }
      : {}),
    ...(options.executionMetadata
      ? { execution_metadata: options.executionMetadata }
      : {}),
    files: options.files ?? [],
    errors: [],
    logs_summary: options.logsSummary
  };
}

export function normalizeFailedResult(options: {
  executionId: string | null;
  error: NormalizedError;
  logsSummary: string;
}): NormalizedExecutionResult {
  return {
    execution_id: options.executionId,
    status: "failed",
    result_type: "json",
    result: {},
    files: [],
    errors: [options.error],
    logs_summary: options.logsSummary
  };
}

export function normalizePendingConfirmationResult(options: {
  executionId: string | null;
  toolId: string;
  permissionScope: string;
  logsSummary: string;
  resultDetails?: Record<string, unknown>;
}): NormalizedExecutionResult {
  return {
    execution_id: options.executionId,
    status: "pending_confirmation",
    result_type: "json",
    result: {
      required_confirmation: true,
      tool_id: options.toolId,
      permission_scope: options.permissionScope,
      ...(options.resultDetails ?? {})
    },
    files: [],
    errors: [],
    logs_summary: options.logsSummary
  };
}
