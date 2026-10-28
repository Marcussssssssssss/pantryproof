"""Structural validation for synthetic-only row-alignment link records."""

from __future__ import annotations

from evaluation.manifest_schema import EvaluationManifest
from evaluation.prediction_schema import (
    EvaluationRunScope,
    PredictionBundle,
    PredictionReceipt,
)
from evaluation.receipt_join_schema import ReceiptJoinEntry, ReceiptJoinSet
from evaluation.receipt_join_validation import validate_receipt_join_set
from evaluation.reference_schema import TierAReferenceReceipt
from evaluation.row_alignment_schema import (
    PredictionReferenceRowLink,
    ReceiptRowAlignment,
    RowAlignmentExecutionStatus,
    RowAlignmentProvenance,
    RowLinkOutcome,
)


class RowAlignmentValidationError(ValueError):
    """Raised when row-alignment structure or source binding is invalid."""


def _fail(message: str) -> None:
    raise RowAlignmentValidationError(message)


def _revalidate_record(value: object, expected: type, label: str) -> None:
    if not isinstance(value, expected):
        _fail(f"{label} has invalid record type {type(value).__name__}.")
    try:
        expected.__post_init__(value)
    except (AttributeError, TypeError, ValueError) as error:
        _fail(f"{label} violates constructor invariants: {error}")


def _revalidate_alignment_graph(alignment: object) -> ReceiptRowAlignment:
    _revalidate_record(alignment, ReceiptRowAlignment, "row alignment")
    assert isinstance(alignment, ReceiptRowAlignment)
    _revalidate_record(
        alignment.prediction_scope,
        EvaluationRunScope,
        "row-alignment prediction scope",
    )
    _revalidate_record(
        alignment.provenance,
        RowAlignmentProvenance,
        "row-alignment provenance",
    )
    for index, link in enumerate(alignment.row_links):
        _revalidate_record(
            link,
            PredictionReferenceRowLink,
            f"row link at index {index}",
        )
    return alignment


def _source_binding(alignment: ReceiptRowAlignment) -> tuple[object, ...]:
    return (
        alignment.manifest_id,
        alignment.manifest_version,
        alignment.dataset_version,
        alignment.prediction_bundle_id,
        alignment.prediction_scope,
        alignment.join_set_id,
        alignment.join_set_version,
        alignment.join_revision_id,
    )


def _expected_source_binding(join_set: ReceiptJoinSet) -> tuple[object, ...]:
    return (
        join_set.manifest_id,
        join_set.manifest_version,
        join_set.dataset_version,
        join_set.prediction_bundle_id,
        join_set.prediction_scope,
        join_set.join_set_id,
        join_set.join_set_version,
        join_set.revision_id,
    )


def _find_join_entry(
    alignment: ReceiptRowAlignment,
    join_set: ReceiptJoinSet,
) -> ReceiptJoinEntry:
    entries = {
        item.join_entry_id: item
        for item in join_set.entries
        if item.join_entry_id == alignment.join_entry_id
    }
    entry = entries.get(alignment.join_entry_id)
    if entry is None:
        _fail("Row alignment references an unknown receipt-join entry.")
    return entry


def _find_prediction_receipt(
    join_entry: ReceiptJoinEntry,
    prediction_bundle: PredictionBundle,
) -> PredictionReceipt | None:
    if join_entry.runtime_receipt_id is None:
        return None
    receipts = {
        item.runtime_receipt_id: item for item in prediction_bundle.receipts
    }
    receipt = receipts.get(join_entry.runtime_receipt_id)
    if receipt is None:
        _fail("Receipt-join runtime identity is absent from the prediction bundle.")
    return receipt


def _find_reference_receipt(
    join_entry: ReceiptJoinEntry,
    reference_receipts: tuple[TierAReferenceReceipt, ...],
) -> TierAReferenceReceipt | None:
    if join_entry.reference_receipt_id is None:
        return None
    receipts = {item.receipt_id: item for item in reference_receipts}
    receipt = receipts.get(join_entry.reference_receipt_id)
    if receipt is None:
        _fail("Receipt-join reference identity is absent from reference records.")
    return receipt


