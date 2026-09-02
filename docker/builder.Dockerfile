FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY pyproject.toml README.md ./
COPY rag_subsystem ./rag_subsystem
COPY shared ./shared
COPY ragenius_builder/requirements.txt ./ragenius_builder/requirements.txt

RUN python -m pip install --upgrade pip \
    && python -m pip install -e ".[pgvector,pdf-extract]" \
    && python -m pip install -r ragenius_builder/requirements.txt

COPY ragenius_builder ./ragenius_builder
COPY workflows ./workflows
COPY scripts/install_demo_seed.py ./scripts/install_demo_seed.py

ENV RAGENIUS_BUILDER_DB=/runtime/demo/builder/rag_app.db
ENV RAGENIUS_BUILDER_STORAGE_ROOT=/runtime/demo/builder
ENV RAGENIUS_INSTRUCTION_MODEL_SNAPSHOT_ROOT=/runtime/demo/builder/instruction_understanding
ENV RAGENIUS_EXECUTION_BASE_URL=http://execution:3001

EXPOSE 8011

WORKDIR /app/ragenius_builder/flask_scaffold
CMD ["python", "-m", "flask", "--app", "app.py", "run", "--host", "0.0.0.0", "--port", "8011"]
