# Proposed Purchase-Date Feature Construction V0

Status: provisional, synthetic-only implementation for
`FEATURE-CONSTRUCTION-01`.

Research status: `PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`.

## Purpose and public boundary

`pipeline/proposed/feature_construction.py` constructs the approved seven-slot
feature representation for purchase-date candidates whose complete source-bound
V2 hard-constraint result is `ELIGIBLE`:

```python
construct_purchase_date_features_v0(
    *,
    operand_audit: HardConstraintOperandAuditResultV0,
    constraint_results: tuple[ConstraintResultV2, ...],
) -> FeatureConstructionResultV0
```

The function does not score, calibrate, select or replace a candidate. It does
not route review, write persistence state, or activate Android behavior.

V0 is deliberately purchase-date-specific. Its approved arithmetic and price
non-applicability values must not be reused for another field type.

## Exact source handoff

The private backend helper
`_execute_purchase_date_observational_graph_v0(...)` performs the existing
candidate, D3 and G2A sequence once and returns:

1. the exact `HardConstraintOperandAuditResultV0` instance supplied to G2A; and
2. its corresponding ordered `tuple[ConstraintResultV2, ...]`.

The existing public
`execute_purchase_date_observational_path_v0(...)` keeps its six keyword-only
arguments and continues to return only the V2 tuple. It delegates to the private
helper, so no existing public contract or package export changes.

Feature construction consumes the exact in-process audit and matching results.
It does not rerun OCR, the source gate, B2, B3, the proposed adapter, suspicion,
candidate generation, D3 or G2A.

## Component-local records

- `FeatureSlotValueV0` stores one typed value, its availability, truthful
  provenance references and an optional typed missing/non-applicable reason.
- `CandidateFeatureVectorV0` binds seven ordered slots to the exact eligible D3
  candidate, candidate audit, V2 result, permanent c0 and `Theta_A`.
- `FeatureConstructionResultV0` retains the complete unchanged V2 tuple, the
  exact D3 audit, the exact E1 readiness observation and eligible-only vectors.

These are component-local records. They do not change Contract V1, Contract V2
or `pipeline.proposed` package exports. `CandidateEvidenceV1` is not fabricated:
it requires V1 constraints and later score/calibration state, while V2
`CONSTRAINT_UNAVAILABLE` has no safe V1 projection.

## Seven-slot behavior

The exact order is `[q_o, q_e, a_l, a_y, s_r, s_a, s_p]` and the schema ID is
`pantryproof-candidate-evidence-7-v1`.

| Slot | V0 value | Missingness and provenance |
| --- | --- | --- |
| `q_o` | Minimum of all exact referenced native OCR confidences after deterministic `Decimal(str(value))` conversion. | A missing referenced score makes the slot `None`. Every present value must be finite, non-Boolean and inside the provisional feature domain `[0,1]`; values are never clipped or rescaled. All source token IDs are retained. The domain is a feature-input rule, not a claim about every PaddleOCR configuration. |
| `q_e` | Direct bounded B2 target-field confidence when one is actually stored. | Current B2 stores `None`, so V0 records missing extractor confidence. OCR confidence is never substituted. Field ID and extractor version are retained. |
| `a_l` | Permanent c0 is `Decimal("1")`. An altered candidate reuses the exact stored `PreliminaryRankV1.normalized_edit_similarity`. | Similarity is not recomputed and is not claimed to be independent lexical correctness. Candidate, c0 and candidate-provenance IDs are retained, together with any tie-group ID. |
| `a_y` | `None`. | V0 invents no spatial-agreement score. Exact target field, item-row where applicable and source-token references remain provenance. |
| `s_r` | `None`. | No approved versioned retailer resource is bound. The provenance group is empty rather than containing a fabricated resource reference. |
| `s_a` | Categorical `NOT_APPLICABLE`. | Approved only for purchase-date candidates. Field and candidate identity are retained; the slot is not marked missing. |
| `s_p` | Categorical `NOT_APPLICABLE`. | Approved only for purchase-date candidates. It is not a price lookup, plausibility result or ground-truth claim. |

The missingness mask is always equivalent to `value is None`. Genuine missing
evidence, approved non-applicability, invalid evidence and configuration errors
remain distinct.

## V2 admission and complete-set validation

Before any vector is built, V0 requires:

- exactly one V2 result for every retained D3 candidate;
- canonical candidate order and unique result/candidate IDs;
- exact Python object identity for each D3 candidate and permanent c0 at both
  the aggregate-result and nested rule-outcome boundaries;
- complete receipt and field identity;
- complete content equality for D3, V2 profile and `Theta_A` references;
- one common purchase-date rule profile; and
- successful nested D3 and V2 reconstruction.

Aggregate handling is:

- `ELIGIBLE`: construct a vector;
- `CONSTRAINT_REJECTED`: retain the complete V2 audit but construct no vector;
- `CONSTRAINT_UNAVAILABLE`: retain the complete V2 audit and reasons but
  construct no vector.

V2 unavailability is never projected into V1 eligibility, rejection or
`OTHER`. Permanent c0 remains first and auditable even when it is rejected or
unavailable. HC-D04, HC-D05 and HC-D13 remain controller decisions and are not
resolved here.

Validation completes for the whole candidate set before a result is returned.
Any integrity or configuration failure raises a typed feature-construction
exception and returns no partial aggregate.

## Identity and configuration limitations

The result records capture their original D3 audit, candidate audit, candidate,
V2 result and E1 readiness references once. Repeated validation rejects later
reference substitution. Candidate and c0 binding uses `is`, including every
nested V2 rule outcome; `Theta_A` and profile binding uses complete immutable
content equality. Slot missingness and non-applicability reasons must use the
component's typed reason codes.

`ConstraintResultV2` itself does not store the originating operand-audit or
candidate-audit object. A standalone value-equal reconstruction that keeps the
same exact candidate and c0 objects cannot independently prove which factory
invocation created it. The live private backend handoff and aggregate
capture-once checks preserve the intended in-process boundary; they are not
cryptographic authentication.

Likewise, a declared `ConfigurationRefV1.content_hash` is metadata. This
component neither authenticates configuration bytes nor declares `Theta_A`
evaluation-frozen.

## Explicit exclusions and remaining dependencies

V0 contains no:

- retailer or price resource provider;
- layout-agreement formula;
- arithmetic evaluator for non-date fields;
- scorer or trained parameters;
- calibration or `Kappa` behavior;
- candidate selection or replacement;
- `Phi`, PT1 or PT2 routing;
- field decision, review resolution or persistence outcome; or
- real-receipt or held-out evaluation path.

Production expansion requires separately approved and versioned retailer/price
resources, field-specific layout and arithmetic methodology, authenticated
configuration manifests, scorer/calibration decisions and controller rules.
Synthetic tests establish deterministic contract behavior only; they do not
establish extraction accuracy, feature validity or real-backend readiness.

## Synthetic conformance coverage

The focused suite checks exact order, values, types, masks, provenance,
purchase-date non-applicability, mixed and partially missing OCR confidence,
provisional OCR domain validation, exact lexical-similarity reuse, eligible-only
vectors, preservation of rejected/unavailable audits, permanent c0, exact D3
identities at aggregate and nested-rule boundaries, typed reason codes, complete
`Theta_A` equality, result completeness/order, substitution attacks,
determinism, reconstruction tampering, atomic failure and absence of upstream
reruns. Existing backend tests additionally prove the private graph helper uses
candidate generation, D3 and G2A once while leaving the public API unchanged.
