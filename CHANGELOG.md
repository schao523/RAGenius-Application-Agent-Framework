# Changelog

Notable changes will be recorded here. This project follows semantic versioning
once tagged public releases begin.

## [v1.0.3] - 2026-09-11

### Security

- Updated Fastify and the frontend and execution-subsystem Vitest toolchains to
  patched releases.
- Pinned patched transitive releases of `fast-uri` and `js-yaml` in the
  execution subsystem.
- Resolved the npm dependency vulnerabilities reported for the execution
  subsystem and application frontend.

### Documentation

- Added a bounded runtime test specification for determining whether Codex
  Desktop Computer Use application approval is inherited by independent Codex
  CLI, direct App Server, or RAGenius-launched App Server processes while
  preserving fail-closed behavior.

## [v1.0.2] - 2026-09-08

### Added

- Governed Codex and OpenClaw Agent execution.
- Builder-managed Agent Skill discovery, approval, binding, and synchronized
  trusted projections.
- Session-scoped artifacts and Agent input staging.
- Provider-neutral interactive execution with confirmation, cancellation,
  recovery, and bounded diagnostics.
- Optional Codex MCP elicitation and managed Gmail authentication verification,
  disabled by default.
- Windows Docker demo package using public GHCR images, immutable demo seed
  data, writable Docker volumes, and local embedding model setup.
- Official public demo seed data for Bible Tutor, Church Ministry Prompt
  Designer, and GPT Application Design Assistant.

### Fixed

- Normalized final-answer citation metadata before schema validation so
  internal retrieval fields such as `chunk_id` cannot crash chat responses.
- Refreshed demo instruction-understanding snapshots from active runtime
  snapshots.
- Improved Docker demo defaults for Windows x64 and Windows ARM64 Docker
  Desktop evaluation.

### Documentation

- Added RAGenius User Guide coverage for Docker demo installation,
  source-checkout runner usage, embedding setup, PowerShell ExecutionPolicy,
  preserved Docker volumes, and advanced Codex/OpenClaw integration setup.

### Security

- Service-to-service authentication and scoped credentials.
- Single-use confirmation and interaction state machines.
- Filesystem and WSL path-containment checks.
- Fail-closed provider verification and redacted execution diagnostics.
