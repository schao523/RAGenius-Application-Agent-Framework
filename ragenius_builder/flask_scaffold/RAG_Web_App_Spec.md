# RAG Web Application Optimized Prompt v3.5 Implementation Plan

## Overview
Designing a RAG web application following v3.5 rules with Tailwind-first, accessible HTML, PostgreSQL schema, and non-executable backend/API specifications. The `rag_subsystem` is treated as an opaque service invoked only through `process_files` and `retrieve_data`, always scoped to `app_id`.

## Assumptions
- Application names are unique and act as immutable external lookup keys; rename is internal-only.
- Minimal viable UI written in semantic HTML with Tailwind utility classes; icons use text fallbacks where applicable.
- Debug panel rendered only when the authenticated role is `internal`; auth mechanism itself is out of scope.
- Retrieval timeout enforced at request level (3s) with lazy-loading chunked result rendering on the client.

## Frontend Pages (semantic HTML + Tailwind)
Each page includes a skip link (`#main`), focus-visible styles, and form controls with labels, helper text, and `aria-describedby`. State messaging uses `aria-live="polite"` for save/progress updates.

### `/apps` — Application List
```html
<!DOCTYPE html>
<html lang="en" class="h-full">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Apps</title>
  <link href="/tailwind.css" rel="stylesheet" />
</head>
<body class="min-h-full bg-slate-50 text-slate-900">
  <a href="#main" class="sr-only focus:not-sr-only focus:ring-2 focus:ring-blue-500">Skip to content</a>
  <header class="border-b bg-white shadow-sm">
    <div class="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
      <div>
        <p class="text-sm text-slate-500">Manage RAG Apps</p>
        <h1 class="text-2xl font-semibold">Applications</h1>
      </div>
      <a href="/apps/new" class="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">New App</a>
    </div>
  </header>
  <main id="main" class="mx-auto max-w-6xl px-4 py-6 space-y-6">
    <section aria-label="Application filters" class="flex flex-col gap-2 sm:flex-row sm:items-center">
      <label class="flex items-center gap-2 text-sm text-slate-700">
        <span class="min-w-[80px]">Search</span>
        <input type="search" class="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200" placeholder="Search apps" aria-label="Search applications" />
      </label>
    </section>
    <section aria-label="Application list" class="grid gap-4">
      <!-- Application card template -->
      <article class="rounded-lg border border-slate-200 bg-white p-4 shadow-sm focus-within:ring-2 focus-within:ring-blue-400">
        <div class="flex items-start justify-between">
          <div>
            <h2 class="text-lg font-semibold"><a href="/apps/{app_id}" class="focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">App Name</a></h2>
            <p class="text-sm text-slate-600">Description text</p>
            <p class="mt-1 text-xs text-slate-500">Updated 2024-01-01</p>
          </div>
          <div class="flex gap-2">
            <span class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700">4 docs</span>
            <a href="/apps/{app_id}/search" class="text-sm font-semibold text-blue-600 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">Search</a>
          </div>
        </div>
      </article>
    </section>
  </main>
</body>
</html>
```

