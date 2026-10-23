"""Synthetic adversarial tests for shared candidate finalization V0."""

from __future__ import annotations

import inspect
import unittest
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, replace
from decimal import Decimal
from unittest.mock import patch

from pipeline.proposed.candidate_deduplication import deduplicate_candidate_drafts
from pipeline.proposed.candidate_finalization import (
    CANDIDATE_FINALIZATION_COMPONENT_VERSION,
    CANDIDATE_FINALIZATION_RECORD_VERSION,
    SHARED_PROVENANCE_UNAVAILABLE,
    BlockedCandidateFinalizationAuditV0,
    CandidateFinalizationCoverageStatusV0,
    CandidateFinalizationCoverageV0,
    CandidateFinalizationIntegrityError,
    CandidateFinalizationReadinessV0,
    CandidateFinalizationResultV0,
    materialize_ranked_candidate_records,
)
from pipeline.proposed.candidate_generation import generate_candidate_drafts
from pipeline.proposed.candidate_identity import prepare_candidate_identities
from pipeline.proposed.candidate_limiting import (
    TOTAL_CANDIDATE_LIMIT_EXCEEDED,
    CandidateLimitDecisionStatusV0,
    CandidateLimitingConfigurationV0,
    apply_candidate_limit,
)
from pipeline.proposed.candidate_provenance import materialize_altered_provenance
from pipeline.proposed.candidate_ranking import (
    CandidateRankingConfigurationV0,
    ProvenanceMaterializationStatusV0,
    compute_preliminary_candidate_ranking,
)
from pipeline.proposed.contracts import (
    CandidateEvidenceV1,
    CandidateLimitStatus,
    CandidateRecordV1,
    CandidateRole,
    CandidateSourceKind,
)
from test_proposed_candidate_deduplication import _SyntheticCandidateFixture


GENERIC = CandidateSourceKind.GENERIC_NORMALIZATION
SOURCE = CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR


class ProposedCandidateFinalizationTests(unittest.TestCase):
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
    def configuration(ranking, candidate_limit: int = 2):
        return CandidateLimitingConfigurationV0(
            theta_a_ref=ranking.configuration.theta_a_ref,
            candidate_limit=candidate_limit,
            fixture_reference="synthetic:candidate-finalization:test-v0",
        )

    def limit(self, ranking, candidate_limit: int = 2):
        return apply_candidate_limit(
            ranking_result=ranking,
            configuration=self.configuration(ranking, candidate_limit),
        )

    def finalize(self, ranking, candidate_limit: int = 2):
        return materialize_ranked_candidate_records(
            limit_result=self.limit(ranking, candidate_limit)
        )

    def test_original_c0_is_preserved_by_reference(self) -> None:
        limit_result = self.limit(self.ranking((("one", GENERIC, "shop"),)), 2)
        result = materialize_ranked_candidate_records(limit_result=limit_result)
        self.assertIs(result.original_candidate, limit_result.original_candidate)
        self.assertIsNone(result.original_candidate.preliminary_rank)
        self.assertIs(result.original_candidate.role, CandidateRole.ORIGINAL)

    def test_empty_altered_set_is_complete_and_structurally_finalized(self) -> None:
        result = self.finalize(self.ranking(), 3)
        self.assertEqual((), result.retained_records)
        self.assertEqual((), result.overflow_records)
        self.assertIs(
            result.readiness,
            CandidateFinalizationReadinessV0.RETAINED_SET_STRUCTURALLY_FINALIZED,
        )
        self.assertIs(
            result.coverage.status,
            CandidateFinalizationCoverageStatusV0.COMPLETE_SHARED_LEDGER,
        )

    def test_one_retained_materialized_candidate(self) -> None:
        result = self.finalize(self.ranking((("one", GENERIC, "shop"),)), 2)
        self.assertEqual(1, len(result.retained_records))
        self.assertIs(
            result.retained_records[0].limit_status, CandidateLimitStatus.RETAINED
        )
        self.assertIsNone(result.retained_records[0].overflow_reason)

    def test_multiple_retained_candidates_preserve_rank_order(self) -> None:
        result = self.finalize(
            self.ranking(
                (("a", GENERIC, "pantry mars"), ("b", GENERIC, "shop"))
            ),
            3,
        )
        self.assertEqual(
            tuple(decision.candidate_id for decision in result.limit_result.decisions),
            tuple(record.candidate_id for record in result.retained_records),
        )

    def test_one_materialized_overflow_candidate(self) -> None:
        result = self.finalize(self.ranking((("one", GENERIC, "shop"),)), 1)
        self.assertEqual(1, len(result.overflow_records))
        record = result.overflow_records[0]
        self.assertIs(record.limit_status, CandidateLimitStatus.LIMIT_OVERFLOW)
        self.assertEqual(TOTAL_CANDIDATE_LIMIT_EXCEEDED, record.overflow_reason)

    def test_multiple_materialized_overflow_candidates(self) -> None:
        result = self.finalize(
            self.ranking(
                (
                    ("a", GENERIC, "pantry mars"),
                    ("b", GENERIC, "pantry shop"),
                    ("c", GENERIC, "shop"),
                )
            ),
            2,
        )
        self.assertEqual(2, len(result.overflow_records))
        self.assertTrue(
            all(
                record.overflow_reason == TOTAL_CANDIDATE_LIMIT_EXCEEDED
                for record in result.overflow_records
            )
        )

    def test_candidate_limit_one_keeps_only_c0_within_capacity(self) -> None:
        result = self.finalize(self.ranking((("one", GENERIC, "shop"),)), 1)
        self.assertEqual((), result.retained_records)
        self.assertEqual(1, len(result.overflow_records))
        self.assertIs(result.original_candidate.limit_status, CandidateLimitStatus.RETAINED)

    def test_candidate_and_c0_ids_are_exact(self) -> None:
        result = self.finalize(self.ranking((("one", GENERIC, "shop"),)), 2)
        decision = result.limit_result.decisions[0]
        record = result.retained_records[0]
        self.assertEqual(decision.candidate_id, record.candidate_id)
        self.assertEqual(result.original_candidate.candidate_id, record.c0_candidate_id)

    def test_normalized_key_is_exact(self) -> None:
        result = self.finalize(self.ranking((("one", GENERIC, "shop"),)), 2)
        self.assertEqual(
            result.limit_result.decisions[0].ranked_candidate.identity.normalized_dedup_key,
            result.retained_records[0].normalized_dedup_key,
        )

    def test_representative_display_value_is_exact(self) -> None:
        result = self.finalize(self.ranking((("one", GENERIC, "Pantry Shop"),)), 2)
        self.assertEqual(
            result.limit_result.decisions[0].ranked_candidate.identity.representative_value,
            result.retained_records[0].value,
        )

    def test_shared_rank_object_is_preserved_by_identity(self) -> None:
        result = self.finalize(self.ranking((("one", GENERIC, "shop"),)), 2)
        self.assertIs(
            result.retained_records[0].preliminary_rank,
            result.limit_result.decisions[0].ranked_candidate.preliminary_rank,
        )

    def test_multiple_shared_provenance_members_are_preserved(self) -> None:
        ranking = self.ranking(
            (
                ("source", SOURCE, "pantry shop"),
                ("generic", GENERIC, "pantry shop"),
            )
        )
        result = self.finalize(ranking, 2)
        self.assertEqual(2, len(result.retained_records[0].provenance))

    def test_canonical_provenance_order_and_member_references_are_preserved(self) -> None:
        result = self.finalize(
            self.ranking(
                (
                    ("generic", GENERIC, "pantry shop"),
                    ("source", SOURCE, "pantry shop"),
                )
            ),
            2,
        )
        source = result.limit_result.decisions[0].ranked_candidate.source_record
        expected = tuple(member.provenance for member in source.members)
        self.assertEqual(expected, result.retained_records[0].provenance)
        self.assertTrue(
            all(
                observed is original
                for observed, original in zip(
                    result.retained_records[0].provenance, expected, strict=True
                )
            )
        )

    def test_retained_provenance_blockage_blocks_readiness(self) -> None:
        result = self.finalize(
            self.ranking((("blocked", GENERIC, "shop"),), multi_provenance=True),
            2,
        )
        self.assertEqual((), result.retained_records)
        self.assertEqual(1, len(result.blocked_audits))
        self.assertIs(
            result.readiness,
            CandidateFinalizationReadinessV0.BLOCKED_BY_RETAINED_PROVENANCE,
        )

    def test_overflow_provenance_blockage_does_not_block_retained_readiness(self) -> None:
        result = self.finalize(
            self.mixed_materialized_and_blocked(blocked_first=False), 2
        )
        self.assertIs(
            result.readiness,
            CandidateFinalizationReadinessV0.RETAINED_SET_STRUCTURALLY_FINALIZED,
        )
        self.assertIs(
            result.coverage.status,
            CandidateFinalizationCoverageStatusV0.INCOMPLETE_BLOCKED_PROVENANCE,
        )
        self.assertEqual(1, len(result.blocked_audits))

    def test_partial_retained_materialization_is_diagnostic_only(self) -> None:
        result = self.finalize(
            self.mixed_materialized_and_blocked(blocked_first=True), 3
        )
        self.assertEqual(1, len(result.retained_records))
        self.assertIs(
            result.readiness,
            CandidateFinalizationReadinessV0.BLOCKED_BY_RETAINED_PROVENANCE,
        )

    def test_blocked_retained_candidate_is_not_backfilled(self) -> None:
        result = self.finalize(
            self.mixed_materialized_and_blocked(blocked_first=True), 2
        )
        self.assertEqual((), result.retained_records)
        self.assertEqual(1, len(result.overflow_records))
        self.assertEqual(
            result.limit_result.decisions[0].candidate_id,
            result.coverage.blocked_retained_candidate_ids[0],
        )

    def test_blocked_audit_preserves_exact_decision_and_source(self) -> None:
        result = self.finalize(
            self.ranking((("blocked", GENERIC, "shop"),), multi_provenance=True),
            2,
        )
        audit = result.blocked_audits[0]
        self.assertIs(audit.decision, result.limit_result.decisions[0])
        self.assertEqual(SHARED_PROVENANCE_UNAVAILABLE, audit.reason)
        self.assertIs(
            audit.decision.provenance_status,
            ProvenanceMaterializationStatusV0.BLOCKED,
        )

    def test_readiness_and_coverage_are_independent_for_blocked_overflow(self) -> None:
        result = self.finalize(
            self.mixed_materialized_and_blocked(blocked_first=False), 2
        )
        self.assertIs(
            result.readiness,
            CandidateFinalizationReadinessV0.RETAINED_SET_STRUCTURALLY_FINALIZED,
        )
        self.assertIs(
            result.coverage.status,
            CandidateFinalizationCoverageStatusV0.INCOMPLETE_BLOCKED_PROVENANCE,
        )

    def test_ranking_unavailable_is_distinct_from_empty_ready(self) -> None:
        empty = self.finalize(self.ranking(), 2)
        unavailable = self.finalize(self.ranking_blocked(), 2)
        self.assertIsNot(empty.readiness, unavailable.readiness)
        self.assertIsNot(empty.coverage.status, unavailable.coverage.status)

    def test_ranking_unavailable_constructs_no_altered_records_or_capacity_audits(self) -> None:
        result = self.finalize(self.ranking_blocked(), 2)
        self.assertEqual((), result.retained_records)
        self.assertEqual((), result.overflow_records)
        self.assertEqual((), result.blocked_audits)
        self.assertIs(
            result.readiness, CandidateFinalizationReadinessV0.RANKING_UNAVAILABLE
        )

    def test_ranking_unavailable_coverage_has_exact_blocked_ids(self) -> None:
        result = self.finalize(self.ranking_blocked(), 2)
        self.assertEqual(
            tuple(block.identity.candidate_id for block in result.ranking_blocks),
            result.coverage.ranking_blocked_candidate_ids,
        )
        self.assertTrue(
            all(
                observed is original
                for observed, original in zip(
                    result.ranking_blocks,
                    result.limit_result.ranking_blocks,
                    strict=True,
                )
            )
        )

    def test_duplicate_missing_and_reordered_shared_records_are_rejected(self) -> None:
        result = self.finalize(
            self.ranking(
                (("a", GENERIC, "pantry mars"), ("b", GENERIC, "shop"))
            ),
            3,
        )
        variants = (
            result.retained_records[:1],
            (result.retained_records[0], result.retained_records[0]),
            tuple(reversed(result.retained_records)),
        )
        for records in variants:
            with self.subTest(records=records), self.assertRaises(
                CandidateFinalizationIntegrityError
            ):
                replace(result, retained_records=records)

    def test_forged_candidate_role_is_rejected_on_reconstruction(self) -> None:
        result = self.finalize(self.ranking((("one", GENERIC, "shop"),)), 2)
        object.__setattr__(result.retained_records[0], "role", CandidateRole.ORIGINAL)
        with self.assertRaises(CandidateFinalizationIntegrityError):
            result.__post_init__()

    def test_forged_candidate_rank_is_rejected_on_reconstruction(self) -> None:
        result = self.finalize(self.ranking((("one", GENERIC, "shop"),)), 2)
        copied_rank = deepcopy(result.retained_records[0].preliminary_rank)
        object.__setattr__(result.retained_records[0], "preliminary_rank", copied_rank)
        with self.assertRaisesRegex(CandidateFinalizationIntegrityError, "rank object"):
            result.__post_init__()

    def test_forged_limit_status_is_rejected_on_reconstruction(self) -> None:
        result = self.finalize(self.ranking((("one", GENERIC, "shop"),)), 2)
        object.__setattr__(
            result.retained_records[0],
            "limit_status",
            CandidateLimitStatus.LIMIT_OVERFLOW,
        )
        with self.assertRaises(CandidateFinalizationIntegrityError):
            result.__post_init__()

    def test_forged_or_missing_overflow_reason_is_rejected(self) -> None:
        for reason in (None, "OTHER"):
            with self.subTest(reason=reason):
                result = self.finalize(self.ranking((("one", GENERIC, "shop"),)), 1)
                object.__setattr__(result.overflow_records[0], "overflow_reason", reason)
                with self.assertRaises(CandidateFinalizationIntegrityError):
                    result.__post_init__()

    def test_missing_canonical_provenance_member_is_rejected(self) -> None:
        result = self.finalize(
            self.ranking(
                (
                    ("source", SOURCE, "pantry shop"),
                    ("generic", GENERIC, "pantry shop"),
                )
            ),
            2,
        )
        object.__setattr__(
            result.retained_records[0],
            "provenance",
            result.retained_records[0].provenance[:1],
        )
        with self.assertRaises(CandidateFinalizationIntegrityError):
            result.__post_init__()

    def test_reordered_canonical_provenance_is_rejected(self) -> None:
        result = self.finalize(
            self.ranking(
                (
                    ("source", SOURCE, "pantry shop"),
                    ("generic", GENERIC, "pantry shop"),
                )
            ),
            2,
        )
        object.__setattr__(
            result.retained_records[0],
            "provenance",
            tuple(reversed(result.retained_records[0].provenance)),
        )
        with self.assertRaises(CandidateFinalizationIntegrityError):
            result.__post_init__()

    def test_forged_blocked_audit_is_rejected(self) -> None:
        materialized = self.limit(self.ranking((("one", GENERIC, "shop"),)), 2)
        with self.assertRaises(CandidateFinalizationIntegrityError):
            BlockedCandidateFinalizationAuditV0(decision=materialized.decisions[0])

    def test_duplicated_blocked_identity_is_rejected(self) -> None:
        result = self.finalize(
            self.ranking((("blocked", GENERIC, "shop"),), multi_provenance=True),
            2,
        )
        with self.assertRaises(CandidateFinalizationIntegrityError):
            replace(
                result,
                blocked_audits=(result.blocked_audits[0], result.blocked_audits[0]),
            )

    def test_changed_coverage_categories_are_rejected(self) -> None:
        result = self.finalize(self.ranking((("one", GENERIC, "shop"),)), 2)
        object.__setattr__(
            result.coverage,
            "retained_materialized_candidate_ids",
            (),
        )
        with self.assertRaises(CandidateFinalizationIntegrityError):
            result.__post_init__()

    def test_changed_coverage_status_is_rejected(self) -> None:
        result = self.finalize(self.ranking((("one", GENERIC, "shop"),)), 2)
        object.__setattr__(
            result.coverage,
            "status",
            CandidateFinalizationCoverageStatusV0.INCOMPLETE_BLOCKED_PROVENANCE,
        )
        with self.assertRaises(CandidateFinalizationIntegrityError):
            result.__post_init__()

    def test_changed_readiness_is_rejected(self) -> None:
        result = self.finalize(self.ranking((("one", GENERIC, "shop"),)), 2)
        object.__setattr__(
            result,
            "readiness",
            CandidateFinalizationReadinessV0.BLOCKED_BY_RETAINED_PROVENANCE,
        )
        with self.assertRaises(CandidateFinalizationIntegrityError):
            result.__post_init__()

    def test_mutated_synthetic_configuration_is_rejected_at_both_boundaries(self) -> None:
        for boundary in ("public", "aggregate"):
            with self.subTest(boundary=boundary):
                limit_result = self.limit(self.ranking(), 2)
                result = materialize_ranked_candidate_records(
                    limit_result=limit_result
                )
                object.__setattr__(limit_result.configuration, "scope_id", "production")
                with self.assertRaises(CandidateFinalizationIntegrityError):
                    if boundary == "public":
                        materialize_ranked_candidate_records(
                            limit_result=limit_result
                        )
                    else:
                        result.__post_init__()

    def test_equivalent_to_c0_audit_is_preserved_without_duplicate_record(self) -> None:
        limit_result = self.limit(
            self.ranking((("same", GENERIC, "pantry mart"),)), 2
        )
        result = materialize_ranked_candidate_records(limit_result=limit_result)
        self.assertIsNotNone(result.equivalent_to_c0)
        self.assertIs(result.equivalent_to_c0, limit_result.equivalent_to_c0)
        self.assertEqual((), result.retained_records)
        self.assertEqual((), result.overflow_records)

    def test_discovery_order_independence(self) -> None:
        specs = (
            ("a", GENERIC, "pantry mars"),
            ("b", GENERIC, "pantry shop"),
            ("c", GENERIC, "shop"),
        )
        first = self.finalize(self.ranking(specs), 2)
        second = self.finalize(self.ranking(tuple(reversed(specs))), 2)
        projection = lambda result: (
            tuple(record.candidate_id for record in result.retained_records),
            tuple(record.candidate_id for record in result.overflow_records),
            result.coverage,
        )
        self.assertEqual(projection(first), projection(second))

    def test_repeated_execution_is_deterministic_and_records_are_frozen(self) -> None:
        limit_result = self.limit(self.ranking((("one", GENERIC, "shop"),)), 2)
        first = materialize_ranked_candidate_records(limit_result=limit_result)
        second = materialize_ranked_candidate_records(limit_result=limit_result)
        self.assertEqual(first, second)
        with self.assertRaises(FrozenInstanceError):
            first.readiness = CandidateFinalizationReadinessV0.RANKING_UNAVAILABLE  # type: ignore[misc]

    def test_constructor_failure_is_wrapped_with_original_cause(self) -> None:
        limit_result = self.limit(self.ranking((("one", GENERIC, "shop"),)), 2)
        with patch(
            "pipeline.proposed.candidate_finalization.CandidateRecordV1",
            side_effect=ValueError("synthetic constructor failure"),
        ):
            with self.assertRaises(CandidateFinalizationIntegrityError) as caught:
                materialize_ranked_candidate_records(limit_result=limit_result)
        self.assertIsInstance(caught.exception.__cause__, ValueError)
        self.assertIn("synthetic constructor failure", str(caught.exception.__cause__))

    def test_public_api_is_keyword_only_and_has_one_input(self) -> None:
        signature = inspect.signature(materialize_ranked_candidate_records)
        self.assertEqual(("limit_result",), tuple(signature.parameters))
        self.assertIs(
            signature.parameters["limit_result"].kind,
            inspect.Parameter.KEYWORD_ONLY,
        )

    def test_public_api_does_not_rerun_public_upstream_components(self) -> None:
        limit_result = self.limit(self.ranking((("one", GENERIC, "shop"),)), 2)
        patches = (
            patch(
                "pipeline.proposed.candidate_generation.generate_candidate_drafts",
                side_effect=AssertionError("generation reran"),
            ),
            patch(
                "pipeline.proposed.candidate_deduplication.deduplicate_candidate_drafts",
                side_effect=AssertionError("deduplication reran"),
            ),
            patch(
                "pipeline.proposed.candidate_provenance.materialize_altered_provenance",
                side_effect=AssertionError("provenance reran"),
            ),
            patch(
                "pipeline.proposed.candidate_ranking.compute_preliminary_candidate_ranking",
                side_effect=AssertionError("ranking reran"),
            ),
            patch(
                "pipeline.proposed.candidate_limiting.apply_candidate_limit",
                side_effect=AssertionError("limiting reran"),
            ),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            result = materialize_ranked_candidate_records(limit_result=limit_result)
        self.assertEqual(1, len(result.retained_records))

    def test_outputs_contain_no_candidate_evidence(self) -> None:
        result = self.finalize(self.ranking((("one", GENERIC, "shop"),)), 2)
        outputs = (
            *result.retained_records,
            *result.overflow_records,
            *result.blocked_audits,
        )
        self.assertTrue(all(not isinstance(item, CandidateEvidenceV1) for item in outputs))

    def test_finalizer_has_no_deferred_method_inputs_or_outputs(self) -> None:
        source = inspect.getsource(materialize_ranked_candidate_records).lower()
        for forbidden in (
            "price",
            "constraint",
            "score",
            "calibration",
            "review",
            "persistence",
            "held_out",
        ):
            self.assertNotIn(forbidden, source)

    def test_versions_and_record_shapes_are_exact(self) -> None:
        result = self.finalize(self.ranking(), 2)
        self.assertEqual(
            CANDIDATE_FINALIZATION_COMPONENT_VERSION, result.component_version
        )
        self.assertEqual(CANDIDATE_FINALIZATION_RECORD_VERSION, result.record_version)
        self.assertEqual(
            CANDIDATE_FINALIZATION_RECORD_VERSION, result.coverage.record_version
        )
        names = {field.name for field in fields(CandidateFinalizationResultV0)}
        self.assertNotIn("original_candidate", names)
        self.assertNotIn("configuration", names)

    def test_mutated_candidate_value_id_and_key_are_rejected(self) -> None:
        mutations = (
            ("value", "forged value"),
            ("candidate_id", "forged:id"),
            ("normalized_dedup_key", "forged:key"),
            ("c0_candidate_id", "forged:c0"),
        )
        for field_name, value in mutations:
            with self.subTest(field=field_name):
                result = self.finalize(
                    self.ranking((("one", GENERIC, "shop"),)), 2
                )
                object.__setattr__(result.retained_records[0], field_name, value)
                with self.assertRaises(CandidateFinalizationIntegrityError):
                    result.__post_init__()

    def test_materialized_ids_are_derived_not_a_terminal_category(self) -> None:
        result = self.finalize(
            self.ranking(
                (("a", GENERIC, "pantry mars"), ("b", GENERIC, "shop"))
            ),
            2,
        )
        self.assertEqual(
            result.coverage.retained_materialized_candidate_ids
            + result.coverage.overflow_materialized_candidate_ids,
            result.coverage.materialized_candidate_ids,
        )

    def test_terminal_coverage_categories_are_disjoint_and_complete(self) -> None:
        result = self.finalize(
            self.mixed_materialized_and_blocked(blocked_first=True), 2
        )
        terminal = (
            result.coverage.retained_materialized_candidate_ids
            + result.coverage.overflow_materialized_candidate_ids
            + result.coverage.blocked_retained_candidate_ids
            + result.coverage.blocked_overflow_candidate_ids
        )
        upstream = tuple(
            decision.candidate_id for decision in result.limit_result.decisions
        )
        self.assertEqual(set(upstream), set(terminal))
        self.assertEqual(len(terminal), len(set(terminal)))

    def test_deepcopied_rank_reference_is_rejected_even_when_values_match(self) -> None:
        result = self.finalize(self.ranking((("one", GENERIC, "shop"),)), 2)
        copied = replace(
            result.retained_records[0],
            preliminary_rank=deepcopy(result.retained_records[0].preliminary_rank),
        )
        object.__setattr__(result, "retained_records", (copied,))
        with self.assertRaisesRegex(CandidateFinalizationIntegrityError, "rank object"):
            result.__post_init__()

    def test_deepcopied_provenance_reference_is_rejected_even_when_values_match(self) -> None:
        result = self.finalize(self.ranking((("one", GENERIC, "shop"),)), 2)
        copied = replace(
            result.retained_records[0],
            provenance=deepcopy(result.retained_records[0].provenance),
        )
        object.__setattr__(result, "retained_records", (copied,))
        with self.assertRaisesRegex(CandidateFinalizationIntegrityError, "provenance"):
            result.__post_init__()

    def test_limit_result_is_preserved_by_reference(self) -> None:
        limit_result = self.limit(self.ranking(), 2)
        result = materialize_ranked_candidate_records(limit_result=limit_result)
        self.assertIs(result.limit_result, limit_result)
        self.assertIs(result.boundary_tie_audit, limit_result.boundary_tie_audit)
        self.assertIs(result.limiting_configuration, limit_result.configuration)

    def test_invalid_finalization_versions_are_rejected(self) -> None:
        result = self.finalize(self.ranking(), 2)
        for name in ("component_version", "record_version"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                replace(result, **{name: "future-version"})
        with self.assertRaises(ValueError):
            replace(result.coverage, record_version="future-version")

    def test_coverage_rejects_overlapping_terminal_categories(self) -> None:
        with self.assertRaises(CandidateFinalizationIntegrityError):
            CandidateFinalizationCoverageV0(
                status=CandidateFinalizationCoverageStatusV0.INCOMPLETE_BLOCKED_PROVENANCE,
                materialized_candidate_ids=("candidate:a",),
                retained_materialized_candidate_ids=("candidate:a",),
                overflow_materialized_candidate_ids=(),
                blocked_retained_candidate_ids=("candidate:a",),
                blocked_overflow_candidate_ids=(),
                ranking_blocked_candidate_ids=(),
            )

    def test_numeric_configuration_mutation_is_rejected(self) -> None:
        for value in (True, 0, -1, 1.5, Decimal("2")):
            with self.subTest(value=value):
                limit_result = self.limit(self.ranking(), 2)
                object.__setattr__(limit_result.configuration, "candidate_limit", value)
                with self.assertRaises(CandidateFinalizationIntegrityError):
                    materialize_ranked_candidate_records(limit_result=limit_result)


if __name__ == "__main__":
    unittest.main()
