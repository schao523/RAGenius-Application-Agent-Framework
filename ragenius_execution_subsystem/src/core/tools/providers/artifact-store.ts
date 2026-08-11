import { randomUUID } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

export interface StoredArtifactRecord {
  [key: string]: unknown;
  artifact_id: string;
  session_id?: string;
  artifact_type: string;
  display_name: string;
  storage_file_name?: string;
  summary?: string;
  app_id: string;
  created_at: string;
  created_by_execution_id?: string;
  created_by_turn_id?: string;
  source_tool_id?: string;
  source_skill_id?: string;
  source_upload_id?: string;
  reviewed?: boolean;
  reviewed_at?: string;
  reviewed_by?: string;
  review_source?: string;
  source_message_ids?: string[];
  content_hash?: string;
  provider_origin: string;
  mime_type?: string;
  size_bytes?: number;
  path: string;
  file_path?: string;
  status: "ready" | "deleted";
  deleted_at?: string;
  content: unknown;
}

export interface ArtifactContentIdentity {
  appId: string;
  sessionId: string;
  sha256: string;
  sizeBytes: number;
  mediaType: string;
}

export type ScopedArtifactFile = {
  artifact_id: string;
  display_name: string;
  mime_type?: string;
  size_bytes: number;
  absolute_path: string;
};

function inferMimeType(name: string, artifactType: string, content: unknown): string | undefined {
  const lowerName = String(name || "").toLowerCase();
  if (lowerName.endsWith(".md")) {
    return "text/markdown";
  }
  if (lowerName.endsWith(".txt")) {
    return "text/plain";
  }
  if (lowerName.endsWith(".json")) {
    return "application/json";
  }
  if (lowerName.endsWith(".pdf")) {
    return "application/pdf";
  }
  if (lowerName.endsWith(".pptx")) {
    return "application/vnd.openxmlformats-officedocument.presentationml.presentation";
  }
  if (lowerName.endsWith(".mp4")) {
    return "video/mp4";
  }
  if (
    content &&
    typeof content === "object" &&
    !Array.isArray(content) &&
    typeof (content as { mime_type?: unknown }).mime_type === "string"
  ) {
    return String((content as { mime_type: string }).mime_type);
  }
  if (artifactType === "file_inventory") {
    return "application/json";
  }
  return undefined;
}

function normalizeMimeType(value: string | undefined): string {
  return String(value || "application/octet-stream")
    .split(";", 1)[0]!
    .trim()
    .toLowerCase();
}

export class ArtifactStore {
  constructor(private readonly rootDir: string) {}

  private resolveStoragePath(value: string): string {
    return path.isAbsolute(value) ? value : path.resolve(value);
  }

  private async canonicalRoot(): Promise<string> {
    const root = this.resolveStoragePath(this.rootDir);
    await fs.mkdir(root, { recursive: true });
    return fs.realpath(root);
  }