### `/apps/new` — New Application Form
```html
<!DOCTYPE html>
<html lang="en" class="h-full">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>New Application</title>
  <link href="/tailwind.css" rel="stylesheet" />
</head>
<body class="min-h-full bg-slate-50 text-slate-900">
  <a href="#main" class="sr-only focus:not-sr-only focus:ring-2 focus:ring-blue-500">Skip to content</a>
  <main id="main" class="mx-auto max-w-4xl px-4 py-8 space-y-6">
    <header class="flex items-center justify-between">
      <div>
        <p class="text-sm text-slate-500">Create a new RAG app</p>
        <h1 class="text-2xl font-semibold">New Application</h1>
      </div>
    </header>
    <form class="space-y-6" aria-describedby="app-form-help">
      <p id="app-form-help" class="text-sm text-slate-600">Application name is unique and slug becomes immutable.</p>
      <div class="space-y-2">
        <label for="name" class="block text-sm font-medium text-slate-700">Name</label>
        <input id="name" name="name" required class="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200" aria-describedby="name-error" />
        <p id="name-error" class="text-sm text-rose-600 hidden">Name must be unique.</p>
      </div>
      <div class="space-y-2">
        <label for="description" class="block text-sm font-medium text-slate-700">Description</label>
        <textarea id="description" name="description" rows="3" class="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200"></textarea>
      </div>
      <div class="grid gap-4 sm:grid-cols-2">
        <div class="space-y-2">
          <label for="starter1" class="block text-sm font-medium text-slate-700">Starter question 1</label>
          <input id="starter1" name="starter_questions[]" class="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200" />
        </div>
        <div class="space-y-2">
          <label for="starter2" class="block text-sm font-medium text-slate-700">Starter question 2</label>
          <input id="starter2" name="starter_questions[]" class="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200" />
        </div>
        <div class="space-y-2">
          <label for="starter3" class="block text-sm font-medium text-slate-700">Starter question 3</label>
          <input id="starter3" name="starter_questions[]" class="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200" />
        </div>
        <div class="space-y-2">
          <label for="starter4" class="block text-sm font-medium text-slate-700">Starter question 4</label>
          <input id="starter4" name="starter_questions[]" class="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200" />
        </div>
      </div>
      <div class="flex items-center justify-end gap-3">
        <a href="/apps" class="text-sm text-slate-700 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">Cancel</a>
        <button type="submit" class="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">Create</button>
      </div>
    </form>
  </main>
</body>
</html>
```

### `/apps/:app_id` — Application Overview
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>App Overview</title>
  <link rel="stylesheet" href="/tailwind.css" />
</head>
<body class="bg-slate-50 text-slate-900">
  <a href="#main" class="sr-only focus:not-sr-only focus:ring-2 focus:ring-blue-500">Skip to content</a>
  <main id="main" class="mx-auto max-w-6xl px-4 py-8 space-y-6">
    <header class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <p class="text-sm text-slate-500">App slug is immutable</p>
        <h1 class="text-3xl font-semibold">App Name</h1>
        <p class="text-sm text-slate-600">Description</p>
      </div>
      <div class="flex gap-3">
        <a href="/apps/{app_id}/config?tab=instructions" class="rounded border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">Instructions</a>
        <a href="/apps/{app_id}/config?tab=settings" class="rounded border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">Settings</a>
        <a href="/apps/{app_id}/upload" class="rounded bg-blue-600 px-3 py-2 text-sm font-semibold text-white shadow focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">Upload</a>
        <a href="/apps/{app_id}/search" class="rounded bg-slate-900 px-3 py-2 text-sm font-semibold text-white shadow focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900">Search</a>
      </div>
    </header>
    <section class="grid gap-4 sm:grid-cols-3">
      <div class="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <p class="text-sm text-slate-500">Documents</p>
        <p class="text-2xl font-semibold">12</p>
      </div>
      <div class="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <p class="text-sm text-slate-500">Last updated</p>
        <p class="text-2xl font-semibold">2024-01-01</p>
      </div>
      <div class="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <p class="text-sm text-slate-500">Status</p>
        <p class="text-2xl font-semibold text-emerald-600">Healthy</p>
      </div>
    </section>
    <section aria-label="Starter questions" class="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h2 class="text-lg font-semibold">Starter questions</h2>
      <ul class="mt-3 space-y-2 text-sm text-slate-700">
        <li>Question 1</li>
        <li>Question 2</li>
      </ul>
    </section>
  </main>
