import { z } from "zod";

export const errorClassSchema = z.enum([
  "validation",
  "permission",
  "tool",
  "workflow",
  "timeout",
  "external_api"
]);

export const executionStatusSchema = z.enum([
  "completed",
  "failed",
  "partial",
  "blocked",
  "pending_confirmation"
]);

export const resultTypeSchema = z.enum(["text", "json", "file", "video"]);

export const normalizedErrorSchema = z.object({
  code: z.string().min(1),
  message: z.string().min(1),
  details: z.unknown().optional(),
  recoverable: z.boolean(),
  suggested_action: z.string().min(1)
});

export const toolExecutionProvenanceSchema = z.object({
  execution_path: z.enum([
    "local",
    "api",
    "rag_adapter",
    "adapter",
    "mcp",
    "rest_fallback"
  ]),
  tool_id: z.string().min(1),
  provider_type: z.enum(["local", "api", "mcp", "rag_adapter", "adapter"]),
  provider_id: z.string().min(1).optional(),
  remote_tool_name: z.string().min(1).optional(),
  fallback_used: z.boolean().optional(),
  fallback_reason: z.string().min(1).optional(),
  auth_context: z.record(z.string(), z.unknown()).optional()
});

export const executionMetadataSchema = z.object({
  used_fallback: z.boolean(),
  fallback_count: z.number().int().nonnegative(),
  execution_paths: z.array(
    z.enum(["local", "api", "rag_adapter", "adapter", "mcp", "rest_fallback"])
  ),
  provider_ids: z.array(z.string().min(1)),
  tool_ids: z.array(z.string().min(1))
});

export const normalizedExecutionResultSchema = z.object({
  execution_id: z.string().min(1).nullable().optional(),
  status: executionStatusSchema,
  result_type: resultTypeSchema,
  result: z.record(z.string(), z.unknown()),
  execution_provenance: z
    .array(toolExecutionProvenanceSchema)
    .optional(),
  execution_metadata: executionMetadataSchema.optional(),
  files: z.array(z.record(z.string(), z.unknown())),
  errors: z.array(normalizedErrorSchema),
  logs_summary: z.string()
});

export type ErrorClass = z.infer<typeof errorClassSchema>;
export type ExecutionStatus = z.infer<typeof executionStatusSchema>;
export type ResultType = z.infer<typeof resultTypeSchema>;
export type NormalizedError = z.infer<typeof normalizedErrorSchema>;
export type ToolExecutionProvenance = z.infer<
  typeof toolExecutionProvenanceSchema
>;
export type ExecutionMetadata = z.infer<typeof executionMetadataSchema>;
export type NormalizedExecutionResult = z.infer<
  typeof normalizedExecutionResultSchema
>;
