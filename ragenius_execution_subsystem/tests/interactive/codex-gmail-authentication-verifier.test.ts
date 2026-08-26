import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { CodexGmailAuthenticationVerifier } from "../../src/core/interactive/codex-gmail-authentication-verifier.js";
import type {
  CodexManagedAuthenticationTarget,
  ManagedAuthenticationVerificationContext
} from "../../src/core/interactive/codex-managed-auth-targets.js";

const target: CodexManagedAuthenticationTarget = {
  id: "gmail",
  label: "Google sign-in",
  launch: { kind: "https_url", url: "https://accounts.google.com/" },
  allowedHosts: ["accounts.google.com"],
  verifierId: "codex-apps-gmail-auth"
};

function context(overrides: {
  authStatus?: "unsupported" | "notLoggedIn" | "bearerToken" | "oAuth";
  hasServer?: boolean;
  tools?: readonly string[];
  toolResult?: { isError: boolean; hasContent: boolean; hasStructuredContent: boolean };
  throwOnCall?: boolean;
} = {}): {
  value: ManagedAuthenticationVerificationContext;
  calls: Array<{ server: string; tool: string; arguments: Readonly<Record<string, unknown>> }>;
} {
  const calls: Array<{
    server: string;
    tool: string;
    arguments: Readonly<Record<string, unknown>>;
  }> = [];
  return {
    calls,
    value: {
      backend: "codex_cli",
      codexMcp: {
        async listServerStatus() {
          return overrides.hasServer === false ? [] : [{
            name: "codex_apps",
            authStatus: overrides.authStatus ?? "bearerToken",
            tools: overrides.tools ?? ["gmail.get_profile"]
          }];
        },
        async callReadOnlyTool(input) {
          calls.push(input);
          if (overrides.throwOnCall) throw new Error("private provider failure");
          return overrides.toolResult ?? {
            isError: false,
            hasContent: true,
            hasStructuredContent: true
          };
        }
      }
    }
  };
}

describe("CodexGmailAuthenticationVerifier", () => {
  it("verifies Gmail with the fixed read-only profile probe", async () => {
    const verifier = new CodexGmailAuthenticationVerifier();
    const probe = context();

    const result = await verifier.verify({
      executionId: "execution-1",
      target,
      context: probe.value
    });

    assert.deepEqual(result, { verified: true });
    assert.deepEqual(probe.calls, [{
      server: "codex_apps",
      tool: "gmail.get_profile",
      arguments: {}
    }]);
  });

  it("fails closed when the Gmail server is absent or unauthenticated", async () => {
    const verifier = new CodexGmailAuthenticationVerifier();

    assert.deepEqual(await verifier.verify({
      executionId: "execution-1",
      target,
      context: context({ hasServer: false }).value
    }), {
      verified: false,
      diagnosticCode: "gmail_mcp_server_unavailable"
    });
    assert.deepEqual(await verifier.verify({
      executionId: "execution-1",
      target,
      context: context({ authStatus: "notLoggedIn" }).value
    }), {
      verified: false,
      diagnosticCode: "gmail_mcp_not_authenticated"
    });
  });

  it("fails closed when the profile probe is unavailable or unsuccessful", async () => {
    const verifier = new CodexGmailAuthenticationVerifier();

    assert.deepEqual(await verifier.verify({
      executionId: "execution-1",
      target,
      context: context({ tools: [] }).value
    }), {
      verified: false,
      diagnosticCode: "gmail_profile_probe_unavailable"
    });
    assert.deepEqual(await verifier.verify({
      executionId: "execution-1",
      target,
      context: context({
        toolResult: { isError: true, hasContent: true, hasStructuredContent: false }
      }).value
    }), {
      verified: false,
      diagnosticCode: "gmail_profile_probe_failed"
    });
    assert.deepEqual(await verifier.verify({
      executionId: "execution-1",
      target,
      context: context({
        toolResult: { isError: false, hasContent: false, hasStructuredContent: false }
      }).value
    }), {
      verified: false,
      diagnosticCode: "gmail_profile_probe_invalid"
    });
  });

  it("redacts provider failures into a bounded diagnostic", async () => {
    const verifier = new CodexGmailAuthenticationVerifier();

    assert.deepEqual(await verifier.verify({
      executionId: "execution-1",
      target,
      context: context({ throwOnCall: true }).value
    }), {
      verified: false,
      diagnosticCode: "gmail_profile_probe_failed"
    });
  });
});
