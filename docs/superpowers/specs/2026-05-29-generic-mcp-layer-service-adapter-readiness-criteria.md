# Generic MCP Layer + Service Adapter Readiness Criteria

## Purpose

Define the concrete criteria for declaring the `ragenius_execution_subsystem` Generic MCP Layer + Service Adapter architecture “fully realized enough” for this system.

This is a pragmatic readiness bar, not an abstract purity test.

The question is not:

- can the current code call more than one MCP server?

The real question is:

- has the architecture become systematic enough that new MCP-backed and adapter-backed capabilities can be added safely, predictably, and with low special-case cost?

## Meaning of “Fully Realized Enough”

For RAGenius, this architecture is “fully realized enough” when:

- adding the next approved MCP provider is mostly configuration, allowlisting, policy mapping, normalization rules, and tests
- service adapters and MCP-backed services share a clear workflow seam
- Builder can safely expose and govern executable contracts for both classes
- operators can understand, review, and control what is enabled
- app isolation and permission boundaries remain intact

This does **not** mean:

- every possible MCP server works automatically
- all providers need zero provider-specific code
- the system is feature-complete forever

It means the architecture has crossed from “promising vertical slices” into “repeatable platform pattern.”

## Readiness Criteria

## 1. Core Transport And Invocation Layer

The architecture is not ready enough until the MCP foundation itself is stable and reusable.

Required criteria:

- real MCP lifecycle support exists and is used in production code:
  - `initialize`
  - `notifications/initialized`
  - `tools/list`
  - `tools/call`
- at least one real remote HTTP MCP provider is working end to end
- the same MCP client seam is reused across multiple providers
- session/header/auth handling is provider-configurable, not hardcoded to one provider
- transport errors are normalized into clear runtime error classes

Practical pass condition:

- adding a second and third HTTP MCP provider does not require a new transport client implementation

## 2. Provider Onboarding Must Be Systematic

The architecture is not ready enough if every new provider still feels like a custom integration project.

Required criteria:

- each new MCP provider follows the same onboarding checklist:
  - runtime config
  - auth source
  - allowlist
  - permission mapping
  - normalization rules
  - tests
- provider config shape is stable and documented
- discovered tool registration follows the same registry pattern:
  - `mcp.<provider>.<tool>`
- provider onboarding does not require redesigning `ToolEngine`
- provider onboarding does not require ad hoc route additions

Practical pass condition:

- Gmail, Google Drive, Calendar, and Docs/Sheets can all be onboarded through the same provider lifecycle with only small provider-specific code

## 3. Service Adapter Layer Must Be First-Class

This architecture is not only about MCP.

It is only “fully realized enough” if internal/external service abstractions are both first-class and share the same workflow seam.

Required criteria:

- `service_call` is the stable workflow seam for:
  - MCP-backed services
  - adapter-backed services
- approved adapters are configured through a stable runtime config model
- adapter-backed tools do not require separate workflow semantics from MCP tools
- permission enforcement works for adapters and MCP tools consistently

Practical pass condition:

- an operator can understand adapter-backed and MCP-backed services as two provider classes under one execution model

## 4. Tool And Service Registry Discipline

The registry layer must be clean enough that the system remains inspectable as more providers are added.

Required criteria:

- discovered MCP tools are registered explicitly
- allowlisted tools only are exposed
- side-effecting classification is explicit
- permission scopes are explicit
- tool ids remain stable once published into Builder contracts
- service adapters also appear as explicit registry-backed capabilities

Practical pass condition:

- the registry is the source of truth for what the runtime can execute, regardless of whether the capability came from local tools, adapters, or MCP discovery

## 5. Builder Normalization Must Be Repeatable

The architecture is not ready enough if Builder inference remains mostly handcrafted per skill forever.

Required criteria:

- Builder can normalize multiple provider families through consistent patterns
- Builder can infer:
  - candidate tools
  - required permissions
  - workflow template
  - risk level
- all MCP-backed skill families are `review_required` unless explicitly proven safe and read-only enough for a future relaxation
- normalization is based on supported capability families, not arbitrary freeform interpretation

