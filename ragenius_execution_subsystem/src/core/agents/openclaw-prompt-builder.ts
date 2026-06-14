import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";

import type { NormalizedOpenClawProviderOptions } from "./openclaw-cli-types.js";

export function buildOpenClawPrompt(input: {
  request: ExecuteAgentRequest;
  workspaceRoot: string;
  options: NormalizedOpenClawProviderOptions;
}): string {
  const lines = [
    "You are executing a RAGenius OpenClaw task.",
    `Workspace root: ${input.workspaceRoot}`,
    "Use only paths inside the workspace root.",
    "Do not use Windows paths, /mnt/c, or /mnt/d.",
    "",
    "User task:",
    input.request.agent_query
  ];

  if (input.options.staged_inputs.length > 0) {
    lines.push("", "Staged inputs:");
    for (const stagedInput of input.options.staged_inputs) {
      if (stagedInput.workspace_relative_path) {
        lines.push(
          `- ${stagedInput.input_id}: ${input.workspaceRoot}/${stagedInput.workspace_relative_path}`
        );
      }
    }
  }

  if (input.options.expected_outputs.length > 0) {
    lines.push("", "Required outputs:");
    for (const output of input.options.expected_outputs) {
      const relativePath =
        output.workspace_relative_path ??
        `outputs/${output.output_id}-${output.display_name}`;
      lines.push(
        `- ${output.output_id}: write exactly to ${input.workspaceRoot}/${relativePath}`
      );
    }
    lines.push("Verify each required output exists before responding.");
  }

  lines.push("", "Return a concise status summary.");
  return lines.join("\n");
}
