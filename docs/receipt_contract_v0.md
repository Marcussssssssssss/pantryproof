# PantryProof Receipt Contract Version 0

Status: initial shared contract for review, not a finalized experimental contract.

## Scope

This contract defines immutable OCR evidence, structured receipt fields, item
rows, receipt output, future correction evidence, optional external price
evidence, and policy/application outcomes. It does not implement OCR,
extraction algorithms, correction scoring, thresholds, calibration, review,
SQLite persistence, inventory updates, or evaluation.

The authoritative moderated FYP1 thesis was not present in the repository,
task attachments, or nearby project directory during Task 1.2. The contract
therefore implements only the task's explicit requirements. Thesis-specific
formats, thresholds, state-transition details, and algorithm semantics remain
unresolved pending review of Chapters 3 and 4.

## Core records

- `OcrSourceToken` preserves literal OCR text, source polygon and optional raw
  model confidence. It is immutable.
- `ReceiptSourceEvidence` groups receipt/image identity, provenance, processing
  status, OCR tokens and one recorded `SourceEvidenceGateResult`.
- `StructuredField` represents one of the seven primary fields as extracted,
  missing or unresolved, with receipt/item-row association and source-token
  references.
- `ReceiptItemRow` holds description, quantity, unit price and line total. A row
  cannot be created unless at least one field is extracted from OCR evidence.
- `ReceiptOutput` holds store, date, detected rows, receipt total, source
  evidence, extraction status and extractor version. Its stage is fixed to
  `PRE_REVIEW_AUTOMATIC`; reviewed and oracle-modified outputs require separate
  future record types.
- `CorrectionEvidence` preserves an immutable original candidate alongside
  optional alternatives, an explicitly selected accepted alternative, and
  qualitative uncertainty. It stores the recorded source-gate result ID and
  does not re-run the gate.
- `ExternalPriceReference` is optional evidence and is separate from extracted
  unit-price ground truth.
- `PreResolutionDisposition` stores the frozen automatic disposition and its
  recorded gate result.
- `PersistenceOutcome` records a later commit or persistence failure while
  retaining the original `PreResolutionDisposition` by reference.

## Required invariants

1. The source sufficiency gate is evaluated outside this contract exactly once
   on the image/OCR package. Its recorded result is required before a
   `ReceiptOutput` is created. Candidate correction refers to its result ID.
   The dataclasses can validate the recorded result but cannot independently
   prove how many times the external gate function executed.
2. An `INSUFFICIENT` gate result rejects `ReceiptOutput` construction and only
   permits a `FALLBACK_NO_UPDATE` pre-resolution disposition.
   Conversely, a `SUFFICIENT` gate result cannot produce
   `FALLBACK_NO_UPDATE` through the ordinary pre-resolution record.
3. Original OCR text and original correction candidates are frozen and are not
   overwritten by later alternatives.
4. Extracted fields require a value and at least one source OCR token.
5. Missing and unresolved fields contain no fabricated value or confidence and
   require an explanatory reason.
6. Structured field token references must exist in the associated source
   package.
7. Field IDs must be unique across all receipt-level and item-level fields in a
   `ReceiptOutput`.
8. An undetected purchase line does not produce an item row. Such a line is a
   false negative during evaluation, not runtime data reconstructed from ground
   truth.
9. Literal OCR text, structured item description, and optional
   `pantry_product_identity` are separate concepts.
10. Confidence is optional, finite, model-native evidence. No score range is
    imposed in Version 0 because upstream model scales have not been normalized.
    The contract does not create, calibrate, or interpret probabilities.
11. `ALTERNATIVE_ACCEPTED` requires a selected candidate that is present in the
    recorded alternatives. Original candidates remain immutable.
12. `OutputStage.PRE_REVIEW_AUTOMATIC` cannot be overridden on initial
    `ReceiptOutput`. Future human-reviewed or oracle-modified output requires a
    separate record with its own provenance, which is not implemented here.
13. Missing external retailer price evidence does not invalidate an extracted
    unit price.

## Policy and persistence states

`PreResolutionDisposition` permits `AUTO_RESOLVED`, `REVIEW_REQUIRED`,
`FALLBACK_NO_UPDATE`, or `FAILED` with the `PRE_RESOLUTION` stage. It is frozen
and remains attached to every later persistence event.

`PersistenceOutcome` separately permits `COMMITTED` or `FAILED` with the
`INVENTORY_PERSISTENCE` stage, but Contract Version 0 permits either event only
when the retained pre-resolution disposition is `AUTO_RESOLVED`.

`REVIEW_REQUIRED` cannot enter persistence until a future review-resolution
contract records an eligible actual `USER_CONFIRMED` or `USER_MODIFIED`
resolution. Those records are not implemented in Version 0, so direct
persistence from `REVIEW_REQUIRED` is rejected. No artificial confirmation flag
is used. `FALLBACK_NO_UPDATE` and `FAILED/PRE_RESOLUTION` are also ineligible for
inventory persistence.

A committed record requires a nonempty
inventory-write reference for structural completeness. The dataclass cannot
prove that the reference corresponds to a successful transaction. A future
persistence service must construct `COMMITTED` only after an actual database
write succeeds. This task implements no write.

## Compatibility impact of hardening

Task 1.2A keeps Contract Version 0 provisional but strengthens construction
rules. Code written against the initial draft must account for these changes:

- The mixed `ApplicationOutcome` record is replaced by
  `PreResolutionDisposition` and `PersistenceOutcome`.
- `ReceiptOutput.output_stage` is no longer an initializer argument.
- Insufficient source evidence, duplicate receipt field IDs, non-finite
  confidence, and inconsistent accepted-candidate records now raise
  `ValueError`.
- Accepted correction records now use `selected_alternative`.
- Persistence outcomes now reject frozen `REVIEW_REQUIRED`,
  `FALLBACK_NO_UPDATE`, and `FAILED/PRE_RESOLUTION` dispositions. This must be
  extended through an explicit review-resolution relationship when Tier B
  review records are introduced.

## Unresolved details for thesis review

- Canonical serialization format and compatibility policy beyond version 0.
- Domain types and normalization rules for dates, quantities and currency.
- Exact extraction and source-gate state transitions.
- Runtime orchestration that guarantees exactly one gate invocation.
- Confidence provenance, calibration, combination and thresholds.
- Candidate-generation, evidence weighting and correction policy.
- Human-review/oracle record types, provenance and audit metadata.
- Tier B `USER_CONFIRMED` and `USER_MODIFIED` resolution records and their
  explicit persistence-eligibility relationship.
- Persistence transaction identifiers and inventory schema integration.

The SROIE test partition was not used to design or test this contract. All unit
tests use synthetic records.
