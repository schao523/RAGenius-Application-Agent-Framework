import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

import type { NotebookLmProviderConfig } from "../../../config/provider-config.js";

import {
  type NotebookLmBridgeRequest,
  type NotebookLmBridgeResponse
} from "./notebooklm-types.js";

export function resolveNotebookLmBridgeScript(bridgeScript: string): string {
  if (path.isAbsolute(bridgeScript)) {
    return bridgeScript;
  }

  const cwdCandidate = path.resolve(process.cwd(), bridgeScript);
  if (fs.existsSync(cwdCandidate)) {
    return cwdCandidate;
  }

  const moduleDir = path.dirname(fileURLToPath(import.meta.url));
  return path.resolve(moduleDir, "../../../../../scripts", path.basename(bridgeScript));
}

export async function executeNotebookLmBridge(
  config: NotebookLmProviderConfig,
  request: NotebookLmBridgeRequest
): Promise<NotebookLmBridgeResponse> {
  return new Promise<NotebookLmBridgeResponse>((resolve, reject) => {
    const bridgeScript = resolveNotebookLmBridgeScript(config.bridgeScript);
    const child = spawn(config.pythonCommand, [bridgeScript], {
      cwd: process.cwd(),
      stdio: "pipe"
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
            `NotebookLM bridge exited with code ${String(code)}.${stderr ? ` ${stderr}` : ""}`
          )
        );
        return;
      }

      try {
        resolve(JSON.parse(stdout) as NotebookLmBridgeResponse);
      } catch (error) {
        reject(error);
      }
    });

    child.stdin.write(JSON.stringify(request));
    child.stdin.end();
  });
}
