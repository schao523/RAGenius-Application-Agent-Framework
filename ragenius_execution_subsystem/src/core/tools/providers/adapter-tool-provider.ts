import { AppError } from "../../errors/app-error.js";
import type { ToolDefinition } from "../tool.types.js";
import { NotebookLmAdapter } from "./notebooklm-adapter.js";
import type { NotebookLmOperation } from "./notebooklm-types.js";

export interface AdapterRuntimeTool {
  id: string;
  command?: string | undefined;
  args: string[];
  enabled: boolean;
}

export interface AdapterRuntimeConfig {
  tools: AdapterRuntimeTool[];
}

export interface AdapterToolProviderDependencies {
  notebooklmAdapter?: NotebookLmAdapter;
}

export class AdapterToolProvider {
  readonly providerType = "adapter" as const;

  constructor(
    private readonly config: AdapterRuntimeConfig = { tools: [] },
    private readonly dependencies: AdapterToolProviderDependencies = {}
  ) {}

  async execute(
    tool: ToolDefinition,
    input: Record<string, unknown>,
    _options?: { appId: string; sessionId?: string; confirmed?: boolean; executionId?: string | null; skillId?: string }
  ): Promise<Record<string, unknown>> {
    const adapter = this.config.tools.find(
      (entry) => entry.id === tool.id && entry.enabled
    );

    if (!adapter) {
      throw new AppError({
        code: "ADAPTER_NOT_ALLOWED",
        message: "Adapter tool is not allowlisted.",
        errorClass: "permission",
        httpStatus: 403,
        details: { tool_id: tool.id },
        recoverable: false,
        suggestedAction: "Use a configured adapter tool."
      });
    }

    if (tool.id.startsWith("adapter.notebooklm.")) {
      if (!this.dependencies.notebooklmAdapter) {
        throw new AppError({
          code: "ADAPTER_NOT_IMPLEMENTED",
          message: "NotebookLM adapter is not configured.",
          errorClass: "tool",
          httpStatus: 502,
          details: { tool_id: tool.id, command: adapter.command },
          recoverable: false,
          suggestedAction: "Configure the NotebookLM adapter."
        });
      }

      const operation = tool.id.replace(
        "adapter.notebooklm.",
        ""
      ) as NotebookLmOperation;
      return this.dependencies.notebooklmAdapter.execute(
        operation,
        input,
        _options
      );
    }

    if (tool.id === "content_transform_adapter") {
      return {
        output: String(input.content ?? "").toUpperCase()
      };
    }

    if (tool.id === "site_build_adapter") {
      return {
        output: `build:${String(input.path ?? "")}`
      };
    }

    throw new AppError({
      code: "ADAPTER_NOT_IMPLEMENTED",
      message: "Adapter tool is not implemented.",
      errorClass: "tool",
      httpStatus: 502,
      details: { tool_id: tool.id, command: adapter.command },
      recoverable: false,
      suggestedAction: "Register an implemented adapter handler."
    });
  }
}
