export function buildCodexChildEnv(
  sourceEnv: NodeJS.ProcessEnv
): NodeJS.ProcessEnv;
export function resolveNotebookLmWritableDir(
  sourceEnv: NodeJS.ProcessEnv
): string | undefined;
export function resolveCodexAdditionalWritableDirs(
  request: { agent_skill_hint?: string },
  sourceEnv: NodeJS.ProcessEnv
): string[];
