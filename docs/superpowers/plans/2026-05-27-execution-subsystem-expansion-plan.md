# RAGenius Execution Subsystem Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current working Builder-managed research skill vertical slice into a broader, operable, configurable execution subsystem that can support multiple real skills, runtime integrations, and production-oriented execution concerns.

**Architecture:** Keep `ragenius_builder` as the source of truth for skill definitions, published versions, and app-skill bindings. Keep `ragenius_execution_subsystem` as the runtime authority for tool/provider execution, transport configuration, API credentials, MCP registration, permission enforcement, and execution lifecycle handling. Evolve the subsystem in layers: first typed runtime configuration and provider wiring, then execution persistence and lifecycle APIs, then broader workflow semantics and production hardening.

**Tech Stack:** Node.js 20+, TypeScript, Fastify, Zod, Fetch/AbortController, PostgreSQL/Prisma, Builder HTTP integration, MCP provider abstraction.

---

## Scope and Current State

The current vertical slice is proven:

- Builder-managed `research_paper_finder` is published and bound through `ragenius_builder`
- `ragenius_execution_subsystem` can resolve the Builder-managed skill by app binding
- the subsystem can execute a real HTTP-backed `research_paper_search_tool`
- the subsystem can fall back across external providers and return normalized JSON

The subsystem is **not** yet broadly complete. Missing capabilities group into:

1. Runtime configuration and provider governance
2. Multi-skill/runtime tool coverage
3. Execution persistence and lifecycle APIs
4. Confirmation/resume lifecycle
5. MCP server runtime registration and real connectivity
6. Workflow feature expansion beyond the current narrow path
7. Observability, security, and operational hardening

---

## Files and Responsibilities

### Existing files to modify

- `ragenius_execution_subsystem/src/config/env.ts`
  - Expand from minimal env parsing to typed runtime config contract.
- `ragenius_execution_subsystem/src/app.ts`
  - Construct typed runtime config and inject provider/runtime dependencies.
- `ragenius_execution_subsystem/src/server.ts`
  - Surface startup configuration state in logs and readiness checks.
- `ragenius_execution_subsystem/src/core/tools/tool-registry.ts`
  - Move from hardcoded MVP-only defaults toward config-aware registration.
- `ragenius_execution_subsystem/src/core/tools/tool-engine.ts`
  - Keep execution core narrow, but use richer runtime/provider config.
- `ragenius_execution_subsystem/src/core/tools/providers/api-tool-provider.ts`
  - Split into reusable provider clients and config-aware execution.
- `ragenius_execution_subsystem/src/core/skills/builder-skill-client.ts`
  - Keep Builder integration read-only and config-driven.
- `ragenius_execution_subsystem/src/api/routes/health.routes.ts`
  - Expand readiness reporting for non-secret config/runtime status.
- `ragenius_execution_subsystem/README.md`
  - Document runtime env/config contract and operator workflow.

### New files to create

- `ragenius_execution_subsystem/src/config/runtime-config.ts`
  - Convert validated env into internal runtime config objects.
- `ragenius_execution_subsystem/src/config/mcp-config.ts`
  - Parse and validate MCP server config records.
- `ragenius_execution_subsystem/src/config/provider-config.ts`
  - Build typed API provider settings from env.
- `ragenius_execution_subsystem/src/core/tools/providers/research-paper-provider.ts`
  - Extract arXiv/Semantic Scholar logic from the generic API provider.
- `ragenius_execution_subsystem/src/core/tools/providers/http-client.ts`
  - Shared fetch/abort/retry behavior for outbound HTTP providers.
- `ragenius_execution_subsystem/src/core/tools/providers/openai-provider.ts`
  - Future real API-provider seam for LLM-backed tools.
- `ragenius_execution_subsystem/src/core/mcp/mcp-server-registry.ts`
  - Runtime MCP server registry from config.
- `ragenius_execution_subsystem/src/core/execution/execution-store.ts`
  - Persistence seam for execution records/logs.
- `ragenius_execution_subsystem/src/core/execution/execution-status-service.ts`
  - Lookup service for `GET /v1/executions/:execution_id` and logs.
- `ragenius_execution_subsystem/tests/config/env.test.ts`
  - Runtime env/schema validation tests.
- `ragenius_execution_subsystem/tests/config/runtime-config.test.ts`
  - Config object construction tests.
