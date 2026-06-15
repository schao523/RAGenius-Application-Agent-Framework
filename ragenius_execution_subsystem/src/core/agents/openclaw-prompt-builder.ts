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
      } else {
        lines.push(
          `- ${stagedInput.input_id}: metadata only (${stagedInput.display_name})`
        );
        if (stagedInput.metadata) {
          lines.push(`  metadata: ${JSON.stringify(stagedInput.metadata)}`);
        }
      }
    }
    lines.push(
      "",
      "Artifact consumption rules:",
      "- Read every staged input file before answering.",
      "- Treat staged input files as the primary source of truth for this task.",
      "- Do not answer from the user task alone when staged inputs are present.",
      "- Use only staged input paths and other files under the workspace root."
    );
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

  lines.push(
    "",
    "Final response rules:",
    "- Report whether each staged input was read.",
    "- Report the exact staged input path(s) used.",
    "- If you created an output file, report the exact output path.",
    "- If required outputs were listed, report whether each required output exists.",
    "- Keep the final response concise.",
    "- Do not include full file contents unless the user explicitly asked for them."
  );

  lines.push("", "Return a concise status summary.");
  return lines.join("\n");
}
