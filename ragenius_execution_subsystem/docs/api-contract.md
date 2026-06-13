# RAGenius Execution Subsystem API Contract

## Implemented Routes

### `GET /healthz`

Returns:

```json
{ "status": "ok" }
```

### `GET /readyz`

Returns:

```json
{
  "status": "ready",
  "checks": {
    "database": "not_configured"
  }
}
```

### `POST /v1/executions`

Request:

```json
{
  "request_type": "execute_skill",
  "app_id": "app_001",
  "session_id": "sess_001",
  "skill_id": "video_director_skill",
  "input": {
    "prompt": "Explain RAG simply",
    "duration": 30
  }
}
```

Responses:

- `200` completed
- `200` dry run
- `202` pending confirmation
- `400` validation error
- `403` permission blocked
- `404` unknown or disabled skill

When the execution subsystem is configured with `BUILDER_BASE_URL`, skill resolution may fall back to a builder-managed published skill that is explicitly bound to the requesting app.

### `GET /v1/skills`

Returns registered skill metadata.

### `GET /v1/skills/:skill_id`

Returns detailed metadata for a single skill.

### `GET /v1/tools`

Returns registered tool metadata.

### `POST /v1/tools/discover/mcp`

Request:

```json
{
  "provider_id": "mcp_mock_001"
}
```

Returns mock discovered tools mapped into the internal tool schema.

## Present but Not Yet Implemented

### `GET /v1/executions/:execution_id`

Returns `501`.

### `GET /v1/executions/:execution_id/logs`

Returns `501`.
