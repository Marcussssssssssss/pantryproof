"""Provisional Version-1 shared records for the PantryProof proposed method.

The records in this module define immutable component boundaries.  They do not
implement candidate generation, candidate limiting, constraints, evidence
features, scoring, calibration, review policy, or persistence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from pipeline.contracts import (
    FailureStage,
    FieldStatus,
    OcrSourceToken,
    PolicyState,
    PreResolutionDisposition,
    ReceiptExtractionStatus,
    ReceiptFieldName,
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
    SourceProcessingStatus,
    StructuredField,
)


PROPOSED_CONTRACT_VERSION = "1"
FEATURE_SCHEMA_ID_V1 = "pantryproof-candidate-evidence-7-v1"


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty.")


def _require_optional_text(value: str | None, name: str) -> None:
    if value is not None:
        _require_text(value, name)


def _require_unique(values: tuple[str, ...], name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must not contain duplicates.")


def _require_finite_decimal(value: Decimal, name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal.")


class CandidateSourceKind(str, Enum):
    ORIGINAL = "ORIGINAL"
    SOURCE_TOKEN_OR_NEIGHBOUR = "SOURCE_TOKEN_OR_NEIGHBOUR"
    GENERIC_NORMALIZATION = "GENERIC_NORMALIZATION"
    RETAILER_MAPPING = "RETAILER_MAPPING"
    PANTRY_TERMINOLOGY = "PANTRY_TERMINOLOGY"


_SOURCE_PRIORITY = {
    CandidateSourceKind.ORIGINAL: 0,
    CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR: 1,
    CandidateSourceKind.GENERIC_NORMALIZATION: 2,
    CandidateSourceKind.RETAILER_MAPPING: 3,
    CandidateSourceKind.PANTRY_TERMINOLOGY: 4,
}


class CandidateRole(str, Enum):
    ORIGINAL = "ORIGINAL"
    ALTERED = "ALTERED"


class CandidateLimitStatus(str, Enum):
    RETAINED = "RETAINED"
    LIMIT_OVERFLOW = "LIMIT_OVERFLOW"


class ConstraintEligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    CONSTRAINT_REJECTED = "CONSTRAINT_REJECTED"


class ConstraintReasonCode(str, Enum):
    FIELD_TYPE_INVALID = "FIELD_TYPE_INVALID"
    ASSOCIATION_AMBIGUOUS = "ASSOCIATION_AMBIGUOUS"
    SOURCE_UNSUPPORTED = "SOURCE_UNSUPPORTED"
    ARITHMETIC_CONTRADICTION = "ARITHMETIC_CONTRADICTION"
    OTHER = "OTHER"


class CandidateAuditStatus(str, Enum):
    SCORING_ELIGIBLE = "SCORING_ELIGIBLE"
    CONSTRAINT_REJECTED = "CONSTRAINT_REJECTED"
    REJECTED_PRICE_ONLY = "REJECTED_PRICE_ONLY"


class ValueAvailabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FeatureSlot(str, Enum):
    OCR_EVIDENCE = "q_o"
    EXTRACTOR_EVIDENCE = "q_e"
    LEXICAL_AGREEMENT = "a_l"
    LAYOUT_AGREEMENT = "a_y"
    RETAILER_SUPPORT = "s_r"
    ARITHMETIC_SUPPORT = "s_a"
    PRICE_REFERENCE_SUPPORT = "s_p"


FEATURE_SLOT_ORDER = tuple(FeatureSlot)


class ConfigurationKind(str, Enum):
    THETA_A = "THETA_A"
    KAPPA = "KAPPA"
    PHI = "PHI"
    PT1 = "PT1"
    PT2 = "PT2"


class ConfigurationState(str, Enum):
    READY = "READY"
    NOT_READY = "NOT_READY"
    NOT_VALID = "NOT_VALID"
    NO_VALID_POINT = "NO_VALID_POINT"


class FieldDecisionState(str, Enum):
    AUTO_ACCEPTED = "AUTO_ACCEPTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class AutomaticCommitPermission(str, Enum):
    PERMITTED = "PERMITTED"
    NOT_PERMITTED = "NOT_PERMITTED"


class ReviewResolutionKind(str, Enum):
    ORACLE_POLICY_RESOLVED = "ORACLE_POLICY_RESOLVED"
    USER_CONFIRMED = "USER_CONFIRMED"
    USER_MODIFIED = "USER_MODIFIED"
    USER_REJECTED = "USER_REJECTED"


class PersistenceResultState(str, Enum):
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class SourceCharacterSpanV1:
    """A genuine half-open character span in one literal OCR token."""

    token_id: str
    start: int
    end: int
    text: str
    record_version: str = PROPOSED_CONTRACT_VERSION

    def __post_init__(self) -> None:
        _require_text(self.token_id, "token_id")
        if type(self.start) is not int or type(self.end) is not int:
            raise ValueError("Source character offsets must be non-Boolean integers.")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("A source character span must be a non-empty range.")
        if not self.text:
            raise ValueError("A source character span must retain literal text.")
        if len(self.text) != self.end - self.start:
            raise ValueError("Source span text length must equal end - start.")
        if self.record_version != PROPOSED_CONTRACT_VERSION:
            raise ValueError("Unsupported proposed-contract record version.")


@dataclass(frozen=True, slots=True)
class B3CompatibleSeedV1:
    """A B3-derived possible future seed, deliberately not a candidate."""

    seed_id: str
    receipt_id: str
    field_id: str
    c0_candidate_id: str
    c0_value: str
    proposed_value: str
    source_kind: CandidateSourceKind
    b3_ruleset_id: str
    b3_event_ids: tuple[str, ...]
    b3_rule_ids: tuple[str, ...]
    source_spans: tuple[SourceCharacterSpanV1, ...] = ()
    record_version: str = PROPOSED_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for name in (
            "seed_id",
            "receipt_id",
            "field_id",
            "c0_candidate_id",
            "c0_value",
            "proposed_value",
            "b3_ruleset_id",
        ):
            _require_text(getattr(self, name), name)
        if self.proposed_value == self.c0_value:
            raise ValueError("A B3 seed must differ from permanent c0.")
        if self.source_kind not in {
            CandidateSourceKind.GENERIC_NORMALIZATION,
            CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
        }:
            raise ValueError("A B3 seed has an incompatible source kind.")
        if not self.b3_event_ids or not self.b3_rule_ids:
            raise ValueError("A B3 seed requires rule and event provenance.")
        _require_unique(self.b3_event_ids, "b3_event_ids")
        _require_unique(self.b3_rule_ids, "b3_rule_ids")
        if self.record_version != PROPOSED_CONTRACT_VERSION:
            raise ValueError("Unsupported proposed-contract record version.")


@dataclass(frozen=True, slots=True)
class MethodReadyFieldV1:
    """One extracted B2 field whose exact B2 value is permanent c0."""

    method_field_id: str
    receipt_id: str
    field_id: str
    field_name: ReceiptFieldName
    original_b2_field: StructuredField
    original_value: str
    c0_candidate_id: str
    c0_value: str
    source_token_ids: tuple[str, ...]
    source_tokens: tuple[OcrSourceToken, ...]
    source_image_id: str
    source_processing_status: SourceProcessingStatus
    b2_extraction_status: ReceiptExtractionStatus
    b2_extractor_version: str
    stored_gate_result: SourceEvidenceGateResult
    b3_ruleset_id: str | None = None
    b3_seed_ids: tuple[str, ...] = ()
    record_version: str = PROPOSED_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for name in (
            "method_field_id",
            "receipt_id",
            "field_id",
            "original_value",
            "c0_candidate_id",
            "c0_value",
            "source_image_id",
            "b2_extractor_version",
        ):
            _require_text(getattr(self, name), name)
        if self.original_b2_field.status is not FieldStatus.EXTRACTED:
            raise ValueError("Only an EXTRACTED B2 field is method-ready.")
        if self.original_b2_field.receipt_id != self.receipt_id:
            raise ValueError("The B2 field must belong to the method-ready receipt.")
        if self.original_b2_field.field_id != self.field_id:
            raise ValueError("The method-ready field must retain the B2 field ID.")
        if self.original_b2_field.field_name is not self.field_name:
            raise ValueError("The method-ready field must retain the B2 field type.")
        if self.original_b2_field.value != self.original_value:
            raise ValueError("original_value must equal the exact B2 field value.")
        if self.original_value != self.c0_value:
            raise ValueError("Permanent c0 must equal the original B2 value.")
        if self.original_b2_field.source_token_ids != self.source_token_ids:
            raise ValueError("Source-token references must equal the B2 references.")
        if tuple(token.token_id for token in self.source_tokens) != self.source_token_ids:
            raise ValueError("Source tokens must follow the B2 source-reference order.")
        if any(token.receipt_id != self.receipt_id for token in self.source_tokens):
            raise ValueError("Every source token must belong to the receipt.")
        if self.stored_gate_result.receipt_id != self.receipt_id:
            raise ValueError("The stored gate result must belong to the receipt.")
        if self.stored_gate_result.decision is not SourceEvidenceDecision.SUFFICIENT:
            raise ValueError(
                "A method-ready EXTRACTED field requires a stored SUFFICIENT gate result."
            )
        _require_unique(self.source_token_ids, "source_token_ids")
        _require_unique(self.b3_seed_ids, "b3_seed_ids")
        if self.b3_seed_ids and self.b3_ruleset_id is None:
            raise ValueError("B3 seed references require a B3 ruleset ID.")
        _require_optional_text(self.b3_ruleset_id, "b3_ruleset_id")
        if self.record_version != PROPOSED_CONTRACT_VERSION:
            raise ValueError("Unsupported proposed-contract record version.")


@dataclass(frozen=True, slots=True)
class CandidateProvenanceV1:
    """One ordered provenance member in a candidate's deduplicated union."""

    provenance_id: str
    receipt_id: str
    field_id: str
    candidate_id: str
    source_kind: CandidateSourceKind
    original_observed_value: str
    source_token_ids: tuple[str, ...] = ()
    source_spans: tuple[SourceCharacterSpanV1, ...] = ()
    source_order_relationship: str | None = None
    source_order_position: int | None = None
    generic_rule_id: str | None = None
    resource_snapshot_id: str | None = None
    record_version: str = PROPOSED_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for name in (
            "provenance_id",
            "receipt_id",
            "field_id",
            "candidate_id",
            "original_observed_value",
        ):
            _require_text(getattr(self, name), name)
        _require_unique(self.source_token_ids, "source_token_ids")
        span_token_ids = tuple(span.token_id for span in self.source_spans)
        if any(token_id not in self.source_token_ids for token_id in span_token_ids):
            raise ValueError("Every source span must reference a declared source token.")
        _require_optional_text(
            self.source_order_relationship, "source_order_relationship"
        )
        if self.source_order_position is not None and self.source_order_position < 0:
            raise ValueError("source_order_position cannot be negative.")
        _require_optional_text(self.generic_rule_id, "generic_rule_id")
        _require_optional_text(self.resource_snapshot_id, "resource_snapshot_id")
        if self.source_kind is CandidateSourceKind.ORIGINAL:
            if not self.source_token_ids:
                raise ValueError("Original provenance requires its B2 source tokens.")
            if self.generic_rule_id is not None or self.resource_snapshot_id is not None:
                raise ValueError("Original provenance cannot claim a rule or resource.")
        elif self.source_kind is CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR:
            if not self.source_token_ids:
                raise ValueError("Source/neighbour provenance requires source tokens.")
            if self.resource_snapshot_id is not None:
                raise ValueError("Source/neighbour provenance cannot claim a resource.")
        elif self.source_kind is CandidateSourceKind.GENERIC_NORMALIZATION:
            if self.generic_rule_id is None:
                raise ValueError("Generic provenance requires a rule ID.")
            if self.resource_snapshot_id is not None:
                raise ValueError("Generic provenance cannot claim a resource snapshot.")
        else:
            if self.resource_snapshot_id is None:
                raise ValueError("Retailer/terminology provenance requires a snapshot ID.")
        if self.record_version != PROPOSED_CONTRACT_VERSION:
            raise ValueError("Unsupported proposed-contract record version.")

    @property
    def source_priority(self) -> int:
        return _SOURCE_PRIORITY[self.source_kind]


