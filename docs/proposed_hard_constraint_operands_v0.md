# Proposed Hard-Constraint Operand Audit V0

## 1. Status and placement

This document specifies a provisional, synthetic-only observational component
between the completed hard-constraint input context and a future
hard-constraint evaluator:

```text
HardConstraintInputResultV0
    -> raw receipt relationship and operand audit V0
    -> future approved hard-rule profile and evaluator
```

The moderated thesis requires candidate-level type, provenance/source,
association, layout and arithmetic checks in Section 3.4.4, Section 4.3,
Tables 4.5-4.6 and Algorithm 4.1. Table 4.10 additionally requires declared
grammars and frozen arithmetic, rounding, promotion, adjustment and
weighted-item behavior. Those eligibility rules are not defined here.

This audit is not evidence that a candidate passes or fails a constraint. It
only records which raw B2 fields and relationships are already present.

## 2. Public API

```python
audit_hard_constraint_operands(
    *,
    hard_constraint_input: HardConstraintInputResultV0,
) -> HardConstraintOperandAuditResultV0
```

The sole input is the exact previously prepared context. There are no candidate
overrides, rule catalogues, grammars, tolerances, resources, prices, reference
annotations, ground truth, validation data, scores or review inputs.

The function revalidates stored records but does not rerun OCR, the source
gate, B2, B3, candidate generation, deduplication, identity preparation,
provenance materialization, ranking, limiting or finalization.

## 3. Local records

All component records are frozen, slotted and versioned.

### `OperandAvailabilityV0`

| State | Exact meaning |
|---|---|
| `AVAILABLE` | The shared B2 field is `EXTRACTED` and retains a nonempty raw value and source-token references. |
| `MISSING` | The shared B2 field is explicitly `MISSING`; its raw value remains `None`. |
| `UNRESOLVED` | The shared B2 field is explicitly `UNRESOLVED`; its raw value remains `None` and its existing reason/evidence remain on the field. |
| `NOT_APPLICABLE` | The operand relationship structurally does not apply, such as item operands for a receipt-level target. No field is fabricated. |

`AVAILABLE` does not mean parseable, plausible, numerically valid or
constraint-eligible.

### `OperandEvidenceV0`

This record preserves the exact existing `StructuredField` reference. At first
construction it also captures one private frozen observation containing the
field ID, receipt ID, field name, item-row ID, status, raw value, source-token
IDs, confidence and unresolved reason. Public observational properties expose
those originally observed primitive values; `b2_field` remains the exact real
upstream object.

Calling `__post_init__()` again does not refresh the private observation. The
current upstream field is structurally revalidated and compared with the first
observation. A valid-looking later change, such as replacing `11.00` with
`12.00`, therefore raises an integrity error instead of silently becoming the
new observed value. The snapshot is integrity metadata, not a second candidate
value or a shared-contract record.

### `ItemRowOperandEvidenceV0`

This record retains one exact `ReceiptItemRow` and the exact four B2 fields in
their public order:

1. item description;
2. quantity;
3. unit price; and
4. line total.

Partial rows are retained. Missing and unresolved operands are not dropped.

### `CandidateSubstitutionPositionV0`

This record identifies the original B2 field targeted by a candidate. An item
target records its exact row, row index and field index. A store, date or
receipt-total target is explicitly receipt-level and has no invented item row.

The candidate value is not substituted into the stored field. Permanent `c0`
therefore equals the original raw value, while an altered candidate can expose
a different `candidate_value` alongside the unchanged `original_b2_value`.

### `CandidateOperandAuditV0`

Each prepared candidate receives exactly one audit containing:

- the exact candidate reference;
- the exact target field and substitution position;
- an explicit available target-source relationship backed by the extracted
  field's stored source-token references;
- item-row relationship availability;
- every detected B2 item row and its raw operands; and
- the exact stored receipt-total operand.

For the current shared contract, a valid extracted item target always carries
an item-row ID and is contained in one unique stored row. If a future valid
contract permits insufficient row information, that condition must be exposed
as `UNAVAILABLE`; it must not be resolved by matching display text, equal
prices, OCR similarity or inferred geometry.

### `HardConstraintOperandAuditResultV0`

The aggregate retains the exact `HardConstraintInputResultV0` and one ordered
candidate audit per `hard_constraint_input.candidates` member. Overflow,
blocked-audit and coverage information is exposed through the existing input
context rather than recomputed or copied into a new ledger.

