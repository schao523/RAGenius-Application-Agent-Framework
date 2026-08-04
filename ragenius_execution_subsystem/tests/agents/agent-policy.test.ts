import assert from "node:assert/strict";
import test from "node:test";

import { classifyAgentRequest } from "../../src/core/agents/agent-policy.js";

const expectedOutput = [{
  output_id: "agent_output",
  media_type: "text/markdown",
  persist_as_artifact: true
}];

test("classifies a declared local report output as a scoped workspace write", () => {
  const policy = classifyAgentRequest({
    request_type: "execute_agent",
    app_id: "app_001",
    session_id: "session_001",
    agent_backend: "codex_cli",
    agent_query: "Answer the questions in the selected artifact and create a report",
    expected_outputs: expectedOutput
  });

  assert.equal(policy.riskClass, "agent_workspace_write");
  assert.equal(policy.workspaceAccess, "scoped_write");
  assert.equal(policy.networkAccess, "deny");
});

test("keeps explicit uploads classified as external writes", () => {
  const policy = classifyAgentRequest({
    request_type: "execute_agent",
    app_id: "app_001",
    session_id: "session_001",
    agent_backend: "codex_cli",
    agent_query: "Create a report and upload it to the external service",
    expected_outputs: expectedOutput
  });

  assert.equal(policy.riskClass, "agent_external_write");
  assert.equal(policy.networkAccess, "allowlisted");
});

test("keeps NotebookLM generation classified as an external write", () => {
  const policy = classifyAgentRequest({
    request_type: "execute_agent",
    app_id: "app_001",
    session_id: "session_001",
    agent_backend: "codex_cli",
    agent_skill_hint: "notebooklm",
    agent_query: "Create a study report",
    expected_outputs: expectedOutput
  });

  assert.equal(policy.riskClass, "agent_external_write");
  assert.equal(policy.networkAccess, "allowlisted");
});

test("keeps NotebookLM summaries read-only when no write is requested", () => {
  const policy = classifyAgentRequest({
    request_type: "execute_agent",
    app_id: "app_001",
    session_id: "session_001",
    agent_backend: "codex_cli",
    agent_skill_hint: "notebooklm",
    agent_query: "Use NotebookLM to summarize Micah 2."
  });

  assert.equal(policy.riskClass, "agent_read_only");
  assert.equal(policy.mode, "auto_allow");
  assert.equal(policy.workspaceAccess, "none");
  assert.equal(policy.providerStateAccess, "scoped_write");
  assert.deepEqual(policy.providerStateLabels, ["notebooklm_profile:default"]);
});

test("plain Codex requests do not receive provider-state access", () => {
  const policy = classifyAgentRequest({
    request_type: "execute_agent",
    app_id: "app_001",
    session_id: "session_001",
    agent_backend: "codex_cli",
    agent_query: "Summarize the supplied text."
  });

  assert.equal(policy.providerStateAccess, "none");
  assert.deepEqual(policy.providerStateLabels, []);
});

test("OpenClaw requests declare scoped agent-state access", () => {
  const policy = classifyAgentRequest({
    request_type: "execute_agent",
    app_id: "app_001",
    session_id: "session_001",
    agent_backend: "openclaw_cli",
    agent_query: "Summarize the supplied text."
  });

  assert.equal(policy.providerStateAccess, "scoped_write");
  assert.deepEqual(policy.providerStateLabels, ["openclaw_agent_state"]);
});

test("bounded negation does not classify a prohibition as destructive", () => {
  const policy = classifyAgentRequest({
    request_type: "execute_agent",
    app_id: "app_001",
    session_id: "session_001",
    agent_backend: "codex_cli",
    agent_query: "Review the files, but do not delete files."
  });

  assert.notEqual(policy.riskClass, "agent_destructive");
});

test("an affirmative delete request remains destructive", () => {
  const policy = classifyAgentRequest({
    request_type: "execute_agent",
    app_id: "app_001",
    session_id: "session_001",
    agent_backend: "codex_cli",
    agent_query: "Delete the file."
  });

  assert.equal(policy.riskClass, "agent_destructive");
});
