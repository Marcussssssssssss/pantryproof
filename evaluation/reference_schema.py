"""Immutable Tier A reference-truth records for research evaluation.

This module contains adjudicated reference data only.  It deliberately has no
constructor or adapter from OCR, baseline, proposed-method, or prediction
outputs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import Any

from pipeline.contracts import ReceiptFieldName


REFERENCE_SCHEMA_VERSION = "0"

RECEIPT_LEVEL_FIELD_NAMES = (
    ReceiptFieldName.STORE_NAME,
    ReceiptFieldName.PURCHASE_DATE,
    ReceiptFieldName.RECEIPT_TOTAL,
)
ITEM_LEVEL_FIELD_NAMES = (
    ReceiptFieldName.ITEM_DESCRIPTION,
    ReceiptFieldName.QUANTITY,
    ReceiptFieldName.UNIT_PRICE,
    ReceiptFieldName.LINE_TOTAL,
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text.")


def _require_identifier(value: object, name: str) -> None:
    _require_text(value, name)
    assert isinstance(value, str)
    if _IDENTIFIER_RE.fullmatch(value) is None:
        raise ValueError(
            f"{name} must use only ASCII letters, digits, '.', '_', ':', '/', or '-'."
        )


def _require_tuple(value: object, name: str) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple.")


class ReferenceAvailability(str, Enum):
    """Whether receipt evidence supports an adjudicated reference value."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class ReferenceValueKind(str, Enum):
    """Whether reference truth is literal or explicitly adjudicator-derived."""

    LITERAL_TRANSCRIPTION = "LITERAL_TRANSCRIPTION"
    ADJUDICATED_DERIVED = "ADJUDICATED_DERIVED"


class ReferenceRecordStatus(str, Enum):
    """Lifecycle state of a complete receipt reference record."""

    DRAFT = "DRAFT"
    FINALIZED = "FINALIZED"


class QADiagnosticStatus(str, Enum):
    """Adjudication-QA state, distinct from structural validity."""

    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    RESOLVED = "RESOLVED"


@dataclass(frozen=True, slots=True)
class ReferenceValue:
    """Literal or explicitly derived truth plus optional separate normalization."""

    original_transcription: str | None
    normalized_value: str | None = None
    normalization_spec_version: str | None = None
    value_kind: ReferenceValueKind = ReferenceValueKind.LITERAL_TRANSCRIPTION
    derived_value: str | None = None
    derivation_rule_reference: str | None = None
    derivation_evidence_field_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.value_kind, ReferenceValueKind):
            raise TypeError("value_kind must be a ReferenceValueKind.")
        _require_tuple(
            self.derivation_evidence_field_ids, "derivation_evidence_field_ids"
        )
        for field_id in self.derivation_evidence_field_ids:
            _require_identifier(field_id, "derivation evidence field ID")
        if len(self.derivation_evidence_field_ids) != len(
            set(self.derivation_evidence_field_ids)
        ):
            raise ValueError(
                "derivation_evidence_field_ids must not contain duplicates."
            )

        if self.value_kind is ReferenceValueKind.LITERAL_TRANSCRIPTION:
            _require_text(self.original_transcription, "original_transcription")
            if (
                self.derived_value is not None
                or self.derivation_rule_reference is not None
                or self.derivation_evidence_field_ids
            ):
                raise ValueError(
                    "Literal reference truth cannot contain derivation data."
                )
        else:
            if self.original_transcription is not None:
                raise ValueError(
                    "Derived reference truth must not fabricate original_transcription."
                )
            _require_text(self.derived_value, "derived_value")
            _require_identifier(
                self.derivation_rule_reference, "derivation_rule_reference"
            )
            if not self.derivation_evidence_field_ids:
                raise ValueError(
                    "Derived reference truth requires receipt evidence field IDs."
                )

        if self.normalized_value is None:
            if self.normalization_spec_version is not None:
                raise ValueError(
                    "normalization_spec_version requires a normalized_value."
                )
        else:
            _require_text(self.normalized_value, "normalized_value")
            _require_identifier(
                self.normalization_spec_version, "normalization_spec_version"
            )

    @property
    def adjudicated_value(self) -> str:
        """Return the literal or derived adjudicated value without normalizing it."""

        if self.value_kind is ReferenceValueKind.ADJUDICATED_DERIVED:
            assert self.derived_value is not None
            return self.derived_value
        assert self.original_transcription is not None
        return self.original_transcription


@dataclass(frozen=True, slots=True)
class AnnotationEventReference:
    """Auditable reference to one annotation event and its stored source."""

    event_id: str
    source_reference: str

    def __post_init__(self) -> None:
        _require_identifier(self.event_id, "annotation event_id")
        _require_identifier(self.source_reference, "annotation source_reference")


