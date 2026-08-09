import type {
  AgentExpectedOutput
} from "../../api/schemas/execution-request.schema.js";

import type { ResolvedAgentArtifact } from "./agent-artifact-resolver.js";

export type AgentSkillProviderSelection = {
  activation_method:
    | "codex_explicit_reference"
    | "codex_prompt_guidance"
    | "openclaw_prompt_guidance";
  agent_skill_id: string;
  approved_fingerprint: string;
  backend: "codex_cli" | "openclaw_cli";
  display_name: string;
  observed_fingerprint: string;
  provider_skill_name: string;
  provider_skill_reference: string;
  runtime_target_id: string;
  source_id: string;
};

export type AgentOperationPlanItem = {
  operation_id: string;
  kind: "read" | "workspace_write" | "external_write";
  description: string;
  required: boolean;
  target_hint?: string;
  minimum_verification:
    | "process_observed"
    | "provider_reported"
    | "independently_verified";
  activation_method?:
    | "codex_explicit_reference"
    | "codex_prompt_guidance"
    | "openclaw_prompt_guidance";
  agent_skill_id?: string;
  agent_skill_backend?: "codex_cli" | "openclaw_cli";
  approved_fingerprint?: string;
  observed_fingerprint?: string;
  provider_skill_name?: string;
  provider_skill_reference?: string;
  runtime_target_id?: string;
  source_id?: string;
};

export type AgentProviderExecutionContext = {
  execution_id: string;
  agent_skill_selection?: AgentSkillProviderSelection;
  authorization: {
    state: "not_required" | "confirmed";
    permission_scope: string;
    policy_fingerprint: string;
    confirmed_at?: string;
  };
  access_policy?: {
    workspace_access: "none" | "read_only" | "scoped_write";
    provider_state_access: "none" | "read" | "scoped_write";
    provider_state_labels: string[];
    network_access: "deny" | "allowlisted";
  };
  operation_plan: AgentOperationPlanItem[];
  resolved_artifacts: ResolvedAgentArtifact[];
  expected_outputs: AgentExpectedOutput[];
};
