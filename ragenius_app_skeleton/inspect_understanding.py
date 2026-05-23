import json, sys
sys.stdout.reconfigure(encoding="utf-8")
p = r"ragenius_app_skeleton/backend/.state/instruction_understanding_snapshots/2302c77b-3d82-4650-bd15-e0ff9c0faab7/understanding.json"
with open(p, encoding="utf-8") as f:
    data = json.load(f)
model = data["compiled_contract"]["hybrid_instruction_runtime_model"]
for key in ["primary_service_mode","routing_rules","service_blocks","procedures","procedure_steps","interaction_logic_blocks"]:
    val = model.get(key)
    if key == "routing_rules":
        print("ROUTING_RULES")
        for item in val:
            if "bible" in str(item).lower() or "??" in str(item):
                print(json.dumps(item, ensure_ascii=False))
    elif key == "service_blocks":
        print("SERVICE_BLOCKS")
        for item in val:
            if "??" in str(item) or "??" in str(item) or "support_module" in str(item):
                print(json.dumps(item, ensure_ascii=False))
    elif key == "procedures":
        print("PROCEDURES")
        for item in val:
            if "??" in str(item) or "support_module" in str(item):
                print(json.dumps(item, ensure_ascii=False))
    elif key == "procedure_steps":
        print("PROCEDURE_STEPS")
        for item in val:
            if "??" in str(item) or "observation_guide.md" in str(item) or "identify_relationship" in str(item) or "examine_structure" in str(item) or "formulate_questions" in str(item):
                print(json.dumps(item, ensure_ascii=False))
    elif key == "interaction_logic_blocks":
        print("INTERACTION_LOGIC_BLOCKS")
        for item in val:
            if "??" in str(item) or "??" in str(item):
                print(json.dumps(item, ensure_ascii=False))
    else:
        print(key, val)
