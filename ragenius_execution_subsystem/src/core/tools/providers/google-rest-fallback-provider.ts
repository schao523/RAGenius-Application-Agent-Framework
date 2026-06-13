import { AppError } from "../../errors/app-error.js";
import type { McpServerRuntimeConfig } from "../../../config/mcp-config.js";

export class GoogleRestFallbackProvider {
  async downloadDriveFileContent(
    configured: McpServerRuntimeConfig,
    input: Record<string, unknown>
  ): Promise<Record<string, unknown>> {
    const authToken = configured.authToken;
    if (!authToken) {
      throw new AppError({
        code: "MCP_PROVIDER_AUTH_FAILED",
        message: "Drive REST fallback requires an OAuth token.",
        errorClass: "tool",
        httpStatus: 502,
        details: { provider_id: configured.id, auth_env: configured.authTokenEnv },
        recoverable: false,
        suggestedAction: "Set the configured MCP auth token environment variable."
      });
    }

    const fileId = String(input.fileId ?? "").trim();
    if (!fileId) {
      throw new AppError({
        code: "VALIDATION_ERROR",
        message: "Drive download requires a fileId.",
        errorClass: "validation",
        httpStatus: 400,
        details: { issue: "Required", path: "fileId" },
        recoverable: true,
        suggestedAction: "Provide a valid Drive file id."
      });
    }

    const metadata = await this.fetchDriveFileMetadata(authToken, fileId);
    const exportMimeType = String(input.exportMimeType ?? "").trim();
    const isNativeGoogleFile = metadata.mimeType.startsWith(
      "application/vnd.google-apps."
    );
    const effectiveMimeType =
      isNativeGoogleFile && exportMimeType.length > 0
        ? exportMimeType
        : isNativeGoogleFile
          ? "text/plain"
          : metadata.mimeType;

    const downloadUrl = isNativeGoogleFile
      ? `https://www.googleapis.com/drive/v3/files/${encodeURIComponent(fileId)}/export?mimeType=${encodeURIComponent(
          effectiveMimeType
        )}`
      : `https://www.googleapis.com/drive/v3/files/${encodeURIComponent(fileId)}?alt=media`;
    const response = await fetch(downloadUrl, {
      headers: {
        Authorization: `Bearer ${authToken}`
      },
      method: "GET"
    });

    if (!response.ok) {
      const responseBody = await response.text().catch(() => "");
      throw new AppError({
        code: "MCP_TOOL_CALL_FAILED",
        message: "Drive REST fallback download failed.",
        errorClass: "tool",
        httpStatus: 502,
        details: {
          file_id: fileId,
          status: response.status,
          response_body: responseBody
        },
        recoverable: true,
        suggestedAction:
          "Verify the Drive file permissions and retry the download."
      });
    }

    const bytes = Buffer.from(await response.arrayBuffer());
    return {
      file_id: fileId,
      name: metadata.name,
      mime_type: effectiveMimeType,
      content: bytes.toString("base64"),
      content_encoding: "base64",
      auth_context: this.buildAuthContext(configured)
    };
  }

