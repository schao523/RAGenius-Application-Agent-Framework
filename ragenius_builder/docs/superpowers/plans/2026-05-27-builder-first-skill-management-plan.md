# RAGenius Builder-First Skill Management Plan

Date: 2026-05-27

## 1. Short Architectural Summary

`ragenius_builder` should be extended into an admin-facing skill console that owns:

- skill ingestion/import
- skill storage
- skill metadata
- skill lifecycle and publish state
- versioning
- app-skill bindings
- admin test initiation

`ragenius_execution_subsystem` must remain the runtime executor. Builder must never execute skills locally. Builder should only:

- validate and publish skill definitions
- expose published skill data through read contracts
- call the execution subsystem for test runs
- display the raw normalized execution result

This plan assumes the active builder runtime is the Flask scaffold in `ragenius_builder/flask_scaffold/`, backed by SQLite plus builder-managed file storage.

### First Success Criterion

The first builder-first MVP is successful when:

- a builder admin can upload/import a skill
- view and manage the imported skill
- publish a valid version
- bind that published skill to an app
- trigger a test execution through `ragenius_execution_subsystem`
- view the raw normalized execution result returned by the execution subsystem

## Must-Have For Builder-First MVP

- managed skill storage and metadata persistence in builder
- self-contained skill folder import with validation
- required lifecycle states with enforced publish gate
- versioned skill records
- explicit app-skill binding records
- builder admin UI for import, list, detail, bind, and test
- builder-to-execution-subsystem client
- raw normalized result display
- narrow published-skill read contract for runtime consumers

## Defer Until Later

- end-user `ragenius_app` integration
- marketplace/discovery features
- rich collaborative review workflows
- approval/resume UX for pending confirmations
- queued async builder test-job persistence
- multi-tenant auth/RBAC hardening beyond local admin assumptions
- distributed skill storage backends
- full execution replay/history browser
- live external tool connectivity beyond current execution subsystem MVP

## 2. Staged Milestones

## Phase 1: Builder Skill-Management Foundation

### Milestone 1.1: Skill Domain Model And Storage Layout

Objective:

- establish the canonical builder-owned model for skills, versions, files, and bindings
- define where managed skill folders live on disk and how builder references them

Likely files/modules/areas affected:

- `ragenius_builder/flask_scaffold/storage.py`
- new builder modules such as:
  - `ragenius_builder/flask_scaffold/skill_models.py`
  - `ragenius_builder/flask_scaffold/skill_storage.py`
  - `ragenius_builder/flask_scaffold/skill_paths.py`
- builder-managed runtime storage roots, for example:
  - `ragenius_builder/flask_scaffold/storage/skills/managed/`
  - `ragenius_builder/flask_scaffold/storage/skills/workspace/`

Dependencies:

- builder skill-management contract in `docs/ragenius_builder_skill_management_contract.md`
- current builder SQLite persistence approach in `flask_scaffold/storage.py`

Acceptance criteria:

- a documented canonical skill storage path exists
- builder distinguishes logical skill identity from versioned skill content
- builder schema covers:
  - `skills`
  - `skill_versions`
  - `app_skill_bindings`
  - optional `skill_validation_results`
- workspace-scoped vs managed-scoped skills are modeled explicitly even if MVP only enables managed scope first

Architectural cautions:

- do not overload `applications`, `instructions`, or `documents` tables with skill concerns
- do not store skill content only in SQLite blobs if the canonical architecture is file-folder based
- do not make bindings implicit through naming or folder placement

Recommended model:

- `skills`
  - stable `id`
  - `slug`
  - `name`
  - `scope`
  - `owner_app_id` nullable
  - `status_summary`
  - `created_at`
  - `updated_at`
  - `current_active_version_id` nullable
  - `current_published_version_id` nullable
- `skill_versions`
  - stable row id
  - `skill_id`
  - semantic `version`
  - lifecycle `state`
  - `manifest_format`
  - `skill_md_rel_path`
  - `storage_root_rel_path`
  - `checksum`
  - `import_source`
  - `validation_status`
  - `published_at` nullable
  - `created_at`
  - `updated_at`
