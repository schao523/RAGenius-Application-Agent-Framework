import json, sys
sys.stdout.reconfigure(encoding="utf-8")
p = r"ragenius_app_skeleton/backend/.state/instruction_understanding_snapshots/2302c77b-3d82-4650-bd15-e0ff9c0faab7/understanding.json"
with open(p, encoding="utf-8") as f:
    data = json.load(f)
model = data["compiled_contract"]["hybrid_instruction_runtime_model"]
for k,v in model.items():
    if isinstance(v, list):
        print(k, len(v))
    elif isinstance(v, dict):
        print(k, 'dict', list(v.keys())[:10])
    else:
        print(k, type(v).__name__, v)
