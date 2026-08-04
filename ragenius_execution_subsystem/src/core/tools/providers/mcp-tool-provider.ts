import { z } from "zod";

import { AppError } from "../../errors/app-error.js";
import type {
  McpRuntimeConfig,
  McpServerRuntimeConfig
} from "../../../config/mcp-config.js";
import {
  buildDefaultRuntimePolicyConfig,
  type FallbackErrorClass,
  type RuntimePolicyConfig
} from "../../../config/policy-config.js";
import {
  toolExecutionProvenanceKey,
  type ToolDefinition,
  type ToolExecutionProvenance
} from "../tool.types.js";
import { ArtifactResolver } from "../../artifacts/artifact-resolver.js";

import type { ArtifactStore } from "./artifact-store.js";
import { GoogleRestFallbackProvider } from "./google-rest-fallback-provider.js";
import { McpHttpClient, type McpRemoteTool } from "./mcp-http-client.js";

const gmailSearchMessagesOutputSchema = z.object({
  results: z.array(
    z
      .object({
        id: z.string()
      })
      .passthrough()
  )
});

const gdocsSearchDocumentsOutputSchema = z.object({
  results: z.array(
    z
      .object({
        id: z.string(),
        title: z.string().optional()
      })
      .passthrough()
  )
});

const gdriveSearchFilesOutputSchema = z.object({
  results: z.array(
    z
      .object({
        id: z.string(),
        name: z.string().optional()
      })
      .passthrough()
  )
});

const gmailCreateDraftInputSchema = z.object({
  to: z.string().min(1),
  subject: z.string().min(1),
  body: z.string().min(1),
  artifactIds: z.array(z.string().min(1)).optional()
});

