CREATE INDEX IF NOT EXISTS "idx_executions_app_session"
ON "executions" ("app_id", "session_id");
