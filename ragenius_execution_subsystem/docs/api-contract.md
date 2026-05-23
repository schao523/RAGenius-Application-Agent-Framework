 

## `api-contract.md`

    # RAGenius Execution Subsystem API Contract
    
    ## Base URL
    
    ```text
    /v1

## Response Conventions

### Standard Execution Result

    {
      "execution_id": "exec_001",
      "status": "completed",
      "result_type": "json",
      "result": {},
      "files": [],
      "errors": [],
      "logs_summary": "Execution completed."
    }

### Standard Error Object

    {
      "code": "VALIDATION_ERROR",
      "message": "Skill input does not match schema.",
      "details": {
        "path": "input.duration",
        "expected": "number",
        "received": "string"
      },
      "recoverable": true,
      "suggested_action": "Send duration as a number."
    }

## Health Routes

### GET `/healthz`

Checks whether the service process is alive.

#### Response `200`

    {
      "status": "ok"
    }

### GET `/readyz`

Checks whether dependencies are ready.

#### Response `200`

    {
      "status": "ready",
      "checks": {
        "database": "ok"
      }
    }

#### Response `503`

    {
      "status": "not_ready",
      "checks": {
        "database": "failed"
      }
    }

## Executions

### POST `/v1/executions`

Submits a structured execution request.

#### Request Body

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

#### Validation Rules

| Field                                    | Rule                                                        |
| ---------------------------------------- | ----------------------------------------------------------- |
| `request_type`                           | Required. Must be `execute_skill` in MVP.                   |
| `app_id`                                 | Required non-empty string.                                  |
| `session_id`                             | Required non-empty string.                                  |
| `skill_id`                               | Required non-empty string. Must reference an enabled skill. |
| `input`                                  | Required object. Must match selected skill input schema.    |
| `execution_options.dry_run`              | Optional boolean. Defaults to `false`.                      |
| `execution_options.require_confirmation` | Optional boolean. Defaults to `false`.                      |

#### Response `200` — Completed

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

#### Response `200` — Dry Run

    {
      "execution_id": null,
      "status": "completed",
      "result_type": "json",
      "result": {
        "dry_run": true,
        "skill_id": "video_director_skill",
        "validated": true,
        "required_tools": ["rag_retrieval_tool", "mock_video_generation_tool"],
        "side_effects_executed": false
      },
      "files": [],
      "errors": [],
      "logs_summary": "Dry run completed. No side-effecting tools were executed."
    }

#### Response `202` — Pending Confirmation

    {
      "execution_id": "exec_002",
      "status": "pending_confirmation",
      "result_type": "json",
      "result": {
        "required_confirmation": true,
        "tool_id": "mock_video_generation_tool",
        "permission_scope": "external_api.write"
      },
      "files": [],
      "errors": [],
      "logs_summary": "Execution paused because confirmation is required."
    }

#### Response `400` — Validation Error

    {
      "error": {
        "code": "VALIDATION_ERROR",
        "message": "Invalid execution request.",
        "details": {
          "path": "skill_id",
          "issue": "Required"
        },
        "recoverable": true,
        "suggested_action": "Provide a valid skill_id."
      }
    }

#### Response `404` — Skill Not Found

    {
      "error": {
        "code": "SKILL_NOT_FOUND",
        "message": "Skill was not found or is disabled.",
        "details": {
          "skill_id": "unknown_skill"
        },
        "recoverable": true,
        "suggested_action": "Use GET /v1/skills to inspect available skills."
      }
    }

#### Response `403` — Permission Blocked

    {
      "error": {
        "code": "PERMISSION_BLOCKED",
        "message": "Tool execution is blocked by policy.",
        "details": {
          "tool_id": "filesystem.delete",
          "policy": "blocked"
        },
        "recoverable": false,
        "suggested_action": "Update the permission policy or use a different skill."
      }
    }

### GET `/v1/executions/:execution_id`

Fetches execution status and result.

#### Path Parameters

| Parameter      | Description          |
| -------------- | -------------------- |
| `execution_id` | Execution identifier |

#### Response `200`

    {
      "execution_id": "exec_001",
      "app_id": "app_001",
      "session_id": "sess_001",
      "skill_id": "video_director_skill",
      "status": "completed",
      "result_type": "video",
      "result": {
        "title": "RAG Explained Simply"
      },
      "files": [],
      "errors": [],
      "logs_summary": "Skill completed in 4 steps with 2 tool calls.",
      "started_at": "2026-05-03T08:00:00.000Z",
      "completed_at": "2026-05-03T08:00:02.000Z"
    }

#### Response `404`

    {
      "error": {
        "code": "EXECUTION_NOT_FOUND",
        "message": "Execution was not found.",
        "details": {
          "execution_id": "exec_missing"
        },
        "recoverable": true,
        "suggested_action": "Check the execution_id and retry."
      }
    }

### GET `/v1/executions/:execution_id/logs`

Fetches structured execution logs.

#### Query Parameters

| Parameter | Description       | Default |
| --------- | ----------------- | ------- |
| `cursor`  | Pagination cursor | none    |
| `limit`   | Page size         | `50`    |

#### Response `200`

    {
      "items": [
        {
          "id": "log_001",
          "execution_id": "exec_001",
          "level": "info",
          "event_type": "tool.called",
          "message": "Tool call completed.",
          "summary": {
            "tool_id": "mock_video_generation_tool",
            "duration_ms": 400
          },
          "created_at": "2026-05-03T08:00:01.000Z"
        }
      ],
      "next_cursor": null
    }

## Skills

### GET `/v1/skills`

Lists registered skills.

#### Response `200`

    {
      "items": [
        {
          "id": "video_director_skill",
          "name": "Video Director Skill",
          "version": "1.0.0",
          "enabled": true,
          "required_tools": ["rag_retrieval_tool", "mock_video_generation_tool"]
        }
      ]
    }

### GET `/v1/skills/:skill_id`

Fetches skill metadata.

#### Response `200`

    {
      "id": "video_director_skill",
      "name": "Video Director Skill",
      "version": "1.0.0",
      "description": "Generates a short video explanation from a prompt.",
      "enabled": true,
      "input_schema": {
        "type": "object",
        "required": ["prompt", "duration"]
      },
      "output_schema": {
        "type": "object"
      },
      "required_tools": ["rag_retrieval_tool", "mock_video_generation_tool"],
      "required_permissions": ["rag.read", "external_api.write"]
    }

## Tools

### GET `/v1/tools`

Lists registered tools.

#### Response `200`

    {
      "items": [
        {
          "id": "rag_retrieval_tool",
          "name": "RAG Retrieval Tool",
          "provider_type": "rag_adapter",
          "permission_scopes": ["rag.read"],
          "side_effecting": false,
          "enabled": true
        },
        {
          "id": "mock_video_generation_tool",
          "name": "Mock Video Generation Tool",
          "provider_type": "api",
          "permission_scopes": ["external_api.write"],
          "side_effecting": true,
          "enabled": true
        }
      ]
    }

### POST `/v1/tools/discover/mcp`

Discovers MCP tools from a configured provider and maps them into the internal tool schema.

#### Request Body

    {
      "provider_id": "mcp_notion_001"
    }

#### Response `200`

    {
      "provider_id": "mcp_notion_001",
      "tools_discovered": [
        {
          "tool_id": "mcp.notion.create_page",
          "name": "Create Notion Page",
          "provider_type": "mcp",
          "permission_scopes": ["mcp.notion.write"],
          "side_effecting": true
        }
      ]
    }

## Error Classification

| Error Class    | Typical HTTP Status |
| -------------- | ------------------- |
| `validation`   | 400 or 422          |
| `permission`   | 403                 |
| `tool`         | 502                 |
| `workflow`     | 500                 |
| `timeout`      | 504                 |
| `external_api` | 502                 |

## Authentication

All `/v1/*` routes should require service-level authentication in production.

MVP implementations may stub authentication behind configuration, but must not expose secrets in code or logs.
    ---
