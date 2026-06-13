## RAGenius Builder

`ragenius_builder/flask_scaffold/` is the primary builder/admin application in this repository.

Use the Flask scaffold for builder work:

```bash
cd ragenius_builder/flask_scaffold
flask --app app.py run --reload
```

What is active:

- admin workflows
- apps CRUD
- instructions markdown editor
- schema-driven settings UI
- uploads and docs management
- search admin tooling
- read-only subsystem settings visibility

What is not active:

- the older FastAPI prototype that previously lived at `ragenius_builder/main.py`

That prototype has been quarantined under `ragenius_builder/archived_fastapi_prototype/` so it remains available for historical reference without presenting itself as a second supported runtime.