@dataclass(frozen=True, slots=True)
class PreliminaryRankV1:
    """Recorded output of a future declared non-price ranking rule."""

    source_priority_rank: int
    normalized_edit_similarity: Decimal
    source_order_displacement: int
    normalized_candidate_text: str
    rank_position: int
    tie_group_id: str | None = None
    record_version: str = PROPOSED_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.source_priority_rank < 1:
            raise ValueError("Altered-candidate source priority starts at one.")
        _require_finite_decimal(
            self.normalized_edit_similarity, "normalized_edit_similarity"
        )
        if self.normalized_edit_similarity < 0 or self.normalized_edit_similarity > 1:
            raise ValueError("normalized_edit_similarity must be within [0, 1].")
        if self.source_order_displacement < 0 or self.rank_position < 1:
            raise ValueError("Rank displacement/position cannot be negative or zero.")
        _require_text(self.normalized_candidate_text, "normalized_candidate_text")
        _require_optional_text(self.tie_group_id, "tie_group_id")
        if self.record_version != PROPOSED_CONTRACT_VERSION:
            raise ValueError("Unsupported proposed-contract record version.")


@dataclass(frozen=True, slots=True)
class CandidateRecordV1:
    """Original or deduplicated altered candidate, before downstream audit."""

    candidate_id: str
    receipt_id: str
    field_id: str
    c0_candidate_id: str
    value: str
    normalized_dedup_key: str
    role: CandidateRole
    provenance: tuple[CandidateProvenanceV1, ...]
    limit_status: CandidateLimitStatus
    preliminary_rank: PreliminaryRankV1 | None = None
    overflow_reason: str | None = None
    record_version: str = PROPOSED_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for name in (
            "candidate_id",
            "receipt_id",
            "field_id",
            "c0_candidate_id",
            "value",
            "normalized_dedup_key",
        ):
            _require_text(getattr(self, name), name)
        if not self.provenance:
            raise ValueError("A candidate requires provenance.")
        _require_unique(
            tuple(item.provenance_id for item in self.provenance), "provenance IDs"
        )
        for item in self.provenance:
            if (
                item.receipt_id != self.receipt_id
                or item.field_id != self.field_id
                or item.candidate_id != self.candidate_id
            ):
                raise ValueError("Candidate provenance identity must match its candidate.")
        if self.role is CandidateRole.ORIGINAL:
            if self.candidate_id != self.c0_candidate_id:
                raise ValueError("The original candidate must be permanent c0.")
            if self.limit_status is not CandidateLimitStatus.RETAINED:
                raise ValueError("Permanent c0 cannot be removed by candidateLimit.")
            if self.preliminary_rank is not None or self.overflow_reason is not None:
                raise ValueError("Permanent c0 is outside altered-candidate ranking.")
            if any(
                item.source_kind is not CandidateSourceKind.ORIGINAL
                for item in self.provenance
            ):
                raise ValueError("Original c0 provenance must use ORIGINAL.")
        else:
            if self.candidate_id == self.c0_candidate_id:
                raise ValueError("An altered candidate cannot reuse the c0 ID.")
            if any(
                item.source_kind is CandidateSourceKind.ORIGINAL
                for item in self.provenance
            ):
                raise ValueError("An altered candidate cannot claim ORIGINAL provenance.")
            if self.preliminary_rank is None:
                raise ValueError("An altered candidate requires recorded rank metadata.")
            if self.limit_status is CandidateLimitStatus.LIMIT_OVERFLOW:
                _require_text(self.overflow_reason or "", "overflow_reason")
            elif self.overflow_reason is not None:
                raise ValueError("Only overflow candidates have an overflow reason.")
        if self.record_version != PROPOSED_CONTRACT_VERSION:
            raise ValueError("Unsupported proposed-contract record version.")


