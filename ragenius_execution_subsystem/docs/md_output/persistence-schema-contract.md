Persistence Schema Contract
This document describes the recommended database schema for the RAGenius Execution Subsystem. The
goal is to store execution state, skill definitions, workflow steps, tool calls, permission policies, MCP
providers, and logs in a relational database (e.g. PostgreSQL) in a way that supports querying, auditing,
recovery and scale.
Design Principles
ò Normalized structure: Separate entities into distinct tables (Executions, Steps, Tool Calls, Skills,
Tools, Policies, Providers, Logs). This avoids duplication and ensures referential integrity.
ò JSON fields for dynamic schemas: Use JSON or JSONB columns for skill input/output schemas,
workflow definitions and tool manifests, enabling flexible evolution without schema changes.
ò Timestamps and lifecycle: Record creation and update timestamps for auditing and event ordering.
ò Indexes: Create indexes on frequently queried fields (e.g. status, execution ID, skill ID, created_at) to
ensure performance.
ò Foreign keys and constraints: Enforce relationships between executions, steps and tool calls, and
ensure referential integrity when deleting or updating records.
Entity Tables
executions
| Column | Type | Constraints | Description           |     |     |     |
| ------ | ---- | ----------- | --------------------- | --- | --- | --- |
| id     | UUID | Primary key | Execution identifier. |     |     |     |
app_id text Not null Application that initiated the execution.
session_id text Not null Session associated with the execution.
| skill_id    | text | Not null        | References       | skills.id               | .               |     |
| ----------- | ---- | --------------- | ---------------- | ----------------------- | --------------- | --- |
|             |      | Not null, check | Current status ( | queued                  | ,  running      | ,   |
| status      | text | in allowed      | completed        | ,  failed               | ,  partial      | ,   |
|             |      | values          | blocked          | ,  pending_confirmation |                 | ).  |
|             |      |                 | Type of result ( | text                    | ,  json ,  file | ,   |
| result_type | text | Nullable        |                  |                         |                 |     |
video ).
| result | jsonb | Nullable | Normalized result object. |     |     |     |
| ------ | ----- | -------- | ------------------------- | --- | --- | --- |
| files  | jsonb | Nullable | List of file references.  |     |     |     |
| errors | jsonb | Nullable | List of error objects.    |     |     |     |
1

| Column | Type | Constraints |     | Description |     |     |     |     |
| ------ | ---- | ----------- | --- | ----------- | --- | --- | --- | --- |
logs_summary text Nullable High?level summary of execution steps.
Not null,
| created_at | timestamptz |     |     | When the execution was created. |     |     |     |     |
| ---------- | ----------- | --- | --- | ------------------------------- | --- | --- | --- | --- |
now()
default
| started_at   | timestamptz | Nullable |     | When execution started.   |     |     |     |     |
| ------------ | ----------- | -------- | --- | ------------------------- | --- | --- | --- | --- |
| completed_at | timestamptz | Nullable |     | When execution completed. |     |     |     |     |
Not null,
| updated_at | timestamptz |     |     | When the record was last updated. |     |     |     |     |
| ---------- | ----------- | --- | --- | --------------------------------- | --- | --- | --- | --- |
now()
default
Indexes:
| ò  idx_executions_app_id     |     |  on ( app_id   | )          |     |     |     |     |     |
| ---------------------------- | --- | -------------- | ---------- | --- | --- | --- | --- | --- |
| idx_executions_session_id    |     |                | session_id |     |     |     |     |     |
| ò                            |     |  on (          |            | )   |     |     |     |     |
| ò  idx_executions_skill_id   |     |  on ( skill_id |            | )   |     |     |     |     |
| ò  idx_executions_status     |     |  on ( status   | )          |     |     |     |     |     |
| ò  idx_executions_created_at |     |  on (          | created_at | )   |     |     |     |     |
workflow_steps
| Column | Type | Constraints |     |     | Description             |     |     |     |
| ------ | ---- | ----------- | --- | --- | ----------------------- | --- | --- | --- |
| id     | UUID | Primary key |     |     | Unique step identifier. |     |     |     |
Not null, references
| execution_id | UUID |     |     |     | Execution to which this step belongs. |     |     |     |
| ------------ | ---- | --- | --- | --- | ------------------------------------- | --- | --- | --- |
executions.id
Step identifier from workflow
| step_id | text | Not null |     |     |     |     |     |     |
| ------- | ---- | -------- | --- | --- | --- | --- | --- | --- |
definition.
|           |      |          |     |     | validation     | ,  tool_call | ,   |     |
| --------- | ---- | -------- | --- | --- | -------------- | ------------ | --- | --- |
|           |      |          |     |     | local_decision | ,            |     |     |
| step_type | text | Not null |     |     |                |              |     |     |
internal_workflow
,
|        |      |          |     |     | service_call | ,  saga    | , or  end    | .   |
| ------ | ---- | -------- | --- | --- | ------------ | ---------- | ------------ | --- |
|        |      |          |     |     | pending      | ,  running | ,  completed | ,   |
| status | text | Not null |     |     |              |            |              |     |
|        |      |          |     |     | failed       | skipped    |              |     |
|        |      |          |     |     |              | ,          | .            |     |
Summarized input payload for the
| input_summary | jsonb | Nullable |     |     |     |     |     |     |
| ------------- | ----- | -------- | --- | --- | --- | --- | --- | --- |
step.
| output_summary | jsonb | Nullable |     |     | Summarized output payload. |     |     |     |
| -------------- | ----- | -------- | --- | --- | -------------------------- | --- | --- | --- |
error
|              | jsonb       | Nullable |     |     | Error details if the step failed. |     |     |     |
| ------------ | ----------- | -------- | --- | --- | --------------------------------- | --- | --- | --- |
| started_at   | timestamptz | Nullable |     |     | Step start time.                  |     |     |     |
| completed_at | timestamptz | Nullable |     |     | Step end time.                    |     |     |     |
2

