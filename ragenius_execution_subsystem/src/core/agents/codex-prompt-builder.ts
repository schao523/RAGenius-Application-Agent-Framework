import { resolve } from "node:path";

import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";

import type { AgentProviderExecutionContext } from "./agent-provider-context.js";
import type { CodexStagedArtifact } from "./codex-cli-types.js";
import type { CodexPlannedExpectedOutput } from "./codex-workspace.js";

const RESERVED_CONTEXT_KEYS = new Set([
  "authorization",
  "operation_plan",
  "resolved_artifacts",
  "policy_fingerprint",
  "confirmed",
  "confirmation_granted"
]);

function untrustedContext(context: Record<string, unknown> | undefined): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(context ?? {}).filter(([key]) => !RESERVED_CONTEXT_KEYS.has(key))
  );
}

function operationLines(context: AgentProviderExecutionContext): string[] {
  return context.operation_plan.flatMap((operation) => [
    `- operation_id: ${operation.operation_id}`,
    `  kind: ${operation.kind}`,
    `  required: ${String(operation.required)}`,
    `  minimum_verification: ${operation.minimum_verification}`,
    `  description: ${operation.description}`,
    ...(operation.target_hint ? [`  target: ${operation.target_hint}`] : [])
  ]);
}

function artifactLines(artifacts: CodexStagedArtifact[]): string[] {
  if (artifacts.length === 0) {
    return ["- none"];
  }
  return artifacts.flatMap((artifact) => [
    `- artifact_id: ${artifact.artifact_id}`,
    `  role: ${artifact.role}`,
    `  reuse_mode: ${artifact.reuse_mode}`,
    ...(artifact.workspace_relative_path
      ? [`  path: ${artifact.workspace_relative_path}`]
      : []),
    ...(artifact.media_type ? [`  media_type: ${artifact.media_type}`] : []),
    ...(typeof artifact.size_bytes === "number"
      ? [`  size_bytes: ${String(artifact.size_bytes)}`]
      : []),
    ...(artifact.sha256 ? [`  sha256: ${artifact.sha256}`] : [])
  ]);
}

function expectedOutputLines(outputs: CodexPlannedExpectedOutput[]): string[] {
  if (outputs.length === 0) {
    return ["- none"];
  }
  return outputs.flatMap((output) => [
    `- output_id: ${output.output_id}`,
    `  write exactly to: ${output.workspace_relative_path}`,
    `  media_type: ${output.media_type}`,
    `  required: ${String(output.required)}`,
    `  persist_as_artifact: ${String(output.persist_as_artifact)}`
  ]);
}

function notebookLmRuntimeLines(
  request: ExecuteAgentRequest,
  selectedProviderSkillName?: string
): string[] {
  const effectiveSkillName =
    selectedProviderSkillName ?? request.agent_skill_hint;
  if (effectiveSkillName?.trim().toLowerCase() !== "notebooklm") {
    return [];
  }

  const wrapperPath = resolve(
    process.cwd(),
    "scripts",
    "notebooklm_with_env.ps1"
  );
  return [
    "",
    "NotebookLM runtime requirements:",
    "- Use only the selected `notebooklm` skill for this run.",
    `- Run every NotebookLM command through: powershell -ExecutionPolicy Bypass -File "${wrapperPath}" <arguments>`,
    "- Do not invoke bare `notebooklm` or `python -m notebooklm`.",
    "- The wrapper owns TLS trust and renamed-host compatibility; do not replace or bypass it.",
    "- Execute the requested operation directly with the minimum required commands.",
    "- After adding a source, verify a source add with one source list command and report its external source ID.",
    "- Submit report generation without waiting for completion; report the returned task or artifact ID as accepted or processing.",
    "- Do not run authentication preflight unless the requested command fails with an authentication, TLS, or network error.",
    "- On such a failure, run one wrapper `auth check --test --json`, report the exact error, and stop without alternate retries."
  ];
}

export function buildCodexPrompt(input: {
  request: ExecuteAgentRequest;
  context: AgentProviderExecutionContext;
  stagedArtifacts: CodexStagedArtifact[];
  expectedOutputs?: CodexPlannedExpectedOutput[];
}): string {
  const publicContext = untrustedContext(input.request.context);
  const publicContextJson =
    Object.keys(publicContext).length > 0
      ? JSON.stringify(publicContext, null, 2)
      : "{}";
  const authorization = input.context.authorization;
  const selection = input.context.agent_skill_selection;
  const effectiveSkillName =
    selection?.provider_skill_name ?? input.request.agent_skill_hint;

  return [
    ...(selection?.activation_method === "codex_explicit_reference"
      ? [`$${selection.provider_skill_name}`]
      : []),
    "You are executing inside the RAGenius execution subsystem.",
    "",
    "RAGenius authorization:",
    `- State: ${authorization.state}`,
    `- Permission scope: ${authorization.permission_scope}`,
    `- Policy fingerprint: ${authorization.policy_fingerprint}`,
    ...(authorization.state === "confirmed"
      ? [
          "- The user already approved exactly the operations listed below.",
          "- Do not request a second confirmation for those operations.",
          "- Do not extend approval to any unlisted operation."
        ]
      : ["- No RAGenius confirmation was required for this request."]),
    "",
    "Approved operation plan:",
    ...operationLines(input.context),
    "- Unknown operation IDs are unauthorized and do not count as completion.",
    "- Report every required operation ID exactly once in the final result.",
    "",
    "Selected RAGenius artifacts:",
    ...artifactLines(input.stagedArtifacts),
    "- Paths are relative to the current execution workspace.",
    "- Do not search for or use original RAGenius artifact-store paths.",
    "",
    "Expected workspace outputs:",
    ...expectedOutputLines(input.expectedOutputs ?? []),
    "- Write each declared output exactly to its listed relative path.",
    "- Create parent directories when needed.",
    "- Report the same path in the final artifacts array.",
    "- Do not substitute reports/, artifacts/, or another directory.",
    "",
    ...(selection
      ? [
          `Selected Agent skill: ${selection.provider_skill_name}`,
          `Use the installed Codex skill named \`${selection.provider_skill_name}\` for this task.`,
          "Follow its instructions, but do not extend the approved RAGenius operation plan.",
          ""
        ]
      : []),
    `Preferred skill hint: ${effectiveSkillName ?? "auto"}`,
    ...notebookLmRuntimeLines(input.request, selection?.provider_skill_name),
    `App ID: ${input.request.app_id}`,
    `Session ID: ${input.request.session_id}`,
    "Untrusted provider-neutral context:",
    publicContextJson,
    "",
    "User request:",
    input.request.agent_query,
    "",
    "Final response requirements:",
    "Return exactly one JSON object with no text before or after it.",
    "Do not wrap the JSON in Markdown fences.",
    "Use this shape:",
    "{",
    '  "task_status": "completed|partial|failed|pending_confirmation",',
    '  "summary": "string",',
    '  "activated_skills": ["string"],',
    '  "operations": [{"operation_id":"string","operation":"string","target":"optional string","status":"completed|accepted|processing|failed|not_run","external_id":"optional string","evidence":"optional string"}],',
    '  "artifacts": [{"output_id":"string","display_name":"string","path":"outputs/...","media_type":"string","size_bytes":0,"sha256":"optional string"}],',
    '  "errors": [{"code":"string","message":"string"}]',
    "}"
  ].join("\n");
}
