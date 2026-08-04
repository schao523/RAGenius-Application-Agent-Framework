# Runtime Tool vs Real Skill Refactor Plan

> Goal: move the product model to:
> - `@exec tool`: NotebookLM tools, Gmail/Drive/Docs/CMS tools, and selected safe local/runtime tools
> - `@exec skill`: only Builder-bound skills or true multi-step workflows
> - internal one-tool wrapper skills: retained only as execution-engine plumbing and hidden from user-facing skill inventory

## Problem Summary

The current system still leaks an internal execution pattern into the user-facing model:

- many runtime "skills" are one-tool wrappers
- these wrappers duplicate already-existing runtime tools
- `@exec skill` becomes confusing because thin wrappers look like real skills
- `@exec tool` depends on wrapper skills internally, but that internal dependency is not a good user-facing abstraction
- tool naming is inconsistent, and runtime inventory currently mixes:
  - real tools
  - internal wrapper skills
  - app-bound Builder skills

This creates the exact user confusion already observed:

- NotebookLM tool and NotebookLM "skill" feel like duplicates
- Gmail MCP tools can appear duplicated by display label
- app-scoped skill mode looks like it is "missing" runtime entries that are actually thin wrappers

## Desired End State

### User-facing model

- Tool mode shows executable runtime tools only
- Skill mode shows only:
  - Builder-bound app skills
  - explicitly allowlisted real multi-step runtime workflows

### Internal model

- one-tool wrapper runtime skills remain available to the execution engine
- tool execution may still resolve through those wrappers internally
- but wrapper skills are hidden from user-facing skill inventory

### Consequences

- runtime tool inventory becomes the primary execution surface for NotebookLM, Gmail, Drive, Docs, and CMS capabilities
- runtime skill inventory becomes a narrower surface for real workflows
- the composer no longer teaches the user the wrong mental model

---

## Classification Model

Add an explicit classification split in `ragenius_execution_subsystem`.

### User-facing runtime tools

Expose as `@exec tool`:

- NotebookLM:
  - `adapter.notebooklm.list_notebooks`
  - `adapter.notebooklm.list_sources`
  - `adapter.notebooklm.ask`
  - `adapter.notebooklm.poll_artifact_task`
  - `adapter.notebooklm.add_source_text`
  - `adapter.notebooklm.add_source_url`
  - `adapter.notebooklm.add_source_file`
  - `adapter.notebooklm.generate_report`
  - `adapter.notebooklm.generate_slide_deck`
  - `adapter.notebooklm.generate_video`
- Gmail / Drive / Docs / CMS:
  - `mcp.cms.search_pages`
  - `mcp.cms.create_page`
  - `mcp.gmail.search_messages`
  - `mcp.gmail.create_draft`
  - `mcp.gmail.create_draft_with_attachments`
  - `mcp.gmail.send_draft`
  - `mcp.gmail.send_message`
  - `mcp.gdocs.search_documents`
  - `mcp.gdrive.search_files`
  - `mcp.gdrive.download_file_content`
- selected safe local/runtime tools only when explicitly approved for user-facing execution

### User-facing skills

Expose as `@exec skill`:

- Builder-bound skills for the current app
- real multi-step runtime workflows only if intentionally allowlisted

Initial expected runtime skill allowlist:

- `video_director_skill` only if kept as a real workflow
- possibly `google_drive_download_file` only if deliberately presented as a workflow rather than a raw tool

Everything else in the current 25-entry runtime skill inventory should be treated as internal plumbing unless explicitly promoted.

### Internal wrapper skills

Keep internal, hide from skill mode:

- `notebooklm_list_notebooks`
- `notebooklm_list_sources`
- `notebooklm_existing_notebook_ask`
- `notebooklm_add_source_text`
- `notebooklm_add_source_url`
- `notebooklm_add_source_file`
- `notebooklm_generate_report`
- `notebooklm_generate_slide_deck`
- `notebooklm_generate_video`
- `notebooklm_poll_artifact_task`
- `mcp_page_search`
- `mcp_page_create`
- `gmail_message_search`
- `gmail_create_draft`
- `gmail_create_draft_with_attachments`
- `gmail_send_draft`
- `gmail_send_message`
- `google_docs_search`
- `google_drive_search`
- `google_drive_download_file`

---

## Refactor Scope

## `ragenius_execution_subsystem`

### 1. Add explicit inventory classification metadata

**Files**
- `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\api\routes\tools.routes.ts`
- `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\skills\skill.types.ts`
- `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\skills\sample-skills.ts`

