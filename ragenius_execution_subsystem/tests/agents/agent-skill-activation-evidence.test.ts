import assert from "node:assert/strict";
import test from "node:test";

import {
  activationFromCodex,
  activationFromOpenClaw,
  openClawAgentSessionRoot
} from "../../src/core/agent-skills/agent-skill-activation-evidence.js";
import type { AgentSkillProviderSelection } from "../../src/core/agents/agent-provider-context.js";

const selection: AgentSkillProviderSelection = {
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
};

test("Codex requires a successful structured SKILL.md read for process evidence", () => {
  const reported = activationFromCodex({
    selection,
    reportedSkillNames: ["approved-skill"],
    commandEvents: []
  });
  assert.equal(reported.activation_status, "not_observed");
  assert.equal(reported.evidence_level, "agent_reported");

  const observed = activationFromCodex({
    selection,
    reportedSkillNames: [],
    commandEvents: [{
      item_id: "command-1",
      command: "Get-Content -Raw C:\\Users\\runner\\.codex\\skills\\approved-skill\\SKILL.md",
      exit_code: 0
    }]
  });
  assert.equal(observed.activation_status, "process_observed");
  assert.equal(observed.evidence_level, "process_observed");
  assert.doesNotMatch(observed.evidence_summary ?? "", /C:\\Users/);

  const escapedWindowsCommand = activationFromCodex({
    selection,
    reportedSkillNames: [],
    commandEvents: [{
      item_id: "command-2",
      command: String.raw`Get-Content -Raw C:\\Users\\runner\\.codex\\skills\\approved-skill\\SKILL.md`,
      exit_code: 0
    }]
  });
  assert.equal(escapedWindowsCommand.activation_status, "process_observed");

  const quotedClaim = activationFromCodex({
    selection,
    reportedSkillNames: [],
    commandEvents: [{
      item_id: "command-3",
      command: String.raw`Write-Output 'Get-Content C:\\skills\\approved-skill\\SKILL.md'`,
      exit_code: 0
    }]
  });
  assert.equal(quotedClaim.activation_status, "not_observed");
});

test("OpenClaw model text is reported evidence while a validated trace is process evidence", () => {
  const openClawSelection: AgentSkillProviderSelection = {
    ...selection,
    activation_method: "openclaw_prompt_guidance",
    backend: "openclaw_cli",
    runtime_target_id: "main"
  };
  const reported = activationFromOpenClaw({
    selection: openClawSelection,
    reportedText: "I used the approved-skill skill for this task."
  });
  assert.equal(reported.activation_status, "not_observed");
  assert.equal(reported.evidence_level, "agent_reported");

  const observed = activationFromOpenClaw({
    selection: openClawSelection,
    reportedText: "",
    validatedSessionTrace:
      '{"tool":"read","path":"/home/openclaw/.openclaw/skills/approved-skill/SKILL.md"}'
  });
  assert.equal(observed.activation_status, "process_observed");
  assert.equal(observed.evidence_level, "process_observed");
  assert.doesNotMatch(observed.evidence_summary ?? "", /\/home\/openclaw/);
});

test("Auto execution reports that no skill was requested", () => {
  const activation = activationFromCodex({
    selection: null,
    reportedSkillNames: ["untrusted-model-claim"],
    commandEvents: []
  });
  assert.equal(activation.activation_method, "auto");
  assert.equal(activation.activation_status, "not_requested");
  assert.equal(activation.evidence_level, "none");
});

test("derives the contained OpenClaw session root from the configured workspace", () => {
  assert.equal(
    openClawAgentSessionRoot("main", "/srv/openclaw/state/workspace"),
    "/srv/openclaw/state/agents/main/sessions"
  );
});
