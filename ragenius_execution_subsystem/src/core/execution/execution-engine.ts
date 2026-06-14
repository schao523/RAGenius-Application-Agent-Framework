import { randomUUID } from "node:crypto";

import {
  type ExecuteSkillRequest,
  executionRequestSchema,
  type ExecutionRequest
} from "../../api/schemas/execution-request.schema.js";
import type {
  ExecutionMetadata,
  NormalizedExecutionResult
} from "../../api/schemas/common-response.schema.js";
import { AppError } from "../errors/app-error.js";
import { getArtifactConsumerSpec } from "../artifacts/artifact-consumption-registry.js";
import { toAppError } from "../errors/error-classifier.js";
import type { AgentProvider } from "../agents/agent-provider.js";
import { classifyAgentRequest } from "../agents/agent-policy.js";
import { CodexCliProvider } from "../agents/codex-cli-provider.js";
import { PermissionEngine } from "../permissions/permission-engine.js";
import type { PermissionPolicy } from "../permissions/permission.types.js";
import type { BuilderSkillClient } from "../skills/builder-skill-client.js";
import { SkillRegistry } from "../skills/skill-registry.js";
import type { SkillDefinition } from "../skills/skill.types.js";
import { ToolEngine } from "../tools/tool-engine.js";
import { ToolRegistry } from "../tools/tool-registry.js";
import type { ToolDefinition } from "../tools/tool.types.js";
import { WorkflowOrchestrator } from "../workflow/workflow-orchestrator.js";
import type { ToolExecutionProvenance } from "../tools/tool.types.js";

import type { ExecutionContext } from "./execution-context.js";
import {
  normalizeCompletedResult,
  normalizeFailedResult,
  normalizePendingConfirmationResult
} from "./result-normalizer.js";
import {
  persistedSkillIdForRequest,
  type ExecutionStore
} from "./execution-store.js";

type NormalizedArtifactReference = {
  artifact_id: string;
  artifact_type: string;
  display_name?: string;
  storage_file_name?: string;
  summary?: string;
  app_id?: string;
  created_at?: string;
  created_by_execution_id?: string;
  created_by_turn_id?: string;
  source_tool_id?: string;
  source_skill_id?: string;
  provider_origin?: string;
  mime_type?: string;
  size_bytes?: number;
  path?: string;
  file_path?: string;
  status?: string;
};

export class ExecutionEngine {
  private readonly skillRegistry: SkillRegistry;
  private readonly toolRegistry: ToolRegistry;
  private readonly permissionEngine: PermissionEngine;
  private readonly toolEngine: ToolEngine;
  private readonly workflowOrchestrator: WorkflowOrchestrator;
  private readonly builderSkillClient: BuilderSkillClient | undefined;
  private readonly executionStore: ExecutionStore | undefined;
  private readonly agentProviders: Map<string, AgentProvider>;

  constructor(options?: {
    skillRegistry?: SkillRegistry;
    builderSkillClient?: BuilderSkillClient | undefined;
    toolRegistry?: ToolRegistry;
    permissionEngine?: PermissionEngine;
    toolEngine?: ToolEngine;
    workflowOrchestrator?: WorkflowOrchestrator;
    executionStore?: ExecutionStore;
    codexCliProvider?: CodexCliProvider;
    agentProviders?: Map<string, AgentProvider>;
  }) {
    this.skillRegistry = options?.skillRegistry ?? new SkillRegistry();
    this.builderSkillClient = options?.builderSkillClient;
    this.toolRegistry = options?.toolRegistry ?? new ToolRegistry();
    this.permissionEngine = options?.permissionEngine ?? new PermissionEngine();
    this.toolEngine =
      options?.toolEngine ?? new ToolEngine(undefined, this.permissionEngine);
    this.workflowOrchestrator =
      options?.workflowOrchestrator ??
      new WorkflowOrchestrator(this.toolRegistry, this.toolEngine);
    this.executionStore = options?.executionStore;
    const codexCliProvider =
      options?.codexCliProvider ??
      new CodexCliProvider({
        enabled: false,
        nodeCommand: "node",
        bridgeScript: "scripts/codex_cli_bridge.js",
        command: "codex",
        args: [],
        timeoutMs: 300000
      });
    this.agentProviders =
      options?.agentProviders ??
      new Map([[codexCliProvider.backend, codexCliProvider]]);
  }

