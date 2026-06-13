# Backend Hardening Implementation Plan for Generic MCP, Adapters, and Policy Contracts

Date: 2026-06-02
Status: Proposed
Scope: `ragenius_builder`, `ragenius_execution_subsystem`

## Goal

Solidify the Builder and execution backend before moving user-facing workflow UX into `ragenius_app`.

This plan addresses the remaining gaps discussed across:

- Generic MCP Layer + Service Adapter maturity
- policy-contract maturity
- Builder contract extraction and governance hardening
- execution-subsystem provider/fallback diagnostics and persistence
- MCP provider configuration/discovery usability

The target outcome is a backend that is:

- stable enough for real user-facing workflows in `ragenius_app`
- explicit about policy and execution-path decisions
- low-friction to onboard the next MCP provider
- auditable when MCP-native vs fallback execution paths differ

## Non-Goals

This phase does not include:

- end-user workflow UX in `ragenius_app`
- broad new provider families beyond hardening the current Gmail, Drive, and Docs baseline
- replacing current Builder skill authoring with an LLM-first system
- rewriting core retrieval logic in `rag_subsystem`

## Current Baseline

The system already supports:

- Builder-managed executable contract normalization for several safe and MCP-backed skill families
- typed policy modules in Builder and runtime
- Gmail MCP read/write slices
- Google Drive read/download slices
- Google Docs read-only slice
- confirmation-gated side effects
- targeted Drive and Gmail REST fallbacks for known managed-MCP gaps

The remaining issues are mainly hardening, generalization, and operability.

## Workstreams

## 1. MCP Lifecycle and Tool Registry Hardening

### Problem

MCP tools must currently be rediscovered after runtime restart, and supported providers/tools are not visible enough to operators.

### Objective

Make enabled MCP providers and allowlisted tools come online predictably, with clear runtime state and operator visibility.

### Tasks

1. Add startup auto-discovery for enabled MCP providers.
   - On runtime boot, discover allowlisted tools for every enabled HTTP MCP provider.
   - Register discovered tools before the service is considered ready.

2. Add discovery state tracking in runtime.
   - Track:
     - configured providers
     - enabled providers
     - discovery success/failure
     - last discovery timestamp
     - discovered tool count

3. Extend `/readyz` and tool routes.
   - Include per-provider discovery status.
   - Include whether tools were:
     - MCP-native only
     - fallback-capable

4. Add optional on-disk discovery cache.
   - Persist remote tool metadata and schemas for diagnostics and cold-start visibility.
   - Cache must not bypass actual registration on startup; it is visibility support, not a substitute for registration.

5. Add explicit refresh endpoint semantics.
   - Keep manual rediscovery available.
   - Distinguish:
     - startup discovery
     - manual refresh
     - cached metadata view

### Acceptance Criteria

- Restarting `ragenius_execution_subsystem` no longer requires manual discovery in normal operation.
- `/readyz` reports whether each provider was discovered successfully.
- `/v1/tools` and `/v1/tools/discover/mcp` clearly show discovered MCP tools and schemas.

## 2. Provider Fallback Formalization

### Problem

Drive and Gmail fallbacks now exist, but they are tactical fixes rather than explicit architecture.

### Objective

Promote fallback behavior into a first-class execution concept with explicit rules, provenance, and auditability.

### Tasks

1. Define fallback policy model in runtime policy config.
   - Add typed policy for:
     - fallback enabled/disabled per provider/tool
     - allowed fallback transport
     - allowed fallback operation classes

2. Introduce execution-path provenance in tool results.
   - For each tool execution, record:
     - `execution_path`
       - `mcp`
       - `rest_fallback`
       - `adapter`
     - provider id
     - remote tool id
     - fallback reason if fallback used

3. Add fallback-aware audit logs.
   - Log:
     - MCP failure class
     - fallback invocation
     - fallback success/failure
   - Avoid logging secrets or payload content.

4. Standardize fallback classification helpers.
   - Move provider-specific string matching into reusable helpers or a typed classification layer.
   - Separate:
     - auth failure
     - schema mismatch
     - permission-style rejection
     - service-disabled

5. Add fallback result normalization rules.
   - Ensure MCP-native and fallback responses normalize to the same contract.

### Acceptance Criteria

- Execution results and logs state when fallback was used.
- Fallback eligibility is policy-driven, not only hardcoded.
- Gmail/Drive fallback behavior is consistent and auditable.

