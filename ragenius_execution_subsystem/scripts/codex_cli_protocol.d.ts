export interface CodexCommandEvent {
  item_id: string;
  command: string;
  exit_code?: number;
  stdout_summary?: string;
  stderr_summary?: string;
}

export interface ParsedCodexProtocol {
  thread_id?: string;
  turn_status: "completed" | "failed" | "unknown";
  final_message: string;
  command_events: CodexCommandEvent[];
  errors: Array<{ code: string; message: string }>;
  usage?: Record<string, unknown>;
  raw_exit_code: number;
  malformed_line_count: number;
  stdout_truncated: boolean;
  stderr_truncated: boolean;
}

export function buildCodexArgs(
  rawArgs: unknown,
  options: {
    workspaceAbsolutePath?: string;
    sandboxMode?: "read-only" | "workspace-write";
    networkAccess?: "deny" | "allowlisted";
    additionalWritableDirs?: string[];
  }
): string[];

export function parseCodexJsonl(
  stdout: string,
  options: { maxOutputBytes: number; rawExitCode: number }
): ParsedCodexProtocol;
