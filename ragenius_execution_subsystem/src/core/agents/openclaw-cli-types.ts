export type OpenClawExecutionMode = "read_only" | "output_required";

export type OpenClawSourceKind = "approved_content" | "artifact" | "inline_text";

export type OpenClawStagedInput = {
  input_id: string;
  source_kind: OpenClawSourceKind;
  source_ref: {
    approved_content_id?: string;
    approved_revision_id?: string;
    artifact_id?: string;
    artifact_version_id?: string;
  };
  display_name: string;
  media_type: string;
  encoding: "utf8" | "binary";
  content_sha256?: string;
  size_bytes?: number;
  workspace_relative_path?: string;
  metadata?: Record<string, unknown>;
};

export type OpenClawExpectedOutput = {
  output_id: string;
  purpose: "answer" | "artifact" | "diagnostic";
  display_name: string;
  media_type: string;
  required: boolean;
  workspace_relative_path?: string;
  persist_as_artifact: boolean;
  artifact_type?: "agent_output";
  artifact_role?: "final" | "intermediate" | "debug";
  min_size_bytes?: number;
  expected_sha256?: string;
};

export type OpenClawProviderOptions = {
  execution_mode?: OpenClawExecutionMode;
  session_key?: string;
  timeout_ms?: number;
  max_stdout_bytes?: number;
  max_stderr_bytes?: number;
  staged_inputs?: OpenClawStagedInput[];
  expected_outputs?: OpenClawExpectedOutput[];
};

export type NormalizedOpenClawProviderOptions = OpenClawProviderOptions & {
  execution_mode: OpenClawExecutionMode;
  staged_inputs: OpenClawStagedInput[];
  expected_outputs: OpenClawExpectedOutput[];
};

export type OpenClawVerificationResult = {
  output_id: string;
  workspace_relative_path: string;
  workspace_absolute_path: string;
  required: boolean;
  exists: boolean;
  verified: boolean;
  verification_status?: "verified" | "failed" | "not_run";
  size_bytes?: number;
  sha256?: string;
  media_type?: string;
  persisted_artifact_id?: string;
  persistence_status?: "not_requested" | "persisted" | "failed";
  persistence_failure_message?: string;
  persistence_failure_code?: "persist_failed";
  failure_code?:
    | "missing_output"
    | "empty_output"
    | "size_below_minimum"
    | "hash_mismatch"
    | "read_failed";
  failure_message?: string;
};

export type OpenClawProviderMetadata = {
  backend: "openclaw_cli";
  provider_name: "OpenClaw";
  invocation_mode: "wsl_cli";
  wsl_distro: string;
  openclaw_command: string;
  openclaw_agent_id: string;
  openclaw_session_key: string;
  execution_mode: OpenClawExecutionMode;
  provider_state_access: "none" | "read" | "scoped_write";
  provider_state_labels: string[];
  expected_output_count: number;
  required_output_count: number;
  verified_output_count: number;
  run_workspace_root: string;
  json_parse_status: "parsed" | "failed" | "not_requested";
  raw_exit_code: number | null;
  timed_out: boolean;
  stdout_truncated: boolean;
  stderr_truncated: boolean;
};

export type OpenClawProviderResult = {
  status: "completed" | "partial" | "failed";
  summary: string;
  output_text: string;
  artifacts: Array<{
    artifact_id?: string;
    output_id: string;
    display_name: string;
    media_type: string;
    role: "final" | "intermediate" | "debug";
    verified: boolean;
  }>;
  reported_outputs: Array<{
    output_id: string;
    display_name: string;
    media_type: string;
    workspace_relative_path: string;
    verified: boolean;
    size_bytes?: number;
    sha256?: string;
  }>;
  provider_metadata: OpenClawProviderMetadata;
  verification_results: OpenClawVerificationResult[];
  operation_verification?: import("./codex-cli-types.js").OperationVerification[];
  diagnostics: {
    failure_code?: string;
    failure_message?: string;
    stdout_tail?: string;
    stderr_tail?: string;
    stdout_truncated: boolean;
    stderr_truncated: boolean;
    redactions_applied: boolean;
  };
  raw: {
    json?: unknown;
    exit_code: number | null;
  };
  agent_skill_activation: import("../agent-skills/agent-skill-activation-evidence.js").AgentSkillActivation;
};