- `ragenius_execution_subsystem/tests/tools/research-paper-provider.test.ts`
  - arXiv/Semantic Scholar client tests.
- `ragenius_execution_subsystem/tests/mcp/mcp-server-registry.test.ts`
  - MCP config parsing tests.
- `ragenius_execution_subsystem/tests/execution/execution-store.test.ts`
  - Persistence seam tests.

---

## Env/Config Contract

This contract is the implementation target for the next subsystem phase.

### Core runtime env

```env
DATABASE_URL=
NODE_ENV=development|test|production
PORT=3001
LOG_LEVEL=debug|info|warn|error
BUILDER_BASE_URL=http://127.0.0.1:8011
```

### Outbound transport env

```env
HTTP_PROXY=
HTTPS_PROXY=
ALL_PROXY=
NO_PROXY=localhost,127.0.0.1,::1
NODE_EXTRA_CA_CERTS=
```

### API provider env

```env
ARXIV_ENABLED=true
ARXIV_REQUEST_TIMEOUT_MS=4000
ARXIV_RETRY_ON_429=true
ARXIV_MAX_RETRIES=1

SEMANTIC_SCHOLAR_ENABLED=true
SEMANTIC_SCHOLAR_API_KEY=
SEMANTIC_SCHOLAR_REQUEST_TIMEOUT_MS=4000
SEMANTIC_SCHOLAR_MAX_RESULTS_DEFAULT=5

OPENAI_ENABLED=false
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_DEFAULT_MODEL=
```

### MCP env

```env
MCP_SERVERS_JSON=[]
```

Example:

```json
[
  {
    "id": "local-browser",
    "transport": "http",
    "baseUrl": "http://127.0.0.1:4100",
    "authTokenEnv": "MCP_LOCAL_BROWSER_TOKEN",
    "enabled": true
  }
]
```

Related secret env:

```env
MCP_LOCAL_BROWSER_TOKEN=
```

### Tool/runtime toggle env

```env
TOOL_RESEARCH_PAPER_SEARCH_ENABLED=true
TOOL_RAG_RETRIEVAL_ENABLED=true
TOOL_OPENAI_ANSWER_ENABLED=false
```

### Config ownership contract

- Builder owns:
  - skill definitions
  - published versions
  - app-skill bindings
  - non-secret skill metadata
- Execution subsystem owns:
  - secrets
  - base URLs
  - transport/proxy/CA behavior
  - provider enablement
  - MCP runtime registration
  - tool/provider implementation mapping

### Non-goals for this phase

- Do not move secrets into Builder DB.
- Do not make execution subsystem depend directly on Builder SQLite.
- Do not broaden Builder into a secret-management surface in this phase.

---

## Roadmap Phases

### Phase 1: Runtime Config Foundation

**Outcome:** The subsystem has a typed, validated, documented runtime config layer instead of scattered `process.env` reads.

### Phase 2: Real Provider Extraction

**Outcome:** Real API tools use dedicated provider clients and shared HTTP/timeout/retry behavior.

### Phase 3: MCP Runtime Registration

**Outcome:** MCP servers can be registered from config, validated at startup, and exposed through readiness/debug surfaces.

### Phase 4: Execution Persistence and Retrieval

**Outcome:** Execution records and logs become persistent, and `GET /v1/executions/:execution_id` plus logs can move off `501`.

### Phase 5: Confirmation and Resume Lifecycle

**Outcome:** Pending confirmation can be resumed or rejected with persisted execution state.

### Phase 6: Workflow Expansion

**Outcome:** The workflow engine can support more than the current narrow `validation`/`tool_call`/`end` slice.

### Phase 7: Beta Hardening

**Outcome:** Security, observability, testing breadth, and operational readiness support multi-skill beta.

---

### Task 1: Expand Typed Env Schema

**Files:**
- Modify: `ragenius_execution_subsystem/src/config/env.ts`
- Create: `ragenius_execution_subsystem/tests/config/env.test.ts`
- Test: `ragenius_execution_subsystem/tests/config/env.test.ts`

- [ ] **Step 1: Write the failing env validation test**

