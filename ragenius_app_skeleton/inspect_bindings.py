import json
p = r"ragenius_app_skeleton/backend/.state/instruction_understanding_snapshots/2302c77b-3d82-4650-bd15-e0ff9c0faab7/understanding.json"
with open(p, encoding="utf-8") as f:
    data = json.load(f)
model = data["compiled_contract"]["hybrid_instruction_runtime_model"]
for key in ["dependency_groups","task_module_mappings","phase_resource_bindings","module_orchestration"]:
    print("===", key, "===")
    val = model.get(key)
    if isinstance(val, list):
        for item in val:
            if "??" in str(item) or "observation_guide.md" in str(item) or "identify_relationship" in str(item) or "examine_structure" in str(item) or "formulate_questions" in str(item) or "????" in str(item):
                print(item)
    else:
        print(val)