## 3. Provider Contract Mapping Generalization

### Problem

Provider input/output mappings and error interpretations are still partially hardcoded and brittle.

### Objective

Reduce one-off provider logic and make provider onboarding more systematic.

### Tasks

1. Introduce provider capability descriptors.
   - For each supported tool family, define:
     - canonical capability id
     - input mapping
     - output normalization
     - permission scopes
     - side-effect classification

2. Move provider-specific schema assumptions into explicit mapping modules.
   - Gmail:
     - create draft
     - create draft with attachments
     - send draft
     - send message
   - Drive:
     - search files
     - download file content
   - Docs:
     - search documents

3. Preserve remote schemas and descriptions consistently.
   - Ensure discovery routes expose:
     - real remote input schema
     - remote description
     - internal normalized contract

4. Add contract mismatch diagnostics.
   - When remote tools reject payload shape, surface:
     - remote response body
     - tool name
     - normalized input summary

5. Define the onboarding checklist for the next provider.
   - Required artifacts:
     - provider config
     - allowlist
     - capability mapping
     - policy entry
     - Builder alias mapping
     - tests

### Acceptance Criteria

- Adding the next MCP provider is mostly config + mapping + tests.
- Discovery and execution can show both remote schema and normalized contract.
- Remote schema mismatches are diagnosable without code spelunking.

## 4. Builder Contract Extraction and Governance Hardening

### Problem

Builder normalization is stronger than before, but still narrow and partly heuristic.

### Objective

Make Builder more deterministic and transparent for explicit and multi-step skill contracts.

### Tasks

1. Expand deterministic markdown extraction.
   - Support more explicit sections in `SKILL.md` for:
     - inputs
     - outputs
     - workflow steps
     - capability aliases

2. Broaden multi-step contract families.
   - Extend deterministic extraction beyond current fixed paper-finder and Drive->Gmail families.
   - Prioritize explicit capability-driven multi-step skills over keyword fallback.

3. Strengthen alias resolution.
   - Formalize supported author-facing aliases for:
     - Gmail
     - Drive
     - Docs
   - Add validation/errors for unknown aliases instead of silent fallback where possible.

4. Improve review panel clarity.
   - Show:
     - effective template family
     - resolved concrete tool ids
     - policy class
     - confirmation requirement
     - fallback-capable tools

5. Add contract drift protections.
   - Ensure published skill metadata preserves:
     - resolved template family
     - normalized tool list
     - normalized permission list
     - workflow/schema refs or materialized equivalents

### Acceptance Criteria

- Explicitly authored `SKILL.md` contracts are not silently collapsed into generic fallbacks.
- Review panel shows resolved concrete tools and policy expectations clearly.
- More skill families can be authored without requiring internal MCP tool-id knowledge.

## 5. Policy Contract Completion

### Problem

The typed policy model exists, but enforcement is only partially externalized and not fully visible.

### Objective

Complete the first mature backend policy layer for Builder and runtime.

### Tasks

1. Expand typed runtime policy coverage.
   - Add typed sections for:
     - provider fallback policy
     - execution-path provenance policy
     - MCP discovery policy
     - remote tool allowlist policy metadata

2. Expand typed Builder policy coverage.
   - Add family-level policy for:
     - auto-finalization eligibility
     - review-required defaults
     - alias resolution rules
     - unsupported-family behavior

3. Add effective-policy rendering hooks.
   - Builder review panel should show:
     - why a skill is review-required
     - what confirmation mode applies
     - what attachments/fallback rules matter

4. Add policy precedence tests.
   - Verify interactions between:
     - hard invariants
     - typed config policy
     - skill-intent inference
     - bound app permissions

5. Add policy snapshots for current supported families.
   - Gmail draft/send
   - Gmail attachments
   - Drive search/download
   - Docs read

### Acceptance Criteria

- Policy decisions are explainable from config + invariants.
- Builder and runtime are aligned on major policy outcomes.
- Fallback and attachment behavior are governed, not incidental.

## 6. Execution Metadata and Observability

### Problem

Important execution details are not persisted or surfaced consistently enough.

### Objective

Make execution records rich enough to support app UX later without new backend archaeology.

### Tasks

1. Persist richer structured result metadata.
   - For Gmail draft workflows:
     - draft id
     - thread id
     - recipient summary
     - subject
   - For Drive artifacts:
     - source file id
     - artifact id
     - mime type
     - original filename

