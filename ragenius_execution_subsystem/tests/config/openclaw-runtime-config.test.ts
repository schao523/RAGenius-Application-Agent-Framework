import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { getEnv } from "../../src/config/env.js";
import {
  buildRuntimeConfig,
  inspectRuntimeConfig
} from "../../src/config/runtime-config.js";

describe("OpenClaw runtime config", () => {
  it("builds default disabled OpenClaw provider config", () => {
    const runtimeConfig = buildRuntimeConfig(getEnv({}));

    assert.equal(runtimeConfig.providers.openClaw.enabled, false);
    assert.equal(runtimeConfig.providers.openClaw.wslDistro, "OpenClawGateway");
    assert.equal(runtimeConfig.providers.openClaw.command, "openclaw");
    assert.equal(runtimeConfig.providers.openClaw.agentId, "main");
    assert.equal(
      runtimeConfig.providers.openClaw.workspaceRoot,
      "/home/openclaw/.openclaw/workspace"
    );
    assert.equal(runtimeConfig.providers.openClaw.timeoutMs, 120000);
    assert.deepEqual(runtimeConfig.providers.openClawGateway, {
      agentId: "main",
      chatIdleTtlMs: 900000,
      chatLevelEnabled: false,
      credentialEnv: "OPENCLAW_GATEWAY_APPROVAL_TOKEN",
      enabled: false,
      gatewayUrl: "ws://127.0.0.1:18789",
      interactionTtlMs: 900000,
      maxMessageBytes: 1048576,
      reconnectBaseDelayMs: 250,
      reconnectMaxAttempts: 5,
      rpcTimeoutMs: 15000,
      supportedVersions: ["2026.6.8"],
      workspaceRoot: "/home/openclaw/.openclaw/workspace",
      wslDistro: "OpenClawGateway"
    });
  });

  it("resolves the external Gateway credential without exposing it in diagnostics", () => {
    const source = {
      OPENCLAW_GATEWAY_INTERACTIVE_ENABLED: "true",
      OPENCLAW_GATEWAY_APPROVAL_CREDENTIAL_ENV: "MY_GATEWAY_TOKEN",
      MY_GATEWAY_TOKEN: "gateway-secret"
    } as NodeJS.ProcessEnv;
    const runtimeConfig = buildRuntimeConfig(getEnv(source), source);
    const diagnostics = inspectRuntimeConfig(runtimeConfig);

    assert.equal(runtimeConfig.providers.openClawGateway.credential, "gateway-secret");
    assert.deepEqual(diagnostics.providers.openClawGateway, {
      credentialConfigured: true,
      enabled: true,
      gatewayUrl: "ws://127.0.0.1:18789"
    });
    assert.equal(JSON.stringify(diagnostics).includes("gateway-secret"), false);
  });

  it("reports OpenClaw provider diagnostics", () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        OPENCLAW_CLI_ENABLED: "true"
      })
    );
    const diagnostics = inspectRuntimeConfig(runtimeConfig);

    assert.equal(diagnostics.providers.openClaw.enabled, true);
  });
});
