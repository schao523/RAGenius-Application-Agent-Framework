import { z } from "zod";

import { AppError } from "../errors/app-error.js";

import type { ToolDefinition } from "./tool.types.js";

const notebookLmNotebookReferenceFields = {
  notebookId: z.string().min(1).optional(),
  notebookTitle: z.string().min(1).optional()
};

function withNotebookLmReference<T extends z.ZodRawShape>(shape: T) {
  return z
    .object({
      ...notebookLmNotebookReferenceFields,
      ...shape
    })
    .refine(
      (value) =>
        (typeof value.notebookId === "string" && value.notebookId.length > 0) ||
        (typeof value.notebookTitle === "string" &&
          value.notebookTitle.length > 0),
      {
        message: "Provide notebookId or notebookTitle."
      }
    );
}

const storedArtifactReferenceSchema = z.object({
  artifact_id: z.string(),
  artifact_type: z.string(),
  display_name: z.string(),
  summary: z.string().optional(),
  app_id: z.string(),
  created_at: z.string(),
  source_tool_id: z.string().optional(),
  source_skill_id: z.string().optional(),
  provider_origin: z.string(),
  mime_type: z.string().optional(),
  size_bytes: z.number().int().nonnegative().optional(),
  path: z.string(),
  file_path: z.string().optional(),
  status: z.string()
});

