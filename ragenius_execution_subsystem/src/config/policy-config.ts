export type TemplatePolicyClass =
  | "safe_read"
  | "review_required"
  | "mutation"
  | "external_write"
  | "unsupported";

export interface TemplateFamilyPolicy {
  policyClass: TemplatePolicyClass;
  autoFinalize: boolean;
  requiresReview: boolean;
  requiresConfirmation: boolean;
  inferredTools: string[];
  requiredPermissions: string[];
  requiresArtifactSource?: boolean;
}

export interface ProviderPolicy {
  enabled: boolean;
  reviewRequired: boolean;
  allowedToolIds: string[];
  defaultPermissionMode: "auto_allow" | "require_confirmation" | "restricted";
  requiresArtifactSourceForOutbound?: boolean;
}

export interface ToolPolicy {
  enabled: boolean;
  permissionScopes: string[];
  sideEffecting: boolean;
  requiresConfirmation: boolean;
  requiresArtifactSource?: boolean;
  inputSourcePolicy?: "free_input" | "artifact_only" | "provider_id_only";
}

export interface ArtifactPolicyConfig {
  enforceAppScope: true;
  outboundEligibleArtifactTypes: string[];
  maxArtifactBytesByType?: Record<string, number>;
}

export interface SideEffectPolicyConfig {
  requireConfirmationFor: Array<"mutation" | "external_write" | "outbound_send">;
  alwaysReviewFamilies: string[];
}

export interface AttachmentPolicyConfig {
  sourceMode: "artifact_only";
  maxAttachmentCount: number;
  maxAttachmentBytes: number;
  allowedMimeTypes: string[];
  allowedArtifactTypes: string[];
}

export type FallbackErrorClass =
  | "permission_rejected"
  | "schema_mismatch"
  | "auth_failed"
  | "service_disabled";

export interface ToolFallbackPolicy {
  enabled: boolean;
  strategy: "rest_api" | "adapter";
  allowedErrorClasses: FallbackErrorClass[];
}

export interface FallbackPolicyConfig {
  tools: Record<string, ToolFallbackPolicy>;
}

export interface RuntimePolicyConfig {
  version: string;
  templateFamilies: Record<string, TemplateFamilyPolicy>;
  providers: Record<string, ProviderPolicy>;
  tools: Record<string, ToolPolicy>;
  artifacts: ArtifactPolicyConfig;
  sideEffects: SideEffectPolicyConfig;
  attachments: AttachmentPolicyConfig;
  fallbacks: FallbackPolicyConfig;
}

export function buildDefaultRuntimePolicyConfig(): RuntimePolicyConfig {
  return {
    version: "1",
    templateFamilies: {
      gmail_attachment_draft_operation: {
        policyClass: "review_required",
        autoFinalize: false,
        requiresReview: true,
        requiresConfirmation: true,
        inferredTools: ["mcp.gmail.create_draft_with_attachments"],
        requiredPermissions: ["external_api.write", "artifact.read"],
        requiresArtifactSource: true
      }
    },
    providers: {
      gmail: {
        enabled: true,
        reviewRequired: true,
        allowedToolIds: [
          "mcp.gmail.search_messages",
          "mcp.gmail.create_draft",
          "mcp.gmail.create_draft_with_attachments",
          "mcp.gmail.send_draft",
          "mcp.gmail.send_message"
        ],
        defaultPermissionMode: "require_confirmation",
        requiresArtifactSourceForOutbound: true
      },
      gdrive: {
        enabled: true,
        reviewRequired: true,
        allowedToolIds: [
          "mcp.gdrive.search_files",
          "mcp.gdrive.download_file_content"
        ],
        defaultPermissionMode: "auto_allow"
      },
      gdocs: {
        enabled: true,
        reviewRequired: true,
        allowedToolIds: ["mcp.gdocs.search_documents"],
        defaultPermissionMode: "auto_allow"
      }
    },
    tools: {
      "mcp.gmail.create_draft_with_attachments": {
        enabled: true,
        permissionScopes: ["external_api.write", "artifact.read"],
        sideEffecting: true,
        requiresConfirmation: true,
        requiresArtifactSource: true,
        inputSourcePolicy: "artifact_only"
      },
      "mcp.gmail.create_draft": {
        enabled: true,
        permissionScopes: ["external_api.write"],
        sideEffecting: true,
        requiresConfirmation: true
      },
      "mcp.gmail.send_draft": {
        enabled: true,
        permissionScopes: ["external_api.write"],
        sideEffecting: true,
        requiresConfirmation: true
      },
      "mcp.gmail.send_message": {
        enabled: true,
        permissionScopes: ["external_api.write"],
        sideEffecting: true,
        requiresConfirmation: true
      },
      "mcp.gdrive.search_files": {
        enabled: true,
        permissionScopes: ["external_api.read"],
        sideEffecting: false,
        requiresConfirmation: false
      },
      "mcp.gdrive.download_file_content": {
        enabled: true,
        permissionScopes: ["external_api.read"],
        sideEffecting: false,
        requiresConfirmation: false
      },
      "save_artifact": {
        enabled: true,
        permissionScopes: ["artifact.write"],
        sideEffecting: false,
        requiresConfirmation: false
      },
      "load_artifact": {
        enabled: true,
        permissionScopes: ["artifact.read"],
        sideEffecting: false,
        requiresConfirmation: false
      }
    },
    artifacts: {
      enforceAppScope: true,
      outboundEligibleArtifactTypes: ["google_drive_export", "chat_export"]
    },
    sideEffects: {
      requireConfirmationFor: ["mutation", "external_write", "outbound_send"],
      alwaysReviewFamilies: [
        "gmail_attachment_draft_operation",
        "gmail_draft_operation",
        "gmail_send_draft_operation",
        "gmail_send_message_operation"
      ]
    },
    attachments: {
      sourceMode: "artifact_only",
      maxAttachmentCount: 3,
      maxAttachmentBytes: 5_000_000,
      allowedMimeTypes: ["application/pdf", "text/plain", "text/markdown"],
      allowedArtifactTypes: ["google_drive_export", "chat_export"]
    },
    fallbacks: {
      tools: {
        "mcp.gdrive.download_file_content": {
          enabled: true,
          strategy: "rest_api",
          allowedErrorClasses: ["permission_rejected"]
        },
        "mcp.gmail.create_draft": {
          enabled: true,
          strategy: "rest_api",
          allowedErrorClasses: ["permission_rejected"]
        },
        "mcp.gmail.create_draft_with_attachments": {
          enabled: true,
          strategy: "rest_api",
          allowedErrorClasses: ["permission_rejected"]
        }
      }
    }
  };
}