| Column | Type | Constraints | Description |     |     |
| ------ | ---- | ----------- | ----------- | --- | --- |
Not null, default
| created_at | timestamptz |     | When the record was created. |     |     |
| ---------- | ----------- | --- | ---------------------------- | --- | --- |
now()
| Index:  idx_workflow_steps_execution_id |     |  on ( execution_id | ).  |     |     |
| --------------------------------------- | --- | ------------------ | --- | --- | --- |
tool_calls
| Column       | Type | Constraints           | Description                  |     |     |
| ------------ | ---- | --------------------- | ---------------------------- | --- | --- |
| id           | UUID | Primary key           | Unique call identifier.      |     |     |
|              |      | Not null, references  | Execution to which this call |     |     |
| execution_id | UUID |                       |                              |     |     |
|              |      | executions.id         | belongs.                     |     |     |
step_id
|     | text | Not null | Step ID that invoked this tool. |     |     |
| --- | ---- | -------- | ------------------------------- | --- | --- |
Not null, references
| tool_id | text |     | Identifier of the tool. |     |     |
| ------- | ---- | --- | ----------------------- | --- | --- |
tools.id
| provider_type | text | Not null | Provider type of the tool. |     |     |
| ------------- | ---- | -------- | -------------------------- | --- | --- |
|               |      |          | started completed          |     |     |
,  ,
| status | text | Not null |                   |            |     |
| ------ | ---- | -------- | ----------------- | ---------- | --- |
|        |      |          | failed ,  timeout | ,  blocked | .   |
Summary of the input passed to
| input_summary | jsonb | Not null |     |     |     |
| ------------- | ----- | -------- | --- | --- | --- |
the tool.
Summary of the output returned
| output_summary | jsonb | Nullable |     |     |     |
| -------------- | ----- | -------- | --- | --- | --- |
by the tool.
| error       | jsonb   | Nullable | Error object if the call failed. |     |     |
| ----------- | ------- | -------- | -------------------------------- | --- | --- |
| duration_ms | integer | Nullable | Execution time in milliseconds.  |     |     |
created_at timestamptz Not null, default  now() When the record was created.
| Index:  idx_tool_calls_execution_id |     |  on ( execution_id | ).  |     |     |
| ----------------------------------- | --- | ------------------ | --- | --- | --- |
skills
| Column | Type | Constraints | Description              |     |     |
| ------ | ---- | ----------- | ------------------------ | --- | --- |
| id     | text | Primary key | Unique skill identifier. |     |     |
| name   | text | Not null    | Human?friendly name.     |     |     |
version
|             | text | Not null | Semantic version.    |     |     |
| ----------- | ---- | -------- | -------------------- | --- | --- |
| description | text | Nullable | What the skill does. |     |     |
3

