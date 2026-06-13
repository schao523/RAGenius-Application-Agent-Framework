import type { ZodType } from "zod";

import type { PermissionMode } from "../permissions/permission.types.js";
import type { WorkflowDefinition } from "../workflow/workflow.types.js";
import type { ResultType } from "../../api/schemas/common-response.schema.js";

export interface SkillDefinition {
  id: string;
  name: string;
  version: string;
  description?: string;
  inventoryVisibility?: "user_tool" | "user_skill" | "internal_wrapper";
  workflowKind?: "single_tool_wrapper" | "multi_step_workflow" | "builder_bound";
  inputSchema: ZodType;
  outputSchema: ZodType;
  requiredTools: string[];
  requiredPermissions: string[];
  workflowDefinition: WorkflowDefinition;
  enabled: boolean;
  confirmationMode?: PermissionMode;
  resultType?: ResultType;
}