```ts
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { getEnv } from "../../src/config/env.js";

describe("env schema", () => {
  it("parses runtime provider env values", () => {
    const env = getEnv({
      DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
      PORT: "3001",
      LOG_LEVEL: "info",
      BUILDER_BASE_URL: "http://127.0.0.1:8011",
      ARXIV_ENABLED: "true",
      ARXIV_REQUEST_TIMEOUT_MS: "4000",
      SEMANTIC_SCHOLAR_ENABLED: "true",
      SEMANTIC_SCHOLAR_REQUEST_TIMEOUT_MS: "4000",
      MCP_SERVERS_JSON: "[]"
    });

    assert.equal(env.ARXIV_ENABLED, true);
    assert.equal(env.ARXIV_REQUEST_TIMEOUT_MS, 4000);
    assert.equal(env.SEMANTIC_SCHOLAR_ENABLED, true);
    assert.equal(env.MCP_SERVERS_JSON, "[]");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- env.test.ts`
Expected: FAIL because `ARXIV_ENABLED` and related keys are not in `env.ts`

- [ ] **Step 3: Implement minimal env schema expansion**

```ts
const envSchema = z.object({
  DATABASE_URL: z.string().min(1).default(
    "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public"
  ),
  NODE_ENV: z.enum(["development", "test", "production"]).default("development"),
  PORT: z.coerce.number().int().positive().default(3000),
  LOG_LEVEL: z.enum(["debug", "info", "warn", "error"]).default("info"),
  BUILDER_BASE_URL: z.string().trim().url().optional(),
  HTTP_PROXY: z.string().trim().optional(),
  HTTPS_PROXY: z.string().trim().optional(),
  ALL_PROXY: z.string().trim().optional(),
  NO_PROXY: z.string().trim().optional(),
  NODE_EXTRA_CA_CERTS: z.string().trim().optional(),
  ARXIV_ENABLED: z.coerce.boolean().default(true),
  ARXIV_REQUEST_TIMEOUT_MS: z.coerce.number().int().positive().default(4000),
  ARXIV_RETRY_ON_429: z.coerce.boolean().default(true),
  ARXIV_MAX_RETRIES: z.coerce.number().int().min(0).default(1),
  SEMANTIC_SCHOLAR_ENABLED: z.coerce.boolean().default(true),
  SEMANTIC_SCHOLAR_API_KEY: z.string().trim().optional(),
  SEMANTIC_SCHOLAR_REQUEST_TIMEOUT_MS: z.coerce.number().int().positive().default(4000),
  SEMANTIC_SCHOLAR_MAX_RESULTS_DEFAULT: z.coerce.number().int().positive().default(5),
  OPENAI_ENABLED: z.coerce.boolean().default(false),
  OPENAI_API_KEY: z.string().trim().optional(),
  OPENAI_BASE_URL: z.string().trim().url().optional(),
  OPENAI_DEFAULT_MODEL: z.string().trim().optional(),
  MCP_SERVERS_JSON: z.string().default("[]"),
  TOOL_RESEARCH_PAPER_SEARCH_ENABLED: z.coerce.boolean().default(true),
  TOOL_RAG_RETRIEVAL_ENABLED: z.coerce.boolean().default(true),
  TOOL_OPENAI_ANSWER_ENABLED: z.coerce.boolean().default(false)
});
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- env.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/src/config/env.ts ragenius_execution_subsystem/tests/config/env.test.ts
git commit -m "feat: expand execution subsystem env schema"
```

### Task 2: Build Internal Runtime Config Objects

**Files:**
- Create: `ragenius_execution_subsystem/src/config/runtime-config.ts`
- Create: `ragenius_execution_subsystem/src/config/provider-config.ts`
- Create: `ragenius_execution_subsystem/src/config/mcp-config.ts`
- Create: `ragenius_execution_subsystem/tests/config/runtime-config.test.ts`
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Test: `ragenius_execution_subsystem/tests/config/runtime-config.test.ts`

- [ ] **Step 1: Write the failing runtime-config test**

```ts
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { buildRuntimeConfig } from "../../src/config/runtime-config.js";

describe("runtime config", () => {
  it("builds provider and mcp config from env", () => {
    const config = buildRuntimeConfig({
      DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public",
      PORT: "3001",
      LOG_LEVEL: "info",
      BUILDER_BASE_URL: "http://127.0.0.1:8011",
      MCP_SERVERS_JSON: '[{\"id\":\"local-browser\",\"transport\":\"http\",\"baseUrl\":\"http://127.0.0.1:4100\",\"enabled\":true}]'
    });

    assert.equal(config.builderBaseUrl, "http://127.0.0.1:8011");
    assert.equal(config.mcpServers[0]?.id, "local-browser");
    assert.equal(config.providers.researchPaper.arxiv.enabled, true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- runtime-config.test.ts`
