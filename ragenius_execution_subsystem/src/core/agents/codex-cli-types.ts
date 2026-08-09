import type { AgentDiagnostics } from "./agent-diagnostics.js";
import type { AgentSkillActivation } from "../agent-skills/agent-skill-activation-evidence.js";

export interface CodexCliBridgeRequest {
  app_id: string;
  session_id: string;
  agent_query: string;
  agent_skill_hint?: string;
  approved_content_id?: string;
  approved_revision_id?: string;
  context?: Record<string, unknown>;
  prompt?: string;
  workspace_absolute_path?: string;
  sandbox_mode?: "read-only" | "workspace-write";
  max_output_bytes?: number;
  policy?: {
    risk_class: string;
    workspace_access: "none" | "read_only" | "scoped_write";
    provider_state_access: "none" | "read" | "scoped_write";
    provider_state_labels: string[];
    network_access: "deny" | "allowlisted";
    reason: string;
    matched_terms?: string[];
  };
}

export interface CodexCliArtifactSummary {
  output_id?: string;
  artifact_id?: string;
  artifact_type?: string;
  display_name?: string;
  name?: string;
  path?: string;
  media_type?: string;
  size_bytes?: number;
  sha256?: string;
}

export interface CodexOutputVerification {
  output_id: string;
  display_name: string;
  media_type: string;
  workspace_relative_path: string;
  workspace_absolute_path: string;
  required: boolean;
  exists: boolean;
  verified: boolean;
  size_bytes?: number;
  sha256?: string;
  failure_code?: "missing_output" | "empty_output" | "size_below_minimum" | "hash_mismatch" | "read_failed";
  failure_message?: string;
}

export interface CodexStagedArtifact {
  artifact_id: string;
  role: "source" | "reference" | "attachment" | "context";
  reuse_mode:
    | "file_backed"
    | "inline_text"
    | "binary_payload"
    | "metadata_only";
  display_name: string;
  media_type?: string;
  size_bytes?: number;
  sha256?: string;
  workspace_relative_path?: string;
}

export interface CodexCliUserSummary {
  status?: string;
  title?: string;
  subtitle?: string;
  preview?: string;
}

export interface CodexCliBridgeSuccessResult {
  final_message: string;
  user_summary?: CodexCliUserSummary;
  activated_skills?: string[];
  tool_summary?: string[];
  artifacts?: CodexCliArtifactSummary[];
  reported_outputs?: CodexCliArtifactSummary[];
  output?: Record<string, unknown>;
  raw_output?: string;
}

export interface CodexCliCommandEvent {
  item_id: string;
  command: string;
  exit_code?: number;
  stdout_summary?: string;
  stderr_summary?: string;
}

export interface CodexCliProtocolResult {
  thread_id?: string;
  turn_status: "completed" | "failed" | "unknown";
  final_message: string;
  command_events: CodexCliCommandEvent[];
  errors: Array<{ code: string; message: string }>;
  usage?: Record<string, unknown>;
  raw_exit_code: number;
  malformed_line_count: number;
  stdout_truncated: boolean;
  stderr_truncated: boolean;
}

export interface CodexAgentTaskOperation {
  operation_id: string;
  operation: string;
  target?: string;
  status: "completed" | "accepted" | "processing" | "failed" | "not_run";
  external_id?: string;
  evidence?: string;
}

export interface CodexAgentTaskResult {
  task_status: "completed" | "partial" | "failed" | "pending_confirmation";
  summary: string;
  activated_skills: string[];
  operations: CodexAgentTaskOperation[];
  artifacts: CodexCliArtifactSummary[];
  output_verification?: CodexOutputVerification[];
  errors: Array<{ code: string; message: string }>;
}

export interface OperationVerification {
  operation_id: string;
  operation: string;
  level: "none" | "process_observed" | "provider_reported" | "independently_verified";
  status: "completed" | "accepted" | "processing" | "failed" | "not_run";
  external_id?: string;
  evidence?: string;
}

export interface CodexNormalizedResult {
  backend: "codex_cli";
  status: "completed" | "partial" | "failed";
  summary: string;
  activated_skills: string[];
  staged_inputs: CodexStagedArtifact[];
  operation_verification: OperationVerification[];
  artifacts: CodexCliArtifactSummary[];
  reported_outputs?: CodexCliArtifactSummary[];
  provider_metadata: {
    thread_id?: string;
    turn_status: "completed" | "failed" | "unknown";
    raw_exit_code: number;
    confirmation_state: "not_required" | "confirmed";
    permission_scope: string;
    policy_fingerprint: string;
    provider_state_access?: "none" | "read" | "scoped_write";
    provider_state_labels?: string[];
    command_count: number;
    successful_command_count: number;
    final_json_status: "parsed" | "invalid" | "missing";
  };
  diagnostics?: AgentDiagnostics & {
    stdout_tail?: string;
    stderr_tail?: string;
  };
  agent_skill_activation?: AgentSkillActivation;
}

export interface CodexCliBridgeSuccessResponse {
  ok: true;
  result: CodexCliBridgeSuccessResult | CodexCliProtocolResult;
}

export interface CodexCliBridgeErrorResponse {
  ok: false;
  error: {
    code: string;
    message: string;
    details?: unknown;
    recoverable?: boolean;
    suggested_action?: string;
  };
}

export type CodexCliBridgeResponse =
  | CodexCliBridgeSuccessResponse
  | CodexCliBridgeErrorResponse;
