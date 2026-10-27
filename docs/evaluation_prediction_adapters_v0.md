# B1/B2/B3 Offline Prediction Adapters V0

Status: `PROVISIONAL_DEVELOPMENT — NOT EVALUATION_FROZEN`

## 1. Purpose and boundary

This module performs a read-only structural copy from an already-produced B1,
B2, or B3 result into one Task 2.5C1A `PredictionReceipt`. It preserves runtime
prediction identity, emitted field states, literal prediction values, and
ordered source-token references.

It does not run OCR or extraction, construct `EvaluationRunScope` or
`PredictionBundle`, join runtime receipts to Task 2.5A references, inspect
reference truth, derive row order, normalize values, align rows, select a
threshold, calculate a metric, or authorize dataset or held-out access.

The moderated thesis PDF was not present in the repository during this task.
This implementation follows the merged evaluation protocol, Task 2.5C1A
contract, actual runtime contracts, and the approved Task 2.5C1B specification;
direct PDF verification is not claimed.

## 2. Public interface

`evaluation.prediction_adapters` exports:

- `PredictionAdapterError`, a `ValueError` subclass for a runtime result that
  cannot be represented losslessly by prediction identity V0;
- `RowOrdinalDeclarations`, the immutable alias
  `tuple[tuple[str, int], ...]`;
- `adapt_b1_result_to_prediction_receipt()`;
- `adapt_b2_result_to_prediction_receipt()`; and
- `adapt_b3_result_to_prediction_receipt()`.

The three functions have the same keyword interface:

```python
adapt_..._result_to_prediction_receipt(
    result,
    *,
    provenance: PredictionProvenance,
    row_ordinals: RowOrdinalDeclarations,
    state_detail: str | None = None,
    expected_version: str | None = None,
) -> PredictionReceipt
```

Each function requires the corresponding concrete `B1ExtractionResult`,
`B2ExtractionResult`, or `B3Result`. The functions do not accept a reference
receipt identifier or an evaluation scope.

`PROPOSED_DEVELOPMENT_CHOICE`: The error type, ordinal declaration alias,
function names, keyword names, and optional exact-version assertion are
development interfaces, not thesis-prescribed names.

## 3. Producer-to-C1A mapping

### 3.1 Structured output

| Runtime source | C1A destination | Mapping |
| --- | --- | --- |
| `ReceiptOutput.receipt_id` | `PredictionReceipt.runtime_receipt_id` | Exact copy |
| Presence of `ReceiptOutput` | `structured_output_present` | `True` |
| Structured result | `execution_state` | `STRUCTURED_OUTPUT` |
| `ReceiptOutput.extraction_status` | `extraction_status` | Exact enum copy, including `FAILED` |
| Store, date, and receipt-total fields | `receipt_fields` | All three emitted runtime records copied |
| `ReceiptOutput.items` | `rows` | One prediction row per emitted runtime row |
| Caller provenance | `PredictionReceipt.provenance` | Exact supplied record |
| Structured result | `state_detail` | `None`; caller detail is rejected |

For every `StructuredField`, the adapter copies `field_id`, `receipt_id`,
`field_name`, `status`, `item_row_id`, `value`, `source_token_ids`, and
`unresolved_reason` without parsing or normalization. Ordered source-token IDs
are not sorted.

For every `ReceiptItemRow`, the adapter copies its runtime row and receipt IDs,
uses the caller-declared ordinal, and copies all four emitted item fields.
Missing and unresolved runtime fields remain explicit prediction fields. The
adapter does not fabricate fields that a producer did not emit.

Empty item tuples are valid. Equal item-description values do not merge rows;
the original row identities remain distinct.

### 3.2 B3 output

The B3 adapter consumes `B3Result.receipt_output`, which is the reconstructed
final B3 output. It therefore records final transformed B3 values, not the
values in `B3Result.original_b2_result`.

The existing `B3Result` and `B3FieldTransformation` contracts ensure that B3
preserves B2-origin receipt, row, field, role, status, association, order, and
source-token identities. The offline adapter creates no B3-specific row or
field IDs.

B3 rule events, candidate records, diagnostics, adjustments, and field-
transformation audit records are not prediction fields. The caller supplies a
`PredictionProvenance.source_record_reference` pointing to the separately
stored B3 artifact. That string is an audit pointer; this adapter neither
retrieves the artifact nor authenticates the reference.

## 4. Required external metadata

The caller must supply:

- a valid `PredictionProvenance` identifying the offline recording event and
  separately retained producer artifact;
- one explicit `(runtime_row_id, output_ordinal)` declaration for every
  structured-output row; and
- a nonempty `state_detail` for a fallback result.

Dataset, tier, partition, cohort, run, system, configuration, and output-stage
identity remain caller-owned `EvaluationRunScope` inputs. Bundle identity and
bundle provenance likewise remain external. The adapter does not infer any of
them from extractor names, receipt IDs, or comparator manifests.

## 5. Ordinal declaration contract

`PROPOSED_DEVELOPMENT_CHOICE`: Row ordinals are supplied as a tuple of pairs so
duplicate declarations remain observable before a mapping is constructed.

For structured output, validation requires exactly one declaration for every
emitted runtime row ID. It rejects:

- missing or extra row IDs;
- duplicate row-ID declarations;
- duplicate ordinal values;
- negative ordinals;
- booleans, non-integers, malformed pairs, or mutable outer collections.

Declared ordinals need not be contiguous and are stored unchanged. The adapter
does not enumerate `ReceiptOutput.items` and does not parse ordinal text from a
runtime row ID. `output_ordinal` is a non-semantic recording attribute; this
contract does not approve it as receipt source order or line-alignment order.

A structured receipt with no item rows requires an explicitly supplied empty
tuple. A fallback has no emitted rows and rejects nonempty declarations.

## 6. Fallback and execution-failure boundary

A no-output result is accepted only when its actual
`PreResolutionDisposition.state` is `FALLBACK_NO_UPDATE`. The adapter copies the
runtime receipt ID from the disposition's gate result and constructs:

- `structured_output_present=False`;
- `execution_state=FALLBACK_NO_UPDATE`;
- `extraction_status=None`;
- empty receipt-field and row tuples; and
- the exact nonempty caller-supplied `state_detail`.

The runtime gate-reason tuple is not stringified or normalized. A missing or
blank caller detail is rejected.

B1, B2, and B3 result contracts do not encode an execution-failure result.
These adapters therefore never create `EXECUTION_FAILED`. A structured
`ReceiptOutput` whose extraction status is `FAILED` remains structured output;
the extraction status is copied exactly.

## 7. Version verification

`expected_version` is an optional exact assertion, not freeze evidence:

- for structured B1 and B2, it is compared with
  `ReceiptOutput.extractor_version`;
- for B3, it is compared with `B3Result.ruleset_id`, which exists for both
  structured and fallback results; and
- B1/B2 fallback result envelopes do not carry the extractor version. If an
  expected version is requested for those artifacts, adaptation fails because
  the assertion cannot be verified from the artifact itself.

The adapters do not substitute imported module constants for missing
artifact-level evidence. Omitting `expected_version` means no caller-requested
version assertion was performed. Neither outcome authenticates a result,
freezes a comparator, or makes a provisional comparator manifest evaluation-
approved.

## 8. Unsupported metadata safeguards

Prediction identity V0 has no field-confidence or pantry-normalized product-
identity attribute. The current B1/B2 producers emit field confidence as
`None` and pantry identity as `None`; B3 preserves those values.

An encountered non-null `StructuredField.confidence` or
`ReceiptItemRow.pantry_product_identity` is rejected with
`PredictionAdapterError`. The adapter does not silently discard either value
and does not modify Task 2.5C1A to accommodate it.

The complete OCR source package, extractor audit internals, Contract V0
version, and B3 rule audit remain in the separately stored producer artifact.
This adapter records the prediction identity subset defined by C1A rather than
serving as a lossless serialization of the entire producer result.

## 9. Scope and serialization compatibility

Callers may place adapted receipts into existing `PredictionBundle` records
under explicit `EvaluationRunScope` values. Reused B2/B3 runtime receipt, row,
field, and token IDs remain valid because C1A namespaces them using the complete
scope. Identical runtime strings do not imply reference identity and do not
join a prediction to Task 2.5A.

The adapters use the existing C1A records and therefore inherit their
structural validation and canonical JSON serialization. No prediction-schema
or validation semantics are changed by Task 2.5C1B.

## 10. Synthetic verification coverage

Synthetic tests cover:

- valid structured B1, B2, and transformed B3 results;
- all seven roles where emitted and exact field-property copying;
- ordered source-token references;
- explicit missing and unresolved fields;
- empty item tuples and duplicate descriptions;
- B1/B2/B3 fallback state and explicit detail;
- malformed, missing, extra, duplicate, negative, boolean, and duplicate-value
  ordinal declarations;
- structured extraction status `FAILED`;
- B2/B3 identity reuse under distinct complete scopes;
- supported and unsupported artifact-level version assertions;
- rejection of non-null confidence and pantry identity;
- canonical C1A serialization; and
- absence of Task 2.5A reference imports or adapter parameters.

These tests demonstrate structural conversion behavior only. They do not claim
extraction accuracy, alignment quality, evaluation eligibility, authentic
provenance, comparator freeze, or empirical results.

## 11. Pending decisions and limitations

### Tai confirmation

- Whether recorded `ReceiptOutput.items` tuple position may eventually supply
  `output_ordinal`; V0 continues to require explicit declarations.
- The frozen meanings and naming of B1/B2/B3 `system_id` and
  `configuration_id` values used by external run scopes.
- Future execution-failure capture and provenance outside producer result
  envelopes.
- Any future C1A treatment of non-null runtime confidence or pantry product
  identity. V0 fails closed.

### Leng confirmation

- The complete proposed-method evaluation artifact, final prediction value and
  status, configuration identity, permanent B2 `c0`, receipt disposition, and
  treatment of non-method-ready missing/unresolved fields.
- Proposed-method adapters remain separate and are not implemented here.

### Shared methodology or contract review

- Runtime-to-reference receipt-link records and namespace rules.
- Whether a recorded output ordinal becomes an approved alignment-order input.
- Alignment normalization, matching objective, threshold grid, and masked
  development-label schema.
- Comparator, configuration, resource, dataset, and methodology freeze
  authority and evidence.

No pending decision is silently resolved by these adapters.
