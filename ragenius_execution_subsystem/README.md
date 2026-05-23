*  

## `README.md`

    # RAGenius Execution Subsystem
    
    `ragenius_execution_subsystem` is the controlled execution backend of the RAGenius system.
    
    It receives structured execution requests from `ragenius_app`, validates them, loads skills, executes internal skill workflows, orchestrates local/API/MCP/RAG-adapter tools, enforces permissions, records trace logs, and returns standardized execution results.
    
    ## What This Subsystem Does
    
    - Accepts validated structured execution requests
    - Executes registered skills
    - Runs skill-internal workflows step by step
    - Coordinates tool calls through a unified tool engine
    - Supports local, API, MCP, and RAG-adapter tools
    - Enforces permission and safety policies before tool execution
    - Tracks execution context, steps, tool calls, and logs
    - Normalizes all outputs into a consistent response envelope
    - Classifies and reports validation, permission, tool, workflow, timeout, and external API errors
    
    ## What This Subsystem Does Not Do
    
    - It does not perform LLM-first reasoning or planning.
    - It does not generate final conversational answers.
    - It does not manage application-level instructions.
    - It does not own the end-user UI.
    - It does not perform RAG ingestion.
    - It does not expose or store raw secrets.
    
    ## System Boundary
    
    ```text
    ragenius_app
      = reasoning, planning, user-facing answer generation
    
    ragenius_execution_subsystem
      = controlled skill execution through tools
    
    rag_subsystem
      = ingestion and retrieval only
    
    ragenius_builder
      = app configuration

## Architecture Overview

The subsystem is organized around four core concepts:

| Concept           | Description                             |
| ----------------- | --------------------------------------- |
| Skill             | Primary reusable execution unit         |
| Workflow          | Internal step sequence inside a skill   |
| Tool              | Low-level execution mechanism           |
| Execution Context | Per-execution state and trace container |

Primary execution flow:
    Structured Execution Request
    → request validation
    → skill loading
    → skill input validation
    → tool resolution
    → permission checks
    → execution context creation
    → internal workflow execution
    → tool orchestration
    → result normalization
    → trace logging
    → standardized response

## Example Request

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

## Example Response

    {
      "execution_id": "exec_001",
      "status": "completed",
      "result_type": "video",
      "result": {
        "title": "RAG Explained Simply",
        "summary": "Generated 30-second explainer video."
      },
      "files": [
        {
          "file_id": "file_001",
          "kind": "video",
          "mime_type": "video/mp4"
        }
      ],
      "errors": [],
      "logs_summary": "Skill completed in 4 steps with 2 tool calls."
    }

## Local Setup

### Prerequisites

* Node.js 20+
* npm
* Docker Desktop or Docker Engine
* PostgreSQL, either local or through Docker Compose

### Install Dependencies

    npm install

### Configure Environment

Copy the example environment file:
    cp .env.example .env

Required variables:
    DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public"
    NODE_ENV="development"
    PORT="3000"
    LOG_LEVEL="info"

Secrets must be provided through environment variables only. Do not commit real credentials.

### Start PostgreSQL

    docker compose up -d

### Run Migrations

    npx prisma migrate dev

### Start Development Server

    npm run dev

### Run Checks

    npm run lint
    npm run typecheck
    npm test

## API Routes

| Method | Route                               | Purpose                                     |
| ------ | ----------------------------------- | ------------------------------------------- |
| GET    | `/healthz`                          | Health check                                |
| GET    | `/readyz`                           | Readiness check                             |
| POST   | `/v1/executions`                    | Submit structured execution request         |
| GET    | `/v1/executions/:execution_id`      | Fetch execution result/status               |
| GET    | `/v1/executions/:execution_id/logs` | Fetch execution logs                        |
| GET    | `/v1/skills`                        | List registered skills                      |
| GET    | `/v1/skills/:skill_id`              | Fetch skill metadata                        |
| GET    | `/v1/tools`                         | List registered tools                       |
| POST   | `/v1/tools/discover/mcp`            | Discover MCP tools from configured provider |

## Standard Result Envelope

All terminal execution responses should follow this shape:
    {
      "status": "completed | failed | partial",
      "result_type": "text | json | file | video",
      "result": {},
      "files": [],
      "errors": [],
      "logs_summary": ""
    }

## Dry Run Behavior

When `execution_options.dry_run=true`, the subsystem validates the request, skill, input schema, tool availability, and permissions without executing side-effecting tools.

## Security Rules

* Unknown request types are rejected.
* Unknown or disabled skills are rejected.
* Unknown tools are rejected.
* Permission checks run before every tool call.
* RAG is read-only through `rag_retrieval_tool`.
* Secrets are redacted from logs.
* Credentials must be represented as environment variable names, never actual values.

## Documentation

See:

* `docs/architecture.md`
* `docs/api-contract.md`
* `docs/security.md`
* `docs/workflow-execution-map.yaml`

## Development Notes

Before completing changes, run:
    npm run lint
    npm run typecheck
    npm test

If any command cannot run, document why and what remains unverified.
    ---