@dataclass(frozen=True, slots=True)
class ConstraintResultV1:
    """Recorded hard-constraint result; no constraint algorithm is included."""

    constraint_result_id: str
    receipt_id: str
    field_id: str
    candidate_id: str
    eligibility: ConstraintEligibility
    evaluated_rule_ids: tuple[str, ...]
    reason_codes: tuple[ConstraintReasonCode, ...] = ()
    reason_detail: str | None = None
    record_version: str = PROPOSED_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for name in (
            "constraint_result_id",
            "receipt_id",
            "field_id",
            "candidate_id",
        ):
            _require_text(getattr(self, name), name)
        _require_unique(self.evaluated_rule_ids, "evaluated_rule_ids")
        if not self.evaluated_rule_ids:
            raise ValueError("A constraint result requires evaluated rule IDs.")
        _require_unique(tuple(code.value for code in self.reason_codes), "reason_codes")
        if self.eligibility is ConstraintEligibility.ELIGIBLE:
            if self.reason_codes or self.reason_detail is not None:
                raise ValueError("Eligible candidates cannot contain rejection reasons.")
        else:
            if not self.reason_codes:
                raise ValueError("Constraint rejection requires a reason code.")
            _require_text(self.reason_detail or "", "reason_detail")
        if self.record_version != PROPOSED_CONTRACT_VERSION:
            raise ValueError("Unsupported proposed-contract record version.")


