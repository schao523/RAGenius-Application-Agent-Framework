import assert from "node:assert/strict";
import test from "node:test";

import { OpenClawCliProvider } from "../../src/core/agents/openclaw-cli-provider.js";
import type { AgentPolicyDecision } from "../../src/core/agents/agent-policy.js";
import type { ResolvedAgentArtifact } from "../../src/core/agents/agent-artifact-resolver.js";
import type { AgentProviderExecutionContext } from "../../src/core/agents/agent-provider-context.js";

const baseConfig = {
  enabled: true,
  wslDistro: "OpenClawGateway",
  command: "openclaw",
  agentId: "main",
  workspaceRoot: "/home/openclaw/.openclaw/workspace",
  timeoutMs: 120000
};

const selectedContext: AgentProviderExecutionContext = {
  execution_id: "execution_selected",
  authorization: {
    state: "not_required",
    permission_scope: "agent.read",
    policy_fingerprint: "a".repeat(64)
  },
  access_policy: {
    workspace_access: "none",
    provider_state_access: "scoped_write",
    provider_state_labels: ["openclaw_agent_state"],
    network_access: "allowlisted"
  },
  operation_plan: [{
    operation_id: "agent_read",
    kind: "read",
    description: "Use the selected skill.",
    required: true,
    minimum_verification: "process_observed"
  }],
  resolved_artifacts: [],
  expected_outputs: [],
  agent_skill_selection: {
    activation_method: "openclaw_prompt_guidance",
    agent_skill_id: "agent-skill-1",
    approved_fingerprint: "sha256:v1:approved",
    backend: "openclaw_cli",
    display_name: "Approved Skill",
    observed_fingerprint: "sha256:v1:approved",
    provider_skill_name: "approved-skill",
    runtime_target_id: "main",
    source_id: "source-1"
  }
};

test("projects canonical OpenClaw guidance and normalizes contained session evidence", async () => {
  let capturedPrompt = "";
  let inspectedSessionFile = "";
  const provider = new OpenClawCliProvider(baseConfig, {
    bridge: async ({ prompt }) => {
      capturedPrompt = prompt;
      const json = {
        status: "ok",
        result: {
          finalAssistantVisibleText: "I used approved-skill.",
          meta: {
            agentMeta: {
              sessionFile: "/home/openclaw/.openclaw/agents/main/sessions/session.jsonl"
            }
          }
        }
      };
      return {
        exitCode: 0,
        stdout: JSON.stringify(json),
        stderr: "",
        timedOut: false,
        stdoutTruncated: false,
        stderrTruncated: false,
        json,
        jsonParseStatus: "parsed"
      };
    },
    readActivationTrace: async ({ sessionFile }) => {
      inspectedSessionFile = sessionFile;
      return '{"tool":"read","path":"/home/openclaw/.openclaw/skills/approved-skill/SKILL.md"}';
    }
  });

  const result = await provider.execute(
    {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Use the selected skill."
    },
    fakeAgentPolicy(),
    selectedContext
  );

  assert.match(capturedPrompt, /Selected Agent skill: approved-skill/);
  assert.match(capturedPrompt, /installed OpenClaw skill named `approved-skill`/);
  assert.doesNotMatch(capturedPrompt, /protected-source-ref/);
  assert.equal(
    inspectedSessionFile,
    "/home/openclaw/.openclaw/agents/main/sessions/session.jsonl"
  );
  assert.equal(result.agent_skill_activation.activation_status, "process_observed");
  assert.equal(result.agent_skill_activation.evidence_level, "process_observed");
});

function fakeAgentPolicy(riskClass = "agent_read_only"): AgentPolicyDecision {
  return {
    riskClass: riskClass as AgentPolicyDecision["riskClass"],
    mode: "auto_allow",
    permissionScope: "agent.read",
    workspaceAccess: "none",
    providerStateAccess: "scoped_write",
    providerStateLabels: ["openclaw_agent_state"],
    networkAccess: "allowlisted",
    reason: "test",
    matchedTerms: []
  };
}

