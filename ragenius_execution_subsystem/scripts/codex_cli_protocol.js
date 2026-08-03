function redact(value) {
  return String(value || "")
    .replace(/\bBearer\s+[^\s'";,]+/gi, "Bearer [REDACTED]")
    .replace(/\b(authorization|token|api[_-]?key|cookie)\s*[:=]\s*[^\s'";,]+/gi, "$1=[REDACTED]");
}

export function buildCodexArgs(rawArgs, options) {
  const source = Array.isArray(rawArgs) ? rawArgs.map((item) => String(item)) : [];
  const args = [];
  for (let index = 0; index < source.length; index += 1) {
    const arg = source[index];
    if (arg === "--dangerously-bypass-approvals-and-sandbox") {
      continue;
    }
    if (arg === "--sandbox" || arg === "-s") {
      index += 1;
      continue;
    }
    if (arg.startsWith("--sandbox=")) {
      continue;
    }
    if (arg === "--add-dir") {
      index += 1;
      continue;
    }
    if (arg.startsWith("--add-dir=")) {
      continue;
    }
    args.push(arg);
  }
  if (!args.some((arg) => arg === "exec" || arg === "e")) {
    args.unshift("exec");
  }
  if (!args.includes("--json")) {
    args.push("--json");
  }
  if (!args.includes("--skip-git-repo-check")) {
    args.push("--skip-git-repo-check");
  }
  if (options?.workspaceAbsolutePath) {
    args.push("--cd", String(options.workspaceAbsolutePath));
  }
  args.push("--sandbox", options?.sandboxMode === "read-only" ? "read-only" : "workspace-write");
  const additionalWritableDirs = Array.isArray(options?.additionalWritableDirs)
    ? [...new Set(options.additionalWritableDirs.map((item) => String(item).trim()).filter(Boolean))]
    : [];
  for (const writableDir of additionalWritableDirs) {
    args.push("--add-dir", writableDir);
  }
  if (options?.networkAccess === "allowlisted") {
    args.push("-c", "sandbox_workspace_write.network_access=true");
  }
  return args;
}

function bounded(value, maxBytes) {
  const redacted = redact(value);
  const bytes = Buffer.from(redacted, "utf8");
  if (bytes.byteLength <= maxBytes) {
    return { text: redacted, truncated: false };
  }
  return {
    text: bytes.subarray(0, maxBytes).toString("utf8"),
    truncated: true
  };
}

function messageText(item) {
  if (typeof item?.text === "string") {
    return item.text;
  }
  if (Array.isArray(item?.content)) {
    return item.content
      .map((part) => typeof part?.text === "string" ? part.text : "")
      .filter(Boolean)
      .join("\n");
  }
  return "";
}

function errorMessage(event) {
  if (typeof event?.error?.message === "string") {
    return redact(event.error.message);
  }
  if (typeof event?.message === "string") {
    return redact(event.message);
  }
  return "Codex turn failed.";
}

export function parseCodexJsonl(stdout, options) {
  const maxOutputBytes = Number.isInteger(options?.maxOutputBytes) && options.maxOutputBytes > 0
    ? options.maxOutputBytes
    : 16384;
  const commands = new Map();
  const errors = [];
  let threadId;
  let turnStatus = "unknown";
  let finalMessage = "";
  let usage;
  let malformedLineCount = 0;
  let stdoutTruncated = false;
  let stderrTruncated = false;

  for (const line of String(stdout || "").split(/\r?\n/)) {
    if (!line.trim()) {
      continue;
    }
    let event;
    try {
      event = JSON.parse(line);
    } catch {
      malformedLineCount += 1;
      continue;
    }
    if (event.type === "thread.started" && typeof event.thread_id === "string") {
      threadId = event.thread_id;
    }
    if (event.type === "turn.started") {
      turnStatus = "unknown";
    }
    if (event.type === "turn.completed") {
      turnStatus = "completed";
      if (event.usage && typeof event.usage === "object") {
        usage = event.usage;
      }
    }
    if (event.type === "turn.failed") {
      turnStatus = "failed";
      errors.push({ code: "CODEX_TURN_FAILED", message: errorMessage(event) });
    }
    const item = event.item;
    if (item?.type === "agent_message" && event.type === "item.completed") {
      finalMessage = messageText(item) || finalMessage;
    }
    if (item?.type === "command_execution") {
      const itemId = String(item.id || `command_${commands.size + 1}`);
      const existing = commands.get(itemId) || { item_id: itemId };
      const command = bounded(item.command || existing.command || "", maxOutputBytes);
      const stdoutValue = bounded(
        item.aggregated_output ?? item.stdout ?? existing.stdout_summary ?? "",
        maxOutputBytes
      );
      const stderrValue = bounded(item.stderr ?? existing.stderr_summary ?? "", maxOutputBytes);
      stdoutTruncated ||= stdoutValue.truncated;
      stderrTruncated ||= stderrValue.truncated;
      commands.set(itemId, {
        item_id: itemId,
        command: command.text,
        ...(typeof item.exit_code === "number"
          ? { exit_code: item.exit_code }
          : existing.exit_code !== undefined
            ? { exit_code: existing.exit_code }
            : {}),
        ...(stdoutValue.text ? { stdout_summary: stdoutValue.text } : {}),
        ...(stderrValue.text ? { stderr_summary: stderrValue.text } : {})
      });
    }
  }

  return {
    ...(threadId ? { thread_id: threadId } : {}),
    turn_status: turnStatus,
    final_message: finalMessage,
    command_events: [...commands.values()],
    errors,
    ...(usage ? { usage } : {}),
    raw_exit_code: Number.isInteger(options?.rawExitCode) ? options.rawExitCode : -1,
    malformed_line_count: malformedLineCount,
    stdout_truncated: stdoutTruncated,
    stderr_truncated: stderrTruncated
  };
}
