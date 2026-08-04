# RAGenius Execution Subsystem MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the validated MVP of `ragenius_execution_subsystem` as a controlled execution backend that accepts structured skill requests, executes approved tools through a unified runtime, enforces permissions, logs safely, and returns normalized results.

**Architecture:** Start with a thin vertical slice that proves the core lifecycle end to end: request validation -> skill loading -> tool resolution -> permission check -> workflow execution -> normalized result. Keep all external integrations mock-safe, use declarative manifests from day one, and add persistence and broader API surface only after the in-memory execution path is passing tests.

**Tech Stack:** Node.js 20+, TypeScript, Fastify, Zod, Vitest, ESLint, Prettier, Prisma, PostgreSQL, npm

---

## Scope and Milestone Rules

- This plan covers `ragenius_execution_subsystem` only.
- MVP means "first production-shaped slice", not throwaway prototype.
- Do not implement full-runtime queue workers, confirmation resume, or rich admin mutation APIs in this plan.
- Do not add LLM planning, final answer generation, RAG ingestion, or app-level instruction management.
- Every milestone must end with targeted tests before moving forward.

## Target File Structure

**Create:**
- `ragenius_execution_subsystem/package.json`
- `ragenius_execution_subsystem/tsconfig.json`
- `ragenius_execution_subsystem/eslint.config.js`
- `ragenius_execution_subsystem/prettier.config.js`
- `ragenius_execution_subsystem/.gitignore`
- `ragenius_execution_subsystem/.env.example`
- `ragenius_execution_subsystem/docker-compose.yml`
- `ragenius_execution_subsystem/prisma/schema.prisma`
- `ragenius_execution_subsystem/src/server.ts`
- `ragenius_execution_subsystem/src/app.ts`
- `ragenius_execution_subsystem/src/config/env.ts`
- `ragenius_execution_subsystem/src/api/routes/health.routes.ts`
- `ragenius_execution_subsystem/src/api/routes/executions.routes.ts`
- `ragenius_execution_subsystem/src/api/routes/skills.routes.ts`
- `ragenius_execution_subsystem/src/api/routes/tools.routes.ts`
- `ragenius_execution_subsystem/src/api/schemas/execution-request.schema.ts`
- `ragenius_execution_subsystem/src/api/schemas/common-response.schema.ts`
- `ragenius_execution_subsystem/src/core/errors/app-error.ts`
- `ragenius_execution_subsystem/src/core/errors/error-classifier.ts`
- `ragenius_execution_subsystem/src/core/execution/execution-context.ts`
- `ragenius_execution_subsystem/src/core/execution/execution-engine.ts`
- `ragenius_execution_subsystem/src/core/execution/result-normalizer.ts`
- `ragenius_execution_subsystem/src/core/skills/skill.types.ts`
- `ragenius_execution_subsystem/src/core/skills/skill-registry.ts`
- `ragenius_execution_subsystem/src/core/skills/sample-skills.ts`
- `ragenius_execution_subsystem/src/core/workflow/workflow.types.ts`
- `ragenius_execution_subsystem/src/core/workflow/workflow-orchestrator.ts`
- `ragenius_execution_subsystem/src/core/workflow/compensation-engine.ts`
- `ragenius_execution_subsystem/src/core/tools/tool.types.ts`
- `ragenius_execution_subsystem/src/core/tools/tool-registry.ts`
- `ragenius_execution_subsystem/src/core/tools/tool-engine.ts`
- `ragenius_execution_subsystem/src/core/tools/providers/local-tool-provider.ts`
- `ragenius_execution_subsystem/src/core/tools/providers/api-tool-provider.ts`
- `ragenius_execution_subsystem/src/core/tools/providers/mcp-tool-provider.ts`
- `ragenius_execution_subsystem/src/core/tools/providers/rag-adapter-provider.ts`
- `ragenius_execution_subsystem/src/core/permissions/permission.types.ts`
- `ragenius_execution_subsystem/src/core/permissions/permission-engine.ts`
- `ragenius_execution_subsystem/src/core/logging/logger.ts`
- `ragenius_execution_subsystem/src/core/logging/audit-log.ts`
- `ragenius_execution_subsystem/src/db/prisma.ts`
- `ragenius_execution_subsystem/src/utils/redact.ts`
- `ragenius_execution_subsystem/src/utils/ids.ts`
- `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`
- `ragenius_execution_subsystem/tests/execution/dry-run.test.ts`
- `ragenius_execution_subsystem/tests/execution/permission-block.test.ts`
- `ragenius_execution_subsystem/tests/tools/tool-engine.test.ts`
- `ragenius_execution_subsystem/tests/tools/mcp-discovery.test.ts`
- `ragenius_execution_subsystem/tests/tools/rag-adapter.test.ts`
- `ragenius_execution_subsystem/tests/workflow/workflow-orchestrator.test.ts`

