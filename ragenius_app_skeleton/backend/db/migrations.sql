-- ============================================================
-- RAGenius App Skeleton - PostgreSQL Migration (Idempotent)
-- ============================================================
-- Scope:
-- - App-side metadata/audit tables only
-- - rag_subsystem vector/chunk tables remain out of scope
-- ============================================================

BEGIN;

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================================
-- collections
-- ============================================================
CREATE TABLE IF NOT EXISTS collections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    domain TEXT NOT NULL,
    active_config_version INTEGER,
    active_adapter_version INTEGER,
    active_template_version INTEGER,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_collections_domain
    ON collections(domain);

CREATE INDEX IF NOT EXISTS idx_collections_active_config_version
    ON collections(active_config_version);

CREATE INDEX IF NOT EXISTS idx_collections_active_adapter_version
    ON collections(active_adapter_version);

CREATE INDEX IF NOT EXISTS idx_collections_active_template_version
    ON collections(active_template_version);

-- ============================================================
-- config_instructions
-- ============================================================
CREATE TABLE IF NOT EXISTS config_instructions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    collection_id UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    version INTEGER NOT NULL CHECK (version > 0),
    source_pdf_name TEXT,
    config_json JSONB NOT NULL,
    extracted_text TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (collection_id, version)
);

CREATE INDEX IF NOT EXISTS idx_config_instructions_collection_id
    ON config_instructions(collection_id);

CREATE INDEX IF NOT EXISTS idx_config_instructions_collection_version
    ON config_instructions(collection_id, version DESC);

-- ============================================================
-- adapter_versions
-- ============================================================
CREATE TABLE IF NOT EXISTS adapter_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    collection_id UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    version INTEGER NOT NULL CHECK (version > 0),
    adapter_json JSONB NOT NULL,
    is_draft BOOLEAN NOT NULL DEFAULT TRUE,
    is_approved BOOLEAN NOT NULL DEFAULT FALSE,
    approved_by TEXT,
    approved_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE (collection_id, version),
    CHECK (NOT (is_draft AND is_approved))
);

CREATE INDEX IF NOT EXISTS idx_adapter_versions_collection_id
    ON adapter_versions(collection_id);

CREATE INDEX IF NOT EXISTS idx_adapter_versions_collection_version
    ON adapter_versions(collection_id, version DESC);

CREATE INDEX IF NOT EXISTS idx_adapter_versions_collection_is_approved
    ON adapter_versions(collection_id, is_approved);

CREATE INDEX IF NOT EXISTS idx_adapter_versions_collection_is_draft
    ON adapter_versions(collection_id, is_draft);

-- optional safety: only one approved adapter per collection
CREATE UNIQUE INDEX IF NOT EXISTS uq_adapter_versions_one_approved_per_collection
    ON adapter_versions(collection_id)
    WHERE is_approved = TRUE;

-- ============================================================
-- sessions (required for session_id-based audit tables)
-- ============================================================
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    collection_id UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    config_version INTEGER NOT NULL CHECK (config_version > 0),
    adapter_version INTEGER NOT NULL CHECK (adapter_version > 0),
    template_version INTEGER NOT NULL CHECK (template_version > 0),
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP WITHOUT TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_sessions_collection_id
    ON sessions(collection_id);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id
    ON sessions(user_id);

CREATE INDEX IF NOT EXISTS idx_sessions_collection_user
    ON sessions(collection_id, user_id);

CREATE INDEX IF NOT EXISTS idx_sessions_collection_versions
    ON sessions(collection_id, config_version, adapter_version, template_version);

-- ============================================================
-- planner_outputs
-- ============================================================
CREATE TABLE IF NOT EXISTS planner_outputs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_query TEXT NOT NULL,
    planner_output JSONB NOT NULL,
    confidence DOUBLE PRECISION,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_planner_outputs_session_id
    ON planner_outputs(session_id);

CREATE INDEX IF NOT EXISTS idx_planner_outputs_created_at
    ON planner_outputs(created_at DESC);

-- ============================================================
-- retrieval_runs
-- ============================================================
CREATE TABLE IF NOT EXISTS retrieval_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    planner_output_id UUID NOT NULL REFERENCES planner_outputs(id) ON DELETE CASCADE,
    retrieval_plan JSONB NOT NULL,
    result_count INTEGER,
    debug_trace JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_retrieval_runs_planner_output_id
    ON retrieval_runs(planner_output_id);

CREATE INDEX IF NOT EXISTS idx_retrieval_runs_created_at
    ON retrieval_runs(created_at DESC);

-- ============================================================
-- chat_messages
-- ============================================================
CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    citations JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id
    ON chat_messages(session_id);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created_at
    ON chat_messages(session_id, created_at);

-- ============================================================
-- documents
-- ============================================================
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    collection_id UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,
    content_type TEXT NOT NULL,
    version TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_collection_id
    ON documents(collection_id);

CREATE INDEX IF NOT EXISTS idx_documents_collection_created_at
    ON documents(collection_id, created_at DESC);

-- ============================================================
-- ingestion_runs
-- ============================================================
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    collection_id UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    document_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'success', 'failed')),
    warnings JSONB,
    debug_trace JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_collection_id
    ON ingestion_runs(collection_id);

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_collection_status
    ON ingestion_runs(collection_id, status);

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_created_at
    ON ingestion_runs(created_at DESC);

-- ============================================================
-- updated_at trigger for collections
-- ============================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_collections_set_updated_at ON collections;

CREATE TRIGGER trg_collections_set_updated_at
BEFORE UPDATE ON collections
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

COMMIT;

