import assert from "node:assert/strict";
import test from "node:test";

import { normalizeOpenClawOptions } from "../../src/core/agents/openclaw-options.js";

test("normalizes read-only OpenClaw options", () => {
  const options = normalizeOpenClawOptions({
    request: {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Explain this briefly."
    },
    executionId: "execution_001"
  });

  assert.equal(options.execution_mode, "read_only");
  assert.equal(options.expected_outputs.length, 0);
});

test("generates default output for ambiguous approved-content output requests", () => {
  const options = normalizeOpenClawOptions({
    request: {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Prepare a reusable markdown summary.",
      context: {
        approved_content: { approved_content_id: "ac_123", revision_id: "rev_1" }
      }
    },
    executionId: "execution_001"
  });

  assert.equal(options.execution_mode, "output_required");
  assert.equal(options.expected_outputs.length, 1);
  assert.equal(options.expected_outputs[0]?.output_id, "openclaw_answer");
  assert.equal(options.expected_outputs[0]?.required, true);
  assert.equal(
    options.expected_outputs[0]?.workspace_relative_path,
    "outputs/openclaw_answer-openclaw-result.md"
  );
});

test("uses provider-neutral expected outputs for OpenClaw output planning", () => {
  const options = normalizeOpenClawOptions({
    request: {
      request_type: "execute_agent",
      app_id: "app_001",
      session_id: "sess_001",
      agent_backend: "openclaw_cli",
      agent_query: "Create a reusable output.",
      expected_outputs: [
        {
          output_id: "agent_answer",
          display_name: "answer.md",
          required: true
        }
      ]
    },
    executionId: "execution_001"
  });

  assert.equal(options.execution_mode, "output_required");
  assert.equal(options.expected_outputs.length, 1);
  assert.equal(options.expected_outputs[0]?.output_id, "agent_answer");
  assert.equal(options.expected_outputs[0]?.display_name, "answer.md");
  assert.equal(options.expected_outputs[0]?.media_type, "text/markdown");
  assert.equal(options.expected_outputs[0]?.persist_as_artifact, true);
  assert.equal(options.expected_outputs[0]?.artifact_type, "agent_output");
  assert.equal(
    options.expected_outputs[0]?.workspace_relative_path,
    "outputs/agent_answer-answer.md"
  );
});

test("rejects unsafe workspace relative paths", () => {
  assert.throws(() =>
    normalizeOpenClawOptions({
      request: {
        request_type: "execute_agent",
        app_id: "app_001",
        session_id: "sess_001",
        agent_backend: "openclaw_cli",
        agent_query: "Write output.",
        context: {
          openclaw: {
            expected_outputs: [
              {
                output_id: "bad",
                purpose: "answer",
                display_name: "bad.md",
                media_type: "text/markdown",
                required: true,
                workspace_relative_path: "../bad.md",
                persist_as_artifact: true
              }
            ]
          }
        }
      },
      executionId: "execution_001"
    })
  );
});
