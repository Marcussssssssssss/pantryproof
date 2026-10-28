"""Immutable synthetic-only row-alignment link records.

These records represent declared alignment results.  They do not run a
matcher, establish that a declared pair is correct, or authorize evaluation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from evaluation.manifest_schema import EvaluationManifest
from evaluation.prediction_schema import EvaluationRunScope, PredictionBundle
from evaluation.receipt_join_schema import ReceiptJoinSet
from evaluation.reference_schema import TierAReferenceReceipt, to_json_compatible


ROW_ALIGNMENT_SCHEMA_VERSION = "0"
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text.")


def _require_identifier(value: object, name: str) -> None:
    _require_text(value, name)
    assert isinstance(value, str)
    if _IDENTIFIER_RE.fullmatch(value) is None:
        raise ValueError(f"{name} has an invalid identifier format.")


def _require_runtime_identifier(value: object, name: str) -> None:
    _require_text(value, name)


def _require_tuple(value: object, name: str) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple.")


def _require_schema_version(value: object) -> None:
    if value != ROW_ALIGNMENT_SCHEMA_VERSION:
        raise ValueError(
            f"This module implements row-alignment schema "
            f"{ROW_ALIGNMENT_SCHEMA_VERSION}."
        )


def _require_ordinal(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer.")
    if value < 0:
        raise ValueError(f"{name} must be non-negative.")


class RowAlignmentExecutionStatus(str, Enum):
    """Whether row alignment completed, was blocked, or never ran."""

    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    NOT_EXECUTED = "NOT_EXECUTED"


class RowLinkOutcome(str, Enum):
    """One terminal row-coverage outcome in a completed alignment."""

    MATCHED = "MATCHED"
    REFERENCE_ONLY = "REFERENCE_ONLY"
    PREDICTION_ONLY = "PREDICTION_ONLY"


@dataclass(frozen=True, slots=True)
class RowAlignmentProvenance:
    """Synthetic audit pointers for an alignment status or execution event."""

    event_id: str
    process_version: str
    source_references: tuple[str, ...]
    actor_reference: str
    recorded_at: str | None = None
    schema_version: str = ROW_ALIGNMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_identifier(self.event_id, "alignment provenance event_id")
        _require_identifier(
            self.process_version, "alignment provenance process_version"
        )
        _require_tuple(self.source_references, "alignment source_references")
        for item in self.source_references:
            _require_identifier(item, "alignment source reference")
        if not self.source_references:
            raise ValueError("Alignment provenance requires a source reference.")
        if len(self.source_references) != len(set(self.source_references)):
            raise ValueError("Alignment source references must be unique.")
        _require_identifier(
            self.actor_reference, "alignment provenance actor_reference"
        )
        if self.recorded_at is not None:
            _require_text(self.recorded_at, "alignment provenance recorded_at")
        _require_schema_version(self.schema_version)


@dataclass(frozen=True, slots=True)
class PredictionReferenceRowLink:
    """One explicit matched or unmatched row-coverage declaration."""

    row_link_id: str
    outcome: RowLinkOutcome
    runtime_receipt_id: str | None
    runtime_row_id: str | None
    prediction_output_ordinal: int | None
    reference_receipt_id: str | None
    reference_row_id: str | None
    reference_source_order: int | None
    alignment_event_id: str
    unmatched_reason: str | None = None
    schema_version: str = ROW_ALIGNMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_identifier(self.row_link_id, "row_link_id")
        if not isinstance(self.outcome, RowLinkOutcome):
            raise TypeError("outcome must be a RowLinkOutcome.")
        _require_identifier(self.alignment_event_id, "alignment_event_id")

        if self.outcome is RowLinkOutcome.MATCHED:
            _require_runtime_identifier(
                self.runtime_receipt_id, "runtime_receipt_id"
            )
            _require_runtime_identifier(self.runtime_row_id, "runtime_row_id")
            _require_ordinal(
                self.prediction_output_ordinal, "prediction_output_ordinal"
            )
            _require_identifier(
                self.reference_receipt_id, "reference_receipt_id"
            )
            _require_identifier(self.reference_row_id, "reference_row_id")
            _require_ordinal(self.reference_source_order, "reference_source_order")
            if self.unmatched_reason is not None:
                raise ValueError("MATCHED cannot contain unmatched_reason.")
        elif self.outcome is RowLinkOutcome.REFERENCE_ONLY:
            if (
                self.runtime_receipt_id is not None
                or self.runtime_row_id is not None
                or self.prediction_output_ordinal is not None
            ):
                raise ValueError(
                    "REFERENCE_ONLY must not fabricate prediction-row data."
                )
            _require_identifier(
                self.reference_receipt_id, "reference_receipt_id"
            )
            _require_identifier(self.reference_row_id, "reference_row_id")
            _require_ordinal(self.reference_source_order, "reference_source_order")
            _require_text(self.unmatched_reason, "unmatched_reason")
        else:
            _require_runtime_identifier(
                self.runtime_receipt_id, "runtime_receipt_id"
            )
            _require_runtime_identifier(self.runtime_row_id, "runtime_row_id")
            _require_ordinal(
                self.prediction_output_ordinal, "prediction_output_ordinal"
            )
            if (
                self.reference_receipt_id is not None
                or self.reference_row_id is not None
                or self.reference_source_order is not None
            ):
                raise ValueError(
                    "PREDICTION_ONLY must not fabricate reference-row data."
                )
            _require_text(self.unmatched_reason, "unmatched_reason")
        _require_schema_version(self.schema_version)


@dataclass(frozen=True, slots=True)
class ReceiptRowAlignment:
    """One receipt-join entry's row-alignment execution-status record."""

    alignment_id: str
    alignment_version: str
    manifest_id: str
    manifest_version: str
    dataset_version: str
    prediction_bundle_id: str
    prediction_scope: EvaluationRunScope
    join_set_id: str
    join_set_version: str
    join_revision_id: str
    join_entry_id: str
    alignment_configuration_reference: str
    execution_status: RowAlignmentExecutionStatus
    row_links: tuple[PredictionReferenceRowLink, ...]
    provenance: RowAlignmentProvenance
    execution_reference: str | None = None
    status_reason: str | None = None
    schema_version: str = ROW_ALIGNMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for value, name in (
            (self.alignment_id, "alignment_id"),
            (self.alignment_version, "alignment_version"),
            (self.manifest_id, "alignment manifest_id"),
            (self.manifest_version, "alignment manifest_version"),
            (self.dataset_version, "alignment dataset_version"),
            (self.prediction_bundle_id, "alignment prediction_bundle_id"),
            (self.join_set_id, "alignment join_set_id"),
            (self.join_set_version, "alignment join_set_version"),
            (self.join_revision_id, "alignment join_revision_id"),
            (self.join_entry_id, "alignment join_entry_id"),
            (
                self.alignment_configuration_reference,
                "alignment_configuration_reference",
            ),
        ):
            _require_identifier(value, name)
        if not isinstance(self.prediction_scope, EvaluationRunScope):
            raise TypeError("prediction_scope must be an EvaluationRunScope.")
        if not isinstance(self.execution_status, RowAlignmentExecutionStatus):
            raise TypeError(
                "execution_status must be a RowAlignmentExecutionStatus."
            )
        _require_tuple(self.row_links, "row_links")
        if any(
            not isinstance(item, PredictionReferenceRowLink)
            for item in self.row_links
        ):
            raise TypeError("row_links contains an invalid row-link record.")
        if not isinstance(self.provenance, RowAlignmentProvenance):
            raise TypeError("provenance must be a RowAlignmentProvenance.")

        if self.execution_status is RowAlignmentExecutionStatus.COMPLETED:
            _require_identifier(self.execution_reference, "execution_reference")
            if self.status_reason is not None:
                raise ValueError("COMPLETED cannot contain status_reason.")
        else:
            if self.row_links:
                raise ValueError(
                    "BLOCKED or NOT_EXECUTED alignment must not contain row links."
                )
            if self.execution_reference is not None:
                raise ValueError(
                    "BLOCKED or NOT_EXECUTED cannot claim execution_reference."
                )
            _require_text(self.status_reason, "status_reason")
        _require_schema_version(self.schema_version)