</body>
</html>
```

### `/apps/:app_id/config?tab=instructions` — Markdown Instructions Editor
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Edit Instructions</title>
  <link rel="stylesheet" href="/tailwind.css" />
</head>
<body class="bg-slate-50 text-slate-900">
  <a href="#main" class="sr-only focus:not-sr-only focus:ring-2 focus:ring-blue-500">Skip to content</a>
  <main id="main" class="mx-auto max-w-6xl px-4 py-8 space-y-4">
    <header class="flex items-center justify-between">
      <div>
        <p class="text-sm text-slate-500">Instructions are stored securely and never sent to the rag subsystem.</p>
        <h1 class="text-2xl font-semibold">Instructions</h1>
      </div>
      <div class="flex gap-2 text-sm text-slate-700" aria-live="polite">Saved just now</div>
    </header>
    <div class="grid gap-4 lg:grid-cols-2">
      <label class="space-y-2" for="markdown-editor">
        <span class="block text-sm font-medium text-slate-700">Markdown</span>
        <textarea id="markdown-editor" class="h-96 w-full rounded border border-slate-300 px-3 py-2 text-sm font-mono focus:border-blue-500 focus:ring-2 focus:ring-blue-200" aria-describedby="md-help md-error"></textarea>
        <p id="md-help" class="text-sm text-slate-600">Use Markdown; changes auto-saved on blur.</p>
        <p id="md-error" class="hidden text-sm text-rose-600">Error saving instructions.</p>
      </label>
      <section aria-label="Preview" class="h-96 overflow-auto rounded border border-slate-200 bg-white p-4 shadow-sm prose prose-slate">
        <h2 class="text-lg font-semibold">Live Preview</h2>
        <p>Rendered markdown...</p>
      </section>
    </div>
    <div class="flex justify-end gap-3">
      <button type="button" class="rounded border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">Cancel</button>
      <button type="submit" class="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">Save</button>
    </div>
  </main>
</body>
</html>
```

### `/apps/:app_id/config?tab=settings` — JSON Schema Settings Form
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Settings</title>
  <link rel="stylesheet" href="/tailwind.css" />
</head>
<body class="bg-slate-50 text-slate-900">
  <a href="#main" class="sr-only focus:not-sr-only focus:ring-2 focus:ring-blue-500">Skip to content</a>
  <main id="main" class="mx-auto max-w-4xl px-4 py-8 space-y-6">
    <header class="flex items-center justify-between">
      <div>
        <p class="text-sm text-slate-500">Inline + server validation against JSON Schema</p>
        <h1 class="text-2xl font-semibold">App Settings</h1>
      </div>
      <div class="text-sm text-slate-700" aria-live="polite">All changes saved</div>
    </header>
    <form class="space-y-5" aria-describedby="settings-help">
      <p id="settings-help" class="text-sm text-slate-600">Validation errors appear inline.</p>
      <div class="space-y-2">
        <label for="embedding_model" class="block text-sm font-medium text-slate-700">Embedding model</label>
        <select id="embedding_model" name="embedding_model" class="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200" aria-describedby="embedding-error">
          <option>text-embedding-3-small</option>
          <option>text-embedding-3-large</option>
        </select>
        <p id="embedding-error" class="hidden text-sm text-rose-600">Invalid model selection.</p>
      </div>
      <div class="space-y-2">
        <label for="chunk_size" class="block text-sm font-medium text-slate-700">Chunk size</label>
        <input id="chunk_size" type="number" name="chunk_size" min="100" max="4000" class="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200" aria-describedby="chunk-error" />
        <p id="chunk-error" class="hidden text-sm text-rose-600">Chunk size must be between 100 and 4000.</p>
      </div>
      <div class="space-y-2">
        <label for="language" class="block text-sm font-medium text-slate-700">Language</label>
        <select id="language" name="language" class="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200" aria-describedby="language-error">
          <option>en</option>
          <option>es</option>
        </select>
        <p id="language-error" class="hidden text-sm text-rose-600">Language not supported.</p>
      </div>
      <div class="flex justify-end gap-3">
        <button type="button" class="rounded border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">Reset</button>
        <button type="submit" class="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">Save</button>
      </div>
    </form>
  </main>
