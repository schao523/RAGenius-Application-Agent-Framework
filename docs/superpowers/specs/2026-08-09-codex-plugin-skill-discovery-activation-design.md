# Codex Plugin Skill Discovery and Activation Design

Date: 2026-08-09
Status: Approved for implementation planning

## Purpose

Extend the existing Agent skill discovery and selection flow so RAGenius can
discover administrator-allowed Codex plugin skills and invoke them through the
canonical namespaced Codex reference. This design preserves the existing
Builder approval model, synchronized trusted read model, execution-subsystem
ownership, and app-facing `agent_skill_id` selection flow.

The feature does not install, update, enable, or disable Codex plugins. It only
discovers enabled plugins already visible to the configured Codex runtime.

## Verified Provider Behavior

Codex CLI 0.146.0 was tested with the installed plugin skill
`superpowers:systematic-debugging`.

- `$superpowers:systematic-debugging <request>` resolved the selected skill
  without a shell read of `SKILL.md`.
- `$systematic-debugging <request>` and ordinary prompt guidance reached the
  same skill only after the Agent located and read `SKILL.md` through a shell
  command.

RAGenius therefore uses the namespaced reference as the deterministic plugin
activation method. Unqualified references and ordinary guidance are not
automatic fallbacks for an execution.

## Trust Model

`codex plugin list --json` is an inventory input, not a trust authority.

Administrators configure one or more broad local directories that are allowed
to contain Codex plugins. For every CLI-reported plugin, execution subsystem:

1. validates the bounded JSON response;
2. requires `installed=true` and `enabled=true`;
3. resolves the reported plugin source path to its canonical filesystem path;
4. requires that path to remain inside one configured broad directory;
5. discovers and validates `SKILL.md` packages beneath the accepted plugin;
6. applies existing symlink, depth, file-count, per-file, and total-byte limits;
7. computes the content fingerprint from the complete skill package.

CLI metadata cannot authorize a path outside the configured directory. A path
that escapes through `..`, a junction, or a symbolic link is rejected after
canonicalization. Public APIs never expose configured roots or canonical
filesystem paths.

Discovery and execution must use the same configured Codex executable, Codex
home, and runtime target. A plugin discovered from one runtime profile cannot
be selected for another.

## Source Configuration

The Codex source configuration gains an explicit discovery mode:

```ts
type CodexAgentSkillSourceConfig = {
  protected_locator_ref: string;
  display_name: string;
  runtime_target_id: string;
  path: string;
  discovery_mode?: "directory" | "plugin_inventory";
};
```

`directory` preserves current standalone skill-directory behavior and is the
default for backward compatibility. `plugin_inventory` means that `path` is a
broad approved directory and eligible plugin roots are obtained from the Codex
CLI inventory, then filtered by canonical containment.

Several configured `plugin_inventory` sources may cover different approved
roots. One CLI-reported plugin must match exactly one effective source after
configured source precedence is applied. Ambiguous equal-precedence matches
fail closed.

## Canonical Skill Reference

Discovery adds a provider-native activation reference without overloading the
manifest name:

```ts
type CodexAgentSkillIdentity = {
  provider_skill_name: string;
  provider_skill_reference: string;
};
```

Examples:

```text
Standalone skill:
  provider_skill_name = research-paper-finder
  provider_skill_reference = research-paper-finder

Plugin skill:
  provider_skill_name = systematic-debugging
  provider_skill_reference = superpowers:systematic-debugging
```

The reference excludes the leading `$`; prompt construction owns provider
syntax. For a plugin, it is formed from the validated CLI `name` and the
validated `SKILL.md` frontmatter `name`. Both components must satisfy the
Codex-compatible skill-name grammar. The CLI `pluginId`, marketplace name, and
version are diagnostic metadata, not invocation syntax.

The stable logical identity becomes:

```text
(backend, runtime_target_id, source_id, provider_skill_reference)
```

This permits two plugins in one broad source to declare the same manifest name
without becoming a false collision. A collision exists only when two effective
entries produce the same canonical reference for the same runtime target.

## Data Flow

1. Builder requests discovery for an execution-configured source option.
2. Execution subsystem runs the bounded plugin inventory command once for the
   requested runtime target.
