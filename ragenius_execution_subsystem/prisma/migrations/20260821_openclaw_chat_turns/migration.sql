ALTER TABLE "agent_sessions"
  ADD COLUMN "session_version" INTEGER NOT NULL DEFAULT 1,
  ADD COLUMN "turn_sequence" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "active_chat_turn_id" TEXT,
  ADD COLUMN "idle_expires_at" TIMESTAMP(3);

CREATE TABLE "agent_chat_turns" (
  "id" TEXT NOT NULL,
  "agent_session_id" TEXT NOT NULL,
  "execution_id" TEXT NOT NULL,
  "app_id" TEXT NOT NULL,
  "session_id" TEXT NOT NULL,
  "sequence" INTEGER NOT NULL,
  "idempotency_key" TEXT NOT NULL,
  "kind" TEXT NOT NULL,
  "state" TEXT NOT NULL,
  "acknowledgement_state" TEXT NOT NULL DEFAULT 'unacknowledged',
  "request_summary" JSONB NOT NULL,
  "provider_run_ref" TEXT,
  "normalized_result" JSONB,
  "completed_at" TIMESTAMP(3),
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "agent_chat_turns_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "agent_chat_turns_agent_session_id_fkey"
    FOREIGN KEY ("agent_session_id") REFERENCES "agent_sessions"("id")
    ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE UNIQUE INDEX "agent_chat_turns_session_sequence_key"
  ON "agent_chat_turns"("agent_session_id", "sequence");
CREATE UNIQUE INDEX "agent_chat_turns_session_idempotency_key"
  ON "agent_chat_turns"("agent_session_id", "idempotency_key");
CREATE INDEX "idx_agent_chat_turns_scope"
  ON "agent_chat_turns"("app_id", "session_id", "execution_id");
CREATE INDEX "idx_agent_chat_turns_state" ON "agent_chat_turns"("state");
