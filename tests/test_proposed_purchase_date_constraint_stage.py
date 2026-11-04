"""Synthetic tests for the purchase-date candidate-set constraint stage V0."""

from __future__ import annotations

import inspect
import unittest
from dataclasses import replace
from unittest.mock import patch

from pipeline.contracts import ReceiptFieldName
from pipeline.proposed.contracts import CandidateSourceKind
from pipeline.proposed.hard_constraint_contracts_v2 import (
    ConstraintAggregateStateV2,
    EvidenceReferenceV2,
    HardConstraintProfileRefV2,
    HardConstraintRuleSpecV2,
    RuleOutcomeStateV2,
    RuleRequirementV2,
    build_source_bound_constraint_result_v2,
)
from pipeline.proposed.hard_constraint_operands import (
    HardConstraintOperandIntegrityError,
)
from pipeline.proposed.purchase_date_calendar_validity import (
    CANDIDATE_RECORD_EVIDENCE_NAMESPACE,
    PURCHASE_DATE_APPLICABILITY_REFERENCE,
    PURCHASE_DATE_CALENDAR_VALIDITY_RULE_ID,
    PURCHASE_DATE_CALENDAR_VALIDITY_RULE_VERSION,
    PURCHASE_DATE_GRAMMAR_REFERENCE,
    PURCHASE_DATE_PROFILE_ID,
    PURCHASE_DATE_PROFILE_VERSION,
    PurchaseDateConfigurationError,
    PurchaseDateIntegrityError,
    PurchaseDateParserCompatibilityError,
    PurchaseDateSourceBindingError,
    evaluate_purchase_date_calendar_validity_v0,
)
from pipeline.proposed.purchase_date_constraint_stage import (
    evaluate_purchase_date_constraint_stage_v0,
)
import pipeline.proposed.purchase_date_constraint_stage as stage_module
import test_proposed_hard_constraint_operands as operand_fixtures


GENERIC = CandidateSourceKind.GENERIC_NORMALIZATION


class ProposedPurchaseDateConstraintStageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.upstream = operand_fixtures.ProposedHardConstraintOperandTests(
            methodName="runTest"
        )
        self.upstream.setUp()

    @staticmethod
    def fixture():
        return operand_fixtures._LayoutCandidateFixture(
            "purchase-date-constraint-stage-receipt",
            (
                ("store", "PANTRYPROOF TEST MART", 20, 0, 180),
                ("date", "DATE: 14/10/2026", 10, 20, 165),
                ("item", "MILK 2 5.50 11.00", 10, 45, 260),
                ("total", "TOTAL 11.00", 170, 80, 155),
            ),
        )

    def audited(
        self,
        values: tuple[str, ...] = (),
        *,
        field_name: ReceiptFieldName = ReceiptFieldName.PURCHASE_DATE,
    ):
        specs = tuple(
            (f"purchase-date-seed-{index}", GENERIC, value)
            for index, value in enumerate(values)
        )
        return self.upstream.audited(
            specs,
            candidate_limit=1 + len(values),
            fixture=self.fixture(),
            field_name=field_name,
        )

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

    def evaluate(self, operand_audit=None, profile=None):
        selected_audit = operand_audit or self.audited()
        selected_profile = profile or self.profile(selected_audit)
        return evaluate_purchase_date_constraint_stage_v0(
            operand_audit=selected_audit,
            rule_profile_reference=selected_profile,
            grammar_reference=PURCHASE_DATE_GRAMMAR_REFERENCE,
        )

    def test_public_interface_is_keyword_only_and_returns_canonical_tuple(self) -> None:
        signature = inspect.signature(evaluate_purchase_date_constraint_stage_v0)
        self.assertEqual(
            ("operand_audit", "rule_profile_reference", "grammar_reference"),
            tuple(signature.parameters),
        )
        self.assertTrue(
            all(
                parameter.kind is inspect.Parameter.KEYWORD_ONLY
                for parameter in signature.parameters.values()
            )
        )
        self.assertEqual(
            ("evaluate_purchase_date_constraint_stage_v0",),
            stage_module.__all__,
        )
        results = self.evaluate()
        self.assertIsInstance(results, tuple)
        self.assertEqual(1, len(results))
        with self.assertRaises(TypeError):
            results[0] = results[0]

    def test_one_candidate_is_permanent_c0_and_uses_approved_ids(self) -> None:
        operand_audit = self.audited()
        result = self.evaluate(operand_audit)[0]
        candidate = operand_audit.candidate_audits[0].candidate
        self.assertIs(candidate, operand_audit.hard_constraint_input.candidates[0])
        self.assertIs(candidate, result.candidate)
        self.assertIs(candidate, result.c0_candidate)
        self.assertEqual(
            f"{candidate.candidate_id}:constraints:v2",
            result.constraint_result_id,
        )
        self.assertEqual(
            f"{candidate.candidate_id}:"
            f"{PURCHASE_DATE_CALENDAR_VALIDITY_RULE_ID}:outcome",
            result.rule_outcomes[0].rule_outcome_id,
        )

    def test_multiple_candidates_preserve_exact_c0_first_order(self) -> None:
        operand_audit = self.audited(("31/02/2026", "10/11/2026"))
        results = self.evaluate(operand_audit)
        expected_candidates = tuple(
            audit.candidate for audit in operand_audit.candidate_audits
        )
        self.assertEqual(len(expected_candidates), len(results))
        self.assertEqual(expected_candidates, tuple(item.candidate for item in results))
        self.assertTrue(
            all(
                result.candidate is candidate
                for result, candidate in zip(results, expected_candidates, strict=True)
            )
        )
        c0 = operand_audit.hard_constraint_input.candidates[0]
        self.assertIs(c0, results[0].candidate)
        self.assertTrue(all(result.c0_candidate is c0 for result in results))

    def test_evaluator_and_factory_run_exactly_once_per_candidate(self) -> None:
        operand_audit = self.audited(("31/02/2026", "10/11/2026"))
        with patch.object(
            stage_module,
            "_evaluate_purchase_date_calendar_validity_v0",
            wraps=evaluate_purchase_date_calendar_validity_v0,
        ) as evaluator, patch.object(
            stage_module,
            "_build_source_bound_constraint_result_v2",
            wraps=build_source_bound_constraint_result_v2,
        ) as factory:
            results = self.evaluate(operand_audit)

        self.assertEqual(len(operand_audit.candidate_audits), evaluator.call_count)
        self.assertEqual(len(operand_audit.candidate_audits), factory.call_count)
        self.assertEqual(len(results), factory.call_count)
        for call, expected_audit in zip(
            evaluator.call_args_list,
            operand_audit.candidate_audits,
            strict=True,
        ):
            self.assertIs(expected_audit, call.kwargs["candidate_audit"])
            self.assertIs(operand_audit, call.kwargs["operand_audit"])

    def test_pass_fail_and_unavailable_states_are_preserved(self) -> None:
        operand_audit = self.audited(("31/02/2026", "10/11/2026"))
        results = self.evaluate(operand_audit)
        state_by_value = {
            result.candidate.value: result.rule_outcomes[0].state
            for result in results
        }
        self.assertIn(RuleOutcomeStateV2.PASS, state_by_value.values())
        self.assertIs(
            RuleOutcomeStateV2.FAIL,
            state_by_value["31/02/2026"],
        )
        self.assertIs(
            RuleOutcomeStateV2.UNAVAILABLE,
            state_by_value["10/11/2026"],
        )
        aggregate_by_value = {
            result.candidate.value: result.aggregate_state for result in results
        }
        self.assertIs(
            ConstraintAggregateStateV2.CONSTRAINT_REJECTED,
            aggregate_by_value["31/02/2026"],
        )
        self.assertIs(
            ConstraintAggregateStateV2.CONSTRAINT_UNAVAILABLE,
            aggregate_by_value["10/11/2026"],
        )

    def test_repeated_evaluation_is_deterministic(self) -> None:
        operand_audit = self.audited(("31/02/2026", "10/11/2026"))
        profile = self.profile(operand_audit)
        first = self.evaluate(operand_audit, profile)
        second = self.evaluate(operand_audit, profile)
        self.assertEqual(first, second)
        self.assertEqual(
            tuple(item.constraint_result_id for item in first),
            tuple(item.constraint_result_id for item in second),
        )

    def test_results_preserve_source_provenance_and_theta_binding(self) -> None:
        operand_audit = self.audited(("31/02/2026",))
        profile = self.profile(operand_audit)
        results = self.evaluate(operand_audit, profile)
        c0 = operand_audit.hard_constraint_input.candidates[0]
        for result, candidate_audit in zip(
            results,
            operand_audit.candidate_audits,
            strict=True,
        ):
            candidate = candidate_audit.candidate
            outcome = result.rule_outcomes[0]
            self.assertIs(candidate, result.candidate)
            self.assertIs(candidate, outcome.candidate)
            self.assertIs(c0, result.c0_candidate)
            self.assertIs(c0, outcome.c0_candidate)
            self.assertIs(profile, result.rule_profile_reference)
            self.assertEqual(profile.theta_a_reference, result.theta_a_reference)
            self.assertEqual(
                (
                    EvidenceReferenceV2(
                        reference_namespace=CANDIDATE_RECORD_EVIDENCE_NAMESPACE,
                        reference_id=candidate.candidate_id,
                        source_record_version=candidate.record_version,
                    ),
                ),
                outcome.evidence_references,
            )

    def test_missing_duplicate_and_reordered_audits_are_rejected(self) -> None:
        for case in ("missing", "duplicate", "reordered"):
            with self.subTest(case=case):
                operand_audit = self.audited(("31/02/2026",))
                audits = operand_audit.candidate_audits
                if case == "missing":
                    forged = audits[:1]
                elif case == "duplicate":
                    forged = (audits[0], audits[0])
                else:
                    forged = tuple(reversed(audits))
                object.__setattr__(operand_audit, "candidate_audits", forged)
                with self.assertRaises(HardConstraintOperandIntegrityError):
                    self.evaluate(operand_audit)

    def test_value_equal_rebound_candidate_is_rejected(self) -> None:
        operand_audit = self.audited(("31/02/2026",))
        rebound_candidate = replace(operand_audit.candidate_audits[1].candidate)
        rebound_audit = replace(
            operand_audit.candidate_audits[1],
            candidate=rebound_candidate,
        )
        object.__setattr__(
            operand_audit,
            "candidate_audits",
            (operand_audit.candidate_audits[0], rebound_audit),
        )
        with self.assertRaises(HardConstraintOperandIntegrityError):
            self.evaluate(operand_audit)

    def test_inconsistent_candidate_evidence_is_rejected(self) -> None:
        operand_audit = self.audited(("31/02/2026",))
        wrong = EvidenceReferenceV2(
            reference_namespace=CANDIDATE_RECORD_EVIDENCE_NAMESPACE,
            reference_id="different-candidate",
            source_record_version=(
                operand_audit.candidate_audits[0].candidate.record_version
            ),
        )
        with patch.object(
            stage_module,
            "_candidate_evidence_reference",
            return_value=wrong,
        ):
            with self.assertRaises(PurchaseDateSourceBindingError):
                self.evaluate(operand_audit)

    def test_non_purchase_date_operand_audit_is_rejected(self) -> None:
        operand_audit = self.audited(field_name=ReceiptFieldName.STORE_NAME)
        with self.assertRaises(PurchaseDateSourceBindingError):
            self.evaluate(operand_audit)

    def test_middle_candidate_compatibility_error_fails_whole_stage(self) -> None:
        operand_audit = self.audited(("31/02/2026", "10/11/2026"))
        middle = operand_audit.candidate_audits[1]

        def evaluate_or_fail(**kwargs):
            if kwargs["candidate_audit"] is middle:
                raise PurchaseDateParserCompatibilityError(
                    "synthetic middle-candidate compatibility failure"
                )
            return evaluate_purchase_date_calendar_validity_v0(**kwargs)

        with patch.object(
            stage_module,
            "_evaluate_purchase_date_calendar_validity_v0",
            side_effect=evaluate_or_fail,
        ) as evaluator, patch.object(
            stage_module,
            "_build_source_bound_constraint_result_v2",
            wraps=build_source_bound_constraint_result_v2,
        ) as factory:
            with self.assertRaises(PurchaseDateParserCompatibilityError):
                self.evaluate(operand_audit)

        self.assertEqual(2, evaluator.call_count)
        self.assertEqual(1, factory.call_count)

    def test_invalid_and_colliding_ids_are_rejected_preflight(self) -> None:
        for helper_name, replacement in (
            ("_rule_outcome_id", ""),
            ("_constraint_result_id", ""),
            ("_rule_outcome_id", "collision"),
            ("_constraint_result_id", "collision"),
        ):
            with self.subTest(helper=helper_name, replacement=replacement):
                operand_audit = self.audited(("31/02/2026",))
                with patch.object(
                    stage_module,
                    helper_name,
                    return_value=replacement,
                ), patch.object(
                    stage_module,
                    "_evaluate_purchase_date_calendar_validity_v0",
                    wraps=evaluate_purchase_date_calendar_validity_v0,
                ) as evaluator:
                    with self.assertRaises(PurchaseDateIntegrityError):
                        self.evaluate(operand_audit)
                self.assertEqual(0, evaluator.call_count)

    def test_theta_mismatch_is_rejected_without_rebinding(self) -> None:
        operand_audit = self.audited()
        profile = self.profile(operand_audit)
        mismatched_theta = replace(
            profile.theta_a_reference,
            configuration_id="different-theta-a",
        )
        mismatched_profile = replace(
            profile,
            theta_a_reference=mismatched_theta,
        )
        with self.assertRaises(PurchaseDateConfigurationError):
            self.evaluate(operand_audit, mismatched_profile)

    def test_stage_does_not_rerun_upstream_pipeline(self) -> None:
        operand_audit = self.audited(("31/02/2026",))
        targets = (
            "pipeline.ocr_adapter.adapt_paddleocr_result",
            "pipeline.layout_b2.extract_b2",
            "pipeline.baseline_b3.apply_b3",
            "pipeline.proposed.adapter.adapt_b2_to_proposed",
            "pipeline.proposed.suspicion.detect_suspicion",
            "pipeline.proposed.candidate_generation.generate_candidate_drafts",
            "pipeline.proposed.candidate_deduplication.deduplicate_candidate_drafts",
            "pipeline.proposed.candidate_identity.prepare_candidate_identities",
            "pipeline.proposed.candidate_provenance.materialize_altered_provenance",
            "pipeline.proposed.candidate_ranking.compute_preliminary_candidate_ranking",
            "pipeline.proposed.candidate_limiting.apply_candidate_limit",
            "pipeline.proposed.candidate_finalization."
            "materialize_ranked_candidate_records",
            "pipeline.proposed.hard_constraint_context.prepare_hard_constraint_inputs",
            "pipeline.proposed.hard_constraint_operands.audit_hard_constraint_operands",
        )
        patches = [
            patch(target, side_effect=AssertionError(target)) for target in targets
        ]
        started = [item.start() for item in patches]
        self.addCleanup(lambda: [item.stop() for item in reversed(patches)])
        results = self.evaluate(operand_audit)
        self.assertEqual(len(targets), len(started))
        self.assertEqual(len(operand_audit.candidate_audits), len(results))

    def test_stage_does_not_mutate_c0_or_canonical_evidence(self) -> None:
        operand_audit = self.audited(("31/02/2026",))
        audits = operand_audit.candidate_audits
        candidates = operand_audit.hard_constraint_input.candidates
        c0 = candidates[0]
        c0_snapshot = (
            c0.candidate_id,
            c0.value,
            c0.c0_candidate_id,
            c0.provenance,
        )
        source_tokens = operand_audit.hard_constraint_input.source_tokens

        self.evaluate(operand_audit)

        self.assertIs(audits, operand_audit.candidate_audits)
        self.assertIs(candidates, operand_audit.hard_constraint_input.candidates)
        self.assertIs(c0, operand_audit.hard_constraint_input.candidates[0])
        self.assertEqual(
            c0_snapshot,
            (c0.candidate_id, c0.value, c0.c0_candidate_id, c0.provenance),
        )
        self.assertTrue(
            all(
                before is after
                for before, after in zip(
                    source_tokens,
                    operand_audit.hard_constraint_input.source_tokens,
                    strict=True,
                )
            )
        )
        operand_audit.__post_init__()


if __name__ == "__main__":
    unittest.main()
