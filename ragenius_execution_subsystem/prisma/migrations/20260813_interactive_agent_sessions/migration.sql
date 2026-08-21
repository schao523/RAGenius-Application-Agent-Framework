CREATE TABLE "agent_sessions" (
    "id" TEXT NOT NULL,
    "execution_id" TEXT NOT NULL,
    "app_id" TEXT NOT NULL,
    "session_id" TEXT NOT NULL,
    "backend" TEXT NOT NULL,
    "transport" TEXT NOT NULL,
    "state" TEXT NOT NULL,
    "provider_session_ref" TEXT NOT NULL,
    "provider_run_ref" TEXT,
    "provider_turn_ref" TEXT,
    "continuation_mode" TEXT NOT NULL,
    "protocol_version" TEXT NOT NULL,
    "capability_snapshot" JSONB NOT NULL,
    "last_interaction_seq" INTEGER NOT NULL DEFAULT 0,
    "last_event_seq" INTEGER NOT NULL DEFAULT 0,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "agent_sessions_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "agent_interactions" (
    "id" TEXT NOT NULL,
    "execution_id" TEXT NOT NULL,
    "agent_session_id" TEXT NOT NULL,
    "app_id" TEXT NOT NULL,
    "session_id" TEXT NOT NULL,
    "sequence" INTEGER NOT NULL,
    "type" TEXT NOT NULL,
    "state" TEXT NOT NULL,
    "prompt" TEXT NOT NULL,
    "options" JSONB NOT NULL,
    "allows_free_text" BOOLEAN NOT NULL,
    "secret_input" BOOLEAN NOT NULL DEFAULT false,
    "provider_correlation_ref" TEXT NOT NULL,
    "policy_binding_hash" TEXT NOT NULL,
    "version" INTEGER NOT NULL DEFAULT 1,
    "expires_at" TIMESTAMP(3) NOT NULL,
    "resolved_at" TIMESTAMP(3),
    "response_summary" JSONB,
    "idempotency_key" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "agent_interactions_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "agent_execution_events" (
    "id" TEXT NOT NULL,
    "execution_id" TEXT NOT NULL,
    "app_id" TEXT NOT NULL,
    "session_id" TEXT NOT NULL,
    "sequence" INTEGER NOT NULL,
    "type" TEXT NOT NULL,
    "provider_event_ref" TEXT,
    "interaction_id" TEXT,
    "payload" JSONB NOT NULL,
    "occurred_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "agent_execution_events_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "agent_sessions_execution_id_key" ON "agent_sessions"("execution_id");
CREATE INDEX "idx_agent_sessions_app_session" ON "agent_sessions"("app_id", "session_id");
CREATE INDEX "idx_agent_sessions_state" ON "agent_sessions"("state");
CREATE UNIQUE INDEX "agent_interactions_execution_sequence_key" ON "agent_interactions"("execution_id", "sequence");
CREATE UNIQUE INDEX "agent_interactions_execution_provider_ref_key" ON "agent_interactions"("execution_id", "provider_correlation_ref");
CREATE INDEX "idx_agent_interactions_scope" ON "agent_interactions"("app_id", "session_id", "execution_id");
CREATE INDEX "idx_agent_interactions_state_expiry" ON "agent_interactions"("state", "expires_at");
CREATE UNIQUE INDEX "agent_execution_events_execution_sequence_key" ON "agent_execution_events"("execution_id", "sequence");
CREATE UNIQUE INDEX "agent_execution_events_execution_provider_ref_key" ON "agent_execution_events"("execution_id", "provider_event_ref");
CREATE INDEX "idx_agent_execution_events_scope" ON "agent_execution_events"("app_id", "session_id", "execution_id");

ALTER TABLE "agent_sessions" ADD CONSTRAINT "agent_sessions_execution_id_fkey"
FOREIGN KEY ("execution_id") REFERENCES "executions"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "agent_interactions" ADD CONSTRAINT "agent_interactions_execution_id_fkey"
FOREIGN KEY ("execution_id") REFERENCES "executions"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "agent_interactions" ADD CONSTRAINT "agent_interactions_agent_session_id_fkey"
FOREIGN KEY ("agent_session_id") REFERENCES "agent_sessions"("id") ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "agent_execution_events" ADD CONSTRAINT "agent_execution_events_execution_id_fkey"
FOREIGN KEY ("execution_id") REFERENCES "executions"("id") ON DELETE CASCADE ON UPDATE CASCADE;
