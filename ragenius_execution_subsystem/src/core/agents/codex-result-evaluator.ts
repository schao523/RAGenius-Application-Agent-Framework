import type { AgentProviderExecutionContext } from "./agent-provider-context.js";
import type { AgentOperationPlanItem } from "./agent-provider-context.js";
import { mergeAgentDiagnostics } from "./agent-diagnostics.js";
import type {
  CodexAgentTaskOperation,
  CodexAgentTaskResult,
  CodexCliArtifactSummary,
  CodexCliCommandEvent,
  CodexCliProtocolResult,
  CodexNormalizedResult,
  CodexStagedArtifact,
  OperationVerification
} from "./codex-cli-types.js";

const taskStatuses = new Set([
  "completed",
  "partial",
  "failed",
  "pending_confirmation"
]);
const operationStatuses = new Set([
  "completed",
  "accepted",
  "processing",
  "failed",
  "not_run"
]);
const evidenceRank = {
  none: 0,
  process_observed: 1,
  provider_reported: 2,
  independently_verified: 3
} as const;

function strings(value: unknown): string[] | null {
  return Array.isArray(value) && value.every((item) => typeof item === "string")
    ? value
    : null;
}

function parseOperations(value: unknown): CodexAgentTaskOperation[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const operations: CodexAgentTaskOperation[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") {
      return null;
    }
    const record = item as Record<string, unknown>;
    if (
      typeof record.operation_id !== "string" ||
      typeof record.operation !== "string" ||
      typeof record.status !== "string" ||
      !operationStatuses.has(record.status)
    ) {
      return null;
    }
    operations.push({
      operation_id: record.operation_id,
      operation: record.operation,
      status: record.status as CodexAgentTaskOperation["status"],
      ...(typeof record.target === "string" ? { target: record.target } : {}),
      ...(typeof record.external_id === "string" && record.external_id.trim()
        ? { external_id: record.external_id.trim() }
        : {}),
      ...(typeof record.evidence === "string" && record.evidence.trim()
        ? { evidence: record.evidence.trim() }
        : {})
    });
  }
  return operations;
}

function parseFinalResult(value: string): {
  status: "parsed" | "invalid" | "missing";
  result?: CodexAgentTaskResult;
} {
  if (!value.trim()) {
    return { status: "missing" };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    return { status: "invalid" };
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { status: "invalid" };
  }
  const record = parsed as Record<string, unknown>;
  const activatedSkills = strings(record.activated_skills);
  const operations = parseOperations(record.operations);
  if (
    typeof record.task_status !== "string" ||
    !taskStatuses.has(record.task_status) ||
    typeof record.summary !== "string" ||
    !activatedSkills ||
    !operations ||
    !Array.isArray(record.artifacts) ||
    !Array.isArray(record.errors)
  ) {
    return { status: "invalid" };
  }
  if (new Set(operations.map((item) => item.operation_id)).size !== operations.length) {
    return { status: "invalid" };
  }
  return {
    status: "parsed",
    result: {
      task_status: record.task_status as CodexAgentTaskResult["task_status"],
      summary: record.summary,
      activated_skills: activatedSkills,
      operations,
      artifacts: record.artifacts as CodexCliArtifactSummary[],
      errors: record.errors as Array<{ code: string; message: string }>
    }
  };
}

function successful(command: CodexCliCommandEvent): boolean {
  return command.exit_code === 0;
}

function relevantCommand(plan: AgentOperationPlanItem, command: string): boolean {
  const normalized = command.toLowerCase();
  if (plan.operation_id === "notebooklm_source_add") {
    return normalized.includes("notebooklm") && normalized.includes("source") && normalized.includes("add");
  }
  if (plan.operation_id === "notebooklm_report_generate") {
    return normalized.includes("notebooklm") && /report|study|briefing|slide|video/.test(normalized);
  }
  return true;
}

function verificationFor(
  plan: AgentOperationPlanItem,
  operation: CodexAgentTaskOperation | undefined,
  commands: CodexCliCommandEvent[],
  readTurnCompleted: boolean,
  providerBackedRead: boolean
): OperationVerification {
  const relevantSuccessfulCommand = commands.some(
    (command) => successful(command) && relevantCommand(plan, command.command)
  );
  if (!operation) {
    if (
      plan.kind === "read" &&
      readTurnCompleted &&
      (!providerBackedRead || relevantSuccessfulCommand)
    ) {
      return {
        operation_id: plan.operation_id,
        operation: plan.description,
        level: "process_observed",
        status: "completed"
      };
    }
    return {
      operation_id: plan.operation_id,
      operation: plan.description,
      level: "none",
      status: "not_run"
    };
  }
  const observed =
    (plan.kind === "read" &&
      readTurnCompleted &&
      (!providerBackedRead || relevantSuccessfulCommand)) ||
    relevantSuccessfulCommand;
  let level: OperationVerification["level"] = observed ? "process_observed" : "none";
  if (operation.external_id) {
    level = "provider_reported";
  }
  return {
    operation_id: plan.operation_id,
    operation: operation.operation,
    level,
    status: operation.status,
    ...(operation.external_id ? { external_id: operation.external_id } : {}),
    ...(operation.evidence ? { evidence: operation.evidence } : {})
  };
}

