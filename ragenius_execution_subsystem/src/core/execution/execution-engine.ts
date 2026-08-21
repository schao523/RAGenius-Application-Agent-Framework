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
import type { AgentProvider, AgentProviderResult } from "../agents/agent-provider.js";
import type { ArtifactReferenceCoordinator } from "../artifacts/artifact-reference-coordinator.js";
import type { AgentProviderExecutionContext } from "../agents/agent-provider-context.js";
import type {
  AgentArtifactResolverInput,
  ResolvedAgentArtifact
} from "../agents/agent-artifact-resolver.js";
import { classifyAgentRequest } from "../agents/agent-policy.js";
import {
  createAgentOperationPlan,
  fingerprintAgentPolicy
} from "../agents/agent-operation-planner.js";
import { CodexCliProvider } from "../agents/codex-cli-provider.js";
import { normalizeOpenClawOptions } from "../agents/openclaw-options.js";
import {
  AgentSkillSelectionError,
  applyResolvedAgentSkillSelection,
  type AgentSkillSelectionService
} from "../agent-skills/agent-skill-selection-service.js";
import type {
  AgentSkillRecoveryClass,
  ResolvedAgentSkillSelection
} from "../agent-skills/agent-skill-types.js";
import { projectAgentSkillSelection } from "../agent-skills/agent-skill-activation-evidence.js";
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
import type { AgentInteractionType } from "../interactive/interactive-agent-types.js";
import type { InteractiveAgentSessionManager } from "../interactive/interactive-agent-session-manager.js";

