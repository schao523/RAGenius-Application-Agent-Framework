import assert from "node:assert/strict";
import test from "node:test";

import { evaluateCodexResult } from "../../src/core/agents/codex-result-evaluator.js";
import type { AgentProviderExecutionContext } from "../../src/core/agents/agent-provider-context.js";
import type { CodexCliProtocolResult } from "../../src/core/agents/codex-cli-types.js";

function context(
  operationPlan: AgentProviderExecutionContext["operation_plan"],
  state: "not_required" | "confirmed" = "confirmed"
): AgentProviderExecutionContext {
  return {
    execution_id: "execution_123",
    authorization: {
      state,
      permission_scope: state === "confirmed" ? "agent.external_write" : "agent.read",
      policy_fingerprint: "a".repeat(64)
    },
    operation_plan: operationPlan,
    resolved_artifacts: [],
    expected_outputs: []
  };
}

function protocol(
  final: unknown,
  overrides: Partial<CodexCliProtocolResult> = {}
): CodexCliProtocolResult {
  return {
    turn_status: "completed",
    final_message: typeof final === "string" ? final : JSON.stringify(final),
    command_events: [],
    errors: [],
    raw_exit_code: 0,
    malformed_line_count: 0,
    stdout_truncated: false,
    stderr_truncated: false,
    ...overrides
  };
}

const sourcePlan = {
  operation_id: "notebooklm_source_add",
  kind: "external_write" as const,
  description: "Add source.",
  required: true,
  minimum_verification: "independently_verified" as const
};
const reportPlan = {
  operation_id: "notebooklm_report_generate",
  kind: "external_write" as const,
  description: "Generate report.",
  required: true,
  minimum_verification: "provider_reported" as const
};

test("exit zero plus pending confirmation after approval fails", () => {
  const result = evaluateCodexResult({
    context: context([sourcePlan]),
    protocol: protocol({
      task_status: "pending_confirmation",
      summary: "Please confirm.",
      activated_skills: ["notebooklm"],
      operations: [],
      artifacts: [],
      errors: []
    })
  });

  assert.equal(result.status, "failed");
  assert.equal(result.diagnostics?.failure_code, "CODEX_UNEXPECTED_CONFIRMATION_REQUEST");
});

test("exit zero plus no mutation evidence fails", () => {
  const result = evaluateCodexResult({
    context: context([sourcePlan]),
    protocol: protocol({
      task_status: "completed",
      summary: "Done.",
      activated_skills: ["notebooklm"],
      operations: [{
        operation_id: "notebooklm_source_add",
        operation: "add source",
        status: "completed"
      }],
      artifacts: [],
      errors: []
    })
  });

  assert.equal(result.status, "failed");
  assert.equal(result.diagnostics?.failure_code, "CODEX_REQUIRED_OPERATION_NOT_RUN");
});

test("one provider-reported operation and one missing operation remains failed", () => {
  const result = evaluateCodexResult({
    context: context([sourcePlan, reportPlan]),
    protocol: protocol(
      {
        task_status: "partial",
        summary: "Source added; report not started.",
        activated_skills: ["notebooklm"],
        operations: [{
          operation_id: "notebooklm_source_add",
          operation: "add source",
          status: "completed",
          external_id: "source_123"
        }],
        artifacts: [],
        errors: []
      },
      {
        command_events: [
          {
            item_id: "cmd_1",
            command: "python -m notebooklm source add",
            exit_code: 0,
            stdout_summary: "created source_123"
          },
          {
            item_id: "cmd_2",
            command: "python -m notebooklm source list",
            exit_code: 0,
            stdout_summary: "source_123 Approved notes"
          }
        ]
      }
    )
  });

  assert.equal(result.status, "failed");
  assert.equal(result.operation_verification[0]?.level, "provider_reported");
  assert.equal(result.operation_verification[1]?.status, "not_run");
});

test("transcript evidence cannot independently verify a source", () => {
  const result = evaluateCodexResult({
    context: context([sourcePlan, reportPlan]),
    protocol: protocol(
      {
        task_status: "completed",
        summary: "Everything is complete.",
        activated_skills: ["notebooklm"],
        operations: [
          {
            operation_id: "notebooklm_source_add",
            operation: "add source",
            status: "completed",
            external_id: "source_123"
          },
          {
            operation_id: "notebooklm_report_generate",
            operation: "generate report",
            status: "accepted",
            external_id: "job_456"
          }
        ],
        artifacts: [],
        errors: []
      },
      {
        command_events: [
          {
            item_id: "cmd_1",
            command: "python -m notebooklm source add",
            exit_code: 0,
            stdout_summary: "created source_123"
          },
          {
            item_id: "cmd_2",
            command: "python -m notebooklm source list",
            exit_code: 0,
            stdout_summary: "source_123 Approved notes"
          },
          {
            item_id: "cmd_3",
            command: "python -m notebooklm report generate",
            exit_code: 0,
            stdout_summary: "accepted job_456"
          }
        ]
      }
    )
  });

  assert.equal(result.status, "partial");
  assert.equal(result.operation_verification[0]?.level, "provider_reported");
  assert.equal(result.operation_verification[1]?.level, "provider_reported");
});

test("turn failure overrides structured completion", () => {
  const result = evaluateCodexResult({
    context: context([sourcePlan]),
    protocol: protocol(
      {
        task_status: "completed",
        summary: "Done.",
        activated_skills: [],
        operations: [],
        artifacts: [],
        errors: []
      },
      { turn_status: "failed" }
    )
  });

  assert.equal(result.status, "failed");
});

test("read-only final text remains backward compatible", () => {
  const result = evaluateCodexResult({
    context: context([{
      operation_id: "agent_read",
      kind: "read",
      description: "Explain.",
      required: true,
      minimum_verification: "process_observed"
    }], "not_required"),
    protocol: protocol("A concise explanation.")
  });

  assert.equal(result.status, "completed");
  assert.equal(result.summary, "A concise explanation.");
  assert.equal(result.provider_metadata.final_json_status, "invalid");
});

test("provider-backed reads require a successful relevant command", () => {
  const result = evaluateCodexResult({
    context: context([{
      operation_id: "agent_read",
      kind: "read",
      description: "List NotebookLM notebooks.",
      required: true,
      minimum_verification: "process_observed"
    }], "not_required"),
    agentSkillHint: "notebooklm",
    protocol: protocol("I found several notebooks.")
  });

  assert.equal(result.status, "failed");
  assert.equal(
    result.diagnostics?.primary?.code,
    "AGENT_PROVIDER_EVIDENCE_MISSING"
  );
});

test("unknown operation ids cannot satisfy the plan", () => {
  const result = evaluateCodexResult({
    context: context([sourcePlan]),
    protocol: protocol({
      task_status: "completed",
      summary: "Done.",
      activated_skills: [],
      operations: [{
        operation_id: "unauthorized_operation",
        operation: "add source",
        status: "completed",
        external_id: "source_123"
      }],
      artifacts: [],
      errors: []
    })
  });

  assert.equal(result.status, "failed");
  assert.equal(result.operation_verification[0]?.status, "not_run");
});
