"""Synthetic adversarial tests for preliminary candidate ranking V0."""

from __future__ import annotations

import hashlib
import inspect
import json
import unittest
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, ROUND_DOWN, getcontext, localcontext
from unittest.mock import patch

import pipeline.proposed.candidate_ranking as candidate_ranking
from pipeline.contracts import ReceiptFieldName
from pipeline.proposed.candidate_deduplication import deduplicate_candidate_drafts
from pipeline.proposed.candidate_generation import generate_candidate_drafts
from pipeline.proposed.candidate_identity import prepare_candidate_identities
from pipeline.proposed.candidate_provenance import materialize_altered_provenance
from pipeline.proposed.candidate_ranking import (
    CANDIDATE_RANKING_PROFILE_ID,
    TIE_GROUP_ID_PREFIX,
    TIE_IDENTITY_SCHEMA_VERSION,
    CandidateRankingBlockReasonV0,
    CandidateRankingConfigurationV0,
    CandidateRankingIntegrityError,
    CandidateRankingReadinessV0,
    DisplacementAvailabilityV0,
    ProvenanceMaterializationStatusV0,
    compute_preliminary_candidate_ranking,
)
from pipeline.proposed.contracts import (
    CandidateRecordV1,
    CandidateSourceKind,
    ConfigurationKind,
    ConfigurationRefV1,
    ConfigurationState,
    SourceCharacterSpanV1,
)
from test_proposed_candidate_deduplication import _SyntheticCandidateFixture


class ProposedCandidateRankingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = _SyntheticCandidateFixture()

    def provenance(
        self,
        specs: tuple[tuple[str, CandidateSourceKind, str], ...] = (),
        *,
        multi_provenance: bool = False,
        field_name: ReceiptFieldName = ReceiptFieldName.STORE_NAME,
    ):
        drafts = self.fixture.drafts(
            field_name=field_name,
            seed_specs=specs,
            multi_provenance=multi_provenance,
        )
        return materialize_altered_provenance(
            identity_preparation=prepare_candidate_identities(
                deduplication_result=deduplicate_candidate_drafts(
                    candidate_drafts=drafts
                )
            )
        )

    def provenance_from_builder(
        self,
        builder,
        *,
        field_name: ReceiptFieldName = ReceiptFieldName.STORE_NAME,
    ):
        adapter, method = self.fixture.adapter_and_method(field_name)
        seeds = builder(adapter, method)
        adapter, method = self.fixture.with_seeds(adapter, method, seeds)
        drafts = generate_candidate_drafts(
            suspicion_result=self.fixture.suspicion(method),
            adapter_result=adapter,
        )
        return materialize_altered_provenance(
            identity_preparation=prepare_candidate_identities(
                deduplication_result=deduplicate_candidate_drafts(
                    candidate_drafts=drafts
                )
            )
        )

    def configuration(self, provenance):
        theta = (
            provenance.identity_preparation.deduplication_result
            .candidate_drafts.suspicion_result.theta_a_ref
        )
        return CandidateRankingConfigurationV0(theta_a_ref=theta)

    def rank(self, provenance):
        return compute_preliminary_candidate_ranking(
            provenance_result=provenance,
            configuration=self.configuration(provenance),
        )

    def source_span(self, adapter, token_id: str, start: int = 0, end: int = 3):
        output = adapter.original_b2_result.receipt_output
        assert output is not None
        token = next(
            item for item in output.source_evidence.tokens if item.token_id == token_id
        )
        end = min(end, len(token.original_text))
        return SourceCharacterSpanV1(
            token_id=token_id,
            start=start,
            end=end,
            text=token.original_text[start:end],
        )

    def test_exact_c0_is_preserved_by_reference_and_never_ranked(self) -> None:
        provenance = self.provenance(
            (("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
        )
        result = self.rank(provenance)
        self.assertIs(provenance.original_candidate, result.original_candidate)
        self.assertIs(provenance.equivalent_to_c0, result.equivalent_to_c0)
        self.assertIsNone(result.original_candidate.preliminary_rank)
        self.assertNotIn(
            result.original_candidate.candidate_id,
            {item.identity.candidate_id for item in result.ranked_candidates},
        )

    def test_empty_altered_set_is_ready_and_deterministic(self) -> None:
        provenance = self.provenance()
        first = self.rank(provenance)
        second = self.rank(provenance)
        self.assertIs(first.readiness, CandidateRankingReadinessV0.READY)
        self.assertEqual((), first.ranked_candidates)
        self.assertEqual((), first.ranking_blocks)
        self.assertEqual(first, second)

    def test_one_and_multiple_altered_candidates_receive_unique_positions(self) -> None:
        one = self.rank(
            self.provenance(
                (("one", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
            )
        )
        self.assertEqual((1,), tuple(
            item.preliminary_rank.rank_position for item in one.ranked_candidates
        ))
        many = self.rank(
            self.provenance(
                (
                    ("a", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),
                    ("b", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry market"),
                    ("c", CandidateSourceKind.GENERIC_NORMALIZATION, "shop"),
                )
            )
        )
        self.assertEqual((1, 2, 3), tuple(
            item.preliminary_rank.rank_position for item in many.ranked_candidates
        ))

    def test_source_priority_overrides_edit_similarity(self) -> None:
        result = self.rank(
            self.provenance(
                (
                    ("close", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry mars"),
                    ("far", CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR, "zzzzzz"),
                )
            )
        )
        self.assertEqual(
            CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
            result.ranked_candidates[0].source_audit.contributions[0].source_kind,
        )
        self.assertLess(
            result.ranked_candidates[0].similarity.decimal_value,
            result.ranked_candidates[1].similarity.decimal_value,
        )

    def test_equal_priority_uses_descending_exact_similarity(self) -> None:
        result = self.rank(
            self.provenance(
                (
                    ("far", CandidateSourceKind.GENERIC_NORMALIZATION, "shop"),
                    ("close", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry mars"),
                )
            )
        )
        self.assertEqual(
            "pantry mars",
            result.ranked_candidates[0].preliminary_rank.normalized_candidate_text,
        )

    def test_exact_ratios_sort_when_34_digit_decimals_are_equal(self) -> None:
        scale = 10**40
        better = (scale - 1, scale)
        worse = (scale - 2, scale - 1)
        self.assertEqual(
            candidate_ranking._decimal_from_fraction(*better),
            candidate_ranking._decimal_from_fraction(*worse),
        )
        left = (2, *better, 0, "same", "candidate:a")
        right = (2, *worse, 0, "same", "candidate:b")
        self.assertLess(candidate_ranking._compare_rank_components(left, right), 0)

    def test_decimal_serialization_ignores_ambient_context(self) -> None:
        provenance = self.provenance(
            (("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
        )
        expected = self.rank(provenance)
        ambient_precision = getcontext().prec
        ambient_rounding = getcontext().rounding
        with localcontext() as context:
            context.prec = 2
            context.rounding = ROUND_DOWN
            observed = self.rank(provenance)
        self.assertEqual(
            expected.ranked_candidates[0].similarity.decimal_value,
            observed.ranked_candidates[0].similarity.decimal_value,
        )
        self.assertEqual(ambient_precision, getcontext().prec)
        self.assertEqual(ambient_rounding, getcontext().rounding)

    def test_levenshtein_uses_unicode_code_points(self) -> None:
        self.assertEqual(
            2,
            candidate_ranking._levenshtein_distance("é", "e\u0301"),
        )
        self.assertEqual(1, candidate_ranking._levenshtein_distance("👩‍💻", "👩‍💼"))

    def test_empty_normalized_text_is_an_integrity_failure(self) -> None:
        provenance = self.provenance(
            (("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
        )
        normalization = (
            provenance.identity_preparation.altered_candidates[0]
            .identity.deduplicated_group.normalization
        )
        object.__setattr__(normalization, "canonical_value", "")
        with self.assertRaises(CandidateRankingIntegrityError):
            self.rank(provenance)

    def test_same_source_token_has_zero_displacement(self) -> None:
        result = self.rank(
            self.provenance(
                (("source", CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR, "shop"),)
            )
        )
        audit = result.ranked_candidates[0].displacement
        self.assertEqual(("store",), audit.supporting_token_ids)
        self.assertEqual(0, audit.displacement)

    def test_neighbours_before_and_after_c0_use_receipt_token_order(self) -> None:
        def builder(adapter, method):
            before = self.source_span(adapter, "date-label")
            after = self.source_span(adapter, "description")
            return (
                self.fixture.seed(
                    method,
                    suffix="before",
                    source_kind=CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
                    proposed_value="12/10/2026",
                    spans=(before,),
                ),
                self.fixture.seed(
                    method,
                    suffix="after",
                    source_kind=CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
                    proposed_value="14/10/2026",
                    spans=(after,),
                ),
            )

        result = self.rank(
            self.provenance_from_builder(
                builder, field_name=ReceiptFieldName.PURCHASE_DATE
            )
        )
        self.assertEqual(
            {1}, {item.displacement.displacement for item in result.ranked_candidates}
        )
        self.assertEqual(
            {"date-label", "description"},
            {
                item.displacement.supporting_token_ids[0]
                for item in result.ranked_candidates
            },
        )

    def test_multiple_c0_tokens_use_minimum_genuine_distance(self) -> None:
        adapter, method = self.fixture.adapter_and_method()
        output = adapter.original_b2_result.receipt_output
        assert output is not None
        token_by_id = {item.token_id: item for item in output.source_evidence.tokens}
        c0_ids = ("store", "date-label")
        original = replace(method.original_b2_field, source_token_ids=c0_ids)
        updated_output = replace(output, store_name=original)
        updated_b2 = replace(adapter.original_b2_result, receipt_output=updated_output)
        method = replace(
            method,
            original_b2_field=original,
            source_token_ids=c0_ids,
            source_tokens=tuple(token_by_id[item] for item in c0_ids),
        )
        span = self.source_span(adapter, "description")
        seed = self.fixture.seed(
            method,
            suffix="multi-c0",
            source_kind=CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
            proposed_value="pantry shop",
            spans=(span,),
        )
        method = replace(method, b3_seed_ids=(seed.seed_id,))
        methods = tuple(
            method if item.field_id == method.field_id else item
            for item in adapter.method_ready_fields
        )
        adapter = replace(
            adapter,
            original_b2_result=updated_b2,
            method_ready_fields=methods,
            b3_seeds=(seed,) + tuple(
                item for item in adapter.b3_seeds if item.field_id != method.field_id
            ),
        )
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
        audit = self.rank(provenance).ranked_candidates[0].displacement
        self.assertEqual(c0_ids, audit.c0_token_ids)
        self.assertEqual((0, 1), audit.c0_token_positions)
        self.assertEqual(2, audit.displacement)

    def test_neighbour_outside_c0_tokens_is_supported(self) -> None:
        def builder(adapter, method):
            span = self.source_span(adapter, "date-label")
            return (
                self.fixture.seed(
                    method,
                    suffix="outside",
                    source_kind=CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
                    proposed_value="pantry shop",
                    spans=(span,),
                ),
            )

        result = self.rank(self.provenance_from_builder(builder))
        audit = result.ranked_candidates[0].displacement
        self.assertNotIn("date-label", audit.c0_token_ids)
        self.assertEqual(("date-label",), audit.supporting_token_ids)
        self.assertEqual(1, audit.displacement)

    def test_multiple_best_priority_contributions_use_all_genuine_positions(self) -> None:
        def builder(adapter, method):
            return tuple(
                self.fixture.seed(
                    method,
                    suffix=suffix,
                    source_kind=CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
                    proposed_value=value,
                    spans=(self.source_span(adapter, token_id),),
                )
                for suffix, value, token_id in (
                    ("far", "pantry shop", "description"),
                    ("near", "ＰＡＮＴＲＹ SHOP", "date-label"),
                )
            )

        audit = self.rank(self.provenance_from_builder(builder)).ranked_candidates[0]
        self.assertEqual(("date-label", "description"), audit.displacement.supporting_token_ids)
        self.assertEqual(1, audit.displacement.displacement)

    def test_lower_priority_evidence_cannot_improve_displacement(self) -> None:
        def builder(adapter, method):
            source = self.fixture.seed(
                method,
                suffix="source",
                source_kind=CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
                proposed_value="pantry shop",
                spans=(self.source_span(adapter, "date-value"),),
            )
            generic = self.fixture.seed(
                method,
                suffix="generic",
                source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
                proposed_value="ＰＡＮＴＲＹ SHOP",
            )
            return source, generic

        ranked = self.rank(self.provenance_from_builder(builder)).ranked_candidates[0]
        self.assertEqual(1, ranked.best_source_priority)
        self.assertEqual(2, ranked.displacement.displacement)

    def test_generic_without_spans_uses_documented_c0_anchored_zero(self) -> None:
        result = self.rank(
            self.provenance(
                (("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
            )
        )
        audit = result.ranked_candidates[0].displacement
        self.assertIs(audit.source_kind, CandidateSourceKind.GENERIC_NORMALIZATION)
        self.assertEqual((), audit.supporting_token_ids)
        self.assertEqual(0, audit.displacement)

    def test_composite_generic_provenance_is_blocked_but_rankable(self) -> None:
        provenance = self.provenance(
            (("composite", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),),
            multi_provenance=True,
        )
        self.assertEqual(1, len(provenance.blocked_candidates))
        result = self.rank(provenance)
        self.assertIs(result.readiness, CandidateRankingReadinessV0.READY)
        self.assertIs(
            result.ranked_candidates[0].provenance_status,
            ProvenanceMaterializationStatusV0.BLOCKED,
        )

    def test_multiple_source_spans_are_provenance_blocked_but_rankable(self) -> None:
        def builder(adapter, method):
            token = method.source_tokens[0]
            midpoint = max(1, len(token.original_text) // 2)
            spans = (
                SourceCharacterSpanV1(
                    token.token_id, 0, midpoint, token.original_text[:midpoint]
                ),
                SourceCharacterSpanV1(
                    token.token_id,
                    midpoint,
                    len(token.original_text),
                    token.original_text[midpoint:],
                ),
            )
            return (
                self.fixture.seed(
                    method,
                    suffix="multiple-spans",
                    source_kind=CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
                    proposed_value="pantry shop",
                    spans=spans,
                ),
            )

        provenance = self.provenance_from_builder(builder)
        self.assertEqual(1, len(provenance.blocked_candidates))
        ranked = self.rank(provenance).ranked_candidates[0]
        self.assertEqual(0, ranked.displacement.displacement)
        self.assertIs(
            ranked.provenance_status, ProvenanceMaterializationStatusV0.BLOCKED
        )

    def test_missing_source_spans_create_explicit_ranking_block(self) -> None:
        def builder(_adapter, method):
            return (
                self.fixture.seed(
                    method,
                    suffix="missing",
                    source_kind=CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
                    proposed_value="pantry shop",
                    spans=(),
                ),
            )

        result = self.rank(self.provenance_from_builder(builder))
        self.assertIs(result.readiness, CandidateRankingReadinessV0.RANKING_BLOCKED)
        self.assertEqual((), result.ranked_candidates)
        block = result.ranking_blocks[0]
        self.assertIs(
            block.reason_code,
            CandidateRankingBlockReasonV0.SOURCE_ORDER_DISPLACEMENT_UNAVAILABLE,
        )
        self.assertIs(
            block.displacement.availability, DisplacementAvailabilityV0.UNAVAILABLE
        )

    def test_any_unrankable_identity_removes_all_definitive_positions(self) -> None:
        def builder(_adapter, method):
            return (
                self.fixture.seed(
                    method,
                    suffix="missing",
                    source_kind=CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
                    proposed_value="pantry shop",
                    spans=(),
                ),
                self.fixture.seed(
                    method,
                    suffix="generic",
                    source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
                    proposed_value="pantry market",
                ),
            )

        result = self.rank(self.provenance_from_builder(builder))
        self.assertEqual((), result.ranked_candidates)
        self.assertEqual(2, len(result.ranking_blocks))
        self.assertEqual(
            {
                CandidateRankingBlockReasonV0.SOURCE_ORDER_DISPLACEMENT_UNAVAILABLE,
                CandidateRankingBlockReasonV0.AGGREGATE_BLOCKED_BY_PEER,
            },
            {item.reason_code for item in result.ranking_blocks},
        )

    def test_invalid_ocr_token_reference_is_integrity_error(self) -> None:
        provenance = self.provenance(
            (("source", CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR, "pantry shop"),)
        )
        span = provenance.materialized_candidates[0].source_audit.contributions[0].source_spans[0]
        object.__setattr__(span, "token_id", "unknown-token")
        with self.assertRaises(CandidateRankingIntegrityError):
            self.rank(provenance)

    def test_materialized_and_provenance_blocked_candidates_compete(self) -> None:
        def builder(_adapter, method):
            materialized = self.fixture.seed(
                method,
                suffix="materialized",
                source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
                proposed_value="pantry mars",
            )
            blocked = self.fixture.seed(
                method,
                suffix="blocked",
                source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
                proposed_value="pantry shop",
                event_ids=("event:blocked:a", "event:blocked:b"),
                rule_ids=("rule:blocked:a", "rule:blocked:b"),
            )
            return materialized, blocked

        provenance = self.provenance_from_builder(builder)
        result = self.rank(provenance)
        self.assertEqual(2, len(result.ranked_candidates))
        self.assertEqual(
            {
                ProvenanceMaterializationStatusV0.MATERIALIZED,
                ProvenanceMaterializationStatusV0.BLOCKED,
            },
            {item.provenance_status for item in result.ranked_candidates},
        )

    def test_tie_group_id_uses_exact_approved_payload(self) -> None:
        result = self.rank(
            self.provenance(
                (
                    ("a", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry mars"),
                    ("b", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry mark"),
                )
            )
        )
        first, second = result.ranked_candidates
        self.assertEqual(
            first.preliminary_rank.tie_group_id,
            second.preliminary_rank.tie_group_id,
        )
        payload = first.tie_identity_payload
        assert payload is not None
        theta = result.configuration.theta_a_ref
        self.assertEqual(
            (
                TIE_IDENTITY_SCHEMA_VERSION,
                CANDIDATE_RANKING_PROFILE_ID,
                first.identity.receipt_id,
                first.identity.field_id,
                theta.configuration_id,
                theta.configuration_version,
                theta.content_hash,
                first.best_source_priority,
                first.similarity.exact_numerator,
                first.similarity.exact_denominator,
                first.displacement.displacement,
            ),
            payload,
        )
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        expected = TIE_GROUP_ID_PREFIX + hashlib.sha256(
            serialized.encode("utf-8")
        ).hexdigest()
        self.assertEqual(expected, first.preliminary_rank.tie_group_id)

    def test_candidate_id_is_the_final_total_order_tiebreaker(self) -> None:
        common = (2, 4, 5, 0, "same")
        self.assertLess(
            candidate_ranking._compare_rank_components(
                (*common, "candidate:a"), (*common, "candidate:b")
            ),
            0,
        )

    def test_repeated_execution_is_deterministic_and_records_are_frozen(self) -> None:
        provenance = self.provenance(
            (
                ("a", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry mars"),
                ("b", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry mark"),
            )
        )
        first = self.rank(provenance)
        second = self.rank(provenance)
        self.assertEqual(first, second)
        with self.assertRaises(FrozenInstanceError):
            first.ranked_candidates = ()  # type: ignore[misc]

    def test_discovery_order_permutation_does_not_change_rank_outputs(self) -> None:
        specs = (
            ("a", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry mars"),
            ("b", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),
            ("c", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry market"),
        )
        first = self.rank(self.provenance(specs))
        second = self.rank(self.provenance(tuple(reversed(specs))))
        projection = lambda result: tuple(
            (
                item.identity.candidate_id,
                item.preliminary_rank,
                item.similarity.exact_numerator,
                item.similarity.exact_denominator,
            )
            for item in result.ranked_candidates
        )
        self.assertEqual(projection(first), projection(second))

    def test_forged_source_similarity_displacement_and_position_are_rejected(self) -> None:
        result = self.rank(
            self.provenance(
                (
                    ("a", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry mars"),
                    ("b", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),
                )
            )
        )
        record = result.ranked_candidates[0]
        with self.assertRaises(CandidateRankingIntegrityError):
            replace(record, best_source_priority=4)
        with self.assertRaises(CandidateRankingIntegrityError):
            replace(
                record,
                similarity=replace(
                    record.similarity,
                    exact_numerator=record.similarity.exact_numerator + 1,
                ),
            )
        with self.assertRaises(CandidateRankingIntegrityError):
            replace(
                record,
                displacement=replace(record.displacement, displacement=1),
            )
        wrong_rank = replace(
            record.preliminary_rank,
            rank_position=record.preliminary_rank.rank_position + 1,
        )
        wrong_record = replace(record, preliminary_rank=wrong_rank)
        altered = (wrong_record, *result.ranked_candidates[1:])
        with self.assertRaises(CandidateRankingIntegrityError):
            replace(result, ranked_candidates=altered)

    def test_wrong_theta_reference_and_local_versions_are_rejected(self) -> None:
        provenance = self.provenance(
            (("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
        )
        theta = self.configuration(provenance).theta_a_ref
        wrong = replace(theta, configuration_version="different-version")
        with self.assertRaisesRegex(CandidateRankingIntegrityError, "upstream"):
            compute_preliminary_candidate_ranking(
                provenance_result=provenance,
                configuration=CandidateRankingConfigurationV0(wrong),
            )
        with self.assertRaisesRegex(ValueError, "record version"):
            CandidateRankingConfigurationV0(theta, record_version="wrong")
        with self.assertRaisesRegex(ValueError, "THETA_A"):
            CandidateRankingConfigurationV0(
                replace(theta, kind=ConfigurationKind.KAPPA)
            )
        with self.assertRaisesRegex(ValueError, "READY"):
            CandidateRankingConfigurationV0(
                ConfigurationRefV1(
                    kind=ConfigurationKind.THETA_A,
                    configuration_id="not-ready",
                    configuration_version="v0",
                    state=ConfigurationState.NOT_READY,
                    status_reason="Synthetic unavailable configuration.",
                )
            )

    def test_forged_tie_group_id_is_rejected(self) -> None:
        result = self.rank(
            self.provenance(
                (
                    ("a", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry mars"),
                    ("b", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry mark"),
                )
            )
        )
        record = result.ranked_candidates[0]
        forged_rank = replace(record.preliminary_rank, tie_group_id="forged")
        with self.assertRaises(CandidateRankingIntegrityError):
            replace(record, preliminary_rank=forged_rank)

    def test_distinct_tie_payload_hash_collision_is_rejected(self) -> None:
        provenance = self.provenance(
            (
                ("a", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry mars"),
                ("b", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry mark"),
                ("c", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry xxxx"),
                ("d", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry yyyy"),
            )
        )
        with patch.object(candidate_ranking, "_sha256_hex", return_value="0" * 64):
            with self.assertRaisesRegex(CandidateRankingIntegrityError, "same tie-group"):
                self.rank(provenance)

    def test_existing_candidate_ids_and_provenance_are_unchanged(self) -> None:
        provenance = self.provenance(
            (
                ("source", CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR, "pantry shop"),
                ("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry market"),
            )
        )
        snapshot = deepcopy(provenance)
        result = self.rank(provenance)
        self.assertEqual(snapshot, provenance)
        source_by_id = {
            item.identity.candidate_id: item
            for item in (*provenance.materialized_candidates, *provenance.blocked_candidates)
        }
        for item in result.ranked_candidates:
            self.assertIs(item.source_record, source_by_id[item.identity.candidate_id])

    def test_component_does_not_limit_or_construct_altered_shared_candidates(self) -> None:
        result = self.rank(
            self.provenance(
                (("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
            )
        )
        self.assertTrue(
            all(not isinstance(item, CandidateRecordV1) for item in result.ranked_candidates)
        )
        for forbidden in (
            "candidate_limit",
            "limit_status",
            "overflow_reason",
            "selected_candidate",
        ):
            self.assertFalse(hasattr(result, forbidden))

    def test_public_api_has_no_future_or_forbidden_inputs_and_reruns_nothing(self) -> None:
        provenance = self.provenance(
            (("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
        )
        signature = inspect.signature(compute_preliminary_candidate_ranking)
        self.assertEqual(
            ("provenance_result", "configuration"), tuple(signature.parameters)
        )
        with patch(
            "pipeline.baseline_b3.apply_b3",
            side_effect=AssertionError("B3 must not rerun"),
        ), patch(
            "pipeline.layout_b2.extract_b2",
            side_effect=AssertionError("B2/OCR evidence must not rerun"),
        ):
            result = self.rank(provenance)
        for forbidden in (
            "candidate_limit",
            "price_reference",
            "constraint_result",
            "score",
            "calibration",
            "ground_truth",
            "held_out",
        ):
            self.assertNotIn(forbidden, signature.parameters)
            self.assertFalse(hasattr(result, forbidden))


if __name__ == "__main__":
    unittest.main()
