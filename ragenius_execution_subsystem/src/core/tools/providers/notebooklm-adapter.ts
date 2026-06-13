import type { NotebookLmProviderConfig } from "../../../config/provider-config.js";
import { AppError } from "../../errors/app-error.js";
import { ArtifactStore } from "./artifact-store.js";

import { executeNotebookLmBridge } from "./notebooklm-bridge.js";
import {
  type NotebookLmBridgeRequest,
  type NotebookLmBridgeResponse,
  type NotebookLmOperation
} from "./notebooklm-types.js";

export type NotebookLmBridgeExecutor = (
  request: NotebookLmBridgeRequest
) => Promise<NotebookLmBridgeResponse>;

export class NotebookLmAdapter {
  private readonly executor: NotebookLmBridgeExecutor;
  private readonly artifactStore: ArtifactStore | undefined;

  constructor(
    private readonly config: NotebookLmProviderConfig,
    executor?: NotebookLmBridgeExecutor,
    dependencies: {
      artifactStore?: ArtifactStore;
    } = {}
  ) {
    this.executor =
      executor ??
      ((request) => executeNotebookLmBridge(this.config, request));
    this.artifactStore = dependencies.artifactStore;
  }

  async execute(
    operation: NotebookLmOperation,
    input: Record<string, unknown>,
    options?: {
      appId: string;
      sessionId?: string;
      confirmed?: boolean;
      executionId?: string | null;
      skillId?: string;
    }
  ): Promise<Record<string, unknown>> {
    if (!this.config.enabled) {
      throw new AppError({
        code: "NOTEBOOKLM_DISABLED",
        message: "NotebookLM adapter is disabled.",
        errorClass: "permission",
        httpStatus: 403,
        details: { operation },
        recoverable: false,
        suggestedAction: "Enable the NotebookLM adapter in runtime config."
      });
    }

    if (!this.config.allowedOperations.includes(operation)) {
      throw new AppError({
        code: "NOTEBOOKLM_OPERATION_NOT_ALLOWED",
        message: "NotebookLM operation is not allowlisted.",
        errorClass: "permission",
        httpStatus: 403,
        details: { operation },
        recoverable: false,
        suggestedAction: "Use an allowlisted NotebookLM operation."
      });
    }

    const resolvedInput = await this.resolveNotebookReference(operation, input);
    const argumentsPayload = this.applyOperationDefaults(operation, resolvedInput);
    const artifactContextInput = {
      ...argumentsPayload,
      ...(typeof input.notebookTitle === "string" && input.notebookTitle.trim().length > 0
        ? { notebookTitle: input.notebookTitle.trim() }
        : {})
    };
    const providerResult = await this.performBridgeRequest(operation, argumentsPayload);
    return this.maybePersistArtifact(
      operation,
      artifactContextInput,
      providerResult,
      options
    );
  }

  private applyOperationDefaults(
    operation: NotebookLmOperation,
    input: Record<string, unknown>
  ): Record<string, unknown> {
    if (
      operation !== "generate_report" &&
      operation !== "generate_slide_deck" &&
      operation !== "generate_video"
    ) {
      return input;
    }

    const payload = { ...input };
    if (payload.waitForCompletion === undefined) {
      payload.waitForCompletion = this.config.generationDefaults.waitForCompletion;
    }
    if (payload.persistArtifacts === undefined) {
      payload.persistArtifacts = this.config.generationDefaults.persistArtifacts;
    }

    return payload;
  }

