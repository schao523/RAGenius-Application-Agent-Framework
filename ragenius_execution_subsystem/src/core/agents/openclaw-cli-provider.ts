import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";
import { AppError } from "../errors/app-error.js";

import type { AgentPolicyDecision } from "./agent-policy.js";
import type { AgentProvider } from "./agent-provider.js";
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
  inspectOpenClawWorkspaceFileViaWsl,
  stageResolvedAgentArtifactsForOpenClaw,
  transferOpenClawInputViaWsl,
  verifyOpenClawOutputs
} from "./openclaw-workspace.js";

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
};

export class OpenClawCliProvider implements AgentProvider {
  readonly backend = "openclaw_cli" as const;

  constructor(
    private readonly config: OpenClawCliProviderConfig,
    private readonly dependencies: OpenClawCliProviderDependencies = {}
  ) {}

  async execute(
    request: ExecuteAgentRequest,
    _policy: AgentPolicyDecision,
    context?: { executionId?: string }
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

    const executionId = context?.executionId ?? "execution_unknown";
    const normalizedOptions = normalizeOpenClawOptions({ request, executionId });
    const stagedArtifactInputs = await this.resolveAndStageArtifacts(request);
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
      workspaceRoot: this.config.workspaceRoot,
      options
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
        ? await this.verifyExpectedOutputs(options.expected_outputs)
        : [];
    const verificationResults = await this.persistVerifiedOutputs({
      request,
      executionId,
      expectedOutputs: options.expected_outputs,
      verificationResults: inspectedVerificationResults
    });
    const requiredFailures = verificationResults.filter(
      (result) => result.required && !result.verified
    );
    const persistenceFailure = verificationResults.find(
      (result) => result.failure_code === "persist_failed"
    );
    const nonzeroExit =
      typeof bridgeResult.exitCode === "number" && bridgeResult.exitCode !== 0;
    const status =
      bridgeResult.timedOut || nonzeroExit || requiredFailures.length > 0
        ? "failed"
        : "completed";
    const providerMetadata = this.buildMetadata({
      sessionKey,
      executionMode: options.execution_mode,
      bridgeResult,
      expectedOutputCount: options.expected_outputs.length,
      requiredOutputCount: options.expected_outputs.filter((output) => output.required)
        .length,
      verifiedOutputCount: verificationResults.filter((result) => result.verified)
        .length
    });
    const outputText = extractOutputText(bridgeResult);

    return {
      status,
      summary:
        status === "completed"
          ? `OpenClaw completed and verified ${providerMetadata.verified_output_count} output(s).`
          : requiredFailures[0]?.failure_message ??
            (bridgeResult.timedOut
              ? "OpenClaw execution timed out."
              : nonzeroExit
                ? "OpenClaw exited with a non-zero status."
              : "OpenClaw execution failed."),
      output_text: outputText,
      artifacts: verificationResults
        .filter((result) => result.verified)
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
      provider_metadata: providerMetadata,
      verification_results: verificationResults,
      diagnostics: {
        ...(requiredFailures[0]?.failure_code
          ? { failure_code: requiredFailures[0].failure_code }
          : bridgeResult.timedOut
            ? { failure_code: "provider_timeout" }
            : nonzeroExit
              ? { failure_code: "provider_nonzero_exit" }
              : persistenceFailure?.failure_code
                ? { failure_code: persistenceFailure.failure_code }
            : {}),
        ...(requiredFailures[0]?.failure_message
          ? { failure_message: requiredFailures[0].failure_message }
          : persistenceFailure?.failure_message
            ? { failure_message: persistenceFailure.failure_message }
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
      }
    };
  }

  private async verifyExpectedOutputs(
    expectedOutputs: ReturnType<typeof normalizeOpenClawOptions>["expected_outputs"]
  ): Promise<OpenClawVerificationResult[]> {
    if (this.dependencies.verifyOutputs) {
      return this.dependencies.verifyOutputs({
        workspaceRoot: this.config.workspaceRoot,
        expectedOutputs
      });
    }
    return verifyOpenClawOutputs({
      workspaceRoot: this.config.workspaceRoot,
      expectedOutputs,
      inspectFile: async (workspaceAbsolutePath) =>
        inspectOpenClawWorkspaceFileViaWsl({
          wslDistro: this.config.wslDistro,
          workspaceAbsolutePath
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
          return verification;
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
            persisted_artifact_id: artifact.artifact_id
          };
        } catch (error) {
          return {
            ...verification,
            verified: false,
            failure_code: "persist_failed" as const,
            failure_message:
              error instanceof Error
                ? error.message
                : "Failed to persist verified OpenClaw output."
          };
        }
      })
    );
  }

  private async resolveAndStageArtifacts(
    request: ExecuteAgentRequest
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

    if (this.dependencies.stageArtifacts) {
      return this.dependencies.stageArtifacts({
        workspaceRoot: this.config.workspaceRoot,
        artifacts
      });
    }

    return stageResolvedAgentArtifactsForOpenClaw({
      workspaceRoot: this.config.workspaceRoot,
      artifacts,
      transfer: async (input) =>
        transferOpenClawInputViaWsl({
          wslDistro: this.config.wslDistro,
          ...input
        })
    });
  }

  private buildMetadata(input: {
    sessionKey: string;
    executionMode: "read_only" | "output_required";
    bridgeResult: OpenClawCliBridgeResult;
    expectedOutputCount: number;
    requiredOutputCount: number;
    verifiedOutputCount: number;
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
      expected_output_count: input.expectedOutputCount,
      required_output_count: input.requiredOutputCount,
      verified_output_count: input.verifiedOutputCount,
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
      if (typeof record.finalAssistantVisibleText === "string") {
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
