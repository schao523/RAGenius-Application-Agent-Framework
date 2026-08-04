import assert from "node:assert/strict";
import test from "node:test";

import { NotebookLmOperationVerifier } from "../../src/core/agents/notebooklm-operation-verifier.js";
import type { AgentVerificationInput } from "../../src/core/agents/agent-operation-verifier.js";

function input(operationId: string, externalId: string): AgentVerificationInput {
  return {
    request: {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "session_001",
      agent_backend: "codex_cli",
      agent_skill_hint: "notebooklm",
      agent_query: "Use the Testing notebook."
    },
    context: {
      execution_id: "execution_001",
      authorization: {
        state: "confirmed",
        permission_scope: "agent.external_write",
        policy_fingerprint: "a".repeat(64)
      },
      operation_plan: [{
        operation_id: operationId,
        kind: "external_write",
        description: operationId,
        required: true,
        target_hint: "Testing",
        minimum_verification: operationId === "notebooklm_source_add"
          ? "independently_verified"
          : "provider_reported"
      }],
      resolved_artifacts: [],
      expected_outputs: []
    },
    reportedVerification: [{
      operation_id: operationId,
      operation: operationId,
      level: "provider_reported",
      status: "completed",
      external_id: externalId
    }]
  };
}

test("verifies a source ID through list_sources", async () => {
  const calls: unknown[] = [];
  const verifier = new NotebookLmOperationVerifier({
    execute: async (operation, args) => {
      calls.push({ operation, args });
      return { sources: [{ id: "source_123", status: "ready" }] };
    }
  });

  const result = await verifier.verify(input("notebooklm_source_add", "source_123"));

  assert.deepEqual(calls, [{
    operation: "list_sources",
    args: { notebookTitle: "Testing" }
  }]);
  assert.equal(result[0]?.level, "independently_verified");
  assert.equal(result[0]?.verifier, "execution_subsystem_adapter");
});

test("rejects a source ID absent from the resolved notebook", async () => {
  const verifier = new NotebookLmOperationVerifier({
    execute: async () => ({ sources: [{ id: "another_source" }] })
  });

  const result = await verifier.verify(input("notebooklm_source_add", "source_123"));

  assert.equal(result[0]?.level, "none");
  assert.equal(result[0]?.status, "failed");
});

test("polls a report task by stable external ID", async () => {
  const verifier = new NotebookLmOperationVerifier({
    execute: async (operation, args) => {
      assert.equal(operation, "poll_artifact_task");
      assert.deepEqual(args, {
        notebookTitle: "Testing",
        taskId: "task_456",
        artifactKind: "report"
      });
      return { task_id: "task_456", status: "completed" };
    }
  });

  const result = await verifier.verify(
    input("notebooklm_report_generate", "task_456")
  );

  assert.equal(result[0]?.level, "independently_verified");
  assert.equal(result[0]?.status, "completed");
});

test("returns bounded failure evidence when adapter lookup fails", async () => {
  const verifier = new NotebookLmOperationVerifier({
    execute: async () => {
      throw new Error("x".repeat(1_000));
    }
  });

  const result = await verifier.verify(input("notebooklm_source_add", "source_123"));

  assert.equal(result[0]?.status, "failed");
  assert.ok((result[0]?.evidence?.length ?? 0) <= 240);
});