test("completes read-only OpenClaw runs", async () => {
  const provider = new OpenClawCliProvider(baseConfig, {
    bridge: async () => ({
      exitCode: 0,
      stdout: JSON.stringify({
        status: "ok",
        result: { finalAssistantVisibleText: "OK" }
      }),
      stderr: "",
      timedOut: false,
      stdoutTruncated: false,
      stderrTruncated: false,
      json: { status: "ok", result: { finalAssistantVisibleText: "OK" } },
      jsonParseStatus: "parsed"
    })
  });

  const result = await provider.execute(
    {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Reply with OK."
    },
    fakeAgentPolicy(),
    { executionId: "execution_001" }
  );

  assert.equal(result.status, "completed");
  assert.equal(result.output_text, "OK");
  assert.equal(result.provider_metadata.backend, "openclaw_cli");
});

test("extracts assistant text from OpenClaw payload arrays", async () => {
  const provider = new OpenClawCliProvider(baseConfig, {
    bridge: async () => ({
      exitCode: 0,
      stdout: JSON.stringify({
        status: "ok",
        result: {
          finalAssistantVisibleText: "",
          payloads: [{ text: "OK.\n\nStatus Summary: ready" }]
        }
      }),
      stderr: "",
      timedOut: false,
      stdoutTruncated: false,
      stderrTruncated: false,
      json: {
        status: "ok",
        result: {
          finalAssistantVisibleText: "",
          payloads: [{ text: "OK.\n\nStatus Summary: ready" }]
        }
      },
      jsonParseStatus: "parsed"
    })
  });

  const result = await provider.execute(
    {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Reply with OK."
    },
    fakeAgentPolicy(),
    { executionId: "execution_001" }
  );

  assert.equal(result.status, "completed");
  assert.equal(result.output_text, "OK.\n\nStatus Summary: ready");
});

test("fails output-required run when required output is missing despite ok JSON", async () => {
  const provider = new OpenClawCliProvider(baseConfig, {
    bridge: async () => ({
      exitCode: 0,
      stdout: JSON.stringify({ status: "ok", summary: "completed", result: {} }),
      stderr: "",
      timedOut: false,
      stdoutTruncated: false,
      stderrTruncated: false,
      json: { status: "ok", summary: "completed", result: {} },
      jsonParseStatus: "parsed"
    }),
    verifyOutputs: async () => [
      {
        output_id: "openclaw_answer",
        workspace_relative_path: "outputs/result.md",
        workspace_absolute_path:
          "/home/openclaw/.openclaw/workspace/outputs/result.md",
        required: true,
        exists: false,
        verified: false,
        failure_code: "missing_output",
        failure_message: "Required output was not created."
      }
    ]
  });

  const result = await provider.execute(
    {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Prepare a reusable markdown summary.",
      context: { openclaw: { execution_mode: "output_required" } }
    },
    fakeAgentPolicy("agent_workspace_write"),
    { executionId: "execution_001" }
  );

  assert.equal(result.status, "failed");
  assert.equal(result.diagnostics.failure_code, "missing_output");
});

