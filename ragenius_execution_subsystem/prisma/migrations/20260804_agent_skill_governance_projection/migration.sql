CREATE TABLE "agent_skill_projection_revisions" (
    "id" TEXT NOT NULL,
    "builder_instance_id" TEXT NOT NULL,
    "revision" INTEGER NOT NULL,
    "digest" TEXT NOT NULL,
    "generated_at" TIMESTAMP(3) NOT NULL,
    "received_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "status" TEXT NOT NULL,

    CONSTRAINT "agent_skill_projection_revisions_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "projected_agent_skill_governance" (
    "id" TEXT NOT NULL,
    "projection_revision_id" TEXT NOT NULL,
    "app_id" TEXT NOT NULL,
    "agent_skill_id" TEXT NOT NULL,
    "backend" TEXT NOT NULL,
    "runtime_target_id" TEXT NOT NULL,
    "source_id" TEXT NOT NULL,
    "protected_locator_ref" TEXT NOT NULL,
    "provider_skill_name" TEXT NOT NULL,
    "display_name" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "current_fingerprint" TEXT NOT NULL,
    "approved_fingerprint" TEXT NOT NULL,
    "source_enabled" BOOLEAN NOT NULL,
    "approval_state" TEXT NOT NULL,
    "binding_enabled" BOOLEAN NOT NULL,
    "model_visible" BOOLEAN NOT NULL,
    "user_invocable" BOOLEAN NOT NULL,
    "direct_tool_dispatch" BOOLEAN NOT NULL,

    CONSTRAINT "projected_agent_skill_governance_pkey" PRIMARY KEY ("id")
);

CREATE TABLE "agent_skill_projection_head" (
    "id" TEXT NOT NULL,
    "active_revision_id" TEXT NOT NULL,

    CONSTRAINT "agent_skill_projection_head_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "agent_skill_projection_builder_revision_key"
ON "agent_skill_projection_revisions"("builder_instance_id", "revision");

CREATE INDEX "idx_agent_skill_projection_revisions_status"
ON "agent_skill_projection_revisions"("status");

CREATE UNIQUE INDEX "projected_agent_skill_revision_app_skill_key"
ON "projected_agent_skill_governance"("projection_revision_id", "app_id", "agent_skill_id");

CREATE INDEX "idx_projected_agent_skill_revision_app_backend"
ON "projected_agent_skill_governance"("projection_revision_id", "app_id", "backend");

CREATE INDEX "idx_projected_agent_skill_revision_app_skill"
ON "projected_agent_skill_governance"("projection_revision_id", "app_id", "agent_skill_id");

CREATE UNIQUE INDEX "agent_skill_projection_head_active_revision_id_key"
ON "agent_skill_projection_head"("active_revision_id");

ALTER TABLE "projected_agent_skill_governance"
ADD CONSTRAINT "projected_agent_skill_governance_projection_revision_id_fkey"
FOREIGN KEY ("projection_revision_id") REFERENCES "agent_skill_projection_revisions"("id")
ON DELETE CASCADE ON UPDATE CASCADE;

ALTER TABLE "agent_skill_projection_head"
ADD CONSTRAINT "agent_skill_projection_head_active_revision_id_fkey"
FOREIGN KEY ("active_revision_id") REFERENCES "agent_skill_projection_revisions"("id")
ON DELETE RESTRICT ON UPDATE CASCADE;
