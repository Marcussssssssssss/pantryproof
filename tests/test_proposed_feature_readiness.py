"""Synthetic adversarial tests for seven-slot input readiness observation V0."""

from __future__ import annotations

import inspect
import unittest
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
from unittest.mock import patch

from pipeline.contracts import ReceiptFieldName
from pipeline.proposed.candidate_deduplication import deduplicate_candidate_drafts
from pipeline.proposed.candidate_finalization import materialize_ranked_candidate_records
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
    FEATURE_SLOT_ORDER,
    CandidateLimitStatus,
    CandidateRole,
    CandidateSourceKind,
    FeatureSlot,
)
from pipeline.proposed.feature_readiness import (
    FEATURE_READINESS_COMPONENT_VERSION,
    FEATURE_READINESS_RECORD_VERSION,
    CandidateFeatureInputObservationV0,
    FeatureInputReadinessIntegrityError,
    FeatureInputReadinessResultV0,
    FeatureSlotInputObservationV0,
    InputFactKindV0,
    InputFactObservationV0,
    InputFactPresenceV0,
    inspect_feature_input_readiness,
)
from pipeline.proposed.hard_constraint_context import prepare_hard_constraint_inputs
from pipeline.proposed.hard_constraint_operands import audit_hard_constraint_operands
from test_proposed_candidate_deduplication import _SyntheticCandidateFixture
from test_proposed_hard_constraint_operands import _LayoutCandidateFixture


GENERIC = CandidateSourceKind.GENERIC_NORMALIZATION


class _MissingOcrConfidenceFixture(_SyntheticCandidateFixture):
    def evidence(self):
        evidence = super().evidence()
        tokens = tuple(
            replace(token, raw_confidence=None)
            if token.token_id == "store"
            else token
            for token in evidence.tokens
        )
        return replace(evidence, tokens=tokens)


class ProposedFeatureInputReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = _SyntheticCandidateFixture("feature-readiness-receipt")

    @staticmethod
    def limiting_configuration(ranking, candidate_limit: int):
        return CandidateLimitingConfigurationV0(
            theta_a_ref=ranking.configuration.theta_a_ref,
            candidate_limit=candidate_limit,
            fixture_reference="synthetic:feature-readiness:test-v0",
        )

    def operand_audit(
        self,
        specs: tuple[tuple[str, CandidateSourceKind, str], ...] = (),
        *,
        candidate_limit: int = 3,
        fixture: _SyntheticCandidateFixture | None = None,
        field_name: ReceiptFieldName = ReceiptFieldName.STORE_NAME,
    ):
        selected = fixture or self.fixture
        drafts = selected.drafts(field_name=field_name, seed_specs=specs)
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
        finalization = materialize_ranked_candidate_records(
            limit_result=apply_candidate_limit(
                ranking_result=ranking,
                configuration=self.limiting_configuration(ranking, candidate_limit),
            )
        )
        context = prepare_hard_constraint_inputs(finalization_result=finalization)
        return audit_hard_constraint_operands(hard_constraint_input=context)

    def result(self, *args, **kwargs) -> FeatureInputReadinessResultV0:
        return inspect_feature_input_readiness(
            operand_audit=self.operand_audit(*args, **kwargs)
        )

    @staticmethod
    def slot(candidate, slot: FeatureSlot) -> FeatureSlotInputObservationV0:
        return next(item for item in candidate.slots if item.slot is slot)

    @staticmethod
    def facts(candidate, slot: FeatureSlot, kind: InputFactKindV0):
        return tuple(
            item
            for item in ProposedFeatureInputReadinessTests.slot(candidate, slot).facts
            if item.kind is kind
        )

    @staticmethod
    def missing_unit_fixture() -> _LayoutCandidateFixture:
        return _LayoutCandidateFixture(
            "feature-readiness-missing-unit",
            (
                ("store", "PANTRYPROOF TEST MART", 20, 0, 180),
                ("date", "DATE: 2026-10-13", 10, 20, 150),
                ("description", "BREAD", 10, 45, 55),
                ("line-total", "8.40", 220, 45, 45),
                ("total", "TOTAL 8.40", 140, 75, 125),
            ),
        )

    @staticmethod
    def unresolved_fixture() -> _LayoutCandidateFixture:
        return _LayoutCandidateFixture(
            "feature-readiness-unresolved",
            (
                ("store", "PANTRYPROOF TEST MART", 20, 0, 180),
                ("date", "DATE: 2026-10-13", 10, 20, 150),
                ("whole-item", "MILK 2 5.50 11.00", 10, 45, 255),
                ("total", "TOTAL 11.00", 130, 75, 135),
            ),
        )

    def test_public_api_has_exactly_one_keyword_only_input(self) -> None:
        signature = inspect.signature(inspect_feature_input_readiness)
        self.assertEqual(("operand_audit",), tuple(signature.parameters))
        self.assertIs(
            signature.parameters["operand_audit"].kind,
            inspect.Parameter.KEYWORD_ONLY,
        )

    def test_public_api_preserves_exact_operand_audit_reference(self) -> None:
        operand_audit = self.operand_audit()
        result = inspect_feature_input_readiness(operand_audit=operand_audit)
        self.assertIs(result.operand_audit, operand_audit)
        self.assertTrue(
            all(item.operand_audit is operand_audit for item in result.candidate_observations)
        )

    def test_aggregate_rejects_value_equal_operand_audit_replacement(self) -> None:
        result = self.result()
        replacement = replace(result.operand_audit)
        self.assertEqual(replacement, result.operand_audit)
        self.assertIsNot(replacement, result.operand_audit)
        object.__setattr__(result, "operand_audit", replacement)
        with self.assertRaises(FeatureInputReadinessIntegrityError):
            result.__post_init__()

    def test_candidate_rejects_value_equal_operand_audit_replacement(self) -> None:
        result = self.result()
        observed = result.candidate_observations[0]
        replacement = replace(result.operand_audit)
        self.assertEqual(replacement, observed.operand_audit)
        self.assertIsNot(replacement, observed.operand_audit)
        object.__setattr__(observed, "operand_audit", replacement)
        with self.assertRaises(FeatureInputReadinessIntegrityError):
            observed.__post_init__()
        with self.assertRaises(FeatureInputReadinessIntegrityError):
            result.__post_init__()

    def test_fresh_wrapper_over_same_exact_upstream_references_is_valid(self) -> None:
        result = self.result((("a", GENERIC, "shop"),), candidate_limit=2)
        candidate_wrappers = tuple(
            replace(item) for item in result.candidate_observations
        )
        reconstructed = replace(
            result,
            candidate_observations=candidate_wrappers,
        )
        self.assertIsNot(reconstructed, result)
        self.assertTrue(
            all(
                current is not original
                for current, original in zip(
                    reconstructed.candidate_observations,
                    result.candidate_observations,
                    strict=True,
                )
            )
        )
        self.assertIs(reconstructed.operand_audit, result.operand_audit)
        self.assertTrue(
            all(
                item.operand_audit is reconstructed.operand_audit
                for item in reconstructed.candidate_observations
            )
        )
        reconstructed.__post_init__()

    def test_c0_only_population_and_exact_reference(self) -> None:
        result = self.result()
        self.assertEqual(1, len(result.candidate_observations))
        observed = result.candidate_observations[0]
        self.assertIs(observed.candidate.role, CandidateRole.ORIGINAL)
        self.assertIs(observed.candidate, result.operand_audit.candidate_audits[0].candidate)

    def test_c0_and_multiple_retained_altered_candidates_preserve_order(self) -> None:
        result = self.result(
            (("a", GENERIC, "pantry mars"), ("b", GENERIC, "shop")),
            candidate_limit=3,
        )
        self.assertEqual(3, len(result.candidate_observations))
        self.assertEqual(
            tuple(item.candidate.candidate_id for item in result.candidate_observations),
            tuple(item.candidate.candidate_id for item in result.operand_audit.candidate_audits),
        )
        self.assertIs(result.candidate_observations[0].candidate.role, CandidateRole.ORIGINAL)

    def test_exact_seven_slot_order(self) -> None:
        result = self.result()
        self.assertEqual(
            FEATURE_SLOT_ORDER,
            tuple(item.slot for item in result.candidate_observations[0].slots),
        )

    def test_reordered_missing_and_duplicated_slots_are_rejected(self) -> None:
        observed = self.result().candidate_observations[0]
        variants = (
            tuple(reversed(observed.slots)),
            observed.slots[:-1],
            (*observed.slots[:-1], observed.slots[0]),
        )
        for slots in variants:
            with self.subTest(slots=tuple(item.slot.value for item in slots)):
                with self.assertRaises(FeatureInputReadinessIntegrityError):
                    replace(observed, slots=slots)

    def test_invalid_candidate_reference_is_rejected(self) -> None:
        result = self.result((("a", GENERIC, "shop"),), candidate_limit=2)
        original, altered = result.candidate_observations
        with self.assertRaises(FeatureInputReadinessIntegrityError):
            replace(
                original,
                candidate_audit=altered.candidate_audit,
                candidate=original.candidate,
            )

    def test_changed_candidate_content_with_same_id_is_rejected(self) -> None:
        result = self.result((("a", GENERIC, "shop"),), candidate_limit=2)
        altered = result.candidate_observations[1].candidate
        original_id = altered.candidate_id
        object.__setattr__(altered, "value", "forged-content")
        self.assertEqual(original_id, altered.candidate_id)
        with self.assertRaises(FeatureInputReadinessIntegrityError):
            result.__post_init__()

    def test_overflow_candidate_injection_is_rejected(self) -> None:
        operand_audit = self.operand_audit(
            (("a", GENERIC, "shop"),), candidate_limit=1
        )
        overflow = operand_audit.overflow_audit_records[0]
        self.assertIs(overflow.limit_status, CandidateLimitStatus.LIMIT_OVERFLOW)
        object.__setattr__(operand_audit.candidate_audits[0], "candidate", overflow)
        with self.assertRaises(FeatureInputReadinessIntegrityError):
            inspect_feature_input_readiness(operand_audit=operand_audit)

    def test_ocr_literals_polygons_and_present_confidence_are_preserved(self) -> None:
        candidate = self.result().candidate_observations[0]
        literals = self.facts(candidate, FeatureSlot.OCR_EVIDENCE, InputFactKindV0.OCR_TOKEN_LITERAL)
        confidences = self.facts(
            candidate,
            FeatureSlot.OCR_EVIDENCE,
            InputFactKindV0.OCR_TOKEN_CONFIDENCE,
        )
        polygons = self.facts(
            candidate,
            FeatureSlot.LAYOUT_AGREEMENT,
            InputFactKindV0.SOURCE_TOKEN_POLYGON,
        )
        self.assertTrue(literals)
        self.assertTrue(polygons)
        self.assertTrue(
            all(item.presence is InputFactPresenceV0.PRESENT for item in confidences)
        )
        self.assertTrue(all(item.raw_number_fingerprints for item in confidences))

    def test_missing_individual_ocr_confidence_is_explicit(self) -> None:
        candidate = self.result(
            fixture=_MissingOcrConfidenceFixture("feature-readiness-missing-ocr")
        ).candidate_observations[0]
        confidences = self.facts(
            candidate,
            FeatureSlot.OCR_EVIDENCE,
            InputFactKindV0.OCR_TOKEN_CONFIDENCE,
        )
        store = next(item for item in confidences if item.source_references == ("store",))
        self.assertIs(store.presence, InputFactPresenceV0.ABSENT_IN_STORED_GRAPH)
        self.assertEqual((), store.raw_number_fingerprints)

    def test_b2_none_confidence_is_absent_and_ocr_is_not_substituted(self) -> None:
        candidate = self.result().candidate_observations[0]
        extractor = self.facts(
            candidate,
            FeatureSlot.EXTRACTOR_EVIDENCE,
            InputFactKindV0.B2_EXTRACTOR_CONFIDENCE,
        )
        self.assertEqual(1, len(extractor))
        self.assertIs(
            extractor[0].presence,
            InputFactPresenceV0.ABSENT_IN_STORED_GRAPH,
        )
        self.assertEqual((), extractor[0].raw_number_fingerprints)

    def test_source_token_text_and_polygon_mutation_are_rejected(self) -> None:
        for attribute, replacement_value in (
            ("original_text", "FORGED"),
            ("polygon", ()),
        ):
            with self.subTest(attribute=attribute):
                result = self.result()
                token = result.operand_audit.hard_constraint_input.source_tokens[0]
                object.__setattr__(token, attribute, replacement_value)
                with self.assertRaises(FeatureInputReadinessIntegrityError):
                    result.__post_init__()

    def test_c0_candidate_and_provenance_values_are_preserved(self) -> None:
        result = self.result((("a", GENERIC, "shop"),), candidate_limit=2)
        altered = result.candidate_observations[1]
        lexical = self.slot(altered, FeatureSlot.LEXICAL_AGREEMENT)
        c0 = next(item for item in lexical.facts if item.kind is InputFactKindV0.C0_VALUE)
        value = next(
            item for item in lexical.facts if item.kind is InputFactKindV0.CANDIDATE_VALUE
        )
        provenance = tuple(
            item
            for item in lexical.facts
            if item.kind is InputFactKindV0.CANDIDATE_PROVENANCE
        )
        self.assertEqual((altered.candidate.c0_candidate_id,), c0.source_references)
        self.assertEqual((altered.candidate.value,), value.raw_texts)
        self.assertEqual(len(altered.candidate.provenance), len(provenance))

    def test_preliminary_similarity_is_not_reused_as_lexical_input(self) -> None:
        altered = self.result(
            (("a", GENERIC, "shop"),), candidate_limit=2
        ).candidate_observations[1]
        self.assertIsNotNone(altered.candidate.preliminary_rank)
        lexical = self.slot(altered, FeatureSlot.LEXICAL_AGREEMENT)
        similarity = str(altered.candidate.preliminary_rank.normalized_edit_similarity)
        self.assertNotIn(similarity, tuple(text for fact in lexical.facts for text in fact.raw_texts))
        self.assertTrue(
            any(
                fact.kind is InputFactKindV0.LEXICAL_TRANSFORMATION_POLICY
                and fact.presence is InputFactPresenceV0.UNDETERMINED_WITHOUT_POLICY
                for fact in lexical.facts
            )
        )

    def test_original_arithmetic_operands_are_preserved_without_calculation(self) -> None:
        candidate = self.result(
            field_name=ReceiptFieldName.ITEM_DESCRIPTION
        ).candidate_observations[0]
        arithmetic = self.slot(candidate, FeatureSlot.ARITHMETIC_SUPPORT)
        flattened = tuple(text for fact in arithmetic.facts for text in fact.raw_texts)
        for literal in ("2", "RM 5.50", "11.00"):
            self.assertIn(literal, flattened)
        policy = next(
            item
            for item in arithmetic.facts
            if item.kind is InputFactKindV0.CANDIDATE_SUBSTITUTED_ARITHMETIC
        )
        self.assertIs(
            policy.presence,
            InputFactPresenceV0.UNDETERMINED_WITHOUT_POLICY,
        )

    def test_missing_and_unresolved_operands_remain_absent_raw_inputs(self) -> None:
        fixtures = (
            self.missing_unit_fixture(),
            self.unresolved_fixture(),
        )
        for fixture in fixtures:
            with self.subTest(receipt_id=fixture.receipt_id):
                candidate = self.result(
                    fixture=fixture,
                    field_name=ReceiptFieldName.ITEM_DESCRIPTION,
                ).candidate_observations[0]
                operands = self.facts(
                    candidate,
                    FeatureSlot.ARITHMETIC_SUPPORT,
                    InputFactKindV0.ORIGINAL_B2_ITEM_OPERAND,
                )
                self.assertTrue(
                    any(
                        item.presence
                        is InputFactPresenceV0.ABSENT_IN_STORED_GRAPH
                        for item in operands
                    )
                )

    def test_retailer_and_price_snapshots_are_unbound_not_absent(self) -> None:
        candidate = self.result().candidate_observations[0]
        retailer = self.facts(
            candidate,
            FeatureSlot.RETAILER_SUPPORT,
            InputFactKindV0.RETAILER_SNAPSHOT_BINDING,
        )[0]
        price = self.facts(
            candidate,
            FeatureSlot.PRICE_REFERENCE_SUPPORT,
            InputFactKindV0.PRICE_REFERENCE_SNAPSHOT_BINDING,
        )[0]
        self.assertIs(
            retailer.presence,
            InputFactPresenceV0.NOT_BOUND_BY_INPUT_CONTRACT,
        )
        self.assertIs(price.presence, InputFactPresenceV0.NOT_BOUND_BY_INPUT_CONTRACT)
        self.assertEqual((), retailer.source_references)
        self.assertEqual((), price.source_references)

    def test_absent_and_unbound_vocabularies_remain_distinct(self) -> None:
        candidate = self.result().candidate_observations[0]
        extractor = self.facts(
            candidate,
            FeatureSlot.EXTRACTOR_EVIDENCE,
            InputFactKindV0.B2_EXTRACTOR_CONFIDENCE,
        )[0]
        retailer = self.facts(
            candidate,
            FeatureSlot.RETAILER_SUPPORT,
            InputFactKindV0.RETAILER_SNAPSHOT_BINDING,
        )[0]
        self.assertIs(extractor.presence, InputFactPresenceV0.ABSENT_IN_STORED_GRAPH)
        self.assertIs(
            retailer.presence,
            InputFactPresenceV0.NOT_BOUND_BY_INPUT_CONTRACT,
        )

    def test_no_fabricated_source_or_resource_references(self) -> None:
        result = self.result((("a", GENERIC, "shop"),), candidate_limit=2)
        context = result.operand_audit.hard_constraint_input
        output = context.receipt_output
        fields_in_receipt = (
            output.store_name,
            output.purchase_date,
            *(field for row in output.items for field in row.fields),
            output.receipt_total,
        )
        candidates = tuple(item.candidate for item in result.candidate_observations)
        allowed = {
            *(token.token_id for token in output.source_evidence.tokens),
            *(item.field_id for item in fields_in_receipt),
            *(row.row_id for row in output.items),
            *(item.candidate_id for item in candidates),
            *(item.c0_candidate_id for item in candidates),
            *(
                provenance.provenance_id
                for candidate in candidates
                for provenance in candidate.provenance
            ),
            *(
                provenance.resource_snapshot_id
                for candidate in candidates
                for provenance in candidate.provenance
                if provenance.resource_snapshot_id is not None
            ),
        }
        observed = {
            reference
            for candidate in result.candidate_observations
            for slot in candidate.slots
            for fact in slot.facts
            for reference in fact.source_references
        }
        self.assertLessEqual(observed, allowed)

    def test_repeatability_and_deterministic_reconstruction(self) -> None:
        operand_audit = self.operand_audit(
            (("a", GENERIC, "shop"),), candidate_limit=2
        )
        first = inspect_feature_input_readiness(operand_audit=operand_audit)
        second = inspect_feature_input_readiness(operand_audit=operand_audit)
        self.assertEqual(first, second)
        self.assertTrue(
            all(
                left.candidate_audit is right.candidate_audit
                for left, right in zip(
                    first.candidate_observations,
                    second.candidate_observations,
                    strict=True,
                )
            )
        )

    def test_repeated_post_init_does_not_refresh_private_observation(self) -> None:
        result = self.result()
        original = result._primitive_observation
        result.__post_init__()
        self.assertIs(original, result._primitive_observation)
        altered_slots = tuple(reversed(result.candidate_observations[0].slots))
        object.__setattr__(result.candidate_observations[0], "slots", altered_slots)
        with self.assertRaises(FeatureInputReadinessIntegrityError):
            result.__post_init__()
        self.assertIs(original, result._primitive_observation)

    def test_frozen_slotted_and_component_local_versions(self) -> None:
        result = self.result()
        self.assertEqual(FEATURE_READINESS_COMPONENT_VERSION, result.component_version)
        self.assertEqual(FEATURE_READINESS_RECORD_VERSION, result.record_version)
        with self.assertRaises(FrozenInstanceError):
            result.component_version = "changed"  # type: ignore[misc]
        # CPython may surface AttributeError or the generated slots/frozen
        # TypeError for an unknown member; either proves no dynamic field exists.
        with self.assertRaises((AttributeError, TypeError)):
            result.unapproved_attribute = True  # type: ignore[attr-defined]

    def test_inspection_does_not_rerun_upstream_components(self) -> None:
        operand_audit = self.operand_audit()
        targets = (
            "pipeline.layout_b2.extract_b2",
            "pipeline.baseline_b3.apply_b3",
            "pipeline.proposed.candidate_generation.generate_candidate_drafts",
            "pipeline.proposed.hard_constraint_operands.audit_hard_constraint_operands",
        )
        patches = [patch(target, side_effect=AssertionError(target)) for target in targets]
        started = [item.start() for item in patches]
        try:
            result = inspect_feature_input_readiness(operand_audit=operand_audit)
        finally:
            for item in reversed(patches):
                item.stop()
        self.assertEqual(4, len(started))
        self.assertIs(result.operand_audit, operand_audit)

    def test_no_forbidden_downstream_records_or_output_shape(self) -> None:
        module_source = Path(
            inspect.getfile(inspect_feature_input_readiness)
        ).read_text(encoding="utf-8")
        for forbidden_type in (
            "ConstraintResultV1",
            "CandidateEvidenceV1",
            "FieldDecisionV1",
            "ConfigurationRefsV1",
        ):
            self.assertNotIn(forbidden_type, module_source)
        forbidden_fields = {
            "feature_schema_id",
            "feature_values",
            "missingness_mask",
            "eligibility",
            "raw_score",
            "calibrated_probability",
            "probability_available",
        }
        record_types = (
            InputFactObservationV0,
            FeatureSlotInputObservationV0,
            CandidateFeatureInputObservationV0,
            FeatureInputReadinessResultV0,
        )
        observed_fields = {
            item.name for record_type in record_types for item in fields(record_type)
        }
        self.assertTrue(forbidden_fields.isdisjoint(observed_fields))

    def test_api_excludes_ground_truth_providers_rules_and_downstream_inputs(self) -> None:
        parameters = set(inspect.signature(inspect_feature_input_readiness).parameters)
        forbidden = {
            "ground_truth",
            "held_out_annotations",
            "price_provider",
            "hard_rule_overrides",
            "feature_values",
            "scorer",
            "calibrator",
        }
        self.assertTrue(parameters.isdisjoint(forbidden))


if __name__ == "__main__":
    unittest.main()
