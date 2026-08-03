import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { z } from "zod";

import { WorkflowOrchestrator } from "../../src/core/workflow/workflow-orchestrator.js";
import { ToolRegistry } from "../../src/core/tools/tool-registry.js";
import { ToolEngine } from "../../src/core/tools/tool-engine.js";
import type { ExecutionContext } from "../../src/core/execution/execution-context.js";
import { PermissionEngine } from "../../src/core/permissions/permission-engine.js";

describe("workflow placeholder", () => {
  it("supports local decision branching", async () => {
    const orchestrator = new WorkflowOrchestrator(
      new ToolRegistry(),
      new ToolEngine(
        {
          api: {
            async execute(tool, input) {
              if (tool.id === "mock_video_generation_tool") {
                return {
                  title: `Video: ${String(input.prompt)}`,
                  summary: `Generated ${String(input.duration)} second explainer video.`,
                  file_id: "file_mock_video_001"
                };
              }

              throw new Error(`unexpected tool ${tool.id}`);
            }
          }
        },
        new PermissionEngine([
          {
            appId: "app_001",
            toolId: "mock_video_generation_tool",
            scope: "external_api.write",
            mode: "auto_allow"
          }
        ])
      )
    );

    const baseContext: Omit<ExecutionContext, "request" | "skill"> = {
      executionId: "execution_001",
      confirmed: false,
      executionOptions: { dry_run: false },
      toolDefinitions: [],
      stepOutputs: {},
      toolResults: {},
      errors: []
    };

    const yesResult = await orchestrator.execute({
      ...baseContext,
      request: {
        request_type: "execute_skill",
        app_id: "app_001",
        session_id: "sess_001",
        skill_id: "branching_skill",
        input: {
          make_video: true,
          prompt: "Explain RAG simply",
          duration: 30
        }
      },
      skill: {
        id: "branching_skill",
        name: "Branching Skill",
        version: "1.0.0",
        description: "tests local decision",
        inputSchema: { parse: (value: unknown) => value } as never,
        outputSchema: { parse: (value: unknown) => value } as never,
        requiredTools: ["mock_video_generation_tool"],
        requiredPermissions: ["external_api.write"],
        workflowDefinition: {
          steps: [
            {
              id: "decide_path",
              type: "local_decision",
              action: "is_truthy",
              inputMapping: {
                value: "$.input.make_video"
              },
              on: {
                true: "make_video",
                false: "end"
              }
            },
            {
              id: "make_video",
              type: "tool_call",
              toolId: "mock_video_generation_tool",
              inputMapping: {
                prompt: "$.input.prompt",
                duration: "$.input.duration"
              },
              outputMapping: {
                title: "$.output.title"
              },
              on: { success: "end" }
            },
            {
              id: "end",
              type: "end"
            }
          ]
        },
        enabled: true,
        resultType: "json"
      }
    });

    assert.equal(yesResult.title, "Video: Explain RAG simply");

    const noResult = await orchestrator.execute({
      ...baseContext,
      stepOutputs: {},
      toolResults: {},
      request: {
        request_type: "execute_skill",
        app_id: "app_001",
        session_id: "sess_001",
        skill_id: "branching_skill",
        input: {
          make_video: false,
          prompt: "Explain RAG simply",
          duration: 30
        }
      },
      skill: {
        id: "branching_skill",
        name: "Branching Skill",
        version: "1.0.0",
        description: "tests local decision",
        inputSchema: { parse: (value: unknown) => value } as never,
        outputSchema: { parse: (value: unknown) => value } as never,
        requiredTools: ["mock_video_generation_tool"],
        requiredPermissions: ["external_api.write"],
        workflowDefinition: {
          steps: [
            {
              id: "decide_path",
              type: "local_decision",
              action: "is_truthy",
              inputMapping: {
                value: "$.input.make_video"
              },
              on: {
                true: "make_video",
                false: "end"
              }
            },
            {
              id: "make_video",
              type: "tool_call",
              toolId: "mock_video_generation_tool",
              inputMapping: {
                prompt: "$.input.prompt",
                duration: "$.input.duration"
              },
              outputMapping: {
                title: "$.output.title"
              },
              on: { success: "end" }
            },
            {
              id: "end",
              type: "end"
            }
          ]
        },
        enabled: true,
        resultType: "json"
      }
    });

    assert.deepEqual(noResult, { decision: false });
  });

  it("supports service call routing through named tools", async () => {
    const orchestrator = new WorkflowOrchestrator(
      new ToolRegistry(),
      new ToolEngine(
        {
          adapter: {
            async execute() {
              return {
                output: "HELLO"
              };
            }
          }
        } as never,
        new PermissionEngine([
          {
            appId: "app_001",
            toolId: "content_transform_adapter",
            scope: "adapter.execute",
            mode: "auto_allow"
          }
        ])
      )
    );

    const result = await orchestrator.execute({
      executionId: "execution_002",
      confirmed: false,
      executionOptions: { dry_run: false },
      toolDefinitions: [],
      stepOutputs: {},
      toolResults: {},
      errors: [],
      request: {
        request_type: "execute_skill",
        app_id: "app_001",
        session_id: "sess_001",
        skill_id: "service_skill",
        input: {
          content: "hello"
        }
      },
      skill: {
        id: "service_skill",
        name: "Service Skill",
        version: "1.0.0",
        description: "tests service call",
        inputSchema: { parse: (value: unknown) => value } as never,
        outputSchema: { parse: (value: unknown) => value } as never,
        requiredTools: ["content_transform_adapter"],
        requiredPermissions: ["adapter.execute"],
        workflowDefinition: {
          steps: [
            {
              id: "invoke_transform",
              type: "service_call",
              serviceId: "content_transform_adapter",
              inputMapping: { content: "$.input.content" },
              outputMapping: { output: "$.output.output" },
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
      }
    });

    assert.deepEqual(result, { output: "HELLO" });
  });

  it("resolves nested array and object mappings across workflow steps", async () => {
    const registry = new ToolRegistry();
    registry.register({
      id: "mcp.gdrive.download_file_content",
      name: "Google Drive Download File Content",
      providerType: "mcp",
      inputSchema: z.object({
        fileId: z.string().min(1)
      }),
      outputSchema: z.object({
        file_id: z.string(),
        name: z.string(),
        mime_type: z.string(),
        content: z.string(),
        content_encoding: z.string()
      }),
      permissionScopes: ["external_api.read"],
      timeoutMs: 5_000,
      sideEffecting: false,
      enabled: true
    });
    registry.register({
      id: "mcp.gmail.create_draft_with_attachments",
      name: "Gmail Create Draft With Attachments",
      providerType: "mcp",
      inputSchema: z.object({
        to: z.string().min(1),
        subject: z.string().min(1),
        body: z.string().min(1),
        artifactIds: z.array(z.string().min(1)),
        metadata: z.record(z.string(), z.string()).optional()
      }),
      outputSchema: z.object({
        id: z.string(),
        status: z.string(),
        threadId: z.string(),
        echoedInput: z.record(z.string(), z.unknown()).optional()
      }),
      permissionScopes: ["artifact.read", "external_api.write"],
      timeoutMs: 5_000,
      sideEffecting: true,
      enabled: true
    });

    const orchestrator = new WorkflowOrchestrator(
      registry,
      new ToolEngine(
        {
          local: {
            async execute(tool: { id: string }, input: Record<string, unknown>) {
              if (tool.id === "save_artifact") {
                return {
                  artifact_id: "artifact_001",
                  display_name: "Quarterly Plan.pdf",
                  storage_file_name: "Quarterly-Plan.pdf",
                  summary: "Google Drive export: Quarterly Plan.pdf",
                  app_id: "app_001",
                  created_at: "2026-06-06T00:00:00.000Z",
                  created_by_execution_id: "execution_003",
                  source_tool_id: "save_artifact",
                  source_skill_id: "google_drive_download_file",
                  provider_origin: "local",
                  mime_type: "application/pdf",
                  size_bytes: 11,
                  path: "/tmp/artifact_001.json",
                  artifact_type: String(input.artifact_type),
                  status: "ready"
                };
              }

              throw new Error(`unexpected tool ${tool.id}`);
            }
          },
          mcp: {
            async execute(tool: { id: string }, input: Record<string, unknown>) {
              if (tool.id === "mcp.gdrive.download_file_content") {
                return {
                  file_id: "file-123",
                  name: "Quarterly Plan.pdf",
                  mime_type: "application/pdf",
                  content: "cGRmLWNvbnRlbnQ=",
                  content_encoding: "base64"
                };
              }

              if (tool.id === "mcp.gmail.create_draft_with_attachments") {
                return {
                  id: "draft_001",
                  status: "draft_created",
                  threadId: "thread_001",
                  echoedInput: input
                } as never;
              }

              throw new Error(`unexpected tool ${tool.id}`);
            }
          }
        } as never,
        new PermissionEngine([
          {
            appId: "app_001",
            toolId: "mcp.gdrive.download_file_content",
            scope: "external_api.read",
            mode: "auto_allow"
          },
          {
            appId: "app_001",
            toolId: "save_artifact",
            scope: "artifact.write",
            mode: "auto_allow"
          },
          {
            appId: "app_001",
            toolId: "mcp.gmail.create_draft_with_attachments",
            scope: "artifact.read",
            mode: "auto_allow"
          },
          {
            appId: "app_001",
            toolId: "mcp.gmail.create_draft_with_attachments",
            scope: "external_api.write",
            mode: "auto_allow"
          }
        ])
      )
    );

    const result = await orchestrator.execute({
      executionId: "execution_003",
      confirmed: false,
      executionOptions: { dry_run: false },
      toolDefinitions: [],
      stepOutputs: {},
      toolResults: {},
      errors: [],
      request: {
        request_type: "execute_skill",
        app_id: "app_001",
        session_id: "sess_001",
        skill_id: "drive_to_gmail_attachment_draft",
        input: {
          fileId: "file-123",
          to: "alice@example.com",
          subject: "Quarterly Plan",
          body: "Attached."
        }
      },
      skill: {
        id: "drive_to_gmail_attachment_draft",
        name: "Drive To Gmail Attachment Draft",
        version: "1.0.0",
        description: "tests nested workflow mapping",
        inputSchema: { parse: (value: unknown) => value } as never,
        outputSchema: { parse: (value: unknown) => value } as never,
        requiredTools: [
          "mcp.gdrive.download_file_content",
          "save_artifact",
          "mcp.gmail.create_draft_with_attachments"
        ],
        requiredPermissions: [
          "external_api.read",
          "artifact.write",
          "artifact.read",
          "external_api.write"
        ],
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
              on: { success: "create_draft_with_attachments" }
            },
            {
              id: "create_draft_with_attachments",
              type: "service_call",
              serviceId: "mcp.gmail.create_draft_with_attachments",
              inputMapping: {
                to: "$.input.to",
                subject: "$.input.subject",
                body: "$.input.body",
                artifactIds: ["$.steps.save_artifact.output.artifact_id"],
                metadata: {
                  source_file_id: "$.steps.save_artifact.output.file_id"
                }
              },
              outputMapping: {
                id: "$.output.id",
                status: "$.output.status",
                threadId: "$.output.threadId",
                artifact_id: "$.steps.save_artifact.output.artifact_id",
                file_id: "$.steps.save_artifact.output.file_id"
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
      }
    });

    assert.deepEqual(result, {
      id: "draft_001",
      status: "draft_created",
      threadId: "thread_001",
      artifact_id: "artifact_001",
      file_id: "file-123"
    });
  });
});
