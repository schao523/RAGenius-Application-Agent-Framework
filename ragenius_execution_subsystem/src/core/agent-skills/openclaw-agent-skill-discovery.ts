import { createHash } from "node:crypto";
import path from "node:path";

import { z } from "zod";

import { runSupervisedProcess } from "../../../scripts/agent_process_supervisor.js";
import type {
  AgentSkillCatalogCandidate,
  AgentSkillDiscoveryAdapter,
  AgentSkillDiscoveryInput,
  AgentSkillDiscoveryResult,
  AgentSkillInspectionInput,
  AgentSkillSourceOption
} from "./agent-skill-types.js";

export interface OpenClawAgentSkillTargetConfig {
  agent_id: string;
  display_name: string;
  protected_locator_ref: string;
  runtime_target_id: string;
  skill_roots: string[];
  wsl_distro: string;
}

export interface OpenClawAgentSkillDiscoveryConfig {
  command: string;
  limits: {
    maxDepth: number;
    maxFileBytes: number;
    maxFiles: number;
    maxTotalBytes: number;
  };
  maxStderrBytes: number;
  maxStdoutBytes: number;
  targets: OpenClawAgentSkillTargetConfig[];
  timeoutMs: number;
}

export interface OpenClawDiscoveryRunResult {
  exitCode: number | null;
  stderr: string;
  stdout: string;
  timedOut: boolean;
}

export interface OpenClawAgentSkillDiscoveryDependencies {
  run?: (input: {
    args: string[];
    command: "wsl";
    maxStderrBytes: number;
    maxStdoutBytes: number;
    timeoutMs: number;
  }) => Promise<OpenClawDiscoveryRunResult>;
}

export class OpenClawAgentSkillDiscoveryError extends Error {
  constructor(readonly code: string) {
    super(code);
    this.name = "OpenClawAgentSkillDiscoveryError";
  }
}

const missingSchema = z.object({
  anyBins: z.array(z.string()).default([]),
  bins: z.array(z.string()).default([]),
  config: z.array(z.string()).default([]),
  env: z.array(z.string()).default([]),
  os: z.array(z.string()).default([])
}).passthrough();

const inventorySkillSchema = z.object({
  bundled: z.boolean().default(false),
  commandVisible: z.boolean().default(false),
  description: z.string().default(""),
  directToolDispatch: z.boolean().optional(),
  direct_tool_dispatch: z.boolean().optional(),
  disabled: z.boolean().default(false),
  eligible: z.boolean().default(false),
  missing: missingSchema.default({}),
  modelVisible: z.boolean().default(false),
  name: z.string().trim().min(1),
  source: z.string().default("openclaw"),
  userInvocable: z.boolean().default(false)
}).passthrough();

const inventorySchema = z.object({
  skills: z.array(inventorySkillSchema)
}).passthrough();

const infoSchema = z.object({
  baseDir: z.string().min(1),
  filePath: z.string().min(1),
  name: z.string().min(1)
}).passthrough();

const inspectionSchema = z.object({
  content_fingerprint: z.string().regex(/^sha256:v1:[a-f0-9]{64}$/),
  file_count: z.number().int().nonnegative(),
  total_bytes: z.number().int().nonnegative()
}).strict();