test("uses the same generated expected output path for prompt and verification", async () => {
  let capturedPrompt = "";
  let capturedVerificationPath = "";
  let capturedWorkspaceRoot = "";
  const provider = new OpenClawCliProvider(baseConfig, {
    bridge: async ({ prompt }) => {
      capturedPrompt = prompt;
      return {
        exitCode: 0,
        stdout: JSON.stringify({ status: "ok", result: {} }),
        stderr: "",
        timedOut: false,
        stdoutTruncated: false,
        stderrTruncated: false,
        json: { status: "ok", result: {} },
        jsonParseStatus: "parsed"
      };
    },
    verifyOutputs: async ({ expectedOutputs, workspaceRoot }) => {
      capturedWorkspaceRoot = workspaceRoot;
      capturedVerificationPath =
        expectedOutputs[0]?.workspace_relative_path ?? "";
      return [
        {
          output_id: "openclaw_answer",
          workspace_relative_path: capturedVerificationPath,
          workspace_absolute_path:
            "/home/openclaw/.openclaw/workspace/" + capturedVerificationPath,
          required: true,
          exists: true,
          verified: true,
          size_bytes: 10,
          media_type: "text/markdown"
        }
      ];
    }
  });

  await provider.execute(
    {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Create a markdown file summarizing this session.",
      context: { openclaw: { execution_mode: "output_required" } }
    },
    fakeAgentPolicy("agent_workspace_write"),
    { executionId: "execution_001" }
  );

  assert.equal(
    capturedVerificationPath,
    "outputs/openclaw_answer-openclaw-result.md"
  );
  assert.equal(
    capturedWorkspaceRoot,
    "/home/openclaw/.openclaw/workspace/runs/execution_001"
  );
  assert.match(
    capturedPrompt,
    /\/home\/openclaw\/\.openclaw\/workspace\/runs\/execution_001\/outputs\/openclaw_answer-openclaw-result\.md/
  );
});

test("completes output-required run when required output verifies", async () => {
  const provider = new OpenClawCliProvider(baseConfig, {
    bridge: async () => ({
      exitCode: 0,
      stdout: JSON.stringify({ status: "ok", result: {} }),
      stderr: "",
      timedOut: false,
      stdoutTruncated: false,
      stderrTruncated: false,
      json: { status: "ok", result: {} },
      jsonParseStatus: "parsed"
    }),
    verifyOutputs: async () => [
      {
        output_id: "openclaw_answer",
        workspace_relative_path: "outputs/result.md",
        workspace_absolute_path:
          "/home/openclaw/.openclaw/workspace/outputs/result.md",
        required: true,
        exists: true,
        verified: true,
        size_bytes: 10,
        media_type: "text/markdown"
      }
    ]
  });

  const result = await provider.execute(
    {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Prepare a reusable markdown summary.",
      context: { openclaw: { execution_mode: "output_required" } }
    },
    fakeAgentPolicy("agent_workspace_write"),
    { executionId: "execution_001" }
  );

  assert.equal(result.status, "completed");
  assert.equal(result.provider_metadata.verified_output_count, 1);
  assert.deepEqual(result.artifacts, []);
  assert.equal(result.reported_outputs[0]?.verified, true);
});

test("fails when OpenClaw reports requested task failure despite verified output", async () => {
  const provider = new OpenClawCliProvider(baseConfig, {
    bridge: async () => ({
      exitCode: 0,
      stdout: JSON.stringify({
        status: "ok",
        result: {
          finalAssistantVisibleText:
            "## Status Summary\n\n**Message sent to OpenClaw Bot:** ❌ **Failed** — request was forbidden due to `tools.sessions.visibility=tree` restrictions.\n\n**Required outputs:**\n- ✅ `/home/openclaw/.openclaw/workspace/outputs/agent_output-agent_output.md` — exists"
        }
      }),
      stderr: "",
      timedOut: false,
      stdoutTruncated: false,
      stderrTruncated: false,
      json: {
        status: "ok",
        result: {
          finalAssistantVisibleText:
            "## Status Summary\n\n**Message sent to OpenClaw Bot:** ❌ **Failed** — request was forbidden due to `tools.sessions.visibility=tree` restrictions.\n\n**Required outputs:**\n- ✅ `/home/openclaw/.openclaw/workspace/outputs/agent_output-agent_output.md` — exists"
        }
      },
      jsonParseStatus: "parsed"
    }),
    verifyOutputs: async () => [
      {
        output_id: "agent_output",
        workspace_relative_path: "outputs/agent_output-agent_output.md",
        workspace_absolute_path:
          "/home/openclaw/.openclaw/workspace/outputs/agent_output-agent_output.md",
        required: true,
        exists: true,
        verified: true,
        size_bytes: 128,
        media_type: "text/markdown"
      }
    ]
  });

  const result = await provider.execute(
    {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Send this message to OpenClaw Bot.",
      expected_outputs: [
        {
          output_id: "agent_output",
          display_name: "agent-output.md",
          required: true,
          persist_as_artifact: false
        }
      ]
    },
    fakeAgentPolicy("agent_external_write"),
    { executionId: "execution_001" }
  );

  assert.equal(result.status, "failed");
  assert.equal(result.summary, "OpenClaw reported that the requested task failed.");
  assert.equal(result.diagnostics.failure_code, "agent_task_failed");
  assert.match(
    result.diagnostics.failure_message ?? "",
    /request was forbidden/
  );
});

