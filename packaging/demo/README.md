# RAGenius Windows Docker Demo

This package runs the public RAGenius demo from GHCR images and immutable seed data.

## Quick start

```powershell
Expand-Archive RAGenius-Demo-<version>-Windows.zip
cd RAGenius-Demo
Copy-Item .env.template .env
# Edit .env and set DEEPSEEK_API_KEY or another supported LLM key.
.\Install.ps1
.\Start.ps1
```

Open:

- Application Runner: http://127.0.0.1:5173
- Builder: http://127.0.0.1:8011

## Runtime data model

`demo-data/` is mounted read-only and is not modified. Writable state is stored in Docker volumes:

- `ragenius_demo_runtime`
- `ragenius_demo_postgres`

Use `.\Stop.ps1` to stop containers while keeping data. Use `.\Reset.ps1` to delete volumes and recreate the runtime from seed data.
