import { z } from "zod";

import type { SkillDefinition } from "./skill.types.js";

const internalWrapperSkillMeta = {
  inventoryVisibility: "internal_wrapper" as const,
  workflowKind: "single_tool_wrapper" as const
};

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

const videoDirectorInputSchema = z.object({
  prompt: z.string().min(1),
  duration: z.number().min(1).max(300)
});

const videoDirectorOutputSchema = z.object({
  title: z.string(),
  summary: z.string(),
  file_id: z.string()
});

const fileInventoryInputSchema = z.object({
  path: z.string().min(1)
});

const fileInventoryOutputSchema = z.object({
  artifact_id: z.string()
});

const contentReplaceInputSchema = z.object({
  path: z.string().min(1),
  content: z.string()
});

const contentReplaceOutputSchema = z.object({
  path: z.string(),
  bytes_written: z.number().int().nonnegative(),
  updated: z.boolean()
});

const saveChatExportArtifactInputSchema = z.object({
  name: z.string().min(1),
  displayName: z.string().min(1).optional(),
  content: z.string().min(1),
  format: z.enum(["md", "txt"]).optional(),
  messageCount: z.number().int().positive().optional(),
  sessionId: z.string().min(1).optional(),
  reviewed: z.boolean().optional(),
  reviewedAt: z.string().min(1).optional(),
  reviewedBy: z.string().min(1).optional(),
  reviewSource: z.string().min(1).optional(),
  sourceMessageIds: z.array(z.string().min(1)).optional(),
  contentHash: z.string().min(1).optional()
});

const saveChatExportArtifactOutputSchema = z.object({
  artifact_id: z.string(),
  display_name: z.string().optional(),
  path: z.string(),
  file_path: z.string().optional(),
  artifact_type: z.literal("chat_export"),
  reviewed: z.boolean().optional(),
  reviewed_at: z.string().optional(),
  reviewed_by: z.string().optional(),
  review_source: z.string().optional(),
  source_message_ids: z.array(z.string()).optional(),
  content_hash: z.string().optional()
});

const adapterContentTransformInputSchema = z.object({
  content: z.string().min(1)
});

const adapterContentTransformOutputSchema = z.object({
  output: z.string()
});

const notebookLmListNotebooksInputSchema = z.object({});

const notebookLmListNotebooksOutputSchema = z.object({
  notebooks: z.array(
    z.object({
      id: z.string(),
      title: z.string(),
      sources_count: z.number().int().nonnegative()
    })
  )
});

const notebookLmListSourcesInputSchema = withNotebookLmReference({});

const notebookLmListSourcesOutputSchema = z.object({
  sources: z.array(
    z.object({
      id: z.string(),
      title: z.string(),
      kind: z.string(),
      status: z.string().nullable().optional()
    })
  )
});

const notebookLmAskInputSchema = withNotebookLmReference({
  question: z.string().min(1),
  sourceIds: z.array(z.string().min(1)).optional(),
  conversationId: z.string().min(1).optional()
});

const notebookLmAskOutputSchema = z.object({
  answer: z.string(),
  conversation_id: z.string(),
  references: z.array(
    z.object({
      source_id: z.string(),
      title: z.string()
    })
  ),
  turn_number: z.number().int().positive().optional().nullable()
});

const notebookLmPollArtifactTaskInputSchema = withNotebookLmReference({
  taskId: z.string().min(1),
  artifactKind: z.enum(["report", "slide_deck", "video"]),
  downloadIfComplete: z.boolean().optional(),
  outputFormat: z.enum(["pdf", "pptx"]).optional()
});

const notebookLmPollArtifactTaskOutputSchema = z.object({
  notebook_id: z.string(),
  artifact_kind: z.enum(["report", "slide_deck", "video"]),
  task_id: z.string(),
  status: z.string(),
  error: z.string().nullable().optional(),
  error_code: z.string().nullable().optional(),
  output_format: z.string().optional(),
  download_path: z.string().optional(),
  mime_type: z.string().optional()
});

const notebookLmSourceSummarySchema = z.object({
  id: z.string(),
  title: z.string(),
  kind: z.string(),
  status: z.string().nullable().optional()
});

const notebookLmAddSourceTextInputSchema = withNotebookLmReference({
  title: z.string().min(1),
  content: z.string().min(1),
  wait: z.boolean().optional()
});

const notebookLmAddSourceUrlInputSchema = withNotebookLmReference({
  url: z.string().min(1),
  wait: z.boolean().optional()
});

const notebookLmAddSourceFileInputSchema = withNotebookLmReference({
  filePath: z.string().min(1),
  title: z.string().min(1).optional(),
  mimeType: z.string().min(1).optional(),
  wait: z.boolean().optional()
});

