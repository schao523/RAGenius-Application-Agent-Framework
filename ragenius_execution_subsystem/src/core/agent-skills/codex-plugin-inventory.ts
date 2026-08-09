import { z } from "zod";

import {
  runSupervisedProcess,
  type SupervisedProcessResult,
  type SupervisedProcessSpec
} from "../../../scripts/agent_process_supervisor.js";

const pluginSchema = z.object({
  pluginId: z.string().trim().min(1),
  name: z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/),
  marketplaceName: z.string().trim().min(1).optional(),
  version: z.string().trim().min(1).optional(),
  installed: z.boolean(),
  enabled: z.boolean(),
  source: z.object({
    source: z.string().trim().min(1),
    path: z.string().trim().min(1)
  })
});

const inventorySchema = z.object({
  installed: z.array(pluginSchema),
  available: z.array(z.unknown()).optional()
});

export interface CodexPluginInventoryEntry {
  marketplace_name?: string;
  name: string;
  plugin_id: string;
  source_path: string;
  version?: string;
}

export interface CodexPluginInventoryConfig {
  command: string;
  maxStderrBytes: number;
  maxStdoutBytes: number;
  timeoutMs: number;
}

export class CodexPluginInventoryError extends Error {
  constructor(readonly code: string) {
    super(code);
    this.name = "CodexPluginInventoryError";
  }
}

export class CodexPluginInventoryReader {
  constructor(
    private readonly config: CodexPluginInventoryConfig,
    private readonly dependencies: {
      run: (spec: SupervisedProcessSpec) => Promise<SupervisedProcessResult>;
    } = { run: runSupervisedProcess }
  ) {}

  async list(): Promise<CodexPluginInventoryEntry[]> {
    let result: SupervisedProcessResult;
    try {
      result = await this.dependencies.run({
        command: this.config.command,
        args: ["plugin", "list", "--json"],
        timeoutMs: this.config.timeoutMs,
        maxStdoutBytes: this.config.maxStdoutBytes,
        maxStderrBytes: this.config.maxStderrBytes
      });
    } catch {
      throw new CodexPluginInventoryError(
        "AGENT_SKILL_PLUGIN_INVENTORY_EXIT_FAILED"
      );
    }

    if (result.timedOut) {
      throw new CodexPluginInventoryError(
        "AGENT_SKILL_PLUGIN_INVENTORY_TIMEOUT"
      );
    }
    if (result.stdoutTruncated || result.stderrTruncated) {
      throw new CodexPluginInventoryError(
        "AGENT_SKILL_PLUGIN_INVENTORY_OUTPUT_LIMIT"
      );
    }
    if (result.exitCode !== 0) {
      throw new CodexPluginInventoryError(
        "AGENT_SKILL_PLUGIN_INVENTORY_EXIT_FAILED"
      );
    }

    try {
      const parsed = inventorySchema.parse(JSON.parse(result.stdout));
      return parsed.installed
        .filter((plugin) =>
          plugin.installed && plugin.enabled && plugin.source.source === "local"
        )
        .map((plugin) => ({
          ...(plugin.marketplaceName
            ? { marketplace_name: plugin.marketplaceName }
            : {}),
          name: plugin.name,
          plugin_id: plugin.pluginId,
          source_path: plugin.source.path,
          ...(plugin.version ? { version: plugin.version } : {})
        }));
    } catch {
      throw new CodexPluginInventoryError(
        "AGENT_SKILL_PLUGIN_INVENTORY_INVALID"
      );
    }
  }
}
