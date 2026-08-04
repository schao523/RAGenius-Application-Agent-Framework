import assert from "node:assert/strict";
import test from "node:test";

import { CodexCliProvider } from "../../src/core/agents/codex-cli-provider.js";
import type { AgentProviderExecutionContext } from "../../src/core/agents/agent-provider-context.js";
import type { CodexRunWorkspace } from "../../src/core/agents/codex-workspace.js";
import { finalizeAgentResult } from "../../src/core/agents/agent-result-finalizer.js";

const config = {
  enabled: true,
  nodeCommand: "node",
  bridgeScript: "scripts/codex_cli_bridge.js",
  command: "codex",
  args: ["exec", "--json"],
  timeoutMs: 120000,
  runRoot: "D:/runtime/codex-runs",
  runRetentionHours: 24,
  maxOutputBytes: 16384,
  sandboxMode: "workspace-write" as const
};

const policy = {
  riskClass: "agent_external_write" as const,
  mode: "require_confirmation" as const,
  permissionScope: "agent.external_write",
  workspaceAccess: "none" as const,
  providerStateAccess: "scoped_write" as const,
  providerStateLabels: ["notebooklm_profile:default"],
  networkAccess: "allowlisted" as const,
  reason: "External write agent requests require confirmation.",
  matchedTerms: ["add"]
};

const providerContext: AgentProviderExecutionContext = {
  execution_id: "execution_123",
  authorization: {
    state: "confirmed",
    permission_scope: "agent.external_write",
    policy_fingerprint: "a".repeat(64),
    confirmed_at: "2026-08-03T01:02:03.000Z"
  },
  operation_plan: [{
    operation_id: "notebooklm_source_add",
    kind: "external_write",
    description: "Add source.",
    required: true,
    minimum_verification: "independently_verified"
  }],
  resolved_artifacts: [{
    artifact_id: "artifact_123",
    artifact_type: "session_export",
    display_name: "Approved.md",
    app_id: "app_001",
    status: "ready",
    role: "source",
    requested_reuse_mode: "inline_text",
    consumption: {
      default_mode: "inline_text",
      supported_modes: ["inline_text"],
      resolved_mode: "inline_text"
    },
    payload: { text_content: "Approved", metadata: {} },
    provenance: { provider_origin: "ragenius_app" }
  }],
  expected_outputs: []
};

const workspace: CodexRunWorkspace = {
  root_absolute_path: "D:/runtime/codex-runs/execution_123",
  inputs_absolute_path: "D:/runtime/codex-runs/execution_123/inputs",
  outputs_absolute_path: "D:/runtime/codex-runs/execution_123/outputs"
};

