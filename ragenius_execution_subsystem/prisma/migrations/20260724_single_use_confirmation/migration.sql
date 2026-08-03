CREATE TABLE "execution_confirmations" (
    "id" TEXT NOT NULL,
    "execution_id" TEXT NOT NULL,
    "app_id" TEXT NOT NULL,
    "session_id" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "decision" TEXT NOT NULL DEFAULT 'pending',
    "policy_snapshot" JSONB NOT NULL,
    "expires_at" TIMESTAMP(3) NOT NULL,
    "decided_at" TIMESTAMP(3),
    "consumed_at" TIMESTAMP(3),
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "execution_confirmations_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "execution_confirmations_execution_id_key"
ON "execution_confirmations"("execution_id");

CREATE INDEX "idx_execution_confirmations_app_session"
ON "execution_confirmations"("app_id", "session_id");

CREATE INDEX "idx_execution_confirmations_status"
ON "execution_confirmations"("status");

CREATE INDEX "idx_execution_confirmations_expires_at"
ON "execution_confirmations"("expires_at");
