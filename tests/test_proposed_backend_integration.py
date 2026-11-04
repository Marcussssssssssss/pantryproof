"""Synthetic end-to-end integration tests for the observational backend path."""

from __future__ import annotations

import unittest
from decimal import Decimal

from pipeline.baseline_b3 import apply_b3
from pipeline.contracts import ReceiptFieldName
from pipeline.layout_b2 import extract_b2
from pipeline.proposed.adapter import adapt_b2_to_proposed
from pipeline.proposed.candidate_deduplication import deduplicate_candidate_drafts
from pipeline.proposed.candidate_finalization import (
    materialize_ranked_candidate_records,
)
from pipeline.proposed.candidate_generation import generate_candidate_drafts
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
from pipeline.proposed.contracts import (
    CandidateSourceKind,
    ConfigurationKind,
    ConfigurationRefV1,
    ConfigurationState,
)
from pipeline.proposed.hard_constraint_context import prepare_hard_constraint_inputs
from pipeline.proposed.hard_constraint_contracts_v2 import (
    ConstraintAggregateStateV2,
    HardConstraintProfileRefV2,
    HardConstraintRuleSpecV2,
    RuleOutcomeStateV2,
    RuleRequirementV2,
    constraint_result_v2_to_json,
)
from pipeline.proposed.hard_constraint_operands import (
    HardConstraintOperandIntegrityError,
    audit_hard_constraint_operands,
)
from pipeline.proposed.purchase_date_calendar_validity import (
    PURCHASE_DATE_APPLICABILITY_REFERENCE,
    PURCHASE_DATE_CALENDAR_VALIDITY_RULE_ID,
    PURCHASE_DATE_CALENDAR_VALIDITY_RULE_VERSION,
    PURCHASE_DATE_GRAMMAR_REFERENCE,
    PURCHASE_DATE_PROFILE_ID,
    PURCHASE_DATE_PROFILE_VERSION,
)
from pipeline.proposed.purchase_date_constraint_stage import (
    evaluate_purchase_date_constraint_stage_v0,
)
from pipeline.proposed.suspicion import (
    ConfidenceAggregationV0,
    ConfidenceRuleV0,
    SuspicionConfigurationV0,
    SuspicionContextV0,
    UpstreamObservationStateV0,
    UpstreamObservationV0,
    UpstreamSignalV0,
    detect_suspicion,
)
from test_proposed_hard_constraint_operands import _LayoutCandidateFixture


_GENERIC = CandidateSourceKind.GENERIC_NORMALIZATION
_FIXTURE_REFERENCE = "synthetic:backend-integration:v0"


