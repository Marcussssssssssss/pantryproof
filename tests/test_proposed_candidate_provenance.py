"""Synthetic adversarial tests for altered provenance materialization V0."""

from __future__ import annotations

import hashlib
import inspect
import json
import unittest
from dataclasses import FrozenInstanceError, replace
from unittest.mock import patch

import pipeline.proposed.candidate_provenance as candidate_provenance
from pipeline.proposed.candidate_deduplication import deduplicate_candidate_drafts
from pipeline.proposed.candidate_generation import generate_candidate_drafts
from pipeline.proposed.candidate_identity import prepare_candidate_identities
from pipeline.proposed.candidate_provenance import (
    ALTERED_PROVENANCE_ID_PREFIX,
    PROVENANCE_MEMBER_SCHEMA_VERSION,
    CandidateProvenanceIntegrityError,
    ProvenanceBlockingReasonV0,
    materialize_altered_provenance,
)
from pipeline.proposed.contracts import (
    PROPOSED_CONTRACT_VERSION,
    B3CompatibleSeedV1,
    CandidateProvenanceV1,
    CandidateRecordV1,
    CandidateSourceKind,
    SourceCharacterSpanV1,
)
from test_proposed_candidate_deduplication import _SyntheticCandidateFixture


class ProposedCandidateProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = _SyntheticCandidateFixture()

    def preparation(
        self,
        specs: tuple[tuple[str, CandidateSourceKind, str], ...] = (),
        *,
        multi_provenance: bool = False,
    ):
        drafts = self.fixture.drafts(
            seed_specs=specs,
            multi_provenance=multi_provenance,
        )
        return prepare_candidate_identities(
            deduplication_result=deduplicate_candidate_drafts(
                candidate_drafts=drafts
            )
        )

    def preparation_from_seeds(self, seeds_builder):
        adapter, method = self.fixture.adapter_and_method()
        seeds = seeds_builder(adapter, method)
        adapter, method = self.fixture.with_seeds(adapter, method, seeds)
        drafts = generate_candidate_drafts(
            suspicion_result=self.fixture.suspicion(method),
            adapter_result=adapter,
        )
        return prepare_candidate_identities(
            deduplication_result=deduplicate_candidate_drafts(
                candidate_drafts=drafts
            )
        )

    def seed(
        self,
        method,
        *,
        suffix: str,
        source_kind: CandidateSourceKind,
        proposed_value: str,
        spans: tuple[SourceCharacterSpanV1, ...] = (),
        event_ids: tuple[str, ...] | None = None,
        rule_ids: tuple[str, ...] | None = None,
    ) -> B3CompatibleSeedV1:
        return self.fixture.seed(
            method,
            suffix=suffix,
            source_kind=source_kind,
            proposed_value=proposed_value,
            spans=spans,
            event_ids=event_ids,
            rule_ids=rule_ids,
        )

    def test_single_rule_generic_with_and_without_spans(self) -> None:
        without_spans = materialize_altered_provenance(
            identity_preparation=self.preparation(
                (("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
            )
        )
        generic = without_spans.materialized_candidates[0].shared_provenance[0]
        self.assertEqual((), generic.source_spans)
        self.assertEqual((), generic.source_token_ids)
        self.assertEqual("ＰＡＮＴＲＹ MART", generic.original_observed_value)
        self.assertEqual("rule:generic", generic.generic_rule_id)

        def with_span(_adapter, method):
            span = self.fixture.span(method)
            return (
                self.seed(
                    method,
                    suffix="generic-span",
                    source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
                    proposed_value="pantry shop",
                    spans=(span,),
                ),
            )

        with_spans = materialize_altered_provenance(
            identity_preparation=self.preparation_from_seeds(with_span)
        )
        member = with_spans.materialized_candidates[0].shared_provenance[0]
        self.assertEqual(("store",), member.source_token_ids)
        self.assertEqual("ＰＡＮ", member.source_spans[0].text)
        self.assertEqual("ＰＡＮＴＲＹ MART", member.original_observed_value)

    def test_multiple_events_with_one_generic_rule_remain_linked_locally(self) -> None:
        def builder(_adapter, method):
            return (
                self.seed(
                    method,
                    suffix="multi-event",
                    source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
                    proposed_value="pantry shop",
                    event_ids=("event:a", "event:b"),
                    rule_ids=("rule:generic",),
                ),
            )

        preparation = self.preparation_from_seeds(builder)
        result = materialize_altered_provenance(
            identity_preparation=preparation
        )
        source_audit = result.materialized_candidates[0].source_audit
        self.assertEqual(
            ("event:a", "event:b"), source_audit.contributions[0].b3_event_ids
        )
        self.assertEqual(
            "rule:generic",
            result.materialized_candidates[0].shared_provenance[0].generic_rule_id,
        )

    def test_composite_generic_rules_are_blocked_atomically(self) -> None:
        preparation = self.preparation(
            (("composite", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),),
            multi_provenance=True,
        )
        result = materialize_altered_provenance(
            identity_preparation=preparation
        )
        self.assertEqual((), result.materialized_candidates)
        blocked = result.blocked_candidates[0]
        self.assertEqual((), blocked.shared_provenance)
        self.assertIs(
            blocked.blocking_records[0].reason_code,
            ProvenanceBlockingReasonV0.COMPOSITE_GENERIC_RULES,
        )
        self.assertEqual(2, len(blocked.source_audit.contributions[0].b3_rule_ids))

    def test_source_neighbour_single_literal_span_is_projected(self) -> None:
        preparation = self.preparation(
            (("source", CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR, "pantry shop"),)
        )
        result = materialize_altered_provenance(
            identity_preparation=preparation
        )
        provenance = result.materialized_candidates[0].shared_provenance[0]
        span = preparation.altered_candidates[0].contributions[0].source_spans[0]
        self.assertIs(
            CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
            provenance.source_kind,
        )
        self.assertEqual(span.text, provenance.original_observed_value)
        self.assertEqual((span,), provenance.source_spans)
        self.assertEqual((span.token_id,), provenance.source_token_ids)
        self.assertIsNone(provenance.generic_rule_id)

    def test_genuine_neighbour_token_outside_c0_tokens_is_permitted(self) -> None:
        def builder(adapter, method):
            output = adapter.original_b2_result.receipt_output
            assert output is not None
            neighbour = next(
                token for token in output.source_evidence.tokens
                if token.token_id == "date-label"
            )
            span = SourceCharacterSpanV1(
                neighbour.token_id,
                0,
                4,
                neighbour.original_text[:4],
            )
            return (
                self.seed(
                    method,
                    suffix="neighbour",
                    source_kind=CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
                    proposed_value="pantry shop",
                    spans=(span,),
                ),
            )

        preparation = self.preparation_from_seeds(builder)
        method = preparation.deduplication_result.candidate_drafts.original.method_ready_field
        provenance = materialize_altered_provenance(
            identity_preparation=preparation
        ).materialized_candidates[0].shared_provenance[0]
        self.assertNotIn("date-label", method.source_token_ids)
        self.assertEqual(("date-label",), provenance.source_token_ids)
        self.assertEqual("DATE", provenance.original_observed_value)

    def test_missing_source_span_is_blocked(self) -> None:
        def builder(_adapter, method):
            return (
                self.seed(
                    method,
                    suffix="missing",
                    source_kind=CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
                    proposed_value="pantry shop",
                    spans=(),
                ),
            )

        result = materialize_altered_provenance(
            identity_preparation=self.preparation_from_seeds(builder)
        )
        self.assertEqual((), result.materialized_candidates)
        self.assertIs(
            result.blocked_candidates[0].blocking_records[0].reason_code,
            ProvenanceBlockingReasonV0.MISSING_SOURCE_NEIGHBOUR_SPANS,
        )

    def test_multiple_source_spans_are_blocked_without_composition(self) -> None:
        def builder(_adapter, method):
            token = method.source_tokens[0]
            spans = (
                SourceCharacterSpanV1(token.token_id, 0, 2, token.original_text[0:2]),
                SourceCharacterSpanV1(token.token_id, 2, 4, token.original_text[2:4]),
            )
            return (
                self.seed(
                    method,
                    suffix="multiple",
                    source_kind=CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
                    proposed_value="pantry shop",
                    spans=spans,
                ),
            )

        result = materialize_altered_provenance(
            identity_preparation=self.preparation_from_seeds(builder)
        )
        blocked = result.blocked_candidates[0]
        self.assertIs(
            blocked.blocking_records[0].reason_code,
            ProvenanceBlockingReasonV0.MULTIPLE_SOURCE_NEIGHBOUR_SPANS,
        )
        self.assertEqual(2, len(blocked.source_audit.contributions[0].source_spans))
        self.assertEqual((), blocked.shared_provenance)

    def test_unknown_ocr_token_is_rejected(self) -> None:
        preparation = self.preparation(
            (("source", CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR, "pantry shop"),)
        )
        span = preparation.altered_candidates[0].contributions[0].source_spans[0]
        object.__setattr__(span, "token_id", "unknown-token")
        with self.assertRaisesRegex(
            CandidateProvenanceIntegrityError, "upstream reconstruction|Unknown"
        ):
            materialize_altered_provenance(identity_preparation=preparation)

    def test_cross_receipt_source_token_is_rejected(self) -> None:
        preparation = self.preparation(
            (("source", CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR, "pantry shop"),)
        )
        output = (
            preparation.deduplication_result.candidate_drafts.adapter_result
            .original_b2_result.receipt_output
        )
        assert output is not None
        object.__setattr__(output.source_evidence.tokens[0], "receipt_id", "other")
        with self.assertRaisesRegex(CandidateProvenanceIntegrityError, "Every original"):
            materialize_altered_provenance(identity_preparation=preparation)

    def test_invalid_and_boolean_offsets_are_rejected(self) -> None:
        for invalid_start in (False, -1, 99):
            with self.subTest(invalid_start=invalid_start):
                preparation = self.preparation(
                    (("source", CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR, "pantry shop"),)
                )
                span = preparation.altered_candidates[0].contributions[0].source_spans[0]
                object.__setattr__(span, "start", invalid_start)
                with self.assertRaisesRegex(
                    CandidateProvenanceIntegrityError, "invalid literal OCR offsets"
                ):
                    materialize_altered_provenance(
                        identity_preparation=preparation
                    )

    def test_mismatched_literal_slice_is_rejected(self) -> None:
        preparation = self.preparation(
            (("source", CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR, "pantry shop"),)
        )
        span = preparation.altered_candidates[0].contributions[0].source_spans[0]
        object.__setattr__(span, "text", "BAD")
        with self.assertRaisesRegex(CandidateProvenanceIntegrityError, "OCR slice"):
            materialize_altered_provenance(identity_preparation=preparation)

    def test_multiple_source_kinds_form_ordered_union(self) -> None:
        preparation = self.preparation(
            (
                ("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),
                ("source", CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR, "ＰＡＮＴＲＹ SHOP"),
            )
        )
        outcome = materialize_altered_provenance(
            identity_preparation=preparation
        ).materialized_candidates[0]
        self.assertEqual(
            (
                CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
                CandidateSourceKind.GENERIC_NORMALIZATION,
            ),
            tuple(member.source_kind for member in outcome.shared_provenance),
        )
        self.assertEqual(2, len(outcome.source_audit.contributions))

    def test_one_blocked_contribution_blocks_complete_union(self) -> None:
        def builder(_adapter, method):
            generic = self.seed(
                method,
                suffix="generic",
                source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
                proposed_value="pantry shop",
            )
            missing = self.seed(
                method,
                suffix="missing",
                source_kind=CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
                proposed_value="PANTRY SHOP",
                spans=(),
            )
            return generic, missing

        result = materialize_altered_provenance(
            identity_preparation=self.preparation_from_seeds(builder)
        )
        self.assertEqual((), result.materialized_candidates)
        blocked = result.blocked_candidates[0]
        self.assertEqual(2, len(blocked.source_audit.contributions))
        self.assertEqual(1, len(blocked.blocking_records))
        self.assertEqual((), blocked.shared_provenance)

    def test_identical_projections_deduplicate_and_retain_links(self) -> None:
        def builder(_adapter, method):
            return tuple(
                self.seed(
                    method,
                    suffix=suffix,
                    source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
                    proposed_value=value,
                    event_ids=(f"event:{suffix}",),
                    rule_ids=("rule:same",),
                )
                for suffix, value in (("a", "pantry shop"), ("b", "PANTRY SHOP"))
            )

        outcome = materialize_altered_provenance(
            identity_preparation=self.preparation_from_seeds(builder)
        ).materialized_candidates[0]
        self.assertEqual(1, len(outcome.members))
        self.assertEqual(2, len(outcome.members[0].contributing_proposal_references))
        self.assertEqual(2, len(outcome.source_audit.contributions))

    def test_nonidentical_projections_are_not_merged(self) -> None:
        def builder(_adapter, method):
            return tuple(
                self.seed(
                    method,
                    suffix=suffix,
                    source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
                    proposed_value=value,
                    rule_ids=(rule,),
                )
                for suffix, value, rule in (
                    ("a", "pantry shop", "rule:a"),
                    ("b", "PANTRY SHOP", "rule:b"),
                )
            )

        outcome = materialize_altered_provenance(
            identity_preparation=self.preparation_from_seeds(builder)
        ).materialized_candidates[0]
        self.assertEqual(2, len(outcome.members))
        self.assertEqual(
            {"rule:a", "rule:b"},
            {member.provenance.generic_rule_id for member in outcome.members},
        )

    def test_exact_payload_serialization_and_sha256(self) -> None:
        preparation = self.preparation(
            (("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
        )
        outcome = materialize_altered_provenance(
            identity_preparation=preparation
        ).materialized_candidates[0]
        projection = outcome.members[0]
        identity = outcome.identity
        payload = (
            PROVENANCE_MEMBER_SCHEMA_VERSION,
            PROPOSED_CONTRACT_VERSION,
            identity.receipt_id,
            identity.field_id,
            identity.candidate_id,
            CandidateSourceKind.GENERIC_NORMALIZATION.value,
            "ＰＡＮＴＲＹ MART",
            (),
            (),
            None,
            None,
            "rule:generic",
            None,
        )
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        expected_id = ALTERED_PROVENANCE_ID_PREFIX + hashlib.sha256(
            serialized.encode("utf-8")
        ).hexdigest()
        self.assertEqual(payload, projection.identity_payload)
        self.assertEqual(serialized, projection.identity_payload_json)
        self.assertEqual(expected_id, projection.provenance.provenance_id)
        self.assertEqual(64, len(expected_id.rsplit(":", 1)[-1]))

    def test_unicode_json_escaping_and_invalid_unicode(self) -> None:
        def unicode_builder(_adapter, method):
            return (
                self.seed(
                    method,
                    suffix="unicode",
                    source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
                    proposed_value="pantry shop",
                    rule_ids=('règle:"A"',),
                ),
            )

        projection = materialize_altered_provenance(
            identity_preparation=self.preparation_from_seeds(unicode_builder)
        ).materialized_candidates[0].members[0]
        self.assertIn("règle", projection.identity_payload_json)
        self.assertIn('\\"A\\"', projection.identity_payload_json)

        def invalid_builder(_adapter, method):
            return (
                self.seed(
                    method,
                    suffix="invalid-unicode",
                    source_kind=CandidateSourceKind.GENERIC_NORMALIZATION,
                    proposed_value="pantry shop",
                    rule_ids=("bad\ud800rule",),
                ),
            )

        with self.assertRaisesRegex(
            CandidateProvenanceIntegrityError, "strict canonical UTF-8"
        ):
            materialize_altered_provenance(
                identity_preparation=self.preparation_from_seeds(invalid_builder)
            )

    def test_strict_serializer_rejects_boolean_float_and_wrong_shape(self) -> None:
        preparation = self.preparation(
            (("source", CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR, "pantry shop"),)
        )
        projection = materialize_altered_provenance(
            identity_preparation=preparation
        ).materialized_candidates[0].members[0]
        payload = projection.identity_payload
        spans = payload[8]
        boolean_span = ((spans[0][0], False, spans[0][2], spans[0][3]),)
        with self.assertRaisesRegex(CandidateProvenanceIntegrityError, "non-Boolean"):
            candidate_provenance._canonical_provenance_json(
                (*payload[:8], boolean_span, *payload[9:])
            )
        with self.assertRaisesRegex(CandidateProvenanceIntegrityError, "support only"):
            candidate_provenance._canonical_provenance_json(
                (*payload[:10], 1.5, *payload[11:])
            )
        with self.assertRaisesRegex(CandidateProvenanceIntegrityError, "13-part"):
            candidate_provenance._canonical_provenance_json(payload[:-1])

    def test_synthetic_digest_collision_is_rejected(self) -> None:
        preparation = self.preparation(
            (
                ("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),
                ("source", CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR, "ＰＡＮＴＲＹ SHOP"),
            )
        )
        with patch.object(candidate_provenance, "_sha256_hex", return_value="0" * 64):
            with self.assertRaises(CandidateProvenanceIntegrityError):
                materialize_altered_provenance(
                    identity_preparation=preparation
                )

    def test_candidate_identity_stable_after_added_provenance(self) -> None:
        base = self.preparation(
            (("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
        )
        enriched = self.preparation(
            (
                ("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),
                ("source", CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR, "ＰＡＮＴＲＹ SHOP"),
            )
        )
        base_id = materialize_altered_provenance(
            identity_preparation=base
        ).materialized_candidates[0].identity.candidate_id
        enriched_id = materialize_altered_provenance(
            identity_preparation=enriched
        ).materialized_candidates[0].identity.candidate_id
        self.assertEqual(base_id, enriched_id)

    def test_c0_and_equivalence_audit_are_preserved_by_reference(self) -> None:
        preparation = self.preparation(
            (("equivalent", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry mart"),)
        )
        result = materialize_altered_provenance(
            identity_preparation=preparation
        )
        self.assertIs(preparation.original_candidate, result.original_candidate)
        self.assertIs(preparation.equivalent_to_c0, result.equivalent_to_c0)
        self.assertEqual((), result.materialized_candidates)
        self.assertEqual((), result.blocked_candidates)

    def test_full_reconstruction_rejects_forgery_and_partial_partitions(self) -> None:
        preparation = self.preparation(
            (("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
        )
        result = materialize_altered_provenance(
            identity_preparation=preparation
        )
        projection = result.materialized_candidates[0].members[0]
        with self.assertRaises(CandidateProvenanceIntegrityError):
            replace(
                projection,
                identity_payload_json=projection.identity_payload_json + " ",
            )
        with self.assertRaises(CandidateProvenanceIntegrityError):
            replace(result, materialized_candidates=())
        with self.assertRaises(CandidateProvenanceIntegrityError):
            replace(result, original_candidate=replace(result.original_candidate))

    def test_forged_upstream_blocking_status_is_rejected(self) -> None:
        preparation = self.preparation(
            (("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
        )
        source_audit = preparation.altered_candidates[0]
        object.__setattr__(source_audit, "has_blocked_contributions", True)
        with self.assertRaisesRegex(CandidateProvenanceIntegrityError, "upstream reconstruction"):
            materialize_altered_provenance(identity_preparation=preparation)

    def test_unsupported_resource_sources_fail_closed_and_cannot_materialize(self) -> None:
        for source_kind in (
            CandidateSourceKind.RETAILER_MAPPING,
            CandidateSourceKind.PANTRY_TERMINOLOGY,
        ):
            with self.subTest(source_kind=source_kind):
                preparation = self.preparation(
                    (("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
                )
                contribution = preparation.altered_candidates[0].contributions[0]
                object.__setattr__(contribution, "source_kind", source_kind)
                blocking = candidate_provenance._blocking_shape(contribution)
                assert blocking is not None
                self.assertIs(
                    blocking[0],
                    ProvenanceBlockingReasonV0.UNSUPPORTED_SOURCE_KIND_OR_RESOURCE,
                )
                with self.assertRaises(CandidateProvenanceIntegrityError):
                    materialize_altered_provenance(
                        identity_preparation=preparation
                    )

    def test_empty_altered_candidate_case_is_valid_and_deterministic(self) -> None:
        preparation = self.preparation()
        first = materialize_altered_provenance(
            identity_preparation=preparation
        )
        second = materialize_altered_provenance(
            identity_preparation=preparation
        )
        self.assertEqual(first, second)
        self.assertEqual((), first.materialized_candidates)
        self.assertEqual((), first.blocked_candidates)

    def test_repeated_run_is_deterministic_and_records_are_frozen(self) -> None:
        preparation = self.preparation(
            (("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
        )
        first = materialize_altered_provenance(
            identity_preparation=preparation
        )
        second = materialize_altered_provenance(
            identity_preparation=preparation
        )
        self.assertEqual(first, second)
        with self.assertRaises(FrozenInstanceError):
            first.materialized_candidates = ()  # type: ignore[misc]

    def test_no_b3_rerun_candidate_record_or_future_policy_inputs(self) -> None:
        preparation = self.preparation(
            (("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
        )
        with patch(
            "pipeline.baseline_b3.apply_b3",
            side_effect=AssertionError("B3 must not rerun"),
        ):
            result = materialize_altered_provenance(
                identity_preparation=preparation
            )
        self.assertTrue(
            all(
                isinstance(member.provenance, CandidateProvenanceV1)
                for item in result.materialized_candidates
                for member in item.members
            )
        )
        self.assertTrue(
            all(
                not isinstance(item, CandidateRecordV1)
                for item in (*result.materialized_candidates, *result.blocked_candidates)
            )
        )
        signature = inspect.signature(materialize_altered_provenance)
        self.assertEqual(("identity_preparation",), tuple(signature.parameters))
        for forbidden in (
            "preliminary_rank",
            "candidate_limit",
            "price_reference",
            "constraint_result",
            "score",
            "calibration",
            "ground_truth",
            "held_out",
        ):
            self.assertFalse(hasattr(result, forbidden))


if __name__ == "__main__":
    unittest.main()
