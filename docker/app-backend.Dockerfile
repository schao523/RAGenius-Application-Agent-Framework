FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY pyproject.toml README.md ./
COPY rag_subsystem ./rag_subsystem
COPY shared ./shared
COPY ragenius_app_skeleton/backend/requirements.txt ./ragenius_app_skeleton/backend/requirements.txt
COPY ragenius_builder/requirements.txt ./ragenius_builder/requirements.txt

RUN python -m pip install --upgrade pip \
    && python -m pip install -e ".[pgvector,pdf-extract,local-embeddings]" \
    && python -m pip install -r ragenius_app_skeleton/backend/requirements.txt \
    && python -m pip install -r ragenius_builder/requirements.txt

COPY ragenius_app_skeleton/backend ./ragenius_app_skeleton/backend
COPY ragenius_app_skeleton/prompts ./ragenius_app_skeleton/prompts
COPY ragenius_app_skeleton/schemas ./ragenius_app_skeleton/schemas
COPY ragenius_app_skeleton/workflows ./ragenius_app_skeleton/workflows
COPY ragenius_builder ./ragenius_builder
COPY workflows ./workflows
COPY scripts/install_demo_seed.py ./scripts/install_demo_seed.py

ENV RAGENIUS_BUILDER_DB=/runtime/demo/builder/rag_app.db
ENV RAGENIUS_APP_STATE_DB=/runtime/demo/app/.state/runtime_state.db
ENV RAGENIUS_APP_UPLOADS_DIR=/runtime/demo/app/.state/session_uploads
ENV RAGENIUS_EXECUTION_SUBSYSTEM_URL=http://execution:3001/v1

EXPOSE 8000

WORKDIR /app/ragenius_app_skeleton
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
