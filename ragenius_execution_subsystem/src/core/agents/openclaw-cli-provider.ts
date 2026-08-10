import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";
import { AppError } from "../errors/app-error.js";

import type { AgentPolicyDecision } from "./agent-policy.js";
import type { AgentProvider } from "./agent-provider.js";
import type { AgentProviderExecutionContext } from "./agent-provider-context.js";
import type {
  AgentArtifactResolverInput,
  ResolvedAgentArtifact
} from "./agent-artifact-resolver.js";
import {
  executeOpenClawCliBridge,
  type OpenClawCliBridgeResult
} from "./openclaw-cli-bridge.js";
import type {
  OpenClawProviderMetadata,
  OpenClawProviderResult,
  OpenClawStagedInput,
  OpenClawExpectedOutput,
  OpenClawVerificationResult
} from "./openclaw-cli-types.js";
import { normalizeOpenClawOptions } from "./openclaw-options.js";
import { buildOpenClawPrompt } from "./openclaw-prompt-builder.js";
import {
  buildOpenClawRunWorkspaceRoot,
  cleanupOpenClawRunWorkspacesViaWsl,
  inspectOpenClawWorkspaceFileViaWsl,
  stageResolvedAgentArtifactsForOpenClaw,
  transferOpenClawFileViaWsl,
  transferOpenClawInputViaWsl,
  verifyOpenClawOutputs
} from "./openclaw-workspace.js";
import {
  activationFromOpenClaw,
  extractOpenClawSessionFile,
  readContainedOpenClawSessionTrace
} from "../agent-skills/agent-skill-activation-evidence.js";

type PersistedAgentOutputArtifact = {
  artifact_id: string;
  artifact_type: "agent_output";
  display_name: string;
  mime_type?: string;
};

export type OpenClawCliProviderConfig = {
  enabled: boolean;
  wslDistro: string;
  command: string;
  agentId: string;
  workspaceRoot: string;
  timeoutMs: number;
  maxStdoutBytes?: number;
  maxStderrBytes?: number;
  runRetentionHours?: number;
};

export type OpenClawCliProviderDependencies = {
  bridge?: (input: {
    config: {
      wslDistro: string;
      command: string;
      agentId: string;
      timeoutMs: number;
      maxStdoutBytes: number;
      maxStderrBytes: number;
    };
    sessionKey: string;
    prompt: string;
  }) => Promise<OpenClawCliBridgeResult>;
  verifyOutputs?: (input: {
    workspaceRoot: string;
    expectedOutputs: ReturnType<typeof normalizeOpenClawOptions>["expected_outputs"];
  }) => Promise<OpenClawVerificationResult[]>;
  resolveArtifacts?: (
    input: AgentArtifactResolverInput
  ) => Promise<ResolvedAgentArtifact[]>;
  stageArtifacts?: (input: {
    workspaceRoot: string;
    artifacts: ResolvedAgentArtifact[];
  }) => Promise<OpenClawStagedInput[]>;
  persistOutput?: (input: {
    request: ExecuteAgentRequest;
    executionId: string;
    output: OpenClawExpectedOutput;
    verification: OpenClawVerificationResult;
  }) => Promise<PersistedAgentOutputArtifact>;
  cleanupRuns?: (input: {
    workspaceRoot: string;
    currentExecutionId: string;
    retentionHours: number;
  }) => Promise<void>;
  finalizeResult?: (input: {
    request: ExecuteAgentRequest;
    context: AgentProviderExecutionContext;
    result: OpenClawProviderResult;
  }) => Promise<OpenClawProviderResult>;
  readActivationTrace?: (input: {
    wslDistro: string;
    agentId: string;
    sessionFile: string;
    workspaceRoot?: string;
  }) => Promise<string>;
};

export class OpenClawCliProvider implements AgentProvider {
  readonly backend = "openclaw_cli" as const;

  constructor(
    private readonly config: OpenClawCliProviderConfig,
    private readonly dependencies: OpenClawCliProviderDependencies = {}
  ) {}

