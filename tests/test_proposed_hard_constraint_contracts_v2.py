"""Synthetic conformance tests for immutable hard-constraint Contract V2."""

from __future__ import annotations

import inspect
import json
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from pathlib import Path
import unittest

from pipeline.proposed.contracts import (
    CandidateLimitStatus,
    CandidateProvenanceV1,
    CandidateRecordV1,
    CandidateRole,
    CandidateSourceKind,
    ConfigurationKind,
    ConfigurationRefV1,
    ConfigurationState,
    PreliminaryRankV1,
    SourceCharacterSpanV1,
    ValueAvailabilityStatus,
)
from pipeline.proposed.hard_constraint_contracts_v2 import (
    ConstraintAggregateReasonV2,
    ConstraintAggregateStateV2,
    ConstraintResultV2,
    ConstraintRuleOutcomeV2,
    EvidenceReferenceV2,
    HardConstraintAuditIntegrityError,
    HardConstraintProfileRefV2,
    HardConstraintProfileConfigurationError,
    HardConstraintResourceRefV2,
    HardConstraintRuleSpecV2,
    HardConstraintSerializationError,
    HardConstraintSourceBindingError,
    RuleEvidenceAvailabilityV2,
    RuleOutcomeReasonKindV2,
    RuleOutcomeStateV2,
    RuleRequirementV2,
    build_source_bound_constraint_result_v2,
    constraint_result_v2_from_json,
    constraint_result_v2_to_json,
)
from pipeline.proposed.hard_constraint_operands import OperandAvailabilityV0


