import type { AgentProviderExecutionContext } from "./agent-provider-context.js";
import type { AgentProviderResult } from "./agent-provider.js";
import { mergeAgentDiagnostics, primaryDiagnosticFromLegacy } from "./agent-diagnostics.js";
import type { TrustedOperationVerification } from "./agent-operation-verifier.js";
import type { OperationVerification } from "./codex-cli-types.js";

const evidenceRank = {
  none: 0,
  process_observed: 1,
  provider_reported: 2,
  independently_verified: 3
} as const;

const evidenceOnlyFailureCodes = new Set([
  "CODEX_OPERATION_PARTIAL",
  "CODEX_OPERATION_VERIFICATION_FAILED",
  "CODEX_REQUIRED_OPERATION_NOT_RUN",
  "AGENT_OPERATION_VERIFICATION_FAILED"
]);

function operationRecords(value: unknown[] | undefined): OperationVerification[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is OperationVerification => Boolean(
    item && typeof item === "object" &&
    typeof (item as OperationVerification).operation_id === "string" &&
    typeof (item as OperationVerification).level === "string"
  ));
}

export async function finalizeAgentResult(input: {
  context: AgentProviderExecutionContext;
  result: AgentProviderResult;
  trustedVerification: TrustedOperationVerification[];
}): Promise<AgentProviderResult> {
  const reported = operationRecords(input.result.operation_verification);
  if (reported.length === 0) {
    return {
      ...input.result,
      verification_results: [
        ...(input.result.verification_results ?? []),
        ...input.trustedVerification
      ]
    };
  }

  const reconciled = input.context.operation_plan.map((plan) => {
    const providerRecord = reported.find(
      (candidate) => candidate.operation_id === plan.operation_id
    ) ?? {
      operation_id: plan.operation_id,
      operation: plan.description,
      level: "none" as const,
      status: "not_run" as const
    };
    const trusted = input.trustedVerification.find(
      (candidate) =>
        candidate.operation_id === plan.operation_id &&
        candidate.status === "completed" &&
        candidate.level === "independently_verified"
    );
    return trusted ?? providerRecord;
  });
  const required = input.context.operation_plan
    .map((plan, index) => ({ plan, evidence: reconciled[index]! }))
    .filter(({ plan }) => plan.required);
  const met = required.filter(({ plan, evidence }) =>
    !["failed", "not_run"].includes(evidence.status) &&
    evidenceRank[evidence.level] >= evidenceRank[plan.minimum_verification]
  );
  const primary = primaryDiagnosticFromLegacy(input.result.diagnostics);
  const fatalProviderFailure = input.result.status === "failed" &&
    Boolean(primary?.code) && !evidenceOnlyFailureCodes.has(primary!.code);
  if (fatalProviderFailure) {
    return {
      ...input.result,
      operation_verification: reconciled,
      verification_results: [
        ...(input.result.verification_results ?? []),
        ...input.trustedVerification
      ]
    };
  }

  const { diagnostics: _diagnostics, ...withoutDiagnostics } = input.result;
  if (met.length === required.length) {
    return {
      ...withoutDiagnostics,
      status: "completed",
      operation_verification: reconciled,
      verification_results: [
        ...(input.result.verification_results ?? []),
        ...input.trustedVerification
      ]
    };
  }

  const status = met.length > 0 ? "partial" : "failed";
  return {
    ...withoutDiagnostics,
    status,
    operation_verification: reconciled,
    verification_results: [
      ...(input.result.verification_results ?? []),
      ...input.trustedVerification
    ],
    diagnostics: mergeAgentDiagnostics({
      code: status === "partial"
        ? "AGENT_OPERATION_PARTIAL"
        : "AGENT_OPERATION_VERIFICATION_FAILED",
      message: status === "partial"
        ? "Some required agent operations lack trusted evidence."
        : "Required agent operation evidence did not meet policy."
    }, [])
  };
}
