Unified Tool Provider Contract
The RAGenius Execution Subsystem invokes tools through a unified interface called the Tool Engine. Tools
encapsulate the low?level work required to fulfil a step in a skill workflowùsuch as reading a file, calling an
external API, running a script, or retrieving data from RAG. This document specifies the contract for defining
and executing tools so that developers can add new tools without modifying the core engine.
Provider Types
A tool belongs to exactly one provider type, which determines how it is invoked:
| Provider Type | Description |     | Typical Examples |     |     |
| ------------- | ----------- | --- | ---------------- | --- | --- |
Runs locally within the execution
environment. Useful for file operations,
| local |     |     | file.read | ,  python.execute |     |
| ----- | --- | --- | --------- | ----------------- | --- |
simple computations, or sandboxed Python
execution.
Invokes an external REST or SDK API over
|     |     |     | sendgrid.send_email |     | ,   |
| --- | --- | --- | ------------------- | --- | --- |
api
the network. Often requires credentials or
stripe.create_charge
API keys.
Discovered from a Multi?Call Provider (MCP).
|     | MCPs expose their own set of tools. The |     | mcp.notion.create_page |     | ,   |
| --- | --------------------------------------- | --- | ---------------------- | --- | --- |
mcp
|     | engine must map these tools into the |     | mcp.asana.create_task |     |     |
| --- | ------------------------------------ | --- | --------------------- | --- | --- |
internal schema before use.
Wrapper around the RAG subsystem. Only
rag_adapter supports read?only retrieval; ingestion or rag_retrieval_tool
mutation is forbidden.
Tool Definition
Each tool must provide a manifest with these properties:
| Field | Type   | Description                           |     |     |     |
| ----- | ------ | ------------------------------------- | --- | --- | --- |
|       | string | Unique identifier for the tool (e.g.  |     |     |     |
id
|      | (unique) | mock_video_generation_tool |     | ).  |     |
| ---- | -------- | -------------------------- | --- | --- | --- |
| name | string   | Human?friendly name.       |     |     |     |
providerType string One of  local ,  api ,  mcp , or  rag_adapter .
1

