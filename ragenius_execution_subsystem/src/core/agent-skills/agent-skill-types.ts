export type AgentSkillBackend = "codex_cli" | "openclaw_cli";

export type AgentSkillSourceKind =
  | "codex_directory"
  | "openclaw_agent_inventory";

export type AgentSkillDiscoveryStatus =
  | "available"
  | "disabled_at_provider"
  | "ineligible"
  | "invalid"
  | "missing"
  | "source_unavailable";

export interface AgentSkillSourceOption {
  backend: AgentSkillBackend;
  display_name: string;
  protected_locator_ref: string;
  runtime_target_id: string;
  source_kind: AgentSkillSourceKind;
}

export interface AgentSkillDiscoveryInput {
  protected_locator_ref: string;
  runtime_target_id: string;
  source_id: string;
}

export interface AgentSkillInspectionInput extends AgentSkillDiscoveryInput {
  provider_skill_name: string;
}

export interface AgentSkillDiscoveryErrorRecord {
  code: string;
  message: string;
  provider_skill_name?: string;
}

export interface AgentSkillCatalogCandidate {
  agent_skill_id: string;
  backend: AgentSkillBackend;
  content_fingerprint: string;
  description: string;
  direct_tool_dispatch: boolean;
  discovered_at: string;
  discovery_status: AgentSkillDiscoveryStatus;
  display_name: string;
  last_seen_at: string;
  missing_requirements: {
    bins: string[];
    config: string[];
    env: string[];
    os: string[];
  };
  model_visible: boolean;
  provider_metadata: Record<string, unknown>;
  provider_skill_name: string;
  runtime_target_id: string;
  source_id: string;
  source_kind: AgentSkillSourceKind;
  source_label: string;
  user_invocable: boolean;
}

export interface AgentSkillDiscoveryResult {
  backend: AgentSkillBackend;
  complete: boolean;
  discovered_at: string;
  errors: AgentSkillDiscoveryErrorRecord[];
  items: AgentSkillCatalogCandidate[];
  runtime_target_id: string;
  source_id: string;
}

export interface AgentSkillDiscoveryAdapter {
  readonly backend: AgentSkillBackend;
  discover(input: AgentSkillDiscoveryInput): Promise<AgentSkillDiscoveryResult>;
  inspect(input: AgentSkillInspectionInput): Promise<AgentSkillCatalogCandidate>;
  sourceOptions(): AgentSkillSourceOption[];
}

export interface ResolvedAgentSkillSelection {
  activation_method:
    | "codex_explicit_reference"
    | "codex_prompt_guidance"
    | "openclaw_prompt_guidance";
  agent_skill_id: string;
  approved_fingerprint: string;
  backend: AgentSkillBackend;
  display_name: string;
  observed_fingerprint: string;
  protected_locator_ref: string;
  provider_skill_name: string;
  resolved_at: string;
  runtime_target_id: string;
  source_id: string;
}

export type AgentSkillApprovalState = "approved" | "revoked" | "superseded";

export interface ProjectedAgentSkillGovernance {
  agent_skill_id: string;
  app_id: string;
  approval_state: AgentSkillApprovalState;
  approved_fingerprint: string;
  backend: AgentSkillBackend;
  binding_enabled: boolean;
  current_fingerprint: string;
  description: string;
  direct_tool_dispatch: boolean;
  display_name: string;
  model_visible: boolean;
  protected_locator_ref: string;
  provider_skill_name: string;
  runtime_target_id: string;
  source_enabled: boolean;
  source_id: string;
  user_invocable: boolean;
}

export interface AgentSkillGovernanceProjection {
  builder_instance_id: string;
  digest: string;
  generated_at: string;
  items: ProjectedAgentSkillGovernance[];
  revision: number;
}

export interface ProjectionRevisionSummary {
  builder_instance_id: string;
  digest: string;
  generated_at: string;
  item_count: number;
  received_at: string;
  revision: number;
}

export interface ProjectionReceipt extends ProjectionRevisionSummary {
  idempotent: boolean;
}
