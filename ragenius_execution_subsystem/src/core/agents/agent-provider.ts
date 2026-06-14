import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";

import type { AgentPolicyDecision } from "./agent-policy.js";

export type AgentBackend = "codex_cli" | "openclaw_cli";

export type AgentProviderResult = {
  status?: "completed" | "failed";
  summary?: string;
  output_text?: string;
  final_message?: string;
  user_summary?: unknown;
  activated_skills?: string[];
  tool_summary?: string[];
  artifacts?: unknown[];
  output?: Record<string, unknown>;
  raw_output?: string;
  provider_metadata?: Record<string, unknown>;
  verification_results?: unknown[];
  diagnostics?: Record<string, unknown>;
  raw?: Record<string, unknown>;
};

export interface AgentProvider {
  readonly backend: AgentBackend;
  execute(
    request: ExecuteAgentRequest,
    policy: AgentPolicyDecision,
    context?: { executionId?: string }
  ): Promise<AgentProviderResult>;
}
