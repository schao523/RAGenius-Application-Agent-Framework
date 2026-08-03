import type {
  AgentExpectedOutput
} from "../../api/schemas/execution-request.schema.js";

import type { ResolvedAgentArtifact } from "./agent-artifact-resolver.js";

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
};

export type AgentProviderExecutionContext = {
  execution_id: string;
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
