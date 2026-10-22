"""Synthetic adversarial tests for candidate limiting and overflow audit V0."""

from __future__ import annotations

import inspect
import unittest
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
from decimal import Decimal
from unittest.mock import patch

from pipeline.proposed.candidate_deduplication import deduplicate_candidate_drafts
from pipeline.proposed.candidate_generation import generate_candidate_drafts
from pipeline.proposed.candidate_identity import prepare_candidate_identities
from pipeline.proposed.candidate_limiting import (
    CANDIDATE_LIMITING_POLICY_ID,
    CANDIDATE_LIMITING_SCOPE_ID,
    CANDIDATE_LIMITING_TIE_POLICY_ID,
    TOTAL_CANDIDATE_LIMIT_EXCEEDED,
    BoundaryTieAuditV0,
    BoundaryTieStatusV0,
    CandidateLimitDecisionStatusV0,
    CandidateLimitResultV0,
    CandidateLimitingConfigurationV0,
    CandidateLimitingIntegrityError,
    CandidateLimitingReadinessV0,
    CandidateRetainedSetReadinessV0,
    apply_candidate_limit,
)
from pipeline.proposed.candidate_provenance import materialize_altered_provenance
from pipeline.proposed.candidate_ranking import (
    CandidateRankingConfigurationV0,
    CandidateRankingReadinessV0,
    ProvenanceMaterializationStatusV0,
    compute_preliminary_candidate_ranking,
)
from pipeline.proposed.contracts import (
    CandidateRecordV1,
    CandidateSourceKind,
    ConfigurationKind,
    ConfigurationState,
)
from test_proposed_candidate_deduplication import _SyntheticCandidateFixture


GENERIC = CandidateSourceKind.GENERIC_NORMALIZATION
SOURCE = CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR


class ProposedCandidateLimitingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = _SyntheticCandidateFixture()

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
        theta = drafts.suspicion_result.theta_a_ref
        return compute_preliminary_candidate_ranking(
            provenance_result=provenance,
            configuration=CandidateRankingConfigurationV0(theta_a_ref=theta),
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

    def configuration(self, ranking, candidate_limit: int = 2):
        return CandidateLimitingConfigurationV0(
            theta_a_ref=ranking.configuration.theta_a_ref,
            candidate_limit=candidate_limit,
            fixture_reference="synthetic:candidate-limiting:test-v0",
        )

    def limit(self, ranking, candidate_limit: int = 2):
        return apply_candidate_limit(
            ranking_result=ranking,
            configuration=self.configuration(ranking, candidate_limit),
        )

    @staticmethod
    def statuses(result):
        return tuple(item.status for item in result.decisions)

    def mixed_materialized_and_blocked(self, *, blocked_first: bool):
        def builder(_adapter, method):
            blocked_value = "pantry mars" if blocked_first else "pantry shop"
            materialized_value = "shop" if blocked_first else "pantry mars"
            blocked = self.fixture.seed(
                method,
                suffix="blocked",
                source_kind=GENERIC,
                proposed_value=blocked_value,
                event_ids=("event:blocked:a", "event:blocked:b"),
                rule_ids=("rule:blocked:a", "rule:blocked:b"),
            )
            materialized = self.fixture.seed(
                method,
                suffix="materialized",
                source_kind=GENERIC,
                proposed_value=materialized_value,
            )
            return blocked, materialized

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

    def test_candidate_limit_one_has_zero_altered_capacity(self) -> None:
        result = self.limit(
            self.ranking((("one", GENERIC, "pantry shop"),)), 1
        )
        self.assertEqual(0, result.altered_capacity)
        self.assertEqual(
            (CandidateLimitDecisionStatusV0.LIMIT_OVERFLOW,),
            self.statuses(result),
        )
        self.assertEqual(1, result.bounded_total_count)

    def test_empty_altered_set_is_structurally_ready(self) -> None:
        result = self.limit(self.ranking(), 3)
        self.assertEqual((), result.decisions)
        self.assertEqual(1, result.bounded_total_count)
        self.assertIs(
            result.retained_set_readiness,
            CandidateRetainedSetReadinessV0.STRUCTURALLY_READY,
        )

    def test_one_altered_candidate_is_within_capacity(self) -> None:
        result = self.limit(
            self.ranking((("one", GENERIC, "pantry shop"),)), 2
        )
        self.assertEqual(
            (CandidateLimitDecisionStatusV0.WITHIN_CAPACITY,),
            self.statuses(result),
        )
        self.assertIsNone(result.decisions[0].overflow_reason)

    def test_multiple_candidates_below_capacity_are_retained(self) -> None:
        ranking = self.ranking(
            (("a", GENERIC, "pantry mars"), ("b", GENERIC, "shop"))
        )
        result = self.limit(ranking, 4)
        self.assertEqual(2, result.within_capacity_count)
        self.assertEqual(0, result.overflow_count)

    def test_exactly_full_capacity_has_no_overflow(self) -> None:
        ranking = self.ranking(
            (("a", GENERIC, "pantry mars"), ("b", GENERIC, "shop"))
        )
        result = self.limit(ranking, 3)
        self.assertEqual(2, result.within_capacity_count)
        self.assertEqual(3, result.bounded_total_count)

    def test_one_candidate_beyond_capacity_overflows(self) -> None:
        ranking = self.ranking(
            (("a", GENERIC, "pantry mars"), ("b", GENERIC, "shop"))
        )
        result = self.limit(ranking, 2)
        self.assertEqual(
            (
                CandidateLimitDecisionStatusV0.WITHIN_CAPACITY,
                CandidateLimitDecisionStatusV0.LIMIT_OVERFLOW,
            ),
            self.statuses(result),
        )

    def test_multiple_overflow_candidates_remain_auditable(self) -> None:
        ranking = self.ranking(
            (
                ("a", GENERIC, "pantry mars"),
                ("b", GENERIC, "pantry shop"),
                ("c", GENERIC, "shop"),
            )
        )
        result = self.limit(ranking, 2)
        self.assertEqual(1, result.within_capacity_count)
        self.assertEqual(2, result.overflow_count)
        self.assertEqual(
            (TOTAL_CANDIDATE_LIMIT_EXCEEDED,) * 2,
            tuple(item.overflow_reason for item in result.decisions[1:]),
        )

    def test_boolean_limit_is_rejected(self) -> None:
        ranking = self.ranking()
        with self.assertRaisesRegex(ValueError, "non-Boolean integer"):
            self.configuration(ranking, True)  # type: ignore[arg-type]

    def test_other_invalid_limit_types_and_values_are_rejected(self) -> None:
        ranking = self.ranking()
        for value in (0, -1, 1.0, Decimal("1"), "1", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.configuration(ranking, value)  # type: ignore[arg-type]

    def test_strict_boundary_tie_is_split_without_expansion(self) -> None:
        ranking = self.ranking(
            (("a", GENERIC, "pantry mars"), ("b", GENERIC, "pantry mark"))
        )
        result = self.limit(ranking, 2)
        audit = result.boundary_tie_audit
        self.assertIs(audit.status, BoundaryTieStatusV0.TIE_GROUP_SPLIT)
        self.assertEqual(2, len(audit.member_candidate_ids))
        self.assertEqual(1, len(audit.within_capacity_candidate_ids))
        self.assertEqual(1, len(audit.overflow_candidate_ids))
        self.assertEqual(2, result.bounded_total_count)

    def test_tie_group_entirely_within_capacity_is_not_split(self) -> None:
        ranking = self.ranking(
            (("a", GENERIC, "pantry mars"), ("b", GENERIC, "pantry mark"))
        )
        result = self.limit(ranking, 3)
        self.assertIs(result.boundary_tie_audit.status, BoundaryTieStatusV0.NO_SPLIT)

    def test_tie_group_entirely_outside_capacity_is_not_split(self) -> None:
        ranking = self.ranking(
            (
                ("source", SOURCE, "shop"),
                ("a", GENERIC, "pantry mars"),
                ("b", GENERIC, "pantry mark"),
            )
        )
        result = self.limit(ranking, 2)
        self.assertIs(result.boundary_tie_audit.status, BoundaryTieStatusV0.NO_SPLIT)
        self.assertEqual(2, result.overflow_count)

    def test_candidate_limit_one_never_reports_a_boundary_split(self) -> None:
        ranking = self.ranking(
            (("a", GENERIC, "pantry mars"), ("b", GENERIC, "pantry mark"))
        )
        result = self.limit(ranking, 1)
        self.assertIs(result.boundary_tie_audit.status, BoundaryTieStatusV0.NO_SPLIT)

    def test_stored_normalized_text_and_candidate_id_order_is_preserved(self) -> None:
        ranking = self.ranking(
            (("b", GENERIC, "pantry mark"), ("a", GENERIC, "pantry mars"))
        )
        result = self.limit(ranking, 3)
        self.assertEqual(
            tuple(item.identity.candidate_id for item in ranking.ranked_candidates),
            tuple(item.candidate_id for item in result.decisions),
        )
        self.assertTrue(
            all(
                decision.ranked_candidate is ranked
                for decision, ranked in zip(
                    result.decisions, ranking.ranked_candidates, strict=True
                )
            )
        )

    def test_materialized_retained_candidate_is_structurally_ready(self) -> None:
        result = self.limit(
            self.ranking((("one", GENERIC, "pantry shop"),)), 2
        )
        self.assertIs(
            result.decisions[0].provenance_status,
            ProvenanceMaterializationStatusV0.MATERIALIZED,
        )
        self.assertIs(
            result.retained_set_readiness,
            CandidateRetainedSetReadinessV0.STRUCTURALLY_READY,
        )

    def test_provenance_blocked_retained_candidate_blocks_readiness(self) -> None:
        ranking = self.ranking(
            (("blocked", GENERIC, "pantry shop"),), multi_provenance=True
        )
        result = self.limit(ranking, 2)
        self.assertIs(
            result.decisions[0].provenance_status,
            ProvenanceMaterializationStatusV0.BLOCKED,
        )
        self.assertIs(
            result.retained_set_readiness,
            CandidateRetainedSetReadinessV0.BLOCKED_BY_SELECTED_PROVENANCE,
        )

    def test_provenance_blocked_overflow_preserves_both_facts(self) -> None:
        result = self.limit(
            self.mixed_materialized_and_blocked(blocked_first=False), 2
        )
        blocked = next(
            item
            for item in result.decisions
            if item.provenance_status is ProvenanceMaterializationStatusV0.BLOCKED
        )
        self.assertIs(
            blocked.status, CandidateLimitDecisionStatusV0.LIMIT_OVERFLOW
        )
        self.assertEqual(TOTAL_CANDIDATE_LIMIT_EXCEEDED, blocked.overflow_reason)
        self.assertIs(
            result.retained_set_readiness,
            CandidateRetainedSetReadinessV0.STRUCTURALLY_READY,
        )

    def test_blocked_retained_candidate_is_not_backfilled(self) -> None:
        result = self.limit(
            self.mixed_materialized_and_blocked(blocked_first=True), 2
        )
        self.assertIs(
            result.decisions[0].provenance_status,
            ProvenanceMaterializationStatusV0.BLOCKED,
        )
        self.assertIs(
            result.decisions[0].status,
            CandidateLimitDecisionStatusV0.WITHIN_CAPACITY,
        )
        self.assertIs(
            result.decisions[1].status,
            CandidateLimitDecisionStatusV0.LIMIT_OVERFLOW,
        )

    def test_all_candidates_can_be_provenance_blocked_but_rankable(self) -> None:
        ranking = self.ranking(
            (("a", GENERIC, "pantry mars"), ("b", GENERIC, "shop")),
            multi_provenance=True,
        )
        result = self.limit(ranking, 2)
        self.assertTrue(
            all(
                item.provenance_status is ProvenanceMaterializationStatusV0.BLOCKED
                for item in result.decisions
            )
        )
        self.assertIs(
            result.retained_set_readiness,
            CandidateRetainedSetReadinessV0.BLOCKED_BY_SELECTED_PROVENANCE,
        )

    def test_valid_ranking_blocked_aggregate_returns_unavailable_audit(self) -> None:
        ranking = self.ranking_blocked()
        self.assertIs(
            ranking.readiness, CandidateRankingReadinessV0.RANKING_BLOCKED
        )
        result = self.limit(ranking, 2)
        self.assertIs(
            result.readiness, CandidateLimitingReadinessV0.RANKING_UNAVAILABLE
        )
        self.assertEqual(ranking.ranking_blocks, result.ranking_blocks)
        self.assertIs(
            result.boundary_tie_audit.status,
            BoundaryTieStatusV0.RANKING_UNAVAILABLE,
        )

    def test_ranking_unavailable_has_no_limit_decisions_or_count(self) -> None:
        result = self.limit(self.ranking_blocked(), 7)
        self.assertEqual((), result.decisions)
        self.assertIsNone(result.bounded_total_count)
        self.assertIs(
            result.retained_set_readiness,
            CandidateRetainedSetReadinessV0.RANKING_UNAVAILABLE,
        )

    def test_incorrect_theta_reference_is_rejected(self) -> None:
        ranking = self.ranking()
        wrong_theta = replace(
            ranking.configuration.theta_a_ref,
            configuration_version="wrong-version",
            content_hash="sha256:wrong",
        )
        configuration = CandidateLimitingConfigurationV0(
            theta_a_ref=wrong_theta,
            candidate_limit=1,
            fixture_reference="synthetic:wrong-theta",
        )
        with self.assertRaisesRegex(CandidateLimitingIntegrityError, "Theta_A"):
            apply_candidate_limit(
                ranking_result=ranking, configuration=configuration
            )

    def test_ready_theta_does_not_claim_limit_authentication(self) -> None:
        ranking = self.ranking()
        configuration = self.configuration(ranking, 1)
        names = {item.name for item in fields(configuration)}
        self.assertEqual(CANDIDATE_LIMITING_SCOPE_ID, configuration.scope_id)
        self.assertFalse(
            names.intersection({"authenticated", "manifest_verified", "production_ready"})
        )

    def test_unsupported_scope_policy_and_versions_are_rejected(self) -> None:
        configuration = self.configuration(self.ranking(), 1)
        mutations = (
            {"scope_id": "production"},
            {"limiting_policy_id": "other-policy"},
            {"tie_policy_id": "other-tie-policy"},
            {"component_version": "future-component"},
            {"record_version": "future-record"},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                replace(configuration, **mutation)

    def test_forged_capacity_status_is_rejected_by_aggregate(self) -> None:
        result = self.limit(
            self.ranking((("one", GENERIC, "pantry shop"),)), 2
        )
        forged = replace(
            result.decisions[0],
            status=CandidateLimitDecisionStatusV0.LIMIT_OVERFLOW,
            overflow_reason=TOTAL_CANDIDATE_LIMIT_EXCEEDED,
        )
        with self.assertRaises(CandidateLimitingIntegrityError):
            replace(result, decisions=(forged,))

    def test_incorrect_overflow_reason_is_rejected(self) -> None:
        result = self.limit(
            self.ranking((("one", GENERIC, "pantry shop"),)), 1
        )
        with self.assertRaisesRegex(ValueError, "approved overflow reason"):
            replace(result.decisions[0], overflow_reason="OTHER_REASON")

    def test_missing_duplicate_and_reordered_identities_are_rejected(self) -> None:
        ranking = self.ranking(
            (("a", GENERIC, "pantry mars"), ("b", GENERIC, "shop"))
        )
        result = self.limit(ranking, 3)
        variants = (
            result.decisions[:1],
            (result.decisions[0], result.decisions[0]),
            tuple(reversed(result.decisions)),
        )
        for decisions in variants:
            with self.subTest(decisions=decisions), self.assertRaises(
                CandidateLimitingIntegrityError
            ):
                replace(result, decisions=decisions)

    def test_forged_boundary_tie_audit_is_rejected(self) -> None:
        ranking = self.ranking(
            (("a", GENERIC, "pantry mars"), ("b", GENERIC, "pantry mark"))
        )
        result = self.limit(ranking, 2)
        forged = BoundaryTieAuditV0(
            status=BoundaryTieStatusV0.NO_SPLIT,
            candidate_limit=2,
            altered_capacity=1,
        )
        with self.assertRaises(CandidateLimitingIntegrityError):
            replace(result, boundary_tie_audit=forged)

    def test_changed_retained_set_readiness_is_rejected(self) -> None:
        result = self.limit(
            self.ranking((("one", GENERIC, "pantry shop"),)), 2
        )
        with self.assertRaises(CandidateLimitingIntegrityError):
            replace(
                result,
                retained_set_readiness=(
                    CandidateRetainedSetReadinessV0.BLOCKED_BY_SELECTED_PROVENANCE
                ),
            )

    def test_repeated_execution_is_identical_and_records_are_frozen(self) -> None:
        ranking = self.ranking(
            (("a", GENERIC, "pantry mars"), ("b", GENERIC, "shop"))
        )
        configuration = self.configuration(ranking, 2)
        first = apply_candidate_limit(
            ranking_result=ranking, configuration=configuration
        )
        second = apply_candidate_limit(
            ranking_result=ranking, configuration=configuration
        )
        self.assertEqual(first, second)
        with self.assertRaises(FrozenInstanceError):
            first.decisions = ()  # type: ignore[misc]

    def test_discovery_order_independence_is_inherited_from_ranking(self) -> None:
        specs = (
            ("a", GENERIC, "pantry mars"),
            ("b", GENERIC, "pantry shop"),
            ("c", GENERIC, "shop"),
        )
        first = self.limit(self.ranking(specs), 2)
        second = self.limit(self.ranking(tuple(reversed(specs))), 2)
        projection = lambda result: tuple(
            (item.candidate_id, item.status, item.overflow_reason)
            for item in result.decisions
        )
        self.assertEqual(projection(first), projection(second))

    def test_original_c0_is_preserved_unchanged_and_by_reference(self) -> None:
        ranking = self.ranking((("one", GENERIC, "pantry shop"),))
        result = self.limit(ranking, 2)
        self.assertIs(ranking.original_candidate, result.original_candidate)
        self.assertIsNone(result.original_candidate.preliminary_rank)
        with self.assertRaises(CandidateLimitingIntegrityError):
            replace(result, original_candidate=deepcopy(result.original_candidate))

    def test_c0_equivalence_audit_is_preserved_by_reference(self) -> None:
        ranking = self.ranking((("same", GENERIC, "pantry mart"),))
        self.assertIsNotNone(ranking.equivalent_to_c0)
        result = self.limit(ranking, 1)
        self.assertIs(ranking.equivalent_to_c0, result.equivalent_to_c0)
        with self.assertRaises(CandidateLimitingIntegrityError):
            replace(result, equivalent_to_c0=deepcopy(result.equivalent_to_c0))

    def test_no_altered_shared_candidate_record_is_materialized(self) -> None:
        result = self.limit(
            self.ranking((("one", GENERIC, "pantry shop"),)), 2
        )
        self.assertTrue(
            all(not isinstance(item, CandidateRecordV1) for item in result.decisions)
        )
        self.assertIsInstance(result.original_candidate, CandidateRecordV1)

    def test_component_does_not_invoke_public_ranking_or_upstream_pipelines(self) -> None:
        ranking = self.ranking((("one", GENERIC, "pantry shop"),))
        configuration = self.configuration(ranking, 2)
        with patch(
            "pipeline.proposed.candidate_ranking.compute_preliminary_candidate_ranking",
            side_effect=AssertionError("ranking must not rerun"),
        ):
            result = apply_candidate_limit(
                ranking_result=ranking, configuration=configuration
            )
        self.assertEqual(1, len(result.decisions))

    def test_public_api_has_no_future_or_forbidden_inputs(self) -> None:
        self.assertEqual(
            ("ranking_result", "configuration"),
            tuple(inspect.signature(apply_candidate_limit).parameters),
        )
        self.assertTrue(
            all(
                parameter.kind is inspect.Parameter.KEYWORD_ONLY
                for parameter in inspect.signature(
                    apply_candidate_limit
                ).parameters.values()
            )
        )
        source = inspect.getsource(apply_candidate_limit)
        for forbidden in (
            "ocr",
            "b2",
            "b3",
            "candidate_evidence",
            "price_reference",
            "constraint_result",
            "score",
            "calibration",
            "review",
            "held_out",
        ):
            self.assertNotIn(forbidden, source.lower())

    def test_malformed_ranking_input_is_an_integrity_failure(self) -> None:
        ranking = self.ranking((("one", GENERIC, "pantry shop"),))
        object.__setattr__(ranking.ranked_candidates[0].preliminary_rank, "rank_position", 2)
        with self.assertRaises(CandidateLimitingIntegrityError):
            self.limit(ranking, 2)

    def test_policy_identifiers_are_exact(self) -> None:
        configuration = self.configuration(self.ranking(), 1)
        self.assertEqual(
            CANDIDATE_LIMITING_POLICY_ID, configuration.limiting_policy_id
        )
        self.assertEqual(
            CANDIDATE_LIMITING_TIE_POLICY_ID, configuration.tie_policy_id
        )

    def test_ranking_unavailable_preserves_exact_block_references(self) -> None:
        ranking = self.ranking_blocked()
        result = self.limit(ranking, 2)
        self.assertTrue(
            all(
                observed is original
                for observed, original in zip(
                    result.ranking_blocks, ranking.ranking_blocks, strict=True
                )
            )
        )

    def test_configuration_fixture_reference_is_diagnostic_and_required(self) -> None:
        ranking = self.ranking()
        with self.assertRaisesRegex(ValueError, "fixture_reference"):
            CandidateLimitingConfigurationV0(
                theta_a_ref=ranking.configuration.theta_a_ref,
                candidate_limit=1,
                fixture_reference=" ",
            )

    def test_mutated_configuration_is_rejected_by_public_api(self) -> None:
        mutations = (
            ("scope_id", "production"),
            ("limiting_policy_id", "other-policy"),
            ("tie_policy_id", "other-tie-policy"),
            ("component_version", "future-component"),
            ("record_version", "future-record"),
            ("fixture_reference", " "),
            ("candidate_limit", True),
            ("candidate_limit", 0),
            ("candidate_limit", -1),
            ("candidate_limit", 1.5),
            ("candidate_limit", Decimal("1")),
            ("candidate_limit", "1"),
        )
        for field_name, invalid_value in mutations:
            with self.subTest(field=field_name, value=invalid_value):
                ranking = self.ranking()
                configuration = self.configuration(ranking, 2)
                object.__setattr__(configuration, field_name, invalid_value)
                with self.assertRaisesRegex(
                    CandidateLimitingIntegrityError,
                    "configuration failed",
                ):
                    apply_candidate_limit(
                        ranking_result=ranking,
                        configuration=configuration,
                    )

    def test_mutated_configuration_is_rejected_by_result_reconstruction(self) -> None:
        mutations = (
            ("scope_id", "production"),
            ("limiting_policy_id", "other-policy"),
            ("tie_policy_id", "other-tie-policy"),
            ("component_version", "future-component"),
            ("record_version", "future-record"),
            ("fixture_reference", ""),
            ("candidate_limit", False),
            ("candidate_limit", 0),
            ("candidate_limit", -5),
            ("candidate_limit", 2.0),
            ("candidate_limit", Decimal("2")),
            ("candidate_limit", None),
        )
        for field_name, invalid_value in mutations:
            with self.subTest(field=field_name, value=invalid_value):
                result = self.limit(self.ranking(), 2)
                object.__setattr__(result.configuration, field_name, invalid_value)
                with self.assertRaisesRegex(
                    CandidateLimitingIntegrityError,
                    "configuration failed",
                ):
                    result.__post_init__()

    def test_mutated_theta_invariants_are_rejected_at_both_boundaries(self) -> None:
        theta_mutations = (
            ("kind", ConfigurationKind.KAPPA),
            ("state", ConfigurationState.NOT_READY),
            ("content_hash", " "),
            ("configuration_id", " "),
            ("configuration_version", ""),
            ("status_reason", "forged ready-state reason"),
            ("record_version", "future-configuration-ref"),
        )
        for field_name, invalid_value in theta_mutations:
            for boundary in ("public_api", "aggregate"):
                with self.subTest(
                    field=field_name,
                    value=invalid_value,
                    boundary=boundary,
                ):
                    ranking = self.ranking()
                    result = self.limit(ranking, 2)
                    object.__setattr__(
                        result.configuration.theta_a_ref,
                        field_name,
                        invalid_value,
                    )
                    with self.assertRaisesRegex(
                        CandidateLimitingIntegrityError,
                        "configuration failed",
                    ):
                        if boundary == "public_api":
                            apply_candidate_limit(
                                ranking_result=ranking,
                                configuration=result.configuration,
                            )
                        else:
                            result.__post_init__()

    def test_result_preserves_complete_upstream_ranking_result(self) -> None:
        ranking = self.ranking((("one", GENERIC, "pantry shop"),))
        result = self.limit(ranking, 2)
        self.assertIs(ranking, result.ranking_result)
        self.assertIs(
            result.decisions[0].ranked_candidate.source_record,
            ranking.ranked_candidates[0].source_record,
        )


if __name__ == "__main__":
    unittest.main()
