import { z, type ZodType } from "zod";

import { AppError } from "../errors/app-error.js";
import type { PermissionMode } from "../permissions/permission.types.js";

import type { SkillDefinition } from "./skill.types.js";

export interface BuilderSkillClient {
  getBoundSkill(appId: string, skillId: string): Promise<SkillDefinition | null>;
}

type BuilderBinding = {
  skill_id: string;
  skill_version?: string;
  enabled: boolean;
  permission_mode?: PermissionMode;
};

type BuilderPublishedSkill = {
  skill_id: string;
  name: string;
  version: string;
  description?: string;
  enabled: boolean;
  required_tools?: string[];
  required_permissions?: string[];
  input_schema?: Record<string, unknown>;
  output_schema?: Record<string, unknown>;
  workflow_definition?: Record<string, unknown>;
};

function jsonSchemaToZod(schema: Record<string, unknown> | undefined): ZodType {
  const schemaObject = schema ?? {};
  const type = schemaObject.type;

  if (type === "string") {
    return z.string();
  }
  if (type === "number") {
    return z.number();
  }
  if (type === "integer") {
    return z.number().int();
  }
  if (type === "boolean") {
    return z.boolean();
  }
  if (type === "array") {
    const itemSchema = schemaObject.items;
    return z.array(
      jsonSchemaToZod(
        typeof itemSchema === "object" && itemSchema !== null
          ? (itemSchema as Record<string, unknown>)
          : undefined
      )
    );
  }
  if (type === "object" || (schemaObject.properties && typeof schemaObject.properties === "object")) {
    const properties = (schemaObject.properties ?? {}) as Record<string, Record<string, unknown>>;
    const required = new Set(
      Array.isArray(schemaObject.required) ? schemaObject.required.map(String) : []
    );
    const shape: Record<string, ZodType> = {};
    for (const [key, value] of Object.entries(properties)) {
      const child = jsonSchemaToZod(value);
      shape[key] = required.has(key) ? child : child.optional();
    }
    return z.object(shape);
  }

  return z.unknown();
}

export class HttpBuilderSkillClient implements BuilderSkillClient {
  constructor(private readonly baseUrl: string) {}

  async getBoundSkill(appId: string, skillId: string): Promise<SkillDefinition | null> {
    const bindingsResponse = await fetch(
      `${this.baseUrl}/api/apps/${encodeURIComponent(appId)}/skill-bindings?skill_id=${encodeURIComponent(skillId)}`
    );
    if (!bindingsResponse.ok) {
      if (bindingsResponse.status === 404) {
        return null;
      }
      throw new AppError({
        code: "BUILDER_BINDING_LOOKUP_FAILED",
        message: "Builder binding lookup failed.",
        errorClass: "external_api",
        httpStatus: 503,
        details: { app_id: appId, skill_id: skillId, status: bindingsResponse.status },
        recoverable: true,
        suggestedAction: "Retry after the builder service becomes available."
      });
    }

    const bindingsPayload = (await bindingsResponse.json()) as { items?: BuilderBinding[] };
    const binding = (bindingsPayload.items ?? []).find(
      (item) => item.skill_id === skillId && item.enabled
    );
    if (!binding) {
      return null;
    }

    const publishedUrl = new URL(
      `/api/skills/published/${encodeURIComponent(skillId)}`,
      this.baseUrl.endsWith("/") ? this.baseUrl : `${this.baseUrl}/`
    );
    if (binding.skill_version) {
      publishedUrl.searchParams.set("version", binding.skill_version);
    }
    const publishedResponse = await fetch(publishedUrl);
    if (!publishedResponse.ok) {
      if (publishedResponse.status === 404) {
        return null;
      }
      throw new AppError({
        code: "BUILDER_SKILL_LOOKUP_FAILED",
        message: "Builder published skill lookup failed.",
        errorClass: "external_api",
        httpStatus: 503,
        details: { app_id: appId, skill_id: skillId, status: publishedResponse.status },
        recoverable: true,
        suggestedAction: "Retry after the builder service becomes available."
      });
    }

    const published = (await publishedResponse.json()) as BuilderPublishedSkill;
    const definition: SkillDefinition = {
      id: published.skill_id,
      name: published.name,
      version: published.version,
      inputSchema: jsonSchemaToZod(published.input_schema),
      outputSchema: jsonSchemaToZod(published.output_schema),
      requiredTools: published.required_tools ?? [],
      requiredPermissions: published.required_permissions ?? [],
      workflowDefinition: ((published.workflow_definition ?? {
        steps: []
      }) as unknown) as SkillDefinition["workflowDefinition"],
      enabled: published.enabled,
      resultType: "json"
    };
    if (published.description) {
      definition.description = published.description;
    }
    if (binding.permission_mode) {
      definition.confirmationMode = binding.permission_mode;
    }
    return definition;
  }
}