@dataclass(frozen=True, slots=True)
class ConfigurationRefV1:
    kind: ConfigurationKind
    configuration_id: str
    configuration_version: str
    state: ConfigurationState
    content_hash: str | None = None
    status_reason: str | None = None
    record_version: str = PROPOSED_CONTRACT_VERSION

    def __post_init__(self) -> None:
        _require_text(self.configuration_id, "configuration_id")
        _require_text(self.configuration_version, "configuration_version")
        _require_optional_text(self.content_hash, "content_hash")
        _require_optional_text(self.status_reason, "status_reason")
        if self.state is ConfigurationState.READY:
            if self.content_hash is None:
                raise ValueError("A READY configuration requires a content hash.")
            if self.status_reason is not None:
                raise ValueError("A READY configuration has no failure reason.")
        else:
            _require_text(self.status_reason or "", "status_reason")
        if (
            self.state is ConfigurationState.NO_VALID_POINT
            and self.kind is not ConfigurationKind.PT2
        ):
            raise ValueError("NO_VALID_POINT is specific to PT2 selection.")
        if self.record_version != PROPOSED_CONTRACT_VERSION:
            raise ValueError("Unsupported proposed-contract record version.")


@dataclass(frozen=True, slots=True)
class ConfigurationRefsV1:
    theta_a: ConfigurationRefV1
    kappa: ConfigurationRefV1
    phi: ConfigurationRefV1
    pt1: ConfigurationRefV1
    pt2: ConfigurationRefV1
    record_version: str = PROPOSED_CONTRACT_VERSION

    def __post_init__(self) -> None:
        expected = (
            (self.theta_a, ConfigurationKind.THETA_A),
            (self.kappa, ConfigurationKind.KAPPA),
            (self.phi, ConfigurationKind.PHI),
            (self.pt1, ConfigurationKind.PT1),
            (self.pt2, ConfigurationKind.PT2),
        )
        if any(reference.kind is not kind for reference, kind in expected):
            raise ValueError("Configuration references must retain their distinct roles.")
        if self.record_version != PROPOSED_CONTRACT_VERSION:
            raise ValueError("Unsupported proposed-contract record version.")


