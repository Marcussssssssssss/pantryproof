# Zero-Admitted Scoring-Operation Assembly V0

Status: bounded synthetic-only implementation pending independent review.

Research status: `PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`.

## Purpose

`pipeline/proposed/scoring_operation_assembly.py` implements the approved
audit-only completion path for a structurally valid scoring population in which
no retained candidate is admitted to scoring. It consumes existing
SCORING-02C records and returns the existing `ScoringOperationResultV2` wire
record. It introduces no shared schema, serialized error, admission policy,
score formula, probability, selection, correction, controller or persistence
state.

The public interface is:

```python
def assemble_zero_admitted_scoring_operation_v0(
    *,
    source_snapshot: ScoringSourceSnapshotV2,
    admissions: tuple[PreScoreAdmissionEvidenceV2, ...],
) -> ScoringOperationResultV2:
    ...
```

## Input boundary

The source snapshot must already retain the exact live
`FeatureConstructionResultV0`, complete c0-first D3 candidate population,
unchanged V2 results, eligible feature vectors and parent `Theta_A` reference.
The admissions must already exist. This component does not decide whether
price is sole support and does not authenticate that an operational admission
evaluator ran.

Before examining admission states, the assembler revalidates:

- the complete scoring source and its deterministic ID;
- exactly one admission per retained candidate;
- exact D3 order and candidate identity;
- exact V2-result and eligible-feature identity;
- the source snapshot binding;
- permanent c0 identity;
- unique and deterministic admission IDs; and
- all nested SCORING-02C record and version invariants.

Missing, additional, duplicate, reordered, cross-snapshot, substituted,
malformed or noncanonical records fail before any output is constructed.

## Valid admitted populations

After complete validation, any `ADMITTED` candidate causes
`ScoringOperationDeferredError`. This is an execution-boundary exception, not
a shared scoring outcome and not an integrity classification. No partial
result or `FieldScoringFailureV2` is created. The assembler does not invoke a
resolver or scorer and does not fabricate a raw score or probability.

Operational trusted-Theta resolution and scoring remain unauthorized and
blocked.

## Zero-admitted completion

For a complete population with zero admitted candidates, the assembler:

1. creates one `CandidateScoreEvidenceV2` per retained candidate;
2. records `NOT_APPLICABLE` with the exact reason implied by the existing
   admission state;
3. preserves each original admission object and its source relationships;
4. creates a complete c0-first `FieldScoringAuditV2`;
5. records `COMPLETE_ZERO_ADMITTED_BYPASS` and
   `NOT_INVOKED_ZERO_ADMITTED`;
6. keeps resolver result and trusted scorer binding null; and
7. materializes score, field-audit and operation IDs using the existing
   SCORING-02C canonical-content ID functions.

The resulting operation serializes through the existing scoring V2 codec and
decodes only against its exact live source snapshot. Canonical IDs are content
integrity metadata, not authentication, owner approval or empirical evidence.

## Failure and atomicity

Existing `ScoringAuditIntegrityError` and `ScoringSourceBindingError` failures
propagate. Complete validation precedes the deferred-operation check, so an
invalid record cannot be concealed by an otherwise admitted state. All local
output objects are created only after source and admission validation and the
zero-admitted check succeed.

## Synthetic conformance coverage

The focused tests cover valid mixed-state bypasses, c0 and ordering continuity,
exact V2/feature/Theta relationships, reason mapping, deterministic IDs,
canonical byte equality, source-bound decoding, malformed populations,
identity substitutions, version and ID tampering, admitted-population
deferral, validation precedence and resolver non-invocation.

All evidence is synthetic. A test pass establishes structural behavior only.

## Explicit exclusions and remaining blockers

This component does not implement or authorize:

- an operational price-only admission evaluator;
- a trusted registry, artifact resolver or real `READY` scorer;
- a scoring formula, learned model, model fitting or inference;
- candidate-local score `UNAVAILABLE`;
- calibration, `Kappa` or probability production;
- candidate selection, replacement of permanent c0 or automatic commitment;
- `Phi`, review routing, controller aggregation or persistence;
- Android/Kotlin changes; or
- real-receipt, validation, calibration or held-out evaluation.

SM-06 remains blocked. SM-02, SM-04, SM-08 and SM-10 remain deferred; SM-07
remains blocked; and SM-09 and SM-11 remain unresolved. Independent review is
required before any Git integration.
