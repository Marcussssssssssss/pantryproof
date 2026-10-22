"""Synthetic adversarial tests for candidate normalization/deduplication V0."""

from __future__ import annotations

import inspect
import json
import unittest
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from unittest.mock import patch

from pipeline.baseline_b3 import apply_b3
from pipeline.contracts import (
    OcrSourceToken,
    Point,
    ReceiptExtractionStatus,
    ReceiptFieldName,
    ReceiptSourceEvidence,
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
    SourceProcessingStatus,
    SourceProvenance,
)
from pipeline.layout_b2 import extract_b2
from pipeline.proposed.adapter import ProposedAdapterResultV1, adapt_b2_to_proposed
from pipeline.proposed.candidate_deduplication import (
    NORMALIZATION_PROFILE_ID,
    CandidateDeduplicationIntegrityError,
    CandidateNormalizationV0,
    NormalizationParseStatusV0,
    deduplicate_candidate_drafts,
    normalize_candidate_value,
)
from pipeline.proposed.candidate_generation import generate_candidate_drafts
from pipeline.proposed.contracts import (
    B3CompatibleSeedV1,
    CandidateSourceKind,
    ConfigurationKind,
    ConfigurationRefV1,
    ConfigurationState,
    MethodReadyFieldV1,
    SourceCharacterSpanV1,
)
from pipeline.proposed.suspicion import (
    ConfidenceAggregationV0,
    ConfidenceRuleV0,
    SuspicionConfigurationV0,
    SuspicionContextV0,
    UpstreamObservationStateV0,
    UpstreamObservationV0,
    UpstreamSignalV0,
    detect_suspicion,
)