  async execute(
    request: ExecuteAgentRequest,
    policy: AgentPolicyDecision,
    context?: AgentProviderExecutionContext | { executionId?: string }
  ): Promise<OpenClawProviderResult> {
    if (!this.config.enabled) {
      throw new AppError({
        code: "OPENCLAW_CLI_NOT_ENABLED",
        message: "OpenClaw CLI agent execution is not enabled.",
        errorClass: "validation",
        httpStatus: 400,
        details: { backend: this.backend },
        recoverable: true,
        suggestedAction:
          "Set OPENCLAW_CLI_ENABLED=true and configure the OpenClaw CLI bridge."
      });
    }

    const executionId = context
      ? "execution_id" in context
        ? context.execution_id
        : context.executionId ?? "execution_unknown"
      : "execution_unknown";
    const runWorkspaceRoot = buildOpenClawRunWorkspaceRoot(
      this.config.workspaceRoot,
      executionId
    );
    if (this.config.runRetentionHours) {
      const cleanupRuns =
        this.dependencies.cleanupRuns ??
        ((input: {
          workspaceRoot: string;
          currentExecutionId: string;
          retentionHours: number;
        }) =>
          cleanupOpenClawRunWorkspacesViaWsl({
            wslDistro: this.config.wslDistro,
            ...input
          }));
      await cleanupRuns({
        workspaceRoot: this.config.workspaceRoot,
        currentExecutionId: executionId,
        retentionHours: this.config.runRetentionHours
      });
    }
    const normalizedOptions = normalizeOpenClawOptions({ request, executionId });
    const stagedArtifactInputs = await this.resolveAndStageArtifacts(
      request,
      runWorkspaceRoot
    );
    const options = {
      ...normalizedOptions,
      staged_inputs: [
        ...normalizedOptions.staged_inputs,
        ...stagedArtifactInputs
      ]
    };
    const sessionKey =
      options.session_key ??
      buildOpenClawSessionKey({
        appId: request.app_id,
        sessionId: request.session_id,
        executionId
      });
    const prompt = buildOpenClawPrompt({
      request,
      workspaceRoot: runWorkspaceRoot,
      options,
      ...(context && "execution_id" in context && context.agent_skill_selection
        ? { selection: context.agent_skill_selection }
        : {})
    });
    const bridge = this.dependencies.bridge ?? ((bridgeInput) =>
      executeOpenClawCliBridge(bridgeInput));
    const bridgeResult = await bridge({
      config: {
        wslDistro: this.config.wslDistro,
        command: this.config.command,
        agentId: this.config.agentId,
        timeoutMs: options.timeout_ms ?? this.config.timeoutMs,
        maxStdoutBytes:
          options.max_stdout_bytes ?? this.config.maxStdoutBytes ?? 262144,
        maxStderrBytes:
          options.max_stderr_bytes ?? this.config.maxStderrBytes ?? 65536
      },
      sessionKey,
      prompt
    });
    const inspectedVerificationResults =
      options.expected_outputs.length > 0
        ? await this.verifyExpectedOutputs(
            options.expected_outputs,
            runWorkspaceRoot
          )
        : [];
    const verificationResults = await this.persistVerifiedOutputs({
      request,
      executionId,
      expectedOutputs: options.expected_outputs,
      verificationResults: inspectedVerificationResults.map((result) => ({
        ...result,
        verification_status:
          result.verification_status ??
          (result.verified ? "verified" : "failed")
      }))
    });
    const requiredFailures = verificationResults.filter(
      (result) => result.required && !result.verified
    );
    const requiredPersistenceFailure = verificationResults.find(
      (result) => result.required && result.persistence_status === "failed"
    );
    const optionalPersistenceFailure = verificationResults.find(
      (result) => !result.required && result.persistence_status === "failed"
    );
    const nonzeroExit =
      typeof bridgeResult.exitCode === "number" && bridgeResult.exitCode !== 0;
    const outputText = extractOutputText(bridgeResult);
    const taskFailure = classifyOpenClawTaskFailure(outputText);
    const status =
      bridgeResult.timedOut ||
      nonzeroExit ||
      requiredFailures.length > 0 ||
      requiredPersistenceFailure ||
      taskFailure.failed
        ? "failed"
        : optionalPersistenceFailure
          ? "partial"
        : "completed";
    const providerMetadata = this.buildMetadata({
      policy,
      sessionKey,
      executionMode: options.execution_mode,
      bridgeResult,
      expectedOutputCount: options.expected_outputs.length,
      requiredOutputCount: options.expected_outputs.filter((output) => output.required)
        .length,
      verifiedOutputCount: verificationResults.filter((result) => result.verified)
        .length,
      runWorkspaceRoot
    });
    const trustedContext = context && "execution_id" in context
      ? context
      : undefined;
    let validatedSessionTrace: string | undefined;
    const sessionFile = extractOpenClawSessionFile(bridgeResult.json);
    if (trustedContext?.agent_skill_selection && sessionFile) {
      try {
        validatedSessionTrace = await (
          this.dependencies.readActivationTrace ?? readContainedOpenClawSessionTrace
        )({
          wslDistro: this.config.wslDistro,
          agentId: this.config.agentId,
          sessionFile,
          workspaceRoot: this.config.workspaceRoot
        });
      } catch {
        validatedSessionTrace = undefined;
      }
    }
    const result: OpenClawProviderResult = {
      status,
      summary:
        status === "completed"
          ? `OpenClaw completed and verified ${providerMetadata.verified_output_count} output(s).`
          : status === "partial"
            ? "OpenClaw completed, but an optional output could not be persisted."
          : taskFailure.message ??
            requiredFailures[0]?.failure_message ??
            requiredPersistenceFailure?.persistence_failure_message ??
            (bridgeResult.timedOut
              ? "OpenClaw execution timed out."
              : nonzeroExit
                ? "OpenClaw exited with a non-zero status."
              : "OpenClaw execution failed."),
      output_text: outputText,
      artifacts: verificationResults
        .filter(
          (result) =>
            result.verified && Boolean(result.persisted_artifact_id)
        )
        .map((result) => ({
          output_id: result.output_id,
          display_name:
            options.expected_outputs.find((output) => output.output_id === result.output_id)
              ?.display_name ??
            result.workspace_relative_path.split("/").at(-1) ??
            result.output_id,
          media_type: result.media_type ?? "application/octet-stream",
          role: "final",
          verified: true,
          ...(result.persisted_artifact_id
            ? { artifact_id: result.persisted_artifact_id }
            : {})
        })),
      reported_outputs: verificationResults
        .filter((result) => result.verified)
        .map((result) => {
          const output = options.expected_outputs.find(
            (candidate) => candidate.output_id === result.output_id
          );
          return {
            output_id: result.output_id,
            display_name:
              output?.display_name ??
              result.workspace_relative_path.split("/").at(-1) ??
              result.output_id,
            media_type: result.media_type ?? "application/octet-stream",
            workspace_relative_path: result.workspace_relative_path,
            verified: true,
            ...(typeof result.size_bytes === "number"
              ? { size_bytes: result.size_bytes }
              : {}),
            ...(result.sha256 ? { sha256: result.sha256 } : {})
          };
        }),
      provider_metadata: providerMetadata,
      verification_results: verificationResults,
      diagnostics: {
        ...(requiredFailures[0]?.failure_code
          ? { failure_code: requiredFailures[0].failure_code }
          : taskFailure.failed
            ? { failure_code: "agent_task_failed" }
          : bridgeResult.timedOut
            ? { failure_code: "provider_timeout" }
            : nonzeroExit
              ? { failure_code: "provider_nonzero_exit" }
              : requiredPersistenceFailure || optionalPersistenceFailure
                ? { failure_code: "persist_failed" }
            : {}),
        ...(requiredFailures[0]?.failure_message
          ? { failure_message: requiredFailures[0].failure_message }
          : taskFailure.detail
            ? { failure_message: taskFailure.detail }
          : (requiredPersistenceFailure ?? optionalPersistenceFailure)
                ?.persistence_failure_message
            ? {
                failure_message: (requiredPersistenceFailure ??
                  optionalPersistenceFailure)!
                  .persistence_failure_message
              }
          : {}),
        stdout_tail: bridgeResult.stdout,
        stderr_tail: bridgeResult.stderr,
        stdout_truncated: bridgeResult.stdoutTruncated,
        stderr_truncated: bridgeResult.stderrTruncated,
        redactions_applied: true
      },
      raw: {
        ...(bridgeResult.json !== undefined ? { json: bridgeResult.json } : {}),
        exit_code: bridgeResult.exitCode
      },
      agent_skill_activation: activationFromOpenClaw({
        selection: trustedContext?.agent_skill_selection,
        reportedText: outputText,
        ...(validatedSessionTrace ? { validatedSessionTrace } : {}),
        providerFailed: status === "failed"
      })
    };
    if (this.dependencies.finalizeResult && context && "execution_id" in context) {
      return this.dependencies.finalizeResult({
        request,
        context,
        result
      });
    }
    return result;
  }