Expected: FAIL because `buildRuntimeConfig` does not exist

- [ ] **Step 3: Implement internal config types**

```ts
export interface McpServerConfig {
  id: string;
  transport: "http" | "stdio";
  baseUrl?: string;
  command?: string;
  args?: string[];
  authTokenEnv?: string;
  enabled: boolean;
}

export interface RuntimeConfig {
  builderBaseUrl?: string;
  logLevel: "debug" | "info" | "warn" | "error";
  providers: {
    researchPaper: {
      arxiv: {
        enabled: boolean;
        timeoutMs: number;
        retryOn429: boolean;
        maxRetries: number;
      };
      semanticScholar: {
        enabled: boolean;
        apiKey?: string;
        timeoutMs: number;
        defaultResults: number;
      };
    };
  };
  mcpServers: McpServerConfig[];
  network: {
    httpProxy?: string;
    httpsProxy?: string;
    allProxy?: string;
    noProxy?: string;
    extraCaCerts?: string;
  };
}
```

- [ ] **Step 4: Implement config construction and inject into app startup**

```ts
export function buildRuntimeConfig(source: NodeJS.ProcessEnv = process.env): RuntimeConfig {
  const env = getEnv(source);
  const parsedMcpServers = parseMcpServersJson(env.MCP_SERVERS_JSON);

  return {
    builderBaseUrl: env.BUILDER_BASE_URL,
    logLevel: env.LOG_LEVEL,
    providers: {
      researchPaper: {
        arxiv: {
          enabled: env.ARXIV_ENABLED,
          timeoutMs: env.ARXIV_REQUEST_TIMEOUT_MS,
          retryOn429: env.ARXIV_RETRY_ON_429,
          maxRetries: env.ARXIV_MAX_RETRIES
        },
        semanticScholar: {
          enabled: env.SEMANTIC_SCHOLAR_ENABLED,
          apiKey: env.SEMANTIC_SCHOLAR_API_KEY,
          timeoutMs: env.SEMANTIC_SCHOLAR_REQUEST_TIMEOUT_MS,
          defaultResults: env.SEMANTIC_SCHOLAR_MAX_RESULTS_DEFAULT
        }
      }
    },
    mcpServers: parsedMcpServers,
    network: {
      httpProxy: env.HTTP_PROXY,
      httpsProxy: env.HTTPS_PROXY,
      allProxy: env.ALL_PROXY,
      noProxy: env.NO_PROXY,
      extraCaCerts: env.NODE_EXTRA_CA_CERTS
    }
  };
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `npm test -- runtime-config.test.ts`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add ragenius_execution_subsystem/src/config/runtime-config.ts ragenius_execution_subsystem/src/config/provider-config.ts ragenius_execution_subsystem/src/config/mcp-config.ts ragenius_execution_subsystem/src/app.ts ragenius_execution_subsystem/tests/config/runtime-config.test.ts
git commit -m "feat: add typed runtime config objects"
```

### Task 3: Extract Research Paper Provider and Shared HTTP Client

**Files:**
- Create: `ragenius_execution_subsystem/src/core/tools/providers/http-client.ts`
- Create: `ragenius_execution_subsystem/src/core/tools/providers/research-paper-provider.ts`
- Modify: `ragenius_execution_subsystem/src/core/tools/providers/api-tool-provider.ts`
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Create: `ragenius_execution_subsystem/tests/tools/research-paper-provider.test.ts`
- Test: `ragenius_execution_subsystem/tests/tools/research-paper-provider.test.ts`

- [ ] **Step 1: Write the failing provider extraction test**