</body>
</html>
```

### `/apps/:app_id/upload` — Upload Queue
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Upload Documents</title>
  <link rel="stylesheet" href="/tailwind.css" />
</head>
<body class="bg-slate-50 text-slate-900">
  <a href="#main" class="sr-only focus:not-sr-only focus:ring-2 focus:ring-blue-500">Skip to content</a>
  <main id="main" class="mx-auto max-w-5xl px-4 py-8 space-y-6">
    <header class="flex items-center justify-between">
      <div>
        <p class="text-sm text-slate-500">Streamed progress with retry/cancel</p>
        <h1 class="text-2xl font-semibold">Upload</h1>
      </div>
    </header>
    <section class="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center shadow-sm">
      <p class="text-sm text-slate-600">Drag and drop files or</p>
      <label class="mt-2 inline-flex cursor-pointer items-center rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">
        <span>Choose files</span>
        <input type="file" class="sr-only" multiple />
      </label>
    </section>
    <section aria-label="Upload queue" class="space-y-3">
      <article class="rounded border border-slate-200 bg-white p-4 shadow-sm">
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="text-sm font-semibold text-slate-900">document.pdf</p>
            <p class="text-xs text-slate-600">1.2 MB • application/pdf</p>
            <p class="mt-1 text-xs text-amber-600">Uploading…</p>
          </div>
          <div class="flex items-center gap-2">
            <span class="rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">Uploading</span>
            <button class="text-sm text-blue-600 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">Cancel</button>
          </div>
        </div>
        <div class="mt-3 h-2 rounded bg-slate-200" role="progressbar" aria-valuenow="32" aria-valuemin="0" aria-valuemax="100">
          <div class="h-2 w-[32%] rounded bg-blue-600"></div>
        </div>
      </article>
      <article class="rounded border border-slate-200 bg-white p-4 shadow-sm">
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="text-sm font-semibold text-slate-900">guide.docx</p>
            <p class="text-xs text-slate-600">800 KB • application/vnd.openxmlformats-officedocument.wordprocessingml.document</p>
            <p class="mt-1 text-xs text-emerald-600">Ready</p>
          </div>
          <div class="flex items-center gap-2">
            <span class="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">Ready</span>
            <button class="text-sm text-blue-600 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">Re-ingest</button>
          </div>
        </div>
      </article>
    </section>
  </main>
</body>
</html>
```

### `/apps/:app_id/docs` — Documents List
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Documents</title>
  <link rel="stylesheet" href="/tailwind.css" />
</head>
<body class="bg-slate-50 text-slate-900">
  <a href="#main" class="sr-only focus:not-sr-only focus:ring-2 focus:ring-blue-500">Skip to content</a>
  <main id="main" class="mx-auto max-w-6xl px-4 py-8 space-y-4">
    <header class="flex items-center justify-between">
      <div>
        <p class="text-sm text-slate-500">Browse documents</p>
        <h1 class="text-2xl font-semibold">Documents</h1>
      </div>
      <a href="/apps/{app_id}/upload" class="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">Upload</a>
    </header>
    <div class="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <table class="min-w-full divide-y divide-slate-200 text-left text-sm">
        <thead class="bg-slate-50 text-slate-700">
          <tr>
            <th class="px-4 py-3 font-semibold">Filename</th>
            <th class="px-4 py-3 font-semibold">Status</th>
            <th class="px-4 py-3 font-semibold">Tags</th>
            <th class="px-4 py-3 font-semibold">Actions</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-slate-100">
          <tr>
            <td class="px-4 py-3">handbook.pdf</td>
            <td class="px-4 py-3"><span class="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">Ready</span></td>
            <td class="px-4 py-3">en, policy</td>
            <td class="px-4 py-3">
              <div class="flex gap-3">
                <a href="/apps/{app_id}/docs/{doc_id}" class="text-blue-600 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">View</a>
                <button class="text-rose-600 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">Delete</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </main>
</body>
</html>
```

### `/apps/:app_id/docs/:doc_id` — Document Detail
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Document Detail</title>
  <link rel="stylesheet" href="/tailwind.css" />
</head>
<body class="bg-slate-50 text-slate-900">
  <a href="#main" class="sr-only focus:not-sr-only focus:ring-2 focus:ring-blue-500">Skip to content</a>
  <main id="main" class="mx-auto max-w-4xl px-4 py-8 space-y-4">
    <header class="flex items-center justify-between">
      <div>
        <p class="text-sm text-slate-500">Document metadata</p>
        <h1 class="text-2xl font-semibold">handbook.pdf</h1>
        <p class="text-sm text-slate-600">application/pdf • 1.2 MB • en</p>
      </div>
      <div class="flex gap-2">
        <button class="rounded border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">Re-ingest</button>
        <button class="rounded border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-semibold text-rose-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose-600">Delete</button>
      </div>
    </header>
    <section class="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h2 class="text-lg font-semibold">Status</h2>
      <p class="mt-2 text-sm text-emerald-700">Ready</p>
      <p class="text-xs text-slate-600">No errors.</p>
    </section>
  </main>
</body>
</html>
```

