Persistence Schema Contract
===========================

##### This document describes the recommended database schema for the RAGenius Execution Subsystem. The goal is to store execution state, skill definitions, workflow steps, tool calls, permission policies, MCP providers, and logs in a relational database (e.g. PostgreSQL) in a way that supports querying, auditing, recovery and scale.

Design Principles
-----------------

* **Normalized structure:** Separate entities into distinct tables (Executions, Steps, Tool Calls, Skills, Tools, Policies, Providers, Logs). This avoids duplication and ensures referential integrity.
* **JSON fields for dynamic schemas:** Use JSON or JSONB columns for skill input/output schemas, workflow definitions and tool manifests, enabling flexible evolution without schema changes.
* **Timestamps and lifecycle:** Record creation and update timestamps for auditing and event ordering.
* **Indexes:** Create indexes on frequently queried fields (e.g. status, execution ID, skill ID, created_at) to ensure performance.
* **Foreign keys and constraints:** Enforce relationships between executions, steps and tool calls, and ensure referential integrity when deleting or updating records.

Entity Tables
-------------

### `executions`

| Column         | Type        | Constraints                       | Description                                                                                                |
| -------------- | ----------- | --------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `id`           | UUID        | Primary key                       | Execution identifier.                                                                                      |
| `app_id`       | text        | Not null                          | Application that initiated the execution.                                                                  |
| `session_id`   | text        | Not null                          | Session associated with the execution.                                                                     |
| `skill_id`     | text        | Not null                          | References `skills.id`.                                                                                    |
| `status`       | text        | Not null, check in allowed values | Current status (`queued`, `running`, `completed`, `failed`, `partial`, `blocked`, `pending_confirmation`). |
| `result_type`  | text        | Nullable                          | Type of result (`text`, `json`, `file`, `video`).                                                          |
| `result`       | jsonb       | Nullable                          | Normalized result object.                                                                                  |
| `files`        | jsonb       | Nullable                          | List of file references.                                                                                   |
| `errors`       | jsonb       | Nullable                          | List of error objects.                                                                                     |
| `logs_summary` | text        | Nullable                          | High‑level summary of execution steps.                                                                     |
| `created_at`   | timestamptz | Not null, default `now()`         | When the execution was created.                                                                            |
| `started_at`   | timestamptz | Nullable                          | When execution started.                                                                                    |
| `completed_at` | timestamptz | Nullable                          | When execution completed.                                                                                  |
| `updated_at`   | timestamptz | Not null, default `now()`         | When the record was last updated.                                                                          |

Indexes:

* `idx_executions_app_id` on (`app_id`)
* `idx_executions_session_id` on (`session_id`)
* `idx_executions_skill_id` on (`skill_id`)
* `idx_executions_status` on (`status`)
* `idx_executions_created_at` on (`created_at`)

### `workflow_steps`

| Column           | Type        | Constraints                          | Description                                                                                         |
| ---------------- | ----------- | ------------------------------------ | --------------------------------------------------------------------------------------------------- |
| `id`             | UUID        | Primary key                          | Unique step identifier.                                                                             |
| `execution_id`   | UUID        | Not null, references `executions.id` | Execution to which this step belongs.                                                               |
| `step_id`        | text        | Not null                             | Step identifier from workflow definition.                                                           |
| `step_type`      | text        | Not null                             | `validation`, `tool_call`, `local_decision`, `internal_workflow`, `service_call`, `saga`, or `end`. |
| `status`         | text        | Not null                             | `pending`, `running`, `completed`, `failed`, `skipped`.                                             |
| `input_summary`  | jsonb       | Nullable                             | Summarized input payload for the step.                                                              |
| `output_summary` | jsonb       | Nullable                             | Summarized output payload.                                                                          |
| `error`          | jsonb       | Nullable                             | Error details if the step failed.                                                                   |
| `started_at`     | timestamptz | Nullable                             | Step start time.                                                                                    |
| `completed_at`   | timestamptz | Nullable                             | Step end time.                                                                                      |
| `created_at`     | timestamptz | Not null, default `now()`            | When the record was created.                                                                        |

Index: `idx_workflow_steps_execution_id` on (`execution_id`).

### `tool_calls`

| Column           | Type        | Constraints                          | Description                                             |
| ---------------- | ----------- | ------------------------------------ | ------------------------------------------------------- |
| `id`             | UUID        | Primary key                          | Unique call identifier.                                 |
| `execution_id`   | UUID        | Not null, references `executions.id` | Execution to which this call belongs.                   |
| `step_id`        | text        | Not null                             | Step ID that invoked this tool.                         |
| `tool_id`        | text        | Not null, references `tools.id`      | Identifier of the tool.                                 |
| `provider_type`  | text        | Not null                             | Provider type of the tool.                              |
| `status`         | text        | Not null                             | `started`, `completed`, `failed`, `timeout`, `blocked`. |
| `input_summary`  | jsonb       | Not null                             | Summary of the input passed to the tool.                |
| `output_summary` | jsonb       | Nullable                             | Summary of the output returned by the tool.             |
| `error`          | jsonb       | Nullable                             | Error object if the call failed.                        |
| `duration_ms`    | integer     | Nullable                             | Execution time in milliseconds.                         |
| `created_at`     | timestamptz | Not null, default `now()`            | When the record was created.                            |

Index: `idx_tool_calls_execution_id` on (`execution_id`).

### `skills`