- `app_skill_bindings`
  - per contract:
    - `id`
    - `app_id`
    - `skill_id`
    - `skill_version`
    - `enabled`
    - `permission_mode`
    - execution policy JSON
    - timestamps

### Milestone 1.2: Skill Import/Ingestion Pipeline

Objective:

- allow admin upload/import of a self-contained skill folder into builder-managed storage

Likely files/modules/areas affected:

- `ragenius_builder/flask_scaffold/app.py`
- new modules such as:
  - `skill_import.py`
  - `skill_archive.py`
  - `skill_validation.py`
- new templates:
  - `templates/skills_import.html`
  - `templates/skills_list.html`
  - `templates/skill_detail.html`
- `static/app.js`

Dependencies:

- milestone 1.1 storage model
- canonical skill folder contract

Acceptance criteria:

- admin can upload a `.zip` skill package for MVP import
- builder extracts import into a temp location, validates structure, then writes into canonical managed storage
- required file `SKILL.md` is enforced
- supported subfolders are accepted:
  - `assets/`
  - `references/`
  - `workflows/`
  - `prompts/`
  - `schemas/`
- disallowed patterns are blocked:
  - path traversal
  - executable/script payloads outside explicitly allowed text/resource types
  - duplicate version import without explicit replace/new-version flow

Architectural cautions:

- do not depend on browser local-folder APIs for MVP; zip import is simpler and deterministic
- do not import directly into the live canonical path before validation completes
- do not assume all skills are execution-ready because they contain `SKILL.md`

MVP import policy:

- support managed-skill zip import first
- defer browser directory upload and skill authoring-from-scratch wizard

### Milestone 1.3: Metadata Extraction, Lifecycle States, And Publish Validation

Objective:

- extract skill metadata from imported content
- enforce lifecycle states and a validation gate before publish

Likely files/modules/areas affected:

- `skill_validation.py`
- `skill_models.py`
- `storage.py`
- `app.py`
- `templates/skill_detail.html`

Dependencies:

- milestones 1.1 and 1.2
- execution subsystem manifest spec in `ragenius_execution_subsystem/docs/skill-manifest-spec.md`

Acceptance criteria:

- builder stores extracted metadata:
  - skill id
  - name
  - version
  - description
  - required tools
  - required permissions
  - workflow references
  - manifest checksum
- builder supports required lifecycle states:
  - `draft`
  - `review`
  - `published`
  - `active`
  - `deprecated`
  - `disabled`
  - `archived`
- publish action is blocked until validation passes
- validation report is visible in builder UI

Architectural cautions:

- do not let builder “fix” manifests silently during import
- do not allow unpublished versions to be treated as runtime-consumable
- do not confuse `published` with `active`; binding/test selection rules must be explicit

Minimum publish validation set:

- `SKILL.md` exists and parses into builder metadata
- required manifest fields are present
- declared workflow references exist in the imported folder
- referenced local resource paths resolve inside the skill root
- declared schemas parse
- no invalid/unknown lifecycle transition is allowed

### Milestone 1.4: Versioning Model

Objective:

- support multiple versions per logical skill with explicit publish/activate semantics

Likely files/modules/areas affected:

- `storage.py`
- `skill_models.py`
- `skill_validation.py`
- `templates/skill_detail.html`
- new `templates/skill_version_detail.html`

Dependencies:

- milestone 1.3

Acceptance criteria:

- builder can display all imported versions for a skill
- builder can mark one version as current published
- builder can mark one published version as current active
- builder prevents accidental overwrite of historical versions
- builder can deprecate or disable a version without deleting its stored folder

Architectural cautions:

- version rows should be immutable snapshots for content; state can change, content should not silently mutate
- deleting a version should be deferred; prefer archive/deprecate semantics
- binding records must be able to pin a specific version

Recommended version policy:

- import of a new semantic version creates a new immutable `skill_versions` row
- publish transitions a version from `review` to `published`
- activate sets the logical skill’s `current_active_version_id`
- bindings can either:
  - pin a specific version for MVP
  - later support “follow current active version”

### Milestone 1.5: App-Skill Binding Model And Admin UI

Objective:

- let builder admins bind a published skill version to an application explicitly

Likely files/modules/areas affected:

