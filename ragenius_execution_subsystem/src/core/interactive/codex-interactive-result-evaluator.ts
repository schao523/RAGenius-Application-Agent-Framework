import type { AgentOperationPlanItem } from "../agents/agent-provider-context.js";

export type CodexMcpToolOutcome = {
  errorCode?: string;
  itemId: string;
  operationId?: string;
  status: "completed" | "failed" | "cancelled" | "denied";
  toolName: string;
};

export type CodexInteractiveOperationVerification = {
  error_code?: string;
  level: "none" | "provider_reported";
  operation: string;
  operation_id: string;
  status: "completed" | "failed" | "not_run";
  tool_name?: string;
};

export function evaluateCodexInteractiveOperations(input: {
  operationPlan: readonly AgentOperationPlanItem[];
  outcomes: readonly CodexMcpToolOutcome[];
}): {
  failureCode: "MCP_OPERATION_BLOCKED" | "AGENT_OPERATION_VERIFICATION_FAILED" | null;
  operationVerification: CodexInteractiveOperationVerification[];
  statusOverride: "completed" | "failed" | "partial";
} {
  const requiredOperationIds = input.operationPlan
    .filter((operation) => operation.required)
    .map((operation) => operation.operation_id);
  const soleRequiredOperationId = requiredOperationIds.length === 1
    ? requiredOperationIds[0]
    : null;
  const operationVerification = input.operationPlan.map((operation) => {
    const matches = input.outcomes.filter(
      (outcome) =>
        outcome.operationId === operation.operation_id ||
        (!outcome.operationId && soleRequiredOperationId === operation.operation_id)
    );
    const failed = matches.find((outcome) => outcome.status !== "completed");
    const completed = matches.find((outcome) => outcome.status === "completed");
    if (failed) {
      return {
        ...(failed.errorCode ? { error_code: failed.errorCode } : {}),
        level: "none" as const,
        operation: operation.description,
        operation_id: operation.operation_id,
        status: "failed" as const,
        tool_name: failed.toolName
      };
    }
    if (completed) {
      return {
        level: "provider_reported" as const,
        operation: operation.description,
        operation_id: operation.operation_id,
        status: "completed" as const,
        tool_name: completed.toolName
      };
    }
    return {
      level: "none" as const,
      operation: operation.description,
      operation_id: operation.operation_id,
      status: "not_run" as const
    };
  });
  const required = input.operationPlan
    .map((operation, index) => ({ operation, verification: operationVerification[index]! }))
    .filter(({ operation }) => operation.required);
  const completedCount = required.filter(
    ({ verification }) => verification.status === "completed"
  ).length;
  const blocked = required.some(({ verification }) => verification.status === "failed");
  if (completedCount === required.length) {
    return { failureCode: null, operationVerification, statusOverride: "completed" };
  }
  return {
    failureCode: blocked ? "MCP_OPERATION_BLOCKED" : "AGENT_OPERATION_VERIFICATION_FAILED",
    operationVerification,
    statusOverride: completedCount > 0 ? "partial" : "failed"
  };
}
