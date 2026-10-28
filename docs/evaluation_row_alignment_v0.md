# Offline Row-Alignment Link Contract V0

Status: `PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`

This synthetic-only contract implements the row-link representation and
structural validation authorized by `SCH-JA-05` and `SCH-JA-06` in
`docs/evaluation_decision_log.md`. It records declared alignment outcomes. It
does not run a matcher, prove that a declared match is correct, authenticate a
receipt join, compute a metric, or authorize evaluation.

## 1. Authority and traceability

### `THESIS_TRACED_REQUIREMENT`

The proposed evaluation protocol traces thesis requirements for independent
prediction/reference identities, complete representation of matched and
unmatched rows, one-to-one row association, deterministic evaluation inputs,
and separation of runtime state from offline evaluation state. Direct thesis
re-verification is not claimed by this document.

### `APPROVED_EVALUATION_SCHEMA_DECISION`

- `SCH-JA-05` approves separate `COMPLETED`, `BLOCKED`, and `NOT_EXECUTED`
  alignment states; `MATCHED`, `REFERENCE_ONLY`, and `PREDICTION_ONLY` row-link
  outcomes; complete one-to-one row coverage for completed records; and
  link-free blocked/unexecuted records with reason and provenance.
- `SCH-JA-06` approves immutable, versioned row-link records and deterministic
  identity-based serialization whose order is representational only.

Both decisions are recorded under approval envelope
`EVAL-APP-2026-10-27-C2B-01`. Their implementation remains unaccepted pending
independent review.

### `PROPOSED_DEVELOPMENT_CHOICE`

The exact Python class names, field decomposition, exception type, opaque
alignment-configuration reference, execution-reference field, provenance
shape, collection conflict key, and canonical JSON sort keys are provisional
development choices. They are not asserted to appear verbatim in the thesis.

## 2. Existing identities consumed

The contract uses existing identities without modifying their source records:

- reference receipt: `TierAReferenceReceipt.receipt_id`;
- reference row: `ReferenceItemRow.row_id`, scoped by its `receipt_id`;
- reference audit order: `ReferenceItemRow.source_order`;
- prediction receipt: `PredictionReceipt.runtime_receipt_id` inside one
  `PredictionBundle.scope`;
- prediction row: `PredictionItemRow.runtime_row_id`, scoped by its
  `runtime_receipt_id`;
- prediction recording ordinal: `PredictionItemRow.output_ordinal`;
- receipt association: `ReceiptJoinEntry` inside one `ReceiptJoinSet`; and
- immutable source context: manifest/dataset versions, prediction bundle,
  complete `EvaluationRunScope`, join-set identity/version, and revision ID.

Prediction and reference receipt IDs remain separate namespaces. Prediction
and reference row IDs remain separate subordinate namespaces even when their
text is equal. A row ID is never generated from tuple position, description
text, filename, ordinal, or another side's identity.

`output_ordinal` and `source_order` are copied and checked only as audit data.
They are not row identities, matching evidence, a shared order, matcher
execution order, or approved tie-breaking input.

## 3. Public schema

All records are frozen, slotted dataclasses and use schema version `"0"`.

### Enums

- `RowAlignmentExecutionStatus`: `COMPLETED`, `BLOCKED`, `NOT_EXECUTED`.
- `RowLinkOutcome`: `MATCHED`, `REFERENCE_ONLY`, `PREDICTION_ONLY`.

Execution status and row-link outcome are independent dimensions. A link
outcome never represents whether a matcher executed.

### `RowAlignmentProvenance`

Records a synthetic event ID, process version, immutable source references,
actor reference, optional recorded time, and schema version. These values are
audit pointers and do not prove that software ran or that an actor was
authorized.

### `PredictionReferenceRowLink`

Records:

- stable `row_link_id`;
- one `RowLinkOutcome`;
- nullable prediction receipt/row identities and copied output ordinal;
- nullable reference receipt/row identities and copied source order;
- the containing alignment provenance event ID;
- unmatched reason where applicable; and
- schema version.

