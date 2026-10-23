"""Structural/finalization validation for Tier A reference records.

Passing these validators does not establish dataset or Tier A evaluation
eligibility. Eligibility is a separate, frozen-checklist decision outside V0.
"""

from __future__ import annotations

from pipeline.contracts import ReceiptFieldName

from evaluation.reference_schema import (
    ITEM_LEVEL_FIELD_NAMES,
    RECEIPT_LEVEL_FIELD_NAMES,
    REFERENCE_SCHEMA_VERSION,
    AnnotationProvenance,
    QADiagnosticStatus,
    ReferenceField,
    ReferenceItemRow,
    ReferenceRecordStatus,
    ReferenceValueKind,
    TierAReferenceReceipt,
)


class ReferenceValidationError(ValueError):
    """Raised when reference truth is structurally invalid or not ready."""


def _fail(message: str) -> None:
    raise ReferenceValidationError(message)


def _validate_field_scope(
    field: ReferenceField,
    *,
    expected_name: ReceiptFieldName,
    receipt_id: str,
    row_id: str | None,
) -> None:
    if field.field_name is not expected_name:
        _fail(
            f"Field {field.field_id!r} has conflicting role {field.field_name.value}; "
            f"expected {expected_name.value}."
        )
    if field.receipt_id != receipt_id:
        _fail(f"Field {field.field_id!r} is linked to another receipt.")
    if row_id is None:
        if field.field_name not in RECEIPT_LEVEL_FIELD_NAMES:
            _fail(f"Item-level field {field.field_id!r} is represented at receipt level.")
        if field.item_row_id is not None:
            _fail(
                f"Receipt-level field {field.field_id!r} must not reference an item row."
            )
    else:
        if field.field_name not in ITEM_LEVEL_FIELD_NAMES:
            _fail(f"Receipt-level field {field.field_id!r} is attached to an item row.")
        if field.item_row_id != row_id:
            _fail(
                f"Field {field.field_id!r} points to nonexistent or incorrect row "
                f"{field.item_row_id!r}; expected {row_id!r}."
            )


def _validate_item_row(row: ReferenceItemRow, receipt_id: str) -> None:
    if row.receipt_id != receipt_id:
        _fail(f"Item row {row.row_id!r} is linked to another receipt.")
    expected = (
        (row.description, ReceiptFieldName.ITEM_DESCRIPTION),
        (row.quantity, ReceiptFieldName.QUANTITY),
        (row.unit_price, ReceiptFieldName.UNIT_PRICE),
        (row.line_total, ReceiptFieldName.LINE_TOTAL),
    )
    for field, expected_name in expected:
        _validate_field_scope(
            field,
            expected_name=expected_name,
            receipt_id=receipt_id,
            row_id=row.row_id,
        )


def _validate_provenance_links(
    receipt: TierAReferenceReceipt,
    provenance: AnnotationProvenance,
    *,
    require_evaluation_ready: bool,
) -> None:
    if provenance.schema_version != receipt.schema_version:
        _fail("Receipt and provenance schema versions conflict.")
    if provenance.schema_version != REFERENCE_SCHEMA_VERSION:
        _fail("Unsupported annotation provenance schema version.")

    annotation_ids = {event.event_id for event in provenance.annotation_events}
    adjudication_ids = {event.event_id for event in provenance.adjudication_events}
    if not annotation_ids:
        _fail("Annotation provenance must contain at least one annotation event.")

    for field in receipt.all_fields:
        if field.annotation_event_id not in annotation_ids:
            _fail(
                f"Field {field.field_id!r} references an unknown annotation event."
            )
        if field.adjudication_event_id is not None:
            if field.adjudication_event_id not in adjudication_ids:
                _fail(
                    f"Field {field.field_id!r} references an unknown adjudication event."
                )
        elif require_evaluation_ready:
            _fail(
                f"Finalized field {field.field_id!r} lacks adjudication provenance."
            )

    if require_evaluation_ready and not adjudication_ids:
        _fail("Finalized reference truth requires an adjudication event.")


def _validate_diagnostics(
    receipt: TierAReferenceReceipt, *, require_evaluation_ready: bool
) -> None:
    known_field_ids = {field.field_id for field in receipt.all_fields}
    adjudication_ids = {
        event.event_id for event in receipt.provenance.adjudication_events
    }
    seen: set[str] = set()
    for diagnostic in receipt.qa_diagnostics:
        if diagnostic.diagnostic_id in seen:
            _fail(f"Duplicate QA diagnostic ID {diagnostic.diagnostic_id!r}.")
        seen.add(diagnostic.diagnostic_id)
        if diagnostic.receipt_id != receipt.receipt_id:
            _fail(
                f"QA diagnostic {diagnostic.diagnostic_id!r} belongs to another receipt."
            )
        unknown_fields = set(diagnostic.related_field_ids) - known_field_ids
        if unknown_fields:
            _fail(
                f"QA diagnostic {diagnostic.diagnostic_id!r} references unknown fields: "
                f"{sorted(unknown_fields)}."
            )
        if diagnostic.status is QADiagnosticStatus.RESOLVED:
            if diagnostic.resolution_adjudication_event_id not in adjudication_ids:
                _fail(
                    f"Resolved QA diagnostic {diagnostic.diagnostic_id!r} lacks a "
                    "known adjudication event."
                )
        elif require_evaluation_ready:
            _fail(
                f"Finalized reference truth has unresolved QA diagnostic "
                f"{diagnostic.diagnostic_id!r}."
            )


