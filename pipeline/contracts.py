"""Version-0 shared data contracts for PantryProof OCR and receipt data.

These definitions preserve source evidence and represent extraction/correction
state. They intentionally do not implement OCR, extraction, correction scoring,
policy thresholds, human review, or inventory persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from math import isfinite


CONTRACT_VERSION = "0"


class SourceProcessingStatus(str, Enum):
    RECEIVED = "RECEIVED"
    OCR_COMPLETED = "OCR_COMPLETED"
    OCR_PARTIAL = "OCR_PARTIAL"
    OCR_FAILED = "OCR_FAILED"


class SourceEvidenceDecision(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"


class ReceiptFieldName(str, Enum):
    STORE_NAME = "STORE_NAME"
    PURCHASE_DATE = "PURCHASE_DATE"
    ITEM_DESCRIPTION = "ITEM_DESCRIPTION"
    QUANTITY = "QUANTITY"
    UNIT_PRICE = "UNIT_PRICE"
    LINE_TOTAL = "LINE_TOTAL"
    RECEIPT_TOTAL = "RECEIPT_TOTAL"


class FieldStatus(str, Enum):
    EXTRACTED = "EXTRACTED"
    MISSING = "MISSING"
    UNRESOLVED = "UNRESOLVED"


class ReceiptExtractionStatus(str, Enum):
    EXTRACTED = "EXTRACTED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class OutputStage(str, Enum):
    PRE_REVIEW_AUTOMATIC = "PRE_REVIEW_AUTOMATIC"
    HUMAN_REVIEWED = "HUMAN_REVIEWED"
    ORACLE_MODIFIED = "ORACLE_MODIFIED"


class CorrectionStatus(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    ORIGINAL_RETAINED = "ORIGINAL_RETAINED"
    ALTERNATIVE_PROPOSED = "ALTERNATIVE_PROPOSED"
    ALTERNATIVE_ACCEPTED = "ALTERNATIVE_ACCEPTED"
    ALTERNATIVE_REJECTED = "ALTERNATIVE_REJECTED"


class UncertaintyState(str, Enum):
    NOT_ASSESSED = "NOT_ASSESSED"
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"


class EvidenceAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class PolicyState(str, Enum):
    AUTO_RESOLVED = "AUTO_RESOLVED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FALLBACK_NO_UPDATE = "FALLBACK_NO_UPDATE"
    FAILED = "FAILED"
    COMMITTED = "COMMITTED"


class FailureStage(str, Enum):
    PRE_RESOLUTION = "PRE_RESOLUTION"
    INVENTORY_PERSISTENCE = "INVENTORY_PERSISTENCE"


def _require_text(value: str, name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{name} must be non-empty.")


def _require_unique(values: tuple[str, ...], name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must not contain duplicates.")


@dataclass(frozen=True, slots=True)
class Point:
    """One source-image coordinate."""

    x: float
    y: float


@dataclass(frozen=True, slots=True)
class SourceProvenance:
    """Where an image or other original input came from."""

    source_system: str
    source_reference: str
    content_sha256: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.source_system, "source_system")
        _require_text(self.source_reference, "source_reference")
        if self.content_sha256 is not None:
            _require_text(self.content_sha256, "content_sha256")


@dataclass(frozen=True, slots=True)
class OcrSourceToken:
    """Immutable literal OCR evidence for one detected source region."""

    receipt_id: str
    token_id: str
    original_text: str
    polygon: tuple[Point, ...]
    raw_confidence: float | None = None

    def __post_init__(self) -> None:
        _require_text(self.receipt_id, "receipt_id")
        _require_text(self.token_id, "token_id")
        if not self.original_text:
            raise ValueError("original_text must preserve a non-empty OCR transcription.")
        if len(self.polygon) < 3:
            raise ValueError("polygon must contain at least three points.")
        if self.raw_confidence is not None and not isfinite(self.raw_confidence):
            raise ValueError("raw_confidence must be finite when provided.")


@dataclass(frozen=True, slots=True)
class SourceEvidenceGateResult:
    """Recorded result of the one-time source-evidence sufficiency gate."""

    gate_result_id: str
    receipt_id: str
    decision: SourceEvidenceDecision
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.gate_result_id, "gate_result_id")
        _require_text(self.receipt_id, "receipt_id")
        _require_unique(self.reasons, "reasons")
        if self.decision is SourceEvidenceDecision.INSUFFICIENT and not self.reasons:
            raise ValueError("An insufficient gate result requires at least one reason.")


@dataclass(frozen=True, slots=True)
class ReceiptSourceEvidence:
    """Recorded image/OCR package consumed by extraction and later correction."""

    receipt_id: str
    image_id: str
    provenance: SourceProvenance
    processing_status: SourceProcessingStatus
    tokens: tuple[OcrSourceToken, ...]
    gate_result: SourceEvidenceGateResult

    def __post_init__(self) -> None:
        _require_text(self.receipt_id, "receipt_id")
        _require_text(self.image_id, "image_id")
        token_ids = tuple(token.token_id for token in self.tokens)
        _require_unique(token_ids, "token IDs")
        if any(token.receipt_id != self.receipt_id for token in self.tokens):
            raise ValueError("Every OCR token must belong to the evidence receipt.")
        if self.gate_result.receipt_id != self.receipt_id:
            raise ValueError("The gate result must belong to the evidence receipt.")

    @property
    def token_ids(self) -> frozenset[str]:
        return frozenset(token.token_id for token in self.tokens)


_ITEM_FIELDS = {
    ReceiptFieldName.ITEM_DESCRIPTION,
    ReceiptFieldName.QUANTITY,
    ReceiptFieldName.UNIT_PRICE,
    ReceiptFieldName.LINE_TOTAL,
}


@dataclass(frozen=True, slots=True)
class StructuredField:
    """One extracted, missing, or unresolved receipt field.

    Confidence is optional and model-native. Its absence must remain ``None``;
    this contract does not create or calibrate probabilities.
    """

    field_id: str
    receipt_id: str
    field_name: ReceiptFieldName
    status: FieldStatus
    value: str | None = None
    item_row_id: str | None = None
    source_token_ids: tuple[str, ...] = ()
    confidence: float | None = None
    unresolved_reason: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.field_id, "field_id")
        _require_text(self.receipt_id, "receipt_id")
        _require_unique(self.source_token_ids, "source_token_ids")

        is_item_field = self.field_name in _ITEM_FIELDS
        if is_item_field and self.item_row_id is None:
            raise ValueError("Item fields require item_row_id.")
        if not is_item_field and self.item_row_id is not None:
            raise ValueError("Receipt-level fields must not have item_row_id.")
        if self.item_row_id is not None:
            _require_text(self.item_row_id, "item_row_id")
        if self.confidence is not None and not isfinite(self.confidence):
            raise ValueError("confidence must be finite when provided.")

        if self.status is FieldStatus.EXTRACTED:
            if self.value is None or not self.value.strip():
                raise ValueError("An extracted field requires a non-empty value.")
            if not self.source_token_ids:
                raise ValueError("An extracted field requires source OCR token references.")
            if self.unresolved_reason is not None:
                raise ValueError("An extracted field must not have an unresolved reason.")
        else:
            if self.value is not None:
                raise ValueError("Missing or unresolved fields must not contain a value.")
            if self.confidence is not None:
                raise ValueError("Missing or unresolved fields must not contain confidence.")
            if self.unresolved_reason is None:
                raise ValueError("Missing or unresolved fields require a reason.")
            _require_text(self.unresolved_reason, "unresolved_reason")


@dataclass(frozen=True, slots=True)
class ReceiptItemRow:
    """A detected item row; it cannot exist without extracted OCR-backed data."""

    row_id: str
    receipt_id: str
    description: StructuredField
    quantity: StructuredField
    unit_price: StructuredField
    line_total: StructuredField
    pantry_product_identity: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.row_id, "row_id")
        _require_text(self.receipt_id, "receipt_id")
        expected = (
            (self.description, ReceiptFieldName.ITEM_DESCRIPTION),
            (self.quantity, ReceiptFieldName.QUANTITY),
            (self.unit_price, ReceiptFieldName.UNIT_PRICE),
            (self.line_total, ReceiptFieldName.LINE_TOTAL),
        )
        for field, expected_name in expected:
            if field.field_name is not expected_name:
                raise ValueError(f"Expected {expected_name.value} for row field.")
            if field.receipt_id != self.receipt_id or field.item_row_id != self.row_id:
                raise ValueError("Every item field must belong to its receipt and row.")

        extracted_fields = [
            field for field, _ in expected if field.status is FieldStatus.EXTRACTED
        ]
        if not extracted_fields or not any(
            field.source_token_ids for field in extracted_fields
        ):
            raise ValueError("An item row requires extracted OCR-backed field evidence.")
        if self.pantry_product_identity is not None:
            _require_text(self.pantry_product_identity, "pantry_product_identity")

    @property
    def fields(self) -> tuple[StructuredField, ...]:
        return (self.description, self.quantity, self.unit_price, self.line_total)


@dataclass(frozen=True, slots=True)
class ReceiptOutput:
    """Structured receipt output linked back to its immutable source package."""

    receipt_id: str
    store_name: StructuredField
    purchase_date: StructuredField
    items: tuple[ReceiptItemRow, ...]
    receipt_total: StructuredField
    source_evidence: ReceiptSourceEvidence
    extraction_status: ReceiptExtractionStatus
    extractor_version: str
    output_stage: OutputStage = field(
        default=OutputStage.PRE_REVIEW_AUTOMATIC, init=False
    )
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        _require_text(self.receipt_id, "receipt_id")
        _require_text(self.extractor_version, "extractor_version")
        if self.contract_version != CONTRACT_VERSION:
            raise ValueError(f"This module implements contract version {CONTRACT_VERSION}.")
        if self.source_evidence.receipt_id != self.receipt_id:
            raise ValueError("Source evidence must belong to the output receipt.")
        if (
            self.source_evidence.gate_result.decision
            is SourceEvidenceDecision.INSUFFICIENT
        ):
            raise ValueError(
                "Structured receipt output cannot be created from insufficient "
                "source evidence; record FALLBACK_NO_UPDATE instead."
            )

        top_level = (
            (self.store_name, ReceiptFieldName.STORE_NAME),
            (self.purchase_date, ReceiptFieldName.PURCHASE_DATE),
            (self.receipt_total, ReceiptFieldName.RECEIPT_TOTAL),
        )
        for field, expected_name in top_level:
            if field.field_name is not expected_name:
                raise ValueError(f"Expected {expected_name.value} for receipt field.")
            if field.receipt_id != self.receipt_id:
                raise ValueError("Every receipt field must belong to the output receipt.")

        row_ids = tuple(item.row_id for item in self.items)
        _require_unique(row_ids, "item row IDs")
        if any(item.receipt_id != self.receipt_id for item in self.items):
            raise ValueError("Every item row must belong to the output receipt.")

        all_fields = [field for field, _ in top_level]
        all_fields.extend(field for item in self.items for field in item.fields)
        field_ids = tuple(field.field_id for field in all_fields)
        _require_unique(field_ids, "field IDs within a receipt")
        unknown_tokens = {
            token_id
            for field in all_fields
            for token_id in field.source_token_ids
            if token_id not in self.source_evidence.token_ids
        }
        if unknown_tokens:
            raise ValueError(
                f"Structured fields reference unknown source tokens: {sorted(unknown_tokens)}"
            )


@dataclass(frozen=True, slots=True)
class CandidateValue:
    """Immutable original or alternative value with non-probabilistic evidence."""

    value: str
    evidence_references: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.value, "candidate value")
        _require_unique(self.evidence_references, "evidence_references")


@dataclass(frozen=True, slots=True)
class CorrectionEvidence:
    """Future correction evidence that never overwrites its original candidate."""

    field_id: str
    original_candidate: CandidateValue
    gate_result_id: str
    status: CorrectionStatus
    uncertainty: UncertaintyState
    alternatives: tuple[CandidateValue, ...] = ()
    selected_alternative: CandidateValue | None = None
    evidence_references: tuple[str, ...] = ()
    uncertainty_reason: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.field_id, "field_id")
        _require_text(self.gate_result_id, "gate_result_id")
        _require_unique(self.evidence_references, "evidence_references")
        if len(self.alternatives) != len(set(self.alternatives)):
            raise ValueError("alternatives must not contain duplicate candidates.")
        if (
            self.status is CorrectionStatus.ALTERNATIVE_PROPOSED
            and not self.alternatives
        ):
            raise ValueError("A proposed correction requires an alternative candidate.")
        if self.status is CorrectionStatus.ALTERNATIVE_ACCEPTED:
            if not self.alternatives:
                raise ValueError("An accepted correction requires alternative candidates.")
            if self.selected_alternative is None:
                raise ValueError("An accepted correction requires a selected alternative.")
            if self.selected_alternative not in self.alternatives:
                raise ValueError("The selected alternative must belong to alternatives.")
        elif self.selected_alternative is not None:
            raise ValueError(
                "A selected alternative is only valid for ALTERNATIVE_ACCEPTED."
            )
        if self.uncertainty in {
            UncertaintyState.UNRESOLVED,
            UncertaintyState.CONFLICTING_EVIDENCE,
        }:
            if self.uncertainty_reason is None:
                raise ValueError("Unresolved uncertainty requires a reason.")
            _require_text(self.uncertainty_reason, "uncertainty_reason")


@dataclass(frozen=True, slots=True)
class ExternalPriceReference:
    """Optional retailer evidence, separate from extracted unit-price truth."""

    availability: EvidenceAvailability
    reference_value: str | None = None
    provenance: SourceProvenance | None = None
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        if self.availability is EvidenceAvailability.AVAILABLE:
            if self.reference_value is None or not self.reference_value.strip():
                raise ValueError("Available price evidence requires a reference value.")
            if self.provenance is None:
                raise ValueError("Available price evidence requires provenance.")
            if self.unavailable_reason is not None:
                raise ValueError("Available price evidence cannot have an unavailable reason.")
        else:
            if self.reference_value is not None or self.provenance is not None:
                raise ValueError("Unavailable price evidence cannot contain reference data.")
            if self.unavailable_reason is None:
                raise ValueError("Unavailable price evidence requires a reason.")
            _require_text(self.unavailable_reason, "unavailable_reason")


@dataclass(frozen=True, slots=True)
class PreResolutionDisposition:
    """Frozen decision produced before any later inventory persistence attempt."""

    state: PolicyState
    gate_result: SourceEvidenceGateResult
    failure_stage: FailureStage | None = None
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        allowed_states = {
            PolicyState.AUTO_RESOLVED,
            PolicyState.REVIEW_REQUIRED,
            PolicyState.FALLBACK_NO_UPDATE,
            PolicyState.FAILED,
        }
        if self.state not in allowed_states:
            raise ValueError("Pre-resolution disposition cannot be COMMITTED.")

        if self.gate_result.decision is SourceEvidenceDecision.INSUFFICIENT:
            if self.state is not PolicyState.FALLBACK_NO_UPDATE:
                raise ValueError(
                    "Insufficient source evidence requires FALLBACK_NO_UPDATE."
                )
        elif self.state is PolicyState.FALLBACK_NO_UPDATE:
            raise ValueError(
                "Sufficient source evidence cannot produce FALLBACK_NO_UPDATE."
            )

        if self.state is PolicyState.FAILED:
            if self.failure_stage is not FailureStage.PRE_RESOLUTION:
                raise ValueError("Pre-resolution FAILED requires PRE_RESOLUTION stage.")
            if self.failure_reason is None:
                raise ValueError("FAILED requires a failure reason.")
            _require_text(self.failure_reason, "failure_reason")
        elif self.failure_stage is not None or self.failure_reason is not None:
            raise ValueError("Only FAILED dispositions may contain failure details.")


@dataclass(frozen=True, slots=True)
class PersistenceOutcome:
    """Later persistence event retaining its frozen pre-resolution disposition.

    Construction validates record shape only. A future persistence service must
    create COMMITTED only after a database transaction actually succeeds.
    """

    pre_resolution: PreResolutionDisposition
    state: PolicyState
    failure_stage: FailureStage | None = None
    failure_reason: str | None = None
    inventory_write_reference: str | None = None

    def __post_init__(self) -> None:
        if self.pre_resolution.state is not PolicyState.AUTO_RESOLVED:
            raise ValueError(
                "Contract Version 0 permits persistence only after AUTO_RESOLVED; "
                "review, fallback, and pre-resolution failure are not eligible."
            )

        if self.state is PolicyState.FAILED:
            if self.failure_stage is not FailureStage.INVENTORY_PERSISTENCE:
                raise ValueError(
                    "Persistence FAILED requires INVENTORY_PERSISTENCE stage."
                )
            if self.failure_reason is None:
                raise ValueError("FAILED requires a failure reason.")
            _require_text(self.failure_reason, "failure_reason")
            if self.inventory_write_reference is not None:
                raise ValueError("A failed persistence event cannot have a write reference.")
        elif self.state is PolicyState.COMMITTED:
            if self.failure_stage is not None or self.failure_reason is not None:
                raise ValueError("COMMITTED cannot contain failure details.")
            if self.inventory_write_reference is None:
                raise ValueError("COMMITTED requires a recorded inventory write reference.")
            _require_text(self.inventory_write_reference, "inventory_write_reference")
        else:
            raise ValueError("Persistence outcome must be COMMITTED or FAILED.")
