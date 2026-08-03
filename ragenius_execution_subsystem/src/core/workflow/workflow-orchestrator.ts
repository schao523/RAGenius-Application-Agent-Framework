import { AppError } from "../errors/app-error.js";
import type { ExecutionContext } from "../execution/execution-context.js";
import type { ToolEngine } from "../tools/tool-engine.js";
import type { ToolRegistry } from "../tools/tool-registry.js";
import {
  toolExecutionProvenanceKey,
  type ToolExecutionProvenance
} from "../tools/tool.types.js";

import type { WorkflowStepDefinition } from "./workflow.types.js";

function resolveReference(
  expression: unknown,
  context: ExecutionContext,
  toolOutput?: Record<string, unknown>
): unknown {
  if (typeof expression !== "string" || !expression.startsWith("$.")) {
    return expression;
  }

  const segments = expression.slice(2).split(".");
  let current: unknown;

  if (segments[0] === "input") {
    current = context.request.input;
    segments.shift();
  } else if (segments[0] === "steps") {
    current = context.stepOutputs;
    segments.shift();
  } else if (segments[0] === "output") {
    current = toolOutput ?? {};
    segments.shift();
  } else {
    return undefined;
  }

  for (const segment of segments) {
    if (
      typeof current !== "object" ||
      current === null ||
      !(segment in current)
    ) {
      return undefined;
    }

    current = (current as Record<string, unknown>)[segment];
  }

  return current;
}

function resolveValue(
  value: unknown,
  context: ExecutionContext,
  toolOutput?: Record<string, unknown>
): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => resolveValue(item, context, toolOutput));
  }

  if (typeof value === "object" && value !== null) {
    const result: Record<string, unknown> = {};
    for (const [key, nestedValue] of Object.entries(value)) {
      result[key] = resolveValue(nestedValue, context, toolOutput);
    }
    return result;
  }

  return resolveReference(value, context, toolOutput);
}

function mapInput(
  step: WorkflowStepDefinition,
  context: ExecutionContext
): Record<string, unknown> {
  const mapping = step.inputMapping ?? {};
  const result: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(mapping)) {
    result[key] = resolveValue(value, context);
  }

  return result;
}

function mapOutput(
  step: WorkflowStepDefinition,
  context: ExecutionContext,
  output: Record<string, unknown>
): Record<string, unknown> {
  const mapping = step.outputMapping ?? {};
  const result: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(mapping)) {
    result[key] = resolveValue(value, context, output);
  }

  return result;
}

export class WorkflowOrchestrator {
  constructor(
    private readonly toolRegistry: ToolRegistry,
    private readonly toolEngine: ToolEngine
  ) {}

  async execute(context: ExecutionContext): Promise<Record<string, unknown>> {
    const workflow = context.skill?.workflowDefinition;
    if (!workflow) {
      throw new AppError({
        code: "WORKFLOW_NOT_FOUND",
        message: "Skill workflow definition is missing.",
        errorClass: "workflow",
        httpStatus: 500,
        recoverable: false,
        suggestedAction: "Register a valid workflow definition."
      });
    }

    const stepsById = new Map(
      workflow.steps.map((step) => [step.id, step] as const)
    );
    let currentStep = workflow.steps[0];

    while (currentStep) {
      if (currentStep.type === "end") {
        break;
      }

      let nextStepId = currentStep.on?.success;

      if (currentStep.type === "validation") {
        this.runValidationStep(currentStep, context);
      } else if (currentStep.type === "local_decision") {
        nextStepId = this.runLocalDecisionStep(currentStep, context);
      } else if (currentStep.type === "service_call") {
        const serviceId = currentStep.serviceId ?? "";
        const tool = this.toolRegistry.get(serviceId);
        const input = mapInput(currentStep, context);
        const output = await this.toolEngine.execute(
          tool,
          input,
          this.buildToolExecutionOptions(context)
        );
        context.toolResults[currentStep.id] = output;
        const mappedOutput = mapOutput(currentStep, context, output);
        context.stepOutputs[currentStep.id] = {
          ...(this.getExecutionStepMetadata(output)
            ? { execution: this.getExecutionStepMetadata(output) }
            : {}),
          output: mappedOutput,
          raw_output: output
        };
      } else if (currentStep.type === "tool_call") {
        const tool = this.toolRegistry.get(currentStep.toolId ?? "");
        const input = mapInput(currentStep, context);
        const output = await this.toolEngine.execute(
          tool,
          input,
          this.buildToolExecutionOptions(context)
        );
        context.toolResults[currentStep.id] = output;
        const mappedOutput = mapOutput(currentStep, context, output);
        context.stepOutputs[currentStep.id] = {
          ...(this.getExecutionStepMetadata(output)
            ? { execution: this.getExecutionStepMetadata(output) }
            : {}),
          output: mappedOutput,
          raw_output: output
        };
      }

      currentStep = nextStepId ? stepsById.get(nextStepId) : undefined;
    }

    const stepOutputs = Object.values(context.stepOutputs);
    const finalOutput = (
      stepOutputs.length > 0 ? stepOutputs[stepOutputs.length - 1]?.output : {}
    ) as Record<string, unknown>;
    return finalOutput;
  }

  private runValidationStep(
    step: WorkflowStepDefinition,
    context: ExecutionContext
  ): void {
    if (step.action === "validate_prompt") {
      const prompt = context.request.input.prompt;
      if (typeof prompt !== "string" || prompt.trim().length === 0) {
        throw new AppError({
          code: "VALIDATION_ERROR",
          message: "Prompt must not be empty.",
          errorClass: "validation",
          httpStatus: 400,
          details: { path: "input.prompt" },
          recoverable: true,
          suggestedAction: "Provide a non-empty prompt."
        });
      }
    }
  }

  private runLocalDecisionStep(
    step: WorkflowStepDefinition,
    context: ExecutionContext
  ): string | undefined {
    const input = mapInput(step, context);

    if (step.action === "is_truthy") {
      const decision = Boolean(input.value);
      context.stepOutputs[step.id] = {
        output: {
          decision
        },
        raw_output: input
      };
      return decision ? step.on?.true : step.on?.false;
    }

    throw new AppError({
      code: "WORKFLOW_STEP_NOT_IMPLEMENTED",
      message: "Local decision action is not implemented.",
      errorClass: "workflow",
      httpStatus: 500,
      details: {
        step_id: step.id,
        action: step.action
      },
      recoverable: false,
      suggestedAction: "Register a supported local decision action."
    });
  }

  private buildToolExecutionOptions(
    context: ExecutionContext
  ): {
    appId: string;
    sessionId?: string;
    confirmed?: boolean;
    executionId?: string | null;
    skillId?: string;
    permissionPolicies?: ExecutionContext["permissionPolicies"];
  } {
    const options: {
      appId: string;
      sessionId?: string;
      confirmed?: boolean;
      executionId?: string | null;
      skillId?: string;
      permissionPolicies?: ExecutionContext["permissionPolicies"];
    } = {
      appId: context.request.app_id,
      sessionId: context.request.session_id,
      confirmed: context.confirmed,
      ...(context.executionId !== null ? { executionId: context.executionId } : {}),
      ...(typeof context.skill?.id === "string" ? { skillId: context.skill.id } : {})
    };

    if (context.permissionPolicies && context.permissionPolicies.length > 0) {
      options.permissionPolicies = context.permissionPolicies;
    }

    return options;
  }

  private getExecutionStepMetadata(
    output: Record<string, unknown>
  ): ToolExecutionProvenance | undefined {
    return output[toolExecutionProvenanceKey] as
      | ToolExecutionProvenance
      | undefined;
  }
}