Add metadata fields that separate:

- `inventory_visibility`: `user_tool` | `user_skill` | `internal_wrapper`
- `user_facing`: boolean
- `workflow_kind`: `single_tool_wrapper` | `multi_step_workflow` | `builder_bound`

Recommended implementation:

- extend runtime skill definitions with optional metadata:
  - `inventoryVisibility`
  - `workflowKind`
- default all existing sample wrapper skills to:
  - `inventoryVisibility = "internal_wrapper"`
  - `workflowKind = "single_tool_wrapper"`
- explicitly mark genuine multi-step workflows as:
  - `inventoryVisibility = "user_skill"`
  - `workflowKind = "multi_step_workflow"`

### 2. Improve tool inventory labels and descriptions

**Files**
- `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\api\routes\tools.routes.ts`

Tool inventory should return distinct display labels, especially for MCP tools where remote names are too generic.

Examples:

- `mcp.gmail.create_draft` -> `Gmail Create Draft`
- `mcp.gmail.create_draft_with_attachments` -> `Gmail Create Draft With Attachments`
- `mcp.gmail.send_draft` -> `Gmail Send Draft`
- `mcp.gmail.send_message` -> `Gmail Send Message`
- `mcp.gdocs.search_documents` -> `Google Docs Search`
- `mcp.gdrive.search_files` -> `Google Drive Search`
- `mcp.gdrive.download_file_content` -> `Google Drive Download File`
- `mcp.cms.search_pages` -> `CMS Page Search`
- `mcp.cms.create_page` -> `CMS Page Create`

Recommended approach:

- add a small display-name normalization helper in `tools.routes.ts`
- prefer explicit normalized labels over raw remote MCP tool names

### 3. Split skill inventory into user-facing vs internal

**Files**
- `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\api\routes\tools.routes.ts`

Keep `/v1/skills/inventory` for full internal/debug inventory if needed, but add one of:

- `/v1/skills/user-inventory`
- or a query param like `/v1/skills/inventory?visibility=user`

Recommended behavior:

- default user-facing inventory should exclude `internal_wrapper`
- optional debug inventory may still expose everything

This gives the app a clean source of truth and avoids duplicating filtering rules in Python.

### 4. Keep tool inventory as the primary runtime execution surface

**Files**
- `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\api\routes\tools.routes.ts`

Ensure `/v1/tools/inventory` remains:

- runtime-scoped
- user-facing
- fully schema-serialized
- clearly labeled
- risk-tagged

### 5. Preserve internal wrapper execution mapping

**Files**
- `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\skills\sample-skills.ts`
- possibly `D:\GitHub\Codex-RAGenius-System\ragenius_execution_subsystem\src\core\skills\skill-registry.ts`

Do not remove wrapper skills yet.

They are still useful because:

- the execution engine executes skills, not raw tools
- tool mode in the app currently resolves a tool to a one-tool wrapper skill

This means the refactor is a user-facing inventory cleanup first, not an engine rewrite.

---

## `ragenius_app_skeleton`

### 1. Use runtime tool inventory as-is for tool mode

**Files**
- `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py`
- `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\execution_subsystem_client.py`

Tool mode should keep using:

- `/exec/tools` -> runtime tool inventory

But `/exec/tools` should be sourced from:

- user-facing runtime tool inventory only
- not from any app-bound or Builder-bound notion

### 2. Change skill mode to show only Builder-bound skills plus allowlisted real workflows

**Files**
- `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py`

Current behavior:

- `/exec/skills?app_id=...` returns only Builder-bound skills

Recommended end-state:

- keep Builder-bound skills as the default for app skill mode
- optionally merge in a tiny allowlist of user-facing runtime workflows from `3001`
- do not merge internal wrapper runtime skills

Recommended helper split:

- `_builder_bound_skill_inventory_items(app_id)`
- `_user_facing_runtime_skill_inventory_items()`
- `_exec_skill_inventory_items(app_id)` returns:
  - Builder-bound app skills
  - optional user-facing runtime workflows

Do not use `_combined_skill_inventory_items` for user-facing skill mode anymore.

### 3. Keep tool-to-wrapper resolution internal

**Files**
- `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\backend\app\main.py`

Keep:

- `_resolve_runtime_exec_skill_for_tool(...)`

But treat it as internal plumbing only.

Do not let that mapping determine what users think is a skill.

### 4. Improve tool label normalization in the composer payload

**Files**
- `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ExecutionComposer.jsx`

The frontend should trust normalized display names from the backend, but still allow a final fallback:

- prefer `display_name`
- then `name`
- then `tool_id` / `skill_id`

### 5. Add explicit inventory-source labeling in UI

**Files**
- `D:\GitHub\Codex-RAGenius-System\ragenius_app_skeleton\frontend\src\components\ExecutionComposer.jsx`

Show:

- `Tool` mode: runtime tool / provider
- `Skill` mode: Builder-bound skill / workflow

Avoid showing internal wrapper ids as if they are user-facing skills.

### 6. Add a small note in skill mode

Skill mode should explain:

- only app-bound skills and true workflows appear here

This prevents users from interpreting hidden wrapper skills as missing data.

---

## Exact Code Changes

### `ragenius_execution_subsystem`

1. `src/core/skills/skill.types.ts`
- add optional metadata fields for visibility and workflow kind

2. `src/core/skills/sample-skills.ts`
- annotate each runtime skill:
  - NotebookLM wrapper skills -> `internal_wrapper`
  - Gmail/Drive/Docs/CMS wrapper skills -> `internal_wrapper`
  - true workflow skills -> `user_skill`

3. `src/api/routes/tools.routes.ts`
- add:
  - display-name normalization helper for tools
  - user-facing skill filtering helper
  - enriched inventory metadata:
    - `display_name`
    - `inventory_visibility`
    - `workflow_kind`
- expose:
  - user-facing tool inventory
  - user-facing skill inventory
  - optional full/debug inventory if still needed

4. `tests/execution/execute-skill.test.ts`
- add assertions that:
  - Gmail draft tools have distinct labels
  - user-facing skill inventory excludes internal wrapper skills
  - tool inventory still includes NotebookLM and Gmail/Drive/Docs/CMS runtime tools

### `ragenius_app_skeleton`

1. `backend/app/execution_subsystem_client.py`
- optionally add:
  - `get_user_skill_inventory()` if `3001` gets a dedicated route

2. `backend/app/main.py`
- split user-facing skill inventory from runtime wrapper inventory
- stop treating internal runtime wrappers as app skill-mode candidates
- keep tool mode runtime-scoped and user-facing

3. `frontend/src/components/ExecutionComposer.jsx`
- use `display_name` if present
- keep current required/optional field UX
- add a short skill-mode explanation

4. `frontend/src/App.jsx`
- no conceptual change to routing
- only inventory-source and mode labeling cleanup if needed

5. tests
- `backend/tests/test_chat_exec_routing.py`
- `frontend/src/components/ExecutionComposer.test.jsx`
- add assertions for:
  - distinct Gmail tool labels
  - absence of internal wrapper skills from skill mode
  - presence of NotebookLM/Gmail/Drive/Docs/CMS runtime tools in tool mode

---

## Migration Sequence

### Phase 1
- fix inventory classification metadata in `3001`
- fix tool display labels
- add user-facing skill filtering in `3001`

### Phase 2
- update `8012` to consume user-facing inventories correctly
- keep tool execution routing unchanged internally

### Phase 3
- update composer labels/help text
- verify:
  - tool mode contains NotebookLM + Gmail/Drive/Docs/CMS runtime tools
  - skill mode contains only Builder-bound skills and true workflows

### Phase 4
- optional cleanup:
  - reduce or hide debug/internal inventory endpoints from normal app usage
  - document wrapper-skill plumbing clearly for maintainers

---

## Verification Checklist

After implementation:

1. `3001 /v1/tools/inventory`
- contains NotebookLM + Gmail/Drive/Docs/CMS runtime tools
- shows distinct Gmail draft labels
- returns usable JSON Schema for each tool

2. `3001` user-facing skill inventory
- excludes NotebookLM/Gmail/Drive wrapper skills
- includes only true workflows

3. `8012 /exec/tools`
- shows all user-facing runtime tools

4. `8012 /exec/skills?app_id=...`
- shows only Builder-bound app skills plus intentionally allowlisted workflows

5. Composer UX
- tool mode does not show duplicated generic names like `create_draft`
- skill mode does not appear to be missing thin wrapper entries, because they are no longer presented as skills

---

## Risks

- If wrapper skills are hidden too early without preserving tool-to-wrapper resolution, `@exec tool` will break.
- If user-facing skill filtering is implemented only in `8012` and not `3001`, inventory semantics will remain fragmented.
- If tool display-name normalization stays app-side only, other consumers of `3001` will continue seeing confusing duplicates.

The safest design is:

- inventory classification and label normalization in `3001`
- app-mode presentation and Builder scoping in `8012`

