# Typed Policy Config Design For Builder And Execution Subsystem

## Purpose

Turn the generic policy contract model into a concrete typed policy configuration design for:

- `ragenius_builder`
- `ragenius_execution_subsystem`

The goal is to replace scattered implicit policy with a clear model that:

- constrains Builder inference and finalization
- guides Builder review/governance UX
- drives runtime enforcement in the execution subsystem
- preserves hard invariants in code

## Design Goals

- keep hard safety invariants non-optional
- move governance and capability policy into typed config
- let Builder inference consult policy instead of duplicating rules
- let runtime enforce provider/tool policy from the same policy family
- support provider-backed workflows, artifact-based workflows, mutation flows, and future attachment flows

## Non-Goals

- no attempt to make all safety behavior fully user-configurable
- no direct secret storage in Builder policy
- no replacement of explicit finalized contracts with freeform inference
- no role-based approval workflow state machine yet

## Policy Layers

The typed policy model should be split into three layers.

### 1. Hard Invariants

Stay in code, not config:

- app isolation
- no cross-app artifact leakage
- no execution of unfinalized draft contracts
- no secret storage in Builder skill metadata
- no bypass of required confirmation for side-effecting operations

Config may narrow behavior, but it must not disable these invariants.

### 2. Shared Policy Config

Typed config that both Builder and runtime can reason about conceptually.

Examples:

- provider enablement policy
- tool allowlist policy
- template-family finalization policy
- confirmation policy
- artifact source policy
- attachment policy

Builder and runtime do not need identical file formats internally, but they should share the same conceptual schema.

### 3. Local Projection Config

Each subsystem will project the shared concepts into its own implementation model.

- Builder projection:
  - inference
  - draft normalization
  - review-required decisions
  - review panel display

- execution subsystem projection:
  - tool/provider allowlists
  - runtime permission enforcement
  - confirmation gating
  - artifact-source enforcement

## Top-Level Policy Shape

Recommended conceptual root:

```ts
type PlatformPolicyConfig = {
  version: string;
  templateFamilies: TemplateFamilyPolicyMap;
  providers: ProviderPolicyMap;
  tools: ToolPolicyMap;
  artifacts: ArtifactPolicyConfig;
  sideEffects: SideEffectPolicyConfig;
  attachments: AttachmentPolicyConfig;
};
```

The config should be versioned so policy behavior can evolve intentionally.

## Typed Sections

### Template Family Policy

Controls Builder normalization and finalization behavior.

```ts
type TemplateFamilyPolicy = {
  policyClass:
    | "safe_read"
    | "review_required"
    | "mutation"
    | "external_write"
    | "unsupported";
  autoFinalize: boolean;
  requiresReview: boolean;
  requiresConfirmation: boolean;
  inferredTools: string[];
  requiredPermissions: string[];
  requiresArtifactSource?: boolean;
};

type TemplateFamilyPolicyMap = Record<string, TemplateFamilyPolicy>;
```

Examples:

- `file_inspection_report`
- `google_drive_read_operation`
- `google_drive_export_operation`
- `gmail_send_message_operation`

Builder uses this to decide:

- how a draft should be classified
- whether auto-finalization is allowed
- what baseline permissions/tools are expected

### Provider Policy

Controls provider enablement and family-wide governance.

```ts
type ProviderPolicy = {
  enabled: boolean;
  reviewRequired: boolean;
  allowedToolIds: string[];
  defaultPermissionMode: "auto_allow" | "require_confirmation" | "restricted";
  requiresArtifactSourceForOutbound?: boolean;
};

type ProviderPolicyMap = Record<string, ProviderPolicy>;
```

Examples:

- `gmail`
- `gdrive`
- `gdocs`
- future `gsheets`, `calendar`

Execution subsystem uses this to constrain discovery and execution. Builder uses it to decide whether inferred provider-backed contracts are always review-only.

### Tool Policy

Controls per-tool behavior beyond provider family defaults.

```ts
type ToolPolicy = {
  enabled: boolean;
  permissionScopes: string[];
  sideEffecting: boolean;
  requiresConfirmation: boolean;
  requiresArtifactSource?: boolean;
  inputSourcePolicy?: "free_input" | "artifact_only" | "provider_id_only";
};

type ToolPolicyMap = Record<string, ToolPolicy>;
```

Examples:

- `mcp.gmail.search_messages`
- `mcp.gmail.send_message`
- `mcp.gdrive.search_files`
- `mcp.gdrive.download_file_content`
- `save_artifact`

Tool policy should override provider defaults when needed.

### Artifact Policy

Controls what artifacts may be produced and consumed across workflows.

```ts
type ArtifactPolicyConfig = {
  enforceAppScope: true;
  allowedSourceKinds: Array<"generated" | "provider_export" | "retrieval_report">;
  outboundEligibleArtifactTypes: string[];
  maxArtifactBytesByType?: Record<string, number>;
};
```

Purpose:

- define which artifact classes may be used as cross-provider handoff objects
- support future attachment workflows without allowing arbitrary file paths

### Side-Effect Policy

Controls generic confirmation and review rules.

```ts
type SideEffectPolicyConfig = {
  requireConfirmationFor:
    Array<"mutation" | "external_write" | "outbound_send">;
  alwaysReviewFamilies: string[];
};
```

