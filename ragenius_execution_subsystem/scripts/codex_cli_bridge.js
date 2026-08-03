import {
  buildCodexChildEnv,
  resolveCodexAdditionalWritableDirs
} from "./codex_cli_environment.js";
import { buildCodexArgs, parseCodexJsonl } from "./codex_cli_protocol.js";
import { runSupervisedProcess } from "./agent_process_supervisor.js";

function sanitizeProxyEnv(sourceEnv) {
  const env = { ...sourceEnv };
  const proxyKeys = [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy"
  ];
  const deadProxyPattern = /^(https?|socks5?):\/\/(127\.0\.0\.1|localhost):9(?:\/)?$/i;
  for (const key of proxyKeys) {
    const value = String(env[key] || "").trim();
    if (value && deadProxyPattern.test(value)) {
      delete env[key];
    }
  }
  return env;
}

function parseJson(value, fallback) {
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

/* eslint-disable @typescript-eslint/no-unused-vars -- Retained for legacy direct bridge result normalization. */
function shortenText(value, maxLength = 220) {
  const text = String(value || "").trim().replace(/\s+/g, " ");
  if (!text) {
    return "";
  }
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`;
}

function summarizeNotebookTitles(items, limit = 3) {
  if (!Array.isArray(items)) {
    return "";
  }
  return items
    .slice(0, limit)
    .map((item) => {
      if (item && typeof item === "object") {
        return String(item.title || item.name || item.id || "").trim();
      }
      return "";
    })
    .filter(Boolean)
    .join(", ");
}

function buildUserSummary(result, request) {
  const output = result.output && typeof result.output === "object" && !Array.isArray(result.output)
    ? result.output
    : {};
  const status = String(output.status || "completed").trim().toLowerCase() || "completed";
  const notebookTitle =
    output.notebook && typeof output.notebook === "object"
      ? String(output.notebook.title || "").trim()
      : "";

  if (typeof output.answer === "string" && output.answer.trim()) {
    return {
      status,
      title: "NotebookLM question answered",
      subtitle: notebookTitle || undefined,
      preview: shortenText(output.answer, 220)
    };
  }

  if (Array.isArray(output.notebooks)) {
    return {
      status,
      title: `NotebookLM notebooks (${output.notebooks.length})`,
      preview: summarizeNotebookTitles(output.notebooks, 4) || undefined
    };
  }

  if (Array.isArray(output.sources)) {
    return {
      status,
      title: `NotebookLM sources (${output.sources.length})`,
      subtitle: notebookTitle || undefined,
      preview: summarizeNotebookTitles(output.sources, 4) || undefined
    };
  }

  if (Array.isArray(result.artifacts) && result.artifacts.length > 0) {
    return {
      status,
      title: `Codex created ${result.artifacts.length} artifact${result.artifacts.length === 1 ? "" : "s"}`,
      subtitle: notebookTitle || undefined,
      preview: shortenText(result.final_message, 200) || undefined
    };
  }

  if (status === "failed" || status === "blocked") {
    return {
      status,
      title: "Codex could not complete the request",
      subtitle: request.agent_skill_hint || undefined,
      preview: shortenText(
        output.error || result.final_message || "The agent run failed before producing a result.",
        220
      )
    };
  }

  return {
    status,
    title: shortenText(result.final_message || "Codex agent request completed.", 120),
    subtitle: request.agent_skill_hint || undefined,
    preview: ""
  };
}

function buildPrompt(request) {
  const approved = request.approved_revision_id
    ? `Approved revision: ${request.approved_revision_id}`
    : "Approved revision: none";
  const approvedContent = request.approved_content_id
    ? `Approved content: ${request.approved_content_id}`
    : "Approved content: none";
  const skillHint = request.agent_skill_hint
    ? `Preferred skill hint: ${request.agent_skill_hint}`
    : "Preferred skill hint: auto";
  const contextJson = JSON.stringify(request.context || {}, null, 2);
  const policyJson = JSON.stringify(request.policy || {}, null, 2);
  const sslCertFile = String(process.env.SSL_CERT_FILE || "").trim();
  const requestsCaBundle = String(process.env.REQUESTS_CA_BUNDLE || "").trim();
  const curlCaBundle = String(process.env.CURL_CA_BUNDLE || "").trim();
  const pythonHttpsVerify = String(process.env.PYTHONHTTPSVERIFY || "").trim();
  const notebooklmPython = String(process.env.NOTEBOOKLM_PYTHON_COMMAND || "python").trim() || "python";
  const notebooklmWrapperPath = `${process.cwd().replaceAll("\\", "/")}/scripts/notebooklm_with_env.ps1`;

  const notebooklmRuntimeHints = [
    "NotebookLM runtime guidance:",
    `- Use \`${notebooklmPython} -m notebooklm ...\` rather than a bare \`notebooklm\` command.`,
    "- Run NotebookLM-related shell commands in PowerShell.",
    `- Prefer this wrapper for all NotebookLM commands: \`${notebooklmWrapperPath}\`.`,
    `- Example: \`powershell -ExecutionPolicy Bypass -File "${notebooklmWrapperPath.replaceAll("/", "\\")}" auth check --test --json\`.`,
    "- When using the wrapper, do not prepend your own $env:SSL_CERT_FILE / REQUESTS_CA_BUNDLE / CURL_CA_BUNDLE assignments. The wrapper manages them itself.",
  ];
  if (sslCertFile || requestsCaBundle || curlCaBundle || pythonHttpsVerify) {
    notebooklmRuntimeHints.push("- Before any NotebookLM command, set these environment variables in the same PowerShell command:");
    if (sslCertFile) {
      notebooklmRuntimeHints.push(`  $env:SSL_CERT_FILE='${sslCertFile}'`);
    }
    if (requestsCaBundle) {
      notebooklmRuntimeHints.push(`  $env:REQUESTS_CA_BUNDLE='${requestsCaBundle}'`);
    }
    if (curlCaBundle) {
      notebooklmRuntimeHints.push(`  $env:CURL_CA_BUNDLE='${curlCaBundle}'`);
    }
    if (pythonHttpsVerify) {
      notebooklmRuntimeHints.push(`  $env:PYTHONHTTPSVERIFY='${pythonHttpsVerify}'`);
    }
    notebooklmRuntimeHints.push(`- Only if the wrapper is unavailable, inline the environment variables in the same command before invoking NotebookLM.`);
  }

  const constrainedSkillHints = [];
  if (request.agent_skill_hint === "notebooklm") {
    constrainedSkillHints.push(
      "Execution constraints for this run:",
      "- Use only the `notebooklm` skill. Do not load unrelated skills if `notebooklm` is already available.",
      "- Do not explore alternate skill directories once the `notebooklm` skill has been loaded successfully.",
      "- Perform only the minimum required commands to satisfy the request.",
      "- Execute the user-requested NotebookLM command first instead of running `notebooklm auth check --test --json` as a mandatory preflight.",
      "- Only run NotebookLM auth diagnostics if the requested command itself fails with an auth, cookie, or network-related error.",
      "- For notebook listing requests, call the wrapper with `list --json` directly.",
      "- For notebook ask requests, resolve the notebook and execute the `ask` command directly; do not stop solely because a preflight auth check failed.",
      "- If NotebookLM auth or TLS validation fails, return a structured failure immediately.",
      "- Do not retry the same NotebookLM auth/list command multiple times.",
      "- Do not spend time on generic process/bootstrap skills unless they are strictly required by the runtime."
    );
  }

  return [
    "You are executing inside the RAGenius execution subsystem.",
    "Return either plain text or JSON with keys final_message, activated_skills, tool_summary, artifacts, and output.",
    "When using NotebookLM, prefer `python -m notebooklm ...` rather than a bare `notebooklm` command.",
    "Do not assume the `notebooklm` executable is on PATH.",
    "If NotebookLM authentication fails, report the exact error rather than silently retrying broad alternate flows.",
    ...notebooklmRuntimeHints,
    ...constrainedSkillHints,
    `App ID: ${request.app_id}`,
    `Session ID: ${request.session_id}`,
    approved,
    approvedContent,
    skillHint,
    "Policy constraints:",
    policyJson,
    "Structured context:",
    contextJson,
    "User request:",
    request.agent_query
  ].join("\n");
}

