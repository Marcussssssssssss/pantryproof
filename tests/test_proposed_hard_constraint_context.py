"""Synthetic adversarial tests for hard-constraint input context V0."""

from __future__ import annotations

import inspect
import unittest
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
from unittest.mock import patch

from pipeline.contracts import OutputStage
from pipeline.proposed.candidate_deduplication import deduplicate_candidate_drafts
from pipeline.proposed.candidate_finalization import (
    CandidateFinalizationCoverageStatusV0,
    CandidateFinalizationReadinessV0,
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
    CandidateEvidenceV1,
    CandidateLimitStatus,
    CandidateRecordV1,
    CandidateRole,
    CandidateSourceKind,
    ConstraintResultV1,
)
from pipeline.proposed.hard_constraint_context import (
    HARD_CONSTRAINT_CONTEXT_COMPONENT_VERSION,
    HARD_CONSTRAINT_CONTEXT_RECORD_VERSION,
    HardConstraintInputIntegrityError,
    HardConstraintInputResultV0,
    HardConstraintInputUnavailableError,
    HardConstraintInputUnavailableReasonV0,
    prepare_hard_constraint_inputs,
)
from test_proposed_candidate_deduplication import _SyntheticCandidateFixture


GENERIC = CandidateSourceKind.GENERIC_NORMALIZATION
SOURCE = CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR


class ProposedHardConstraintContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = _SyntheticCandidateFixture(
            receipt_id="hard-constraint-context-receipt"
        )

    def ranking(
        self,
        specs: tuple[tuple[str, CandidateSourceKind, str], ...] = (),
        *,
        multi_provenance: bool = False,
    ):
        drafts = self.fixture.drafts(
            seed_specs=specs,
            multi_provenance=multi_provenance,
        )
        provenance = materialize_altered_provenance(
            identity_preparation=prepare_candidate_identities(
                deduplication_result=deduplicate_candidate_drafts(
                    candidate_drafts=drafts
                )
            )
        )
        return compute_preliminary_candidate_ranking(
            provenance_result=provenance,
            configuration=CandidateRankingConfigurationV0(
                theta_a_ref=drafts.suspicion_result.theta_a_ref
            ),
        )

    def ranking_from_builder(self, builder):
        adapter, method = self.fixture.adapter_and_method()
        seeds = builder(adapter, method)
        adapter, method = self.fixture.with_seeds(adapter, method, seeds)
        drafts = generate_candidate_drafts(
            suspicion_result=self.fixture.suspicion(method),
            adapter_result=adapter,
        )
        provenance = materialize_altered_provenance(
            identity_preparation=prepare_candidate_identities(
                deduplication_result=deduplicate_candidate_drafts(
                    candidate_drafts=drafts
                )
            )
        )
        return compute_preliminary_candidate_ranking(
            provenance_result=provenance,
            configuration=CandidateRankingConfigurationV0(
                theta_a_ref=drafts.suspicion_result.theta_a_ref
            ),
        )

    def mixed_materialized_and_blocked(self, *, blocked_first: bool):
        def builder(_adapter, method):
            blocked_value = "pantry mars" if blocked_first else "pantry shop"
            materialized_value = "shop" if blocked_first else "pantry mars"
            return (
                self.fixture.seed(
                    method,
                    suffix="blocked",
                    source_kind=GENERIC,
                    proposed_value=blocked_value,
                    event_ids=("event:blocked:a", "event:blocked:b"),
                    rule_ids=("rule:blocked:a", "rule:blocked:b"),
                ),
                self.fixture.seed(
                    method,
                    suffix="materialized",
                    source_kind=GENERIC,
                    proposed_value=materialized_value,
                ),
            )

        return self.ranking_from_builder(builder)

    def ranking_blocked(self):
        def builder(_adapter, method):
            return (
                self.fixture.seed(
                    method,
                    suffix="missing-position",
                    source_kind=SOURCE,
                    proposed_value="pantry shop",
                    spans=(),
                ),
            )

        return self.ranking_from_builder(builder)

    @staticmethod
    def configuration(ranking, candidate_limit: int = 3):
        return CandidateLimitingConfigurationV0(
            theta_a_ref=ranking.configuration.theta_a_ref,
            candidate_limit=candidate_limit,
            fixture_reference="synthetic:hard-constraint-context:test-v0",
        )

    def finalize(self, ranking, candidate_limit: int = 3):
        return materialize_ranked_candidate_records(
            limit_result=apply_candidate_limit(
                ranking_result=ranking,
                configuration=self.configuration(ranking, candidate_limit),
            )
        )

    @staticmethod
    def generation(finalization):
        return (
            finalization.limit_result.ranking_result.provenance_result
            .identity_preparation.deduplication_result.candidate_drafts
        )

    def prepared(
        self,
        specs: tuple[tuple[str, CandidateSourceKind, str], ...] = (),
        candidate_limit: int = 3,
    ):
        finalization = self.finalize(self.ranking(specs), candidate_limit)
        return prepare_hard_constraint_inputs(finalization_result=finalization)

    def test_public_api_has_one_keyword_only_input(self) -> None:
        signature = inspect.signature(prepare_hard_constraint_inputs)
        self.assertEqual(("finalization_result",), tuple(signature.parameters))
        self.assertIs(
            signature.parameters["finalization_result"].kind,
            inspect.Parameter.KEYWORD_ONLY,
        )

    def test_exact_finalization_result_reference_is_preserved(self) -> None:
        finalization = self.finalize(self.ranking())
        result = prepare_hard_constraint_inputs(finalization_result=finalization)
        self.assertIs(result.finalization_result, finalization)

    def test_exact_method_ready_field_reference_is_preserved(self) -> None:
        result = self.prepared()
        generation = self.generation(result.finalization_result)
        self.assertIs(result.method_ready_field, generation.original.method_ready_field)

    def test_exact_adapter_reference_is_preserved(self) -> None:
        result = self.prepared()
        generation = self.generation(result.finalization_result)
        self.assertIs(result.adapter_result, generation.adapter_result)

    def test_permanent_c0_is_first_and_preserved_by_reference(self) -> None:
        result = self.prepared((("one", GENERIC, "shop"),))
        self.assertIs(result.candidates[0], result.finalization_result.original_candidate)
        self.assertIs(result.candidates[0].role, CandidateRole.ORIGINAL)

    def test_one_retained_altered_candidate_is_preserved(self) -> None:
        result = self.prepared((("one", GENERIC, "shop"),), 2)
        self.assertEqual(2, len(result.candidates))
        self.assertIs(
            result.candidates[1], result.finalization_result.retained_records[0]
        )

    def test_multiple_retained_candidates_preserve_order_and_references(self) -> None:
        result = self.prepared(
            (("a", GENERIC, "pantry mars"), ("b", GENERIC, "shop")),
            3,
        )
        self.assertEqual(
            (result.finalization_result.original_candidate,
             *result.finalization_result.retained_records),
            result.candidates,
        )
        self.assertTrue(
            all(
                observed is expected
                for observed, expected in zip(
                    result.candidates[1:],
                    result.finalization_result.retained_records,
                    strict=True,
                )
            )
        )

    def test_valid_empty_altered_set_produces_c0_only(self) -> None:
        result = self.prepared()
        self.assertEqual(1, len(result.candidates))
        self.assertIs(result.candidates[0], result.finalization_result.original_candidate)

    def test_one_overflow_candidate_is_excluded(self) -> None:
        result = self.prepared((("one", GENERIC, "shop"),), 1)
        self.assertEqual((result.finalization_result.original_candidate,), result.candidates)
        self.assertEqual(1, len(result.overflow_audit_records))

    def test_multiple_overflow_candidates_are_excluded(self) -> None:
        result = self.prepared(
            (
                ("a", GENERIC, "pantry mars"),
                ("b", GENERIC, "pantry shop"),
                ("c", GENERIC, "shop"),
            ),
            1,
        )
        self.assertEqual(1, len(result.candidates))
        self.assertEqual(3, len(result.overflow_audit_records))

    def test_blocked_overflow_is_tolerated_with_visible_coverage_warning(self) -> None:
        finalization = self.finalize(
            self.mixed_materialized_and_blocked(blocked_first=False), 2
        )
        result = prepare_hard_constraint_inputs(finalization_result=finalization)
        self.assertIs(
            result.full_ledger_coverage_status,
            CandidateFinalizationCoverageStatusV0.INCOMPLETE_BLOCKED_PROVENANCE,
        )
        self.assertEqual(1, len(result.blocked_audits))
        self.assertEqual(2, len(result.candidates))

    def test_blocked_retained_finalization_uses_typed_unavailability(self) -> None:
        finalization = self.finalize(
            self.ranking((("blocked", GENERIC, "shop"),), multi_provenance=True),
            2,
        )
        with self.assertRaises(HardConstraintInputUnavailableError) as caught:
            prepare_hard_constraint_inputs(finalization_result=finalization)
        self.assertIs(
            caught.exception.reason,
            HardConstraintInputUnavailableReasonV0.RETAINED_PROVENANCE_BLOCKED,
        )
        self.assertIs(caught.exception.finalization_result, finalization)

    def test_ranking_unavailable_uses_distinct_typed_unavailability(self) -> None:
        finalization = self.finalize(self.ranking_blocked(), 2)
        with self.assertRaises(HardConstraintInputUnavailableError) as caught:
            prepare_hard_constraint_inputs(finalization_result=finalization)
        self.assertIs(
            caught.exception.reason,
            HardConstraintInputUnavailableReasonV0.RANKING_UNAVAILABLE,
        )
        self.assertIs(caught.exception.finalization_result, finalization)

    def test_valid_unavailability_is_not_reported_as_integrity_corruption(self) -> None:
        cases = (
            self.finalize(
                self.ranking((("blocked", GENERIC, "shop"),), multi_provenance=True),
                2,
            ),
            self.finalize(self.ranking_blocked(), 2),
        )
        for finalization in cases:
            with self.subTest(readiness=finalization.readiness):
                with self.assertRaises(HardConstraintInputUnavailableError) as caught:
                    prepare_hard_constraint_inputs(finalization_result=finalization)
                self.assertNotIsInstance(
                    caught.exception, HardConstraintInputIntegrityError
                )

    def test_non_pre_review_output_is_rejected_by_public_preparation(self) -> None:
        for stage in (OutputStage.HUMAN_REVIEWED, OutputStage.ORACLE_MODIFIED):
            with self.subTest(stage=stage):
                finalization = self.finalize(self.ranking())
                generation = self.generation(finalization)
                output = generation.adapter_result.original_b2_result.receipt_output
                self.assertIsNotNone(output)
                object.__setattr__(output, "output_stage", stage)
                with self.assertRaises(HardConstraintInputIntegrityError) as caught:
                    prepare_hard_constraint_inputs(
                        finalization_result=finalization
                    )
                self.assertIsInstance(caught.exception.__cause__, ValueError)
                self.assertIn(
                    "PRE_REVIEW_AUTOMATIC",
                    str(caught.exception.__cause__),
                )

    def test_non_pre_review_output_is_rejected_on_aggregate_reconstruction(self) -> None:
        for stage in (OutputStage.HUMAN_REVIEWED, OutputStage.ORACLE_MODIFIED):
            with self.subTest(stage=stage):
                result = self.prepared()
                object.__setattr__(result.receipt_output, "output_stage", stage)
                with self.assertRaises(HardConstraintInputIntegrityError) as caught:
                    result.__post_init__()
                self.assertIsInstance(caught.exception.__cause__, ValueError)
                self.assertIn(
                    "PRE_REVIEW_AUTOMATIC",
                    str(caught.exception.__cause__),
                )

    def test_unavailable_finalization_substitution_is_reconstruction_integrity_error(
        self,
    ) -> None:
        result = self.prepared()
        blocked = self.finalize(
            self.ranking(
                (("blocked", GENERIC, "shop"),),
                multi_provenance=True,
            ),
            2,
        )
        object.__setattr__(result, "finalization_result", blocked)
        with self.assertRaises(HardConstraintInputIntegrityError) as caught:
            result.__post_init__()
        cause = caught.exception.__cause__
        self.assertIsInstance(cause, HardConstraintInputUnavailableError)
        self.assertIs(
            cause.reason,
            HardConstraintInputUnavailableReasonV0.RETAINED_PROVENANCE_BLOCKED,
        )
        self.assertIs(cause.finalization_result, blocked)

    def test_malformed_finalization_is_an_integrity_failure_with_cause(self) -> None:
        finalization = self.finalize(self.ranking())
        object.__setattr__(
            finalization,
            "readiness",
            CandidateFinalizationReadinessV0.RANKING_UNAVAILABLE,
        )
        with self.assertRaises(HardConstraintInputIntegrityError) as caught:
            prepare_hard_constraint_inputs(finalization_result=finalization)
        self.assertIsNotNone(caught.exception.__cause__)

    def test_partial_diagnostic_retained_records_do_not_form_an_input_set(self) -> None:
        finalization = self.finalize(
            self.mixed_materialized_and_blocked(blocked_first=True), 3
        )
        self.assertTrue(finalization.retained_records)
        with self.assertRaises(HardConstraintInputUnavailableError):
            prepare_hard_constraint_inputs(finalization_result=finalization)

    def test_method_field_is_retrieved_through_exact_approved_graph(self) -> None:
        result = self.prepared()
        generation = self.generation(result.finalization_result)
        self.assertIs(result.method_ready_field, generation.original.method_ready_field)
        self.assertEqual(
            result.method_ready_field,
            generation.suspicion_result.method_ready_field,
        )

    def test_adapter_is_retrieved_through_exact_approved_graph(self) -> None:
        result = self.prepared()
        self.assertIs(
            result.adapter_result,
            self.generation(result.finalization_result).adapter_result,
        )

    def test_original_b2_result_and_receipt_output_preserve_references(self) -> None:
        result = self.prepared()
        self.assertIs(result.original_b2_result, result.adapter_result.original_b2_result)
        self.assertIs(result.receipt_output, result.original_b2_result.receipt_output)

    def test_stored_sufficient_gate_is_preserved(self) -> None:
        result = self.prepared()
        self.assertIs(result.stored_gate, result.adapter_result.stored_gate_result)
        self.assertEqual(result.stored_gate, result.method_ready_field.stored_gate_result)
        self.assertEqual(result.stored_gate, result.source_evidence.gate_result)

    def test_receipt_and_field_identities_are_derived_from_method(self) -> None:
        result = self.prepared()
        self.assertEqual(result.method_ready_field.receipt_id, result.receipt_id)
        self.assertEqual(result.method_ready_field.field_id, result.field_id)
        self.assertTrue(
            all(
                item.receipt_id == result.receipt_id
                and item.field_id == result.field_id
                for item in result.candidates
            )
        )

    def test_source_token_ids_and_token_references_are_preserved(self) -> None:
        result = self.prepared()
        self.assertIs(result.source_tokens, result.method_ready_field.source_tokens)
        self.assertEqual(
            result.method_ready_field.source_token_ids,
            tuple(token.token_id for token in result.source_tokens),
        )

    def test_source_image_identity_is_preserved(self) -> None:
        result = self.prepared()
        self.assertEqual(result.method_ready_field.source_image_id, result.source_image_id)
        self.assertEqual(result.source_evidence.image_id, result.source_image_id)

    def test_duplicate_candidate_is_rejected_on_reconstruction(self) -> None:
        result = self.prepared((("one", GENERIC, "shop"),), 2)
        object.__setattr__(
            result,
            "candidates",
            (result.candidates[0], result.candidates[1], result.candidates[1]),
        )
        with self.assertRaises(HardConstraintInputIntegrityError):
            result.__post_init__()

    def test_missing_candidate_is_rejected_on_reconstruction(self) -> None:
        result = self.prepared((("one", GENERIC, "shop"),), 2)
        object.__setattr__(result, "candidates", result.candidates[:1])
        with self.assertRaises(HardConstraintInputIntegrityError):
            result.__post_init__()

    def test_candidate_reordering_is_rejected(self) -> None:
        result = self.prepared((("one", GENERIC, "shop"),), 2)
        object.__setattr__(result, "candidates", tuple(reversed(result.candidates)))
        with self.assertRaises(HardConstraintInputIntegrityError):
            result.__post_init__()

    def test_overflow_candidate_substitution_is_rejected(self) -> None:
        result = self.prepared(
            (("a", GENERIC, "pantry mars"), ("b", GENERIC, "shop")),
            2,
        )
        self.assertEqual(1, len(result.overflow_audit_records))
        object.__setattr__(
            result,
            "candidates",
            (result.candidates[0], result.overflow_audit_records[0]),
        )
        with self.assertRaises(HardConstraintInputIntegrityError):
            result.__post_init__()

    def test_deepcopied_candidate_is_rejected_where_identity_is_required(self) -> None:
        result = self.prepared((("one", GENERIC, "shop"),), 2)
        copied = deepcopy(result.candidates[1])
        object.__setattr__(result, "candidates", (result.candidates[0], copied))
        with self.assertRaises(HardConstraintInputIntegrityError):
            result.__post_init__()

    def test_deepcopied_method_reference_is_rejected_in_prepared_aggregate(self) -> None:
        result = self.prepared()
        object.__setattr__(result, "method_ready_field", deepcopy(result.method_ready_field))
        with self.assertRaisesRegex(HardConstraintInputIntegrityError, "method-ready"):
            result.__post_init__()

    def test_deepcopied_adapter_reference_is_rejected_in_prepared_aggregate(self) -> None:
        result = self.prepared()
        object.__setattr__(result, "adapter_result", deepcopy(result.adapter_result))
        with self.assertRaisesRegex(HardConstraintInputIntegrityError, "adapter"):
            result.__post_init__()

    def test_forged_finalization_readiness_is_integrity_failure(self) -> None:
        result = self.prepared()
        object.__setattr__(
            result.finalization_result,
            "readiness",
            CandidateFinalizationReadinessV0.BLOCKED_BY_RETAINED_PROVENANCE,
        )
        with self.assertRaises(HardConstraintInputIntegrityError):
            result.__post_init__()

    def test_forged_full_ledger_coverage_is_integrity_failure(self) -> None:
        result = self.prepared()
        object.__setattr__(
            result.finalization_result.coverage,
            "status",
            CandidateFinalizationCoverageStatusV0.INCOMPLETE_BLOCKED_PROVENANCE,
        )
        with self.assertRaises(HardConstraintInputIntegrityError):
            result.__post_init__()

    def test_mutated_synthetic_limiting_configuration_is_rejected(self) -> None:
        result = self.prepared()
        object.__setattr__(
            result.finalization_result.limiting_configuration,
            "scope_id",
            "production",
        )
        with self.assertRaises(HardConstraintInputIntegrityError):
            result.__post_init__()

    def test_c0_equivalent_proposal_creates_no_duplicate(self) -> None:
        result = self.prepared((("same", GENERIC, "pantry mart"),), 2)
        self.assertEqual(1, len(result.candidates))
        self.assertIsNotNone(result.finalization_result.equivalent_to_c0)

    def test_repeated_execution_is_deterministic(self) -> None:
        finalization = self.finalize(self.ranking((("one", GENERIC, "shop"),)), 2)
        first = prepare_hard_constraint_inputs(finalization_result=finalization)
        second = prepare_hard_constraint_inputs(finalization_result=finalization)
        self.assertEqual(first, second)
        self.assertTrue(
            all(a is b for a, b in zip(first.candidates, second.candidates, strict=True))
        )

    def test_discovery_order_independence_is_inherited(self) -> None:
        specs = (
            ("a", GENERIC, "pantry mars"),
            ("b", GENERIC, "pantry shop"),
            ("c", GENERIC, "shop"),
        )
        first = self.prepared(specs, 3)
        second = self.prepared(tuple(reversed(specs)), 3)
        self.assertEqual(
            tuple(item.candidate_id for item in first.candidates),
            tuple(item.candidate_id for item in second.candidates),
        )

    def test_result_is_frozen_slotted_and_versioned(self) -> None:
        result = self.prepared()
        self.assertFalse(hasattr(result, "__dict__"))
        self.assertEqual(
            HARD_CONSTRAINT_CONTEXT_COMPONENT_VERSION, result.component_version
        )
        self.assertEqual(HARD_CONSTRAINT_CONTEXT_RECORD_VERSION, result.record_version)
        with self.assertRaises(FrozenInstanceError):
            result.record_version = "changed"  # type: ignore[misc]

    def test_result_shape_contains_only_approved_stored_fields(self) -> None:
        self.assertEqual(
            {
                "finalization_result",
                "method_ready_field",
                "adapter_result",
                "candidates",
                "component_version",
                "record_version",
            },
            {item.name for item in fields(HardConstraintInputResultV0)},
        )
        for forbidden in (
            "eligible",
            "passed_constraints",
            "production_ready",
            "manifest_verified",
        ):
            self.assertNotIn(forbidden, {item.name for item in fields(HardConstraintInputResultV0)})

    def test_invalid_result_versions_are_rejected(self) -> None:
        result = self.prepared()
        for name in ("component_version", "record_version"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                replace(result, **{name: "future-version"})

    def test_public_boundary_does_not_rerun_upstream_pipeline_functions(self) -> None:
        finalization = self.finalize(self.ranking((("one", GENERIC, "shop"),)), 2)
        targets = (
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
            "pipeline.proposed.candidate_finalization.materialize_ranked_candidate_records",
        )
        patches = [patch(target, side_effect=AssertionError(target)) for target in targets]
        started = [item.start() for item in patches]
        self.addCleanup(lambda: [item.stop() for item in reversed(patches)])
        self.assertEqual(len(targets), len(started))
        result = prepare_hard_constraint_inputs(finalization_result=finalization)
        self.assertEqual(2, len(result.candidates))

    def test_no_source_gate_execution_interface_is_accepted_or_invoked(self) -> None:
        signature = inspect.signature(prepare_hard_constraint_inputs)
        self.assertNotIn("source_gate", signature.parameters)
        self.assertNotIn("gate_callback", signature.parameters)
        result = self.prepared()
        self.assertIs(result.stored_gate, result.adapter_result.stored_gate_result)

    def test_outputs_contain_no_constraint_or_candidate_evidence_records(self) -> None:
        result = self.prepared((("one", GENERIC, "shop"),), 2)
        self.assertTrue(all(isinstance(item, CandidateRecordV1) for item in result.candidates))
        self.assertTrue(
            all(
                not isinstance(item, (ConstraintResultV1, CandidateEvidenceV1))
                for item in result.candidates
            )
        )

    def test_no_downstream_inputs_are_accepted(self) -> None:
        parameters = inspect.signature(prepare_hard_constraint_inputs).parameters
        for forbidden in (
            "rules",
            "thresholds",
            "prices",
            "resources",
            "ground_truth",
            "scores",
            "calibration",
            "review",
            "held_out",
        ):
            self.assertNotIn(forbidden, parameters)

    def test_reference_and_value_rules_follow_upstream_contracts(self) -> None:
        finalization = self.finalize(self.ranking())
        generation = self.generation(finalization)
        copied_method = deepcopy(generation.original.method_ready_field)
        object.__setattr__(generation.original, "method_ready_field", copied_method)
        result = prepare_hard_constraint_inputs(finalization_result=finalization)
        self.assertIs(result.method_ready_field, copied_method)
        self.assertEqual(
            result.method_ready_field,
            generation.suspicion_result.method_ready_field,
        )
        self.assertIsNot(
            result.method_ready_field,
            generation.suspicion_result.method_ready_field,
        )

    def test_mutated_source_image_identity_is_rejected(self) -> None:
        finalization = self.finalize(self.ranking())
        method = self.generation(finalization).original.method_ready_field
        object.__setattr__(method, "source_image_id", "forged:image")
        with self.assertRaises(HardConstraintInputIntegrityError):
            prepare_hard_constraint_inputs(finalization_result=finalization)

    def test_mutated_source_token_reference_is_rejected(self) -> None:
        finalization = self.finalize(self.ranking())
        method = self.generation(finalization).original.method_ready_field
        forged = replace(method.source_tokens[0], original_text="FORGED")
        object.__setattr__(
            method,
            "source_tokens",
            (forged, *method.source_tokens[1:]),
        )
        with self.assertRaises(HardConstraintInputIntegrityError):
            prepare_hard_constraint_inputs(finalization_result=finalization)

    def test_retained_candidates_are_shared_retained_records_only(self) -> None:
        result = self.prepared((("one", GENERIC, "shop"),), 2)
        self.assertIs(result.candidates[0].limit_status, CandidateLimitStatus.RETAINED)
        self.assertTrue(
            all(
                candidate.limit_status is CandidateLimitStatus.RETAINED
                for candidate in result.candidates[1:]
            )
        )

    def test_theta_a_is_derived_from_validated_limiting_configuration(self) -> None:
        result = self.prepared()
        self.assertIs(
            result.theta_a_ref,
            result.finalization_result.limiting_configuration.theta_a_ref,
        )
        self.assertEqual(
            result.theta_a_ref,
            self.generation(result.finalization_result).suspicion_result.theta_a_ref,
        )


if __name__ == "__main__":
    unittest.main()
