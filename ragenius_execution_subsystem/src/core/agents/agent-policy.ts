import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";
import type { PermissionMode } from "../permissions/permission.types.js";

export type AgentRiskClass =
  | "agent_read_only"
  | "agent_external_write"
  | "agent_workspace_write"
  | "agent_destructive";

export type AgentWorkspaceAccess = "none" | "read_only" | "scoped_write";
export type AgentNetworkAccess = "deny" | "allowlisted";
export type AgentProviderStateAccess = "none" | "read" | "scoped_write";

export interface AgentPolicyDecision {
  riskClass: AgentRiskClass;
  mode: PermissionMode;
  permissionScope: string;
  workspaceAccess: AgentWorkspaceAccess;
  providerStateAccess: AgentProviderStateAccess;
  providerStateLabels: string[];
  networkAccess: AgentNetworkAccess;
  reason: string;
  matchedTerms: string[];
}

const DESTRUCTIVE_PATTERNS = [
  /\bdelete\b/,
  /\bremove\b/,
  /\bdestroy\b/,
  /\berase\b/,
  /\bwipe\b/,
  /\bpurge\b/,
  /\bdrop\b/,
  /\btruncate\b/
];

const WORKSPACE_PATTERNS = [
  /\bfile\b/,
  /\bfiles\b/,
  /\bworkspace\b/,
  /\brepo\b/,
  /\brepository\b/,
  /\bpatch\b/,
  /\bcode\b/,
  /\bbranch\b/,
  /\bcommit\b/,
  /\bpr\b/,
  /\bpull request\b/
];

const WORKSPACE_WRITE_PATTERNS = [
  /\bwrite\b/,
  /\bedit\b/,
  /\bmodify\b/,
  /\bupdate\b/,
  /\brefactor\b/,
  /\bpatch\b/,
  /\bcreate\b/,
  /\bsave\b/,
  /\brename\b/
];

const EXTERNAL_WRITE_PATTERNS = [
  /\bgenerate\b/,
  /\bcreate\b/,
  /\bdraft\b/,
  /\bsend\b/,
  /\bpublish\b/,
  /\bpost\b/,
  /\bupload\b/,
  /\badd\b/,
  /\bimport\b/,
  /\bexport\b/,
  /\bbuild\b/
];

const EXPLICIT_EXTERNAL_WRITE_PATTERNS = [
  /\bdraft\b/,
  /\bsend\b/,
  /\bpublish\b/,
  /\bpost\b/,
  /\bupload\b/,
  /\badd\b/,
  /\bimport\b/
];

const EXTERNAL_SKILL_HINTS = new Set(["notebooklm"]);

function matchingTerms(query: string, patterns: RegExp[]): string[] {
  return patterns
    .map((pattern) => {
      const match = query.match(pattern);
      return match?.[0]?.trim().toLowerCase() ?? "";
    })
    .filter(Boolean);
}

function normalizedQuery(request: ExecuteAgentRequest): string {
  return [
    request.agent_query,
    typeof request.agent_skill_hint === "string" ? request.agent_skill_hint : ""
  ]
    .filter(Boolean)
    .join(" ")
    .trim()
    .toLowerCase();
}

