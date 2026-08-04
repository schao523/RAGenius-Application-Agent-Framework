import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { runSupervisedProcess } from "../../scripts/agent_process_supervisor.js";

async function waitForFile(filePath: string): Promise<number[]> {
  const deadline = Date.now() + 5_000;
  while (Date.now() < deadline) {
    try {
      return JSON.parse(await fs.readFile(filePath, "utf8")) as number[];
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
  }
  throw new Error("Timed out waiting for supervised PID fixture.");
}

function isAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

async function waitForExit(pid: number): Promise<void> {
  const deadline = Date.now() + 5_000;
  while (Date.now() < deadline && isAlive(pid)) {
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  assert.equal(isAlive(pid), false, `process ${pid} survived supervision`);
}

test("timeout terminates the supervised process tree", async () => {
  const pidFile = path.join(
    await fs.mkdtemp(path.join(os.tmpdir(), "ragenius-supervisor-")),
    "pids.json"
  );
  const childSource = "setInterval(() => {}, 1000)";
  const parentSource = [
    "const { spawn } = require('node:child_process');",
    "const fs = require('node:fs');",
    `const child = spawn(process.execPath, ['-e', ${JSON.stringify(childSource)}], { stdio: 'ignore' });`,
    "fs.writeFileSync(process.argv[1], JSON.stringify([process.pid, child.pid]));",
    "setInterval(() => {}, 1000);"
  ].join(" ");

  const run = runSupervisedProcess({
    command: process.execPath,
    args: ["-e", parentSource, pidFile],
    timeoutMs: 250,
    killGraceMs: 2_000,
    maxStdoutBytes: 1024,
    maxStderrBytes: 1024
  });
  const pids = await waitForFile(pidFile);
  const result = await run;

  assert.equal(result.timedOut, true);
  assert.equal(pids.length, 2);
  await Promise.all(pids.map(waitForExit));
});

test("captures bounded output without using a shell", async () => {
  const result = await runSupervisedProcess({
    command: process.execPath,
    args: ["-e", "process.stdout.write('abcdef'); process.stderr.write('wxyz')"],
    timeoutMs: 5_000,
    maxStdoutBytes: 4,
    maxStderrBytes: 3
  });

  assert.equal(result.exitCode, 0);
  assert.equal(result.stdout, "cdef");
  assert.equal(result.stderr, "xyz");
  assert.equal(result.stdoutTruncated, true);
  assert.equal(result.stderrTruncated, true);
});
