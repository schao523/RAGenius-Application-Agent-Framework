## Archived FastAPI Prototype

This folder contains the older `v3.3` FastAPI prototype that originally lived at the root of `ragenius_builder/`.

Status:

- archived
- not a supported runtime
- retained only for historical/spec reference

Reasons it is quarantined:

- it uses an in-memory data model and divergent file layout
- it overlaps confusingly with the active Flask builder app
- it is materially behind the current builder/admin implementation in `../flask_scaffold/`

Do not build new builder features here. Use `../flask_scaffold/` instead.
