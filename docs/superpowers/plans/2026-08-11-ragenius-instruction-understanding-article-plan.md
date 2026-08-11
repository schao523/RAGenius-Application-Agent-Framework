# RAGenius Instruction Understanding Article Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a comprehensive, technically accurate, visually verified Word article under `docs/` explaining the RAGenius application instruction-understanding model to AI researchers and developers.

**Architecture:** Build an evidence matrix from current repository documents and production code, use it to draft a hybrid research-and-developer article, generate the DOCX with explicit publication design tokens, and verify both its structure and every rendered page. The article will treat LLM semantic compilation as the central meaning-making stage while explaining how deterministic parsing, grounding, validation, persistence, and runtime planning constrain and operationalize that semantic interpretation.

**Tech Stack:** Repository Markdown and Python sources; bundled workspace Python runtime; `python-docx`; document-skill OOXML helpers; LibreOffice-backed `render_docx.py`; PNG visual inspection.

## Global Constraints

- Deliverable: `docs/RAGenius_Instruction_Understanding_Model.docx`.
- Audience: AI researchers, RAG architects, application developers, and technical product designers.
- Target length: approximately 12–18 rendered US Letter pages.
- Treat `ragenius_builder` as the administrative source of truth and `ragenius_app_skeleton` as the active integrated runtime.
- Treat `ragenius_app` as legacy/reference material only.
- Keep retrieval and ingestion responsibilities in `rag_subsystem`.
- Preserve application-scoped `app_id` semantics and file-backed instructions at `instructions/{app_id}/instructions.md`.
- Present LLM semantic compilation as a central stage that produces `app_semantic_model` from grounded deterministic candidates.
- Explain that canonicalization, deterministic grounding, schema/relationship validation, and publication rules constrain the LLM output.
- Distinguish implemented behavior, compatibility behavior, architectural interpretation, and roadmap material.
- Label the worked example as illustrative rather than a production snapshot.
- Use exact code-contract names for modes and fields.
- Render and inspect every page before delivery.

---

## File Structure

- Create: `docs/RAGenius_Instruction_Understanding_Model.docx` — final downloadable Word article.
- Use as approved design authority: `docs/superpowers/specs/2026-08-11-ragenius-instruction-understanding-article-design.md`.
- Create during production, then remove after successful generation: `.tmp/ragenius_instruction_article/build_article.py` — deterministic DOCX builder.
- Create during production, then remove after successful QA: `.tmp/ragenius_instruction_article/rendered/` — page PNGs and optional PDF used only for visual inspection.
- Create during production, then remove after successful QA: `.tmp/ragenius_instruction_article/evidence.md` — repository evidence matrix and claim ledger.

### Task 1: Build the Evidence Matrix

**Files:**
- Create temporarily: `.tmp/ragenius_instruction_article/evidence.md`
- Read: `AGENTS.md`
- Read: `README.md`
- Read: `docs/2026-05-24-ragenius-app-ragenius-app-skeleton-handover.md`
- Read: `docs/2026-05-13-instruction-understanding-remaining-phases.md`
- Read: `docs/2026-05-14-phase-5-real-llm-verification-checklist.md`
- Read: `docs/ragenius_builder_skill_management_contract.md`
- Read: `ragenius_builder/docs/builder_gui_instruction_model_contract.md`
- Read: `ragenius_builder/docs/builder_gui_instruction_model_design.md`
- Read: `ragenius_app_skeleton/backend/app/instruction_understanding_service.py`
- Read: `ragenius_app_skeleton/backend/app/chat_repos.py`
- Read: `ragenius_app_skeleton/backend/app/main.py`
- Read: `ragenius_app_skeleton/workflows/nodes/load_template_registry.py`
- Read: `ragenius_app_skeleton/workflows/nodes/planner.py`
- Read: `ragenius_app_skeleton/workflows/graph_state.py`

**Interfaces:**
- Consumes: approved article specification and repository source files.
- Produces: a claim ledger with columns `Claim`, `Status`, `Evidence path`, `Evidence location`, and `Article section`.

