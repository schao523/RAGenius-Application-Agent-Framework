import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { createAppServices } from "../../src/app.js";
import { getEnv } from "../../src/config/env.js";
import {
  buildRuntimeConfig,
  inspectRuntimeConfig,
  validateRuntimeConfig
} from "../../src/config/runtime-config.js";

describe("runtime config", () => {
  it("builds bounded Agent input import defaults and normalized overrides", () => {
    const defaults = buildRuntimeConfig(getEnv({}));
    assert.deepEqual(defaults.artifactImports, {
      maxBytes: 536870912,
      allowedMimeTypes: [
        "video/mp4",
        "application/pdf",
        "text/plain",
        "text/markdown",
        "application/octet-stream"
      ],
      tempRetentionHours: 24,
      binaryInMemoryMaxBytes: 26214400
    });

    const configured = buildRuntimeConfig(getEnv({
      AGENT_INPUT_MAX_BYTES: "2048",
      AGENT_INPUT_ALLOWED_MIME_TYPES: " Video/MP4, text/plain,video/mp4 ",
      AGENT_INPUT_TEMP_RETENTION_HOURS: "2",
      AGENT_BINARY_IN_MEMORY_MAX_BYTES: "512"
    }));
    assert.deepEqual(configured.artifactImports, {
      maxBytes: 2048,
      allowedMimeTypes: ["video/mp4", "text/plain"],
      tempRetentionHours: 2,
      binaryInMemoryMaxBytes: 512
    });
  });

  it("uses bounded safe Codex workspace defaults and accepts explicit overrides", () => {
    const defaults = buildRuntimeConfig(getEnv({
      DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public"
    }));

    assert.equal(defaults.providers.codexCli.runRoot, "storage/codex-runs");
    assert.equal(defaults.providers.codexCli.runRetentionHours, 24);
    assert.equal(defaults.providers.codexCli.maxOutputBytes, 16384);
    assert.equal(defaults.providers.codexCli.sandboxMode, "workspace-write");
    assert.deepEqual(defaults.agentSkills.codex.inventory, {
      maxStderrBytes: 65536,
      maxStdoutBytes: 1048576,
      timeoutMs: 15000
    });

    const configured = buildRuntimeConfig(getEnv({
      DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
      CODEX_RUN_ROOT: "D:/runtime/codex-runs",
      CODEX_RUN_RETENTION_HOURS: "12",
      CODEX_MAX_OUTPUT_BYTES: "8192",
      CODEX_CLI_SANDBOX_MODE: "read-only",
      CODEX_AGENT_SKILL_INVENTORY_TIMEOUT_MS: "7000",
      CODEX_AGENT_SKILL_INVENTORY_MAX_STDOUT_BYTES: "32768",
      CODEX_AGENT_SKILL_INVENTORY_MAX_STDERR_BYTES: "2048",
      CODEX_AGENT_SKILL_SOURCES_JSON: JSON.stringify([{
        display_name: "Approved plugins",
        path: "C:/approved/plugins",
        protected_locator_ref: "plugin-root-1",
        runtime_target_id: "codex-local-default",
        discovery_mode: "plugin_inventory",
        precedence: 10
      }])
    }));

    assert.equal(configured.providers.codexCli.runRoot, "D:/runtime/codex-runs");
    assert.equal(configured.providers.codexCli.runRetentionHours, 12);
    assert.equal(configured.providers.codexCli.maxOutputBytes, 8192);
    assert.equal(configured.providers.codexCli.sandboxMode, "read-only");
    assert.deepEqual(configured.agentSkills.codex.inventory, {
      maxStderrBytes: 2048,
      maxStdoutBytes: 32768,
      timeoutMs: 7000
    });
    assert.deepEqual(configured.agentSkills.codex.sourceOptions[0], {
      display_name: "Approved plugins",
      path: "C:/approved/plugins",
      protected_locator_ref: "plugin-root-1",
      runtime_target_id: "codex-local-default",
      discovery_mode: "plugin_inventory",
      precedence: 10
    });
  });

  it("rejects unsafe Codex sandbox modes", () => {
    assert.throws(() => getEnv({
      DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
      CODEX_CLI_SANDBOX_MODE: "danger-full-access"
    }));
  });

  it("builds provider, tool, and MCP runtime config from env", () => {
    const sourceEnv = {
      DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
      BUILDER_BASE_URL: "http://127.0.0.1:8011",
      HTTP_PROXY: "http://proxy.local:8080",
      FILESYSTEM_ALLOWED_ROOTS:
        "D:/GitHub/Codex-RAGenius-System/docs,D:/GitHub/Codex-RAGenius-System/ragenius_builder/flask_scaffold/instructions",
      FILESYSTEM_MUTATION_ROOTS: "D:/GitHub/Codex-RAGenius-System/docs",
      FILESYSTEM_MAX_READ_BYTES: "8192",
      FILESYSTEM_MAX_WRITE_BYTES: "16384",
      FILESYSTEM_MAX_PATCH_BYTES: "4096",
      ARTIFACT_STORAGE_ROOT: "storage/artifacts",
      ARXIV_ENABLED: "true",
      ARXIV_REQUEST_TIMEOUT_MS: "4500",
      SEMANTIC_SCHOLAR_ENABLED: "true",
      SEMANTIC_SCHOLAR_API_KEY: "semantic-secret",
      SEMANTIC_SCHOLAR_REQUEST_TIMEOUT_MS: "3500",
      NOTEBOOKLM_ENABLED: "true",
      NOTEBOOKLM_PYTHON_COMMAND: "python",
      NOTEBOOKLM_BRIDGE_SCRIPT: "scripts/notebooklm_bridge.py",
      NOTEBOOKLM_AUTH_MODE: "env_json",
      NOTEBOOKLM_PROFILE: "default",
      NOTEBOOKLM_ALLOWED_OPERATIONS: "list_notebooks,list_sources,ask",
      NOTEBOOKLM_GENERATION_WAIT_FOR_COMPLETION: "true",
      NOTEBOOKLM_GENERATION_PERSIST_ARTIFACTS: "true",
      MCP_LOCAL_BROWSER_TOKEN: "mcp-secret",
      RAGENIUS_EXECUTION_SERVICE_AUTH_REQUIRED: "true",
      RAGENIUS_EXECUTION_SERVICE_ID: "ragenius_app_backend",
      RAGENIUS_EXECUTION_SERVICE_TOKEN: "service-secret",
      ADAPTERS_JSON: JSON.stringify([
        {
          id: "content_transform_adapter",
          command: "internal:transform",
          args: [],
          enabled: true
        }
      ]),
      MCP_SERVERS_JSON: JSON.stringify([
        {
          id: "local-browser",
          transport: "http",
          baseUrl: "http://127.0.0.1:4100",
          authTokenEnv: "MCP_LOCAL_BROWSER_TOKEN",
          allowedToolNames: ["search_messages"],
          enabled: true
        }
      ]),
      TOOL_RESEARCH_PAPER_SEARCH_ENABLED: "true",
      TOOL_RAG_RETRIEVAL_ENABLED: "false"
    } as NodeJS.ProcessEnv;

    const runtimeConfig = buildRuntimeConfig(getEnv(sourceEnv), sourceEnv);

    assert.equal(runtimeConfig.builder.baseUrl, "http://127.0.0.1:8011");
    assert.deepEqual(runtimeConfig.serviceAuth, {
      required: true,
      credentials: [
        {
          serviceId: "ragenius_app_backend",
          token: "service-secret",
          scopes: ["execution"]
        }
      ]
    });
    assert.equal(runtimeConfig.network.httpProxy, "http://proxy.local:8080");
    assert.equal(runtimeConfig.fileTools.allowedRoots.length, 2);
    assert.deepEqual(runtimeConfig.fileTools.mutationRoots, [
      "D:/GitHub/Codex-RAGenius-System/docs"
    ]);
    assert.equal(runtimeConfig.fileTools.maxReadBytes, 8192);
    assert.equal(runtimeConfig.fileTools.maxWriteBytes, 16384);
    assert.equal(runtimeConfig.fileTools.maxPatchBytes, 4096);
    assert.equal(runtimeConfig.artifactStore.rootDir, "storage/artifacts");
    assert.equal(runtimeConfig.providers.researchPaper.arxiv.requestTimeoutMs, 4500);
    assert.equal(runtimeConfig.providers.researchPaper.semanticScholar.apiKey, "semantic-secret");
    assert.deepEqual(runtimeConfig.providers.notebooklm, {
      enabled: true,
      pythonCommand: "python",
      bridgeScript: "scripts/notebooklm_bridge.py",
      authMode: "env_json",
      profile: "default",
      allowedOperations: ["list_notebooks", "list_sources", "ask"],
      generationDefaults: {
        waitForCompletion: true,
        persistArtifacts: true
      }
    });
    assert.equal(runtimeConfig.tools.ragRetrieval.enabled, false);
    assert.equal(runtimeConfig.adapters.tools.length, 1);
    assert.equal(runtimeConfig.mcp.servers.length, 1);
    assert.deepEqual(runtimeConfig.mcp.servers[0], {
      id: "local-browser",
      transport: "http",
      baseUrl: "http://127.0.0.1:4100",
      authTokenEnv: "MCP_LOCAL_BROWSER_TOKEN",
      authToken: "mcp-secret",
      allowedToolNames: ["search_messages"],
      enabled: true
    });
  });

  it("allows NotebookLM adapter entries without dummy command values", () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        NOTEBOOKLM_ENABLED: "true",
        NOTEBOOKLM_PYTHON_COMMAND: "python",
        NOTEBOOKLM_BRIDGE_SCRIPT: "scripts/notebooklm_bridge.py",
        NOTEBOOKLM_AUTH_MODE: "profile",
        NOTEBOOKLM_PROFILE: "default",
        NOTEBOOKLM_ALLOWED_OPERATIONS: "generate_video",
        ADAPTERS_JSON: JSON.stringify([
          {
            id: "adapter.notebooklm.generate_video",
            enabled: true
          }
        ]),
        MCP_SERVERS_JSON: "[]"
      })
    );

    assert.deepEqual(runtimeConfig.adapters.tools, [
      {
        id: "adapter.notebooklm.generate_video",
        args: [],
        enabled: true
      }
    ]);
  });

  it("still requires command for generic non-NotebookLM adapter entries", () => {
    assert.throws(
      () =>
        buildRuntimeConfig(
          getEnv({
            DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
            ADAPTERS_JSON: JSON.stringify([
              {
                id: "content_transform_adapter",
                enabled: true
              }
            ]),
            MCP_SERVERS_JSON: "[]"
          })
        ),
      /Required/
    );
  });

  it("wires builder client creation from runtime config instead of direct env reads", () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        BUILDER_BASE_URL: "http://127.0.0.1:8011",
        MCP_SERVERS_JSON: "[]"
      })
    );

    const services = createAppServices({}, runtimeConfig);

    assert.ok(services.builderSkillClient);
    assert.equal(services.runtimeConfig.builder.baseUrl, "http://127.0.0.1:8011");
  });

  it("reports non-secret runtime diagnostics", () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        BUILDER_BASE_URL: "http://127.0.0.1:8011",
        HTTPS_PROXY: "http://proxy.local:8080",
        NODE_EXTRA_CA_CERTS: "C:\\certs\\root.pem",
        RAGENIUS_EXECUTION_SERVICE_AUTH_REQUIRED: "true",
        RAGENIUS_EXECUTION_SERVICE_TOKEN: "service-secret",
        MCP_SERVERS_JSON: JSON.stringify([
        {
          id: "local-browser",
          transport: "http",
          baseUrl: "http://127.0.0.1:4100",
          allowedToolNames: ["search_messages"],
          enabled: true
        }
      ])
      })
    );

    const diagnostics = inspectRuntimeConfig(runtimeConfig);

    assert.equal(diagnostics.builder.configured, true);
    assert.equal(diagnostics.adapters.configured, false);
    assert.equal(diagnostics.fileTools.configured, false);
    assert.equal(diagnostics.fileTools.mutationConfigured, false);
    assert.equal(diagnostics.artifactStore.configured, true);
    assert.equal(diagnostics.network.proxyConfigured, true);
    assert.equal(diagnostics.network.extraCaCertsConfigured, true);
    assert.equal(diagnostics.mcp.configuredServers, 1);
    assert.equal(diagnostics.mcp.providers[0]?.authConfigured, false);
    assert.equal(diagnostics.mcp.providers[0]?.allowlistedTools, 1);
    assert.equal(diagnostics.providers.arxiv.enabled, true);
    assert.deepEqual(diagnostics.serviceAuth, {
      configured: true,
      required: true
    });
    assert.equal(
      Object.prototype.hasOwnProperty.call(diagnostics.serviceAuth, "token"),
      false
    );
  });

  it("builds default fallback policy for current MCP-backed Gmail and Drive tools", () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        BUILDER_BASE_URL: "http://127.0.0.1:8011",
        MCP_SERVERS_JSON: "[]"
      })
    );

    assert.equal(
      runtimeConfig.policy.fallbacks.tools["mcp.gdrive.download_file_content"]?.enabled,
      true
    );
    assert.equal(
      runtimeConfig.policy.fallbacks.tools["mcp.gdrive.download_file_content"]?.strategy,
      "rest_api"
    );
    assert.deepEqual(
      runtimeConfig.policy.fallbacks.tools["mcp.gdrive.download_file_content"]?.allowedErrorClasses,
      ["permission_rejected"]
    );

    assert.equal(
      runtimeConfig.policy.fallbacks.tools["mcp.gmail.create_draft"]?.enabled,
      true
    );
    assert.equal(
      runtimeConfig.policy.fallbacks.tools["mcp.gmail.create_draft_with_attachments"]?.enabled,
      true
    );
  });

  it("fails fast for known-bad loopback discard proxies", () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        HTTPS_PROXY: "http://127.0.0.1:9",
        MCP_SERVERS_JSON: "[]"
      })
    );

    assert.throws(
      () => validateRuntimeConfig(runtimeConfig),
      /invalid discard proxy target/i
    );
  });

  it("fails fast when required service authentication has no token", () => {
    const runtimeConfig = buildRuntimeConfig(
      getEnv({
        DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
        MCP_SERVERS_JSON: "[]",
        RAGENIUS_EXECUTION_SERVICE_AUTH_REQUIRED: "true"
      })
    );

    assert.throws(
      () => validateRuntimeConfig(runtimeConfig),
      /no service token is configured/i
    );
  });

  it("rejects malformed scoped service credentials", () => {
    assert.throws(
      () =>
        buildRuntimeConfig(
          getEnv({
            DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
            MCP_SERVERS_JSON: "[]",
            RAGENIUS_EXECUTION_SERVICE_CREDENTIALS_JSON: "not-json"
          })
        ),
      SyntaxError
    );
  });
});
