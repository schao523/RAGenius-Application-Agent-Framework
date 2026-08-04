-- CreateSchema
CREATE SCHEMA IF NOT EXISTS "public";

-- CreateTable
CREATE TABLE "executions" (
    "id" TEXT NOT NULL,
    "request_type" TEXT NOT NULL,
    "app_id" TEXT NOT NULL,
    "session_id" TEXT NOT NULL,
    "skill_id" TEXT NOT NULL,
    "request_payload" JSONB NOT NULL,
    "status" TEXT NOT NULL,
    "result_type" TEXT,
    "result" JSONB,
    "files" JSONB,
    "errors" JSONB,
    "logs_summary" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "started_at" TIMESTAMP(3),
    "completed_at" TIMESTAMP(3),
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "executions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "workflow_steps" (
    "id" TEXT NOT NULL,
    "execution_id" TEXT NOT NULL,
    "step_id" TEXT NOT NULL,
    "step_type" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "input_summary" JSONB,
    "output_summary" JSONB,
    "error" JSONB,
    "started_at" TIMESTAMP(3),
    "completed_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "workflow_steps_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "skills" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "version" TEXT NOT NULL,
    "description" TEXT,
    "input_schema" JSONB NOT NULL,
    "output_schema" JSONB NOT NULL,
    "required_tools" JSONB NOT NULL,
    "required_permissions" JSONB NOT NULL,
    "workflow_definition" JSONB NOT NULL,
    "enabled" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "skills_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "tools" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "provider_type" TEXT NOT NULL,
    "input_schema" JSONB NOT NULL,
    "output_schema" JSONB NOT NULL,
    "permission_scopes" JSONB NOT NULL,
    "timeout_ms" INTEGER,
    "side_effecting" BOOLEAN NOT NULL,
    "metadata" JSONB,
    "enabled" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "tools_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "tool_calls" (
    "id" TEXT NOT NULL,
    "execution_id" TEXT NOT NULL,
    "step_id" TEXT NOT NULL,
    "tool_id" TEXT NOT NULL,
    "provider_type" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "input_summary" JSONB NOT NULL,
    "output_summary" JSONB,
    "error" JSONB,
    "duration_ms" INTEGER,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "tool_calls_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "permission_policies" (
    "id" TEXT NOT NULL,
    "app_id" TEXT NOT NULL,
    "tool_id" TEXT NOT NULL,
    "scope" TEXT NOT NULL,
    "policy" TEXT NOT NULL,
    "conditions" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "permission_policies_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "mcp_providers" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "server_url" TEXT NOT NULL,
    "auth_type" TEXT NOT NULL,
    "auth_config" JSONB,
    "discovered_tools" JSONB,
    "last_discovered_at" TIMESTAMP(3),
    "enabled" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "mcp_providers_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "execution_logs" (
    "id" TEXT NOT NULL,
    "execution_id" TEXT NOT NULL,
    "level" TEXT NOT NULL,
    "event_type" TEXT NOT NULL,
    "message" TEXT NOT NULL,
    "summary" JSONB,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "execution_logs_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "idx_executions_app_id" ON "executions"("app_id");

-- CreateIndex
CREATE INDEX "idx_executions_session_id" ON "executions"("session_id");

-- CreateIndex
CREATE INDEX "idx_executions_skill_id" ON "executions"("skill_id");

-- CreateIndex
CREATE INDEX "idx_executions_status" ON "executions"("status");

-- CreateIndex
CREATE INDEX "idx_executions_created_at" ON "executions"("created_at");

-- CreateIndex
CREATE INDEX "idx_workflow_steps_execution_id" ON "workflow_steps"("execution_id");

-- CreateIndex
CREATE INDEX "idx_skills_name_version" ON "skills"("name", "version");

-- CreateIndex
CREATE INDEX "idx_tools_provider_type" ON "tools"("provider_type");

-- CreateIndex
CREATE INDEX "idx_tool_calls_execution_id" ON "tool_calls"("execution_id");

-- CreateIndex
CREATE UNIQUE INDEX "permission_policy_app_tool_scope_key" ON "permission_policies"("app_id", "tool_id", "scope");

-- CreateIndex
CREATE INDEX "idx_execution_logs_execution_id" ON "execution_logs"("execution_id");

-- AddForeignKey
ALTER TABLE "workflow_steps" ADD CONSTRAINT "workflow_steps_execution_id_fkey" FOREIGN KEY ("execution_id") REFERENCES "executions"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "tool_calls" ADD CONSTRAINT "tool_calls_execution_id_fkey" FOREIGN KEY ("execution_id") REFERENCES "executions"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "tool_calls" ADD CONSTRAINT "tool_calls_tool_id_fkey" FOREIGN KEY ("tool_id") REFERENCES "tools"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "execution_logs" ADD CONSTRAINT "execution_logs_execution_id_fkey" FOREIGN KEY ("execution_id") REFERENCES "executions"("id") ON DELETE CASCADE ON UPDATE CASCADE;
