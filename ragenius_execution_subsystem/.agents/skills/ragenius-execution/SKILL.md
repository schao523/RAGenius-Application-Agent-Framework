

## `SKILL.md`

    ---
    name: ragenius-execution
    description: Use when modifying the RAGenius Execution Subsystem, especially execution lifecycle, skills, workflow orchestration, tools, MCP adapters, RAG adapter, permissions, result normalization, or audit logging.
    ---
    
    # RAGenius Execution Skill Guidance
    
    Use this skill when working on `ragenius_execution_subsystem`.
    
    ## Purpose
    
    This subsystem is a controlled execution backend. It receives structured execution requests, validates them, executes registered skills, orchestrates approved tools, enforces permissions, records trace logs, and returns normalized results.
    
    ## Boundaries
    
    Do not add responsibilities that belong to other RAGenius subsystems.
    
    ```text
    ragenius_app
      = reasoning, planning, user-facing answers
    
    ragenius_execution_subsystem
      = controlled execution of skills through tools
    
    rag_subsystem
      = ingestion and retrieval only
    
    ragenius_builder
      = app configuration

This subsystem must not:

* perform LLM-first reasoning or planning
* generate final conversational answers
* manage app instructions
* own user-facing UI
* ingest or mutate RAG data
* execute tools without permission checks
* log raw secrets

## Core Rules

* App plans; execution subsystem executes.
* Skills are the primary execution unit.
* Workflows are internal to skills.
* Tools are invoked only through the unified `ToolEngine`.
* MCP is a dynamic tool provider layer.
* RAG is read-only through `rag_retrieval_tool`.
* Permission checks happen before every tool call.
* Unknown tools are denied by default.
* Unknown or disabled skills are denied by default.
* Results must use the standardized envelope.
* Errors must be classified.
* Logs must redact secrets.

## Standard Execution Request

    {
      "request_type": "execute_skill",
      "app_id": "app_001",
      "session_id": "sess_001",
      "skill_id": "video_director_skill",
      "input": {
        "prompt": "Explain RAG simply",
        "duration": 30
      },
      "execution_options": {
        "dry_run": false,
        "require_confirmation": false
      }
    }

## Standard Result Envelope

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

## Execution Lifecycle

When implementing or modifying execution behavior, preserve this lifecycle:
    1. Validate request envelope.
    2. Reject unsupported request_type.
    3. Load skill by skill_id.
    4. Reject unknown or disabled skill.
    5. Validate input against skill schema.
    6. Resolve required tools.
    7. Check permissions.
    8. If dry_run=true, return preview without side effects.
    9. Create execution context.
    10. Run internal workflow.
    11. Execute tool calls through ToolEngine.
    12. Normalize results.
    13. Run compensation if needed.
    14. Write trace logs.
    15. Return standardized response.

## Permission Modes

    type PermissionMode =
      | "auto_allow"
      | "restricted"
      | "require_confirmation"
      | "blocked";

Behavior:

* `auto_allow`: continue after validation.
* `restricted`: check configured constraints.
* `require_confirmation`: pause and return pending confirmation result.
* `blocked`: stop and return permission error.

## Tool Provider Types

Supported providers:

* `local`
* `api`
* `mcp`
* `rag_adapter`

Every provider should conform to the internal tool execution interface. Do not call provider-specific tools directly from workflow code.

## MCP Guidance

MCP tools are dynamically discovered but not automatically trusted.

For discovered tools:

* map to internal schema
* assign permission scopes
* mark side-effecting behavior
* validate input
* enforce timeout
* check permissions before execution

## RAG Guidance

RAG is read-only.

Allowed:
    rag_retrieval_tool → rag_subsystem

Not allowed:

* ingestion
* mutation
* deletion
* index updates
* permission policy changes

## Logging Guidance

Log summaries, not raw sensitive payloads.

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

## Tests to Add or Update

When behavior changes, update tests for:

* valid skill execution
* request validation
* unknown skill rejection
* skill input validation
* dry-run safety
* permission block
* require-confirmation behavior
* MCP discovery
* RAG read-only behavior
* timeout classification
* tool error classification
* compensation behavior
* result normalization
* log redaction

## Completion Checklist

Before finalizing changes, run:
    npm run lint
    npm run typecheck
    npm test

If a command cannot run, state why and what remains unverified.
