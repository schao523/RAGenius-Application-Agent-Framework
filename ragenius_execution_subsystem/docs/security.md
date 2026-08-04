# RAGenius Execution Subsystem Security Guide

## Current Security Guarantees

- Unknown or disabled skills are rejected.
- Unknown tools are rejected.
- Tool input is validated before execution.
- Permission checks run before every tool call.
- `rag_retrieval_tool` is read-only.
- Side-effecting tools require explicit policy.
- `require_confirmation` pauses execution before the tool runs.
- Sensitive fields are redacted in log summaries.

## Redacted Fields

- `authorization`
- `cookie`
- `set-cookie`
- `api_key`
- `apikey`
- `access_token`
- `refresh_token`
- `password`
- `secret`
- `private_key`
- bearer-token-like strings

## MVP Security Limits

- No real external providers are used.
- No real MCP server credentials are used.
- No confirmation resume endpoint exists yet.
- No persistent audit log storage exists yet.

## High-Risk Tool Policy

- `rag_adapter` read-only retrieval can be auto-allowed
- side-effecting API tools require explicit policy
- discovered MCP write tools are treated as side-effecting

## Dry Run Safety

Dry run validates request, skill, tool availability, and permissions, but does not execute side-effecting tools.
