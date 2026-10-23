# Tier A Reference Annotation Contract V0

Status: `PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`

## 1. Scope and source status

This contract is an evaluation-only representation of adjudicated receipt
reference truth for the Tier A workflow. It does not consume records from OCR,
B1, B2, B3, the proposed method, retailer price resources, user outcomes, or
model predictions. It does not execute derivation. It can record a separately
adjudicated unit-price derivation under a frozen annotation rule.

The moderated thesis PDF was not available in the Task 2.5A working copy or at
the external path recorded by `docs/proposed_method_traceability_v0.md`.
Consequently, the entries below marked `THESIS_REQUIRED_AS_SUPPLIED` trace the
requirements explicitly supplied in the approved Task 2.5A brief and the
existing thesis-verified repository documentation. Direct re-verification
against Sections 3.2.1-3.2.3, 3.3, and 3.7 remains required before an
evaluation freeze.

This module does not implement collection, annotation workflow, split
assignment, line-item alignment, metrics, statistics, model fitting, PT1/PT2,
or held-out evaluation.

## 2. Requirement traceability

| Requirement | Contract representation | Classification |
|---|---|---|
| Receipt-visible truth is independent of system predictions | No prediction or runtime-output type is accepted by any public reference record | `THESIS_REQUIRED_AS_SUPPLIED` |
| Seven common target fields | Contract V0 `ReceiptFieldName`; three receipt-level and four item-level roles | `THESIS_REQUIRED_AS_SUPPLIED`; reuse is `PROPOSED_DEVELOPMENT_CHOICE` |
| Preserve receipt, row, field role and source order | `TierAReferenceReceipt`, `ReferenceItemRow.source_order`, and `ReferenceField` links | `THESIS_REQUIRED_AS_SUPPLIED` |
| Explicit reference availability | `ReferenceAvailability.AVAILABLE` / `UNAVAILABLE` | `THESIS_REQUIRED_AS_SUPPLIED` |
| Unit price may be genuinely unavailable | Any item unit-price field may be `UNAVAILABLE` while other row fields remain available | `THESIS_REQUIRED_AS_SUPPLIED` |
| Unit price may be separately derivable under a frozen annotation rule | `ReferenceValueKind.ADJUDICATED_DERIVED`, with no claimed transcription and with rule/evidence references | `THESIS_REQUIRED_AS_SUPPLIED`; exact record shape is `PROPOSED_DEVELOPMENT_CHOICE` |
| Retailer-price absence does not determine truth availability | The reference contract contains no external-price input | `THESIS_REQUIRED_AS_SUPPLIED` |
| Original and normalized values remain separate | `ReferenceValue.original_transcription`, `normalized_value`, and `normalization_spec_version` | `THESIS_REQUIRED_AS_SUPPLIED` |
| Auditable annotation and adjudication | Versioned provenance event catalogues plus field event references | `THESIS_REQUIRED_AS_SUPPLIED`; exact event record design is `PROPOSED_DEVELOPMENT_CHOICE` |
| Draft truth cannot enter evaluation | `ReferenceRecordStatus.DRAFT` is rejected by evaluation-ready validation | `THESIS_REQUIRED_AS_SUPPLIED`; enum spelling is `PROPOSED_DEVELOPMENT_CHOICE` |
| Validation must not force receipt total to raw line sum | No arithmetic-equality structural invariant exists | `THESIS_REQUIRED_AS_SUPPLIED` |

## 3. Public data types and intended use

All records are frozen, slotted dataclasses. All stored collections are tuples.

- `ReferenceAvailability`: evaluator-side `AVAILABLE` or `UNAVAILABLE` state.
- `ReferenceValueKind`: literal transcription or adjudicated derived value.
- `ReferenceRecordStatus`: `DRAFT` or `FINALIZED` receipt lifecycle state.
- `QADiagnosticStatus`: `REVIEW_REQUIRED` or `RESOLVED` adjudication-QA state.
- `ReferenceValue`: literal transcription or explicit adjudicated derived value,
  plus optional versioned normalization.
- `AnnotationEventReference`: annotation event ID and stored source reference.
- `AdjudicationEventReference`: adjudication event ID and adjudicated source.
- `AnnotationProvenance`: schema/guideline versions and event catalogues.
- `ReferenceField`: one of the seven field roles, availability, row link, value,
  and provenance links.
