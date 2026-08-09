import assert from "node:assert/strict";
import path from "node:path";

import {
  activationFromCodex
} from "../src/core/agent-skills/agent-skill-activation-evidence.js";
import type { AgentSkillProviderSelection } from "../src/core/agents/agent-provider-context.js";
import { runSupervisedProcess } from "./agent_process_supervisor.js";
import { buildCodexArgs, parseCodexJsonl } from "./codex_cli_protocol.js";

type Method = "codex_explicit_reference" | "codex_prompt_guidance";

function configuredArgs(): string[] {
  const raw = process.env.CODEX_CLI_ARGS_JSON ?? '["exec","--json"]';
  const parsed = JSON.parse(raw) as unknown;
  assert.ok(Array.isArray(parsed) && parsed.every((item) => typeof item === "string"));
  return parsed;
}

function prompt(method: Method, skillName: string): string {
  const activation = method === "codex_explicit_reference"
    ? [`$${skillName}`]
    : [
        `Selected Agent skill: ${skillName}`,
        `Use the installed Codex skill named \`${skillName}\` for this task.`,
        "Follow its instructions, but do not extend the approved RAGenius operation plan."
      ];
  return [
    ...activation,
    "You are executing inside the RAGenius execution subsystem.",
    "",
    "RAGenius authorization:",
    "- State: not_required",
    "- Permission scope: agent.read",
    "- No RAGenius confirmation was required for this request.",
    "",
    "Approved operation plan:",
    "- operation_id: agent_read",
    "  kind: read",
    "  required: true",
    "  minimum_verification: process_observed",
    "  description: Load the selected skill instructions for an activation smoke test.",
    "- Unknown operation IDs are unauthorized and do not count as completion.",
    "",
    "User request:",
    "Activation smoke test only. Read the selected skill SKILL.md, do not search the web or modify files.",
    "",
    "Final response requirements:",
    "Return exactly one JSON object with no text before or after it.",
    JSON.stringify({
      task_status: "completed",
      summary: "SKILL_ACTIVATED",
      activated_skills: [skillName],
      operations: [{
        operation_id: "agent_read",
        operation: "Load selected skill instructions",
        status: "completed"
      }],
      artifacts: [],
      errors: []
    })
  ].join("\n");
}

async function runVersion(command: string): Promise<string> {
  const result = await runSupervisedProcess({
    command,
    args: ["--version"],
    timeoutMs: 10000,
    maxStdoutBytes: 4096,
    maxStderrBytes: 4096
  });
  return result.stdout.trim() || result.stderr.trim() || "unknown";
}

async function runMethod(input: {
  command: string;
  method: Method;
  selection: AgentSkillProviderSelection;
  workspace: string;
}) {
  const args = buildCodexArgs(configuredArgs(), {
    workspaceAbsolutePath: input.workspace,
    sandboxMode: process.env.CODEX_CLI_SANDBOX_MODE === "read-only"
      ? "read-only"
      : "workspace-write",
    networkAccess: "deny",
    additionalWritableDirs: []
  });
  const startedAt = Date.now();
  const result = await runSupervisedProcess({
    command: input.command,
    args,
    cwd: input.workspace,
    stdin: prompt(input.method, input.selection.provider_skill_name),
    timeoutMs: Number(process.env.CODEX_CLI_TIMEOUT_MS ?? 300000),
    maxStdoutBytes: 4_194_304,
    maxStderrBytes: 65_536
  });
  const protocol = parseCodexJsonl(result.stdout, {
    maxOutputBytes: 16384,
    rawExitCode: result.exitCode ?? -1
  });
  const activation = activationFromCodex({
    selection: { ...input.selection, activation_method: input.method },
    commandEvents: protocol.command_events,
    reportedSkillNames: [] ,
    providerFailed:
      result.timedOut || result.exitCode !== 0 || protocol.turn_status !== "completed"
  });
  return {
    method: input.method,
    duration_ms: Date.now() - startedAt,
    exit_code: result.exitCode,
    timed_out: result.timedOut,
    turn_status: protocol.turn_status,
    command_count: protocol.command_events.length,
    command_events: protocol.command_events.map((event) => ({
      command: event.command,
      exit_code: event.exit_code
    })),
    activation_status: activation.activation_status,
    evidence_level: activation.evidence_level
  };
}

async function main(): Promise<void> {
  const skillName = String(process.env.CODEX_AGENT_SKILL_SMOKE_NAME ?? "").trim();
  assert.match(
    skillName,
    /^[a-z0-9]+(?:-[a-z0-9]+)*$/,
    "Set CODEX_AGENT_SKILL_SMOKE_NAME to an installed read-only test skill."
  );
  const command = String(process.env.CODEX_CLI_COMMAND ?? "codex").trim() || "codex";
  const workspace = path.resolve(
    process.env.CODEX_AGENT_SKILL_SMOKE_WORKSPACE ?? process.cwd()
  );
  const selection: AgentSkillProviderSelection = {
    activation_method: "codex_explicit_reference",
    agent_skill_id: "smoke-agent-skill",
    approved_fingerprint: "smoke-fingerprint",
    backend: "codex_cli",
    display_name: skillName,
    observed_fingerprint: "smoke-fingerprint",
    provider_skill_name: skillName,
    provider_skill_reference: skillName,
    runtime_target_id: "codex-smoke",
    source_id: "smoke-source"
  };
  const results = [];
  for (const method of [
    "codex_explicit_reference",
    "codex_prompt_guidance"
  ] as const) {
    results.push(await runMethod({ command, method, selection, workspace }));
  }
  const chosen = results.find((result) =>
    result.method === "codex_explicit_reference" &&
    result.activation_status === "process_observed"
  ) ?? results.find((result) => result.activation_status === "process_observed");
  if (!chosen) {
    console.error(JSON.stringify({ diagnostic_results: results }, null, 2));
  }
  assert.ok(chosen, "Neither Codex activation method produced process-observed evidence.");
  console.log(JSON.stringify({
    codex_version: await runVersion(command),
    configured_args: configuredArgs(),
    skill_name: skillName,
    workspace,
    results,
    chosen_method: chosen.method
  }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
