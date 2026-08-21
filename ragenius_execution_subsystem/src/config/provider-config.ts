import { z } from "zod";

import type { AppEnv } from "./env.js";

export interface BuilderRuntimeConfig {
  baseUrl?: string;
}

export interface NetworkRuntimeConfig {
  httpProxy?: string;
  httpsProxy?: string;
  allProxy?: string;
  noProxy?: string;
  extraCaCertsPath?: string;
}

export interface FileToolRuntimeConfig {
  allowedRoots: string[];
  mutationRoots: string[];
  maxReadBytes: number;
  maxWriteBytes: number;
  maxPatchBytes: number;
}

export interface ArtifactStoreRuntimeConfig {
  rootDir: string;
}

export interface AdapterRuntimeToolConfig {
  id: string;
  command?: string | undefined;
  args: string[];
  enabled: boolean;
}

export interface AdapterRuntimeConfig {
  tools: AdapterRuntimeToolConfig[];
}

export interface ArxivProviderConfig {
  enabled: boolean;
  requestTimeoutMs: number;
  retryOn429: boolean;
  maxRetries: number;
}

export interface SemanticScholarProviderConfig {
  enabled: boolean;
  apiKey?: string;
  requestTimeoutMs: number;
  maxResultsDefault: number;
}

export interface OpenAiProviderConfig {
  enabled: boolean;
  apiKey?: string;
  baseUrl?: string;
  defaultModel?: string;
}

export interface NotebookLmProviderConfig {
  enabled: boolean;
  pythonCommand: string;
  bridgeScript: string;
  authMode: "env_json" | "profile" | "storage_path";
  profile?: string;
  storagePath?: string;
  allowedOperations: string[];
  generationDefaults: {
    waitForCompletion: boolean;
    persistArtifacts: boolean;
  };
}

export interface CodexCliProviderConfig {
  enabled: boolean;
  nodeCommand: string;
  bridgeScript: string;
  command: string;
  args: string[];
  timeoutMs: number;
  runRoot?: string;
  runRetentionHours?: number;
  maxOutputBytes?: number;
  sandboxMode?: "read-only" | "workspace-write";
}

export interface CodexAppServerProviderConfig {
  enabled: boolean;
  command: string;
  initializationTimeoutMs: number;
  interactionTtlMs: number;
  maxDeltaBytes: number;
  maxLineBytes: number;
  maxStderrBytes: number;
  runRoot: string;
  supportedVersions: string[];
}

export interface OpenClawCliRuntimeConfig {
  enabled: boolean;
  wslDistro: string;
  command: string;
  agentId: string;
  workspaceRoot: string;
  timeoutMs: number;
  maxStdoutBytes: number;
  maxStderrBytes: number;
  runRetentionHours: number;
}

export interface OpenClawGatewayProviderConfig {
  agentId: string;
  chatLevelEnabled: boolean;
  credential?: string;
  credentialEnv: string;
  enabled: boolean;
  gatewayUrl: string;
  interactionTtlMs: number;
  maxMessageBytes: number;
  reconnectBaseDelayMs: number;
  reconnectMaxAttempts: number;
  rpcTimeoutMs: number;
  supportedVersions: string[];
  workspaceRoot: string;
  wslDistro: string;
}

export interface ResearchPaperProviderConfig {
  arxiv: ArxivProviderConfig;
  semanticScholar: SemanticScholarProviderConfig;
}

export interface ProviderRuntimeConfig {
  codexAppServer: CodexAppServerProviderConfig;
  codexCli: CodexCliProviderConfig;
  notebooklm: NotebookLmProviderConfig;
  openClaw: OpenClawCliRuntimeConfig;
  openClawGateway: OpenClawGatewayProviderConfig;
  researchPaper: ResearchPaperProviderConfig;
  openAi: OpenAiProviderConfig;
}

export interface ToolToggleRuntimeConfig {
  researchPaperSearch: { enabled: boolean };
  ragRetrieval: { enabled: boolean };
  openAiAnswer: { enabled: boolean };
}

const adapterSchema = z.array(
  z
    .object({
      id: z.string().min(1),
      command: z.string().min(1).optional(),
      args: z.array(z.string()).default([]),
      enabled: z.boolean().default(true)
    })
    .superRefine((value, ctx) => {
      if (value.id.startsWith("adapter.notebooklm.")) {
        return;
      }
      if (typeof value.command === "string" && value.command.length > 0) {
        return;
      }
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["command"],
        message: "Required"
      });
    })
);

const splitCsv = (value: string): string[] =>
  value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);