def _validate_derived_values(receipt: TierAReferenceReceipt) -> None:
    fields_by_id = {field.field_id: field for field in receipt.all_fields}
    for field in receipt.all_fields:
        value = field.value
        if value is None or value.value_kind is not ReferenceValueKind.ADJUDICATED_DERIVED:
            continue

        if field.field_name is not ReceiptFieldName.UNIT_PRICE:
            _fail(
                f"Derived field {field.field_id!r} is not a unit-price reference."
            )
        for evidence_field_id in value.derivation_evidence_field_ids:
            evidence = fields_by_id.get(evidence_field_id)
            if evidence is None:
                _fail(
                    f"Derived field {field.field_id!r} references unknown receipt "
                    f"evidence {evidence_field_id!r}."
                )
            if evidence.item_row_id != field.item_row_id:
                _fail(
                    f"Derived field {field.field_id!r} references evidence outside "
                    "its item row."
                )
            if evidence.value is None or (
                evidence.value.value_kind
                is not ReferenceValueKind.LITERAL_TRANSCRIPTION
            ):
                _fail(
                    f"Derived field {field.field_id!r} requires available literal "
                    "receipt evidence."
                )


def validate_reference_receipt(
    receipt: TierAReferenceReceipt,
    *,
    require_evaluation_ready: bool = False,
) -> None:
    """Validate structure/provenance without deciding Tier A eligibility."""

    if not isinstance(receipt, TierAReferenceReceipt):
        raise TypeError("receipt must be a TierAReferenceReceipt.")
    if require_evaluation_ready and receipt.status is not ReferenceRecordStatus.FINALIZED:
        _fail("Draft reference truth is not evaluation-ready.")

    top_level = (
        (receipt.store_name, ReceiptFieldName.STORE_NAME),
        (receipt.purchase_date, ReceiptFieldName.PURCHASE_DATE),
        (receipt.receipt_total, ReceiptFieldName.RECEIPT_TOTAL),
    )
    for field, expected_name in top_level:
        _validate_field_scope(
            field,
            expected_name=expected_name,
            receipt_id=receipt.receipt_id,
            row_id=None,
        )

    row_ids: set[str] = set()
    prior_source_order = -1
    for row in receipt.items:
        if row.row_id in row_ids:
            _fail(f"Duplicate item-row ID {row.row_id!r} within receipt.")
        row_ids.add(row.row_id)
        if row.source_order <= prior_source_order:
            _fail("Item rows must have unique, strictly increasing source_order values.")
        prior_source_order = row.source_order
        _validate_item_row(row, receipt.receipt_id)

    field_roles: dict[str, ReceiptFieldName] = {}
    for field in receipt.all_fields:
        prior_role = field_roles.get(field.field_id)
        if prior_role is not None:
            if prior_role is not field.field_name:
                _fail(
                    f"Duplicate field identity {field.field_id!r} has conflicting "
                    "field roles."
                )
            _fail(f"Duplicate field identity {field.field_id!r} within receipt.")
        field_roles[field.field_id] = field.field_name

    _validate_provenance_links(
        receipt,
        receipt.provenance,
        require_evaluation_ready=require_evaluation_ready,
    )
    _validate_derived_values(receipt)
    _validate_diagnostics(
        receipt, require_evaluation_ready=require_evaluation_ready
    )


def validate_evaluation_ready_receipt(receipt: TierAReferenceReceipt) -> None:
    """Require finalized structure, not dataset/Tier A eligibility.

    The retained public name means ready for a later eligibility screen and
    evaluation infrastructure. It does not certify the receipt against the
    separately frozen dataset-eligibility checklist.
    """

    validate_reference_receipt(receipt, require_evaluation_ready=True)


def validate_reference_collection(
    receipts: tuple[TierAReferenceReceipt, ...],
    *,
    require_evaluation_ready: bool = True,
) -> None:
    """Validate uniqueness/structure, not dataset or partition eligibility."""

    if not isinstance(receipts, tuple):
        raise TypeError("receipts must be a tuple.")
    seen: set[str] = set()
    for receipt in receipts:
        if not isinstance(receipt, TierAReferenceReceipt):
            raise TypeError("receipts contains a non-reference-receipt value.")
        if receipt.receipt_id in seen:
            _fail(f"Duplicate receipt ID {receipt.receipt_id!r} in collection.")
        seen.add(receipt.receipt_id)
        validate_reference_receipt(
            receipt, require_evaluation_ready=require_evaluation_ready
        )