| Column | Type | Constraints |     | Description |
| ------ | ---- | ----------- | --- | ----------- |
JSON Schema describing the
| input_schema | jsonb | Not null |     |     |
| ------------ | ----- | -------- | --- | --- |
expected input.
JSON Schema describing the
| output_schema | jsonb | Not null |     |     |
| ------------- | ----- | -------- | --- | --- |
result.
required_tools
|     | jsonb | Not null |     | List of tool identifiers. |
| --- | ----- | -------- | --- | ------------------------- |
List of required permission
| required_permissions | jsonb | Not null |     |     |
| -------------------- | ----- | -------- | --- | --- |
scopes.
Declarative description of the
| workflow_definition | jsonb | Not null |     |     |
| ------------------- | ----- | -------- | --- | --- |
workflow steps.
Not null, default
| enabled | boolean |     |     | Whether the skill is active. |
| ------- | ------- | --- | --- | ---------------------------- |
true
Not null, default
created_at
|     | timestamptz |     |     | Creation time. |
| --- | ----------- | --- | --- | -------------- |
now()
Not null, default
| updated_at | timestamptz |     |     | Last update time. |
| ---------- | ----------- | --- | --- | ----------------- |
now()
| idx_skills_name_version |       | name version |     |     |
| ----------------------- | ----- | ------------ | --- | --- |
| Index:                  |  on ( | ,            | ).  |     |
tools
| Column | Type | Constraints |     | Description             |
| ------ | ---- | ----------- | --- | ----------------------- |
| id     | text | Primary key |     | Unique tool identifier. |
| name   | text | Not null    |     | Human?friendly name.    |
local ,  api ,  mcp ,
| provider_type | text | Not null |     |     |
| ------------- | ---- | -------- | --- | --- |
rag_adapter
.
| input_schema  | jsonb | Not null |     | JSON Schema of expected inputs. |
| ------------- | ----- | -------- | --- | ------------------------------- |
| output_schema | jsonb | Not null |     | JSON Schema of outputs.         |
List of scopes required to call the
| permission_scopes | jsonb | Not null |     |     |
| ----------------- | ----- | -------- | --- | --- |
tool.
| timeout_ms | integer | Nullable |     | Timeout in milliseconds. |
| ---------- | ------- | -------- | --- | ------------------------ |
side_effecting boolean Not null Whether the tool has side effects.
| metadata | jsonb | Nullable |     | Provider?specific metadata. |
| -------- | ----- | -------- | --- | --------------------------- |
Not null, default
enabled
|     | boolean |     |     | Whether the tool can be called. |
| --- | ------- | --- | --- | ------------------------------- |
true
4

