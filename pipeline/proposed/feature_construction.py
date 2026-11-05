"""Purchase-date seven-slot feature construction V0.

This module consumes one exact in-process D3 operand audit and the matching
source-bound V2 hard-constraint results.  It constructs feature vectors only
for constraint-eligible purchase-date candidates.  It does not score,
calibrate, select, route review, or authorize persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from math import isfinite

from pipeline.contracts import ReceiptFieldName
from pipeline.proposed.contracts import (
    FEATURE_SCHEMA_ID_V1,
    FEATURE_SLOT_ORDER,
    CandidateRecordV1,
    CandidateRole,
    ConfigurationRefV1,
    FeatureSlot,
    FeatureValueV1,
)
from pipeline.proposed.feature_readiness import (
    FeatureInputReadinessResultV0,
    inspect_feature_input_readiness,
)
from pipeline.proposed.hard_constraint_contracts_v2 import (
    ConstraintAggregateStateV2,
    ConstraintResultV2,
)
from pipeline.proposed.hard_constraint_operands import (
    CandidateOperandAuditV0,
    HardConstraintOperandAuditResultV0,
)


FEATURE_CONSTRUCTION_COMPONENT_VERSION = "feature-construction-v0"
FEATURE_CONSTRUCTION_RECORD_VERSION = "feature-construction-record-v0"
NOT_APPLICABLE_VALUE = "NOT_APPLICABLE"
_DOMAIN_MINIMUM = Decimal("0")
_DOMAIN_MAXIMUM = Decimal("1")


class FeatureConstructionError(ValueError):
    """Base error for the bounded feature-construction component."""


class FeatureConstructionIntegrityError(FeatureConstructionError):
    """Stored source evidence or candidate-set relationships are contradictory."""


class FeatureConstructionConfigurationError(FeatureConstructionError):
    """The supplied graph is outside the approved V0 configuration."""


class FeatureValueAvailabilityV0(str, Enum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FeatureValueReasonV0(str, Enum):
    OCR_CONFIDENCE_MISSING = "OCR_CONFIDENCE_MISSING"
    EXTRACTOR_CONFIDENCE_MISSING = "EXTRACTOR_CONFIDENCE_MISSING"
    LAYOUT_AGREEMENT_UNAVAILABLE_V0 = "LAYOUT_AGREEMENT_UNAVAILABLE_V0"
    RETAILER_RESOURCE_UNAVAILABLE = "RETAILER_RESOURCE_UNAVAILABLE"
    PURCHASE_DATE_ARITHMETIC_NOT_APPLICABLE = (
        "PURCHASE_DATE_ARITHMETIC_NOT_APPLICABLE"
    )
    PURCHASE_DATE_PRICE_NOT_APPLICABLE = "PURCHASE_DATE_PRICE_NOT_APPLICABLE"


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")


def _unique_references(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _decimal_confidence(value: object, source_name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise FeatureConstructionIntegrityError(
            f"Present confidence {source_name!r} must be a non-Boolean number."
        )
    if isinstance(value, float) and not isfinite(value):
        raise FeatureConstructionIntegrityError(
            f"Present confidence {source_name!r} must be finite."
        )
    converted = value if isinstance(value, Decimal) else Decimal(str(value))
    if not converted.is_finite():
        raise FeatureConstructionIntegrityError(
            f"Present confidence {source_name!r} must be finite."
        )
    if converted < _DOMAIN_MINIMUM or converted > _DOMAIN_MAXIMUM:
        raise FeatureConstructionIntegrityError(
            f"Present confidence {source_name!r} lies outside the provisional [0, 1] feature domain."
        )
    return converted


@dataclass(frozen=True, slots=True)
class FeatureSlotValueV0:
    """One typed slot value with explicit availability and provenance."""

    slot: FeatureSlot
    value: FeatureValueV1
    availability: FeatureValueAvailabilityV0
    provenance_references: tuple[str, ...]
    reason: FeatureValueReasonV0 | None = None
    record_version: str = FEATURE_CONSTRUCTION_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.slot, FeatureSlot):
            raise TypeError("slot must be FeatureSlot.")
        if not isinstance(self.availability, FeatureValueAvailabilityV0):
            raise TypeError("availability must be FeatureValueAvailabilityV0.")
        if self.reason is not None and not isinstance(
            self.reason, FeatureValueReasonV0
        ):
            raise TypeError("reason must be FeatureValueReasonV0 or None.")
        if not isinstance(self.provenance_references, tuple) or any(
            not isinstance(reference, str) or not reference.strip()
            for reference in self.provenance_references
        ):
            raise ValueError("provenance_references must contain non-empty strings.")
        if len(self.provenance_references) != len(set(self.provenance_references)):
            raise ValueError("provenance_references must not contain duplicates.")

        if isinstance(self.value, Decimal):
            if not self.value.is_finite():
                raise ValueError("Decimal feature values must be finite.")
        elif self.value is not None and not isinstance(self.value, (str, bool)):
            raise TypeError("Feature values must be Decimal, string, Boolean, or None.")
        if isinstance(self.value, str):
            _require_text(self.value, "value")

        if self.availability is FeatureValueAvailabilityV0.MISSING:
            if self.value is not None or self.reason is None:
                raise ValueError("A missing feature requires null value and a reason.")
        elif self.availability is FeatureValueAvailabilityV0.NOT_APPLICABLE:
            if self.value != NOT_APPLICABLE_VALUE or self.reason is None:
                raise ValueError(
                    "A non-applicable feature requires its categorical value and reason."
                )
        else:
            if self.value is None or self.reason is not None:
                raise ValueError(
                    "An available feature requires a value and no missingness reason."
                )
        if self.record_version != FEATURE_CONSTRUCTION_RECORD_VERSION:
            raise ValueError("Unsupported feature-slot record version.")

    @property
    def is_missing(self) -> bool:
        return self.value is None


def _slot_values(
    operand_audit: HardConstraintOperandAuditResultV0,
    candidate_audit: CandidateOperandAuditV0,
) -> tuple[FeatureSlotValueV0, ...]:
    context = operand_audit.hard_constraint_input
    candidate = candidate_audit.candidate
    target = candidate_audit.target_field
    tokens = context.method_ready_field.source_tokens

    ocr_values: list[Decimal] = []
    ocr_missing = False
    for token in tokens:
        if token.raw_confidence is None:
            ocr_missing = True
        else:
            ocr_values.append(_decimal_confidence(token.raw_confidence, token.token_id))
    q_o = FeatureSlotValueV0(
        slot=FeatureSlot.OCR_EVIDENCE,
        value=None if ocr_missing else min(ocr_values),
        availability=(
            FeatureValueAvailabilityV0.MISSING
            if ocr_missing
            else FeatureValueAvailabilityV0.AVAILABLE
        ),
        provenance_references=tuple(token.token_id for token in tokens),
        reason=(
            FeatureValueReasonV0.OCR_CONFIDENCE_MISSING if ocr_missing else None
        ),
    )

    extractor_confidence = target.confidence
    q_e = FeatureSlotValueV0(
        slot=FeatureSlot.EXTRACTOR_EVIDENCE,
        value=(
            None
            if extractor_confidence is None
            else _decimal_confidence(extractor_confidence, target.field_id)
        ),
        availability=(
            FeatureValueAvailabilityV0.MISSING
            if extractor_confidence is None
            else FeatureValueAvailabilityV0.AVAILABLE
        ),
        provenance_references=_unique_references(
            (target.field_id, context.receipt_output.extractor_version)
        ),
        reason=(
            FeatureValueReasonV0.EXTRACTOR_CONFIDENCE_MISSING
            if extractor_confidence is None
            else None
        ),
    )

    if candidate.role is CandidateRole.ORIGINAL:
        lexical_value = Decimal("1")
        rank_reference: tuple[str, ...] = ()
    else:
        rank = candidate.preliminary_rank
        if rank is None:
            raise FeatureConstructionIntegrityError(
                "An altered retained candidate lost its preliminary rank."
            )
        lexical_value = rank.normalized_edit_similarity
        rank_reference = () if rank.tie_group_id is None else (rank.tie_group_id,)
    a_l = FeatureSlotValueV0(
        slot=FeatureSlot.LEXICAL_AGREEMENT,
        value=lexical_value,
        availability=FeatureValueAvailabilityV0.AVAILABLE,
        provenance_references=_unique_references(
            (
                candidate.candidate_id,
                candidate.c0_candidate_id,
                *(item.provenance_id for item in candidate.provenance),
                *rank_reference,
            )
        ),
    )

    a_y = FeatureSlotValueV0(
        slot=FeatureSlot.LAYOUT_AGREEMENT,
        value=None,
        availability=FeatureValueAvailabilityV0.MISSING,
        provenance_references=_unique_references(
            (
                target.field_id,
                *((target.item_row_id,) if target.item_row_id is not None else ()),
                *target.source_token_ids,
            )
        ),
        reason=FeatureValueReasonV0.LAYOUT_AGREEMENT_UNAVAILABLE_V0,
    )

    s_r = FeatureSlotValueV0(
        slot=FeatureSlot.RETAILER_SUPPORT,
        value=None,
        availability=FeatureValueAvailabilityV0.MISSING,
        provenance_references=(),
        reason=FeatureValueReasonV0.RETAILER_RESOURCE_UNAVAILABLE,
    )

    applicability_references = _unique_references(
        (target.field_id, candidate.candidate_id)
    )
    s_a = FeatureSlotValueV0(
        slot=FeatureSlot.ARITHMETIC_SUPPORT,
        value=NOT_APPLICABLE_VALUE,
        availability=FeatureValueAvailabilityV0.NOT_APPLICABLE,
        provenance_references=applicability_references,
        reason=FeatureValueReasonV0.PURCHASE_DATE_ARITHMETIC_NOT_APPLICABLE,
    )
    s_p = FeatureSlotValueV0(
        slot=FeatureSlot.PRICE_REFERENCE_SUPPORT,
        value=NOT_APPLICABLE_VALUE,
        availability=FeatureValueAvailabilityV0.NOT_APPLICABLE,
        provenance_references=applicability_references,
        reason=FeatureValueReasonV0.PURCHASE_DATE_PRICE_NOT_APPLICABLE,
    )
    return q_o, q_e, a_l, a_y, s_r, s_a, s_p


def _capture_reference(record: object, attribute: str, current: object, message: str) -> None:
    try:
        original = getattr(record, attribute)
    except AttributeError:
        object.__setattr__(record, attribute, current)
    else:
        if original is not current:
            raise FeatureConstructionIntegrityError(message)


@dataclass(frozen=True, slots=True)
class CandidateFeatureVectorV0:
    """Seven-slot values for one exact eligible D3 candidate."""

    operand_audit: HardConstraintOperandAuditResultV0
    candidate_audit: CandidateOperandAuditV0
    constraint_result: ConstraintResultV2
    candidate: CandidateRecordV1
    theta_a_reference: ConfigurationRefV1
    slot_values: tuple[FeatureSlotValueV0, ...]
    feature_schema_id: str = FEATURE_SCHEMA_ID_V1
    record_version: str = FEATURE_CONSTRUCTION_RECORD_VERSION
    _original_operand_audit_reference: HardConstraintOperandAuditResultV0 = field(
        init=False, repr=False, compare=False
    )
    _original_candidate_audit_reference: CandidateOperandAuditV0 = field(
        init=False, repr=False, compare=False
    )
    _original_constraint_result_reference: ConstraintResultV2 = field(
        init=False, repr=False, compare=False
    )
    _original_candidate_reference: CandidateRecordV1 = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        _capture_reference(
            self,
            "_original_operand_audit_reference",
            self.operand_audit,
            "The exact D3 operand-audit reference changed.",
        )
        _capture_reference(
            self,
            "_original_candidate_audit_reference",
            self.candidate_audit,
            "The exact D3 candidate-audit reference changed.",
        )
        _capture_reference(
            self,
            "_original_constraint_result_reference",
            self.constraint_result,
            "The exact V2 constraint-result reference changed.",
        )
        _capture_reference(
            self,
            "_original_candidate_reference",
            self.candidate,
            "The exact D3 candidate reference changed.",
        )
        if not isinstance(self.slot_values, tuple) or any(
            not isinstance(slot, FeatureSlotValueV0) for slot in self.slot_values
        ):
            raise TypeError("slot_values must contain FeatureSlotValueV0 records.")
        try:
            self.operand_audit.__post_init__()
            self.candidate_audit.__post_init__()
            self.constraint_result.__post_init__()
            self.candidate.__post_init__()
        except (AttributeError, TypeError, ValueError) as exc:
            raise FeatureConstructionIntegrityError(
                "Feature-vector upstream evidence failed revalidation."
            ) from exc

        if not any(
            stored is self.candidate_audit
            for stored in self.operand_audit.candidate_audits
        ):
            raise FeatureConstructionIntegrityError(
                "The candidate audit is not an exact D3 aggregate member."
            )
        if self.candidate is not self.candidate_audit.candidate:
            raise FeatureConstructionIntegrityError(
                "The feature candidate is not the exact D3 candidate."
            )
        c0_candidate = self.operand_audit.candidate_audits[0].candidate
        if (
            self.constraint_result.candidate is not self.candidate
            or self.constraint_result.c0_candidate is not c0_candidate
        ):
            raise FeatureConstructionIntegrityError(
                "The V2 result changed exact candidate or permanent-c0 identity."
            )
        if (
            self.constraint_result.aggregate_state
            is not ConstraintAggregateStateV2.ELIGIBLE
        ):
            raise FeatureConstructionIntegrityError(
                "Only an ELIGIBLE V2 candidate may receive a feature vector."
            )
        upstream_theta = self.operand_audit.hard_constraint_input.theta_a_ref
        if (
            self.theta_a_reference != upstream_theta
            or self.constraint_result.theta_a_reference != upstream_theta
        ):
            raise FeatureConstructionConfigurationError(
                "Feature, D3, and V2 Theta_A references must match completely."
            )
        if self.feature_schema_id != FEATURE_SCHEMA_ID_V1:
            raise FeatureConstructionConfigurationError(
                "The approved seven-slot feature schema identifier is required."
            )
        if tuple(slot.slot for slot in self.slot_values) != FEATURE_SLOT_ORDER:
            raise FeatureConstructionIntegrityError(
                "Feature values must preserve exact Equation 4.1 order."
            )
        for slot in self.slot_values:
            slot.__post_init__()
        expected = _slot_values(self.operand_audit, self.candidate_audit)
        if self.slot_values != expected:
            raise FeatureConstructionIntegrityError(
                "Stored feature values differ from deterministic source reconstruction."
            )
        if self.record_version != FEATURE_CONSTRUCTION_RECORD_VERSION:
            raise ValueError("Unsupported candidate-feature-vector version.")

    @property
    def feature_slots(self) -> tuple[FeatureSlot, ...]:
        return tuple(slot.slot for slot in self.slot_values)

    @property
    def feature_values(self) -> tuple[FeatureValueV1, ...]:
        return tuple(slot.value for slot in self.slot_values)

    @property
    def feature_provenance_refs(self) -> tuple[tuple[str, ...], ...]:
        return tuple(slot.provenance_references for slot in self.slot_values)

    @property
    def missingness_mask(self) -> tuple[bool, ...]:
        return tuple(slot.is_missing for slot in self.slot_values)


def _validated_candidate_set(
    operand_audit: HardConstraintOperandAuditResultV0,
    constraint_results: tuple[ConstraintResultV2, ...],
) -> tuple[tuple[CandidateOperandAuditV0, ConstraintResultV2], ...]:
    if not isinstance(operand_audit, HardConstraintOperandAuditResultV0):
        raise TypeError("operand_audit must be HardConstraintOperandAuditResultV0.")
    if not isinstance(constraint_results, tuple) or any(
        not isinstance(result, ConstraintResultV2) for result in constraint_results
    ):
        raise TypeError("constraint_results must be a tuple of ConstraintResultV2.")
    try:
        operand_audit.__post_init__()
    except (AttributeError, TypeError, ValueError) as exc:
        raise FeatureConstructionIntegrityError(
            "The supplied D3 operand audit failed complete revalidation."
        ) from exc

    audits = operand_audit.candidate_audits
    if not audits or len(constraint_results) != len(audits):
        raise FeatureConstructionIntegrityError(
            "Exactly one V2 result is required per retained D3 candidate."
        )
    c0_candidate = audits[0].candidate
    if c0_candidate.role is not CandidateRole.ORIGINAL:
        raise FeatureConstructionIntegrityError("Permanent c0 must remain first.")
    target = audits[0].target_field
    if target.field_name is not ReceiptFieldName.PURCHASE_DATE:
        raise FeatureConstructionConfigurationError(
            "Feature-construction V0 is approved only for purchase-date candidates."
        )

    upstream_theta = operand_audit.hard_constraint_input.theta_a_ref
    result_ids: set[str] = set()
    candidate_ids: set[str] = set()
    first_profile = constraint_results[0].rule_profile_reference
    pairs: list[tuple[CandidateOperandAuditV0, ConstraintResultV2]] = []
    for audit, result in zip(audits, constraint_results, strict=True):
        try:
            result.__post_init__()
        except (AttributeError, TypeError, ValueError) as exc:
            raise FeatureConstructionIntegrityError(
                "A supplied V2 result failed complete revalidation."
            ) from exc
        if result.constraint_result_id in result_ids:
            raise FeatureConstructionIntegrityError(
                "constraint_result_id values must be unique."
            )
        if result.candidate.candidate_id in candidate_ids:
            raise FeatureConstructionIntegrityError(
                "Exactly one V2 result is permitted per retained candidate."
            )
        result_ids.add(result.constraint_result_id)
        candidate_ids.add(result.candidate.candidate_id)
        if result.candidate is not audit.candidate:
            raise FeatureConstructionIntegrityError(
                "V2 results must preserve exact D3 candidate order and identity."
            )
        if result.c0_candidate is not c0_candidate:
            raise FeatureConstructionIntegrityError(
                "Every V2 result must retain the exact permanent c0."
            )
        if any(
            outcome.candidate is not audit.candidate
            or outcome.c0_candidate is not c0_candidate
            for outcome in result.rule_outcomes
        ):
            raise FeatureConstructionIntegrityError(
                "Every V2 rule outcome must retain the exact D3 candidate and permanent c0."
            )
        if (
            result.receipt_id != c0_candidate.receipt_id
            or result.field_id != c0_candidate.field_id
        ):
            raise FeatureConstructionIntegrityError(
                "V2 receipt or field identity differs from the D3 candidate set."
            )
        if (
            result.theta_a_reference != upstream_theta
            or result.rule_profile_reference.theta_a_reference != upstream_theta
        ):
            raise FeatureConstructionConfigurationError(
                "V2 and D3 Theta_A references must match completely."
            )
        if result.rule_profile_reference != first_profile:
            raise FeatureConstructionConfigurationError(
                "One purchase-date candidate set requires one common V2 profile."
            )
        pairs.append((audit, result))
    return tuple(pairs)


def _expected_vectors(
    operand_audit: HardConstraintOperandAuditResultV0,
    pairs: tuple[tuple[CandidateOperandAuditV0, ConstraintResultV2], ...],
) -> tuple[CandidateFeatureVectorV0, ...]:
    theta_a = operand_audit.hard_constraint_input.theta_a_ref
    return tuple(
        CandidateFeatureVectorV0(
            operand_audit=operand_audit,
            candidate_audit=audit,
            constraint_result=result,
            candidate=audit.candidate,
            theta_a_reference=theta_a,
            slot_values=_slot_values(operand_audit, audit),
        )
        for audit, result in pairs
        if result.aggregate_state is ConstraintAggregateStateV2.ELIGIBLE
    )


@dataclass(frozen=True, slots=True)
class FeatureConstructionResultV0:
    """Atomic eligible vectors plus the complete unchanged V2 audit population."""

    operand_audit: HardConstraintOperandAuditResultV0
    constraint_results: tuple[ConstraintResultV2, ...]
    input_readiness: FeatureInputReadinessResultV0
    candidate_features: tuple[CandidateFeatureVectorV0, ...]
    component_version: str = FEATURE_CONSTRUCTION_COMPONENT_VERSION
    record_version: str = FEATURE_CONSTRUCTION_RECORD_VERSION
    _original_operand_audit_reference: HardConstraintOperandAuditResultV0 = field(
        init=False, repr=False, compare=False
    )
    _original_constraint_result_references: tuple[ConstraintResultV2, ...] = field(
        init=False, repr=False, compare=False
    )
    _original_input_readiness_reference: FeatureInputReadinessResultV0 = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        _capture_reference(
            self,
            "_original_operand_audit_reference",
            self.operand_audit,
            "The result's exact D3 operand-audit reference changed.",
        )
        _capture_reference(
            self,
            "_original_input_readiness_reference",
            self.input_readiness,
            "The exact feature-readiness observation reference changed.",
        )
        try:
            original_results = self._original_constraint_result_references
        except AttributeError:
            object.__setattr__(
                self,
                "_original_constraint_result_references",
                self.constraint_results,
            )
        else:
            if len(original_results) != len(self.constraint_results) or any(
                original is not current
                for original, current in zip(
                    original_results, self.constraint_results, strict=True
                )
            ):
                raise FeatureConstructionIntegrityError(
                    "The exact V2 result references changed after construction."
                )
        if not isinstance(self.input_readiness, FeatureInputReadinessResultV0):
            raise TypeError("input_readiness must be FeatureInputReadinessResultV0.")
        if not isinstance(self.candidate_features, tuple) or any(
            not isinstance(feature, CandidateFeatureVectorV0)
            for feature in self.candidate_features
        ):
            raise TypeError("candidate_features must contain CandidateFeatureVectorV0.")
        if self.component_version != FEATURE_CONSTRUCTION_COMPONENT_VERSION:
            raise ValueError("Unsupported feature-construction component version.")
        if self.record_version != FEATURE_CONSTRUCTION_RECORD_VERSION:
            raise ValueError("Unsupported feature-construction result version.")

        pairs = _validated_candidate_set(self.operand_audit, self.constraint_results)
        try:
            self.input_readiness.__post_init__()
        except (AttributeError, TypeError, ValueError) as exc:
            raise FeatureConstructionIntegrityError(
                "Feature-input readiness failed complete revalidation."
            ) from exc
        if self.input_readiness.operand_audit is not self.operand_audit:
            raise FeatureConstructionIntegrityError(
                "Feature readiness must retain the result's exact D3 audit."
            )
        reconstructed_readiness = inspect_feature_input_readiness(
            operand_audit=self.operand_audit
        )
        if self.input_readiness != reconstructed_readiness:
            raise FeatureConstructionIntegrityError(
                "Feature readiness differs from deterministic reconstruction."
            )

        expected = _expected_vectors(self.operand_audit, pairs)
        if len(self.candidate_features) != len(expected):
            raise FeatureConstructionIntegrityError(
                "Exactly the V2-eligible candidates require feature vectors."
            )
        for observed, reconstructed in zip(
            self.candidate_features, expected, strict=True
        ):
            observed.__post_init__()
            if (
                observed.operand_audit is not self.operand_audit
                or observed.constraint_result
                is not reconstructed.constraint_result
                or observed.candidate_audit is not reconstructed.candidate_audit
                or observed.candidate is not reconstructed.candidate
            ):
                raise FeatureConstructionIntegrityError(
                    "Candidate feature records changed exact source references."
                )
            if observed != reconstructed:
                raise FeatureConstructionIntegrityError(
                    "Candidate feature records differ from deterministic reconstruction."
                )


def construct_purchase_date_features_v0(
    *,
    operand_audit: HardConstraintOperandAuditResultV0,
    constraint_results: tuple[ConstraintResultV2, ...],
) -> FeatureConstructionResultV0:
    """Construct approved V0 features atomically for eligible purchase dates."""

    pairs = _validated_candidate_set(operand_audit, constraint_results)
    readiness = inspect_feature_input_readiness(operand_audit=operand_audit)
    vectors = _expected_vectors(operand_audit, pairs)
    return FeatureConstructionResultV0(
        operand_audit=operand_audit,
        constraint_results=constraint_results,
        input_readiness=readiness,
        candidate_features=vectors,
    )


__all__ = (
    "CandidateFeatureVectorV0",
    "FeatureConstructionConfigurationError",
    "FeatureConstructionError",
    "FeatureConstructionIntegrityError",
    "FeatureConstructionResultV0",
    "FeatureSlotValueV0",
    "FeatureValueAvailabilityV0",
    "FeatureValueReasonV0",
    "construct_purchase_date_features_v0",
)
