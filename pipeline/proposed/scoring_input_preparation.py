"""Prepare structural scoring evidence from an existing FC01 result.

The source ID binds canonical content. It supplies no scorer or admission
authority. Only the zero-V2-eligible path can complete without a policy.
"""

from dataclasses import replace

from pipeline.proposed.feature_construction import FeatureConstructionResultV0
from pipeline.proposed.hard_constraint_contracts_v2 import (
    ConstraintAggregateStateV2,
    ConstraintResultV2,
)
from pipeline.proposed.scoring_codec_v2 import (
    expected_admission_id,
    expected_source_snapshot_id,
)
from pipeline.proposed.scoring_contracts_v2 import (
    AdmissionStateV2,
    PreScoreAdmissionEvidenceV2,
    ScoringAuditIntegrityError,
    ScoringOperationResultV2,
    ScoringSourceSnapshotV2,
    construct_scoring_source_snapshot_v2,
)
from pipeline.proposed.scoring_operation_assembly import (
    ScoringOperationDeferredError,
    assemble_zero_admitted_scoring_operation_v0,
)


_COMPONENT_ID = "pantryproof.scoring-input-preparation"
_COMPONENT_VERSION = "scoring-input-preparation-v0"
_PENDING_ID = "pending-deterministic-id"
_CONSTRAINT_ONLY_STATE = {
    ConstraintAggregateStateV2.CONSTRAINT_REJECTED:
        AdmissionStateV2.NOT_APPLICABLE_CONSTRAINT_REJECTED,
    ConstraintAggregateStateV2.CONSTRAINT_UNAVAILABLE:
        AdmissionStateV2.NOT_APPLICABLE_CONSTRAINT_UNAVAILABLE,
}


def prepare_scoring_source_snapshot_v2(
    *, feature_construction_result: FeatureConstructionResultV0
) -> ScoringSourceSnapshotV2:
    """Validate FC01 and bind its exact retained population to a canonical ID."""

    if type(feature_construction_result) is not FeatureConstructionResultV0:
        raise ScoringAuditIntegrityError(
            "feature_construction_result must be FeatureConstructionResultV0."
        )
    try:
        snapshot = construct_scoring_source_snapshot_v2(
            source_snapshot_id=_PENDING_ID,
            feature_construction_result=feature_construction_result,
        )
    except (AttributeError, TypeError) as exc:
        raise ScoringAuditIntegrityError("Malformed FC01 source result.") from exc

    return replace(snapshot, source_snapshot_id=expected_source_snapshot_id(snapshot))


def _constraint_only_admission(
    snapshot: ScoringSourceSnapshotV2, result: ConstraintResultV2
) -> PreScoreAdmissionEvidenceV2:
    admission = PreScoreAdmissionEvidenceV2(
        admission_id=_PENDING_ID,
        source_snapshot_id=snapshot.source_snapshot_id,
        candidate=result.candidate,
        constraint_result=result,
        feature_vector=None,
        state=_CONSTRAINT_ONLY_STATE[result.aggregate_state],
        policy_id=None,
        policy_version=None,
        evidence_references=(),
        component_id=_COMPONENT_ID,
        component_version=_COMPONENT_VERSION,
    )
    return replace(admission, admission_id=expected_admission_id(admission))


def assemble_constraint_only_scoring_operation_v0(
    *, feature_construction_result: FeatureConstructionResultV0
) -> ScoringOperationResultV2:
    """Return the structural, zero-admitted audit for a zero-eligible field."""

    snapshot = prepare_scoring_source_snapshot_v2(
        feature_construction_result=feature_construction_result
    )
    if snapshot.candidate_features:
        raise ScoringOperationDeferredError(
            "V2-eligible candidates require an approved pre-score admission path."
        )
    admissions = tuple(
        _constraint_only_admission(snapshot, result)
        for result in snapshot.constraint_results
    )
    return assemble_zero_admitted_scoring_operation_v0(
        source_snapshot=snapshot, admissions=admissions
    )
