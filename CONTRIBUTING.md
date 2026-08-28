# Contributing To RAGenius

RAGenius welcomes focused bug fixes, tests, documentation, provider adapters,
and subsystem improvements.

## Before Starting

- Search existing issues and pull requests.
- Open an issue before a large cross-subsystem or contract change.
- Do not add integrated runtime behavior to `ragenius_app`; use
  `ragenius_app_skeleton`.
- Keep retrieval in `rag_subsystem`, administration in `ragenius_builder`,
  user chat in `ragenius_app_skeleton`, and execution in
  `ragenius_execution_subsystem`.
- Preserve `app_id` isolation and session ownership.

## Development Setup

Follow the root `README.md` and the
[`Contributor Startup Guide`](docs/contributor-startup-guide.md). Use tracked
`.env.example` files as templates and keep real credentials in ignored local
`.env` files. Do not use production accounts or data in tests.

## Change Expectations

- Add or update tests before changing behavior.
- Keep public contracts backward compatible unless a migration is approved.
- Validate inputs at subsystem boundaries.
- Fail closed for authorization, path containment, ownership, and provider
  verification errors.
- Redact tokens, cookies, account identifiers, provider payloads, and private
  artifact content from logs and fixtures.
- Do not commit generated runtime databases, artifacts, model data, test state,
  or dependency directories.

## Verification

Run the relevant commands from the root `README.md`. For a cross-subsystem pull
request, run all credential-free Python and Node suites. Live provider tests
must be described separately and must contain sanitized evidence only.

## Pull Requests

Keep each pull request scoped to one coherent change. Include:

- the problem and boundary affected;
- the implementation and compatibility impact;
- tests run and their results;
- security or migration considerations;
- screenshots for user-visible changes.

By contributing, you confirm that you have the right to submit the work under
the repository's MIT License.
