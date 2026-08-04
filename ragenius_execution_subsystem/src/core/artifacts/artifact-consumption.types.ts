import type { StoredArtifactRecord } from "../tools/providers/artifact-store.js";

export type ArtifactConsumptionMode =
  | "file_backed"
  | "inline_text"
  | "binary_payload"
  | "metadata_only";

export interface ArtifactConsumerSpec {
  artifact_type: string;
  default_consumption_mode: ArtifactConsumptionMode;
  supported_consumption_modes: ArtifactConsumptionMode[];
  reusable: boolean;
  picker_visibility: "selectable" | "hidden";
  eligible_consumers: string[];
}

export interface ArtifactResolvedPayload {
  file_path?: string;
  text_content?: string;
  binary_content_base64?: string;
  mime_type?: string;
  metadata: Record<string, unknown>;
}

export interface ResolvedArtifact {
  artifact_id: string;
  artifact_type: string;
  display_name: string;
  summary?: string;
  app_id: string;
  status: StoredArtifactRecord["status"];
  consumption: {
    default_mode: ArtifactConsumptionMode;
    supported_modes: ArtifactConsumptionMode[];
    resolved_mode: ArtifactConsumptionMode;
  };
  payload: ArtifactResolvedPayload;
  provenance: {
    created_by_execution_id?: string;
    created_by_turn_id?: string;
    source_tool_id?: string;
    source_skill_id?: string;
    provider_origin: string;
  };
}