Purpose:

- avoid embedding confirmation rules in many per-feature conditionals

### Attachment Policy

A generic section for outbound attachment-like workflows, not tied only to Gmail.

```ts
type AttachmentPolicyConfig = {
  sourceMode: "artifact_only";
  maxAttachmentCount: number;
  maxAttachmentBytes: number;
  allowedMimeTypes: string[];
  allowedArtifactTypes: string[];
};
```

Initial recommendation:

- keep `sourceMode` fixed to `artifact_only`

This should be treated as configurable policy constrained by hard invariants, not as a freeform inference choice.

## Builder Projection

Builder should not execute this policy directly as runtime enforcement, but it should consult a Builder-facing projection.

Recommended Builder policy model:

```ts
type BuilderPolicyProjection = {
  templateFamilies: TemplateFamilyPolicyMap;
  providerReviewPolicy: Record<string, { reviewRequired: boolean }>;
  unsupportedFallbackMode: "descriptive_only" | "reject";
};
```

Builder uses this for:

- normalization classification
- auto-finalization decisions
- review panel labeling
- required tools/permissions defaults

### Builder Storage Guidance

Builder should store with each normalized/published version:

- `template_family`
- `policy_class`
- `auto_finalize`
- `required_tools`
- `required_permissions`
- finalized workflow/schema snapshot
- policy version used at finalization time

That preserves auditability even if policy later changes.

## Execution Subsystem Projection

The execution subsystem should have a runtime projection optimized for enforcement.

Recommended shape:

```ts
type ExecutionPolicyProjection = {
  providers: ProviderPolicyMap;
  tools: ToolPolicyMap;
  artifacts: ArtifactPolicyConfig;
  sideEffects: SideEffectPolicyConfig;
  attachments: AttachmentPolicyConfig;
};
```

Runtime uses this for:

- provider discovery allowlisting
- tool invocation allowlisting
- confirmation gating
- artifact input/output checks
- outbound capability restrictions

### Runtime Config Integration

This should sit alongside existing runtime config rather than replacing it.

For example:

- existing env/runtime config still provides:
  - base URLs
  - auth token env names
  - enabled providers
- policy config adds:
  - what those providers/tools are allowed to do
  - what input/output models are permitted

So:

- operational connectivity config stays operational
- governance and capability rules move into typed policy config

## File/Env Shape Recommendations

### Builder

Recommended first storage form:

- JSON file under Builder config or seeded DB-backed config record

Example conceptual file:

```json
{
  "version": "1",
  "templateFamilies": {
    "gmail_send_message_operation": {
      "policyClass": "external_write",
      "autoFinalize": false,
      "requiresReview": true,
      "requiresConfirmation": true,
      "inferredTools": ["mcp.gmail.send_message"],
      "requiredPermissions": ["external_api.write"]
    }
  }
}
```

### Execution Subsystem

Recommended first storage form:

- JSON env var or JSON config file loaded at startup

Example:

```env
POLICY_CONFIG_JSON={...}
```

or

```env
POLICY_CONFIG_PATH=./config/policy.json
```

Recommendation:

- use a typed JSON file path for maintainability
- use env only to point to the file

## Precedence Rules

Policy resolution should follow this order:

1. hard invariants
2. explicit tool policy
3. provider policy
4. template-family defaults
5. inferred draft assumptions

This ensures:

- explicit runtime restrictions win
- inference never overrides safety boundaries

## Example: Google Drive Export + Future Gmail Attachment

Under this model:

- Builder infers `google_drive_export_operation`
- template family policy marks it `review_required`
- tool policy says `mcp.gdrive.download_file_content` is read-only
- artifact policy says `google_drive_export` is outbound-eligible
- attachment policy later says outbound attachments must come from artifact ids only

Then a future Gmail attachment workflow can consume:

- only app-scoped eligible artifacts
- not arbitrary local file paths
- not arbitrary Drive ids directly

That is exactly the kind of boundary this policy model is meant to standardize.

## Implementation Recommendations

### Phase 1

Introduce typed policy structures in code with seeded defaults:

- Builder:
  - policy module for template families
- execution subsystem:
  - policy module for providers/tools/artifacts

### Phase 2

Refactor current hard-coded normalization decisions to consult policy:

- Gmail families
- Docs/Drive families
- mutation families

### Phase 3

Refactor runtime provider/tool rules to consult policy:

- MCP allowlists
- confirmation gating
- artifact-source enforcement

### Phase 4

Expose read-only policy visibility in Builder review UX and runtime diagnostics.

## Acceptance Criteria

This design is implemented well enough when:

- Builder normalization no longer depends primarily on ad hoc hard-coded family rules
- execution subsystem provider/tool restrictions can be explained through typed policy config
- finalized skill contracts record the policy version used
- future attachment-capable flows can be expressed as policy-constrained artifact-based contracts
- hard invariants remain enforced in code, not downgraded into optional config

## Recommendation

The next concrete move after this design is:

1. implement a small typed policy module in Builder
2. implement a matching runtime policy module in `ragenius_execution_subsystem`
3. migrate one real family, such as Google Drive export/read plus Gmail outbound send, to read from policy instead of embedded conditionals