  private async verifyExpectedOutputs(
    expectedOutputs: ReturnType<typeof normalizeOpenClawOptions>["expected_outputs"],
    runWorkspaceRoot: string
  ): Promise<OpenClawVerificationResult[]> {
    if (this.dependencies.verifyOutputs) {
      return this.dependencies.verifyOutputs({
        workspaceRoot: runWorkspaceRoot,
        expectedOutputs
      });
    }
    return verifyOpenClawOutputs({
      workspaceRoot: runWorkspaceRoot,
      expectedOutputs,
      inspectFile: async (workspaceAbsolutePath) =>
        inspectOpenClawWorkspaceFileViaWsl({
          wslDistro: this.config.wslDistro,
          workspaceAbsolutePath,
          allowedWorkspaceRoot: runWorkspaceRoot
        })
    });
  }

  private async persistVerifiedOutputs(input: {
    request: ExecuteAgentRequest;
    executionId: string;
    expectedOutputs: ReturnType<typeof normalizeOpenClawOptions>["expected_outputs"];
    verificationResults: OpenClawVerificationResult[];
  }): Promise<OpenClawVerificationResult[]> {
    if (!this.dependencies.persistOutput) {
      return input.verificationResults;
    }

    return Promise.all(
      input.verificationResults.map(async (verification) => {
        const output = input.expectedOutputs.find(
          (candidate) => candidate.output_id === verification.output_id
        );
        if (!output || !verification.verified || output.persist_as_artifact !== true) {
          return {
            ...verification,
            persistence_status: "not_requested" as const
          };
        }

        try {
          const artifact = await this.dependencies.persistOutput?.({
            request: input.request,
            executionId: input.executionId,
            output,
            verification
          });
          if (!artifact?.artifact_id) {
            return verification;
          }
          return {
            ...verification,
            persisted_artifact_id: artifact.artifact_id,
            persistence_status: "persisted" as const
          };
        } catch (error) {
          return {
            ...verification,
            persistence_status: "failed" as const,
            persistence_failure_code: "persist_failed" as const,
            persistence_failure_message:
              error instanceof Error
                ? error.message
                : "Failed to persist verified OpenClaw output."
          };
        }
      })
    );
  }