function normalizeSuccessResult(stdout, request) {
  const trimmed = String(stdout || "").trim();
  const parsed = trimmed ? parseJson(trimmed, null) : null;
  if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
    const finalMessage =
      typeof parsed.final_message === "string" && parsed.final_message.trim()
        ? parsed.final_message.trim()
        : trimmed || "Codex CLI completed the agent request.";
    const normalizedResult = {
      final_message: finalMessage,
      activated_skills: Array.isArray(parsed.activated_skills)
        ? parsed.activated_skills.filter((item) => typeof item === "string")
        : request.agent_skill_hint
          ? [request.agent_skill_hint]
          : [],
      tool_summary: Array.isArray(parsed.tool_summary)
        ? parsed.tool_summary.filter((item) => typeof item === "string")
        : [],
      artifacts: Array.isArray(parsed.artifacts)
        ? parsed.artifacts.filter((item) => item && typeof item === "object")
        : [],
      output:
        parsed.output && typeof parsed.output === "object" && !Array.isArray(parsed.output)
          ? parsed.output
          : parsed,
      raw_output: trimmed
    };
    const parsedUserSummary =
      parsed.user_summary && typeof parsed.user_summary === "object" && !Array.isArray(parsed.user_summary)
        ? parsed.user_summary
        : {};
    normalizedResult.user_summary = {
      ...buildUserSummary(normalizedResult, request),
      ...Object.fromEntries(
        Object.entries(parsedUserSummary).filter(([, value]) => typeof value === "string" && value.trim())
      )
    };
    return normalizedResult;
  }

  const fallbackResult = {
    final_message: trimmed || "Codex CLI completed the agent request.",
    activated_skills: request.agent_skill_hint ? [request.agent_skill_hint] : [],
    tool_summary: [],
    artifacts: [],
    output: {},
    raw_output: trimmed
  };
  fallbackResult.user_summary = buildUserSummary(fallbackResult, request);
  return fallbackResult;
}

