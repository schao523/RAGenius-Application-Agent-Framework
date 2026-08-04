# Database-Backed Execution Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current in-memory execution persistence with a PostgreSQL/Prisma-backed execution store inside `ragenius_execution_subsystem` while preserving the existing execution, lookup, logs, and confirmation/resume APIs.

**Architecture:** Keep the `ExecutionStore` interface as the runtime persistence boundary. Add a `PrismaExecutionStore` implementation that persists execution records, original execution requests, and execution logs into PostgreSQL through Prisma. Preserve `InMemoryExecutionStore` for tests only, and wire the runtime to use the Prisma-backed store by default through the existing `src/db/prisma.ts` seam.

**Tech Stack:** Node.js 20+, TypeScript, Fastify, Prisma, PostgreSQL, Node test runner, Zod

---

## Scope and Design Notes

- `ragenius_execution_subsystem` owns execution lifecycle persistence.
- `ragenius_builder` does not own execution records or logs.
- The external `execution_id` should remain the subsystem’s stable public identifier.
- The first database-backed store should persist:
  - execution id
  - request type
  - app id
  - session id
  - skill id
  - original request payload
  - status
  - result type
  - result payload
  - files payload
  - errors payload
  - logs summary
  - timestamps
  - execution log entries
- `InMemoryExecutionStore` remains for unit tests and fast isolated route tests.
- Runtime startup should use Prisma-backed persistence, but test code should still be able to inject a different `ExecutionStore`.

## File Structure

### Existing files to modify

- `ragenius_execution_subsystem/prisma/schema.prisma`
  - Align the schema with the current runtime execution contract.
- `ragenius_execution_subsystem/src/db/prisma.ts`
  - Replace the stub with a real Prisma client creation seam.
- `ragenius_execution_subsystem/src/app.ts`
  - Wire Prisma-backed `ExecutionStore` into runtime services.
- `ragenius_execution_subsystem/src/server.ts`
  - Connect/disconnect Prisma client with app lifecycle.
- `ragenius_execution_subsystem/src/core/execution/execution-store.ts`
  - Keep the interface stable and preserve `InMemoryExecutionStore` for tests.
- `ragenius_execution_subsystem/src/core/execution/execution-status-service.ts`
  - Continue reading through the store interface.
- `ragenius_execution_subsystem/src/core/execution/execution-engine.ts`
  - No contract redesign; ensure persisted request/result shape remains compatible.
- `ragenius_execution_subsystem/README.md`
  - Document PostgreSQL/Prisma-backed execution persistence.

### New files to create

- `ragenius_execution_subsystem/src/core/execution/prisma-execution-store.ts`
  - Prisma-backed implementation of `ExecutionStore`.
- `ragenius_execution_subsystem/tests/execution/prisma-execution-store.test.ts`
  - Focused persistence tests for the Prisma-backed store.
- `ragenius_execution_subsystem/prisma/migrations/<timestamp>_execution_store_contract/migration.sql`
  - Migration generated from the updated schema.

---

## Task 1: Align Prisma Schema With the Runtime Execution Contract

**Files:**
- Modify: `ragenius_execution_subsystem/prisma/schema.prisma`
- Test: `npx prisma validate`

- [ ] **Step 1: Write the schema contract change**

Update `Execution` so it stores the runtime’s public execution id and the original request payload. Keep logs in `ExecutionLog`. Use the current public execution id as the primary key to avoid introducing a new ID translation layer.