@dataclass(frozen=True, slots=True)
class AdjudicationEventReference:
    """Auditable reference to one adjudication event and resulting source."""

    event_id: str
    adjudicated_reference_source: str

    def __post_init__(self) -> None:
        _require_identifier(self.event_id, "adjudication event_id")
        _require_identifier(
            self.adjudicated_reference_source, "adjudicated_reference_source"
        )


@dataclass(frozen=True, slots=True)
class AnnotationProvenance:
    """Versioned annotation and adjudication event catalogue for one receipt."""

    schema_version: str
    annotation_guideline_version: str
    annotation_events: tuple[AnnotationEventReference, ...]
    adjudication_events: tuple[AdjudicationEventReference, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.schema_version, "schema_version")
        _require_identifier(
            self.annotation_guideline_version, "annotation_guideline_version"
        )
        _require_tuple(self.annotation_events, "annotation_events")
        _require_tuple(self.adjudication_events, "adjudication_events")
        if any(
            not isinstance(event, AnnotationEventReference)
            for event in self.annotation_events
        ):
            raise TypeError("annotation_events contains an invalid event record.")
        if any(
            not isinstance(event, AdjudicationEventReference)
            for event in self.adjudication_events
        ):
            raise TypeError("adjudication_events contains an invalid event record.")

        annotation_ids = tuple(event.event_id for event in self.annotation_events)
        adjudication_ids = tuple(event.event_id for event in self.adjudication_events)
        if len(annotation_ids) != len(set(annotation_ids)):
            raise ValueError("annotation event IDs must be unique.")
        if len(adjudication_ids) != len(set(adjudication_ids)):
            raise ValueError("adjudication event IDs must be unique.")
        if set(annotation_ids) & set(adjudication_ids):
            raise ValueError(
                "Annotation and adjudication event IDs must identify distinct events."
            )


@dataclass(frozen=True, slots=True)
class ReferenceField:
    """One receipt-visible reference field with explicit availability."""

    field_id: str
    receipt_id: str
    field_name: ReceiptFieldName
    availability: ReferenceAvailability
    annotation_event_id: str
    adjudication_event_id: str | None
    item_row_id: str | None = None
    value: ReferenceValue | None = None
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.field_id, "field_id")
        _require_identifier(self.receipt_id, "field receipt_id")
        if not isinstance(self.field_name, ReceiptFieldName):
            raise TypeError("field_name must be a ReceiptFieldName.")
        if not isinstance(self.availability, ReferenceAvailability):
            raise TypeError("availability must be a ReferenceAvailability.")
        _require_identifier(self.annotation_event_id, "annotation_event_id")
        if self.adjudication_event_id is not None:
            _require_identifier(self.adjudication_event_id, "adjudication_event_id")
        if self.item_row_id is not None:
            _require_identifier(self.item_row_id, "item_row_id")

        if self.availability is ReferenceAvailability.AVAILABLE:
            if not isinstance(self.value, ReferenceValue):
                raise ValueError(
                    "A reference-available field requires an adjudicated ReferenceValue."
                )
            if self.unavailable_reason is not None:
                raise ValueError(
                    "A reference-available field cannot have an unavailable_reason."
                )
            if (
                self.value.value_kind is ReferenceValueKind.ADJUDICATED_DERIVED
                and self.field_name is not ReceiptFieldName.UNIT_PRICE
            ):
                raise ValueError(
                    "Only unit-price reference truth may be adjudicator-derived in V0."
                )
        else:
            if self.value is not None:
                raise ValueError(
                    "A reference-unavailable field must not contain a fabricated value."
                )
            _require_text(self.unavailable_reason, "unavailable_reason")


@dataclass(frozen=True, slots=True)
class ReferenceItemRow:
    """One ordered pantry-relevant purchased line on a reference receipt."""

    row_id: str
    receipt_id: str
    source_order: int
    description: ReferenceField
    quantity: ReferenceField
    unit_price: ReferenceField
    line_total: ReferenceField

    def __post_init__(self) -> None:
        _require_identifier(self.row_id, "row_id")
        _require_identifier(self.receipt_id, "row receipt_id")
        if isinstance(self.source_order, bool) or not isinstance(self.source_order, int):
            raise TypeError("source_order must be an integer.")
        if self.source_order < 0:
            raise ValueError("source_order must be non-negative.")
        if any(
            not isinstance(field, ReferenceField)
            for field in (
                self.description,
                self.quantity,
                self.unit_price,
                self.line_total,
            )
        ):
            raise TypeError("Every item-row field must be a ReferenceField.")

    @property
    def fields(self) -> tuple[ReferenceField, ...]:
        return (self.description, self.quantity, self.unit_price, self.line_total)


