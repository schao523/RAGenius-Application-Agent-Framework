import { createHash } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

import { parse as parseYaml } from "yaml";

import type {
  AgentSkillCatalogCandidate,
  AgentSkillDiscoveryAdapter,
  AgentSkillDiscoveryErrorRecord,
  AgentSkillDiscoveryInput,
  AgentSkillDiscoveryResult,
  AgentSkillInspectionInput,
  AgentSkillSourceOption
} from "./agent-skill-types.js";
import {
  CodexPluginInventoryError,
  type CodexPluginInventoryEntry,
  type CodexPluginInventoryReader
} from "./codex-plugin-inventory.js";

interface CodexSkillPackage {
  plugin?: CodexPluginInventoryEntry;
  root: string;
  skillDirectory: string;
}

export interface CodexAgentSkillSourceConfig {
  display_name: string;
  discovery_mode?: "directory" | "plugin_inventory";
  path: string;
  precedence?: number;
  protected_locator_ref: string;
  runtime_target_id: string;
}

export interface CodexAgentSkillDiscoveryConfig {
  limits: {
    maxDepth: number;
    maxFileBytes: number;
    maxFiles: number;
    maxTotalBytes: number;
  };
  sourceOptions: CodexAgentSkillSourceConfig[];
}

export class CodexAgentSkillDiscoveryError extends Error {
  constructor(readonly code: string) {
    super(code);
    this.name = "CodexAgentSkillDiscoveryError";
  }
}