import type { ExecutionContext } from "./execution-context.js";
import {
  type ApprovedConfirmation,
  ConfirmationService
} from "./confirmation-service.js";
import { InMemoryConfirmationStore } from "./confirmation-store.js";
import {
  normalizeCompletedResult,
  normalizeFailedResult,
  normalizePendingConfirmationResult,
  normalizeTerminalResult
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
  private readonly confirmationService: ConfirmationService;
  private readonly agentProviders: Map<string, AgentProvider>;
  private readonly artifactReferenceCoordinator: ArtifactReferenceCoordinator | undefined;
  private readonly resolveAgentArtifacts:
    | ((input: AgentArtifactResolverInput) => Promise<ResolvedAgentArtifact[]>)
    | undefined;
  private readonly resolveScopedSkillArtifactFile:
    | ((input: {
        appId: string;
        artifactId: string;
        sessionId: string;
      }) => Promise<string>)
    | undefined;
  private readonly notebookLmProfile: string;
  private readonly agentSkillSelectionService:
    | Pick<AgentSkillSelectionService, "resolve">
    | undefined;
  private readonly interactiveSessionManager:
    | Pick<InteractiveAgentSessionManager, "start">
    | undefined;
  private readonly interactiveRequirementResolver:
    | ((input: {
        request: ExecutionRequest & { request_type: "execute_agent" };
        selection: ResolvedAgentSkillSelection | null;
      }) => {
        requiredInteractionTypes: AgentInteractionType[];
        requiredRecoveryClass?: AgentSkillRecoveryClass;
      } | null)
    | undefined;

  constructor(options?: {
    skillRegistry?: SkillRegistry;
    builderSkillClient?: BuilderSkillClient | undefined;
    toolRegistry?: ToolRegistry;
    permissionEngine?: PermissionEngine;
    toolEngine?: ToolEngine;
    workflowOrchestrator?: WorkflowOrchestrator;
    executionStore?: ExecutionStore;
    confirmationService?: ConfirmationService;
    codexCliProvider?: CodexCliProvider;
    agentProviders?: Map<string, AgentProvider>;
    artifactReferenceCoordinator?: ArtifactReferenceCoordinator;
    resolveAgentArtifacts?: (
      input: AgentArtifactResolverInput
    ) => Promise<ResolvedAgentArtifact[]>;
    resolveScopedSkillArtifactFile?: (input: {
      appId: string;
      artifactId: string;
      sessionId: string;
    }) => Promise<string>;
    notebookLmProfile?: string;
    agentSkillSelectionService?: Pick<AgentSkillSelectionService, "resolve">;
    interactiveSessionManager?: Pick<InteractiveAgentSessionManager, "start">;
    interactiveRequirementResolver?: (input: {
      request: ExecutionRequest & { request_type: "execute_agent" };
      selection: ResolvedAgentSkillSelection | null;
    }) => {
      requiredInteractionTypes: AgentInteractionType[];
      requiredRecoveryClass?: AgentSkillRecoveryClass;
    } | null;
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
    this.notebookLmProfile = options?.notebookLmProfile?.trim() || "default";
    this.agentSkillSelectionService = options?.agentSkillSelectionService;
    this.interactiveSessionManager = options?.interactiveSessionManager;
    this.interactiveRequirementResolver = options?.interactiveRequirementResolver;
    this.confirmationService =
      options?.confirmationService ??
      new ConfirmationService(new InMemoryConfirmationStore(), {
        ttlMs: 900000
      });
    this.resolveAgentArtifacts = options?.resolveAgentArtifacts;
    this.artifactReferenceCoordinator = options?.artifactReferenceCoordinator;
    this.resolveScopedSkillArtifactFile = options?.resolveScopedSkillArtifactFile;
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
    options?: {
      approvedConfirmation?: ApprovedConfirmation;
      executionId?: string;
    }
  ): Promise<NormalizedExecutionResult> {
    let request: ExecutionRequest | undefined;
    let executionId: string | null = null;
    try {
      request = executionRequestSchema.parse(requestLike);
      executionId = options?.executionId ?? this.createExecutionId();
      if (request.request_type === "execute_agent") {
        let resolvedSelection: ResolvedAgentSkillSelection | null;
        try {
          resolvedSelection = await this.resolveAgentSkillSelection(request);
        } catch (error) {
          if (
            options?.approvedConfirmation &&
            error instanceof AgentSkillSelectionError
          ) {
            this.throwPolicyChanged();
          }
          throw error;
        }
        const policyRequest = applyResolvedAgentSkillSelection(
          request,
          resolvedSelection
        );
        const agentPolicy = classifyAgentRequest(policyRequest, {
          notebookLmProfile: this.notebookLmProfile
        });
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

        if (request.execution_options?.dry_run === true) {
          const expectedOutputs =
            request.agent_backend === "openclaw_cli"
              ? normalizeOpenClawOptions({ request, executionId }).expected_outputs
              : request.expected_outputs ?? [];
          const result = normalizeCompletedResult({
            executionId,
            resultType: "json",
            result: {
              dry_run: true,
              request_type: request.request_type,
              backend: request.agent_backend,
              provider_available: true,
              policy: {
                mode: agentPolicy.mode,
                permission_scope: agentPolicy.permissionScope,
                risk_class: agentPolicy.riskClass,
                workspace_access: agentPolicy.workspaceAccess,
                provider_state_access: agentPolicy.providerStateAccess,
                provider_state_labels: agentPolicy.providerStateLabels,
                network_access: agentPolicy.networkAccess,
                reason: agentPolicy.reason,
                matched_terms: agentPolicy.matchedTerms
              },
              confirmation_required:
                agentPolicy.mode === "require_confirmation",
              blocked: agentPolicy.mode === "blocked",
              artifacts: request.artifact_refs ?? [],
              expected_outputs: expectedOutputs,
              ...(resolvedSelection
                ? {
                    agent_skill_selection:
                      projectAgentSkillSelection(resolvedSelection)
                  }
                : {}),
              side_effects_executed: false
            },
            logsSummary:
              "Agent dry run completed. No provider, staging, bridge, or persistence operation was invoked."
          });
          await this.persistResult(request, result);
          return result;
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
              provider_state_access: agentPolicy.providerStateAccess,
              provider_state_labels: agentPolicy.providerStateLabels,
              network_access: agentPolicy.networkAccess,
              policy_reason: agentPolicy.reason,
              matched_terms: agentPolicy.matchedTerms
            },
            recoverable: false,
            suggestedAction:
              "Use a non-destructive request or adjust the agent policy."
          });
        }

        const operationPlan = createAgentOperationPlan(
          policyRequest,
          agentPolicy,
          resolvedSelection
        );
        const agentPolicySnapshot = {
          backend: request.agent_backend,
          matched_terms: agentPolicy.matchedTerms,
          mode: agentPolicy.mode,
          network_access: agentPolicy.networkAccess,
          provider_state_access: agentPolicy.providerStateAccess,
          provider_state_labels: agentPolicy.providerStateLabels,
          operation_plan: operationPlan,
          permission_scope: agentPolicy.permissionScope,
          policy_reason: agentPolicy.reason,
          request_type: request.request_type,
          risk_class: agentPolicy.riskClass,
          workspace_access: agentPolicy.workspaceAccess
        };
        if (agentPolicy.mode === "require_confirmation") {
          if (!options?.approvedConfirmation) {
            return this.pauseForConfirmation({
              executionId,
              logsSummary:
                "Execution paused because agent confirmation is required.",
              permissionScope: agentPolicy.permissionScope,
              policySnapshot: agentPolicySnapshot,
              request,
              resultDetails: {
                backend: request.agent_backend,
                risk_class: agentPolicy.riskClass,
                workspace_access: agentPolicy.workspaceAccess,
                provider_state_access: agentPolicy.providerStateAccess,
                provider_state_labels: agentPolicy.providerStateLabels,
                network_access: agentPolicy.networkAccess,
                policy_reason: agentPolicy.reason,
                ...(agentPolicy.matchedTerms.length > 0
                  ? { matched_terms: agentPolicy.matchedTerms }
                  : {})
              },
              toolId: request.agent_backend
            });
          }
          this.assertPolicySnapshot(
            options.approvedConfirmation.policySnapshot,
            agentPolicySnapshot
          );
        } else if (options?.approvedConfirmation) {
          this.throwPolicyChanged();
        }

        const artifactScope = {
          appId: request.app_id,
          sessionId: request.session_id
        };
        const releaseArtifactLeases = this.artifactReferenceCoordinator?.acquire(
          (request.artifact_refs ?? []).map((reference) => ({
            ...artifactScope,
            artifactId: reference.artifact_id
          }))
        ) ?? (() => undefined);
        let agentResult: AgentProviderResult;
        try {
        let resolvedArtifacts: ResolvedAgentArtifact[] = [];
        if (request.agent_backend === "codex_cli" && request.artifact_refs?.length) {
          try {
            if (!this.resolveAgentArtifacts) {
              throw new Error("Agent artifact resolver is not configured.");
            }
            resolvedArtifacts = await this.resolveAgentArtifacts({
              appId: request.app_id,
              sessionId: request.session_id,
              backend: request.agent_backend,
              refs: request.artifact_refs
            });
          } catch (error) {
            throw new AppError({
              code: "CODEX_ARTIFACT_RESOLUTION_FAILED",
              message: "Selected artifacts could not be resolved for Codex.",
              errorClass: "validation",
              httpStatus: 400,
              details: {
                cause_code:
                  error instanceof AppError ? error.code : "ARTIFACT_RESOLUTION_FAILED",
                cause: error instanceof Error ? error.message : String(error)
              },
              recoverable: true,
              suggestedAction:
                "Select ready artifacts from the current app session and retry."
            });
          }
        }
        const providerContext: AgentProviderExecutionContext = {
          execution_id: executionId,
          ...(resolvedSelection
            ? { agent_skill_selection: projectAgentSkillSelection(resolvedSelection) }
            : {}),
          authorization: {
            state: options?.approvedConfirmation ? "confirmed" : "not_required",
            permission_scope: agentPolicy.permissionScope,
            policy_fingerprint: fingerprintAgentPolicy(agentPolicySnapshot),
            ...(options?.approvedConfirmation?.confirmedAt
              ? { confirmed_at: options.approvedConfirmation.confirmedAt }
              : {})
          },
          access_policy: {
            workspace_access: agentPolicy.workspaceAccess,
            provider_state_access: agentPolicy.providerStateAccess,
            provider_state_labels: agentPolicy.providerStateLabels,
            network_access: agentPolicy.networkAccess
          },
          operation_plan: operationPlan,
          resolved_artifacts: resolvedArtifacts,
          expected_outputs: request.expected_outputs ?? []
        };
        const interactiveRequirement = this.interactiveRequirementResolver?.({
          request,
          selection: resolvedSelection
        }) ?? null;
        if (interactiveRequirement) {
          if (!this.interactiveSessionManager || !this.executionStore) {
            throw new AppError({
              code: "INTERACTIVE_EXECUTION_NOT_CONFIGURED",
              message: "Interactive Agent execution is not configured.",
              errorClass: "validation",
              httpStatus: 503,
              recoverable: true,
              suggestedAction: "Enable a compatible interactive Agent adapter."
            });
          }
          const scope = {
            appId: request.app_id,
            executionId,
            sessionId: request.session_id
          };
          const current = await this.executionStore.get(scope);
          if (!current) {
            await this.executionStore.save({
              executionId,
              request,
              result: interactiveRunningResult(executionId)
            });
          } else if (
            current.status === "pending_confirmation" &&
            options?.approvedConfirmation
          ) {
            await this.executionStore.transition({
              scope,
              from: ["pending_confirmation"],
              result: interactiveRunningResult(executionId)
            });
          }
          await this.interactiveSessionManager.start({
            policy: agentPolicy,
            providerContext,
            request: policyRequest,
            requiredInteractionTypes:
              interactiveRequirement.requiredInteractionTypes,
            ...(interactiveRequirement.requiredRecoveryClass
              ? {
                  requiredRecoveryClass:
                    interactiveRequirement.requiredRecoveryClass
                }
              : {}),
            scope
          });
          return (
            (await this.executionStore.get(scope)) ??
            normalizeFailedResult({
              executionId,
              error: {
                code: "INTERACTIVE_EXECUTION_STATE_MISSING",
                message: "Interactive execution state was not persisted.",
                recoverable: true,
                suggested_action: "Retry the Agent execution."
              },
              logsSummary: "Interactive execution state is unavailable."
            })
          );
        }
        agentResult = await provider.execute(
          policyRequest,
          agentPolicy,
          providerContext
        );
        } finally {
          releaseArtifactLeases();
        }
        const providerStatus = agentResult.status ?? "completed";
        const result = normalizeTerminalResult({
          executionId,
          status: providerStatus,
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
          logsSummary:
            providerStatus === "completed"
              ? `${provider.backend} agent request completed.`
              : providerStatus === "partial"
                ? `${provider.backend} agent request completed with warnings.`
                : `${provider.backend} agent request failed.`
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

      const confirmationDecisions: Array<{
        scope: string;
        tool_id: string;
      }> = [];
      const blockedDecisions: Array<{
        scope: string;
        tool_id: string;
      }> = [];
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

        const blockedDecision = decisions.find(
          (decision) => decision.mode === "blocked"
        );
        if (blockedDecision) {
          blockedDecisions.push({
            scope: blockedDecision.scope,
            tool_id: tool.id
          });
        }

        confirmationDecisions.push(
          ...decisions
            .filter((decision) => decision.mode === "require_confirmation")
            .map((decision) => ({
              scope: decision.scope,
              tool_id: tool.id
            }))
        );
      }

      if (request.execution_options?.dry_run === true) {
        const result = normalizeCompletedResult({
          executionId,
          resultType: "json",
          result: {
            dry_run: true,
            request_type: request.request_type,
            skill_id: skill.id,
            validated: true,
            required_tools: skill.requiredTools,
            policy: {
              blocked: blockedDecisions,
              confirmation_required: confirmationDecisions
            },
            blocked: blockedDecisions.length > 0,
            confirmation_required: confirmationDecisions.length > 0,
            side_effects_executed: false
          },
          logsSummary:
            "Skill dry run completed. No workflow or tool was invoked."
        });
        await this.persistResult(request, result);
        return result;
      }

      const firstBlockedDecision = blockedDecisions[0];
      if (firstBlockedDecision) {
        throw new AppError({
          code: "PERMISSION_BLOCKED",
          message: "Tool execution is blocked by policy.",
          errorClass: "permission",
          httpStatus: 403,
          details: {
            tool_id: firstBlockedDecision.tool_id,
            permission_scope: firstBlockedDecision.scope
          },
          recoverable: false,
          suggestedAction:
            "Update the permission policy or use a different tool."
        });
      }

      const skillPolicySnapshot = {
        mode: "require_confirmation",
        permissions: confirmationDecisions,
        request_type: request.request_type,
        skill_id: skill.id
      };
      if (confirmationDecisions.length > 0) {
        if (!options?.approvedConfirmation) {
          const firstDecision = confirmationDecisions[0]!;
          return this.pauseForConfirmation({
            executionId,
            logsSummary: "Execution paused because confirmation is required.",
            permissionScope: firstDecision.scope,
            policySnapshot: skillPolicySnapshot,
            request,
            toolId: firstDecision.tool_id
          });
        }
        this.assertPolicySnapshot(
          options.approvedConfirmation.policySnapshot,
          skillPolicySnapshot
        );
      } else if (options?.approvedConfirmation) {
        this.throwPolicyChanged();
      }

      const executableRequest = await this.resolveSkillArtifactInputs(request);
      const context = this.createContext(
        executableRequest,
        options?.approvedConfirmation !== undefined
      );
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

  getConfirmationService(): ConfirmationService {
    return this.confirmationService;
  }

  private async resolveSkillArtifactInputs(
    request: ExecuteSkillRequest
  ): Promise<ExecuteSkillRequest> {
    const refs = Array.isArray(request.input.artifactRefs)
      ? request.input.artifactRefs
      : [];
    if (refs.length === 0) {
      return request;
    }

    const resolvedInput = { ...request.input };
    const resolvedFields = new Map<string, string[]>();
    for (const candidate of refs) {
      if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) {
        continue;
      }
      const ref = candidate as Record<string, unknown>;
      const artifactId = String(ref.artifact_id ?? "").trim();
      const fieldName = String(ref.field_name ?? "").trim();
      const consumption =
        ref.consumption && typeof ref.consumption === "object"
          ? ref.consumption as Record<string, unknown>
          : {};
      const mode = String(consumption.resolved_mode ?? "").trim();
      if (!artifactId || !fieldName || mode !== "file_backed") {
        continue;
      }
      const requestedValues = Array.isArray(request.input[fieldName])
        ? request.input[fieldName] as unknown[]
        : [request.input[fieldName]];
      if (!requestedValues.some((value) => String(value ?? "").trim() === artifactId)) {
        throw new AppError({
          code: "ARTIFACT_REFERENCE_INVALID",
          message: "Artifact reference does not match its declared input field.",
          errorClass: "validation",
          httpStatus: 400,
          details: { artifact_id: artifactId, field_name: fieldName },
          recoverable: true,
          suggestedAction: "Select the artifact again and resubmit the skill."
        });
      }
      if (!this.resolveScopedSkillArtifactFile) {
        throw new AppError({
          code: "ARTIFACT_RESOLUTION_FAILED",
          message: "Scoped artifact file resolution is unavailable.",
          errorClass: "tool",
          httpStatus: 500,
          details: { artifact_id: artifactId, field_name: fieldName },
          recoverable: true,
          suggestedAction: "Configure the execution artifact store and retry."
        });
      }
      const absolutePath = await this.resolveScopedSkillArtifactFile({
        appId: request.app_id,
        artifactId,
        sessionId: request.session_id
      });
      resolvedFields.set(fieldName, [
        ...(resolvedFields.get(fieldName) ?? []),
        absolutePath
      ]);
    }

    for (const [fieldName, values] of resolvedFields) {
      resolvedInput[fieldName] = Array.isArray(request.input[fieldName])
        ? values
        : values[0];
    }
    return { ...request, input: resolvedInput };
  }

  private createContext(
    request: ExecuteSkillRequest,
    confirmed: boolean
  ): ExecutionContext {
    return {
      confirmed,
      executionId: null,
      request,
      executionOptions: request.execution_options ?? { dry_run: false },
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

  private async resolveAgentSkillSelection(
    request: Extract<ExecutionRequest, { request_type: "execute_agent" }>
  ): Promise<ResolvedAgentSkillSelection | null> {
    if (this.agentSkillSelectionService) {
      return this.agentSkillSelectionService.resolve(request);
    }
    if (request.agent_skill_ref) {
      throw new AppError({
        code: "AGENT_SKILL_RESOLUTION_UNAVAILABLE",
        message: "Agent skill selection cannot be resolved by this execution engine.",
        errorClass: "validation",
        httpStatus: 503,
        recoverable: true,
        suggestedAction: "Configure the synchronized Agent skill selection service."
      });
    }
    return null;
  }

  private async pauseForConfirmation(input: {
    executionId: string;
    logsSummary: string;
    permissionScope: string;
    policySnapshot: Record<string, unknown>;
    request: ExecutionRequest;
    resultDetails?: Record<string, unknown>;
    toolId: string;
  }): Promise<NormalizedExecutionResult> {
    const confirmation = await this.confirmationService.issue({
      appId: input.request.app_id,
      executionId: input.executionId,
      policySnapshot: input.policySnapshot,
      sessionId: input.request.session_id
    });
    const result = normalizePendingConfirmationResult({
      executionId: input.executionId,
      toolId: input.toolId,
      permissionScope: input.permissionScope,
      logsSummary: input.logsSummary,
      resultDetails: {
        ...(input.resultDetails ?? {}),
        ...confirmation
      }
    });
    await this.persistResult(input.request, result);
    return result;
  }

  private assertPolicySnapshot(
    approved: Record<string, unknown>,
    current: Record<string, unknown>
  ): void {
    if (this.stableStringify(approved) !== this.stableStringify(current)) {
      this.throwPolicyChanged();
    }
  }

  private throwPolicyChanged(): never {
    throw new AppError({
      code: "CONFIRMATION_POLICY_CHANGED",
      message: "Execution policy changed after confirmation was issued.",
      errorClass: "permission",
      httpStatus: 409,
      recoverable: true,
      suggestedAction: "Submit the execution again for a new confirmation."
    });
  }

  private stableStringify(value: unknown): string {
    if (Array.isArray(value)) {
      return `[${value.map((item) => this.stableStringify(item)).join(",")}]`;
    }
    if (value && typeof value === "object") {
      const record = value as Record<string, unknown>;
      return `{${Object.keys(record)
        .sort()
        .map(
          (key) =>
            `${JSON.stringify(key)}:${this.stableStringify(record[key])}`
        )
        .join(",")}}`;
    }
    return JSON.stringify(value);
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

function interactiveRunningResult(executionId: string): NormalizedExecutionResult {
  return {
    execution_id: executionId,
    status: "running",
    result_type: "json",
    result: {},
    files: [],
    errors: [],
    logs_summary: "Interactive Agent execution is starting."
  };
}
