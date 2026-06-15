import Fastify, { type FastifyInstance } from "fastify";

import { registerExecutionRoutes } from "./api/routes/executions.routes.js";
import { registerHealthRoutes } from "./api/routes/health.routes.js";
import { registerSkillRoutes } from "./api/routes/skills.routes.js";
import { registerToolRoutes } from "./api/routes/tools.routes.js";
import { createPrismaClient } from "./db/prisma.js";
import type { AgentProvider } from "./core/agents/agent-provider.js";
import { CodexCliProvider } from "./core/agents/codex-cli-provider.js";
import { OpenClawCliProvider } from "./core/agents/openclaw-cli-provider.js";
import { AgentArtifactResolver } from "./core/agents/agent-artifact-resolver.js";
import { AgentOutputArtifactPersister } from "./core/agents/agent-output-artifact-persister.js";
import { readOpenClawWorkspaceFileViaWsl } from "./core/agents/openclaw-workspace.js";
import { ExecutionEngine } from "./core/execution/execution-engine.js";
import { ExecutionStatusService } from "./core/execution/execution-status-service.js";
import {
  InMemoryExecutionStore,
  type ExecutionStore
} from "./core/execution/execution-store.js";
import { PrismaExecutionStore } from "./core/execution/prisma-execution-store.js";
import { toAppError } from "./core/errors/error-classifier.js";
import { PermissionEngine } from "./core/permissions/permission-engine.js";
import { getEnv } from "./config/env.js";
import {
  buildRuntimeConfig,
  type RuntimeConfig
} from "./config/runtime-config.js";
import {
  HttpBuilderSkillClient,
  type BuilderSkillClient
} from "./core/skills/builder-skill-client.js";
import { SkillRegistry } from "./core/skills/skill-registry.js";
import { MockApiToolProvider } from "./core/tools/providers/api-tool-provider.js";
import { AdapterToolProvider } from "./core/tools/providers/adapter-tool-provider.js";
import { ArtifactStore } from "./core/tools/providers/artifact-store.js";
import { FilePolicy } from "./core/tools/providers/file-policy.js";
import { MockMcpToolProvider } from "./core/tools/providers/mcp-tool-provider.js";
import { NotebookLmAdapter } from "./core/tools/providers/notebooklm-adapter.js";
import { PhaseOneLocalToolProvider } from "./core/tools/providers/local-tool-provider.js";
import { ToolEngine } from "./core/tools/tool-engine.js";
import { ToolRegistry } from "./core/tools/tool-registry.js";
import { WorkflowOrchestrator } from "./core/workflow/workflow-orchestrator.js";
import type { ToolDefinition } from "./core/tools/tool.types.js";

export interface McpDiscoveryProviderState {
  discoveredToolCount: number;
  discoveredToolIds: string[];
  lastDiscoveredAt: string | null;
  lastError: string | null;
  status: "not_started" | "success" | "failed";
}

export interface McpDiscoveryState {
  startupCompleted: boolean;
  providers: Record<string, McpDiscoveryProviderState>;
}

export interface AppServices {
  artifactStore: ArtifactStore;
  discoverMcpProvider: (providerId: string) => Promise<ToolDefinition[]>;
  builderSkillClient: BuilderSkillClient | undefined;
  executionEngine: ExecutionEngine;
  executionStatusService: ExecutionStatusService;
  executionStore: ExecutionStore;
  mcpDiscovery: McpDiscoveryState;
  permissionEngine: PermissionEngine;
  runtimeConfig: RuntimeConfig;
  skillRegistry: SkillRegistry;
  toolEngine: ToolEngine;
  toolRegistry: ToolRegistry;
  workflowOrchestrator: WorkflowOrchestrator;
}