### `/apps/:app_id/search` — Search Page
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Search</title>
  <link rel="stylesheet" href="/tailwind.css" />
</head>
<body class="bg-slate-50 text-slate-900">
  <a href="#main" class="sr-only focus:not-sr-only focus:ring-2 focus:ring-blue-500">Skip to content</a>
  <main id="main" class="mx-auto max-w-5xl px-4 py-8 space-y-6">
    <header class="flex flex-col gap-2">
      <p class="text-sm text-slate-500">Lazy-loaded results, 3s retrieval timeout</p>
      <h1 class="text-2xl font-semibold">Search</h1>
    </header>
    <form class="space-y-3" aria-describedby="search-help">
      <label class="block space-y-2">
        <span class="text-sm font-medium text-slate-700">Query</span>
        <textarea class="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-200" rows="3" aria-describedby="search-help search-error"></textarea>
      </label>
      <p id="search-help" class="text-sm text-slate-600">Results stream as they arrive.</p>
      <p id="search-error" class="hidden text-sm text-rose-600">Error retrieving results.</p>
      <div class="flex justify-end">
        <button type="submit" class="rounded bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">Search</button>
      </div>
    </form>
    <section aria-label="Search results" class="space-y-4">
      <div class="rounded border border-slate-200 bg-white p-4 shadow-sm">
        <p class="text-sm font-semibold text-slate-900">Empty state</p>
        <p class="text-sm text-slate-600">Try asking a starter question.</p>
      </div>
      <div class="rounded border border-amber-100 bg-amber-50 p-4 text-amber-800 shadow-sm hidden" role="alert">Rate limit exceeded (429). Please retry later.</div>
      <div class="rounded border border-rose-100 bg-rose-50 p-4 text-rose-800 shadow-sm hidden" role="alert">Service unavailable (503). Try again soon.</div>
      <article class="rounded border border-slate-200 bg-white p-4 shadow-sm">
        <header class="flex items-center justify-between">
          <h2 class="text-lg font-semibold">Result title</h2>
          <span class="text-xs text-slate-500">Score 0.87</span>
        </header>
        <p class="mt-2 text-sm text-slate-700">Snippet with highlighted context…</p>
        <div class="mt-3 space-x-2 text-xs text-blue-700">
          <a href="/apps/{app_id}/docs/{doc_id}" class="underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">View source</a>
          <span>•</span>
          <span class="text-slate-600">Page 3</span>
        </div>
      </article>
      <section class="rounded border border-slate-200 bg-slate-900 p-4 text-sm text-white shadow-sm hidden" aria-label="Debug panel">
        <h3 class="text-base font-semibold">Debug (internal only)</h3>
        <pre class="mt-2 whitespace-pre-wrap">{ "request": {}, "latency_ms": 1200 }</pre>
      </section>
    </section>
  </main>
