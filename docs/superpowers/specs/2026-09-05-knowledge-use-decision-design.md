# Knowledge Use Decision Design

**Status:** Current accepted design

**Date:** 2026-09-06

**Contract:** `docs/knowledge-use-decision-contract.md`

## Implemented Architecture

`workflows/nodes/answer.py` computes a deterministic two-mode decision and supplies it to normal and safe-answer calls. The answer prompt instructs the model to prefer evidence, supplement cautiously when allowed, and avoid fabricated citations.

The decision remains local to answer generation. It does not add a graph node, planner branch, retrieval operation, or DeepSeek call.

The feature is intentionally active without a rollout environment variable. The accepted policy precedence is explicit: an evidence-only marker disables supplementation; otherwise the answer model may use relevant stable model knowledge subject to application instructions and safety rules.

## Data Shape

```json
{
  "mode": "application_evidence_only | evidence_first_with_model_supplementation",
  "model_knowledge_allowed": true,
  "reason": "stable_reason_code"
}
```

The decision does not duplicate instructions, retrieved evidence, or secrets.

## Data Flow

1. Evidence analysis computes existing coverage independently.
2. Answer generation assembles app-local policy context.
3. A deterministic marker check creates the Knowledge Use Decision.
4. The decision is supplied to the normal answer call and copied into any safe-answer retry context.
5. Context optimization retains the compact decision.

Direct general out-of-scope answers remain a separate path and do not use evidence supplementation.

## Safety and Compatibility

- Explicit evidence-only policy always disables supplementation.
- Missing optional policy sections do not create an evidence-only restriction.
- No planner, retrieval, resource-binding, citation schema, or application snapshot changes are required.
- Existing answer output schema remains unchanged.
- Token cost is negligible because the decision is compact and deterministic.
- The decision is not currently persisted or exposed as a public API field.

## Testing Strategy

Unit tests cover supplementation permission, evidence-only precedence, normal/safe-answer propagation, citation separation, and direct general-route context isolation.

Adjacent pipeline tests verify absence of changes to planner, retrieval, resource, persistence, and workflow state.

Representative manual testing of Knowledge Use Decision and Semantic Scope behavior was accepted on 2026-09-06. The feature remains active in code.