- `storage.py`
- `app.py`
- `templates/app_detail.html`
- new templates:
  - `templates/app_skills.html`
  - binding section inside `templates/skill_detail.html`

Dependencies:

- milestones 1.1 through 1.4
- existing application CRUD pages in builder

Acceptance criteria:

- admin can bind a published or active skill version to an app
- binding UI captures:
  - skill
  - version
  - enabled flag
  - permission mode
  - simple execution policy JSON or form fields
- app detail page shows current bound skills
- builder prevents binding of draft/review/archived versions

Architectural cautions:

- do not auto-bind imported skills to all apps
- do not store app-specific overrides inside the skill folder itself
- app isolation still applies; bindings must always be app-specific

### Milestone 1.6: Builder Skill Administration Pages And APIs

Objective:

- expose complete admin-facing skill management in both HTML pages and builder JSON APIs

Likely files/modules/areas affected:

- `app.py`
- new templates:
  - `templates/skills_list.html`
  - `templates/skills_import.html`
  - `templates/skill_detail.html`
  - `templates/skill_version_detail.html`
  - `templates/app_skills.html`
- `static/app.js`

Dependencies:

- all prior Phase 1 milestones

Acceptance criteria:

- builder pages exist for:
  - upload/import skill
  - list skills
  - view skill
  - view versions
  - manage lifecycle
  - bind to app
- builder JSON APIs exist for:
  - list skills
  - get skill
  - import skill
  - list skill versions
  - publish/activate/deprecate/disable/archive version
  - list/create/update bindings

Architectural cautions:

- keep builder as admin console, not skill runtime
- keep API surface scoped to builder ownership concerns only

## Phase 2: Builder GUI Test-Skill Capability

### Milestone 2.1: Builder Testability Rules And Test Input UX

Objective:

- define how builder chooses a skill version that can be tested and how admins provide execution input

Likely files/modules/areas affected:

- `app.py`
- new template:
  - `templates/skill_test.html`
- `static/app.js`

Dependencies:

- published skill and binding flows from Phase 1

Acceptance criteria:

- builder only allows test execution for versions that are:
  - `published` or `active`
  - bound to the selected app
  - enabled at both skill/binding levels
- builder test form collects:
  - app id
  - skill id
  - version
  - session id
  - JSON input payload
  - execution options:
    - `dry_run`
    - `require_confirmation`
- input form can optionally prefill from imported skill metadata or stored sample input later, but raw JSON entry is sufficient for MVP

Architectural cautions:

- do not let builder execute unbound draft skills just because an admin imported them
- do not design a user-chat-like interface; this is an operator test console

### Milestone 2.2: Builder-To-Execution-Subsystem Client

Objective:

- let builder call the execution subsystem over HTTP and surface its raw normalized result

Likely files/modules/areas affected:

- new module:
  - `ragenius_builder/flask_scaffold/execution_client.py`
- `app.py`
- optional builder settings surface for execution subsystem base URL

Dependencies:

- execution subsystem API contract:
  - `POST /v1/executions`
  - optional `GET /healthz`
  - optional `GET /readyz`

Acceptance criteria:

- builder can construct the execution request:
  - `request_type: "execute_skill"`
  - `app_id`
  - `session_id`
  - `skill_id`
  - `input`
  - `execution_options`
- builder sends requests to configured execution subsystem base URL
- builder captures:
  - HTTP status
  - response headers if useful
  - parsed JSON result
  - transport error details on failure

Architectural cautions:

- builder must not embed runtime orchestration logic
- builder must not transform the skill into an ad hoc local execution object and run it itself
- treat the execution subsystem as the only execution authority

### Milestone 2.3: Normalized Result Display And Status Handling

Objective:

- show the raw normalized execution result in the admin UI with minimal but useful status-specific framing

Likely files/modules/areas affected:

- `templates/skill_test.html`
- `static/app.js`
- `app.py`

Dependencies:

- milestone 2.2
- normalized result schema from execution subsystem

Acceptance criteria:

- builder displays raw result JSON exactly as returned
- builder also shows status-specific summaries for:
  - `completed`
  - `failed`
  - `pending_confirmation`