**Modify:**
- `ragenius_execution_subsystem/README.md`
- `ragenius_execution_subsystem/AGENTS.md`
- `ragenius_execution_subsystem/.agents/skills/ragenius-execution/SKILL.md`
- `ragenius_execution_subsystem/docs/architecture.md`
- `ragenius_execution_subsystem/docs/api-contract.md`
- `ragenius_execution_subsystem/docs/security.md`
- `ragenius_execution_subsystem/docs/workflow-execution-map.yaml`

## Milestone 1: Bootstrap the Subsystem Repo

**Outcome:** The subsystem becomes a runnable TypeScript service workspace with test, lint, and typecheck entry points, but no business logic yet.

**Files:**
- Create: repo root config and `src/` skeleton files listed above
- Modify: `README.md`

- [ ] Initialize `package.json` with `dev`, `build`, `lint`, `typecheck`, and `test` scripts.
- [ ] Add TypeScript, Fastify, Zod, Vitest, ESLint, Prettier, Prisma, and test typings.
- [ ] Create the `src/` folder layout without implementation-heavy logic.
- [ ] Add `.env.example` with placeholders only and `docker-compose.yml` for local PostgreSQL.
- [ ] Add a minimal Fastify app exposing only `GET /healthz` and `GET /readyz`.
- [ ] Add one smoke test proving the app boots and returns `200` for `/healthz`.

**Exit criteria:**
- `npm run lint`, `npm run typecheck`, and `npm test` execute successfully.
- The repo has a clear implementation skeleton that matches the docs.

## Milestone 2: Lock the Core Contracts First

**Outcome:** The MVP request/response shapes, error classes, permission modes, and tool provider types are encoded before runtime logic grows around them.

**Files:**
- Create: `src/api/schemas/*.ts`, `src/core/errors/*.ts`, `src/core/permissions/permission.types.ts`, `src/core/tools/tool.types.ts`, `src/core/skills/skill.types.ts`, `src/core/workflow/workflow.types.ts`
- Test: `tests/execution/execute-skill.test.ts`

- [ ] Implement the `ExecutionRequest` Zod schema and exported TypeScript type.
- [ ] Implement the normalized result envelope type and shared error object type.
- [ ] Add explicit string unions for `ErrorClass`, `PermissionMode`, and `ToolProviderType`.
- [ ] Define `ToolDefinition`, `SkillDefinition`, workflow step types, and execution context shape.
- [ ] Add request-schema tests for valid payloads, missing required fields, and bad `request_type`.
- [ ] Add centralized HTTP-safe error mapping so route handlers do not leak stack traces.

**Exit criteria:**
- Invalid execution requests fail at the API boundary.
- Contract types are imported by later layers instead of being redefined ad hoc.

## Milestone 3: Implement Skill and Tool Registries with Mock Providers

**Outcome:** The subsystem can load one sample skill and resolve one read-only RAG tool plus one side-effecting mock API tool through a single tool runtime path.

**Files:**
- Create: `src/core/skills/*`, `src/core/tools/*`, provider files under `src/core/tools/providers/`
- Test: `tests/tools/tool-engine.test.ts`, `tests/tools/mcp-discovery.test.ts`, `tests/tools/rag-adapter.test.ts`