```prisma
model Execution {
  id             String   @id
  requestType    String   @map("request_type")
  appId          String   @map("app_id")
  sessionId      String   @map("session_id")
  skillId        String   @map("skill_id")
  requestPayload Json     @map("request_payload")
  status         String
  resultType     String?  @map("result_type")
  result         Json?
  files          Json?
  errors         Json?
  logsSummary    String?  @map("logs_summary")
  createdAt      DateTime @default(now()) @map("created_at")
  updatedAt      DateTime @updatedAt @map("updated_at")

  logs ExecutionLog[]

  @@index([appId], map: "idx_executions_app_id")
  @@index([sessionId], map: "idx_executions_session_id")
  @@index([skillId], map: "idx_executions_skill_id")
  @@index([status], map: "idx_executions_status")
  @@index([createdAt], map: "idx_executions_created_at")
  @@map("executions")
}

model ExecutionLog {
  id          String   @id @default(uuid())
  executionId String   @map("execution_id")
  level       String
  eventType   String   @map("event_type")
  message     String
  summary     Json?
  createdAt   DateTime @default(now()) @map("created_at")

  execution Execution @relation(fields: [executionId], references: [id], onDelete: Cascade)

  @@index([executionId], map: "idx_execution_logs_execution_id")
  @@map("execution_logs")
}
```

- [ ] **Step 2: Remove schema pieces that the runtime does not yet persist**

Delete the unused persistence models from the current MVP schema for this phase:

```prisma
model WorkflowStep { ... }
model Skill { ... }
model Tool { ... }
model ToolCall { ... }
model PermissionPolicy { ... }
model McpProvider { ... }
```

This keeps the schema YAGNI-aligned with what the runtime actually persists today.

- [ ] **Step 3: Run Prisma validation**

Run: `npx prisma validate`
Expected: PASS with a valid PostgreSQL schema

- [ ] **Step 4: Commit**

```bash
git add ragenius_execution_subsystem/prisma/schema.prisma
git commit -m "refactor: align prisma schema with execution store contract"
```

---

## Task 2: Replace the Prisma Client Stub With a Real Client Seam

**Files:**
- Modify: `ragenius_execution_subsystem/src/db/prisma.ts`
- Test: `npm test -- execution-store.test.ts`

- [ ] **Step 1: Write the real Prisma client seam**

Replace the stub interface with a real Prisma client export:

```ts
import { PrismaClient } from "@prisma/client";

let prismaClient: PrismaClient | undefined;

export function createPrismaClient(): PrismaClient {
  if (!prismaClient) {
    prismaClient = new PrismaClient();
  }

  return prismaClient;
}
```

- [ ] **Step 2: Preserve test injection by not hardcoding this into store logic**

Do not change tests to depend directly on a live DB here. Keep this seam injectable from `app.ts` and store constructors.

- [ ] **Step 3: Run a focused verification**

Run: `npm test -- execution-store.test.ts`
Expected: PASS because in-memory store tests should remain unaffected

- [ ] **Step 4: Commit**

```bash
git add ragenius_execution_subsystem/src/db/prisma.ts
git commit -m "feat: add real prisma client seam"
```

---

## Task 3: Add PrismaExecutionStore

**Files:**
- Create: `ragenius_execution_subsystem/src/core/execution/prisma-execution-store.ts`
- Modify: `ragenius_execution_subsystem/src/core/execution/execution-store.ts`
- Test: `ragenius_execution_subsystem/tests/execution/prisma-execution-store.test.ts`

- [ ] **Step 1: Write the failing persistence test**