  async execute(
    requestLike: unknown,
    options?: { executionId?: string }
  ): Promise<NormalizedExecutionResult> {
    let request: ExecutionRequest | undefined;
    let executionId: string | null = null;
    try {
      request = executionRequestSchema.parse(requestLike);
      executionId = options?.executionId ?? this.createExecutionId();
      if (request.request_type === "execute_agent") {
        const agentPolicy = classifyAgentRequest(request);
        if (agentPolicy.mode === "require_confirmation") {
          if (request.execution_options?.require_confirmation !== true) {
            const result = normalizePendingConfirmationResult({
              executionId,
              toolId: request.agent_backend,
              permissionScope: agentPolicy.permissionScope,
              logsSummary:
                "Execution paused because agent confirmation is required.",
              resultDetails: {
                backend: request.agent_backend,
                risk_class: agentPolicy.riskClass,
                workspace_access: agentPolicy.workspaceAccess,
                network_access: agentPolicy.networkAccess,
                policy_reason: agentPolicy.reason,
                ...(agentPolicy.matchedTerms.length > 0
                  ? { matched_terms: agentPolicy.matchedTerms }
                  : {})
              }
            });
            await this.persistResult(request, result);
            return result;
          }
        }

        if (agentPolicy.mode === "blocked") {
          throw new AppError({
            code: "PERMISSION_BLOCKED",
            message: "Agent execution is blocked by policy.",
            errorClass: "permission",
            httpStatus: 403,
            details: {
              backend: request.agent_backend,
              permission_scope: agentPolicy.permissionScope,
              risk_class: agentPolicy.riskClass,
              workspace_access: agentPolicy.workspaceAccess,
              network_access: agentPolicy.networkAccess,
              policy_reason: agentPolicy.reason,
              matched_terms: agentPolicy.matchedTerms
            },
            recoverable: false,
            suggestedAction:
              "Use a non-destructive request or adjust the agent policy."
          });
        }

        const provider = this.agentProviders.get(request.agent_backend);
        if (!provider) {
          throw new AppError({
            code: "UNKNOWN_AGENT_BACKEND",
            message: `Unknown agent backend: ${request.agent_backend}`,
            errorClass: "validation",
            httpStatus: 400,
            details: { backend: request.agent_backend },
            recoverable: false,
            suggestedAction: "Use a supported agent backend."
          });
        }

        const agentResult = await provider.execute(request, agentPolicy, {
          executionId
        });
        const result = normalizeCompletedResult({
          executionId,
          resultType: "json",
          result: {
            backend: request.agent_backend,
            policy_class: agentPolicy.riskClass,
            workspace_access: agentPolicy.workspaceAccess,
            network_access: agentPolicy.networkAccess,
            ...agentResult
          },
          executionMetadata: {
            used_fallback: false,
            fallback_count: 0,
            execution_paths: ["local"],
            provider_ids: [provider.backend],
            tool_ids: []
          },
          logsSummary: `${provider.backend} agent request completed.`
        });
        await this.persistResult(request, result);
        return result;
      }
      const skill = await this.resolveSkill(request.app_id, request.skill_id);
      skill.inputSchema.parse(request.input);
      const tools = this.toolRegistry.resolve(skill.requiredTools);
      const skillPermissionPolicies = this.buildSkillPermissionPolicies(
        request.app_id,
        skill,
        tools
      );

      for (const tool of tools) {
        const permissionInput =
          tool.id === "mock_video_generation_tool"
            ? {
                prompt: request.input.prompt,
                duration: request.input.duration
              }
            : {
                ...request.input,
                query: request.input.prompt ?? request.input.query ?? request.input.topic,
                topK: 3
              };

        const decisions = this.permissionEngine.evaluate(
          request.app_id,
          tool,
          permissionInput,
          skillPermissionPolicies
        );

        const confirmationDecision = decisions.find(
          (decision) => decision.mode === "require_confirmation"
        );
        if (
          confirmationDecision &&
          request.execution_options?.require_confirmation !== true
        ) {
          const result = normalizePendingConfirmationResult({
            executionId,
            toolId: tool.id,
            permissionScope: confirmationDecision.scope,
            logsSummary: "Execution paused because confirmation is required."
          });
          await this.persistResult(request, result);
          return result;
        }

        const blockedDecision = decisions.find(
          (decision) => decision.mode === "blocked"
        );
        if (blockedDecision) {
          throw new AppError({
            code: "PERMISSION_BLOCKED",
            message: "Tool execution is blocked by policy.",
            errorClass: "permission",
            httpStatus: 403,
            details: {
              tool_id: tool.id,
              permission_scope: blockedDecision.scope
            },
            recoverable: false,
            suggestedAction:
              "Update the permission policy or use a different tool."
          });
        }
      }

      if (request.execution_options?.dry_run === true) {
        const result = normalizeCompletedResult({
          executionId,
          resultType: "json",
          result: {
            dry_run: true,
            skill_id: skill.id,
            validated: true,
            required_tools: skill.requiredTools,
            side_effects_executed: false
          },
          logsSummary:
            "Dry run completed. No side-effecting tools were executed."
        });
        await this.persistResult(request, result);
        return result;
      }

      const context = this.createContext(request);
      context.executionId = executionId;
      context.skill = skill;
      context.toolDefinitions = tools;
      context.permissionPolicies = skillPermissionPolicies;

      const workflowResult = await this.workflowOrchestrator.execute(context);
      const executionProvenance = this.collectExecutionProvenance(context);
      const fallbackCount = executionProvenance.filter(
        (entry) => entry.execution_path === "rest_fallback"
      ).length;
      const executionMetadata = this.buildExecutionMetadata(
        executionProvenance,
        fallbackCount
      );
      const normalizedResult = this.attachArtifactsToResult(
        workflowResult,
        context,
        skill.id,
        executionId
      );

      const result = normalizeCompletedResult({
        executionId,
        resultType: skill.resultType ?? "json",
        result:
          (skill.resultType ?? "json") === "video"
            ? {
                title: workflowResult.title,
                summary: workflowResult.summary,
                ...(Array.isArray((normalizedResult as { artifacts?: unknown[] }).artifacts)
                  ? { artifacts: (normalizedResult as { artifacts: unknown[] }).artifacts }
                  : {})
              }
            : normalizedResult,
        files:
          (skill.resultType ?? "json") === "video" && workflowResult.file_id
            ? [
                {
                  file_id: workflowResult.file_id,
                  kind: "video",
                  mime_type: "video/mp4"
                }
              ]
            : [],
        executionProvenance,
        ...(executionMetadata ? { executionMetadata } : {}),
        logsSummary:
          fallbackCount > 0
            ? `Skill completed in 3 steps with 2 tool calls. ${fallbackCount} fallback path(s) used.`
            : "Skill completed in 3 steps with 2 tool calls."
      });
      await this.persistResult(request, result);
      return result;
    } catch (error) {
      console.error("[execution-engine] execution failed", {
        executionId,
        requestType: request?.request_type ?? null,
        skillId: request ? persistedSkillIdForRequest(request) : null,
        appId: request?.app_id ?? null,
        sessionId: request?.session_id ?? null,
        error:
          error instanceof Error
            ? error instanceof AppError
              ? {
                  name: error.name,
                  code: error.code,
                  message: error.message,
                  details: error.details,
                  recoverable: error.recoverable,
                  suggestedAction: error.suggestedAction,
                  stack: error.stack
                }
              : {
                  name: error.name,
                  message: error.message,
                  stack: error.stack
                }
            : error
      });
      const appError = toAppError(error);
      const result = normalizeFailedResult({
        executionId,
        error: appError.toNormalizedError(),
        logsSummary: "Execution failed."
      });
      if (request) {
        await this.persistResult(request, result);
      }
      return result;
    }
  }