FeatureValueV1 = Decimal | str | bool | None


@dataclass(frozen=True, slots=True)
class CandidateEvidenceV1:
    """Post-limit candidate audit with optional seven-slot evidence and scores."""

    evidence_id: str
    candidate: CandidateRecordV1
    constraint_result: ConstraintResultV1
    candidate_status: CandidateAuditStatus
    configuration_refs: ConfigurationRefsV1
    feature_schema_id: str | None = None
    feature_slots: tuple[FeatureSlot, ...] = ()
    feature_values: tuple[FeatureValueV1, ...] = ()
    feature_provenance_refs: tuple[tuple[str, ...], ...] = ()
    missingness_mask: tuple[bool, ...] = ()
    score_status: ValueAvailabilityStatus = ValueAvailabilityStatus.NOT_APPLICABLE
    raw_score: Decimal | None = None
    score_reason: str | None = None
    calibration_status: ValueAvailabilityStatus = (
        ValueAvailabilityStatus.NOT_APPLICABLE
    )
    probability_available: bool = False
    calibrated_probability: Decimal | None = None
    calibration_reason: str | None = None
    record_version: str = PROPOSED_CONTRACT_VERSION

    def __post_init__(self) -> None:
        _require_text(self.evidence_id, "evidence_id")
        candidate = self.candidate
        constraint = self.constraint_result
        if candidate.limit_status is not CandidateLimitStatus.RETAINED:
            raise ValueError("Limit-overflow candidates cannot receive evidence audit.")
        if (
            constraint.receipt_id != candidate.receipt_id
            or constraint.field_id != candidate.field_id
            or constraint.candidate_id != candidate.candidate_id
        ):
            raise ValueError("Constraint identity must match the candidate.")

        rejected = self.candidate_status in {
            CandidateAuditStatus.CONSTRAINT_REJECTED,
            CandidateAuditStatus.REJECTED_PRICE_ONLY,
        }
        if self.candidate_status is CandidateAuditStatus.CONSTRAINT_REJECTED:
            if constraint.eligibility is not ConstraintEligibility.CONSTRAINT_REJECTED:
                raise ValueError("Constraint-rejected status requires rejection evidence.")
        elif constraint.eligibility is not ConstraintEligibility.ELIGIBLE:
            raise ValueError("Only constraint-eligible candidates may continue.")
        if (
            self.candidate_status is CandidateAuditStatus.REJECTED_PRICE_ONLY
            and candidate.role is not CandidateRole.ALTERED
        ):
            raise ValueError("Price-only rejection applies only to altered candidates.")

        if rejected:
            if any(
                (
                    self.feature_schema_id is not None,
                    self.feature_slots,
                    self.feature_values,
                    self.feature_provenance_refs,
                    self.missingness_mask,
                    self.raw_score is not None,
                    self.calibrated_probability is not None,
                    self.probability_available,
                )
            ):
                raise ValueError("Rejected candidates bypass features, scoring, and calibration.")
            if (
                self.score_status is not ValueAvailabilityStatus.NOT_APPLICABLE
                or self.calibration_status is not ValueAvailabilityStatus.NOT_APPLICABLE
            ):
                raise ValueError("Rejected-candidate score/probability is NOT_APPLICABLE.")
            if self.score_reason is not None or self.calibration_reason is not None:
                raise ValueError("Rejected candidates use status, not unavailable reasons.")
        else:
            self._validate_feature_vector()
            self._validate_scores()
        if self.record_version != PROPOSED_CONTRACT_VERSION:
            raise ValueError("Unsupported proposed-contract record version.")

    def _validate_feature_vector(self) -> None:
        if self.feature_schema_id != FEATURE_SCHEMA_ID_V1:
            raise ValueError("Scoring-eligible evidence requires the V1 feature schema.")
        if self.feature_slots != FEATURE_SLOT_ORDER:
            raise ValueError("Feature slots must follow Equation 4.1 order.")
        expected_length = len(FEATURE_SLOT_ORDER)
        if not all(
            len(value) == expected_length
            for value in (
                self.feature_values,
                self.feature_provenance_refs,
                self.missingness_mask,
            )
        ):
            raise ValueError("Feature values, provenance, and mask must have seven slots.")
        for index, (value, is_missing) in enumerate(
            zip(self.feature_values, self.missingness_mask, strict=True)
        ):
            if is_missing != (value is None):
                raise ValueError(f"Feature mask disagrees with slot {index}.")
            if isinstance(value, Decimal):
                _require_finite_decimal(value, f"feature_values[{index}]")
            elif value is not None and not isinstance(value, (str, bool)):
                raise ValueError("Feature values must be Decimal, string, bool, or null.")
        for references in self.feature_provenance_refs:
            _require_unique(references, "feature provenance references")

    def _validate_scores(self) -> None:
        if self.score_status is ValueAvailabilityStatus.NOT_APPLICABLE:
            raise ValueError("A scoring-eligible candidate must have a score status.")
        if self.score_status is ValueAvailabilityStatus.AVAILABLE:
            if self.raw_score is None:
                raise ValueError("AVAILABLE score status requires raw_score.")
            _require_finite_decimal(self.raw_score, "raw_score")
            if self.score_reason is not None:
                raise ValueError("An available raw score has no unavailable reason.")
            if self.configuration_refs.theta_a.state is not ConfigurationState.READY:
                raise ValueError("An available raw score requires READY Theta_A.")
        else:
            if self.raw_score is not None:
                raise ValueError("An unavailable raw score must remain null.")
            _require_text(self.score_reason or "", "score_reason")

        if self.calibration_status is ValueAvailabilityStatus.NOT_APPLICABLE:
            raise ValueError("A scoring-eligible candidate must record calibration status.")
        if self.calibration_status is ValueAvailabilityStatus.AVAILABLE:
            if (
                self.score_status is not ValueAvailabilityStatus.AVAILABLE
                or self.raw_score is None
            ):
                raise ValueError(
                    "AVAILABLE calibration requires an available raw score."
                )
            if not self.probability_available or self.calibrated_probability is None:
                raise ValueError("AVAILABLE calibration requires an available probability.")
            _require_finite_decimal(
                self.calibrated_probability, "calibrated_probability"
            )
            if not 0 <= self.calibrated_probability <= 1:
                raise ValueError("calibrated_probability must be within [0, 1].")
            if self.calibration_reason is not None:
                raise ValueError("Available calibration has no unavailable reason.")
            if self.configuration_refs.kappa.state is not ConfigurationState.READY:
                raise ValueError("An available probability requires READY Kappa.")
        else:
            if self.probability_available or self.calibrated_probability is not None:
                raise ValueError("Unavailable calibration must preserve a null probability.")
            _require_text(self.calibration_reason or "", "calibration_reason")