export function createAppServices(
  overrides: Partial<AppServices> = {},
  runtimeConfig: RuntimeConfig = buildRuntimeConfig(getEnv()),
  dependencies: {
    prismaClient?: ReturnType<typeof createPrismaClient>;
  } = {}
): AppServices {
  const permissionEngine =
    overrides.permissionEngine ?? new PermissionEngine();
  const artifactStore = overrides.artifactStore ?? new ArtifactStore(runtimeConfig.artifactStore.rootDir);
  const executionStore =
    overrides.executionStore ??
    (dependencies.prismaClient
      ? new PrismaExecutionStore(dependencies.prismaClient)
      : new InMemoryExecutionStore());
  const executionStatusService =
    overrides.executionStatusService ??
    new ExecutionStatusService(executionStore);
  const toolRegistry = overrides.toolRegistry ?? new ToolRegistry();
  const toolEngine =
    overrides.toolEngine ??
    new ToolEngine(
      {
        api: new MockApiToolProvider(runtimeConfig.providers),
        adapter: new AdapterToolProvider(runtimeConfig.adapters, {
          notebooklmAdapter: new NotebookLmAdapter(
            runtimeConfig.providers.notebooklm,
            undefined,
            { artifactStore }
          )
        }),
        local: new PhaseOneLocalToolProvider(
          new FilePolicy(runtimeConfig.fileTools),
          artifactStore
        ),
        mcp: new MockMcpToolProvider(runtimeConfig.mcp, {
          artifactStore,
          policy: runtimeConfig.policy
        })
      },
      permissionEngine
    );
  const skillRegistry = overrides.skillRegistry ?? new SkillRegistry();
  const builderSkillClient =
    overrides.builderSkillClient ??
    (runtimeConfig.builder.baseUrl
      ? new HttpBuilderSkillClient(runtimeConfig.builder.baseUrl)
      : undefined);
  const workflowOrchestrator =
    overrides.workflowOrchestrator ??
    new WorkflowOrchestrator(toolRegistry, toolEngine);
  const codexCliProvider = new CodexCliProvider(runtimeConfig.providers.codexCli);
  const agentArtifactResolver = new AgentArtifactResolver(artifactStore);
  const agentOutputArtifactPersister = new AgentOutputArtifactPersister(
    artifactStore,
    {
      readOutputBytes: (workspaceAbsolutePath) =>
        readOpenClawWorkspaceFileViaWsl({
          wslDistro: runtimeConfig.providers.openClaw.wslDistro,
          workspaceAbsolutePath
        })
    }
  );
  const openClawCliProvider = new OpenClawCliProvider(
    runtimeConfig.providers.openClaw,
    {
      resolveArtifacts: (input) => agentArtifactResolver.resolve(input),
      persistOutput: (input) => agentOutputArtifactPersister.persist(input)
    }
  );
  const executionEngine =
    overrides.executionEngine ??
    new ExecutionEngine({
      builderSkillClient,
      agentProviders: new Map<string, AgentProvider>([
        [codexCliProvider.backend, codexCliProvider],
        [openClawCliProvider.backend, openClawCliProvider]
      ]),
      executionStore,
      permissionEngine,
      skillRegistry,
      toolEngine,
      toolRegistry,
      workflowOrchestrator
    });
  const mcpDiscovery: McpDiscoveryState = {
    startupCompleted: false,
    providers: Object.fromEntries(
      runtimeConfig.mcp.servers.map((server) => [
        server.id,
        {
          discoveredToolCount: 0,
          discoveredToolIds: [],
          lastDiscoveredAt: null,
          lastError: null,
          status: "not_started" as const
        }
      ])
    )
  };

  const discoverMcpProvider = async (
    providerId: string
  ): Promise<ToolDefinition[]> => {
    const discovered = await toolEngine.discoverMcpTools(providerId);
    for (const tool of discovered) {
      toolRegistry.register(tool);
    }

    const state = mcpDiscovery.providers[providerId];
    if (state) {
      state.discoveredToolCount = discovered.length;
      state.discoveredToolIds = discovered.map((tool) => tool.id);
      state.lastDiscoveredAt = new Date().toISOString();
      state.lastError = null;
      state.status = "success";
    }

    return discovered;
  };

  return {
    artifactStore,
    discoverMcpProvider,
    builderSkillClient,
    executionEngine,
    executionStatusService,
    executionStore,
    mcpDiscovery,
    permissionEngine,
    runtimeConfig,
    skillRegistry,
    toolEngine,
    toolRegistry,
    workflowOrchestrator
  };
}

export function buildApp(
  overrides: Partial<AppServices> = {},
  runtimeConfig: RuntimeConfig = buildRuntimeConfig(getEnv()),
  dependencies: {
    prismaClient?: ReturnType<typeof createPrismaClient>;
  } = {}
): FastifyInstance {
  const app = Fastify();
  const services = createAppServices(overrides, runtimeConfig, dependencies);

  app.decorate("services", services);

  app.addHook("onReady", async () => {
    const enabledServers = services.runtimeConfig.mcp.servers.filter(
      (server) => server.enabled
    );
    for (const server of enabledServers) {
      try {
        await services.discoverMcpProvider(server.id);
      } catch (error) {
        const state = services.mcpDiscovery.providers[server.id];
        if (state) {
          state.lastDiscoveredAt = new Date().toISOString();
          state.lastError =
            error instanceof Error ? error.message : String(error);
          state.status = "failed";
        }
      }
    }
    services.mcpDiscovery.startupCompleted = true;
  });

  app.setErrorHandler((error, _request, reply) => {
    const appError = toAppError(error);
    void reply.status(appError.httpStatus).send({
      error: appError.toNormalizedError()
    });
  });

  void app.register(registerHealthRoutes);
  void app.register(registerExecutionRoutes, { prefix: "/v1" });
  void app.register(registerSkillRoutes, { prefix: "/v1" });
  void app.register(registerToolRoutes, { prefix: "/v1" });

  return app;
}
