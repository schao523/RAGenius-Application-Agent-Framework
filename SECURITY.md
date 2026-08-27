# Security Policy

## Supported Code

Security fixes target the current `main` branch and the latest published
release, when releases exist. Older snapshots may not receive fixes.

## Reporting A Vulnerability

Use GitHub's private vulnerability reporting or a private draft security
advisory for this repository. Do not open a public issue for an unpatched
vulnerability and do not include credentials, personal data, provider payloads,
or exploit data in public discussions.

Include the affected revision, subsystem, reproduction conditions, impact, and
a minimal sanitized proof of concept. Maintainers will acknowledge a report as
capacity permits and coordinate disclosure after a fix is available.

## Credential Exposure

If a credential is committed or posted publicly, revoke or rotate it first.
Deleting it from the latest commit is not sufficient because Git history and
forks may retain it. Contact the maintainers privately before attempting a
history rewrite.

## Security Boundaries

RAGenius treats app isolation, session ownership, service credentials,
confirmation state, filesystem containment, provider verification, and log
redaction as security boundaries. Optional Agent and MCP capabilities remain
disabled until explicitly configured by an administrator.
