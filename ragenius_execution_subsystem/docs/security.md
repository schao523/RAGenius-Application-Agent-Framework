    
    
    ## security.md
    
    ```markdown
    # RAGenius Execution Subsystem Security Guide
    
    ## Security Goal
    
    The execution subsystem must safely execute structured skill requests while preventing unauthorized tool use, unsafe side effects, secret leakage, and untraceable execution.
    
    ## Non-Negotiable Rules
    
    - Reject unknown request types.
    - Reject unknown or disabled skills.
    - Reject unknown tools.
    - Validate every request before execution.
    - Validate every skill input before workflow execution.
    - Validate every tool input before tool execution.
    - Run permission checks before every tool call.
    - Treat MCP tools as external provider tools.
    - Treat RAG as read-only.
    - Redact secrets from logs.
    - Never commit real credentials.
    - Do not store raw secrets in the database.
    
    ## Permission Model
    
    The subsystem supports four permission modes.
    
    | Mode | Meaning | Behavior |
    |---|---|---|
    | `auto_allow` | Low-risk operation | Execute after validation |
    | `restricted` | Allowed only under constraints | Check configured conditions before execution |
    | `require_confirmation` | Needs user/app confirmation | Pause and return pending confirmation result |
    | `blocked` | Not allowed | Stop execution and return permission error |
    
    ## Permission Check Timing
    
    Permission checks must happen immediately before every tool call.
    
    ```text
    workflow step
    → resolve tool
    → validate tool input
    → check permission
    → execute tool only if allowed

Do not rely only on skill-level permission checks. A skill-level check can be used as an early preview, but tool-level enforcement is mandatory.

## High-Risk Tool Classes

| Tool Class            | Minimum Recommended Policy                   |
| --------------------- | -------------------------------------------- |
| File write/delete     | `restricted` or `require_confirmation`       |
| Code execution        | `restricted` or `require_confirmation`       |
| Network access        | `restricted`                                 |
| External API mutation | `restricted` or `require_confirmation`       |
| MCP mutation tools    | `restricted` or `require_confirmation`       |
| RAG retrieval         | `auto_allow` or `restricted`, read-only only |

## RAG Security Boundary

RAG access is allowed only through:
    rag_retrieval_tool → rag_subsystem

The execution subsystem must not:

* ingest documents into RAG
* mutate RAG indexes
* delete RAG data
* change retrieval policies
* treat RAG retrieval as planning authority

RAG is a read-only knowledge provider.

## MCP Security Boundary

MCP providers are dynamic tool providers.

For every discovered MCP tool:

* Map it into the internal tool schema.
* Assign permission scopes.
* Mark whether it is side-effecting.
* Validate inputs before execution.
* Apply timeout policy.
* Redact outputs before logging.

Unknown MCP tools must not execute by default.

## Dry Run Safety

When `dry_run=true`, the subsystem may perform:

* request validation
* skill lookup
* skill input validation
* tool resolution
* permission checks
* execution preview generation

The subsystem must not perform:

* file writes
* file deletes
* external API mutations
* MCP mutation calls
* code execution with side effects
* real video/document generation calls

Dry run responses should explicitly state that no side effects were executed.

## Secret Handling

Secrets must be loaded only through environment variables or a dedicated secret manager.

Never commit:

* API keys
* bearer tokens
* OAuth client secrets
* database passwords
* private keys
* cookies
* session tokens

`.env.example` may contain variable names but must not contain real secret values.

Example:
    DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public"
    MCP_TOKEN="replace_me"
    VIDEO_API_KEY="replace_me"

## Log Redaction

Logs must redact:

* `authorization`
* `cookie`
* `set-cookie`
* `api_key`
* `apikey`
* `access_token`
* `refresh_token`
* `password`
* `secret`
* `private_key`
* bearer tokens

Recommended redacted form:
    {
      "authorization": "[REDACTED]",
      "api_key": "[REDACTED]"
    }

## Safe Logging Defaults

Log summaries by default, not full payloads.

Allowed by default:

* execution ID
* skill ID
* tool ID
* provider type
* duration
* status
* error code
* sanitized input/output summary

Avoid by default:

* full request body
* full tool response
* raw document contents
* user secrets
* credentials
* authorization headers

## Error Safety

Returned errors should be helpful but should not leak internals.

Each error should include:
    {
      "code": "PERMISSION_BLOCKED",
      "message": "Tool execution is blocked by policy.",
      "details": {
        "tool_id": "filesystem.delete",
        "policy": "blocked"
      },
      "recoverable": false,
      "suggested_action": "Update the permission policy or use a different skill."
    }

Do not expose:

* stack traces in production API responses
* raw provider credentials
* internal network addresses unless required for operators
* full external API payloads containing sensitive data

## External API Safety

External API tools must define:

* provider name
* endpoint or operation name
* input schema
* output schema
* timeout
* retry policy
* side-effect flag
* permission scope
* redaction behavior

Mutation APIs should be treated as side-effecting.

## Code Execution Safety

If code execution tools are added:

* Require `restricted` or `require_confirmation` policy.
* Run in sandboxed environment.
* Set CPU, memory, and timeout limits.
* Disable unrestricted network access unless explicitly allowed.
* Do not mount sensitive host paths.
* Log summaries only.

## File System Safety

File tools must distinguish between:

* read
* write
* delete
* move
* list

Write/delete operations must be restricted or require confirmation.

Use allowlisted paths where possible.

## Audit Requirements

Audit logs should include:

* execution ID
* app ID
* session ID
* skill ID
* step ID
* tool ID
* permission decision
* provider type
* status
* error code
* duration
* redaction applied flag

Audit logs should not contain raw secrets.

## Recommended Security Tests

At minimum, test that:

1. Unknown skills are rejected.
2. Unknown tools are rejected.
3. Blocked tools do not execute.
4. `require_confirmation` tools pause execution.
5. Dry run does not execute side-effecting tools.
6. RAG adapter does not mutate data.
7. MCP discovered tools require registration and permissions.
8. Secrets are redacted from logs.
9. Tool input validation runs before execution.
10. Production errors do not expose stack traces.

* * *
