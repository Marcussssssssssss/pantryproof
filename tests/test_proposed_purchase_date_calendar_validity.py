"""Synthetic tests for PURCHASE_DATE_CALENDAR_VALIDITY_V0."""

from __future__ import annotations

import subprocess
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from pipeline import baseline_b3
from pipeline.contracts import ReceiptFieldName
from pipeline.proposed.contracts import (
    CandidateSourceKind,
    ConfigurationKind,
    ConfigurationRefV1,
    ConfigurationState,
)
from pipeline.proposed.hard_constraint_contracts_v2 import (
    ConstraintAggregateStateV2,
    EvidenceReferenceV2,
    HardConstraintProfileRefV2,
    HardConstraintResourceRefV2,
    HardConstraintRuleSpecV2,
    RuleEvidenceAvailabilityV2,
    RuleOutcomeReasonKindV2,
    RuleOutcomeStateV2,
    RuleRequirementV2,
    build_source_bound_constraint_result_v2,
)
from pipeline.proposed.purchase_date_calendar_validity import (
    AMBIGUOUS_DATE_INTERPRETATION,
    AMBIGUOUS_DATE_INTERPRETATION_DETAIL,
    APPROVED_B3_RULESET_ID,
    APPROVED_B3_SOURCE_BLOB,
    CALENDAR_DATE_IMPOSSIBLE,
    CALENDAR_DATE_IMPOSSIBLE_DETAIL,
    CANDIDATE_RECORD_EVIDENCE_NAMESPACE,
    DATE_FORMAT_UNSUPPORTED,
    DATE_FORMAT_UNSUPPORTED_DETAIL,
    PURCHASE_DATE_APPLICABILITY_REFERENCE,
    PURCHASE_DATE_CALENDAR_VALIDITY_COMPONENT_VERSION,
    PURCHASE_DATE_CALENDAR_VALIDITY_RULE_ID,
    PURCHASE_DATE_CALENDAR_VALIDITY_RULE_VERSION,
    PURCHASE_DATE_GRAMMAR_REFERENCE,
    PURCHASE_DATE_PROFILE_ID,
    PURCHASE_DATE_PROFILE_VERSION,
    PurchaseDateConfigurationError,
    PurchaseDateEvaluationError,
    PurchaseDateIntegrityError,
    PurchaseDateParserCompatibilityError,
    PurchaseDateSourceBindingError,
    evaluate_purchase_date_calendar_validity_v0,
    recognizes_purchase_date_grammar_v0,
)
import test_proposed_hard_constraint_operands as operand_fixtures


class ProposedPurchaseDateCalendarValidityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.upstream = operand_fixtures.ProposedHardConstraintOperandTests(
            methodName="runTest"
        )
        self.upstream.setUp()

    @staticmethod
    def altered_candidate_fixture():
        return operand_fixtures._LayoutCandidateFixture(
            "g2a-calendar-validity-receipt",
            (
                ("store", "PANTRYPROOF TEST MART", 20, 0, 180),
                ("date", "DATE: 14/10/2026", 10, 20, 165),
                ("item", "MILK 2 5.50 11.00", 10, 45, 260),
                ("total", "TOTAL 11.00", 170, 80, 155),
            ),
        )

    def audited(self, value: str | None = None):
        specs = (
            ()
            if value is None
            else (("g2a", CandidateSourceKind.GENERIC_NORMALIZATION, value),)
        )
        aggregate = self.upstream.audited(
            specs,
            fixture=None if value is None else self.altered_candidate_fixture(),
            field_name=ReceiptFieldName.PURCHASE_DATE,
        )
        if value is None:
            candidate_audit = aggregate.candidate_audits[0]
        else:
            candidate_audit = next(
                item for item in aggregate.candidate_audits if item.candidate.value == value
            )
        return aggregate, candidate_audit

    @staticmethod
    def profile(aggregate) -> HardConstraintProfileRefV2:
        rule = HardConstraintRuleSpecV2(
            rule_id=PURCHASE_DATE_CALENDAR_VALIDITY_RULE_ID,
            rule_version=PURCHASE_DATE_CALENDAR_VALIDITY_RULE_VERSION,
            position=0,
            requirement=RuleRequirementV2.MANDATORY,
            applicability_reference=PURCHASE_DATE_APPLICABILITY_REFERENCE,
        )
        return HardConstraintProfileRefV2(
            profile_id=PURCHASE_DATE_PROFILE_ID,
            profile_version=PURCHASE_DATE_PROFILE_VERSION,
            theta_a_reference=aggregate.hard_constraint_input.theta_a_ref,
            ordered_rule_specs=(rule,),
        )

    @staticmethod
    def evidence(candidate_audit) -> EvidenceReferenceV2:
        candidate = candidate_audit.candidate
        return EvidenceReferenceV2(
            reference_namespace=CANDIDATE_RECORD_EVIDENCE_NAMESPACE,
            reference_id=candidate.candidate_id,
            source_record_version=candidate.record_version,
        )

    def evaluate(self, value: str | None = None, **changes):
        arguments, aggregate, candidate_audit = self.arguments(value, **changes)
        return (
            evaluate_purchase_date_calendar_validity_v0(**arguments),
            aggregate,
            candidate_audit,
        )

    def arguments(self, value: str | None = None, **changes):
        aggregate, candidate_audit = self.audited(value)
        arguments = {
            "rule_outcome_id": "synthetic:g2a:outcome",
            "operand_audit": aggregate,
            "candidate_audit": candidate_audit,
            "rule_profile_reference": self.profile(aggregate),
            "grammar_reference": PURCHASE_DATE_GRAMMAR_REFERENCE,
            "candidate_evidence_reference": self.evidence(candidate_audit),
        }
        arguments.update(changes)
        return arguments, aggregate, candidate_audit

    def test_public_import_and_pinned_b3_dependency(self) -> None:
        self.assertEqual(
            "purchase-date-calendar-validity-v0",
            PURCHASE_DATE_CALENDAR_VALIDITY_COMPONENT_VERSION,
        )
        self.assertEqual(APPROVED_B3_RULESET_ID, baseline_b3.EXTRACTOR_VERSION)
        repository = Path(__file__).resolve().parents[1]
        observed = subprocess.run(
            ["git", "hash-object", "pipeline/baseline_b3.py"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(APPROVED_B3_SOURCE_BLOB, observed)

    def test_passes_exactly_one_distinct_valid_interpretation(self) -> None:
        for value in (
            "2026-10-13",
            "13/10/2026",
            "10/13/2026",
            "11/11/2026",
            "13 OCT 2026",
            "October 13, 2026",
            "29/02/2024",
        ):
            with self.subTest(value=value):
                outcome, _, _ = self.evaluate(value)
                self.assertIs(RuleOutcomeStateV2.PASS, outcome.state)
                self.assertTrue(outcome.attempted)
                self.assertIs(
                    RuleEvidenceAvailabilityV2.AVAILABLE,
                    outcome.evidence_availability,
                )
                self.assertIsNone(outcome.outcome_reason_kind)
                self.assertIsNone(outcome.outcome_code)
                self.assertIsNone(outcome.outcome_detail)

    def test_fails_recognized_calendar_impossible_literals(self) -> None:
        for value in (
            "31/02/2026",
            "29/02/2025",
            "2026-02-30",
            "31 APRIL 2026",
        ):
            with self.subTest(value=value):
                outcome, _, _ = self.evaluate(value)
                self.assertIs(RuleOutcomeStateV2.FAIL, outcome.state)
                self.assertTrue(outcome.attempted)
                self.assertIs(
                    RuleEvidenceAvailabilityV2.AVAILABLE,
                    outcome.evidence_availability,
                )
                self.assertIs(
                    RuleOutcomeReasonKindV2.FAILURE,
                    outcome.outcome_reason_kind,
                )
                self.assertEqual(CALENDAR_DATE_IMPOSSIBLE, outcome.outcome_code)
                self.assertEqual(
                    CALENDAR_DATE_IMPOSSIBLE_DETAIL,
                    outcome.outcome_detail,
                )

    def test_ambiguous_date_is_unavailable(self) -> None:
        outcome, _, _ = self.evaluate("10/11/2026")
        self.assertIs(RuleOutcomeStateV2.UNAVAILABLE, outcome.state)
        self.assertTrue(outcome.attempted)
        self.assertIs(
            RuleEvidenceAvailabilityV2.UNAVAILABLE,
            outcome.evidence_availability,
        )
        self.assertIs(
            RuleOutcomeReasonKindV2.UNAVAILABILITY,
            outcome.outcome_reason_kind,
        )
        self.assertEqual(AMBIGUOUS_DATE_INTERPRETATION, outcome.outcome_code)
        self.assertEqual(
            AMBIGUOUS_DATE_INTERPRETATION_DETAIL,
            outcome.outcome_detail,
        )

    def test_unsupported_and_malformed_literals_are_unavailable(self) -> None:
        for value in (
            "13.10.2026",
            "13-10/2026",
            "13/10/26",
            "13 FOO 2026",
            "not-a-date",
            "---",
        ):
            with self.subTest(value=value):
                outcome, _, _ = self.evaluate(value)
                self.assertIs(RuleOutcomeStateV2.UNAVAILABLE, outcome.state)
                self.assertTrue(outcome.attempted)
                self.assertIs(
                    RuleEvidenceAvailabilityV2.UNAVAILABLE,
                    outcome.evidence_availability,
                )
                self.assertIs(
                    RuleOutcomeReasonKindV2.UNAVAILABILITY,
                    outcome.outcome_reason_kind,
                )
                self.assertEqual(DATE_FORMAT_UNSUPPORTED, outcome.outcome_code)
                self.assertEqual(DATE_FORMAT_UNSUPPORTED_DETAIL, outcome.outcome_detail)

    def test_unicode_behavior_matches_approved_b3_semantics(self) -> None:
        for value in (
            "２０２６-１０-１３",
            "١٣/١٠/٢٠٢٦",
            "13\u00a0OCT\t2026",
            "13 ſEP 2026",
        ):
            with self.subTest(value=value):
                self.assertTrue(recognizes_purchase_date_grammar_v0(value))
                outcome, _, _ = self.evaluate(value)
                self.assertIs(RuleOutcomeStateV2.PASS, outcome.state)

    def test_b3_invalid_is_not_directly_mapped_to_fail(self) -> None:
        unsupported, _, _ = self.evaluate("13.10.2026")
        impossible, _, _ = self.evaluate("31/02/2026")
        self.assertIs(RuleOutcomeStateV2.UNAVAILABLE, unsupported.state)
        self.assertIs(RuleOutcomeStateV2.FAIL, impossible.state)

    def test_outcome_preserves_exact_candidate_c0_theta_and_evidence(self) -> None:
        outcome, aggregate, candidate_audit = self.evaluate("2026-10-13")
        self.assertIs(candidate_audit.candidate, outcome.candidate)
        self.assertIs(aggregate.hard_constraint_input.candidates[0], outcome.c0_candidate)
        self.assertEqual(
            aggregate.hard_constraint_input.theta_a_ref,
            outcome.theta_a_reference,
        )
        self.assertEqual((self.evidence(candidate_audit),), outcome.evidence_references)
        self.assertEqual("14/10/2026", outcome.c0_candidate.value)

    def test_existing_source_bound_factory_accepts_exact_outcome(self) -> None:
        outcome, aggregate, candidate_audit = self.evaluate("2026-10-13")
        result = build_source_bound_constraint_result_v2(
            constraint_result_id="synthetic:g2a:constraint-result",
            operand_audit=aggregate,
            candidate_audit=candidate_audit,
            rule_profile_reference=outcome.rule_profile_reference,
            rule_outcomes=(outcome,),
        )
        self.assertIs(candidate_audit.candidate, result.candidate)
        self.assertIs(ConstraintAggregateStateV2.ELIGIBLE, result.aggregate_state)

    def test_value_equal_candidate_audit_copy_fails_source_binding(self) -> None:
        aggregate, candidate_audit = self.audited("2026-10-13")
        with self.assertRaises(PurchaseDateSourceBindingError):
            evaluate_purchase_date_calendar_validity_v0(
                rule_outcome_id="synthetic:g2a:copy",
                operand_audit=aggregate,
                candidate_audit=replace(candidate_audit),
                rule_profile_reference=self.profile(aggregate),
                grammar_reference=PURCHASE_DATE_GRAMMAR_REFERENCE,
                candidate_evidence_reference=self.evidence(candidate_audit),
            )

    def test_non_purchase_date_candidate_fails_source_binding(self) -> None:
        aggregate = self.upstream.audited(field_name=ReceiptFieldName.STORE_NAME)
        candidate_audit = aggregate.candidate_audits[0]
        with self.assertRaises(PurchaseDateSourceBindingError):
            evaluate_purchase_date_calendar_validity_v0(
                rule_outcome_id="synthetic:g2a:wrong-field",
                operand_audit=aggregate,
                candidate_audit=candidate_audit,
                rule_profile_reference=self.profile(aggregate),
                grammar_reference=PURCHASE_DATE_GRAMMAR_REFERENCE,
                candidate_evidence_reference=self.evidence(candidate_audit),
            )

    def test_candidate_evidence_namespace_id_and_version_are_exact(self) -> None:
        aggregate, candidate_audit = self.audited("2026-10-13")
        correct = self.evidence(candidate_audit)
        mutations = (
            replace(correct, reference_namespace="OTHER_NAMESPACE"),
            replace(correct, reference_id="other-candidate"),
            replace(correct, source_record_version="999"),
        )
        for evidence in mutations:
            with self.subTest(evidence=evidence):
                with self.assertRaises(PurchaseDateSourceBindingError):
                    evaluate_purchase_date_calendar_validity_v0(
                        rule_outcome_id="synthetic:g2a:bad-evidence",
                        operand_audit=aggregate,
                        candidate_audit=candidate_audit,
                        rule_profile_reference=self.profile(aggregate),
                        grammar_reference=PURCHASE_DATE_GRAMMAR_REFERENCE,
                        candidate_evidence_reference=evidence,
                    )

    def test_incompatible_profile_identifiers_are_configuration_errors(self) -> None:
        aggregate, candidate_audit = self.audited("2026-10-13")
        profile = self.profile(aggregate)
        mutations = (
            replace(profile, profile_id="other-profile"),
            replace(profile, profile_version="v999"),
            replace(
                profile,
                ordered_rule_specs=(
                    replace(profile.ordered_rule_specs[0], rule_id="OTHER_RULE"),
                ),
            ),
            replace(
                profile,
                ordered_rule_specs=(
                    replace(profile.ordered_rule_specs[0], rule_version="v999"),
                ),
            ),
            replace(
                profile,
                ordered_rule_specs=(
                    replace(
                        profile.ordered_rule_specs[0],
                        applicability_reference="OTHER_APPLICABILITY",
                    ),
                ),
            ),
        )
        for invalid_profile in mutations:
            with self.subTest(profile=invalid_profile):
                with self.assertRaises(PurchaseDateConfigurationError):
                    evaluate_purchase_date_calendar_validity_v0(
                        rule_outcome_id="synthetic:g2a:bad-profile",
                        operand_audit=aggregate,
                        candidate_audit=candidate_audit,
                        rule_profile_reference=invalid_profile,
                        grammar_reference=PURCHASE_DATE_GRAMMAR_REFERENCE,
                        candidate_evidence_reference=self.evidence(candidate_audit),
                    )

    def test_external_profile_resource_is_rejected(self) -> None:
        aggregate, candidate_audit = self.audited("2026-10-13")
        resource = HardConstraintResourceRefV2(
            resource_reference_id="synthetic:forbidden-resource",
            resource_kind="DATE_GRAMMAR",
            resource_id="synthetic-date-grammar",
            resource_version="v0",
            declared_content_reference="synthetic://date-grammar",
        )
        rule = replace(
            self.profile(aggregate).ordered_rule_specs[0],
            resource_reference_ids=(resource.resource_reference_id,),
        )
        profile = replace(
            self.profile(aggregate),
            ordered_rule_specs=(rule,),
            resource_references=(resource,),
        )
        with self.assertRaises(PurchaseDateConfigurationError):
            evaluate_purchase_date_calendar_validity_v0(
                rule_outcome_id="synthetic:g2a:resource",
                operand_audit=aggregate,
                candidate_audit=candidate_audit,
                rule_profile_reference=profile,
                grammar_reference=PURCHASE_DATE_GRAMMAR_REFERENCE,
                candidate_evidence_reference=self.evidence(candidate_audit),
            )

    def test_theta_a_mismatch_is_configuration_error(self) -> None:
        aggregate, candidate_audit = self.audited("2026-10-13")
        profile = self.profile(aggregate)
        different_theta = ConfigurationRefV1(
            kind=ConfigurationKind.THETA_A,
            configuration_id="theta-a-other",
            configuration_version="v1",
            state=ConfigurationState.READY,
            content_hash="sha256:synthetic-other",
        )
        with self.assertRaises(PurchaseDateConfigurationError):
            evaluate_purchase_date_calendar_validity_v0(
                rule_outcome_id="synthetic:g2a:theta",
                operand_audit=aggregate,
                candidate_audit=candidate_audit,
                rule_profile_reference=replace(
                    profile,
                    theta_a_reference=different_theta,
                ),
                grammar_reference=PURCHASE_DATE_GRAMMAR_REFERENCE,
                candidate_evidence_reference=self.evidence(candidate_audit),
            )

    def test_wrong_grammar_reference_is_configuration_error(self) -> None:
        with self.assertRaises(PurchaseDateConfigurationError):
            self.evaluate("2026-10-13", grammar_reference="OTHER_GRAMMAR")

    def test_incompatible_b3_ruleset_is_configuration_error(self) -> None:
        arguments, _, _ = self.arguments("2026-10-13")
        with patch.object(baseline_b3, "EXTRACTOR_VERSION", "B3-future"):
            with self.assertRaises(PurchaseDateParserCompatibilityError):
                evaluate_purchase_date_calendar_validity_v0(**arguments)

    def test_b3_grammar_drift_fails_closed(self) -> None:
        arguments, _, _ = self.arguments("13.10.2026")
        drifted = baseline_b3.DateParseResult(
            original="13.10.2026",
            state=baseline_b3.B3ParseState.VALID,
            normalized_value="2026-10-13",
            interpretations=("2026-10-13",),
        )
        with patch.object(baseline_b3, "parse_generic_date", return_value=drifted):
            with self.assertRaises(PurchaseDateParserCompatibilityError):
                evaluate_purchase_date_calendar_validity_v0(**arguments)

    def test_malformed_b3_parse_result_fails_closed(self) -> None:
        arguments, _, _ = self.arguments("2026-10-13")
        malformed = baseline_b3.DateParseResult(
            original="2026-10-13",
            state=baseline_b3.B3ParseState.VALID,
            normalized_value="2026-10-13",
            interpretations=("2026-10-13", "2026-10-13"),
        )
        with patch.object(baseline_b3, "parse_generic_date", return_value=malformed):
            with self.assertRaises(PurchaseDateParserCompatibilityError):
                evaluate_purchase_date_calendar_validity_v0(**arguments)

    def test_unexpected_parser_failure_is_typed_and_emits_no_outcome(self) -> None:
        arguments, _, _ = self.arguments("2026-10-13")
        with patch.object(
            baseline_b3,
            "parse_generic_date",
            side_effect=RuntimeError("synthetic parser failure"),
        ):
            with self.assertRaises(PurchaseDateEvaluationError):
                evaluate_purchase_date_calendar_validity_v0(**arguments)

    def test_post_construction_source_mutation_is_detected(self) -> None:
        aggregate, candidate_audit = self.audited("2026-10-13")
        object.__setattr__(candidate_audit.candidate, "record_version", "999")
        with self.assertRaises(PurchaseDateIntegrityError):
            evaluate_purchase_date_calendar_validity_v0(
                rule_outcome_id="synthetic:g2a:mutated",
                operand_audit=aggregate,
                candidate_audit=candidate_audit,
                rule_profile_reference=self.profile(aggregate),
                grammar_reference=PURCHASE_DATE_GRAMMAR_REFERENCE,
                candidate_evidence_reference=EvidenceReferenceV2(
                    reference_namespace=CANDIDATE_RECORD_EVIDENCE_NAMESPACE,
                    reference_id=candidate_audit.candidate.candidate_id,
                    source_record_version="999",
                ),
            )

    def test_repeated_evaluation_is_deterministic(self) -> None:
        aggregate, candidate_audit = self.audited("31/02/2026")
        arguments = {
            "rule_outcome_id": "synthetic:g2a:deterministic",
            "operand_audit": aggregate,
            "candidate_audit": candidate_audit,
            "rule_profile_reference": self.profile(aggregate),
            "grammar_reference": PURCHASE_DATE_GRAMMAR_REFERENCE,
            "candidate_evidence_reference": self.evidence(candidate_audit),
        }
        first = evaluate_purchase_date_calendar_validity_v0(**arguments)
        second = evaluate_purchase_date_calendar_validity_v0(**arguments)
        self.assertEqual(first, second)
        self.assertEqual(CALENDAR_DATE_IMPOSSIBLE_DETAIL, first.outcome_detail)

    def test_evaluator_never_emits_not_applicable(self) -> None:
        for value in ("2026-10-13", "31/02/2026", "10/11/2026", "bad"):
            with self.subTest(value=value):
                outcome, _, _ = self.evaluate(value)
                self.assertIsNot(RuleOutcomeStateV2.NOT_APPLICABLE, outcome.state)


if __name__ == "__main__":
    unittest.main()