  private createContext(request: ExecuteSkillRequest): ExecutionContext {
    return {
      executionId: null,
      request,
      executionOptions: request.execution_options ?? {
        dry_run: false,
        require_confirmation: false
      },
      toolDefinitions: [],
      permissionPolicies: [],
      stepOutputs: {},
      toolResults: {},
      errors: []
    };
  }

  private buildSkillPermissionPolicies(
    appId: string,
    skill: SkillDefinition,
    tools: ToolDefinition[]
  ): PermissionPolicy[] {
    if (!skill.confirmationMode) {
      return [];
    }

    return tools.flatMap((tool) =>
      tool.permissionScopes.map((scope: string) => ({
        appId,
        toolId: tool.id,
        scope,
        mode: skill.confirmationMode as PermissionPolicy["mode"]
      }))
    );
  }

  private async resolveSkill(appId: string, skillId: string): Promise<SkillDefinition> {
    try {
      return this.skillRegistry.get(skillId);
    } catch (error) {
      const appError = toAppError(error);
      if (appError.code !== "SKILL_NOT_FOUND" || !this.builderSkillClient) {
        throw error;
      }
      const builderSkill = await this.builderSkillClient.getBoundSkill(appId, skillId);
      if (!builderSkill) {
        throw error;
      }
      return builderSkill;
    }
  }