Required shapes are:

| Outcome | Prediction side | Reference side | Unmatched reason |
| --- | --- | --- | --- |
| `MATCHED` | exactly one receipt/row/ordinal | exactly one receipt/row/source order | prohibited |
| `REFERENCE_ONLY` | prohibited | exactly one receipt/row/source order | required |
| `PREDICTION_ONLY` | exactly one receipt/row/ordinal | prohibited | required |

A structurally valid `MATCHED` record asserts only that the supplied result
declares a pair. It does not establish methodological correctness.

### `ReceiptRowAlignment`

Records one receipt-join entry's alignment status:

- alignment ID and version;
- manifest and dataset versions;
- prediction bundle and complete `EvaluationRunScope`;
- join-set ID/version/revision and join-entry ID;
- opaque alignment-configuration reference;
- execution status;
- row-link tuple;
- provenance;
- completed execution reference or blocked/unexecuted reason; and
- schema version.

For `COMPLETED`, an explicit synthetic `execution_reference` is required and a
status reason is prohibited. The row-link tuple may be empty only when both
applicable source row inventories are empty. For `BLOCKED` or `NOT_EXECUTED`,
the reason is required, execution reference is prohibited, and the row-link
tuple must be empty.

These records represent states, not automatic state transitions. The schema
does not change one state into another or infer completion from source data.

## 4. Source binding and receipt outcomes

`validate_row_alignment()` requires the exact `ReceiptJoinSet`,
`EvaluationManifest`, `PredictionBundle`, and reference-receipt collection.
It first validates the receipt join structurally, then requires exact equality
of every copied source-scope and revision identifier.

The named join entry controls applicable receipt sides:

- `JOINED`: both source receipts resolve. Completed records may contain all
  three row-link outcomes, subject to exact coverage.
- receipt-level `REFERENCE_ONLY`: no prediction receipt or row identity may be
  fabricated. A completed record covers every reference row with row-level
  `REFERENCE_ONLY` links.
- receipt-level `PREDICTION_ONLY`: no reference receipt or row identity may be
  fabricated. A completed record covers every prediction row with row-level
  `PREDICTION_ONLY` links.

A genuine joined fallback or execution-failure prediction receipt has a real
runtime receipt identity but no prediction rows. If an alignment is explicitly
recorded as completed, its reference rows are covered as `REFERENCE_ONLY`.
A fallback alone never establishes completion. A structured output with zero
rows is governed by the same explicit-status rule.

The structural validator does not call the receipt-join readiness validator
and does not represent a structurally valid or unverified receipt association
as authenticated. Any future evaluation consumer requiring verified joins
must separately pass the existing claim-bound receipt-join trust boundary.

## 5. Validation invariants

### Completed alignments

Validation requires:

- every row-link ID is unique;
- every prediction row resolves under the join entry's runtime receipt;
- every reference row resolves under the join entry's reference receipt;
- copied ordinal/source-order values equal their source records;
- each applicable prediction row participates exactly once;
- each applicable reference row participates exactly once;
- duplicate, split, merged, many-to-one, cross-receipt, unknown, missing, and
  extra row use is rejected;
- each link references the alignment provenance event; and
- `MATCHED` is impossible when either receipt side is absent.

Completed alignment may consist entirely of unmatched row links. No rule
infers that a declared pair is correct from identity presence or text equality.

### Blocked and unexecuted alignments

Both states require explicit reason and provenance and contain no canonical row
links or execution reference. Their immutable source-scope and join-entry
references preserve access to the available source row inventories without
copying or fabricating rows.

No status assigns false negatives, system failures, exclusions, metric
denominators, precision, recall, or F1.

### Defensive consumption validation

Public validators replay constructor invariants for the alignment record,
complete prediction scope, provenance, and every nested row link. Reflective
post-construction mutation of frozen records therefore fails closed under
`RowAlignmentValidationError`.

