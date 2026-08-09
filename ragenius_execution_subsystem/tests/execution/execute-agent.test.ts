import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  executionRequestSchema
} from "../../src/api/schemas/execution-request.schema.js";
import type { AgentProvider } from "../../src/core/agents/agent-provider.js";
import type { AgentProviderExecutionContext } from "../../src/core/agents/agent-provider-context.js";
import type { AgentSkillSelectionService } from "../../src/core/agent-skills/agent-skill-selection-service.js";
import type { ResolvedAgentSkillSelection } from "../../src/core/agent-skills/agent-skill-types.js";
import {
  createAgentOperationPlan
} from "../../src/core/agents/agent-operation-planner.js";
import { classifyAgentRequest } from "../../src/core/agents/agent-policy.js";
import { ExecutionEngine } from "../../src/core/execution/execution-engine.js";
import { persistedSkillIdForRequest } from "../../src/core/execution/execution-store.js";
import { buildApp } from "../../src/app.js";

describe("execute_agent requests", () => {
  const approvedSelection: ResolvedAgentSkillSelection = {
    activation_method: "codex_explicit_reference",
    agent_skill_id: "agent-skill-1",
    approved_fingerprint: "sha256:v1:approved",
    backend: "codex_cli",
    display_name: "Approved Skill",
    observed_fingerprint: "sha256:v1:approved",
    protected_locator_ref: "protected-source-ref",
    provider_skill_name: "systematic-debugging",
    provider_skill_reference: "superpowers:systematic-debugging",
    resolved_at: "2026-08-04T00:00:00.000Z",
    runtime_target_id: "codex-local-default",
    source_id: "source-1"
  };

  it("accepts openclaw_cli as an execute_agent backend", () => {
    const parsed = executionRequestSchema.parse({
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Inspect the approved content."
    });

    assert.equal(parsed.request_type, "execute_agent");
    assert.equal(parsed.agent_backend, "openclaw_cli");
  });

  it("rejects unknown execute_agent backends", () => {
    assert.throws(() =>
      executionRequestSchema.parse({
        request_type: "execute_agent",
        app_id: "app_001",
        session_id: "sess_001",
        agent_backend: "unknown_agent",
        agent_query: "Inspect the approved content."
      })
    );
  });

  it("accepts session-scoped artifact refs and provider-neutral expected outputs", () => {
    const parsed = executionRequestSchema.parse({
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Summarize the selected artifact into markdown.",
      artifact_refs: [
        {
          artifact_id: "artifact_123",
          role: "source",
          reuse_mode: "file_backed",
          display_name: "Bible notes.md",
          mime_type: "text/markdown"
        }
      ],
      expected_outputs: [
        {
          output_id: "agent_answer",
          display_name: "agent-answer.md",
          media_type: "text/markdown",
          required: true,
          persist_as_artifact: true,
          artifact_type: "agent_output",
          min_size_bytes: 1
        }
      ]
    });

    assert.equal(parsed.request_type, "execute_agent");
    assert.equal(parsed.artifact_refs?.[0]?.artifact_id, "artifact_123");
    assert.equal(parsed.artifact_refs?.[0]?.reuse_mode, "file_backed");
    assert.equal(parsed.expected_outputs?.[0]?.output_id, "agent_answer");
    assert.equal(parsed.expected_outputs?.[0]?.persist_as_artifact, true);
  });

  it("rejects invalid artifact refs and expected outputs", () => {
    assert.throws(() =>
      executionRequestSchema.parse({
        request_type: "execute_agent",
        app_id: "app_001",
        session_id: "sess_001",
        agent_backend: "openclaw_cli",
        agent_query: "Use this artifact.",
        artifact_refs: [
          {
            artifact_id: "artifact_123",
            role: "source",
            reuse_mode: "raw_path"
          }
        ]
      })
    );

    assert.throws(() =>
      executionRequestSchema.parse({
        request_type: "execute_agent",
        app_id: "app_001",
        session_id: "sess_001",
        agent_backend: "openclaw_cli",
        agent_query: "Create output.",
        expected_outputs: [
          {
            output_id: "bad/output",
            persist_as_artifact: true
          }
        ]
      })
    );
  });

  it("dispatches openclaw_cli agent requests to the OpenClaw provider", async () => {
    const openclawProvider: AgentProvider = {
      backend: "openclaw_cli",
      async execute() {
        return {
          status: "completed",
          summary: "OpenClaw completed.",
          output_text: "OpenClaw response.",
          artifacts: [],
          provider_metadata: {
            backend: "openclaw_cli",
            provider_name: "OpenClaw",
            invocation_mode: "wsl_cli",
            wsl_distro: "OpenClawGateway",
            openclaw_command: "openclaw",
            openclaw_agent_id: "main",
            openclaw_session_key: "ragenius:app_001:sess_001:execution_test",
            execution_mode: "read_only",
            expected_output_count: 0,
            required_output_count: 0,
            verified_output_count: 0,
            json_parse_status: "parsed",
            raw_exit_code: 0,
            timed_out: false,
            stdout_truncated: false,
            stderr_truncated: false
          },
          verification_results: [],
          diagnostics: {
            stdout_truncated: false,
            stderr_truncated: false,
            redactions_applied: true
          },
          raw: { exit_code: 0 }
        };
      }
    };

    const engine = new ExecutionEngine({
      agentProviders: new Map([["openclaw_cli", openclawProvider]])
    });

    const result = await engine.execute({
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Reply with OK."
    });

    assert.equal(result.status, "completed");
    assert.equal((result.result as Record<string, unknown>).backend, "openclaw_cli");
    assert.deepEqual(result.execution_metadata?.provider_ids, ["openclaw_cli"]);
  });

  it("resolves an approved skill before planning and binds its identity to every operation", async () => {
    const lifecycle: string[] = [];
    let capturedContext: AgentProviderExecutionContext | undefined;
    let capturedSkillHint = "";
    const selectionService = {
      async resolve() {
        lifecycle.push("resolve");
        return approvedSelection;
      }
    } as unknown as AgentSkillSelectionService;
    const provider: AgentProvider = {
      backend: "codex_cli",
      async execute(providerRequest, _policy, context) {
        lifecycle.push("provider");
        capturedSkillHint = providerRequest.agent_skill_hint ?? "";
        capturedContext = context;
        return { status: "completed" };
      }
    };
    const engine = new ExecutionEngine({
      agentProviders: new Map([["codex_cli", provider]]),
      agentSkillSelectionService: selectionService
    });

    const result = await engine.execute({
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "codex_cli",
      agent_query: "Inspect the workspace without changing it.",
      agent_skill_ref: {
        agent_skill_id: "agent-skill-1",
        approved_fingerprint: "sha256:v1:approved"
      }
    });

    assert.equal(result.status, "completed");
    assert.deepEqual(lifecycle, ["resolve", "provider"]);
    assert.equal(capturedSkillHint, "systematic-debugging");
    assert.equal(capturedContext?.operation_plan[0]?.agent_skill_id, "agent-skill-1");
    assert.equal(capturedContext?.operation_plan[0]?.provider_skill_name, "systematic-debugging");
    assert.equal(
      capturedContext?.operation_plan[0]?.provider_skill_reference,
      "superpowers:systematic-debugging"
    );
    assert.equal(
      capturedContext?.operation_plan[0]?.approved_fingerprint,
      "sha256:v1:approved"
    );
    assert.equal(
      capturedContext?.operation_plan[0]?.observed_fingerprint,
      "sha256:v1:approved"
    );
    assert.equal(capturedContext?.operation_plan[0]?.runtime_target_id, "codex-local-default");
    assert.equal(capturedContext?.operation_plan[0]?.activation_method, "codex_explicit_reference");
    assert.equal(capturedContext?.agent_skill_selection?.agent_skill_id, "agent-skill-1");
    assert.equal(
      JSON.stringify(capturedContext?.agent_skill_selection).includes("protected-source-ref"),
      false
    );
  });

  it("returns the safe resolved selection in explicit Agent dry runs", async () => {
    const engine = new ExecutionEngine({
      agentProviders: new Map([[
        "codex_cli",
        { backend: "codex_cli", execute: async () => ({ status: "completed" }) }
      ]]),
      agentSkillSelectionService: {
        resolve: async () => approvedSelection
      }
    });

    const result = await engine.execute({
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "codex_cli",
      agent_query: "Inspect the workspace.",
      agent_skill_ref: {
        agent_skill_id: "agent-skill-1",
        approved_fingerprint: "sha256:v1:approved"
      },
      execution_options: { dry_run: true }
    });

    const dryRunSelection = result.result.agent_skill_selection as Record<string, unknown>;
    assert.equal(dryRunSelection.agent_skill_id, "agent-skill-1");
    assert.equal(
      JSON.stringify(dryRunSelection).includes("protected-source-ref"),
      false
    );
  });

  it("uses the provider terminal status as the top-level status", async () => {
    const failedProvider: AgentProvider = {
      backend: "openclaw_cli",
      async execute() {
        return {
          status: "failed",
          summary: "Required output was not created.",
          diagnostics: { failure_code: "missing_output" }
        };
      }
    };
    const engine = new ExecutionEngine({
      agentProviders: new Map([["openclaw_cli", failedProvider]])
    });

    const result = await engine.execute({
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Reply with OK."
    });

    assert.equal(result.status, "failed");
    assert.equal(result.result.summary, "Required output was not created.");
    assert.deepEqual(result.result.diagnostics, {
      failure_code: "missing_output"
    });
  });

  it("returns normalized provider failure diagnostics from the HTTP route", async () => {
    const failedProvider: AgentProvider = {
      backend: "openclaw_cli",
      async execute() {
        return {
          status: "failed",
          summary: "Required output was not created.",
          diagnostics: {
            failure_code: "missing_output",
            failure_message: "The expected markdown file does not exist."
          }
        };
      }
    };
    const app = buildApp({
      executionEngine: new ExecutionEngine({
        agentProviders: new Map([["openclaw_cli", failedProvider]])
      })
    });

    const response = await app.inject({
      method: "POST",
      url: "/v1/executions",
      payload: {
        request_type: "execute_agent",
        app_id: "app_001",
        session_id: "sess_001",
        agent_backend: "openclaw_cli",
        agent_query: "Reply with OK."
      }
    });

    assert.equal(response.statusCode, 200);
    assert.equal(response.json().status, "failed");
    assert.equal(
      response.json().result.diagnostics.failure_code,
      "missing_output"
    );
    await app.close();
  });

  it("does not invoke the agent provider during dry run", async () => {
    let providerCalls = 0;
    const provider: AgentProvider = {
      backend: "openclaw_cli",
      async execute() {
        providerCalls += 1;
        return { status: "completed" };
      }
    };
    const engine = new ExecutionEngine({
      agentProviders: new Map([["openclaw_cli", provider]])
    });

    const result = await engine.execute({
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Create a markdown file.",
      artifact_refs: [
        {
          artifact_id: "artifact_123",
          role: "source",
          reuse_mode: "file_backed"
        }
      ],
      execution_options: { dry_run: true }
    });

    assert.equal(result.status, "completed");
    assert.equal(result.result.dry_run, true);
    assert.equal(result.result.confirmation_required, true);
    assert.equal(result.result.side_effects_executed, false);
    assert.equal(providerCalls, 0);
  });

  it("persists backend-aware agent skill ids", () => {
    assert.equal(
      persistedSkillIdForRequest({
        request_type: "execute_agent",
        app_id: "app_001",
        session_id: "sess_001",
        agent_backend: "openclaw_cli",
        agent_query: "Inspect content."
      }),
      "openclaw_cli"
    );

    assert.equal(
      persistedSkillIdForRequest({
        request_type: "execute_agent",
        app_id: "app_001",
        session_id: "sess_001",
        agent_backend: "codex_cli",
        agent_query: "Use NotebookLM.",
        agent_skill_hint: "notebooklm"
      }),
      "codex_cli:notebooklm"
    );

    assert.equal(
      persistedSkillIdForRequest({
        request_type: "execute_agent",
        app_id: "app_001",
        session_id: "sess_001",
        agent_backend: "codex_cli",
        agent_query: "Use the approved skill.",
        agent_skill_ref: {
          agent_skill_id: "agent-skill-1",
          approved_fingerprint: "sha256:v1:approved"
        }
      }),
      "codex_cli:agent-skill-1"
    );
  });

  it("passes confirmed authorization, immutable operations, and resolved artifacts to Codex", async () => {
    const request = executionRequestSchema.parse({
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "codex_cli",
      agent_skill_hint: "notebooklm",
      agent_query:
        "Add the selected artifact as a source to Testing, then create a study report.",
      artifact_refs: [{
        artifact_id: "artifact_123",
        role: "source",
        reuse_mode: "inline_text"
      }],
      expected_outputs: [{
        output_id: "study_report",
        required: true
      }],
      context: {
        authorization: { state: "not_required" },
        operation_plan: [],
        resolved_artifacts: []
      }
    });
    assert.equal(request.request_type, "execute_agent");
    const policy = classifyAgentRequest(request);
    const operationPlan = createAgentOperationPlan(request, policy);
    const policySnapshot = {
      backend: request.agent_backend,
      matched_terms: policy.matchedTerms,
      mode: policy.mode,
      network_access: policy.networkAccess,
      provider_state_access: policy.providerStateAccess,
      provider_state_labels: policy.providerStateLabels,
      operation_plan: operationPlan,
      permission_scope: policy.permissionScope,
      policy_reason: policy.reason,
      request_type: request.request_type,
      risk_class: policy.riskClass,
      workspace_access: policy.workspaceAccess
    };
    let capturedContext: AgentProviderExecutionContext | undefined;
    const provider: AgentProvider = {
      backend: "codex_cli",
      async execute(_request, _policy, context) {
        capturedContext = context;
        return { status: "completed", summary: "Started." };
      }
    };
    const engine = new ExecutionEngine({
      agentProviders: new Map([["codex_cli", provider]]),
      resolveAgentArtifacts: async () => [{
        artifact_id: "artifact_123",
        artifact_type: "session_export",
        display_name: "approved.md",
        app_id: "app_001",
        status: "ready",
        role: "source",
        requested_reuse_mode: "inline_text",
        consumption: {
          default_mode: "inline_text",
          supported_modes: ["inline_text"],
          resolved_mode: "inline_text"
        },
        payload: {
          text_content: "Approved session content.",
          metadata: {}
        },
        provenance: { provider_origin: "ragenius_app" }
      }]
    });

    const result = await engine.execute(request, {
      approvedConfirmation: {
        confirmationId: "confirmation_123",
        confirmedAt: "2026-08-03T01:02:03.000Z",
        policySnapshot
      },
      executionId: "execution_123"
    });

    assert.equal(result.status, "completed");
    assert.equal(capturedContext?.authorization.state, "confirmed");
    assert.equal(
      capturedContext?.authorization.confirmed_at,
      "2026-08-03T01:02:03.000Z"
    );
    assert.deepEqual(
      capturedContext?.operation_plan.map((item) => item.operation_id),
      ["notebooklm_source_add", "notebooklm_report_generate"]
    );
    assert.equal(capturedContext?.resolved_artifacts[0]?.artifact_id, "artifact_123");
    assert.equal(capturedContext?.expected_outputs[0]?.output_id, "study_report");
    assert.equal(
      capturedContext?.access_policy?.provider_state_access,
      "scoped_write"
    );
    assert.deepEqual(
      capturedContext?.access_policy?.provider_state_labels,
      ["notebooklm_profile:default"]
    );
    assert.notEqual(capturedContext?.authorization.policy_fingerprint, "");
  });

  it("does not invoke Codex when selected artifact resolution fails", async () => {
    let providerCalls = 0;
    const provider: AgentProvider = {
      backend: "codex_cli",
      async execute() {
        providerCalls += 1;
        return { status: "completed" };
      }
    };
    const engine = new ExecutionEngine({
      agentProviders: new Map([["codex_cli", provider]]),
      resolveAgentArtifacts: async () => {
        throw new Error("artifact bytes are unavailable");
      }
    });

    const result = await engine.execute({
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "codex_cli",
      agent_query: "Explain the selected artifact.",
      artifact_refs: [{
        artifact_id: "artifact_123",
        role: "source",
        reuse_mode: "inline_text"
      }]
    });

    assert.equal(result.status, "failed");
    assert.equal(result.errors[0]?.code, "CODEX_ARTIFACT_RESOLUTION_FAILED");
    assert.equal(providerCalls, 0);
  });
});