test("persists verified required OpenClaw outputs as agent artifacts", async () => {
  let persistedExecutionId = "";
  let persistedOutputId = "";
  const provider = new OpenClawCliProvider(baseConfig, {
    bridge: async () => ({
      exitCode: 0,
      stdout: JSON.stringify({ status: "ok", result: {} }),
      stderr: "",
      timedOut: false,
      stdoutTruncated: false,
      stderrTruncated: false,
      json: { status: "ok", result: {} },
      jsonParseStatus: "parsed"
    }),
    verifyOutputs: async () => [
      {
        output_id: "agent_answer",
        workspace_relative_path: "outputs/agent_answer-answer.md",
        workspace_absolute_path:
          "/home/openclaw/.openclaw/workspace/outputs/agent_answer-answer.md",
        required: true,
        exists: true,
        verified: true,
        size_bytes: 32,
        sha256: "abc",
        media_type: "text/markdown"
      }
    ],
    persistOutput: async ({ executionId, output, verification }) => {
      persistedExecutionId = executionId;
      persistedOutputId = output.output_id;
      assert.equal(verification.workspace_relative_path, "outputs/agent_answer-answer.md");
      return {
        artifact_id: "artifact_agent_1",
        artifact_type: "agent_output",
        display_name: output.display_name,
        mime_type: output.media_type
      };
    }
  });

  const result = await provider.execute(
    {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Create a reusable output.",
      expected_outputs: [
        {
          output_id: "agent_answer",
          display_name: "answer.md",
          required: true,
          persist_as_artifact: true
        }
      ]
    },
    fakeAgentPolicy("agent_workspace_write"),
    { executionId: "execution_001" }
  );

  assert.equal(result.status, "completed");
  assert.equal(persistedExecutionId, "execution_001");
  assert.equal(persistedOutputId, "agent_answer");
  assert.equal(result.verification_results[0]?.persisted_artifact_id, "artifact_agent_1");
  assert.equal(result.artifacts[0]?.artifact_id, "artifact_agent_1");
  assert.equal(result.artifacts[0]?.display_name, "answer.md");
});

test("fails required output execution when artifact persistence fails", async () => {
  const provider = new OpenClawCliProvider(baseConfig, {
    bridge: async () => ({
      exitCode: 0,
      stdout: JSON.stringify({ status: "ok", result: {} }),
      stderr: "",
      timedOut: false,
      stdoutTruncated: false,
      stderrTruncated: false,
      json: { status: "ok", result: {} },
      jsonParseStatus: "parsed"
    }),
    verifyOutputs: async () => [
      {
        output_id: "agent_answer",
        workspace_relative_path: "outputs/agent_answer-answer.md",
        workspace_absolute_path:
          "/home/openclaw/.openclaw/workspace/outputs/agent_answer-answer.md",
        required: true,
        exists: true,
        verified: true,
        size_bytes: 32,
        media_type: "text/markdown"
      }
    ],
    persistOutput: async () => {
      throw new Error("artifact store unavailable");
    }
  });

  const result = await provider.execute(
    {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Create a reusable output.",
      expected_outputs: [
        {
          output_id: "agent_answer",
          display_name: "answer.md",
          required: true,
          persist_as_artifact: true
        }
      ]
    },
    fakeAgentPolicy("agent_workspace_write"),
    { executionId: "execution_001" }
  );

  assert.equal(result.status, "failed");
  assert.equal(result.diagnostics.failure_code, "persist_failed");
  assert.equal(result.verification_results[0]?.verified, true);
  assert.equal(result.verification_results[0]?.persistence_status, "failed");
  assert.match(
    result.verification_results[0]?.persistence_failure_message ?? "",
    /artifact store unavailable/
  );
});

