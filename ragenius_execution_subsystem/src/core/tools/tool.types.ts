import type { ZodType } from "zod";

export type ToolProviderType =
  | "local"
  | "api"
  | "mcp"
  | "rag_adapter"
  | "adapter";

export interface ToolExecutionProvenance {
  execution_path:
    | "local"
    | "api"
    | "rag_adapter"
    | "adapter"
    | "mcp"
    | "rest_fallback";
  tool_id: string;
  provider_type: ToolProviderType;
  provider_id?: string;
  remote_tool_name?: string;
  fallback_used?: boolean;
  fallback_reason?: string;
  auth_context?: Record<string, unknown>;
}

export const toolExecutionProvenanceKey = "__execution_provenance";

export interface ToolDefinition {
  id: string;
  name: string;
  providerType: ToolProviderType;
  inputSchema: ZodType;
  outputSchema: ZodType;
  permissionScopes: string[];
  timeoutMs?: number;
  sideEffecting: boolean;
  enabled?: boolean;
  metadata?: Record<string, unknown>;
}
