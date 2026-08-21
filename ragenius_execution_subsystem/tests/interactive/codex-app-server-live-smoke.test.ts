import assert from "node:assert/strict";
import test from "node:test";

import { CodexAppServerProcessFactory } from "../../src/core/interactive/codex-app-server-process.js";
import { CodexAppServerAdapter } from "../../src/core/interactive/codex-app-server-adapter.js";
import type { InteractiveProviderEvent } from "../../src/core/interactive/interactive-agent-adapter.js";

test("Codex app-server initializes over stdio", {
  skip: process.env.CODEX_APP_SERVER_INTERACTIVE_SMOKE !== "1"
}, async () => {
  const factory = new CodexAppServerProcessFactory({
    command: process.env.CODEX_APP_SERVER_COMMAND || "codex",
    initializationTimeoutMs: 15000,
    maxLineBytes: 65536,
    maxStderrBytes: 65536
  });
  const version = await factory.versionInfo();
  assert.equal(version.available, true);
  const transport = await factory.create();
  try {
    const initialized = await transport.request("initialize", {
      clientInfo: { name: "RAGenius smoke", version: "0.1.0" },
      capabilities: { experimentalApi: true }
    }) as Record<string, unknown>;
    assert.equal(typeof initialized.userAgent, "string");
  } finally {
    await transport.close();
  }
});

test("Codex app-server completes a bounded read-only turn", {
  skip: process.env.CODEX_APP_SERVER_INTERACTIVE_SMOKE !== "1",
  timeout: 60000
}, async () => {
  const command = process.env.CODEX_APP_SERVER_COMMAND || "codex";
  const processConfig = {
    command,
    initializationTimeoutMs: 15000,
    maxLineBytes: 1048576,
    maxStderrBytes: 65536
  };
  const adapter = new CodexAppServerAdapter({
    ...processConfig,
    enabled: true,
    interactionTtlMs: 60000,
    maxDeltaBytes: 16384,
    runRoot: ".test_tmp/codex-interactive-smoke",
    supportedVersions: ["0.146.0"]
  }, new CodexAppServerProcessFactory(processConfig));
  let finish!: (event: InteractiveProviderEvent) => void;
  const terminal = new Promise<InteractiveProviderEvent>((resolve) => { finish = resolve; });
  const preflightInput = {
    policy: {
      matchedTerms: [], mode: "auto_allow" as const, networkAccess: "deny" as const,
      permissionScope: "agent.read", providerStateAccess: "none" as const,
      providerStateLabels: [], reason: "Read-only smoke.", riskClass: "agent_read_only" as const,
      workspaceAccess: "read_only" as const
    },
    providerContext: {
      execution_id: "execution_smoke",
      authorization: {
        permission_scope: "agent.read", policy_fingerprint: "smoke", state: "not_required" as const
      },
      operation_plan: [], resolved_artifacts: [], expected_outputs: []
    },
    request: {
      request_type: "execute_agent" as const,
      app_id: "app_smoke", session_id: "session_smoke",
      agent_backend: "codex_cli" as const,
      agent_query: "Reply with exactly: OK"
    },
    requiredInteractionTypes: [],
    scope: { appId: "app_smoke", executionId: "execution_smoke", sessionId: "session_smoke" }
  };
  const preflight = await adapter.preflight(preflightInput);
  assert.equal(preflight.available, true);
  await adapter.start({
    ...preflightInput,
    agentSessionId: "agent_session_smoke",
    capabilities: preflight.capabilities,
    protocolVersion: preflight.protocolVersion,
    emit: async (event) => {
      if (event.type === "run_completed" || event.type === "run_cancelled") finish(event);
    }
  });
  let timeout: NodeJS.Timeout | undefined;
  const event = await Promise.race([
    terminal,
    new Promise<never>((_resolve, reject) => {
      timeout = setTimeout(
        () => reject(new Error("Codex read-only turn did not complete.")),
        45000
      );
    })
  ]).finally(() => {
    if (timeout) clearTimeout(timeout);
  });
  assert.equal(event.type, "run_completed");
  assert.equal(event.payload.status, "completed");
});