function emit(response, exitCode) {
  /* eslint-enable @typescript-eslint/no-unused-vars */
  process.stdout.write(`${JSON.stringify(response)}\n`);
  process.exit(exitCode);
}

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  input += chunk;
});
process.stdin.on("end", async () => {
  const request = parseJson(input || "{}", {});
  const command = String(process.env.CODEX_CLI_COMMAND || "codex").trim() || "codex";
  const args = buildCodexArgs(
    parseJson(process.env.CODEX_CLI_ARGS_JSON || "[]", []),
    {
      workspaceAbsolutePath: request.workspace_absolute_path,
      sandboxMode: request.sandbox_mode,
      networkAccess: request.policy?.network_access,
      additionalWritableDirs: resolveCodexAdditionalWritableDirs(request, process.env)
    }
  );
  const timeoutMs = Number.parseInt(process.env.CODEX_CLI_TIMEOUT_MS || "300000", 10);
  const prompt = typeof request.prompt === "string" && request.prompt.trim()
    ? request.prompt
    : buildPrompt(request);
  const childEnv = buildCodexChildEnv(sanitizeProxyEnv(process.env));

  let supervised;
  try {
    supervised = await runSupervisedProcess({
      command,
      args,
      cwd: request.workspace_absolute_path || process.cwd(),
      env: childEnv,
      stdin: prompt,
      timeoutMs,
      maxStdoutBytes: Number(process.env.CODEX_CLI_MAX_STDOUT_BYTES) || 4_194_304,
      maxStderrBytes: Number(process.env.CODEX_CLI_MAX_STDERR_BYTES) || 65_536
    });
  } catch (error) {
    emit(
      {
        ok: false,
        error: {
          code: "CODEX_CLI_COMMAND_FAILED",
          message: "Failed to launch the Codex CLI command.",
          details: {
            command,
            args,
            error: error && error.message ? error.message : String(error)
          },
          recoverable: true,
          suggested_action: "Verify the Codex CLI command path and retry."
        }
      },
      0
    );
    return;
  }

  const { exitCode: code, stdout, stderr, timedOut } = supervised;
  if (timedOut) {
      emit(
        {
          ok: false,
          error: {
            code: "CODEX_CLI_TIMEOUT",
            message: "Codex CLI timed out before producing a result.",
            details: {
              command,
              args,
              timeout_ms: timeoutMs,
              stderr: stderr.trim() || undefined
            },
            recoverable: true,
            suggested_action: "Increase CODEX_CLI_TIMEOUT_MS or reduce the request scope."
          }
        },
        0
      );
      return;
  }

  if (code !== 0) {
      emit(
        {
          ok: false,
          error: {
            code: "CODEX_CLI_EXIT_NONZERO",
            message: "Codex CLI exited with a non-zero status.",
            details: {
              command,
              args,
              exit_code: code,
              stderr: stderr.trim() || undefined,
              stdout: stdout.trim() || undefined
            },
            recoverable: true,
            suggested_action: "Inspect the Codex CLI stderr output and retry the request."
          }
        },
        0
      );
      return;
  }

  emit(
    {
      ok: true,
      result: parseCodexJsonl(stdout, {
        maxOutputBytes: Number(request.max_output_bytes) || 16384,
        rawExitCode: code ?? 0
      })
    },
    0
  );
});
