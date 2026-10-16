"""Synthetic tests for the provisional B2-as-c0 proposed-method adapter."""

from __future__ import annotations

import inspect
import json
import unittest
from copy import deepcopy
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from pipeline.baseline_b3 import apply_b3
from pipeline.contracts import (
    FieldStatus,
    OcrSourceToken,
    Point,
    PolicyState,
    ReceiptExtractionStatus,
    ReceiptSourceEvidence,
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
    SourceProcessingStatus,
    SourceProvenance,
)
from pipeline.layout_b2 import B2ExtractionResult, extract_b2
from pipeline.proposed.adapter import (
    ProposedAdapterIntegrityError,
    adapt_b2_to_proposed,
)
from pipeline.proposed.contracts import (
    CandidateSourceKind,
    PROPOSED_CONTRACT_VERSION,
    to_deterministic_json,
)


class ProposedAdapterTests(unittest.TestCase):
    RECEIPT_ID = "synthetic-proposed-receipt"

    def token(
        self, token_id: str, text: str, x: float, y: float, width: float = 50
    ) -> OcrSourceToken:
        return OcrSourceToken(
            receipt_id=self.RECEIPT_ID,
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

    def gate(
        self, decision: SourceEvidenceDecision = SourceEvidenceDecision.SUFFICIENT
    ) -> SourceEvidenceGateResult:
        return SourceEvidenceGateResult(
            gate_result_id="synthetic-proposed-gate",
            receipt_id=self.RECEIPT_ID,
            decision=decision,
            reasons=("Synthetic source package is insufficient.",)
            if decision is SourceEvidenceDecision.INSUFFICIENT
            else (),
        )

    def tokens(self, *, store: str = "ＰＡＮＴＲＹ MART") -> tuple[OcrSourceToken, ...]:
        return (
            self.token("store", store, 10, 0, 150),
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

    def evidence(
        self,
        tokens: tuple[OcrSourceToken, ...] | None = None,
        *,
        decision: SourceEvidenceDecision = SourceEvidenceDecision.SUFFICIENT,
    ) -> ReceiptSourceEvidence:
        return ReceiptSourceEvidence(
            receipt_id=self.RECEIPT_ID,
            image_id="synthetic-proposed-image",
            provenance=SourceProvenance(
                source_system="synthetic-unit-test",
                source_reference="memory://synthetic-proposed-image",
            ),
            processing_status=SourceProcessingStatus.OCR_COMPLETED,
            tokens=self.tokens() if tokens is None else tokens,
            gate_result=self.gate(decision),
        )

    def results(self):
        b2 = extract_b2(self.evidence())
        b3 = apply_b3(b2)
        return b2, b3, adapt_b2_to_proposed(b2, b3)

    def test_original_b2_object_and_value_are_permanent_c0(self) -> None:
        b2, b3, adapted = self.results()
        output = b2.receipt_output
        assert output is not None and b3.receipt_output is not None
        store = adapted.method_ready_fields[0]

        self.assertIs(output.store_name, store.original_b2_field)
        self.assertEqual("ＰＡＮＴＲＹ MART", store.original_value)
        self.assertEqual(store.original_value, store.c0_value)
        self.assertEqual(f"{store.field_id}:c0", store.c0_candidate_id)
        self.assertEqual("pantry mart", b3.receipt_output.store_name.value)
        self.assertNotEqual(store.c0_value, b3.receipt_output.store_name.value)
        self.assertEqual(PROPOSED_CONTRACT_VERSION, store.record_version)

    def test_b3_difference_is_a_seed_not_a_runtime_candidate(self) -> None:
        _, _, adapted = self.results()
        store = adapted.method_ready_fields[0]
        seed = next(item for item in adapted.b3_seeds if item.field_id == store.field_id)

        self.assertEqual(CandidateSourceKind.GENERIC_NORMALIZATION, seed.source_kind)
        self.assertEqual(store.c0_candidate_id, seed.c0_candidate_id)
        self.assertEqual(store.c0_value, seed.c0_value)
        self.assertEqual("pantry mart", seed.proposed_value)
        self.assertIn(seed.seed_id, store.b3_seed_ids)
        self.assertFalse(hasattr(seed, "limit_status"))
        self.assertFalse(hasattr(adapted, "selected_candidate"))

    def test_every_extracted_field_has_c0_even_without_b3_transformation(self) -> None:
        b2 = extract_b2(self.evidence(tokens=self.tokens(store="PANTRY MART")))
        adapted = adapt_b2_to_proposed(b2)
        output = b2.receipt_output
        assert output is not None
        original_fields = (
            output.store_name,
            output.purchase_date,
            *(field for row in output.items for field in row.fields),
            output.receipt_total,
        )
        extracted = tuple(
            field for field in original_fields if field.status is FieldStatus.EXTRACTED
        )

        self.assertEqual(tuple(field.field_id for field in extracted), tuple(
            field.field_id for field in adapted.method_ready_fields
        ))
        self.assertTrue(all(field.original_value == field.c0_value for field in adapted.method_ready_fields))
        self.assertTrue(all(field.b3_seed_ids == () for field in adapted.method_ready_fields))

    def test_source_tokens_order_and_literal_objects_are_preserved(self) -> None:
        b2, _, adapted = self.results()
        output = b2.receipt_output
        assert output is not None
        unit = next(
            item for item in adapted.method_ready_fields if item.field_id.endswith("unit-price")
        )
        token_by_id = {token.token_id: token for token in output.source_evidence.tokens}
        self.assertEqual(unit.source_token_ids, tuple(token.token_id for token in unit.source_tokens))
        self.assertTrue(
            all(token is token_by_id[token.token_id] for token in unit.source_tokens)
        )
        self.assertEqual("RM 5.50", unit.source_tokens[0].original_text)

    def test_missing_fields_are_recorded_as_excluded_not_invented(self) -> None:
        b2 = extract_b2(
            self.evidence(
                tokens=(
                    self.token("store", "STORE", 10, 0),
                    self.token("date-label", "DATE:", 10, 20, 40),
                    self.token("date-value", "2026-10-13", 65, 20, 90),
                )
            )
        )
        output = b2.receipt_output
        assert output is not None
        self.assertEqual(ReceiptExtractionStatus.PARTIAL, output.extraction_status)
        adapted = adapt_b2_to_proposed(b2)

        self.assertEqual((output.store_name.field_id,), tuple(
            field.field_id for field in adapted.method_ready_fields
        ))
        self.assertIn(output.purchase_date.field_id, adapted.excluded_b2_field_ids)
        self.assertIn(output.receipt_total.field_id, adapted.excluded_b2_field_ids)

    def test_structurally_failed_sufficient_b2_is_not_changed_to_fallback(self) -> None:
        b2 = extract_b2(self.evidence(tokens=()))
        output = b2.receipt_output
        assert output is not None
        self.assertEqual(ReceiptExtractionStatus.FAILED, output.extraction_status)
        adapted = adapt_b2_to_proposed(b2)

        self.assertIsNone(adapted.fallback_disposition)
        self.assertEqual(ReceiptExtractionStatus.FAILED, adapted.b2_extraction_status)
        self.assertEqual((), adapted.method_ready_fields)
        self.assertTrue(adapted.excluded_b2_field_ids)

    def test_insufficient_source_preserves_fallback(self) -> None:
        b2 = extract_b2(
            self.evidence(decision=SourceEvidenceDecision.INSUFFICIENT)
        )
        b3 = apply_b3(b2)
        adapted = adapt_b2_to_proposed(b2, b3)

        self.assertIsNone(adapted.b2_extraction_status)
        self.assertEqual((), adapted.method_ready_fields)
        self.assertEqual((), adapted.b3_seeds)
        self.assertEqual(
            PolicyState.FALLBACK_NO_UPDATE, adapted.fallback_disposition.state
        )

    def test_corrupted_stored_gate_pass_is_integrity_failure(self) -> None:
        b2 = deepcopy(extract_b2(self.evidence()))
        output = b2.receipt_output
        assert output is not None
        object.__setattr__(
            output.source_evidence.gate_result,
            "decision",
            SourceEvidenceDecision.INSUFFICIENT,
        )
        with self.assertRaisesRegex(ProposedAdapterIntegrityError, "stored sufficient"):
            adapt_b2_to_proposed(b2)

    def test_wrong_b2_version_is_integrity_failure(self) -> None:
        b2 = deepcopy(extract_b2(self.evidence()))
        output = b2.receipt_output
        assert output is not None
        object.__setattr__(output, "extractor_version", "B2-unrelated")
        with self.assertRaisesRegex(ProposedAdapterIntegrityError, "exact B2 version"):
            adapt_b2_to_proposed(b2)

    def test_unrelated_b3_result_is_rejected(self) -> None:
        first = extract_b2(self.evidence())
        second = extract_b2(self.evidence())
        unrelated_b3 = apply_b3(second)
        with self.assertRaisesRegex(ProposedAdapterIntegrityError, "exact B2 result"):
            adapt_b2_to_proposed(first, unrelated_b3)

    def test_adapter_cannot_rerun_gate_ocr_or_extraction(self) -> None:
        b2, b3, _ = self.results()
        self.assertEqual(
            ("b2_result", "b3_result"),
            tuple(inspect.signature(adapt_b2_to_proposed).parameters),
        )
        with patch("pipeline.layout_b2.extract_b2", side_effect=AssertionError):
            adapted = adapt_b2_to_proposed(b2, b3)
        self.assertTrue(adapted.method_ready_fields)

    def test_adapter_output_and_upstream_records_are_immutable(self) -> None:
        b2, b3, adapted = self.results()
        with self.assertRaises(FrozenInstanceError):
            adapted.receipt_id = "changed"
        self.assertIs(adapted.original_b2_result, b2)
        self.assertIs(b3.original_b2_result, b2)

    def test_repeated_adaptation_is_deterministic_and_does_not_mutate_baselines(self) -> None:
        b2 = extract_b2(self.evidence())
        b3 = apply_b3(b2)
        before_b2 = deepcopy(b2)
        before_b3 = deepcopy(b3)
        first = adapt_b2_to_proposed(b2, b3)
        second = adapt_b2_to_proposed(b2, b3)

        self.assertEqual(first, second)
        self.assertEqual(before_b2, b2)
        self.assertEqual(before_b3, b3)

    def test_language_neutral_cross_component_fixture(self) -> None:
        _, _, adapted = self.results()
        changed = next(
            field for field in adapted.method_ready_fields if field.b3_seed_ids
        )
        seed = next(item for item in adapted.b3_seeds if item.field_id == changed.field_id)
        payload = {
            "fixture_version": "proposed-b2-c0-b3-seed-v1",
            "contract_version": PROPOSED_CONTRACT_VERSION,
            "receipt_id": adapted.receipt_id,
            "gate": {
                "gate_result_id": adapted.stored_gate_result.gate_result_id,
                "decision": adapted.stored_gate_result.decision,
            },
            "method_ready_field": {
                "method_field_id": changed.method_field_id,
                "field_id": changed.field_id,
                "field_name": changed.field_name,
                "original_value": changed.original_value,
                "c0_candidate_id": changed.c0_candidate_id,
                "c0_value": changed.c0_value,
                "source_token_ids": changed.source_token_ids,
                "b3_seed_ids": changed.b3_seed_ids,
            },
            "b3_seed": seed,
            "decimal_value": Decimal("0.8750"),
            "unavailable_value": None,
        }
        actual = to_deterministic_json(payload)
        fixture_path = (
            Path(__file__).parent
            / "fixtures"
            / "proposed"
            / "b2_c0_b3_seed_v1.json"
        )
        expected_payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        expected = json.dumps(
            expected_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.assertEqual(expected, actual)
        self.assertEqual(actual, to_deterministic_json(payload))
        self.assertIn('"decimal_value":"0.8750"', actual)
        self.assertIn('"unavailable_value":null', actual)


if __name__ == "__main__":
    unittest.main()
