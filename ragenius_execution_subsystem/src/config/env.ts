import { z } from "zod";

const booleanEnv = (defaultValue: boolean) =>
  z.preprocess((value) => {
    if (typeof value === "string") {
      const normalized = value.trim().toLowerCase();
      if (normalized === "true") {
        return true;
      }
      if (normalized === "false") {
        return false;
      }
    }
    return value;
  }, z.boolean().default(defaultValue));

const envSchema = z.object({
  DATABASE_URL: z.string().min(1).default(
    "postgresql://postgres:postgres@localhost:5432/ragenius_execution?schema=public"
  ),
  NODE_ENV: z
    .enum(["development", "test", "production"])
    .default("development"),
  PORT: z.coerce.number().int().positive().default(3000),
  LOG_LEVEL: z
    .enum(["debug", "info", "warn", "error"])
    .default("info"),
  EXECUTION_CONFIRMATION_TTL_MS: z.coerce
    .number()
    .int()
    .positive()
    .default(900000),
  AGENT_ASYNC_EXECUTION_ENABLED: booleanEnv(false),
  AGENT_ASYNC_CONCURRENCY: z.coerce.number().int().positive().default(1),
  RAGENIUS_EXECUTION_SERVICE_AUTH_REQUIRED: booleanEnv(false),
  RAGENIUS_EXECUTION_SERVICE_ID: z.string().trim().min(1).default("ragenius_app"),
  RAGENIUS_EXECUTION_SERVICE_TOKEN: z.string().trim().min(1).optional(),
  RAGENIUS_EXECUTION_SERVICE_CREDENTIALS_JSON: z.string().default("[]"),
  AGENT_SKILL_TRUSTED_BUILDER_INSTANCE_ID: z.string().trim().min(1).default("builder-primary"),
  AGENT_SKILL_PROJECTION_MAX_ITEMS: z.coerce.number().int().positive().default(10000),
  AGENT_SKILL_PROJECTION_MAX_BYTES: z.coerce.number().int().positive().default(8388608),
  CODEX_AGENT_SKILL_SOURCES_JSON: z.string().default("[]"),
  CODEX_AGENT_SKILL_MAX_DEPTH: z.coerce.number().int().nonnegative().default(6),
  CODEX_AGENT_SKILL_MAX_FILES: z.coerce.number().int().positive().default(512),
  CODEX_AGENT_SKILL_MAX_FILE_BYTES: z.coerce.number().int().positive().default(1048576),
  CODEX_AGENT_SKILL_MAX_TOTAL_BYTES: z.coerce.number().int().positive().default(16777216),
  CODEX_AGENT_SKILL_INVENTORY_TIMEOUT_MS: z.coerce.number().int().positive().default(15000),
  CODEX_AGENT_SKILL_INVENTORY_MAX_STDOUT_BYTES: z.coerce.number().int().positive().default(1048576),
  CODEX_AGENT_SKILL_INVENTORY_MAX_STDERR_BYTES: z.coerce.number().int().positive().default(65536),
  OPENCLAW_AGENT_SKILL_ALLOWED_TARGETS_JSON: z.string().default("[]"),
  OPENCLAW_AGENT_SKILL_MAX_DEPTH: z.coerce.number().int().nonnegative().default(6),
  OPENCLAW_AGENT_SKILL_MAX_FILES: z.coerce.number().int().positive().default(512),
  OPENCLAW_AGENT_SKILL_MAX_FILE_BYTES: z.coerce.number().int().positive().default(1048576),
  OPENCLAW_AGENT_SKILL_MAX_TOTAL_BYTES: z.coerce.number().int().positive().default(16777216),
  BUILDER_BASE_URL: z.string().trim().url().optional(),
  HTTP_PROXY: z.string().trim().optional(),
  HTTPS_PROXY: z.string().trim().optional(),
  ALL_PROXY: z.string().trim().optional(),
  NO_PROXY: z.string().trim().optional(),
  NODE_EXTRA_CA_CERTS: z.string().trim().optional(),
  FILESYSTEM_ALLOWED_ROOTS: z.string().default(""),
  FILESYSTEM_MUTATION_ROOTS: z.string().default(""),
  FILESYSTEM_MAX_READ_BYTES: z.coerce.number().int().positive().default(65536),
  FILESYSTEM_MAX_WRITE_BYTES: z.coerce.number().int().positive().default(65536),
  FILESYSTEM_MAX_PATCH_BYTES: z.coerce.number().int().positive().default(32768),
  ARTIFACT_STORAGE_ROOT: z.string().trim().default("storage/artifacts"),
  AGENT_INPUT_MAX_BYTES: z.coerce.number().int().positive().default(536870912),
  AGENT_INPUT_ALLOWED_MIME_TYPES: z.string().default(
    "video/mp4,application/pdf,text/plain,text/markdown,application/octet-stream"
  ),
  AGENT_INPUT_TEMP_RETENTION_HOURS: z.coerce.number().int().positive().default(24),
  AGENT_BINARY_IN_MEMORY_MAX_BYTES: z.coerce.number().int().positive().default(26214400),
  ARXIV_ENABLED: booleanEnv(true),
  ARXIV_REQUEST_TIMEOUT_MS: z.coerce.number().int().positive().default(4000),
  ARXIV_RETRY_ON_429: booleanEnv(true),
  ARXIV_MAX_RETRIES: z.coerce.number().int().min(0).default(1),
  SEMANTIC_SCHOLAR_ENABLED: booleanEnv(true),
  SEMANTIC_SCHOLAR_API_KEY: z.string().trim().optional(),
  SEMANTIC_SCHOLAR_REQUEST_TIMEOUT_MS: z.coerce.number().int().positive().default(4000),
  SEMANTIC_SCHOLAR_MAX_RESULTS_DEFAULT: z.coerce.number().int().positive().default(5),
  NOTEBOOKLM_ENABLED: booleanEnv(false),
  NOTEBOOKLM_PYTHON_COMMAND: z.string().trim().default("python"),
  NOTEBOOKLM_BRIDGE_SCRIPT: z
    .string()
    .trim()
    .default("scripts/notebooklm_bridge.py"),
  NOTEBOOKLM_AUTH_MODE: z
    .enum(["env_json", "profile", "storage_path"])
    .default("env_json"),
  NOTEBOOKLM_PROFILE: z.string().trim().optional(),
  NOTEBOOKLM_STORAGE_PATH: z.string().trim().optional(),
  NOTEBOOKLM_ALLOWED_OPERATIONS: z
    .string()
    .default("list_notebooks,list_sources,ask"),
  NOTEBOOKLM_GENERATION_WAIT_FOR_COMPLETION: booleanEnv(true),
  NOTEBOOKLM_GENERATION_PERSIST_ARTIFACTS: booleanEnv(true),
  CODEX_CLI_ENABLED: booleanEnv(false),
  CODEX_CLI_NODE_COMMAND: z.string().trim().default("node"),
  CODEX_CLI_BRIDGE_SCRIPT: z
    .string()
    .trim()
    .default("scripts/codex_cli_bridge.js"),
  CODEX_CLI_COMMAND: z.string().trim().default("codex"),
  CODEX_CLI_ARGS_JSON: z.string().default("[]"),
  CODEX_CLI_TIMEOUT_MS: z.coerce.number().int().positive().default(300000),
  CODEX_RUN_ROOT: z.string().trim().min(1).default("storage/codex-runs"),
  CODEX_RUN_RETENTION_HOURS: z.coerce.number().int().positive().default(24),
  CODEX_MAX_OUTPUT_BYTES: z.coerce.number().int().positive().default(16384),
  CODEX_CLI_SANDBOX_MODE: z
    .enum(["read-only", "workspace-write"])
    .default("workspace-write"),
  OPENCLAW_CLI_ENABLED: booleanEnv(false),
  OPENCLAW_WSL_DISTRO: z.string().trim().default("OpenClawGateway"),
  OPENCLAW_CLI_COMMAND: z.string().trim().default("openclaw"),
  OPENCLAW_AGENT_ID: z.string().trim().default("main"),
  OPENCLAW_WORKSPACE_ROOT: z
    .string()
    .trim()
    .default("/home/openclaw/.openclaw/workspace"),
  OPENCLAW_DEFAULT_TIMEOUT_MS: z.coerce.number().int().positive().default(120000),
  OPENCLAW_MAX_STDOUT_BYTES: z.coerce.number().int().positive().default(262144),
  OPENCLAW_MAX_STDERR_BYTES: z.coerce.number().int().positive().default(65536),
  OPENCLAW_RUN_RETENTION_HOURS: z.coerce.number().int().positive().default(24),
  OPENAI_ENABLED: booleanEnv(false),
  OPENAI_API_KEY: z.string().trim().optional(),
  OPENAI_BASE_URL: z.string().trim().url().optional(),
  OPENAI_DEFAULT_MODEL: z.string().trim().optional(),
  MCP_SERVERS_JSON: z.string().default("[]"),
  ADAPTERS_JSON: z.string().default("[]"),
  TOOL_RESEARCH_PAPER_SEARCH_ENABLED: booleanEnv(true),
  TOOL_RAG_RETRIEVAL_ENABLED: booleanEnv(true),
  TOOL_OPENAI_ANSWER_ENABLED: booleanEnv(false)
});

export type AppEnv = z.infer<typeof envSchema>;

export function getEnv(source: NodeJS.ProcessEnv = process.env): AppEnv {
  return envSchema.parse(source);
}
