# RAGenius Windows Demo Package Design

Date: 2026-06-18

## 1. Objective

Create a Windows-only demo distribution for the complete RAGenius system. A user on another PC must be able to:

1. install Docker Desktop with WSL2;
2. download a small ZIP release;
3. enter their own LLM and optional external-service credentials;
4. run one PowerShell installation command;
5. open the Builder and end-user application;
6. demonstrate retrieval, application instructions, skills, execution, and selected external integrations;
7. restore the demo to a known clean state.

The release downloads public, versioned container images from GitHub Container Registry (GHCR). It does not package source trees, development dependencies, production credentials, or customer data.

## 2. Selected Approach

Use a ZIP-based Windows distribution containing Docker Compose configuration, PowerShell lifecycle scripts, sanitized demo snapshots, and documentation.

Each production application remains a separate service:

- `ragenius-app-frontend`
- `ragenius-app-backend`
- `ragenius-builder`
- `ragenius-execution`
- `ragenius-demo-init`
- shared RAG/application PostgreSQL with pgvector
- isolated Execution PostgreSQL

This is preferred over a single combined image because the repository has distinct Python, Node.js, storage, health, and security boundaries. It is preferred over a native EXE installer for the first release because Docker Compose gives repeatable dependencies and useful service-level diagnostics.

## 3. Release Artifact

The generated release is:

```text
RAGenius-Demo-<version>-Windows.zip
└── RAGenius-Demo/
    ├── Install.ps1
    ├── Start-RAGenius.ps1
    ├── Stop-RAGenius.ps1
    ├── Reset-Demo.ps1
    ├── Status-RAGenius.ps1
    ├── Open-RAGenius.ps1
    ├── Uninstall-RAGenius.ps1
    ├── docker-compose.demo.yml
    ├── .env.template
    ├── README-Windows.md
    ├── VERSION
    └── demo-data/
        ├── manifest.json
        ├── builder/
        ├── instructions/
        ├── documents/
        ├── skills/
        └── database/
```

The release ZIP contains no `.env` file. `Install.ps1` creates `.env` from `.env.template` and never overwrites an existing `.env`.

## 4. Container Images

Images are published publicly to GHCR:

```text
ghcr.io/schao523/ragenius-app-frontend:<version>
ghcr.io/schao523/ragenius-app-backend:<version>
ghcr.io/schao523/ragenius-builder:<version>
ghcr.io/schao523/ragenius-execution:<version>
ghcr.io/schao523/ragenius-demo-init:<version>
```

Release Compose files use immutable version tags. CI also publishes a matching commit-SHA tag. The ZIP must never use `latest`.

Each application image is a production image:

- dependencies are installed at image-build time;
- frontend assets are built at image-build time;
- source directories are not bind-mounted from the target PC;
- application processes run as non-root where practical;
- health checks are defined;
- writable state is mounted only at declared volume locations.

The database services may use pinned upstream PostgreSQL/pgvector images rather than repository-owned wrappers.

## 5. Service and Storage Boundaries

### Shared RAG/Application Database

The App backend and `rag_subsystem` use one PostgreSQL database with pgvector. Retrieval and ingestion remain implemented by `rag_subsystem`. All chunks and retrieval operations remain scoped by `app_id`.

### Builder State

The supported Builder is `ragenius_builder/flask_scaffold/app.py`.

Builder uses:

- a writable SQLite database;
- writable upload storage;
- writable skill storage;
- file-backed application instructions at:

```text
instructions/{app_id}/instructions.md
```

Database instruction rows retain metadata and URI information. The demo initializer must not replace file-backed instructions with database-only content.

### Execution State

`ragenius_execution_subsystem` uses its own PostgreSQL database. Its Prisma schema and migrations must never run against the shared RAG/application database.

Execution artifacts use a separate writable volume. Filesystem allowlists use container paths, never paths from the build PC.

## 6. Immutable Snapshot and Writable Runtime Data

The demo initializer image contains a sanitized, immutable factory snapshot. Running services use writable Docker volumes.

Factory snapshot contents include:

- stable demo application IDs and unique names;
- application metadata and settings;
- instruction Markdown snapshots;
- sample documents and metadata;
- published skill versions and app-skill bindings;
- database seed or migration inputs;
- optional precomputed vectors created with the declared embedding model;
- a dataset manifest and checksums.