</body>
</html>
```

## Reusable UI Components
- **Application Card**: title, description, badge count, search link, focus ring on child anchors.
- **Form Field**: label + input/select/textarea with helper and error text linked via `aria-describedby`.
- **Status Chip**: color variants for uploading (blue), ingesting (amber), ready (emerald), error (rose), canceled (slate).
- **Markdown Editor**: split view textarea + preview, `aria-live` save indicator.
- **JSON Schema Form Controls**: inline validation, server errors mapped to 422 format.
- **Upload Queue Item**: filename, mime, size, progress bar, retry/cancel buttons, status chip.
- **Search Result Card**: title, snippet, score, citation link; error/empty/429/503 states.

## Backend / API Structure (non-executable)
- **Database (PostgreSQL)**
  - `application` (`id` UUID PK, `name` text UNIQUE, `name_lower` text GENERATED ALWAYS AS lower(name) STORED, `slug` text UNIQUE, `description` text, `starter_questions` text[] CHECK (array_length(starter_questions,1)=4), `instructions_uri` text, `instructions_version` integer DEFAULT 1, `instructions_updated_at` timestamptz DEFAULT now(), `config_settings` jsonb, `config_schema` jsonb, `created_at` timestamptz DEFAULT now(), `updated_at` timestamptz DEFAULT now())
  - `document` (`id` UUID PK, `app_id` UUID REFERENCES application(id) ON DELETE CASCADE, `filename` text NOT NULL, `mime_type` text, `size_bytes` bigint, `language` text, `tags` text[], `status` text CHECK (status IN ('pending','uploading','ingesting','ready','error','canceled')) DEFAULT 'pending', `error_message` text, `created_at` timestamptz DEFAULT now(), `updated_at` timestamptz DEFAULT now())
  - `ingestion_job` (`id` UUID PK, `app_id` UUID REFERENCES application(id) ON DELETE CASCADE, `document_id` UUID REFERENCES document(id) ON DELETE CASCADE, `status` text CHECK (status IN ('queued','running','success','failed')) DEFAULT 'queued', `attempt` integer DEFAULT 0, `error_message` text, `started_at` timestamptz, `finished_at` timestamptz)

- **Validation Error Shape**
  - `422 { "errors": [{ "path": string, "msg": string, "code": string }] }`

- **Auth Roles**
  - `external`: read-only (GET endpoints only, plus `/search` per app); cannot modify names/slugs/settings/instructions.
  - `internal`: full CRUD, upload, ingest, settings, instructions; debug panel visibility.

- **Endpoints** (all scoped by `app_id` where applicable; rate limit `/by-name` 60/min/IP)
  - `GET /api/apps` → list applications; query params for pagination/search.
  - `GET /api/apps/by-name/{name}` → look up by unique name (external lookup key).
  - `POST /api/apps` (internal) → create; body: name, description, starter_questions[4], config_settings?, config_schema?; slug auto-generated lower-kebab-case immutable.
  - `PATCH /api/apps/{app_id}` (internal) → update description/starter_questions only (name/slug immutable externally).
  - `GET /api/apps/{app_id}/instructions` → returns signed URL (`instructions/{app_id}/instructions.md`, TTL 15m) and version metadata.
  - `PATCH /api/apps/{app_id}/instructions` (internal) → writes file then updates DB version/timestamp.
  - `GET /api/apps/{app_id}/settings` → returns `config_settings` + `config_schema`.
  - `PATCH /api/apps/{app_id}/settings` (internal) → server-validated against JSON Schema; responds with updated settings.
  - `POST /api/apps/{app_id}/uploads` (internal) → initiate upload; returns upload id + signed URL.
  - `GET /api/apps/{app_id}/docs` → list documents with statuses.
  - `GET /api/apps/{app_id}/docs/{doc_id}` → document detail.
  - `DELETE /api/apps/{app_id}/docs/{doc_id}` (internal) → delete + cancel ingestion if pending.
  - `POST /api/apps/{app_id}/docs/{doc_id}/reingest` (internal) → enqueue ingestion; retries max 2 per spec.
  - `POST /api/apps/{app_id}/search` → triggers retrieval with 3s timeout; lazy result streaming; uses `retrieve_data(query_text, top_k, filters, config, store, embed_client, router)`.

- **Request/Response Objects (representative)**
  - Application DTO: `{ id, name, slug, description, starter_questions: string[4], instructions_uri, instructions_version, instructions_updated_at, config_settings, config_schema }`
  - Document DTO: `{ id, app_id, filename, mime_type, size_bytes, language, tags, status, error_message, created_at, updated_at }`
  - Upload Init Request: `{ filename, mime_type, size_bytes, language?, tags? }` → Response `{ upload_id, document_id, signed_url, expires_at }`
  - Re-ingest Request: `{}` → Response `{ job_id, status }`
  - Search Request: `{ query_text: string, top_k?: number, filters?: object }` → Response `{ results: [{ id, doc_id, score, snippet, source_uri, page }], debug?: object }`

- **Service Bindings to rag_subsystem**
  - Ingestion: `process_files(documents, config, store, embed_client, router)` invoked via `svc.rag.process_files` binding; respects retry max 2.
  - Retrieval: `retrieve_data(query_text, top_k, filters, config, store, embed_client, router)` invoked via `svc.rag.retrieve_data` with 3s timeout.

## Workflow Summary (rag_application_flows_v3_5)
1. **App lookup by name**: query applications by lowercase name; if missing → `app_lookup_failed` end.
2. **Update instructions**: write file at `instructions/{app_id}/instructions.md` (never passed to rag subsystem); on success update DB, else `instructions_write_failed`.
3. **Update instructions DB**: persist metadata; on failure end `db_write_failed`; on success `success_end`.
4. **Ingest documents**: call `svc.rag.process_files` with retry (max 2, backoff 300ms); success → `ingestion_success`, failure → `ingestion_failed`.
5. **Retrieve query**: call `svc.rag.retrieve_data`; success → `success_end`, failure → `retrieval_failed`.
6. **Policies**: rate limit 60/min, minimize logged fields, scope every operation by `app_id`, external integrators are read-only.

## Workflow Execution Map (verbatim)
```yaml
workflow_id: rag_app_flows_v3_5
version: 3.5
description: RAG application lifecycle flows

