"""Synthetic tests for the reusable observational backend execution seam."""

from __future__ import annotations

import inspect
import unittest
from dataclasses import replace
from unittest.mock import patch

from pipeline.contracts import ReceiptFieldName
from pipeline.proposed.backend_observational_path import (
    execute_purchase_date_observational_path_v0,
)
import pipeline.proposed.backend_observational_path as path_module
from pipeline.proposed.candidate_generation import CandidateGenerationIntegrityError
from pipeline.proposed.candidate_limiting import (
    CandidateLimitingConfigurationV0,
    CandidateLimitingIntegrityError,
)
from pipeline.proposed.candidate_ranking import (
    CandidateRankingConfigurationV0,
    CandidateRankingIntegrityError,
)
from pipeline.proposed.contracts import CandidateRole, CandidateSourceKind
from pipeline.proposed.hard_constraint_contracts_v2 import (
    ConstraintAggregateStateV2,
    HardConstraintProfileRefV2,
    HardConstraintRuleSpecV2,
    RuleOutcomeStateV2,
    RuleRequirementV2,
    constraint_result_v2_to_json,
)
from pipeline.proposed.purchase_date_calendar_validity import (
    PURCHASE_DATE_APPLICABILITY_REFERENCE,
    PURCHASE_DATE_CALENDAR_VALIDITY_RULE_ID,
    PURCHASE_DATE_CALENDAR_VALIDITY_RULE_VERSION,
    PURCHASE_DATE_GRAMMAR_REFERENCE,
    PURCHASE_DATE_PROFILE_ID,
    PURCHASE_DATE_PROFILE_VERSION,
    PurchaseDateConfigurationError,
)
import test_proposed_backend_integration as integration_fixtures


_GENERIC = CandidateSourceKind.GENERIC_NORMALIZATION
_FIXTURE_REFERENCE = "synthetic:backend-observational-path:v0"


class ProposedBackendObservationalPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.integration = integration_fixtures.ProposedBackendIntegrationTests(
            methodName="runTest"
        )

    @staticmethod
    def profile(theta_a) -> HardConstraintProfileRefV2:
        return HardConstraintProfileRefV2(
            profile_id=PURCHASE_DATE_PROFILE_ID,
            profile_version=PURCHASE_DATE_PROFILE_VERSION,
            theta_a_reference=theta_a,
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

    def inputs(
        self,
        *,
        synthetic_values: tuple[str, ...] | None,
        candidate_limit: int,
    ) -> dict[str, object]:
        fixture = self.integration.fixture()
        adapter_result, method_field = fixture.adapter_and_method(
            ReceiptFieldName.PURCHASE_DATE
        )
        if synthetic_values is not None:
            seeds = tuple(
                fixture.seed(
                    method_field,
                    suffix=f"observational-path-{index}",
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

        suspicion_result = self.integration.suspicion(method_field)
        ranking_configuration = CandidateRankingConfigurationV0(
            theta_a_ref=suspicion_result.theta_a_ref
        )
        limiting_configuration = CandidateLimitingConfigurationV0(
            theta_a_ref=suspicion_result.theta_a_ref,
            candidate_limit=candidate_limit,
            fixture_reference=_FIXTURE_REFERENCE,
        )
        rule_profile_reference = self.profile(suspicion_result.theta_a_ref)
        return {
            "adapter_result": adapter_result,
            "suspicion_result": suspicion_result,
            "ranking_configuration": ranking_configuration,
            "limiting_configuration": limiting_configuration,
            "rule_profile_reference": rule_profile_reference,
            "grammar_reference": PURCHASE_DATE_GRAMMAR_REFERENCE,
        }

    @staticmethod
    def execute(inputs: dict[str, object]):
        return execute_purchase_date_observational_path_v0(**inputs)

    def test_public_interface_is_exact_and_keyword_only(self) -> None:
        signature = inspect.signature(execute_purchase_date_observational_path_v0)
        self.assertEqual(
            (
                "adapter_result",
                "suspicion_result",
                "ranking_configuration",
                "limiting_configuration",
                "rule_profile_reference",
                "grammar_reference",
            ),
            tuple(signature.parameters),
        )
        self.assertTrue(
            all(
                parameter.kind is inspect.Parameter.KEYWORD_ONLY
                for parameter in signature.parameters.values()
            )
        )
        self.assertEqual(
            ("execute_purchase_date_observational_path_v0",),
            path_module.__all__,
        )

    def test_natural_adapter_path_preserves_c0_and_does_not_rerun_upstream(self) -> None:
        inputs = self.inputs(synthetic_values=None, candidate_limit=2)
        adapter = inputs["adapter_result"]
        method = inputs["suspicion_result"].method_ready_field
        natural_seeds = tuple(
            seed for seed in adapter.b3_seeds if seed.field_id == method.field_id
        )
        self.assertEqual(
            ("2026-10-14",),
            tuple(seed.proposed_value for seed in natural_seeds),
        )

        with patch(
            "pipeline.ocr_adapter.adapt_paddleocr_result",
            side_effect=AssertionError("OCR must not rerun"),
        ), patch(
            "pipeline.layout_b2.extract_b2",
            side_effect=AssertionError("B2 must not rerun"),
        ), patch(
            "pipeline.baseline_b3.apply_b3",
            side_effect=AssertionError("B3 must not rerun"),
        ), patch(
            "pipeline.proposed.adapter.adapt_b2_to_proposed",
            side_effect=AssertionError("adapter must not rerun"),
        ), patch(
            "pipeline.proposed.suspicion.detect_suspicion",
            side_effect=AssertionError("suspicion must not rerun"),
        ):
            results = self.execute(inputs)

        self.assertEqual(1, len(results))
        result = results[0]
        self.assertIs(CandidateRole.ORIGINAL, result.candidate.role)
        self.assertIs(result.candidate, result.c0_candidate)
        self.assertEqual(method.c0_candidate_id, result.candidate.candidate_id)
        self.assertEqual(method.c0_value, result.candidate.value)
        self.assertIs(RuleOutcomeStateV2.PASS, result.rule_outcomes[0].state)
        self.assertIs(ConstraintAggregateStateV2.ELIGIBLE, result.aggregate_state)
        self.assertEqual(
            method.source_token_ids,
            result.candidate.provenance[0].source_token_ids,
        )

    def test_multiple_candidates_preserve_all_states_identity_and_theta(self) -> None:
        inputs = self.inputs(
            synthetic_values=("31/02/2026", "10/11/2026"),
            candidate_limit=3,
        )
        stage = path_module._evaluate_purchase_date_constraint_stage_v0
        with patch.object(
            path_module,
            "_evaluate_purchase_date_constraint_stage_v0",
            wraps=stage,
        ) as stage_call:
            results = self.execute(inputs)

        stage_call.assert_called_once()
        operand_audit = stage_call.call_args.kwargs["operand_audit"]
        self.assertEqual(3, len(results))
        self.assertEqual(len(operand_audit.candidate_audits), len(results))
        self.assertTrue(
            all(
                result.candidate is candidate_audit.candidate
                for candidate_audit, result in zip(
                    operand_audit.candidate_audits,
                    results,
                    strict=True,
                )
            )
        )
        c0 = results[0].candidate
        self.assertIs(CandidateRole.ORIGINAL, c0.role)
        self.assertTrue(all(result.c0_candidate is c0 for result in results))
        self.assertEqual(
            len({result.candidate.candidate_id for result in results}),
            len(results),
        )

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

        theta_a = inputs["suspicion_result"].theta_a_ref
        self.assertEqual(theta_a, inputs["ranking_configuration"].theta_a_ref)
        self.assertEqual(theta_a, inputs["limiting_configuration"].theta_a_ref)
        self.assertEqual(theta_a, inputs["rule_profile_reference"].theta_a_reference)
        self.assertTrue(all(result.theta_a_reference == theta_a for result in results))
        self.assertTrue(all(result.candidate.provenance for result in results))
        altered_provenance = {
            result.candidate.value: result.candidate.provenance
            for result in results[1:]
        }
        self.assertEqual(
            (_GENERIC,),
            tuple(item.source_kind for item in altered_provenance["31/02/2026"]),
        )
        self.assertEqual(
            ("rule:observational-path-0",),
            tuple(
                item.generic_rule_id
                for item in altered_provenance["31/02/2026"]
            ),
        )
        self.assertEqual(
            (_GENERIC,),
            tuple(item.source_kind for item in altered_provenance["10/11/2026"]),
        )
        self.assertEqual(
            ("rule:observational-path-1",),
            tuple(
                item.generic_rule_id
                for item in altered_provenance["10/11/2026"]
            ),
        )

    def test_repeated_execution_is_deterministic_and_does_not_mutate_inputs(self) -> None:
        inputs = self.inputs(
            synthetic_values=("31/02/2026", "10/11/2026"),
            candidate_limit=3,
        )
        adapter = inputs["adapter_result"]
        suspicion = inputs["suspicion_result"]
        candidate_ids_before = tuple(seed.seed_id for seed in adapter.b3_seeds)
        input_snapshots = {
            name: (id(value), repr(value)) for name, value in inputs.items()
        }

        first = self.execute(inputs)
        second = self.execute(inputs)

        self.assertEqual(
            tuple(constraint_result_v2_to_json(result) for result in first),
            tuple(constraint_result_v2_to_json(result) for result in second),
        )
        self.assertEqual(
            candidate_ids_before,
            tuple(seed.seed_id for seed in adapter.b3_seeds),
        )
        self.assertEqual(
            input_snapshots,
            {name: (id(value), repr(value)) for name, value in inputs.items()},
        )
        adapter.__post_init__()
        suspicion.__post_init__()
        inputs["ranking_configuration"].__post_init__()
        inputs["limiting_configuration"].__post_init__()
        inputs["rule_profile_reference"].__post_init__()

    def test_mismatched_adapter_and_suspicion_fail_closed(self) -> None:
        natural = self.inputs(synthetic_values=None, candidate_limit=2)
        altered = self.inputs(
            synthetic_values=("31/02/2026",),
            candidate_limit=2,
        )
        contradictory = dict(natural)
        contradictory["suspicion_result"] = altered["suspicion_result"]
        with self.assertRaises(CandidateGenerationIntegrityError):
            self.execute(contradictory)

    def test_ranking_theta_mismatch_propagates_typed_error(self) -> None:
        inputs = self.inputs(synthetic_values=None, candidate_limit=2)
        theta_a = inputs["suspicion_result"].theta_a_ref
        inputs["ranking_configuration"] = CandidateRankingConfigurationV0(
            theta_a_ref=replace(
                theta_a,
                configuration_id="different-ranking-theta-a",
            )
        )
        with self.assertRaises(CandidateRankingIntegrityError):
            self.execute(inputs)

    def test_limiting_theta_mismatch_propagates_typed_error(self) -> None:
        inputs = self.inputs(synthetic_values=None, candidate_limit=2)
        theta_a = inputs["suspicion_result"].theta_a_ref
        inputs["limiting_configuration"] = CandidateLimitingConfigurationV0(
            theta_a_ref=replace(
                theta_a,
                configuration_id="different-limiting-theta-a",
            ),
            candidate_limit=2,
            fixture_reference=_FIXTURE_REFERENCE,
        )
        with self.assertRaises(CandidateLimitingIntegrityError):
            self.execute(inputs)

    def test_profile_theta_mismatch_propagates_typed_error(self) -> None:
        inputs = self.inputs(synthetic_values=None, candidate_limit=2)
        profile = inputs["rule_profile_reference"]
        inputs["rule_profile_reference"] = replace(
            profile,
            theta_a_reference=replace(
                profile.theta_a_reference,
                configuration_id="different-profile-theta-a",
            ),
        )
        with self.assertRaises(PurchaseDateConfigurationError):
            self.execute(inputs)

    def test_grammar_mismatch_propagates_typed_error(self) -> None:
        inputs = self.inputs(synthetic_values=None, candidate_limit=2)
        inputs["grammar_reference"] = "purchase-date-grammar:contradictory"
        with self.assertRaises(PurchaseDateConfigurationError):
            self.execute(inputs)

    def test_incomplete_adapter_seed_graph_fails_before_results(self) -> None:
        inputs = self.inputs(synthetic_values=None, candidate_limit=2)
        adapter = inputs["adapter_result"]
        selected_field_id = inputs["suspicion_result"].method_ready_field.field_id
        object.__setattr__(
            adapter,
            "b3_seeds",
            tuple(
                seed for seed in adapter.b3_seeds if seed.field_id != selected_field_id
            ),
        )
        with self.assertRaises(CandidateGenerationIntegrityError):
            self.execute(inputs)


if __name__ == "__main__":
    unittest.main()
