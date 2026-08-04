import type { AppEnv } from "./env.js";
import {
  buildAdapterRuntimeConfig,
  buildArtifactStoreRuntimeConfig,
  buildBuilderRuntimeConfig,
  buildFileToolRuntimeConfig,
  buildNetworkRuntimeConfig,
  buildProviderRuntimeConfig,
  buildToolToggleRuntimeConfig,
  type AdapterRuntimeConfig,
  type ArtifactStoreRuntimeConfig,
  type BuilderRuntimeConfig,
  type FileToolRuntimeConfig,
  type NetworkRuntimeConfig,
  type ProviderRuntimeConfig,
  type ToolToggleRuntimeConfig
} from "./provider-config.js";
import {
  buildMcpRuntimeConfig,
  type McpRuntimeConfig
} from "./mcp-config.js";
import {
  buildDefaultRuntimePolicyConfig,
  type RuntimePolicyConfig
} from "./policy-config.js";
import { z } from "zod";

export interface RuntimeConfig {
  agentAsync: { enabled: boolean; concurrency: number };
  adapters: AdapterRuntimeConfig;
  artifactStore: ArtifactStoreRuntimeConfig;
  builder: BuilderRuntimeConfig;
  confirmationTtlMs: number;
  env: AppEnv;
  fileTools: FileToolRuntimeConfig;
  mcp: McpRuntimeConfig;
  network: NetworkRuntimeConfig;
  policy: RuntimePolicyConfig;
  providers: ProviderRuntimeConfig;
  serviceAuth: ServiceAuthRuntimeConfig;
  tools: ToolToggleRuntimeConfig;
}

export interface ServiceAuthRuntimeConfig {
  required: boolean;
  credentials: Array<{
    serviceId: string;
    token: string;
    scopes: string[];
  }>;
}

const serviceCredentialSchema = z.object({
  service_id: z.string().trim().min(1),
  token: z.string().trim().min(1),
  scopes: z.array(z.string().trim().min(1)).default([])
}).strict();

function buildServiceAuthRuntimeConfig(env: AppEnv): ServiceAuthRuntimeConfig {
  const configured = z.array(serviceCredentialSchema).parse(
    JSON.parse(env.RAGENIUS_EXECUTION_SERVICE_CREDENTIALS_JSON)
  );
  const credentials = configured.map((credential) => ({
    serviceId: credential.service_id,
    token: credential.token,
    scopes: [...new Set(credential.scopes)]
  }));
  if (env.RAGENIUS_EXECUTION_SERVICE_TOKEN) {
    credentials.push({
      serviceId: env.RAGENIUS_EXECUTION_SERVICE_ID,
      token: env.RAGENIUS_EXECUTION_SERVICE_TOKEN,
      scopes: ["execution"]
    });
  }
  return {
    required: env.RAGENIUS_EXECUTION_SERVICE_AUTH_REQUIRED,
    credentials
  };
}

export interface RuntimeConfigDiagnostics {
  adapters: {
    configured: boolean;
    enabled: number;
  };
  artifactStore: {
    configured: boolean;
  };
  builder: {
    configured: boolean;
  };
  fileTools: {
    configured: boolean;
    allowedRoots: number;
    mutationConfigured: boolean;
    mutationRoots: number;
  };
  mcp: {
    configuredServers: number;
    enabledServers: number;
    startupDiscoveryEnabled: boolean;
    providers: Array<{
      id: string;
      transport: string;
      authConfigured: boolean;
      allowlistedTools: number;
    }>;
  };
  network: {
    extraCaCertsConfigured: boolean;
    proxyConfigured: boolean;
    proxyTargets: string[];
  };
  providers: {
    codexCli: { enabled: boolean };
    notebooklm: { enabled: boolean };
    openClaw: { enabled: boolean };
    arxiv: { enabled: boolean };
    openAi: { enabled: boolean };
    semanticScholar: { enabled: boolean; hasApiKey: boolean };
  };
  serviceAuth: {
    configured: boolean;
    required: boolean;
  };
  tools: {
    openAiAnswer: boolean;
    ragRetrieval: boolean;
    researchPaperSearch: boolean;
  };
}

