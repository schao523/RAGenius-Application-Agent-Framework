export type PermissionMode =
  | "auto_allow"
  | "restricted"
  | "require_confirmation"
  | "blocked";

export interface PermissionDecision {
  mode: PermissionMode;
  scope: string;
  toolId: string;
  reason?: string;
  conditions?: Record<string, unknown>;
}

export interface PermissionPolicy {
  appId: string;
  toolId: string;
  scope: string;
  mode: PermissionMode;
  conditions?: Record<string, unknown>;
}