  private async resolveNotebookReference(
    operation: NotebookLmOperation,
    input: Record<string, unknown>
  ): Promise<Record<string, unknown>> {
    if (!this.requiresNotebookReference(operation)) {
      return input;
    }

    const notebookId =
      typeof input.notebookId === "string" && input.notebookId.trim().length > 0
        ? input.notebookId.trim()
        : undefined;
    if (notebookId) {
      const { notebookTitle: _notebookTitle, ...rest } = input;
      return {
        ...rest,
        notebookId
      };
    }

    const notebookTitle =
      typeof input.notebookTitle === "string" &&
      input.notebookTitle.trim().length > 0
        ? input.notebookTitle.trim()
        : undefined;
    if (!notebookTitle) {
      throw new AppError({
        code: "NOTEBOOKLM_NOTEBOOK_REFERENCE_REQUIRED",
        message: "NotebookLM operations require notebookId or notebookTitle.",
        errorClass: "validation",
        httpStatus: 400,
        details: { operation },
        recoverable: true,
        suggestedAction: "Provide notebookId or notebookTitle and retry."
      });
    }

    const response = await this.performBridgeRequest("list_notebooks", {});

    const notebooks = Array.isArray(response.notebooks)
      ? response.notebooks
      : [];
    const matches = notebooks.filter(
      (notebook) =>
        notebook &&
        typeof notebook === "object" &&
        typeof notebook.title === "string" &&
        notebook.title === notebookTitle &&
        typeof notebook.id === "string"
    ) as Array<{ id: string; title: string }>;

    if (matches.length === 0) {
      throw new AppError({
        code: "NOTEBOOKLM_NOTEBOOK_NOT_FOUND",
        message: "NotebookLM notebook title could not be resolved.",
        errorClass: "validation",
        httpStatus: 404,
        details: { notebook_title: notebookTitle, operation },
        recoverable: true,
        suggestedAction: "Provide a valid notebookTitle or notebookId and retry."
      });
    }

    if (matches.length > 1) {
      throw new AppError({
        code: "NOTEBOOKLM_NOTEBOOK_TITLE_AMBIGUOUS",
        message: "NotebookLM notebook title is ambiguous.",
        errorClass: "validation",
        httpStatus: 409,
        details: {
          notebook_title: notebookTitle,
          operation,
          candidates: matches.map((notebook) => ({
            id: notebook.id,
            title: notebook.title
          }))
        },
        recoverable: true,
        suggestedAction: "Provide notebookId instead of notebookTitle and retry."
      });
    }

    const resolvedMatch = matches[0];
    if (!resolvedMatch) {
      throw new AppError({
        code: "NOTEBOOKLM_NOTEBOOK_NOT_FOUND",
        message: "NotebookLM notebook title could not be resolved.",
        errorClass: "validation",
        httpStatus: 404,
        details: { notebook_title: notebookTitle, operation },
        recoverable: true,
        suggestedAction: "Provide a valid notebookTitle or notebookId and retry."
      });
    }

    const { notebookTitle: _notebookTitle, ...rest } = input;
    return {
      ...rest,
      notebookId: resolvedMatch.id
    };
  }

  private requiresNotebookReference(operation: NotebookLmOperation): boolean {
    return (
      operation === "list_sources" ||
      operation === "ask" ||
      operation === "poll_artifact_task" ||
      operation === "add_source_text" ||
      operation === "add_source_file" ||
      operation === "add_source_url" ||
      operation === "generate_report" ||
      operation === "generate_slide_deck" ||
      operation === "generate_video"
    );
  }

  private async performBridgeRequest(
    operation: NotebookLmOperation,
    argumentsPayload: Record<string, unknown>
  ): Promise<Record<string, unknown>> {
    try {
      const response = await this.executor({
        operation,
        arguments: argumentsPayload
      });

      if (!response.ok) {
        throw new AppError({
          code: response.error.code,
          message: response.error.message,
          errorClass: "tool",
          httpStatus: 502,
          details: response.error.details,
          recoverable: response.error.recoverable,
          suggestedAction: response.error.suggested_action
        });
      }

      return response.result;
    } catch (error) {
      if (error instanceof AppError) {
        throw error;
      }

      throw new AppError({
        code: "NOTEBOOKLM_BRIDGE_FAILED",
        message: "NotebookLM bridge execution failed.",
        errorClass: "tool",
        httpStatus: 502,
        details: {
          operation,
          cause: error instanceof Error ? error.message : String(error),
          python_command: this.config.pythonCommand,
          bridge_script: this.config.bridgeScript,
          auth_mode: this.config.authMode,
          profile: this.config.profile ?? null,
          storage_path: this.config.storagePath ?? null
        },
        recoverable: false,
        suggestedAction:
          "Inspect NotebookLM bridge configuration and process output, then retry."
      });
    }
  }