test("orchestrates staging, trusted prompt, bridge, evaluation, and cleanup", async () => {
  const calls: string[] = [];
  const provider = new CodexCliProvider(
    config,
    async (_config, request) => {
      calls.push("bridge");
      assert.equal(request.workspace_absolute_path, workspace.root_absolute_path);
      assert.equal(request.sandbox_mode, "workspace-write");
      assert.match(request.prompt ?? "", /trusted prompt/);
      return {
        ok: true,
        result: {
          thread_id: "thread_123",
          turn_status: "completed",
          final_message: JSON.stringify({
            task_status: "completed",
            summary: "Source added.",
            activated_skills: ["notebooklm"],
            operations: [{
              operation_id: "notebooklm_source_add",
              operation: "add source",
              status: "completed",
              external_id: "source_123"
            }],
            artifacts: [],
            errors: []
          }),
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
              stdout_summary: "source_123 Approved"
            }
          ],
          errors: [],
          raw_exit_code: 0,
          malformed_line_count: 0,
          stdout_truncated: false,
          stderr_truncated: false
        }
      };
    },
    {
      createWorkspace: async () => {
        calls.push("workspace");
        return workspace;
      },
      stageArtifacts: async () => {
        calls.push("stage");
        return [{
          artifact_id: "artifact_123",
          role: "source",
          reuse_mode: "inline_text",
          display_name: "Approved.md",
          size_bytes: 8,
          sha256: "b".repeat(64),
          workspace_relative_path: "inputs/artifact_123-Approved.md"
        }];
      },
      buildPrompt: () => {
        calls.push("prompt");
        return "trusted prompt";
      },
      finalizeResult: async ({ context, result }) => {
        calls.push("finalize");
        return await finalizeAgentResult({
          context,
          result,
          trustedVerification: [{
            operation_id: "notebooklm_source_add",
            operation: "add source",
            level: "independently_verified",
            status: "completed",
            external_id: "source_123",
            verifier: "execution_subsystem_adapter",
            checked_at: "2026-08-03T00:00:00.000Z"
          }]
        }) as typeof result;
      },
      cleanupWorkspaces: async () => {
        calls.push("cleanup");
      }
    }
  );

  const result = await provider.execute(
    {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "session_001",
      agent_backend: "codex_cli",
      agent_skill_hint: "notebooklm",
      agent_query: "Add the selected artifact as a source."
    },
    policy,
    providerContext
  );

  assert.deepEqual(calls, ["workspace", "stage", "prompt", "bridge", "finalize", "cleanup"]);
  assert.ok("status" in result);
  assert.equal(result.status, "completed");
  assert.equal(result.operation_verification[0]?.level, "independently_verified");
  assert.equal(result.staged_inputs[0]?.workspace_relative_path, "inputs/artifact_123-Approved.md");
  assert.equal(JSON.stringify(result).includes(workspace.root_absolute_path), false);
});

test("cleans retained workspaces when the bridge fails", async () => {
  let cleanupCalls = 0;
  const provider = new CodexCliProvider(
    config,
    async () => {
      throw new Error("bridge unavailable");
    },
    {
      createWorkspace: async () => workspace,
      stageArtifacts: async () => [],
      buildPrompt: () => "trusted prompt",
      cleanupWorkspaces: async () => {
        cleanupCalls += 1;
      }
    }
  );

  await assert.rejects(
    provider.execute(
      {
        request_type: "execute_agent",
        app_id: "app_001",
        session_id: "session_001",
        agent_backend: "codex_cli",
        agent_query: "Add a source."
      },
      policy,
      { ...providerContext, resolved_artifacts: [] }
    ),
    /bridge execution failed/i
  );
  assert.equal(cleanupCalls, 1);
});

test("does not invoke the bridge when staging fails", async () => {
  let bridgeCalls = 0;
  const provider = new CodexCliProvider(
    config,
    async () => {
      bridgeCalls += 1;
      throw new Error("unexpected bridge invocation");
    },
    {
      createWorkspace: async () => workspace,
      stageArtifacts: async () => {
        throw new Error("staged hash mismatch");
      },
      cleanupWorkspaces: async () => undefined
    }
  );

  await assert.rejects(
    provider.execute(
      {
        request_type: "execute_agent",
        app_id: "app_001",
        session_id: "session_001",
        agent_backend: "codex_cli",
        agent_query: "Add a source."
      },
      policy,
      providerContext
    ),
    /staging failed/i
  );
  assert.equal(bridgeCalls, 0);
});