  private async resolveAndStageArtifacts(
    request: ExecuteAgentRequest,
    runWorkspaceRoot: string
  ): Promise<OpenClawStagedInput[]> {
    const refs = request.artifact_refs ?? [];
    if (refs.length === 0) {
      return [];
    }
    if (!this.dependencies.resolveArtifacts) {
      throw new AppError({
        code: "OPENCLAW_ARTIFACT_RESOLVER_NOT_CONFIGURED",
        message: "OpenClaw artifact reuse is not configured.",
        errorClass: "validation",
        httpStatus: 400,
        details: { backend: this.backend },
        recoverable: true,
        suggestedAction:
          "Configure the OpenClaw artifact resolver before reusing artifacts."
      });
    }

    const artifacts = await this.dependencies.resolveArtifacts({
      appId: request.app_id,
      sessionId: request.session_id,
      backend: this.backend,
      refs
    });

    try {
      if (this.dependencies.stageArtifacts) {
        return await this.dependencies.stageArtifacts({
          workspaceRoot: runWorkspaceRoot,
          artifacts
        });
      }

      return await stageResolvedAgentArtifactsForOpenClaw({
        workspaceRoot: runWorkspaceRoot,
        artifacts,
        transfer: async (input) =>
          transferOpenClawInputViaWsl({
            wslDistro: this.config.wslDistro,
            allowedWorkspaceRoot: runWorkspaceRoot,
            ...input
          }),
        transferFile: async (input) =>
          transferOpenClawFileViaWsl({
            wslDistro: this.config.wslDistro,
            ...input
          })
      });
    } catch (error) {
      throw new AppError({
        code: "OPENCLAW_ARTIFACT_STAGING_FAILED",
        message: "OpenClaw artifact staging failed.",
        errorClass: "tool",
        httpStatus: 502,
        details: {
          backend: this.backend,
          cause: error instanceof Error ? error.message : String(error)
        },
        recoverable: true,
        suggestedAction:
          "Retry the execution or inspect the OpenClaw WSL workspace configuration."
      });
    }
  }