def _validate_completed_links(
    alignment: ReceiptRowAlignment,
    *,
    join_entry: ReceiptJoinEntry,
    prediction_receipt: PredictionReceipt | None,
    reference_receipt: TierAReferenceReceipt | None,
) -> None:
    prediction_rows = (
        {}
        if prediction_receipt is None
        else {item.runtime_row_id: item for item in prediction_receipt.rows}
    )
    reference_rows = (
        {}
        if reference_receipt is None
        else {item.row_id: item for item in reference_receipt.items}
    )

    link_ids: set[str] = set()
    covered_prediction_rows: set[str] = set()
    covered_reference_rows: set[str] = set()
    for link in alignment.row_links:
        if link.row_link_id in link_ids:
            _fail(f"Duplicate row-link ID {link.row_link_id!r}.")
        link_ids.add(link.row_link_id)
        if link.alignment_event_id != alignment.provenance.event_id:
            _fail(
                f"Row link {link.row_link_id!r} references another alignment event."
            )

        if link.runtime_row_id is not None:
            if link.runtime_receipt_id != join_entry.runtime_receipt_id:
                _fail(
                    f"Row link {link.row_link_id!r} uses a prediction row from "
                    "another receipt."
                )
            source_row = prediction_rows.get(link.runtime_row_id)
            if source_row is None:
                _fail(
                    f"Row link {link.row_link_id!r} references an unknown "
                    "prediction row."
                )
            if source_row.runtime_receipt_id != link.runtime_receipt_id:
                _fail("Prediction row and containing receipt identities conflict.")
            if source_row.output_ordinal != link.prediction_output_ordinal:
                _fail(
                    "Copied prediction output ordinal disagrees with the source row."
                )
            if link.runtime_row_id in covered_prediction_rows:
                _fail("A prediction row participates in more than one row link.")
            covered_prediction_rows.add(link.runtime_row_id)

        if link.reference_row_id is not None:
            if link.reference_receipt_id != join_entry.reference_receipt_id:
                _fail(
                    f"Row link {link.row_link_id!r} uses a reference row from "
                    "another receipt."
                )
            source_row = reference_rows.get(link.reference_row_id)
            if source_row is None:
                _fail(
                    f"Row link {link.row_link_id!r} references an unknown "
                    "reference row."
                )
            if source_row.receipt_id != link.reference_receipt_id:
                _fail("Reference row and containing receipt identities conflict.")
            if source_row.source_order != link.reference_source_order:
                _fail(
                    "Copied reference source order disagrees with the source row."
                )
            if link.reference_row_id in covered_reference_rows:
                _fail("A reference row participates in more than one row link.")
            covered_reference_rows.add(link.reference_row_id)

        if link.outcome is RowLinkOutcome.MATCHED and (
            prediction_receipt is None or reference_receipt is None
        ):
            _fail("MATCHED cannot cross a missing receipt side.")

    expected_prediction_rows = set(prediction_rows)
    if covered_prediction_rows != expected_prediction_rows:
        _fail(
            "Completed alignment does not exactly cover prediction rows; "
            f"missing={sorted(expected_prediction_rows - covered_prediction_rows)}, "
            f"extra={sorted(covered_prediction_rows - expected_prediction_rows)}."
        )
    expected_reference_rows = set(reference_rows)
    if covered_reference_rows != expected_reference_rows:
        _fail(
            "Completed alignment does not exactly cover reference rows; "
            f"missing={sorted(expected_reference_rows - covered_reference_rows)}, "
            f"extra={sorted(covered_reference_rows - expected_reference_rows)}."
        )


def validate_row_alignment(
    alignment: ReceiptRowAlignment,
    *,
    join_set: ReceiptJoinSet,
    manifest: EvaluationManifest,
    prediction_bundle: PredictionBundle,
    reference_receipts: tuple[TierAReferenceReceipt, ...],
) -> None:
    """Validate structure and row coverage without authenticating a matcher."""

    alignment = _revalidate_alignment_graph(alignment)
    validate_receipt_join_set(
        join_set,
        manifest=manifest,
        prediction_bundle=prediction_bundle,
        reference_receipts=reference_receipts,
    )
    if _source_binding(alignment) != _expected_source_binding(join_set):
        _fail("Row alignment is bound to another join source scope or revision.")

    join_entry = _find_join_entry(alignment, join_set)
    prediction_receipt = _find_prediction_receipt(join_entry, prediction_bundle)
    reference_receipt = _find_reference_receipt(join_entry, reference_receipts)

    if alignment.execution_status is RowAlignmentExecutionStatus.COMPLETED:
        _validate_completed_links(
            alignment,
            join_entry=join_entry,
            prediction_receipt=prediction_receipt,
            reference_receipt=reference_receipt,
        )


def validate_row_alignment_collection(
    alignments: tuple[ReceiptRowAlignment, ...],
    *,
    join_set: ReceiptJoinSet,
    manifest: EvaluationManifest,
    prediction_bundle: PredictionBundle,
    reference_receipts: tuple[TierAReferenceReceipt, ...],
) -> None:
    """Validate one complete, consistently configured join-entry collection."""

    if not isinstance(alignments, tuple):
        _fail("alignments must be a tuple.")
    validate_receipt_join_set(
        join_set,
        manifest=manifest,
        prediction_bundle=prediction_bundle,
        reference_receipts=reference_receipts,
    )
    expected_join_entry_ids = {item.join_entry_id for item in join_set.entries}
    record_keys: set[tuple[str, str]] = set()
    complete_scope_keys: set[tuple[object, ...]] = set()
    covered_join_entry_ids: set[str] = set()
    configuration_references: set[str] = set()
    for alignment in alignments:
        alignment = _revalidate_alignment_graph(alignment)
        validate_row_alignment(
            alignment,
            join_set=join_set,
            manifest=manifest,
            prediction_bundle=prediction_bundle,
            reference_receipts=reference_receipts,
        )
        record_key = (alignment.alignment_id, alignment.alignment_version)
        if record_key in record_keys:
            _fail(f"Duplicate row-alignment record identity {record_key!r}.")
        record_keys.add(record_key)
        complete_scope_key = (*_source_binding(alignment), alignment.join_entry_id)
        if complete_scope_key in complete_scope_keys:
            _fail(
                "Conflicting row-alignment records occupy the same complete scope."
            )
        complete_scope_keys.add(complete_scope_key)
        if alignment.join_entry_id in covered_join_entry_ids:
            _fail(
                f"Duplicate alignment coverage for join entry "
                f"{alignment.join_entry_id!r}."
            )
        covered_join_entry_ids.add(alignment.join_entry_id)
        configuration_references.add(
            alignment.alignment_configuration_reference
        )

    missing_join_entries = expected_join_entry_ids - covered_join_entry_ids
    extra_join_entries = covered_join_entry_ids - expected_join_entry_ids
    if missing_join_entries or extra_join_entries:
        _fail(
            "Alignment collection does not exactly cover receipt-join entries; "
            f"missing={sorted(missing_join_entries)}, "
            f"extra={sorted(extra_join_entries)}."
        )
    if len(configuration_references) > 1:
        _fail(
            "Alignment collection contains inconsistent "
            "alignment_configuration_reference values."
        )


__all__ = (
    "RowAlignmentValidationError",
    "validate_row_alignment",
    "validate_row_alignment_collection",
)