Practical pass condition:

- Gmail, Drive, Calendar, Docs/Sheets, and adapter-backed admin/content skills all fit the same normalization discipline

## 6. Builder Governance UX Must Be Sufficient

The architecture is not ready enough if operators cannot see what will actually execute.

Required criteria:

- Builder shows inferred contract metadata before publish
- operators can inspect:
  - tools
  - permissions
  - schemas
  - workflow
  - risk class
- risky contracts are clearly labeled
- unsupported contracts are clearly labeled
- publish does not rely on hidden inference

Practical pass condition:

- a reviewer can tell, from Builder alone, whether a skill is:
  - low-risk read-only
  - mutation-capable
  - external-write-capable
  - unsupported

## 7. Permission And Isolation Model Must Hold Across Providers

This is a hard gate.

The architecture is not ready enough unless isolation and permission behavior remain consistent as providers expand.

Required criteria:

- app isolation is preserved
- artifact scoping is preserved
- read/write scopes are explicit and enforced
- confirmation-gated execution works for side-effecting adapter and MCP paths
- provider onboarding does not bypass the shared permission engine
- external providers remain read-only or write-scoped according to declared policy

Practical pass condition:

- adding a new provider cannot silently introduce a side-effecting path outside the existing permission/confirmation model

## 8. Observability And Failure Handling Must Be Good Enough

The architecture is not ready enough if failures are too opaque to operate safely.

Required criteria:

- provider discovery failures are visible
- auth failures are visible
- allowlist failures are visible
- execution records persist enough lifecycle data to debug service calls
- review-required and pending-confirmation flows are traceable
- logs avoid secret leakage

Practical pass condition:

- an operator can distinguish:
  - config failure
  - auth failure
  - provider discovery failure
  - tool not allowlisted
  - permission confirmation required
  - downstream tool call failure

## 9. Provider Coverage Threshold

A single provider is not enough to declare the architecture mature.

Minimum practical threshold:

- at least 3 distinct real MCP provider families working end to end
- at least 1 meaningful adapter-backed service family working end to end

Recommended provider mix:

- communication: Gmail
- storage/content: Google Drive
- scheduling: Google Calendar
- document productivity: Docs and/or Sheets
- internal service abstraction: at least one approved adapter family

Why this matters:

- it proves the architecture handles different capability shapes rather than just one provider’s quirks

## 10. Marginal Cost Test

This is the most practical readiness test.

The architecture is “fully realized enough” when the marginal cost of adding the next provider is low and predictable.

Pass condition:

Adding the next provider should usually require only:

1. config entry
2. allowlist
3. permission mapping
4. small normalization rules
5. tests

Fail condition:

If each provider still requires:

- major tool-engine changes
- new workflow semantics
- new admin routes
- custom execution lifecycle logic

then the architecture is still not sufficiently generalized.

## Declared Readiness Bar

For this system, the Generic MCP Layer + Service Adapter architecture should be declared “fully realized enough” only when **all** of the following are true:

- the generic MCP transport/lifecycle layer is reused across multiple real providers
- service adapters and MCP-backed services both execute through the same `service_call` seam
- Builder normalization and review UX handle both families clearly
- permission, confirmation, and app-isolation rules hold across providers
- operators can review and diagnose provider-backed contracts cleanly
- at least three distinct real MCP provider families are working end to end
- adding the next provider is mostly configuration + policy + tests, not architecture work

## Current Status Interpretation

Given the current system state, the architecture is best described as:

- **validated foundation**
- **credible reusable pattern**
- **not yet fully realized enough**

Why:

- Gmail is a strong real MCP proof
- service adapters exist
- `service_call` exists
- Builder normalization and review UX now exist

But:

- real provider count is still too small
- provider onboarding is still somewhat handcrafted
- broader operator governance and generalized provider abstraction still need more proof

## Recommendation

Use this document as the readiness gate for future expansion.

The next major checkpoint should be after:

- Gmail
- Google Drive
- Google Calendar
- Docs/Sheets

and at least one solid adapter-backed family

At that point, reassess against this checklist instead of relying on intuition.