| Field |     | Type |     | Description |     |     |
| ----- | --- | ---- | --- | ----------- | --- | --- |
JSON
Schema describing the expected input. The tool engine must
| inputSchema |     | Schema |     |     |     |     |
| ----------- | --- | ------ | --- | --- | --- | --- |
validate inputs against this before execution.
object
JSON
outputSchema Schema Schema describing the output. Used for result normalization.
object
|     |     | array of |     | Permission scopes required to call this tool (e.g.  |     |     |
| --- | --- | -------- | --- | --------------------------------------------------- | --- | --- |
permissionScopes
|     |     | strings |     | filesystem.write                                              | ,  external_api.write | ).  |
| --- | --- | ------- | --- | ------------------------------------------------------------- | --------------------- | --- |
|     |     | integer |     | Maximum time to wait for the tool to complete. Default should |                       |     |
timeoutMs
|     |     | (optional) |     | be reasonable (e.g. 30s). |     |     |
| --- | --- | ---------- | --- | ------------------------- | --- | --- |
Whether calling this tool can create external side effects (file
sideEffecting boolean writes, network mutations, etc.). Side?effecting tools must be
restricted or require confirmation.
|     |     | object |     | Free?form metadata about the tool (e.g. provider endpoint, |     |     |
| --- | --- | ------ | --- | ---------------------------------------------------------- | --- | --- |
metadata
|     |     | (optional) |     | description, version). |     |     |
| --- | --- | ---------- | --- | ---------------------- | --- | --- |
Example Tool Manifest (JSON)
{
| "id":           | "mock_video_generation_tool", |            |              |     |     |     |
| --------------- | ----------------------------- | ---------- | ------------ | --- | --- | --- |
| "name":         | "Mock Video Generation Tool", |            |              |     |     |     |
| "providerType": |                               | "api",     |              |     |     |     |
| "inputSchema":  |                               | {          |              |     |     |     |
|                 | "type": "object",             |            |              |     |     |     |
|                 | "required":                   | ["prompt", | "duration"], |     |     |     |
|                 | "properties":                 | {          |              |     |     |     |
|                 | "prompt":                     | { "type":  | "string"     | },  |     |     |
"duration": { "type": "number", "minimum": 1, "maximum": 300 },
|     | "context": | { "type": | "string" | }   |     |     |
| --- | ---------- | --------- | -------- | --- | --- | --- |
}
},
| "outputSchema": |                   | {         |            |             |     |     |
| --------------- | ----------------- | --------- | ---------- | ----------- | --- | --- |
|                 | "type": "object", |           |            |             |     |     |
|                 | "required":       | ["title", | "summary", | "file_id"], |     |     |
|                 | "properties":     | {         |            |             |     |     |
|                 | "title":          | { "type": | "string"   | },          |     |     |
|                 | "summary":        | { "type": | "string"   | },          |     |     |
|                 | "file_id":        | { "type": | "string"   | }           |     |     |
}
},
| "permissionScopes": |     | ["external_api.write"], |     |     |     |     |
| ------------------- | --- | ----------------------- | --- | --- | --- | --- |
| "timeoutMs":        |     | 30000,                  |     |     |     |     |
2

"sideEffecting": true,
"metadata": {
"endpoint": "https://mock-video.example.com/generate",
"provider": "MockVideoAPI"
}
}
Execution Contract
1. Input validation: The tool engine must validate the input against inputSchema before invoking
the tool. Invalid inputs result in a validation error and no call is made.
2. Permission check: Before each call, the permission engine must verify that the execution context
has all permissionScopes declared by the tool. If a scope is restricted or
require_confirmation , the engine must pause or block the call accordingly.
3. Timeout enforcement: If the tool does not complete within timeoutMs , the engine should
terminate the call and classify the error as timeout . Retries may be attempted based on
configured retry policy.
4. Provider invocation:
5. For local tools, call the local adapter with the validated input.
6. For api tools, call the configured endpoint or SDK. The engine must inject credentials from
environment variables or secrets manager and must not log raw tokens.
7. For mcp tools, call the MCP client with the mapped tool metadata. The MCP layer should handle
authentication, discovery and error mapping.
8. For rag_adapter tools, call the RAG subsystem in read?only mode with the provided query. No
ingestion or mutation operations are allowed.
9. Result normalization: The raw output should be validated against outputSchema and then
mapped into the stepÆs expected output fields. The engine should return only the data needed by the
workflow and omit any sensitive metadata.
10. Error handling: Errors must be classified as one of validation , permission , tool ,
timeout , or external_api . Each error should include a code, message, details, recoverability
flag, and suggested action.
11. Logging: Log the tool call with execution ID, tool ID, provider type, input summary, output summary,
error class, duration, and whether redaction was applied. Do not log secrets, full payloads or raw
tokens.
Provider?Specific Notes
Local Providers
ò Should run in a sandboxed environment with resource limits (CPU, memory, disk).
ò File system tools must be constrained to allowed directories.
ò Code execution tools (e.g. Python) should be limited to restricted modules and not allow arbitrary
network access unless explicitly allowed.
3

API Providers
ò Credentials (API keys, tokens) must be sourced from environment variables or secret management.
They must never be hard?coded or logged.
ò The tool metadata should include endpoint URL and any required headers.
ò Consider adding retry policies and exponential backoff to handle transient failures.
MCP Providers
ò The MCP integration layer is responsible for discovering tools and mapping them into the internal
schema. Each discovered tool must be assigned a unique id , providerType of mcp , and
appropriate permissionScopes based on the providerÆs capabilities.
ò Unknown MCP tools must not be executed until explicitly allowed and registered.
ò Use caching to reduce discovery calls, and handle provider downtime gracefully.
RAG Adapter Providers
ò Only read?only retrieval operations are allowed. Ingestion, mutation, deletion, or index modification
operations must never be exposed through a rag_adapter tool.
ò Inputs typically include a query string and optional topK parameter.
ò Outputs should return items with fields like title , content , and optional metadata .
ò The adapter should support simple filtering or ranking parameters but should never influence the
planning logic.
Tool Registration
Tools should be registered via a registry service or CLI with their manifests. Registration should validate the
manifest, assign the tool to the correct provider type, and ensure there are no ID collisions. Once
registered, tools can be discovered by skills via the required_tools list.
Deprecation and Removal
ò Mark tools as enabled: false to prevent new executions while still allowing historical logs to be
reviewed.
ò Before removing a tool completely, migrate or disable any skills that depend on it.
ò Document the reason for deprecation and possible alternatives.
4