function queryForDestructiveClassification(query: string): string {
  return query.replace(
    /\b(?:do not|don't|never)\s+(?:\w+\s+){0,3}(?:delete|remove|destroy|erase|wipe|purge|drop|truncate)\b/g,
    ""
  );
}

function providerStateFor(
  request: ExecuteAgentRequest,
  notebookLmProfile: string
): Pick<AgentPolicyDecision, "providerStateAccess" | "providerStateLabels"> {
  if (request.agent_skill_hint?.trim().toLowerCase() === "notebooklm") {
    return {
      providerStateAccess: "scoped_write",
      providerStateLabels: [`notebooklm_profile:${notebookLmProfile}`]
    };
  }
  if (request.agent_backend === "openclaw_cli") {
    return {
      providerStateAccess: "scoped_write",
      providerStateLabels: ["openclaw_agent_state"]
    };
  }
  return { providerStateAccess: "none", providerStateLabels: [] };
}

export function classifyAgentRequest(
  request: ExecuteAgentRequest,
  options: { notebookLmProfile?: string } = {}
): AgentPolicyDecision {
  const query = normalizedQuery(request);
  const providerState = providerStateFor(
    request,
    options.notebookLmProfile?.trim() || "default"
  );
  const destructiveTerms = matchingTerms(
    queryForDestructiveClassification(query),
    DESTRUCTIVE_PATTERNS
  );
  if (destructiveTerms.length > 0) {
    return {
      ...providerState,
      riskClass: "agent_destructive",
      mode: "blocked",
      permissionScope: "agent.destructive",
      workspaceAccess: "scoped_write",
      networkAccess: "deny",
      reason: "Destructive agent requests are blocked.",
      matchedTerms: destructiveTerms
    };
  }

  const explicitExternalTerms = matchingTerms(
    query,
    EXPLICIT_EXTERNAL_WRITE_PATTERNS
  );
  const skillHint = request.agent_skill_hint?.trim().toLowerCase();
  const externalSkillWriteTerms = matchingTerms(query, EXTERNAL_WRITE_PATTERNS);
  if (
    explicitExternalTerms.length > 0 ||
    (skillHint &&
      EXTERNAL_SKILL_HINTS.has(skillHint) &&
      externalSkillWriteTerms.length > 0)
  ) {
    return {
      ...providerState,
      riskClass: "agent_external_write",
      mode: "require_confirmation",
      permissionScope: "agent.external_write",
      workspaceAccess: "none",
      networkAccess: "allowlisted",
      reason: "External write agent requests require confirmation.",
      matchedTerms: explicitExternalTerms.length > 0
        ? explicitExternalTerms
        : externalSkillWriteTerms
    };
  }

  if (
    request.expected_outputs?.some(
      (output) => output.persist_as_artifact === true
    )
  ) {
    return {
      ...providerState,
      riskClass: "agent_workspace_write",
      mode: "require_confirmation",
      permissionScope: "agent.workspace_write",
      workspaceAccess: "scoped_write",
      networkAccess: "deny",
      reason: "Persisted agent outputs require scoped workspace access.",
      matchedTerms: matchingTerms(query, WORKSPACE_WRITE_PATTERNS)
    };
  }

  const workspaceTerms = matchingTerms(query, WORKSPACE_PATTERNS);
  const workspaceWriteTerms = matchingTerms(query, WORKSPACE_WRITE_PATTERNS);
  if (workspaceTerms.length > 0 && workspaceWriteTerms.length > 0) {
    return {
      ...providerState,
      riskClass: "agent_workspace_write",
      mode: "require_confirmation",
      permissionScope: "agent.workspace_write",
      workspaceAccess: "scoped_write",
      networkAccess: "deny",
      reason: "Workspace-writing agent requests require confirmation.",
      matchedTerms: [...new Set([...workspaceTerms, ...workspaceWriteTerms])]
    };
  }

  const externalWriteTerms = matchingTerms(query, EXTERNAL_WRITE_PATTERNS);
  if (externalWriteTerms.length > 0) {
    return {
      ...providerState,
      riskClass: "agent_external_write",
      mode: "require_confirmation",
      permissionScope: "agent.external_write",
      workspaceAccess: "none",
      networkAccess: "allowlisted",
      reason: "External write agent requests require confirmation.",
      matchedTerms: externalWriteTerms
    };
  }

  return {
    ...providerState,
    riskClass: "agent_read_only",
    mode: "auto_allow",
    permissionScope: "agent.read",
    workspaceAccess: "none",
    networkAccess: "allowlisted",
    reason: "Read-only agent requests are auto-allowed.",
    matchedTerms: []
  };
}
