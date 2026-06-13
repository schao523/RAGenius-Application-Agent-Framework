import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { getArtifactConsumerSpec } from "../../core/artifacts/artifact-consumption-registry.js";

export async function registerToolRoutes(app: FastifyInstance): Promise<void> {
  const serializeSchema = (schema: unknown): unknown => {
    if (schema instanceof z.ZodEffects) {
      return serializeSchema(schema.innerType());
    }
    if (schema instanceof z.ZodOptional || schema instanceof z.ZodNullable) {
      return serializeSchema(schema.unwrap());
    }
    if (schema instanceof z.ZodDefault) {
      return serializeSchema(schema.removeDefault());
    }
    if (schema instanceof z.ZodString) {
      return { type: "string" };
    }
    if (schema instanceof z.ZodNumber) {
      return { type: Number.isInteger(schema.minValue ?? NaN) ? "number" : "number" };
    }
    if (schema instanceof z.ZodBoolean) {
      return { type: "boolean" };
    }
    if (schema instanceof z.ZodLiteral) {
      return { const: schema.value };
    }
    if (schema instanceof z.ZodEnum) {
      return { type: "string", enum: schema.options };
    }
    if (schema instanceof z.ZodArray) {
      return {
        type: "array",
        items: serializeSchema(schema.element)
      };
    }
    if (schema instanceof z.ZodObject) {
      const shape = schema.shape;
      const properties = Object.fromEntries(
        Object.entries(shape).map(([key, value]) => [key, serializeSchema(value)])
      );
      const required = Object.entries(shape)
        .filter(([, value]) => !(value instanceof z.ZodOptional) && !(value instanceof z.ZodDefault))
        .map(([key]) => key);
      return {
        type: "object",
        properties,
        ...(required.length > 0 ? { required } : {})
      };
    }
    if (
      schema &&
      typeof schema === "object" &&
      "toJSON" in schema &&
      typeof (schema as { toJSON?: () => unknown }).toJSON === "function"
    ) {
      return (schema as { toJSON: () => unknown }).toJSON();
    }
    return schema;
  };

  const inferProviderId = (
    tool: {
      id: string;
      providerType: string;
      metadata?: Record<string, unknown>;
    }
  ): string => {
    const metadataProviderId = tool.metadata?.providerId;
    if (typeof metadataProviderId === "string" && metadataProviderId.length > 0) {
      return metadataProviderId;
    }
    if (tool.providerType === "mcp" && tool.id.startsWith("mcp.")) {
      return tool.id.split(".")[1] ?? "mcp";
    }
    if (tool.id.startsWith("adapter.notebooklm.")) {
      return "notebooklm";
    }
    if (tool.providerType === "adapter") {
      return "custom_adapter";
    }
    if (tool.providerType === "local") {
      return tool.id.includes("artifact") ? "artifact_store" : "filesystem";
    }
    if (tool.providerType === "rag_adapter") {
      return "rag_subsystem";
    }
    if (tool.id === "research_paper_search_tool") {
      return "research_paper";
    }
    if (tool.id === "openai_answer_tool") {
      return "openai";
    }
    return tool.providerType;
  };

  const normalizeToolDisplayName = (
    tool: {
      id: string;
      name: string;
      providerType: string;
    }
  ): string => {
    const explicitNames: Record<string, string> = {
      "mcp.gmail.search_messages": "Gmail Message Search",
      "mcp.gmail.create_draft": "Gmail Create Draft",
      "mcp.gmail.create_draft_with_attachments": "Gmail Create Draft With Attachments",
      "mcp.gmail.send_draft": "Gmail Send Draft",
      "mcp.gmail.send_message": "Gmail Send Message",
      "mcp.gdocs.search_documents": "Google Docs Search",
      "mcp.gdrive.search_files": "Google Drive Search",
      "mcp.gdrive.download_file_content": "Google Drive Download File",
      "mcp.cms.search_pages": "CMS Page Search",
      "mcp.cms.create_page": "CMS Page Create"
    };
    return explicitNames[tool.id] ?? tool.name;
  };

  const normalizeArtifactPicker = (
    candidate: unknown,
    inputSchema: unknown,
    options: { requireSchemaField?: boolean } = {}
  ):
    | {
        enabled: true;
        field_name: string;
        selection_mode: string;
        allowed_artifact_types: unknown[];
        allowed_mime_types: unknown[];
        eligible_for: unknown;
        accepted_artifact_types: unknown[];
        required_consumption_mode: unknown;
        max_artifact_count: unknown;
      }
    | null => {
    if (!candidate || typeof candidate !== "object") {
      return null;
    }
    const picker = candidate as Record<string, unknown>;
    if (picker.enabled === false) {
      return null;
    }
    const fieldName = String(picker.field_name || picker.fieldName || "artifactIds").trim();
    if (!fieldName) {
      return null;
    }
    const properties =
      typeof inputSchema === "object" &&
      inputSchema !== null &&
      "properties" in inputSchema &&
      typeof (inputSchema as { properties?: unknown }).properties === "object"
        ? (inputSchema as { properties: Record<string, unknown> }).properties
        : {};
    if (options.requireSchemaField !== false && !(fieldName in properties)) {
      return null;
    }
    const allowedArtifactTypes = Array.isArray(picker.allowed_artifact_types)
      ? picker.allowed_artifact_types
      : [];
    const acceptedArtifactTypes = Array.isArray(picker.accepted_artifact_types)
      ? picker.accepted_artifact_types
      : allowedArtifactTypes;
    return {
      enabled: true,
      field_name: fieldName,
      selection_mode: String(picker.selection_mode || "multiple"),
      allowed_artifact_types: allowedArtifactTypes,
      allowed_mime_types: Array.isArray(picker.allowed_mime_types)
        ? picker.allowed_mime_types
        : [],
      eligible_for: picker.eligible_for ?? null,
      accepted_artifact_types: acceptedArtifactTypes,
      required_consumption_mode: picker.required_consumption_mode ?? null,
      max_artifact_count: picker.max_artifact_count ?? null
    };
  };

  const inferInventoryVisibility = (
    skill: {
      inventoryVisibility?: "user_tool" | "user_skill" | "internal_wrapper";
      workflowKind?: "single_tool_wrapper" | "multi_step_workflow" | "builder_bound";
    }
  ): "user_tool" | "user_skill" | "internal_wrapper" => {
    if (skill.inventoryVisibility) {
      return skill.inventoryVisibility;
    }
    return "internal_wrapper";
  };

  const inferWorkflowKind = (
    skill: {
      workflowKind?: "single_tool_wrapper" | "multi_step_workflow" | "builder_bound";
    }
  ): "single_tool_wrapper" | "multi_step_workflow" | "builder_bound" => {
    return skill.workflowKind ?? "single_tool_wrapper";
  };

  const toolInventory = () =>
    app.services.toolRegistry.list().map((tool) => {
      const providerId = inferProviderId(tool);
      const fallbackPolicy = app.services.runtimeConfig.policy.fallbacks.tools[tool.id];
      const toolPolicy = app.services.runtimeConfig.policy.tools[tool.id];
      const inputSchema =
        (tool.metadata?.remoteInputSchema as unknown) ??
        serializeSchema(tool.inputSchema);
      const outputSchema = serializeSchema(tool.outputSchema);
      const policyClass =
        typeof tool.metadata?.policyClass === "string"
          ? tool.metadata.policyClass
          : null;
      const requiresConfirmation =
        typeof tool.metadata?.requiresConfirmation === "boolean"
          ? tool.metadata.requiresConfirmation
          : null;
      const explicitArtifactPicker = normalizeArtifactPicker(
        tool.metadata?.artifactPicker,
        inputSchema,
        { requireSchemaField: true }
      );
      const policyArtifactPicker =
        toolPolicy?.inputSourcePolicy === "artifact_only" ||
        (typeof inputSchema === "object" &&
          inputSchema !== null &&
          "properties" in inputSchema &&
          typeof (inputSchema as { properties?: unknown }).properties === "object" &&
          (inputSchema as { properties: Record<string, unknown> }).properties?.artifactIds)
          ? normalizeArtifactPicker(
              {
                enabled: true,
                field_name: "artifactIds",
                selection_mode: "multiple",
                allowed_artifact_types:
                  toolPolicy?.requiresArtifactSource
                    ? app.services.runtimeConfig.policy.attachments.allowedArtifactTypes
                    : [],
                allowed_mime_types:
                  toolPolicy?.requiresArtifactSource
                    ? app.services.runtimeConfig.policy.attachments.allowedMimeTypes
                    : [],
                eligible_for: toolPolicy?.requiresArtifactSource ? "attachments" : null,
                accepted_artifact_types:
                  toolPolicy?.requiresArtifactSource
                    ? app.services.runtimeConfig.policy.attachments.allowedArtifactTypes
                    : [],
                required_consumption_mode: toolPolicy?.requiresArtifactSource
                  ? "binary_payload"
                  : null,
                max_artifact_count: toolPolicy?.requiresArtifactSource
                  ? app.services.runtimeConfig.policy.attachments.maxAttachmentCount
                  : null
              },
              inputSchema,
              { requireSchemaField: false }
            )
          : null;
      const artifactPicker = explicitArtifactPicker ?? policyArtifactPicker;
      return {
        tool_id: tool.id,
        name: normalizeToolDisplayName(tool),
        family: tool.providerType,
        provider_id: providerId,
        exec_capable: Boolean(tool.enabled ?? true),
        exec_kind: "tool",
        enabled: tool.enabled ?? true,
        permission_scopes: tool.permissionScopes,
        side_effecting: tool.sideEffecting,
        timeout_ms: tool.timeoutMs ?? null,
        policy_class: policyClass,
        requires_confirmation: requiresConfirmation,
        risk_class: tool.sideEffecting ? "write" : "read_only",
        input_schema: inputSchema,
        output_schema: outputSchema,
        fallback_capable: Boolean(fallbackPolicy?.enabled),
        fallback_strategy: fallbackPolicy?.strategy ?? null,
        ...(artifactPicker ? { artifact_picker: artifactPicker } : {}),
        metadata: tool.metadata ?? {}
      };
    });

  const skillInventory = (visibility?: string) =>
    app.services.skillRegistry
      .list()
      .filter((skill) => {
        if (visibility !== "user") {
          return true;
        }
        return inferInventoryVisibility(skill) === "user_skill";
      })
      .map((skill) => ({
        skill_id: skill.id,
        name: skill.name,
        version: skill.version,
        description: skill.description ?? "",
        enabled: skill.enabled,
        exec_capable: Boolean(skill.enabled),
        exec_kind: "skill",
        required_tools: skill.requiredTools,
        required_permissions: skill.requiredPermissions,
        confirmation_mode: skill.confirmationMode ?? null,
        result_type: skill.resultType ?? null,
        inventory_visibility: inferInventoryVisibility(skill),
        workflow_kind: inferWorkflowKind(skill),
        input_schema: serializeSchema(skill.inputSchema),
        output_schema: serializeSchema(skill.outputSchema)
      }));

  const runtimeIntegrations = () => {
    const runtimeConfig = app.services.runtimeConfig;
    const allTools = toolInventory();
    const integrationRows: Array<Record<string, unknown>> = [];

    for (const server of runtimeConfig.mcp.servers) {
      const discovery = app.services.mcpDiscovery.providers[server.id];
      const serverTools = allTools.filter(
        (tool) => tool.family === "mcp" && tool.provider_id === server.id
      );
      integrationRows.push({
        id: server.id,
        family: "mcp",
        configured: true,
        enabled: server.enabled,
        auth_configured: Boolean(server.authToken),
        tool_count: serverTools.length,
        tool_ids: serverTools.map((tool) => tool.tool_id),
        allowlisted_tools: server.allowedToolNames,
        health: {
          status: discovery?.status ?? "not_started",
          last_error: discovery?.lastError ?? null,
          last_discovered_at: discovery?.lastDiscoveredAt ?? null
        }
      });
    }

    const notebookLmTools = allTools.filter(
      (tool) => tool.family === "adapter" && tool.provider_id === "notebooklm"
    );
    integrationRows.push({
      id: "notebooklm",
      family: "adapter",
      configured: Boolean(
        runtimeConfig.providers.notebooklm.pythonCommand &&
          runtimeConfig.providers.notebooklm.bridgeScript
      ),
      enabled: runtimeConfig.providers.notebooklm.enabled,
      auth_configured:
        runtimeConfig.providers.notebooklm.authMode === "env_json"
          ? true
          : Boolean(
              runtimeConfig.providers.notebooklm.profile ||
                runtimeConfig.providers.notebooklm.storagePath
            ),
      tool_count: notebookLmTools.length,
      tool_ids: notebookLmTools.map((tool) => tool.tool_id),
      allowed_operations: runtimeConfig.providers.notebooklm.allowedOperations,
      health: {
        status: runtimeConfig.providers.notebooklm.enabled ? "configured" : "disabled",
        last_error: null
      }
    });

    const customAdapterTools = runtimeConfig.adapters.tools.filter(
      (tool) => !tool.id.startsWith("adapter.notebooklm.")
    );
    integrationRows.push({
      id: "custom_adapter",
      family: "adapter",
      configured: customAdapterTools.length > 0,
      enabled: customAdapterTools.some((tool) => tool.enabled),
      auth_configured: true,
      tool_count: customAdapterTools.length,
      tool_ids: customAdapterTools.map((tool) => tool.id),
      health: {
        status: customAdapterTools.length > 0 ? "configured" : "not_configured",
        last_error: null
      }
    });

    const researchPaperTools = allTools.filter(
      (tool) => tool.family === "api" && tool.provider_id === "research_paper"
    );
    integrationRows.push({
      id: "research_paper",
      family: "api",
      configured:
        runtimeConfig.providers.researchPaper.arxiv.enabled ||
        runtimeConfig.providers.researchPaper.semanticScholar.enabled,
      enabled:
        runtimeConfig.providers.researchPaper.arxiv.enabled ||
        runtimeConfig.providers.researchPaper.semanticScholar.enabled,
      auth_configured:
        runtimeConfig.providers.researchPaper.arxiv.enabled ||
        Boolean(runtimeConfig.providers.researchPaper.semanticScholar.apiKey),
      tool_count: researchPaperTools.length,
      tool_ids: researchPaperTools.map((tool) => tool.tool_id),
      health: {
        status: "configured",
        last_error: null
      }
    });

    const openAiTools = allTools.filter(
      (tool) => tool.family === "api" && tool.provider_id === "openai"
    );
    integrationRows.push({
      id: "openai",
      family: "api",
      configured: runtimeConfig.providers.openAi.enabled,
      enabled: runtimeConfig.providers.openAi.enabled,
      auth_configured: Boolean(runtimeConfig.providers.openAi.apiKey),
      tool_count: openAiTools.length,
      tool_ids: openAiTools.map((tool) => tool.tool_id),
      health: {
        status: runtimeConfig.providers.openAi.enabled ? "configured" : "disabled",
        last_error: null
      }
    });

    const localTools = allTools.filter((tool) => tool.family === "local");
    integrationRows.push({
      id: "local_runtime",
      family: "local",
      configured: true,
      enabled: localTools.some((tool) => tool.enabled),
      auth_configured: true,
      tool_count: localTools.length,
      tool_ids: localTools.map((tool) => tool.tool_id),
      health: {
        status: "ready",
        last_error: null
      }
    });

    const ragTools = allTools.filter((tool) => tool.family === "rag_adapter");
    integrationRows.push({
      id: "rag_subsystem",
      family: "rag_adapter",
      configured: true,
      enabled: ragTools.some((tool) => tool.enabled),
      auth_configured: true,
      tool_count: ragTools.length,
      tool_ids: ragTools.map((tool) => tool.tool_id),
      health: {
        status: "ready",
        last_error: null
      }
    });

    return {
      items: integrationRows,
      summary: {
        total_integrations: integrationRows.length,
        by_family: integrationRows.reduce<Record<string, number>>((acc, row) => {
          const family = String(row.family);
          acc[family] = (acc[family] ?? 0) + 1;
          return acc;
        }, {})
      }
    };
  };

  app.get("/tools", async () => ({
    items: app.services.toolRegistry.list().map((tool) => ({
      id: tool.id,
      name: tool.name,
      provider_type: tool.providerType,
      permission_scopes: tool.permissionScopes,
      side_effecting: tool.sideEffecting,
      enabled: tool.enabled ?? true
    }))
  }));

  app.get("/tools/inventory", async () => ({
    items: toolInventory()
  }));

  app.get("/artifacts", async (request) => {
    const query = (request.query as {
      app_id?: string;
      session_id?: string;
      artifact_type?: string;
      eligible_for?: string;
      status?: string;
    } | undefined) ?? {};
    const appId = String(query.app_id || "").trim();
    if (!appId) {
      return { items: [] };
    }
    const eligibleFor = String(query.eligible_for || "").trim().toLowerCase();
    const listOptions: {
      artifactType?: string;
      allowedArtifactTypes?: string[];
      allowedMimeTypes?: string[];
      sessionId?: string;
      status?: "ready";
    } = {};
    const sessionId = String(query.session_id || "").trim();
    const artifactType = String(query.artifact_type || "").trim();
    if (artifactType) {
      listOptions.artifactType = artifactType;
    }
    if (sessionId) {
      listOptions.sessionId = sessionId;
    }
    if (eligibleFor === "attachments") {
      listOptions.allowedArtifactTypes =
        app.services.runtimeConfig.policy.attachments.allowedArtifactTypes;
      listOptions.allowedMimeTypes =
        app.services.runtimeConfig.policy.attachments.allowedMimeTypes;
    }
    if (String(query.status || "").trim().toLowerCase() === "ready") {
      listOptions.status = "ready";
    }
    const items = await app.services.artifactStore.list(appId, listOptions);
    return {
      items: items.map((item) => {
        const spec = getArtifactConsumerSpec(String(item.artifact_type || "").trim());
        return {
          ...item,
          ...(spec
            ? {
                consumption: {
                  default_mode: spec.default_consumption_mode,
                  supported_modes: spec.supported_consumption_modes,
                },
                reusable: spec.reusable,
                picker_visibility: spec.picker_visibility,
                eligible_consumers: spec.eligible_consumers,
              }
            : {}),
        };
      }),
    };
  });

  app.patch("/artifacts/:artifact_id", async (request, reply) => {
    const params = request.params as { artifact_id?: string };
    const body = (request.body as {
      app_id?: string;
      metadata?: {
        reviewed?: boolean;
        reviewed_at?: string;
        reviewed_by?: string;
        review_source?: string;
        source_message_ids?: string[];
        content_hash?: string;
      };
    } | undefined) ?? {};
    const artifactId = String(params.artifact_id || "").trim();
    const appId = String(body.app_id || "").trim();
    if (!artifactId || !appId) {
      reply.code(400);
      return {
        error: {
          code: "INVALID_ARTIFACT_UPDATE",
          message: "artifact_id and app_id are required."
        }
      };
    }
    try {
      const metadataPatch: {
        reviewed?: boolean;
        reviewed_at?: string;
        reviewed_by?: string;
        review_source?: string;
        source_message_ids?: string[];
        content_hash?: string;
      } = {
        ...(typeof body.metadata?.reviewed === "boolean" ? { reviewed: body.metadata.reviewed } : {}),
        ...(typeof body.metadata?.reviewed_at === "string" ? { reviewed_at: body.metadata.reviewed_at } : {}),
        ...(typeof body.metadata?.reviewed_by === "string" ? { reviewed_by: body.metadata.reviewed_by } : {}),
        ...(typeof body.metadata?.review_source === "string" ? { review_source: body.metadata.review_source } : {}),
        ...(Array.isArray(body.metadata?.source_message_ids) ? { source_message_ids: body.metadata.source_message_ids } : {}),
        ...(typeof body.metadata?.content_hash === "string" ? { content_hash: body.metadata.content_hash } : {})
      };
      return await app.services.artifactStore.updateMetadata(
        appId,
        artifactId,
        metadataPatch
      );
    } catch (error) {
      reply.code(404);
      return {
        error: {
          code: "ARTIFACT_NOT_FOUND",
          message: error instanceof Error ? error.message : "Artifact not found."
        }
      };
    }
  });

  app.get("/skills/inventory", async (request) => ({
    items: skillInventory(
      typeof (request.query as { visibility?: string } | undefined)?.visibility === "string"
        ? (request.query as { visibility?: string }).visibility
        : undefined
    )
  }));

  app.post("/tools/discover/mcp", async (request) => {
    const body = request.body as { provider_id: string };
    const discovered = await app.services.discoverMcpProvider(body.provider_id);

    return {
      provider_id: body.provider_id,
      tools_discovered: discovered.map((tool) => ({
        tool_id: tool.id,
        name: tool.name,
        provider_type: tool.providerType,
        permission_scopes: tool.permissionScopes,
        side_effecting: tool.sideEffecting,
        input_schema:
          (tool.metadata?.remoteInputSchema as unknown) ??
          serializeSchema(tool.inputSchema),
        output_schema: serializeSchema(tool.outputSchema),
        metadata: tool.metadata ?? {}
      }))
    };
  });

  app.get("/tools/providers/mcp/status", async () => ({
    startup_completed: app.services.mcpDiscovery.startupCompleted,
    providers: app.services.mcpDiscovery.providers
  }));

  app.get("/runtime/integrations", async () => runtimeIntegrations());
}
