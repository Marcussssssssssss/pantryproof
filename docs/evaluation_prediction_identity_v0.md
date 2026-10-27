# Offline Prediction Identity Contracts V0

Status: `PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`

## 1. Purpose and boundary

This contract records immutable offline identities and declared states for
already-produced predictions. It exists before prediction-to-reference joining
or receipt-line alignment and contains no reference truth.

It does not run OCR or extraction, convert B1/B2/B3 outputs, adapt proposed
method decisions, join runtime receipts to Task 2.5A receipts, normalize text,
match rows, choose thresholds, score predictions, compute metrics, or authorize
dataset or held-out access.

The moderated thesis PDF was not available in the repository during the
preceding Task 2.5C0 audit. Requirements described here are reconciled against
the supplied evaluation protocol and merged contracts; direct PDF verification
is not claimed.

## 2. Relationship to existing contracts

### 2.1 Confirmed runtime behavior

- Contract V0 `ReceiptOutput` carries one runtime `receipt_id`, an ordered item
  tuple, three receipt-level fields, extraction status, extractor version,
  source evidence, and an output stage.
- `ReceiptItemRow` and `StructuredField` preserve runtime row, field, receipt,
  role, status, literal value, item-row association, and source-token identity.
- A Contract V0 extracted field has a nonempty value and source-token evidence.
  Missing and unresolved fields carry no value and retain a reason.
- B1 and B2 create different row and field IDs. B3 deliberately preserves B2
  receipt, row, field, role, order, status, and source-reference identities.
- The B2-to-proposed adapter retains exact B2 fields and values as permanent
  `c0`, while non-extracted B2 field IDs remain separately recorded.
- Current runtime item position is represented by tuple order. No runtime
  contract names that position authoritative receipt source order.

This module reuses `ReceiptFieldName`, `FieldStatus`,
`ReceiptExtractionStatus`, and `OutputStage`. It does not alter their runtime
meaning.

### 2.2 Task 2.5A and Task 2.5B

Task 2.5A owns independent reference receipt, row, field, value, availability,
and annotation provenance. None of those records is imported or copied into
the prediction schema.

Task 2.5B owns dataset, partition, cohort, membership, grouping, and alignment-
subset declarations. An optional manifest cross-check validates only prediction
scope dataset/tier and the existence of declared partition/cohort identities.
It does not compare a runtime receipt ID with manifest receipt membership,
because no approved runtime-to-reference receipt join exists.

## 3. Public records

All records are frozen, slotted dataclasses with schema version `"0"`.

- `PredictionExecutionState`: declares `STRUCTURED_OUTPUT`,
  `FALLBACK_NO_UPDATE`, or `EXECUTION_FAILED` for this offline envelope. It is
  not a replacement for runtime policy or failure-stage contracts.
- `PredictionProvenance`: recording event, source-record reference, recorder
  version, and optional recorded timestamp.
- `EvaluationRunScope`: dataset, tier, partition, cohort, run, system,
  configuration, and output-stage identity. `identity_key` returns that complete
  namespace.
- `PredictionField`: original runtime field ID, runtime receipt ID, field role,
  status, optional row association, literal value, ordered source-token IDs, and
  missing/unresolved reason.
- `PredictionItemRow`: original runtime row ID, runtime receipt ID, explicitly
  supplied output ordinal, and the fields actually recorded for that row.
- `PredictionReceipt`: runtime receipt ID, structured-output presence,
  execution state, optional extraction status, emitted receipt fields and rows,
  provenance, and optional fallback/failure detail.
- `PredictionBundle`: one run scope and its receipt predictions.

Public functions are:

- `validate_prediction_bundle()`;
- `validate_prediction_collection()`;
- `serialize_prediction_bundle()`; and
- `serialize_prediction_collection()`.

`PROPOSED_DEVELOPMENT_CHOICE`: The names, decomposition, schema version,
offline identifier grammar, execution-state enum, provenance fields, complete
scope-key order, and JSON representation are provisional development choices.

## 4. Identity namespaces

Runtime receipt, row, field, and token IDs are opaque source identities. V0
checks only the Contract V0 guarantee that they are nonempty; it does not parse
them or force them into the stricter offline identifier grammar. Unicode or
otherwise opaque runtime IDs are preserved unchanged.

