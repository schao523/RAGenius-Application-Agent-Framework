# RAGenius Execution Subsystem Architecture

## Purpose

The MVP implements a controlled execution backend for `ragenius_app`.

The current runtime is a vertical slice:

1. validate request
2. load skill
3. validate skill input
4. resolve tools
5. evaluate permissions
6. short-circuit dry run or pending confirmation
7. execute workflow steps through `ToolEngine`
8. normalize result

## Boundaries

```text
ragenius_app
  = reasoning, planning, final user-facing answers

ragenius_execution_subsystem
  = validated skill execution through tools

rag_subsystem
  = retrieval and ingestion, but this MVP only uses read-only retrieval

ragenius_builder
  = app configuration
```

## Implemented Core Components

- `ExecutionEngine`
- `SkillRegistry`
- `ToolRegistry`
- `ToolEngine`
- `PermissionEngine`
- `WorkflowOrchestrator`
- redaction-aware logging helpers

## Current Skills and Tools

### Skill

- `video_director_skill`

### Tools

- `rag_retrieval_tool`
- `mock_video_generation_tool`
- discovered mock MCP tools registered through `POST /v1/tools/discover/mcp`

## MVP Limitations

- Execution lookup and log retrieval routes are stubbed with `501`.
- Persistence is schema-first only at this stage.
- MCP discovery is mock-backed only.
- Confirmation can pause execution, but resume/confirm endpoints are not implemented yet.
- Queue and worker execution are deferred.
