"""Purchase-date-only candidate-set hard-constraint execution stage V0.

The stage consumes one canonical D3 operand audit, evaluates every retained
candidate with the existing G2A rule, and materializes one source-bound
Contract V2 result per candidate.  It is audit-only: it does not select,
discard, commit, score, calibrate, or route any candidate.
"""

from __future__ import annotations

from pipeline.proposed.hard_constraint_contracts_v2 import (
    ConstraintResultV2,
    EvidenceReferenceV2,
    HardConstraintProfileRefV2,
    build_source_bound_constraint_result_v2 as _build_source_bound_constraint_result_v2,
)
from pipeline.proposed.hard_constraint_operands import (
    CandidateOperandAuditV0,
    HardConstraintOperandAuditResultV0,
)
from pipeline.proposed.purchase_date_calendar_validity import (
    CANDIDATE_RECORD_EVIDENCE_NAMESPACE as _CANDIDATE_RECORD_EVIDENCE_NAMESPACE,
    PURCHASE_DATE_CALENDAR_VALIDITY_RULE_ID as _PURCHASE_DATE_RULE_ID,
    PurchaseDateIntegrityError as _PurchaseDateIntegrityError,
    evaluate_purchase_date_calendar_validity_v0 as _evaluate_purchase_date_calendar_validity_v0,
)


__all__ = ("evaluate_purchase_date_constraint_stage_v0",)


def _rule_outcome_id(candidate_id: str) -> str:
    return f"{candidate_id}:{_PURCHASE_DATE_RULE_ID}:outcome"


def _constraint_result_id(candidate_id: str) -> str:
    return f"{candidate_id}:constraints:v2"


def _candidate_evidence_reference(
    candidate_audit: CandidateOperandAuditV0,
) -> EvidenceReferenceV2:
    candidate = candidate_audit.candidate
    return EvidenceReferenceV2(
        reference_namespace=_CANDIDATE_RECORD_EVIDENCE_NAMESPACE,
        reference_id=candidate.candidate_id,
        source_record_version=candidate.record_version,
    )


def _evaluation_plan(
    operand_audit: HardConstraintOperandAuditResultV0,
) -> tuple[
    tuple[
        CandidateOperandAuditV0,
        EvidenceReferenceV2,
        str,
        str,
    ],
    ...,
]:
    """Derive and validate every deterministic ID before any evaluation."""

    plans: list[
        tuple[
            CandidateOperandAuditV0,
            EvidenceReferenceV2,
            str,
            str,
        ]
    ] = []
    outcome_ids: set[str] = set()
    result_ids: set[str] = set()

    for candidate_audit in operand_audit.candidate_audits:
        candidate_id = candidate_audit.candidate.candidate_id
        outcome_id = _rule_outcome_id(candidate_id)
        result_id = _constraint_result_id(candidate_id)
        if not isinstance(outcome_id, str) or not outcome_id.strip():
            raise _PurchaseDateIntegrityError(
                "The deterministic purchase-date rule outcome ID is invalid."
            )
        if not isinstance(result_id, str) or not result_id.strip():
            raise _PurchaseDateIntegrityError(
                "The deterministic purchase-date constraint result ID is invalid."
            )
        if outcome_id in outcome_ids:
            raise _PurchaseDateIntegrityError(
                "Deterministic purchase-date rule outcome IDs must be unique."
            )
        if result_id in result_ids:
            raise _PurchaseDateIntegrityError(
                "Deterministic purchase-date constraint result IDs must be unique."
            )
        outcome_ids.add(outcome_id)
        result_ids.add(result_id)
        plans.append(
            (
                candidate_audit,
                _candidate_evidence_reference(candidate_audit),
                outcome_id,
                result_id,
            )
        )

    return tuple(plans)


def evaluate_purchase_date_constraint_stage_v0(
    *,
    operand_audit: HardConstraintOperandAuditResultV0,
    rule_profile_reference: HardConstraintProfileRefV2,
    grammar_reference: str,
) -> tuple[ConstraintResultV2, ...]:
    """Evaluate every exact retained purchase-date candidate in D3 order.

    The canonical operand audit owns candidate identity, completeness, and
    c0-first ordering.  IDs and candidate evidence references are derived from
    those exact records.  Any typed upstream, G2A, or V2 validation exception is
    propagated; results are returned only after the complete stage succeeds.
    """

    if not isinstance(operand_audit, HardConstraintOperandAuditResultV0):
        raise TypeError(
            "operand_audit must be HardConstraintOperandAuditResultV0."
        )
    operand_audit.__post_init__()

    plans = _evaluation_plan(operand_audit)
    results: list[ConstraintResultV2] = []
    for candidate_audit, evidence_reference, outcome_id, result_id in plans:
        outcome = _evaluate_purchase_date_calendar_validity_v0(
            rule_outcome_id=outcome_id,
            operand_audit=operand_audit,
            candidate_audit=candidate_audit,
            rule_profile_reference=rule_profile_reference,
            grammar_reference=grammar_reference,
            candidate_evidence_reference=evidence_reference,
        )
        results.append(
            _build_source_bound_constraint_result_v2(
                constraint_result_id=result_id,
                operand_audit=operand_audit,
                candidate_audit=candidate_audit,
                rule_profile_reference=rule_profile_reference,
                rule_outcomes=(outcome,),
            )
        )
    return tuple(results)
