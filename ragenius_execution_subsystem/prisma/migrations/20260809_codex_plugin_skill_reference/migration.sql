ALTER TABLE "projected_agent_skill_governance"
ADD COLUMN "provider_skill_reference" TEXT;

UPDATE "projected_agent_skill_governance"
SET "provider_skill_reference" = "provider_skill_name"
WHERE "provider_skill_reference" IS NULL;

ALTER TABLE "projected_agent_skill_governance"
ALTER COLUMN "provider_skill_reference" SET NOT NULL;
