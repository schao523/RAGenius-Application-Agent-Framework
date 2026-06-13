export interface CodexCliBridgeRequest {
  app_id: string;
  session_id: string;
  agent_query: string;
  agent_skill_hint?: string;
  approved_content_id?: string;
  approved_revision_id?: string;
  context?: Record<string, unknown>;
  policy?: {
    risk_class: string;
    workspace_access: "none" | "read_only" | "scoped_write";
    network_access: "deny" | "allowlisted";
    reason: string;
    matched_terms?: string[];
  };
}

export interface CodexCliArtifactSummary {
  artifact_id?: string;
  artifact_type?: string;
  name?: string;
  path?: string;
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
  output?: Record<string, unknown>;
  raw_output?: string;
}

export interface CodexCliBridgeSuccessResponse {
  ok: true;
  result: CodexCliBridgeSuccessResult;
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
