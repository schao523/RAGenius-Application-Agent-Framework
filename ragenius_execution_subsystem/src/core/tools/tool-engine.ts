import { getEnv } from "../../config/env.js";
import {
  buildAdapterRuntimeConfig,
  buildProviderRuntimeConfig
} from "../../config/provider-config.js";
import { AppError } from "../errors/app-error.js";
import { PermissionEngine } from "../permissions/permission-engine.js";
import type { PermissionPolicy } from "../permissions/permission.types.js";

import { MockApiToolProvider } from "./providers/api-tool-provider.js";
import { AdapterToolProvider } from "./providers/adapter-tool-provider.js";
import { MockMcpToolProvider } from "./providers/mcp-tool-provider.js";
import { NotebookLmAdapter } from "./providers/notebooklm-adapter.js";
import { MockRagAdapterProvider } from "./providers/rag-adapter-provider.js";
import {
  toolExecutionProvenanceKey,
  type ToolDefinition,
  type ToolExecutionProvenance,
  type ToolProviderType
} from "./tool.types.js";

type ToolProvider = {
  execute?: (
    tool: ToolDefinition,
    input: Record<string, unknown>,
    options?: {
      appId: string;
      sessionId?: string;
      confirmed?: boolean;
      executionId?: string | null;
      skillId?: string;
    }
  ) => Promise<Record<string, unknown>>;
  discover?: (providerId: string) => Promise<ToolDefinition[]>;
};

export class ToolEngine {
  private readonly providers: Partial<Record<ToolProviderType, ToolProvider>>;
  private readonly permissionEngine: PermissionEngine;

  constructor(
    providers: Partial<Record<ToolProviderType, ToolProvider>> = {},
    permissionEngine: PermissionEngine = new PermissionEngine()
  ) {
    const providerRuntimeConfig = buildProviderRuntimeConfig(getEnv());
    this.providers = {
      api: new MockApiToolProvider(providerRuntimeConfig),
      adapter: new AdapterToolProvider(buildAdapterRuntimeConfig(getEnv()), {
        notebooklmAdapter: new NotebookLmAdapter(providerRuntimeConfig.notebooklm)
      }),
      mcp: new MockMcpToolProvider(),
      rag_adapter: new MockRagAdapterProvider(),
      ...providers
    };
    this.permissionEngine = permissionEngine;
  }

  async execute(
    tool: ToolDefinition,
    input: Record<string, unknown>,
    options: {
      appId: string;
      sessionId?: string;
      confirmed?: boolean;
      executionId?: string | null;
      skillId?: string;
      permissionPolicies?: PermissionPolicy[] | undefined;
    }
  ): Promise<Record<string, unknown>> {
    const parsedInput = tool.inputSchema.safeParse(input);
    if (!parsedInput.success) {
      const issue = parsedInput.error.issues[0];
      throw new AppError({
        code: "VALIDATION_ERROR",
        message: "Tool input does not match schema.",
        errorClass: "validation",
        httpStatus: 400,
        details: issue
          ? {
              path: issue.path.join("."),
              issue: issue.message
            }
          : undefined,
        recoverable: true,
        suggestedAction: "Provide valid tool input."
      });
    }

    if (options.confirmed !== true) {
      this.permissionEngine.assertAllowed(
        options.appId,
        tool,
        parsedInput.data,
        options.permissionPolicies
      );
    }

    const provider = this.providers[tool.providerType];
    if (!provider?.execute) {
      throw new AppError({
        code: "TOOL_PROVIDER_NOT_FOUND",
        message: "Tool provider is not registered.",
        errorClass: "tool",
        httpStatus: 502,
        details: { provider_type: tool.providerType },
        recoverable: false,
        suggestedAction: "Register the required provider."
      });
    }

    const timeoutMs = tool.timeoutMs ?? 30_000;

    let output: Record<string, unknown>;
    let timeoutHandle: NodeJS.Timeout | undefined;
    try {
      output = await Promise.race([
        provider.execute(tool, parsedInput.data, options),
        new Promise<Record<string, unknown>>((_, reject) => {
          timeoutHandle = setTimeout(() => {
            reject(
              new AppError({
                code: "TOOL_TIMEOUT",
                message: "Tool execution timed out.",
                errorClass: "timeout",
                httpStatus: 504,
                details: { tool_id: tool.id, timeout_ms: timeoutMs },
                recoverable: true,
                suggestedAction: "Retry later or increase timeout."
              })
            );
          }, timeoutMs);
        })
      ]);
    } catch (error) {
      if (error instanceof AppError) {
        throw error;
      }

      throw new AppError({
        code: "TOOL_EXECUTION_FAILED",
        message: "Tool execution failed.",
        errorClass: "tool",
        httpStatus: 502,
        details: { tool_id: tool.id },
        recoverable: true,
        suggestedAction: "Retry later or inspect the provider."
      });
    } finally {
      if (timeoutHandle) {
        clearTimeout(timeoutHandle);
      }
    }

    const provenance: ToolExecutionProvenance | undefined =
      this.extractExecutionProvenance(tool, output);

    const parsedOutput = tool.outputSchema.safeParse(output);
    if (!parsedOutput.success) {
      const issue = parsedOutput.error.issues[0];
      throw new AppError({
        code: "TOOL_OUTPUT_INVALID",
        message: "Tool output does not match schema.",
        errorClass: "tool",
        httpStatus: 502,
        details: issue
          ? {
              path: issue.path.join("."),
              issue: issue.message
            }
          : undefined,
        recoverable: false,
        suggestedAction: "Fix the provider output contract."
      });
    }
    if (provenance) {
      Object.defineProperty(parsedOutput.data, toolExecutionProvenanceKey, {
        configurable: true,
        enumerable: false,
        value: provenance,
        writable: false
      });
    }

    return parsedOutput.data;
  }

  async discoverMcpTools(providerId: string): Promise<ToolDefinition[]> {
    const provider = this.providers.mcp;
    if (!provider?.discover) {
      throw new AppError({
        code: "MCP_PROVIDER_NOT_FOUND",
        message: "MCP discovery provider is not registered.",
        errorClass: "tool",
        httpStatus: 502,
        details: { provider_id: providerId },
        recoverable: false,
        suggestedAction: "Register an MCP discovery provider."
      });
    }

    return provider.discover(providerId);
  }

  private extractExecutionProvenance(
    tool: ToolDefinition,
    output: Record<string, unknown>
  ): ToolExecutionProvenance {
    const providerProvenance = output[
      toolExecutionProvenanceKey
    ] as ToolExecutionProvenance | undefined;
    if (providerProvenance) {
      return {
        ...providerProvenance,
        tool_id: tool.id,
        provider_type: tool.providerType
      };
    }

    return {
      execution_path: tool.providerType,
      tool_id: tool.id,
      provider_type: tool.providerType,
      ...(tool.metadata?.providerId
        ? { provider_id: String(tool.metadata.providerId) }
        : {}),
      ...(tool.metadata?.remoteToolName
        ? { remote_tool_name: String(tool.metadata.remoteToolName) }
        : {})
    };
  }
}
