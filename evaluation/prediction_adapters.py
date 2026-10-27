"""Read-only B1/B2/B3 adapters for offline prediction identity V0.

The adapters copy already-produced runtime predictions into the evaluation-only
``PredictionReceipt`` contract.  They do not run extraction, construct run
scope, join reference truth, infer row order, or interpret prediction values.
"""

from __future__ import annotations

from typing import TypeAlias

from evaluation.prediction_schema import (
    PredictionExecutionState,
    PredictionField,
    PredictionItemRow,
    PredictionProvenance,
    PredictionReceipt,
)
from pipeline.baseline_b1 import B1ExtractionResult
from pipeline.baseline_b3 import B3Result
from pipeline.contracts import (
    PolicyState,
    PreResolutionDisposition,
    ReceiptItemRow,
    ReceiptOutput,
    StructuredField,
)
from pipeline.layout_b2 import B2ExtractionResult


RowOrdinalDeclarations: TypeAlias = tuple[tuple[str, int], ...]


class PredictionAdapterError(ValueError):
    """Raised when a runtime result cannot be represented losslessly in V0."""


def _require_provenance(provenance: PredictionProvenance) -> None:
    if not isinstance(provenance, PredictionProvenance):
        raise TypeError("provenance must be PredictionProvenance.")


def _require_expected_version(expected_version: str | None) -> None:
    if expected_version is not None and (
        not isinstance(expected_version, str) or not expected_version.strip()
    ):
        raise PredictionAdapterError(
            "expected_version must be nonempty text when provided."
        )


def _verify_version(
    *,
    producer_name: str,
    actual_version: str,
    expected_version: str | None,
) -> None:
    _require_expected_version(expected_version)
    if expected_version is not None and actual_version != expected_version:
        raise PredictionAdapterError(
            f"{producer_name} version mismatch: expected {expected_version!r}, "
            f"found {actual_version!r}."
        )


def _require_state_detail(state_detail: str | None) -> str:
    if not isinstance(state_detail, str) or not state_detail.strip():
        raise PredictionAdapterError(
            "A fallback result requires caller-supplied nonempty state_detail."
        )
    return state_detail


def _validate_ordinal_declarations(
    rows: tuple[ReceiptItemRow, ...],
    declarations: RowOrdinalDeclarations,
) -> dict[str, int]:
    if not isinstance(declarations, tuple):
        raise TypeError("row_ordinals must be a tuple of (row_id, ordinal) tuples.")

    declared: dict[str, int] = {}
    used_ordinals: set[int] = set()
    for declaration in declarations:
        if not isinstance(declaration, tuple) or len(declaration) != 2:
            raise TypeError("Each row ordinal declaration must be a two-item tuple.")
        row_id, ordinal = declaration
        if not isinstance(row_id, str) or not row_id.strip():
            raise PredictionAdapterError("Declared row IDs must be nonempty text.")
        if row_id in declared:
            raise PredictionAdapterError(
                f"Duplicate ordinal declaration for runtime row {row_id!r}."
            )
        if isinstance(ordinal, bool) or not isinstance(ordinal, int):
            raise TypeError("Declared output ordinals must be integers, not booleans.")
        if ordinal < 0:
            raise PredictionAdapterError("Declared output ordinals must be non-negative.")
        if ordinal in used_ordinals:
            raise PredictionAdapterError(
                f"Duplicate declared output ordinal {ordinal!r}."
            )
        declared[row_id] = ordinal
        used_ordinals.add(ordinal)

    emitted_ids = {row.row_id for row in rows}
    declared_ids = set(declared)
    missing = emitted_ids - declared_ids
    extra = declared_ids - emitted_ids
    if missing:
        raise PredictionAdapterError(
            f"Missing ordinal declarations for runtime rows: {sorted(missing)!r}."
        )
    if extra:
        raise PredictionAdapterError(
            f"Ordinal declarations reference un-emitted rows: {sorted(extra)!r}."
        )
    return declared


def _adapt_field(field: StructuredField) -> PredictionField:
    if field.confidence is not None:
        raise PredictionAdapterError(
            f"Runtime field {field.field_id!r} has confidence that prediction "
            "identity V0 cannot represent."
        )
    return PredictionField(
        runtime_field_id=field.field_id,
        runtime_receipt_id=field.receipt_id,
        field_name=field.field_name,
        status=field.status,
        item_row_id=field.item_row_id,
        value=field.value,
        source_token_ids=field.source_token_ids,
        unresolved_reason=field.unresolved_reason,
    )


def _adapt_row(row: ReceiptItemRow, output_ordinal: int) -> PredictionItemRow:
    if row.pantry_product_identity is not None:
        raise PredictionAdapterError(
            f"Runtime row {row.row_id!r} has pantry_product_identity that "
            "prediction identity V0 cannot represent."
        )
    return PredictionItemRow(
        runtime_row_id=row.row_id,
        runtime_receipt_id=row.receipt_id,
        output_ordinal=output_ordinal,
        fields=tuple(_adapt_field(field) for field in row.fields),
    )


