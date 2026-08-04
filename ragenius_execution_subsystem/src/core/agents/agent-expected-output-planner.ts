import type {
  AgentExpectedOutput,
  ExecuteAgentRequest
} from "../../api/schemas/execution-request.schema.js";

export type PlannedAgentExpectedOutput = {
  output_id: string;
  display_name: string;
  media_type: string;
  required: boolean;
  persist_as_artifact: boolean;
  artifact_type: "agent_output";
  min_size_bytes?: number;
  expected_sha256?: string;
};

export interface AgentExpectedOutputPlannerInput {
  request: ExecuteAgentRequest;
  generateDefaultOutput?: boolean;
}

function inferDisplayName(outputId: string): string {
  return `${outputId}.md`;
}

function inferMediaType(displayName: string, mediaType?: string): string {
  if (mediaType) {
    return mediaType;
  }
  if (displayName.toLowerCase().endsWith(".md")) {
    return "text/markdown";
  }
  return "application/octet-stream";
}

function normalizeExpectedOutput(
  output: AgentExpectedOutput
): PlannedAgentExpectedOutput {
  const displayName = output.display_name ?? inferDisplayName(output.output_id);
  const required = output.required ?? false;

  return {
    output_id: output.output_id,
    display_name: displayName,
    media_type: inferMediaType(displayName, output.media_type),
    required,
    persist_as_artifact: output.persist_as_artifact ?? required,
    artifact_type: output.artifact_type ?? "agent_output",
    ...(typeof output.min_size_bytes === "number"
      ? { min_size_bytes: output.min_size_bytes }
      : {}),
    ...(output.expected_sha256 ? { expected_sha256: output.expected_sha256 } : {})
  };
}

function defaultOpenClawOutput(): PlannedAgentExpectedOutput {
  return {
    output_id: "openclaw_answer",
    display_name: "openclaw-result.md",
    media_type: "text/markdown",
    required: true,
    persist_as_artifact: true,
    artifact_type: "agent_output",
    min_size_bytes: 1
  };
}

export function planAgentExpectedOutputs(
  input: AgentExpectedOutputPlannerInput
): PlannedAgentExpectedOutput[] {
  const explicitOutputs = input.request.expected_outputs ?? [];

  if (explicitOutputs.length > 0) {
    return explicitOutputs.map(normalizeExpectedOutput);
  }

  if (input.generateDefaultOutput) {
    return [defaultOpenClawOutput()];
  }

  return [];
}