2. Persist tool-level execution provenance.
   - MCP vs fallback path
   - provider/tool used
   - error/fallback chain summary

3. Improve log summarization.
   - Include whether fallback was used.
   - Include whether confirmation gate was crossed.

4. Add operator diagnostics routes or richer payloads.
   - Do not expose secrets.
   - Do expose enough to debug provider-state problems quickly.

### Acceptance Criteria

- Execution history contains enough metadata to drive future `ragenius_app` follow-up UX.
- Logs can explain how a draft/file result was produced.

## 7. Adapter Model and Capability Abstraction

### Problem

The MCP side is stronger than the generic internal adapter story.

### Objective

Bring adapter modeling closer to parity with MCP-backed execution.

### Tasks

1. Define capability-level abstraction where useful.
   - Preserve concrete tool ids for execution.
   - Add optional higher-level capability labels for:
     - file_discovery
     - file_download
     - draft_create
     - draft_send

2. Align adapter and MCP result normalization.
   - Similar capability families should normalize similarly regardless of provider transport.

3. Define adapter/fallback relationship explicitly.
   - REST fallbacks should be treated as adapter-backed execution paths, not anonymous special cases.

4. Add adapter policy hooks.
   - Adapter paths should participate in the same permission and provenance model.

### Acceptance Criteria

- MCP-native and adapter-backed execution paths are conceptually aligned.
- Fallback paths no longer feel like unowned side code.

## 8. Operator UX for MCP Configuration and Support Visibility

### Problem

It is too hard to know which MCPs are configured, enabled, discovered, and supported.

### Objective

Make backend MCP support operable without shell-only knowledge.

### Tasks

1. Add Builder/admin MCP status view.
   - Show:
     - configured providers
     - enabled flag
     - last discovery status
     - discovered tools
     - auth configured yes/no

2. Add support matrix view.
   - Show supported:
     - author-facing aliases
     - resolved concrete tools
     - policy class
     - fallback availability

3. Add “refresh discovery” admin action.
   - Manual trigger for diagnostics and recovery.

4. Add validation for new MCP configuration entries.
   - Validate:
     - provider id uniqueness
     - base URL
     - auth env name
     - allowlist content

### Acceptance Criteria

- Operators can tell which MCP providers and tools are supported without reading code.
- Restart no longer implies manual shell rediscovery in normal use.

## Implementation Order

### Phase A: Runtime Operability

1. startup auto-discovery
2. runtime discovery status in `/readyz`
3. tool/provider visibility improvements

### Phase B: Fallback Formalization

1. execution-path provenance
2. fallback policy model
3. fallback-aware audit/logging

### Phase C: Provider Mapping Generalization

1. capability descriptors
2. provider mapping modules
3. remote schema visibility and mismatch diagnostics

### Phase D: Builder Hardening

1. expanded deterministic extraction
2. stronger alias validation
3. improved review/governance visibility

### Phase E: Policy Contract Completion

1. typed policy expansion
2. Builder/runtime policy alignment
3. policy precedence tests

### Phase F: Adapter and Support Visibility

1. adapter parity work
2. Builder/admin MCP configuration/status surface
3. support matrix

## Test Strategy

### Runtime

- startup discovery tests
- provider discovery failure-path tests
- Drive/Gmail MCP-native and fallback tests
- provenance persistence tests
- execution metadata normalization tests

### Builder

- alias resolution tests
- markdown extraction tests
- review panel rendering tests
- policy explanation tests

### Integration

- Drive file -> artifact -> Gmail draft
- Gmail draft -> send draft
- managed MCP success
- managed MCP fallback
- provider disabled / auth missing / schema mismatch

## Exit Criteria

This backend hardening phase is complete when:

- enabled MCP providers auto-discover on runtime startup
- runtime can explain configured/discovered provider state without manual debugging
- Gmail/Drive fallback behavior is policy-governed and auditable
- Builder more reliably turns explicit skill intent into executable contracts
- effective policy is visible enough for review and debugging
- execution records persist enough structured metadata for later `ragenius_app` follow-up UX
- onboarding the next provider requires mostly:
  - config
  - allowlist
  - capability mapping
  - policy entries
  - tests

## Recommended Immediate Next Slice

Start with:

1. startup auto-discovery of enabled MCP providers
2. execution-path provenance for MCP vs REST fallback
3. Builder/admin MCP provider and tool status visibility

That gives the highest operational value while stabilizing the architecture before `ragenius_app` work begins.