  private async maybePersistArtifact(
    operation: NotebookLmOperation,
    input: Record<string, unknown>,
    result: Record<string, unknown>,
    options?: {
      appId: string;
      sessionId?: string;
      confirmed?: boolean;
      executionId?: string | null;
      skillId?: string;
    }
  ): Promise<Record<string, unknown>> {
    if (!this.shouldPersistArtifact(operation, input, result)) {
      return result;
    }

    if (!this.artifactStore || !options?.appId) {
      return result;
    }

    const artifactKind = String(result.artifact_kind ?? "").trim();
    const artifactType = this.artifactTypeForKind(artifactKind);
    if (!artifactType) {
      return result;
    }

    const displayName = this.buildArtifactDisplayName(operation, input, result);
    const persistencePlan = this.buildPersistencePlan(displayName, result);
    if (!persistencePlan) {
      return result;
    }

    try {
      const storedArtifact = await this.artifactStore.save(
        options.appId,
        artifactType,
        persistencePlan.displayName,
        result,
        {
          ...(typeof options.sessionId === "string"
            ? { sessionId: options.sessionId }
            : {}),
          ...(typeof options.executionId === "string"
            ? { executionId: options.executionId }
            : {}),
          sourceToolId: `adapter.notebooklm.${operation}`,
          ...(typeof options.skillId === "string"
            ? { sourceSkillId: options.skillId }
            : {}),
          summary: this.buildArtifactSummary(artifactKind, input, result),
          providerOrigin: "notebooklm",
          ...(persistencePlan.mimeType ? { mimeType: persistencePlan.mimeType } : {}),
          ...(persistencePlan.fileSourcePath
            ? { fileSourcePath: persistencePlan.fileSourcePath }
            : {}),
          ...(persistencePlan.fileTextContent !== undefined
            ? { fileTextContent: persistencePlan.fileTextContent }
            : {})
        }
      );

      return {
        ...result,
        artifacts: [storedArtifact]
      };
    } catch (error) {
      throw new AppError({
        code: "NOTEBOOKLM_ARTIFACT_PERSIST_FAILED",
        message: "NotebookLM output could not be persisted as an artifact.",
        errorClass: "tool",
        httpStatus: 502,
        details: {
          operation,
          artifact_kind: artifactKind,
          cause: error instanceof Error ? error.message : String(error)
        },
        recoverable: true,
        suggestedAction: "Retry the NotebookLM request or inspect artifact storage."
      });
    }
  }

  private shouldPersistArtifact(
    operation: NotebookLmOperation,
    input: Record<string, unknown>,
    result: Record<string, unknown>
  ): boolean {
    if (
      operation !== "generate_report" &&
      operation !== "generate_slide_deck" &&
      operation !== "generate_video"
    ) {
      return false;
    }

    if (input.persistArtifacts !== true) {
      return false;
    }

    return String(result.status ?? "").toLowerCase() === "completed";
  }

  private artifactTypeForKind(artifactKind: string): string | undefined {
    const normalized = artifactKind.trim().toLowerCase();
    if (normalized === "report") {
      return "notebooklm_report";
    }
    if (normalized === "slide_deck") {
      return "notebooklm_slide_deck";
    }
    if (normalized === "video") {
      return "notebooklm_video";
    }
    return undefined;
  }