def _canonical_alignment_payload(
    alignment: ReceiptRowAlignment,
) -> dict[str, Any]:
    payload = to_json_compatible(alignment)
    payload["row_links"] = sorted(
        payload["row_links"],
        key=lambda item: (
            item["outcome"],
            item["runtime_receipt_id"] or "",
            item["runtime_row_id"] or "",
            item["reference_receipt_id"] or "",
            item["reference_row_id"] or "",
            item["row_link_id"],
        ),
    )
    payload["provenance"]["source_references"] = sorted(
        payload["provenance"]["source_references"]
    )
    return payload


def serialize_row_alignment(
    alignment: ReceiptRowAlignment,
    *,
    join_set: ReceiptJoinSet,
    manifest: EvaluationManifest,
    prediction_bundle: PredictionBundle,
    reference_receipts: tuple[TierAReferenceReceipt, ...],
) -> str:
    """Validate and canonically serialize one row-alignment status record."""

    from evaluation.row_alignment_validation import validate_row_alignment

    validate_row_alignment(
        alignment,
        join_set=join_set,
        manifest=manifest,
        prediction_bundle=prediction_bundle,
        reference_receipts=reference_receipts,
    )
    return json.dumps(
        _canonical_alignment_payload(alignment),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def serialize_row_alignment_collection(
    alignments: tuple[ReceiptRowAlignment, ...],
    *,
    join_set: ReceiptJoinSet,
    manifest: EvaluationManifest,
    prediction_bundle: PredictionBundle,
    reference_receipts: tuple[TierAReferenceReceipt, ...],
) -> str:
    """Validate and serialize a complete, consistently configured collection."""

    from evaluation.row_alignment_validation import validate_row_alignment_collection

    validate_row_alignment_collection(
        alignments,
        join_set=join_set,
        manifest=manifest,
        prediction_bundle=prediction_bundle,
        reference_receipts=reference_receipts,
    )
    payload = [_canonical_alignment_payload(item) for item in alignments]
    payload.sort(
        key=lambda item: (
            item["manifest_id"],
            item["manifest_version"],
            item["prediction_scope"]["dataset_id"],
            item["dataset_version"],
            item["prediction_scope"]["partition_id"],
            item["prediction_scope"]["cohort_id"],
            item["prediction_bundle_id"],
            item["prediction_scope"]["run_id"],
            item["prediction_scope"]["system_id"],
            item["prediction_scope"]["configuration_id"],
            item["prediction_scope"]["output_stage"],
            item["join_set_id"],
            item["join_set_version"],
            item["join_revision_id"],
            item["join_entry_id"],
            item["alignment_id"],
            item["alignment_version"],
        )
    )
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


__all__ = (
    "ROW_ALIGNMENT_SCHEMA_VERSION",
    "PredictionReferenceRowLink",
    "ReceiptRowAlignment",
    "RowAlignmentExecutionStatus",
    "RowAlignmentProvenance",
    "RowLinkOutcome",
    "serialize_row_alignment",
    "serialize_row_alignment_collection",
)
