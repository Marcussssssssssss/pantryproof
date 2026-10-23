"""Observe raw seven-slot inputs without constructing evidence features.

This component inventories only facts already stored in one validated D3
operand audit.  It makes no hard-constraint, feature, scoring, calibration,
selection, review, or persistence claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pipeline.contracts import FieldStatus, OcrSourceToken, StructuredField
from pipeline.proposed.contracts import (
    FEATURE_SLOT_ORDER,
    CandidateLimitStatus,
    CandidateRecordV1,
    CandidateRole,
    FeatureSlot,
)
from pipeline.proposed.hard_constraint_operands import (
    CandidateOperandAuditV0,
    HardConstraintOperandAuditResultV0,
    OperandAvailabilityV0,
    OperandEvidenceV0,
)


FEATURE_READINESS_COMPONENT_VERSION = "feature-input-readiness-v0"
FEATURE_READINESS_RECORD_VERSION = "feature-input-readiness-record-v0"


class FeatureInputReadinessIntegrityError(ValueError):
    """The supplied graph or a reconstructed observation is contradictory."""


class InputFactPresenceV0(str, Enum):
    """Presence of one raw input fact, never a feature-readiness verdict."""

    PRESENT = "PRESENT"
    ABSENT_IN_STORED_GRAPH = "ABSENT_IN_STORED_GRAPH"
    NOT_BOUND_BY_INPUT_CONTRACT = "NOT_BOUND_BY_INPUT_CONTRACT"
    UNDETERMINED_WITHOUT_POLICY = "UNDETERMINED_WITHOUT_POLICY"


class InputFactKindV0(str, Enum):
    """Closed observational fact kinds used in the seven ordered slots."""

    OCR_TOKEN_LITERAL = "OCR_TOKEN_LITERAL"
    OCR_TOKEN_CONFIDENCE = "OCR_TOKEN_CONFIDENCE"
    OCR_MODEL_IDENTITY = "OCR_MODEL_IDENTITY"
    B2_TARGET_FIELD = "B2_TARGET_FIELD"
    B2_EXTRACTOR_CONFIDENCE = "B2_EXTRACTOR_CONFIDENCE"
    B2_EXTRACTOR_IDENTIFIER = "B2_EXTRACTOR_IDENTIFIER"
    B2_FIELD_ASSOCIATION = "B2_FIELD_ASSOCIATION"
    C0_VALUE = "C0_VALUE"
    CANDIDATE_VALUE = "CANDIDATE_VALUE"
    SOURCE_LITERAL = "SOURCE_LITERAL"
    CANDIDATE_PROVENANCE = "CANDIDATE_PROVENANCE"
    LEXICAL_TRANSFORMATION_POLICY = "LEXICAL_TRANSFORMATION_POLICY"
    SOURCE_TOKEN_POLYGON = "SOURCE_TOKEN_POLYGON"
    SUBSTITUTION_POSITION = "SUBSTITUTION_POSITION"
    CANDIDATE_GEOMETRY_POLICY = "CANDIDATE_GEOMETRY_POLICY"
    RECEIPT_STORE_FIELD = "RECEIPT_STORE_FIELD"
    RETAILER_SNAPSHOT_BINDING = "RETAILER_SNAPSHOT_BINDING"
    ORIGINAL_B2_ITEM_OPERAND = "ORIGINAL_B2_ITEM_OPERAND"
    ORIGINAL_B2_RECEIPT_TOTAL_OPERAND = "ORIGINAL_B2_RECEIPT_TOTAL_OPERAND"
    CANDIDATE_SUBSTITUTED_ARITHMETIC = "CANDIDATE_SUBSTITUTED_ARITHMETIC"
    RECEIPT_DATE_FIELD = "RECEIPT_DATE_FIELD"
    PRICE_REFERENCE_SNAPSHOT_BINDING = "PRICE_REFERENCE_SNAPSHOT_BINDING"
    PRICE_ASSOCIATION_POLICY = "PRICE_ASSOCIATION_POLICY"


NumberFingerprintV0 = tuple[str, str, str]
PolygonFingerprintV0 = tuple[tuple[NumberFingerprintV0, NumberFingerprintV0], ...]


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")


def _require_unique_text(values: tuple[str, ...], name: str) -> None:
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{name} must contain non-empty strings.")
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must not contain duplicates.")


def _number_fingerprint(value: object) -> NumberFingerprintV0:
    value_type = type(value)
    return value_type.__module__, value_type.__qualname__, repr(value)


def _refs(*values: str | None) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value is not None))


@dataclass(frozen=True, slots=True)
class InputFactObservationV0:
    """One literal datum, relationship, absence, or unresolved policy input."""

    kind: InputFactKindV0
    presence: InputFactPresenceV0
    source_references: tuple[str, ...] = ()
    raw_texts: tuple[str, ...] = ()
    raw_number_fingerprints: tuple[NumberFingerprintV0, ...] = ()
    polygon_fingerprints: tuple[PolygonFingerprintV0, ...] = ()
    detail: str | None = None
    record_version: str = FEATURE_READINESS_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.kind, InputFactKindV0):
            raise TypeError("kind must be InputFactKindV0.")
        if not isinstance(self.presence, InputFactPresenceV0):
            raise TypeError("presence must be InputFactPresenceV0.")
        for value, name in (
            (self.source_references, "source_references"),
            (self.raw_texts, "raw_texts"),
            (self.raw_number_fingerprints, "raw_number_fingerprints"),
            (self.polygon_fingerprints, "polygon_fingerprints"),
        ):
            if not isinstance(value, tuple):
                raise TypeError(f"{name} must be a tuple.")
        _require_unique_text(self.source_references, "source_references")
        if any(not isinstance(value, str) or not value for value in self.raw_texts):
            raise ValueError("raw_texts must contain literal non-empty strings.")
        for fingerprint in self.raw_number_fingerprints:
            if (
                not isinstance(fingerprint, tuple)
                or len(fingerprint) != 3
                or any(not isinstance(value, str) or not value for value in fingerprint)
            ):
                raise ValueError("raw number fingerprints require three strings.")
        for polygon in self.polygon_fingerprints:
            if not isinstance(polygon, tuple) or len(polygon) < 3:
                raise ValueError("Observed polygons require at least three points.")
            for point in polygon:
                if not isinstance(point, tuple) or len(point) != 2:
                    raise ValueError("Observed polygon points require x/y fingerprints.")
                for fingerprint in point:
                    if not isinstance(fingerprint, tuple) or len(fingerprint) != 3:
                        raise ValueError("Observed coordinates require number fingerprints.")

        if self.presence is InputFactPresenceV0.PRESENT:
            if self.detail is not None:
                raise ValueError("A present raw fact has no absence/policy detail.")
            if not any(
                (
                    self.source_references,
                    self.raw_texts,
                    self.raw_number_fingerprints,
                    self.polygon_fingerprints,
                )
            ):
                raise ValueError("A present fact must preserve stored input material.")
        else:
            _require_text(self.detail or "", "detail")
            if self.presence is InputFactPresenceV0.NOT_BOUND_BY_INPUT_CONTRACT:
                if any(
                    (
                        self.source_references,
                        self.raw_texts,
                        self.raw_number_fingerprints,
                        self.polygon_fingerprints,
                    )
                ):
                    raise ValueError(
                        "An unbound input cannot claim stored evidence or resources."
                    )
        if self.record_version != FEATURE_READINESS_RECORD_VERSION:
            raise ValueError("Unsupported feature-readiness fact version.")


@dataclass(frozen=True, slots=True)
class FeatureSlotInputObservationV0:
    """Ordered raw input facts associated with one conceptual feature slot."""

    slot: FeatureSlot
    facts: tuple[InputFactObservationV0, ...]
    record_version: str = FEATURE_READINESS_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.slot, FeatureSlot):
            raise TypeError("slot must be an existing FeatureSlot.")
        if not isinstance(self.facts, tuple) or not self.facts:
            raise ValueError("Each slot requires a non-empty tuple of input facts.")
        if any(not isinstance(item, InputFactObservationV0) for item in self.facts):
            raise TypeError("facts must contain InputFactObservationV0 records.")
        for item in self.facts:
            item.__post_init__()
        identities = tuple((item.kind, item.source_references) for item in self.facts)
        if len(identities) != len(set(identities)):
            raise ValueError("A slot cannot duplicate the same input-fact identity.")
        if self.record_version != FEATURE_READINESS_RECORD_VERSION:
            raise ValueError("Unsupported feature-readiness slot version.")


@dataclass(frozen=True, slots=True)
class CandidateFeatureInputObservationV0:
    """Seven-slot raw input inventory for one exact retained candidate."""

    operand_audit: HardConstraintOperandAuditResultV0
    candidate_audit: CandidateOperandAuditV0
    candidate: CandidateRecordV1
    slots: tuple[FeatureSlotInputObservationV0, ...]
    record_version: str = FEATURE_READINESS_RECORD_VERSION
    _original_operand_audit_reference: HardConstraintOperandAuditResultV0 = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.operand_audit, HardConstraintOperandAuditResultV0):
            raise TypeError("operand_audit must be HardConstraintOperandAuditResultV0.")
        try:
            original_operand_audit = self._original_operand_audit_reference
        except AttributeError:
            object.__setattr__(
                self,
                "_original_operand_audit_reference",
                self.operand_audit,
            )
        else:
            if self.operand_audit is not original_operand_audit:
                raise FeatureInputReadinessIntegrityError(
                    "Candidate observation's exact D3 operand-audit reference changed."
                )
        if not isinstance(self.candidate_audit, CandidateOperandAuditV0):
            raise TypeError("candidate_audit must be CandidateOperandAuditV0.")
        if not isinstance(self.candidate, CandidateRecordV1):
            raise TypeError("candidate must be CandidateRecordV1.")
        try:
            self.operand_audit.__post_init__()
            self.candidate_audit.__post_init__()
            self.candidate.__post_init__()
        except (TypeError, ValueError) as exc:
            raise FeatureInputReadinessIntegrityError(
                "Candidate input evidence failed upstream revalidation."
            ) from exc
        if not any(
            item is self.candidate_audit
            for item in self.operand_audit.candidate_audits
        ):
            raise FeatureInputReadinessIntegrityError(
                "Candidate observation must retain an exact supplied operand audit member."
            )
        if self.candidate is not self.candidate_audit.candidate:
            raise FeatureInputReadinessIntegrityError(
                "Candidate observation must retain the exact operand candidate."
            )
        if self.candidate.limit_status is not CandidateLimitStatus.RETAINED:
            raise FeatureInputReadinessIntegrityError(
                "Overflow candidates cannot receive feature-input observations."
            )
        if not isinstance(self.slots, tuple) or any(
            not isinstance(item, FeatureSlotInputObservationV0)
            for item in self.slots
        ):
            raise TypeError("slots must contain FeatureSlotInputObservationV0 records.")
        if tuple(item.slot for item in self.slots) != FEATURE_SLOT_ORDER:
            raise FeatureInputReadinessIntegrityError(
                "Candidate observations require exactly seven slots in contract order."
            )
        for item in self.slots:
            item.__post_init__()
        expected = _slot_observations(
            self.candidate_audit,
            self.operand_audit.hard_constraint_input,
        )
        if self.slots != expected:
            raise FeatureInputReadinessIntegrityError(
                "Candidate slot observations differ from deterministic reconstruction."
            )
        if self.record_version != FEATURE_READINESS_RECORD_VERSION:
            raise ValueError("Unsupported candidate feature-readiness version.")


@dataclass(frozen=True, slots=True)
class FeatureInputReadinessResultV0:
    """Deterministic seven-slot observations for an exact D3 operand audit."""

    operand_audit: HardConstraintOperandAuditResultV0
    candidate_observations: tuple[CandidateFeatureInputObservationV0, ...]
    component_version: str = FEATURE_READINESS_COMPONENT_VERSION
    record_version: str = FEATURE_READINESS_RECORD_VERSION
    _primitive_observation: tuple[Any, ...] = field(
        init=False,
        repr=False,
        compare=False,
    )
    _original_operand_audit_reference: HardConstraintOperandAuditResultV0 = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.operand_audit, HardConstraintOperandAuditResultV0):
            raise TypeError("operand_audit must be HardConstraintOperandAuditResultV0.")
        try:
            original_operand_audit = self._original_operand_audit_reference
        except AttributeError:
            object.__setattr__(
                self,
                "_original_operand_audit_reference",
                self.operand_audit,
            )
        else:
            if self.operand_audit is not original_operand_audit:
                raise FeatureInputReadinessIntegrityError(
                    "Result's exact D3 operand-audit reference changed."
                )
        if not isinstance(self.candidate_observations, tuple) or any(
            not isinstance(item, CandidateFeatureInputObservationV0)
            for item in self.candidate_observations
        ):
            raise TypeError(
                "candidate_observations must contain candidate input records."
            )
        if self.component_version != FEATURE_READINESS_COMPONENT_VERSION:
            raise ValueError("Unsupported feature-readiness component version.")
        if self.record_version != FEATURE_READINESS_RECORD_VERSION:
            raise ValueError("Unsupported feature-readiness result version.")

        try:
            self.operand_audit.__post_init__()
        except (TypeError, ValueError) as exc:
            raise FeatureInputReadinessIntegrityError(
                "Supplied D3 operand audit failed complete revalidation."
            ) from exc
        expected = _candidate_observations(self.operand_audit)
        if len(self.candidate_observations) != len(expected):
            raise FeatureInputReadinessIntegrityError(
                "Exactly one observation is required per retained candidate."
            )
        for observed, reconstructed, upstream in zip(
            self.candidate_observations,
            expected,
            self.operand_audit.candidate_audits,
            strict=True,
        ):
            observed.__post_init__()
            if observed.operand_audit is not self.operand_audit:
                raise FeatureInputReadinessIntegrityError(
                    "Candidate observations must reference the result's exact D3 audit."
                )
            if observed.candidate_audit is not upstream:
                raise FeatureInputReadinessIntegrityError(
                    "Candidate observations must retain exact upstream audit references."
                )
            if observed != reconstructed:
                raise FeatureInputReadinessIntegrityError(
                    "Candidate observations differ from deterministic reconstruction."
                )

        candidates = tuple(item.candidate for item in self.candidate_observations)
        if not candidates or candidates[0].role is not CandidateRole.ORIGINAL:
            raise FeatureInputReadinessIntegrityError("Permanent c0 must remain first.")
        if any(item.limit_status is not CandidateLimitStatus.RETAINED for item in candidates):
            raise FeatureInputReadinessIntegrityError(
                "Only retained candidates belong to the observation population."
            )
        overflow_ids = {
            item.candidate_id for item in self.operand_audit.overflow_audit_records
        }
        if overflow_ids.intersection(item.candidate_id for item in candidates):
            raise FeatureInputReadinessIntegrityError(
                "Overflow candidates cannot enter feature-input observations."
            )

        current = _primitive_payload(self.candidate_observations)
        try:
            original = self._primitive_observation
        except AttributeError:
            object.__setattr__(self, "_primitive_observation", current)
        else:
            if original != current:
                raise FeatureInputReadinessIntegrityError(
                    "Stored feature-input observations changed after construction."
                )


def _present(
    kind: InputFactKindV0,
    *,
    references: tuple[str, ...] = (),
    texts: tuple[str, ...] = (),
    numbers: tuple[object, ...] = (),
    polygons: tuple[tuple[tuple[object, object], ...], ...] = (),
) -> InputFactObservationV0:
    return InputFactObservationV0(
        kind=kind,
        presence=InputFactPresenceV0.PRESENT,
        source_references=_refs(*references),
        raw_texts=texts,
        raw_number_fingerprints=tuple(_number_fingerprint(value) for value in numbers),
        polygon_fingerprints=tuple(
            tuple(
                (_number_fingerprint(x), _number_fingerprint(y))
                for x, y in polygon
            )
            for polygon in polygons
        ),
    )


def _nonpresent(
    kind: InputFactKindV0,
    presence: InputFactPresenceV0,
    detail: str,
    *,
    references: tuple[str, ...] = (),
    texts: tuple[str, ...] = (),
) -> InputFactObservationV0:
    return InputFactObservationV0(
        kind=kind,
        presence=presence,
        source_references=_refs(*references),
        raw_texts=texts,
        detail=detail,
    )


def _token_literal(token: OcrSourceToken, kind: InputFactKindV0) -> InputFactObservationV0:
    return _present(
        kind,
        references=(token.token_id,),
        texts=(token.original_text,),
    )


def _token_confidence(token: OcrSourceToken) -> InputFactObservationV0:
    if token.raw_confidence is None:
        return _nonpresent(
            InputFactKindV0.OCR_TOKEN_CONFIDENCE,
            InputFactPresenceV0.ABSENT_IN_STORED_GRAPH,
            "The associated OCR token stores no model-native confidence.",
            references=(token.token_id,),
        )
    return _present(
        InputFactKindV0.OCR_TOKEN_CONFIDENCE,
        references=(token.token_id,),
        numbers=(token.raw_confidence,),
    )


def _field_fact(
    field_value: StructuredField,
    kind: InputFactKindV0,
) -> InputFactObservationV0:
    references = _refs(
        field_value.field_id,
        field_value.item_row_id,
        *field_value.source_token_ids,
    )
    texts = [field_value.field_name.value, field_value.status.value]
    if field_value.value is not None:
        texts.append(field_value.value)
    if field_value.unresolved_reason is not None:
        texts.append(field_value.unresolved_reason)
    if field_value.status is FieldStatus.EXTRACTED:
        return _present(kind, references=references, texts=tuple(texts))
    return _nonpresent(
        kind,
        InputFactPresenceV0.ABSENT_IN_STORED_GRAPH,
        "The stored receipt field has no extracted value.",
        references=references,
        texts=tuple(texts),
    )


def _operand_fact(
    operand: OperandEvidenceV0,
    kind: InputFactKindV0,
    *,
    row_id: str | None = None,
) -> InputFactObservationV0:
    references = _refs(
        operand.field_id,
        row_id,
        *operand.source_token_ids,
    )
    texts = [
        operand.field_name.value,
        operand.original_status.value,
        operand.availability.value,
    ]
    if operand.raw_value is not None:
        texts.append(operand.raw_value)
    if operand.unresolved_reason is not None:
        texts.append(operand.unresolved_reason)
    if operand.availability is OperandAvailabilityV0.AVAILABLE:
        return _present(kind, references=references, texts=tuple(texts))
    return _nonpresent(
        kind,
        InputFactPresenceV0.ABSENT_IN_STORED_GRAPH,
        "The original stored B2 operand has no extracted raw value.",
        references=references,
        texts=tuple(texts),
    )


def _substitution_fact(audit: CandidateOperandAuditV0) -> InputFactObservationV0:
    position = audit.substitution_position
    references = _refs(
        position.target_field.field_id,
        position.item_row.row_id if position.item_row is not None else None,
    )
    texts = [position.scope.value]
    numbers: list[object] = []
    for value in (position.item_row_index, position.item_field_index):
        if value is not None:
            numbers.append(value)
    return _present(
        InputFactKindV0.SUBSTITUTION_POSITION,
        references=references,
        texts=tuple(texts),
        numbers=tuple(numbers),
    )


def _slot_observations(
    audit: CandidateOperandAuditV0,
    context: Any,
) -> tuple[FeatureSlotInputObservationV0, ...]:
    candidate = audit.candidate
    method = context.method_ready_field
    output = context.receipt_output
    tokens = method.source_tokens

    q_o_facts = (
        *(_token_literal(token, InputFactKindV0.OCR_TOKEN_LITERAL) for token in tokens),
        *(_token_confidence(token) for token in tokens),
        _nonpresent(
            InputFactKindV0.OCR_MODEL_IDENTITY,
            InputFactPresenceV0.NOT_BOUND_BY_INPUT_CONTRACT,
            "The D3 input contract carries OCR evidence but no authenticated OCR model identity.",
        ),
    )

    target = audit.target_field
    target_references = _refs(
        target.field_id,
        target.item_row_id,
        *target.source_token_ids,
    )
    q_e_confidence = (
        _nonpresent(
            InputFactKindV0.B2_EXTRACTOR_CONFIDENCE,
            InputFactPresenceV0.ABSENT_IN_STORED_GRAPH,
            "The exact B2 target field stores confidence=None.",
            references=(target.field_id,),
        )
        if target.confidence is None
        else _present(
            InputFactKindV0.B2_EXTRACTOR_CONFIDENCE,
            references=(target.field_id,),
            numbers=(target.confidence,),
        )
    )
    q_e_facts = (
        _field_fact(target, InputFactKindV0.B2_TARGET_FIELD),
        q_e_confidence,
        _present(
            InputFactKindV0.B2_EXTRACTOR_IDENTIFIER,
            texts=(output.extractor_version,),
        ),
        _present(
            InputFactKindV0.B2_FIELD_ASSOCIATION,
            references=target_references,
            texts=(audit.target_source_relationship.value, audit.item_row_relationship.value),
        ),
    )

    provenance_facts = tuple(
        _present(
            InputFactKindV0.CANDIDATE_PROVENANCE,
            references=_refs(
                item.provenance_id,
                item.candidate_id,
                *item.source_token_ids,
                item.resource_snapshot_id,
            ),
            texts=tuple(
                value
                for value in (
                    item.source_kind.value,
                    item.original_observed_value,
                    item.source_order_relationship,
                    item.generic_rule_id,
                    item.resource_snapshot_id,
                )
                if value is not None
            ),
            numbers=(
                ()
                if item.source_order_position is None
                else (item.source_order_position,)
            ),
        )
        for item in candidate.provenance
    )
    a_l_facts = (
        _present(
            InputFactKindV0.C0_VALUE,
            references=(candidate.c0_candidate_id,),
            texts=(method.c0_value,),
        ),
        _present(
            InputFactKindV0.CANDIDATE_VALUE,
            references=(candidate.candidate_id,),
            texts=(candidate.value,),
        ),
        *(_token_literal(token, InputFactKindV0.SOURCE_LITERAL) for token in tokens),
        *provenance_facts,
        _nonpresent(
            InputFactKindV0.LEXICAL_TRANSFORMATION_POLICY,
            InputFactPresenceV0.UNDETERMINED_WITHOUT_POLICY,
            "No approved lexical feature transformation or terminology support rule is supplied.",
            references=(candidate.candidate_id, candidate.c0_candidate_id),
        ),
    )

    polygon_facts = tuple(
        _present(
            InputFactKindV0.SOURCE_TOKEN_POLYGON,
            references=(token.token_id,),
            polygons=(tuple((point.x, point.y) for point in token.polygon),),
        )
        for token in tokens
    )
    a_y_facts = (
        *polygon_facts,
        _present(
            InputFactKindV0.B2_FIELD_ASSOCIATION,
            references=target_references,
            texts=(audit.target_source_relationship.value, audit.item_row_relationship.value),
        ),
        _substitution_fact(audit),
        _nonpresent(
            InputFactKindV0.CANDIDATE_GEOMETRY_POLICY,
            InputFactPresenceV0.UNDETERMINED_WITHOUT_POLICY,
            "Stored geometry is not an approved candidate-specific layout transformation.",
            references=(candidate.candidate_id, target.field_id),
        ),
    )

    s_r_facts = (
        _field_fact(output.store_name, InputFactKindV0.RECEIPT_STORE_FIELD),
        _present(
            InputFactKindV0.CANDIDATE_VALUE,
            references=(candidate.candidate_id,),
            texts=(candidate.value,),
        ),
        _nonpresent(
            InputFactKindV0.RETAILER_SNAPSHOT_BINDING,
            InputFactPresenceV0.NOT_BOUND_BY_INPUT_CONTRACT,
            "The D3 input contract binds no approved retailer-support snapshot; this makes no global resource claim.",
        ),
    )

    arithmetic_facts = tuple(
        _operand_fact(
            operand,
            InputFactKindV0.ORIGINAL_B2_ITEM_OPERAND,
            row_id=row.row_id,
        )
        for row in audit.item_rows
        for operand in row.operands
    )
    s_a_facts = (
        _substitution_fact(audit),
        *arithmetic_facts,
        _operand_fact(
            audit.receipt_total_operand,
            InputFactKindV0.ORIGINAL_B2_RECEIPT_TOTAL_OPERAND,
        ),
        _nonpresent(
            InputFactKindV0.CANDIDATE_SUBSTITUTED_ARITHMETIC,
            InputFactPresenceV0.UNDETERMINED_WITHOUT_POLICY,
            "No candidate substitution, parsing, equation, tolerance, rounding, exception, or completeness policy was applied.",
            references=(candidate.candidate_id, target.field_id),
        ),
    )

    s_p_facts = (
        _field_fact(output.store_name, InputFactKindV0.RECEIPT_STORE_FIELD),
        _field_fact(output.purchase_date, InputFactKindV0.RECEIPT_DATE_FIELD),
        _present(
            InputFactKindV0.CANDIDATE_VALUE,
            references=_refs(candidate.candidate_id, target.item_row_id),
            texts=(candidate.value,),
        ),
        _nonpresent(
            InputFactKindV0.PRICE_REFERENCE_SNAPSHOT_BINDING,
            InputFactPresenceV0.NOT_BOUND_BY_INPUT_CONTRACT,
            "The D3 input contract binds no versioned price-reference snapshot; this makes no global resource claim.",
        ),
        _nonpresent(
            InputFactKindV0.PRICE_ASSOCIATION_POLICY,
            InputFactPresenceV0.UNDETERMINED_WITHOUT_POLICY,
            "No approved candidate-to-price association or discrepancy policy was applied.",
            references=_refs(candidate.candidate_id, target.item_row_id),
        ),
    )

    facts_by_slot = {
        FeatureSlot.OCR_EVIDENCE: q_o_facts,
        FeatureSlot.EXTRACTOR_EVIDENCE: q_e_facts,
        FeatureSlot.LEXICAL_AGREEMENT: a_l_facts,
        FeatureSlot.LAYOUT_AGREEMENT: a_y_facts,
        FeatureSlot.RETAILER_SUPPORT: s_r_facts,
        FeatureSlot.ARITHMETIC_SUPPORT: s_a_facts,
        FeatureSlot.PRICE_REFERENCE_SUPPORT: s_p_facts,
    }
    return tuple(
        FeatureSlotInputObservationV0(slot=slot, facts=facts_by_slot[slot])
        for slot in FEATURE_SLOT_ORDER
    )


def _candidate_observations(
    operand_audit: HardConstraintOperandAuditResultV0,
) -> tuple[CandidateFeatureInputObservationV0, ...]:
    context = operand_audit.hard_constraint_input
    return tuple(
        CandidateFeatureInputObservationV0(
            operand_audit=operand_audit,
            candidate_audit=audit,
            candidate=audit.candidate,
            slots=_slot_observations(audit, context),
        )
        for audit in operand_audit.candidate_audits
    )


def _primitive_payload(
    observations: tuple[CandidateFeatureInputObservationV0, ...],
) -> tuple[Any, ...]:
    return tuple(
        (
            item.candidate.candidate_id,
            item.candidate.value,
            tuple(
                (
                    slot.slot.value,
                    tuple(
                        (
                            fact.kind.value,
                            fact.presence.value,
                            fact.source_references,
                            fact.raw_texts,
                            fact.raw_number_fingerprints,
                            fact.polygon_fingerprints,
                            fact.detail,
                        )
                        for fact in slot.facts
                    ),
                )
                for slot in item.slots
            ),
        )
        for item in observations
    )


def inspect_feature_input_readiness(
    *,
    operand_audit: HardConstraintOperandAuditResultV0,
) -> FeatureInputReadinessResultV0:
    """Inventory stored seven-slot inputs without constructing features."""

    if not isinstance(operand_audit, HardConstraintOperandAuditResultV0):
        raise TypeError("operand_audit must be HardConstraintOperandAuditResultV0.")
    try:
        operand_audit.__post_init__()
    except (TypeError, ValueError) as exc:
        raise FeatureInputReadinessIntegrityError(
            "Supplied D3 operand audit failed complete revalidation."
        ) from exc
    observations = _candidate_observations(operand_audit)
    return FeatureInputReadinessResultV0(
        operand_audit=operand_audit,
        candidate_observations=observations,
    )