  private buildArtifactDisplayName(
    operation: NotebookLmOperation,
    input: Record<string, unknown>,
    result: Record<string, unknown>
  ): string {
    const notebookLabel =
      (typeof input.notebookTitle === "string" && input.notebookTitle.trim().length > 0
        ? input.notebookTitle.trim()
        : typeof input.notebookId === "string" && input.notebookId.trim().length > 0
          ? input.notebookId.trim()
          : typeof result.notebook_id === "string" && result.notebook_id.trim().length > 0
            ? result.notebook_id.trim()
            : "notebooklm").replace(/[<>:"/\\|?*\u0000-\u001F]/g, "-");
    const artifactKind = String(result.artifact_kind ?? "").trim().toLowerCase();
    const extension = this.resolveArtifactExtension(operation, input, result);
    const kindLabel = artifactKind
      ? artifactKind
          .replace(/_/g, " ")
          .replace(/\b\w/g, (value) => value.toUpperCase())
      : "Artifact";
    return `NotebookLM ${kindLabel} - ${notebookLabel}.${extension}`;
  }

  private buildPersistencePlan(
    displayName: string,
    result: Record<string, unknown>
  ):
    | {
        displayName: string;
        mimeType?: string;
        fileSourcePath?: string;
        fileTextContent?: string;
      }
    | undefined {
    const downloadPath =
      typeof result.download_path === "string" && result.download_path.trim().length > 0
        ? result.download_path.trim()
        : undefined;
    const contentMarkdown =
      typeof result.content_markdown === "string" ? result.content_markdown : undefined;
    const mimeType =
      typeof result.mime_type === "string" && result.mime_type.trim().length > 0
        ? result.mime_type.trim()
        : undefined;

    if (downloadPath) {
      return {
        displayName,
        ...(mimeType ? { mimeType } : {}),
        fileSourcePath: downloadPath
      };
    }

    if (contentMarkdown !== undefined) {
      return {
        displayName,
        mimeType: mimeType ?? "text/markdown",
        fileTextContent: contentMarkdown
      };
    }

    return undefined;
  }

  private resolveArtifactExtension(
    operation: NotebookLmOperation,
    input: Record<string, unknown>,
    result: Record<string, unknown>
  ): string {
    const downloadPath =
      typeof result.download_path === "string" && result.download_path.trim().length > 0
        ? result.download_path.trim()
        : undefined;
    const fromPath = downloadPath?.match(/\.([A-Za-z0-9]+)$/)?.[1];
    if (fromPath) {
      return fromPath.toLowerCase();
    }

    const mimeType =
      typeof result.mime_type === "string" ? result.mime_type.trim().toLowerCase() : "";
    if (mimeType === "application/pdf") {
      return "pdf";
    }
    if (
      mimeType ===
      "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ) {
      return "pptx";
    }
    if (mimeType === "video/mp4") {
      return "mp4";
    }

    if (operation === "generate_slide_deck") {
      const outputFormat =
        typeof input.outputFormat === "string" && input.outputFormat.trim().length > 0
          ? input.outputFormat.trim().toLowerCase()
          : undefined;
      if (outputFormat === "pptx" || outputFormat === "pdf") {
        return outputFormat;
      }
    }

    if (operation === "generate_video") {
      return "mp4";
    }

    return "md";
  }

  private buildArtifactSummary(
    artifactKind: string,
    input: Record<string, unknown>,
    result: Record<string, unknown>
  ): string {
    const notebookLabel =
      typeof input.notebookTitle === "string" && input.notebookTitle.trim().length > 0
        ? input.notebookTitle.trim()
        : typeof input.notebookId === "string" && input.notebookId.trim().length > 0
          ? input.notebookId.trim()
          : typeof result.notebook_id === "string" && result.notebook_id.trim().length > 0
            ? result.notebook_id.trim()
            : "the notebook";
    return `NotebookLM ${artifactKind.replace(/_/g, " ")} generated from ${notebookLabel}`;
  }
}