const notebookLmAddSourceOutputSchema = z.object({
  notebook_id: z.string(),
  source: notebookLmSourceSummarySchema
});

const notebookLmGenerateReportInputSchema = withNotebookLmReference({
  sourceIds: z.array(z.string().min(1)).optional(),
  reportFormat: z.string().min(1).optional(),
  language: z.string().min(1).optional(),
  customPrompt: z.string().min(1).optional(),
  extraInstructions: z.string().min(1).optional(),
  waitForCompletion: z.boolean().optional(),
  persistArtifacts: z.boolean().optional()
});

const notebookLmGenerateReportOutputSchema = z.object({
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
});

const notebookLmGenerateSlideDeckInputSchema = withNotebookLmReference({
  sourceIds: z.array(z.string().min(1)).optional(),
  language: z.string().min(1).optional(),
  instructions: z.string().min(1).optional(),
  slideFormat: z.string().min(1).optional(),
  slideLength: z.string().min(1).optional(),
  outputFormat: z.enum(["pdf", "pptx"]).optional(),
  waitForCompletion: z.boolean().optional(),
  persistArtifacts: z.boolean().optional()
});

const notebookLmGenerateSlideDeckOutputSchema = z.object({
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
});

const notebookLmGenerateVideoInputSchema = withNotebookLmReference({
  sourceIds: z.array(z.string().min(1)).optional(),
  language: z.string().min(1).optional(),
  instructions: z.string().min(1).optional(),
  videoFormat: z.string().min(1).optional(),
  videoStyle: z.string().min(1).optional(),
  stylePrompt: z.string().min(1).optional(),
  waitForCompletion: z.boolean().optional(),
  persistArtifacts: z.boolean().optional()
});

const notebookLmGenerateVideoOutputSchema = z.object({
  notebook_id: z.string(),
  artifact_kind: z.literal("video"),
  task_id: z.string(),
  status: z.string(),
  error: z.string().nullable().optional(),
  error_code: z.string().nullable().optional(),
  download_path: z.string().optional(),
  mime_type: z.string().optional(),
  artifacts: z.array(storedArtifactReferenceSchema).optional()
});

const mcpPageSearchInputSchema = z.object({
  query: z.string().min(1)
});

const mcpPageSearchOutputSchema = z.object({
  results: z.array(
    z.object({
      id: z.string(),
      title: z.string()
    })
  )
});

const mcpPageCreateInputSchema = z.object({
  title: z.string().min(1)
});

const mcpPageCreateOutputSchema = z.object({
  id: z.string(),
  title: z.string()
});

const gmailMessageSearchInputSchema = z.object({
  query: z.string().min(1)
});

const gmailMessageSearchOutputSchema = z.object({
  results: z.array(
    z.object({
      id: z.string()
    }).passthrough()
  )
});

const gmailCreateDraftInputSchema = z.object({
  to: z.string().min(1),
  subject: z.string().min(1),
  body: z.string().min(1)
});

const gmailCreateDraftOutputSchema = z.object({
  id: z.string(),
  status: z.string(),
  threadId: z.string().optional()
});

const gmailCreateDraftWithAttachmentsInputSchema = z.object({
  to: z.string().min(1),
  subject: z.string().min(1),
  body: z.string().min(1),
  artifactIds: z.array(z.string().min(1)).min(1)
});

const gmailSendDraftInputSchema = z.object({
  draftId: z.string().min(1)
});

const gmailSendDraftOutputSchema = z.object({
  id: z.string(),
  status: z.string(),
  threadId: z.string().optional()
});

const gmailSendMessageInputSchema = z.object({
  to: z.string().min(1),
  subject: z.string().min(1),
  body: z.string().min(1)
});

const gmailSendMessageOutputSchema = z.object({
  id: z.string(),
  status: z.string(),
  threadId: z.string().optional()
});

const googleDocsSearchInputSchema = z.object({
  query: z.string().min(1)
});

const googleDocsSearchOutputSchema = z.object({
  results: z.array(
    z.object({
      id: z.string(),
      title: z.string().optional()
    }).passthrough()
  )
});

const googleDriveSearchInputSchema = z.object({
  query: z.string().min(1)
});

const googleDriveSearchOutputSchema = z.object({
  results: z.array(
    z.object({
      id: z.string(),
      name: z.string().optional()
    }).passthrough()
  )
});

const googleDriveDownloadFileInputSchema = z.object({
  fileId: z.string().min(1)
});

const googleDriveDownloadFileOutputSchema = z.object({
  artifact_id: z.string(),
  artifact_type: z.string(),
  path: z.string(),
  file_id: z.string(),
  name: z.string().optional(),
  mime_type: z.string().optional()
});

