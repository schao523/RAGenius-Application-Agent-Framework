export type WorkflowStepType =
  | "validation"
  | "tool_call"
  | "local_decision"
  | "service_call"
  | "internal_workflow"
  | "saga"
  | "end";

export interface WorkflowTransitions {
  success?: string;
  failure?: string;
  partial?: string;
  requires_confirmation?: string;
  true?: string;
  false?: string;
}

export interface WorkflowRetryPolicy {
  max: number;
  backoffMs: number;
}

export interface WorkflowStepDefinition {
  id: string;
  type: WorkflowStepType;
  action?: string;
  serviceId?: string;
  toolId?: string;
  inputMapping?: Record<string, unknown>;
  outputMapping?: Record<string, unknown>;
  retry?: WorkflowRetryPolicy;
  on?: WorkflowTransitions;
}

export interface WorkflowDefinition {
  steps: WorkflowStepDefinition[];
}
