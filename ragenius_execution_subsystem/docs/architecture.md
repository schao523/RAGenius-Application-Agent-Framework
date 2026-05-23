
    ## architecture.md

    ```markdown
    # RAGenius Execution Subsystem Architecture

    ## Purpose

    `ragenius_execution_subsystem` is a controlled execution backend for the RAGenius system.

    Its purpose is to safely execute structured skill requests by orchestrating tools through validated workflows while maintaining permission control, traceability, and standardized results.

    ## System Boundaries

    ```text
    ragenius_app
      → owns reasoning, planning, and final conversational answers

    ragenius_execution_subsystem
      → owns validated execution of skills through tools

    rag_subsystem
      → owns knowledge ingestion and retrieval

    ragenius_builder
      → owns app configuration

The execution subsystem does not perform LLM-first reasoning or planning. It only executes requests that have already been structured by `ragenius_app`.

## Primary Data Flow

    1. ragenius_app creates an internal action plan.
    2. ragenius_app transforms the plan into a Structured Execution Request.
    3. ragenius_execution_subsystem validates the request.
    4. Skill registry loads the target skill.
    5. Skill input is validated against the skill input schema.
    6. Required tools are resolved through the tool registry.
    7. Permission engine checks tool and scope policies.
    8. Execution context is created.
    9. Workflow orchestrator runs the skill's internal workflow.
    10. Tool engine invokes local, API, MCP, or RAG-adapter tools.
    11. Result normalizer creates a standard output envelope.
    12. Logger records execution, step, tool, and error summaries.
    13. API returns the normalized result.

## Core Components

### 1. API Layer

Responsible for:

* Receiving REST requests
* Validating request envelopes
* Returning consistent API responses
* Mapping domain errors to HTTP responses

Primary routes:

| Route                                   | Purpose                       |
| --------------------------------------- | ----------------------------- |
| `POST /v1/executions`                   | Submit execution request      |
| `GET /v1/executions/:execution_id`      | Fetch execution status/result |
| `GET /v1/executions/:execution_id/logs` | Fetch execution logs          |
| `GET /v1/skills`                        | List skills                   |
| `GET /v1/skills/:skill_id`              | Inspect skill metadata        |
| `GET /v1/tools`                         | List tools                    |
| `POST /v1/tools/discover/mcp`           | Discover MCP tools            |

### 2. Skill Execution Engine

Responsible for:

* Interpreting structured execution requests
* Loading skills
* Validating skill input
* Starting workflow execution
* Coordinating result normalization

A skill is the primary execution unit.

A skill includes:

* `id`
* `name`
* `version`
* `input_schema`
* `output_schema`
* `required_tools`
* `required_permissions`
* `workflow_definition`
* `enabled`

### 3. Skill Registry

Responsible for:

* Registering available skills
* Loading skill definitions by `skill_id`
* Rejecting unknown or disabled skills
* Providing skill metadata to API routes

For MVP, the registry may contain in-memory sample skills. Production implementations may load skills from PostgreSQL or configuration files.

### 4. Workflow Orchestrator

Responsible for:

* Executing ordered steps inside a skill
* Passing outputs between steps
* Supporting optional branching
* Handling step-level errors
* Triggering retries where configured
* Triggering compensation if side-effecting steps must be rolled back

The workflow is internal to a skill and is not a required top-level API interface in the MVP.

### 5. Unified Tool Engine

Responsible for:

* Registering tools
* Validating tool inputs
* Executing tools through normalized provider interfaces
* Normalizing tool outputs
* Enforcing timeout rules
* Reporting tool errors

Supported provider types:

| Provider      | Description                                |
| ------------- | ------------------------------------------ |
| `local`       | Local file, Python, or local adapter tools |
| `api`         | External REST/SDK API integrations         |
| `mcp`         | Dynamically discovered MCP server tools    |
| `rag_adapter` | Read-only adapter to the RAG subsystem     |

### 6. MCP Integration Layer

Responsible for:

* Connecting to MCP providers
* Discovering available tools
* Mapping MCP tool metadata into internal tool schema
* Executing MCP tools through the tool engine

MCP is treated as a dynamic tool provider layer, not as an autonomous planner.

### 7. RAG Adapter

Responsible for:

* Exposing read-only retrieval through `rag_retrieval_tool`
* Calling the `rag_subsystem` for knowledge lookup
* Returning normalized retrieval results

The execution subsystem must not perform RAG ingestion or mutation.

### 8. Permission Engine

Responsible for:

* Checking tool permission scopes before execution
* Applying policy modes
* Preventing unauthorized side effects
* Returning structured permission errors

Permission modes:

| Mode                   | Meaning                                      |
| ---------------------- | -------------------------------------------- |
| `auto_allow`           | Execute without additional confirmation      |
| `restricted`           | Execute only under configured constraints    |
| `require_confirmation` | Pause and require confirmation from app/user |
| `blocked`              | Do not execute                               |

### 9. Execution Context

Responsible for maintaining per-execution state:

* `execution_id`
* original input
* selected skill
* execution options
* intermediate outputs
* step statuses
* tool results
* error summaries
* timing information

### 10. Result Normalizer

Responsible for converting all execution outcomes into the standard result envelope:
    {
      "status": "completed | failed | partial",
      "result_type": "text | json | file | video",
      "result": {},
      "files": [],
      "errors": [],
      "logs_summary": ""
    }

### 11. Logging and Traceability

Responsible for recording:

* execution start/end
* step start/end
* tool call summaries
* input/output summaries
* errors
* duration
* audit/debug indicators

Logs must redact secrets and credentials.

## Data Model Overview

Primary tables:

| Table              | Purpose                                                  |
| ------------------ | -------------------------------------------------------- |
| `Execution`        | Stores execution lifecycle and final result              |
| `Skill`            | Stores skill metadata and workflow definition            |
| `WorkflowStep`     | Stores per-step status and summaries                     |
| `Tool`             | Stores tool definitions and provider metadata            |
| `ToolCall`         | Stores tool invocation summaries                         |
| `PermissionPolicy` | Stores tool access policies                              |
| `McpProvider`      | Stores MCP provider configuration and discovery metadata |
| `ExecutionLog`     | Stores structured execution logs                         |

## Execution Statuses

Recommended statuses:

* `queued`
* `running`
* `completed`
* `failed`
* `partial`
* `blocked`
* `pending_confirmation`

## Failure Model

Errors must be classified as:

* `validation`
* `permission`
* `tool`
* `workflow`
* `timeout`
* `external_api`

Each error should include:
    {
      "code": "TOOL_ERROR",
      "message": "Video generation provider failed.",
      "details": {},
      "recoverable": true,
      "suggested_action": "Retry later or switch provider."
    }

## Design Principles

1. App plans; execution subsystem executes.
2. Skills are the primary execution unit.
3. Workflows are internal to skills.
4. Tools are invoked only through the unified tool engine.
5. MCP is a provider layer, not a planner.
6. RAG is read-only through adapter.
7. Unknown tools and skills are denied by default.
8. Permission checks happen before every tool call.
9. Results always use a standardized envelope.
10. All executions are traceable.

* * *