  private buildMetadata(input: {
    policy: AgentPolicyDecision;
    sessionKey: string;
    executionMode: "read_only" | "output_required";
    bridgeResult: OpenClawCliBridgeResult;
    expectedOutputCount: number;
    requiredOutputCount: number;
    verifiedOutputCount: number;
    runWorkspaceRoot: string;
  }): OpenClawProviderMetadata {
    return {
      backend: this.backend,
      provider_name: "OpenClaw",
      invocation_mode: "wsl_cli",
      wsl_distro: this.config.wslDistro,
      openclaw_command: this.config.command,
      openclaw_agent_id: this.config.agentId,
      openclaw_session_key: input.sessionKey,
      execution_mode: input.executionMode,
      provider_state_access: input.policy.providerStateAccess,
      provider_state_labels: input.policy.providerStateLabels,
      expected_output_count: input.expectedOutputCount,
      required_output_count: input.requiredOutputCount,
      verified_output_count: input.verifiedOutputCount,
      run_workspace_root: input.runWorkspaceRoot,
      json_parse_status: input.bridgeResult.jsonParseStatus,
      raw_exit_code: input.bridgeResult.exitCode,
      timed_out: input.bridgeResult.timedOut,
      stdout_truncated: input.bridgeResult.stdoutTruncated,
      stderr_truncated: input.bridgeResult.stderrTruncated
    };
  }
}

export function buildOpenClawSessionKey(input: {
  appId: string;
  sessionId: string;
  executionId: string;
}): string {
  return `ragenius:${input.appId}:${input.sessionId}:${input.executionId}`;
}

function extractOutputText(bridgeResult: OpenClawCliBridgeResult): string {
  const json = bridgeResult.json;
  if (json && typeof json === "object" && "result" in json) {
    const result = (json as { result?: unknown }).result;
    if (result && typeof result === "object") {
      const record = result as {
        finalAssistantVisibleText?: unknown;
        payloads?: unknown;
      };
      if (
        typeof record.finalAssistantVisibleText === "string" &&
        record.finalAssistantVisibleText.trim()
      ) {
        return record.finalAssistantVisibleText;
      }
      if (Array.isArray(record.payloads)) {
        const firstTextPayload = record.payloads.find(
          (payload) =>
            payload &&
            typeof payload === "object" &&
            typeof (payload as { text?: unknown }).text === "string"
        ) as { text?: string } | undefined;
        if (firstTextPayload?.text) {
          return firstTextPayload.text;
        }
      }
    }
  }
  return bridgeResult.stdout.trim();
}

function classifyOpenClawTaskFailure(outputText: string): {
  failed: boolean;
  message?: string;
  detail?: string;
} {
  const normalized = outputText.replace(/\r\n/g, "\n").trim();
  if (!normalized) {
    return { failed: false };
  }

  const failurePatterns = [
    /(?:^|\n)\s*(?:\*\*)?(?:task outcome|task status|overall status|message sent[^:\n]*)(?:\*\*)?\s*:\s*(?:❌\s*)?(?:\*\*)?(failed|failure|blocked|forbidden|denied)(?:\*\*)?/i,
    /(?:request|action|message|task)\s+(?:was\s+)?(?:forbidden|denied|blocked|rejected|not permitted)/i,
    /no further actions can be taken/i,
    /tools\.sessions\.visibility=tree/i
  ];

  if (!failurePatterns.some((pattern) => pattern.test(normalized))) {
    return { failed: false };
  }

  return {
    failed: true,
    message: "OpenClaw reported that the requested task failed.",
    detail: extractFailureDetail(normalized)
  };
}

function extractFailureDetail(outputText: string): string {
  const lines = outputText
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const failureLine = lines.find((line) =>
    /failed|failure|forbidden|denied|blocked|not permitted|no further actions can be taken|tools\.sessions\.visibility=tree/i.test(
      line
    )
  );
  return failureLine?.slice(0, 500) ?? "OpenClaw reported task failure.";
}
