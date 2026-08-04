export type AgentDiagnostic = {
  code: string;
  message: string;
  error_class?: string;
};

export type AgentSecondaryDiagnostic = {
  stage: "verification" | "persistence" | "cleanup" | "transport";
  code: string;
  message: string;
};

export type AgentDiagnostics = {
  primary?: AgentDiagnostic;
  secondary?: AgentSecondaryDiagnostic[];
  failure_code?: string;
  failure_message?: string;
};

export function mergeAgentDiagnostics(
  primary: AgentDiagnostic | undefined,
  secondary: AgentSecondaryDiagnostic[]
): AgentDiagnostics {
  const effectivePrimary = primary ?? secondary[0];
  const remainingSecondary = primary ? secondary : secondary.slice(1);
  return {
    ...(effectivePrimary ? { primary: effectivePrimary } : {}),
    secondary: remainingSecondary,
    ...(effectivePrimary
      ? {
          failure_code: effectivePrimary.code,
          failure_message: effectivePrimary.message
        }
      : {})
  };
}

export function primaryDiagnosticFromLegacy(input:
  | {
      primary?: AgentDiagnostic;
      failure_code?: string;
      failure_message?: string;
    }
  | undefined
): AgentDiagnostic | undefined {
  if (input?.primary) {
    return input.primary;
  }
  if (!input?.failure_code) {
    return undefined;
  }
  return {
    code: input.failure_code,
    message: input.failure_message ?? input.failure_code
  };
}
