# Knowledge Use Decision Contract

**Status:** Normative and active

**Date:** 2026-09-06

**Scope:** Normal user-query answer generation in `ragenius_app_skeleton`.

## 1. Purpose

Knowledge Use Decision controls whether the answer model may supplement retrieved evidence with relevant model knowledge. It does not determine workflow routing and does not replace retrieval, evidence analysis, application instructions, or safety policy.

## 2. Design Constraints

- No additional LLM call is required to make the decision.
- The decision is deterministic from current application policy.
- Retrieved evidence remains the preferred factual source.
- Model knowledge must remain within the active application's purpose, instructions, and safety boundaries.
- Model knowledge must never receive fabricated citations.
- `rag_subsystem` remains unchanged.

## 3. Decision Modes

### `application_evidence_only`

Use when an explicit application policy requires answers to rely only on retrieved evidence or the knowledge base.

- `model_knowledge_allowed = false`
- missing evidence is disclosed or handled through existing safe-answer behavior

### `evidence_first_with_model_supplementation`

Use when no evidence-only restriction exists.

- `model_knowledge_allowed = true`
- evidence is preferred and must not be contradicted without explicit uncertainty handling
- stable, relevant model knowledge may fill gaps needed for an effective in-scope answer

### Related `general_model_direct` route

`general_model_direct` is not a Knowledge Use Decision value. It is a separately validated general out-of-scope route. This route is not evidence supplementation and must not inherit application-specific workflow/resource context.

## 4. Inputs

The deterministic decision inspects only:

- global application instruction context
- configured safety rules
- adapter guardrails
- selected instruction block policy

The decision must not scan unrelated applications or use another application's policy.

## 5. Evidence Sufficiency

Evidence sufficiency informs whether supplementation is useful; it does not grant permission. Permission comes from application policy.

The deterministic Knowledge Use Decision does not classify evidence sufficiency. Existing `evidence_analysis`, retrieved evidence, and `infoTypes_missing` remain separate answer-model inputs. The answer model may choose not to supplement when missing information is unnecessary, unstable, unsafe, outside application scope, or outside its reliable knowledge.

## 6. Answer Behavior

When supplementation is allowed:

- use only relevant, stable knowledge needed to answer the current request
- distinguish evidence-backed statements from model-knowledge supplementation when the distinction materially affects trust
- do not cite model knowledge as a retrieved source
- do not override user-provided artifacts or authoritative retrieved evidence silently
- preserve application tone, workflow, output format, and safety rules

When supplementation is prohibited:

- use retrieved/session-upload evidence only for factual claims
- retain existing missing-information and safe-answer behavior
- never silently enable supplementation because retrieval was weak

## 7. Activation and Observability

Knowledge Use Decision is active for normal in-scope answer generation. The runtime:

- constructs one compact decision before answer generation
- supplies the same decision to the normal answer call and any safe-answer retry
- preserves the decision through compact-context optimization
- adds no model invocation
- does not include the decision in the separate `general_model_direct` context

The decision is currently an ephemeral answer-context control, not a public response field or persisted turn diagnostic. Existing task-model diagnostics continue to report the answer calls and token context. Adding persisted decision observability later is permitted only as an optional, backward-compatible field and must not change routing or answer behavior.

The active decision contains:

- decision mode
- model-knowledge permission
- stable reason code

## 8. Failure Behavior

- Missing optional policy sections are treated as having no explicit evidence-only marker.
- No observability enhancement may trigger a second LLM call.
- Provider failure continues through existing answer fallbacks.
- The decision must not alter planner state, retrieval filters, citations, session ownership, or application isolation.

## 9. Acceptance Criteria

- Explicit evidence-only policy disables supplementation.
- Ordinary in-scope query permits evidence-first supplementation without another LLM call.
- Weak evidence alone cannot override an evidence-only policy.
- Citations contain only retrieved or session-upload sources.
- Direct out-of-scope behavior remains separate.
- The active decision is supplied to both normal and safe-answer calls.
- Compact-context optimization retains the decision unchanged.
- The direct general out-of-scope call receives only the user query and bounded chat history, not the Knowledge Use Decision or application evidence.
- Bible Tutor, Church Ministry Prompt Designer, GPT Application Design Assistant, and 與孩子一起成長 retain workflow and resource behavior.
- Representative manual testing for Semantic Scope and Knowledge Use Decision was accepted on 2026-09-06.
