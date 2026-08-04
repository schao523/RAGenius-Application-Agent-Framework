import type { FastifyInstance } from "fastify";

export async function registerSkillRoutes(app: FastifyInstance): Promise<void> {
  app.get("/skills", async () => ({
    items: app.services.skillRegistry.list().map((skill) => ({
      id: skill.id,
      name: skill.name,
      version: skill.version,
      enabled: skill.enabled,
      required_tools: skill.requiredTools
    }))
  }));

  app.get("/skills/:skill_id", async (request) => {
    const params = request.params as { skill_id: string };
    const skill = app.services.skillRegistry.get(params.skill_id);

    return {
      id: skill.id,
      name: skill.name,
      version: skill.version,
      description: skill.description,
      enabled: skill.enabled,
      input_schema: skill.inputSchema,
      output_schema: skill.outputSchema,
      required_tools: skill.requiredTools,
      required_permissions: skill.requiredPermissions
    };
  });
}