  private createExecutionId(): string {
    return `execution_${randomUUID().replace(/-/g, "").slice(0, 12)}`;
  }

  private async persistResult(
    request: ExecutionRequest,
    result: NormalizedExecutionResult
  ): Promise<void> {
    if (!this.executionStore || !result.execution_id) {
      return;
    }

    await this.executionStore.save({
      executionId: result.execution_id,
      request,
      result
    });
  }

  private collectExecutionProvenance(
    context: ExecutionContext
  ): ToolExecutionProvenance[] {
    return Object.values(context.stepOutputs)
      .map(
        (stepOutput) =>
          stepOutput.execution as ToolExecutionProvenance | undefined
      )
      .filter(
        (entry): entry is ToolExecutionProvenance =>
          entry !== undefined
      );
  }

  private buildExecutionMetadata(
    executionProvenance: ToolExecutionProvenance[],
    fallbackCount: number
  ): ExecutionMetadata | undefined {
    if (executionProvenance.length === 0) {
      return undefined;
    }

    return {
      used_fallback: fallbackCount > 0,
      fallback_count: fallbackCount,
      execution_paths: [
        ...new Set(executionProvenance.map((entry) => entry.execution_path))
      ],
      provider_ids: [
        ...new Set(
          executionProvenance
            .map((entry) => entry.provider_id)
            .filter((value): value is string => typeof value === "string")
        )
      ],
      tool_ids: [
        ...new Set(executionProvenance.map((entry) => entry.tool_id))
      ]
    };
  }

  private attachArtifactsToResult(
    workflowResult: Record<string, unknown>,
    context: ExecutionContext,
    skillId: string,
    executionId: string
  ): Record<string, unknown> {
    const collected = new Map<string, NormalizedArtifactReference>();
    const existingArtifacts = Array.isArray(workflowResult.artifacts)
      ? workflowResult.artifacts
      : [];

    for (const item of existingArtifacts) {
      const normalized = this.normalizeArtifactReference(item, skillId, executionId);
      if (normalized) {
        collected.set(normalized.artifact_id, normalized);
      }
    }

    for (const stepOutput of Object.values(context.stepOutputs)) {
      const rawOutput =
        stepOutput &&
        typeof stepOutput === "object" &&
        "raw_output" in stepOutput &&
        stepOutput.raw_output &&
        typeof stepOutput.raw_output === "object"
          ? (stepOutput.raw_output as Record<string, unknown>)
          : undefined;
      const rawArtifacts =
        rawOutput && Array.isArray(rawOutput.artifacts) ? rawOutput.artifacts : [];
      for (const item of rawArtifacts) {
        const normalizedFromArray = this.normalizeArtifactReference(
          item,
          skillId,
          executionId
        );
        if (normalizedFromArray) {
          collected.set(normalizedFromArray.artifact_id, normalizedFromArray);
        }
      }
      const normalized = this.normalizeArtifactReference(rawOutput, skillId, executionId);
      if (normalized) {
        collected.set(normalized.artifact_id, normalized);
      }
    }

    if (collected.size === 0) {
      return workflowResult;
    }

    return {
      ...workflowResult,
      artifacts: [...collected.values()]
    };
  }

  private normalizeArtifactReference(
    candidate: unknown,
    skillId: string,
    executionId: string
  ): NormalizedArtifactReference | null {
    if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) {
      return null;
    }