- [ ] **Step 1: Create a section-by-section evidence checklist**

Record evidence for component boundaries, instruction storage, deterministic parsing, semantic compilation, semantic validation, hybrid projection, planner consumption, persistence, staleness, review/revision, isolation, and roadmap status.

- [ ] **Step 2: Trace the semantic compilation call contract**

Confirm and record that `compile_instruction_understanding()` builds deterministic context, invokes the optional semantic compiler, normalizes `app_semantic_model`, validates it, builds `hybrid_instruction_runtime_model`, and projects compatibility fields.

- [ ] **Step 3: Trace publication and failure semantics**

Confirm and record how valid compilation becomes active, how invalid semantic attempts remain diagnostic-only, and how the active record is preserved.

- [ ] **Step 4: Trace runtime consumption**

Confirm and record how compiled understanding enters the template registry and graph state, and how the planner consumes hybrid routing, procedures, modules, clarification gates, and runtime compatibility fields.

- [ ] **Step 5: Audit current versus planned behavior**

Mark each claim as `implemented`, `compatibility`, `design/contract`, `roadmap`, or `architectural interpretation`. No roadmap-only claim may be written in the present tense as deployed behavior.

- [ ] **Step 6: Verify the evidence matrix**

Search for unsupported claims, missing production sources, and contradictions between documents and code. Resolve conflicts in favor of current production code and repository-level `AGENTS.md` boundaries.

## Task 2: Draft the Article and Build the Word Document

**Files:**
- Create temporarily: `.tmp/ragenius_instruction_article/build_article.py`
- Create: `docs/RAGenius_Instruction_Understanding_Model.docx`
- Consume: `.tmp/ragenius_instruction_article/evidence.md`
- Consume: `docs/superpowers/specs/2026-08-11-ragenius-instruction-understanding-article-design.md`

**Interfaces:**
- Consumes: verified evidence matrix and approved editorial structure.
- Produces: a complete DOCX with semantic headings, real Word lists, explicit table geometry, diagrams, source notes, headers, footers, and page numbers.

- [ ] **Step 1: Resolve the document design preset**

Read the document skill's `references/design_presets.md`, `references/header_templates.md`, and `tasks/create_edit.md`. Select the closest professional technical-report preset and record exact page, margin, typography, spacing, color, table, callout, header, and footer tokens in the builder.

- [ ] **Step 2: Draft the complete manuscript**

Write the approved front matter and thirteen article sections. Give special prominence to the hybrid semantic compilation thesis: deterministic parsing bounds the evidence; the LLM interprets meaning and produces `app_semantic_model`; deterministic grounding and validation govern what may be published and executed.

- [ ] **Step 3: Add the end-to-end architecture visual**

Create a compact diagram showing:

`Builder Markdown + registered documents -> deterministic candidate graph -> LLM semantic compiler -> grounded app_semantic_model -> validation -> hybrid runtime model -> compatibility projection -> active snapshot -> planner/runtime`.

The diagram must also show the invalid-attempt branch preserving the last-known-good active model.

- [ ] **Step 4: Add the layered-model explanation**

Use a concise comparison table or layered figure for authored source, deterministic structural contract, LLM semantic model, hybrid runtime model, and compatibility projection. Each layer must state its purpose, producer, and primary consumers.

- [ ] **Step 5: Add the illustrative worked example**

Use a fictional research assistant with one default literature-review workflow, a source-evaluation support module, explicit clarification criteria, and registered paper resources. Show how a synthesis query and a source-quality query activate different runtime structures.

- [ ] **Step 6: Add practical guidance and diagnostics**

Include authoring guidance, failure modes, operator diagnostics, and a role-based checklist for instruction authors, reviewers, runtime developers, and operators.

- [ ] **Step 7: Add repository sources**

List each principal repository-relative path and state what fact or contract it supports. Do not use web citations or imply external validation.