```ts
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { PrismaClient } from "@prisma/client";
import type { ExecutionRequest } from "../../src/api/schemas/execution-request.schema.js";
import { PrismaExecutionStore } from "../../src/core/execution/prisma-execution-store.js";

describe("prisma execution store", () => {
  it("persists and reloads execution records and requests", async () => {
    const prisma = {
      execution: {
        upsert: async ({ create }: { create: Record<string, unknown> }) => create,
        findUnique: async () => ({
          id: "execution_001",
          requestType: "execute_skill",
          appId: "app_001",
          sessionId: "sess_001",
          skillId: "video_director_skill",
          requestPayload: {
            request_type: "execute_skill",
            app_id: "app_001",
            session_id: "sess_001",
            skill_id: "video_director_skill",
            input: { prompt: "Explain RAG simply", duration: 30 }
          },
          status: "completed",
          resultType: "video",
          result: { title: "Video: Explain RAG simply" },
          files: [],
          errors: [],
          logsSummary: "Skill completed.",
          createdAt: new Date("2026-05-27T00:00:00.000Z"),
          updatedAt: new Date("2026-05-27T00:00:01.000Z")
        })
      },
      executionLog: {
        createMany: async () => ({ count: 1 }),
        findMany: async () => [
          {
            executionId: "execution_001",
            level: "info",
            eventType: "summary",
            message: "Skill completed.",
            createdAt: new Date("2026-05-27T00:00:01.000Z")
          }
        ]
      }
    } as unknown as PrismaClient;

    const store = new PrismaExecutionStore(prisma);
    const request: ExecutionRequest = {
      request_type: "execute_skill",
      app_id: "app_001",
      session_id: "sess_001",
      skill_id: "video_director_skill",
      input: { prompt: "Explain RAG simply", duration: 30 }
    };

    await store.save({
      executionId: "execution_001",
      request,
      result: {
        execution_id: "execution_001",
        status: "completed",
        result_type: "video",
        result: { title: "Video: Explain RAG simply" },
        files: [],
        errors: [],
        logs_summary: "Skill completed."
      }
    });

    const record = await store.get("execution_001");
    const storedRequest = await store.getRequest("execution_001");
    const logs = await store.getLogs("execution_001");

    assert.equal(record?.execution_id, "execution_001");
    assert.equal(storedRequest?.session_id, "sess_001");
    assert.equal(logs[0]?.message, "Skill completed.");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- prisma-execution-store.test.ts`
Expected: FAIL because `PrismaExecutionStore` does not exist yet

- [ ] **Step 3: Implement PrismaExecutionStore**

```ts
import type { PrismaClient } from "@prisma/client";

import type { ExecutionRequest } from "../../api/schemas/execution-request.schema.js";
import type { NormalizedExecutionResult } from "../../api/schemas/common-response.schema.js";
import type {
  ExecutionLogEntry,
  ExecutionRecord,
  ExecutionStore,
  SaveExecutionRecordInput
} from "./execution-store.js";

export class PrismaExecutionStore implements ExecutionStore {
  constructor(private readonly prisma: PrismaClient) {}

  async save(input: SaveExecutionRecordInput): Promise<void> {
    const timestamp = new Date();
    await this.prisma.execution.upsert({
      where: { id: input.executionId },
      create: {
        id: input.executionId,
        requestType: input.request.request_type,
        appId: input.request.app_id,
        sessionId: input.request.session_id,
        skillId: input.request.skill_id,
        requestPayload: input.request,
        status: input.result.status,
        resultType: input.result.result_type,
        result: input.result.result,
        files: input.result.files,
        errors: input.result.errors,
        logsSummary: input.result.logs_summary
      },
      update: {
        requestPayload: input.request,
        status: input.result.status,
        resultType: input.result.result_type,
        result: input.result.result,
        files: input.result.files,
        errors: input.result.errors,
        logsSummary: input.result.logs_summary,
        updatedAt: timestamp
      }
    });

    await this.prisma.executionLog.createMany({
      data: [
        {
          executionId: input.executionId,
          level: input.result.status === "failed" ? "error" : "info",
          eventType: "summary",
          message: input.result.logs_summary,
          summary: null
        }
      ]
    });
  }

  async get(executionId: string): Promise<ExecutionRecord | null> {
    const row = await this.prisma.execution.findUnique({
      where: { id: executionId }
    });
    if (!row) {
      return null;
    }
    return {
      execution_id: row.id,
      app_id: row.appId,
      created_at: row.createdAt.toISOString(),
      updated_at: row.updatedAt.toISOString(),
      request_type: row.requestType as ExecutionRequest["request_type"],
      session_id: row.sessionId,
      skill_id: row.skillId,
      status: row.status as NormalizedExecutionResult["status"],
      result_type: (row.resultType ?? "json") as NormalizedExecutionResult["result_type"],
      result: (row.result ?? {}) as Record<string, unknown>,
      files: Array.isArray(row.files) ? (row.files as Array<Record<string, unknown>>) : [],
      errors: Array.isArray(row.errors) ? (row.errors as NormalizedExecutionResult["errors"]) : [],
      logs_summary: row.logsSummary ?? ""
    };
  }

  async getLogs(executionId: string): Promise<ExecutionLogEntry[]> {
    const rows = await this.prisma.executionLog.findMany({
      where: { executionId },
      orderBy: { createdAt: "asc" }
    });
    return rows.map((row) => ({
      created_at: row.createdAt.toISOString(),
      execution_id: row.executionId,
      level: row.level as "info" | "error",
      message: row.message
    }));
  }

  async getRequest(executionId: string): Promise<ExecutionRequest | null> {
    const row = await this.prisma.execution.findUnique({
      where: { id: executionId }
    });
    return (row?.requestPayload as ExecutionRequest | null) ?? null;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- prisma-execution-store.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/src/core/execution/prisma-execution-store.ts ragenius_execution_subsystem/tests/execution/prisma-execution-store.test.ts
git commit -m "feat: add prisma-backed execution store"
```