@dataclass(frozen=True, slots=True)
class FieldDecisionV1:
    """Frozen pre-review field prediction and policy decision."""

    decision_id: str
    method_field_id: str
    method_ready_field: MethodReadyFieldV1
    receipt_id: str
    field_id: str
    c0_candidate_id: str
    c0_value: str
    selected_candidate: CandidateRecordV1
    selected_candidate_evidence: CandidateEvidenceV1
    pre_review_predicted_value: str
    decision: FieldDecisionState
    automatic_commit_permission: AutomaticCommitPermission
    decision_reason: str
    cached_unresolved_conflict: bool | None
    configuration_refs: ConfigurationRefsV1
    record_version: str = PROPOSED_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for name in (
            "decision_id",
            "method_field_id",
            "receipt_id",
            "field_id",
            "c0_candidate_id",
            "c0_value",
            "pre_review_predicted_value",
            "decision_reason",
        ):
            _require_text(getattr(self, name), name)
        candidate = self.selected_candidate
        evidence = self.selected_candidate_evidence
        original = self.method_ready_field
        if original.receipt_id != self.receipt_id:
            raise ValueError("The method-ready original must belong to the receipt.")
        if original.field_id != self.field_id:
            raise ValueError("The method-ready original must identify the field.")
        if original.method_field_id != self.method_field_id:
            raise ValueError("The method-field identity must match its original record.")
        if original.c0_candidate_id != self.c0_candidate_id:
            raise ValueError("The decision must retain the original c0 candidate ID.")
        if original.c0_value != self.c0_value:
            raise ValueError("The decision c0 value must equal the original B2 value.")
        if candidate.receipt_id != self.receipt_id or candidate.field_id != self.field_id:
            raise ValueError("The selected candidate must belong to the field.")
        if evidence.candidate != candidate:
            raise ValueError(
                "The selected-candidate audit must match the immutable candidate record."
            )
        if candidate.c0_candidate_id != self.c0_candidate_id:
            raise ValueError("The selected candidate must retain permanent c0 identity.")
        if candidate.value != self.pre_review_predicted_value:
            raise ValueError("The frozen prediction must equal the selected candidate value.")
        if candidate.limit_status is not CandidateLimitStatus.RETAINED:
            raise ValueError("An overflow candidate cannot be selected.")
        if candidate.role is CandidateRole.ORIGINAL and candidate.value != self.c0_value:
            raise ValueError("Selected original c0 must retain its value.")
        if self.configuration_refs != evidence.configuration_refs:
            raise ValueError(
                "Field-decision configurations must match selected candidate evidence."
            )
        if not evidence.probability_available and (
            candidate.role is not CandidateRole.ORIGINAL
            or candidate.candidate_id != original.c0_candidate_id
            or candidate.value != original.c0_value
            or self.pre_review_predicted_value != original.c0_value
        ):
            raise ValueError(
                "Unavailable selected-candidate probability requires freezing the "
                "permanent original c0 prediction."
            )
        if self.decision is FieldDecisionState.AUTO_ACCEPTED:
            if self.automatic_commit_permission is not AutomaticCommitPermission.PERMITTED:
                raise ValueError("AUTO_ACCEPTED requires automatic commit permission.")
            if self.cached_unresolved_conflict is not False:
                raise ValueError("AUTO_ACCEPTED requires a cached no-conflict result.")
            if (
                evidence.candidate_status is not CandidateAuditStatus.SCORING_ELIGIBLE
                or evidence.constraint_result.eligibility
                is not ConstraintEligibility.ELIGIBLE
                or not evidence.probability_available
            ):
                raise ValueError(
                    "AUTO_ACCEPTED requires eligible, probability-available candidate evidence."
                )
            if self.configuration_refs.phi.state is not ConfigurationState.READY:
                raise ValueError("AUTO_ACCEPTED requires a READY Phi policy configuration.")
        elif self.automatic_commit_permission is not AutomaticCommitPermission.NOT_PERMITTED:
            raise ValueError("REVIEW_REQUIRED cannot permit automatic commit.")
        if self.record_version != PROPOSED_CONTRACT_VERSION:
            raise ValueError("Unsupported proposed-contract record version.")