- `ReferenceItemRow`: one ordered pantry-relevant row containing description,
  quantity, unit price, and line total.
- `ReferenceQADiagnostic`: a non-mutating adjudicator-review concern or its
  recorded resolution.
- `TierAReferenceReceipt`: receipt identity, source reference, provenance,
  store/date/total, ordered item rows, lifecycle state, and diagnostics.

`ReferenceValidationError`, `validate_reference_receipt()`,
`validate_evaluation_ready_receipt()`, and `validate_reference_collection()`
provide deterministic validation. `serialize_reference_receipt()` and
`serialize_reference_collection()` provide compact deterministic JSON.

`PROPOSED_DEVELOPMENT_CHOICE`: Schema version is the string `"0"`. Public class
and function names, enum spellings, tuple storage, and the module split are
development interfaces, not thesis-mandated names.

## 4. Field availability semantics

`AVAILABLE` means receipt evidence visibly supports an annotatable adjudicated
value. It requires `ReferenceValue` and forbids an unavailable reason.

`UNAVAILABLE` means the field is genuinely absent or not annotatable under the
declared protocol. It forbids a value and requires a reason. It does not mean a
system missed the field. It is not inferred from B1/B2/B3/PantryProof output or
from missing retailer/product-price evidence.

No value is inferred automatically from another field, line arithmetic, a
product resource, or a model. A unit price may be unavailable while description
and line total remain available. Alternatively, a human-adjudicated unit price
may be recorded as derived only when its frozen annotation rule and literal
same-row receipt-evidence field IDs are retained.

## 5. Identity, role, and linkage rules

A receipt has one stable de-identified `receipt_id` and one
`source_reference_id`. Each row ID is unique within the receipt. Each field ID
is unique within the receipt. Field receipt and row links must agree with their
container. Receipt-level fields cannot have row links; item-level fields must
link to their row. The three receipt slots and four row slots enforce the seven
roles.

`PROPOSED_DEVELOPMENT_CHOICE`: Identifiers use the ASCII grammar
`[A-Za-z0-9][A-Za-z0-9._:/-]*`. This validates identifier shape but cannot prove
that an identifier is de-identified; dataset governance must establish that.

`PROPOSED_DEVELOPMENT_CHOICE`: `source_order` is a non-negative integer, and the
stored item tuple must have unique, strictly increasing values. Validation does
not reorder rows.

## 6. Literal, derived, and normalized reference handling

For `LITERAL_TRANSCRIPTION`, `original_transcription` is mandatory and is stored
exactly as supplied, including spacing or source glyphs. Literal values cannot
contain derivation metadata.

For `ADJUDICATED_DERIVED`, `original_transcription` must be null so the derived
value cannot masquerade as printed receipt text. `derived_value`,
`derivation_rule_reference`, and one or more `derivation_evidence_field_ids` are
mandatory. V0 permits this mode only for unit price. Evidence IDs must resolve
to available literal fields on the same item row; derived values cannot be
chained. The containing field still requires annotation and adjudication event
provenance.

`normalized_value` remains optional and separate for either mode. When present
it requires a nonempty `normalization_spec_version`. A version without a
normalized value is rejected. `adjudicated_value` exposes the literal or derived
value without applying normalization.

`PROPOSED_DEVELOPMENT_CHOICE`: Exact monetary, quantity, and date reference
values are strings. This prevents binary floating-point coercion while leaving
the normalization grammar unresolved. Derived unit-price evidence is restricted
to known same-row literal fields and cannot be chained. V0 supplies no price-
derivation implementation, approved derivation formula, normalization algorithm,
currency quantization, date convention, or unit conversion.

## 7. Annotation and adjudication provenance

The receipt provenance records a schema version, annotation-guideline version,
annotation events, and adjudication events. Every field references a known
annotation event. Every finalized field also references a known adjudication
event. Event source references identify stored artifacts without embedding
those artifacts in this contract.

`PROPOSED_DEVELOPMENT_CHOICE`: Annotation and adjudication event IDs occupy
separate namespaces and cannot be the same value. Multiple events are supported
without claiming that they are independent annotations.