---

## Task 4: Wire PrismaExecutionStore Into Runtime Startup

**Files:**
- Modify: `ragenius_execution_subsystem/src/app.ts`
- Modify: `ragenius_execution_subsystem/src/server.ts`
- Test: `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`

- [ ] **Step 1: Keep `InMemoryExecutionStore` only as the test/default injection seam**

Update `createAppServices()` so runtime construction prefers `PrismaExecutionStore(createPrismaClient())`, while tests can still override `executionStore` explicitly.

```ts
import { createPrismaClient } from "./db/prisma.js";
import { PrismaExecutionStore } from "./core/execution/prisma-execution-store.js";

const prisma = createPrismaClient();
const executionStore =
  overrides.executionStore ?? new PrismaExecutionStore(prisma);
```

- [ ] **Step 2: Add lifecycle connect/disconnect in server startup**

```ts
import { createPrismaClient } from "./db/prisma.js";

const prisma = createPrismaClient();
await prisma.$connect();

const app = buildApp({}, runtimeConfig);

app.addHook("onClose", async () => {
  await prisma.$disconnect();
});
```

- [ ] **Step 3: Verify existing route tests still pass**

Run: `npm test -- execute-skill.test.ts permission-block.test.ts`
Expected: PASS because tests should continue using injected stores or isolated seams

- [ ] **Step 4: Commit**

```bash
git add ragenius_execution_subsystem/src/app.ts ragenius_execution_subsystem/src/server.ts
git commit -m "feat: wire prisma execution store into runtime"
```

---

## Task 5: Generate and Review Prisma Migration

**Files:**
- Create: `ragenius_execution_subsystem/prisma/migrations/<timestamp>_execution_store_contract/migration.sql`
- Test: `npx prisma migrate dev --name execution_store_contract`

- [ ] **Step 1: Generate the migration**

Run:

```bash
npx prisma migrate dev --name execution_store_contract
```

Expected: migration folder created with SQL for `executions` and `execution_logs`

- [ ] **Step 2: Review generated SQL for the contract**

Confirm the SQL contains:

```sql
CREATE TABLE "executions" (
  "id" TEXT PRIMARY KEY,
  "request_type" TEXT NOT NULL,
  "app_id" TEXT NOT NULL,
  "session_id" TEXT NOT NULL,
  "skill_id" TEXT NOT NULL,
  "request_payload" JSONB NOT NULL,
  "status" TEXT NOT NULL,
  "result_type" TEXT,
  "result" JSONB,
  "files" JSONB,
  "errors" JSONB,
  "logs_summary" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMP(3) NOT NULL
);
```

- [ ] **Step 3: Re-validate Prisma**