- [ ] **Step 8: Generate the DOCX**

Run the builder using the bundled workspace Python runtime. Confirm the final file exists, opens as a ZIP/OOXML package, and contains non-empty `word/document.xml`, styles, numbering, headers/footers, and media parts where applicable.

## Task 3: Structural, Accuracy, and Accessibility QA

**Files:**
- Inspect: `docs/RAGenius_Instruction_Understanding_Model.docx`
- Inspect: `.tmp/ragenius_instruction_article/evidence.md`

**Interfaces:**
- Consumes: generated DOCX and evidence matrix.
- Produces: an accuracy-approved and structurally valid DOCX ready for render QA.

- [ ] **Step 1: Extract and compare document text**

Extract all DOCX paragraphs and table text. Confirm that every approved section is present, the title is correct, no draft markers remain, and the repository source list is complete.

- [ ] **Step 2: Run terminology and claim audits**

Search the extracted text for incorrect component roles, claims that `ragenius_app` is active, retrieval logic outside `rag_subsystem`, missing `app_id` isolation, and roadmap claims stated as current behavior. Cross-check all mode and field names against the evidence matrix.

- [ ] **Step 3: Audit the LLM semantic-compilation explanation**

Confirm the article explicitly states all of the following:

- The semantic compiler is LLM-backed when configured.
- It receives deterministic, application-scoped structural context.
- It produces `app_semantic_model`.
- It is prohibited from inventing ungrounded resources, IDs, workflows, modules, roles, or rules.
- Its output is canonicalized, grounded, validated, and conditionally published.
- Invalid attempts do not replace a valid active understanding.

- [ ] **Step 4: Audit Word structure and design tokens**

Verify US Letter geometry, one-inch margins, semantic heading styles, real numbering definitions, explicit table widths, accessible header rows, consistent fonts/colors, restrained callouts, page numbering, and header/footer placement.

- [ ] **Step 5: Run accessibility and package checks**

Use the document skill's accessibility audit. Confirm meaningful alternative text for diagrams, logical heading order, non-empty table headers, and absence of corrupt relationships or missing media.

- [ ] **Step 6: Correct all structural or factual defects**

Regenerate the document after corrections and repeat Steps 1–5 until all checks pass.

## Task 4: Render and Inspect Every Page

**Files:**
- Inspect: `docs/RAGenius_Instruction_Understanding_Model.docx`
- Create temporarily: `.tmp/ragenius_instruction_article/rendered/page-*.png`

**Interfaces:**
- Consumes: structurally verified DOCX.
- Produces: final DOCX that has passed page-level visual QA.

- [ ] **Step 1: Read the render-verification procedure**

Read the document skill's `tasks/verify_render.md` completely and use its required renderer and inspection criteria.

- [ ] **Step 2: Render the complete document**

Run `render_docx.py` with the bundled workspace Python runtime and output every page as PNG. Optionally emit a PDF for page-count and conversion diagnostics, but do not deliver the PDF.

- [ ] **Step 3: Inspect every page at full resolution**

Check every page for clipping, overlap, broken tables, missing glyphs, low-resolution visuals, widows/orphans, detached headings, bad page breaks, oversized blank areas, inconsistent headers/footers, and illegible diagram labels.

- [ ] **Step 4: Revise and re-render**

Correct every identified issue in the builder, regenerate the DOCX, rerun structural checks affected by the change, and render every page again. Repeat until all pages are clean.

- [ ] **Step 5: Perform final delivery checks**

Confirm the final DOCX is under `docs/`, its modified time matches the final render cycle, its package is valid, and the latest rendered page count is within the intended article range or justified by content density.

- [ ] **Step 6: Remove temporary production files**

Remove only `.tmp/ragenius_instruction_article/` after confirming the final DOCX exists and passed QA. Do not remove any repository source or user-authored file.

- [ ] **Step 7: Review the final repository diff**

Confirm the deliverable and planning documents are the only intended changes. Run `git diff --check` and verify no unrelated files were modified.

