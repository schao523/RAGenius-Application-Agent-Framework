import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";
import type { PermissionMode } from "../permissions/permission.types.js";

export type AgentRiskClass =
  | "agent_read_only"
  | "agent_external_write"
  | "agent_workspace_write"
  | "agent_destructive";

export type AgentWorkspaceAccess = "none" | "read_only" | "scoped_write";
export type AgentNetworkAccess = "deny" | "allowlisted";

export interface AgentPolicyDecision {
  riskClass: AgentRiskClass;
  mode: PermissionMode;
  permissionScope: string;
  workspaceAccess: AgentWorkspaceAccess;
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

export function classifyAgentRequest(
  request: ExecuteAgentRequest
): AgentPolicyDecision {
  const query = normalizedQuery(request);
  const destructiveTerms = matchingTerms(query, DESTRUCTIVE_PATTERNS);
  if (destructiveTerms.length > 0) {
    return {
      riskClass: "agent_destructive",
      mode: "blocked",
      permissionScope: "agent.destructive",
      workspaceAccess: "scoped_write",
      networkAccess: "deny",
      reason: "Destructive agent requests are blocked.",
      matchedTerms: destructiveTerms
    };
  }

  const workspaceTerms = matchingTerms(query, WORKSPACE_PATTERNS);
  const workspaceWriteTerms = matchingTerms(query, WORKSPACE_WRITE_PATTERNS);
  if (workspaceTerms.length > 0 && workspaceWriteTerms.length > 0) {
    return {
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
    riskClass: "agent_read_only",
    mode: "auto_allow",
    permissionScope: "agent.read",
    workspaceAccess: "none",
    networkAccess: "allowlisted",
    reason: "Read-only agent requests are auto-allowed.",
    matchedTerms: []
  };
}
