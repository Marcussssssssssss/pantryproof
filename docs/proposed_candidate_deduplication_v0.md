# Proposed Candidate Normalization and Deduplication V0

Status: provisional development component. This profile is **not**
validation-frozen and is not approved as a held-out evaluation policy.

## Scope and boundary

`pipeline/proposed/candidate_deduplication.py` consumes one validated
`CandidateGenerationResultV0` and performs only field-compatible key
normalization and local deduplication. It does not discover candidates, call
`apply_b3()`, rank, limit, constrain, score, calibrate, or materialize
`CandidateRecordV1`, `CandidateProvenanceV1`, or `PreliminaryRankV1`.

The thesis requires candidate values to be deduplicated using a normalized,
field-compatible value while retaining source tags. The precise normalization
profile below, fallback tags, key serialization, and representative
tie-breakers are approved provisional engineering choices for this increment;
they are not claimed to be thesis-prescribed or held-out-validated.

## Public interface

```python
normalize_candidate_value(
    *, field_name: ReceiptFieldName, exact_value: str
) -> CandidateNormalizationV0

deduplicate_candidate_drafts(
    *, candidate_drafts: CandidateGenerationResultV0
) -> CandidateDeduplicationResultV0
```

The immutable, slotted local records are:

- `CandidateNormalizationV0`: exact value, field, canonical display/audit
  value, serialized key, and parse status.
- `DeduplicatedAlteredGroupV0`: one normalized altered group, its exact
  representative, and every contributing raw proposal.
- `EquivalentToC0AuditV0`: altered proposals whose normalized key equals c0.
- `CandidateDeduplicationResultV0`: the exact upstream draft result and the
  complete reconstructable output.

The profile identifier is `candidate-field-normalization-v0`; the component
records their dependency on frozen `B3-generic-rules-v0` helpers.

## Canonical key representation

Keys are compact JSON arrays with, at minimum, the profile ID, receipt field
name, semantic parse tag, and canonical payload. JSON avoids delimiter
ambiguity and retains Unicode deterministically. Keys are field-tagged, so an
identical string in two different receipt field types is not equivalent.

The exact stored c0 and exact altered values are never overwritten by their
canonical values. Normalization creates separate records only.

## Field rules

### Store name and item description

The component reuses frozen B3 `normalize_receipt_text()`:

1. Unicode NFKC normalization.
2. Unicode casefolding.
3. Frozen B3 punctuation translation (for example, curly quotation marks and
   dash variants map to their configured ASCII forms).
4. Whitespace collapse.

It does not remove general punctuation or perform synonym, brand, retailer,
pantry-identity, or semantic matching. Thus `MILK-POWDER`, `MILK/POWDER`, and
`MILK POWDER` remain distinct.

### Purchase date

The component reuses frozen B3 `parse_generic_date()` and accepts only its
complete, calendar-valid, unambiguous grammar. A valid date key carries its ISO
`YYYY-MM-DD` value. Ambiguous numeric dates retain normalized text under a
`DATE_AMBIGUOUS_TEXT` tag. Invalid or unsupported dates retain normalized text
under `DATE_INVALID_TEXT`. It never chooses a locale for an ambiguous date and
never repairs invalid input.

### Quantity

The component reuses frozen B3 `parse_positive_quantity()`: a complete,
positive, unitless Decimal representation, including the helper's comma-group
grammar. Equivalent Decimal forms receive the same plain-decimal key without
binary floating-point arithmetic or rounding. Zero, negative, unit-bearing,
and unsupported strings retain normalized text under a
`QUANTITY_INVALID_TEXT` tag.

### Unit price, line total, and receipt total

The component reuses frozen B3 `parse_money()`: a complete, nonnegative,
dot-decimal amount with one or two fractional digits and optional `RM`, `MYR`,
or `$` prefix. Valid values use an exact two-decimal amount and one of these
explicit groups:

- `MYR`: both `RM` and `MYR`.
- `USD_SYMBOL`: the literal `$` marker (without asserting a jurisdiction).
- `NO_CURRENCY`: no marker was present.

The three groups remain separate. No missing currency is inferred and no
currency conversion occurs. Unsupported precision, unsupported currency, and
other malformed values retain normalized text under `MONEY_INVALID_TEXT`; the
component does not silently round them.

## Deduplication and representative selection

Processing is one method-ready field at a time. The component computes c0's
key, groups altered proposals by their keys, and rejects mixed method-field
identities.

Within each altered group, all proposals are retained in deterministic order.
The exact representative is the first proposal under:

1. permitted source-category priority;
2. ascending exact proposed-value Unicode code-point order;
3. ascending proposal reference.

Adapter discovery position is deliberately not a representative tie-breaker.
Its original value remains inside every retained proposal for later
source-order-displacement work. The representative only supplies a future
candidate's displayed exact value; it does not replace or erase contributors.

If an altered proposal normalizes to c0, no altered candidate group is emitted
for that key. Permanent c0 remains the sole candidate draft, while every such
altered proposal is retained in `EquivalentToC0AuditV0`. Altered provenance is
not attached to an ORIGINAL shared candidate record.

## Provenance and integrity guarantees

Each group or c0-equivalence audit retains complete
`AlteredCandidateProposalV0` objects, including:

- B3 seed and proposal identity;
- source category and exact proposed value;
- original adapter position;
- all B3 event IDs and rule IDs;
- literal OCR spans, when supplied; and
- the immutable method-ready field, original c0, and source references.

No source token, span, event/rule relationship, or resource snapshot is
invented. Component-local records validate their canonical ordering and
normalization. `CandidateDeduplicationResultV0` re-derives the complete output
from its stored `CandidateGenerationResultV0`, so reconstructed or serialized
records that contradict the upstream drafts are rejected.

## Known limitations and later work

- The profile is provisional and may change only through a reviewed version
  change before validation freeze.
- Normalized equality is representation equality, not proof that two values
  have the same real-world meaning.
- Invalid and ambiguous inputs use conservative tagged text fallbacks; no
  locale, unit, currency, retailer, or product meaning is inferred.
- Composite mapping from multiple B3 rules/events into
  `CandidateProvenanceV1` remains unresolved and is intentionally deferred.
- Retailer and pantry terminology snapshot providers are unavailable in this
  increment.
- Candidate IDs, edit similarity, ranking, displacement, tie groups,
  `candidateLimit`, overflow, hard constraints, evidence features, scoring,
  calibration, and review policy belong to later tasks.
- The upstream adapter authenticates only its stored B3 evidence relationships;
  this component does not independently rerun or authenticate the original B3
  execution.