The aggregate additionally retains a private ordered observation of every OCR
token already present in the source-evidence graph: token and receipt IDs,
literal text, polygon coordinates and raw confidence. Reconstruction compares
the live upstream tokens with this first observation. Public results still
refer to the real `OcrSourceToken` objects; copied token records are not exposed
as replacement source evidence, and OCR is never fetched or rerun.

## 4. Candidate order and coverage

The input tuple is already:

```python
(c0, *retained_altered_candidates)
```

The audit preserves that order and exact references. Permanent `c0` is always
audited. Materialized overflow candidates, provenance-blocked overflow
identities, blocked retained diagnostics, equivalent-to-c0 duplicates and any
new/backfilled candidate are excluded.

Incomplete coverage caused only by blocked overflow remains visible and does
not change the prepared retained set. A blocked retained set never reaches this
component because `HardConstraintInputResultV0` cannot be constructed for it.

## 5. Receipt relationships and raw evidence

Row association uses the stored B2 field ID, `item_row_id`, `ReceiptItemRow`
identity and public row order. It never uses candidate display text or numeric
similarity.

Receipt-level evidence preserves:

- all detected B2 rows in order;
- all four public fields per row in order;
- exact field statuses and raw values;
- exact source-token references;
- the stored receipt-total field; and
- partial, missing and unresolved fields.

The component does not assert that all purchased items were detected. It does
not add hidden rows or derive a receipt total from observed line totals.

## 6. Integrity versus ordinary unavailability

An integrity contradiction includes a changed receipt/field/candidate ID,
forged row relationship, substituted reference, changed raw status/value,
changed field confidence/reason, changed source-token reference or literal OCR
payload, candidate omission/duplication/reorder or overflow injection. These
raise `HardConstraintOperandIntegrityError`.

Ordinary unavailability is valid upstream evidence such as a `MISSING` unit
price or `UNRESOLVED` quantity. It remains an observational state and is not a
constraint rejection.

The aggregate reconstructs the expected audit from the revalidated input and
compares the live records with the observations captured during its first
construction. This distinguishes three guarantees:

1. shared upstream object references remain the public evidence graph;
2. private local observations detect covered changes after observation; and
3. shared validators continue to enforce structural record validity.

Frozen dataclasses alone are not treated as proof of immutability. These checks
do not prove that evidence was authentic before the observation, prevent every
possible mutation, or withstand deliberate coordinated tampering with both the
upstream graph and every private observation.

## 7. Explicit exclusions

This component creates no `ConstraintResultV1` or `CandidateEvidenceV1` and
performs no:

- hard-rule PASS/FAIL decision;
- type, date, quantity or money parsing;
- `Decimal` conversion;
- item or receipt arithmetic;
- tolerance or rounding evaluation;
- promotion, tax, voucher, discount or rounding interpretation;
- weighted-unit inference or conversion;
- layout scoring;
- price-reference lookup;
- seven-slot feature construction;
- scoring, calibration or candidate selection;
- review routing; or
- inventory persistence.

In particular, strings such as `RM 5.50` and `11.00` remain exact strings.

## 8. Deferred decisions and coordination

The future eligibility stage still requires joint approval by Leng, Tai and
the shared-contract owners for:

- exact rule IDs and per-field applicability;
- date, quantity and monetary grammars;
- layout and association rules;
- arithmetic precision, tolerance and rounding;
- promotion, adjustment, tax and weighted-item exceptions;
- receipt completeness and adjustment-scope semantics;
- authenticated `Theta_A` hard-rule manifest content; and
- mapping mandatory unavailable evidence into the aggregate interface.

Contract V1 currently exposes only `ELIGIBLE` and `CONSTRAINT_REJECTED`. It
does not represent a mandatory hard rule whose required evidence is
unavailable. This audit does not hide that gap by treating unavailability as a
pass or failure. Any shared-contract change requires coordinated schema,
fixture, traceability and test review.

## 9. Limitations

V0 is exercised only with synthetic fixtures. It authenticates neither source
bytes nor the `Theta_A` configuration manifest, and it proves neither
exactly-once upstream execution nor receipt completeness. The observation
snapshots detect only covered post-construction inconsistencies; they are not
cryptographic hashes or source-authenticity assertions. The component performs
no OCR inference, dataset access, tuning, held-out evaluation, human review or
persistence operation.