The presence of multiple people, checks, or events must not be interpreted as
independent double annotation. This schema does not establish the required 15%
independent double-annotation sample, selection stratification, agreement
metrics, adjudication route, ethical approval, adjudicator eligibility, consent,
or dataset eligibility.

## 8. Structural validation versus adjudication QA

Structural errors include duplicate or invalid identities, role/scope conflicts,
broken receipt/row/event links, contradictory availability/value state, and
incomplete finalized provenance. They raise `ReferenceValidationError` (or a
local construction `ValueError`/`TypeError`) and cannot be scored.

`ReferenceQADiagnostic` records a concern that requires human adjudication but
does not rewrite truth. A structurally valid draft may retain
`REVIEW_REQUIRED`; evaluation-ready validation rejects it. A resolved diagnostic
requires a known adjudication event and a resolution note. No diagnostic
auto-corrects any field.

Receipt total is deliberately not constrained to the unadjusted sum of line
totals because discounts, taxes, rounding, and adjustments may legitimately
explain a difference.

`PROPOSED_DEVELOPMENT_CHOICE`: The diagnostic record shape and the rule that an
unresolved diagnostic blocks `FINALIZED` status are development safeguards.
V0 does not automatically generate arithmetic or semantic diagnostics.

### 8.1 Finalization is not dataset eligibility

`FINALIZED` and `validate_evaluation_ready_receipt()` establish only that the
record is structurally complete, internally linked, fully adjudicated, and free
of unresolved QA diagnostics. The retained function name means ready for the
later eligibility screen; it does not certify Tier A eligibility.

`THESIS_REQUIRED_AS_SUPPLIED`: An eligible Tier A record must represent a
traceable grocery transaction with at least one pantry-relevant purchased line
whose identity and receipt membership are annotatable. Eligibility is governed
by a separately frozen checklist.

`PROPOSED_DEVELOPMENT_CHOICE`: V0 intentionally allows a finalized structural
record with zero item rows so structural finalization cannot silently substitute
for the future eligibility decision. No `tier_a_eligible` flag is exposed.

## 9. Deterministic serialization and synthetic tests

Dataclass field names are retained; enums become their string values; tuples
become JSON arrays; null remains JSON `null`; keys are sorted; and compact
separators are used. Item-row order is preserved. Collection serialization
sorts receipts by receipt ID.

`PROPOSED_DEVELOPMENT_CHOICE`: These canonical JSON rules and receipt sorting
are interoperability choices, not an annotation storage or database format.

Synthetic tests cover multiple rows, all seven roles, available/unavailable and
adjudicator-derived unit prices, unavailable receipt-level fields, duplicate
receipt/row/field IDs, role and linkage conflicts, value/availability
contradictions, literal versus normalized preservation, derivation provenance,
fabricated-transcription rejection, deterministic serialization, incomplete
drafts and finalized records, the finalization/eligibility distinction,
provenance contradictions, QA state, immutability, absence of prediction
constructors, and a valid promotional-total discrepancy. They do not measure
extraction accuracy, annotation agreement, or Tier A dataset eligibility.

## 10. Unresolved decisions and limitations

- Direct thesis verification is pending because the moderated PDF was not
  locally available during implementation.
- The annotation guideline content and version have not been approved here.
- No normalization specification or field-specific normalized grammar is fixed.
- The permitted unit-price derivation rule, operands, arithmetic convention,
  rounding, and annotation guideline have not been selected or implemented.
- Stable ID generation, de-identification procedure, annotation storage, actor
  pseudonymization, access control, and audit-log persistence remain unresolved.
- Dataset eligibility, consent/access, exclusion rules, contributor grouping,
  duplicate detection, the 60/20/20 split, and unseen-retailer criteria are not
  established by this schema.
- Independent double-annotation sampling, agreement calculations, adjudicator
  eligibility, and adjudication workflow remain outside V0.
- No line-item matcher, metric, bootstrap, calibration, risk computation,
  PT1/PT2 selection, model fitting, or held-out evaluation is implemented.
- The schema and shared Contract V0/V1 interfaces remain provisional and are
  not evaluation-frozen.
