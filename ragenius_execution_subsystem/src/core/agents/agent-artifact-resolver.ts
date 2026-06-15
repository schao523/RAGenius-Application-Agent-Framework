import { AppError } from "../errors/app-error.js";
import { ArtifactResolver } from "../artifacts/artifact-resolver.js";
import { getArtifactConsumerSpec } from "../artifacts/artifact-consumption-registry.js";
import type {
  ArtifactConsumptionMode,
  ResolvedArtifact
} from "../artifacts/artifact-consumption.types.js";
import type { ArtifactStore } from "../tools/providers/artifact-store.js";
import type { AgentArtifactRef } from "../../api/schemas/execution-request.schema.js";

import type { AgentBackend } from "./agent-provider.js";

type ResolvedAgentPayload = ResolvedArtifact["payload"] & {
  inline_truncated?: boolean;
  original_inline_bytes?: number;
};

export type ResolvedAgentArtifact = Omit<ResolvedArtifact, "payload"> & {
  role: AgentArtifactRef["role"];
  requested_reuse_mode: AgentArtifactRef["reuse_mode"];
  payload: ResolvedAgentPayload;
};

export interface AgentArtifactResolverInput {
  appId: string;
  sessionId: string;
  backend: AgentBackend;
  refs: AgentArtifactRef[];
}

export interface AgentArtifactResolverOptions {
  maxInlineTextBytes?: number;
}

const DEFAULT_MAX_INLINE_TEXT_BYTES = 64 * 1024;

const backendSupportedModes: Record<AgentBackend, ArtifactConsumptionMode[]> = {
  codex_cli: ["file_backed", "inline_text", "metadata_only"],
  openclaw_cli: ["file_backed", "inline_text", "binary_payload", "metadata_only"]
};

function appError(
  code: string,
  message: string,
  details: Record<string, unknown>
): AppError {
  return new AppError({
    code,
    message,
    errorClass: "validation",
    httpStatus: 400,
    details,
    recoverable: true,
    suggestedAction: "Select a compatible artifact for this agent execution."
  });
}

function truncateInlineText(
  payload: ResolvedArtifact["payload"],
  maxBytes: number
): ResolvedAgentPayload {
  if (typeof payload.text_content !== "string") {
    return { ...payload };
  }

  const originalBytes = Buffer.byteLength(payload.text_content, "utf-8");
  if (originalBytes <= maxBytes) {
    return {
      ...payload,
      inline_truncated: false,
      original_inline_bytes: originalBytes
    };
  }

  return {
    ...payload,
    text_content: Buffer.from(payload.text_content, "utf-8")
      .subarray(0, maxBytes)
      .toString("utf-8"),
    inline_truncated: true,
    original_inline_bytes: originalBytes
  };
}

export class AgentArtifactResolver {
  private readonly resolver: ArtifactResolver;
  private readonly maxInlineTextBytes: number;

  constructor(
    private readonly artifactStore: ArtifactStore,
    options?: AgentArtifactResolverOptions
  ) {
    this.resolver = new ArtifactResolver(artifactStore);
    this.maxInlineTextBytes =
      typeof options?.maxInlineTextBytes === "number"
        ? options.maxInlineTextBytes
        : DEFAULT_MAX_INLINE_TEXT_BYTES;
  }

  async resolve(input: AgentArtifactResolverInput): Promise<ResolvedAgentArtifact[]> {
    const resolved: ResolvedAgentArtifact[] = [];

    for (const ref of input.refs) {
      resolved.push(await this.resolveOne(input, ref));
    }

    return resolved;
  }

  private async resolveOne(
    input: AgentArtifactResolverInput,
    ref: AgentArtifactRef
  ): Promise<ResolvedAgentArtifact> {
    const artifact = await this.loadOwnedArtifact(input, ref);
    const spec = getArtifactConsumerSpec(artifact.artifact_type);

    if (!spec || spec.reusable !== true) {
      throw appError(
        "AGENT_ARTIFACT_TYPE_UNSUPPORTED",
        "Artifact type is not reusable by agent execution.",
        {
          artifact_id: ref.artifact_id,
          artifact_type: artifact.artifact_type
        }
      );
    }

    if (!spec.supported_consumption_modes.includes(ref.reuse_mode)) {
      throw appError(
        "ARTIFACT_CONSUMPTION_MODE_UNSUPPORTED",
        "Artifact does not support the requested reuse mode.",
        {
          artifact_id: ref.artifact_id,
          artifact_type: artifact.artifact_type,
          requested_reuse_mode: ref.reuse_mode,
          supported_modes: spec.supported_consumption_modes
        }
      );
    }

    if (!backendSupportedModes[input.backend].includes(ref.reuse_mode)) {
      throw appError(
        "AGENT_ARTIFACT_MODE_UNSUPPORTED",
        "Agent backend does not support the requested artifact reuse mode.",
        {
          artifact_id: ref.artifact_id,
          backend: input.backend,
          requested_reuse_mode: ref.reuse_mode,
          supported_modes: backendSupportedModes[input.backend]
        }
      );
    }

    const sharedResolved = await this.resolver.resolve(input.appId, ref.artifact_id, {
      requiredMode: ref.reuse_mode
    });

    return {
      ...sharedResolved,
      role: ref.role,
      requested_reuse_mode: ref.reuse_mode,
      payload: truncateInlineText(sharedResolved.payload, this.maxInlineTextBytes)
    };
  }

  private async loadOwnedArtifact(
    input: AgentArtifactResolverInput,
    ref: AgentArtifactRef
  ) {
    let artifact;
    try {
      artifact = await this.artifactStore.load(input.appId, ref.artifact_id);
    } catch (error) {
      throw appError("ARTIFACT_NOT_FOUND", "Artifact was not found for this app.", {
        artifact_id: ref.artifact_id,
        app_id: input.appId,
        cause: error instanceof Error ? error.message : String(error)
      });
    }

    if (artifact.status !== "ready") {
      throw appError("ARTIFACT_NOT_READY", "Artifact is not ready for reuse.", {
        artifact_id: ref.artifact_id,
        status: artifact.status
      });
    }

    if (artifact.session_id !== input.sessionId) {
      throw appError(
        "ARTIFACT_SESSION_MISMATCH",
        "Artifact does not belong to the current session.",
        {
          artifact_id: ref.artifact_id,
          artifact_session_id: artifact.session_id ?? null,
          requested_session_id: input.sessionId
        }
      );
    }

    return artifact;
  }
}