Writable named volumes include:

```text
ragenius_demo_rag_db
ragenius_demo_execution_db
ragenius_demo_builder_state
ragenius_demo_instructions
ragenius_demo_uploads
ragenius_demo_skills
ragenius_demo_artifacts
```

The initializer copies or imports factory data only when the installed dataset marker is absent. Normal restarts do not overwrite user changes.

## 7. Demo Dataset

The initial release should contain two small, clearly separated applications. Each has a stable `app_id`, distinct instructions, distinct documents, and explicit skill bindings. At least one pair of similarly worded documents should be included to test that cross-application retrieval does not occur.

The manifest records:

```json
{
  "schema_version": 1,
  "dataset_version": "1.0.0",
  "system_version": "1.0.0",
  "embedding_model": "BAAI/bge-large-zh-v1.5",
  "applications": [],
  "checksums": {}
}
```

Preferred vector strategy:

1. ship source documents as the canonical snapshot;
2. ship precomputed vectors only when model identity and vector schema are fixed;
3. otherwise run an installation-time ingestion job and cache model files in a Docker volume.

The initializer validates:

- application names are unique;
- all application-owned records have a known `app_id`;
- instructions exist at the required file-backed path;
- documents and vector rows have matching application ownership;
- skills and bindings reference existing versions;
- checksums match the manifest.

## 8. Configuration and Secrets

`.env.template` separates required and optional values.

Required configuration includes:

- image owner and release version;
- local port assignments;
- generated database passwords;
- LLM provider selection;
- required LLM API key.

Optional integration configuration includes values such as:

- `SEMANTIC_SCHOLAR_API_KEY`;
- `MCP_SERVERS_JSON`;
- provider-specific OAuth access tokens;
- NotebookLM configuration;
- OpenAI-compatible model/base URL settings supported by the runtime.

`Install.ps1` generates strong local database passwords and writes them to `.env`. User API keys are entered locally. Scripts must avoid printing secret values. `.env` is excluded from release archives, image build contexts, logs, and diagnostic bundles.

External tools are disabled unless their required configuration is present. Missing optional credentials degrade the affected integration only; core Builder, App, RAG, and Execution services remain usable.

## 9. Network and Ports

Only user-facing ports are published to the Windows host. Database ports remain internal to the Compose network unless a diagnostic profile explicitly exposes them.

Suggested defaults:

- end-user application: `http://localhost:8080`
- Builder: `http://localhost:8011`
- Execution API: not public by default
- application backend: not public by default

The frontend or reverse proxy routes backend traffic internally. The Builder reaches Execution through the Compose service name. Execution reaches Builder using `BUILDER_BASE_URL=http://ragenius-builder:<port>`.

## 10. Installation Flow

`Install.ps1` performs these idempotent steps:

1. verify Windows PowerShell/PowerShell and 64-bit Windows;
2. verify Docker Desktop, Docker Compose v2, and a running Linux container engine;
3. verify required ports are available;
4. create `.env` without replacing existing secrets;
5. validate required LLM configuration;
6. pull the pinned GHCR images;
7. create the Compose project and named volumes;
8. start databases and wait for health checks;
9. run database migrations/bootstrap;
10. run the one-shot demo initializer;
11. start application services;
12. run readiness and isolation smoke checks;
13. print URLs and optionally open the browser.

A failed step exits nonzero and prints the service and log command required for diagnosis. Re-running installation resumes safely.

## 11. Lifecycle Scripts

### Start

`Start-RAGenius.ps1` starts the existing Compose project, waits for readiness, and prints URLs.

### Stop

`Stop-RAGenius.ps1` stops containers without deleting volumes or `.env`.

### Status

`Status-RAGenius.ps1` reports Docker availability, container health, service URLs, dataset version, and failed health checks. It never prints credentials.

### Open

`Open-RAGenius.ps1` opens the end-user application and Builder URLs.

### Reset

`Reset-Demo.ps1` requires explicit confirmation, then:

1. stops RAGenius containers;
2. deletes only named volumes owned by the RAGenius demo Compose project;
3. preserves `.env`;
4. recreates databases and writable storage;
5. restores the immutable snapshot through the initializer;
6. restarts and verifies services.

The script must verify the exact Compose project and volume names before deletion.

### Uninstall