roles:
  - name: internal
  - name: external

events:
  - name: app.created
  - name: doc.ingested

guards:
  - name: isInternal
  - name: isExternal

states:
  - id: start
    type: start
    on:
      next: app_lookup_by_name

  - id: app_lookup_by_name
    type: task
    action:
      type: db_query
      query: "select * from applications where name_lower = :name"
    on:
      not_found: app_lookup_failed
      success: update_instructions

  - id: update_instructions
    type: task
    action:
      type: file_write
      path_ref: "instructions/{app_id}/instructions.md"
    on:
      success: update_instructions_db
      failure: instructions_write_failed

  - id: update_instructions_db
    type: task
    action:
      type: db_update
    on:
      success: success_end
      failure: db_write_failed

  - id: ingest_documents
    type: task
    retry: {max: 2, backoff_ms: 300}
    action:
      type: service_call
      binding_ref: "svc.rag.process_files"
    on:
      success: ingestion_success
      failure: ingestion_failed

  - id: retrieve_query
    type: task
    action:
      type: service_call
      binding_ref: "svc.rag.retrieve_data"
    on:
      success: success_end
      failure: retrieval_failed

  - id: ingestion_success
    type: end

  - id: success_end
    type: end

  - id: retrieval_failed
    type: end

  - id: instructions_write_failed
    type: end

  - id: db_write_failed
    type: end

bindings:
  - id: "svc.rag.process_files"
    kind: mcp
    tool: "rag.process_files"

  - id: "svc.rag.retrieve_data"
    kind: mcp
    tool: "rag.retrieve_data"

schemas:
  Document:
    required: ["id","app_id","filename"]
  Application:
    required: ["id","name","slug"]

policies:
  rate_limit: {unit: minute, max: 60}
  privacy: {minimize_fields: true}
```

## Final Checklist
- 已覆蓋頁面: /apps, /apps/new, /apps/:app_id, /apps/:app_id/config?tab=instructions, /apps/:app_id/config?tab=settings, /apps/:app_id/upload, /apps/:app_id/docs, /apps/:app_id/docs/:doc_id, /apps/:app_id/search.
- 已覆蓋 API: all specified endpoints with roles, validation shape, rate limits, signed URL TTL.
- 已覆蓋 workflow: rag_application_flows_v3_5 summary plus verbatim execution map.
- TODO & assumptions: auth plumbing, actual RAG implementation, storage drivers, and streaming mechanics are placeholders; external integrators are read-only; slug immutability enforced server-side.
