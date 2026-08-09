import assert from "node:assert/strict";
import test from "node:test";

import { finalizeAgentResult } from "../../src/core/agents/agent-result-finalizer.js";

const context = {
  execution_id: "execution_001",
  authorization: {
    state: "confirmed" as const,
    permission_scope: "agent.external_write",
    policy_fingerprint: "a".repeat(64)
  },
  operation_plan: [{
    operation_id: "notebooklm_source_add",
    kind: "external_write" as const,
    description: "Add source.",
    required: true,
    minimum_verification: "independently_verified" as const
  }],
  resolved_artifacts: [],
  expected_outputs: []
};

test("provider-reported evidence cannot satisfy independent verification", async () => {
  const result = await finalizeAgentResult({
    context,
    result: {
      status: "completed",
      operation_verification: [{
        operation_id: "notebooklm_source_add",
        operation: "Add source.",
        level: "provider_reported",
        status: "completed",
        external_id: "source_123"
      }]
    },
    trustedVerification: []
  });

  assert.equal(result.status, "failed");
});

test("trusted adapter evidence raises the operation to independently verified", async () => {
  const result = await finalizeAgentResult({
    context,
    result: {
      status: "failed",
      operation_verification: [{
        operation_id: "notebooklm_source_add",
        operation: "Add source.",
        level: "provider_reported",
        status: "completed",
        external_id: "source_123"
      }],
      diagnostics: {
        failure_code: "CODEX_OPERATION_VERIFICATION_FAILED",
        failure_message: "Insufficient evidence."
      }
    },
    trustedVerification: [{
      operation_id: "notebooklm_source_add",
      operation: "Add source.",
      level: "independently_verified",
      status: "completed",
      external_id: "source_123",
      verifier: "execution_subsystem_adapter",
      checked_at: "2026-08-03T00:00:00.000Z"
    }]
  });

  assert.equal(result.status, "completed");
  assert.equal(
    (result.operation_verification?.[0] as { level?: string }).level,
    "independently_verified"
  );
});

test("normalizes successful explicit references without promoting model claims to process evidence", async () => {
  const result = await finalizeAgentResult({
    context: {
      ...context,
      agent_skill_selection: {
        activation_method: "codex_explicit_reference",
        agent_skill_id: "agent-skill-1",
        approved_fingerprint: "sha256:v1:approved",
        backend: "codex_cli",
        display_name: "Approved Skill",
        observed_fingerprint: "sha256:v1:approved",
        provider_skill_name: "approved-skill",
        provider_skill_reference: "approved-skill",
        runtime_target_id: "codex-local-default",
        source_id: "source-1"
      }
    },
    result: {
      status: "completed",
      activated_skills: ["approved-skill"]
    },
    trustedVerification: []
  });

  assert.equal(result.agent_skill_activation?.activation_status, "activated");
  assert.equal(
    result.agent_skill_activation?.evidence_level,
    "provider_reference_resolved"
  );
});