`Uninstall-RAGenius.ps1` removes containers and offers separate choices for deleting demo volumes and `.env`. Images are not deleted by default.

## 12. External Tool Integrations

The package includes the Execution subsystem and its supported external integration configuration, but it does not include live credentials.

Integration states are:

- configured and available;
- disabled because credentials/configuration are absent;
- configured but unhealthy;
- pending user confirmation for side-effecting operations.

Read-only integrations may be demonstrated after configuration. Write-capable integrations remain governed by the existing review and confirmation policy. The demo packaging layer must not bypass `ToolEngine`, permission checks, MCP allowlists, artifact scoping, or confirmation gates.

Demo documentation must distinguish implemented live providers from controlled seams or mocks.

## 13. Health, Readiness, and Verification

Installation is successful only when automated checks verify:

- all required containers are healthy;
- Builder can read both demo applications;
- instruction metadata resolves to the expected Markdown file;
- App backend can retrieve content for each demo application;
- a cross-app leakage probe returns no foreign application content;
- Execution can reach Builder;
- an internal non-side-effecting sample skill completes;
- database schema/dataset versions match the release manifest;
- optional integrations report disabled rather than crashing when credentials are absent.

CI verifies:

1. unit and integration tests for each component;
2. production image builds;
3. container vulnerability scanning;
4. Compose startup from a clean environment;
5. initialization and restart idempotency;
6. reset and second initialization;
7. app-isolation smoke tests;
8. secret scanning of images and ZIP contents;
9. installation documentation commands.

## 14. GHCR Publishing

A tagged release workflow:

1. checks out the repository and required nested application source;
2. runs component tests;
3. builds multi-stage production images;
4. tags images with release version and commit SHA;
5. pushes public images to GHCR;
6. renders `docker-compose.demo.yml` with pinned tags;
7. builds the sanitized initializer snapshot;
8. assembles the Windows ZIP;
9. runs a clean-machine-style Compose smoke test;
10. publishes checksums and the ZIP as GitHub Release assets.

Public packages need anonymous pull access. Source-code visibility and container-package visibility are managed independently according to GitHub repository policy.

## 15. Upgrade Policy

The first demo release supports clean installation and reset. In-place migration between demo dataset versions is not required initially.

For an upgrade:

- scripts pull a new pinned version;
- database migrations are forward-only;
- factory snapshots never overwrite an installed writable dataset;
- users may choose reset-to-new-demo-data explicitly;
- `.env` remains local and is migrated only through additive template checks.

## 16. Security and Data Rules

The release must not contain:

- real API keys, passwords, OAuth tokens, cookies, or browser profiles;
- production/customer documents or instructions;
- real user sessions or chat history;
- sensitive execution logs;
- build-machine absolute paths;
- writable host-root mounts;
- Docker socket access.

The release must preserve:

- `app_id`-scoped retrieval and storage;
- unique application names;
- read-only external lookup semantics where defined;
- Builder ownership of admin workflows;
- App ownership of user chat workflows;
- `rag_subsystem` ownership of retrieval and ingestion;
- separate Execution persistence and side-effect policy.

## 17. Acceptance Criteria

The package is acceptable when a clean Windows 10/11 PC with Docker Desktop and internet access can:

1. extract the ZIP into a user-writable directory;
2. configure one supported LLM API key;
3. run `.\Install.ps1`;
4. reach the end-user app and Builder;
5. query preloaded documents with citations;
6. edit file-backed instructions and observe the changed application behavior;
7. execute a safe sample skill;
8. configure and test at least one external read integration;
9. demonstrate that one application's content is not retrieved by another;
10. run `.\Reset-Demo.ps1` and recover the exact factory dataset;
11. restart Windows/Docker and resume the writable state with `.\Start-RAGenius.ps1`.

## 18. Initial Implementation Scope

The first implementation should deliver:

- production Dockerfiles for all four application services;
- one Compose demo topology;
- one initializer image and versioned snapshot format;
- two isolated demo applications;
- PowerShell install/start/stop/status/open/reset/uninstall scripts;
- public GHCR publishing workflow;
- GitHub Release ZIP assembly;
- automated health, reset, and isolation smoke tests;
- Windows installation and external-integration documentation.

A native `.exe`/MSI installer, Kubernetes deployment, offline image archives, automatic Docker Desktop installation, and production-grade backup/restore are explicitly deferred.
