import assert from "node:assert/strict";
import test from "node:test";

import { OpenClawCliProvider } from "../../src/core/agents/openclaw-cli-provider.js";
import type { AgentPolicyDecision } from "../../src/core/agents/agent-policy.js";

const baseConfig = {
  enabled: true,
  wslDistro: "OpenClawGateway",
  command: "openclaw",
  agentId: "main",
  workspaceRoot: "/home/openclaw/.openclaw/workspace",
  timeoutMs: 120000
};

function fakeAgentPolicy(riskClass = "agent_read_only"): AgentPolicyDecision {
  return {
    riskClass: riskClass as AgentPolicyDecision["riskClass"],
    mode: "auto_allow",
    permissionScope: "agent.read",
    workspaceAccess: "none",
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
    verifyOutputs: async ({ expectedOutputs }) => {
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
  assert.match(
    capturedPrompt,
    /\/home\/openclaw\/\.openclaw\/workspace\/outputs\/openclaw_answer-openclaw-result\.md/
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
  assert.equal(result.artifacts[0]?.verified, true);
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
