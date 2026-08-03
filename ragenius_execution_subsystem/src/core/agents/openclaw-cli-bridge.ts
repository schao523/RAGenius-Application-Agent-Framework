import { createHash } from "node:crypto";

import { runSupervisedProcess } from "../../../scripts/agent_process_supervisor.js";

export type OpenClawCliBridgeConfig = {
  wslDistro: string;
  command: string;
  agentId: string;
  timeoutMs: number;
  maxStdoutBytes: number;
  maxStderrBytes: number;
};

export type OpenClawSpawnResult = {
  exitCode: number | null;
  stdout: string;
  stderr: string;
  timedOut: boolean;
};

export type OpenClawSpawnProcess = (
  command: string,
  args: string[],
  options: { timeoutMs: number }
) => Promise<OpenClawSpawnResult>;

export type OpenClawCliBridgeResult = OpenClawSpawnResult & {
  stdoutTruncated: boolean;
  stderrTruncated: boolean;
  json?: unknown;
  jsonParseStatus: "parsed" | "failed" | "not_requested";
};

export async function executeOpenClawCliBridge(input: {
  config: OpenClawCliBridgeConfig;
  sessionKey: string;
  prompt: string;
  spawnProcess?: OpenClawSpawnProcess;
}): Promise<OpenClawCliBridgeResult> {
  const args = [
    "-d",
    input.config.wslDistro,
    "--exec",
    input.config.command,
    "agent",
    "--agent",
    input.config.agentId,
    "--session-key",
    input.sessionKey,
    "--message",
    input.prompt,
    "--json"
  ];
  const raw = input.spawnProcess
    ? await input.spawnProcess("wsl", args, { timeoutMs: input.config.timeoutMs })
    : await spawnOpenClawWithSupervision(input.config, args);
  const stdout = truncateTail(raw.stdout, input.config.maxStdoutBytes);
  const stderr = truncateTail(raw.stderr, input.config.maxStderrBytes);
  const parsed = parseJson(stdout.value);

  return {
    exitCode: raw.exitCode,
    stdout: stdout.value,
    stderr: stderr.value,
    timedOut: raw.timedOut,
    stdoutTruncated: stdout.truncated,
    stderrTruncated: stderr.truncated,
    ...(parsed.status === "parsed" ? { json: parsed.value } : {}),
    jsonParseStatus: parsed.status
  };
}

export function buildOpenClawSupervisedWslArgs(input: {
  wslDistro: string;
  processGroupFile: string;
  agentArgs: string[];
}): string[] {
  return [
    "-d",
    input.wslDistro,
    "--exec",
    "setsid",
    "--wait",
    "sh",
    "-c",
    'umask 077; printf "%s" "$$" > "$1"; shift; exec "$@"',
    "ragenius-openclaw-supervisor",
    input.processGroupFile,
    ...input.agentArgs
  ];
}

export function extractOpenClawExecArgs(directWslArgs: string[]): string[] {
  const execIndex = directWslArgs.indexOf("--exec");
  if (execIndex < 0 || execIndex + 1 >= directWslArgs.length) {
    throw new Error("OpenClaw WSL arguments do not contain an executable.");
  }
  return directWslArgs.slice(execIndex + 1);
}

async function runWslLifecycleCommand(
  wslDistro: string,
  args: string[]
): Promise<OpenClawSpawnResult> {
  const result = await runSupervisedProcess({
    command: "wsl",
    args: ["-d", wslDistro, "--exec", ...args],
    timeoutMs: 5_000,
    killGraceMs: 1_000,
    maxStdoutBytes: 1024,
    maxStderrBytes: 4096
  });
  return {
    exitCode: result.exitCode,
    stdout: result.stdout,
    stderr: result.stderr,
    timedOut: result.timedOut
  };
}

async function spawnOpenClawWithSupervision(
  config: OpenClawCliBridgeConfig,
  directWslArgs: string[]
): Promise<OpenClawSpawnResult> {
  const agentArgs = extractOpenClawExecArgs(directWslArgs);
  const marker = createHash("sha256")
    .update(agentArgs.join("\u0000"))
    .digest("hex")
    .slice(0, 24);
  const processGroupFile = `/tmp/ragenius-openclaw-${marker}.pgid`;
  const result = await runSupervisedProcess({
    command: "wsl",
    args: buildOpenClawSupervisedWslArgs({
      wslDistro: config.wslDistro,
      processGroupFile,
      agentArgs
    }),
    timeoutMs: config.timeoutMs,
    maxStdoutBytes: config.maxStdoutBytes,
    maxStderrBytes: config.maxStderrBytes,
    beforeTerminate: async () => {
      const pidResult = await runWslLifecycleCommand(config.wslDistro, [
        "cat",
        "--",
        processGroupFile
      ]);
      const processGroupId = pidResult.stdout.trim();
      if (!/^\d+$/.test(processGroupId)) {
        throw new Error("OpenClaw process-group marker was unavailable.");
      }
      await runWslLifecycleCommand(config.wslDistro, [
        "kill",
        "-TERM",
        "--",
        `-${processGroupId}`
      ]);
    }
  });
  try {
    await runWslLifecycleCommand(config.wslDistro, [
      "rm",
      "-f",
      "--",
      processGroupFile
    ]);
  } catch {
    // The run result remains authoritative if marker cleanup is unavailable.
  }
  return {
    exitCode: result.exitCode,
    stdout: result.stdout,
    stderr: result.stderr,
    timedOut: result.timedOut
  };
}

function truncateTail(value: string, maxBytes: number): {
  value: string;
  truncated: boolean;
} {
  const buffer = Buffer.from(value, "utf8");
  if (buffer.byteLength <= maxBytes) {
    return { value, truncated: false };
  }
  return {
    value: buffer.subarray(buffer.byteLength - maxBytes).toString("utf8"),
    truncated: true
  };
}

function parseJson(value: string): { status: "parsed"; value: unknown } | {
  status: "failed" | "not_requested";
} {
  const trimmed = value.trim();
  if (!trimmed) {
    return { status: "not_requested" };
  }
  try {
    return { status: "parsed", value: JSON.parse(trimmed) };
  } catch (_error) {
    return { status: "failed" };
  }
}