class ProposedBackendIntegrationTests(unittest.TestCase):
    @staticmethod
    def fixture() -> _LayoutCandidateFixture:
        return _LayoutCandidateFixture(
            "backend-integration-receipt",
            (
                ("store", "PANTRYPROOF TEST MART", 20, 0, 180),
                ("date", "DATE: 14/10/2026", 10, 20, 165),
                ("item", "MILK 2 5.50 11.00", 10, 45, 260),
                ("total", "TOTAL 11.00", 170, 80, 155),
            ),
        )

    @staticmethod
    def suspicion(method_field):
        context_builder_id = "backend-integration-context-v0"

        def observation(signal: UpstreamSignalV0) -> UpstreamObservationV0:
            state = (
                UpstreamObservationStateV0.FAIL
                if signal is UpstreamSignalV0.PARSE_TYPE
                else UpstreamObservationStateV0.PASS
            )
            return UpstreamObservationV0(
                observation_id=(
                    f"{method_field.field_id}:{signal.value}:integration-observation"
                ),
                receipt_id=method_field.receipt_id,
                field_id=method_field.field_id,
                signal=signal,
                state=state,
                provider_id=context_builder_id,
                provider_version="test-v0",
                evidence_ids=(
                    f"{method_field.field_id}:{signal.value}:integration-evidence",
                ),
                reason=(
                    "Synthetic parse/type suspicion."
                    if state is UpstreamObservationStateV0.FAIL
                    else None
                ),
            )

        observations = {
            signal: observation(signal) for signal in UpstreamSignalV0
        }
        context = SuspicionContextV0(
            context_id=f"{method_field.method_field_id}:integration-context",
            receipt_id=method_field.receipt_id,
            method_field_id=method_field.method_field_id,
            field_id=method_field.field_id,
            gate_result_id=method_field.stored_gate_result.gate_result_id,
            source_image_id=method_field.source_image_id,
            source_token_ids=method_field.source_token_ids,
            ocr_confidence_source="synthetic-ocr-source",
            context_builder_id=context_builder_id,
            context_builder_version="test-v0",
            required_content=observations[UpstreamSignalV0.REQUIRED_CONTENT],
            parse_type=observations[UpstreamSignalV0.PARSE_TYPE],
            line_association=observations[UpstreamSignalV0.LINE_ASSOCIATION],
            arithmetic=observations[UpstreamSignalV0.ARITHMETIC],
        )
        theta_a = ConfigurationRefV1(
            kind=ConfigurationKind.THETA_A,
            configuration_id="theta-a-backend-integration-v0",
            configuration_version="test-v0",
            state=ConfigurationState.READY,
            content_hash="sha256:synthetic-backend-integration-v0",
        )
        configuration = SuspicionConfigurationV0(
            theta_a_ref=theta_a,
            ocr_confidence_rule=ConfidenceRuleV0(
                rule_id="backend-integration-ocr-confidence",
                score_source="synthetic-ocr-source",
                aggregation=ConfidenceAggregationV0.MIN_ALL_REFERENCED,
                threshold=Decimal("0.50"),
                domain_minimum=Decimal("0.00"),
                domain_maximum=Decimal("1.00"),
            ),
            extractor_confidence_rule=ConfidenceRuleV0(
                rule_id="backend-integration-extractor-confidence",
                score_source=method_field.b2_extractor_version,
                aggregation=ConfidenceAggregationV0.DIRECT,
                threshold=Decimal("0.50"),
                domain_minimum=Decimal("0.00"),
                domain_maximum=Decimal("1.00"),
            ),
            context_builder_id=context_builder_id,
            context_builder_version="test-v0",
        )
        return detect_suspicion(method_field, context, configuration)

    @staticmethod
    def profile(operand_audit) -> HardConstraintProfileRefV2:
        return HardConstraintProfileRefV2(
            profile_id=PURCHASE_DATE_PROFILE_ID,
            profile_version=PURCHASE_DATE_PROFILE_VERSION,
            theta_a_reference=operand_audit.hard_constraint_input.theta_a_ref,
            ordered_rule_specs=(
                HardConstraintRuleSpecV2(
                    rule_id=PURCHASE_DATE_CALENDAR_VALIDITY_RULE_ID,
                    rule_version=PURCHASE_DATE_CALENDAR_VALIDITY_RULE_VERSION,
                    position=0,
                    requirement=RuleRequirementV2.MANDATORY,
                    applicability_reference=PURCHASE_DATE_APPLICABILITY_REFERENCE,
                ),
            ),
        )

    def execute(
        self,
        *,
        synthetic_values: tuple[str, ...] | None,
        candidate_limit: int,
    ) -> dict[str, object]:
        fixture = self.fixture()
        source_evidence = fixture.evidence()
        b2_result = extract_b2(source_evidence)
        b3_result = apply_b3(b2_result)
        adapter_result = adapt_b2_to_proposed(b2_result, b3_result)
        method_field = next(
            field
            for field in adapter_result.method_ready_fields
            if field.field_name is ReceiptFieldName.PURCHASE_DATE
        )

        if synthetic_values is not None:
            seeds = tuple(
                fixture.seed(
                    method_field,
                    suffix=f"backend-integration-{index}",
                    source_kind=_GENERIC,
                    proposed_value=value,
                )
                for index, value in enumerate(synthetic_values)
            )
            adapter_result, method_field = fixture.with_seeds(
                adapter_result,
                method_field,
                seeds,
            )

        suspicion_result = self.suspicion(method_field)
        candidate_drafts = generate_candidate_drafts(
            suspicion_result=suspicion_result,
            adapter_result=adapter_result,
        )
        deduplication_result = deduplicate_candidate_drafts(
            candidate_drafts=candidate_drafts
        )
        identity_result = prepare_candidate_identities(
            deduplication_result=deduplication_result
        )
        provenance_result = materialize_altered_provenance(
            identity_preparation=identity_result
        )
        ranking_result = compute_preliminary_candidate_ranking(
            provenance_result=provenance_result,
            configuration=CandidateRankingConfigurationV0(
                theta_a_ref=suspicion_result.theta_a_ref
            ),
        )
        limiting_result = apply_candidate_limit(
            ranking_result=ranking_result,
            configuration=CandidateLimitingConfigurationV0(
                theta_a_ref=ranking_result.configuration.theta_a_ref,
                candidate_limit=candidate_limit,
                fixture_reference=_FIXTURE_REFERENCE,
            ),
        )
        finalization_result = materialize_ranked_candidate_records(
            limit_result=limiting_result
        )
        hard_constraint_input = prepare_hard_constraint_inputs(
            finalization_result=finalization_result
        )
        operand_audit = audit_hard_constraint_operands(
            hard_constraint_input=hard_constraint_input
        )
        profile = self.profile(operand_audit)
        constraint_results = evaluate_purchase_date_constraint_stage_v0(
            operand_audit=operand_audit,
            rule_profile_reference=profile,
            grammar_reference=PURCHASE_DATE_GRAMMAR_REFERENCE,
        )
        return {
            "source_evidence": source_evidence,
            "b2_result": b2_result,
            "b3_result": b3_result,
            "adapter_result": adapter_result,
            "method_field": method_field,
            "suspicion_result": suspicion_result,
            "candidate_drafts": candidate_drafts,
            "deduplication_result": deduplication_result,
            "identity_result": identity_result,
            "provenance_result": provenance_result,
            "ranking_result": ranking_result,
            "limiting_result": limiting_result,
            "finalization_result": finalization_result,
            "hard_constraint_input": hard_constraint_input,
            "operand_audit": operand_audit,
            "profile": profile,
            "constraint_results": constraint_results,
        }

    def test_natural_b2_b3_seed_flows_through_complete_backend(self) -> None:
        execution = self.execute(synthetic_values=None, candidate_limit=2)
        adapter = execution["adapter_result"]
        method = execution["method_field"]
        natural_seeds = tuple(
            seed for seed in adapter.b3_seeds if seed.field_id == method.field_id
        )
        self.assertEqual(
            ("2026-10-14",),
            tuple(seed.proposed_value for seed in natural_seeds),
        )

        drafts = execution["candidate_drafts"]
        deduplicated = execution["deduplication_result"]
        self.assertEqual(1, len(drafts.altered_proposals))
        self.assertEqual((), deduplicated.altered_groups)
        self.assertIsNotNone(deduplicated.equivalent_to_c0)

        hard_input = execution["hard_constraint_input"]
        results = execution["constraint_results"]
        self.assertEqual(("14/10/2026",), tuple(c.value for c in hard_input.candidates))
        self.assertEqual(1, len(results))
        self.assertIs(hard_input.candidates[0], results[0].candidate)
        self.assertIs(hard_input.candidates[0], results[0].c0_candidate)
        self.assertIs(RuleOutcomeStateV2.PASS, results[0].rule_outcomes[0].state)
        self.assertIs(ConstraintAggregateStateV2.ELIGIBLE, results[0].aggregate_state)

        source_evidence = execution["source_evidence"]
        b2_result = execution["b2_result"]
        b3_result = execution["b3_result"]
        self.assertIs(source_evidence, b2_result.receipt_output.source_evidence)
        self.assertIs(b2_result, b3_result.original_b2_result)
        self.assertIs(b2_result, adapter.original_b2_result)
        self.assertIs(b2_result, hard_input.original_b2_result)

    def test_synthetic_multi_candidate_path_preserves_all_outcomes(self) -> None:
        execution = self.execute(
            synthetic_values=("31/02/2026", "10/11/2026"),
            candidate_limit=3,
        )
        hard_input = execution["hard_constraint_input"]
        operand_audit = execution["operand_audit"]
        results = execution["constraint_results"]

        self.assertEqual(3, len(results))
        self.assertTrue(
            all(
                result.candidate is audit.candidate
                for result, audit in zip(
                    results,
                    operand_audit.candidate_audits,
                    strict=True,
                )
            )
        )
        c0 = hard_input.candidates[0]
        self.assertIs(c0, results[0].candidate)
        self.assertTrue(all(result.c0_candidate is c0 for result in results))

        state_by_value = {
            result.candidate.value: result.rule_outcomes[0].state
            for result in results
        }
        self.assertIs(RuleOutcomeStateV2.PASS, state_by_value["14/10/2026"])
        self.assertIs(RuleOutcomeStateV2.FAIL, state_by_value["31/02/2026"])
        self.assertIs(
            RuleOutcomeStateV2.UNAVAILABLE,
            state_by_value["10/11/2026"],
        )

        theta_a = execution["suspicion_result"].theta_a_ref
        self.assertEqual(theta_a, execution["profile"].theta_a_reference)
        self.assertTrue(all(result.theta_a_reference == theta_a for result in results))

    def test_complete_path_is_deterministic_and_does_not_mutate_sources(self) -> None:
        first = self.execute(
            synthetic_values=("31/02/2026", "10/11/2026"),
            candidate_limit=3,
        )
        second = self.execute(
            synthetic_values=("31/02/2026", "10/11/2026"),
            candidate_limit=3,
        )
        first_results = first["constraint_results"]
        second_results = second["constraint_results"]
        self.assertEqual(
            tuple(constraint_result_v2_to_json(result) for result in first_results),
            tuple(constraint_result_v2_to_json(result) for result in second_results),
        )
        self.assertEqual(
            tuple(
                candidate.candidate_id
                for candidate in first["hard_constraint_input"].candidates
            ),
            tuple(
                candidate.candidate_id
                for candidate in second["hard_constraint_input"].candidates
            ),
        )

        for execution in (first, second):
            source = execution["source_evidence"]
            b2_result = execution["b2_result"]
            operand_audit = execution["operand_audit"]
            self.assertIs(source, b2_result.receipt_output.source_evidence)
            self.assertIs(source, operand_audit.hard_constraint_input.source_evidence)
            operand_audit.__post_init__()

    def test_tampered_candidate_completeness_fails_closed(self) -> None:
        execution = self.execute(
            synthetic_values=("31/02/2026", "10/11/2026"),
            candidate_limit=3,
        )
        operand_audit = execution["operand_audit"]
        object.__setattr__(
            operand_audit,
            "candidate_audits",
            operand_audit.candidate_audits[:-1],
        )
        with self.assertRaises(HardConstraintOperandIntegrityError):
            evaluate_purchase_date_constraint_stage_v0(
                operand_audit=operand_audit,
                rule_profile_reference=execution["profile"],
                grammar_reference=PURCHASE_DATE_GRAMMAR_REFERENCE,
            )


if __name__ == "__main__":
    unittest.main()