    const record = candidate as Record<string, unknown>;
    const artifactId =
      typeof record.artifact_id === "string" && record.artifact_id.trim().length > 0
        ? record.artifact_id.trim()
        : "";
    const artifactType =
      typeof record.artifact_type === "string" && record.artifact_type.trim().length > 0
        ? record.artifact_type.trim()
        : "";
    if (!artifactId || !artifactType) {
      return null;
    }

    return {
      artifact_id: artifactId,
      artifact_type: artifactType,
      ...(typeof record.display_name === "string" && record.display_name.trim().length > 0
        ? { display_name: record.display_name.trim() }
        : {}),
      ...(typeof record.storage_file_name === "string" && record.storage_file_name.trim().length > 0
        ? { storage_file_name: record.storage_file_name.trim() }
        : {}),
      ...(typeof record.summary === "string" && record.summary.trim().length > 0
        ? { summary: record.summary.trim() }
        : {}),
      ...(typeof record.app_id === "string" && record.app_id.trim().length > 0
        ? { app_id: record.app_id.trim() }
        : {}),
      ...(typeof record.created_at === "string" && record.created_at.trim().length > 0
        ? { created_at: record.created_at.trim() }
        : { created_at: new Date().toISOString() }),
      ...(typeof record.created_by_execution_id === "string" && record.created_by_execution_id.trim().length > 0
        ? { created_by_execution_id: record.created_by_execution_id.trim() }
        : { created_by_execution_id: executionId }),
      ...(typeof record.created_by_turn_id === "string" && record.created_by_turn_id.trim().length > 0
        ? { created_by_turn_id: record.created_by_turn_id.trim() }
        : {}),
      ...(typeof record.source_tool_id === "string" && record.source_tool_id.trim().length > 0
        ? { source_tool_id: record.source_tool_id.trim() }
        : {}),
      ...(typeof record.source_skill_id === "string" && record.source_skill_id.trim().length > 0
        ? { source_skill_id: record.source_skill_id.trim() }
        : { source_skill_id: skillId }),
      ...(record.reviewed === true ? { reviewed: true } : {}),
      ...(typeof record.reviewed_at === "string" && record.reviewed_at.trim().length > 0
        ? { reviewed_at: record.reviewed_at.trim() }
        : {}),
      ...(typeof record.reviewed_by === "string" && record.reviewed_by.trim().length > 0
        ? { reviewed_by: record.reviewed_by.trim() }
        : {}),
      ...(typeof record.review_source === "string" && record.review_source.trim().length > 0
        ? { review_source: record.review_source.trim() }
        : {}),
      ...(Array.isArray(record.source_message_ids)
        ? { source_message_ids: record.source_message_ids.map((value) => String(value || "").trim()).filter(Boolean) }
        : {}),
      ...(typeof record.content_hash === "string" && record.content_hash.trim().length > 0
        ? { content_hash: record.content_hash.trim() }
        : {}),
      ...(typeof record.provider_origin === "string" && record.provider_origin.trim().length > 0
        ? { provider_origin: record.provider_origin.trim() }
        : {}),
      ...(typeof record.mime_type === "string" && record.mime_type.trim().length > 0
        ? { mime_type: record.mime_type.trim() }
        : {}),
      ...(typeof record.size_bytes === "number" ? { size_bytes: record.size_bytes } : {}),
      ...(typeof record.path === "string" && record.path.trim().length > 0
        ? { path: record.path.trim() }
        : {}),
      ...(typeof record.file_path === "string" && record.file_path.trim().length > 0
        ? { file_path: record.file_path.trim() }
        : {}),
      ...(typeof record.status === "string" && record.status.trim().length > 0
        ? { status: record.status.trim() }
        : { status: "ready" }),
      ...(() => {
        const spec = getArtifactConsumerSpec(artifactType);
        return spec
          ? {
              consumption: {
                default_mode: spec.default_consumption_mode,
                supported_modes: spec.supported_consumption_modes,
              },
              reusable: spec.reusable,
              picker_visibility: spec.picker_visibility,
              eligible_consumers: spec.eligible_consumers,
            }
          : {};
      })()
    };
  }
}
