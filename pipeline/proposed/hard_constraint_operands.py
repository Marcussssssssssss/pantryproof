"""Observational receipt-operand audit for future hard constraints.

This component projects one already-validated ``HardConstraintInputResultV0``
into raw B2 field and row relationships.  It deliberately performs no parsing,
arithmetic, constraint eligibility, scoring, review, or persistence work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from pipeline.contracts import (
    FieldStatus,
    OcrSourceToken,
    ReceiptFieldName,
    ReceiptItemRow,
    ReceiptOutput,
    StructuredField,
)
from pipeline.proposed.candidate_finalization import (
    BlockedCandidateFinalizationAuditV0,
    CandidateFinalizationCoverageStatusV0,
)
from pipeline.proposed.contracts import CandidateRecordV1
from pipeline.proposed.hard_constraint_context import HardConstraintInputResultV0


HARD_CONSTRAINT_OPERANDS_COMPONENT_VERSION = "hard-constraint-operands-v0"
HARD_CONSTRAINT_OPERANDS_RECORD_VERSION = "hard-constraint-operands-record-v0"


_ITEM_FIELD_NAMES = (
    ReceiptFieldName.ITEM_DESCRIPTION,
    ReceiptFieldName.QUANTITY,
    ReceiptFieldName.UNIT_PRICE,
    ReceiptFieldName.LINE_TOTAL,
)


class HardConstraintOperandIntegrityError(ValueError):
    """Stored context or reconstructed operand evidence is contradictory."""


class OperandAvailabilityV0(str, Enum):
    """Observed B2 availability, not parse or constraint validity."""

    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    UNRESOLVED = "UNRESOLVED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RelationshipAvailabilityV0(str, Enum):
    """Whether a stored relationship exists without inferring one."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CandidateSubstitutionScopeV0(str, Enum):
    """Structural location of the original field a candidate targets."""

    RECEIPT_FIELD = "RECEIPT_FIELD"
    ITEM_ROW_FIELD = "ITEM_ROW_FIELD"


def _availability(field: StructuredField) -> OperandAvailabilityV0:
    if field.status is FieldStatus.EXTRACTED:
        return OperandAvailabilityV0.AVAILABLE
    if field.status is FieldStatus.MISSING:
        return OperandAvailabilityV0.MISSING
    if field.status is FieldStatus.UNRESOLVED:
        return OperandAvailabilityV0.UNRESOLVED
    raise HardConstraintOperandIntegrityError(
        "Stored B2 field has an unsupported availability status."
    )


def _receipt_fields(output: ReceiptOutput) -> tuple[StructuredField, ...]:
    return (
        output.store_name,
        output.purchase_date,
        *(field for row in output.items for field in row.fields),
        output.receipt_total,
    )


def _number_fingerprint(value: object) -> tuple[str, str, str]:
    """Retain type and literal representation without numeric interpretation."""

    value_type = type(value)
    return (value_type.__module__, value_type.__qualname__, repr(value))


@dataclass(frozen=True, slots=True)
class _StructuredFieldObservationV0:
    """Private primitive observation captured once for reconstruction integrity."""

    field_id: str
    receipt_id: str
    field_name: str
    item_row_id: str | None
    status: str
    raw_value: str | None
    source_token_ids: tuple[str, ...]
    confidence: float | None
    confidence_fingerprint: tuple[str, str, str] | None
    unresolved_reason: str | None

    @classmethod
    def capture(cls, field_value: StructuredField) -> _StructuredFieldObservationV0:
        confidence = field_value.confidence
        return cls(
            field_id=field_value.field_id,
            receipt_id=field_value.receipt_id,
            field_name=field_value.field_name.value,
            item_row_id=field_value.item_row_id,
            status=field_value.status.value,
            raw_value=field_value.value,
            source_token_ids=field_value.source_token_ids,
            confidence=confidence,
            confidence_fingerprint=(
                None if confidence is None else _number_fingerprint(confidence)
            ),
            unresolved_reason=field_value.unresolved_reason,
        )


