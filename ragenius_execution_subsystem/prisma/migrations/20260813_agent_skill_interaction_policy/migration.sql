ALTER TABLE "projected_agent_skill_governance"
ADD COLUMN "interaction_requirement" TEXT NOT NULL DEFAULT 'autonomous',
ADD COLUMN "supported_interaction_types_json" TEXT NOT NULL DEFAULT '[]',
ADD COLUMN "required_transport" TEXT NOT NULL DEFAULT 'one_shot',
ADD COLUMN "recovery_class" TEXT NOT NULL DEFAULT 'not_resumable';