3. It filters enabled local plugins to the selected approved root.
4. It validates and fingerprints contained skills and returns catalog
   candidates containing `provider_skill_reference`.
5. Builder stores the reference with the catalog entry and includes it in
   administrator review, approval, app binding, and trusted projection data.
6. Execution subsystem atomically stores the projected reference with the
   active governance revision.
7. Selection resolves only by `agent_skill_id` or the existing controlled
   legacy path, then re-inspects the same plugin and compares identity and
   fingerprint.
8. Codex prompt construction emits `$<provider_skill_reference>` before the
   RAGenius prompt envelope.
9. Execution metadata records requested and resolved references without
   exposing source paths.

`ragenius_app_skeleton` continues to submit `agent_skill_id`; it does not build
Codex references. It may display the canonical reference supplied by the
trusted public inventory, but it cannot override it.

## Persistence and Compatibility

Add non-null `provider_skill_reference` fields to Builder catalog records and
execution-subsystem governance projections. Migrations backfill existing rows
from `provider_skill_name`, which is correct for current standalone Codex
skills and existing OpenClaw records.

Projection payloads carry the new field. During a bounded rolling upgrade,
execution subsystem may accept an omitted field and derive it from
`provider_skill_name`; newly published projections must always include it.
After rollout verification, omission can be rejected in a later contract
version.

`provider_skill_name` remains the manifest/provider display identity and is
used for filesystem inspection. `provider_skill_reference` is used for stable
selection identity, prompt activation, and activation diagnostics.

## Prompt and Evidence Behavior

For `activation_method="codex_explicit_reference"`, prompt construction emits:

```text
$superpowers:systematic-debugging
```

It must never reconstruct the reference from display text or user input.
Standalone skills continue to emit `$research-paper-finder`.

A canonical explicit reference is provider-resolved before model tool use, so
the absence of a `SKILL.md` shell-read event is not activation failure.
Activation evidence therefore distinguishes:

- `provider_reference_resolved`: an approved canonical reference was emitted
  and the Codex run accepted it;
- `process_observed`: structured events independently show the selected skill
  package being read or reported by provider metadata;
- `agent_reported`: only model-produced result content reports activation;
- `not_observed`: no acceptable evidence exists.

The evidence level is diagnostic and cannot replace pre-invocation approval,
containment, fingerprint, or binding checks.

## Failure Behavior

Plugin inventory discovery fails closed for the affected source when:

- the command times out or exits nonzero;
- stdout exceeds its configured bound;
- JSON is malformed or required fields have invalid types;
- a plugin source is non-local, missing, or outside every approved root;
- canonicalization or containment checks fail;
- plugin or skill names cannot form a valid canonical reference;
- duplicate canonical references remain after precedence resolution.

An unavailable plugin inventory does not invalidate independent standalone
`directory` sources. Previously approved plugin entries become unavailable or
missing on the next complete synchronized discovery; they cannot execute after
runtime revalidation fails.

Logs may include plugin id, namespace, version, failure code, and redacted
source label. They must not expose full protected paths through user-facing
APIs.

## Verification

Automated tests must cover:

- bounded parsing of the real CLI response shape;
- installed, enabled, disabled, unavailable, and malformed entries;
- canonical approved-root containment and junction/symlink escapes;
- broad roots containing multiple plugins;
- duplicate manifest names with distinct plugin namespaces;
- duplicate canonical references failing closed;
- standalone source backward compatibility;
- persistence migration and trusted projection compatibility;
- Builder approval and app binding of plugin skills;
- execution-time identity and fingerprint revalidation;
- namespaced Codex prompt construction;
- activation evidence when no `SKILL.md` command event occurs;
- public serialization without protected paths.

A real smoke test must run an approved namespaced plugin skill through the
production Codex executable in a read-only workspace and verify skill-specific
output. The test must also confirm that the generated prompt starts with the
exact synchronized `provider_skill_reference`.

## Out of Scope

- Plugin installation, upgrade, removal, enablement, or authentication.
- Automatic approval or app binding of newly discovered skills.
- Copying plugin skill packages into RAGenius-managed storage.
- User-configurable plugin roots.
- Automatic fallback from a namespaced reference to ordinary guidance.
- Changes to OpenClaw invocation syntax beyond schema compatibility.
