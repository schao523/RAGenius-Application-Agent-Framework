import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";
import type { CodexCliProviderConfig } from "../../config/provider-config.js";
import { AppError } from "../errors/app-error.js";
import type { AgentPolicyDecision } from "./agent-policy.js";
import type { AgentProvider } from "./agent-provider.js";

import { executeCodexCliBridge } from "./codex-cli-bridge.js";
import type {
  CodexCliBridgeRequest,
  CodexCliBridgeResponse,
  CodexCliBridgeSuccessResult
} from "./codex-cli-types.js";

type CodexCliBridgeExecutor = (
  config: CodexCliProviderConfig,
  request: CodexCliBridgeRequest
) => Promise<CodexCliBridgeResponse>;

export class CodexCliProvider implements AgentProvider {
  readonly backend = "codex_cli" as const;

  constructor(
    private readonly config: CodexCliProviderConfig,
    private readonly bridgeExecutor: CodexCliBridgeExecutor = executeCodexCliBridge
  ) {}

  async execute(
    request: ExecuteAgentRequest,
    policy: AgentPolicyDecision
  ): Promise<CodexCliBridgeSuccessResult> {
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

    let response: CodexCliBridgeResponse;
    try {
      response = await this.bridgeExecutor(this.config, {
        app_id: request.app_id,
        session_id: request.session_id,
        agent_query: request.agent_query,
        ...(request.agent_skill_hint
          ? { agent_skill_hint: request.agent_skill_hint }
          : {}),
        ...(request.approved_content_id
          ? { approved_content_id: request.approved_content_id }
          : {}),
        ...(request.approved_revision_id
          ? { approved_revision_id: request.approved_revision_id }
          : {}),
        ...(request.context ? { context: request.context } : {}),
        policy: {
          risk_class: policy.riskClass,
          workspace_access: policy.workspaceAccess,
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

    return response.result;
  }
}
