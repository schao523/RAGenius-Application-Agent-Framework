import type { ExecuteAgentRequest } from "../../api/schemas/execution-request.schema.js";
import type { ArtifactStore } from "../tools/providers/artifact-store.js";
export type AgentOutputPersistenceSpec = {
  output_id: string;
  display_name: string;
  media_type: string;
  purpose?: "answer" | "artifact" | "diagnostic";
  required?: boolean;
  persist_as_artifact?: boolean;
  artifact_type?: "agent_output";
  artifact_role?: "final" | "intermediate" | "debug";
};

export type VerifiedAgentOutput = {
  output_id?: string;
  workspace_relative_path: string;
  workspace_absolute_path: string;
  required?: boolean;
  exists?: boolean;
  verified?: boolean;
  media_type?: string;
  size_bytes?: number;
  sha256?: string;
};

export type PersistedAgentOutputArtifact = {
  artifact_id: string;
  artifact_type: "agent_output";
  display_name: string;
  mime_type?: string;
};

export interface AgentOutputArtifactPersisterDependencies {
  readOutputBytes: (workspaceAbsolutePath: string) => Promise<Buffer>;
}

export class AgentOutputArtifactPersister {
  constructor(
    private readonly artifactStore: ArtifactStore,
    private readonly dependencies: AgentOutputArtifactPersisterDependencies
  ) {}

  async persist(input: {
    request: ExecuteAgentRequest;
    executionId: string;
    output: AgentOutputPersistenceSpec;
    verification: VerifiedAgentOutput;
  }): Promise<PersistedAgentOutputArtifact> {
    const bytes = await this.dependencies.readOutputBytes(
      input.verification.workspace_absolute_path
    );
    return this.saveBytes(input, bytes, {
      output_id: input.output.output_id,
      role: input.output.artifact_role ?? "final",
      workspace_relative_path: input.verification.workspace_relative_path,
      size_bytes: input.verification.size_bytes,
      sha256: input.verification.sha256,
      media_type: input.output.media_type
    });
  }

  async persistText(input: {
    request: ExecuteAgentRequest;
    executionId: string;
    output: AgentOutputPersistenceSpec;
    text: string;
  }): Promise<PersistedAgentOutputArtifact> {
    const bytes = Buffer.from(input.text, "utf8");
    return this.saveBytes(input, bytes, {
      output_id: input.output.output_id,
      role: input.output.artifact_role ?? "final",
      capture_source: "interactive_final_response",
      size_bytes: bytes.byteLength,
      media_type: input.output.media_type
    });
  }

  private async saveBytes(
    input: {
      request: ExecuteAgentRequest;
      executionId: string;
      output: AgentOutputPersistenceSpec;
    },
    bytes: Buffer,
    content: Record<string, unknown>
  ): Promise<PersistedAgentOutputArtifact> {
    const isTextOutput =
      input.output.media_type.startsWith("text/") ||
      input.output.media_type === "application/json" ||
      input.output.media_type === "application/markdown";
    const saved = await this.artifactStore.save(
      input.request.app_id,
      "agent_output",
      input.output.display_name,
      isTextOutput
        ? {
            ...content,
            content: bytes.toString("utf-8")
          }
        : {
            ...content,
            content: bytes.toString("base64"),
            content_encoding: "base64"
          },
      {
        sessionId: input.request.session_id,
        executionId: input.executionId,
        sourceSkillId: input.request.agent_backend,
        providerOrigin: input.request.agent_backend,
        mimeType: input.output.media_type,
        summary: `Agent output from ${input.request.agent_backend}`,
        ...(isTextOutput
          ? { fileTextContent: bytes.toString("utf-8") }
          : { fileBytes: bytes })
      }
    );

    return {
      artifact_id: String(saved.artifact_id),
      artifact_type: "agent_output",
      display_name: String(saved.display_name),
      ...(typeof saved.mime_type === "string" ? { mime_type: saved.mime_type } : {})
    };
  }
}