class ProposedHardConstraintContractV2Tests(unittest.TestCase):
    RECEIPT_ID = "hc-v2-receipt"
    FIELD_ID = "hc-v2-receipt:store-name"
    C0_ID = f"{FIELD_ID}:c0"
    FIXTURE_PATH = (
        Path(__file__).parent
        / "fixtures"
        / "proposed"
        / "hard_constraint_contract_v2.json"
    )

    def theta(self, *, ready: bool = True) -> ConfigurationRefV1:
        state = ConfigurationState.READY if ready else ConfigurationState.NOT_READY
        return ConfigurationRefV1(
            kind=ConfigurationKind.THETA_A,
            configuration_id="theta-a-hc-v2",
            configuration_version="v1",
            state=state,
            content_hash="sha256:synthetic-theta-a" if ready else None,
            status_reason=None if ready else "Synthetic configuration not ready.",
        )

    def original(self, *, value: str = "PANTRY MART") -> CandidateRecordV1:
        provenance = CandidateProvenanceV1(
            provenance_id="hc-v2-provenance-c0",
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            candidate_id=self.C0_ID,
            source_kind=CandidateSourceKind.ORIGINAL,
            original_observed_value=value,
            source_token_ids=("store-token",),
            source_spans=(
                SourceCharacterSpanV1(
                    token_id="store-token",
                    start=0,
                    end=len(value),
                    text=value,
                ),
            ),
        )
        return CandidateRecordV1(
            candidate_id=self.C0_ID,
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            c0_candidate_id=self.C0_ID,
            value=value,
            normalized_dedup_key=value.casefold(),
            role=CandidateRole.ORIGINAL,
            provenance=(provenance,),
            limit_status=CandidateLimitStatus.RETAINED,
        )

    def altered(self, c0: CandidateRecordV1 | None = None) -> CandidateRecordV1:
        c0 = c0 or self.original()
        candidate_id = f"{self.FIELD_ID}:candidate:001"
        provenance = CandidateProvenanceV1(
            provenance_id="hc-v2-provenance-altered",
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            candidate_id=candidate_id,
            source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
            original_observed_value=c0.value,
            source_token_ids=("store-token",),
            source_spans=(
                SourceCharacterSpanV1(
                    token_id="store-token",
                    start=0,
                    end=len(c0.value),
                    text=c0.value,
                ),
            ),
            generic_rule_id="B3_TEXT_NORMALIZE",
        )
        return CandidateRecordV1(
            candidate_id=candidate_id,
            receipt_id=self.RECEIPT_ID,
            field_id=self.FIELD_ID,
            c0_candidate_id=c0.candidate_id,
            value="Pantry Mart",
            normalized_dedup_key="pantry mart altered",
            role=CandidateRole.ALTERED,
            provenance=(provenance,),
            limit_status=CandidateLimitStatus.RETAINED,
            preliminary_rank=PreliminaryRankV1(
                source_priority_rank=2,
                normalized_edit_similarity=Decimal("0.8750"),
                source_order_displacement=0,
                normalized_candidate_text="pantry mart",
                rank_position=1,
                tie_group_id="rank-tie-001",
            ),
        )

    def profile(
        self,
        *,
        theta: ConfigurationRefV1 | None = None,
        rules: tuple[HardConstraintRuleSpecV2, ...] | None = None,
        resources: tuple[HardConstraintResourceRefV2, ...] | None = None,
    ) -> HardConstraintProfileRefV2:
        resource = HardConstraintResourceRefV2(
            resource_reference_id="resource:pantry-terms:v1",
            resource_kind="PANTRY_TERMINOLOGY",
            resource_id="pantry-terms",
            resource_version="v1",
            declared_content_reference="synthetic://pantry-terms/v1",
            declared_content_hash="sha256:synthetic-resource",
        )
        selected_resources = (resource,) if resources is None else resources
        selected_rules = rules or (
            HardConstraintRuleSpecV2(
                rule_id="FIELD_TYPE_COMPATIBLE",
                rule_version="v1",
                position=0,
                requirement=RuleRequirementV2.MANDATORY,
                applicability_reference="profile:field-type:v1",
            ),
            HardConstraintRuleSpecV2(
                rule_id="RECEIPT_ARITHMETIC",
                rule_version="v1",
                position=1,
                requirement=RuleRequirementV2.MANDATORY,
                applicability_reference="profile:arithmetic:v1",
            ),
            HardConstraintRuleSpecV2(
                rule_id="PANTRY_TERMINOLOGY_HINT",
                rule_version="v1",
                position=2,
                requirement=RuleRequirementV2.OPTIONAL,
                applicability_reference="profile:pantry-terms:v1",
                resource_reference_ids=(resource.resource_reference_id,),
            ),
        )
        return HardConstraintProfileRefV2(
            profile_id="hard-constraint-profile-synthetic",
            profile_version="v1",
            theta_a_reference=theta or self.theta(),
            ordered_rule_specs=selected_rules,
            resource_references=selected_resources,
            declared_content_hash="sha256:synthetic-profile",
        )

    @staticmethod
    def aggregate_for(
        states: tuple[RuleOutcomeStateV2, ...],
    ) -> tuple[ConstraintAggregateStateV2, ConstraintAggregateReasonV2]:
        mandatory = states[:2]
        if RuleOutcomeStateV2.FAIL in mandatory:
            return (
                ConstraintAggregateStateV2.CONSTRAINT_REJECTED,
                ConstraintAggregateReasonV2.MANDATORY_RULE_FAILED,
            )
        if RuleOutcomeStateV2.UNAVAILABLE in mandatory:
            return (
                ConstraintAggregateStateV2.CONSTRAINT_UNAVAILABLE,
                ConstraintAggregateReasonV2.MANDATORY_RULE_UNAVAILABLE,
            )
        if RuleOutcomeStateV2.PASS in mandatory:
            return (
                ConstraintAggregateStateV2.ELIGIBLE,
                ConstraintAggregateReasonV2.ALL_APPLICABLE_MANDATORY_RULES_PASSED,
            )
        return (
            ConstraintAggregateStateV2.CONSTRAINT_UNAVAILABLE,
            ConstraintAggregateReasonV2.NO_APPLICABLE_MANDATORY_RULE,
        )

    def outcome(
        self,
        *,
        candidate: CandidateRecordV1,
        c0: CandidateRecordV1,
        profile: HardConstraintProfileRefV2,
        rule_index: int,
        state: RuleOutcomeStateV2,
    ) -> ConstraintRuleOutcomeV2:
        if state is RuleOutcomeStateV2.PASS:
            attempted = True
            availability = RuleEvidenceAvailabilityV2.AVAILABLE
            reason_kind = None
            code = None
            detail = None
        elif state is RuleOutcomeStateV2.FAIL:
            attempted = True
            availability = RuleEvidenceAvailabilityV2.AVAILABLE
            reason_kind = RuleOutcomeReasonKindV2.FAILURE
            code = "SYNTHETIC_RULE_FAILURE"
            detail = "Synthetic failure for structural conformance testing."
        elif state is RuleOutcomeStateV2.NOT_APPLICABLE:
            attempted = False
            availability = RuleEvidenceAvailabilityV2.NOT_APPLICABLE
            reason_kind = RuleOutcomeReasonKindV2.PROFILE_EXCLUSION
            code = "PROFILE_EXCLUDED"
            detail = "Rule is not applicable under the synthetic profile."
        else:
            attempted = False
            availability = RuleEvidenceAvailabilityV2.UNAVAILABLE
            reason_kind = RuleOutcomeReasonKindV2.UNAVAILABILITY
            code = "REQUIRED_OPERAND_UNAVAILABLE"
            detail = "Required synthetic evidence is unavailable."
        rule = profile.ordered_rule_specs[rule_index]
        resources = tuple(
            resource
            for resource in profile.resource_references
            if resource.resource_reference_id in rule.resource_reference_ids
        )
        evidence = (
            EvidenceReferenceV2(
                reference_namespace="D3_OPERAND_AUDIT",
                reference_id=f"{candidate.candidate_id}:{rule.rule_id}:evidence",
                source_record_version="hard-constraint-operands-record-v0",
            ),
        )
        return ConstraintRuleOutcomeV2(
            rule_outcome_id=f"{candidate.candidate_id}:{rule.rule_id}:outcome",
            receipt_id=candidate.receipt_id,
            field_id=candidate.field_id,
            candidate=candidate,
            c0_candidate=c0,
            rule_spec=rule,
            state=state,
            attempted=attempted,
            evidence_availability=availability,
            evidence_references=evidence,
            outcome_reason_kind=reason_kind,
            outcome_code=code,
            outcome_detail=detail,
            theta_a_reference=profile.theta_a_reference,
            rule_profile_reference=profile,
            resource_references=resources,
        )

    def result(
        self,
        states: tuple[RuleOutcomeStateV2, ...] = (
            RuleOutcomeStateV2.PASS,
            RuleOutcomeStateV2.PASS,
            RuleOutcomeStateV2.NOT_APPLICABLE,
        ),
        *,
        candidate: CandidateRecordV1 | None = None,
        c0: CandidateRecordV1 | None = None,
        profile: HardConstraintProfileRefV2 | None = None,
    ) -> ConstraintResultV2:
        c0 = c0 or self.original()
        candidate = candidate or c0
        profile = profile or self.profile()
        outcomes = tuple(
            self.outcome(
                candidate=candidate,
                c0=c0,
                profile=profile,
                rule_index=index,
                state=state,
            )
            for index, state in enumerate(states)
        )
        aggregate_state, aggregate_reason = self.aggregate_for(states)
        return ConstraintResultV2(
            constraint_result_id=f"{candidate.candidate_id}:constraints:v2",
            receipt_id=candidate.receipt_id,
            field_id=candidate.field_id,
            candidate=candidate,
            c0_candidate=c0,
            theta_a_reference=profile.theta_a_reference,
            rule_profile_reference=profile,
            rule_outcomes=outcomes,
            aggregate_state=aggregate_state,
            aggregate_reason=aggregate_reason,
        )

    def test_records_are_frozen(self) -> None:
        result = self.result()
        with self.assertRaises(FrozenInstanceError):
            result.aggregate_state = ConstraintAggregateStateV2.CONSTRAINT_REJECTED

    def test_complete_audit_accepts_original_and_altered_candidates(self) -> None:
        original = self.result()
        c0 = self.original()
        altered = self.result(candidate=self.altered(c0), c0=c0)
        self.assertEqual(original.candidate.role, CandidateRole.ORIGINAL)
        self.assertEqual(altered.candidate.role, CandidateRole.ALTERED)
        self.assertEqual(altered.candidate.c0_candidate_id, c0.candidate_id)

    def test_aggregate_truth_table(self) -> None:
        cases = (
            (
                (RuleOutcomeStateV2.PASS, RuleOutcomeStateV2.PASS, RuleOutcomeStateV2.FAIL),
                ConstraintAggregateStateV2.ELIGIBLE,
                ConstraintAggregateReasonV2.ALL_APPLICABLE_MANDATORY_RULES_PASSED,
            ),
            (
                (RuleOutcomeStateV2.FAIL, RuleOutcomeStateV2.PASS, RuleOutcomeStateV2.PASS),
                ConstraintAggregateStateV2.CONSTRAINT_REJECTED,
                ConstraintAggregateReasonV2.MANDATORY_RULE_FAILED,
            ),
            (
                (RuleOutcomeStateV2.PASS, RuleOutcomeStateV2.UNAVAILABLE, RuleOutcomeStateV2.PASS),
                ConstraintAggregateStateV2.CONSTRAINT_UNAVAILABLE,
                ConstraintAggregateReasonV2.MANDATORY_RULE_UNAVAILABLE,
            ),
            (
                (RuleOutcomeStateV2.NOT_APPLICABLE, RuleOutcomeStateV2.NOT_APPLICABLE, RuleOutcomeStateV2.FAIL),
                ConstraintAggregateStateV2.CONSTRAINT_UNAVAILABLE,
                ConstraintAggregateReasonV2.NO_APPLICABLE_MANDATORY_RULE,
            ),
            (
                (RuleOutcomeStateV2.PASS, RuleOutcomeStateV2.NOT_APPLICABLE, RuleOutcomeStateV2.UNAVAILABLE),
                ConstraintAggregateStateV2.ELIGIBLE,
                ConstraintAggregateReasonV2.ALL_APPLICABLE_MANDATORY_RULES_PASSED,
            ),
        )
        for states, expected_state, expected_reason in cases:
            with self.subTest(states=states):
                result = self.result(states)
                self.assertIs(result.aggregate_state, expected_state)
                self.assertIs(result.aggregate_reason, expected_reason)

    def test_mandatory_failure_precedes_mandatory_unavailability(self) -> None:
        result = self.result(
            (
                RuleOutcomeStateV2.FAIL,
                RuleOutcomeStateV2.UNAVAILABLE,
                RuleOutcomeStateV2.PASS,
            )
        )
        self.assertIs(
            result.aggregate_state,
            ConstraintAggregateStateV2.CONSTRAINT_REJECTED,
        )

    def test_missing_duplicate_unexpected_and_reordered_rule_outcomes_fail(self) -> None:
        result = self.result()
        mutations = (
            result.rule_outcomes[:-1],
            (result.rule_outcomes[0], result.rule_outcomes[0], result.rule_outcomes[2]),
            result.rule_outcomes + (result.rule_outcomes[-1],),
            (result.rule_outcomes[1], result.rule_outcomes[0], result.rule_outcomes[2]),
        )
        for outcomes in mutations:
            with self.subTest(length=len(outcomes)):
                with self.assertRaises(HardConstraintAuditIntegrityError):
                    replace(result, rule_outcomes=outcomes)

    def test_aggregate_state_and_reason_are_recomputed(self) -> None:
        result = self.result()
        with self.assertRaises(HardConstraintAuditIntegrityError):
            replace(
                result,
                aggregate_state=ConstraintAggregateStateV2.CONSTRAINT_REJECTED,
                aggregate_reason=ConstraintAggregateReasonV2.MANDATORY_RULE_FAILED,
            )

    def test_rule_state_invariants_reject_contradictions(self) -> None:
        result = self.result()
        passing = result.rule_outcomes[0]
        with self.assertRaises(HardConstraintAuditIntegrityError):
            replace(passing, attempted=False)
        with self.assertRaises(HardConstraintAuditIntegrityError):
            replace(
                passing,
                state=RuleOutcomeStateV2.UNAVAILABLE,
                evidence_availability=RuleEvidenceAvailabilityV2.AVAILABLE,
                outcome_reason_kind=RuleOutcomeReasonKindV2.UNAVAILABILITY,
                outcome_code="MISSING_INPUT",
            )
        with self.assertRaises(HardConstraintAuditIntegrityError):
            replace(
                passing,
                state=RuleOutcomeStateV2.NOT_APPLICABLE,
                attempted=False,
                evidence_availability=RuleEvidenceAvailabilityV2.NOT_APPLICABLE,
                outcome_reason_kind=None,
                outcome_code="PROFILE_EXCLUDED",
            )

    def test_reason_codes_and_evidence_references_are_strict(self) -> None:
        result = self.result(
            (
                RuleOutcomeStateV2.FAIL,
                RuleOutcomeStateV2.PASS,
                RuleOutcomeStateV2.NOT_APPLICABLE,
            )
        )
        failed = result.rule_outcomes[0]
        with self.assertRaises(HardConstraintAuditIntegrityError):
            replace(failed, outcome_code="bad-code")
        with self.assertRaises(HardConstraintAuditIntegrityError):
            replace(
                failed,
                evidence_references=(
                    failed.evidence_references[0],
                    failed.evidence_references[0],
                ),
            )
        with self.assertRaises(HardConstraintAuditIntegrityError):
            replace(failed, outcome_code=None)

    def test_approved_exception_is_explicit_not_an_ordinary_pass(self) -> None:
        result = self.result(
            (
                RuleOutcomeStateV2.PASS,
                RuleOutcomeStateV2.NOT_APPLICABLE,
                RuleOutcomeStateV2.NOT_APPLICABLE,
            )
        )
        exception = replace(
            result.rule_outcomes[1],
            outcome_reason_kind=RuleOutcomeReasonKindV2.APPROVED_EXCEPTION,
            outcome_code="APPROVED_SYNTHETIC_EXCEPTION",
        )
        rebuilt = replace(
            result,
            rule_outcomes=(result.rule_outcomes[0], exception, result.rule_outcomes[2]),
        )
        self.assertIs(exception.state, RuleOutcomeStateV2.NOT_APPLICABLE)
        self.assertIs(rebuilt.aggregate_state, ConstraintAggregateStateV2.ELIGIBLE)

    def test_profile_requires_ready_theta_a_mandatory_rule_and_complete_resources(self) -> None:
        base = self.profile()
        optional = replace(
            base.ordered_rule_specs[0],
            requirement=RuleRequirementV2.OPTIONAL,
        )
        all_optional = (optional,) + tuple(
            replace(rule, requirement=RuleRequirementV2.OPTIONAL)
            for rule in base.ordered_rule_specs[1:]
        )
        invalid_builders = (
            lambda: replace(base, theta_a_reference=self.theta(ready=False)),
            lambda: replace(base, ordered_rule_specs=()),
            lambda: replace(base, ordered_rule_specs=all_optional),
            lambda: replace(base, resource_references=()),
            lambda: replace(
                base,
                resource_references=base.resource_references
                + (
                    HardConstraintResourceRefV2(
                        resource_reference_id="resource:unused:v1",
                        resource_kind="SYNTHETIC_RESOURCE",
                        resource_id="unused",
                        resource_version="v1",
                        declared_content_reference="synthetic://unused/v1",
                    ),
                ),
            ),
        )
        for builder in invalid_builders:
            with self.subTest(builder=builder):
                with self.assertRaises(HardConstraintProfileConfigurationError):
                    builder()

    def test_profile_rule_codes_positions_and_resources_are_strict(self) -> None:
        base = self.profile()
        with self.assertRaises(HardConstraintProfileConfigurationError):
            replace(base.ordered_rule_specs[0], rule_id="bad-rule")
        with self.assertRaises(HardConstraintProfileConfigurationError):
            replace(base.ordered_rule_specs[0], position=True)
        with self.assertRaises(HardConstraintProfileConfigurationError):
            replace(base, ordered_rule_specs=tuple(reversed(base.ordered_rule_specs)))
        with self.assertRaises(HardConstraintProfileConfigurationError):
            replace(
                base,
                ordered_rule_specs=(
                    replace(
                        base.ordered_rule_specs[0],
                        resource_reference_ids=("resource:unknown:v1",),
                    ),
                )
                + base.ordered_rule_specs[1:],
            )

    def test_candidate_and_permanent_c0_identity_cannot_drift(self) -> None:
        result = self.result()
        foreign_c0 = replace(
            result.c0_candidate,
            receipt_id="other-receipt",
            field_id="other-receipt:store-name",
            candidate_id="other-receipt:store-name:c0",
            c0_candidate_id="other-receipt:store-name:c0",
            provenance=(
                replace(
                    result.c0_candidate.provenance[0],
                    receipt_id="other-receipt",
                    field_id="other-receipt:store-name",
                    candidate_id="other-receipt:store-name:c0",
                ),
            ),
        )
        with self.assertRaises(HardConstraintAuditIntegrityError):
            replace(result, c0_candidate=foreign_c0)

    def test_overflow_candidate_cannot_receive_v2_audit(self) -> None:
        c0 = self.original()
        overflow = replace(
            self.altered(c0),
            limit_status=CandidateLimitStatus.LIMIT_OVERFLOW,
            overflow_reason="LIMIT_OVERFLOW",
        )
        with self.assertRaises(HardConstraintAuditIntegrityError):
            self.result(candidate=overflow, c0=c0)

    def test_nested_candidate_mutation_is_detected_on_reconstruction(self) -> None:
        result = self.result()
        object.__setattr__(
            result.candidate.provenance[0],
            "source_kind",
            "FORGED_SOURCE_KIND",
        )
        with self.assertRaises(HardConstraintAuditIntegrityError):
            result.__post_init__()

    def test_direct_v2_rejects_boolean_nested_rank_integers(self) -> None:
        for field_name in (
            "source_priority_rank",
            "source_order_displacement",
            "rank_position",
        ):
            with self.subTest(field_name=field_name):
                c0 = self.original()
                altered = self.altered(c0)
                invalid_rank = replace(
                    altered.preliminary_rank,
                    **{field_name: True},
                )
                invalid_candidate = replace(
                    altered,
                    preliminary_rank=invalid_rank,
                )
                with self.assertRaises(HardConstraintAuditIntegrityError):
                    self.result(candidate=invalid_candidate, c0=c0)

    def test_direct_v2_rejects_boolean_provenance_position(self) -> None:
        c0 = self.original()
        altered = self.altered(c0)
        invalid_provenance = replace(
            altered.provenance[0],
            source_order_position=True,
        )
        invalid_candidate = replace(
            altered,
            provenance=(invalid_provenance,),
        )
        with self.assertRaises(HardConstraintAuditIntegrityError):
            self.result(candidate=invalid_candidate, c0=c0)

    def test_direct_v2_revalidates_span_integer_types(self) -> None:
        for field_name in ("start", "end"):
            with self.subTest(field_name=field_name):
                c0 = self.original()
                object.__setattr__(
                    c0.provenance[0].source_spans[0],
                    field_name,
                    True,
                )
                with self.assertRaises(HardConstraintAuditIntegrityError):
                    self.result(candidate=c0, c0=c0)

    def test_legitimate_nested_integers_round_trip_without_decimal_rescaling(self) -> None:
        c0 = self.original()
        altered = self.altered(c0)
        provenance = replace(
            altered.provenance[0],
            source_order_relationship="SAME_TOKEN",
            source_order_position=0,
        )
        candidate = replace(altered, provenance=(provenance,))
        result = self.result(candidate=candidate, c0=c0)
        payload = constraint_result_v2_to_json(result)
        rebuilt = constraint_result_v2_from_json(payload)
        self.assertEqual(rebuilt, result)
        self.assertIn('"normalized_edit_similarity":"0.8750"', payload)

    def test_rule_profile_and_resource_provenance_cannot_drift(self) -> None:
        result = self.result()
        optional = result.rule_outcomes[2]
        with self.assertRaises(HardConstraintAuditIntegrityError):
            replace(optional, resource_references=())
        with self.assertRaises(HardConstraintAuditIntegrityError):
            replace(optional, theta_a_reference=self.theta(ready=False))

    def test_theta_kind_state_and_matching_reference_are_enforced(self) -> None:
        theta = self.theta()
        with self.assertRaises(HardConstraintProfileConfigurationError):
            self.profile(theta=replace(theta, kind=ConfigurationKind.KAPPA))
        with self.assertRaises(HardConstraintProfileConfigurationError):
            self.profile(theta=self.theta(ready=False))
        result = self.result()
        different_ready = replace(
            result.theta_a_reference,
            configuration_id="theta-a-different",
        )
        with self.assertRaises(HardConstraintAuditIntegrityError):
            replace(result.rule_outcomes[0], theta_a_reference=different_ready)

    def test_missing_and_unresolved_d3_evidence_are_not_v2_unavailable_states(self) -> None:
        self.assertIn(OperandAvailabilityV0.MISSING, tuple(OperandAvailabilityV0))
        self.assertIn(OperandAvailabilityV0.UNRESOLVED, tuple(OperandAvailabilityV0))
        self.assertNotIn("UNAVAILABLE", OperandAvailabilityV0.__members__)
        self.assertIn(
            RuleOutcomeStateV2.UNAVAILABLE,
            tuple(RuleOutcomeStateV2),
        )
        self.assertIsNot(RuleEvidenceAvailabilityV2, ValueAvailabilityStatus)

    def test_v2_unavailability_has_no_implicit_v1_projection(self) -> None:
        result = self.result(
            (
                RuleOutcomeStateV2.UNAVAILABLE,
                RuleOutcomeStateV2.PASS,
                RuleOutcomeStateV2.PASS,
            )
        )
        self.assertIs(
            result.aggregate_state,
            ConstraintAggregateStateV2.CONSTRAINT_UNAVAILABLE,
        )
        import pipeline.proposed.hard_constraint_contracts_v2 as module

        self.assertNotIn("ConstraintResultV1", inspect.getsource(module))

    def test_standalone_record_is_candidate_level_not_field_wide(self) -> None:
        result = self.result()
        public_names = set(dir(result))
        self.assertNotIn("candidate_audits", public_names)
        self.assertNotIn("retained_candidates", public_names)
        self.assertEqual(result.candidate.candidate_id, self.C0_ID)

    def _source_audit(self):
        from pipeline.proposed.candidate_deduplication import deduplicate_candidate_drafts
        from pipeline.proposed.candidate_finalization import materialize_ranked_candidate_records
        from pipeline.proposed.candidate_identity import prepare_candidate_identities
        from pipeline.proposed.candidate_limiting import (
            CandidateLimitingConfigurationV0,
            apply_candidate_limit,
        )
        from pipeline.proposed.candidate_provenance import materialize_altered_provenance
        from pipeline.proposed.candidate_ranking import (
            CandidateRankingConfigurationV0,
            compute_preliminary_candidate_ranking,
        )
        from pipeline.proposed.hard_constraint_context import prepare_hard_constraint_inputs
        from pipeline.proposed.hard_constraint_operands import audit_hard_constraint_operands
        from tests.test_proposed_candidate_deduplication import (
            _SyntheticCandidateFixture,
        )

        fixture = _SyntheticCandidateFixture("hc-v2-source-bound-receipt")
        drafts = fixture.drafts()
        provenance = materialize_altered_provenance(
            identity_preparation=prepare_candidate_identities(
                deduplication_result=deduplicate_candidate_drafts(
                    candidate_drafts=drafts
                )
            )
        )
        ranking = compute_preliminary_candidate_ranking(
            provenance_result=provenance,
            configuration=CandidateRankingConfigurationV0(
                theta_a_ref=drafts.suspicion_result.theta_a_ref
            ),
        )
        limited = apply_candidate_limit(
            ranking_result=ranking,
            configuration=CandidateLimitingConfigurationV0(
                theta_a_ref=ranking.configuration.theta_a_ref,
                candidate_limit=1,
                fixture_reference="synthetic:hc-v2-source-bound",
            ),
        )
        finalized = materialize_ranked_candidate_records(limit_result=limited)
        context = prepare_hard_constraint_inputs(finalization_result=finalized)
        return audit_hard_constraint_operands(hard_constraint_input=context)

    def _source_bound_inputs(self):
        audit = self._source_audit()
        candidate_audit = audit.candidate_audits[0]
        theta = (
            audit.hard_constraint_input.finalization_result.limit_result
            .ranking_result.configuration.theta_a_ref
        )
        profile, outcomes = self._source_profile_and_outcomes(
            candidate_audit,
            theta,
        )
        return audit, candidate_audit, profile, outcomes

    def _source_profile_and_outcomes(self, candidate_audit, theta):
        candidate = candidate_audit.candidate
        profile = self.profile(theta=theta)
        outcomes = tuple(
            self.outcome(
                candidate=candidate,
                c0=candidate,
                profile=profile,
                rule_index=index,
                state=state,
            )
            for index, state in enumerate(
                (
                    RuleOutcomeStateV2.PASS,
                    RuleOutcomeStateV2.PASS,
                    RuleOutcomeStateV2.NOT_APPLICABLE,
                )
            )
        )
        return profile, outcomes

    def test_source_bound_factory_requires_exact_d3_candidate_audit(self) -> None:
        audit, candidate_audit, profile, outcomes = self._source_bound_inputs()
        result = build_source_bound_constraint_result_v2(
            constraint_result_id="hc-v2-source-bound-result",
            operand_audit=audit,
            candidate_audit=candidate_audit,
            rule_profile_reference=profile,
            rule_outcomes=outcomes,
        )
        self.assertIs(result.candidate, candidate_audit.candidate)
        with self.assertRaises(HardConstraintSourceBindingError):
            build_source_bound_constraint_result_v2(
                constraint_result_id="hc-v2-copied-audit",
                operand_audit=audit,
                candidate_audit=replace(candidate_audit),
                rule_profile_reference=profile,
                rule_outcomes=outcomes,
            )

    def test_source_bound_factory_uses_typed_audit_errors_for_bad_rule_sets(self) -> None:
        audit, candidate_audit, profile, outcomes = self._source_bound_inputs()
        mutations = {
            "missing": outcomes[:-1],
            "extra": outcomes + (outcomes[-1],),
            "duplicate": (outcomes[0], outcomes[0], outcomes[2]),
            "reordered": (outcomes[1], outcomes[0], outcomes[2]),
        }
        for case_name, mutation in mutations.items():
            with self.subTest(case_name=case_name):
                with self.assertRaises(HardConstraintAuditIntegrityError):
                    build_source_bound_constraint_result_v2(
                        constraint_result_id=f"hc-v2-source-bound-{case_name}",
                        operand_audit=audit,
                        candidate_audit=candidate_audit,
                        rule_profile_reference=profile,
                        rule_outcomes=mutation,
                    )

    def test_source_bound_factory_binds_complete_theta_a_to_d3_context(self) -> None:
        audit, candidate_audit, matching_profile, matching_outcomes = (
            self._source_bound_inputs()
        )
        upstream_theta = audit.hard_constraint_input.theta_a_ref
        matching = build_source_bound_constraint_result_v2(
            constraint_result_id="hc-v2-source-bound-matching-theta",
            operand_audit=audit,
            candidate_audit=candidate_audit,
            rule_profile_reference=matching_profile,
            rule_outcomes=matching_outcomes,
        )
        self.assertEqual(matching.theta_a_reference, upstream_theta)

        mismatches = {
            "configuration_id": replace(
                upstream_theta,
                configuration_id="different-theta-a-id",
            ),
            "configuration_version": replace(
                upstream_theta,
                configuration_version="different-version",
            ),
            "content_hash": replace(
                upstream_theta,
                content_hash="sha256:different-declared-content",
            ),
        }
        for case_name, mismatched_theta in mismatches.items():
            with self.subTest(case_name=case_name):
                profile, outcomes = self._source_profile_and_outcomes(
                    candidate_audit,
                    mismatched_theta,
                )
                with self.assertRaises(HardConstraintSourceBindingError):
                    build_source_bound_constraint_result_v2(
                        constraint_result_id=f"hc-v2-theta-mismatch-{case_name}",
                        operand_audit=audit,
                        candidate_audit=candidate_audit,
                        rule_profile_reference=profile,
                        rule_outcomes=outcomes,
                    )

        equal_but_distinct_theta = replace(upstream_theta)
        self.assertIsNot(equal_but_distinct_theta, upstream_theta)
        self.assertEqual(equal_but_distinct_theta, upstream_theta)
        equal_profile, equal_outcomes = self._source_profile_and_outcomes(
            candidate_audit,
            equal_but_distinct_theta,
        )
        equal_result = build_source_bound_constraint_result_v2(
            constraint_result_id="hc-v2-source-bound-equal-distinct-theta",
            operand_audit=audit,
            candidate_audit=candidate_audit,
            rule_profile_reference=equal_profile,
            rule_outcomes=equal_outcomes,
        )
        self.assertEqual(equal_result.theta_a_reference, upstream_theta)
        self.assertIsNot(equal_result.theta_a_reference, upstream_theta)

    def test_standalone_constructor_preserves_content_not_python_identity(self) -> None:
        result = self.result()
        rebuilt = constraint_result_v2_from_json(
            constraint_result_v2_to_json(result)
        )
        self.assertEqual(rebuilt, result)
        self.assertIsNot(rebuilt.candidate, result.candidate)

    def test_deterministic_json_round_trip_preserves_decimal_and_nulls(self) -> None:
        c0 = self.original()
        result = self.result(candidate=self.altered(c0), c0=c0)
        payload = constraint_result_v2_to_json(result)
        rebuilt = constraint_result_v2_from_json(payload)
        self.assertEqual(constraint_result_v2_to_json(rebuilt), payload)
        decoded = json.loads(payload)
        self.assertEqual(
            decoded["candidate"]["preliminary_rank"]["normalized_edit_similarity"],
            "0.8750",
        )
        self.assertIsNone(decoded["rule_outcomes"][0]["outcome_code"])

    def test_serialization_rejects_unknown_fields_versions_enums_and_decimal_numbers(self) -> None:
        decoded = json.loads(constraint_result_v2_to_json(self.result()))
        mutations = []
        unknown = json.loads(json.dumps(decoded))
        unknown["unknown"] = "value"
        mutations.append(unknown)
        version = json.loads(json.dumps(decoded))
        version["record_version"] = "999"
        mutations.append(version)
        enum_value = json.loads(json.dumps(decoded))
        enum_value["aggregate_state"] = "UNKNOWN"
        mutations.append(enum_value)
        c0 = self.original()
        altered = json.loads(
            constraint_result_v2_to_json(self.result(candidate=self.altered(c0), c0=c0))
        )
        altered["candidate"]["preliminary_rank"]["normalized_edit_similarity"] = 0.875
        mutations.append(altered)
        for mutation in mutations:
            with self.subTest(mutation=mutation.get("unknown", "known")):
                with self.assertRaises(HardConstraintSerializationError):
                    constraint_result_v2_from_json(json.dumps(mutation))

    def test_direct_unsupported_versions_are_rejected(self) -> None:
        result = self.result()
        with self.assertRaises(HardConstraintAuditIntegrityError):
            replace(result, record_version="999")
        with self.assertRaises(HardConstraintProfileConfigurationError):
            replace(result.rule_profile_reference, record_version="999")

    def test_serialization_rejects_bom_and_malformed_json(self) -> None:
        with self.assertRaises(HardConstraintSerializationError):
            constraint_result_v2_from_json("\ufeff{}")
        with self.assertRaises(HardConstraintSerializationError):
            constraint_result_v2_from_json("{")
        with self.assertRaises(HardConstraintSerializationError):
            constraint_result_v2_from_json(
                '{"record_version":"2","record_version":"2"}'
            )

    def test_fixture_positive_records_reconstruct_deterministically(self) -> None:
        fixture = json.loads(self.FIXTURE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(fixture["fixture_version"], "hard-constraint-v2-fixture-v2")
        for record in fixture["positive_records"]:
            with self.subTest(record=record["constraint_result_id"]):
                payload = json.dumps(
                    record,
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                rebuilt = constraint_result_v2_from_json(payload)
                self.assertEqual(constraint_result_v2_to_json(rebuilt), payload)

    def _execute_negative_fixture_case(self, operation: str) -> None:
        if operation.startswith("JSON_"):
            document = json.loads(constraint_result_v2_to_json(self.result()))
            outcomes = document["rule_outcomes"]
            if operation == "JSON_REMOVE_LAST_RULE_OUTCOME":
                outcomes.pop()
            elif operation == "JSON_DUPLICATE_FIRST_RULE_OUTCOME":
                outcomes[1] = json.loads(json.dumps(outcomes[0]))
            elif operation == "JSON_APPEND_UNEXPECTED_RULE_OUTCOME":
                outcomes.append(json.loads(json.dumps(outcomes[-1])))
            elif operation == "JSON_SWAP_FIRST_TWO_RULE_OUTCOMES":
                outcomes[0], outcomes[1] = outcomes[1], outcomes[0]
            else:
                self.fail(f"Unsupported JSON fixture operation: {operation}")
            constraint_result_v2_from_json(json.dumps(document))
            return

        if operation == "CONSTRUCT_NOT_READY_PROFILE":
            replace(
                self.profile(),
                theta_a_reference=self.theta(ready=False),
            )
            return
        if operation == "CONSTRUCT_AGGREGATE_MISMATCH":
            replace(
                self.result(),
                aggregate_state=ConstraintAggregateStateV2.CONSTRAINT_REJECTED,
                aggregate_reason=ConstraintAggregateReasonV2.MANDATORY_RULE_FAILED,
            )
            return
        if operation == "CONSTRUCT_C0_CONTENT_MISMATCH":
            result = self.result()
            replace(
                result,
                c0_candidate=replace(result.c0_candidate, value="OTHER C0"),
            )
            return
        if operation == "LIVE_COPY_CANDIDATE_AUDIT":
            audit, candidate_audit, profile, outcomes = self._source_bound_inputs()
            build_source_bound_constraint_result_v2(
                constraint_result_id="hc-v2-fixture-copied-live-audit",
                operand_audit=audit,
                candidate_audit=replace(candidate_audit),
                rule_profile_reference=profile,
                rule_outcomes=outcomes,
            )
            return
        self.fail(f"Unsupported negative fixture operation: {operation}")

    def test_fixture_negative_cases_execute_at_declared_boundaries(self) -> None:
        fixture = json.loads(self.FIXTURE_PATH.read_text(encoding="utf-8"))
        expected_errors = {
            "HardConstraintSerializationError": HardConstraintSerializationError,
            "HardConstraintProfileConfigurationError": (
                HardConstraintProfileConfigurationError
            ),
            "HardConstraintAuditIntegrityError": HardConstraintAuditIntegrityError,
            "HardConstraintSourceBindingError": HardConstraintSourceBindingError,
        }
        expected_boundaries = {
            "JSON_DESERIALIZATION",
            "STANDALONE_CONSTRUCTOR",
            "LIVE_D3_FACTORY",
        }
        self.assertEqual(len(fixture["negative_cases"]), 8)
        self.assertEqual(
            len({case["case_id"] for case in fixture["negative_cases"]}),
            8,
        )
        self.assertEqual(
            len({case["operation"] for case in fixture["negative_cases"]}),
            8,
        )
        for case in fixture["negative_cases"]:
            with self.subTest(case_id=case["case_id"]):
                self.assertIn(case["boundary"], expected_boundaries)
                expected_boundary = (
                    "JSON_DESERIALIZATION"
                    if case["operation"].startswith("JSON_")
                    else "STANDALONE_CONSTRUCTOR"
                    if case["operation"].startswith("CONSTRUCT_")
                    else "LIVE_D3_FACTORY"
                )
                self.assertEqual(case["boundary"], expected_boundary)
                expected_error = expected_errors[case["expected_error"]]
                with self.assertRaises(expected_error):
                    self._execute_negative_fixture_case(case["operation"])

    def test_module_does_not_implement_downstream_services(self) -> None:
        import pipeline.proposed.hard_constraint_contracts_v2 as module

        source = inspect.getsource(module)
        for forbidden in (
            "CandidateEvidenceV1(",
            "FieldDecisionV1(",
            "calibrated_probability=",
            "PersistenceResultState",
            "ReviewResolutionV1(",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
