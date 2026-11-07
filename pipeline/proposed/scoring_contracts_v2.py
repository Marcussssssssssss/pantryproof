"""Structural V2-native raw-scoring evidence contracts.

The records in this module audit already-constructed D3, Constraint V2, and
seven-slot feature evidence.  They do not select a scorer, execute a scorer,
calibrate a score, select a candidate, or authorize replacement of permanent
``c0``.  Live construction preserves exact upstream Python references; the
public codec provides the separate content-only cross-runtime boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import NoReturn

from pipeline.proposed.contracts import CandidateRecordV1, CandidateRole, ConfigurationRefV1
from pipeline.proposed.feature_construction import (
    CandidateFeatureVectorV0,
    FeatureConstructionResultV0,
)
from pipeline.proposed.hard_constraint_contracts_v2 import (
    ConstraintAggregateStateV2,
    ConstraintResultV2,
)
from pipeline.proposed.trusted_theta_contracts_v1 import (
    TrustedResolverStateV1,
    TrustedScorerBindingV1,
    TrustedScorerResolverResultV1,
)


SCORING_COMPONENT_VERSION = "scoring-contracts-v2"
SCORING_RECORD_VERSION = "scoring-record-v2"


class ScoringContractError(ValueError):
    """Base error for invalid structural scoring evidence."""


class ScoringSourceBindingError(ScoringContractError):
    """Raised when exact D3/V2/feature references are substituted."""


class ScoringAuditIntegrityError(ScoringContractError):
    """Raised when a scoring audit is incomplete or contradictory."""


class AdmissionStateV2(str, Enum):
    ADMITTED = "ADMITTED"
    NOT_APPLICABLE_CONSTRAINT_REJECTED = (
        "NOT_APPLICABLE_CONSTRAINT_REJECTED"
    )
    NOT_APPLICABLE_CONSTRAINT_UNAVAILABLE = (
        "NOT_APPLICABLE_CONSTRAINT_UNAVAILABLE"
    )
    REJECTED_PRICE_ONLY_SUPPORT = "REJECTED_PRICE_ONLY_SUPPORT"


class ScoreStatusV2(str, Enum):
    AVAILABLE = "AVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ScoreNotApplicableReasonV2(str, Enum):
    CONSTRAINT_REJECTED = "CONSTRAINT_REJECTED"
    CONSTRAINT_UNAVAILABLE = "CONSTRAINT_UNAVAILABLE"
    PRE_SCORE_REJECTED_PRICE_ONLY_SUPPORT = (
        "PRE_SCORE_REJECTED_PRICE_ONLY_SUPPORT"
    )


class ScorerInvocationStateV2(str, Enum):
    INVOKED = "INVOKED"
    NOT_INVOKED_ZERO_ADMITTED = "NOT_INVOKED_ZERO_ADMITTED"


class FieldScoringCompletionStateV2(str, Enum):
    COMPLETE_SCORED = "COMPLETE_SCORED"
    COMPLETE_ZERO_ADMITTED_BYPASS = "COMPLETE_ZERO_ADMITTED_BYPASS"


class FieldScoringFailureStateV2(str, Enum):
    TRUSTED_SCORER_NOT_READY = "TRUSTED_SCORER_NOT_READY"
    TRUSTED_SCORER_NOT_VALID = "TRUSTED_SCORER_NOT_VALID"
    CONFIGURATION_FAILURE = "CONFIGURATION_FAILURE"
    MANIFEST_FAILURE = "MANIFEST_FAILURE"
    COMPATIBILITY_FAILURE = "COMPATIBILITY_FAILURE"
    INTEGRITY_FAILURE = "INTEGRITY_FAILURE"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"


def _fail(error_type: type[ScoringContractError], message: str) -> NoReturn:
    raise error_type(message)


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScoringAuditIntegrityError(f"{name} must be a nonempty string.")
    return value


def _require_optional_text(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, name)


def _require_enum(value: object, enum_type: type[Enum], name: str) -> None:
    if not isinstance(value, enum_type):
        raise ScoringAuditIntegrityError(
            f"{name} must be {enum_type.__name__}."
        )


def _require_tuple(value: object, name: str) -> tuple[object, ...]:
    if not isinstance(value, tuple):
        raise ScoringAuditIntegrityError(f"{name} must be a tuple.")
    return value


def _capture_reference(
    record: object,
    attribute: str,
    current: object,
    message: str,
) -> None:
    try:
        original = getattr(record, attribute)
    except AttributeError:
        object.__setattr__(record, attribute, current)
    else:
        if original is not current:
            raise ScoringSourceBindingError(message)


def _capture_reference_tuple(
    record: object,
    attribute: str,
    current: tuple[object, ...],
    message: str,
) -> None:
    try:
        original = getattr(record, attribute)
    except AttributeError:
        object.__setattr__(record, attribute, current)
    else:
        if len(original) != len(current) or any(
            before is not after
            for before, after in zip(original, current, strict=True)
        ):
            raise ScoringSourceBindingError(message)


def _revalidate(value: object, expected_type: type, name: str) -> None:
    if not isinstance(value, expected_type):
        raise ScoringAuditIntegrityError(
            f"{name} must be {expected_type.__name__}."
        )
    try:
        value.__post_init__()
    except (AttributeError, TypeError, ValueError) as exc:
        raise ScoringAuditIntegrityError(
            f"{name} failed complete nested-record revalidation."
        ) from exc


@dataclass(frozen=True, slots=True)
class ScoringSourceSnapshotV2:
    """Exact live feature-construction graph used by one field scoring audit."""

    source_snapshot_id: str
    feature_construction_result: FeatureConstructionResultV0
    source_component_versions: tuple[str, ...]
    component_version: str = SCORING_COMPONENT_VERSION
    record_version: str = SCORING_RECORD_VERSION
    _original_feature_construction_reference: FeatureConstructionResultV0 = field(
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        _capture_reference(
            self,
            "_original_feature_construction_reference",
            self.feature_construction_result,
            "The exact feature-construction source reference changed.",
        )
        _require_text(self.source_snapshot_id, "source_snapshot_id")
        _revalidate(
            self.feature_construction_result,
            FeatureConstructionResultV0,
            "feature_construction_result",
        )
        versions = _require_tuple(
            self.source_component_versions,
            "source_component_versions",
        )
        if any(not isinstance(item, str) or not item.strip() for item in versions):
            _fail(
                ScoringAuditIntegrityError,
                "source_component_versions must contain nonempty strings.",
            )
        if len(set(versions)) != len(versions):
            _fail(
                ScoringAuditIntegrityError,
                "source_component_versions must be unique and ordered.",
            )
        operand = self.feature_construction_result.operand_audit
        expected_versions = (
            operand.hard_constraint_input.component_version,
            operand.component_version,
            self.feature_construction_result.component_version,
        )
        if versions != expected_versions:
            _fail(
                ScoringAuditIntegrityError,
                "Stored source component versions differ from the live source graph.",
            )
        if self.component_version != SCORING_COMPONENT_VERSION:
            _fail(ScoringAuditIntegrityError, "Unsupported scoring component version.")
        if self.record_version != SCORING_RECORD_VERSION:
            _fail(ScoringAuditIntegrityError, "Unsupported scoring record version.")

        candidates = self.candidates
        if not candidates or candidates[0].role is not CandidateRole.ORIGINAL:
            _fail(ScoringAuditIntegrityError, "Permanent c0 must remain first.")
        if candidates[0].candidate_id != candidates[0].c0_candidate_id:
            _fail(ScoringAuditIntegrityError, "Permanent c0 must remain self-bound.")
        if len(self.constraint_results) != len(candidates):
            _fail(
                ScoringAuditIntegrityError,
                "Exactly one V2 result is required per retained D3 candidate.",
            )
        if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
            _fail(ScoringAuditIntegrityError, "Candidate identifiers must be unique.")
        if len(
            {result.constraint_result_id for result in self.constraint_results}
        ) != len(self.constraint_results):
            _fail(ScoringAuditIntegrityError, "V2 result identifiers must be unique.")

    @property
    def candidate_audits(self):
        return self.feature_construction_result.operand_audit.candidate_audits

    @property
    def candidates(self) -> tuple[CandidateRecordV1, ...]:
        return tuple(audit.candidate for audit in self.candidate_audits)

    @property
    def c0_candidate(self) -> CandidateRecordV1:
        return self.candidates[0]

    @property
    def constraint_results(self) -> tuple[ConstraintResultV2, ...]:
        return self.feature_construction_result.constraint_results

    @property
    def candidate_features(self) -> tuple[CandidateFeatureVectorV0, ...]:
        return self.feature_construction_result.candidate_features

    @property
    def receipt_id(self) -> str:
        return self.feature_construction_result.operand_audit.hard_constraint_input.receipt_id

    @property
    def field_id(self) -> str:
        return self.feature_construction_result.operand_audit.hard_constraint_input.field_id

    @property
    def theta_a_reference(self) -> ConfigurationRefV1:
        return self.feature_construction_result.operand_audit.hard_constraint_input.theta_a_ref


def construct_scoring_source_snapshot_v2(
    *,
    source_snapshot_id: str,
    feature_construction_result: FeatureConstructionResultV0,
) -> ScoringSourceSnapshotV2:
    """Bind a structural snapshot to the exact supplied feature result."""

    if not isinstance(feature_construction_result, FeatureConstructionResultV0):
        raise ScoringAuditIntegrityError(
            "feature_construction_result must be FeatureConstructionResultV0."
        )
    operand = feature_construction_result.operand_audit
    return ScoringSourceSnapshotV2(
        source_snapshot_id=source_snapshot_id,
        feature_construction_result=feature_construction_result,
        source_component_versions=(
            operand.hard_constraint_input.component_version,
            operand.component_version,
            feature_construction_result.component_version,
        ),
    )


@dataclass(frozen=True, slots=True)
class PreScoreAdmissionEvidenceV2:
    """Separate hard-eligibility and pre-score admission evidence."""

    admission_id: str
    source_snapshot_id: str
    candidate: CandidateRecordV1
    constraint_result: ConstraintResultV2
    feature_vector: CandidateFeatureVectorV0 | None
    state: AdmissionStateV2
    policy_id: str | None
    policy_version: str | None
    evidence_references: tuple[str, ...]
    component_id: str
    component_version: str
    record_version: str = SCORING_RECORD_VERSION
    _original_candidate_reference: CandidateRecordV1 = field(
        init=False, repr=False, compare=False
    )
    _original_constraint_result_reference: ConstraintResultV2 = field(
        init=False, repr=False, compare=False
    )
    _original_feature_vector_reference: CandidateFeatureVectorV0 | None = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        _capture_reference(
            self,
            "_original_candidate_reference",
            self.candidate,
            "The exact admission candidate reference changed.",
        )
        _capture_reference(
            self,
            "_original_constraint_result_reference",
            self.constraint_result,
            "The exact admission V2-result reference changed.",
        )
        _capture_reference(
            self,
            "_original_feature_vector_reference",
            self.feature_vector,
            "The exact admission feature-vector reference changed.",
        )
        _require_text(self.admission_id, "admission_id")
        _require_text(self.source_snapshot_id, "source_snapshot_id")
        _require_text(self.component_id, "component_id")
        _require_text(self.component_version, "component_version")
        _require_optional_text(self.policy_id, "policy_id")
        _require_optional_text(self.policy_version, "policy_version")
        _require_enum(self.state, AdmissionStateV2, "state")
        if self.record_version != SCORING_RECORD_VERSION:
            _fail(ScoringAuditIntegrityError, "Unsupported admission record version.")
        _revalidate(self.candidate, CandidateRecordV1, "candidate")
        _revalidate(self.constraint_result, ConstraintResultV2, "constraint_result")
        if self.constraint_result.candidate is not self.candidate:
            _fail(
                ScoringSourceBindingError,
                "Admission must retain the exact V2 candidate reference.",
            )
        references = _require_tuple(self.evidence_references, "evidence_references")
        for reference in references:
            _require_text(reference, "evidence_reference")
        if len(set(references)) != len(references):
            _fail(
                ScoringAuditIntegrityError,
                "Admission evidence references must be unique and ordered.",
            )

        eligible = (
            self.constraint_result.aggregate_state
            is ConstraintAggregateStateV2.ELIGIBLE
        )
        if self.state in (
            AdmissionStateV2.ADMITTED,
            AdmissionStateV2.REJECTED_PRICE_ONLY_SUPPORT,
        ):
            if not eligible:
                _fail(
                    ScoringAuditIntegrityError,
                    "Only a V2-eligible candidate can enter pre-score admission.",
                )
            if self.feature_vector is None:
                _fail(
                    ScoringAuditIntegrityError,
                    "Eligible admission evidence requires its feature vector.",
                )
            _revalidate(
                self.feature_vector,
                CandidateFeatureVectorV0,
                "feature_vector",
            )
            if (
                self.feature_vector.candidate is not self.candidate
                or self.feature_vector.constraint_result is not self.constraint_result
            ):
                _fail(
                    ScoringSourceBindingError,
                    "Admission feature evidence changed candidate or V2 identity.",
                )
            if self.policy_id is None or self.policy_version is None:
                _fail(
                    ScoringAuditIntegrityError,
                    "Evaluated admission requires policy identity and version.",
                )
            if not references:
                _fail(
                    ScoringAuditIntegrityError,
                    "Evaluated admission requires structural evidence references.",
                )
        else:
            expected = {
                AdmissionStateV2.NOT_APPLICABLE_CONSTRAINT_REJECTED:
                    ConstraintAggregateStateV2.CONSTRAINT_REJECTED,
                AdmissionStateV2.NOT_APPLICABLE_CONSTRAINT_UNAVAILABLE:
                    ConstraintAggregateStateV2.CONSTRAINT_UNAVAILABLE,
            }[self.state]
            if self.constraint_result.aggregate_state is not expected:
                _fail(
                    ScoringAuditIntegrityError,
                    "Admission not-applicability contradicts the original V2 state.",
                )
            if self.feature_vector is not None:
                _fail(
                    ScoringAuditIntegrityError,
                    "A non-eligible V2 candidate cannot receive a feature vector.",
                )
            if self.policy_id is not None or self.policy_version is not None:
                _fail(
                    ScoringAuditIntegrityError,
                    "Admission policy must not be evaluated for a non-eligible candidate.",
                )
            if references:
                _fail(
                    ScoringAuditIntegrityError,
                    "Non-eligible admission must not invent admission-policy evidence.",
                )


_REASON_BY_ADMISSION = {
    AdmissionStateV2.NOT_APPLICABLE_CONSTRAINT_REJECTED:
        ScoreNotApplicableReasonV2.CONSTRAINT_REJECTED,
    AdmissionStateV2.NOT_APPLICABLE_CONSTRAINT_UNAVAILABLE:
        ScoreNotApplicableReasonV2.CONSTRAINT_UNAVAILABLE,
    AdmissionStateV2.REJECTED_PRICE_ONLY_SUPPORT:
        ScoreNotApplicableReasonV2.PRE_SCORE_REJECTED_PRICE_ONLY_SUPPORT,
}


@dataclass(frozen=True, slots=True)
class CandidateScoreEvidenceV2:
    """Raw score or explicit non-applicability for one retained candidate."""

    score_evidence_id: str
    admission: PreScoreAdmissionEvidenceV2
    score_status: ScoreStatusV2
    raw_score: Decimal | None
    not_applicable_reason: ScoreNotApplicableReasonV2 | None
    trusted_scorer_binding: TrustedScorerBindingV1 | None
    component_id: str
    component_version: str
    record_version: str = SCORING_RECORD_VERSION
    _original_admission_reference: PreScoreAdmissionEvidenceV2 = field(
        init=False, repr=False, compare=False
    )
    _original_binding_reference: TrustedScorerBindingV1 | None = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        _capture_reference(
            self,
            "_original_admission_reference",
            self.admission,
            "The exact admission reference changed.",
        )
        _capture_reference(
            self,
            "_original_binding_reference",
            self.trusted_scorer_binding,
            "The exact trusted-scorer binding reference changed.",
        )
        _require_text(self.score_evidence_id, "score_evidence_id")
        _require_text(self.component_id, "component_id")
        _require_text(self.component_version, "component_version")
        _require_enum(self.score_status, ScoreStatusV2, "score_status")
        if self.record_version != SCORING_RECORD_VERSION:
            _fail(ScoringAuditIntegrityError, "Unsupported score-evidence version.")
        _revalidate(self.admission, PreScoreAdmissionEvidenceV2, "admission")

        if self.score_status is ScoreStatusV2.AVAILABLE:
            if self.admission.state is not AdmissionStateV2.ADMITTED:
                _fail(
                    ScoringAuditIntegrityError,
                    "Only an admitted candidate can carry an available raw score.",
                )
            if not isinstance(self.raw_score, Decimal) or not self.raw_score.is_finite():
                _fail(
                    ScoringAuditIntegrityError,
                    "An available raw score must be a finite Decimal.",
                )
            if self.not_applicable_reason is not None:
                _fail(
                    ScoringAuditIntegrityError,
                    "An available raw score cannot carry a not-applicable reason.",
                )
            if self.trusted_scorer_binding is None:
                _fail(
                    ScoringAuditIntegrityError,
                    "An available raw score requires a trusted-scorer binding.",
                )
            _revalidate(
                self.trusted_scorer_binding,
                TrustedScorerBindingV1,
                "trusted_scorer_binding",
            )
            if (
                self.trusted_scorer_binding.parent_theta_a
                != self.constraint_result.theta_a_reference
            ):
                _fail(
                    ScoringAuditIntegrityError,
                    "Trusted scorer Theta_A differs from the exact V2 source.",
                )
            sign, digits, exponent = self.raw_score.as_tuple()
            if sign and not any(digits):
                _fail(
                    ScoringAuditIntegrityError,
                    "Negative zero is not a permitted raw-score value.",
                )
            if exponent != -self.trusted_scorer_binding.numeric_scale:
                _fail(
                    ScoringAuditIntegrityError,
                    "Raw-score scale differs from the structural scorer binding.",
                )
            if len(digits) > self.trusted_scorer_binding.numeric_precision:
                _fail(
                    ScoringAuditIntegrityError,
                    "Raw-score precision exceeds the structural scorer binding.",
                )
        else:
            if self.admission.state is AdmissionStateV2.ADMITTED:
                _fail(
                    ScoringAuditIntegrityError,
                    "An admitted candidate cannot silently become NOT_APPLICABLE.",
                )
            if self.raw_score is not None:
                _fail(
                    ScoringAuditIntegrityError,
                    "NOT_APPLICABLE requires raw_score=null.",
                )
            expected_reason = _REASON_BY_ADMISSION[self.admission.state]
            if self.not_applicable_reason is not expected_reason:
                _fail(
                    ScoringAuditIntegrityError,
                    "Score reason contradicts the admission/V2 state.",
                )
            if self.trusted_scorer_binding is not None:
                _fail(
                    ScoringAuditIntegrityError,
                    "NOT_APPLICABLE cannot carry a trusted scorer binding.",
                )

    @property
    def candidate(self) -> CandidateRecordV1:
        return self.admission.candidate

    @property
    def constraint_result(self) -> ConstraintResultV2:
        return self.admission.constraint_result

    @property
    def feature_vector(self) -> CandidateFeatureVectorV0 | None:
        return self.admission.feature_vector


def _validate_population(
    snapshot: ScoringSourceSnapshotV2,
    entries: tuple[CandidateScoreEvidenceV2, ...],
) -> None:
    if len(entries) != len(snapshot.candidates):
        _fail(
            ScoringAuditIntegrityError,
            "Exactly one score audit is required per retained D3 candidate.",
        )
    features_by_candidate = {
        feature.candidate.candidate_id: feature
        for feature in snapshot.candidate_features
    }
    score_ids: set[str] = set()
    admission_ids: set[str] = set()
    for entry, candidate, result in zip(
        entries,
        snapshot.candidates,
        snapshot.constraint_results,
        strict=True,
    ):
        _revalidate(entry, CandidateScoreEvidenceV2, "candidate_score")
        if entry.score_evidence_id in score_ids:
            _fail(ScoringAuditIntegrityError, "score_evidence_id values must be unique.")
        if entry.admission.admission_id in admission_ids:
            _fail(ScoringAuditIntegrityError, "admission_id values must be unique.")
        score_ids.add(entry.score_evidence_id)
        admission_ids.add(entry.admission.admission_id)
        if entry.admission.source_snapshot_id != snapshot.source_snapshot_id:
            _fail(
                ScoringSourceBindingError,
                "Score admission is bound to a different source snapshot.",
            )
        if entry.candidate is not candidate:
            _fail(
                ScoringSourceBindingError,
                "Score entries must preserve exact D3 candidate order and identity.",
            )
        if entry.constraint_result is not result:
            _fail(
                ScoringSourceBindingError,
                "Score entries must preserve exact V2 result order and identity.",
            )
        expected_feature = features_by_candidate.get(candidate.candidate_id)
        if entry.feature_vector is not expected_feature:
            _fail(
                ScoringSourceBindingError,
                "Score entries must preserve exact eligible feature-vector identity.",
            )
        if result.c0_candidate is not snapshot.c0_candidate:
            _fail(
                ScoringSourceBindingError,
                "Every score entry must retain the exact permanent c0.",
            )


@dataclass(frozen=True, slots=True)
class FieldScoringAuditV2:
    """Complete successful or zero-admitted field scoring audit."""

    field_audit_id: str
    source_snapshot: ScoringSourceSnapshotV2
    candidate_scores: tuple[CandidateScoreEvidenceV2, ...]
    admitted_candidate_ids: tuple[str, ...]
    admitted_candidate_count: int
    resolver_invocation: ScorerInvocationStateV2
    resolver_result: TrustedScorerResolverResultV1 | None
    trusted_scorer_binding: TrustedScorerBindingV1 | None
    completion_state: FieldScoringCompletionStateV2
    component_id: str
    component_version: str
    record_version: str = SCORING_RECORD_VERSION
    _original_source_snapshot_reference: ScoringSourceSnapshotV2 = field(
        init=False, repr=False, compare=False
    )
    _original_candidate_score_references: tuple[CandidateScoreEvidenceV2, ...] = field(
        init=False, repr=False, compare=False
    )
    _original_resolver_result_reference: TrustedScorerResolverResultV1 | None = field(
        init=False, repr=False, compare=False
    )
    _original_binding_reference: TrustedScorerBindingV1 | None = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        _capture_reference(
            self,
            "_original_source_snapshot_reference",
            self.source_snapshot,
            "The exact scoring source snapshot reference changed.",
        )
        _capture_reference_tuple(
            self,
            "_original_candidate_score_references",
            self.candidate_scores,
            "The exact candidate-score entry references changed.",
        )
        _capture_reference(
            self,
            "_original_resolver_result_reference",
            self.resolver_result,
            "The exact resolver-result reference changed.",
        )
        _capture_reference(
            self,
            "_original_binding_reference",
            self.trusted_scorer_binding,
            "The exact aggregate trusted binding reference changed.",
        )
        _require_text(self.field_audit_id, "field_audit_id")
        _require_text(self.component_id, "component_id")
        _require_text(self.component_version, "component_version")
        _require_enum(self.resolver_invocation, ScorerInvocationStateV2, "resolver_invocation")
        _require_enum(self.completion_state, FieldScoringCompletionStateV2, "completion_state")
        if self.record_version != SCORING_RECORD_VERSION:
            _fail(ScoringAuditIntegrityError, "Unsupported field-audit version.")
        _revalidate(self.source_snapshot, ScoringSourceSnapshotV2, "source_snapshot")
        entries = _require_tuple(self.candidate_scores, "candidate_scores")
        if any(not isinstance(entry, CandidateScoreEvidenceV2) for entry in entries):
            _fail(ScoringAuditIntegrityError, "candidate_scores contains an invalid record.")
        _validate_population(self.source_snapshot, entries)
        admitted = tuple(
            entry.candidate.candidate_id
            for entry in entries
            if entry.admission.state is AdmissionStateV2.ADMITTED
        )
        if self.admitted_candidate_ids != admitted:
            _fail(
                ScoringAuditIntegrityError,
                "admitted_candidate_ids must be the canonical admitted subsequence.",
            )
        if (
            isinstance(self.admitted_candidate_count, bool)
            or not isinstance(self.admitted_candidate_count, int)
            or self.admitted_candidate_count != len(admitted)
        ):
            _fail(ScoringAuditIntegrityError, "admitted_candidate_count is inconsistent.")

        if not admitted:
            if self.completion_state is not FieldScoringCompletionStateV2.COMPLETE_ZERO_ADMITTED_BYPASS:
                _fail(ScoringAuditIntegrityError, "Zero admitted candidates require bypass completion.")
            if self.resolver_invocation is not ScorerInvocationStateV2.NOT_INVOKED_ZERO_ADMITTED:
                _fail(ScoringAuditIntegrityError, "Zero-admitted bypass must record resolver non-invocation.")
            if self.resolver_result is not None or self.trusted_scorer_binding is not None:
                _fail(ScoringAuditIntegrityError, "Zero-admitted bypass cannot fabricate resolver or manifest readiness.")
            if any(entry.score_status is not ScoreStatusV2.NOT_APPLICABLE for entry in entries):
                _fail(ScoringAuditIntegrityError, "Zero-admitted bypass requires all scores NOT_APPLICABLE.")
            return

        if self.completion_state is not FieldScoringCompletionStateV2.COMPLETE_SCORED:
            _fail(ScoringAuditIntegrityError, "Admitted candidates require complete-scored state.")
        if self.resolver_invocation is not ScorerInvocationStateV2.INVOKED:
            _fail(ScoringAuditIntegrityError, "Scored fields must record resolver invocation.")
        if self.resolver_result is None or self.trusted_scorer_binding is None:
            _fail(ScoringAuditIntegrityError, "Scored fields require resolver result and trusted binding.")
        _revalidate(self.resolver_result, TrustedScorerResolverResultV1, "resolver_result")
        _revalidate(self.trusted_scorer_binding, TrustedScorerBindingV1, "trusted_scorer_binding")
        if self.resolver_result.state is not TrustedResolverStateV1.READY:
            _fail(ScoringAuditIntegrityError, "A successful score audit requires resolver READY.")
        if self.resolver_result.parent_theta_a != self.source_snapshot.theta_a_reference:
            _fail(ScoringAuditIntegrityError, "Resolver Theta_A differs from the exact scoring source.")
        if self.trusted_scorer_binding.parent_theta_a != self.source_snapshot.theta_a_reference:
            _fail(ScoringAuditIntegrityError, "Trusted scorer binding Theta_A differs from the exact scoring source.")
        if self.resolver_result.binding is not self.trusted_scorer_binding:
            _fail(ScoringSourceBindingError, "The resolver and field audit must share the exact trusted binding.")
        manifest = self.resolver_result.manifest
        if manifest is None:  # READY validation requires it; keep the local boundary exact.
            _fail(ScoringAuditIntegrityError, "Resolver READY unexpectedly lacks its manifest.")
        for entry in entries:
            if entry.feature_vector is not None and (
                entry.feature_vector.feature_schema_id != manifest.feature_schema_id
                or entry.feature_vector.feature_slots != manifest.feature_slot_order
            ):
                _fail(
                    ScoringAuditIntegrityError,
                    "Feature-vector schema/order differs from the trusted manifest.",
                )
            if entry.admission.state in (
                AdmissionStateV2.ADMITTED,
                AdmissionStateV2.REJECTED_PRICE_ONLY_SUPPORT,
            ) and (
                entry.admission.policy_id != manifest.admission_policy_id
                or entry.admission.policy_version != manifest.admission_policy_version
            ):
                _fail(
                    ScoringAuditIntegrityError,
                    "Admission policy identity differs from the trusted manifest.",
                )
            if entry.admission.state is AdmissionStateV2.ADMITTED:
                if entry.score_status is not ScoreStatusV2.AVAILABLE:
                    _fail(ScoringAuditIntegrityError, "Every admitted candidate requires an available score.")
                if entry.trusted_scorer_binding is not self.trusted_scorer_binding:
                    _fail(ScoringSourceBindingError, "Available candidate scores must share the exact field binding.")


@dataclass(frozen=True, slots=True)
class FieldScoringFailureV2:
    """Atomic field-level failure with no partial candidate score aggregate."""

    failure_id: str
    source_snapshot: ScoringSourceSnapshotV2
    admissions: tuple[PreScoreAdmissionEvidenceV2, ...]
    admitted_candidate_ids: tuple[str, ...]
    resolver_invocation: ScorerInvocationStateV2
    resolver_result: TrustedScorerResolverResultV1 | None
    failure_state: FieldScoringFailureStateV2
    failure_code: str
    component_id: str
    component_version: str
    record_version: str = SCORING_RECORD_VERSION
    _original_source_snapshot_reference: ScoringSourceSnapshotV2 = field(
        init=False, repr=False, compare=False
    )
    _original_admission_references: tuple[PreScoreAdmissionEvidenceV2, ...] = field(
        init=False, repr=False, compare=False
    )
    _original_resolver_result_reference: TrustedScorerResolverResultV1 | None = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        _capture_reference(self, "_original_source_snapshot_reference", self.source_snapshot, "The exact failure source snapshot changed.")
        _capture_reference_tuple(self, "_original_admission_references", self.admissions, "The exact failure admission references changed.")
        _capture_reference(self, "_original_resolver_result_reference", self.resolver_result, "The exact failure resolver result changed.")
        _require_text(self.failure_id, "failure_id")
        _require_text(self.failure_code, "failure_code")
        _require_text(self.component_id, "component_id")
        _require_text(self.component_version, "component_version")
        _require_enum(self.resolver_invocation, ScorerInvocationStateV2, "resolver_invocation")
        _require_enum(self.failure_state, FieldScoringFailureStateV2, "failure_state")
        if self.record_version != SCORING_RECORD_VERSION:
            _fail(ScoringAuditIntegrityError, "Unsupported field-failure version.")
        _revalidate(self.source_snapshot, ScoringSourceSnapshotV2, "source_snapshot")
        admissions = _require_tuple(self.admissions, "admissions")
        if len(admissions) != len(self.source_snapshot.candidates):
            _fail(ScoringAuditIntegrityError, "Field failure requires one admission per retained candidate.")
        features_by_candidate = {
            feature.candidate.candidate_id: feature
            for feature in self.source_snapshot.candidate_features
        }
        seen: set[str] = set()
        for admission, candidate, result in zip(
            admissions,
            self.source_snapshot.candidates,
            self.source_snapshot.constraint_results,
            strict=True,
        ):
            _revalidate(admission, PreScoreAdmissionEvidenceV2, "admission")
            if admission.admission_id in seen:
                _fail(ScoringAuditIntegrityError, "admission_id values must be unique.")
            seen.add(admission.admission_id)
            if admission.source_snapshot_id != self.source_snapshot.source_snapshot_id:
                _fail(
                    ScoringSourceBindingError,
                    "Failure admission is bound to a different source snapshot.",
                )
            if admission.candidate is not candidate or admission.constraint_result is not result:
                _fail(ScoringSourceBindingError, "Failure admissions must preserve exact source order and identity.")
            expected_feature = features_by_candidate.get(candidate.candidate_id)
            if admission.feature_vector is not expected_feature:
                _fail(
                    ScoringSourceBindingError,
                    "Failure admissions must preserve exact feature-vector identity.",
                )
        admitted = tuple(
            admission.candidate.candidate_id
            for admission in admissions
            if admission.state is AdmissionStateV2.ADMITTED
        )
        if self.admitted_candidate_ids != admitted:
            _fail(ScoringAuditIntegrityError, "Failure admitted IDs must match canonical admissions.")
        if not admitted:
            _fail(ScoringAuditIntegrityError, "Zero admitted candidates require the successful audit-only bypass, not failure.")
        if self.resolver_invocation is not ScorerInvocationStateV2.INVOKED:
            _fail(ScoringAuditIntegrityError, "A post-admission field failure requires resolver invocation.")

        if self.failure_state is FieldScoringFailureStateV2.TRUSTED_SCORER_NOT_READY:
            expected_resolver_state = TrustedResolverStateV1.NOT_READY
        elif self.failure_state is FieldScoringFailureStateV2.TRUSTED_SCORER_NOT_VALID:
            expected_resolver_state = TrustedResolverStateV1.NOT_VALID
        else:
            expected_resolver_state = None
        if expected_resolver_state is not None:
            if self.resolver_result is None:
                _fail(ScoringAuditIntegrityError, "Resolver failure requires its resolver result.")
            _revalidate(self.resolver_result, TrustedScorerResolverResultV1, "resolver_result")
            if self.resolver_result.state is not expected_resolver_state:
                _fail(ScoringAuditIntegrityError, "Field failure state contradicts resolver state.")
            if self.resolver_result.parent_theta_a != self.source_snapshot.theta_a_reference:
                _fail(ScoringAuditIntegrityError, "Failure resolver Theta_A differs from the exact scoring source.")
        elif self.resolver_result is not None:
            _revalidate(self.resolver_result, TrustedScorerResolverResultV1, "resolver_result")
            if self.resolver_result.parent_theta_a != self.source_snapshot.theta_a_reference:
                _fail(ScoringAuditIntegrityError, "Failure resolver Theta_A differs from the exact scoring source.")
            if self.resolver_result.state is not TrustedResolverStateV1.READY:
                _fail(
                    ScoringAuditIntegrityError,
                    "A non-READY resolver result must use its matching trusted-scorer failure state.",
                )


@dataclass(frozen=True, slots=True)
class ScoringOperationResultV2:
    """Discriminated complete field audit or atomic field failure."""

    operation_result_id: str
    outcome: FieldScoringAuditV2 | FieldScoringFailureV2
    record_version: str = SCORING_RECORD_VERSION
    _original_outcome_reference: FieldScoringAuditV2 | FieldScoringFailureV2 = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        _capture_reference(
            self,
            "_original_outcome_reference",
            self.outcome,
            "The exact scoring operation outcome reference changed.",
        )
        _require_text(self.operation_result_id, "operation_result_id")
        if not isinstance(self.outcome, (FieldScoringAuditV2, FieldScoringFailureV2)):
            _fail(ScoringAuditIntegrityError, "outcome must be a complete audit or field failure.")
        self.outcome.__post_init__()
        if self.record_version != SCORING_RECORD_VERSION:
            _fail(ScoringAuditIntegrityError, "Unsupported operation-result version.")


__all__ = (
    "AdmissionStateV2",
    "CandidateScoreEvidenceV2",
    "FieldScoringAuditV2",
    "FieldScoringCompletionStateV2",
    "FieldScoringFailureStateV2",
    "FieldScoringFailureV2",
    "PreScoreAdmissionEvidenceV2",
    "SCORING_COMPONENT_VERSION",
    "SCORING_RECORD_VERSION",
    "ScoreNotApplicableReasonV2",
    "ScoreStatusV2",
    "ScorerInvocationStateV2",
    "ScoringAuditIntegrityError",
    "ScoringContractError",
    "ScoringOperationResultV2",
    "ScoringSourceBindingError",
    "ScoringSourceSnapshotV2",
    "construct_scoring_source_snapshot_v2",
)