- [ ] Build an in-memory `SkillRegistry` that denies unknown or disabled skills.
- [ ] Register `video_director_skill` as the only MVP skill, with input schema `{ prompt, duration }`.
- [ ] Build an in-memory `ToolRegistry` with `rag_retrieval_tool` and `mock_video_generation_tool`.
- [ ] Implement `ToolEngine` as the only path allowed to invoke providers.
- [ ] Implement mock provider adapters:
- [ ] `rag_adapter` provider returns fake retrieval items and has no mutation path.
- [ ] `api` provider returns fake video metadata and is marked `sideEffecting: true`.
- [ ] `mcp` provider supports mock discovery only and maps discovered tools into internal `ToolDefinition`.
- [ ] Add tool tests for input validation, unknown tool rejection, timeout classification, provider failure classification, MCP mapping, and RAG read-only behavior.

**Exit criteria:**
- `GET /v1/skills` and `GET /v1/tools` can be built on top of working registries.
- All tool execution passes through validation and normalized error handling.

## Milestone 4: Add Permission Enforcement Before Every Tool Call

**Outcome:** The system enforces `auto_allow`, `restricted`, `require_confirmation`, and `blocked` consistently before tools run.

**Files:**
- Create: `src/core/permissions/permission-engine.ts`
- Modify: `src/core/tools/tool-engine.ts`, `src/core/execution/execution-engine.ts`
- Test: `tests/execution/permission-block.test.ts`, extend `tests/tools/tool-engine.test.ts`

- [ ] Implement an in-memory policy store keyed by `app_id`, `tool_id`, and `scope`.
- [ ] Make read-only RAG calls default to safe allowance in MVP.
- [ ] Make side-effecting tools require explicit policy and never silently auto-allow.
- [ ] Return `pending_confirmation` without executing the tool when policy mode is `require_confirmation`.
- [ ] Return structured permission errors when policy mode is `blocked`.
- [ ] Evaluate `restricted` conditions using simple safe predicates only.
- [ ] Add tests proving permission checks happen before provider invocation.

**Exit criteria:**
- Blocked tools are never called.
- Dry run still performs policy evaluation.
- Permission decisions are traceable and deterministic.

## Milestone 5: Build the MVP Workflow and Execution Engine

**Outcome:** One validated execution request can run end to end through the documented lifecycle and return a standardized envelope.

**Files:**
- Create: `src/core/execution/*`, `src/core/workflow/*`, `src/utils/ids.ts`
- Modify: registries and permission engine as needed
- Test: `tests/execution/execute-skill.test.ts`, `tests/execution/dry-run.test.ts`, `tests/workflow/workflow-orchestrator.test.ts`

- [ ] Implement execution lifecycle in this order:
- [ ] validate request envelope
- [ ] load skill
- [ ] validate skill input
- [ ] resolve required tools
- [ ] check permissions
- [ ] short-circuit dry run
- [ ] create execution context
- [ ] execute internal workflow
- [ ] normalize result
- [ ] log summary
- [ ] Implement a declarative workflow orchestrator supporting:
- [ ] `validation`
- [ ] `tool_call`
- [ ] `local_decision`
- [ ] `service_call`
- [ ] `end`
- [ ] Keep `saga` and compensation minimal for MVP: support the interface, but only add a simple compensation hook needed by tests.
- [ ] Map step outputs into execution context so the sample skill can retrieve context then generate a video result.
- [ ] Return `completed`, `failed`, `partial`, and `pending_confirmation` using the normalized envelope only.
- [ ] Add tests for valid execution, invalid skill input, dry-run safety, workflow failure classification, partial result handling if implemented, and compensation hook behavior if enabled.

**Exit criteria:**
- `video_director_skill` executes end to end without real external calls.
- Dry run never triggers side-effecting provider execution.
- Terminal responses always match the normalized envelope.

## Milestone 6: Expose the MVP REST Surface

**Outcome:** The documented MVP API exists for health, execution submission, skill inspection, tool inspection, and mock MCP discovery.

**Files:**
- Create: all route files under `src/api/routes/`
- Modify: `src/app.ts`, `src/server.ts`
- Test: extend execution and tool tests with HTTP-level coverage

