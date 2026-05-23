import json, sys
sys.stdout.reconfigure(encoding="utf-8")
p = r"ragenius_app_skeleton/backend/.state/instruction_understanding_snapshots/2302c77b-3d82-4650-bd15-e0ff9c0faab7/understanding.json"
with open(p, encoding="utf-8") as f:
    data = json.load(f)
for key in ['step_candidates','instruction_units','instruction_blocks','instruction_modules','instruction_workflows','resource_reference_catalog']:
    print('===', key, '===')
    val = data['compiled_contract'].get(key) or []
    for item in val:
        text = json.dumps(item, ensure_ascii=False)
        if any(token in text for token in ['????','Observation','observation_guide.md','identify_relationship_guide.md','examine_structure_guide.md','formulate_questions_guide.md','??????','????????.pdf']):
            print(text)
