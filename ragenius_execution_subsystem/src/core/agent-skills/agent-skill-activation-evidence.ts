import type { ResolvedAgentSkillSelection } from "./agent-skill-types.js";
import path from "node:path";
import type {
  AgentSkillProviderSelection
} from "../agents/agent-provider-context.js";
import type { CodexCliCommandEvent } from "../agents/codex-cli-types.js";
import { runSupervisedProcess } from "../../../scripts/agent_process_supervisor.js";

export type AgentSkillActivation = {
  requested_agent_skill_id?: string;
  requested_provider_skill_name?: string;
  resolved_agent_skill_id?: string;
  resolved_provider_skill_name?: string;
  resolved_fingerprint?: string;
  activation_method:
    | "auto"
    | "codex_explicit_reference"
    | "codex_prompt_guidance"
    | "openclaw_prompt_guidance";
  activation_status:
    | "not_requested"
    | "projected"
    | "process_observed"
    | "not_observed"
    | "failed";
  evidence_level: "none" | "agent_reported" | "process_observed";
  evidence_summary?: string;
};

export function projectAgentSkillSelection(
  selection: ResolvedAgentSkillSelection
): AgentSkillProviderSelection {
  return {
    activation_method: selection.activation_method,
    agent_skill_id: selection.agent_skill_id,
    approved_fingerprint: selection.approved_fingerprint,
    backend: selection.backend,
    display_name: selection.display_name,
    observed_fingerprint: selection.observed_fingerprint,
    provider_skill_name: selection.provider_skill_name,
    provider_skill_reference: selection.provider_skill_reference,
    runtime_target_id: selection.runtime_target_id,
    source_id: selection.source_id
  };
}

function autoActivation(): AgentSkillActivation {
  return {
    activation_method: "auto",
    activation_status: "not_requested",
    evidence_level: "none"
  };
}

function selectedActivation(
  selection: AgentSkillProviderSelection,
  evidence: {
    processObserved: boolean;
    agentReported: boolean;
    providerFailed?: boolean;
    observationSource: string;
  }
): AgentSkillActivation {
  const evidenceLevel = evidence.processObserved
    ? "process_observed"
    : evidence.agentReported
      ? "agent_reported"
      : "none";
  return {
    requested_agent_skill_id: selection.agent_skill_id,
    requested_provider_skill_name: selection.provider_skill_name,
    resolved_agent_skill_id: selection.agent_skill_id,
    resolved_provider_skill_name: selection.provider_skill_name,
    resolved_fingerprint: selection.observed_fingerprint,
    activation_method: selection.activation_method,
    activation_status: evidence.processObserved
      ? "process_observed"
      : evidence.providerFailed
        ? "failed"
        : "not_observed",
    evidence_level: evidenceLevel,
    evidence_summary: evidence.processObserved
      ? `Observed the selected skill instructions through ${evidence.observationSource}.`
      : evidence.agentReported
        ? "The agent reported using the selected skill, but no process evidence was observed."
        : "No process evidence of the selected skill was observed."
  };
}

function normalizedPathText(value: string): string {
  return value.replaceAll("\\", "/").replace(/\/{2,}/g, "/").toLowerCase();
}

function includesSkillManifest(value: string, providerSkillName: string): boolean {
  const normalized = normalizedPathText(value);
  const skillName = providerSkillName.trim().toLowerCase();
  return Boolean(skillName) && normalized.includes(`/${skillName}/skill.md`);
}

function reportsSkill(value: string, providerSkillName: string): boolean {
  return value.toLowerCase().includes(providerSkillName.trim().toLowerCase());
}

