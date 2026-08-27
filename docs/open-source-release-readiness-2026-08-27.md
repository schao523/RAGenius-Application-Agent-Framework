# Open-Source Release Readiness

Date: 2026-08-27

## Completed Repository Work

- MIT license confirmed.
- Contributor, conduct, security, and support policies added.
- Root architecture, setup, safe-default, startup, and test guidance expanded.
- Builder dependency and environment templates added with placeholders only.
- Pull-request and structured issue templates added.
- Credential-free Windows CI added for all active subsystems.
- Git attributes and editor defaults added.
- Reachable Git history audited for credentials; see
  `open-source-secret-audit-2026-08-27.md`.

## Local Verification

| Area | Result |
| --- | --- |
| RAG subsystem | 35 passed |
| App backend | 131 passed, 1 skipped |
| App frontend | 182 passed; production build passed |
| Builder | 125 passed |
| Execution subsystem | 522 passed, 8 live tests skipped; typecheck and lint passed |

The first restricted local runs reproduced environment-only ACL and child
process errors. Repository-scoped temp paths and unrestricted process execution
produced the results above. A clean GitHub Actions runner should not contain the
stale local scratch directories that caused those initial errors.

## Safe Release Profile

- MCP elicitation is disabled by default.
- Managed authentication handoff is disabled by default.
- Generic user action is disabled by default.
- Authentication host and managed-target allowlists are empty by default.
- Gmail support is an explicit administrator opt-in using the trusted verifier.
- Browser and Computer Use post-action semantic verification remains deferred.
- Live provider tests are not part of credential-free CI.

## Deferred Engineering Work

- Managed authentication initiated by an approved instruction skill.
- Duplicate live interaction-response verification against an external write.
- Browser or Computer Use post-action semantic verification.
- Broader platform qualification beyond the Windows integrated path.

## Repository Host Checklist

Before changing repository visibility or announcing a release:

1. Push this baseline and confirm all GitHub Actions jobs pass.
2. Enable private vulnerability reporting and GitHub secret scanning.
3. Enable dependency alerts and review any actionable production dependency
   findings.
4. Protect `main` and require the CI workflow for pull requests.
5. Confirm issue, security-advisory, and branch-protection links with a
   non-maintainer account.
6. Create the first version tag only after the remote CI and safe-default smoke
   test pass.

Do not enable optional provider credentials in repository or organization
secrets merely to make live tests run on public pull requests.