`validate_row_alignment()` is deliberately the individual/partial-development
boundary. It validates one supplied record and its row coverage without
requiring records for other receipt-join entries.

`validate_row_alignment_collection()` is the canonical complete-collection
boundary. It first validates the supplied receipt join even when the alignment
tuple is empty, then requires exactly one `ReceiptRowAlignment` for every
`ReceiptJoinEntry` in that join-set revision. Empty or incomplete collections,
unknown join entries, duplicate entry coverage, duplicate alignment
ID/version keys, and multiple records occupying the same complete source
scope and join-entry key fail closed.

Every record in one complete collection must carry the same
`alignment_configuration_reference`, including `BLOCKED` and `NOT_EXECUTED`
records. The reference identifies the declared or intended common alignment
context only. Its contents are not interpreted, it is not a configuration
freeze, and it remains separate from the prediction run's `configuration_id`.

A receipt whose alignment did not run is not inferred from absence: the
collection must contain an explicit `NOT_EXECUTED` record with reason and
provenance. A blocked receipt likewise requires an explicit `BLOCKED` record.
No links or execution claims are fabricated to make the collection complete.

Exact collection-envelope mechanics and the uniform opaque-configuration rule
are `PROPOSED_DEVELOPMENT_CHOICE` implementations of the approved complete
coverage and common-context decisions. V0 defines no alignment revision
lineage; competing versions for one complete key therefore fail closed rather
than silently replacing history.

## 6. Deterministic serialization

- `serialize_row_alignment()` validates and serializes one record.
- `serialize_row_alignment_collection()` validates a complete, uniformly
  configured receipt-join-entry collection and serializes it independently of
  input tuple order.

JSON object keys are sorted. Row links are sorted by outcome, null-safe runtime
receipt/row IDs, null-safe reference receipt/row IDs, and link ID. Collections
are sorted by manifest, dataset, complete prediction scope, bundle, join-set
revision, join entry, and alignment identity/version.

This order is `PROPOSED_DEVELOPMENT_CHOICE` and strictly representational. It
must not be interpreted as receipt source order, prediction order, reference
order, matcher execution order, tie-breaking, or inferred association.
Serialization preserves null-side distinctions, statuses, reasons,
provenance, copied audit order values, and schema versions. It creates no rows
or links.

## 7. Synthetic test boundary

Synthetic fixtures cover all row outcomes and execution statuses; exact
coverage; duplicate, missing, unknown, cross-receipt and cross-scope rows;
separate namespaces; all-unmatched completion; zero-row structured output;
fallback and missing prediction receipts; prohibited links and missing reasons;
reflective mutation; deterministic serialization; non-semantic audit ordering;
empty/incomplete collection rejection; explicit completed, blocked, and
unexecuted collection coverage; uniform configuration identity; and
conflicting complete-scope records.

Structural collection completeness does not prove that a matcher executed,
that any row pair is correct, that a configuration is frozen, or that the
records are eligible for evaluation.

The tests use no images, real receipts, datasets, external verification,
internet access, matcher, normalization, distance calculation, threshold, or
metric.

## 8. Pending decisions and explicit exclusions

The following are `PENDING_APPROVAL` and are not implemented:

- normalization profile and product-significant punctuation;
- distance definition and representation;
- actual matcher algorithm and candidate generation;
- monotonic source-order semantics;
- duplicate-description assignment and total tie-breaking;
- missing/unresolved description methodology;
- matcher configuration contents and freeze authority;
- threshold grid, selection, masking, and training-only development workflow;
- match-evidence schema beyond the opaque external configuration/execution
  references;
- alignment revision-lineage policy;
- proposed-method adaptation;
- metric and exclusion-ledger denominator effects;
- real receipt association/authentication, datasets, validation, and held-out
  execution; and
- independent implementation acceptance.

No runtime, reference, manifest, prediction, receipt-join, decision-log, or
Leng-owned contract is changed by this implementation.