const gmailCreateDraftOutputSchema = z.object({
  id: z.string(),
  status: z.string(),
  threadId: z.string().optional()
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

const genericReadOutputSchema = z.object({
  results: z.array(z.object({}).passthrough())
});

const genericWriteOutputSchema = z.object({
  id: z.string(),
  title: z.string()
});

const genericQueryInputSchema = z.object({
  query: z.string().min(1)
});

const driveDownloadFileInputSchema = z.object({
  fileId: z.string().min(1)
});

const driveDownloadFileOutputSchema = z.object({
  file_id: z.string(),
  name: z.string(),
  mime_type: z.string(),
  content: z.string(),
  content_encoding: z.string().optional()
});

const genericTitleInputSchema = z.object({
  title: z.string().min(1)
});

function normalizeStringArray(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((entry) => String(entry).trim())
      .filter((entry) => entry.length > 0);
  }

  const text = String(value ?? "").trim();
  return text.length > 0 ? [text] : [];
}

function normalizeGmailToolInput(
  toolName: string,
  input: Record<string, unknown>
): Record<string, unknown> {
  if (toolName !== "create_draft" && toolName !== "send_message") {
    return input;
  }

  const normalized: Record<string, unknown> = { ...input };
  normalized.to = normalizeStringArray(input.to);

  if ("cc" in input) {
    normalized.cc = normalizeStringArray(input.cc);
  }
  if ("bcc" in input) {
    normalized.bcc = normalizeStringArray(input.bcc);
  }
  if ("html_body" in input && !("htmlBody" in input)) {
    normalized.htmlBody = input.html_body;
    delete normalized.html_body;
  }

  if (Array.isArray(input.attachments)) {
    normalized.attachments = input.attachments.map((attachment) => {
      if (!attachment || typeof attachment !== "object") {
        return attachment;
      }
      const source = attachment as Record<string, unknown>;
      const mapped: Record<string, unknown> = { ...source };
      if ("mime_type" in mapped && !("mimeType" in mapped)) {
        mapped.mimeType = mapped.mime_type;
        delete mapped.mime_type;
      }
      return mapped;
    });
  }

  return normalized;
}

function normalizeInputSchema(toolName: string): z.ZodType {
  if (toolName === "create_draft") {
    return gmailCreateDraftInputSchema;
  }

  if (toolName === "send_draft") {
    return gmailSendDraftInputSchema;
  }

  if (toolName === "send_message") {
    return gmailSendMessageInputSchema;
  }

  if (toolName === "download_file_content") {
    return driveDownloadFileInputSchema;
  }

  if (toolName.includes("search")) {
    return genericQueryInputSchema;
  }

  if (toolName.includes("create") || toolName.includes("draft")) {
    return genericTitleInputSchema;
  }

  return z.object({}).passthrough();
}

function normalizeOutputSchema(
  providerId: string,
  toolName: string
): z.ZodType {
  if (providerId === "gmail" && toolName === "search_messages") {
    return gmailSearchMessagesOutputSchema;
  }

  if (providerId === "gmail" && toolName === "create_draft") {
    return gmailCreateDraftOutputSchema;
  }

  if (providerId === "gmail" && toolName === "send_draft") {
    return gmailSendDraftOutputSchema;
  }

  if (providerId === "gmail" && toolName === "send_message") {
    return gmailSendMessageOutputSchema;
  }

  if (providerId === "gdocs" && toolName === "search_documents") {
    return gdocsSearchDocumentsOutputSchema;
  }

  if (providerId === "gdrive" && toolName === "search_files") {
    return gdriveSearchFilesOutputSchema;
  }

  if (providerId === "gdrive" && toolName === "download_file_content") {
    return driveDownloadFileOutputSchema;
  }

  if (toolName.includes("search") || toolName.includes("list") || toolName.includes("get")) {
    return genericReadOutputSchema;
  }

  return genericWriteOutputSchema;
}

function isSideEffecting(toolName: string): boolean {
  return (
    toolName.includes("create") ||
    toolName.includes("send") ||
    toolName.includes("update") ||
    toolName.includes("delete")
  );
}

function permissionScopesFor(toolName: string): string[] {
  return [isSideEffecting(toolName) ? "external_api.write" : "external_api.read"];
}

function mapRemoteTool(
  providerId: string,
  toolName: string,
  remoteTool?: McpRemoteTool,
  variant: "default" | "with_attachments" = "default",
  policy: RuntimePolicyConfig = buildDefaultRuntimePolicyConfig()
): ToolDefinition {
  const toolId =
    providerId === "gmail" &&
    toolName === "create_draft" &&
    variant === "with_attachments"
      ? "mcp.gmail.create_draft_with_attachments"
      : `mcp.${providerId}.${toolName}`;
  const toolPolicy = policy.tools[toolId];
  return {
    id: toolId,
    name: remoteTool?.title ?? remoteTool?.name ?? toolName,
    providerType: "mcp",
    inputSchema: normalizeInputSchema(toolName),
    outputSchema: normalizeOutputSchema(providerId, toolName),
    permissionScopes: toolPolicy?.permissionScopes ?? permissionScopesFor(toolName),
    sideEffecting: toolPolicy?.sideEffecting ?? isSideEffecting(toolName),
    timeoutMs: 10_000,
    enabled: true,
    metadata: {
      providerId,
      remoteToolName: remoteTool?.name ?? toolName,
      capabilityVariant: variant,
      remoteInputSchema: remoteTool?.inputSchema ?? null,
      remoteDescription: remoteTool?.description ?? null,
      remoteTitle: remoteTool?.title ?? null
    }
  };
}

function getAllowedToolNames(server: McpServerRuntimeConfig): string[] {
  if (server.allowedToolNames.length > 0) {
    return server.allowedToolNames;
  }

  if (server.id === "gmail") {
    return ["search_messages", "get_message", "get_thread", "list_labels"];
  }

  if (server.id === "gdocs") {
    return ["search_documents"];
  }

  if (server.id === "gdrive") {
    return ["search_files", "download_file_content"];
  }

  return [];
}

export interface McpDiscoveredTool {
  tool_id: string;
  name: string;
  permission_scopes: string[];
  side_effecting: boolean;
  input_schema: ReturnType<typeof z.object>;
  output_schema: ReturnType<typeof z.object>;
}

function findServer(
  config: McpRuntimeConfig,
  providerId: string
): McpServerRuntimeConfig | undefined {
  return config.servers.find(
    (server) => server.id === providerId && server.enabled
  );
}

function assertConfiguredServer(
  config: McpRuntimeConfig,
  providerId: string
): McpServerRuntimeConfig {
  const configured = findServer(config, providerId);
  if (!configured) {
    throw new AppError({
      code: "MCP_PROVIDER_NOT_FOUND",
      message: "MCP provider is not configured.",
      errorClass: "tool",
      httpStatus: 502,
      details: { provider_id: providerId },
      recoverable: false,
      suggestedAction: "Configure and enable the requested MCP provider."
    });
  }

  if (configured.authTokenEnv && !configured.authToken) {
    throw new AppError({
      code: "MCP_PROVIDER_AUTH_FAILED",
      message: "MCP provider authentication is missing.",
      errorClass: "tool",
      httpStatus: 502,
      details: { provider_id: providerId, auth_env: configured.authTokenEnv },
      recoverable: false,
      suggestedAction: "Set the configured MCP auth token environment variable."
    });
  }

  return configured;
}

export class McpToolProvider {
  readonly providerType = "mcp";

  constructor(
    private readonly config: McpRuntimeConfig = {
      servers: []
    },
    private readonly options: {
      artifactStore?: ArtifactStore;
      policy?: RuntimePolicyConfig;
      googleRestFallbackProvider?: GoogleRestFallbackProvider;
    } = {}
  ) {}

  async discover(providerId: string): Promise<ToolDefinition[]> {
    const configured = assertConfiguredServer(this.config, providerId);

    if (configured.transport !== "http") {
      return this.discoverFallback(providerId, configured.allowedToolNames);
    }

    const client = new McpHttpClient({
      baseUrl: configured.baseUrl,
      ...(configured.authToken ? { authToken: configured.authToken } : {})
    });
    await client.initialize();
    const remoteTools = await client.listTools();
    const allowlist = getAllowedToolNames(configured);

    const discovered = remoteTools.filter((tool) =>
      allowlist.length === 0 ? true : allowlist.includes(tool.name)
    );

    return discovered.flatMap((tool) => {
      const mapped = [
        mapRemoteTool(providerId, tool.name, tool, "default", this.policy)
      ];
      if (providerId === "gmail" && tool.name === "create_draft") {
        mapped.push(
          mapRemoteTool(
            providerId,
            tool.name,
            tool,
            "with_attachments",
            this.policy
          )
        );
      }
      return mapped;
    });
  }

  async execute(
    tool: ToolDefinition,
    input: Record<string, unknown>,
    options?: {
      appId: string;
      sessionId?: string;
      confirmed?: boolean;
      executionId?: string | null;
      skillId?: string;
    }
  ): Promise<Record<string, unknown>> {
    const providerId = String(tool.metadata?.providerId ?? "");
    const configured = assertConfiguredServer(this.config, providerId);
    const remoteToolName = String(tool.metadata?.remoteToolName ?? tool.id.split(".").pop() ?? "");

    const allowlist = getAllowedToolNames(configured);
    if (allowlist.length > 0 && !allowlist.includes(remoteToolName)) {
      throw new AppError({
        code: "MCP_TOOL_NOT_ALLOWED",
        message: "The requested MCP tool is not allowlisted.",
        errorClass: "tool",
        httpStatus: 403,
        details: { provider_id: providerId, tool_name: remoteToolName },
        recoverable: false,
        suggestedAction: "Use an allowlisted MCP tool or update the runtime allowlist."
      });
    }

    if (configured.transport !== "http") {
      return this.executeFallback(tool, input, providerId);
    }

    const client = new McpHttpClient({
      baseUrl: configured.baseUrl,
      ...(configured.authToken ? { authToken: configured.authToken } : {})
    });
    await client.initialize();
    const remoteInput =
      tool.id === "mcp.gmail.create_draft_with_attachments"
        ? await this.buildAttachmentAwareDraftInput(input, options?.appId ?? "")
        : input;
    const normalizedRemoteInput = normalizeGmailToolInput(
      remoteToolName,
      remoteInput
    );
    try {
      const output = await client.callTool(remoteToolName, normalizedRemoteInput);
      return this.attachExecutionProvenance(output, {
        execution_path: "mcp",
        tool_id: tool.id,
        provider_type: "mcp",
        provider_id: providerId,
        remote_tool_name: remoteToolName
      });
    } catch (error) {
      const driveFallbackClass =
        providerId === "gdrive" && remoteToolName === "download_file_content"
          ? this.classifyDriveFallback(error)
          : null;
      if (
        driveFallbackClass &&
        this.isFallbackEnabled(tool.id, driveFallbackClass)
      ) {
        const output = await this.googleRestFallbackProvider.downloadDriveFileContent(
          configured,
          normalizedRemoteInput
        );
        const authContext = this.extractAuthContext(output);
        return this.attachExecutionProvenance(output, {
          execution_path: "rest_fallback",
          tool_id: tool.id,
          provider_type: "mcp",
          provider_id: providerId,
          remote_tool_name: remoteToolName,
          fallback_used: true,
          fallback_reason: "mcp_permission_rejected",
          ...(authContext ? { auth_context: authContext } : {})
        });
      }
      const gmailFallbackClass =
        providerId === "gmail" && remoteToolName === "create_draft"
          ? this.classifyGmailFallback(error)
          : null;
      if (
        gmailFallbackClass &&
        this.isFallbackEnabled(tool.id, gmailFallbackClass)
      ) {
        const output = await this.googleRestFallbackProvider.createGmailDraft(
          configured,
          normalizedRemoteInput
        );
        const authContext = this.extractAuthContext(output);
        return this.attachExecutionProvenance(output, {
          execution_path: "rest_fallback",
          tool_id: tool.id,
          provider_type: "mcp",
          provider_id: providerId,
          remote_tool_name: remoteToolName,
          fallback_used: true,
          fallback_reason: "mcp_permission_rejected",
          ...(authContext ? { auth_context: authContext } : {})
        });
      }
      throw error;
    }
  }

  private discoverFallback(
    providerId: string,
    allowedToolNames: string[]
  ): ToolDefinition[] {
    const fallbackTools = [
      mapRemoteTool(providerId, "search_pages", {
        name: "search_pages",
        title: "Search Pages"
      }),
      mapRemoteTool(providerId, "create_page", {
        name: "create_page",
        title: "Create Page"
      })
    ];

    if (allowedToolNames.length === 0) {
      return fallbackTools;
    }

    return fallbackTools.filter((tool) =>
      allowedToolNames.includes(String(tool.metadata?.remoteToolName ?? ""))
    );
  }

  private executeFallback(
    tool: ToolDefinition,
    input: Record<string, unknown>,
    providerId: string
  ): Record<string, unknown> {
    if (tool.id === `mcp.${providerId}.search_pages`) {
      return {
        results: [
          {
            id: "page_1",
            title: "Homepage"
          }
        ]
      };
    }

    if (tool.id === `mcp.${providerId}.create_page`) {
      return {
        id: "page_created_1",
        title: String(input.title ?? "")
      };
    }

    throw new AppError({
      code: "MCP_TOOL_NOT_IMPLEMENTED",
      message: "MCP tool execution is not implemented.",
      errorClass: "tool",
      httpStatus: 502,
      details: { tool_id: tool.id, provider_id: providerId },
      recoverable: false,
      suggestedAction: "Register an executable MCP tool handler."
    });
  }

  private get policy(): RuntimePolicyConfig {
    return this.options.policy ?? buildDefaultRuntimePolicyConfig();
  }

  private get googleRestFallbackProvider(): GoogleRestFallbackProvider {
    return this.options.googleRestFallbackProvider ?? new GoogleRestFallbackProvider();
  }

  private async buildAttachmentAwareDraftInput(
    input: Record<string, unknown>,
    appId: string
  ): Promise<Record<string, unknown>> {
    const artifactIds = Array.isArray(input.artifactIds)
      ? input.artifactIds.map((value) => String(value))
      : [];
    if (artifactIds.length === 0) {
      throw new AppError({
        code: "ATTACHMENT_SOURCE_INVALID",
        message: "Attachment-capable Gmail drafts require artifact ids.",
        errorClass: "validation",
        httpStatus: 400,
        recoverable: true,
        suggestedAction: "Provide one or more app-scoped artifact ids."
      });
    }
    if (!this.options.artifactStore) {
      throw new AppError({
        code: "ARTIFACT_STORE_UNAVAILABLE",
        message: "Artifact storage is not configured for attachment-capable Gmail drafts.",
        errorClass: "tool",
        httpStatus: 500,
        recoverable: false,
        suggestedAction: "Configure artifact storage before using attachment-capable Gmail drafts."
      });
    }
    if (artifactIds.length > this.policy.attachments.maxAttachmentCount) {
      throw new AppError({
        code: "ATTACHMENT_POLICY_VIOLATION",
        message: "Too many attachments were supplied.",
        errorClass: "validation",
        httpStatus: 400,
        details: {
          max_attachment_count: this.policy.attachments.maxAttachmentCount
        },
        recoverable: true,
        suggestedAction: "Reduce the number of attachments."
      });
    }

    const attachments: Array<Record<string, unknown>> = [];
    let totalBytes = 0;
    const artifactResolver = new ArtifactResolver(this.options.artifactStore);
    for (const artifactId of artifactIds) {
      const artifact = await artifactResolver.resolve(appId, artifactId, {
        requiredMode: "binary_payload"
      });
      if (
        !this.policy.attachments.allowedArtifactTypes.includes(artifact.artifact_type)
      ) {
        throw new AppError({
          code: "ATTACHMENT_POLICY_VIOLATION",
          message: "Artifact type is not allowed for outbound attachments.",
          errorClass: "validation",
          httpStatus: 400,
          details: { artifact_id: artifactId, artifact_type: artifact.artifact_type },
          recoverable: true,
          suggestedAction: "Use an allowed artifact type."
        });
      }

      const mimeType = String(artifact.payload.mime_type ?? "");
      if (!this.policy.attachments.allowedMimeTypes.includes(mimeType)) {
        throw new AppError({
          code: "ATTACHMENT_POLICY_VIOLATION",
          message: "Attachment MIME type is not allowed.",
          errorClass: "validation",
          httpStatus: 400,
          details: { artifact_id: artifactId, mime_type: mimeType },
          recoverable: true,
          suggestedAction: "Use an allowed attachment MIME type."
        });
      }

      const encodedContent = String(artifact.payload.binary_content_base64 ?? "");
      const byteLength = Buffer.from(encodedContent, "base64").byteLength;
      totalBytes += byteLength;
      if (totalBytes > this.policy.attachments.maxAttachmentBytes) {
        throw new AppError({
          code: "ATTACHMENT_POLICY_VIOLATION",
          message: "Total attachment size exceeds policy.",
          errorClass: "validation",
          httpStatus: 400,
          details: {
            max_attachment_bytes: this.policy.attachments.maxAttachmentBytes
          },
          recoverable: true,
          suggestedAction: "Use fewer or smaller attachments."
        });
      }

      attachments.push({
        filename: String(artifact.payload.metadata.name ?? artifact.display_name ?? artifactId),
        mimeType,
        content: encodedContent
      });
    }

    return {
      to: input.to,
      subject: input.subject,
      body: input.body,
      attachments
    };
  }

  private isFallbackEnabled(
    toolId: string,
    errorClass: FallbackErrorClass
  ): boolean {
    const policy = this.policy.fallbacks.tools[toolId];
    if (!policy || !policy.enabled) {
      return false;
    }
    return policy.allowedErrorClasses.includes(errorClass);
  }

  private classifyDriveFallback(error: unknown): FallbackErrorClass | null {
    if (!(error instanceof AppError) || error.code !== "MCP_TOOL_CALL_FAILED") {
      return null;
    }

    const result = (error.details as { result?: unknown })?.result;
    if (!Array.isArray(result)) {
      return null;
    }

    return result.some((entry) =>
      String((entry as { text?: unknown })?.text ?? "")
        .toLowerCase()
        .includes("does not have permission")
    )
      ? "permission_rejected"
      : null;
  }

  private classifyGmailFallback(error: unknown): FallbackErrorClass | null {
    if (!(error instanceof AppError) || error.code !== "MCP_TOOL_CALL_FAILED") {
      return null;
    }

    const result = (error.details as { result?: unknown })?.result;
    if (!Array.isArray(result)) {
      return null;
    }

    return result.some((entry) =>
      String((entry as { text?: unknown })?.text ?? "")
        .toLowerCase()
        .includes("does not have permission")
    )
      ? "permission_rejected"
      : null;
  }

  private attachExecutionProvenance(
    output: Record<string, unknown>,
    provenance: ToolExecutionProvenance
  ): Record<string, unknown> {
    const enrichedOutput = {
      ...output,
    };
    Object.defineProperty(enrichedOutput, toolExecutionProvenanceKey, {
      value: provenance,
      enumerable: false,
      configurable: true,
      writable: true,
    });
    return enrichedOutput;
  }

  private extractAuthContext(
    output: Record<string, unknown>
  ): Record<string, unknown> | undefined {
    const authContext = output.auth_context;
    return typeof authContext === "object" &&
      authContext !== null &&
      !Array.isArray(authContext)
      ? (authContext as Record<string, unknown>)
      : undefined;
  }
}

export const MockMcpToolProvider = McpToolProvider;