function isContained(root: string, candidate: string): boolean {
  const relative = path.relative(root, candidate);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function lengthPrefix(length: number): Buffer {
  const result = Buffer.alloc(8);
  result.writeBigUInt64BE(BigInt(length));
  return result;
}

function stableAgentSkillId(input: {
  runtimeTargetId: string;
  sourceId: string;
  providerSkillName: string;
}): string {
  const digest = createHash("sha256")
    .update(`codex_cli\u0000${input.runtimeTargetId}\u0000${input.sourceId}\u0000${input.providerSkillName}`)
    .digest("hex");
  return `agent_skill_${digest.slice(0, 24)}`;
}

function parseManifest(content: string): { name: string; description: string } {
  if (!content.startsWith("---\n") && !content.startsWith("---\r\n")) {
    throw new CodexAgentSkillDiscoveryError("AGENT_SKILL_MANIFEST_INVALID");
  }
  const normalized = content.replace(/\r\n/g, "\n");
  const end = normalized.indexOf("\n---\n", 4);
  if (end < 0) {
    throw new CodexAgentSkillDiscoveryError("AGENT_SKILL_MANIFEST_INVALID");
  }
  const parsed = parseYaml(normalized.slice(4, end));
  if (
    typeof parsed !== "object" ||
    parsed === null ||
    typeof parsed.name !== "string" ||
    !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(parsed.name) ||
    typeof parsed.description !== "string" ||
    !parsed.description.trim()
  ) {
    throw new CodexAgentSkillDiscoveryError("AGENT_SKILL_MANIFEST_INVALID");
  }
  return { name: parsed.name, description: parsed.description.trim() };
}

export class CodexAgentSkillDiscoveryAdapter
  implements AgentSkillDiscoveryAdapter
{
  readonly backend = "codex_cli" as const;

  constructor(
    private readonly config: CodexAgentSkillDiscoveryConfig,
    private readonly dependencies: {
      pluginInventory?: Pick<CodexPluginInventoryReader, "list">;
    } = {}
  ) {}

  sourceOptions(): AgentSkillSourceOption[] {
    return this.config.sourceOptions.map((source) => ({
      backend: this.backend,
      display_name: source.display_name,
      protected_locator_ref: source.protected_locator_ref,
      precedence: source.precedence ?? 100,
      runtime_target_id: source.runtime_target_id,
      source_kind: source.discovery_mode === "plugin_inventory"
        ? "codex_plugin_inventory"
        : "codex_directory"
    }));
  }

  async discover(input: AgentSkillDiscoveryInput): Promise<AgentSkillDiscoveryResult> {
    const source = this.source(input);
    const root = await fs.realpath(source.path);
    const errors: AgentSkillDiscoveryErrorRecord[] = [];
    let packages: CodexSkillPackage[] = [];
    let complete = true;
    try {
      const discovered = source.discovery_mode === "plugin_inventory"
        ? await this.pluginPackages(source, input, errors)
        : await this.directoryPackages(root, errors);
      packages = discovered.packages;
      complete = discovered.complete;
    } catch (error) {
      complete = false;
      errors.push({
        code: error instanceof CodexPluginInventoryError
          ? error.code
          : "AGENT_SKILL_SOURCE_UNAVAILABLE",
        message: "Codex skill source inventory is unavailable."
      });
    }

    const discoveredAt = new Date().toISOString();
    const items: AgentSkillCatalogCandidate[] = [];
    for (const skillPackage of packages) {
      try {
        items.push(await this.inspectDirectory({
          discoveredAt,
          input,
          ...(skillPackage.plugin ? { plugin: skillPackage.plugin } : {}),
          root: skillPackage.root,
          skillDirectory: skillPackage.skillDirectory,
          source
        }));
      } catch (error) {
        const code = error instanceof CodexAgentSkillDiscoveryError
          ? error.code
          : "AGENT_SKILL_MANIFEST_INVALID";
        const providerSkillName = await this.manifestNameOrDirectory(
          skillPackage.skillDirectory
        );
        const providerSkillReference = skillPackage.plugin
          ? `${skillPackage.plugin.name}:${providerSkillName}`
          : providerSkillName;
        errors.push({
          code,
          message: "Codex skill could not be inspected.",
          provider_skill_name: providerSkillName
        });
        items.push(this.invalidCandidate({
          discoveredAt,
          input,
          ...(skillPackage.plugin ? { plugin: skillPackage.plugin } : {}),
          providerSkillName,
          providerSkillReference,
          source
        }));
      }
    }

    const counts = new Map<string, number>();
    for (const item of items) {
      counts.set(
        item.provider_skill_reference,
        (counts.get(item.provider_skill_reference) ?? 0) + 1
      );
    }
    const normalized = items.map((item) =>
      (counts.get(item.provider_skill_reference) ?? 0) > 1
        ? { ...item, discovery_status: "invalid" as const }
        : item
    );
    for (const [providerSkillReference, count] of counts) {
      if (count > 1) {
        errors.push({
          code: "AGENT_SKILL_NAME_COLLISION",
          message: "Multiple Codex skills declared the same canonical reference.",
          provider_skill_name: providerSkillReference
        });
      }
    }

    return {
      backend: this.backend,
      complete,
      discovered_at: discoveredAt,
      errors,
      items: normalized,
      runtime_target_id: input.runtime_target_id,
      source_id: input.source_id
    };
  }

  async inspect(input: AgentSkillInspectionInput): Promise<AgentSkillCatalogCandidate> {
    const result = await this.discover(input);
    const item = result.items.find((candidate) =>
      candidate.provider_skill_name === input.provider_skill_name &&
      candidate.provider_skill_reference ===
        (input.provider_skill_reference ?? input.provider_skill_name) &&
      candidate.discovery_status === "available"
    );
    if (item) return item;
    const containmentError = result.errors.find((error) =>
      error.code === "AGENT_SKILL_SOURCE_NOT_ALLOWED"
    );
    if (containmentError) {
      throw new CodexAgentSkillDiscoveryError(containmentError.code);
    }
    const inspectionError = result.errors.find((error) =>
      error.provider_skill_name === input.provider_skill_name
    );
    if (inspectionError) {
      throw new CodexAgentSkillDiscoveryError(inspectionError.code);
    }
    throw new CodexAgentSkillDiscoveryError("AGENT_SKILL_NOT_FOUND");
  }

  private source(input: AgentSkillDiscoveryInput): CodexAgentSkillSourceConfig {
    const source = this.config.sourceOptions.find((candidate) =>
      candidate.protected_locator_ref === input.protected_locator_ref &&
      candidate.runtime_target_id === input.runtime_target_id
    );
    if (!source) {
      throw new CodexAgentSkillDiscoveryError("AGENT_SKILL_SOURCE_NOT_ALLOWED");
    }
    return source;
  }

  private async directoryPackages(
    root: string,
    errors: AgentSkillDiscoveryErrorRecord[]
  ): Promise<{ complete: boolean; packages: CodexSkillPackage[] }> {
    const walked = await this.walkSkillDirectories(root, errors);
    return {
      complete: walked.complete,
      packages: walked.skillDirectories.map((skillDirectory) => ({
        root,
        skillDirectory
      }))
    };
  }

  private async pluginPackages(
    source: CodexAgentSkillSourceConfig,
    input: AgentSkillDiscoveryInput,
    errors: AgentSkillDiscoveryErrorRecord[]
  ): Promise<{ complete: boolean; packages: CodexSkillPackage[] }> {
    if (!this.dependencies.pluginInventory) {
      throw new CodexPluginInventoryError(
        "AGENT_SKILL_PLUGIN_INVENTORY_INVALID"
      );
    }
    const configuredRoots: Array<{
      canonicalRoot: string;
      source: CodexAgentSkillSourceConfig;
    }> = [];
    for (const candidate of this.config.sourceOptions) {
      if (
        candidate.discovery_mode !== "plugin_inventory" ||
        candidate.runtime_target_id !== input.runtime_target_id
      ) {
        continue;
      }
      configuredRoots.push({
        canonicalRoot: await fs.realpath(candidate.path),
        source: candidate
      });
    }

    const packages: CodexSkillPackage[] = [];
    let complete = true;
    for (const plugin of await this.dependencies.pluginInventory.list()) {
      let pluginRoot: string;
      try {
        pluginRoot = await fs.realpath(plugin.source_path);
      } catch {
        complete = false;
        errors.push({
          code: "AGENT_SKILL_SOURCE_UNAVAILABLE",
          message: "A Codex plugin source is unavailable.",
          provider_skill_name: plugin.name
        });
        continue;
      }
      const matches = configuredRoots.filter((candidate) =>
        isContained(candidate.canonicalRoot, pluginRoot)
      );
      if (matches.length === 0) {
        errors.push({
          code: "AGENT_SKILL_SOURCE_NOT_ALLOWED",
          message: "A Codex plugin is outside configured sources.",
          provider_skill_name: plugin.name
        });
        continue;
      }
      const minimumPrecedence = Math.min(
        ...matches.map((candidate) => candidate.source.precedence ?? 100)
      );
      const winners = matches.filter((candidate) =>
        (candidate.source.precedence ?? 100) === minimumPrecedence
      );
      if (winners.length !== 1) {
        errors.push({
          code: "AGENT_SKILL_SOURCE_AMBIGUOUS",
          message: "A Codex plugin matches equal-precedence configured sources.",
          provider_skill_name: plugin.name
        });
        continue;
      }
      if (winners[0]?.source.protected_locator_ref !== source.protected_locator_ref) {
        continue;
      }
      const walked = await this.walkSkillDirectories(pluginRoot, errors);
      complete = complete && walked.complete;
      packages.push(...walked.skillDirectories.map((skillDirectory) => ({
        plugin,
        root: pluginRoot,
        skillDirectory
      })));
    }
    return { complete, packages };
  }

  private async walkSkillDirectories(
    root: string,
    errors: AgentSkillDiscoveryErrorRecord[]
  ): Promise<{ complete: boolean; skillDirectories: string[] }> {
    let complete = true;
    const skillDirectories: string[] = [];
    const walk = async (directory: string, depth: number): Promise<void> => {
      if (depth > this.config.limits.maxDepth) {
        complete = false;
        errors.push({
          code: "AGENT_SKILL_DEPTH_LIMIT",
          message: "Configured Codex skill discovery depth was exceeded."
        });
        return;
      }
      const entries = await fs.readdir(directory, { withFileTypes: true });
      for (const entry of entries) {
        const candidate = path.join(directory, entry.name);
        if (entry.isSymbolicLink()) {
          const resolved = await fs.realpath(candidate);
          if (!isContained(root, resolved)) {
            complete = false;
            errors.push({
              code: "AGENT_SKILL_SOURCE_NOT_ALLOWED",
              message: "A linked Codex skill path escaped its configured source."
            });
          }
          continue;
        }
        if (entry.isDirectory()) {
          await walk(candidate, depth + 1);
        } else if (entry.isFile() && entry.name === "SKILL.md") {
          skillDirectories.push(directory);
        }
      }
    };
    await walk(root, 0);
    return { complete, skillDirectories };
  }

  private async inspectDirectory(input: {
    discoveredAt: string;
    input: AgentSkillDiscoveryInput;
    plugin?: CodexPluginInventoryEntry;
    root: string;
    skillDirectory: string;
    source: CodexAgentSkillSourceConfig;
  }): Promise<AgentSkillCatalogCandidate> {
    const canonicalDirectory = await fs.realpath(input.skillDirectory);
    if (!isContained(input.root, canonicalDirectory)) {
      throw new CodexAgentSkillDiscoveryError("AGENT_SKILL_SOURCE_NOT_ALLOWED");
    }
    const manifestPath = path.join(canonicalDirectory, "SKILL.md");
    const manifestStat = await fs.stat(manifestPath);
    if (manifestStat.size > this.config.limits.maxFileBytes) {
      throw new CodexAgentSkillDiscoveryError("AGENT_SKILL_FILE_BYTES_LIMIT");
    }
    const manifest = parseManifest(await fs.readFile(manifestPath, "utf8"));
    const providerSkillReference = input.plugin
      ? `${input.plugin.name}:${manifest.name}`
      : manifest.name;
    const contentFingerprint = await this.fingerprintDirectory(
      input.root,
      canonicalDirectory
    );
    return {
      agent_skill_id: stableAgentSkillId({
        providerSkillName: providerSkillReference,
        runtimeTargetId: input.input.runtime_target_id,
        sourceId: input.input.source_id
      }),
      backend: this.backend,
      content_fingerprint: contentFingerprint,
      description: manifest.description,
      direct_tool_dispatch: false,
      discovered_at: input.discoveredAt,
      discovery_status: "available",
      display_name: manifest.name,
      last_seen_at: input.discoveredAt,
      missing_requirements: { bins: [], config: [], env: [], os: [] },
      model_visible: true,
      provider_metadata: input.plugin ? {
        plugin_id: input.plugin.plugin_id,
        plugin_name: input.plugin.name,
        ...(input.plugin.marketplace_name
          ? { marketplace_name: input.plugin.marketplace_name }
          : {}),
        ...(input.plugin.version ? { version: input.plugin.version } : {})
      } : {},
      provider_skill_name: manifest.name,
      provider_skill_reference: providerSkillReference,
      runtime_target_id: input.input.runtime_target_id,
      source_id: input.input.source_id,
      source_kind: input.plugin
        ? "codex_plugin_inventory"
        : "codex_directory",
      source_label: input.source.display_name,
      user_invocable: true
    };
  }

  private async manifestNameOrDirectory(skillDirectory: string): Promise<string> {
    try {
      const manifestPath = path.join(skillDirectory, "SKILL.md");
      const stat = await fs.stat(manifestPath);
      if (stat.size > this.config.limits.maxFileBytes) {
        return path.basename(skillDirectory);
      }
      return parseManifest(await fs.readFile(manifestPath, "utf8")).name;
    } catch {
      return path.basename(skillDirectory);
    }
  }

  private invalidCandidate(input: {
    discoveredAt: string;
    input: AgentSkillDiscoveryInput;
    plugin?: CodexPluginInventoryEntry;
    providerSkillName: string;
    providerSkillReference: string;
    source: CodexAgentSkillSourceConfig;
  }): AgentSkillCatalogCandidate {
    return {
      agent_skill_id: stableAgentSkillId({
        providerSkillName: input.providerSkillReference,
        runtimeTargetId: input.input.runtime_target_id,
        sourceId: input.input.source_id
      }),
      backend: this.backend,
      content_fingerprint: "",
      description: "",
      direct_tool_dispatch: false,
      discovered_at: input.discoveredAt,
      discovery_status: "invalid",
      display_name: input.providerSkillName,
      last_seen_at: input.discoveredAt,
      missing_requirements: { bins: [], config: [], env: [], os: [] },
      model_visible: false,
      provider_metadata: input.plugin ? {
        plugin_id: input.plugin.plugin_id,
        plugin_name: input.plugin.name
      } : {},
      provider_skill_name: input.providerSkillName,
      provider_skill_reference: input.providerSkillReference,
      runtime_target_id: input.input.runtime_target_id,
      source_id: input.input.source_id,
      source_kind: input.plugin
        ? "codex_plugin_inventory"
        : "codex_directory",
      source_label: input.source.display_name,
      user_invocable: false
    };
  }

  private async fingerprintDirectory(root: string, skillRoot: string): Promise<string> {
    const files: Array<{ bytes: Buffer; relativePath: string }> = [];
    let totalBytes = 0;

    const walk = async (directory: string, depth: number): Promise<void> => {
      if (depth > this.config.limits.maxDepth) {
        throw new CodexAgentSkillDiscoveryError("AGENT_SKILL_DEPTH_LIMIT");
      }
      const entries = await fs.readdir(directory, { withFileTypes: true });
      for (const entry of entries) {
        const candidate = path.join(directory, entry.name);
        const stat = await fs.lstat(candidate);
        if (stat.isSymbolicLink()) {
          throw new CodexAgentSkillDiscoveryError("AGENT_SKILL_SOURCE_NOT_ALLOWED");
        }
        const resolved = await fs.realpath(candidate);
        if (!isContained(root, resolved)) {
          throw new CodexAgentSkillDiscoveryError("AGENT_SKILL_SOURCE_NOT_ALLOWED");
        }
        if (stat.isDirectory()) {
          await walk(candidate, depth + 1);
          continue;
        }
        if (!stat.isFile()) continue;
        if (stat.size > this.config.limits.maxFileBytes) {
          throw new CodexAgentSkillDiscoveryError("AGENT_SKILL_FILE_BYTES_LIMIT");
        }
        if (files.length + 1 > this.config.limits.maxFiles) {
          throw new CodexAgentSkillDiscoveryError("AGENT_SKILL_FILE_COUNT_LIMIT");
        }
        totalBytes += stat.size;
        if (totalBytes > this.config.limits.maxTotalBytes) {
          throw new CodexAgentSkillDiscoveryError("AGENT_SKILL_TOTAL_BYTES_LIMIT");
        }
        files.push({
          bytes: await fs.readFile(candidate),
          relativePath: path.relative(skillRoot, candidate).split(path.sep).join("/")
        });
      }
    };
    await walk(skillRoot, 0);
    files.sort((left, right) => left.relativePath.localeCompare(right.relativePath));
    const hash = createHash("sha256");
    for (const file of files) {
      const pathBytes = Buffer.from(file.relativePath, "utf8");
      hash.update(lengthPrefix(pathBytes.length));
      hash.update(pathBytes);
      hash.update(lengthPrefix(file.bytes.length));
      hash.update(file.bytes);
    }
    return `sha256:v1:${hash.digest("hex")}`;
  }
}