@dataclass(frozen=True, slots=True)
class _SourceTokenObservationV0:
    """Private literal OCR-token observation; the source object stays upstream."""

    token_id: str
    receipt_id: str
    original_text: str
    polygon_coordinates: tuple[
        tuple[tuple[str, str, str], tuple[str, str, str]], ...
    ]
    raw_confidence_fingerprint: tuple[str, str, str] | None

    @classmethod
    def capture(cls, token: OcrSourceToken) -> _SourceTokenObservationV0:
        return cls(
            token_id=token.token_id,
            receipt_id=token.receipt_id,
            original_text=token.original_text,
            polygon_coordinates=tuple(
                (_number_fingerprint(point.x), _number_fingerprint(point.y))
                for point in token.polygon
            ),
            raw_confidence_fingerprint=(
                None
                if token.raw_confidence is None
                else _number_fingerprint(token.raw_confidence)
            ),
        )


def _capture_field_observation(
    owner: object,
    field_value: StructuredField,
) -> _StructuredFieldObservationV0:
    current = _StructuredFieldObservationV0.capture(field_value)
    try:
        observed = getattr(owner, "_field_observation")
    except AttributeError:
        object.__setattr__(owner, "_field_observation", current)
        return current
    if observed != current:
        raise HardConstraintOperandIntegrityError(
            "Stored B2 field changed after its raw operand observation."
        )
    return observed


@dataclass(frozen=True, slots=True)
class OperandEvidenceV0:
    """One exact stored B2 field exposed without interpreting its raw value."""

    b2_field: StructuredField
    record_version: str = HARD_CONSTRAINT_OPERANDS_RECORD_VERSION
    _field_observation: _StructuredFieldObservationV0 = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.b2_field, StructuredField):
            raise TypeError("b2_field must be StructuredField.")
        try:
            self.b2_field.__post_init__()
            _availability(self.b2_field)
        except (TypeError, ValueError) as exc:
            raise HardConstraintOperandIntegrityError(
                "Stored B2 operand failed shared-field revalidation."
            ) from exc
        _capture_field_observation(self, self.b2_field)
        if self.record_version != HARD_CONSTRAINT_OPERANDS_RECORD_VERSION:
            raise ValueError("Unsupported hard-constraint operand record version.")

    @property
    def field_id(self) -> str:
        return self._field_observation.field_id

    @property
    def receipt_id(self) -> str:
        return self._field_observation.receipt_id

    @property
    def field_name(self) -> ReceiptFieldName:
        return ReceiptFieldName(self._field_observation.field_name)

    @property
    def item_row_id(self) -> str | None:
        return self._field_observation.item_row_id

    @property
    def original_status(self) -> FieldStatus:
        return FieldStatus(self._field_observation.status)

    @property
    def raw_value(self) -> str | None:
        return self._field_observation.raw_value

    @property
    def source_token_ids(self) -> tuple[str, ...]:
        return self._field_observation.source_token_ids

    @property
    def confidence(self) -> float | None:
        return self._field_observation.confidence

    @property
    def unresolved_reason(self) -> str | None:
        return self._field_observation.unresolved_reason

    @property
    def availability(self) -> OperandAvailabilityV0:
        status = self.original_status
        if status is FieldStatus.EXTRACTED:
            return OperandAvailabilityV0.AVAILABLE
        if status is FieldStatus.MISSING:
            return OperandAvailabilityV0.MISSING
        if status is FieldStatus.UNRESOLVED:
            return OperandAvailabilityV0.UNRESOLVED
        raise HardConstraintOperandIntegrityError(
            "Observed B2 field has an unsupported availability status."
        )


@dataclass(frozen=True, slots=True)
class ItemRowOperandEvidenceV0:
    """One exact detected B2 item row and its four fields in B2 order."""

    b2_row: ReceiptItemRow
    operands: tuple[OperandEvidenceV0, ...]
    record_version: str = HARD_CONSTRAINT_OPERANDS_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.b2_row, ReceiptItemRow):
            raise TypeError("b2_row must be ReceiptItemRow.")
        if not isinstance(self.operands, tuple) or any(
            not isinstance(operand, OperandEvidenceV0) for operand in self.operands
        ):
            raise TypeError("operands must be a tuple of OperandEvidenceV0.")
        try:
            self.b2_row.__post_init__()
            for operand in self.operands:
                operand.__post_init__()
        except (TypeError, ValueError) as exc:
            raise HardConstraintOperandIntegrityError(
                "Stored item-row operand evidence failed revalidation."
            ) from exc
        if len(self.operands) != len(self.b2_row.fields) or any(
            operand.b2_field is not field
            for operand, field in zip(
                self.operands, self.b2_row.fields, strict=True
            )
        ):
            raise HardConstraintOperandIntegrityError(
                "Item operands must preserve exact B2 row field references and order."
            )
        if self.record_version != HARD_CONSTRAINT_OPERANDS_RECORD_VERSION:
            raise ValueError("Unsupported hard-constraint operand record version.")

    @property
    def row_id(self) -> str:
        return self.b2_row.row_id

    @property
    def receipt_id(self) -> str:
        return self.b2_row.receipt_id


