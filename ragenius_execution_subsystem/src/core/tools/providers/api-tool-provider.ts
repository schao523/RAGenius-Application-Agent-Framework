import { AppError } from "../../errors/app-error.js";
import type { ProviderRuntimeConfig } from "../../../config/provider-config.js";
import type { ToolDefinition } from "../tool.types.js";

import { ResearchPaperProvider } from "./research-paper-provider.js";

export interface ApiToolProvider {
  providerType: "api";
  execute(
    tool: ToolDefinition,
    input: Record<string, unknown>,
    options?: {
      appId: string;
      sessionId?: string;
      confirmed?: boolean;
      executionId?: string | null;
      skillId?: string;
    }
  ): Promise<Record<string, unknown>>;
}

export class MockApiToolProvider implements ApiToolProvider {
  readonly providerType = "api";
  private readonly researchPaperProvider: ResearchPaperProvider;

  constructor(
    config: ProviderRuntimeConfig = {
      codexAppServer: {
        authHandoffEnabled: false,
        enabled: false,
        command: "codex",
        initializationTimeoutMs: 15000,
        interactionTtlMs: 900000,
        managedAuthTargets: [],
        maxDeltaBytes: 16384,
        maxLineBytes: 1048576,
        maxStderrBytes: 65536,
        mcpAuthAllowedHosts: [],
        mcpElicitationEnabled: false,
        runRoot: "storage/codex-runs",
        supportedVersions: ["0.146.0"],
        userActionEnabled: false
      },
      codexCli: {
        enabled: false,
        nodeCommand: "node",
        bridgeScript: "scripts/codex_cli_bridge.js",
        command: "codex",
        args: [],
        timeoutMs: 120000
      },
      openClaw: {
        enabled: false,
        wslDistro: "OpenClawGateway",
        command: "openclaw",
        agentId: "main",
        workspaceRoot: "/home/openclaw/.openclaw/workspace",
        timeoutMs: 120000,
        maxStdoutBytes: 262144,
        maxStderrBytes: 65536,
        runRetentionHours: 24
      },
      openClawGateway: {
        agentId: "main",
        chatLevelEnabled: false,
        chatIdleTtlMs: 900000,
        credentialEnv: "OPENCLAW_GATEWAY_APPROVAL_TOKEN",
        enabled: false,
        gatewayUrl: "ws://127.0.0.1:18789",
        interactionTtlMs: 900000,
        maxMessageBytes: 1048576,
        reconnectBaseDelayMs: 250,
        reconnectMaxAttempts: 5,
        rpcTimeoutMs: 15000,
        supportedVersions: ["2026.6.8"],
        workspaceRoot: "/home/openclaw/.openclaw/workspace",
        wslDistro: "OpenClawGateway"
      },
      notebooklm: {
        enabled: false,
        pythonCommand: "python",
        bridgeScript: "scripts/notebooklm_bridge.py",
        authMode: "env_json",
        allowedOperations: [],
        generationDefaults: {
          waitForCompletion: true,
          persistArtifacts: true
        }
      },
      researchPaper: {
        arxiv: {
          enabled: true,
          requestTimeoutMs: 4000,
          retryOn429: true,
          maxRetries: 1
        },
        semanticScholar: {
          enabled: true,
          requestTimeoutMs: 4000,
          maxResultsDefault: 5
        }
      },
      openAi: {
        enabled: false
      }
    }
  ) {
    this.researchPaperProvider = new ResearchPaperProvider(config.researchPaper);
  }

  async execute(
    tool: ToolDefinition,
    input: Record<string, unknown>,
    _options?: {
      appId: string;
      sessionId?: string;
      confirmed?: boolean;
      executionId?: string | null;
      skillId?: string;
    }
  ): Promise<Record<string, unknown>> {
    if (tool.id === "research_paper_search_tool") {
      return this.researchPaperProvider.search({
        topic: String(input.topic ?? "").trim(),
        limit: typeof input.limit === "number" ? input.limit : 5,
        source: String(input.source ?? "auto") as
          | "auto"
          | "arxiv"
          | "semantic-scholar"
      });
    }

    if (tool.id !== "mock_video_generation_tool") {
      throw new AppError({
        code: "TOOL_PROVIDER_NOT_IMPLEMENTED",
        message: "The requested API tool is not implemented.",
        errorClass: "tool",
        httpStatus: 502,
        details: { tool_id: tool.id },
        recoverable: false,
        suggestedAction: "Register a supported API tool."
      });
    }

    const prompt = input.prompt;
    const duration = input.duration;

    if (prompt === "timeout") {
      await new Promise((resolve) => setTimeout(resolve, 25));
    }

    if (prompt === "provider-failure") {
      throw new AppError({
        code: "VIDEO_PROVIDER_FAILED",
        message: "Mock video provider failed.",
        errorClass: "tool",
        httpStatus: 502,
        details: { tool_id: tool.id },
        recoverable: true,
        suggestedAction: "Retry later or switch providers."
      });
    }

    return {
      title: `Video: ${String(prompt)}`,
      summary: `Generated ${String(duration)} second explainer video.`,
      file_id: "file_mock_video_001"
    };
  }
}