| Column |     | Type | Constraints |     | Description |     |     |
| ------ | --- | ---- | ----------- | --- | ----------- | --- | --- |
Not null, default
| created_at |     | timestamptz |     |     | Creation time. |     |     |
| ---------- | --- | ----------- | --- | --- | -------------- | --- | --- |
now()
Not null, default
| updated_at |     | timestamptz |     |     | Last update time. |     |     |
| ---------- | --- | ----------- | --- | --- | ----------------- | --- | --- |
now()
permission_policies
| Column | Type | Constraints |     | Description        |     |     |     |
| ------ | ---- | ----------- | --- | ------------------ | --- | --- | --- |
| id     | UUID | Primary key |     | Policy identifier. |     |     |     |
app_id text Not null Application to which this policy applies.
tool_id
|        | text | Not null |     | Identifier of the tool. |               |            |     |
| ------ | ---- | -------- | --- | ----------------------- | ------------- | ---------- | --- |
| scope  | text | Not null |     | Permission scope.       |               |            |     |
|        |      |          |     | auto_allow              | ,  restricted | ,          |     |
| policy | text | Not null |     |                         |               |            |     |
|        |      |          |     | require_confirmation    |               | ,  blocked | .   |
Additional constraints (see examples in auth
| conditions | jsonb | Nullable |     |     |     |     |     |
| ---------- | ----- | -------- | --- | --- | --- | --- | --- |
document).
Not null, default
| created_at | timestamptz |     |     | Creation time. |     |     |     |
| ---------- | ----------- | --- | --- | -------------- | --- | --- | --- |
now()
Not null, default
| updated_at | timestamptz |     |     | Last update time. |     |     |     |
| ---------- | ----------- | --- | --- | ----------------- | --- | --- | --- |
now()
| Unique index:  | (app_id, tool_id, scope) |     |  to avoid duplicate policy entries. |     |     |     |     |
| -------------- | ------------------------ | --- | ----------------------------------- | --- | --- | --- | --- |
mcp_providers
| Column |     | Type | Constraints |     | Description          |     |     |
| ------ | --- | ---- | ----------- | --- | -------------------- | --- | --- |
| id     |     | UUID | Primary key |     | Provider identifier. |     |     |
Name of the MCP provider (e.g.
| name       |     | text | Not null |     |                             |           |     |
| ---------- | --- | ---- | -------- | --- | --------------------------- | --------- | --- |
|            |     |      |          |     | Notion Asana                |           |     |
|            |     |      |          |     | ,                           | ).        |     |
| server_url |     | text | Not null |     | Base URL of the MCP server. |           |     |
|            |     |      |          |     | none ,  bearer              | ,  oauth2 | ,   |
| auth_type  |     | text | Not null |     |                             |           |     |
|            |     |      |          |     | mcp_session                 | .         |     |
Configuration needed for
| auth_config |     | jsonb | Nullable |     |     |     |     |
| ----------- | --- | ----- | -------- | --- | --- | --- | --- |
authentication (client ID, scopes, etc.).
discovered_tools jsonb Nullable Cached list of discovered tools.
5

| Column | Type | Constraints | Description |     |     |
| ------ | ---- | ----------- | ----------- | --- | --- |
last_discovered_at timestamptz Nullable Last time discovery ran.
Not null, default
| enabled | boolean |     | Whether this provider is active. |     |     |
| ------- | ------- | --- | -------------------------------- | --- | --- |
true
Not null, default
| created_at | timestamptz |     | Creation time. |     |     |
| ---------- | ----------- | --- | -------------- | --- | --- |
now()
Not null, default
updated_at
|     | timestamptz |     | Last update time. |     |     |
| --- | ----------- | --- | ----------------- | --- | --- |
now()
execution_logs
| Column | Type | Constraints | Description            |     |     |
| ------ | ---- | ----------- | ---------------------- | --- | --- |
| id     | UUID | Primary key | Log record identifier. |     |     |
Not null, references
| execution_id | UUID |     | Execution to which this log belongs. |     |     |
| ------------ | ---- | --- | ------------------------------------ | --- | --- |
executions.id
|       |      |          | debug ,  info | ,  warn ,  error | ,   |
| ----- | ---- | -------- | ------------- | ---------------- | --- |
| level | text | Not null |               |                  |     |
audit
.
Nature of the event (e.g.
| event_type | text | Not null | tool.called                 | ,   |     |
| ---------- | ---- | -------- | --------------------------- | --- | --- |
|            |      |          | execution.started           | ).  |     |
| message    | text | Not null | Human?readable description. |     |     |
Structured summary of event (e.g. tool
| summary | jsonb | Nullable |     |     |     |
| ------- | ----- | -------- | --- | --- | --- |
ID, duration).
created_at timestamptz Not null, default  now() When the log was created.
| Index:  idx_execution_logs_execution_id |     |  on ( execution_id | ).  |     |     |
| --------------------------------------- | --- | ------------------ | --- | --- | --- |
Schema Evolution
ò Use migrations (e.g. via Prisma, Flyway or Liquibase) to evolve the schema.
ò For backwards?compatible changes (adding columns, adding nullable fields), create new columns
with defaults.
ò For breaking changes (renaming columns, changing types), plan a migration strategy that copies
data to new tables and cleans up old structures.
ò Consider using event sourcing for extremely dynamic workflows, but for most cases the relational
model suffices.
6

Data Retention and Privacy
ò Define retention periods for executions, logs and tool call summaries based on regulatory
requirements and operational needs (e.g. 90 days, 1 year).
ò Support purging of old logs or anonymizing sensitive data.
ò Avoid storing full tool inputs or outputs when they may contain user secrets or large payloads. Store
only summaries and file references.
7
