from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_root_compose_defines_canonical_pgvector_database() -> None:
    compose = _read("compose.yml")

    assert "pgvector/pgvector:pg16" in compose
    assert '"${RAGENIUS_POSTGRES_PORT:-5433}:5432"' in compose
    assert "container_name:" not in compose
    assert "ragenius_postgres_data:/var/lib/postgresql/data" in compose
    assert "rag_subsystem/sql/init_pgvector.sql:/docker-entrypoint-initdb.d/20-init-pgvector.sql:ro" in compose
    assert "docker/postgres/init/10-create-execution-database.sql:/docker-entrypoint-initdb.d/10-create-execution-database.sql:ro" in compose
    assert "pg_isready -U ragenius -d ragenius" in compose


def test_execution_database_initializer_is_idempotent() -> None:
    initializer = _read("docker/postgres/init/10-create-execution-database.sql")

    assert "WHERE NOT EXISTS" in initializer
    assert "CREATE DATABASE ragenius_execution OWNER ragenius" in initializer
    assert "\\gexec" in initializer


def test_environment_templates_use_canonical_database_urls() -> None:
    app_env = _read("ragenius_app_skeleton/.env.example")
    builder_env = _read("ragenius_builder/.env.example")
    execution_env = _read("ragenius_execution_subsystem/.env.example")

    rag_dsn = "postgresql://ragenius:ragenius@localhost:5433/ragenius"
    execution_dsn = "postgresql://ragenius:ragenius@localhost:5433/ragenius_execution?schema=public"

    assert f"RAG_VECTOR_STORE_DSN={rag_dsn}" in app_env
    assert f"RAG_VECTOR_STORE_DSN={rag_dsn}" in builder_env
    assert f'DATABASE_URL="{execution_dsn}"' in execution_env


def test_execution_environment_template_preserves_safe_agent_defaults() -> None:
    execution_env = _read("ragenius_execution_subsystem/.env.example")

    expected_defaults = (
        'CODEX_MCP_ELICITATION_ENABLED="false"',
        'CODEX_INTERACTIVE_AUTH_HANDOFF_ENABLED="false"',
        'CODEX_INTERACTIVE_USER_ACTION_ENABLED="false"',
        'CODEX_MCP_AUTH_ALLOWED_HOSTS_JSON="[]"',
        'CODEX_MANAGED_AUTH_TARGETS_JSON="[]"',
    )
    for setting in expected_defaults:
        assert setting in execution_env


def test_database_consumers_run_shared_preflight() -> None:
    preflight = REPO_ROOT / "scripts" / "Test-RageniusPostgres.ps1"
    assert preflight.is_file()

    expected_calls = {
        "ragenius_app_skeleton/start-ragenius-app-skeleton.ps1": "RAG_VECTOR_STORE_DSN",
        "ragenius_builder/start-ragenius-builder.ps1": "RAG_VECTOR_STORE_DSN",
        "ragenius_execution_subsystem/start-ragenius-execution-subsystem.ps1": "DATABASE_URL",
    }
    for relative_path, variable_name in expected_calls.items():
        startup_script = _read(relative_path)
        assert "Test-RageniusPostgres.ps1" in startup_script
        assert variable_name in startup_script


def test_python_database_requirements_support_windows_arm64() -> None:
    app_requirements = _read("ragenius_app_skeleton/backend/requirements.txt")
    root_project = _read("pyproject.toml")
    subsystem_project = _read("rag_subsystem/pyproject.toml")

    assert "pg8000>=1.31,<2" in app_requirements
    assert "psycopg[binary]" not in app_requirements
    assert "uvicorn[standard]" not in app_requirements
    assert "\nuvicorn\n" in f"\n{app_requirements}"
    assert "pdfplumber" not in app_requirements
    assert "pypdf>=5.0.0" in app_requirements
    assert 'pgvector = ["pg8000>=1.31,<2"]' in root_project
    assert 'pgvector = ["pg8000>=1.31,<2"]' in subsystem_project
