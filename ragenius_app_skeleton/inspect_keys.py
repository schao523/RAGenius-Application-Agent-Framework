import json, sys
sys.stdout.reconfigure(encoding="utf-8")
p = r"ragenius_app_skeleton/backend/.state/instruction_understanding_snapshots/2302c77b-3d82-4650-bd15-e0ff9c0faab7/understanding.json"
with open(p, encoding="utf-8") as f:
    data = json.load(f)
print(data.keys())
print(data.get('compiled_contract', {}).keys())
print(data.get('compiled_contract', {}).get('hybrid_instruction_runtime_model', {}).keys())