const OPENCLAW_SKILL_INSPECTION_SCRIPT = String.raw`
import hashlib, json, os, struct, sys

base_dir = os.path.realpath(sys.argv[1])
roots = [os.path.realpath(value) for value in json.loads(sys.argv[2])]
max_depth, max_files, max_file_bytes, max_total_bytes = map(int, sys.argv[3:7])

def contained(root, candidate):
    try:
        return os.path.commonpath([root, candidate]) == root
    except ValueError:
        return False

if not any(contained(root, base_dir) for root in roots):
    print("AGENT_SKILL_SOURCE_NOT_ALLOWED", file=sys.stderr)
    raise SystemExit(73)

files = []
total_bytes = 0
for current, directories, names in os.walk(base_dir, topdown=True, followlinks=False):
    relative_dir = os.path.relpath(current, base_dir)
    depth = 0 if relative_dir == "." else len(relative_dir.split(os.sep))
    if depth > max_depth:
        print("AGENT_SKILL_DEPTH_LIMIT", file=sys.stderr)
        raise SystemExit(73)
    for directory in list(directories):
        candidate = os.path.join(current, directory)
        if os.path.islink(candidate):
            print("AGENT_SKILL_SOURCE_NOT_ALLOWED", file=sys.stderr)
            raise SystemExit(73)
        if directory in {".git", "node_modules", "__pycache__"}:
            directories.remove(directory)
    for name in names:
        candidate = os.path.join(current, name)
        if os.path.islink(candidate):
            print("AGENT_SKILL_SOURCE_NOT_ALLOWED", file=sys.stderr)
            raise SystemExit(73)
        resolved = os.path.realpath(candidate)
        if not any(contained(root, resolved) for root in roots):
            print("AGENT_SKILL_SOURCE_NOT_ALLOWED", file=sys.stderr)
            raise SystemExit(73)
        if name.endswith((".lock", ".tmp")) or not os.path.isfile(candidate):
            continue
        size = os.path.getsize(candidate)
        if size > max_file_bytes:
            print("AGENT_SKILL_FILE_BYTES_LIMIT", file=sys.stderr)
            raise SystemExit(73)
        if len(files) + 1 > max_files:
            print("AGENT_SKILL_FILE_COUNT_LIMIT", file=sys.stderr)
            raise SystemExit(73)
        total_bytes += size
        if total_bytes > max_total_bytes:
            print("AGENT_SKILL_TOTAL_BYTES_LIMIT", file=sys.stderr)
            raise SystemExit(73)
        relative = os.path.relpath(candidate, base_dir).replace(os.sep, "/")
        files.append((relative, candidate, size))

digest = hashlib.sha256()
for relative, candidate, size in sorted(files):
    path_bytes = relative.encode("utf-8")
    digest.update(struct.pack(">Q", len(path_bytes)))
    digest.update(path_bytes)
    digest.update(struct.pack(">Q", size))
    with open(candidate, "rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)

print(json.dumps({
    "content_fingerprint": "sha256:v1:" + digest.hexdigest(),
    "file_count": len(files),
    "total_bytes": total_bytes
}))
`;

function stableId(input: {
  providerSkillName: string;
  runtimeTargetId: string;
  sourceId: string;
}): string {
  const digest = createHash("sha256")
    .update(`openclaw_cli\u0000${input.runtimeTargetId}\u0000${input.sourceId}\u0000${input.providerSkillName}`)
    .digest("hex");
  return `agent_skill_${digest.slice(0, 24)}`;
}

function lexicalContained(roots: string[], candidate: string): boolean {
  return roots.some((root) => {
    const relative = path.posix.relative(root, candidate);
    return relative === "" || (!relative.startsWith("..") && !path.posix.isAbsolute(relative));
  });
}

async function mapWithConcurrency<T, R>(
  items: T[],
  concurrency: number,
  mapper: (item: T) => Promise<R>
): Promise<R[]> {
  const results = new Array<R>(items.length);
  let nextIndex = 0;
  const workers = Array.from(
    { length: Math.min(concurrency, items.length) },
    async () => {
      while (nextIndex < items.length) {
        const index = nextIndex;
        nextIndex += 1;
        results[index] = await mapper(items[index]!);
      }
    }
  );
  await Promise.all(workers);
  return results;
}