export const videoDirectorSkill: SkillDefinition = {
  id: "video_director_skill",
  name: "Video Director Skill",
  version: "1.0.0",
  description: "Generates a short explainer video from a prompt.",
  inventoryVisibility: "user_skill",
  workflowKind: "multi_step_workflow",
  inputSchema: videoDirectorInputSchema,
  outputSchema: videoDirectorOutputSchema,
  requiredTools: ["rag_retrieval_tool", "mock_video_generation_tool"],
  requiredPermissions: ["rag.read", "external_api.write"],
  workflowDefinition: {
    steps: [
      {
        id: "validate_prompt",
        type: "validation",
        action: "validate_prompt",
        on: { success: "retrieve_context" }
      },
      {
        id: "retrieve_context",
        type: "tool_call",
        toolId: "rag_retrieval_tool",
        inputMapping: {
          query: "$.input.prompt",
          topK: 3
        },
        outputMapping: {
          context: "$.output.items"
        },
        on: { success: "generate_video" }
      },
      {
        id: "generate_video",
        type: "tool_call",
        toolId: "mock_video_generation_tool",
        inputMapping: {
          prompt: "$.input.prompt",
          duration: "$.input.duration",
          context: "$.steps.retrieve_context.output.context"
        },
        outputMapping: {
          title: "$.output.title",
          summary: "$.output.summary",
          file_id: "$.output.file_id"
        },
        on: { success: "success_completed" }
      },
      {
        id: "success_completed",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "video"
};

export const fileInventorySkill: SkillDefinition = {
  id: "file_inventory",
  name: "File Inventory",
  version: "1.0.0",
  description: "Inspect a path and save an inventory artifact.",
  ...internalWrapperSkillMeta,
  inputSchema: fileInventoryInputSchema,
  outputSchema: fileInventoryOutputSchema,
  requiredTools: ["list_files", "save_artifact"],
  requiredPermissions: ["filesystem.read", "artifact.write"],
  workflowDefinition: {
    steps: [
      {
        id: "list_files",
        type: "tool_call",
        toolId: "list_files",
        inputMapping: {
          path: "$.input.path"
        },
        outputMapping: {
          entries: "$.output.entries"
        },
        on: { success: "save_report" }
      },
      {
        id: "save_report",
        type: "tool_call",
        toolId: "save_artifact",
        inputMapping: {
          artifact_type: "file_inventory",
          name: "inventory-report",
          content: "$.steps.list_files.output.entries"
        },
        outputMapping: {
          artifact_id: "$.output.artifact_id"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const contentReplaceSkill: SkillDefinition = {
  id: "content_replace",
  name: "Content Replace",
  version: "1.0.0",
  description: "Replace file content within configured mutation roots.",
  ...internalWrapperSkillMeta,
  inputSchema: contentReplaceInputSchema,
  outputSchema: contentReplaceOutputSchema,
  requiredTools: ["write_file"],
  requiredPermissions: ["filesystem.write"],
  workflowDefinition: {
    steps: [
      {
        id: "write_file",
        type: "tool_call",
        toolId: "write_file",
        inputMapping: {
          path: "$.input.path",
          content: "$.input.content"
        },
        outputMapping: {
          path: "$.output.path",
          bytes_written: "$.output.bytes_written",
          updated: "$.output.updated"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const saveChatExportArtifactSkill: SkillDefinition = {
  id: "save_chat_export_artifact",
  name: "Save Chat Export Artifact",
  version: "1.0.0",
  description: "Persist selected chat transcript content as an app-scoped artifact.",
  ...internalWrapperSkillMeta,
  inputSchema: saveChatExportArtifactInputSchema,
  outputSchema: saveChatExportArtifactOutputSchema,
  requiredTools: ["save_artifact"],
  requiredPermissions: ["artifact.write"],
  workflowDefinition: {
    steps: [
      {
        id: "save_artifact",
        type: "tool_call",
        toolId: "save_artifact",
        inputMapping: {
          artifact_type: "chat_export",
          name: "$.input.name",
          display_name: "$.input.displayName",
          reviewed: "$.input.reviewed",
          reviewed_at: "$.input.reviewedAt",
          reviewed_by: "$.input.reviewedBy",
          review_source: "$.input.reviewSource",
          source_message_ids: "$.input.sourceMessageIds",
          content_hash: "$.input.contentHash",
          content: {
            content: "$.input.content",
            format: "$.input.format",
            message_count: "$.input.messageCount",
            session_id: "$.input.sessionId",
            reviewed: "$.input.reviewed",
            reviewed_at: "$.input.reviewedAt",
            reviewed_by: "$.input.reviewedBy",
            review_source: "$.input.reviewSource",
            source_message_ids: "$.input.sourceMessageIds",
            content_hash: "$.input.contentHash"
          }
        },
        outputMapping: {
          artifact_id: "$.output.artifact_id",
          display_name: "$.output.display_name",
          path: "$.output.path",
          file_path: "$.output.file_path",
          artifact_type: "$.output.artifact_type",
          reviewed: "$.output.reviewed",
          reviewed_at: "$.output.reviewed_at",
          reviewed_by: "$.output.reviewed_by",
          review_source: "$.output.review_source",
          source_message_ids: "$.output.source_message_ids",
          content_hash: "$.output.content_hash"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const adapterContentTransformSkill: SkillDefinition = {
  id: "adapter_content_transform",
  name: "Adapter Content Transform",
  version: "1.0.0",
  description: "Transform content through an approved adapter.",
  ...internalWrapperSkillMeta,
  inputSchema: adapterContentTransformInputSchema,
  outputSchema: adapterContentTransformOutputSchema,
  requiredTools: ["content_transform_adapter"],
  requiredPermissions: ["adapter.execute"],
  workflowDefinition: {
    steps: [
      {
        id: "run_transform",
        type: "service_call",
        serviceId: "content_transform_adapter",
        inputMapping: {
          content: "$.input.content"
        },
        outputMapping: {
          output: "$.output.output"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const notebookLmListNotebooksSkill: SkillDefinition = {
  id: "notebooklm_list_notebooks",
  name: "NotebookLM List Notebooks",
  version: "1.0.0",
  description: "List NotebookLM notebooks visible to the configured NotebookLM session.",
  ...internalWrapperSkillMeta,
  inputSchema: notebookLmListNotebooksInputSchema,
  outputSchema: notebookLmListNotebooksOutputSchema,
  requiredTools: ["adapter.notebooklm.list_notebooks"],
  requiredPermissions: ["external_api.read"],
  workflowDefinition: {
    steps: [
      {
        id: "list_notebooks",
        type: "service_call",
        serviceId: "adapter.notebooklm.list_notebooks",
        inputMapping: {},
        outputMapping: {
          notebooks: "$.output.notebooks"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const notebookLmListSourcesSkill: SkillDefinition = {
  id: "notebooklm_list_sources",
  name: "NotebookLM List Sources",
  version: "1.0.0",
  description: "List sources for a NotebookLM notebook.",
  ...internalWrapperSkillMeta,
  inputSchema: notebookLmListSourcesInputSchema,
  outputSchema: notebookLmListSourcesOutputSchema,
  requiredTools: ["adapter.notebooklm.list_sources"],
  requiredPermissions: ["external_api.read"],
  workflowDefinition: {
    steps: [
      {
        id: "list_sources",
        type: "service_call",
        serviceId: "adapter.notebooklm.list_sources",
        inputMapping: {
          notebookId: "$.input.notebookId",
          notebookTitle: "$.input.notebookTitle"
        },
        outputMapping: {
          sources: "$.output.sources"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const notebookLmAskSkill: SkillDefinition = {
  id: "notebooklm_existing_notebook_ask",
  name: "NotebookLM Existing Notebook Ask",
  version: "1.0.0",
  description: "Ask a question against an existing NotebookLM notebook.",
  ...internalWrapperSkillMeta,
  inputSchema: notebookLmAskInputSchema,
  outputSchema: notebookLmAskOutputSchema,
  requiredTools: ["adapter.notebooklm.ask"],
  requiredPermissions: ["external_api.read"],
  workflowDefinition: {
    steps: [
      {
        id: "ask_notebooklm",
        type: "service_call",
        serviceId: "adapter.notebooklm.ask",
        inputMapping: {
          notebookId: "$.input.notebookId",
          notebookTitle: "$.input.notebookTitle",
          question: "$.input.question",
          sourceIds: "$.input.sourceIds",
          conversationId: "$.input.conversationId"
        },
        outputMapping: {
          answer: "$.output.answer",
          conversation_id: "$.output.conversation_id",
          references: "$.output.references",
          turn_number: "$.output.turn_number"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const notebookLmAddSourceTextSkill: SkillDefinition = {
  id: "notebooklm_add_source_text",
  name: "NotebookLM Add Source Text",
  version: "1.0.0",
  description: "Add text content as a source to an existing NotebookLM notebook.",
  ...internalWrapperSkillMeta,
  inputSchema: notebookLmAddSourceTextInputSchema,
  outputSchema: notebookLmAddSourceOutputSchema,
  requiredTools: ["adapter.notebooklm.add_source_text"],
  requiredPermissions: ["external_api.write"],
  confirmationMode: "require_confirmation",
  workflowDefinition: {
    steps: [
      {
        id: "add_source_text",
        type: "service_call",
        serviceId: "adapter.notebooklm.add_source_text",
        inputMapping: {
          notebookId: "$.input.notebookId",
          notebookTitle: "$.input.notebookTitle",
          title: "$.input.title",
          content: "$.input.content",
          wait: "$.input.wait"
        },
        outputMapping: {
          notebook_id: "$.output.notebook_id",
          source: "$.output.source"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const notebookLmAddSourceUrlSkill: SkillDefinition = {
  id: "notebooklm_add_source_url",
  name: "NotebookLM Add Source URL",
  version: "1.0.0",
  description: "Add a URL source to an existing NotebookLM notebook.",
  ...internalWrapperSkillMeta,
  inputSchema: notebookLmAddSourceUrlInputSchema,
  outputSchema: notebookLmAddSourceOutputSchema,
  requiredTools: ["adapter.notebooklm.add_source_url"],
  requiredPermissions: ["external_api.write"],
  confirmationMode: "require_confirmation",
  workflowDefinition: {
    steps: [
      {
        id: "add_source_url",
        type: "service_call",
        serviceId: "adapter.notebooklm.add_source_url",
        inputMapping: {
          notebookId: "$.input.notebookId",
          notebookTitle: "$.input.notebookTitle",
          url: "$.input.url",
          wait: "$.input.wait"
        },
        outputMapping: {
          notebook_id: "$.output.notebook_id",
          source: "$.output.source"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const notebookLmAddSourceFileSkill: SkillDefinition = {
  id: "notebooklm_add_source_file",
  name: "NotebookLM Add Source File",
  version: "1.0.0",
  description: "Upload a file source into an existing NotebookLM notebook.",
  ...internalWrapperSkillMeta,
  inputSchema: notebookLmAddSourceFileInputSchema,
  outputSchema: notebookLmAddSourceOutputSchema,
  requiredTools: ["adapter.notebooklm.add_source_file"],
  requiredPermissions: ["external_api.write"],
  confirmationMode: "require_confirmation",
  workflowDefinition: {
    steps: [
      {
        id: "add_source_file",
        type: "service_call",
        serviceId: "adapter.notebooklm.add_source_file",
        inputMapping: {
          notebookId: "$.input.notebookId",
          notebookTitle: "$.input.notebookTitle",
          filePath: "$.input.filePath",
          title: "$.input.title",
          mimeType: "$.input.mimeType",
          wait: "$.input.wait"
        },
        outputMapping: {
          notebook_id: "$.output.notebook_id",
          source: "$.output.source"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const notebookLmGenerateReportSkill: SkillDefinition = {
  id: "notebooklm_generate_report",
  name: "NotebookLM Generate Report",
  version: "1.0.0",
  description: "Generate a NotebookLM report from an existing notebook.",
  ...internalWrapperSkillMeta,
  inputSchema: notebookLmGenerateReportInputSchema,
  outputSchema: notebookLmGenerateReportOutputSchema,
  requiredTools: ["adapter.notebooklm.generate_report"],
  requiredPermissions: ["external_api.write"],
  confirmationMode: "require_confirmation",
  workflowDefinition: {
    steps: [
      {
        id: "generate_report",
        type: "service_call",
        serviceId: "adapter.notebooklm.generate_report",
        inputMapping: {
          notebookId: "$.input.notebookId",
          notebookTitle: "$.input.notebookTitle",
          sourceIds: "$.input.sourceIds",
          reportFormat: "$.input.reportFormat",
          language: "$.input.language",
          customPrompt: "$.input.customPrompt",
          extraInstructions: "$.input.extraInstructions",
          waitForCompletion: "$.input.waitForCompletion",
          persistArtifacts: "$.input.persistArtifacts"
        },
        outputMapping: {
          notebook_id: "$.output.notebook_id",
          artifact_kind: "$.output.artifact_kind",
          task_id: "$.output.task_id",
          status: "$.output.status",
          error: "$.output.error",
          error_code: "$.output.error_code",
          content_markdown: "$.output.content_markdown",
          download_path: "$.output.download_path",
          mime_type: "$.output.mime_type"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const notebookLmGenerateSlideDeckSkill: SkillDefinition = {
  id: "notebooklm_generate_slide_deck",
  name: "NotebookLM Generate Slide Deck",
  version: "1.0.0",
  description: "Generate a NotebookLM slide deck from an existing notebook.",
  ...internalWrapperSkillMeta,
  inputSchema: notebookLmGenerateSlideDeckInputSchema,
  outputSchema: notebookLmGenerateSlideDeckOutputSchema,
  requiredTools: ["adapter.notebooklm.generate_slide_deck"],
  requiredPermissions: ["external_api.write"],
  confirmationMode: "require_confirmation",
  workflowDefinition: {
    steps: [
      {
        id: "generate_slide_deck",
        type: "service_call",
        serviceId: "adapter.notebooklm.generate_slide_deck",
        inputMapping: {
          notebookId: "$.input.notebookId",
          notebookTitle: "$.input.notebookTitle",
          sourceIds: "$.input.sourceIds",
          language: "$.input.language",
          instructions: "$.input.instructions",
          slideFormat: "$.input.slideFormat",
          slideLength: "$.input.slideLength",
          outputFormat: "$.input.outputFormat",
          waitForCompletion: "$.input.waitForCompletion",
          persistArtifacts: "$.input.persistArtifacts"
        },
        outputMapping: {
          notebook_id: "$.output.notebook_id",
          artifact_kind: "$.output.artifact_kind",
          task_id: "$.output.task_id",
          status: "$.output.status",
          error: "$.output.error",
          error_code: "$.output.error_code",
          output_format: "$.output.output_format",
          download_path: "$.output.download_path",
          mime_type: "$.output.mime_type"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const notebookLmGenerateVideoSkill: SkillDefinition = {
  id: "notebooklm_generate_video",
  name: "NotebookLM Generate Video",
  version: "1.0.0",
  description: "Generate a NotebookLM video from an existing notebook.",
  ...internalWrapperSkillMeta,
  inputSchema: notebookLmGenerateVideoInputSchema,
  outputSchema: notebookLmGenerateVideoOutputSchema,
  requiredTools: ["adapter.notebooklm.generate_video"],
  requiredPermissions: ["external_api.write"],
  confirmationMode: "require_confirmation",
  workflowDefinition: {
    steps: [
      {
        id: "generate_video",
        type: "service_call",
        serviceId: "adapter.notebooklm.generate_video",
        inputMapping: {
          notebookId: "$.input.notebookId",
          notebookTitle: "$.input.notebookTitle",
          sourceIds: "$.input.sourceIds",
          language: "$.input.language",
          instructions: "$.input.instructions",
          videoFormat: "$.input.videoFormat",
          videoStyle: "$.input.videoStyle",
          stylePrompt: "$.input.stylePrompt",
          waitForCompletion: "$.input.waitForCompletion",
          persistArtifacts: "$.input.persistArtifacts"
        },
        outputMapping: {
          notebook_id: "$.output.notebook_id",
          artifact_kind: "$.output.artifact_kind",
          task_id: "$.output.task_id",
          status: "$.output.status",
          error: "$.output.error",
          error_code: "$.output.error_code",
          download_path: "$.output.download_path",
          mime_type: "$.output.mime_type"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const notebookLmPollArtifactTaskSkill: SkillDefinition = {
  id: "notebooklm_poll_artifact_task",
  name: "NotebookLM Poll Artifact Task",
  version: "1.0.0",
  description: "Poll the status of a NotebookLM artifact generation task.",
  ...internalWrapperSkillMeta,
  inputSchema: notebookLmPollArtifactTaskInputSchema,
  outputSchema: notebookLmPollArtifactTaskOutputSchema,
  requiredTools: ["adapter.notebooklm.poll_artifact_task"],
  requiredPermissions: ["external_api.read"],
  workflowDefinition: {
    steps: [
      {
        id: "poll_artifact_task",
        type: "service_call",
        serviceId: "adapter.notebooklm.poll_artifact_task",
        inputMapping: {
          notebookId: "$.input.notebookId",
          notebookTitle: "$.input.notebookTitle",
          taskId: "$.input.taskId",
          artifactKind: "$.input.artifactKind",
          downloadIfComplete: "$.input.downloadIfComplete",
          outputFormat: "$.input.outputFormat"
        },
        outputMapping: {
          notebook_id: "$.output.notebook_id",
          artifact_kind: "$.output.artifact_kind",
          task_id: "$.output.task_id",
          status: "$.output.status",
          error: "$.output.error",
          error_code: "$.output.error_code",
          output_format: "$.output.output_format",
          download_path: "$.output.download_path",
          mime_type: "$.output.mime_type"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const mcpPageSearchSkill: SkillDefinition = {
  id: "mcp_page_search",
  name: "MCP Page Search",
  version: "1.0.0",
  description: "Search pages through the CMS MCP provider.",
  ...internalWrapperSkillMeta,
  inputSchema: mcpPageSearchInputSchema,
  outputSchema: mcpPageSearchOutputSchema,
  requiredTools: ["mcp.cms.search_pages"],
  requiredPermissions: ["external_api.read"],
  workflowDefinition: {
    steps: [
      {
        id: "search_pages",
        type: "service_call",
        serviceId: "mcp.cms.search_pages",
        inputMapping: {
          query: "$.input.query"
        },
        outputMapping: {
          results: "$.output.results"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const mcpPageCreateSkill: SkillDefinition = {
  id: "mcp_page_create",
  name: "MCP Page Create",
  version: "1.0.0",
  description: "Create pages through the CMS MCP provider.",
  ...internalWrapperSkillMeta,
  inputSchema: mcpPageCreateInputSchema,
  outputSchema: mcpPageCreateOutputSchema,
  requiredTools: ["mcp.cms.create_page"],
  requiredPermissions: ["external_api.write"],
  workflowDefinition: {
    steps: [
      {
        id: "create_page",
        type: "service_call",
        serviceId: "mcp.cms.create_page",
        inputMapping: {
          title: "$.input.title"
        },
        outputMapping: {
          id: "$.output.id",
          title: "$.output.title"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const gmailMessageSearchSkill: SkillDefinition = {
  id: "gmail_message_search",
  name: "Gmail Message Search",
  version: "1.0.0",
  description: "Search Gmail messages through the Gmail MCP provider.",
  ...internalWrapperSkillMeta,
  inputSchema: gmailMessageSearchInputSchema,
  outputSchema: gmailMessageSearchOutputSchema,
  requiredTools: ["mcp.gmail.search_messages"],
  requiredPermissions: ["external_api.read"],
  workflowDefinition: {
    steps: [
      {
        id: "search_messages",
        type: "service_call",
        serviceId: "mcp.gmail.search_messages",
        inputMapping: {
          query: "$.input.query"
        },
        outputMapping: {
          results: "$.output.results"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const gmailCreateDraftSkill: SkillDefinition = {
  id: "gmail_create_draft",
  name: "Gmail Create Draft",
  version: "1.0.0",
  description: "Create a Gmail draft through the Gmail MCP provider.",
  ...internalWrapperSkillMeta,
  confirmationMode: "require_confirmation",
  inputSchema: gmailCreateDraftInputSchema,
  outputSchema: gmailCreateDraftOutputSchema,
  requiredTools: ["mcp.gmail.create_draft"],
  requiredPermissions: ["external_api.write"],
  workflowDefinition: {
    steps: [
      {
        id: "create_draft",
        type: "service_call",
        serviceId: "mcp.gmail.create_draft",
        inputMapping: {
          to: "$.input.to",
          subject: "$.input.subject",
          body: "$.input.body"
        },
        outputMapping: {
          id: "$.output.id",
          status: "$.output.status",
          threadId: "$.output.threadId"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const gmailCreateDraftWithAttachmentsSkill: SkillDefinition = {
  id: "gmail_create_draft_with_attachments",
  name: "Gmail Create Draft With Attachments",
  version: "1.0.0",
  description: "Create a Gmail draft with app-scoped artifact attachments through the Gmail MCP provider.",
  ...internalWrapperSkillMeta,
  confirmationMode: "require_confirmation",
  inputSchema: gmailCreateDraftWithAttachmentsInputSchema,
  outputSchema: gmailCreateDraftOutputSchema,
  requiredTools: ["mcp.gmail.create_draft_with_attachments"],
  requiredPermissions: ["external_api.write", "artifact.read"],
  workflowDefinition: {
    steps: [
      {
        id: "create_draft_with_attachments",
        type: "service_call",
        serviceId: "mcp.gmail.create_draft_with_attachments",
        inputMapping: {
          to: "$.input.to",
          subject: "$.input.subject",
          body: "$.input.body",
          artifactIds: "$.input.artifactIds"
        },
        outputMapping: {
          id: "$.output.id",
          status: "$.output.status",
          threadId: "$.output.threadId"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const gmailSendDraftSkill: SkillDefinition = {
  id: "gmail_send_draft",
  name: "Gmail Send Draft",
  version: "1.0.0",
  description: "Send an existing Gmail draft through the Gmail MCP provider.",
  ...internalWrapperSkillMeta,
  confirmationMode: "require_confirmation",
  inputSchema: gmailSendDraftInputSchema,
  outputSchema: gmailSendDraftOutputSchema,
  requiredTools: ["mcp.gmail.send_draft"],
  requiredPermissions: ["external_api.write"],
  workflowDefinition: {
    steps: [
      {
        id: "send_draft",
        type: "service_call",
        serviceId: "mcp.gmail.send_draft",
        inputMapping: {
          draftId: "$.input.draftId"
        },
        outputMapping: {
          id: "$.output.id",
          status: "$.output.status",
          threadId: "$.output.threadId"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const gmailSendMessageSkill: SkillDefinition = {
  id: "gmail_send_message",
  name: "Gmail Send Message",
  version: "1.0.0",
  description: "Send a Gmail message directly through the Gmail MCP provider.",
  ...internalWrapperSkillMeta,
  confirmationMode: "require_confirmation",
  inputSchema: gmailSendMessageInputSchema,
  outputSchema: gmailSendMessageOutputSchema,
  requiredTools: ["mcp.gmail.send_message"],
  requiredPermissions: ["external_api.write"],
  workflowDefinition: {
    steps: [
      {
        id: "send_message",
        type: "service_call",
        serviceId: "mcp.gmail.send_message",
        inputMapping: {
          to: "$.input.to",
          subject: "$.input.subject",
          body: "$.input.body"
        },
        outputMapping: {
          id: "$.output.id",
          status: "$.output.status",
          threadId: "$.output.threadId"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const googleDocsSearchSkill: SkillDefinition = {
  id: "google_docs_search",
  name: "Google Docs Search",
  version: "1.0.0",
  description: "Search Google Docs documents through the Google Docs MCP provider.",
  ...internalWrapperSkillMeta,
  inputSchema: googleDocsSearchInputSchema,
  outputSchema: googleDocsSearchOutputSchema,
  requiredTools: ["mcp.gdocs.search_documents"],
  requiredPermissions: ["external_api.read"],
  workflowDefinition: {
    steps: [
      {
        id: "search_documents",
        type: "service_call",
        serviceId: "mcp.gdocs.search_documents",
        inputMapping: {
          query: "$.input.query"
        },
        outputMapping: {
          results: "$.output.results"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const googleDriveSearchSkill: SkillDefinition = {
  id: "google_drive_search",
  name: "Google Drive Search",
  version: "1.0.0",
  description: "Search Google Drive files through the Google Drive MCP provider.",
  ...internalWrapperSkillMeta,
  inputSchema: googleDriveSearchInputSchema,
  outputSchema: googleDriveSearchOutputSchema,
  requiredTools: ["mcp.gdrive.search_files"],
  requiredPermissions: ["external_api.read"],
  workflowDefinition: {
    steps: [
      {
        id: "search_files",
        type: "service_call",
        serviceId: "mcp.gdrive.search_files",
        inputMapping: {
          query: "$.input.query"
        },
        outputMapping: {
          results: "$.output.results"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const googleDriveDownloadFileSkill: SkillDefinition = {
  id: "google_drive_download_file",
  name: "Google Drive Download File",
  version: "1.0.0",
  description: "Download Google Drive file content through the Google Drive MCP provider and store it as an artifact.",
  ...internalWrapperSkillMeta,
  inputSchema: googleDriveDownloadFileInputSchema,
  outputSchema: googleDriveDownloadFileOutputSchema,
  requiredTools: ["mcp.gdrive.download_file_content", "save_artifact"],
  requiredPermissions: ["external_api.read", "artifact.write"],
  workflowDefinition: {
    steps: [
      {
        id: "download_file_content",
        type: "service_call",
        serviceId: "mcp.gdrive.download_file_content",
        inputMapping: {
          fileId: "$.input.fileId"
        },
        outputMapping: {
          file_id: "$.output.file_id",
          name: "$.output.name",
          mime_type: "$.output.mime_type",
          content: "$.output.content",
          content_encoding: "$.output.content_encoding"
        },
        on: { success: "save_artifact" }
      },
      {
        id: "save_artifact",
        type: "tool_call",
        toolId: "save_artifact",
        inputMapping: {
          artifact_type: "google_drive_export",
          name: "$.steps.download_file_content.output.name",
          content: "$.steps.download_file_content.output"
        },
        outputMapping: {
          artifact_id: "$.output.artifact_id",
          path: "$.output.path",
          artifact_type: "$.output.artifact_type",
          file_id: "$.steps.download_file_content.output.file_id",
          name: "$.steps.download_file_content.output.name",
          mime_type: "$.steps.download_file_content.output.mime_type"
        },
        on: { success: "finish" }
      },
      {
        id: "finish",
        type: "end"
      }
    ]
  },
  enabled: true,
  resultType: "json"
};

export const sampleSkills: SkillDefinition[] = [
  videoDirectorSkill,
  fileInventorySkill,
  contentReplaceSkill,
  saveChatExportArtifactSkill,
  adapterContentTransformSkill,
  notebookLmListNotebooksSkill,
  notebookLmListSourcesSkill,
  notebookLmAskSkill,
  notebookLmAddSourceTextSkill,
  notebookLmAddSourceUrlSkill,
  notebookLmAddSourceFileSkill,
  notebookLmGenerateReportSkill,
  notebookLmGenerateSlideDeckSkill,
  notebookLmGenerateVideoSkill,
  notebookLmPollArtifactTaskSkill,
  mcpPageSearchSkill,
  mcpPageCreateSkill,
  gmailMessageSearchSkill,
  gmailCreateDraftSkill,
  gmailCreateDraftWithAttachmentsSkill,
  gmailSendDraftSkill,
  gmailSendMessageSkill,
  googleDocsSearchSkill,
  googleDriveSearchSkill,
  googleDriveDownloadFileSkill
];