export function buildBuilderRuntimeConfig(env: AppEnv): BuilderRuntimeConfig {
  return env.BUILDER_BASE_URL
    ? {
        baseUrl: env.BUILDER_BASE_URL
      }
    : {};
}

export function buildNetworkRuntimeConfig(env: AppEnv): NetworkRuntimeConfig {
  return {
    ...(env.HTTP_PROXY ? { httpProxy: env.HTTP_PROXY } : {}),
    ...(env.HTTPS_PROXY ? { httpsProxy: env.HTTPS_PROXY } : {}),
    ...(env.ALL_PROXY ? { allProxy: env.ALL_PROXY } : {}),
    ...(env.NO_PROXY ? { noProxy: env.NO_PROXY } : {}),
    ...(env.NODE_EXTRA_CA_CERTS
      ? { extraCaCertsPath: env.NODE_EXTRA_CA_CERTS }
      : {})
  };
}

export function buildFileToolRuntimeConfig(
  env: AppEnv
): FileToolRuntimeConfig {
  return {
    allowedRoots: splitCsv(env.FILESYSTEM_ALLOWED_ROOTS),
    mutationRoots: splitCsv(env.FILESYSTEM_MUTATION_ROOTS),
    maxReadBytes: env.FILESYSTEM_MAX_READ_BYTES,
    maxWriteBytes: env.FILESYSTEM_MAX_WRITE_BYTES,
    maxPatchBytes: env.FILESYSTEM_MAX_PATCH_BYTES
  };
}

export function buildArtifactStoreRuntimeConfig(
  env: AppEnv
): ArtifactStoreRuntimeConfig {
  return {
    rootDir: env.ARTIFACT_STORAGE_ROOT
  };
}

export function buildAdapterRuntimeConfig(
  env: AppEnv
): AdapterRuntimeConfig {
  const parsed = adapterSchema.parse(JSON.parse(env.ADAPTERS_JSON));
  return {
    tools: parsed.map((tool) => ({
      id: tool.id,
      ...(tool.command ? { command: tool.command } : {}),
      args: tool.args,
      enabled: tool.enabled
    }))
  };
}

