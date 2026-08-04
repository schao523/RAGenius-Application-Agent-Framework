import assert from "node:assert/strict";
import test from "node:test";

import { planAgentExpectedOutputs } from "../../src/core/agents/agent-expected-output-planner.js";

test("preserves explicit provider-neutral expected outputs with defaults", () => {
  const outputs = planAgentExpectedOutputs({
    request: {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Create a reusable answer.",
      expected_outputs: [
        {
          output_id: "agent_answer",
          required: true
        }
      ]
    }
  });

  assert.equal(outputs.length, 1);
  assert.equal(outputs[0]?.output_id, "agent_answer");
  assert.equal(outputs[0]?.display_name, "agent_answer.md");
  assert.equal(outputs[0]?.media_type, "text/markdown");
  assert.equal(outputs[0]?.required, true);
  assert.equal(outputs[0]?.persist_as_artifact, true);
  assert.equal(outputs[0]?.artifact_type, "agent_output");
});

test("generates default OpenClaw output only when required", () => {
  const outputs = planAgentExpectedOutputs({
    request: {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Prepare a reusable markdown summary."
    },
    generateDefaultOutput: true
  });

  assert.equal(outputs.length, 1);
  assert.equal(outputs[0]?.output_id, "openclaw_answer");
  assert.equal(outputs[0]?.display_name, "openclaw-result.md");
  assert.equal(outputs[0]?.required, true);
  assert.equal(outputs[0]?.persist_as_artifact, true);
});

test("does not generate output for read-only requests", () => {
  const outputs = planAgentExpectedOutputs({
    request: {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "codex_cli",
      agent_query: "Explain this briefly."
    }
  });

  assert.equal(outputs.length, 0);
});

test("keeps persistence decisions outside provider-specific context", () => {
  const outputs = planAgentExpectedOutputs({
    request: {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Create output.",
      context: {
        openclaw: {
          expected_outputs: [
            {
              output_id: "legacy",
              purpose: "answer",
              display_name: "legacy.md",
              media_type: "text/markdown",
              required: true,
              persist_as_artifact: false
            }
          ]
        }
      }
    },
    generateDefaultOutput: true
  });

  assert.equal(outputs.length, 1);
  assert.equal(outputs[0]?.output_id, "openclaw_answer");
  assert.equal(outputs[0]?.persist_as_artifact, true);
});
