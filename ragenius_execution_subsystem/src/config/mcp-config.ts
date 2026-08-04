import { z } from "zod";

import type { AppEnv } from "./env.js";

const httpServerSchema = z.object({
  id: z.string().min(1),
  transport: z.literal("http"),
  baseUrl: z.string().trim().url(),
  authTokenEnv: z.string().min(1).optional(),
  allowedToolNames: z.array(z.string().min(1)).default([]),
  enabled: z.boolean().default(true)
});

const stdioServerSchema = z.object({
  id: z.string().min(1),
  transport: z.literal("stdio"),
  command: z.string().min(1),
  args: z.array(z.string()).default([]),
  authTokenEnv: z.string().min(1).optional(),
  allowedToolNames: z.array(z.string().min(1)).default([]),
  enabled: z.boolean().default(true)
});

const mcpServerSchema = z.discriminatedUnion("transport", [
  httpServerSchema,
  stdioServerSchema
]);

type ParsedMcpServer = z.infer<typeof mcpServerSchema>;

export type McpServerRuntimeConfig =
  | {
      id: string;
      transport: "http";
      baseUrl: string;
      authTokenEnv?: string;
      authToken?: string;
      allowedToolNames: string[];
      enabled: boolean;
    }
  | {
      id: string;
      transport: "stdio";
      command: string;
      args: string[];
      authTokenEnv?: string;
      authToken?: string;
      allowedToolNames: string[];
      enabled: boolean;
    };

export interface McpRuntimeConfig {
  servers: McpServerRuntimeConfig[];
}

function resolveAuthToken(
  authTokenEnv: string | undefined,
  env: NodeJS.ProcessEnv
): string | undefined {
  if (!authTokenEnv) {
    return undefined;
  }

  const token = env[authTokenEnv];
  return typeof token === "string" && token.trim().length > 0 ? token : undefined;
}

function mapMcpServer(
  server: ParsedMcpServer,
  env: NodeJS.ProcessEnv
): McpServerRuntimeConfig {
  const authToken = resolveAuthToken(server.authTokenEnv, env);

  if (server.transport === "http") {
    return {
      id: server.id,
      transport: "http",
      baseUrl: server.baseUrl,
      allowedToolNames: server.allowedToolNames,
      enabled: server.enabled,
      ...(server.authTokenEnv ? { authTokenEnv: server.authTokenEnv } : {}),
      ...(authToken ? { authToken } : {})
    };
  }

  return {
    id: server.id,
    transport: "stdio",
    command: server.command,
    args: server.args,
    allowedToolNames: server.allowedToolNames,
    enabled: server.enabled,
    ...(server.authTokenEnv ? { authTokenEnv: server.authTokenEnv } : {}),
    ...(authToken ? { authToken } : {})
  };
}

export function buildMcpRuntimeConfig(
  env: AppEnv,
  source: NodeJS.ProcessEnv = process.env
): McpRuntimeConfig {
  const parsedJson = JSON.parse(env.MCP_SERVERS_JSON) as unknown;
  const parsedServers = z.array(mcpServerSchema).parse(parsedJson);

  return {
    servers: parsedServers.map((server) => mapMcpServer(server, source))
  };
}
