export type SupervisedProcessResult = {
  exitCode: number | null;
  signal: NodeJS.Signals | null;
  stdout: string;
  stderr: string;
  stdoutTruncated: boolean;
  stderrTruncated: boolean;
  timedOut: boolean;
  pid: number | null;
};

export type SupervisedProcessSpec = {
  command: string;
  args?: string[];
  cwd?: string;
  env?: NodeJS.ProcessEnv;
  stdin?: string | Buffer;
  timeoutMs: number;
  killGraceMs?: number;
  maxStdoutBytes?: number;
  maxStderrBytes?: number;
  beforeTerminate?: (input: { pid: number | null }) => void | Promise<void>;
};

export function runSupervisedProcess(
  spec: SupervisedProcessSpec
): Promise<SupervisedProcessResult>;