export class OpenClawAgentSkillDiscoveryAdapter
  implements AgentSkillDiscoveryAdapter
{
  readonly backend = "openclaw_cli" as const;

  constructor(
    private readonly config: OpenClawAgentSkillDiscoveryConfig,
    private readonly dependencies: OpenClawAgentSkillDiscoveryDependencies = {}
  ) {}

  sourceOptions(): AgentSkillSourceOption[] {
    return this.config.targets.map((target) => ({
      backend: this.backend,
      display_name: target.display_name,
      protected_locator_ref: target.protected_locator_ref,
      runtime_target_id: target.runtime_target_id,
      source_kind: "openclaw_agent_inventory"
    }));
  }

  async discover(input: AgentSkillDiscoveryInput): Promise<AgentSkillDiscoveryResult> {
    const target = this.target(input);
    const inventory = await this.inventory(target);
    const discoveredAt = new Date().toISOString();
    const items: AgentSkillCatalogCandidate[] = [];
    const errors: AgentSkillDiscoveryResult["errors"] = [];
    const inspected = await mapWithConcurrency(inventory.skills, 4, async (skill) => {
      try {
        return {
          item: await this.inspectSkill({ discoveredAt, input, skill, target })
        };
      } catch (error) {
        const code = error instanceof OpenClawAgentSkillDiscoveryError
          ? error.code
          : "OPENCLAW_SKILL_INSPECTION_FAILED";
        return {
          error: {
            code,
            message: "OpenClaw skill package could not be inspected.",
            provider_skill_name: skill.name
          },
          item: this.candidate({
            contentFingerprint: "",
            discoveredAt,
            input,
            skill,
            status: "invalid",
            target
          })
        };
      }
    });
    for (const result of inspected) {
      items.push(result.item);
      if (result.error) errors.push(result.error);
    }
    return {
      backend: this.backend,
      complete: true,
      discovered_at: discoveredAt,
      errors,
      items,
      runtime_target_id: input.runtime_target_id,
      source_id: input.source_id
    };
  }

  async inspect(input: AgentSkillInspectionInput): Promise<AgentSkillCatalogCandidate> {
    const target = this.target(input);
    const inventory = await this.inventory(target);
    const skill = inventory.skills.find((candidate) => candidate.name === input.provider_skill_name);
    if (!skill) {
      throw new OpenClawAgentSkillDiscoveryError("AGENT_SKILL_NOT_FOUND");
    }
    return this.inspectSkill({
      discoveredAt: new Date().toISOString(),
      input,
      skill,
      target
    });
  }

  private target(input: AgentSkillDiscoveryInput): OpenClawAgentSkillTargetConfig {
    const target = this.config.targets.find((candidate) =>
      candidate.protected_locator_ref === input.protected_locator_ref &&
      candidate.runtime_target_id === input.runtime_target_id
    );
    if (!target) {
      throw new OpenClawAgentSkillDiscoveryError("AGENT_SKILL_SOURCE_NOT_ALLOWED");
    }
    return target;
  }

  private async inventory(target: OpenClawAgentSkillTargetConfig) {
    const result = await this.run([
      "-d", target.wsl_distro, "--exec", this.config.command,
      "skills", "list", "--agent", target.agent_id, "--json"
    ]);
    return this.parseResult(result, inventorySchema, {
      invalidCode: "OPENCLAW_SKILL_INVENTORY_INVALID",
      timeoutCode: "OPENCLAW_SKILL_DISCOVERY_TIMEOUT"
    });
  }

  private async inspectSkill(input: {
    discoveredAt: string;
    input: AgentSkillDiscoveryInput;
    skill: z.infer<typeof inventorySkillSchema>;
    target: OpenClawAgentSkillTargetConfig;
  }): Promise<AgentSkillCatalogCandidate> {
    const infoResult = await this.run([
      "-d", input.target.wsl_distro, "--exec", this.config.command,
      "skills", "info", input.skill.name, "--agent", input.target.agent_id, "--json"
    ]);
    const info = this.parseResult(infoResult, infoSchema, {
      invalidCode: "OPENCLAW_SKILL_INFO_INVALID",
      timeoutCode: "OPENCLAW_SKILL_DISCOVERY_TIMEOUT"
    });
    if (
      info.name !== input.skill.name ||
      !lexicalContained(input.target.skill_roots, info.baseDir) ||
      !lexicalContained(input.target.skill_roots, info.filePath)
    ) {
      throw new OpenClawAgentSkillDiscoveryError("AGENT_SKILL_SOURCE_NOT_ALLOWED");
    }
    const inspectionResult = await this.run([
      "-d", input.target.wsl_distro, "--exec", "python3", "-c",
      OPENCLAW_SKILL_INSPECTION_SCRIPT,
      info.baseDir,
      JSON.stringify(input.target.skill_roots),
      String(this.config.limits.maxDepth),
      String(this.config.limits.maxFiles),
      String(this.config.limits.maxFileBytes),
      String(this.config.limits.maxTotalBytes)
    ]);
    const inspection = this.parseResult(inspectionResult, inspectionSchema, {
      invalidCode: this.inspectionFailureCode(inspectionResult),
      timeoutCode: "OPENCLAW_SKILL_DISCOVERY_TIMEOUT"
    });
    return this.candidate({
      contentFingerprint: inspection.content_fingerprint,
      discoveredAt: input.discoveredAt,
      input: input.input,
      skill: input.skill,
      status: this.status(input.skill),
      target: input.target
    });
  }

  private candidate(input: {
    contentFingerprint: string;
    discoveredAt: string;
    input: AgentSkillDiscoveryInput;
    skill: z.infer<typeof inventorySkillSchema>;
    status: AgentSkillCatalogCandidate["discovery_status"];
    target: OpenClawAgentSkillTargetConfig;
  }): AgentSkillCatalogCandidate {
    const directToolDispatch = input.skill.directToolDispatch ??
      input.skill.direct_tool_dispatch ?? false;
    return {
      agent_skill_id: stableId({
        providerSkillName: input.skill.name,
        runtimeTargetId: input.input.runtime_target_id,
        sourceId: input.input.source_id
      }),
      backend: this.backend,
      content_fingerprint: input.contentFingerprint,
      description: input.skill.description,
      direct_tool_dispatch: directToolDispatch,
      discovered_at: input.discoveredAt,
      discovery_status: input.status,
      display_name: input.skill.name,
      last_seen_at: input.discoveredAt,
      missing_requirements: {
        bins: [...input.skill.missing.bins, ...input.skill.missing.anyBins],
        config: input.skill.missing.config,
        env: input.skill.missing.env,
        os: input.skill.missing.os
      },
      model_visible: input.skill.modelVisible,
      provider_metadata: {
        bundled: input.skill.bundled,
        command_visible: input.skill.commandVisible,
        source: input.skill.source
      },
      provider_skill_name: input.skill.name,
      runtime_target_id: input.input.runtime_target_id,
      source_id: input.input.source_id,
      source_kind: "openclaw_agent_inventory",
      source_label: input.target.display_name,
      user_invocable: input.skill.userInvocable
    };
  }

  private status(
    skill: z.infer<typeof inventorySkillSchema>
  ): AgentSkillCatalogCandidate["discovery_status"] {
    const directToolDispatch = skill.directToolDispatch ??
      skill.direct_tool_dispatch ?? false;
    if (skill.disabled) return "disabled_at_provider";
    if (!skill.eligible || !skill.modelVisible || directToolDispatch) return "ineligible";
    return "available";
  }

  private inspectionFailureCode(result: OpenClawDiscoveryRunResult): string {
    const match = result.stderr.match(/(AGENT_SKILL_[A-Z_]+)/);
    return match?.[1] ?? "OPENCLAW_SKILL_INSPECTION_FAILED";
  }

  private parseResult<S extends z.ZodTypeAny>(
    result: OpenClawDiscoveryRunResult,
    schema: S,
    codes: { invalidCode: string; timeoutCode: string }
  ): z.output<S> {
    if (result.timedOut) {
      throw new OpenClawAgentSkillDiscoveryError(codes.timeoutCode);
    }
    if (result.exitCode !== 0) {
      throw new OpenClawAgentSkillDiscoveryError(codes.invalidCode);
    }
    try {
      return schema.parse(JSON.parse(result.stdout));
    } catch {
      throw new OpenClawAgentSkillDiscoveryError(codes.invalidCode);
    }
  }

  private run(args: string[]): Promise<OpenClawDiscoveryRunResult> {
    if (this.dependencies.run) {
      return this.dependencies.run({
        args,
        command: "wsl",
        maxStderrBytes: this.config.maxStderrBytes,
        maxStdoutBytes: this.config.maxStdoutBytes,
        timeoutMs: this.config.timeoutMs
      });
    }
    return runSupervisedProcess({
      args,
      command: "wsl",
      maxStderrBytes: this.config.maxStderrBytes,
      maxStdoutBytes: this.config.maxStdoutBytes,
      timeoutMs: this.config.timeoutMs
    });
  }
}