@dataclass(frozen=True, slots=True)
class ReviewResolutionV1:
    """A realized Tier A oracle or Tier B user review action."""

    resolution_id: str
    receipt_id: str
    field_id: str
    field_decision: FieldDecisionV1
    resolution_kind: ReviewResolutionKind
    presented_value: str
    actor_reference: str
    resolution_event_id: str
    resolved_value: str | None = None
    record_version: str = PROPOSED_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for name in (
            "resolution_id",
            "receipt_id",
            "field_id",
            "presented_value",
            "actor_reference",
            "resolution_event_id",
        ):
            _require_text(getattr(self, name), name)
        decision = self.field_decision
        if decision.receipt_id != self.receipt_id or decision.field_id != self.field_id:
            raise ValueError("Review resolution must match its field decision.")
        if decision.decision is not FieldDecisionState.REVIEW_REQUIRED:
            raise ValueError("Only a REVIEW_REQUIRED field can receive review resolution.")
        if self.presented_value != decision.pre_review_predicted_value:
            raise ValueError("Review must preserve the actually presented prediction.")
        if self.resolution_kind is ReviewResolutionKind.USER_REJECTED:
            if self.resolved_value is not None:
                raise ValueError("A rejected review has no resolved value.")
        else:
            _require_text(self.resolved_value or "", "resolved_value")
        if self.resolution_kind is ReviewResolutionKind.USER_CONFIRMED:
            if self.resolved_value != self.presented_value:
                raise ValueError("USER_CONFIRMED must retain the presented value.")
        elif self.resolution_kind is ReviewResolutionKind.USER_MODIFIED:
            if self.resolved_value == self.presented_value:
                raise ValueError("USER_MODIFIED must record an actual changed value.")
        if self.record_version != PROPOSED_CONTRACT_VERSION:
            raise ValueError("Unsupported proposed-contract record version.")

    @property
    def production_persistence_eligible(self) -> bool:
        return self.resolution_kind in {
            ReviewResolutionKind.USER_CONFIRMED,
            ReviewResolutionKind.USER_MODIFIED,
        }


