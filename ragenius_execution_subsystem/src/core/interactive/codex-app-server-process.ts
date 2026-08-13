import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";

import {
  runSupervisedProcess,
  terminateSupervisedProcessTree
} from "../../../scripts/agent_process_supervisor.js";
import { CodexAppServerCodec, recordValue, stringValue } from "./codex-app-server-codec.js";
import type {
  CodexAppServerTransport,
  CodexAppServerTransportFactory,
  CodexVersionInfo
} from "./codex-app-server-adapter.js";

export interface CodexAppServerProcessConfig {
  command: string;
  initializationTimeoutMs: number;
  maxLineBytes: number;
  maxStderrBytes: number;
}

type PendingRequest = {
  reject(error: Error): void;
  resolve(value: unknown): void;
  timeout: NodeJS.Timeout;
};

export class CodexAppServerProcessFactory implements CodexAppServerTransportFactory {
  constructor(private readonly config: CodexAppServerProcessConfig) {}

  async versionInfo(): Promise<CodexVersionInfo> {
    try {
      const result = await runSupervisedProcess({
        command: this.config.command,
        args: ["--version"],
        timeoutMs: this.config.initializationTimeoutMs,
        maxStdoutBytes: 4096,
        maxStderrBytes: this.config.maxStderrBytes
      });
      const match = result.stdout.match(/(\d+\.\d+\.\d+)/);
      return {
        available: result.exitCode === 0 && Boolean(match),
        ...(match?.[1] ? { version: match[1] } : {}),
        ...(result.exitCode !== 0 ? { reason: "Codex version probe failed." } : {})
      };
    } catch (error) {
      return {
        available: false,
        reason: error instanceof Error ? error.message : String(error)
      };
    }
  }

  async create(): Promise<CodexAppServerTransport> {
    return CodexAppServerProcessTransport.start(this.config);
  }
}

class CodexAppServerProcessTransport implements CodexAppServerTransport {
  private readonly codec: CodexAppServerCodec;
  private readonly pending = new Map<number, PendingRequest>();
  private handler: ((message: Record<string, unknown>) => Promise<void>) | undefined;
  private closeHandler: ((error?: Error) => Promise<void>) | undefined;
  private nextId = 1;
  private stdoutBuffer = "";
  private stderrBytes = Buffer.alloc(0);
  private closed = false;

  private constructor(
    private readonly child: ChildProcessWithoutNullStreams,
    private readonly config: CodexAppServerProcessConfig
  ) {
    this.codec = new CodexAppServerCodec({ maxLineBytes: config.maxLineBytes });
    child.stdout.on("data", (chunk: Buffer) => this.consumeStdout(chunk));
    child.stderr.on("data", (chunk: Buffer) => this.captureStderr(chunk));
    child.once("error", (error) => {
      this.failPending(error);
      this.notifyClose(error);
    });
    child.once("close", (code, signal) => {
      this.closed = true;
      const error = new Error(
        `Codex app-server process disconnected (code=${String(code)}, signal=${String(signal)}).`
      );
      this.failPending(error);
      this.notifyClose(error);
    });
  }

  static start(config: CodexAppServerProcessConfig): CodexAppServerProcessTransport {
    const child = spawn(config.command, ["app-server", "--stdio"], {
      cwd: process.cwd(),
      env: process.env,
      shell: false,
      windowsHide: true,
      detached: process.platform !== "win32",
      stdio: "pipe"
    });
    return new CodexAppServerProcessTransport(child, config);
  }

  async request(method: string, params?: unknown): Promise<unknown> {
    this.assertOpen();
    const id = this.nextId++;
    const response = new Promise<unknown>((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`Codex app-server request timed out: ${method}`));
      }, this.config.initializationTimeoutMs);
      timeout.unref();
      this.pending.set(id, { reject, resolve, timeout });
    });
    this.child.stdin.write(this.codec.encodeRequest(id, method, params));
    return response;
  }

  async notify(method: string, params?: unknown): Promise<void> {
    this.assertOpen();
    this.child.stdin.write(this.codec.encodeNotification(method, params));
  }

  async respond(id: string | number, result: unknown): Promise<void> {
    this.assertOpen();
    this.child.stdin.write(this.codec.encodeResponse(id, result));
  }

  onMessage(handler: (message: Record<string, unknown>) => Promise<void>): void {
    this.handler = handler;
  }

  onClose(handler: (error?: Error) => Promise<void>): void {
    this.closeHandler = handler;
  }

  isClosed(): boolean { return this.closed; }

  async close(): Promise<void> {
    if (this.closed) return;
    this.closed = true;
    this.child.stdin.end();
    await terminateSupervisedProcessTree(this.child.pid ?? null);
  }

  private consumeStdout(chunk: Buffer): void {
    this.stdoutBuffer += chunk.toString("utf8");
    if (Buffer.byteLength(this.stdoutBuffer, "utf8") > this.config.maxLineBytes * 2) {
      this.failPending(new Error("Codex app-server stdout exceeded framing bounds."));
      void this.close();
      return;
    }
    let newline = this.stdoutBuffer.indexOf("\n");
    while (newline >= 0) {
      const line = this.stdoutBuffer.slice(0, newline).trim();
      this.stdoutBuffer = this.stdoutBuffer.slice(newline + 1);
      if (line) {
        try {
          this.consumeMessage(this.codec.decode(line));
        } catch (error) {
          this.failPending(error instanceof Error ? error : new Error(String(error)));
          void this.close();
          return;
        }
      }
      newline = this.stdoutBuffer.indexOf("\n");
    }
  }

  private consumeMessage(message: Record<string, unknown>): void {
    const id = message.id;
    if ((typeof id === "number" || typeof id === "string") && !("method" in message)) {
      const numericId = typeof id === "number" ? id : Number(id);
      const pending = this.pending.get(numericId);
      if (!pending) return;
      clearTimeout(pending.timeout);
      this.pending.delete(numericId);
      if (message.error) {
        const error = recordValue(message.error);
        pending.reject(new Error(stringValue(error.message) || "Codex app-server request failed."));
      } else {
        pending.resolve(message.result);
      }
      return;
    }
    if (this.handler) {
      void this.handler(message).catch((error) => this.failPending(
        error instanceof Error ? error : new Error(String(error))
      ));
    }
  }

  private captureStderr(chunk: Buffer): void {
    this.stderrBytes = Buffer.concat([this.stderrBytes, chunk]);
    if (this.stderrBytes.byteLength > this.config.maxStderrBytes) {
      this.stderrBytes = this.stderrBytes.subarray(
        this.stderrBytes.byteLength - this.config.maxStderrBytes
      );
    }
  }

  private failPending(error: Error): void {
    for (const pending of this.pending.values()) {
      clearTimeout(pending.timeout);
      pending.reject(error);
    }
    this.pending.clear();
  }

  private notifyClose(error: Error): void {
    if (!this.closeHandler) return;
    void this.closeHandler(error).catch(() => undefined);
  }

  private assertOpen(): void {
    if (this.closed) throw new Error("Codex app-server process is closed.");
  }
}