@dataclass(frozen=True, slots=True)
class ReferenceQADiagnostic:
    """A recorded adjudication concern; it never mutates reference truth."""

    diagnostic_id: str
    receipt_id: str
    code: str
    message: str
    related_field_ids: tuple[str, ...]
    status: QADiagnosticStatus
    resolution_adjudication_event_id: str | None = None
    resolution_note: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.diagnostic_id, "diagnostic_id")
        _require_identifier(self.receipt_id, "diagnostic receipt_id")
        _require_identifier(self.code, "diagnostic code")
        _require_text(self.message, "diagnostic message")
        _require_tuple(self.related_field_ids, "related_field_ids")
        for field_id in self.related_field_ids:
            _require_identifier(field_id, "related field ID")
        if len(self.related_field_ids) != len(set(self.related_field_ids)):
            raise ValueError("related_field_ids must not contain duplicates.")
        if not isinstance(self.status, QADiagnosticStatus):
            raise TypeError("status must be a QADiagnosticStatus.")

        if self.status is QADiagnosticStatus.RESOLVED:
            _require_identifier(
                self.resolution_adjudication_event_id,
                "resolution_adjudication_event_id",
            )
            _require_text(self.resolution_note, "resolution_note")
        elif (
            self.resolution_adjudication_event_id is not None
            or self.resolution_note is not None
        ):
            raise ValueError(
                "A review-required diagnostic cannot contain resolution details."
            )


@dataclass(frozen=True, slots=True)
class TierAReferenceReceipt:
    """Evaluation-only Tier A reference truth for one de-identified receipt."""

    receipt_id: str
    source_reference_id: str
    provenance: AnnotationProvenance
    store_name: ReferenceField
    purchase_date: ReferenceField
    items: tuple[ReferenceItemRow, ...]
    receipt_total: ReferenceField
    status: ReferenceRecordStatus
    qa_diagnostics: tuple[ReferenceQADiagnostic, ...] = ()
    schema_version: str = REFERENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_identifier(self.receipt_id, "receipt_id")
        _require_identifier(self.source_reference_id, "source_reference_id")
        if not isinstance(self.provenance, AnnotationProvenance):
            raise TypeError("provenance must be AnnotationProvenance.")
        if any(
            not isinstance(field, ReferenceField)
            for field in (self.store_name, self.purchase_date, self.receipt_total)
        ):
            raise TypeError("Receipt-level fields must be ReferenceField records.")
        _require_tuple(self.items, "items")
        if any(not isinstance(item, ReferenceItemRow) for item in self.items):
            raise TypeError("items contains an invalid item-row record.")
        if not isinstance(self.status, ReferenceRecordStatus):
            raise TypeError("status must be a ReferenceRecordStatus.")
        _require_tuple(self.qa_diagnostics, "qa_diagnostics")
        if any(
            not isinstance(item, ReferenceQADiagnostic)
            for item in self.qa_diagnostics
        ):
            raise TypeError("qa_diagnostics contains an invalid diagnostic record.")
        if self.schema_version != REFERENCE_SCHEMA_VERSION:
            raise ValueError(
                f"This module implements schema version {REFERENCE_SCHEMA_VERSION}."
            )

        # Import at construction time to keep schema records and cross-record
        # validation in separate modules without a module-import cycle.
        from evaluation.reference_validation import validate_reference_receipt

        validate_reference_receipt(
            self,
            require_evaluation_ready=self.status is ReferenceRecordStatus.FINALIZED,
        )

    @property
    def receipt_fields(self) -> tuple[ReferenceField, ...]:
        return (self.store_name, self.purchase_date, self.receipt_total)

    @property
    def all_fields(self) -> tuple[ReferenceField, ...]:
        return (
            self.store_name,
            self.purchase_date,
            *(field for item in self.items for field in item.fields),
            self.receipt_total,
        )


def to_json_compatible(value: Any) -> Any:
    """Convert reference records to JSON-safe primitives without numeric coercion."""

    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: to_json_compatible(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, tuple):
        return [to_json_compatible(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): to_json_compatible(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(
        f"Unsupported reference-contract JSON value: {type(value).__name__}."
    )


def to_deterministic_json(value: Any) -> str:
    """Serialize supported reference records with canonical key ordering."""

    return json.dumps(
        to_json_compatible(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def serialize_reference_receipt(receipt: TierAReferenceReceipt) -> str:
    """Serialize one structurally valid receipt without changing its values."""

    from evaluation.reference_validation import validate_reference_receipt

    validate_reference_receipt(receipt, require_evaluation_ready=False)
    return to_deterministic_json(receipt)


def serialize_reference_collection(
    receipts: tuple[TierAReferenceReceipt, ...],
    *,
    require_evaluation_ready: bool = True,
) -> str:
    """Serialize a collection canonically by receipt ID after validation."""

    from evaluation.reference_validation import validate_reference_collection

    validate_reference_collection(
        receipts, require_evaluation_ready=require_evaluation_ready
    )
    ordered = tuple(sorted(receipts, key=lambda receipt: receipt.receipt_id))
    return to_deterministic_json(ordered)