def _adapt_structured_output(
    output: ReceiptOutput,
    *,
    provenance: PredictionProvenance,
    row_ordinals: RowOrdinalDeclarations,
    state_detail: str | None,
) -> PredictionReceipt:
    if state_detail is not None:
        raise PredictionAdapterError(
            "Structured output must not receive fallback state_detail."
        )
    ordinal_by_row = _validate_ordinal_declarations(output.items, row_ordinals)
    return PredictionReceipt(
        runtime_receipt_id=output.receipt_id,
        structured_output_present=True,
        execution_state=PredictionExecutionState.STRUCTURED_OUTPUT,
        extraction_status=output.extraction_status,
        receipt_fields=tuple(
            _adapt_field(field)
            for field in (output.store_name, output.purchase_date, output.receipt_total)
        ),
        rows=tuple(
            _adapt_row(row, ordinal_by_row[row.row_id]) for row in output.items
        ),
        provenance=provenance,
    )


def _adapt_fallback(
    disposition: PreResolutionDisposition | None,
    *,
    provenance: PredictionProvenance,
    row_ordinals: RowOrdinalDeclarations,
    state_detail: str | None,
) -> PredictionReceipt:
    if disposition is None or disposition.state is not PolicyState.FALLBACK_NO_UPDATE:
        raise PredictionAdapterError(
            "An absent ReceiptOutput must have a genuine FALLBACK_NO_UPDATE disposition."
        )
    if row_ordinals:
        raise PredictionAdapterError(
            "A fallback result without emitted rows cannot accept row ordinals."
        )
    if not isinstance(row_ordinals, tuple):
        raise TypeError("row_ordinals must be a tuple of (row_id, ordinal) tuples.")
    return PredictionReceipt(
        runtime_receipt_id=disposition.gate_result.receipt_id,
        structured_output_present=False,
        execution_state=PredictionExecutionState.FALLBACK_NO_UPDATE,
        extraction_status=None,
        receipt_fields=(),
        rows=(),
        provenance=provenance,
        state_detail=_require_state_detail(state_detail),
    )


def _adapt_b1_or_b2_result(
    *,
    producer_name: str,
    output: ReceiptOutput | None,
    disposition: PreResolutionDisposition | None,
    provenance: PredictionProvenance,
    row_ordinals: RowOrdinalDeclarations,
    state_detail: str | None,
    expected_version: str | None,
) -> PredictionReceipt:
    _require_provenance(provenance)
    _require_expected_version(expected_version)
    if output is None:
        if expected_version is not None:
            raise PredictionAdapterError(
                f"A {producer_name} fallback artifact exposes no extractor version; "
                "the requested expected_version cannot be verified."
            )
        return _adapt_fallback(
            disposition,
            provenance=provenance,
            row_ordinals=row_ordinals,
            state_detail=state_detail,
        )

    _verify_version(
        producer_name=producer_name,
        actual_version=output.extractor_version,
        expected_version=expected_version,
    )
    return _adapt_structured_output(
        output,
        provenance=provenance,
        row_ordinals=row_ordinals,
        state_detail=state_detail,
    )


def adapt_b1_result_to_prediction_receipt(
    result: B1ExtractionResult,
    *,
    provenance: PredictionProvenance,
    row_ordinals: RowOrdinalDeclarations,
    state_detail: str | None = None,
    expected_version: str | None = None,
) -> PredictionReceipt:
    """Copy one B1 result into prediction identity V0 without interpretation."""

    if not isinstance(result, B1ExtractionResult):
        raise TypeError("result must be B1ExtractionResult.")
    return _adapt_b1_or_b2_result(
        producer_name="B1",
        output=result.receipt_output,
        disposition=result.pre_resolution_disposition,
        provenance=provenance,
        row_ordinals=row_ordinals,
        state_detail=state_detail,
        expected_version=expected_version,
    )


def adapt_b2_result_to_prediction_receipt(
    result: B2ExtractionResult,
    *,
    provenance: PredictionProvenance,
    row_ordinals: RowOrdinalDeclarations,
    state_detail: str | None = None,
    expected_version: str | None = None,
) -> PredictionReceipt:
    """Copy one B2 result into prediction identity V0 without interpretation."""

    if not isinstance(result, B2ExtractionResult):
        raise TypeError("result must be B2ExtractionResult.")
    return _adapt_b1_or_b2_result(
        producer_name="B2",
        output=result.receipt_output,
        disposition=result.pre_resolution_disposition,
        provenance=provenance,
        row_ordinals=row_ordinals,
        state_detail=state_detail,
        expected_version=expected_version,
    )


def adapt_b3_result_to_prediction_receipt(
    result: B3Result,
    *,
    provenance: PredictionProvenance,
    row_ordinals: RowOrdinalDeclarations,
    state_detail: str | None = None,
    expected_version: str | None = None,
) -> PredictionReceipt:
    """Copy final transformed B3 output into prediction identity V0."""

    if not isinstance(result, B3Result):
        raise TypeError("result must be B3Result.")
    _require_provenance(provenance)
    _verify_version(
        producer_name="B3",
        actual_version=result.ruleset_id,
        expected_version=expected_version,
    )
    if result.receipt_output is None:
        return _adapt_fallback(
            result.pre_resolution_disposition,
            provenance=provenance,
            row_ordinals=row_ordinals,
            state_detail=state_detail,
        )
    return _adapt_structured_output(
        result.receipt_output,
        provenance=provenance,
        row_ordinals=row_ordinals,
        state_detail=state_detail,
    )


__all__ = (
    "PredictionAdapterError",
    "RowOrdinalDeclarations",
    "adapt_b1_result_to_prediction_receipt",
    "adapt_b2_result_to_prediction_receipt",
    "adapt_b3_result_to_prediction_receipt",
)