export const defaultTools: ToolDefinition[] = [
  {
    id: "read_file",
    name: "Read File",
    providerType: "local",
    inputSchema: z.object({
      path: z.string().min(1),
      encoding: z.string().optional(),
      max_bytes: z.number().int().positive().max(1_000_000).optional()
    }),
    outputSchema: z.object({
      path: z.string(),
      content: z.string(),
      truncated: z.boolean(),
      size_bytes: z.number().int().nonnegative()
    }),
    permissionScopes: ["filesystem.read"],
    timeoutMs: 2_000,
    sideEffecting: false,
    enabled: true,
    metadata: {
      safePhase: 1,
      policyClass: "safe_read"
    }
  },
  {
    id: "list_files",
    name: "List Files",
    providerType: "local",
    inputSchema: z.object({
      path: z.string().min(1),
      recursive: z.boolean().optional(),
      depth: z.number().int().min(0).max(10).optional(),
      glob: z.string().optional(),
      include_dirs: z.boolean().optional()
    }),
    outputSchema: z.object({
      path: z.string(),
      entries: z.array(
        z.object({
          path: z.string(),
          name: z.string(),
          type: z.enum(["file", "directory"]),
          size_bytes: z.number().int().nonnegative().optional(),
          modified_at: z.string().optional()
        })
      )
    }),
    permissionScopes: ["filesystem.read"],
    timeoutMs: 5_000,
    sideEffecting: false,
    enabled: true,
    metadata: {
      safePhase: 1,
      policyClass: "safe_read"
    }
  },
  {
    id: "retrieve_documents",
    name: "Retrieve Documents",
    providerType: "rag_adapter",
    inputSchema: z.object({
      query: z.string().min(1),
      top_k: z.number().int().positive().max(10).optional(),
      filters: z.record(z.string(), z.unknown()).optional()
    }),
    outputSchema: z.object({
      items: z.array(
        z.object({
          title: z.string(),
          content: z.string(),
          metadata: z.record(z.string(), z.unknown())
        })
      )
    }),
    permissionScopes: ["rag.read"],
    timeoutMs: 2_000,
    sideEffecting: false,
    enabled: true,
    metadata: {
      safePhase: 1,
      policyClass: "safe_read"
    }
  },
  {
    id: "search_metadata",
    name: "Search Metadata",
    providerType: "rag_adapter",
    inputSchema: z.object({
      query: z.string().min(1),
      limit: z.number().int().positive().max(25).optional(),
      filters: z.record(z.string(), z.unknown()).optional()
    }),
    outputSchema: z.object({
      items: z.array(
        z.object({
          document_id: z.string(),
          title: z.string(),
          tags: z.array(z.string())
        })
      )
    }),
    permissionScopes: ["metadata.read"],
    timeoutMs: 2_000,
    sideEffecting: false,
    enabled: true,
    metadata: {
      safePhase: 1,
      policyClass: "safe_read"
    }
  },
  {
    id: "save_artifact",
    name: "Save Artifact",
    providerType: "local",
    inputSchema: z.object({
      artifact_type: z.string().min(1),
      name: z.string().min(1),
      display_name: z.string().min(1).optional(),
      content: z.unknown(),
      format: z.string().optional(),
      reviewed: z.boolean().optional(),
      reviewed_at: z.string().min(1).optional(),
      reviewed_by: z.string().min(1).optional(),
      review_source: z.string().min(1).optional(),
      source_message_ids: z.array(z.string().min(1)).optional(),
      content_hash: z.string().min(1).optional()
    }),
    outputSchema: z.object({
      artifact_id: z.string(),
      path: z.string(),
      artifact_type: z.string(),
      display_name: z.string(),
      storage_file_name: z.string().optional(),
      summary: z.string().optional(),
      app_id: z.string(),
      created_at: z.string(),
      created_by_execution_id: z.string().optional(),
      created_by_turn_id: z.string().optional(),
      source_tool_id: z.string().optional(),
      source_skill_id: z.string().optional(),
      reviewed: z.boolean().optional(),
      reviewed_at: z.string().optional(),
      reviewed_by: z.string().optional(),
      review_source: z.string().optional(),
      source_message_ids: z.array(z.string()).optional(),
      content_hash: z.string().optional(),
      provider_origin: z.literal("local"),
      mime_type: z.string().optional(),
      size_bytes: z.number().int().nonnegative().optional(),
      file_path: z.string().optional(),
      status: z.literal("ready")
    }),
    permissionScopes: ["artifact.write"],
    timeoutMs: 2_000,
    sideEffecting: false,
    enabled: true,
    metadata: {
      safePhase: 1,
      policyClass: "artifact_safe"
    }
  },
  {
    id: "write_file",
    name: "Write File",
    providerType: "local",
    inputSchema: z.object({
      path: z.string().min(1),
      content: z.string(),
      encoding: z.string().optional(),
      if_exists: z.literal("overwrite").optional()
    }),
    outputSchema: z.object({
      path: z.string(),
      bytes_written: z.number().int().nonnegative(),
      updated: z.boolean()
    }),
    permissionScopes: ["filesystem.write"],
    timeoutMs: 3_000,
    sideEffecting: true,
    enabled: true,
    metadata: {
      safePhase: 2,
      policyClass: "mutation"
    }
  },
  {
    id: "patch_file",
    name: "Patch File",
    providerType: "local",
    inputSchema: z.object({
      path: z.string().min(1),
      patch: z.string().min(1),
      format: z.literal("unified_diff").optional()
    }),
    outputSchema: z.object({
      path: z.string(),
      updated: z.boolean(),
      summary: z.string()
    }),
    permissionScopes: ["filesystem.patch"],
    timeoutMs: 3_000,
    sideEffecting: true,
    enabled: true,
    metadata: {
      safePhase: 2,
      policyClass: "mutation"
    }
  },
  {
    id: "content_transform_adapter",
    name: "Content Transform Adapter",
    providerType: "adapter",
    inputSchema: z.object({
      content: z.string().min(1)
    }),
    outputSchema: z.object({
      output: z.string()
    }),
    permissionScopes: ["adapter.execute"],
    timeoutMs: 2_000,
    sideEffecting: false,
    enabled: true,
    metadata: {
      safePhase: 3,
      policyClass: "review_required"
    }
  },
  {
    id: "adapter.notebooklm.list_notebooks",
    name: "NotebookLM List Notebooks",
    providerType: "adapter",
    inputSchema: z.object({}),
    outputSchema: z.object({
      notebooks: z.array(
        z.object({
          id: z.string(),
          title: z.string(),
          sources_count: z.number().int().nonnegative()
        })
      )
    }),
    permissionScopes: ["external_api.read"],
    timeoutMs: 10_000,
    sideEffecting: false,
    enabled: true,
    metadata: {
      safePhase: 3,
      policyClass: "review_required",
      providerId: "notebooklm"
    }
  },
  {
    id: "adapter.notebooklm.list_sources",
    name: "NotebookLM List Sources",
    providerType: "adapter",
    inputSchema: withNotebookLmReference({}),
    outputSchema: z.object({
      sources: z.array(
        z.object({
          id: z.string(),
          title: z.string(),
          kind: z.string(),
          status: z.string().nullable().optional()
        })
      )
    }),
    permissionScopes: ["external_api.read"],
    timeoutMs: 10_000,
    sideEffecting: false,
    enabled: true,
    metadata: {
      safePhase: 3,
      policyClass: "review_required",
      providerId: "notebooklm"
    }
  },
  {
    id: "adapter.notebooklm.ask",
    name: "NotebookLM Ask",
    providerType: "adapter",
    inputSchema: withNotebookLmReference({
      question: z.string().min(1),
      sourceIds: z.array(z.string().min(1)).optional(),
      conversationId: z.string().min(1).optional()
    }),
    outputSchema: z.object({
      answer: z.string(),
      conversation_id: z.string(),
      references: z.array(
        z.object({
          source_id: z.string(),
          title: z.string()
        })
      ),
      turn_number: z.number().int().positive().optional().nullable()
    }),
    permissionScopes: ["external_api.read"],
    timeoutMs: 20_000,
    sideEffecting: false,
    enabled: true,
    metadata: {
      safePhase: 3,
      policyClass: "review_required",
      providerId: "notebooklm"
    }
  },
  {
    id: "adapter.notebooklm.poll_artifact_task",
    name: "NotebookLM Poll Artifact Task",
    providerType: "adapter",
    inputSchema: withNotebookLmReference({
      taskId: z.string().min(1),
      artifactKind: z.enum(["report", "slide_deck", "video"]),
      downloadIfComplete: z.boolean().optional(),
      outputFormat: z.enum(["pdf", "pptx"]).optional()
    }),
    outputSchema: z.object({
      notebook_id: z.string(),
      artifact_kind: z.enum(["report", "slide_deck", "video"]),
      task_id: z.string(),
      status: z.string(),
      error: z.string().nullable().optional(),
      error_code: z.string().nullable().optional(),
      output_format: z.string().optional(),
      download_path: z.string().optional(),
      mime_type: z.string().optional()
    }),
    permissionScopes: ["external_api.read"],
    timeoutMs: 30_000,
    sideEffecting: false,
    enabled: true,
    metadata: {
      safePhase: 1,
      policyClass: "external_read",
      providerId: "notebooklm"
    }
  },
  {
    id: "adapter.notebooklm.add_source_text",
    name: "NotebookLM Add Source Text",
    providerType: "adapter",
    inputSchema: withNotebookLmReference({
      title: z.string().min(1),
      content: z.string().min(1),
      wait: z.boolean().optional()
    }),
    outputSchema: z.object({
      notebook_id: z.string(),
      source: z.object({
        id: z.string(),
        title: z.string(),
        kind: z.string(),
        status: z.string().nullable().optional()
      })
    }),
    permissionScopes: ["external_api.write"],
    timeoutMs: 30_000,
    sideEffecting: true,
    enabled: true,
    metadata: {
      safePhase: 3,
      policyClass: "review_required",
      providerId: "notebooklm"
    }
  },
  {
    id: "adapter.notebooklm.add_source_url",
    name: "NotebookLM Add Source URL",
    providerType: "adapter",
    inputSchema: withNotebookLmReference({
      url: z.string().min(1),
      wait: z.boolean().optional()
    }),
    outputSchema: z.object({
      notebook_id: z.string(),
      source: z.object({
        id: z.string(),
        title: z.string(),
        kind: z.string(),
        status: z.string().nullable().optional()
      })
    }),
    permissionScopes: ["external_api.write"],
    timeoutMs: 30_000,
    sideEffecting: true,
    enabled: true,
    metadata: {
      safePhase: 3,
      policyClass: "review_required",
      providerId: "notebooklm"
    }
  },
  {
    id: "adapter.notebooklm.add_source_file",
    name: "NotebookLM Add Source File",
    providerType: "adapter",
    inputSchema: withNotebookLmReference({
      filePath: z.string().min(1),
      title: z.string().min(1).optional(),
      mimeType: z.string().min(1).optional(),
      wait: z.boolean().optional()
    }),
    outputSchema: z.object({
      notebook_id: z.string(),
      source: z.object({
        id: z.string(),
        title: z.string(),
        kind: z.string(),
        status: z.string().nullable().optional()
      })
    }),
    permissionScopes: ["external_api.write"],
    timeoutMs: 120_000,
    sideEffecting: true,
    enabled: true,
    metadata: {
      safePhase: 3,
      policyClass: "review_required",
      providerId: "notebooklm",
      artifactPicker: {
        enabled: true,
        field_name: "filePath",
        selection_mode: "single",
        accepted_artifact_types: ["chat_export"],
        required_consumption_mode: "file_backed",
        max_artifact_count: 1
      }
    }
  },
  {
    id: "adapter.notebooklm.generate_report",
    name: "NotebookLM Generate Report",
    providerType: "adapter",
    inputSchema: withNotebookLmReference({
      sourceIds: z.array(z.string().min(1)).optional(),
      reportFormat: z.string().min(1).optional(),
      language: z.string().min(1).optional(),
      customPrompt: z.string().min(1).optional(),
      extraInstructions: z.string().min(1).optional(),
      waitForCompletion: z.boolean().optional(),
      persistArtifacts: z.boolean().optional()
    }),
    outputSchema: z.object({
      notebook_id: z.string(),
      artifact_kind: z.literal("report"),
      task_id: z.string(),
      status: z.string(),
      error: z.string().nullable().optional(),
      error_code: z.string().nullable().optional(),
      content_markdown: z.string().optional(),
      download_path: z.string().optional(),
      mime_type: z.string().optional(),
      artifacts: z.array(storedArtifactReferenceSchema).optional()
    }),
    permissionScopes: ["external_api.write"],
    timeoutMs: 180_000,
    sideEffecting: true,
    enabled: true,
    metadata: {
      safePhase: 3,
      policyClass: "review_required",
      providerId: "notebooklm"
    }
  },
  {
    id: "adapter.notebooklm.generate_slide_deck",
    name: "NotebookLM Generate Slide Deck",
    providerType: "adapter",
    inputSchema: withNotebookLmReference({
      sourceIds: z.array(z.string().min(1)).optional(),
      language: z.string().min(1).optional(),
      instructions: z.string().min(1).optional(),
      slideFormat: z.string().min(1).optional(),
      slideLength: z.string().min(1).optional(),
      outputFormat: z.enum(["pdf", "pptx"]).optional(),
      waitForCompletion: z.boolean().optional(),
      persistArtifacts: z.boolean().optional()
    }),
    outputSchema: z.object({
      notebook_id: z.string(),
      artifact_kind: z.literal("slide_deck"),
      task_id: z.string(),
      status: z.string(),
      error: z.string().nullable().optional(),
      error_code: z.string().nullable().optional(),
      output_format: z.string().optional(),
      download_path: z.string().optional(),
      mime_type: z.string().optional(),
      artifacts: z.array(storedArtifactReferenceSchema).optional()
    }),
    permissionScopes: ["external_api.write"],
    timeoutMs: 240_000,
    sideEffecting: true,
    enabled: true,
    metadata: {
      safePhase: 3,
      policyClass: "review_required",
      providerId: "notebooklm"
    }
  },
  {
    id: "adapter.notebooklm.generate_video",
    name: "NotebookLM Generate Video",
    providerType: "adapter",
    inputSchema: withNotebookLmReference({
      sourceIds: z.array(z.string().min(1)).optional(),
      language: z.string().min(1).optional(),
      instructions: z.string().min(1).optional(),
      videoFormat: z.string().min(1).optional(),
      videoStyle: z.string().min(1).optional(),
      stylePrompt: z.string().min(1).optional(),
      waitForCompletion: z.boolean().optional(),
      persistArtifacts: z.boolean().optional()
    }),
    outputSchema: z.object({
      notebook_id: z.string(),
      artifact_kind: z.literal("video"),
      task_id: z.string(),
      status: z.string(),
      error: z.string().nullable().optional(),
      error_code: z.string().nullable().optional(),
      download_path: z.string().optional(),
      mime_type: z.string().optional(),
      artifacts: z.array(storedArtifactReferenceSchema).optional()
    }),
    permissionScopes: ["external_api.write"],
    timeoutMs: 240_000,
    sideEffecting: true,
    enabled: true,
    metadata: {
      safePhase: 3,
      policyClass: "review_required",
      providerId: "notebooklm"
    }
  },
  {
    id: "site_build_adapter",
    name: "Site Build Adapter",
    providerType: "adapter",
    inputSchema: z.object({
      path: z.string().min(1)
    }),
    outputSchema: z.object({
      output: z.string()
    }),
    permissionScopes: ["adapter.execute"],
    timeoutMs: 5_000,
    sideEffecting: true,
    enabled: true,
    metadata: {
      safePhase: 3,
      policyClass: "review_required"
    }
  },
  {
    id: "load_artifact",
    name: "Load Artifact",
    providerType: "local",
    inputSchema: z.object({
      artifact_id: z.string().min(1)
    }),
    outputSchema: z.object({
      artifact_id: z.string(),
      artifact_type: z.string(),
      path: z.string(),
      display_name: z.string(),
      storage_file_name: z.string().optional(),
      summary: z.string().optional(),
      app_id: z.string(),
      created_at: z.string(),
      created_by_execution_id: z.string().optional(),
      created_by_turn_id: z.string().optional(),
      source_tool_id: z.string().optional(),
      source_skill_id: z.string().optional(),
      provider_origin: z.literal("local"),
      mime_type: z.string().optional(),
      size_bytes: z.number().int().nonnegative().optional(),
      file_path: z.string().optional(),
      status: z.literal("ready"),
      content: z.unknown()
    }),
    permissionScopes: ["artifact.read"],
    timeoutMs: 2_000,
    sideEffecting: false,
    enabled: true,
    metadata: {
      safePhase: 1,
      policyClass: "artifact_safe"
    }
  },
  {
    id: "rag_retrieval_tool",
    name: "RAG Retrieval Tool",
    providerType: "rag_adapter",
    inputSchema: z.object({
      query: z.string().min(1),
      topK: z.number().int().positive().max(10).optional(),
      operation: z.string().optional()
    }),
    outputSchema: z.object({
      items: z.array(
        z.object({
          title: z.string(),
          content: z.string(),
          metadata: z.record(z.string(), z.unknown())
        })
      )
    }),
    permissionScopes: ["rag.read"],
    timeoutMs: 1_000,
    sideEffecting: false,
    enabled: true
  },
  {
    id: "research_paper_search_tool",
    name: "Research Paper Search Tool",
    providerType: "api",
    inputSchema: z.object({
      topic: z.string().min(1),
      limit: z.number().int().positive().max(10).optional(),
      source: z.enum(["auto", "arxiv", "semantic-scholar"]).optional()
    }),
    outputSchema: z.object({
      topic: z.string(),
      source: z.string(),
      papers: z.array(
        z.object({
          title: z.string(),
          link: z.string(),
          year: z.number().int(),
          authors: z.array(z.string()),
          summary: z.string(),
          why_it_matters: z.string()
        })
      )
    }),
    permissionScopes: ["external_api.read"],
    timeoutMs: 20_000,
    sideEffecting: false,
    enabled: true
  },
  {
    id: "mock_video_generation_tool",
    name: "Mock Video Generation Tool",
    providerType: "api",
    inputSchema: z.object({
      prompt: z.string().min(1),
      duration: z.number().min(1).max(300),
      context: z.unknown().optional()
    }),
    outputSchema: z.object({
      title: z.string(),
      summary: z.string(),
      file_id: z.string()
    }),
    permissionScopes: ["external_api.write"],
    timeoutMs: 10,
    sideEffecting: true,
    enabled: true
  }
];

export class ToolRegistry {
  private readonly tools = new Map<string, ToolDefinition>();

  constructor(initialTools: ToolDefinition[] = defaultTools) {
    for (const tool of initialTools) {
      this.tools.set(tool.id, tool);
    }
  }

  list(): ToolDefinition[] {
    return [...this.tools.values()];
  }

  get(toolId: string): ToolDefinition {
    const tool = this.tools.get(toolId);
    if (!tool || tool.enabled === false) {
      throw new AppError({
        code: "TOOL_NOT_FOUND",
        message: "Tool was not found or is disabled.",
        errorClass: "validation",
        httpStatus: 404,
        details: { tool_id: toolId },
        recoverable: true,
        suggestedAction: "Use GET /v1/tools to inspect available tools."
      });
    }

    return tool;
  }

  resolve(toolIds: string[]): ToolDefinition[] {
    return toolIds.map((toolId) => this.get(toolId));
  }

  register(tool: ToolDefinition): void {
    this.tools.set(tool.id, tool);
  }
}
