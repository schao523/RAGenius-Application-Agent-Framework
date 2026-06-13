import type {
  ArtifactConsumerSpec,
  ArtifactConsumptionMode
} from "./artifact-consumption.types.js";

function defineArtifactConsumerSpec(
  artifact_type: string,
  default_consumption_mode: ArtifactConsumptionMode,
  supported_consumption_modes: ArtifactConsumptionMode[],
  eligible_consumers: string[],
  picker_visibility: "selectable" | "hidden" = "selectable",
  reusable = true
): ArtifactConsumerSpec {
  return {
    artifact_type,
    default_consumption_mode,
    supported_consumption_modes,
    reusable,
    picker_visibility,
    eligible_consumers
  };
}

const registry = new Map<string, ArtifactConsumerSpec>([
  [
    "chat_export",
    defineArtifactConsumerSpec(
      "chat_export",
      "file_backed",
      ["file_backed", "inline_text", "binary_payload", "metadata_only"],
      ["export", "future_markdown_processors", "gmail_attachments"]
    )
  ],
  [
    "google_drive_export",
    defineArtifactConsumerSpec(
      "google_drive_export",
      "binary_payload",
      ["binary_payload", "file_backed", "metadata_only"],
      ["gmail_attachments", "export"]
    )
  ],
  [
    "file_inventory",
    defineArtifactConsumerSpec(
      "file_inventory",
      "metadata_only",
      ["metadata_only", "inline_text"],
      ["debug", "future_audit_report_flows"]
    )
  ],
  [
    "notebooklm_report",
    defineArtifactConsumerSpec(
      "notebooklm_report",
      "file_backed",
      ["file_backed", "inline_text", "metadata_only"],
      ["export", "future_markdown_processors"]
    )
  ],
  [
    "notebooklm_slide_deck",
    defineArtifactConsumerSpec(
      "notebooklm_slide_deck",
      "file_backed",
      ["file_backed", "metadata_only"],
      ["export"]
    )
  ],
  [
    "notebooklm_video",
    defineArtifactConsumerSpec(
      "notebooklm_video",
      "file_backed",
      ["file_backed", "metadata_only"],
      ["export"]
    )
  ]
]);

export function getArtifactConsumerSpec(
  artifactType: string
): ArtifactConsumerSpec | undefined {
  return registry.get(artifactType);
}
