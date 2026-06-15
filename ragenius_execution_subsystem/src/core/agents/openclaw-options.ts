import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";

import {
  planAgentExpectedOutputs,
  type PlannedAgentExpectedOutput
} from "./agent-expected-output-planner.js";
import {
  type NormalizedOpenClawProviderOptions,
  type OpenClawExpectedOutput,
  type OpenClawExecutionMode,
  type OpenClawProviderOptions,
  type OpenClawStagedInput
} from "./openclaw-cli-types.js";

const OUTPUT_REQUIRED_TERMS = [
  "create",
  "write",
  "export",
  "save",
  "generate",
  "produce",
  "transform",
  "convert",
  "prepare"
];

export function normalizeOpenClawOptions(input: {
  request: ExecuteAgentRequest;
  executionId: string;
}): NormalizedOpenClawProviderOptions {
  const rawOptions = readRawOptions(input.request);
  validateTimeout(rawOptions.timeout_ms);

  const stagedInputs = validateStagedInputs(rawOptions.staged_inputs ?? []);
  const plannedOutputs = planAgentExpectedOutputs({ request: input.request });
  let expectedOutputs =
    plannedOutputs.length > 0
      ? validateExpectedOutputs(plannedOutputs.map(plannedOutputToOpenClawOutput))
      : validateExpectedOutputs(rawOptions.expected_outputs ?? []);
  let executionMode = classifyOpenClawExecutionMode({
    request: input.request,
    options: rawOptions,
    stagedInputs,
    expectedOutputs
  });

  if (
    executionMode === "output_required" &&
    expectedOutputs.length === 0
  ) {
    expectedOutputs = planAgentExpectedOutputs({
      request: input.request,
      generateDefaultOutput: true
    }).map(plannedOutputToOpenClawOutput);
  }
  expectedOutputs = expectedOutputs.map((output) => ({
    ...output,
    workspace_relative_path:
      output.workspace_relative_path ?? defaultOutputPath(output)
  }));

  return {
    ...rawOptions,
    execution_mode: executionMode,
    staged_inputs: stagedInputs,
    expected_outputs: expectedOutputs
  };
}

function plannedOutputToOpenClawOutput(
  output: PlannedAgentExpectedOutput
): OpenClawExpectedOutput {
  return {
    output_id: output.output_id,
    purpose: "answer",
    display_name: output.display_name,
    media_type: output.media_type,
    required: output.required,
    persist_as_artifact: output.persist_as_artifact,
    artifact_type: output.artifact_type,
    artifact_role: "final",
    ...(typeof output.min_size_bytes === "number"
      ? { min_size_bytes: output.min_size_bytes }
      : {}),
    ...(output.expected_sha256 ? { expected_sha256: output.expected_sha256 } : {})
  };
}

function readRawOptions(request: ExecuteAgentRequest): OpenClawProviderOptions {
  const context = request.context;
  const openclaw =
    context &&
    typeof context === "object" &&
    !Array.isArray(context) &&
    "openclaw" in context
      ? (context.openclaw as unknown)
      : undefined;

  if (!openclaw || typeof openclaw !== "object" || Array.isArray(openclaw)) {
    return {};
  }

  return openclaw as OpenClawProviderOptions;
}

function validateTimeout(timeoutMs: number | undefined): void {
  if (timeoutMs !== undefined && timeoutMs < 1000) {
    throw new Error("OpenClaw timeout_ms must be at least 1000.");
  }
}

function validateStagedInputs(inputs: OpenClawStagedInput[]): OpenClawStagedInput[] {
  const seen = new Set<string>();
  return inputs.map((input) => {
    if (seen.has(input.input_id)) {
      throw new Error(`Duplicate OpenClaw staged input id: ${input.input_id}`);
    }
    seen.add(input.input_id);
    if (input.workspace_relative_path) {
      assertSafeWorkspaceRelativePath(input.workspace_relative_path);
    }
    return input;
  });
}

function validateExpectedOutputs(
  outputs: OpenClawExpectedOutput[]
): OpenClawExpectedOutput[] {
  const seen = new Set<string>();
  return outputs.map((output) => {
    if (seen.has(output.output_id)) {
      throw new Error(`Duplicate OpenClaw expected output id: ${output.output_id}`);
    }
    seen.add(output.output_id);
    if (output.workspace_relative_path) {
      assertSafeWorkspaceRelativePath(output.workspace_relative_path);
    }
    return output;
  });
}

export function assertSafeWorkspaceRelativePath(value: string): string {
  const normalized = value.replace(/\\/g, "/").trim();
  if (
    !normalized ||
    normalized.startsWith("/") ||
    /^[A-Za-z]:\//.test(normalized) ||
    normalized.split("/").includes("..")
  ) {
    throw new Error(`Unsafe OpenClaw workspace-relative path: ${value}`);
  }
  return normalized;
}

function classifyOpenClawExecutionMode(input: {
  request: ExecuteAgentRequest;
  options: OpenClawProviderOptions;
  stagedInputs: OpenClawStagedInput[];
  expectedOutputs: OpenClawExpectedOutput[];
}): OpenClawExecutionMode {
  if (input.options.execution_mode) {
    return input.options.execution_mode;
  }
  if (input.expectedOutputs.some((output) => output.required)) {
    return "output_required";
  }

  const query = input.request.agent_query.toLowerCase();
  const hasOutputTerm = OUTPUT_REQUIRED_TERMS.some((term) =>
    query.includes(term)
  );
  const hasApprovedContent =
    input.request.context &&
    typeof input.request.context === "object" &&
    "approved_content" in input.request.context;

  if (hasOutputTerm && (hasApprovedContent || input.stagedInputs.length > 0)) {
    return "output_required";
  }
  if (hasOutputTerm && /\b(file|artifact|markdown|document|output)\b/.test(query)) {
    return "output_required";
  }

  return "read_only";
}

function defaultExpectedOutput(): OpenClawExpectedOutput {
  return {
    output_id: "openclaw_answer",
    purpose: "answer",
    display_name: "openclaw-result.md",
    media_type: "text/markdown",
    required: true,
    workspace_relative_path: "outputs/openclaw_answer-openclaw-result.md",
    persist_as_artifact: true,
    artifact_role: "final",
    min_size_bytes: 1
  };
}

function defaultOutputPath(output: OpenClawExpectedOutput): string {
  return assertSafeWorkspaceRelativePath(
    `outputs/${output.output_id}-${output.display_name}`
  );
}
