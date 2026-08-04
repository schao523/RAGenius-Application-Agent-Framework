export function createExecutionId(): string {
  return `exec_${crypto.randomUUID()}`;
}
