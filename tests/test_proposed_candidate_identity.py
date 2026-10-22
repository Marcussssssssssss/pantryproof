"""Synthetic adversarial tests for candidate identity/provenance audit V0."""

from __future__ import annotations

import hashlib
import inspect
import json
import unittest
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from unittest.mock import patch

import pipeline.proposed.candidate_identity as candidate_identity
from pipeline.proposed.candidate_deduplication import (
    NORMALIZATION_PROFILE_ID,
    deduplicate_candidate_drafts,
)
from pipeline.proposed.candidate_generation import generate_candidate_drafts
from pipeline.proposed.candidate_identity import (
    ALTERED_CANDIDATE_ID_PREFIX,
    ALTERED_IDENTITY_SCHEMA_VERSION,
    ORIGINAL_PROVENANCE_ID_PREFIX,
    ORIGINAL_PROVENANCE_SCHEMA_VERSION,
    CandidateIdentityIntegrityError,
    ProvenanceProjectionClassificationV0,
    prepare_candidate_identities,
)
from pipeline.proposed.contracts import (
    CandidateLimitStatus,
    CandidateProvenanceV1,
    CandidateRecordV1,
    CandidateRole,
    CandidateSourceKind,
)
from test_proposed_candidate_deduplication import _SyntheticCandidateFixture


class ProposedCandidateIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = _SyntheticCandidateFixture()

    def dedup(
        self,
        specs: tuple[tuple[str, CandidateSourceKind, str], ...] = (),
        *,
        multi_provenance: bool = False,
    ):
        return deduplicate_candidate_drafts(
            candidate_drafts=self.fixture.drafts(
                seed_specs=specs,
                multi_provenance=multi_provenance,
            )
        )

    def test_exact_original_c0_shared_record_is_materialized(self) -> None:
        dedup = self.dedup()
        method = dedup.candidate_drafts.original.method_ready_field

        result = prepare_candidate_identities(deduplication_result=dedup)
        original = result.original_candidate

        self.assertEqual(method.c0_candidate_id, original.candidate_id)
        self.assertEqual(method.c0_candidate_id, original.c0_candidate_id)
        self.assertEqual(method.c0_value, original.value)
        self.assertEqual(method.receipt_id, original.receipt_id)
        self.assertEqual(method.field_id, original.field_id)
        self.assertEqual(
            dedup.original_normalization.normalized_key,
            original.normalized_dedup_key,
        )
        self.assertIs(original.role, CandidateRole.ORIGINAL)
        self.assertIs(original.limit_status, CandidateLimitStatus.RETAINED)
        self.assertIsNone(original.preliminary_rank)
        self.assertIsNone(original.overflow_reason)

    def test_original_provenance_retains_tokens_without_fabricated_spans(self) -> None:
        dedup = self.dedup()
        method = dedup.candidate_drafts.original.method_ready_field
        provenance = prepare_candidate_identities(
            deduplication_result=dedup
        ).original_candidate.provenance

        self.assertEqual(1, len(provenance))
        member = provenance[0]
        self.assertIs(member.source_kind, CandidateSourceKind.ORIGINAL)
        self.assertEqual(method.c0_value, member.original_observed_value)
        self.assertEqual(method.source_token_ids, member.source_token_ids)
        self.assertEqual((), member.source_spans)
        self.assertIsNone(member.generic_rule_id)
        self.assertIsNone(member.resource_snapshot_id)
        self.assertIsNone(member.source_order_relationship)
        self.assertIsNone(member.source_order_position)

    def test_original_provenance_id_uses_exact_approved_payload(self) -> None:
        dedup = self.dedup()
        method = dedup.candidate_drafts.original.method_ready_field
        result = prepare_candidate_identities(deduplication_result=dedup)
        payload = (
            ORIGINAL_PROVENANCE_SCHEMA_VERSION,
            method.receipt_id,
            method.field_id,
            method.c0_candidate_id,
            method.c0_value,
            method.source_token_ids,
        )
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        expected = ORIGINAL_PROVENANCE_ID_PREFIX + hashlib.sha256(
            serialized.encode("utf-8")
        ).hexdigest()
        self.assertEqual(
            expected, result.original_candidate.provenance[0].provenance_id
        )

    def test_altered_identity_payload_serialization_and_hash_are_exact(self) -> None:
        dedup = self.dedup(
            (("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
        )
        result = prepare_candidate_identities(deduplication_result=dedup)
        identity = result.altered_candidates[0].identity
        method = dedup.candidate_drafts.original.method_ready_field
        payload = (
            ALTERED_IDENTITY_SCHEMA_VERSION,
            NORMALIZATION_PROFILE_ID,
            method.receipt_id,
            method.field_id,
            method.c0_candidate_id,
            dedup.altered_groups[0].normalization.normalized_key,
        )
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        expected_id = ALTERED_CANDIDATE_ID_PREFIX + hashlib.sha256(
            serialized.encode("utf-8")
        ).hexdigest()
        self.assertEqual(payload, identity.identity_payload)
        self.assertEqual(serialized, identity.identity_payload_json)
        self.assertEqual(expected_id, identity.candidate_id)
        self.assertEqual(64, len(identity.candidate_id.rsplit(":", 1)[-1]))

    def test_repeated_execution_is_identical_and_stable(self) -> None:
        dedup = self.dedup(
            (("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
        )
        first = prepare_candidate_identities(deduplication_result=dedup)
        second = prepare_candidate_identities(deduplication_result=dedup)
        self.assertEqual(first, second)
        self.assertEqual(
            first.altered_candidates[0].identity.candidate_id,
            second.altered_candidates[0].identity.candidate_id,
        )

    def test_added_provenance_and_changed_representative_do_not_change_identity(self) -> None:
        base = self.dedup(
            (("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
        )
        enriched = self.dedup(
            (
                ("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),
                (
                    "source",
                    CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
                    "ＰＡＮＴＲＹ SHOP",
                ),
            )
        )
        base_result = prepare_candidate_identities(deduplication_result=base)
        enriched_result = prepare_candidate_identities(
            deduplication_result=enriched
        )
        first = base_result.altered_candidates[0]
        second = enriched_result.altered_candidates[0]
        self.assertNotEqual(
            first.identity.representative_value,
            second.identity.representative_value,
        )
        self.assertEqual(first.identity.candidate_id, second.identity.candidate_id)
        self.assertEqual(1, len(first.contributions))
        self.assertEqual(2, len(second.contributions))

    def test_each_identity_domain_component_changes_the_digest(self) -> None:
        baseline = dict(
            normalization_profile_id=NORMALIZATION_PROFILE_ID,
            receipt_id="receipt-a",
            field_id="field-a",
            c0_candidate_id="field-a:c0",
            normalized_dedup_key='["profile","FIELD","TEXT","milk"]',
        )

        def identifier(values):
            payload = candidate_identity._altered_identity_payload(**values)
            return candidate_identity._identifier(
                ALTERED_CANDIDATE_ID_PREFIX, payload
            )[0]

        original = identifier(baseline)
        mutations = (
            {"receipt_id": "receipt-b"},
            {"field_id": "field-b"},
            {"c0_candidate_id": "different:c0"},
            {"normalization_profile_id": "candidate-field-normalization-v1"},
            {"normalized_dedup_key": '["profile","FIELD","TEXT","rice"]'},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                changed = dict(baseline)
                changed.update(mutation)
                self.assertNotEqual(original, identifier(changed))

    def test_unicode_and_json_escaping_are_canonical(self) -> None:
        dedup = self.dedup(
            (
                (
                    "unicode",
                    CandidateSourceKind.GENERIC_NORMALIZATION,
                    'Caf\u00e9 "A"\nShop',
                ),
            )
        )
        identity = prepare_candidate_identities(
            deduplication_result=dedup
        ).altered_candidates[0].identity
        expected = json.dumps(
            identity.identity_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        self.assertEqual(expected, identity.identity_payload_json)
        self.assertIn("caf\u00e9", identity.identity_payload_json)
        self.assertIn('\\"', identity.identity_payload_json)

    def test_unpaired_unicode_surrogate_is_rejected_before_hashing(self) -> None:
        dedup = self.dedup(
            (("surrogate", CandidateSourceKind.GENERIC_NORMALIZATION, "bad\ud800value"),)
        )
        with self.assertRaisesRegex(
            CandidateIdentityIntegrityError, "strict canonical UTF-8"
        ):
            prepare_candidate_identities(deduplication_result=dedup)

    def test_unsupported_identity_payload_shape_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            CandidateIdentityIntegrityError, "only strings and nested tuples"
        ):
            candidate_identity._canonical_identity_json(("valid", 1))

    def test_synthetic_hash_collision_fails_closed(self) -> None:
        dedup = self.dedup(
            (
                ("milk", CandidateSourceKind.GENERIC_NORMALIZATION, "milk shop"),
                ("rice", CandidateSourceKind.GENERIC_NORMALIZATION, "rice shop"),
            )
        )
        with patch.object(candidate_identity, "_sha256_hex", return_value="0" * 64):
            with self.assertRaisesRegex(
                CandidateIdentityIntegrityError, "same candidate ID"
            ):
                prepare_candidate_identities(deduplication_result=dedup)

    def test_multiple_sources_and_complete_composite_provenance_are_retained(self) -> None:
        dedup = self.dedup(
            (
                ("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),
                (
                    "source",
                    CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
                    "ＰＡＮＴＲＹ SHOP",
                ),
            ),
            multi_provenance=True,
        )
        audit = prepare_candidate_identities(
            deduplication_result=dedup
        ).altered_candidates[0]
        self.assertEqual(2, len(audit.contributions))
        for contribution in audit.contributions:
            proposal = contribution.proposal
            self.assertIs(proposal.b3_seed, contribution.b3_seed)
            self.assertEqual(proposal.b3_event_ids, contribution.b3_event_ids)
            self.assertEqual(proposal.b3_rule_ids, contribution.b3_rule_ids)
            self.assertEqual(proposal.source_spans, contribution.source_spans)
            self.assertEqual(
                proposal.adapter_seed_position,
                contribution.adapter_seed_position,
            )

    def test_single_rule_generic_without_spans_is_deferred(self) -> None:
        dedup = self.dedup(
            (("single", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
        )
        contribution = prepare_candidate_identities(
            deduplication_result=dedup
        ).altered_candidates[0].contributions[0]
        self.assertEqual((), contribution.source_spans)
        self.assertEqual((), contribution.source_token_ids)
        self.assertIs(
            contribution.projection_classification,
            ProvenanceProjectionClassificationV0.PROJECTION_DEFERRED,
        )
        self.assertFalse(contribution.is_blocked)

    def test_composite_generic_is_blocked_without_guessed_pairing(self) -> None:
        dedup = self.dedup(
            (("composite", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),),
            multi_provenance=True,
        )
        audit = prepare_candidate_identities(
            deduplication_result=dedup
        ).altered_candidates[0]
        contribution = audit.contributions[0]
        self.assertIs(
            contribution.projection_classification,
            ProvenanceProjectionClassificationV0.BLOCKED_COMPOSITE_GENERIC_RULES,
        )
        self.assertTrue(contribution.is_blocked)
        self.assertTrue(audit.has_blocked_contributions)
        self.assertEqual(2, len(contribution.b3_event_ids))
        self.assertEqual(2, len(contribution.b3_rule_ids))

    def test_source_neighbour_without_spans_is_blocked_but_identity_remains(self) -> None:
        adapter, method = self.fixture.adapter_and_method()
        seed = self.fixture.seed(
            method,
            suffix="no-source-token",
            source_kind=CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
            proposed_value="pantry shop",
            spans=(),
        )
        adapter, method = self.fixture.with_seeds(adapter, method, (seed,))
        drafts = generate_candidate_drafts(
            suspicion_result=self.fixture.suspicion(method),
            adapter_result=adapter,
        )
        dedup = deduplicate_candidate_drafts(candidate_drafts=drafts)
        audit = prepare_candidate_identities(
            deduplication_result=dedup
        ).altered_candidates[0]
        contribution = audit.contributions[0]
        self.assertIs(
            contribution.projection_classification,
            ProvenanceProjectionClassificationV0.BLOCKED_MISSING_SOURCE_TOKENS,
        )
        self.assertTrue(audit.has_blocked_contributions)
        self.assertTrue(audit.identity.candidate_id.startswith(ALTERED_CANDIDATE_ID_PREFIX))
        self.assertEqual((), contribution.source_token_ids)

    def test_genuine_source_spans_supply_only_recorded_token_ids(self) -> None:
        dedup = self.dedup(
            (
                (
                    "source",
                    CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR,
                    "pantry shop",
                ),
            )
        )
        contribution = prepare_candidate_identities(
            deduplication_result=dedup
        ).altered_candidates[0].contributions[0]
        self.assertIs(
            contribution.projection_classification,
            ProvenanceProjectionClassificationV0.PROJECTION_DEFERRED,
        )
        self.assertEqual(
            tuple(dict.fromkeys(span.token_id for span in contribution.source_spans)),
            contribution.source_token_ids,
        )

    def test_c0_equivalence_sidecar_is_preserved_without_altered_identity(self) -> None:
        dedup = self.dedup(
            (("equivalent", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry mart"),)
        )
        self.assertIsNotNone(dedup.equivalent_to_c0)
        result = prepare_candidate_identities(deduplication_result=dedup)
        self.assertEqual((), result.altered_candidates)
        self.assertIs(dedup.equivalent_to_c0, result.equivalent_to_c0)
        self.assertEqual(
            (CandidateSourceKind.ORIGINAL,),
            tuple(item.source_kind for item in result.original_candidate.provenance),
        )

    def test_forged_identity_classification_contribution_and_result_fail(self) -> None:
        dedup = self.dedup(
            (("altered", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
        )
        result = prepare_candidate_identities(deduplication_result=dedup)
        audit = result.altered_candidates[0]
        contribution = audit.contributions[0]
        with self.assertRaises(CandidateIdentityIntegrityError):
            replace(audit.identity, candidate_id=ALTERED_CANDIDATE_ID_PREFIX + "0" * 64)
        with self.assertRaises(CandidateIdentityIntegrityError):
            replace(
                contribution,
                projection_classification=(
                    ProvenanceProjectionClassificationV0.BLOCKED_MISSING_SOURCE_TOKENS
                ),
            )
        with self.assertRaises(CandidateIdentityIntegrityError):
            replace(audit, contributions=())
        with self.assertRaises(CandidateIdentityIntegrityError):
            replace(result, altered_candidates=())
        forged_original = replace(
            result.original_candidate,
            normalized_dedup_key="forged-key",
        )
        with self.assertRaises(CandidateIdentityIntegrityError):
            replace(result, original_candidate=forged_original)

    def test_upstream_is_immutable_and_local_records_are_frozen(self) -> None:
        dedup = self.dedup(
            (("altered", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
        )
        snapshot = deepcopy(dedup)
        result = prepare_candidate_identities(deduplication_result=dedup)
        self.assertEqual(snapshot, dedup)
        self.assertIs(dedup, result.deduplication_result)
        with self.assertRaises(FrozenInstanceError):
            result.altered_candidates[0].has_blocked_contributions = True  # type: ignore[misc]

    def test_no_b3_rerun_or_retailer_snapshot_fabrication(self) -> None:
        dedup = self.dedup(
            (("altered", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
        )
        with patch(
            "pipeline.baseline_b3.apply_b3",
            side_effect=AssertionError("B3 must not rerun"),
        ):
            result = prepare_candidate_identities(deduplication_result=dedup)
        contribution = result.altered_candidates[0].contributions[0]
        self.assertFalse(hasattr(contribution, "resource_snapshot_id"))

    def test_public_boundary_has_no_future_policy_or_evidence_inputs(self) -> None:
        signature = inspect.signature(prepare_candidate_identities)
        self.assertEqual(("deduplication_result",), tuple(signature.parameters))
        result = prepare_candidate_identities(
            deduplication_result=self.dedup(
                (("altered", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
            )
        )
        altered = result.altered_candidates[0]
        self.assertNotIsInstance(altered.identity, CandidateRecordV1)
        self.assertTrue(
            all(
                not isinstance(item, CandidateProvenanceV1)
                for item in altered.contributions
            )
        )
        for forbidden in (
            "preliminary_rank",
            "limit_status",
            "overflow_reason",
            "normalized_edit_similarity",
            "source_order_displacement",
            "price_reference",
            "ground_truth",
            "constraint_result",
            "score",
        ):
            self.assertFalse(hasattr(altered.identity, forbidden))


if __name__ == "__main__":
    unittest.main()