- builder clearly distinguishes:
  - HTTP transport errors
  - builder validation errors before submit
  - execution subsystem normalized failures
- builder shows `logs_summary` prominently
- builder shows `files` and `errors` sections without hiding raw payload

Architectural cautions:

- do not reinterpret failed/pending results into builder-specific pseudo-statuses
- do not strip fields from the normalized envelope
- keep the raw response visible for MVP verification

Minimal handling rules:

- `completed`: show raw JSON and highlight `result`, `files`, `logs_summary`
- `failed`: show raw JSON and highlight first error plus full error list
- `pending_confirmation`: show raw JSON and clearly state that builder is not resuming confirmations in MVP

### Milestone 2.4: Minimal Execution-Subsystem Dependency For Real Builder Test Runs

Objective:

- define the smallest real runtime change required so builder-managed published skills can actually be executed by the execution subsystem

Likely files/modules/areas affected:

- builder contracts only in this plan
- execution subsystem later likely touches:
  - `ragenius_execution_subsystem/src/core/skills/skill-registry.ts`
  - new builder-backed skill provider module

Dependencies:

- published-skill read contract from builder

Acceptance criteria:

- builder plan explicitly requires a minimal runtime bridge:
  - execution subsystem can resolve a published skill by `skill_id` and version from builder-managed storage or builder read APIs
- this bridge is sufficient for admin test runs only
- full replacement of in-memory sample skill loading is deferred to Phase 3

Architectural cautions:

- do not make builder send the full skill folder as an ad hoc execution payload to avoid runtime integration
- the executor should load published skill definitions through a stable builder-backed read contract, even in MVP

### Milestone 2.5: Mockable Versus Real For Phase 2

Objective:

- lock down what can remain mocked and what must be real for the builder-first MVP

Likely files/modules/areas affected:

- builder test plan and future tests
- execution subsystem provider/test seams

Dependencies:

- milestones 2.1 through 2.4

Acceptance criteria:

- real in Phase 2:
  - builder skill import
  - builder metadata/lifecycle/binding persistence
  - builder HTTP call to execution subsystem
  - execution subsystem normalized response envelope
- mockable in Phase 2:
  - external APIs used by tools
  - MCP tool discovery/provider behavior
  - RAG retrieval tool internals
  - rich execution persistence/resume flows
- conditionally real:
  - builder-backed published skill lookup in execution subsystem
  - if not implemented yet, Phase 2 cannot claim real uploaded-skill execution and must be treated as incomplete

Architectural cautions:

- do not let a mock builder client become the production integration path
- do not claim builder-first MVP success using only the hardcoded `video_director_skill`

## Phase 3: Follow-On Runtime Integration Readiness

### Milestone 3.1: Published-Skill Read Contract From Builder

Objective:

- expose a stable read contract so runtime consumers can retrieve published skill definitions and their colocated resources from builder-managed storage

Likely files/modules/areas affected:

- builder APIs in `app.py`
- new builder read-only skill serialization module

Dependencies:

- Phase 1 storage/versioning model

Acceptance criteria:

- builder exposes read-only published-skill endpoints for runtime use, for example:
  - list published skills
  - get published skill by id
  - get specific published version
  - fetch execution-ready manifest metadata
  - resolve resource paths/URIs inside the published skill folder
- response includes enough for executor loading:
  - skill id
  - version
  - enabled/published state
  - required tools
  - required permissions
  - workflow references
  - resource root reference
  - manifest checksum

Architectural cautions:

- runtime consumers must not read draft/review versions
- builder should expose published data through a read contract, not direct database coupling

### Milestone 3.2: App-Skill Binding Read Contract From Builder

Objective:

- expose a runtime-safe read contract for app-to-skill eligibility and policy lookup

Likely files/modules/areas affected:

- builder APIs in `app.py`
- `storage.py`

Dependencies:

- Phase 1 bindings model

Acceptance criteria:

- builder exposes read-only binding lookup by app id
- response includes:
  - app id
  - skill id
  - bound version
  - enabled flag
  - permission mode
  - execution policy
- executor can determine whether a requested skill is allowed for the app before execution

Architectural cautions:

- do not let runtime infer bindings from folder names or global skill registry alone
- app isolation depends on explicit binding lookup