```ts
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

import { ResearchPaperProvider } from "../../src/core/tools/providers/research-paper-provider.js";

const originalFetch = globalThis.fetch;

describe("research paper provider", () => {
  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("falls back to semantic scholar when arxiv times out", async () => {
    globalThis.fetch = ((input: string | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("export.arxiv.org")) {
        return new Promise<Response>((_, reject) => {
          init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true });
        });
      }
      return Promise.resolve(
        new Response(JSON.stringify({ data: [{ title: "Semantic fallback", url: "https://example.org", year: 2024, authors: [{ name: "Author" }], abstract: "summary" }] }), { status: 200 })
      );
    }) as typeof fetch;

    const provider = new ResearchPaperProvider({
      arxiv: { enabled: true, timeoutMs: 100, retryOn429: true, maxRetries: 1 },
      semanticScholar: { enabled: true, timeoutMs: 100, defaultResults: 5 }
    });

    const result = await provider.search({
      topic: "DeepSeek",
      limit: 2,
      source: "auto"
    });

    assert.equal(result.source, "semantic-scholar");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- research-paper-provider.test.ts`
Expected: FAIL because `ResearchPaperProvider` does not exist

- [ ] **Step 3: Implement the shared HTTP client seam**

```ts
export async function fetchWithTimeout(
  input: string | URL,
  init: RequestInit,
  timeoutMs: number
): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, {
      ...init,
      signal: controller.signal
    });
  } finally {
    clearTimeout(timeout);
  }
}
```

- [ ] **Step 4: Extract research-paper provider into its own class**

```ts
export class ResearchPaperProvider {
  constructor(private readonly config: RuntimeConfig["providers"]["researchPaper"]) {}

  async search(input: { topic: string; limit: number; source: string }) {
    // move arxiv and semantic scholar logic here
  }
}
```

- [ ] **Step 5: Rewire `api-tool-provider.ts` to delegate**

```ts
if (tool.id === "research_paper_search_tool") {
  return this.researchPaperProvider.search({
    topic,
    limit,
    source: requestedSource
  });
}
```

- [ ] **Step 6: Run tests to verify extraction works**

Run: `npm test -- research-paper-provider.test.ts tool-engine.test.ts execute-skill.test.ts`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add ragenius_execution_subsystem/src/core/tools/providers/http-client.ts ragenius_execution_subsystem/src/core/tools/providers/research-paper-provider.ts ragenius_execution_subsystem/src/core/tools/providers/api-tool-provider.ts ragenius_execution_subsystem/src/app.ts ragenius_execution_subsystem/tests/tools/research-paper-provider.test.ts
git commit -m "refactor: extract research paper provider"
```

### Task 4: Register MCP Servers from Typed Config

**Files:**
- Create: `ragenius_execution_subsystem/src/core/mcp/mcp-server-registry.ts`
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Create: `ragenius_execution_subsystem/tests/mcp/mcp-server-registry.test.ts`
- Test: `ragenius_execution_subsystem/tests/mcp/mcp-server-registry.test.ts`

- [ ] **Step 1: Write the failing MCP registry test**

```ts
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { McpServerRegistry } from "../../src/core/mcp/mcp-server-registry.js";

