import { spawn } from "node:child_process";

function boundedTail(maxBytes) {
  let value = Buffer.alloc(0);
  let truncated = false;
  return {
    append(chunk) {
      const incoming = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      value = Buffer.concat([value, incoming]);
      if (value.byteLength > maxBytes) {
        value = value.subarray(value.byteLength - maxBytes);
        truncated = true;
      }
    },
    result() {
      return { value: value.toString("utf8"), truncated };
    }
  };
}

function waitForClose(child, timeoutMs) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (!settled) {
        settled = true;
        resolve();
      }
    };
    child.once("close", finish);
    const timeout = setTimeout(finish, timeoutMs);
    timeout.unref();
  });
}

async function terminateWindowsTree(pid, graceMs) {
  const taskkill = spawn(
    "taskkill.exe",
    ["/PID", String(pid), "/T", "/F"],
    { shell: false, windowsHide: true, stdio: "ignore" }
  );
  await waitForClose(taskkill, graceMs);
}

async function terminatePosixGroup(pid, graceMs) {
  try {
    process.kill(-pid, "SIGTERM");
  } catch {
    return;
  }
  await new Promise((resolve) => {
    const timeout = setTimeout(resolve, Math.min(graceMs, 500));
    timeout.unref();
  });
  try {
    process.kill(-pid, "SIGKILL");
  } catch {
    // The process group already exited.
  }
}

export async function terminateSupervisedProcessTree(pid, graceMs = 5_000) {
  if (!pid) {
    return;
  }
  if (process.platform === "win32") {
    await terminateWindowsTree(pid, graceMs);
  } else {
    await terminatePosixGroup(pid, graceMs);
  }
}

export async function runSupervisedProcess(spec) {
  const maxStdoutBytes = Math.max(0, spec.maxStdoutBytes ?? 262_144);
  const maxStderrBytes = Math.max(0, spec.maxStderrBytes ?? 65_536);
  const killGraceMs = Math.max(100, spec.killGraceMs ?? 5_000);
  const stdout = boundedTail(maxStdoutBytes);
  const stderr = boundedTail(maxStderrBytes);
  let timedOut = false;
  let terminationPromise;

  return new Promise((resolve, reject) => {
    const child = spawn(spec.command, spec.args ?? [], {
      cwd: spec.cwd,
      env: spec.env,
      shell: false,
      windowsHide: true,
      detached: process.platform !== "win32",
      stdio: [typeof spec.stdin === "string" || Buffer.isBuffer(spec.stdin)
        ? "pipe"
        : "ignore", "pipe", "pipe"]
    });
    let settled = false;
    let timeoutHandle;
    let forceResolveHandle;

    const finish = async (exitCode, signal) => {
      if (settled) {
        return;
      }
      settled = true;
      if (timeoutHandle) {
        clearTimeout(timeoutHandle);
      }
      if (forceResolveHandle) {
        clearTimeout(forceResolveHandle);
      }
      if (terminationPromise) {
        await terminationPromise;
      }
      const stdoutResult = stdout.result();
      const stderrResult = stderr.result();
      resolve({
        exitCode,
        signal,
        stdout: stdoutResult.value,
        stderr: stderrResult.value,
        stdoutTruncated: stdoutResult.truncated,
        stderrTruncated: stderrResult.truncated,
        timedOut,
        pid: child.pid ?? null
      });
    };

    child.stdout?.on("data", (chunk) => stdout.append(chunk));
    child.stderr?.on("data", (chunk) => stderr.append(chunk));
    child.once("error", (error) => {
      if (timeoutHandle) {
        clearTimeout(timeoutHandle);
      }
      reject(error);
    });
    child.once("close", (exitCode, signal) => {
      void finish(exitCode, signal);
    });

    if (child.stdin && spec.stdin !== undefined) {
      child.stdin.end(spec.stdin);
    }

    if (Number.isFinite(spec.timeoutMs) && spec.timeoutMs > 0) {
      timeoutHandle = setTimeout(() => {
        timedOut = true;
        terminationPromise = (async () => {
          try {
            await spec.beforeTerminate?.({ pid: child.pid ?? null });
          } catch (error) {
            stderr.append(`\nTermination hook failed: ${error instanceof Error ? error.message : String(error)}`);
          }
          if (child.pid) {
            await terminateSupervisedProcessTree(child.pid, killGraceMs);
          }
        })();
        forceResolveHandle = setTimeout(() => {
          void finish(null, null);
        }, killGraceMs + 1_000);
        forceResolveHandle.unref();
      }, spec.timeoutMs);
      timeoutHandle.unref();
    }
  });
}