- [ ] Implement `POST /v1/executions`.
- [ ] Implement `GET /v1/skills` and `GET /v1/skills/:skill_id`.
- [ ] Implement `GET /v1/tools`.
- [ ] Implement `POST /v1/tools/discover/mcp`.
- [ ] Add placeholder-but-correct `GET /v1/executions/:execution_id` and `GET /v1/executions/:execution_id/logs` behavior only if backed by real state; otherwise keep them clearly documented as MVP-limited.
- [ ] Ensure all route handlers convert domain failures into structured HTTP responses from the API contract.
- [ ] Add route-level tests for completed execution, dry run, pending confirmation, unknown skill, and permission blocked cases.

**Exit criteria:**
- The API contract is true for implemented routes.
- No normal response exposes stack traces or raw provider payloads.

## Milestone 7: Add Persistence and Redacted Logging Without Overbuilding

**Outcome:** The subsystem can persist core execution records and produce safe summaries, while remaining MVP-sized.

**Files:**
- Create: `prisma/schema.prisma`, `src/db/prisma.ts`, `src/core/logging/*`, `src/utils/redact.ts`
- Modify: execution engine and route handlers
- Test: extend execution tests; add focused redaction tests

- [ ] Define Prisma models for `Execution`, `Skill`, `WorkflowStep`, `Tool`, `ToolCall`, `PermissionPolicy`, `McpProvider`, and `ExecutionLog`.
- [ ] Use JSON fields for dynamic schemas and summaries rather than premature table expansion.
- [ ] Wire persistence behind small repository functions, not directly from route handlers.
- [ ] Persist only summaries and metadata needed by MVP retrieval routes.
- [ ] Implement redaction for authorization headers, bearer tokens, cookies, API keys, passwords, secrets, and private keys.
- [ ] Add tests proving logs redact secrets and retain useful step/tool summaries.
- [ ] If a live PostgreSQL instance is unavailable, still make `npx prisma validate` and `npx prisma generate` pass.

**Exit criteria:**
- Persistence schema matches the documented contract closely enough for MVP.
- No raw secrets are stored or logged.

## Milestone 8: Align Docs, Agent Guidance, and Full Validation

**Outcome:** The code, docs, and agent instructions say the same thing, and the MVP is verifiably complete.

**Files:**
- Modify: `README.md`, `AGENTS.md`, `.agents/skills/ragenius-execution/SKILL.md`, `docs/*.md`, `docs/workflow-execution-map.yaml`

- [ ] Update `README.md` to match implemented setup, routes, examples, and MVP limitations.
- [ ] Update subsystem docs if implementation differs from current contract wording.
- [ ] Keep MCP, queue/worker, and confirmation resume explicitly labeled as mock, stubbed, or deferred when not fully implemented.
- [ ] Run the full validation set:
- [ ] `npm run lint`
- [ ] `npm run typecheck`
- [ ] `npm test`
- [ ] `npm run build`
- [ ] `npx prisma validate`
- [ ] Record any not-run or blocked commands with exact reasons.

**Exit criteria:**
- Docs describe the real MVP, not the desired future runtime.
- The subsystem is ready for a separate "upgrade to full runtime" plan rather than forcing both scopes into one pass.

## Milestone Ordering Rationale

1. Bootstrap first so the subsystem is runnable.
2. Lock contracts before logic to avoid churn.
3. Prove registries and provider indirection before orchestration.
4. Enforce permissions before side effects.
5. Implement the end-to-end lifecycle only after the lower layers exist.
6. Add the HTTP surface after the domain runtime works.
7. Add persistence and safe logging after the in-memory flow is proven.
8. Align docs only after the implementation is real.

## Risks to Watch During Execution

- Building too much of the full-runtime queue/worker model into MVP.
- Letting workflow code invoke providers directly instead of going through `ToolEngine`.
- Treating MCP discovery as trusted execution instead of registry input.
- Overcomplicating compensation before the base workflow passes tests.
- Persisting raw request or tool payloads that may carry secrets.
- Documenting future-state routes as complete when the backend is still mock-backed.

## Definition of MVP Done

- One sample skill can execute end to end.
- Tool calls are validated, permission-checked, timed, and normalized.
- RAG access is read-only.
- Side-effecting tool execution is blocked, allowed, or paused by policy.
- Dry run never performs side effects.
- API routes return deterministic structured results.
- Logging is useful and redacted.
- Prisma schema validates.
- Lint, typecheck, and tests pass.
