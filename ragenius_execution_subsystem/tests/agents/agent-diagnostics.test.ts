import assert from "node:assert/strict";
import test from "node:test";

import { mergeAgentDiagnostics } from "../../src/core/agents/agent-diagnostics.js";

test("persistence failure does not replace provider authentication failure", () => {
  const result = mergeAgentDiagnostics(
    { code: "NOTEBOOKLM_AUTH_FAILED", message: "Authentication failed." },
    [
      {
        stage: "persistence",
        code: "CODEX_OUTPUT_PERSIST_FAILED",
        message: "save failed"
      }
    ]
  );

  assert.equal(result.primary?.code, "NOTEBOOKLM_AUTH_FAILED");
  assert.equal(result.secondary?.[0]?.code, "CODEX_OUTPUT_PERSIST_FAILED");
  assert.equal(result.failure_code, "NOTEBOOKLM_AUTH_FAILED");
  assert.equal(result.failure_message, "Authentication failed.");
});

test("promotes the first secondary failure only when no primary exists", () => {
  const result = mergeAgentDiagnostics(undefined, [
    {
      stage: "verification",
      code: "AGENT_OUTPUT_VERIFICATION_FAILED",
      message: "Output was missing."
    }
  ]);

  assert.equal(result.primary?.code, "AGENT_OUTPUT_VERIFICATION_FAILED");
  assert.deepEqual(result.secondary, []);
});