test("persists verified Codex outputs and returns stable artifact metadata", async () => {
  const calls: string[] = [];
  const provider = new CodexCliProvider(
    config,
    async () => ({
      ok: true,
      result: {
        thread_id: "thread_123",
        turn_status: "completed",
        final_message: "{}",
        command_events: [],
        errors: [],
        raw_exit_code: 0,
        malformed_line_count: 0,
        stdout_truncated: false,
        stderr_truncated: false
      }
    }),
    {
      createWorkspace: async () => workspace,
      stageArtifacts: async () => [],
      buildPrompt: () => "trusted prompt",
      evaluateResult: () => ({
        backend: "codex_cli",
        status: "completed",
        summary: "Report created.",
        activated_skills: [],
        staged_inputs: [],
        operation_verification: [{
          operation_id: "agent_workspace_write",
          operation: "Create report.",
          level: "process_observed",
          status: "completed"
        }],
        artifacts: [{
          path: "outputs/study-report.md",
          media_type: "text/markdown"
        }],
        provider_metadata: {
          turn_status: "completed",
          raw_exit_code: 0,
          confirmation_state: "confirmed",
          permission_scope: "agent.workspace_write",
          policy_fingerprint: "a".repeat(64),
          command_count: 1,
          successful_command_count: 1,
          final_json_status: "parsed"
        }
      }),
      verifyOutputs: async () => {
        calls.push("verify");
        return [{
          output_id: "agent_output",
          display_name: "study-report.md",
          media_type: "text/markdown",
          workspace_relative_path: "outputs/study-report.md",
          workspace_absolute_path: "D:/runtime/codex-runs/execution_123/outputs/study-report.md",
          required: false,
          exists: true,
          verified: true,
          size_bytes: 128,
          sha256: "b".repeat(64)
        }];
      },
      persistOutput: async () => {
        calls.push("persist");
        return {
          artifact_id: "artifact_agent_123",
          artifact_type: "agent_output",
          display_name: "study-report.md",
          mime_type: "text/markdown"
        };
      },
      cleanupWorkspaces: async () => {
        calls.push("cleanup");
      }
    }
  );

  const result = await provider.execute(
    {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "session_001",
      agent_backend: "codex_cli",
      agent_query: "Create a report.",
      expected_outputs: [{
        output_id: "agent_output",
        media_type: "text/markdown",
        persist_as_artifact: true
      }]
    },
    { ...policy, riskClass: "agent_workspace_write", workspaceAccess: "scoped_write" },
    {
      ...providerContext,
      expected_outputs: [{
        output_id: "agent_output",
        media_type: "text/markdown",
        persist_as_artifact: true
      }]
    }
  );

  assert.deepEqual(calls, ["verify", "persist", "cleanup"]);
  assert.deepEqual(result.artifacts, [{
    artifact_id: "artifact_agent_123",
    artifact_type: "agent_output",
    display_name: "study-report.md",
    mime_type: "text/markdown"
  }]);
  assert.equal("path" in (result.artifacts?.[0] ?? {}), false);
  assert.equal(
    (result.reported_outputs?.[0] as { path?: string } | undefined)?.path,
    "outputs/study-report.md"
  );
});

test("keeps provider-declared Codex artifact ids out of stable artifacts", async () => {
  const provider = new CodexCliProvider(
    config,
    async () => ({
      ok: true,
      result: {
        thread_id: "thread_123",
        turn_status: "completed",
        final_message: "{}",
        command_events: [],
        errors: [],
        raw_exit_code: 0,
        malformed_line_count: 0,
        stdout_truncated: false,
        stderr_truncated: false
      }
    }),
    {
      createWorkspace: async () => workspace,
      stageArtifacts: async () => [],
      buildPrompt: () => "trusted prompt",
      evaluateResult: () => ({
        backend: "codex_cli",
        status: "completed",
        summary: "Codex reported an output.",
        activated_skills: [],
        staged_inputs: [],
        operation_verification: [],
        artifacts: [
          {
            artifact_id: "provider_invented_id",
            display_name: "reported.md",
            path: "outputs/reported.md"
          }
        ],
        provider_metadata: {
          turn_status: "completed",
          raw_exit_code: 0,
          confirmation_state: "not_required",
          permission_scope: "agent.read",
          policy_fingerprint: "a".repeat(64),
          command_count: 0,
          successful_command_count: 0,
          final_json_status: "parsed"
        }
      }),
      cleanupWorkspaces: async () => undefined
    }
  );

  const result = await provider.execute(
    {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "session_001",
      agent_backend: "codex_cli",
      agent_query: "Summarize locally."
    },
    policy,
    { ...providerContext, operation_plan: [] }
  );

  assert.deepEqual(result.artifacts, []);
  assert.equal(result.reported_outputs?.[0]?.artifact_id, "provider_invented_id");
});
