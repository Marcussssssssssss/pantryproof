"""Assemble the approved zero-admitted scoring-operation audit.

This component consumes already-created SCORING-02C source and admission
records.  It does not evaluate admission policy, resolve a trusted scorer,
execute scoring, calibrate, select a candidate, or authorize replacement of
permanent ``c0``.
"""

from __future__ import annotations

from dataclasses import replace

from pipeline.proposed.scoring_codec_v2 import (
    expected_admission_id,
    expected_field_audit_id,
    expected_operation_result_id,
    expected_score_evidence_id,
    expected_source_snapshot_id,
)
from pipeline.proposed.scoring_contracts_v2 import (
    AdmissionStateV2,
    CandidateScoreEvidenceV2,
    FieldScoringAuditV2,
    FieldScoringCompletionStateV2,
    PreScoreAdmissionEvidenceV2,
    ScoreNotApplicableReasonV2,
    ScoreStatusV2,
    ScorerInvocationStateV2,
    ScoringAuditIntegrityError,
    ScoringOperationResultV2,
    ScoringSourceBindingError,
    ScoringSourceSnapshotV2,
)


SCORING_OPERATION_ASSEMBLY_COMPONENT_ID = (
    "pantryproof.scoring-zero-admitted-assembly"
)
SCORING_OPERATION_ASSEMBLY_COMPONENT_VERSION = (
    "scoring-zero-admitted-assembly-v0"
)


class ScoringOperationDeferredError(RuntimeError):
    """Raised when valid admissions require an operational scoring path."""


_NOT_APPLICABLE_REASON_BY_STATE = {
    AdmissionStateV2.NOT_APPLICABLE_CONSTRAINT_REJECTED: (
        ScoreNotApplicableReasonV2.CONSTRAINT_REJECTED
    ),
    AdmissionStateV2.NOT_APPLICABLE_CONSTRAINT_UNAVAILABLE: (
        ScoreNotApplicableReasonV2.CONSTRAINT_UNAVAILABLE
    ),
    AdmissionStateV2.REJECTED_PRICE_ONLY_SUPPORT: (
        ScoreNotApplicableReasonV2.PRE_SCORE_REJECTED_PRICE_ONLY_SUPPORT
    ),
}


def _validate_inputs(
    source_snapshot: ScoringSourceSnapshotV2,
    admissions: tuple[PreScoreAdmissionEvidenceV2, ...],
) -> None:
    if not isinstance(source_snapshot, ScoringSourceSnapshotV2):
        raise ScoringAuditIntegrityError(
            "source_snapshot must be ScoringSourceSnapshotV2."
        )
    source_snapshot.__post_init__()
    if source_snapshot.source_snapshot_id != expected_source_snapshot_id(
        source_snapshot
    ):
        raise ScoringAuditIntegrityError(
            "ScoringSourceSnapshotV2 deterministic ID mismatch."
        )

    if not isinstance(admissions, tuple):
        raise ScoringAuditIntegrityError("admissions must be a tuple.")
    if len(admissions) != len(source_snapshot.candidates):
        raise ScoringAuditIntegrityError(
            "Exactly one admission is required per retained D3 candidate."
        )

    features_by_candidate = {
        feature.candidate.candidate_id: feature
        for feature in source_snapshot.candidate_features
    }
    seen_admission_ids: set[str] = set()
    for admission, candidate, constraint_result in zip(
        admissions,
        source_snapshot.candidates,
        source_snapshot.constraint_results,
        strict=True,
    ):
        if not isinstance(admission, PreScoreAdmissionEvidenceV2):
            raise ScoringAuditIntegrityError(
                "admissions contains an invalid record."
            )
        admission.__post_init__()
        if admission.admission_id in seen_admission_ids:
            raise ScoringAuditIntegrityError(
                "admission_id values must be unique."
            )
        seen_admission_ids.add(admission.admission_id)
        if admission.admission_id != expected_admission_id(admission):
            raise ScoringAuditIntegrityError(
                "PreScoreAdmissionEvidenceV2 deterministic ID mismatch."
            )
        if admission.source_snapshot_id != source_snapshot.source_snapshot_id:
            raise ScoringSourceBindingError(
                "Admission is bound to a different scoring source snapshot."
            )
        if admission.candidate is not candidate:
            raise ScoringSourceBindingError(
                "Admissions must preserve exact D3 candidate order and identity."
            )
        if admission.constraint_result is not constraint_result:
            raise ScoringSourceBindingError(
                "Admissions must preserve exact V2 result order and identity."
            )
        expected_feature = features_by_candidate.get(candidate.candidate_id)
        if admission.feature_vector is not expected_feature:
            raise ScoringSourceBindingError(
                "Admissions must preserve exact eligible feature-vector identity."
            )
        if constraint_result.c0_candidate is not source_snapshot.c0_candidate:
            raise ScoringSourceBindingError(
                "Every admission must retain the exact permanent c0."
            )


