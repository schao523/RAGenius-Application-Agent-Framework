import { spawn } from "node:child_process";

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
  const spawnProcess = input.spawnProcess ?? spawnWithTimeout;
  const raw = await spawnProcess("wsl", args, {
    timeoutMs: input.config.timeoutMs
  });
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

async function spawnWithTimeout(
  command: string,
  args: string[],
  options: { timeoutMs: number }
): Promise<OpenClawSpawnResult> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"]
    });
    const stdoutChunks: Buffer[] = [];
    const stderrChunks: Buffer[] = [];
    let timedOut = false;
    let settled = false;

    const timeout = setTimeout(() => {
      timedOut = true;
      child.kill();
      setTimeout(() => {
        if (!settled) {
          child.kill("SIGKILL");
        }
      }, 5000).unref();
    }, options.timeoutMs);

    child.stdout.on("data", (chunk: Buffer) => stdoutChunks.push(chunk));
    child.stderr.on("data", (chunk: Buffer) => stderrChunks.push(chunk));
    child.on("error", (error) => {
      clearTimeout(timeout);
      settled = true;
      reject(error);
    });
    child.on("close", (exitCode) => {
      clearTimeout(timeout);
      settled = true;
      resolve({
        exitCode,
        stdout: Buffer.concat(stdoutChunks).toString("utf8"),
        stderr: Buffer.concat(stderrChunks).toString("utf8"),
        timedOut
      });
    });
  });
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
