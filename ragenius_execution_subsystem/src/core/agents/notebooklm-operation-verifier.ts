import type { NotebookLmOperation } from "../tools/providers/notebooklm-types.js";

import type {
  AgentOperationVerifier,
  AgentVerificationInput,
  TrustedOperationVerification
} from "./agent-operation-verifier.js";

type NotebookLmVerificationAdapter = {
  execute(
    operation: NotebookLmOperation,
    input: Record<string, unknown>,
    options?: {
      appId: string;
      sessionId?: string;
      executionId?: string | null;
    }
  ): Promise<Record<string, unknown>>;
};

function boundedEvidence(value: unknown): string {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  return text.length <= 240 ? text : `${text.slice(0, 237)}...`;
}

function recordId(value: unknown): string | undefined {
  if (!value || typeof value !== "object") {
    return undefined;
  }
  const record = value as Record<string, unknown>;
  for (const key of ["id", "source_id", "task_id", "artifact_id"]) {
    if (typeof record[key] === "string" && record[key].trim()) {
      return record[key].trim();
    }
  }
  return undefined;
}

export class NotebookLmOperationVerifier implements AgentOperationVerifier {
  readonly id = "notebooklm";

  constructor(
    private readonly adapter: NotebookLmVerificationAdapter,
    private readonly now: () => Date = () => new Date()
  ) {}

  supports(input: AgentVerificationInput): boolean {
    return input.request.agent_skill_hint?.trim().toLowerCase() === "notebooklm";
  }

  async verify(
    input: AgentVerificationInput
  ): Promise<TrustedOperationVerification[]> {
    const results: TrustedOperationVerification[] = [];
    for (const plan of input.context.operation_plan) {
      if (
        plan.operation_id !== "notebooklm_source_add" &&
        plan.operation_id !== "notebooklm_report_generate"
      ) {
        continue;
      }
      const reported = input.reportedVerification.find(
        (candidate) => candidate.operation_id === plan.operation_id
      );
      if (!reported?.external_id || !plan.target_hint) {
        results.push(this.failed(plan.operation_id, plan.description, reported?.external_id,
          "Stable external ID or server-owned notebook target is missing."));
        continue;
      }
      try {
        if (plan.operation_id === "notebooklm_source_add") {
          const response = await this.adapter.execute(
            "list_sources",
            { notebookTitle: plan.target_hint },
            {
              appId: input.request.app_id,
              sessionId: input.request.session_id,
              executionId: input.context.execution_id
            }
          );
          const sources = Array.isArray(response.sources) ? response.sources : [];
          const found = sources.some((source) => recordId(source) === reported.external_id);
          results.push(found
            ? this.verified(plan.operation_id, plan.description, reported.external_id,
                `Source ${reported.external_id} exists in the resolved notebook.`)
            : this.failed(plan.operation_id, plan.description, reported.external_id,
                "Reported source ID was not found in the resolved notebook."));
          continue;
        }

        const response = await this.adapter.execute(
          "poll_artifact_task",
          {
            notebookTitle: plan.target_hint,
            taskId: reported.external_id,
            artifactKind: "report"
          },
          {
            appId: input.request.app_id,
            sessionId: input.request.session_id,
            executionId: input.context.execution_id
          }
        );
        const responseId = recordId(response);
        const status = String(response.status ?? "").trim().toLowerCase();
        const complete = responseId === reported.external_id &&
          ["completed", "complete", "ready", "succeeded"].includes(status);
        results.push(complete
          ? this.verified(plan.operation_id, plan.description, reported.external_id,
              `Artifact task ${reported.external_id} completed.`)
          : this.failed(plan.operation_id, plan.description, reported.external_id,
              `Artifact task status is ${status || "unknown"}.`));
      } catch (error) {
        results.push(this.failed(
          plan.operation_id,
          plan.description,
          reported.external_id,
          error instanceof Error ? error.message : String(error)
        ));
      }
    }
    return results;
  }

  private verified(
    operationId: string,
    operation: string,
    externalId: string,
    evidence: string
  ): TrustedOperationVerification {
    return {
      operation_id: operationId,
      operation,
      level: "independently_verified",
      status: "completed",
      external_id: externalId,
      evidence: boundedEvidence(evidence),
      verifier: "execution_subsystem_adapter",
      checked_at: this.now().toISOString()
    };
  }

  private failed(
    operationId: string,
    operation: string,
    externalId: string | undefined,
    evidence: string
  ): TrustedOperationVerification {
    return {
      operation_id: operationId,
      operation,
      level: "none",
      status: "failed",
      ...(externalId ? { external_id: externalId } : {}),
      evidence: boundedEvidence(evidence),
      verifier: "execution_subsystem_adapter",
      checked_at: this.now().toISOString()
    };
  }
}