@dataclass(frozen=True, slots=True)
class CandidateSubstitutionPositionV0:
    """The original B2 field position targeted by one prepared candidate."""

    target_field: StructuredField
    scope: CandidateSubstitutionScopeV0
    item_row: ReceiptItemRow | None
    item_row_index: int | None
    item_field_index: int | None
    record_version: str = HARD_CONSTRAINT_OPERANDS_RECORD_VERSION
    _field_observation: _StructuredFieldObservationV0 = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.target_field, StructuredField):
            raise TypeError("target_field must be StructuredField.")
        if not isinstance(self.scope, CandidateSubstitutionScopeV0):
            raise TypeError("scope must be CandidateSubstitutionScopeV0.")
        try:
            self.target_field.__post_init__()
        except (TypeError, ValueError) as exc:
            raise HardConstraintOperandIntegrityError(
                "Candidate target field failed shared-field revalidation."
            ) from exc
        _capture_field_observation(self, self.target_field)
        if self.target_field.status is not FieldStatus.EXTRACTED:
            raise HardConstraintOperandIntegrityError(
                "A prepared candidate must target the original EXTRACTED B2 field."
            )

        if self.scope is CandidateSubstitutionScopeV0.RECEIPT_FIELD:
            if self.target_field.field_name in _ITEM_FIELD_NAMES:
                raise HardConstraintOperandIntegrityError(
                    "An item field cannot claim a receipt-level substitution position."
                )
            if any(
                value is not None
                for value in (
                    self.item_row,
                    self.item_row_index,
                    self.item_field_index,
                )
            ):
                raise HardConstraintOperandIntegrityError(
                    "A receipt-level substitution has no item-row position."
                )
        else:
            if self.target_field.field_name not in _ITEM_FIELD_NAMES:
                raise HardConstraintOperandIntegrityError(
                    "An item-row substitution requires an item field."
                )
            if not isinstance(self.item_row, ReceiptItemRow):
                raise HardConstraintOperandIntegrityError(
                    "An item-row substitution requires its exact stored row."
                )
            if type(self.item_row_index) is not int or self.item_row_index < 0:
                raise HardConstraintOperandIntegrityError(
                    "item_row_index must be a non-Boolean non-negative integer."
                )
            if type(self.item_field_index) is not int or not (
                0 <= self.item_field_index < len(self.item_row.fields)
            ):
                raise HardConstraintOperandIntegrityError(
                    "item_field_index must identify one stored B2 row field."
                )
            if self.item_row.fields[self.item_field_index] is not self.target_field:
                raise HardConstraintOperandIntegrityError(
                    "The substitution position does not reference its target field."
                )
            if self.target_field.item_row_id != self.item_row.row_id:
                raise HardConstraintOperandIntegrityError(
                    "The target field and substitution row identities differ."
                )
        if self.record_version != HARD_CONSTRAINT_OPERANDS_RECORD_VERSION:
            raise ValueError("Unsupported hard-constraint operand record version.")