A prediction receipt key is the complete `EvaluationRunScope.identity_key`
plus `runtime_receipt_id`. Row and field identities are subordinate to that
receipt. Therefore the same B2 field ID may legitimately appear for B3, or in
another run, configuration, or output stage. Reuse inside an identical complete
scope is rejected.

No runtime ID is assumed equal to a Task 2.5A reference ID. Coincident strings
remain identities in different namespaces until a separately approved offline
join says otherwise.

`PROPOSED_DEVELOPMENT_CHOICE`: `output_ordinal` is a unique, non-negative
integer within one emitted receipt. It may later be populated from recorded
output tuple position. It is deliberately not called source order, and V0 does
not parse an ordinal from a row-ID string or require contiguous values.

## 5. Missing, unresolved, absent, and fallback distinctions

- An emitted `MISSING` or `UNRESOLVED` field is present in `PredictionField`,
  has `value=None`, and retains its declared reason.
- A field not emitted by a producer has no `PredictionField` record. Validation
  and serialization do not synthesize one.
- A structured receipt may therefore contain only the fields actually supplied
  to this offline contract. V0 does not claim producer completeness.
- A receipt with no structured output has empty field and row tuples, no
  extraction status, an explicit fallback or execution-failure state, and a
  nonempty state detail.

Absent structured output is not reference unavailability. This contract has no
reference-availability input.

## 6. Structural validation

Validation rejects:

- malformed offline scope/provenance IDs or empty runtime IDs;
- duplicate receipt keys within one scope;
- duplicate complete receipt keys across bundles;
- duplicate row IDs, output ordinals, field IDs, or field roles in their
  applicable receipt/row scope;
- receipt, row, field, or field-role linkage conflicts;
- extracted fields without literal values or source-token references;
- missing/unresolved fields with values or without reasons;
- structured-output records with fallback/failure state or no extraction
  status; and
- no-output records containing rows, fields, or an extraction status.

When a Task 2.5B manifest is supplied, validation rejects dataset/tier conflicts
and unknown partition or cohort IDs. It intentionally does not inspect manifest
receipt membership and makes no correctness comparison against Task 2.5A.

Structural success does not prove that a producer emitted a complete runtime
receipt, that provenance is authentic, that a configuration is frozen, or that
the bundle is eligible for alignment or evaluation.

## 7. Deterministic serialization

Serialization validates first, preserves nulls and enum values, sorts object
keys, orders bundles by complete scope and bundle identity, orders receipts by
runtime receipt ID, rows by supplied ordinal then runtime row ID, and fields by
role then runtime field ID. Ordered source-token references are not reordered.

Canonical serialization introduces no missing field, row, receipt, source,
confidence, prediction, reference, or correctness value.

## 8. Synthetic coverage

Synthetic tests cover valid structured, fallback, and execution-failure
records; missing and unresolved fields; absent emitted fields; B2/B3 source-ID
reuse; run/configuration/stage scoping; duplicate complete and subordinate keys;
receipt/row/field linkage; field roles; output ordinals; opaque Unicode runtime
IDs; manifest dataset/partition/cohort checks without receipt-ID equality;
immutability; schema versions; and deterministic serialization with preserved
nulls.

The tests do not claim extraction accuracy, runtime completeness, alignment
quality, annotation agreement, dataset eligibility, or held-out readiness.

## 9. Pending decisions

### Tai confirmation

- Whether runtime receipt IDs equal reference/manifest receipt IDs or require an
  explicit join.
- Whether `ReceiptOutput.items` tuple position becomes the approved prediction
  order consumed by alignment.
- Exact B1/B2/B3 adapter completeness and fallback mapping.
- Comparator implementation/configuration freeze evidence.

### Leng confirmation

- The complete proposed-method evaluation bundle, including original B2
  structure, `FieldDecisionV1` completeness, configuration identity, permanent
  `c0`, and receipt disposition.
- Treatment of B2 missing/unresolved fields that are not method-ready.

### Shared methodology approval

- Runtime-to-reference receipt-link records and namespace rules.
- Prediction-to-reference alignment-link schema.
- Description normalization and significant-punctuation policy.
- Normalized Levenshtein definition, global matching objective, tie completion,
  malformed-description treatment, threshold grid, and masked-label schema.

Actual adapters, joining, matching, threshold selection, metrics, dataset use,
and held-out execution remain outside Task 2.5C1A.
