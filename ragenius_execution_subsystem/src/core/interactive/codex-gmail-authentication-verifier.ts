import type {
  CodexMcpServerVerificationStatus,
  ManagedAuthenticationVerificationInput,
  ManagedAuthenticationVerifier
} from "./codex-managed-auth-targets.js";

const SERVER_NAME = "codex_apps";
const PROFILE_TOOL = "gmail.get_profile";

export class CodexGmailAuthenticationVerifier implements ManagedAuthenticationVerifier {
  readonly id = "codex-apps-gmail-auth";

  async verify(input: ManagedAuthenticationVerificationInput): Promise<{
    verified: boolean;
    diagnosticCode?: string;
  }> {
    if (!input.context || input.context.backend !== "codex_cli") {
      return { verified: false, diagnosticCode: "codex_mcp_context_unavailable" };
    }

    let statuses: readonly CodexMcpServerVerificationStatus[];
    try {
      statuses = await input.context.codexMcp.listServerStatus();
    } catch {
      return { verified: false, diagnosticCode: "gmail_mcp_server_unavailable" };
    }
    const server = statuses.find((candidate) => candidate.name === SERVER_NAME);
    if (!server) {
      return { verified: false, diagnosticCode: "gmail_mcp_server_unavailable" };
    }
    if (server.authStatus !== "bearerToken" && server.authStatus !== "oAuth") {
      return { verified: false, diagnosticCode: "gmail_mcp_not_authenticated" };
    }
    if (!server.tools.includes(PROFILE_TOOL)) {
      return { verified: false, diagnosticCode: "gmail_profile_probe_unavailable" };
    }

    try {
      const result = await input.context.codexMcp.callReadOnlyTool({
        server: SERVER_NAME,
        tool: PROFILE_TOOL,
        arguments: {}
      });
      if (result.isError) {
        return { verified: false, diagnosticCode: "gmail_profile_probe_failed" };
      }
      if (!result.hasContent && !result.hasStructuredContent) {
        return { verified: false, diagnosticCode: "gmail_profile_probe_invalid" };
      }
      return { verified: true };
    } catch {
      return { verified: false, diagnosticCode: "gmail_profile_probe_failed" };
    }
  }
}