@dataclass(frozen=True, slots=True)
class CandidateOperandAuditV0:
    """Raw operand and relationship inventory for one prepared candidate."""

    candidate: CandidateRecordV1
    substitution_position: CandidateSubstitutionPositionV0
    target_source_relationship: RelationshipAvailabilityV0
    item_row_relationship: RelationshipAvailabilityV0
    item_rows: tuple[ItemRowOperandEvidenceV0, ...]
    receipt_total_operand: OperandEvidenceV0
    record_version: str = HARD_CONSTRAINT_OPERANDS_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, CandidateRecordV1):
            raise TypeError("candidate must be CandidateRecordV1.")
        if not isinstance(
            self.substitution_position, CandidateSubstitutionPositionV0
        ):
            raise TypeError(
                "substitution_position must be CandidateSubstitutionPositionV0."
            )
        if not isinstance(
            self.target_source_relationship, RelationshipAvailabilityV0
        ):
            raise TypeError(
                "target_source_relationship must be RelationshipAvailabilityV0."
            )
        if not isinstance(self.item_row_relationship, RelationshipAvailabilityV0):
            raise TypeError(
                "item_row_relationship must be RelationshipAvailabilityV0."
            )
        if not isinstance(self.item_rows, tuple) or any(
            not isinstance(row, ItemRowOperandEvidenceV0) for row in self.item_rows
        ):
            raise TypeError("item_rows must be ItemRowOperandEvidenceV0 records.")
        if not isinstance(self.receipt_total_operand, OperandEvidenceV0):
            raise TypeError("receipt_total_operand must be OperandEvidenceV0.")
        try:
            self.candidate.__post_init__()
            self.substitution_position.__post_init__()
            for row in self.item_rows:
                row.__post_init__()
            self.receipt_total_operand.__post_init__()
        except (TypeError, ValueError) as exc:
            raise HardConstraintOperandIntegrityError(
                "Candidate operand audit failed nested-record revalidation."
            ) from exc

        target = self.substitution_position.target_field
        if (
            self.candidate.receipt_id != target.receipt_id
            or self.candidate.field_id != target.field_id
        ):
            raise HardConstraintOperandIntegrityError(
                "Candidate identity differs from its original B2 target field."
            )
        if self.target_source_relationship is not RelationshipAvailabilityV0.AVAILABLE:
            raise HardConstraintOperandIntegrityError(
                "The extracted target must retain its stored source-token relationship."
            )
        expected_relationship = (
            RelationshipAvailabilityV0.AVAILABLE
            if self.substitution_position.scope
            is CandidateSubstitutionScopeV0.ITEM_ROW_FIELD
            else RelationshipAvailabilityV0.NOT_APPLICABLE
        )
        if self.item_row_relationship is not expected_relationship:
            raise HardConstraintOperandIntegrityError(
                "Item-row relationship availability contradicts the target position."
            )
        position = self.substitution_position
        if position.scope is CandidateSubstitutionScopeV0.ITEM_ROW_FIELD:
            if (
                position.item_row_index is None
                or position.item_row_index >= len(self.item_rows)
                or self.item_rows[position.item_row_index].b2_row
                is not position.item_row
            ):
                raise HardConstraintOperandIntegrityError(
                    "The substitution row index does not identify its exact row evidence."
                )
        row_ids = tuple(row.row_id for row in self.item_rows)
        if len(row_ids) != len(set(row_ids)) or any(
            row.receipt_id != self.candidate.receipt_id for row in self.item_rows
        ):
            raise HardConstraintOperandIntegrityError(
                "Receipt item-row evidence has duplicate or contradictory identity."
            )
        if (
            self.receipt_total_operand.field_name
            is not ReceiptFieldName.RECEIPT_TOTAL
            or self.receipt_total_operand.b2_field.receipt_id
            != self.candidate.receipt_id
        ):
            raise HardConstraintOperandIntegrityError(
                "Receipt-total operand identity contradicts the candidate receipt."
            )
        if self.record_version != HARD_CONSTRAINT_OPERANDS_RECORD_VERSION:
            raise ValueError("Unsupported hard-constraint operand record version.")

    @property
    def target_field(self) -> StructuredField:
        return self.substitution_position.target_field

    @property
    def candidate_value(self) -> str:
        return self.candidate.value

    @property
    def original_b2_value(self) -> str:
        value = self.substitution_position._field_observation.raw_value
        if value is None:  # Protected by the extracted target invariant.
            raise HardConstraintOperandIntegrityError(
                "The original candidate target unexpectedly has no raw value."
            )
        return value

    @property
    def target_source_availability(self) -> OperandAvailabilityV0:
        status = FieldStatus(
            self.substitution_position._field_observation.status
        )
        if status is not FieldStatus.EXTRACTED:
            raise HardConstraintOperandIntegrityError(
                "The observed candidate target is no longer extracted."
            )
        return OperandAvailabilityV0.AVAILABLE

    @property
    def item_operand_availability(
        self,
    ) -> tuple[tuple[ReceiptFieldName, OperandAvailabilityV0], ...]:
        position = self.substitution_position
        if position.scope is CandidateSubstitutionScopeV0.RECEIPT_FIELD:
            return tuple(
                (field_name, OperandAvailabilityV0.NOT_APPLICABLE)
                for field_name in _ITEM_FIELD_NAMES
            )
        if position.item_row_index is None:  # Protected by position validation.
            raise HardConstraintOperandIntegrityError(
                "Item-row substitution unexpectedly lacks a row index."
            )
        row = self.item_rows[position.item_row_index]
        return tuple(
            (operand.field_name, operand.availability)
            for operand in row.operands
        )