test("returns partial when optional output persistence fails", async () => {
  const provider = new OpenClawCliProvider(baseConfig, {
    bridge: async () => ({
      exitCode: 0,
      stdout: JSON.stringify({ status: "ok", result: {} }),
      stderr: "",
      timedOut: false,
      stdoutTruncated: false,
      stderrTruncated: false,
      json: { status: "ok", result: {} },
      jsonParseStatus: "parsed"
    }),
    verifyOutputs: async () => [
      {
        output_id: "optional_notes",
        workspace_relative_path: "outputs/optional_notes.md",
        workspace_absolute_path:
          "/home/openclaw/.openclaw/workspace/outputs/optional_notes.md",
        required: false,
        exists: true,
        verified: true,
        size_bytes: 32,
        media_type: "text/markdown"
      }
    ],
    persistOutput: async () => {
      throw new Error("optional persist failed");
    }
  });

  const result = await provider.execute(
    {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Create optional notes.",
      expected_outputs: [
        {
          output_id: "optional_notes",
          display_name: "optional-notes.md",
          required: false,
          persist_as_artifact: true
        }
      ]
    },
    fakeAgentPolicy("agent_workspace_write"),
    { executionId: "execution_001" }
  );

  assert.equal(result.status, "partial");
  assert.equal(result.diagnostics.failure_code, "persist_failed");
  assert.equal(result.verification_results[0]?.verified, true);
  assert.equal(result.verification_results[0]?.persistence_status, "failed");
  assert.equal(result.artifacts.length, 0);
});

test("reports timeout diagnostics", async () => {
  const provider = new OpenClawCliProvider(baseConfig, {
    bridge: async () => ({
      exitCode: null,
      stdout: "",
      stderr: "timeout",
      timedOut: true,
      stdoutTruncated: false,
      stderrTruncated: false,
      jsonParseStatus: "not_requested"
    })
  });

  const result = await provider.execute(
    {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Reply with OK."
    },
    fakeAgentPolicy(),
    { executionId: "execution_001" }
  );

  assert.equal(result.status, "failed");
  assert.equal(result.provider_metadata.timed_out, true);
  assert.equal(result.diagnostics.failure_code, "provider_timeout");
});

test("fails read-only runs when OpenClaw exits non-zero", async () => {
  const provider = new OpenClawCliProvider(baseConfig, {
    bridge: async () => ({
      exitCode: 2,
      stdout: "",
      stderr: "openclaw failed",
      timedOut: false,
      stdoutTruncated: false,
      stderrTruncated: false,
      jsonParseStatus: "not_requested"
    })
  });

  const result = await provider.execute(
    {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Explain this briefly."
    },
    fakeAgentPolicy(),
    { executionId: "execution_001" }
  );

  assert.equal(result.status, "failed");
  assert.equal(result.summary, "OpenClaw exited with a non-zero status.");
  assert.equal(result.diagnostics.failure_code, "provider_nonzero_exit");
  assert.equal(result.raw.exit_code, 2);
});

