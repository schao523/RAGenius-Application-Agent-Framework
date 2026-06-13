# AGENTS.md

## Scope

This file applies to work inside:

- `ragenius_builder/`

Use it together with the repository-root `AGENTS.md`.

---

## Runtime Target

Treat:

- `ragenius_builder/flask_scaffold/`

as the active builder/admin runtime.

Do not treat archived FastAPI prototype files as a supported runtime target.

---

## Storage Contract

`ragenius_builder` uses a dual storage model intentionally.

Do not casually merge these storage patterns.

Authoritative reference:

- `docs/ragenius_builder_skill_management_contract.md`

Required distinctions:

- Application instructions are convention-resolved from `DatabaseStore.base_dir` as `instructions/{app_id}/instructions.md`.
- Uploaded application documents are DB-path-resolved from `documents.file_path`.
- Persisted skill files are resolved from `DatabaseStore.base_dir` plus DB-stored relative metadata such as `skill_md_rel_path` and `storage_root_rel_path`.
- Skill import archives use transient staging storage and are not the source of truth for persisted skill resources.

Do not refactor these into a single storage-resolution model unless explicitly requested.

---

## Cleanup Rules

When changing delete or cleanup logic, preserve the existing storage contracts:

- instruction cleanup must use the convention-resolved instructions location
- uploaded document cleanup must use DB `documents.file_path`
- persisted skill cleanup must use skill relative metadata plus `DatabaseStore.base_dir`
- transient skill import cleanup must use staging storage rules

Do not assume one storage root or one resolution strategy for all builder artifacts.

---

## Boundary Rules

Preserve:

- builder/admin workflows in `ragenius_builder`
- application isolation
- `app_id` scoping
- read-only external lookup behavior
- file-backed markdown instructions

Do not move end-user chat workflows into builder.
