"""Purchase-date observational backend execution path V0.

This module composes existing approved candidate, D3, and G2A components.  It
does not reconstruct upstream extraction or suspicion evidence, select a
candidate, commit a correction, or introduce controller policy.
"""

from __future__ import annotations

from pipeline.proposed.adapter import ProposedAdapterResultV1
from pipeline.proposed.candidate_deduplication import (
    deduplicate_candidate_drafts as _deduplicate_candidate_drafts,
)
from pipeline.proposed.candidate_finalization import (
    materialize_ranked_candidate_records as _materialize_ranked_candidate_records,
)
from pipeline.proposed.candidate_generation import (
    generate_candidate_drafts as _generate_candidate_drafts,
)
from pipeline.proposed.candidate_identity import (
    prepare_candidate_identities as _prepare_candidate_identities,
)
from pipeline.proposed.candidate_limiting import (
    CandidateLimitingConfigurationV0,
    apply_candidate_limit as _apply_candidate_limit,
)
from pipeline.proposed.candidate_provenance import (
    materialize_altered_provenance as _materialize_altered_provenance,
)
from pipeline.proposed.candidate_ranking import (
    CandidateRankingConfigurationV0,
    compute_preliminary_candidate_ranking as _compute_preliminary_candidate_ranking,
)
from pipeline.proposed.hard_constraint_context import (
    prepare_hard_constraint_inputs as _prepare_hard_constraint_inputs,
)
from pipeline.proposed.hard_constraint_contracts_v2 import (
    ConstraintResultV2,
    HardConstraintProfileRefV2,
)
from pipeline.proposed.hard_constraint_operands import (
    audit_hard_constraint_operands as _audit_hard_constraint_operands,
)
from pipeline.proposed.purchase_date_constraint_stage import (
    evaluate_purchase_date_constraint_stage_v0 as _evaluate_purchase_date_constraint_stage_v0,
)
from pipeline.proposed.suspicion import SuspicionResultV0


__all__ = ("execute_purchase_date_observational_path_v0",)


def execute_purchase_date_observational_path_v0(
    *,
    adapter_result: ProposedAdapterResultV1,
    suspicion_result: SuspicionResultV0,
    ranking_configuration: CandidateRankingConfigurationV0,
    limiting_configuration: CandidateLimitingConfigurationV0,
    rule_profile_reference: HardConstraintProfileRefV2,
    grammar_reference: str,
) -> tuple[ConstraintResultV2, ...]:
    """Execute the approved purchase-date path from stored upstream records.

    Every intermediate record is immutable and remains local.  Existing typed
    validation exceptions propagate unchanged, so no partial result tuple is
    returned when any candidate or binding fails.
    """

    candidate_drafts = _generate_candidate_drafts(
        suspicion_result=suspicion_result,
        adapter_result=adapter_result,
    )
    deduplication_result = _deduplicate_candidate_drafts(
        candidate_drafts=candidate_drafts
    )
    identity_result = _prepare_candidate_identities(
        deduplication_result=deduplication_result
    )
    provenance_result = _materialize_altered_provenance(
        identity_preparation=identity_result
    )
    ranking_result = _compute_preliminary_candidate_ranking(
        provenance_result=provenance_result,
        configuration=ranking_configuration,
    )
    limiting_result = _apply_candidate_limit(
        ranking_result=ranking_result,
        configuration=limiting_configuration,
    )
    finalization_result = _materialize_ranked_candidate_records(
        limit_result=limiting_result
    )
    hard_constraint_input = _prepare_hard_constraint_inputs(
        finalization_result=finalization_result
    )
    operand_audit = _audit_hard_constraint_operands(
        hard_constraint_input=hard_constraint_input
    )
    return _evaluate_purchase_date_constraint_stage_v0(
        operand_audit=operand_audit,
        rule_profile_reference=rule_profile_reference,
        grammar_reference=grammar_reference,
    )