  private assertContained(root: string, candidate: string): string {
    const relative = path.relative(root, candidate);
    if (relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative))) {
      return candidate;
    }
    throw new Error("Artifact path escapes the configured storage root.");
  }

  private normalizeStoredPath(value: string | null | undefined): string | undefined {
    const normalized = String(value || "").trim();
    if (!normalized) {
      return undefined;
    }
    return this.resolveStoragePath(normalized);
  }

  private sanitizeFileName(name: string): string {
    const base = path.basename(String(name || "").trim()) || "artifact";
    const sanitized = base.replace(/[<>:"/\\|?*\u0000-\u001F]/g, "-").trim();
    return sanitized || "artifact";
  }

  private inferDisplayName(name: string, artifactType: string): string {
    const safeName = this.sanitizeFileName(name);
    if (safeName && safeName !== "artifact") {
      return safeName;
    }

    const fallbackByType: Record<string, string> = {
      chat_export: "chat-export.md",
      google_drive_export: "drive-export",
      file_inventory: "file-inventory.json"
    };
    return fallbackByType[artifactType] ?? "artifact";
  }

  private inferSummary(
    artifactType: string,
    displayName: string,
    content: unknown
  ): string | undefined {
    if (artifactType === "chat_export") {
      const messageCount =
        content &&
        typeof content === "object" &&
        !Array.isArray(content) &&
        typeof (content as { message_count?: unknown }).message_count === "number"
          ? Number((content as { message_count: number }).message_count)
          : undefined;
      return typeof messageCount === "number"
        ? `Chat export from ${messageCount} selected message${messageCount === 1 ? "" : "s"}`
        : `Chat export: ${displayName}`;
    }

    if (artifactType === "google_drive_export") {
      return `Google Drive export: ${displayName}`;
    }

    if (artifactType === "file_inventory") {
      return `File inventory: ${displayName}`;
    }

    return undefined;
  }

  async save(
    appId: string,
    artifactType: string,
    name: string,
    content: unknown,
    options?: {
      sessionId?: string;
      displayName?: string;
      executionId?: string;
      turnId?: string;
      sourceToolId?: string;
      sourceSkillId?: string;
      sourceUploadId?: string;
      summary?: string;
      providerOrigin?: string;
      mimeType?: string;
      fileSourcePath?: string;
      moveFileSource?: boolean;
      fileTextContent?: string;
      fileBytes?: Buffer;
      reviewed?: boolean;
      reviewedAt?: string;
      reviewedBy?: string;
      reviewSource?: string;
      sourceMessageIds?: string[];
      contentHash?: string;
    }
  ): Promise<Omit<StoredArtifactRecord, "content">> {
    const artifactId = `artifact_${randomUUID().replace(/-/g, "")}`;
    const dir = this.resolveStoragePath(path.join(this.rootDir, appId, artifactType));
    await fs.mkdir(dir, { recursive: true });
    const metadataPath = path.join(dir, `${artifactId}.json`);
    const displayName = this.inferDisplayName(options?.displayName ?? name, artifactType);
    const storageFileName = this.sanitizeFileName(name || displayName);
    const createdAt = new Date().toISOString();
    const mimeType =
      options?.mimeType ?? inferMimeType(displayName, artifactType, content);
    const summary =
      options?.summary ?? this.inferSummary(artifactType, displayName, content);
    let exportFilePath: string | undefined;
    let sizeBytes: number | undefined;
    const fileSourcePath =
      typeof options?.fileSourcePath === "string" &&
      options.fileSourcePath.trim().length > 0
        ? options.fileSourcePath.trim()
        : undefined;
    const fileTextContent =
      typeof options?.fileTextContent === "string"
        ? options.fileTextContent
        : undefined;
    const fileBytes = Buffer.isBuffer(options?.fileBytes)
      ? options.fileBytes
      : undefined;

    if (fileSourcePath) {
      exportFilePath = path.join(dir, `${artifactId}-${storageFileName}`);
      if (options?.moveFileSource) {
        await fs.rename(fileSourcePath, exportFilePath);
      } else {
        await fs.copyFile(fileSourcePath, exportFilePath);
      }
      const stat = await fs.stat(exportFilePath);
      sizeBytes = stat.size;
    } else if (fileBytes) {
      exportFilePath = path.join(dir, `${artifactId}-${storageFileName}`);
      await fs.writeFile(exportFilePath, fileBytes);
      sizeBytes = fileBytes.byteLength;
    } else if (fileTextContent !== undefined) {
      exportFilePath = path.join(dir, `${artifactId}-${storageFileName}`);
      await fs.writeFile(exportFilePath, fileTextContent, "utf-8");
      sizeBytes = Buffer.byteLength(fileTextContent, "utf-8");
    } else if (
      artifactType === "chat_export" &&
      content &&
      typeof content === "object" &&
      !Array.isArray(content) &&
      typeof (content as { content?: unknown }).content === "string"
    ) {
      exportFilePath = path.join(dir, `${artifactId}-${storageFileName}`);
      const fileContent = String((content as { content: string }).content);
      await fs.writeFile(exportFilePath, fileContent, "utf-8");
      sizeBytes = Buffer.byteLength(fileContent, "utf-8");
    } else {
      sizeBytes = Buffer.byteLength(JSON.stringify(content), "utf-8");
    }

    const metadata: StoredArtifactRecord = {
      artifact_id: artifactId,
      ...(typeof options?.sessionId === "string" && options.sessionId.trim().length > 0
        ? { session_id: options.sessionId.trim() }
        : {}),
      artifact_type: artifactType,
      display_name: displayName,
      storage_file_name: storageFileName,
      ...(summary ? { summary } : {}),
      app_id: appId,
      created_at: createdAt,
      ...(options?.executionId ? { created_by_execution_id: options.executionId } : {}),
      ...(options?.turnId ? { created_by_turn_id: options.turnId } : {}),
      ...(options?.sourceToolId ? { source_tool_id: options.sourceToolId } : {}),
      ...(options?.sourceSkillId ? { source_skill_id: options.sourceSkillId } : {}),
      ...(options?.sourceUploadId ? { source_upload_id: options.sourceUploadId } : {}),
      ...(options?.reviewed ? { reviewed: true } : {}),
      ...(options?.reviewedAt ? { reviewed_at: options.reviewedAt } : {}),
      ...(options?.reviewedBy ? { reviewed_by: options.reviewedBy } : {}),
      ...(options?.reviewSource ? { review_source: options.reviewSource } : {}),
      ...(Array.isArray(options?.sourceMessageIds) && options.sourceMessageIds.length > 0
        ? { source_message_ids: options.sourceMessageIds }
        : {}),
      ...(options?.contentHash ? { content_hash: options.contentHash } : {}),
      provider_origin: options?.providerOrigin ?? "local",
      ...(mimeType ? { mime_type: mimeType } : {}),
      ...(typeof sizeBytes === "number" ? { size_bytes: sizeBytes } : {}),
      path: metadataPath,
      ...(exportFilePath ? { file_path: exportFilePath } : {}),
      status: "ready",
      content
    };

    await fs.writeFile(
      metadataPath,
      JSON.stringify(metadata, null, 2),
      "utf-8"
    );
    return {
      artifact_id: artifactId,
      ...(typeof options?.sessionId === "string" && options.sessionId.trim().length > 0
        ? { session_id: options.sessionId.trim() }
        : {}),
      artifact_type: artifactType,
      display_name: displayName,
      storage_file_name: storageFileName,
      ...(summary ? { summary } : {}),
      app_id: appId,
      created_at: createdAt,
      ...(options?.executionId ? { created_by_execution_id: options.executionId } : {}),
      ...(options?.turnId ? { created_by_turn_id: options.turnId } : {}),
      ...(options?.sourceToolId ? { source_tool_id: options.sourceToolId } : {}),
      ...(options?.sourceSkillId ? { source_skill_id: options.sourceSkillId } : {}),
      ...(options?.sourceUploadId ? { source_upload_id: options.sourceUploadId } : {}),
      ...(options?.reviewed ? { reviewed: true } : {}),
      ...(options?.reviewedAt ? { reviewed_at: options.reviewedAt } : {}),
      ...(options?.reviewedBy ? { reviewed_by: options.reviewedBy } : {}),
      ...(options?.reviewSource ? { review_source: options.reviewSource } : {}),
      ...(Array.isArray(options?.sourceMessageIds) && options.sourceMessageIds.length > 0
        ? { source_message_ids: options.sourceMessageIds }
        : {}),
      ...(options?.contentHash ? { content_hash: options.contentHash } : {}),
      provider_origin: options?.providerOrigin ?? "local",
      ...(mimeType ? { mime_type: mimeType } : {}),
      ...(typeof sizeBytes === "number" ? { size_bytes: sizeBytes } : {}),
      path: metadataPath,
      ...(exportFilePath ? { file_path: exportFilePath } : {}),
      status: "ready"
    };
  }

  async load(
    appId: string,
    artifactId: string
  ): Promise<StoredArtifactRecord> {
    const appRoot = this.resolveStoragePath(path.join(this.rootDir, appId));
    let entries: string[];
    try {
      entries = (await fs.readdir(appRoot, { recursive: true })) as string[];
    } catch (error) {
      const details =
        error instanceof Error ? `: ${error.message}` : "";
      throw new Error(`Artifact not found: ${artifactId}${details}`);
    }
    const match = entries
      .map((entry) => String(entry))
      .find((entry) => entry.endsWith(`${artifactId}.json`));
    if (!match) {
      throw new Error(`Artifact not found: ${artifactId}`);
    }

    const filePath = path.join(appRoot, match);
    const parsed = JSON.parse(await fs.readFile(filePath, "utf-8")) as Partial<StoredArtifactRecord> & {
      content: unknown;
      name?: string;
      file_path?: string | null;
      path?: string | null;
      display_name?: string;
      summary?: string;
      created_at?: string;
      app_id?: string;
      session_id?: string;
      status?: "ready" | "deleted";
      deleted_at?: string;
      provider_origin?: "local";
      size_bytes?: number;
      mime_type?: string;
      source_tool_id?: string;
      source_skill_id?: string;
      source_upload_id?: string;
      reviewed?: boolean;
      reviewed_at?: string;
      reviewed_by?: string;
      review_source?: string;
      source_message_ids?: string[];
      content_hash?: string;
      created_by_execution_id?: string;
      created_by_turn_id?: string;
      storage_file_name?: string;
    };
    const artifactType = path.basename(path.dirname(filePath));
    const displayName =
      typeof parsed.display_name === "string" && parsed.display_name.length > 0
        ? parsed.display_name
        : typeof parsed.name === "string" && parsed.name.length > 0
          ? this.inferDisplayName(parsed.name, artifactType)
          : this.inferDisplayName(path.basename(filePath, ".json"), artifactType);
    const normalizedMetadataPath = this.normalizeStoredPath(parsed.path) ?? filePath;
    const normalizedFilePath = this.normalizeStoredPath(parsed.file_path);
    return {
      artifact_id: artifactId,
      ...(typeof parsed.session_id === "string" && parsed.session_id.length > 0
        ? { session_id: parsed.session_id }
        : {}),
      artifact_type: artifactType,
      display_name: displayName,
      ...(typeof parsed.storage_file_name === "string" && parsed.storage_file_name.length > 0
        ? { storage_file_name: parsed.storage_file_name }
        : {}),
      ...(typeof parsed.summary === "string" && parsed.summary.length > 0
        ? { summary: parsed.summary }
        : {}),
      app_id: typeof parsed.app_id === "string" && parsed.app_id.length > 0 ? parsed.app_id : appId,
      created_at:
        typeof parsed.created_at === "string" && parsed.created_at.length > 0
          ? parsed.created_at
          : new Date().toISOString(),
      ...(typeof parsed.created_by_execution_id === "string" && parsed.created_by_execution_id.length > 0
        ? { created_by_execution_id: parsed.created_by_execution_id }
        : {}),
      ...(typeof parsed.created_by_turn_id === "string" && parsed.created_by_turn_id.length > 0
        ? { created_by_turn_id: parsed.created_by_turn_id }
        : {}),
      ...(typeof parsed.source_tool_id === "string" && parsed.source_tool_id.length > 0
        ? { source_tool_id: parsed.source_tool_id }
        : {}),
      ...(typeof parsed.source_skill_id === "string" && parsed.source_skill_id.length > 0
        ? { source_skill_id: parsed.source_skill_id }
        : {}),
      ...(typeof parsed.source_upload_id === "string" && parsed.source_upload_id.length > 0
        ? { source_upload_id: parsed.source_upload_id }
        : {}),
      ...(parsed.reviewed === true ? { reviewed: true } : {}),
      ...(typeof parsed.reviewed_at === "string" && parsed.reviewed_at.length > 0
        ? { reviewed_at: parsed.reviewed_at }
        : {}),
      ...(typeof parsed.reviewed_by === "string" && parsed.reviewed_by.length > 0
        ? { reviewed_by: parsed.reviewed_by }
        : {}),
      ...(typeof parsed.review_source === "string" && parsed.review_source.length > 0
        ? { review_source: parsed.review_source }
        : {}),
      ...(Array.isArray(parsed.source_message_ids)
        ? { source_message_ids: parsed.source_message_ids.map((value) => String(value || "").trim()).filter(Boolean) }
        : {}),
      ...(typeof parsed.content_hash === "string" && parsed.content_hash.length > 0
        ? { content_hash: parsed.content_hash }
        : {}),
      provider_origin:
        typeof parsed.provider_origin === "string" && parsed.provider_origin.length > 0
          ? parsed.provider_origin
          : "local",
      ...(typeof parsed.mime_type === "string" && parsed.mime_type.length > 0
        ? { mime_type: parsed.mime_type }
        : {}),
      ...(typeof parsed.size_bytes === "number" ? { size_bytes: parsed.size_bytes } : {}),
      path: normalizedMetadataPath,
      ...(normalizedFilePath ? { file_path: normalizedFilePath } : {}),
      status: parsed.status === "deleted" ? "deleted" : "ready",
      ...(typeof parsed.deleted_at === "string" && parsed.deleted_at.length > 0
        ? { deleted_at: parsed.deleted_at }
        : {}),
      content: parsed.content
    };
  }

  async updateMetadata(
    appId: string,
    artifactId: string,
    metadataPatch: {
      reviewed?: boolean;
      reviewed_at?: string;
      reviewed_by?: string;
      review_source?: string;
      source_message_ids?: string[];
      content_hash?: string;
    }
  ): Promise<Omit<StoredArtifactRecord, "content">> {
    const record = await this.load(appId, artifactId);
    const updated: StoredArtifactRecord = {
      ...record,
      ...(metadataPatch.reviewed === true ? { reviewed: true } : {}),
      ...(typeof metadataPatch.reviewed_at === "string" && metadataPatch.reviewed_at.trim().length > 0
        ? { reviewed_at: metadataPatch.reviewed_at.trim() }
        : {}),
      ...(typeof metadataPatch.reviewed_by === "string" && metadataPatch.reviewed_by.trim().length > 0
        ? { reviewed_by: metadataPatch.reviewed_by.trim() }
        : {}),
      ...(typeof metadataPatch.review_source === "string" && metadataPatch.review_source.trim().length > 0
        ? { review_source: metadataPatch.review_source.trim() }
        : {}),
      ...(Array.isArray(metadataPatch.source_message_ids)
        ? { source_message_ids: metadataPatch.source_message_ids.map((value) => String(value || "").trim()).filter(Boolean) }
        : {}),
      ...(typeof metadataPatch.content_hash === "string" && metadataPatch.content_hash.trim().length > 0
        ? { content_hash: metadataPatch.content_hash.trim() }
        : {})
    };
    await fs.writeFile(record.path, JSON.stringify(updated, null, 2), "utf-8");
    const { content: _content, ...result } = updated;
    return result;
  }

  async resolveScopedFile(input: {
    appId: string;
    sessionId: string;
    artifactId: string;
  }): Promise<ScopedArtifactFile> {
    const record = await this.load(input.appId, input.artifactId);
    if (
      record.status !== "ready" ||
      record.app_id !== input.appId ||
      record.session_id !== input.sessionId
    ) {
      throw new Error(`Artifact not found: ${input.artifactId}`);
    }
    const candidate = record.file_path ?? record.path;
    const root = await this.canonicalRoot();
    const canonical = this.assertContained(root, await fs.realpath(candidate));
    const stat = await fs.stat(canonical);
    if (!stat.isFile()) {
      throw new Error(`Artifact file not found: ${input.artifactId}`);
    }
    return {
      artifact_id: record.artifact_id,
      display_name: record.display_name,
      ...(record.mime_type ? { mime_type: record.mime_type } : {}),
      size_bytes: stat.size,
      absolute_path: canonical
    };
  }

  async deleteScoped(input: {
    appId: string;
    sessionId: string;
    artifactId: string;
  }): Promise<boolean> {
    await this.markDeletedScoped(input);
    return true;
  }

  async markDeletedScoped(input: {
    appId: string;
    sessionId: string;
    artifactId: string;
  }): Promise<{ deleted: boolean }> {
    const record = await this.load(input.appId, input.artifactId);
    if (record.app_id !== input.appId || record.session_id !== input.sessionId) {
      throw new Error(`Artifact not found: ${input.artifactId}`);
    }
    if (record.status === "deleted") {
      return { deleted: false };
    }
    const root = await this.canonicalRoot();
    const metadataPath = this.assertContained(root, await fs.realpath(record.path));
    const byteCandidates = [record.file_path].filter(
      (value): value is string => typeof value === "string" && value.length > 0
    );
    const canonicalPaths: string[] = [];
    for (const candidate of byteCandidates) {
      try {
        canonicalPaths.push(this.assertContained(root, await fs.realpath(candidate)));
      } catch (error) {
        if (error && typeof error === "object" && "code" in error && error.code === "ENOENT") {
          continue;
        }
        throw error;
      }
    }
    const tombstone: StoredArtifactRecord = {
      ...record,
      status: "deleted",
      deleted_at: new Date().toISOString(),
      content: null
    };
    delete tombstone.file_path;
    await fs.writeFile(metadataPath, JSON.stringify(tombstone, null, 2), "utf-8");
    for (const candidate of [...new Set(canonicalPaths)]) {
      await fs.unlink(candidate).catch((error: NodeJS.ErrnoException) => {
        if (error.code !== "ENOENT") {
          throw error;
        }
      });
    }
    return { deleted: true };
  }

  async list(
    appId: string,
    options?: {
      artifactType?: string;
      allowedArtifactTypes?: string[];
      allowedMimeTypes?: string[];
      sessionId?: string;
      status?: "ready" | "deleted";
    }
  ): Promise<Array<Omit<StoredArtifactRecord, "content">>> {
    const appRoot = path.join(this.rootDir, appId);
    let entries: string[];
    try {
      entries = (await fs.readdir(appRoot, { recursive: true })) as string[];
    } catch (error) {
      if (
        error &&
        typeof error === "object" &&
        "code" in error &&
        (error as { code?: string }).code === "ENOENT"
      ) {
        return [];
      }
      throw error;
    }

    const allowedTypes = Array.isArray(options?.allowedArtifactTypes)
      ? new Set(
          options?.allowedArtifactTypes
            ?.map((value) => String(value || "").trim())
            .filter(Boolean)
        )
      : null;
    const allowedMimeTypes = Array.isArray(options?.allowedMimeTypes)
      ? new Set(
          options?.allowedMimeTypes
            ?.map((value) => String(value || "").trim())
            .filter(Boolean)
        )
      : null;
    const requestedArtifactType = String(options?.artifactType || "").trim();
    const requestedSessionId = String(options?.sessionId || "").trim();
    const requestedStatus = options?.status ?? "ready";

    const items = await Promise.all(
      entries
        .map((entry) => String(entry))
        .filter((entry) => entry.endsWith(".json"))
        .map(async (entry) => {
          const relativePath = path.join(appRoot, entry);
          const artifactId = path.basename(relativePath, ".json");
          const record = await this.load(appId, artifactId);
          const { content: _content, ...metadata } = record;
          return metadata;
        })
    );

    return items
      .filter((item) => {
        if (requestedArtifactType && item.artifact_type !== requestedArtifactType) {
          return false;
        }
        if (requestedStatus && item.status !== requestedStatus) {
          return false;
        }
        if (requestedSessionId && item.session_id !== requestedSessionId) {
          return false;
        }
        if (allowedTypes && !allowedTypes.has(item.artifact_type)) {
          return false;
        }
        if (
          allowedMimeTypes &&
          (!item.mime_type || !allowedMimeTypes.has(item.mime_type))
        ) {
          return false;
        }
        return true;
      })
      .sort((left, right) =>
        String(right.created_at || "").localeCompare(String(left.created_at || ""))
      );
  }

  async findSessionUploadImport(input: {
    appId: string;
    sessionId: string;
    sourceUploadId: string;
  }): Promise<Omit<StoredArtifactRecord, "content"> | undefined> {
    const items = await this.list(input.appId, {
      artifactType: "session_upload",
      sessionId: input.sessionId,
      status: "ready"
    });
    return items.find((item) => item.source_upload_id === input.sourceUploadId);
  }

  async findReadyByContentIdentity(
    identity: ArtifactContentIdentity
  ): Promise<Omit<StoredArtifactRecord, "content"> | undefined> {
    const sha256 = String(identity.sha256 || "").trim().toLowerCase();
    const mediaType = normalizeMimeType(identity.mediaType);
    const items = await this.list(identity.appId, {
      artifactType: "session_upload",
      sessionId: identity.sessionId,
      status: "ready"
    });
    return items.find((item) =>
      String(item.content_hash || "").trim().toLowerCase() === sha256 &&
      item.size_bytes === identity.sizeBytes &&
      normalizeMimeType(String(item.mime_type || "")) === mediaType
    );
  }
}