Run: `npx prisma validate`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add ragenius_execution_subsystem/prisma/migrations ragenius_execution_subsystem/prisma/schema.prisma
git commit -m "feat: add execution store migration"
```

---

## Task 6: Add Runtime-Level Store Coverage

**Files:**
- Modify: `ragenius_execution_subsystem/tests/execution/execute-skill.test.ts`
- Modify: `ragenius_execution_subsystem/tests/execution/permission-block.test.ts`
- Test: `ragenius_execution_subsystem/tests/execution/*.test.ts`

- [ ] **Step 1: Add a route-level persistence assertion**

Add a store spy to prove POST execution persists through the store seam:

```ts
let savedExecutionId = "";
app = buildApp({
  executionStore: {
    async save(input) {
      savedExecutionId = input.executionId;
    },
    async get() {
      return null;
    },
    async getLogs() {
      return [];
    },
    async getRequest() {
      return null;
    }
  }
});
```

- [ ] **Step 2: Assert execution ids remain stable through confirm**

```ts
assert.equal(confirmResponse.json().execution_id, executionId);
```

- [ ] **Step 3: Run focused execution tests**

Run: `npm test -- execute-skill.test.ts permission-block.test.ts execution-store.test.ts prisma-execution-store.test.ts`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add ragenius_execution_subsystem/tests/execution/execute-skill.test.ts ragenius_execution_subsystem/tests/execution/permission-block.test.ts ragenius_execution_subsystem/tests/execution/execution-store.test.ts ragenius_execution_subsystem/tests/execution/prisma-execution-store.test.ts
git commit -m "test: cover prisma-backed execution persistence"
```

---

## Task 7: Update Runtime Documentation

**Files:**
- Modify: `ragenius_execution_subsystem/README.md`
- Test: docs review

- [ ] **Step 1: Replace outdated MVP persistence statements**

Update README sections like:

```md
## What This Runtime Now Does

- Persists execution records and logs through PostgreSQL/Prisma
- Supports execution lookup and log lookup across process restarts
- Supports persisted confirmation/resume flows
```

- [ ] **Step 2: Update API route documentation**

Replace:

```md
- `GET /v1/executions/:execution_id` returns `501`
- `GET /v1/executions/:execution_id/logs` returns `501`
```

With:

```md
- `GET /v1/executions/:execution_id`
- `GET /v1/executions/:execution_id/logs`
- `POST /v1/executions/:execution_id/confirm`
```

- [ ] **Step 3: Add database setup verification commands**

```md
### Persistence Setup

```bash
npx prisma validate
npx prisma migrate dev
```
```

- [ ] **Step 4: Review docs for consistency**

Run: `rg -n "501|does not persist live execution records yet|does not implement confirmation resume APIs yet" ragenius_execution_subsystem/README.md`
Expected: no stale statements remain

- [ ] **Step 5: Commit**

```bash
git add ragenius_execution_subsystem/README.md
git commit -m "docs: document prisma-backed execution persistence"
```

---

## Phase Exit Criteria

This database-backed execution store subproject is complete when all of these are true:

- Prisma schema matches the runtime execution record contract
- a real `PrismaExecutionStore` exists
- runtime startup uses Prisma-backed persistence by default
- `POST /v1/executions` persists execution records
- `GET /v1/executions/:execution_id` reads persisted records
- `GET /v1/executions/:execution_id/logs` reads persisted logs
- `POST /v1/executions/:execution_id/confirm` resumes from persisted request state
- docs no longer describe execution persistence as missing

## Self-Review

Spec coverage:
- Covers schema alignment, real Prisma store, runtime wiring, migration generation, route-level verification, and docs.
- Does not broaden into workers, analytics, or advanced workflow persistence; that is intentional.

Placeholder scan:
- No `TODO`/`TBD` placeholders remain.
- Commands, files, and code targets are explicit.

Type consistency:
- Uses the existing `ExecutionStore` / `ExecutionStatusService` / `ExecutionEngine` seams.
- Keeps public `execution_id` as the stable runtime identifier rather than introducing a second ID layer.
