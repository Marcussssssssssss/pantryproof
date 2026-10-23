"""Synthetic-only materialization of ranked candidates into shared records.

This component is a deterministic projection of a validated candidate-limiting
result.  It does not rerun candidate production, ranking, or limiting, and it
does not create candidate evidence or make correction decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .candidate_deduplication import EquivalentToC0AuditV0
from .candidate_limiting import (
    TOTAL_CANDIDATE_LIMIT_EXCEEDED,
    BoundaryTieAuditV0,
    CandidateLimitDecisionStatusV0,
    CandidateLimitDecisionV0,
    CandidateLimitResultV0,
    CandidateLimitingConfigurationV0,
    CandidateLimitingReadinessV0,
)
from .candidate_provenance import (
    AlteredCandidateProvenanceMaterializationV0,
    BlockedAlteredCandidateProvenanceV0,
)
from .candidate_ranking import (
    CandidateRankingBlockV0,
    ProvenanceMaterializationStatusV0,
)
from .contracts import (
    PROPOSED_CONTRACT_VERSION,
    CandidateLimitStatus,
    CandidateRecordV1,
    CandidateRole,
)


CANDIDATE_FINALIZATION_COMPONENT_VERSION = "candidate-finalization-v0"
CANDIDATE_FINALIZATION_RECORD_VERSION = "candidate-finalization-record-v0"
SHARED_PROVENANCE_UNAVAILABLE = "SHARED_PROVENANCE_UNAVAILABLE"


class CandidateFinalizationIntegrityError(ValueError):
    """Finalization input or output contradicts its immutable upstream audit."""


class CandidateFinalizationReadinessV0(str, Enum):
    RETAINED_SET_STRUCTURALLY_FINALIZED = (
        "RETAINED_SET_STRUCTURALLY_FINALIZED"
    )
    BLOCKED_BY_RETAINED_PROVENANCE = "BLOCKED_BY_RETAINED_PROVENANCE"
    RANKING_UNAVAILABLE = "RANKING_UNAVAILABLE"


class CandidateFinalizationCoverageStatusV0(str, Enum):
    """Coverage of altered identities as shared candidate records."""

    COMPLETE_SHARED_LEDGER = "COMPLETE_SHARED_LEDGER"
    INCOMPLETE_BLOCKED_PROVENANCE = "INCOMPLETE_BLOCKED_PROVENANCE"
    RANKING_UNAVAILABLE = "RANKING_UNAVAILABLE"


def _require_id_tuple(values: tuple[str, ...], name: str) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{name} must be a tuple.")
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise ValueError(f"{name} must contain non-empty strings.")
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must not contain duplicate IDs.")


@dataclass(frozen=True, slots=True)
class BlockedCandidateFinalizationAuditV0:
    """One exact capacity decision whose shared provenance is unavailable."""

    decision: CandidateLimitDecisionV0
    reason: str = SHARED_PROVENANCE_UNAVAILABLE
    record_version: str = CANDIDATE_FINALIZATION_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.decision, CandidateLimitDecisionV0):
            raise TypeError("decision must be CandidateLimitDecisionV0.")
        try:
            self.decision.__post_init__()
            self.decision.ranked_candidate.__post_init__()
        except (TypeError, ValueError) as exc:
            raise CandidateFinalizationIntegrityError(
                "Blocked audit decision failed upstream revalidation."
            ) from exc
        ranked = self.decision.ranked_candidate
        if ranked.provenance_status is not ProvenanceMaterializationStatusV0.BLOCKED:
            raise CandidateFinalizationIntegrityError(
                "A blocked audit requires BLOCKED provenance status."
            )
        if not isinstance(ranked.source_record, BlockedAlteredCandidateProvenanceV0):
            raise CandidateFinalizationIntegrityError(
                "A blocked audit requires a blocked provenance source record."
            )
        try:
            ranked.source_record.__post_init__()
        except (TypeError, ValueError) as exc:
            raise CandidateFinalizationIntegrityError(
                "Blocked provenance source failed complete revalidation."
            ) from exc
        if ranked.identity.candidate_id == ranked.identity.c0_candidate_id:
            raise CandidateFinalizationIntegrityError(
                "A blocked finalization audit must describe an altered candidate."
            )
        if self.reason != SHARED_PROVENANCE_UNAVAILABLE:
            raise ValueError("Unsupported blocked-finalization reason.")
        if self.record_version != CANDIDATE_FINALIZATION_RECORD_VERSION:
            raise ValueError("Unsupported candidate-finalization record version.")


@dataclass(frozen=True, slots=True)
class CandidateFinalizationCoverageV0:
    """Exact altered-identity shared-record coverage after finalization."""

    status: CandidateFinalizationCoverageStatusV0
    materialized_candidate_ids: tuple[str, ...]
    retained_materialized_candidate_ids: tuple[str, ...]
    overflow_materialized_candidate_ids: tuple[str, ...]
    blocked_retained_candidate_ids: tuple[str, ...]
    blocked_overflow_candidate_ids: tuple[str, ...]
    ranking_blocked_candidate_ids: tuple[str, ...]
    record_version: str = CANDIDATE_FINALIZATION_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.status, CandidateFinalizationCoverageStatusV0):
            raise TypeError(
                "status must be CandidateFinalizationCoverageStatusV0."
            )
        names = (
            "materialized_candidate_ids",
            "retained_materialized_candidate_ids",
            "overflow_materialized_candidate_ids",
            "blocked_retained_candidate_ids",
            "blocked_overflow_candidate_ids",
            "ranking_blocked_candidate_ids",
        )
        for name in names:
            _require_id_tuple(getattr(self, name), name)
        expected_materialized = (
            self.retained_materialized_candidate_ids
            + self.overflow_materialized_candidate_ids
        )
        if self.materialized_candidate_ids != expected_materialized:
            raise CandidateFinalizationIntegrityError(
                "materialized_candidate_ids must concatenate retained and overflow "
                "materialized IDs in rank order."
            )
        terminal_categories = (
            self.retained_materialized_candidate_ids,
            self.overflow_materialized_candidate_ids,
            self.blocked_retained_candidate_ids,
            self.blocked_overflow_candidate_ids,
        )
        terminal_ids = tuple(
            candidate_id for category in terminal_categories for candidate_id in category
        )
        if len(terminal_ids) != len(set(terminal_ids)):
            raise CandidateFinalizationIntegrityError(
                "Altered-identity terminal coverage categories must be disjoint."
            )
        blocked_ids = (
            self.blocked_retained_candidate_ids
            + self.blocked_overflow_candidate_ids
        )
        if self.status is CandidateFinalizationCoverageStatusV0.RANKING_UNAVAILABLE:
            if terminal_ids or self.materialized_candidate_ids:
                raise CandidateFinalizationIntegrityError(
                    "Ranking-unavailable coverage cannot contain capacity categories."
                )
            if not self.ranking_blocked_candidate_ids:
                raise CandidateFinalizationIntegrityError(
                    "Ranking-unavailable coverage requires ranking-blocked identities."
                )
        else:
            if self.ranking_blocked_candidate_ids:
                raise CandidateFinalizationIntegrityError(
                    "A ranked ledger cannot contain ranking-blocked identities."
                )
            if self.status is (
                CandidateFinalizationCoverageStatusV0.COMPLETE_SHARED_LEDGER
            ):
                if blocked_ids:
                    raise CandidateFinalizationIntegrityError(
                        "Complete shared-ledger coverage cannot retain blocked identities."
                    )
            elif not blocked_ids:
                raise CandidateFinalizationIntegrityError(
                    "Incomplete provenance coverage requires a blocked identity."
                )
        if self.record_version != CANDIDATE_FINALIZATION_RECORD_VERSION:
            raise ValueError("Unsupported candidate-finalization record version.")


def _validate_limit_result(limit_result: CandidateLimitResultV0) -> None:
    if not isinstance(limit_result, CandidateLimitResultV0):
        raise TypeError("limit_result must be CandidateLimitResultV0.")
    try:
        limit_result.__post_init__()
        limit_result.original_candidate.__post_init__()
    except (TypeError, ValueError) as exc:
        raise CandidateFinalizationIntegrityError(
            "Candidate limiting result failed complete upstream revalidation."
        ) from exc


def _materialized_record(
    *,
    decision: CandidateLimitDecisionV0,
    original_candidate: CandidateRecordV1,
) -> CandidateRecordV1:
    ranked = decision.ranked_candidate
    source_record = ranked.source_record
    if (
        ranked.provenance_status
        is not ProvenanceMaterializationStatusV0.MATERIALIZED
        or not isinstance(
            source_record, AlteredCandidateProvenanceMaterializationV0
        )
    ):
        raise CandidateFinalizationIntegrityError(
            "Shared candidate construction requires materialized provenance."
        )
    identity = ranked.identity
    if identity.c0_candidate_id != original_candidate.candidate_id:
        raise CandidateFinalizationIntegrityError(
            "Altered candidate c0 identity contradicts the permanent original."
        )
    if (
        identity.receipt_id != original_candidate.receipt_id
        or identity.field_id != original_candidate.field_id
    ):
        raise CandidateFinalizationIntegrityError(
            "Altered candidate receipt/field identity contradicts permanent c0."
        )
    if decision.status is CandidateLimitDecisionStatusV0.WITHIN_CAPACITY:
        limit_status = CandidateLimitStatus.RETAINED
        overflow_reason = None
    elif decision.status is CandidateLimitDecisionStatusV0.LIMIT_OVERFLOW:
        if decision.overflow_reason != TOTAL_CANDIDATE_LIMIT_EXCEEDED:
            raise CandidateFinalizationIntegrityError(
                "Overflow decision does not retain the approved reason."
            )
        limit_status = CandidateLimitStatus.LIMIT_OVERFLOW
        overflow_reason = TOTAL_CANDIDATE_LIMIT_EXCEEDED
    else:
        raise CandidateFinalizationIntegrityError(
            "Unsupported local capacity decision."
        )
    try:
        record = CandidateRecordV1(
            candidate_id=identity.candidate_id,
            receipt_id=identity.receipt_id,
            field_id=identity.field_id,
            c0_candidate_id=original_candidate.candidate_id,
            value=identity.representative_value,
            normalized_dedup_key=identity.normalized_dedup_key,
            role=CandidateRole.ALTERED,
            provenance=source_record.shared_provenance,
            limit_status=limit_status,
            preliminary_rank=ranked.preliminary_rank,
            overflow_reason=overflow_reason,
            record_version=PROPOSED_CONTRACT_VERSION,
        )
        record.__post_init__()
    except (TypeError, ValueError) as exc:
        raise CandidateFinalizationIntegrityError(
            "Materialized candidate could not satisfy CandidateRecordV1."
        ) from exc
    return record


def _derive_finalization(
    limit_result: CandidateLimitResultV0,
) -> tuple[
    tuple[CandidateRecordV1, ...],
    tuple[CandidateRecordV1, ...],
    tuple[BlockedCandidateFinalizationAuditV0, ...],
    CandidateFinalizationReadinessV0,
    CandidateFinalizationCoverageV0,
]:
    _validate_limit_result(limit_result)
    if limit_result.readiness is CandidateLimitingReadinessV0.RANKING_UNAVAILABLE:
        blocked_ids = tuple(
            block.identity.candidate_id for block in limit_result.ranking_blocks
        )
        coverage = CandidateFinalizationCoverageV0(
            status=CandidateFinalizationCoverageStatusV0.RANKING_UNAVAILABLE,
            materialized_candidate_ids=(),
            retained_materialized_candidate_ids=(),
            overflow_materialized_candidate_ids=(),
            blocked_retained_candidate_ids=(),
            blocked_overflow_candidate_ids=(),
            ranking_blocked_candidate_ids=blocked_ids,
        )
        return (
            (),
            (),
            (),
            CandidateFinalizationReadinessV0.RANKING_UNAVAILABLE,
            coverage,
        )

    retained: list[CandidateRecordV1] = []
    overflow: list[CandidateRecordV1] = []
    blocked: list[BlockedCandidateFinalizationAuditV0] = []
    blocked_retained_ids: list[str] = []
    blocked_overflow_ids: list[str] = []

    for decision in limit_result.decisions:
        if (
            decision.provenance_status
            is ProvenanceMaterializationStatusV0.MATERIALIZED
        ):
            record = _materialized_record(
                decision=decision,
                original_candidate=limit_result.original_candidate,
            )
            if decision.status is CandidateLimitDecisionStatusV0.WITHIN_CAPACITY:
                retained.append(record)
            else:
                overflow.append(record)
            continue
        if decision.provenance_status is not ProvenanceMaterializationStatusV0.BLOCKED:
            raise CandidateFinalizationIntegrityError(
                "Unsupported provenance materialization status."
            )
        audit = BlockedCandidateFinalizationAuditV0(decision=decision)
        blocked.append(audit)
        if decision.status is CandidateLimitDecisionStatusV0.WITHIN_CAPACITY:
            blocked_retained_ids.append(decision.candidate_id)
        elif decision.status is CandidateLimitDecisionStatusV0.LIMIT_OVERFLOW:
            blocked_overflow_ids.append(decision.candidate_id)
        else:
            raise CandidateFinalizationIntegrityError(
                "Blocked candidate has an unsupported capacity decision."
            )

    readiness = (
        CandidateFinalizationReadinessV0.BLOCKED_BY_RETAINED_PROVENANCE
        if blocked_retained_ids
        else CandidateFinalizationReadinessV0.RETAINED_SET_STRUCTURALLY_FINALIZED
    )
    coverage_status = (
        CandidateFinalizationCoverageStatusV0.INCOMPLETE_BLOCKED_PROVENANCE
        if blocked
        else CandidateFinalizationCoverageStatusV0.COMPLETE_SHARED_LEDGER
    )
    retained_tuple = tuple(retained)
    overflow_tuple = tuple(overflow)
    coverage = CandidateFinalizationCoverageV0(
        status=coverage_status,
        materialized_candidate_ids=tuple(
            record.candidate_id for record in (*retained_tuple, *overflow_tuple)
        ),
        retained_materialized_candidate_ids=tuple(
            record.candidate_id for record in retained_tuple
        ),
        overflow_materialized_candidate_ids=tuple(
            record.candidate_id for record in overflow_tuple
        ),
        blocked_retained_candidate_ids=tuple(blocked_retained_ids),
        blocked_overflow_candidate_ids=tuple(blocked_overflow_ids),
        ranking_blocked_candidate_ids=(),
    )
    return retained_tuple, overflow_tuple, tuple(blocked), readiness, coverage


def _validate_shared_record_references(
    record: CandidateRecordV1,
    decision: CandidateLimitDecisionV0,
) -> None:
    try:
        record.__post_init__()
        for provenance in record.provenance:
            provenance.__post_init__()
    except (TypeError, ValueError) as exc:
        raise CandidateFinalizationIntegrityError(
            "Shared candidate failed contract revalidation."
        ) from exc
    ranked = decision.ranked_candidate
    source_record = ranked.source_record
    if not isinstance(source_record, AlteredCandidateProvenanceMaterializationV0):
        raise CandidateFinalizationIntegrityError(
            "A shared record cannot originate from blocked provenance."
        )
    if record.preliminary_rank is not ranked.preliminary_rank:
        raise CandidateFinalizationIntegrityError(
            "Shared candidate must retain the exact upstream rank object."
        )
    upstream_members = tuple(member.provenance for member in source_record.members)
    if len(record.provenance) != len(upstream_members) or any(
        observed is not source
        for observed, source in zip(record.provenance, upstream_members, strict=True)
    ):
        raise CandidateFinalizationIntegrityError(
            "Shared candidate must retain canonical upstream provenance members."
        )


@dataclass(frozen=True, slots=True)
class CandidateFinalizationResultV0:
    """Reconstructable shared-record projection of one limiting result."""

    limit_result: CandidateLimitResultV0
    retained_records: tuple[CandidateRecordV1, ...]
    overflow_records: tuple[CandidateRecordV1, ...]
    blocked_audits: tuple[BlockedCandidateFinalizationAuditV0, ...]
    readiness: CandidateFinalizationReadinessV0
    coverage: CandidateFinalizationCoverageV0
    component_version: str = CANDIDATE_FINALIZATION_COMPONENT_VERSION
    record_version: str = CANDIDATE_FINALIZATION_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.limit_result, CandidateLimitResultV0):
            raise TypeError("limit_result must be CandidateLimitResultV0.")
        for value, expected_type, name in (
            (self.retained_records, CandidateRecordV1, "retained_records"),
            (self.overflow_records, CandidateRecordV1, "overflow_records"),
            (
                self.blocked_audits,
                BlockedCandidateFinalizationAuditV0,
                "blocked_audits",
            ),
        ):
            if not isinstance(value, tuple) or any(
                not isinstance(item, expected_type) for item in value
            ):
                raise TypeError(f"{name} contains an unsupported record.")
        if not isinstance(self.readiness, CandidateFinalizationReadinessV0):
            raise TypeError("readiness must be CandidateFinalizationReadinessV0.")
        if not isinstance(self.coverage, CandidateFinalizationCoverageV0):
            raise TypeError("coverage must be CandidateFinalizationCoverageV0.")
        if self.component_version != CANDIDATE_FINALIZATION_COMPONENT_VERSION:
            raise ValueError("Unsupported candidate-finalization component version.")
        if self.record_version != CANDIDATE_FINALIZATION_RECORD_VERSION:
            raise ValueError("Unsupported candidate-finalization record version.")

        try:
            self.coverage.__post_init__()
            expected = _derive_finalization(self.limit_result)
        except (TypeError, ValueError) as exc:
            if isinstance(exc, CandidateFinalizationIntegrityError):
                raise
            raise CandidateFinalizationIntegrityError(
                "Finalization reconstruction failed."
            ) from exc
        observed = (
            self.retained_records,
            self.overflow_records,
            self.blocked_audits,
            self.readiness,
            self.coverage,
        )
        if observed != expected:
            raise CandidateFinalizationIntegrityError(
                "Finalization result must equal its deterministic projection."
            )

        materialized_decisions = tuple(
            decision
            for decision in self.limit_result.decisions
            if decision.provenance_status
            is ProvenanceMaterializationStatusV0.MATERIALIZED
        )
        shared_records = self.retained_records + self.overflow_records
        if len(shared_records) != len(materialized_decisions):
            raise CandidateFinalizationIntegrityError(
                "Every materialized decision must have exactly one shared record."
            )
        for record, decision in zip(
            shared_records, materialized_decisions, strict=True
        ):
            _validate_shared_record_references(record, decision)

        blocked_decisions = tuple(
            decision
            for decision in self.limit_result.decisions
            if decision.provenance_status
            is ProvenanceMaterializationStatusV0.BLOCKED
        )
        if len(self.blocked_audits) != len(blocked_decisions) or any(
            audit.decision is not decision
            for audit, decision in zip(
                self.blocked_audits, blocked_decisions, strict=True
            )
        ):
            raise CandidateFinalizationIntegrityError(
                "Blocked audits must retain exact upstream decision references."
            )
        for audit in self.blocked_audits:
            audit.__post_init__()

    @property
    def original_candidate(self) -> CandidateRecordV1:
        return self.limit_result.original_candidate

    @property
    def equivalent_to_c0(self) -> EquivalentToC0AuditV0 | None:
        return self.limit_result.equivalent_to_c0

    @property
    def ranking_blocks(self) -> tuple[CandidateRankingBlockV0, ...]:
        return self.limit_result.ranking_blocks

    @property
    def boundary_tie_audit(self) -> BoundaryTieAuditV0:
        return self.limit_result.boundary_tie_audit

    @property
    def limiting_configuration(self) -> CandidateLimitingConfigurationV0:
        return self.limit_result.configuration


def materialize_ranked_candidate_records(
    *,
    limit_result: CandidateLimitResultV0,
) -> CandidateFinalizationResultV0:
    """Materialize every provenance-complete ranked identity, fail closed."""

    derived = _derive_finalization(limit_result)
    return CandidateFinalizationResultV0(
        limit_result=limit_result,
        retained_records=derived[0],
        overflow_records=derived[1],
        blocked_audits=derived[2],
        readiness=derived[3],
        coverage=derived[4],
    )