export function buildRuntimeConfig(
  env: AppEnv,
  source: NodeJS.ProcessEnv = process.env
): RuntimeConfig {
  return {
    agentAsync: {
      enabled: env.AGENT_ASYNC_EXECUTION_ENABLED,
      concurrency: env.AGENT_ASYNC_CONCURRENCY
    },
    adapters: buildAdapterRuntimeConfig(env),
    artifactStore: buildArtifactStoreRuntimeConfig(env),
    builder: buildBuilderRuntimeConfig(env),
    confirmationTtlMs: env.EXECUTION_CONFIRMATION_TTL_MS,
    env,
    fileTools: buildFileToolRuntimeConfig(env),
    mcp: buildMcpRuntimeConfig(env, source),
    network: buildNetworkRuntimeConfig(env),
    policy: buildDefaultRuntimePolicyConfig(),
    providers: buildProviderRuntimeConfig(env),
    serviceAuth: buildServiceAuthRuntimeConfig(env),
    tools: buildToolToggleRuntimeConfig(env)
  };
}

export function inspectRuntimeConfig(
  runtimeConfig: RuntimeConfig
): RuntimeConfigDiagnostics {
  const proxyTargets = [
    runtimeConfig.network.httpProxy,
    runtimeConfig.network.httpsProxy,
    runtimeConfig.network.allProxy
  ].filter((value): value is string => Boolean(value));

  return {
    adapters: {
      configured: runtimeConfig.adapters.tools.length > 0,
      enabled: runtimeConfig.adapters.tools.filter((tool) => tool.enabled).length
    },
    artifactStore: {
      configured: Boolean(runtimeConfig.artifactStore.rootDir)
    },
    builder: {
      configured: Boolean(runtimeConfig.builder.baseUrl)
    },
    fileTools: {
      configured: runtimeConfig.fileTools.allowedRoots.length > 0,
      allowedRoots: runtimeConfig.fileTools.allowedRoots.length,
      mutationConfigured: runtimeConfig.fileTools.mutationRoots.length > 0,
      mutationRoots: runtimeConfig.fileTools.mutationRoots.length
    },
    mcp: {
      configuredServers: runtimeConfig.mcp.servers.length,
      enabledServers: runtimeConfig.mcp.servers.filter((server) => server.enabled)
        .length,
      startupDiscoveryEnabled: true,
      providers: runtimeConfig.mcp.servers.map((server) => ({
        id: server.id,
        transport: server.transport,
        authConfigured: Boolean(server.authToken),
        allowlistedTools: server.allowedToolNames.length
      }))
    },
    network: {
      extraCaCertsConfigured: Boolean(runtimeConfig.network.extraCaCertsPath),
      proxyConfigured: proxyTargets.length > 0,
      proxyTargets
    },
    providers: {
      codexCli: {
        enabled: runtimeConfig.providers.codexCli.enabled
      },
      openClaw: {
        enabled: runtimeConfig.providers.openClaw.enabled
      },
      notebooklm: {
        enabled: runtimeConfig.providers.notebooklm.enabled
      },
      arxiv: {
        enabled: runtimeConfig.providers.researchPaper.arxiv.enabled
      },
      semanticScholar: {
        enabled: runtimeConfig.providers.researchPaper.semanticScholar.enabled,
        hasApiKey: Boolean(
          runtimeConfig.providers.researchPaper.semanticScholar.apiKey
        )
      },
      openAi: {
        enabled: runtimeConfig.providers.openAi.enabled
      }
    },
    serviceAuth: {
      configured: runtimeConfig.serviceAuth.credentials.length > 0,
      required: runtimeConfig.serviceAuth.required
    },
    tools: {
      researchPaperSearch: runtimeConfig.tools.researchPaperSearch.enabled,
      ragRetrieval: runtimeConfig.tools.ragRetrieval.enabled,
      openAiAnswer: runtimeConfig.tools.openAiAnswer.enabled
    }
  };
}

function isInvalidDiscardProxyTarget(value: string): boolean {
  try {
    const url = new URL(value);
    const isLoopbackHost =
      url.hostname === "127.0.0.1" ||
      url.hostname === "localhost" ||
      url.hostname === "::1";
    return isLoopbackHost && url.port === "9";
  } catch {
    return false;
  }
}

export function validateRuntimeConfig(runtimeConfig: RuntimeConfig): void {
  if (
    runtimeConfig.serviceAuth.required &&
    runtimeConfig.serviceAuth.credentials.length === 0
  ) {
    throw new Error(
      "Execution service authentication is required but no service token is configured."
    );
  }

  const proxyTargets = [
    runtimeConfig.network.httpProxy,
    runtimeConfig.network.httpsProxy,
    runtimeConfig.network.allProxy
  ].filter((value): value is string => Boolean(value));

  const discardProxy = proxyTargets.find((value) =>
    isInvalidDiscardProxyTarget(value)
  );
  if (discardProxy) {
    throw new Error(
      `Runtime config contains an invalid discard proxy target: ${discardProxy}`
    );
  }
}
