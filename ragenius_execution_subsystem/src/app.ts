import Fastify, { type FastifyInstance } from "fastify";
import fs from "node:fs/promises";

import { registerServiceAuth } from "./api/auth/service-auth.js";
import { registerExecutionRoutes } from "./api/routes/executions.routes.js";
import { registerHealthRoutes } from "./api/routes/health.routes.js";
import { registerSkillRoutes } from "./api/routes/skills.routes.js";
import { registerToolRoutes } from "./api/routes/tools.routes.js";
import { registerArtifactRoutes } from "./api/routes/artifacts.routes.js";
import { registerAgentSkillRoutes } from "./api/routes/agent-skills.routes.js";
import { createPrismaClient } from "./db/prisma.js";
import type { AgentProvider } from "./core/agents/agent-provider.js";
import type { AgentProviderExecutionContext } from "./core/agents/agent-provider-context.js";
import type { ExecuteAgentRequest } from "./api/schemas/execution-request.schema.js";
import { CodexCliProvider } from "./core/agents/codex-cli-provider.js";
import { OpenClawCliProvider } from "./core/agents/openclaw-cli-provider.js";
import { AgentArtifactResolver } from "./core/agents/agent-artifact-resolver.js";
import { AgentOutputArtifactPersister } from "./core/agents/agent-output-artifact-persister.js";
import { AgentOperationVerifierRegistry } from "./core/agents/agent-operation-verifier.js";
import { NotebookLmOperationVerifier } from "./core/agents/notebooklm-operation-verifier.js";
import { finalizeAgentResult } from "./core/agents/agent-result-finalizer.js";
import type { CodexNormalizedResult } from "./core/agents/codex-cli-types.js";
import type { OpenClawProviderResult } from "./core/agents/openclaw-cli-types.js";
import { readOpenClawWorkspaceFileViaWsl } from "./core/agents/openclaw-workspace.js";
import { ExecutionEngine } from "./core/execution/execution-engine.js";
import { ConfirmationService } from "./core/execution/confirmation-service.js";
import {
  InMemoryConfirmationStore,
  type ConfirmationStore
} from "./core/execution/confirmation-store.js";
import { ExecutionStatusService } from "./core/execution/execution-status-service.js";
import { AgentExecutionQueue } from "./core/execution/agent-execution-queue.js";
import {
  InMemoryExecutionStore,
  type ExecutionStore
} from "./core/execution/execution-store.js";
import { PrismaExecutionStore } from "./core/execution/prisma-execution-store.js";
import { PrismaConfirmationStore } from "./core/execution/prisma-confirmation-store.js";
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
import {
  InMemoryAgentSkillProjectionStore,
  type AgentSkillProjectionStore
} from "./core/agent-skills/agent-skill-projection-store.js";
import {
  PrismaAgentSkillProjectionStore,
  type PrismaAgentSkillProjectionClient
} from "./core/agent-skills/prisma-agent-skill-projection-store.js";
import { AgentSkillDiscoveryService } from "./core/agent-skills/agent-skill-discovery-service.js";
import { CodexAgentSkillDiscoveryAdapter } from "./core/agent-skills/codex-agent-skill-discovery.js";

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
  agentExecutionQueue: AgentExecutionQueue;
  agentSkillDiscoveryService: AgentSkillDiscoveryService;
  agentSkillProjectionStore: AgentSkillProjectionStore;
  artifactStore: ArtifactStore;
  confirmationService: ConfirmationService;
  confirmationStore: ConfirmationStore;
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
  const agentSkillProjectionStore =
    overrides.agentSkillProjectionStore ??
    (dependencies.prismaClient
      ? new PrismaAgentSkillProjectionStore(
          dependencies.prismaClient as unknown as PrismaAgentSkillProjectionClient
        )
      : new InMemoryAgentSkillProjectionStore());
  const agentSkillDiscoveryService =
    overrides.agentSkillDiscoveryService ??
    new AgentSkillDiscoveryService([
      new CodexAgentSkillDiscoveryAdapter(runtimeConfig.agentSkills.codex)
    ]);
  const executionStatusService =
    overrides.executionStatusService ??
    new ExecutionStatusService(executionStore);
  const confirmationStore =
    overrides.confirmationStore ??
    (dependencies.prismaClient
      ? new PrismaConfirmationStore(dependencies.prismaClient)
      : new InMemoryConfirmationStore());
  const configuredConfirmationService =
    overrides.confirmationService ??
    new ConfirmationService(confirmationStore, {
      ttlMs: runtimeConfig.confirmationTtlMs
    });
  const notebookLmAdapter = new NotebookLmAdapter(
    runtimeConfig.providers.notebooklm,
    undefined,
    { artifactStore }
  );
  const operationVerifierRegistry = new AgentOperationVerifierRegistry([
    new NotebookLmOperationVerifier(notebookLmAdapter)
  ]);
  const finalizeProviderResult = async <T extends CodexNormalizedResult | OpenClawProviderResult>(
    input: {
      request: ExecuteAgentRequest;
      context: AgentProviderExecutionContext;
      result: T;
    }
  ): Promise<T> => {
    const trustedVerification = await operationVerifierRegistry.verify({
      request: input.request,
      context: input.context,
      reportedVerification: Array.isArray(input.result.operation_verification)
        ? input.result.operation_verification
        : []
    });
    return await finalizeAgentResult({
      context: input.context,
      result: input.result,
      trustedVerification
    }) as T;
  };
  const toolRegistry = overrides.toolRegistry ?? new ToolRegistry();
  const toolEngine =
    overrides.toolEngine ??
    new ToolEngine(
      {
        api: new MockApiToolProvider(runtimeConfig.providers),
        adapter: new AdapterToolProvider(runtimeConfig.adapters, {
          notebooklmAdapter: notebookLmAdapter
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
  const agentArtifactResolver = new AgentArtifactResolver(artifactStore);
  const codexOutputArtifactPersister = new AgentOutputArtifactPersister(
    artifactStore,
    { readOutputBytes: (workspaceAbsolutePath) => fs.readFile(workspaceAbsolutePath) }
  );
  const openClawOutputArtifactPersister = new AgentOutputArtifactPersister(
    artifactStore,
    {
      readOutputBytes: (workspaceAbsolutePath) =>
        readOpenClawWorkspaceFileViaWsl({
          wslDistro: runtimeConfig.providers.openClaw.wslDistro,
          workspaceAbsolutePath
        })
    }
  );
  const codexCliProvider = new CodexCliProvider(
    runtimeConfig.providers.codexCli,
    undefined,
    {
      persistOutput: (input) => codexOutputArtifactPersister.persist(input),
      finalizeResult: finalizeProviderResult
    }
  );
  const openClawCliProvider = new OpenClawCliProvider(
    runtimeConfig.providers.openClaw,
    {
      resolveArtifacts: (input) => agentArtifactResolver.resolve(input),
      persistOutput: (input) => openClawOutputArtifactPersister.persist(input),
      finalizeResult: finalizeProviderResult
    }
  );
  const executionEngine =
    overrides.executionEngine ??
    new ExecutionEngine({
      builderSkillClient,
      confirmationService: configuredConfirmationService,
      agentProviders: new Map<string, AgentProvider>([
        [codexCliProvider.backend, codexCliProvider],
        [openClawCliProvider.backend, openClawCliProvider]
      ]),
      resolveAgentArtifacts: (input) => agentArtifactResolver.resolve(input),
      resolveScopedSkillArtifactFile: async (input) =>
        (await artifactStore.resolveScopedFile(input)).absolute_path,
      notebookLmProfile: runtimeConfig.providers.notebooklm.profile ?? "default",
      executionStore,
      permissionEngine,
      skillRegistry,
      toolEngine,
      toolRegistry,
      workflowOrchestrator
    });
  const confirmationService =
    overrides.confirmationService ??
    overrides.executionEngine?.getConfirmationService() ??
    configuredConfirmationService;
  const agentExecutionQueue =
    overrides.agentExecutionQueue ??
    new AgentExecutionQueue(
      executionStore,
      async (request, options) => {
        const result = await executionEngine.execute(request, options);
        if (options.approvedConfirmation) {
          await confirmationService.finish(
            {
              appId: request.app_id,
              sessionId: request.session_id,
              executionId: options.executionId,
              confirmationId: options.approvedConfirmation.confirmationId
            },
            result.status === "completed" ? "completed" : "failed"
          );
        }
        return result;
      },
      runtimeConfig.agentAsync.concurrency
    );
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
    agentExecutionQueue,
    agentSkillDiscoveryService,
    agentSkillProjectionStore,
    artifactStore,
    confirmationService,
    confirmationStore,
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
  registerServiceAuth(app, services.runtimeConfig.serviceAuth);

  app.addHook("onReady", async () => {
    await services.agentExecutionQueue.reconcileInterrupted();
    services.agentExecutionQueue.start();
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

  app.addHook("onClose", async () => {
    services.agentExecutionQueue.stop();
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
  void app.register(registerArtifactRoutes, { prefix: "/v1" });
  void app.register(registerAgentSkillRoutes, { prefix: "/v1" });

  return app;
}