export function buildProviderRuntimeConfig(
  env: AppEnv,
  source: NodeJS.ProcessEnv = process.env
): ProviderRuntimeConfig {
  return {
    codexAppServer: {
      enabled: env.CODEX_APP_SERVER_INTERACTIVE_ENABLED,
      command: env.CODEX_APP_SERVER_COMMAND,
      initializationTimeoutMs: env.CODEX_APP_SERVER_INITIALIZATION_TIMEOUT_MS,
      interactionTtlMs: env.CODEX_APP_SERVER_INTERACTION_TTL_MS,
      maxDeltaBytes: env.CODEX_APP_SERVER_MAX_DELTA_BYTES,
      maxLineBytes: env.CODEX_APP_SERVER_MAX_LINE_BYTES,
      maxStderrBytes: env.CODEX_APP_SERVER_MAX_STDERR_BYTES,
      runRoot: env.CODEX_RUN_ROOT,
      supportedVersions: splitCsv(env.CODEX_APP_SERVER_SUPPORTED_VERSIONS)
    },
    codexCli: {
      enabled: env.CODEX_CLI_ENABLED,
      nodeCommand: env.CODEX_CLI_NODE_COMMAND,
      bridgeScript: env.CODEX_CLI_BRIDGE_SCRIPT,
      command: env.CODEX_CLI_COMMAND,
      args: z.array(z.string()).parse(JSON.parse(env.CODEX_CLI_ARGS_JSON)),
      timeoutMs: env.CODEX_CLI_TIMEOUT_MS,
      runRoot: env.CODEX_RUN_ROOT,
      runRetentionHours: env.CODEX_RUN_RETENTION_HOURS,
      maxOutputBytes: env.CODEX_MAX_OUTPUT_BYTES,
      sandboxMode: env.CODEX_CLI_SANDBOX_MODE
    },
    openClaw: {
      enabled: env.OPENCLAW_CLI_ENABLED,
      wslDistro: env.OPENCLAW_WSL_DISTRO,
      command: env.OPENCLAW_CLI_COMMAND,
      agentId: env.OPENCLAW_AGENT_ID,
      workspaceRoot: env.OPENCLAW_WORKSPACE_ROOT,
      timeoutMs: env.OPENCLAW_DEFAULT_TIMEOUT_MS,
      maxStdoutBytes: env.OPENCLAW_MAX_STDOUT_BYTES,
      maxStderrBytes: env.OPENCLAW_MAX_STDERR_BYTES,
      runRetentionHours: env.OPENCLAW_RUN_RETENTION_HOURS
    },
    openClawGateway: {
      agentId: env.OPENCLAW_AGENT_ID,
      chatLevelEnabled: env.OPENCLAW_GATEWAY_CHAT_LEVEL_ENABLED,
      credentialEnv: env.OPENCLAW_GATEWAY_APPROVAL_CREDENTIAL_ENV,
      ...(source[env.OPENCLAW_GATEWAY_APPROVAL_CREDENTIAL_ENV]?.trim()
        ? { credential: source[env.OPENCLAW_GATEWAY_APPROVAL_CREDENTIAL_ENV]!.trim() }
        : {}),
      enabled: env.OPENCLAW_GATEWAY_INTERACTIVE_ENABLED,
      gatewayUrl: env.OPENCLAW_GATEWAY_URL,
      interactionTtlMs: env.OPENCLAW_GATEWAY_INTERACTION_TTL_MS,
      maxMessageBytes: env.OPENCLAW_GATEWAY_MAX_MESSAGE_BYTES,
      reconnectBaseDelayMs: env.OPENCLAW_GATEWAY_RECONNECT_BASE_DELAY_MS,
      reconnectMaxAttempts: env.OPENCLAW_GATEWAY_RECONNECT_MAX_ATTEMPTS,
      rpcTimeoutMs: env.OPENCLAW_GATEWAY_RPC_TIMEOUT_MS,
      supportedVersions: splitCsv(env.OPENCLAW_GATEWAY_SUPPORTED_VERSIONS),
      workspaceRoot: env.OPENCLAW_WORKSPACE_ROOT,
      wslDistro: env.OPENCLAW_WSL_DISTRO
    },
    notebooklm: {
      enabled: env.NOTEBOOKLM_ENABLED,
      pythonCommand: env.NOTEBOOKLM_PYTHON_COMMAND,
      bridgeScript: env.NOTEBOOKLM_BRIDGE_SCRIPT,
      authMode: env.NOTEBOOKLM_AUTH_MODE,
      allowedOperations: splitCsv(env.NOTEBOOKLM_ALLOWED_OPERATIONS),
      generationDefaults: {
        waitForCompletion: env.NOTEBOOKLM_GENERATION_WAIT_FOR_COMPLETION,
        persistArtifacts: env.NOTEBOOKLM_GENERATION_PERSIST_ARTIFACTS
      },
      ...(env.NOTEBOOKLM_PROFILE ? { profile: env.NOTEBOOKLM_PROFILE } : {}),
      ...(env.NOTEBOOKLM_STORAGE_PATH
        ? { storagePath: env.NOTEBOOKLM_STORAGE_PATH }
        : {})
    },
    researchPaper: {
      arxiv: {
        enabled: env.ARXIV_ENABLED,
        requestTimeoutMs: env.ARXIV_REQUEST_TIMEOUT_MS,
        retryOn429: env.ARXIV_RETRY_ON_429,
        maxRetries: env.ARXIV_MAX_RETRIES
      },
      semanticScholar: {
        enabled: env.SEMANTIC_SCHOLAR_ENABLED,
        requestTimeoutMs: env.SEMANTIC_SCHOLAR_REQUEST_TIMEOUT_MS,
        maxResultsDefault: env.SEMANTIC_SCHOLAR_MAX_RESULTS_DEFAULT,
        ...(env.SEMANTIC_SCHOLAR_API_KEY
          ? { apiKey: env.SEMANTIC_SCHOLAR_API_KEY }
          : {})
      }
    },
    openAi: {
      enabled: env.OPENAI_ENABLED,
      ...(env.OPENAI_API_KEY ? { apiKey: env.OPENAI_API_KEY } : {}),
      ...(env.OPENAI_BASE_URL ? { baseUrl: env.OPENAI_BASE_URL } : {}),
      ...(env.OPENAI_DEFAULT_MODEL
        ? { defaultModel: env.OPENAI_DEFAULT_MODEL }
        : {})
    }
  };
}

export function buildToolToggleRuntimeConfig(
  env: AppEnv
): ToolToggleRuntimeConfig {
  return {
    researchPaperSearch: {
      enabled: env.TOOL_RESEARCH_PAPER_SEARCH_ENABLED
    },
    ragRetrieval: {
      enabled: env.TOOL_RAG_RETRIEVAL_ENABLED
    },
    openAiAnswer: {
      enabled: env.TOOL_OPENAI_ANSWER_ENABLED
    }
  };
}