function meetsMinimum(
  plan: AgentOperationPlanItem,
  verification: OperationVerification
): boolean {
  return (
    !["failed", "not_run"].includes(verification.status) &&
    evidenceRank[verification.level] >= evidenceRank[plan.minimum_verification]
  );
}

function failedResult(
  base: Omit<CodexNormalizedResult, "status" | "diagnostics">,
  code: string,
  message: string
): CodexNormalizedResult {
  return {
    ...base,
    status: "failed",
    diagnostics: mergeAgentDiagnostics({ code, message }, [])
  };
}

export function evaluateCodexResult(input: {
  context: AgentProviderExecutionContext;
  protocol: CodexCliProtocolResult;
  stagedInputs?: CodexStagedArtifact[];
  agentSkillHint?: string;
}): CodexNormalizedResult {
  const parsed = parseFinalResult(input.protocol.final_message);
  const task = parsed.result;
  const operationById = new Map(
    (task?.operations ?? []).map((operation) => [operation.operation_id, operation])
  );
  const providerBackedRead = Boolean(input.agentSkillHint?.trim());
  const verification = input.context.operation_plan.map((plan) =>
    verificationFor(
      plan,
      operationById.get(plan.operation_id),
      input.protocol.command_events,
      input.protocol.turn_status === "completed" && Boolean(input.protocol.final_message.trim()),
      providerBackedRead
    )
  );
  const successfulCommands = input.protocol.command_events.filter(successful).length;
  const base = {
    backend: "codex_cli" as const,
    summary: task?.summary || input.protocol.final_message.trim() || "Codex did not complete the request.",
    activated_skills: task?.activated_skills ?? [],
    staged_inputs: input.stagedInputs ?? [],
    operation_verification: verification,
    artifacts: [],
    reported_outputs: task?.artifacts ?? [],
    provider_metadata: {
      ...(input.protocol.thread_id ? { thread_id: input.protocol.thread_id } : {}),
      turn_status: input.protocol.turn_status,
      raw_exit_code: input.protocol.raw_exit_code,
      confirmation_state: input.context.authorization.state,
      permission_scope: input.context.authorization.permission_scope,
      policy_fingerprint: input.context.authorization.policy_fingerprint,
      command_count: input.protocol.command_events.length,
      successful_command_count: successfulCommands,
      final_json_status: parsed.status
    }
  };

  if (input.protocol.raw_exit_code !== 0 || input.protocol.turn_status === "failed") {
    return failedResult(base, "CODEX_CLI_EXECUTION_FAILED", "Codex CLI execution failed.");
  }
  if (task?.task_status === "failed") {
    return failedResult(base, "CODEX_TASK_FAILED", task.summary);
  }
  if (
    task?.task_status === "pending_confirmation" &&
    input.context.authorization.state === "confirmed"
  ) {
    return failedResult(
      base,
      "CODEX_UNEXPECTED_CONFIRMATION_REQUEST",
      "Codex requested confirmation after RAGenius had already confirmed the operation."
    );
  }

  const mutationPlan = input.context.operation_plan.some((plan) => plan.kind !== "read");
  if (parsed.status !== "parsed" && mutationPlan) {
    return failedResult(base, "CODEX_FINAL_RESULT_INVALID", "Codex did not return a valid structured mutation result.");
  }

  if (
    providerBackedRead &&
    input.context.operation_plan.some((plan) => plan.kind === "read" && plan.required) &&
    !input.protocol.command_events.some(successful)
  ) {
    return failedResult(
      base,
      "AGENT_PROVIDER_EVIDENCE_MISSING",
      "Provider-backed read completed without a successful provider command."
    );
  }

  const required = input.context.operation_plan
    .map((plan, index) => ({ plan, verification: verification[index]! }))
    .filter(({ plan }) => plan.required);
  const met = required.filter(({ plan, verification: item }) => meetsMinimum(plan, item));
  if (met.length === required.length) {
    const processing = verification.some((item) => ["accepted", "processing"].includes(item.status));
    return {
      ...base,
      status: "completed",
      summary: processing
        ? "Generation started; external output is still processing."
        : base.summary
    };
  }
  if (met.length > 0) {
    return {
      ...base,
      status: "partial",
      diagnostics: mergeAgentDiagnostics(
        {
          code: "CODEX_OPERATION_PARTIAL",
          message: "Some required Codex operations did not complete."
        },
        []
      )
    };
  }
  const hasReportedEvidence = verification.some((item) => item.level !== "none");
  return failedResult(
    base,
    hasReportedEvidence
      ? "CODEX_OPERATION_VERIFICATION_FAILED"
      : "CODEX_REQUIRED_OPERATION_NOT_RUN",
    hasReportedEvidence
      ? "Required operation evidence did not meet the verification policy."
      : "Required operation was not run."
  );
}
