# PantryProof Hard-Constraint Input Context V0

Status: **SYNTHETIC-ONLY DEVELOPMENT BOUNDARY — NOT EVALUATION-FROZEN**

## 1. Authority and stage placement

This component follows the moderated thesis Algorithm 4.1, especially lines
1–8, and the provisional Shared Contract V1. Algorithm 4.1 requires a stored
successful source gate, permanent original `c0`, bounded candidates, and one
audit path per retained candidate before hard constraints are evaluated.

The component sits after shared candidate finalization and immediately before a
future hard-constraint evaluator:

```text
candidate finalization
    -> hard-constraint input context V0
    -> future hard-constraint evaluation
    -> future seven-slot evidence/scoring/calibration/policy stages
```

It prepares verified inputs only. It does not evaluate a rule, declare a
candidate eligible or rejected, construct `ConstraintResultV1` or
`CandidateEvidenceV1`, or make a correction, review, or persistence decision.
The evaluator remains deferred because the rule catalogue, parse grammars,
arithmetic tolerances, exception policy, and operational unavailability
semantics have not been approved or frozen.

## 2. Public API

```python
prepare_hard_constraint_inputs(
    *,
    finalization_result: CandidateFinalizationResultV0,
) -> HardConstraintInputResultV0
```

The API has one keyword-only input. It accepts no rule catalogue, threshold,
price, retailer or terminology resource, configuration override, score,
calibration value, review state, ground truth, or held-out reference.

## 3. Exact upstream traversal

The component reads the already-stored generation result through the approved
graph and never invokes a public upstream computation:

```python
generation = (
    finalization_result
    .limit_result
    .ranking_result
    .provenance_result
    .identity_preparation
    .deduplication_result
    .candidate_drafts
)

method_ready_field = generation.original.method_ready_field
adapter_result = generation.adapter_result
```

The prepared record preserves those selected method and adapter objects by
reference. It also preserves the supplied finalization result and every
prepared candidate by reference. Where an upstream contract permits distinct
but structurally equal records, this boundary retains that rule instead of
adding a new identity requirement. For example, the suspicion method, adapter
method, and selected original method must be completely equal, while the newly
prepared method field must be the exact object reached through
`generation.original`.

## 4. Reconstruction and source integrity

Preparation first executes the existing finalization reconstruction boundary.
That revalidates the stored chain through limiting, ranking, provenance,
identity preparation, deduplication, candidate generation, and suspicion. The
context then verifies:

- one matching adapter method-ready field;
- original `PRE_REVIEW_AUTOMATIC` structured B2 output and no fallback
  disposition;
- a stored `SUFFICIENT` source-evidence gate, without rerunning the gate;
- receipt and field identities;
- exact original B2 field value and permanent `c0` identity;
- source-token IDs, token order, literal stored token records, and source image;
- source processing status, B2 extraction status, and extractor version;
- the permanent original candidate and its canonical original provenance; and
- one consistent synthetic `Theta_A` reference inherited through suspicion,
  ranking, and limiting.

Nested dataclass validators are rerun to detect synthetic adversarial
post-construction mutation. This is structural consistency checking, not
cryptographic authentication. It cannot prove that source-gate execution was
exactly once, that model output is scientifically valid, or that a synthetic
configuration corresponds to an authenticated frozen manifest.

The context explicitly rejects stored B2 output whose `output_stage` has been
mutated to `HUMAN_REVIEWED` or `ORACLE_MODIFIED`. Human-review and oracle state
belong to separate later records; they cannot be smuggled into the original
automatic extraction evidence consumed by this boundary.

## 5. C0-first candidate tuple

The prepared tuple is exactly:

```python
(
    finalization_result.original_candidate,
    *finalization_result.retained_records,
)
```

Permanent `c0` is always first. Retained altered candidates keep finalization
order and object identity. No overflow record, blocked diagnostic identity,
duplicate, omission, substitution, reorder, or backfill is permitted. A valid
empty altered set produces a `c0`-only tuple. A future hard-constraint failure
may make `c0` ineligible for automatic acceptance, but it must not remove `c0`
from this prepared audit set.

## 6. Readiness and coverage

Readiness controls whether complete input preparation is possible:

| Finalization readiness | Context response |
|---|---|
| `RETAINED_SET_STRUCTURALLY_FINALIZED` | Prepare the exact retained set |
| `BLOCKED_BY_RETAINED_PROVENANCE` | Raise typed operational unavailability with `RETAINED_PROVENANCE_BLOCKED` |
| `RANKING_UNAVAILABLE` | Raise typed operational unavailability with `RANKING_UNAVAILABLE` |

No partial `HardConstraintInputResultV0` is created for an unavailable state.
`HardConstraintInputUnavailableError` retains the exact upstream finalization
result and a machine-readable `HardConstraintInputUnavailableReasonV0`.
Malformed, forged, or contradictory evidence instead raises
`HardConstraintInputIntegrityError`, with wrapped validation failures preserved
as the exception cause.

Operational unavailability applies at the public preparation boundary when a
valid upstream finalization cannot supply a complete retained set. Once a
`HardConstraintInputResultV0` exists, substituting an unavailable finalization
is an aggregate-integrity contradiction: reconstruction raises
`HardConstraintInputIntegrityError` and preserves the original
`HardConstraintInputUnavailableError` as its cause.

Coverage and readiness are intentionally independent. An
`INCOMPLETE_BLOCKED_PROVENANCE` coverage status is accepted when the blocked
identity is overflow-only and the retained set is structurally finalized. The
coverage warning and blocked audits remain visible through derived properties.
A complete-ledger label cannot override blocked retained-set readiness.

## 7. Prepared record shape

`HardConstraintInputResultV0` is frozen, slotted, and versioned. Its stored
fields are only:

- `finalization_result`;
- `method_ready_field`;
- `adapter_result`;
- `candidates`;
- fixed component version; and
- fixed record version.

Derived properties expose the original B2 result and receipt output, source
evidence, stored gate, relevant source tokens and image identity, overflow and
blocked audits, full-ledger coverage status, receipt/field IDs, and inherited
`Theta_A` reference. The record has no `eligible`, `passed_constraints`,
`production_ready`, or `manifest_verified` flag.

## 8. Deferred work and team coordination

Before an eligibility-bearing implementation, Leng and Tai must jointly approve
the hard-rule catalogue, field-compatible parse grammars, rule applicability,
arithmetic tolerances and rounding behavior, promotion/discount and
variable-measure exceptions, and how per-rule unavailable/not-applicable states
map into the shared aggregate contract. Any shared Contract V1 change requires
coordinated schema/version, fixture, traceability, and test review.

Retailer and price evidence do not belong in this context. Price evidence
cannot generate a candidate or serve as a hard-constraint input here. The
future seven-slot feature stage must preserve missing price evidence as missing,
not as negative ground truth.

All current configuration and evidence used by this component are synthetic.
No OCR inference, dataset access, training, calibration fitting, threshold
selection, held-out evaluation, human review, or inventory mutation occurs.