| Column                 | Type        | Constraints               | Description                                    |
| ---------------------- | ----------- | ------------------------- | ---------------------------------------------- |
| `id`                   | text        | Primary key               | Unique skill identifier.                       |
| `name`                 | text        | Not null                  | Human‑friendly name.                           |
| `version`              | text        | Not null                  | Semantic version.                              |
| `description`          | text        | Nullable                  | What the skill does.                           |
| `input_schema`         | jsonb       | Not null                  | JSON Schema describing the expected input.     |
| `output_schema`        | jsonb       | Not null                  | JSON Schema describing the result.             |
| `required_tools`       | jsonb       | Not null                  | List of tool identifiers.                      |
| `required_permissions` | jsonb       | Not null                  | List of required permission scopes.            |
| `workflow_definition`  | jsonb       | Not null                  | Declarative description of the workflow steps. |
| `enabled`              | boolean     | Not null, default `true`  | Whether the skill is active.                   |
| `created_at`           | timestamptz | Not null, default `now()` | Creation time.                                 |
| `updated_at`           | timestamptz | Not null, default `now()` | Last update time.                              |

Index: `idx_skills_name_version` on (`name`, `version`).

### `tools`

| Column              | Type        | Constraints               | Description                               |
| ------------------- | ----------- | ------------------------- | ----------------------------------------- |
| `id`                | text        | Primary key               | Unique tool identifier.                   |
| `name`              | text        | Not null                  | Human‑friendly name.                      |
| `provider_type`     | text        | Not null                  | `local`, `api`, `mcp`, `rag_adapter`.     |
| `input_schema`      | jsonb       | Not null                  | JSON Schema of expected inputs.           |
| `output_schema`     | jsonb       | Not null                  | JSON Schema of outputs.                   |
| `permission_scopes` | jsonb       | Not null                  | List of scopes required to call the tool. |
| `timeout_ms`        | integer     | Nullable                  | Timeout in milliseconds.                  |
| `side_effecting`    | boolean     | Not null                  | Whether the tool has side effects.        |
| `metadata`          | jsonb       | Nullable                  | Provider‑specific metadata.               |
| `enabled`           | boolean     | Not null, default `true`  | Whether the tool can be called.           |
| `created_at`        | timestamptz | Not null, default `now()` | Creation time.                            |
| `updated_at`        | timestamptz | Not null, default `now()` | Last update time.                         |

### `permission_policies`

| Column       | Type        | Constraints               | Description                                                    |
| ------------ | ----------- | ------------------------- | -------------------------------------------------------------- |
| `id`         | UUID        | Primary key               | Policy identifier.                                             |
| `app_id`     | text        | Not null                  | Application to which this policy applies.                      |
| `tool_id`    | text        | Not null                  | Identifier of the tool.                                        |
| `scope`      | text        | Not null                  | Permission scope.                                              |
| `policy`     | text        | Not null                  | `auto_allow`, `restricted`, `require_confirmation`, `blocked`. |
| `conditions` | jsonb       | Nullable                  | Additional constraints (see examples in auth document).        |
| `created_at` | timestamptz | Not null, default `now()` | Creation time.                                                 |
| `updated_at` | timestamptz | Not null, default `now()` | Last update time.                                              |

Unique index: `(app_id, tool_id, scope)` to avoid duplicate policy entries.

### `mcp_providers`

| Column               | Type        | Constraints               | Description                                                        |
| -------------------- | ----------- | ------------------------- | ------------------------------------------------------------------ |
| `id`                 | UUID        | Primary key               | Provider identifier.                                               |
| `name`               | text        | Not null                  | Name of the MCP provider (e.g. `Notion`, `Asana`).                 |
| `server_url`         | text        | Not null                  | Base URL of the MCP server.                                        |
| `auth_type`          | text        | Not null                  | `none`, `bearer`, `oauth2`, `mcp_session`.                         |
| `auth_config`        | jsonb       | Nullable                  | Configuration needed for authentication (client ID, scopes, etc.). |
| `discovered_tools`   | jsonb       | Nullable                  | Cached list of discovered tools.                                   |
| `last_discovered_at` | timestamptz | Nullable                  | Last time discovery ran.                                           |
| `enabled`            | boolean     | Not null, default `true`  | Whether this provider is active.                                   |
| `created_at`         | timestamptz | Not null, default `now()` | Creation time.                                                     |
| `updated_at`         | timestamptz | Not null, default `now()` | Last update time.                                                  |

### `execution_logs`

| Column         | Type        | Constraints                          | Description                                                    |
| -------------- | ----------- | ------------------------------------ | -------------------------------------------------------------- |
| `id`           | UUID        | Primary key                          | Log record identifier.                                         |
| `execution_id` | UUID        | Not null, references `executions.id` | Execution to which this log belongs.                           |
| `level`        | text        | Not null                             | `debug`, `info`, `warn`, `error`, `audit`.                     |
| `event_type`   | text        | Not null                             | Nature of the event (e.g. `tool.called`, `execution.started`). |
| `message`      | text        | Not null                             | Human‑readable description.                                    |
| `summary`      | jsonb       | Nullable                             | Structured summary of event (e.g. tool ID, duration).          |
| `created_at`   | timestamptz | Not null, default `now()`            | When the log was created.                                      |

Index: `idx_execution_logs_execution_id` on (`execution_id`).
Schema Evolution
----------------

* Use migrations (e.g. via Prisma, Flyway or Liquibase) to evolve the schema.
* For backwards‑compatible changes (adding columns, adding nullable fields), create new columns with defaults.
* For breaking changes (renaming columns, changing types), plan a migration strategy that copies data to new tables and cleans up old structures.
* Consider using [event sourcing](https://martinfowler.com/eaaDev/EventSourcing.html) for extremely dynamic workflows, but for most cases the relational model suffices.

Data Retention and Privacy
--------------------------

* Define retention periods for executions, logs and tool call summaries based on regulatory requirements and operational needs (e.g. 90 days, 1 year).
* Support purging of old logs or anonymizing sensitive data.
* Avoid storing full tool inputs or outputs when they may contain user secrets or large payloads. Store only summaries and file references.