describe("mcp server registry", () => {
  it("returns enabled configured mcp servers", () => {
    const registry = new McpServerRegistry([
      {
        id: "local-browser",
        transport: "http",
        baseUrl: "http://127.0.0.1:4100",
        enabled: true
      }
    ]);

    assert.equal(registry.list()[0]?.id, "local-browser");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- mcp-server-registry.test.ts`
Expected: FAIL because `McpServerRegistry` does not exist

- [ ] **Step 3: Implement MCP registry**

```ts
export class McpServerRegistry {
  constructor(private readonly servers: McpServerConfig[]) {}

  list(): McpServerConfig[] {
    return this.servers.filter((server) => server.enabled);
  }

  get(id: string): McpServerConfig | undefined {
    return this.servers.find((server) => server.id === id && server.enabled);
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- mcp-server-registry.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/src/core/mcp/mcp-server-registry.ts ragenius_execution_subsystem/tests/mcp/mcp-server-registry.test.ts
git commit -m "feat: add mcp server runtime registry"
```

### Task 5: Add Non-Secret Runtime Readiness Visibility

**Files:**
- Modify: `ragenius_execution_subsystem/src/api/routes/health.routes.ts`
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Test: `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`

- [ ] **Step 1: Write the failing readiness assertion**

```ts
assert.equal(response.json().checks.builder_configured, true);
assert.equal(response.json().checks.research_paper_provider_enabled, true);
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- execute-skill.test.ts`
Expected: FAIL because readiness payload does not include those checks

- [ ] **Step 3: Implement non-secret readiness checks**

```ts
return reply.send({
  status: "ready",
  checks: {
    database: "not_configured",
    builder_configured: Boolean(app.services.runtimeConfig.builderBaseUrl),
    research_paper_provider_enabled: app.services.runtimeConfig.providers.researchPaper.arxiv.enabled
      || app.services.runtimeConfig.providers.researchPaper.semanticScholar.enabled,
    mcp_servers_configured: app.services.runtimeConfig.mcpServers.length
  }
});
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- execute-skill.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/src/api/routes/health.routes.ts ragenius_execution_subsystem/src/app.ts ragenius_execution_subsystem/tests/execution/execute-skill.test.ts
git commit -m "feat: expose non-secret runtime readiness checks"
```

### Task 6: Add Execution Persistence Seam

**Files:**
- Create: `ragenius_execution_subsystem/src/core/execution/execution-store.ts`
- Create: `ragenius_execution_subsystem/tests/execution/execution-store.test.ts`
- Modify: `ragenius_execution_subsystem/src/core/execution/execution-engine.ts`
- Test: `ragenius_execution_subsystem/tests/execution/execution-store.test.ts`

- [ ] **Step 1: Write the failing execution-store test**

```ts
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { InMemoryExecutionStore } from "../../src/core/execution/execution-store.js";

describe("execution store", () => {
  it("creates and returns execution records", async () => {
    const store = new InMemoryExecutionStore();
    const id = await store.create({ skillId: "research_paper_finder", appId: "app_001", status: "running" });
    const record = await store.get(id);
    assert.equal(record?.skillId, "research_paper_finder");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- execution-store.test.ts`
Expected: FAIL because execution store seam does not exist

- [ ] **Step 3: Implement minimal execution-store interface**

```ts
export interface ExecutionStore {
  create(input: { skillId: string; appId: string; status: string }): Promise<string>;
  get(id: string): Promise<{ id: string; skillId: string; appId: string; status: string } | null>;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- execution-store.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/src/core/execution/execution-store.ts ragenius_execution_subsystem/tests/execution/execution-store.test.ts ragenius_execution_subsystem/src/core/execution/execution-engine.ts
git commit -m "feat: add execution persistence seam"
```

### Task 7: Implement Execution Lookup APIs

**Files:**
- Create: `ragenius_execution_subsystem/src/core/execution/execution-status-service.ts`
- Modify: `ragenius_execution_subsystem/src/api/routes/executions.routes.ts`
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Test: `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`

- [ ] **Step 1: Write the failing route test**

```ts
const response = await app.inject({
  method: "GET",
  url: "/v1/executions/execution_001"
});

assert.equal(response.statusCode, 200);
assert.equal(response.json().execution_id, "execution_001");
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- execute-skill.test.ts`
Expected: FAIL because route returns `501`

- [ ] **Step 3: Implement lookup service and route**

```ts
app.get("/executions/:execution_id", async (request, reply) => {
  const executionId = (request.params as { execution_id: string }).execution_id;
  const execution = await app.services.executionStatusService.get(executionId);
  if (!execution) {
    return reply.status(404).send({
      error: {
        code: "EXECUTION_NOT_FOUND",
        message: "Execution record was not found."
      }
    });
  }
  return reply.send(execution);
});
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- execute-skill.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/src/core/execution/execution-status-service.ts ragenius_execution_subsystem/src/api/routes/executions.routes.ts ragenius_execution_subsystem/src/app.ts ragenius_execution_subsystem/tests/execution/execute-skill.test.ts
git commit -m "feat: implement execution lookup route"
```

### Task 8: Implement Confirmation Resume Contract

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/execution/execution-engine.ts`
- Modify: `ragenius_execution_subsystem/src/api/routes/executions.routes.ts`
- Test: `ragenius_execution_subsystem/tests/execution/permission-block.test.ts`

- [ ] **Step 1: Write the failing resume test**

```ts
const response = await app.inject({
  method: "POST",
  url: "/v1/executions/execution_001/confirm",
  payload: { approved: true }
});

assert.equal(response.statusCode, 200);
assert.equal(response.json().status, "completed");
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- permission-block.test.ts`
Expected: FAIL because confirm route does not exist

- [ ] **Step 3: Implement minimal resume API contract**

```ts
app.post("/executions/:execution_id/confirm", async (request, reply) => {
  const executionId = (request.params as { execution_id: string }).execution_id;
  const body = request.body as { approved?: boolean };
  if (body.approved !== true) {
    return reply.status(400).send({
      error: {
        code: "VALIDATION_ERROR",
        message: "approved must be true for confirmation."
      }
    });
  }
  const result = await app.services.executionStatusService.confirm(executionId);
  return reply.send(result);
});
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- permission-block.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/src/core/execution/execution-engine.ts ragenius_execution_subsystem/src/api/routes/executions.routes.ts ragenius_execution_subsystem/tests/execution/permission-block.test.ts
git commit -m "feat: add confirmation resume api"
```

### Task 9: Expand Workflow Support Safely

**Files:**
- Modify: `ragenius_execution_subsystem/src/core/workflow/workflow-orchestrator.ts`
- Modify: `ragenius_execution_subsystem/src/core/workflow/workflow.types.ts`
- Test: `ragenius_execution_subsystem/tests/workflow/workflow-orchestrator.test.ts`

- [ ] **Step 1: Write the failing workflow branching test**

```ts
it("supports local decision branching", async () => {
  // setup workflow with local_decision branch
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- workflow-orchestrator.test.ts`
Expected: FAIL because only a narrow step subset executes today

- [ ] **Step 3: Implement one additional workflow step type at a time**

```ts
if (currentStep.type === "local_decision") {
  const nextStepId = this.evaluateLocalDecision(currentStep, context);
  currentStep = nextStepId ? stepsById.get(nextStepId) : undefined;
  continue;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- workflow-orchestrator.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/src/core/workflow/workflow-orchestrator.ts ragenius_execution_subsystem/src/core/workflow/workflow.types.ts ragenius_execution_subsystem/tests/workflow/workflow-orchestrator.test.ts
git commit -m "feat: add local decision workflow support"
```

### Task 10: Update Operational Documentation

**Files:**
- Modify: `ragenius_execution_subsystem/README.md`
- Create: `ragenius_execution_subsystem/docs/runtime-config.md`
- Test: `README` / docs review

- [ ] **Step 1: Write the docs section content**

```md
## Runtime Configuration Contract

The execution subsystem loads provider, transport, and MCP runtime settings from environment variables at startup.

- Secrets remain runtime-only.
- Builder remains the source of truth for skill definitions and app bindings.
- Non-secret readiness details are available through `/readyz`.
```

- [ ] **Step 2: Add explicit env variable examples**

```env
BUILDER_BASE_URL=http://127.0.0.1:8011
ARXIV_ENABLED=true
SEMANTIC_SCHOLAR_ENABLED=true
MCP_SERVERS_JSON=[]
```

- [ ] **Step 3: Review docs for consistency with code**

Run: `rg -n "ARXIV_|SEMANTIC_SCHOLAR_|MCP_SERVERS_JSON|BUILDER_BASE_URL" ragenius_execution_subsystem`
Expected: env names match between docs and code

- [ ] **Step 4: Commit**

```bash
git add ragenius_execution_subsystem/README.md ragenius_execution_subsystem/docs/runtime-config.md
git commit -m "docs: add execution subsystem runtime config contract"
```

---

## Phase Exit Criteria

### Multi-skill beta readiness

The subsystem is ready for a broader beta when all of these are true:

- typed runtime config is validated at startup
- at least three real skill contracts run through Builder-managed fallback
- at least one real API provider, one RAG provider, and one MCP-backed provider are live
- execution records can be persisted and queried
- confirmation resume flow exists
- readiness/debug surfaces expose non-secret config state
- tool/provider failures are observable and classified consistently

### Production hardening readiness

The subsystem is ready for production hardening when all of these are true:

- multi-skill beta has stabilized
- provider config is no longer hardcoded
- secrets are fully externalized
- runtime logs and tracing are trustworthy
- execution persistence and log retrieval are complete
- transport/proxy/CA behavior is documented and testable

---

## Gap Summary

From this working vertical slice to a broader subsystem, the primary gaps are:

- runtime config maturity
- MCP runtime configuration
- real provider extraction and reuse
- execution persistence
- execution retrieval APIs
- confirmation resume APIs
- richer workflow step support
- operator visibility and docs

The architecture itself is already validated by the working Builder-managed skill path. The remaining work is structured implementation, not basic architectural uncertainty.