### Milestone 3.3: Execution Subsystem Migration Off In-Memory Skills

Objective:

- prepare the execution subsystem to replace `sample-skills.ts` bootstrapping with builder-backed published skill resolution

Likely files/modules/areas affected:

- `ragenius_execution_subsystem/src/core/skills/skill-registry.ts`
- new `builder_skill_provider` or equivalent
- `src/api/routes/skills.routes.ts`
- configuration/env for builder base URL
- execution subsystem tests around skill loading and execution

Dependencies:

- milestones 3.1 and 3.2

Acceptance criteria:

- execution subsystem can list and load published skills from builder
- execution subsystem can verify app-skill binding before execution
- in-memory sample skills are retained only as local fallback/dev fixtures or removed once builder-backed loading is stable
- test execution from builder uses the same published-skill read path intended for future runtime consumers

Architectural cautions:

- do not move lifecycle or publish logic into execution subsystem
- do not bypass builder by copying skill folders into execution subsystem-owned storage

### Milestone 3.4: Explicit Pre-`ragenius_app` Deferrals

Objective:

- define what must stay out of scope until builder-skill-management and execution loading are stable

Likely files/modules/areas affected:

- planning and sequencing only

Dependencies:

- phases 1 through 3

Acceptance criteria:

- the team agrees not to start `ragenius_app` integration until:
  - builder-managed published skill retrieval is real
  - app-skill binding read contract is real
  - builder admin test path proves end-to-end execution against runtime

Architectural cautions:

- premature app integration will hide builder/runtime contract gaps and create duplicate skill ownership paths

## 3. Recommended Execution Order

1. Milestone 1.1: skill domain model and storage layout
2. Milestone 1.2: skill import/ingestion pipeline
3. Milestone 1.3: metadata extraction, lifecycle, publish validation
4. Milestone 1.4: versioning model
5. Milestone 1.5: app-skill binding model and admin UI
6. Milestone 1.6: builder skill administration pages and APIs
7. Milestone 2.1: testability rules and test input UX
8. Milestone 2.2: builder-to-execution-subsystem client
9. Milestone 2.3: normalized result display and status handling
10. Milestone 2.4: minimal execution-subsystem dependency for real builder test runs
11. Milestone 2.5: lock mockable vs real boundaries
12. Milestone 3.1: published-skill read contract
13. Milestone 3.2: app-skill binding read contract
14. Milestone 3.3: execution subsystem migration off in-memory skills
15. Milestone 3.4: hold `ragenius_app` integration until the above is stable

## 4. Explicit Do-Not-Do-This-Yet List

- do not integrate `ragenius_app` as the first consumer in this phase
- do not execute skills locally inside builder
- do not shift runtime orchestration, retries, permission enforcement, or tool execution into builder
- do not let unpublished skills be runtime-loadable
- do not couple execution subsystem directly to builder’s SQLite database
- do not bypass explicit app-skill bindings
- do not treat the current in-memory sample skill registry as the target architecture
- do not build a chat-style skill testing UI
- do not add marketplace, RBAC, approval-resume, or async job orchestration before the builder-first MVP succeeds

## 5. Open Questions / Assumptions

Open questions:

- what exact import artifact should MVP accept first:
  - zip upload only
  - or folder upload in browsers that support directory selection
- what exact manifest format should builder parse from `SKILL.md` for execution readiness:
  - frontmatter inside `SKILL.md`
  - referenced JSON/YAML manifest under `workflows/` or `schemas/`
  - or a builder-side extracted metadata record
- should binding target a pinned version only in MVP, or support “follow active version” immediately
- should builder persist admin test-run history, or is transient result display enough for the first pass
- what builder auth assumptions apply for admin-only operations in this repo’s current local runtime

Current assumptions used by this plan:

- builder active runtime remains `ragenius_builder/flask_scaffold/`
- builder continues using SQLite plus file-backed storage for MVP
- skill import MVP starts with managed skills, not workspace overrides
- builder test UI will show raw JSON response from `POST /v1/executions`
- execution subsystem will need a narrow builder-backed published-skill lookup before the builder-first MVP can be declared complete
