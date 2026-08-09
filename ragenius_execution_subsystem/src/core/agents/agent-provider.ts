import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";

import type { AgentPolicyDecision } from "./agent-policy.js";
import type { AgentProviderExecutionContext } from "./agent-provider-context.js";
import type { AgentDiagnostics } from "./agent-diagnostics.js";
import type { AgentSkillActivation } from "../agent-skills/agent-skill-activation-evidence.js";

export type AgentBackend = "codex_cli" | "openclaw_cli";

export type AgentProviderResult = {
  status?: "completed" | "partial" | "failed";
  summary?: string;
  output_text?: string;
  final_message?: string;
  user_summary?: unknown;
  activated_skills?: string[];
  tool_summary?: string[];
  artifacts?: unknown[];
  reported_outputs?: unknown[];
  output?: Record<string, unknown>;
  raw_output?: string;
  provider_metadata?: Record<string, unknown>;
  verification_results?: unknown[];
  staged_inputs?: unknown[];
  operation_verification?: unknown[];
  diagnostics?: AgentDiagnostics & Record<string, unknown>;
  raw?: Record<string, unknown>;
  agent_skill_activation?: AgentSkillActivation;
};

export interface AgentProvider {
  readonly backend: AgentBackend;
  execute(
    request: ExecuteAgentRequest,
    policy: AgentPolicyDecision,
    context: AgentProviderExecutionContext
  ): Promise<AgentProviderResult>;
}
