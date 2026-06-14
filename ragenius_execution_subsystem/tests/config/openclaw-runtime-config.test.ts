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
