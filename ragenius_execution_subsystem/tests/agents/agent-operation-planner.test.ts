import assert from "node:assert/strict";
import test from "node:test";

import {
  createAgentOperationPlan,
  fingerprintAgentPolicy
} from "../../src/core/agents/agent-operation-planner.js";
import type { AgentPolicyDecision } from "../../src/core/agents/agent-policy.js";

const externalWritePolicy: AgentPolicyDecision = {
  riskClass: "agent_external_write",
  mode: "require_confirmation",
  permissionScope: "agent.external_write",
  workspaceAccess: "none",
  providerStateAccess: "scoped_write",
  providerStateLabels: ["notebooklm_profile:default"],
  networkAccess: "allowlisted",
  reason: "External write agent requests require confirmation.",
  matchedTerms: ["add", "create"]
};

test("plans NotebookLM source add and report generation separately", () => {
  const plan = createAgentOperationPlan(
    {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "session_001",
      agent_backend: "codex_cli",
      agent_skill_hint: "notebooklm",
      agent_query:
        "Add the selected artifact as a source to Testing, then create a study report."
    },
    externalWritePolicy
  );

  assert.deepEqual(
    plan.map((item) => item.operation_id),
    ["notebooklm_source_add", "notebooklm_report_generate"]
  );
  assert.equal(plan[0]?.minimum_verification, "independently_verified");
  assert.equal(plan[1]?.minimum_verification, "provider_reported");
  assert.equal(plan.every((item) => item.required), true);
});

test("plans one verifiable generic mutation for an unknown external write", () => {
  const request = {
    request_type: "execute_agent" as const,
    app_id: "app_001",
    session_id: "session_001",
    agent_backend: "codex_cli" as const,
    agent_query: "Publish the approved content to the configured destination."
  };

  const plan = createAgentOperationPlan(request, externalWritePolicy);

  assert.deepEqual(plan, [
    {
      operation_id: "agent_external_write",
      kind: "external_write",
      description: request.agent_query,
      required: true,
      minimum_verification: "provider_reported"
    }
  ]);
});

test("plans a process-observed read operation for read-only requests", () => {
  const plan = createAgentOperationPlan(
    {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "session_001",
      agent_backend: "codex_cli",
      agent_query: "Explain the selected content."
    },
    {
      riskClass: "agent_read_only",
      mode: "auto_allow",
      permissionScope: "agent.read",
      workspaceAccess: "none",
      providerStateAccess: "none",
      providerStateLabels: [],
      networkAccess: "allowlisted",
      reason: "Read-only agent requests are auto-allowed.",
      matchedTerms: []
    }
  );

  assert.deepEqual(plan, [
    {
      operation_id: "agent_read",
      kind: "read",
      description: "Explain the selected content.",
      required: true,
      minimum_verification: "process_observed"
    }
  ]);
});

test("fingerprint is stable across object key order", () => {
  assert.equal(
    fingerprintAgentPolicy({ mode: "require_confirmation", operation_plan: [] }),
    fingerprintAgentPolicy({ operation_plan: [], mode: "require_confirmation" })
  );
});

test("fingerprint changes when the operation plan changes", () => {
  assert.notEqual(
    fingerprintAgentPolicy({
      mode: "require_confirmation",
      operation_plan: [{ operation_id: "source_add" }]
    }),
    fingerprintAgentPolicy({
      mode: "require_confirmation",
      operation_plan: [{ operation_id: "report_generate" }]
    })
  );
});