@dataclass(frozen=True, slots=True)
class FinalApplicationOutcomeV1:
    """Later application result that never overwrites pre-resolution state."""

    outcome_id: str
    receipt_id: str
    pre_resolution: PreResolutionDisposition
    persistence_state: PersistenceResultState
    field_decisions: tuple[FieldDecisionV1, ...] = ()
    review_resolutions: tuple[ReviewResolutionV1, ...] = ()
    persistence_attempt_id: str | None = None
    inventory_write_reference: str | None = None
    successful_persistence_evidence_id: str | None = None
    failure_stage: FailureStage | None = None
    failure_reason: str | None = None
    record_version: str = PROPOSED_CONTRACT_VERSION

    def __post_init__(self) -> None:
        _require_text(self.outcome_id, "outcome_id")
        _require_text(self.receipt_id, "receipt_id")
        if self.pre_resolution.gate_result.receipt_id != self.receipt_id:
            raise ValueError("Frozen pre-resolution state must belong to the receipt.")
        _require_unique(
            tuple(item.decision_id for item in self.field_decisions),
            "field decision IDs",
        )
        _require_unique(
            tuple(item.field_id for item in self.field_decisions),
            "field decision field IDs",
        )
        _require_unique(
            tuple(item.resolution_id for item in self.review_resolutions),
            "review resolution IDs",
        )
        _require_unique(
            tuple(
                item.field_decision.decision_id for item in self.review_resolutions
            ),
            "review-resolution decision IDs",
        )
        if any(item.receipt_id != self.receipt_id for item in self.field_decisions):
            raise ValueError("Every field decision must belong to the receipt.")
        if any(item.receipt_id != self.receipt_id for item in self.review_resolutions):
            raise ValueError("Every review resolution must belong to the receipt.")
        decision_by_id = {
            item.decision_id: item for item in self.field_decisions
        }
        for resolution in self.review_resolutions:
            bound_decision = decision_by_id.get(resolution.field_decision.decision_id)
            if bound_decision is None:
                raise ValueError(
                    "Every review resolution must bind to a supplied field decision."
                )
            if resolution.field_decision != bound_decision:
                raise ValueError(
                    "A review resolution must match the immutable supplied field decision."
                )

        eligible = self._persistence_eligible()
        if self.persistence_state is PersistenceResultState.NOT_ATTEMPTED:
            if any(
                value is not None
                for value in (
                    self.persistence_attempt_id,
                    self.inventory_write_reference,
                    self.successful_persistence_evidence_id,
                    self.failure_stage,
                    self.failure_reason,
                )
            ):
                raise ValueError("NOT_ATTEMPTED cannot contain transaction results.")
        elif not eligible:
            raise ValueError("The frozen disposition/resolution is not persistence-eligible.")
        elif self.persistence_state is PersistenceResultState.COMMITTED:
            _require_text(self.persistence_attempt_id or "", "persistence_attempt_id")
            _require_text(
                self.inventory_write_reference or "", "inventory_write_reference"
            )
            _require_text(
                self.successful_persistence_evidence_id or "",
                "successful_persistence_evidence_id",
            )
            if self.failure_stage is not None or self.failure_reason is not None:
                raise ValueError("COMMITTED cannot contain persistence failure details.")
        else:
            _require_text(self.persistence_attempt_id or "", "persistence_attempt_id")
            if self.failure_stage is not FailureStage.INVENTORY_PERSISTENCE:
                raise ValueError("Persistence failure requires INVENTORY_PERSISTENCE stage.")
            _require_text(self.failure_reason or "", "failure_reason")
            if (
                self.inventory_write_reference is not None
                or self.successful_persistence_evidence_id is not None
            ):
                raise ValueError("Failed persistence cannot have successful-write evidence.")
        if self.record_version != PROPOSED_CONTRACT_VERSION:
            raise ValueError("Unsupported proposed-contract record version.")

    def _persistence_eligible(self) -> bool:
        state = self.pre_resolution.state
        if state is PolicyState.AUTO_RESOLVED:
            return bool(self.field_decisions) and all(
                item.decision is FieldDecisionState.AUTO_ACCEPTED
                and item.automatic_commit_permission
                is AutomaticCommitPermission.PERMITTED
                for item in self.field_decisions
            ) and not self.review_resolutions
        if state is PolicyState.REVIEW_REQUIRED:
            required = {
                item.decision_id
                for item in self.field_decisions
                if item.decision is FieldDecisionState.REVIEW_REQUIRED
            }
            resolved = {
                item.field_decision.decision_id for item in self.review_resolutions
            }
            return bool(required) and required == resolved and all(
                item.production_persistence_eligible for item in self.review_resolutions
            )
        return False


def to_json_compatible(value: Any) -> Any:
    """Convert contract records to deterministic language-neutral JSON values.

    Decimal values are emitted as strings, avoiding binary floating-point loss.
    """

    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Non-finite Decimal values cannot be serialized.")
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: to_json_compatible(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, tuple):
        return [to_json_compatible(item) for item in value]
    if isinstance(value, list):
        return [to_json_compatible(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): to_json_compatible(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"Unsupported JSON contract value: {type(value).__name__}.")


def to_deterministic_json(value: Any) -> str:
    """Serialize supported contract values with stable ordering and nulls."""

    return json.dumps(
        to_json_compatible(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
