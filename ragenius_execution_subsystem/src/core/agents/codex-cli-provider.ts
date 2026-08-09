import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";
import type { CodexCliProviderConfig } from "../../config/provider-config.js";
import { AppError } from "../errors/app-error.js";
import type { AgentPolicyDecision } from "./agent-policy.js";
import type { AgentProvider } from "./agent-provider.js";
import type { AgentProviderExecutionContext } from "./agent-provider-context.js";
import {
  mergeAgentDiagnostics,
  primaryDiagnosticFromLegacy
} from "./agent-diagnostics.js";

import { executeCodexCliBridge } from "./codex-cli-bridge.js";
import type {
  AgentOutputPersistenceSpec,
  PersistedAgentOutputArtifact,
  VerifiedAgentOutput
} from "./agent-output-artifact-persister.js";
import { buildCodexPrompt } from "./codex-prompt-builder.js";
import { evaluateCodexResult } from "./codex-result-evaluator.js";
import {
  cleanupCodexRunWorkspaces,
  createCodexRunWorkspace,
  planCodexExpectedOutputs,
  stageCodexArtifacts,
  verifyCodexOutputArtifacts
} from "./codex-workspace.js";
import type { CodexRunWorkspace } from "./codex-workspace.js";
import type {
  CodexCliBridgeRequest,
  CodexCliBridgeResponse,
  CodexCliBridgeSuccessResult,
  CodexNormalizedResult,
  CodexOutputVerification,
  CodexStagedArtifact
} from "./codex-cli-types.js";
import { activationFromCodex } from "../agent-skills/agent-skill-activation-evidence.js";

type CodexCliBridgeExecutor = (
  config: CodexCliProviderConfig,
  request: CodexCliBridgeRequest
) => Promise<CodexCliBridgeResponse>;

type CodexCliProviderDependencies = {
  createWorkspace?: (input: {
    runRoot: string;
    executionId: string;
  }) => Promise<CodexRunWorkspace>;
  stageArtifacts?: (input: {
    workspace: CodexRunWorkspace;
    artifacts: AgentProviderExecutionContext["resolved_artifacts"];
  }) => Promise<CodexStagedArtifact[]>;
  buildPrompt?: typeof buildCodexPrompt;
  evaluateResult?: typeof evaluateCodexResult;
  verifyOutputs?: (input: {
    workspace: CodexRunWorkspace;
    expectedOutputs: ReturnType<typeof planCodexExpectedOutputs>;
    reportedArtifacts: CodexNormalizedResult["artifacts"];
  }) => Promise<CodexOutputVerification[]>;
  persistOutput?: (input: {
    request: ExecuteAgentRequest;
    executionId: string;
    output: AgentOutputPersistenceSpec;
    verification: VerifiedAgentOutput;
  }) => Promise<PersistedAgentOutputArtifact>;
  cleanupWorkspaces?: typeof cleanupCodexRunWorkspaces;
  finalizeResult?: (input: {
    request: ExecuteAgentRequest;
    context: AgentProviderExecutionContext;
    result: CodexNormalizedResult;
  }) => Promise<CodexNormalizedResult>;
};

export class CodexCliProvider implements AgentProvider {
  readonly backend = "codex_cli" as const;

  constructor(
    private readonly config: CodexCliProviderConfig,
    private readonly bridgeExecutor: CodexCliBridgeExecutor = executeCodexCliBridge,
    private readonly dependencies: CodexCliProviderDependencies = {}
  ) {}