def _revalidate_input(hard_constraint_input: HardConstraintInputResultV0) -> None:
    if not isinstance(hard_constraint_input, HardConstraintInputResultV0):
        raise TypeError(
            "hard_constraint_input must be HardConstraintInputResultV0."
        )
    try:
        hard_constraint_input.__post_init__()
    except (TypeError, ValueError) as exc:
        raise HardConstraintOperandIntegrityError(
            "Hard-constraint input failed complete reconstruction."
        ) from exc


def _item_row_evidence(output: ReceiptOutput) -> tuple[ItemRowOperandEvidenceV0, ...]:
    return tuple(
        ItemRowOperandEvidenceV0(
            b2_row=row,
            operands=tuple(OperandEvidenceV0(field) for field in row.fields),
        )
        for row in output.items
    )


def _target_field(output: ReceiptOutput, field_id: str) -> StructuredField:
    matches = tuple(
        field for field in _receipt_fields(output) if field.field_id == field_id
    )
    if len(matches) != 1:
        raise HardConstraintOperandIntegrityError(
            "The prepared candidate target is not one unique stored B2 field."
        )
    return matches[0]


def _substitution_position(
    output: ReceiptOutput,
    target: StructuredField,
) -> CandidateSubstitutionPositionV0:
    if target.field_name not in _ITEM_FIELD_NAMES:
        return CandidateSubstitutionPositionV0(
            target_field=target,
            scope=CandidateSubstitutionScopeV0.RECEIPT_FIELD,
            item_row=None,
            item_row_index=None,
            item_field_index=None,
        )

    matches = tuple(
        (row_index, row)
        for row_index, row in enumerate(output.items)
        if row.row_id == target.item_row_id
    )
    if len(matches) != 1:
        raise HardConstraintOperandIntegrityError(
            "The item target does not have one unique stored B2 row relationship."
        )
    row_index, row = matches[0]
    field_matches = tuple(
        index for index, field in enumerate(row.fields) if field is target
    )
    if len(field_matches) != 1:
        raise HardConstraintOperandIntegrityError(
            "The item target is not one exact field in its declared B2 row."
        )
    return CandidateSubstitutionPositionV0(
        target_field=target,
        scope=CandidateSubstitutionScopeV0.ITEM_ROW_FIELD,
        item_row=row,
        item_row_index=row_index,
        item_field_index=field_matches[0],
    )


def _expected_candidate_audits(
    hard_constraint_input: HardConstraintInputResultV0,
) -> tuple[CandidateOperandAuditV0, ...]:
    _revalidate_input(hard_constraint_input)
    output = hard_constraint_input.receipt_output
    target = _target_field(output, hard_constraint_input.field_id)
    position = _substitution_position(output, target)
    rows = _item_row_evidence(output)
    receipt_total = OperandEvidenceV0(output.receipt_total)
    relationship = (
        RelationshipAvailabilityV0.AVAILABLE
        if position.scope is CandidateSubstitutionScopeV0.ITEM_ROW_FIELD
        else RelationshipAvailabilityV0.NOT_APPLICABLE
    )
    return tuple(
        CandidateOperandAuditV0(
            candidate=candidate,
            substitution_position=position,
            target_source_relationship=RelationshipAvailabilityV0.AVAILABLE,
            item_row_relationship=relationship,
            item_rows=rows,
            receipt_total_operand=receipt_total,
        )
        for candidate in hard_constraint_input.candidates
    )