  async createGmailDraft(
    configured: McpServerRuntimeConfig,
    input: Record<string, unknown>
  ): Promise<Record<string, unknown>> {
    const authToken = configured.authToken;
    if (!authToken) {
      throw new AppError({
        code: "MCP_PROVIDER_AUTH_FAILED",
        message: "Gmail REST fallback requires an OAuth token.",
        errorClass: "tool",
        httpStatus: 502,
        details: { provider_id: configured.id, auth_env: configured.authTokenEnv },
        recoverable: false,
        suggestedAction: "Set the configured MCP auth token environment variable."
      });
    }

    const to = this.formatRecipients(input.to);
    const subject = String(input.subject ?? "").trim();
    const body = String(input.body ?? "");
    if (!to || !subject) {
      throw new AppError({
        code: "VALIDATION_ERROR",
        message: "Gmail draft creation requires recipient and subject.",
        errorClass: "validation",
        httpStatus: 400,
        details: { issue: "Required", path: !to ? "to" : "subject" },
        recoverable: true,
        suggestedAction: "Provide valid Gmail draft input."
      });
    }

    const rawMessage = this.buildGmailRawMessage(input);
    const response = await fetch(
      "https://gmail.googleapis.com/gmail/v1/users/me/drafts",
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${authToken}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          message: {
            raw: rawMessage
          }
        })
      }
    );

    if (!response.ok) {
      const responseBody = await response.text().catch(() => "");
      throw new AppError({
        code: "MCP_TOOL_CALL_FAILED",
        message: "Gmail REST fallback draft creation failed.",
        errorClass: "tool",
        httpStatus: 502,
        details: {
          status: response.status,
          response_body: responseBody
        },
        recoverable: true,
        suggestedAction:
          "Verify Gmail API permissions and retry the draft creation."
      });
    }

    const payload = (await response.json()) as {
      id?: unknown;
      message?: { id?: unknown; threadId?: unknown };
    };
    return {
      id: String(payload.id ?? ""),
      status: "draft_created",
      ...(payload.message?.threadId
        ? { threadId: String(payload.message.threadId) }
        : {}),
      auth_context: this.buildAuthContext(configured)
    };
  }

  private async fetchDriveFileMetadata(
    authToken: string,
    fileId: string
  ): Promise<{ name: string; mimeType: string }> {
    const response = await fetch(
      `https://www.googleapis.com/drive/v3/files/${encodeURIComponent(
        fileId
      )}?fields=id,name,mimeType`,
      {
        headers: {
          Authorization: `Bearer ${authToken}`
        },
        method: "GET"
      }
    );

    if (!response.ok) {
      const responseBody = await response.text().catch(() => "");
      throw new AppError({
        code: "MCP_TOOL_CALL_FAILED",
        message: "Drive REST fallback metadata lookup failed.",
        errorClass: "tool",
        httpStatus: 502,
        details: {
          file_id: fileId,
          status: response.status,
          response_body: responseBody
        },
        recoverable: true,
        suggestedAction:
          "Verify the Drive file permissions and retry the download."
      });
    }

    const payload = (await response.json()) as {
      mimeType?: unknown;
      name?: unknown;
    };
    return {
      name: String(payload.name ?? fileId),
      mimeType: String(payload.mimeType ?? "application/octet-stream")
    };
  }

  private buildGmailRawMessage(input: Record<string, unknown>): string {
    const to = this.formatRecipients(input.to);
    const subject = String(input.subject ?? "").trim();
    const body = String(input.body ?? "");
    const attachments = Array.isArray(input.attachments)
      ? input.attachments
      : [];

    const headers = [`To: ${to}`, `Subject: ${subject}`, "MIME-Version: 1.0"];
    let message: string;

    if (attachments.length === 0) {
      message = [
        ...headers,
        'Content-Type: text/plain; charset="UTF-8"',
        "",
        body
      ].join("\r\n");
    } else {
      const boundary = `ragenius-${Date.now()}-${Math.random()
        .toString(16)
        .slice(2)}`;
      const parts: string[] = [
        ...headers,
        `Content-Type: multipart/mixed; boundary="${boundary}"`,
        "",
        `--${boundary}`,
        'Content-Type: text/plain; charset="UTF-8"',
        "",
        body
      ];

      for (const attachment of attachments) {
        const filename = String(
          (attachment as { filename?: unknown }).filename ?? "attachment"
        );
        const mimeType = String(
          (attachment as { mimeType?: unknown; mime_type?: unknown }).mimeType ??
            (attachment as { mime_type?: unknown }).mime_type ??
            "application/octet-stream"
        );
        const content = String(
          (attachment as { content?: unknown }).content ?? ""
        );
        parts.push(
          `--${boundary}`,
          `Content-Type: ${mimeType}; name="${filename}"`,
          "Content-Transfer-Encoding: base64",
          `Content-Disposition: attachment; filename="${filename}"`,
          "",
          content
        );
      }

      parts.push(`--${boundary}--`, "");
      message = parts.join("\r\n");
    }

    return Buffer.from(message, "utf-8")
      .toString("base64")
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/g, "");
  }

  private buildAuthContext(configured: McpServerRuntimeConfig): Record<string, unknown> {
    return {
      provider_id: configured.id,
      auth_token_env: configured.authTokenEnv ?? null,
      auth_source: "mcp_server_auth_token"
    };
  }

  private formatRecipients(value: unknown): string {
    if (Array.isArray(value)) {
      return value
        .map((entry) => String(entry).trim())
        .filter((entry) => entry.length > 0)
        .join(", ");
    }
    return String(value ?? "").trim();
  }
}
