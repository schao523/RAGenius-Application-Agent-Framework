* * *

## `AGENTS.md`

    # AGENTS.md
    
    ## Project Purpose
    
    This repository implements `ragenius_execution_subsystem`, the controlled execution backend for the RAGenius system.
    
    The subsystem receives structured execution requests from `ragenius_app`, validates them, loads skills, executes internal skill workflows, orchestrates tools, enforces permissions, records trace logs, and returns standardized execution results.
    
    ## Non-Negotiable Boundaries
    
    - Do not add LLM-first reasoning or planning to this subsystem.
    - Do not generate final conversational answers from this subsystem.
    - Do not implement RAG ingestion here.
    - Do not manage application-level instructions here.
    - Do not treat MCP tools as trusted by default.
    - Do not commit secrets.
    - Do not log raw credentials.
    - Do not execute unknown tools.
    - Do not execute unknown or disabled skills.
    - Do not bypass permission checks.
    - Do not allow RAG mutation.
    
    ## System Boundary
    
    ```text
    ragenius_app
      = reasoning, planning, final conversational answer generation
    
    ragenius_execution_subsystem
      = skill execution through controlled tools
    
    rag_subsystem
      = ingestion and retrieval only
    
    ragenius_builder
      = app configuration

## Core Architecture Rules

* App plans; execution subsystem executes.
* Skills are the primary execution unit.
* Workflows are internal to skills.
* Tools are invoked only through the unified `ToolEngine`.
* MCP is a dynamic tool provider layer.
* RAG is read-only through `rag_retrieval_tool`.
* Permission checks must run before every tool call.
* Results must use the standardized result envelope.
* Errors must be classified.
* Logs must redact secrets.

## Standard Result Envelope

All terminal execution results must use this shape:
    type NormalizedExecutionResult = {
      status: "completed" | "failed" | "partial" | "blocked" | "pending_confirmation";
      result_type: "text" | "json" | "file" | "video";
      result: Record<string, unknown>;
      files: Array<Record<string, unknown>>;
      errors: Array<{
        code: string;
        message: string;
        details?: unknown;
        recoverable: boolean;
        suggested_action: string;
      }>;
      logs_summary: string;
    };

## Permission Modes

    type PermissionMode =
      | "auto_allow"
      | "restricted"
      | "require_confirmation"
      | "blocked";

Use these rules:

* `auto_allow`: execute after validation.
* `restricted`: execute only if configured constraints pass.
* `require_confirmation`: pause and return pending confirmation result.
* `blocked`: stop execution and return permission error.

## Error Classes

Classify all errors as one of:

* `validation`
* `permission`
* `tool`
* `workflow`
* `timeout`
* `external_api`

## Tool Provider Types

Supported provider types:

* `local`
* `api`
* `mcp`
* `rag_adapter`

Every tool definition must include:

* `id`
* `name`
* `providerType`
* `inputSchema`
* `outputSchema`
* `permissionScopes`
* `timeoutMs`
* `sideEffecting`

## Security Requirements

Always redact:

* API keys
* bearer tokens
* authorization headers
* cookies
* access tokens
* refresh tokens
* passwords
* private keys
* secrets

Never place real values in `.env.example`.

## Testing Expectations

Before completing any task, run:
    npm run lint
    npm run typecheck
    npm test

If a command cannot run, explain why and what remains unverified.

## Documentation Expectations

When changing architecture, APIs, permissions, workflows, or security behavior, update the relevant docs:

* `README.md`
* `docs/architecture.md`
* `docs/api-contract.md`
* `docs/security.md`
* `docs/workflow-execution-map.yaml`

## Preferred Implementation Style

* Keep modules small and focused.

* Prefer dependency injection for registries and providers.

* Avoid hidden network calls in tests.

* Mock external APIs, MCP providers, and RAG for tests.

* Avoid `any` unless unavoidable.

* Prefer explicit error types.

* Keep public API responses deterministic.

* Store dynamic tool/skill schemas as JSON where needed.

* * *
