# Changelog

Notable changes will be recorded here. This project follows semantic versioning
once tagged public releases begin.

## Unreleased

### Added

- Governed Codex and OpenClaw Agent execution.
- Builder-managed Agent Skill discovery, approval, binding, and synchronized
  trusted projections.
- Session-scoped artifacts and Agent input staging.
- Provider-neutral interactive execution with confirmation, cancellation,
  recovery, and bounded diagnostics.
- Optional Codex MCP elicitation and managed Gmail authentication verification,
  disabled by default.

### Security

- Service-to-service authentication and scoped credentials.
- Single-use confirmation and interaction state machines.
- Filesystem and WSL path-containment checks.
- Fail-closed provider verification and redacted execution diagnostics.
