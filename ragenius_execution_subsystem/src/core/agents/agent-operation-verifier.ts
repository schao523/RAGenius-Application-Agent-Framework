import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";

import type { AgentProviderExecutionContext } from "./agent-provider-context.js";
import type { OperationVerification } from "./codex-cli-types.js";

export type TrustedOperationVerification = OperationVerification & {
  verifier: "execution_subsystem_adapter";
  checked_at: string;
};

export type AgentVerificationInput = {
  request: ExecuteAgentRequest;
  context: AgentProviderExecutionContext;
  reportedVerification: OperationVerification[];
};

export interface AgentOperationVerifier {
  readonly id: string;
  supports(input: AgentVerificationInput): boolean;
  verify(input: AgentVerificationInput): Promise<TrustedOperationVerification[]>;
}

export class AgentOperationVerifierRegistry {
  constructor(private readonly verifiers: AgentOperationVerifier[] = []) {}

  async verify(
    input: AgentVerificationInput
  ): Promise<TrustedOperationVerification[]> {
    const results: TrustedOperationVerification[] = [];
    for (const verifier of this.verifiers) {
      if (verifier.supports(input)) {
        results.push(...await verifier.verify(input));
      }
    }
    return results;
  }
}