def _not_applicable_score(
    admission: PreScoreAdmissionEvidenceV2,
) -> CandidateScoreEvidenceV2:
    score = CandidateScoreEvidenceV2(
        score_evidence_id="pending-deterministic-id",
        admission=admission,
        score_status=ScoreStatusV2.NOT_APPLICABLE,
        raw_score=None,
        not_applicable_reason=_NOT_APPLICABLE_REASON_BY_STATE[admission.state],
        trusted_scorer_binding=None,
        component_id=SCORING_OPERATION_ASSEMBLY_COMPONENT_ID,
        component_version=SCORING_OPERATION_ASSEMBLY_COMPONENT_VERSION,
    )
    return replace(
        score,
        score_evidence_id=expected_score_evidence_id(score),
    )


def assemble_zero_admitted_scoring_operation_v0(
    *,
    source_snapshot: ScoringSourceSnapshotV2,
    admissions: tuple[PreScoreAdmissionEvidenceV2, ...],
) -> ScoringOperationResultV2:
    """Build a complete audit-only operation when no candidate is admitted.

    Complete source and admission validation occurs before the admission states
    are inspected.  A structurally valid population containing an ``ADMITTED``
    candidate is deferred without creating a partial result or scoring failure.
    """

    _validate_inputs(source_snapshot, admissions)

    if any(admission.state is AdmissionStateV2.ADMITTED for admission in admissions):
        raise ScoringOperationDeferredError(
            "Operational scoring is deferred for a valid admitted population."
        )

    candidate_scores = tuple(
        _not_applicable_score(admission) for admission in admissions
    )
    audit = FieldScoringAuditV2(
        field_audit_id="pending-deterministic-id",
        source_snapshot=source_snapshot,
        candidate_scores=candidate_scores,
        admitted_candidate_ids=(),
        admitted_candidate_count=0,
        resolver_invocation=ScorerInvocationStateV2.NOT_INVOKED_ZERO_ADMITTED,
        resolver_result=None,
        trusted_scorer_binding=None,
        completion_state=(
            FieldScoringCompletionStateV2.COMPLETE_ZERO_ADMITTED_BYPASS
        ),
        component_id=SCORING_OPERATION_ASSEMBLY_COMPONENT_ID,
        component_version=SCORING_OPERATION_ASSEMBLY_COMPONENT_VERSION,
    )
    audit = replace(audit, field_audit_id=expected_field_audit_id(audit))
    operation = ScoringOperationResultV2(
        operation_result_id="pending-deterministic-id",
        outcome=audit,
    )
    return replace(
        operation,
        operation_result_id=expected_operation_result_id(operation),
    )


__all__ = (
    "SCORING_OPERATION_ASSEMBLY_COMPONENT_ID",
    "SCORING_OPERATION_ASSEMBLY_COMPONENT_VERSION",
    "ScoringOperationDeferredError",
    "assemble_zero_admitted_scoring_operation_v0",
)