test("resolves selected artifacts, stages them, and includes staged paths in prompt", async () => {
  let capturedPrompt = "";
  let resolvedAppId = "";
  let resolvedSessionId = "";
  const provider = new OpenClawCliProvider(baseConfig, {
    resolveArtifacts: async (input) => {
      resolvedAppId = input.appId;
      resolvedSessionId = input.sessionId;
      return [
        {
          artifact_id: "artifact_1",
          artifact_type: "chat_export",
          display_name: "Notes.md",
          app_id: input.appId,
          status: "ready",
          role: "source",
          requested_reuse_mode: "inline_text",
          consumption: {
            default_mode: "file_backed",
            supported_modes: ["file_backed", "inline_text"],
            resolved_mode: "inline_text"
          },
          payload: {
            text_content: "# Notes",
            metadata: {},
            mime_type: "text/markdown"
          },
          provenance: { provider_origin: "local" }
        } satisfies ResolvedAgentArtifact
      ];
    },
    stageArtifacts: async () => [
      {
        input_id: "artifact_1",
        source_kind: "artifact",
        source_ref: { artifact_id: "artifact_1" },
        display_name: "Notes.md",
        media_type: "text/markdown",
        encoding: "utf8",
        workspace_relative_path: "inputs/artifact_1-Notes.md"
      }
    ],
    bridge: async ({ prompt }) => {
      capturedPrompt = prompt;
      return {
        exitCode: 0,
        stdout: JSON.stringify({
          status: "ok",
          result: { finalAssistantVisibleText: "OK" }
        }),
        stderr: "",
        timedOut: false,
        stdoutTruncated: false,
        stderrTruncated: false,
        json: { status: "ok", result: { finalAssistantVisibleText: "OK" } },
        jsonParseStatus: "parsed"
      };
    }
  });

  const result = await provider.execute(
    {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Use the selected artifact.",
      artifact_refs: [
        {
          artifact_id: "artifact_1",
          role: "source",
          reuse_mode: "inline_text"
        }
      ]
    },
    fakeAgentPolicy(),
    { executionId: "execution_001" }
  );

  assert.equal(result.status, "completed");
  assert.equal(resolvedAppId, "app_001");
  assert.equal(resolvedSessionId, "sess_001");
  assert.match(
    capturedPrompt,
    /\/home\/openclaw\/\.openclaw\/workspace\/runs\/execution_001\/inputs\/artifact_1-Notes\.md/
  );
  assert.match(capturedPrompt, /Read every staged input file before answering\./);
  assert.match(
    capturedPrompt,
    /Do not answer from the user task alone when staged inputs are present\./
  );
  assert.match(capturedPrompt, /Final response rules:/);
  assert.match(capturedPrompt, /Report whether each staged input was read\./);
  assert.match(capturedPrompt, /Report the exact staged input path\(s\) used\./);
  assert.match(capturedPrompt, /If you created an output file, report the exact output path\./);
});

test("classifies OpenClaw artifact staging failures before bridge invocation", async () => {
  let bridgeCalled = false;
  const provider = new OpenClawCliProvider(baseConfig, {
    resolveArtifacts: async (input) => [
      {
        artifact_id: "artifact_1",
        artifact_type: "chat_export",
        display_name: "Notes.md",
        app_id: input.appId,
        status: "ready",
        role: "source",
        requested_reuse_mode: "file_backed",
        consumption: {
          default_mode: "file_backed",
          supported_modes: ["file_backed"],
          resolved_mode: "file_backed"
        },
        payload: {
          text_content: "# Notes",
          metadata: {},
          mime_type: "text/markdown"
        },
        provenance: { provider_origin: "local" }
      } satisfies ResolvedAgentArtifact
    ],
    stageArtifacts: async () => {
      throw new Error("canonical staging parent is unavailable");
    },
    bridge: async () => {
      bridgeCalled = true;
      throw new Error("bridge must not run");
    }
  });

  await assert.rejects(
    provider.execute(
      {
        request_type: "execute_agent",
        app_id: "app_001",
        session_id: "sess_001",
        agent_backend: "openclaw_cli",
        agent_query: "Use the selected artifact.",
        artifact_refs: [
          {
            artifact_id: "artifact_1",
            role: "source",
            reuse_mode: "file_backed"
          }
        ]
      },
      fakeAgentPolicy(),
      { executionId: "execution_001" }
    ),
    (error: unknown) => {
      const candidate = error as {
        code?: string;
        message?: string;
        recoverable?: boolean;
      };
      assert.equal(candidate.code, "OPENCLAW_ARTIFACT_STAGING_FAILED");
      assert.equal(candidate.message, "OpenClaw artifact staging failed.");
      assert.equal(candidate.recoverable, true);
      return true;
    }
  );
  assert.equal(bridgeCalled, false);
});
