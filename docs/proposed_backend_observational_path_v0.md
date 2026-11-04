# Proposed Backend Observational Path V0

Status: `PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`

Task: `BACKEND-INTEGRATION-02`

This document describes the smallest reusable production execution seam that
connects the approved proposed-method candidate path to the purchase-date
hard-constraint audit stage. It is observational only: it does not select a
candidate, replace permanent `c0`, commit a correction, or persist an outcome.

## Public interface

`pipeline.proposed.backend_observational_path` exports one function:

```python
def execute_purchase_date_observational_path_v0(
    *,
    adapter_result: ProposedAdapterResultV1,
    suspicion_result: SuspicionResultV0,
    ranking_configuration: CandidateRankingConfigurationV0,
    limiting_configuration: CandidateLimitingConfigurationV0,
    rule_profile_reference: HardConstraintProfileRefV2,
    grammar_reference: str,
) -> tuple[ConstraintResultV2, ...]:
    ...
```

Every argument is keyword-only. The caller must supply existing typed records
and explicit configuration references. The interface has no default
configuration, generic-dictionary input, synthetic observation, or new result
schema.

## Execution sequence

The function composes the existing production components in this order:

1. Candidate draft generation from the stored adapter and suspicion records.
2. Candidate deduplication.
3. Candidate identity preparation.
4. Altered-candidate provenance materialization.
5. Preliminary ranking under the supplied ranking configuration.
6. Candidate limiting under the supplied limiting configuration.
7. Shared candidate-record finalization.
8. D3 hard-constraint input preparation.
9. D3 raw-operand audit.
10. Purchase-date candidate-set constraint evaluation under the supplied G2A
    profile and grammar reference.

The returned value is the existing immutable
`tuple[ConstraintResultV2, ...]`. Candidate ordering, canonical D3 object
references, permanent `c0`, provenance, and the frozen `Theta_A` chain are
therefore retained by the existing components rather than reimplemented here.

## Validation and failure behavior

The seam deliberately adds no replacement validation policy. Each component
revalidates its own inputs and bindings, including adapter/suspicion identity,
candidate provenance, ranking and limiting configuration, D3 source evidence,
profile binding, grammar compatibility, and complete `Theta_A` equality.

Existing typed exceptions propagate unchanged. The function does not catch,
repair, skip, or downgrade an invalid or unavailable record. Because the final
tuple is returned only after the entire purchase-date stage succeeds, a failed
candidate or binding cannot produce a partial result.

Every retained purchase-date candidate is evaluated once by the existing
candidate-set stage. Its approved `PASS`, `FAIL`, or `UNAVAILABLE` audit state
is preserved. No state is interpreted as a selection or correction decision.

## Upstream boundary

The caller remains responsible for producing the adapter result and suspicion
result before invoking this seam. The function does not run OCR, B2 extraction,
B3 extraction, the B2-to-proposed adapter, or suspicion detection. It also does
not reconstruct a suspicion context or infer missing configurations.

## Synthetic conformance coverage

The focused tests cover:

- the natural unmodified B2/B3 adapter path;
- multiple retained candidates yielding `PASS`, `FAIL`, and `UNAVAILABLE`;
- deterministic repeated execution and unchanged upstream records;
- permanent-`c0`, provenance, D3 identity, and `Theta_A` continuity;
- fail-closed adapter/suspicion, ranking, limiting, profile, and seed-graph
  contradictions; and
- absence of OCR, B2, B3, adapter, or suspicion reruns inside the seam.

All evidence is synthetic. Passing these tests is compatibility evidence only;
it is not an accuracy, calibration, or held-out evaluation result.

## Exclusions and remaining dependencies

This V0 path does not implement scoring, calibration, candidate selection,
selective verification, review routing, inventory persistence, Android
activation, or a full receipt controller. Production callers still need an
approved source for suspicion inputs and validation-frozen configuration and
resource references. The current candidate-limit fixture mechanism remains a
development boundary until its production configuration ownership is approved.

Configuration identifiers and declared hashes remain structural provenance
metadata; this seam does not authenticate source bytes or prove source-gate
execution count. Integration into Git and any evaluation freeze require
separate authorization and independent review.