class _SyntheticCandidateFixture:
    def __init__(self, receipt_id: str = "candidate-dedup-receipt") -> None:
        self.receipt_id = receipt_id
        self.context_builder = "candidate-dedup-test-context"

    def token(
        self, token_id: str, text: str, x: float, y: float, width: float = 50
    ) -> OcrSourceToken:
        return OcrSourceToken(
            receipt_id=self.receipt_id,
            token_id=token_id,
            original_text=text,
            polygon=(
                Point(x, y),
                Point(x + width, y),
                Point(x + width, y + 10),
                Point(x, y + 10),
            ),
            raw_confidence=0.91,
        )

    def evidence(self) -> ReceiptSourceEvidence:
        tokens = (
            self.token("store", "ＰＡＮＴＲＹ MART", 10, 0, 150),
            self.token("date-label", "DATE:", 10, 20, 40),
            self.token("date-value", "13/10/2026", 65, 20, 90),
            self.token("description", "MILK", 10, 45, 45),
            self.token("quantity", "2", 90, 45, 10),
            self.token("multiply", "x", 110, 45, 8),
            self.token("unit", "RM 5.50", 135, 45, 55),
            self.token("line-total", "11.00", 215, 45, 45),
            self.token("total-label", "TOTAL", 135, 80, 55),
            self.token("total-value", "11.00", 215, 80, 45),
        )
        gate = SourceEvidenceGateResult(
            gate_result_id=f"{self.receipt_id}:gate",
            receipt_id=self.receipt_id,
            decision=SourceEvidenceDecision.SUFFICIENT,
        )
        return ReceiptSourceEvidence(
            receipt_id=self.receipt_id,
            image_id=f"{self.receipt_id}:image",
            provenance=SourceProvenance(
                source_system="synthetic-unit-test",
                source_reference=f"memory://{self.receipt_id}",
            ),
            processing_status=SourceProcessingStatus.OCR_COMPLETED,
            tokens=tokens,
            gate_result=gate,
        )

    def adapter_and_method(
        self, field_name: ReceiptFieldName = ReceiptFieldName.STORE_NAME
    ) -> tuple[ProposedAdapterResultV1, MethodReadyFieldV1]:
        b2 = extract_b2(self.evidence())
        b3 = apply_b3(b2)
        adapter = adapt_b2_to_proposed(b2, b3)
        method = next(
            item for item in adapter.method_ready_fields if item.field_name is field_name
        )
        return adapter, method

    def seed(
        self,
        method: MethodReadyFieldV1,
        *,
        suffix: str,
        source_kind: CandidateSourceKind,
        proposed_value: str,
        spans: tuple[SourceCharacterSpanV1, ...] = (),
        event_ids: tuple[str, ...] | None = None,
        rule_ids: tuple[str, ...] | None = None,
    ) -> B3CompatibleSeedV1:
        assert method.b3_ruleset_id is not None
        return B3CompatibleSeedV1(
            seed_id=f"{method.field_id}:dedup-seed:{suffix}",
            receipt_id=method.receipt_id,
            field_id=method.field_id,
            c0_candidate_id=method.c0_candidate_id,
            c0_value=method.c0_value,
            proposed_value=proposed_value,
            source_kind=source_kind,
            b3_ruleset_id=method.b3_ruleset_id,
            b3_event_ids=event_ids or (f"event:{suffix}",),
            b3_rule_ids=rule_ids or (f"rule:{suffix}",),
            source_spans=spans,
        )

    def span(self, method: MethodReadyFieldV1) -> SourceCharacterSpanV1:
        token = method.source_tokens[0]
        end = min(3, len(token.original_text))
        return SourceCharacterSpanV1(
            token_id=token.token_id,
            start=0,
            end=end,
            text=token.original_text[:end],
        )

    def with_seeds(
        self,
        adapter: ProposedAdapterResultV1,
        method: MethodReadyFieldV1,
        seeds: tuple[B3CompatibleSeedV1, ...],
    ) -> tuple[ProposedAdapterResultV1, MethodReadyFieldV1]:
        updated_method = replace(
            method, b3_seed_ids=tuple(seed.seed_id for seed in seeds)
        )
        methods = tuple(
            updated_method if item.field_id == method.field_id else item
            for item in adapter.method_ready_fields
        )
        unrelated = tuple(
            seed for seed in adapter.b3_seeds if seed.field_id != method.field_id
        )
        return (
            replace(
                adapter,
                method_ready_fields=methods,
                b3_seeds=seeds + unrelated,
            ),
            updated_method,
        )

    def suspicion(self, method: MethodReadyFieldV1, suspicious: bool = True):
        def observation(signal: UpstreamSignalV0) -> UpstreamObservationV0:
            state = (
                UpstreamObservationStateV0.FAIL
                if suspicious and signal is UpstreamSignalV0.PARSE_TYPE
                else UpstreamObservationStateV0.PASS
            )
            return UpstreamObservationV0(
                observation_id=f"{method.field_id}:{signal.value}:observation",
                receipt_id=method.receipt_id,
                field_id=method.field_id,
                signal=signal,
                state=state,
                provider_id=self.context_builder,
                provider_version="test-v1",
                evidence_ids=(f"{method.field_id}:{signal.value}:evidence",),
                reason=(None if state is UpstreamObservationStateV0.PASS else "Synthetic."),
            )

        observations = {signal: observation(signal) for signal in UpstreamSignalV0}
        context = SuspicionContextV0(
            context_id=f"{method.method_field_id}:dedup-context",
            receipt_id=method.receipt_id,
            method_field_id=method.method_field_id,
            field_id=method.field_id,
            gate_result_id=method.stored_gate_result.gate_result_id,
            source_image_id=method.source_image_id,
            source_token_ids=method.source_token_ids,
            ocr_confidence_source="synthetic-ocr-source",
            context_builder_id=self.context_builder,
            context_builder_version="test-v1",
            required_content=observations[UpstreamSignalV0.REQUIRED_CONTENT],
            parse_type=observations[UpstreamSignalV0.PARSE_TYPE],
            line_association=observations[UpstreamSignalV0.LINE_ASSOCIATION],
            arithmetic=observations[UpstreamSignalV0.ARITHMETIC],
        )
        theta = ConfigurationRefV1(
            kind=ConfigurationKind.THETA_A,
            configuration_id="theta-a-dedup-test",
            configuration_version="test-v1",
            state=ConfigurationState.READY,
            content_hash="sha256:synthetic-dedup-test",
        )
        config = SuspicionConfigurationV0(
            theta_a_ref=theta,
            ocr_confidence_rule=ConfidenceRuleV0(
                rule_id="dedup-ocr-confidence",
                score_source="synthetic-ocr-source",
                aggregation=ConfidenceAggregationV0.MIN_ALL_REFERENCED,
                threshold=Decimal("0.50"),
                domain_minimum=Decimal("0.00"),
                domain_maximum=Decimal("1.00"),
            ),
            extractor_confidence_rule=ConfidenceRuleV0(
                rule_id="dedup-extractor-confidence",
                score_source=method.b2_extractor_version,
                aggregation=ConfidenceAggregationV0.DIRECT,
                threshold=Decimal("0.50"),
                domain_minimum=Decimal("0.00"),
                domain_maximum=Decimal("1.00"),
            ),
            context_builder_id=self.context_builder,
            context_builder_version="test-v1",
        )
        return detect_suspicion(method, context, config)

    def drafts(
        self,
        *,
        field_name: ReceiptFieldName = ReceiptFieldName.STORE_NAME,
        seed_specs: tuple[tuple[str, CandidateSourceKind, str], ...] = (),
        suspicious: bool = True,
        multi_provenance: bool = False,
    ):
        adapter, method = self.adapter_and_method(field_name)
        span = self.span(method)
        seeds = tuple(
            self.seed(
                method,
                suffix=suffix,
                source_kind=source_kind,
                proposed_value=value,
                spans=(span,) if source_kind is CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR else (),
                event_ids=((f"event:{suffix}:a", f"event:{suffix}:b") if multi_provenance else None),
                rule_ids=((f"rule:{suffix}:a", f"rule:{suffix}:b") if multi_provenance else None),
            )
            for suffix, source_kind, value in seed_specs
        )
        adapter, method = self.with_seeds(adapter, method, seeds)
        return generate_candidate_drafts(
            suspicion_result=self.suspicion(method, suspicious=suspicious),
            adapter_result=adapter,
        )


class ProposedCandidateDeduplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = _SyntheticCandidateFixture()

    def norm(self, field_name: ReceiptFieldName, value: str) -> CandidateNormalizationV0:
        return normalize_candidate_value(field_name=field_name, exact_value=value)

    def test_exact_c0_is_retained_and_input_is_not_mutated(self) -> None:
        drafts = self.fixture.drafts()
        snapshot = deepcopy(drafts)

        result = deduplicate_candidate_drafts(candidate_drafts=drafts)

        self.assertEqual("ＰＡＮＴＲＹ MART", result.candidate_drafts.original.value)
        self.assertEqual("ＰＡＮＴＲＹ MART", result.original_normalization.exact_value)
        self.assertEqual(snapshot, drafts)
        self.assertIs(result.candidate_drafts, drafts)
        with self.assertRaises(FrozenInstanceError):
            result.original_normalization.exact_value = "changed"  # type: ignore[misc]

    def test_non_suspicious_input_has_no_altered_output(self) -> None:
        drafts = self.fixture.drafts(
            suspicious=False,
            seed_specs=(("unused", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry mart"),),
        )
        result = deduplicate_candidate_drafts(candidate_drafts=drafts)
        self.assertEqual((), drafts.altered_proposals)
        self.assertEqual((), result.altered_groups)
        self.assertIsNone(result.equivalent_to_c0)

    def test_text_nfkc_case_punctuation_and_whitespace_are_equivalent(self) -> None:
        values = ("ＭＩＬＫ  “A”", 'milk "a"', "  Milk   “A”  ")
        keys = {
            self.norm(ReceiptFieldName.ITEM_DESCRIPTION, value).normalized_key
            for value in values
        }
        self.assertEqual(1, len(keys))

    def test_substantively_different_text_punctuation_is_preserved(self) -> None:
        hyphen = self.norm(ReceiptFieldName.ITEM_DESCRIPTION, "MILK-POWDER")
        slash = self.norm(ReceiptFieldName.ITEM_DESCRIPTION, "MILK/POWDER")
        space = self.norm(ReceiptFieldName.ITEM_DESCRIPTION, "MILK POWDER")
        self.assertEqual(3, len({hyphen.normalized_key, slash.normalized_key, space.normalized_key}))

    def test_valid_dates_share_iso_key_but_ambiguous_and_invalid_are_tagged(self) -> None:
        valid = tuple(
            self.norm(ReceiptFieldName.PURCHASE_DATE, value)
            for value in ("13/10/2026", "2026-10-13", "13 OCT 2026")
        )
        ambiguous = self.norm(ReceiptFieldName.PURCHASE_DATE, "10/11/2026")
        invalid = self.norm(ReceiptFieldName.PURCHASE_DATE, "31/02/2026")
        self.assertEqual(1, len({item.normalized_key for item in valid}))
        self.assertTrue(all(item.canonical_value == "2026-10-13" for item in valid))
        self.assertIs(ambiguous.parse_status, NormalizationParseStatusV0.PARSE_AMBIGUOUS_FALLBACK)
        self.assertIs(invalid.parse_status, NormalizationParseStatusV0.PARSE_INVALID_FALLBACK)
        self.assertNotEqual(valid[0].normalized_key, ambiguous.normalized_key)
        self.assertNotEqual(ambiguous.normalized_key, invalid.normalized_key)

    def test_quantity_equivalence_and_invalid_fallbacks(self) -> None:
        equivalent = tuple(
            self.norm(ReceiptFieldName.QUANTITY, value)
            for value in ("2", "2.0", "02.000")
        )
        invalid = tuple(
            self.norm(ReceiptFieldName.QUANTITY, value)
            for value in ("0", "-2", "2 kg")
        )
        self.assertEqual(1, len({item.normalized_key for item in equivalent}))
        self.assertTrue(all(item.canonical_value == "2" for item in equivalent))
        self.assertTrue(
            all(item.parse_status is NormalizationParseStatusV0.PARSE_INVALID_FALLBACK for item in invalid)
        )
        self.assertEqual(3, len({item.normalized_key for item in invalid}))

    def test_money_rm_myr_equivalent_but_currency_groups_stay_distinct(self) -> None:
        rm = self.norm(ReceiptFieldName.UNIT_PRICE, "RM 5.5")
        myr = self.norm(ReceiptFieldName.UNIT_PRICE, "myr5.50")
        dollar = self.norm(ReceiptFieldName.UNIT_PRICE, "$5.50")
        absent = self.norm(ReceiptFieldName.UNIT_PRICE, "5.50")
        self.assertEqual(rm.normalized_key, myr.normalized_key)
        self.assertEqual("MYR:5.50", rm.canonical_value)
        self.assertEqual(3, len({rm.normalized_key, dollar.normalized_key, absent.normalized_key}))

    def test_unsupported_money_precision_is_not_silently_rounded(self) -> None:
        unsupported = self.norm(ReceiptFieldName.RECEIPT_TOTAL, "RM 5.555")
        rounded = self.norm(ReceiptFieldName.RECEIPT_TOTAL, "RM 5.56")
        self.assertIs(unsupported.parse_status, NormalizationParseStatusV0.PARSE_INVALID_FALLBACK)
        self.assertNotEqual(unsupported.normalized_key, rounded.normalized_key)
        self.assertIn("5.555", unsupported.canonical_value)

    def test_duplicate_proposals_merge_and_preserve_all_provenance(self) -> None:
        specs = (
            ("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),
            ("source", CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR, "ＰＡＮＴＲＹ SHOP"),
        )
        result = deduplicate_candidate_drafts(
            candidate_drafts=self.fixture.drafts(seed_specs=specs, multi_provenance=True)
        )
        self.assertEqual(1, len(result.altered_groups))
        group = result.altered_groups[0]
        self.assertEqual("ＰＡＮＴＲＹ SHOP", group.representative.proposed_value)
        self.assertEqual(2, len(group.contributing_proposals))
        self.assertEqual(
            {"rule:source:a", "rule:source:b", "rule:generic:a", "rule:generic:b"},
            {rule for proposal in group.contributing_proposals for rule in proposal.b3_rule_ids},
        )
        self.assertEqual(
            {"event:source:a", "event:source:b", "event:generic:a", "event:generic:b"},
            {event for proposal in group.contributing_proposals for event in proposal.b3_event_ids},
        )
        self.assertTrue(group.contributing_proposals[0].source_spans)

    def test_altered_equivalent_to_c0_is_only_in_equivalence_audit(self) -> None:
        specs = (
            ("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry mart"),
            ("source", CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR, "PANTRY MART"),
        )
        result = deduplicate_candidate_drafts(
            candidate_drafts=self.fixture.drafts(seed_specs=specs)
        )
        self.assertEqual((), result.altered_groups)
        self.assertIsNotNone(result.equivalent_to_c0)
        assert result.equivalent_to_c0 is not None
        self.assertEqual(2, len(result.equivalent_to_c0.equivalent_proposals))
        self.assertEqual("ＰＡＮＴＲＹ MART", result.candidate_drafts.original.value)

    def test_representative_uses_source_value_reference_not_adapter_position(self) -> None:
        specs_a = (
            ("z-ref", CandidateSourceKind.GENERIC_NORMALIZATION, "PANTRY SHOP"),
            ("a-ref", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),
        )
        specs_b = tuple(reversed(specs_a))
        first = deduplicate_candidate_drafts(
            candidate_drafts=self.fixture.drafts(seed_specs=specs_a)
        )
        second = deduplicate_candidate_drafts(
            candidate_drafts=self.fixture.drafts(seed_specs=specs_b)
        )
        self.assertEqual("PANTRY SHOP", first.altered_groups[0].representative.proposed_value)
        self.assertEqual(
            first.altered_groups[0].representative.proposed_value,
            second.altered_groups[0].representative.proposed_value,
        )
        self.assertEqual(
            first.altered_groups[0].normalization.normalized_key,
            second.altered_groups[0].normalization.normalized_key,
        )

    def test_proposal_reference_breaks_same_source_and_value_ties(self) -> None:
        specs = (
            ("z-ref", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),
            ("a-ref", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),
        )
        result = deduplicate_candidate_drafts(
            candidate_drafts=self.fixture.drafts(seed_specs=specs)
        )
        self.assertTrue(result.altered_groups[0].representative.proposal_reference.endswith("a-ref"))

    def test_original_adapter_positions_are_preserved(self) -> None:
        specs = (
            ("generic", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),
            ("source", CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR, "PANTRY SHOP"),
        )
        drafts = self.fixture.drafts(seed_specs=specs)
        result = deduplicate_candidate_drafts(candidate_drafts=drafts)
        expected = {
            item.proposal_reference: item.adapter_seed_position
            for item in drafts.altered_proposals
        }
        actual = {
            item.proposal_reference: item.adapter_seed_position
            for item in result.altered_groups[0].contributing_proposals
        }
        self.assertEqual(expected, actual)

    def test_keys_are_compact_deterministic_json_and_field_tagged(self) -> None:
        first = self.norm(ReceiptFieldName.QUANTITY, "2.00")
        second = self.norm(ReceiptFieldName.QUANTITY, "2.00")
        payload = json.loads(first.normalized_key)
        self.assertEqual(first.normalized_key, second.normalized_key)
        self.assertEqual(NORMALIZATION_PROFILE_ID, payload[0])
        self.assertEqual("QUANTITY", payload[1])
        self.assertNotIn(" ", first.normalized_key)

    def test_cross_field_keys_are_distinct_and_results_retain_receipt_identity(self) -> None:
        description = self.norm(ReceiptFieldName.ITEM_DESCRIPTION, "2")
        quantity = self.norm(ReceiptFieldName.QUANTITY, "2")
        self.assertNotEqual(description.normalized_key, quantity.normalized_key)

        other = _SyntheticCandidateFixture("another-dedup-receipt")
        first_result = deduplicate_candidate_drafts(candidate_drafts=self.fixture.drafts())
        other_result = deduplicate_candidate_drafts(candidate_drafts=other.drafts())
        self.assertNotEqual(
            first_result.candidate_drafts.original.method_ready_field.receipt_id,
            other_result.candidate_drafts.original.method_ready_field.receipt_id,
        )
        self.assertIs(first_result.candidate_drafts.original.method_ready_field.field_name, ReceiptFieldName.STORE_NAME)

    def test_reconstructed_output_must_match_canonical_upstream_derivation(self) -> None:
        drafts = self.fixture.drafts(
            seed_specs=(("altered", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
        )
        result = deduplicate_candidate_drafts(candidate_drafts=drafts)
        with self.assertRaises(CandidateDeduplicationIntegrityError):
            replace(result, altered_groups=())
        with self.assertRaises(CandidateDeduplicationIntegrityError):
            replace(result.original_normalization, normalized_key='["forged"]')

    def test_public_boundary_has_no_price_ground_truth_ranking_or_limit_input(self) -> None:
        signature = inspect.signature(deduplicate_candidate_drafts)
        self.assertEqual(("candidate_drafts",), tuple(signature.parameters))
        result = deduplicate_candidate_drafts(candidate_drafts=self.fixture.drafts())
        self.assertFalse(hasattr(result, "candidate_limit"))
        self.assertFalse(hasattr(result, "rank"))
        self.assertFalse(hasattr(result, "candidate_ids"))

    def test_deduplication_does_not_invoke_apply_b3(self) -> None:
        drafts = self.fixture.drafts(
            seed_specs=(("altered", CandidateSourceKind.GENERIC_NORMALIZATION, "pantry shop"),)
        )
        with patch("pipeline.baseline_b3.apply_b3", side_effect=AssertionError("must not run")):
            result = deduplicate_candidate_drafts(candidate_drafts=drafts)
        self.assertEqual(1, len(result.altered_groups))


if __name__ == "__main__":
    unittest.main()