  async execute(
    request: ExecuteAgentRequest,
    policy: AgentPolicyDecision,
    context: AgentProviderExecutionContext
  ): Promise<CodexCliBridgeSuccessResult | CodexNormalizedResult> {
    if (!this.config.enabled) {
      throw new AppError({
        code: "CODEX_CLI_NOT_ENABLED",
        message: "Codex CLI agent execution is not enabled.",
        errorClass: "validation",
        httpStatus: 400,
        details: {
          backend: "codex_cli"
        },
        recoverable: true,
        suggestedAction:
          "Set CODEX_CLI_ENABLED=true and configure the Codex CLI bridge command."
      });
    }

    const runRoot = this.config.runRoot ?? "storage/codex-runs";
    const runRetentionHours = this.config.runRetentionHours ?? 24;
    const maxOutputBytes = this.config.maxOutputBytes ?? 16384;
    const sandboxMode = this.config.sandboxMode ?? "workspace-write";
    const createWorkspace =
      this.dependencies.createWorkspace ?? createCodexRunWorkspace;
    const stageArtifacts =
      this.dependencies.stageArtifacts ?? stageCodexArtifacts;
    const cleanupWorkspaces =
      this.dependencies.cleanupWorkspaces ?? cleanupCodexRunWorkspaces;
    let workspace: CodexRunWorkspace | undefined;
    try {
      workspace = await createWorkspace({
        runRoot,
        executionId: context.execution_id
      });
      let stagedArtifacts: CodexStagedArtifact[];
      try {
        stagedArtifacts = await stageArtifacts({
          workspace,
          artifacts: context.resolved_artifacts
        });
      } catch (error) {
        throw new AppError({
          code: "CODEX_ARTIFACT_STAGING_FAILED",
          message: "Codex artifact staging failed.",
          errorClass: "validation",
          httpStatus: 400,
          details: {
            cause: error instanceof Error ? error.message : String(error)
          },
          recoverable: true,
          suggestedAction: "Re-select the artifact and retry the Codex execution."
        });
      }
      const expectedOutputs = planCodexExpectedOutputs(request);
      const effectiveSkillName =
        context.agent_skill_selection?.provider_skill_name ??
        request.agent_skill_hint;
      const prompt = (this.dependencies.buildPrompt ?? buildCodexPrompt)({
        request,
        context,
        stagedArtifacts,
        expectedOutputs
      });
      let response: CodexCliBridgeResponse;
      try {
        response = await this.bridgeExecutor(this.config, {
        app_id: request.app_id,
        session_id: request.session_id,
        agent_query: request.agent_query,
        ...(effectiveSkillName
          ? { agent_skill_hint: effectiveSkillName }
          : {}),
        ...(request.approved_content_id
          ? { approved_content_id: request.approved_content_id }
          : {}),
        ...(request.approved_revision_id
          ? { approved_revision_id: request.approved_revision_id }
          : {}),
        ...(request.context ? { context: request.context } : {}),
        prompt,
        workspace_absolute_path: workspace.root_absolute_path,
        sandbox_mode: sandboxMode,
        max_output_bytes: maxOutputBytes,
        policy: {
          risk_class: policy.riskClass,
          workspace_access: policy.workspaceAccess,
          provider_state_access: policy.providerStateAccess,
          provider_state_labels: policy.providerStateLabels,
          network_access: policy.networkAccess,
          reason: policy.reason,
          ...(policy.matchedTerms.length > 0
            ? { matched_terms: policy.matchedTerms }
            : {})
          }
        });
      } catch (error) {
        throw new AppError({
          code: "CODEX_CLI_BRIDGE_FAILED",
          message: "Codex CLI bridge execution failed.",
          errorClass: "tool",
          httpStatus: 502,
          details: {
            error: error instanceof Error ? error.message : String(error),
            command: this.config.command,
            args: this.config.args,
            bridge_script: this.config.bridgeScript,
            node_command: this.config.nodeCommand,
            timeout_ms: this.config.timeoutMs
          },
          recoverable: true,
          suggestedAction:
            "Inspect the Codex CLI command configuration and retry the agent request."
        });
      }

      if (!response.ok) {
        throw new AppError({
          code: response.error.code || "CODEX_CLI_EXECUTION_FAILED",
          message: response.error.message || "Codex CLI execution failed.",
          errorClass: "tool",
          httpStatus: 502,
          details: response.error.details,
          recoverable: response.error.recoverable ?? true,
          suggestedAction:
            response.error.suggested_action ||
            "Inspect the Codex CLI command output and retry the request."
        });
      }

      if (!("turn_status" in response.result)) {
        return {
          ...response.result,
          agent_skill_activation: activationFromCodex({
            selection: context.agent_skill_selection,
            commandEvents: [],
            reportedSkillNames: response.result.activated_skills ?? []
          })
        };
      }
      let normalized = (this.dependencies.evaluateResult ?? evaluateCodexResult)({
        context,
        protocol: response.result,
        stagedInputs: stagedArtifacts,
        ...(effectiveSkillName
          ? { agentSkillHint: effectiveSkillName }
          : {})
      });
      normalized.provider_metadata = {
        ...normalized.provider_metadata,
        provider_state_access: policy.providerStateAccess,
        provider_state_labels: policy.providerStateLabels
      };
      normalized.agent_skill_activation = activationFromCodex({
        selection: context.agent_skill_selection,
        commandEvents: response.result.command_events,
        reportedSkillNames: normalized.activated_skills,
        providerFailed: normalized.status === "failed"
      });
      if (this.dependencies.finalizeResult) {
        normalized = await this.dependencies.finalizeResult({
          request,
          context,
          result: normalized
        });
      }
      const reportedOutputs = normalized.reported_outputs ?? normalized.artifacts;
      if (expectedOutputs.length === 0) {
        return {
          ...normalized,
          reported_outputs: reportedOutputs,
          artifacts: []
        };
      }

      const verificationResults = await (
        this.dependencies.verifyOutputs ?? verifyCodexOutputArtifacts
      )({
        workspace,
        expectedOutputs,
        reportedArtifacts: reportedOutputs
      });
      const persistedArtifacts: PersistedAgentOutputArtifact[] = [];
      const failedOutputs: Array<{
        required: boolean;
        outputId: string;
        message: string;
      }> = [];

      for (const output of expectedOutputs) {
        if (!output.persist_as_artifact) {
          continue;
        }
        const verification = verificationResults.find(
          (candidate) => candidate.output_id === output.output_id
        );
        if (!verification?.verified) {
          failedOutputs.push({
            required: output.required,
            outputId: output.output_id,
            message: verification?.failure_message ?? "Codex output verification failed."
          });
          continue;
        }
        if (!this.dependencies.persistOutput) {
          failedOutputs.push({
            required: output.required,
            outputId: output.output_id,
            message: "Codex output persistence is not configured."
          });
          continue;
        }
        try {
          persistedArtifacts.push(await this.dependencies.persistOutput({
            request,
            executionId: context.execution_id,
            output,
            verification
          }));
        } catch (error) {
          failedOutputs.push({
            required: output.required,
            outputId: output.output_id,
            message: error instanceof Error
              ? error.message
              : "Codex output persistence failed."
          });
        }
      }

      const requiredFailure = failedOutputs.some((failure) => failure.required);
      const persistenceFailure = failedOutputs[0];
      return {
        ...normalized,
        status: requiredFailure
          ? "failed"
          : failedOutputs.length > 0 && normalized.status === "completed"
            ? "partial"
            : normalized.status,
        reported_outputs: reportedOutputs,
        artifacts: persistedArtifacts,
        ...(persistenceFailure
          ? {
              diagnostics: {
                ...normalized.diagnostics,
                ...mergeAgentDiagnostics(
                  primaryDiagnosticFromLegacy(normalized.diagnostics),
                  [{
                    stage: "persistence",
                    code: requiredFailure
                      ? "CODEX_REQUIRED_OUTPUT_PERSIST_FAILED"
                      : "CODEX_OUTPUT_PERSIST_FAILED",
                    message: `${persistenceFailure.outputId}: ${persistenceFailure.message}`
                  }]
                )
              }
            }
          : {})
      };
    } finally {
      if (workspace) {
        await cleanupWorkspaces({
          runRoot,
          currentExecutionId: context.execution_id,
          retentionHours: runRetentionHours
        });
      }
    }
  }
}
