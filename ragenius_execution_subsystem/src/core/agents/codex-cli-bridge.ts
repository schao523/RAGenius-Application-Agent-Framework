import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

import type { CodexCliProviderConfig } from "../../config/provider-config.js";

import type {
  CodexCliBridgeRequest,
  CodexCliBridgeResponse
} from "./codex-cli-types.js";

export function resolveCodexCliBridgeScript(bridgeScript: string): string {
  if (path.isAbsolute(bridgeScript)) {
    return bridgeScript;
  }

  const cwdCandidate = path.resolve(process.cwd(), bridgeScript);
  if (fs.existsSync(cwdCandidate)) {
    return cwdCandidate;
  }

  const moduleDir = path.dirname(fileURLToPath(import.meta.url));
  return path.resolve(moduleDir, "../../../../scripts", path.basename(bridgeScript));
}

export async function executeCodexCliBridge(
  config: CodexCliProviderConfig,
  request: CodexCliBridgeRequest
): Promise<CodexCliBridgeResponse> {
  return new Promise<CodexCliBridgeResponse>((resolve, reject) => {
    const bridgeScript = resolveCodexCliBridgeScript(config.bridgeScript);
    const child = spawn(config.nodeCommand, [bridgeScript], {
      cwd: process.cwd(),
      stdio: "pipe",
      env: {
        ...process.env,
        CODEX_CLI_COMMAND: config.command,
        CODEX_CLI_ARGS_JSON: JSON.stringify(config.args),
        CODEX_CLI_TIMEOUT_MS: String(config.timeoutMs)
      }
    });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk) => {
      stdout += String(chunk);
    });
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk);
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) {
        reject(
          new Error(
            `Codex CLI bridge exited with code ${String(code)}.${stderr ? ` ${stderr}` : ""}`
          )
        );
        return;
      }

      try {
        resolve(JSON.parse(stdout) as CodexCliBridgeResponse);
      } catch (error) {
        reject(error);
      }
    });

    child.stdin.write(JSON.stringify(request));
    child.stdin.end();
  });
}
