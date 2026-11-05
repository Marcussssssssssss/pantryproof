"""Synthetic tests for purchase-date seven-slot feature construction V0."""

from __future__ import annotations

import inspect
import unittest
from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch

import pipeline.proposed.backend_observational_path as path_module
import pipeline.proposed.feature_construction as feature_module
from pipeline.proposed.contracts import FEATURE_SLOT_ORDER, CandidateRole, FeatureSlot
from pipeline.proposed.feature_construction import (
    FeatureConstructionConfigurationError,
    FeatureConstructionIntegrityError,
    FeatureSlotValueV0,
    FeatureValueAvailabilityV0,
    FeatureValueReasonV0,
    construct_purchase_date_features_v0,
)
from pipeline.proposed.hard_constraint_contracts_v2 import (
    ConstraintAggregateStateV2,
)
import test_proposed_backend_observational_path as backend_fixtures
from test_proposed_hard_constraint_operands import _LayoutCandidateFixture


class _ConfidenceLayoutFixture(_LayoutCandidateFixture):
    def __init__(self, confidence: float | None) -> None:
        super().__init__(
            "feature-construction-confidence-receipt",
            (
                ("store", "PANTRYPROOF TEST MART", 20, 0, 180),
                ("date", "DATE: 14/10/2026", 10, 20, 165),
                ("item", "MILK 2 5.50 11.00", 10, 45, 260),
                ("total", "TOTAL 11.00", 170, 80, 155),
            ),
        )
        self.confidence = confidence

    def token(self, *args, **kwargs):
        return replace(
            super().token(*args, **kwargs),
            raw_confidence=self.confidence,
        )


class _TokenConfidenceLayoutFixture(_LayoutCandidateFixture):
    def __init__(self, confidences: dict[str, float | None]) -> None:
        super().__init__(
            "feature-construction-token-confidence-receipt",
            (
                ("store", "PANTRYPROOF TEST MART", 20, 0, 180),
                ("date-day", "14", 10, 20, 15),
                ("date-month", "OCT", 30, 20, 30),
                ("date-year", "2026", 65, 20, 40),
                ("item", "MILK 2 5.50 11.00", 10, 45, 260),
                ("total", "TOTAL 11.00", 170, 80, 155),
            ),
        )
        self.confidences = confidences

    def token(self, token_id, *args, **kwargs):
        token = super().token(token_id, *args, **kwargs)
        return replace(
            token,
            raw_confidence=self.confidences.get(token_id, token.raw_confidence),
        )


class ProposedFeatureConstructionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.backend = backend_fixtures.ProposedBackendObservationalPathTests(
            methodName="runTest"
        )
        self.backend.setUp()

    def graph(
        self,
        *,
        synthetic_values: tuple[str, ...] | None = None,
        candidate_limit: int = 3,
    ):
        inputs = self.backend.inputs(
            synthetic_values=synthetic_values,
            candidate_limit=candidate_limit,
        )
        operand_audit, constraint_results = (
            path_module._execute_purchase_date_observational_graph_v0(**inputs)
        )
        return inputs, operand_audit, constraint_results

    @staticmethod
    def construct(operand_audit, constraint_results):
        return construct_purchase_date_features_v0(
            operand_audit=operand_audit,
            constraint_results=constraint_results,
        )

    @staticmethod
    def rebound_result(result, theta_a):
        profile = replace(
            result.rule_profile_reference,
            theta_a_reference=theta_a,
        )
        outcomes = tuple(
            replace(
                outcome,
                theta_a_reference=theta_a,
                rule_profile_reference=profile,
            )
            for outcome in result.rule_outcomes
        )
        return replace(
            result,
            theta_a_reference=theta_a,
            rule_profile_reference=profile,
            rule_outcomes=outcomes,
        )

    def test_public_constructor_is_exact_and_keyword_only(self) -> None:
        signature = inspect.signature(construct_purchase_date_features_v0)
        self.assertEqual(
            ("operand_audit", "constraint_results"),
            tuple(signature.parameters),
        )
        self.assertTrue(
            all(
                parameter.kind is inspect.Parameter.KEYWORD_ONLY
                for parameter in signature.parameters.values()
            )
        )
        self.assertIn(
            "construct_purchase_date_features_v0",
            feature_module.__all__,
        )

    def test_c0_has_exact_seven_slot_values_types_and_masks(self) -> None:
        _, operand_audit, constraint_results = self.graph(candidate_limit=2)
        result = self.construct(operand_audit, constraint_results)

        self.assertEqual(1, len(result.candidate_features))
        vector = result.candidate_features[0]
        self.assertEqual(FEATURE_SLOT_ORDER, vector.feature_slots)
        self.assertEqual(
            (
                Decimal("0.91"),
                None,
                Decimal("1"),
                None,
                None,
                "NOT_APPLICABLE",
                "NOT_APPLICABLE",
            ),
            vector.feature_values,
        )
        self.assertEqual(
            (False, True, False, True, True, False, False),
            vector.missingness_mask,
        )
        self.assertEqual(
            (
                FeatureValueAvailabilityV0.AVAILABLE,
                FeatureValueAvailabilityV0.MISSING,
                FeatureValueAvailabilityV0.AVAILABLE,
                FeatureValueAvailabilityV0.MISSING,
                FeatureValueAvailabilityV0.MISSING,
                FeatureValueAvailabilityV0.NOT_APPLICABLE,
                FeatureValueAvailabilityV0.NOT_APPLICABLE,
            ),
            tuple(slot.availability for slot in vector.slot_values),
        )

    def test_purchase_date_non_applicability_is_explicit_not_missing(self) -> None:
        _, operand_audit, constraint_results = self.graph(candidate_limit=2)
        vector = self.construct(operand_audit, constraint_results).candidate_features[0]
        slots = {slot.slot: slot for slot in vector.slot_values}

        arithmetic = slots[FeatureSlot.ARITHMETIC_SUPPORT]
        price = slots[FeatureSlot.PRICE_REFERENCE_SUPPORT]
        self.assertIs(
            FeatureValueReasonV0.PURCHASE_DATE_ARITHMETIC_NOT_APPLICABLE,
            arithmetic.reason,
        )
        self.assertIs(
            FeatureValueReasonV0.PURCHASE_DATE_PRICE_NOT_APPLICABLE,
            price.reason,
        )
        self.assertFalse(arithmetic.is_missing)
        self.assertFalse(price.is_missing)

    def test_provenance_is_truthful_and_missing_resources_are_not_invented(self) -> None:
        _, operand_audit, constraint_results = self.graph(candidate_limit=2)
        vector = self.construct(operand_audit, constraint_results).candidate_features[0]
        slots = {slot.slot: slot for slot in vector.slot_values}
        method = operand_audit.hard_constraint_input.method_ready_field
        target = operand_audit.candidate_audits[0].target_field

        self.assertEqual(
            method.source_token_ids,
            slots[FeatureSlot.OCR_EVIDENCE].provenance_references,
        )
        self.assertIn(
            target.field_id,
            slots[FeatureSlot.EXTRACTOR_EVIDENCE].provenance_references,
        )
        self.assertIn(
            target.field_id,
            slots[FeatureSlot.LAYOUT_AGREEMENT].provenance_references,
        )
        self.assertEqual(
            (),
            slots[FeatureSlot.RETAILER_SUPPORT].provenance_references,
        )
        all_references = {
            reference
            for slot in vector.slot_values
            for reference in slot.provenance_references
        }
        self.assertFalse(
            any("retailer-snapshot" in value or "price-snapshot" in value for value in all_references)
        )

    def test_missing_referenced_ocr_score_makes_q_o_missing(self) -> None:
        fixture = _ConfidenceLayoutFixture(None)
        with patch.object(self.backend.integration, "fixture", return_value=fixture):
            _, operand_audit, constraint_results = self.graph(candidate_limit=2)
        vector = self.construct(operand_audit, constraint_results).candidate_features[0]
        q_o = vector.slot_values[0]

        self.assertIsNone(q_o.value)
        self.assertTrue(q_o.is_missing)
        self.assertIs(
            FeatureValueReasonV0.OCR_CONFIDENCE_MISSING,
            q_o.reason,
        )

    def test_ocr_feature_uses_minimum_of_differing_referenced_scores(self) -> None:
        fixture = _TokenConfidenceLayoutFixture(
            {"date-day": 0.96, "date-month": 0.72, "date-year": 0.88}
        )
        with patch.object(self.backend.integration, "fixture", return_value=fixture):
            _, operand_audit, constraint_results = self.graph(candidate_limit=2)
        vector = self.construct(operand_audit, constraint_results).candidate_features[0]
        q_o = vector.slot_values[0]

        self.assertEqual(Decimal("0.72"), q_o.value)
        self.assertEqual(
            ("date-day", "date-month", "date-year"),
            q_o.provenance_references,
        )

    def test_one_missing_ocr_score_makes_whole_feature_missing(self) -> None:
        fixture = _TokenConfidenceLayoutFixture(
            {"date-day": 0.96, "date-month": None, "date-year": 0.88}
        )
        with patch.object(self.backend.integration, "fixture", return_value=fixture):
            _, operand_audit, constraint_results = self.graph(candidate_limit=2)
        q_o = self.construct(
            operand_audit, constraint_results
        ).candidate_features[0].slot_values[0]

        self.assertIsNone(q_o.value)
        self.assertIs(
            FeatureValueReasonV0.OCR_CONFIDENCE_MISSING,
            q_o.reason,
        )

    def test_b2_confidence_stays_missing_without_ocr_substitution(self) -> None:
        _, operand_audit, constraint_results = self.graph(candidate_limit=2)
        vector = self.construct(operand_audit, constraint_results).candidate_features[0]
        q_o, q_e = vector.slot_values[:2]

        self.assertEqual(Decimal("0.91"), q_o.value)
        self.assertIsNone(q_e.value)
        self.assertIs(
            FeatureValueReasonV0.EXTRACTOR_CONFIDENCE_MISSING,
            q_e.reason,
        )

    def test_out_of_range_and_nonfinite_present_confidence_is_rejected(self) -> None:
        for value in (
            Decimal("-0.01"),
            Decimal("1.01"),
            Decimal("NaN"),
            float("inf"),
            float("-inf"),
            True,
        ):
            with self.subTest(value=value), self.assertRaises(
                FeatureConstructionIntegrityError
            ):
                feature_module._decimal_confidence(value, "synthetic-token")
        self.assertEqual(
            Decimal("0"),
            feature_module._decimal_confidence(0.0, "lower-bound"),
        )
        self.assertEqual(
            Decimal("1"),
            feature_module._decimal_confidence(1.0, "upper-bound"),
        )

    def test_feature_slot_reason_requires_typed_reason_code(self) -> None:
        with self.assertRaises(TypeError):
            FeatureSlotValueV0(
                slot=FeatureSlot.OCR_EVIDENCE,
                value=None,
                availability=FeatureValueAvailabilityV0.MISSING,
                provenance_references=("synthetic-token",),
                reason="OCR_CONFIDENCE_MISSING",
            )

    def test_nonfinite_mutated_source_fails_whole_construction(self) -> None:
        _, operand_audit, constraint_results = self.graph(candidate_limit=2)
        token = operand_audit.hard_constraint_input.method_ready_field.source_tokens[0]
        object.__setattr__(token, "raw_confidence", float("inf"))

        with self.assertRaises(FeatureConstructionIntegrityError):
            self.construct(operand_audit, constraint_results)

    def test_altered_lexical_feature_reuses_exact_stored_similarity(self) -> None:
        _, operand_audit, constraint_results = self.graph(
            synthetic_values=("2026-10-25",),
            candidate_limit=2,
        )
        result = self.construct(operand_audit, constraint_results)
        self.assertEqual(2, len(result.candidate_features))
        altered = result.candidate_features[1]
        rank = altered.candidate.preliminary_rank
        self.assertIsNotNone(rank)
        self.assertIs(
            rank.normalized_edit_similarity,
            altered.slot_values[2].value,
        )
        self.assertIn(
            altered.candidate.candidate_id,
            altered.slot_values[2].provenance_references,
        )
        self.assertNotEqual(Decimal("1"), altered.slot_values[2].value)

    def test_only_eligible_candidates_receive_vectors(self) -> None:
        _, operand_audit, constraint_results = self.graph(
            synthetic_values=("31/02/2026", "10/11/2026"),
            candidate_limit=3,
        )
        result = self.construct(operand_audit, constraint_results)

        self.assertEqual(3, len(result.constraint_results))
        self.assertTrue(
            all(
                observed is original
                for observed, original in zip(
                    result.constraint_results,
                    constraint_results,
                    strict=True,
                )
            )
        )
        self.assertEqual(1, len(result.candidate_features))
        self.assertIs(
            ConstraintAggregateStateV2.ELIGIBLE,
            result.candidate_features[0].constraint_result.aggregate_state,
        )
        self.assertEqual(
            {
                ConstraintAggregateStateV2.ELIGIBLE,
                ConstraintAggregateStateV2.CONSTRAINT_REJECTED,
                ConstraintAggregateStateV2.CONSTRAINT_UNAVAILABLE,
            },
            {item.aggregate_state for item in result.constraint_results},
        )

    def test_permanent_c0_and_d3_source_identity_are_exact(self) -> None:
        _, operand_audit, constraint_results = self.graph(
            synthetic_values=("2026-10-25",),
            candidate_limit=2,
        )
        result = self.construct(operand_audit, constraint_results)
        c0 = operand_audit.candidate_audits[0].candidate

        self.assertIs(result.operand_audit, operand_audit)
        self.assertIs(result.input_readiness.operand_audit, operand_audit)
        self.assertIs(CandidateRole.ORIGINAL, c0.role)
        for vector in result.candidate_features:
            self.assertIs(vector.operand_audit, operand_audit)
            self.assertIs(vector.candidate, vector.candidate_audit.candidate)
            self.assertIs(vector.constraint_result.c0_candidate, c0)

    def test_complete_theta_a_consistency_is_preserved(self) -> None:
        inputs, operand_audit, constraint_results = self.graph(candidate_limit=2)
        result = self.construct(operand_audit, constraint_results)
        theta_a = inputs["suspicion_result"].theta_a_ref

        self.assertEqual(theta_a, operand_audit.hard_constraint_input.theta_a_ref)
        self.assertTrue(
            all(vector.theta_a_reference == theta_a for vector in result.candidate_features)
        )
        self.assertTrue(
            all(item.theta_a_reference == theta_a for item in result.constraint_results)
        )

    def test_distinct_value_equal_theta_reference_remains_compatible(self) -> None:
        _, operand_audit, constraint_results = self.graph(candidate_limit=2)
        equal_theta = replace(constraint_results[0].theta_a_reference)
        rebound = self.rebound_result(constraint_results[0], equal_theta)

        result = self.construct(operand_audit, (rebound,))
        self.assertEqual(1, len(result.candidate_features))
        self.assertIs(result.constraint_results[0], rebound)

    def test_theta_a_mismatch_is_rejected_as_configuration_failure(self) -> None:
        _, operand_audit, constraint_results = self.graph(candidate_limit=2)
        different_theta = replace(
            constraint_results[0].theta_a_reference,
            configuration_id="different-feature-theta-a",
        )
        rebound = self.rebound_result(constraint_results[0], different_theta)

        with self.assertRaises(FeatureConstructionConfigurationError):
            self.construct(operand_audit, (rebound,))

    def test_missing_extra_duplicate_and_reordered_results_are_rejected(self) -> None:
        _, operand_audit, constraint_results = self.graph(
            synthetic_values=("31/02/2026", "10/11/2026"),
            candidate_limit=3,
        )
        invalid = {
            "missing": constraint_results[:-1],
            "extra": constraint_results + (constraint_results[-1],),
            "duplicate": (
                constraint_results[0],
                constraint_results[0],
                constraint_results[2],
            ),
            "reordered": tuple(reversed(constraint_results)),
        }
        for name, records in invalid.items():
            with self.subTest(name=name), self.assertRaises(
                FeatureConstructionIntegrityError
            ):
                self.construct(operand_audit, records)

    def test_value_equal_substituted_candidate_is_rejected(self) -> None:
        _, operand_audit, constraint_results = self.graph(candidate_limit=2)
        original = constraint_results[0]
        copied_candidate = replace(original.candidate)
        copied_outcomes = tuple(
            replace(
                outcome,
                candidate=copied_candidate,
                c0_candidate=copied_candidate,
            )
            for outcome in original.rule_outcomes
        )
        substituted = replace(
            original,
            candidate=copied_candidate,
            c0_candidate=copied_candidate,
            rule_outcomes=copied_outcomes,
        )
        self.assertEqual(original.candidate, substituted.candidate)
        self.assertIsNot(original.candidate, substituted.candidate)

        with self.assertRaises(FeatureConstructionIntegrityError):
            self.construct(operand_audit, (substituted,))

    def test_value_equal_substituted_c0_is_rejected(self) -> None:
        _, operand_audit, constraint_results = self.graph(
            synthetic_values=("2026-10-25",),
            candidate_limit=2,
        )
        altered = constraint_results[1]
        copied_c0 = replace(altered.c0_candidate)
        copied_outcomes = tuple(
            replace(outcome, c0_candidate=copied_c0)
            for outcome in altered.rule_outcomes
        )
        substituted = replace(
            altered,
            c0_candidate=copied_c0,
            rule_outcomes=copied_outcomes,
        )
        records = (constraint_results[0], substituted)

        with self.assertRaises(FeatureConstructionIntegrityError):
            self.construct(operand_audit, records)

    def test_nested_value_equal_candidate_or_c0_substitution_is_rejected(self) -> None:
        _, operand_audit, constraint_results = self.graph(
            synthetic_values=("2026-10-25",),
            candidate_limit=2,
        )
        altered = constraint_results[1]
        copied_candidate = replace(altered.candidate)
        copied_c0 = replace(altered.c0_candidate)
        substitutions = {
            "candidate": replace(
                altered.rule_outcomes[0], candidate=copied_candidate
            ),
            "c0": replace(altered.rule_outcomes[0], c0_candidate=copied_c0),
        }
        for name, outcome in substitutions.items():
            substituted = replace(altered, rule_outcomes=(outcome,))
            self.assertEqual(altered.candidate, substituted.candidate)
            self.assertIs(altered.candidate, substituted.candidate)
            with self.subTest(name=name), self.assertRaises(
                FeatureConstructionIntegrityError
            ):
                self.construct(
                    operand_audit,
                    (constraint_results[0], substituted),
                )

    def test_repeated_construction_is_deterministic_and_does_not_mutate_inputs(self) -> None:
        _, operand_audit, constraint_results = self.graph(
            synthetic_values=("2026-10-25",),
            candidate_limit=2,
        )
        before = (repr(operand_audit), repr(constraint_results))
        first = self.construct(operand_audit, constraint_results)
        second = self.construct(operand_audit, constraint_results)

        self.assertEqual(first, second)
        self.assertEqual(before, (repr(operand_audit), repr(constraint_results)))
        operand_audit.__post_init__()
        for item in constraint_results:
            item.__post_init__()

    def test_reconstruction_rejects_slot_and_result_reference_tampering(self) -> None:
        _, operand_audit, constraint_results = self.graph(candidate_limit=2)
        result = self.construct(operand_audit, constraint_results)
        vector = result.candidate_features[0]
        altered_slot = replace(vector.slot_values[0], value=Decimal("0.50"))
        object.__setattr__(
            vector,
            "slot_values",
            (altered_slot, *vector.slot_values[1:]),
        )
        with self.assertRaises(FeatureConstructionIntegrityError):
            vector.__post_init__()

        clean = self.construct(operand_audit, constraint_results)
        copied_result = replace(clean.constraint_results[0])
        object.__setattr__(clean, "constraint_results", (copied_result,))
        with self.assertRaises(FeatureConstructionIntegrityError):
            clean.__post_init__()

    def test_direct_construction_does_not_rerun_any_upstream_stage(self) -> None:
        _, operand_audit, constraint_results = self.graph(candidate_limit=2)
        forbidden = AssertionError("feature construction must not rerun upstream")
        with patch(
            "pipeline.ocr_adapter.adapt_paddleocr_result",
            side_effect=forbidden,
        ), patch(
            "pipeline.layout_b2.extract_b2",
            side_effect=forbidden,
        ), patch(
            "pipeline.baseline_b3.apply_b3",
            side_effect=forbidden,
        ), patch.object(
            path_module,
            "_generate_candidate_drafts",
            side_effect=forbidden,
        ), patch.object(
            path_module,
            "_audit_hard_constraint_operands",
            side_effect=forbidden,
        ), patch.object(
            path_module,
            "_evaluate_purchase_date_constraint_stage_v0",
            side_effect=forbidden,
        ):
            result = self.construct(operand_audit, constraint_results)

        self.assertEqual(1, len(result.candidate_features))

    def test_failure_is_atomic_and_exposes_no_partial_result(self) -> None:
        _, operand_audit, constraint_results = self.graph(
            synthetic_values=("31/02/2026", "10/11/2026"),
            candidate_limit=3,
        )
        produced = None
        with self.assertRaises(FeatureConstructionIntegrityError):
            produced = self.construct(operand_audit, constraint_results[:-1])
        self.assertIsNone(produced)


if __name__ == "__main__":
    unittest.main()
