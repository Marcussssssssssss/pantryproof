"""Synthetic-only deterministic candidate limiting and overflow audit.

This component consumes the completed preliminary ranking.  It does not rerun
ranking or construct altered shared candidate records, evidence, or decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .candidate_deduplication import EquivalentToC0AuditV0
from .candidate_ranking import (
    CandidateRankingBlockV0,
    CandidateRankingReadinessV0,
    PreliminaryCandidateRankingResultV0,
    ProvenanceMaterializationStatusV0,
    RankedAlteredCandidateV0,
)
from .contracts import (
    CandidateRecordV1,
    ConfigurationKind,
    ConfigurationRefV1,
    ConfigurationState,
)


CANDIDATE_LIMITING_POLICY_ID = "total-candidate-limit-v0"
CANDIDATE_LIMITING_TIE_POLICY_ID = "strict-ranked-boundary-v0"
CANDIDATE_LIMITING_SCOPE_ID = "synthetic-fixture-only-v0"
CANDIDATE_LIMITING_COMPONENT_VERSION = "candidate-limiting-v0"
CANDIDATE_LIMITING_RECORD_VERSION = "candidate-limiting-record-v0"
TOTAL_CANDIDATE_LIMIT_EXCEEDED = "TOTAL_CANDIDATE_LIMIT_EXCEEDED"


class CandidateLimitingIntegrityError(ValueError):
    """Limiting input or output contradicts its immutable ranking evidence."""


class CandidateLimitDecisionStatusV0(str, Enum):
    WITHIN_CAPACITY = "WITHIN_CAPACITY"
    LIMIT_OVERFLOW = "LIMIT_OVERFLOW"


class CandidateLimitingReadinessV0(str, Enum):
    LIMIT_APPLIED = "LIMIT_APPLIED"
    RANKING_UNAVAILABLE = "RANKING_UNAVAILABLE"


class BoundaryTieStatusV0(str, Enum):
    NO_SPLIT = "NO_SPLIT"
    TIE_GROUP_SPLIT = "TIE_GROUP_SPLIT"
    RANKING_UNAVAILABLE = "RANKING_UNAVAILABLE"


class CandidateRetainedSetReadinessV0(str, Enum):
    STRUCTURALLY_READY = "STRUCTURALLY_READY"
    BLOCKED_BY_SELECTED_PROVENANCE = "BLOCKED_BY_SELECTED_PROVENANCE"
    RANKING_UNAVAILABLE = "RANKING_UNAVAILABLE"


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")


def _require_limit(value: int) -> None:
    if type(value) is not int or value < 1:
        raise ValueError("candidate_limit must be a non-Boolean integer at least one.")


@dataclass(frozen=True, slots=True)
class CandidateLimitingConfigurationV0:
    """Unauthenticated synthetic fixture configuration owned by Theta_A."""

    theta_a_ref: ConfigurationRefV1
    candidate_limit: int
    fixture_reference: str
    limiting_policy_id: str = CANDIDATE_LIMITING_POLICY_ID
    tie_policy_id: str = CANDIDATE_LIMITING_TIE_POLICY_ID
    scope_id: str = CANDIDATE_LIMITING_SCOPE_ID
    component_version: str = CANDIDATE_LIMITING_COMPONENT_VERSION
    record_version: str = CANDIDATE_LIMITING_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.theta_a_ref, ConfigurationRefV1):
            raise TypeError("theta_a_ref must be ConfigurationRefV1.")
        try:
            self.theta_a_ref.__post_init__()
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "theta_a_ref failed its ConfigurationRefV1 invariants."
            ) from exc
        if self.theta_a_ref.kind is not ConfigurationKind.THETA_A:
            raise ValueError("Candidate limiting requires a THETA_A reference.")
        if self.theta_a_ref.state is not ConfigurationState.READY:
            raise ValueError("Candidate limiting requires READY THETA_A.")
        _require_text(self.theta_a_ref.content_hash or "", "Theta_A content hash")
        _require_limit(self.candidate_limit)
        _require_text(self.fixture_reference, "fixture_reference")
        if self.limiting_policy_id != CANDIDATE_LIMITING_POLICY_ID:
            raise ValueError("Unsupported candidate-limiting policy.")
        if self.tie_policy_id != CANDIDATE_LIMITING_TIE_POLICY_ID:
            raise ValueError("Unsupported candidate-limit tie policy.")
        if self.scope_id != CANDIDATE_LIMITING_SCOPE_ID:
            raise ValueError("Candidate limiting V0 is synthetic-fixture-only.")
        if self.component_version != CANDIDATE_LIMITING_COMPONENT_VERSION:
            raise ValueError("Unsupported candidate-limiting component version.")
        if self.record_version != CANDIDATE_LIMITING_RECORD_VERSION:
            raise ValueError("Unsupported candidate-limiting record version.")


@dataclass(frozen=True, slots=True)
class CandidateLimitDecisionV0:
    """One local capacity decision retaining the exact upstream ranked record."""

    ranked_candidate: RankedAlteredCandidateV0
    status: CandidateLimitDecisionStatusV0
    overflow_reason: str | None = None
    component_version: str = CANDIDATE_LIMITING_COMPONENT_VERSION
    record_version: str = CANDIDATE_LIMITING_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.ranked_candidate, RankedAlteredCandidateV0):
            raise TypeError("ranked_candidate must be RankedAlteredCandidateV0.")
        if not isinstance(self.status, CandidateLimitDecisionStatusV0):
            raise TypeError("status must be CandidateLimitDecisionStatusV0.")
        if self.status is CandidateLimitDecisionStatusV0.WITHIN_CAPACITY:
            if self.overflow_reason is not None:
                raise ValueError("A within-capacity decision has no overflow reason.")
        elif self.overflow_reason != TOTAL_CANDIDATE_LIMIT_EXCEEDED:
            raise ValueError("Limit overflow requires the approved overflow reason.")
        if self.component_version != CANDIDATE_LIMITING_COMPONENT_VERSION:
            raise ValueError("Unsupported candidate-limiting component version.")
        if self.record_version != CANDIDATE_LIMITING_RECORD_VERSION:
            raise ValueError("Unsupported candidate-limiting record version.")

    @property
    def candidate_id(self) -> str:
        return self.ranked_candidate.identity.candidate_id

    @property
    def provenance_status(self) -> ProvenanceMaterializationStatusV0:
        return self.ranked_candidate.provenance_status


@dataclass(frozen=True, slots=True)
class BoundaryTieAuditV0:
    """Audit of a stored tie group split by the strict altered capacity."""

    status: BoundaryTieStatusV0
    candidate_limit: int
    altered_capacity: int
    tie_group_id: str | None = None
    member_candidate_ids: tuple[str, ...] = ()
    within_capacity_candidate_ids: tuple[str, ...] = ()
    overflow_candidate_ids: tuple[str, ...] = ()
    tie_policy_id: str = CANDIDATE_LIMITING_TIE_POLICY_ID
    record_version: str = CANDIDATE_LIMITING_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.status, BoundaryTieStatusV0):
            raise TypeError("status must be BoundaryTieStatusV0.")
        _require_limit(self.candidate_limit)
        if type(self.altered_capacity) is not int or self.altered_capacity < 0:
            raise ValueError("altered_capacity must be a nonnegative integer.")
        if self.altered_capacity != self.candidate_limit - 1:
            raise CandidateLimitingIntegrityError(
                "Altered capacity must equal total candidate limit minus c0."
            )
        if self.status is BoundaryTieStatusV0.TIE_GROUP_SPLIT:
            _require_text(self.tie_group_id or "", "tie_group_id")
            if not self.member_candidate_ids:
                raise ValueError("A split tie audit requires its complete group.")
            if (
                not self.within_capacity_candidate_ids
                or not self.overflow_candidate_ids
            ):
                raise ValueError("A split tie must have members on both sides.")
            if self.member_candidate_ids != (
                self.within_capacity_candidate_ids + self.overflow_candidate_ids
            ):
                raise CandidateLimitingIntegrityError(
                    "Split tie members must preserve their capacity partition order."
                )
            if len(self.member_candidate_ids) != len(set(self.member_candidate_ids)):
                raise ValueError("Boundary tie candidate IDs must be unique.")
        elif any(
            (
                self.tie_group_id is not None,
                self.member_candidate_ids,
                self.within_capacity_candidate_ids,
                self.overflow_candidate_ids,
            )
        ):
            raise ValueError("A non-split tie audit cannot contain tie members.")
        if self.tie_policy_id != CANDIDATE_LIMITING_TIE_POLICY_ID:
            raise ValueError("Unsupported candidate-limit tie policy.")
        if self.record_version != CANDIDATE_LIMITING_RECORD_VERSION:
            raise ValueError("Unsupported candidate-limiting record version.")


def _boundary_tie_audit(
    ranked: tuple[RankedAlteredCandidateV0, ...],
    configuration: CandidateLimitingConfigurationV0,
) -> BoundaryTieAuditV0:
    candidate_limit = configuration.candidate_limit
    capacity = candidate_limit - 1
    count = len(ranked)
    if 0 < capacity < count:
        retained_edge = ranked[capacity - 1].preliminary_rank.tie_group_id
        overflow_edge = ranked[capacity].preliminary_rank.tie_group_id
        if retained_edge is not None and retained_edge == overflow_edge:
            group = tuple(
                item
                for item in ranked
                if item.preliminary_rank.tie_group_id == retained_edge
            )
            members = tuple(item.identity.candidate_id for item in group)
            within = tuple(
                item.identity.candidate_id
                for item in group
                if item.preliminary_rank.rank_position <= capacity
            )
            overflow = tuple(
                item.identity.candidate_id
                for item in group
                if item.preliminary_rank.rank_position > capacity
            )
            return BoundaryTieAuditV0(
                status=BoundaryTieStatusV0.TIE_GROUP_SPLIT,
                candidate_limit=candidate_limit,
                altered_capacity=capacity,
                tie_group_id=retained_edge,
                member_candidate_ids=members,
                within_capacity_candidate_ids=within,
                overflow_candidate_ids=overflow,
            )
    return BoundaryTieAuditV0(
        status=BoundaryTieStatusV0.NO_SPLIT,
        candidate_limit=candidate_limit,
        altered_capacity=capacity,
    )


def _validate_inputs(
    ranking_result: PreliminaryCandidateRankingResultV0,
    configuration: CandidateLimitingConfigurationV0,
) -> None:
    if not isinstance(ranking_result, PreliminaryCandidateRankingResultV0):
        raise TypeError(
            "ranking_result must be PreliminaryCandidateRankingResultV0."
        )
    if not isinstance(configuration, CandidateLimitingConfigurationV0):
        raise TypeError(
            "configuration must be CandidateLimitingConfigurationV0."
        )
    try:
        configuration.__post_init__()
    except (TypeError, ValueError) as exc:
        raise CandidateLimitingIntegrityError(
            "Limiting configuration failed its complete invariant revalidation."
        ) from exc
    try:
        ranking_result.__post_init__()
    except (TypeError, ValueError) as exc:
        raise CandidateLimitingIntegrityError(
            "Ranking result failed its complete upstream reconstruction."
        ) from exc
    if configuration.theta_a_ref != ranking_result.configuration.theta_a_ref:
        raise CandidateLimitingIntegrityError(
            "Limiting configuration must equal the ranking Theta_A reference."
        )


def _derive_limit(
    ranking_result: PreliminaryCandidateRankingResultV0,
    configuration: CandidateLimitingConfigurationV0,
) -> tuple[
    CandidateLimitingReadinessV0,
    tuple[CandidateLimitDecisionV0, ...],
    tuple[CandidateRankingBlockV0, ...],
    BoundaryTieAuditV0,
    CandidateRetainedSetReadinessV0,
]:
    _validate_inputs(ranking_result, configuration)
    capacity = configuration.candidate_limit - 1
    if ranking_result.readiness is CandidateRankingReadinessV0.RANKING_BLOCKED:
        return (
            CandidateLimitingReadinessV0.RANKING_UNAVAILABLE,
            (),
            ranking_result.ranking_blocks,
            BoundaryTieAuditV0(
                status=BoundaryTieStatusV0.RANKING_UNAVAILABLE,
                candidate_limit=configuration.candidate_limit,
                altered_capacity=capacity,
            ),
            CandidateRetainedSetReadinessV0.RANKING_UNAVAILABLE,
        )

    ranked = ranking_result.ranked_candidates
    positions = tuple(item.preliminary_rank.rank_position for item in ranked)
    if positions != tuple(range(1, len(ranked) + 1)):
        raise CandidateLimitingIntegrityError(
            "Stored altered-candidate ranks must be consecutive and one-based."
        )
    decisions = tuple(
        CandidateLimitDecisionV0(
            ranked_candidate=item,
            status=(
                CandidateLimitDecisionStatusV0.WITHIN_CAPACITY
                if item.preliminary_rank.rank_position <= capacity
                else CandidateLimitDecisionStatusV0.LIMIT_OVERFLOW
            ),
            overflow_reason=(
                None
                if item.preliminary_rank.rank_position <= capacity
                else TOTAL_CANDIDATE_LIMIT_EXCEEDED
            ),
        )
        for item in ranked
    )
    within_count = sum(
        item.status is CandidateLimitDecisionStatusV0.WITHIN_CAPACITY
        for item in decisions
    )
    overflow_count = len(decisions) - within_count
    if (
        within_count != min(len(ranked), capacity)
        or overflow_count != max(0, len(ranked) - capacity)
        or 1 + within_count > configuration.candidate_limit
    ):
        raise CandidateLimitingIntegrityError(
            "Candidate-limit count invariants were not satisfied."
        )
    retained_readiness = (
        CandidateRetainedSetReadinessV0.BLOCKED_BY_SELECTED_PROVENANCE
        if any(
            item.status is CandidateLimitDecisionStatusV0.WITHIN_CAPACITY
            and item.provenance_status is ProvenanceMaterializationStatusV0.BLOCKED
            for item in decisions
        )
        else CandidateRetainedSetReadinessV0.STRUCTURALLY_READY
    )
    return (
        CandidateLimitingReadinessV0.LIMIT_APPLIED,
        decisions,
        (),
        _boundary_tie_audit(ranked, configuration),
        retained_readiness,
    )


@dataclass(frozen=True, slots=True)
class CandidateLimitResultV0:
    """Reconstructable capacity audit for every ranked or blocked identity."""

    ranking_result: PreliminaryCandidateRankingResultV0
    configuration: CandidateLimitingConfigurationV0
    original_candidate: CandidateRecordV1
    equivalent_to_c0: EquivalentToC0AuditV0 | None
    readiness: CandidateLimitingReadinessV0
    decisions: tuple[CandidateLimitDecisionV0, ...]
    ranking_blocks: tuple[CandidateRankingBlockV0, ...]
    boundary_tie_audit: BoundaryTieAuditV0
    retained_set_readiness: CandidateRetainedSetReadinessV0
    component_version: str = CANDIDATE_LIMITING_COMPONENT_VERSION
    record_version: str = CANDIDATE_LIMITING_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(
            self.ranking_result, PreliminaryCandidateRankingResultV0
        ):
            raise TypeError(
                "ranking_result must be PreliminaryCandidateRankingResultV0."
            )
        if not isinstance(self.configuration, CandidateLimitingConfigurationV0):
            raise TypeError(
                "configuration must be CandidateLimitingConfigurationV0."
            )
        if self.original_candidate is not self.ranking_result.original_candidate:
            raise CandidateLimitingIntegrityError(
                "Permanent c0 must be preserved unchanged and by reference."
            )
        if self.equivalent_to_c0 is not self.ranking_result.equivalent_to_c0:
            raise CandidateLimitingIntegrityError(
                "The c0-equivalence audit must be preserved unchanged and by reference."
            )
        if not isinstance(self.readiness, CandidateLimitingReadinessV0):
            raise TypeError("readiness must be CandidateLimitingReadinessV0.")
        if any(
            not isinstance(item, CandidateLimitDecisionV0)
            for item in self.decisions
        ):
            raise TypeError("decisions contains an unsupported record.")
        if any(
            not isinstance(item, CandidateRankingBlockV0)
            for item in self.ranking_blocks
        ):
            raise TypeError("ranking_blocks contains an unsupported record.")
        if not isinstance(self.boundary_tie_audit, BoundaryTieAuditV0):
            raise TypeError("boundary_tie_audit must be BoundaryTieAuditV0.")
        if not isinstance(
            self.retained_set_readiness, CandidateRetainedSetReadinessV0
        ):
            raise TypeError(
                "retained_set_readiness must be CandidateRetainedSetReadinessV0."
            )
        if self.component_version != CANDIDATE_LIMITING_COMPONENT_VERSION:
            raise ValueError("Unsupported candidate-limiting component version.")
        if self.record_version != CANDIDATE_LIMITING_RECORD_VERSION:
            raise ValueError("Unsupported candidate-limiting record version.")

        expected = _derive_limit(self.ranking_result, self.configuration)
        observed = (
            self.readiness,
            self.decisions,
            self.ranking_blocks,
            self.boundary_tie_audit,
            self.retained_set_readiness,
        )
        if observed != expected:
            raise CandidateLimitingIntegrityError(
                "Limit result must equal its complete deterministic derivation."
            )

        if self.readiness is CandidateLimitingReadinessV0.LIMIT_APPLIED:
            ranked = self.ranking_result.ranked_candidates
            if len(self.decisions) != len(ranked) or any(
                decision.ranked_candidate is not source
                for decision, source in zip(self.decisions, ranked, strict=True)
            ):
                raise CandidateLimitingIntegrityError(
                    "Every decision must retain its exact upstream ranked record."
                )
            upstream_ids = tuple(item.identity.candidate_id for item in ranked)
            output_ids = tuple(item.candidate_id for item in self.decisions)
        else:
            blocks = self.ranking_result.ranking_blocks
            if len(self.ranking_blocks) != len(blocks) or any(
                observed_block is not source_block
                for observed_block, source_block in zip(
                    self.ranking_blocks, blocks, strict=True
                )
            ):
                raise CandidateLimitingIntegrityError(
                    "Ranking-unavailable output must retain exact upstream blocks."
                )
            upstream_ids = tuple(item.identity.candidate_id for item in blocks)
            output_ids = tuple(item.identity.candidate_id for item in self.ranking_blocks)
        if output_ids != upstream_ids or len(output_ids) != len(set(output_ids)):
            raise CandidateLimitingIntegrityError(
                "Every altered identity must be accounted for exactly once."
            )

    @property
    def altered_capacity(self) -> int:
        return self.configuration.candidate_limit - 1

    @property
    def within_capacity_count(self) -> int:
        return sum(
            item.status is CandidateLimitDecisionStatusV0.WITHIN_CAPACITY
            for item in self.decisions
        )

    @property
    def overflow_count(self) -> int:
        return sum(
            item.status is CandidateLimitDecisionStatusV0.LIMIT_OVERFLOW
            for item in self.decisions
        )

    @property
    def bounded_total_count(self) -> int | None:
        if self.readiness is CandidateLimitingReadinessV0.RANKING_UNAVAILABLE:
            return None
        return 1 + self.within_capacity_count


def apply_candidate_limit(
    *,
    ranking_result: PreliminaryCandidateRankingResultV0,
    configuration: CandidateLimitingConfigurationV0,
) -> CandidateLimitResultV0:
    """Apply the synthetic total limit without reranking or shared finalization."""

    derived = _derive_limit(ranking_result, configuration)
    return CandidateLimitResultV0(
        ranking_result=ranking_result,
        configuration=configuration,
        original_candidate=ranking_result.original_candidate,
        equivalent_to_c0=ranking_result.equivalent_to_c0,
        readiness=derived[0],
        decisions=derived[1],
        ranking_blocks=derived[2],
        boundary_tie_audit=derived[3],
        retained_set_readiness=derived[4],
    )
