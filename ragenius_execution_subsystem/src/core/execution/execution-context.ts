import type {
  ExecuteSkillRequest,
  ExecutionOptions
} from "../../api/schemas/execution-request.schema.js";
import type { NormalizedError } from "../../api/schemas/common-response.schema.js";
import type { PermissionPolicy } from "../permissions/permission.types.js";
import type { SkillDefinition } from "../skills/skill.types.js";
import type { ToolDefinition } from "../tools/tool.types.js";

export interface ExecutionContext {
  executionId: string | null;
  request: ExecuteSkillRequest;
  skill?: SkillDefinition;
  executionOptions: ExecutionOptions;
  toolDefinitions: ToolDefinition[];
  permissionPolicies?: PermissionPolicy[];
  stepOutputs: Record<string, Record<string, unknown>>;
  toolResults: Record<string, Record<string, unknown>>;
  errors: NormalizedError[];
}
