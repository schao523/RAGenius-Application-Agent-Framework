# # AGENTS.md

# Codex-RAGenius-System

## Repository Mission

RAGenius is a multi-application RAG platform.

Core components:

- rag_subsystem/       Protected ingestion + retrieval engine
- ragenius_app_skeleton/ Active Builder-backed end-user runtime
- ragenius_app/       Legacy/reference app scaffold and specification source
- ragenius_builder/   Admin / Builder control plane
- shared/ = reusable modules

The Builder creates and manages isolated knowledge applications.

---

## Application Status

The production applications are:

- ragenius_app_skeleton
- ragenius_builder

Do not treat Builder as secondary. `ragenius_app` remains independently
runnable for legacy/reference purposes, but it is not used by the integrated
runtime and must not receive new integrated runtime behavior.

---

## Routing Rules

Use ragenius_builder for:

- apps CRUD
- instructions markdown editor
- schema-driven settings UI
- uploads
- docs management
- search admin tools
- external lookup APIs

Use ragenius_app_skeleton for:

- chat 
- user workflows
- citations 
- sessions
- user-facing UX

Use rag_subsystem for:

- retrieval
- ingestion
- vector operations

---

## Boundary Rules

Do not duplicate retrieval logic outside `rag_subsystem`.

Do not put admin workflows into `ragenius_app_skeleton`.

Do not place end-user chat flows into `ragenius_builder`. 

Do not add new integrated runtime flows to `ragenius_app`.



***

## Isolation Rules (Critical)

Every application is isolated.

Always enforce:

- app_id scoped retrieval
- no cross-app leakage
- unique application names
- external lookup read-only

---

## Instructions Storage Rules

Use file-backed markdown instructions:

instructions/{app_id}/instructions.md

Track metadata in DB.

Do not redesign storage without explicit request.

---

## Subsystem Protection

rag_subsystem is business-critical.

Do not rewrite core retrieval/indexing unless explicitly asked.

---

## Priority Order

1. Broken production flows
2. Builder critical functions
3. App user flows
4. Integration
5. Tests
6. Refactor

---

## Implementation Style

Prefer:

- simple maintainable code
- explicit contracts
- schema validation
- backward compatibility

Avoid unnecessary rewrites.