function hasCodexReadCommand(command: string): boolean {
  return /^(?:get-content|cat|type|sed|head|tail)\b|\s-(?:command|c)\s+["']?(?:get-content|cat|type|sed|head|tail)\b/i
    .test(command.trim());
}

export function activationFromCodex(input: {
  selection: AgentSkillProviderSelection | null | undefined;
  commandEvents: CodexCliCommandEvent[];
  reportedSkillNames: string[];
  providerFailed?: boolean;
}): AgentSkillActivation {
  if (!input.selection) return autoActivation();
  const processObserved = input.commandEvents.some((event) =>
    event.exit_code === 0 &&
    hasCodexReadCommand(event.command) &&
    includesSkillManifest(event.command, input.selection!.provider_skill_name)
  );
  const agentReported = input.reportedSkillNames.some((name) =>
    name.trim().toLowerCase() === input.selection!.provider_skill_name.trim().toLowerCase()
  );
  return selectedActivation(input.selection, {
    processObserved,
    agentReported,
    ...(input.providerFailed !== undefined
      ? { providerFailed: input.providerFailed }
      : {}),
    observationSource: "a Codex command event"
  });
}

export function activationFromOpenClaw(input: {
  selection: AgentSkillProviderSelection | null | undefined;
  reportedText: string;
  validatedSessionTrace?: string;
  providerFailed?: boolean;
}): AgentSkillActivation {
  if (!input.selection) return autoActivation();
  const trace = input.validatedSessionTrace ?? "";
  const processObserved =
    /\b(?:read|get-content|cat|type|sed|head|tail)\b/i.test(trace) &&
    includesSkillManifest(trace, input.selection.provider_skill_name);
  return selectedActivation(input.selection, {
    processObserved,
    agentReported: reportsSkill(
      input.reportedText,
      input.selection.provider_skill_name
    ),
    ...(input.providerFailed !== undefined
      ? { providerFailed: input.providerFailed }
      : {}),
    observationSource: "a contained OpenClaw session trace"
  });
}

export function openClawAgentSessionRoot(
  agentId: string,
  workspaceRoot = "/home/openclaw/.openclaw/workspace"
): string {
  if (!/^[A-Za-z0-9._-]+$/.test(agentId)) {
    throw new Error("OpenClaw agent id is invalid for session inspection.");
  }
  return path.posix.join(
    path.posix.dirname(workspaceRoot),
    "agents",
    agentId,
    "sessions"
  );
}

export function extractOpenClawSessionFile(value: unknown): string | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const result = (value as Record<string, unknown>).result;
  if (!result || typeof result !== "object" || Array.isArray(result)) return undefined;
  const meta = (result as Record<string, unknown>).meta;
  if (!meta || typeof meta !== "object" || Array.isArray(meta)) return undefined;
  const agentMeta = (meta as Record<string, unknown>).agentMeta;
  if (!agentMeta || typeof agentMeta !== "object" || Array.isArray(agentMeta)) {
    return undefined;
  }
  const sessionFile = (agentMeta as Record<string, unknown>).sessionFile;
  return typeof sessionFile === "string" && sessionFile.startsWith("/")
    ? sessionFile
    : undefined;
}

const OPENCLAW_TRACE_SCRIPT = [
  "import pathlib,sys",
  "root=pathlib.Path(sys.argv[1]).resolve(strict=True)",
  "target=pathlib.Path(sys.argv[2]).resolve(strict=True)",
  "limit=int(sys.argv[3])",
  "try: target.relative_to(root)",
  "except ValueError: print('OpenClaw session trace escapes agent state', file=sys.stderr); sys.exit(73)",
  "if not target.is_file(): sys.exit(74)",
  "with target.open('rb') as handle:",
  " handle.seek(0,2); size=handle.tell(); handle.seek(max(0,size-limit)); data=handle.read(limit)",
  "sys.stdout.buffer.write(data)"
].join("\n");

export async function readContainedOpenClawSessionTrace(input: {
  wslDistro: string;
  agentId: string;
  sessionFile: string;
  workspaceRoot?: string;
  maxBytes?: number;
}): Promise<string> {
  const maxBytes = Math.min(Math.max(input.maxBytes ?? 65536, 1024), 262144);
  const result = await runSupervisedProcess({
    command: "wsl",
    args: [
      "-d",
      input.wslDistro,
      "--exec",
      "python3",
      "-c",
      OPENCLAW_TRACE_SCRIPT,
      openClawAgentSessionRoot(input.agentId, input.workspaceRoot),
      input.sessionFile,
      String(maxBytes)
    ],
    timeoutMs: 5000,
    maxStdoutBytes: maxBytes,
    maxStderrBytes: 4096
  });
  if (result.timedOut || result.exitCode !== 0) {
    throw new Error("OpenClaw session trace inspection failed.");
  }
  return result.stdout;
}

export function fallbackAgentSkillActivation(input: {
  selection: AgentSkillProviderSelection | null | undefined;
  reportedSkillNames?: string[];
  reportedText?: string;
  providerFailed?: boolean;
}): AgentSkillActivation {
  if (input.selection?.backend === "openclaw_cli") {
    return activationFromOpenClaw({
      selection: input.selection,
      reportedText: input.reportedText ?? "",
      ...(input.providerFailed !== undefined
        ? { providerFailed: input.providerFailed }
        : {})
    });
  }
  return activationFromCodex({
    selection: input.selection,
    commandEvents: [],
    reportedSkillNames: input.reportedSkillNames ?? [],
    ...(input.providerFailed !== undefined
      ? { providerFailed: input.providerFailed }
      : {})
  });
}