def _require_exact_audit(
    observed: CandidateOperandAuditV0,
    expected: CandidateOperandAuditV0,
) -> None:
    try:
        observed.__post_init__()
    except (TypeError, ValueError) as exc:
        raise HardConstraintOperandIntegrityError(
            "Stored candidate operand audit failed revalidation."
        ) from exc
    if observed.candidate is not expected.candidate:
        raise HardConstraintOperandIntegrityError(
            "Candidate audit must preserve the exact prepared candidate reference."
        )
    if observed.target_field is not expected.target_field:
        raise HardConstraintOperandIntegrityError(
            "Candidate audit must preserve the exact stored B2 target field."
        )
    observed_position = observed.substitution_position
    expected_position = expected.substitution_position
    if (
        observed_position.scope is not expected_position.scope
        or observed_position.item_row is not expected_position.item_row
        or observed_position.item_row_index != expected_position.item_row_index
        or observed_position.item_field_index != expected_position.item_field_index
        or observed.target_source_relationship
        is not expected.target_source_relationship
        or observed.item_row_relationship is not expected.item_row_relationship
    ):
        raise HardConstraintOperandIntegrityError(
            "Candidate substitution or row relationship was changed."
        )
    if len(observed.item_rows) != len(expected.item_rows):
        raise HardConstraintOperandIntegrityError(
            "Candidate audit changed the detected B2 row population."
        )
    for observed_row, expected_row in zip(
        observed.item_rows, expected.item_rows, strict=True
    ):
        if observed_row.b2_row is not expected_row.b2_row:
            raise HardConstraintOperandIntegrityError(
                "Candidate audit changed a stored B2 row reference or order."
            )
        if len(observed_row.operands) != len(expected_row.operands) or any(
            left.b2_field is not right.b2_field
            for left, right in zip(
                observed_row.operands, expected_row.operands, strict=True
            )
        ):
            raise HardConstraintOperandIntegrityError(
                "Candidate audit changed raw row operands or their order."
            )
    if (
        observed.receipt_total_operand.b2_field
        is not expected.receipt_total_operand.b2_field
    ):
        raise HardConstraintOperandIntegrityError(
            "Candidate audit changed the stored receipt-total operand."
        )
    if observed != expected:
        raise HardConstraintOperandIntegrityError(
            "Candidate audit differs from deterministic reconstruction."
        )


@dataclass(frozen=True, slots=True)
class HardConstraintOperandAuditResultV0:
    """Deterministic raw-operand audit for an exact prepared candidate set."""

    hard_constraint_input: HardConstraintInputResultV0
    candidate_audits: tuple[CandidateOperandAuditV0, ...]
    component_version: str = HARD_CONSTRAINT_OPERANDS_COMPONENT_VERSION
    record_version: str = HARD_CONSTRAINT_OPERANDS_RECORD_VERSION
    _source_token_observations: tuple[_SourceTokenObservationV0, ...] = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.hard_constraint_input, HardConstraintInputResultV0):
            raise TypeError(
                "hard_constraint_input must be HardConstraintInputResultV0."
            )
        if not isinstance(self.candidate_audits, tuple) or any(
            not isinstance(audit, CandidateOperandAuditV0)
            for audit in self.candidate_audits
        ):
            raise TypeError(
                "candidate_audits must be a tuple of CandidateOperandAuditV0."
            )
        if self.component_version != HARD_CONSTRAINT_OPERANDS_COMPONENT_VERSION:
            raise ValueError("Unsupported hard-constraint operand component version.")
        if self.record_version != HARD_CONSTRAINT_OPERANDS_RECORD_VERSION:
            raise ValueError("Unsupported hard-constraint operand record version.")

        expected = _expected_candidate_audits(self.hard_constraint_input)
        current_token_observations = tuple(
            _SourceTokenObservationV0.capture(token)
            for token in self.hard_constraint_input.source_evidence.tokens
        )
        try:
            original_token_observations = self._source_token_observations
        except AttributeError:
            object.__setattr__(
                self,
                "_source_token_observations",
                current_token_observations,
            )
        else:
            if original_token_observations != current_token_observations:
                raise HardConstraintOperandIntegrityError(
                    "Stored OCR token payload changed after operand observation."
                )
        if len(self.candidate_audits) != len(expected):
            raise HardConstraintOperandIntegrityError(
                "Exactly one operand audit is required per prepared candidate."
            )
        for observed, reconstructed in zip(
            self.candidate_audits, expected, strict=True
        ):
            _require_exact_audit(observed, reconstructed)

    @property
    def overflow_audit_records(self) -> tuple[CandidateRecordV1, ...]:
        return self.hard_constraint_input.overflow_audit_records

    @property
    def blocked_audits(self) -> tuple[BlockedCandidateFinalizationAuditV0, ...]:
        return self.hard_constraint_input.blocked_audits

    @property
    def full_ledger_coverage_status(self) -> CandidateFinalizationCoverageStatusV0:
        return self.hard_constraint_input.full_ledger_coverage_status


def audit_hard_constraint_operands(
    *,
    hard_constraint_input: HardConstraintInputResultV0,
) -> HardConstraintOperandAuditResultV0:
    """Inventory exact stored B2 operands without making eligibility decisions."""

    audits = _expected_candidate_audits(hard_constraint_input)
    return HardConstraintOperandAuditResultV0(
        hard_constraint_input=hard_constraint_input,
        candidate_audits=audits,
    )
