import json, sys
sys.stdout.reconfigure(encoding="utf-8")
p = r"ragenius_app_skeleton/backend/.state/instruction_understanding_snapshots/2302c77b-3d82-4650-bd15-e0ff9c0faab7/understanding.json"
with open(p, encoding="utf-8") as f:
    data = json.load(f)
model = data["compiled_contract"]["hybrid_instruction_runtime_model"]
for key in ["instruction_service_blocks","instruction_procedures","procedure_steps","interaction_logic_blocks","resource_bindings"]:
    print('===', key, '===')
    val = model.get(key) or []
    for item in val:
        text = json.dumps(item, ensure_ascii=False)
        if any(token in text for token in ["??", "??", "observation_guide.md", "identify_relationship", "examine_structure", "formulate_questions", "????"]):
            print(text)
