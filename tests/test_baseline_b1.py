"""Synthetic tests for the B1 minimal deterministic receipt extractor."""

from __future__ import annotations

import inspect
import unittest

from pipeline.baseline_b1 import EXTRACTOR_VERSION, extract_b1
from pipeline.contracts import (
    FieldStatus,
    OcrSourceToken,
    OutputStage,
    Point,
    PolicyState,
    ReceiptExtractionStatus,
    ReceiptSourceEvidence,
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
    SourceProcessingStatus,
    SourceProvenance,
)


class BaselineB1Tests(unittest.TestCase):
    RECEIPT_ID = "synthetic-b1-receipt"

    def token(
        self,
        token_id: str,
        text: str,
        x: float,
        y: float,
        *,
        width: float = 40,
        confidence: float | None = 0.9,
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
            raw_confidence=confidence,
        )

    def simple_tokens(self) -> tuple[OcrSourceToken, ...]:
        return (
            self.token("store", "PANTRYPROOF TEST MART", 0, 0, width=170),
            self.token("date-label", "DATE:", 0, 20),
            self.token("date-value", "2026-10-13", 60, 20, width=90),
            self.token("item1-description", "MILK", 0, 40),
            self.token("item1-quantity", "2", 60, 40, width=10),
            self.token("item1-x", "x", 85, 40, width=10),
            self.token("item1-unit", "5.50", 110, 40),
            self.token("item1-total", "11.00", 170, 40),
            self.token("item2-description", "RICE", 0, 60),
            self.token("item2-quantity", "1", 60, 60, width=10),
            self.token("item2-x", "x", 85, 60, width=10),
            self.token("item2-unit", "12.90", 110, 60),
            self.token("item2-total", "12.90", 170, 60),
            self.token("total-label", "TOTAL", 0, 80),
            self.token("total-value", "23.90", 70, 80),
        )

    def gate(
        self,
        decision: SourceEvidenceDecision = SourceEvidenceDecision.SUFFICIENT,
    ) -> SourceEvidenceGateResult:
        return SourceEvidenceGateResult(
            gate_result_id="synthetic-b1-gate",
            receipt_id=self.RECEIPT_ID,
            decision=decision,
            reasons=("Synthetic fixture records insufficient source evidence.",)
            if decision is SourceEvidenceDecision.INSUFFICIENT
            else (),
        )

    def evidence(
        self,
        tokens: tuple[OcrSourceToken, ...] | None = None,
        *,
        gate_result: SourceEvidenceGateResult | None = None,
    ) -> ReceiptSourceEvidence:
        return ReceiptSourceEvidence(
            receipt_id=self.RECEIPT_ID,
            image_id="synthetic-b1-image",
            provenance=SourceProvenance(
                source_system="synthetic-unit-test",
                source_reference="memory://synthetic-b1-image",
            ),
            processing_status=SourceProcessingStatus.OCR_COMPLETED,
            tokens=tokens if tokens is not None else self.simple_tokens(),
            gate_result=gate_result or self.gate(),
        )

    def output(self, evidence: ReceiptSourceEvidence | None = None):
        result = extract_b1(evidence or self.evidence())
        self.assertIsNone(result.pre_resolution_disposition)
        self.assertIsNotNone(result.receipt_output)
        return result.receipt_output

    def test_simple_receipt_maps_store_date_two_rows_and_total(self) -> None:
        output = self.output()

        self.assertEqual("PANTRYPROOF TEST MART", output.store_name.value)
        self.assertEqual("2026-10-13", output.purchase_date.value)
        self.assertEqual(2, len(output.items))
        self.assertEqual(
            ("MILK", "2", "5.50", "11.00"),
            tuple(field.value for field in output.items[0].fields),
        )
        self.assertEqual(
            ("RICE", "1", "12.90", "12.90"),
            tuple(field.value for field in output.items[1].fields),
        )
        self.assertEqual("23.90", output.receipt_total.value)
        self.assertEqual(ReceiptExtractionStatus.EXTRACTED, output.extraction_status)
        self.assertEqual(EXTRACTOR_VERSION, output.extractor_version)

    def test_every_extracted_field_references_its_actual_ocr_token(self) -> None:
        output = self.output()

        self.assertEqual(("store",), output.store_name.source_token_ids)
        self.assertEqual(("date-value",), output.purchase_date.source_token_ids)
        self.assertEqual(
            (
                ("item1-description",),
                ("item1-quantity",),
                ("item1-unit",),
                ("item1-total",),
            ),
            tuple(field.source_token_ids for field in output.items[0].fields),
        )
        self.assertEqual(("total-value",), output.receipt_total.source_token_ids)

    def test_missing_purchase_date_is_explicit(self) -> None:
        tokens = tuple(
            token
            for token in self.simple_tokens()
            if token.token_id not in {"date-label", "date-value"}
        )

        output = self.output(self.evidence(tokens))

        self.assertEqual(FieldStatus.MISSING, output.purchase_date.status)
        self.assertIsNone(output.purchase_date.value)
        self.assertEqual(ReceiptExtractionStatus.PARTIAL, output.extraction_status)

    def test_ambiguous_numeric_date_is_not_guessed(self) -> None:
        tokens = tuple(
            self.token("date-value", "10/11/2026", 60, 20, width=90)
            if token.token_id == "date-value"
            else token
            for token in self.simple_tokens()
        )

        output = self.output(self.evidence(tokens))

        self.assertEqual(FieldStatus.UNRESOLVED, output.purchase_date.status)
        self.assertIsNone(output.purchase_date.value)

    def test_missing_and_competing_receipt_totals_are_explicit(self) -> None:
        without_total = tuple(
            token
            for token in self.simple_tokens()
            if token.token_id not in {"total-label", "total-value"}
        )
        missing = self.output(self.evidence(without_total))
        self.assertEqual(FieldStatus.MISSING, missing.receipt_total.status)

        competing = self.simple_tokens() + (
            self.token("second-total-label", "GRAND TOTAL", 0, 100, width=90),
            self.token("second-total-value", "23.90", 110, 100),
        )
        unresolved = self.output(self.evidence(competing))
        self.assertEqual(FieldStatus.UNRESOLVED, unresolved.receipt_total.status)
        self.assertEqual(
            {
                "total-label",
                "total-value",
                "second-total-label",
                "second-total-value",
            },
            set(unresolved.receipt_total.source_token_ids),
        )

    def test_subtotal_and_change_are_not_selected_as_receipt_total(self) -> None:
        base = tuple(
            token
            for token in self.simple_tokens()
            if token.token_id not in {"total-label", "total-value"}
        )
        tokens = base + (
            self.token("subtotal-label", "SUBTOTAL", 0, 80, width=65),
            self.token("subtotal-value", "23.90", 80, 80),
            self.token("change-label", "CHANGE", 0, 100, width=55),
            self.token("change-value", "6.10", 80, 100),
            self.token("tax-label", "TAX", 0, 120, width=30),
            self.token("tax-value", "1.20", 80, 120),
            self.token("cash-label", "CASH", 0, 140, width=40),
            self.token("cash-value", "30.00", 80, 140),
            self.token("tendered-label", "TENDERED", 0, 160, width=70),
            self.token("tendered-value", "30.00", 90, 160),
            self.token("balance-label", "BALANCE", 0, 180, width=60),
            self.token("balance-value", "6.10", 80, 180),
            self.token("total-label", "TOTAL", 0, 200),
            self.token("total-value", "23.90", 70, 200),
        )

        output = self.output(self.evidence(tokens))

        self.assertEqual(FieldStatus.EXTRACTED, output.receipt_total.status)
        self.assertEqual("23.90", output.receipt_total.value)
        self.assertEqual(("total-value",), output.receipt_total.source_token_ids)
        self.assertEqual(2, len(output.items))

    def test_generic_financial_summary_lines_are_not_emitted_as_items(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 0, 0, width=170),
            self.token("item", "MILK 2 x 5.50 11.00", 0, 20, width=180),
            self.token("discount", "DISCOUNT 2.00", 0, 40, width=100, confidence=0.81),
            self.token("rounding", "ROUNDING 0.05", 0, 60, width=100),
            self.token("voucher", "VOUCHER 5.00", 0, 80, width=100),
            self.token("service-charge", "SERVICE CHARGE 0.60", 0, 100, width=145),
            self.token("gst", "GST 0.66", 0, 120, width=70),
            self.token("sst", "SST 0.66", 0, 140, width=70),
            self.token("service-tax", "SERVICE TAX 0.66", 0, 160, width=120),
            self.token("payment-total", "PAYMENT TOTAL 10.31", 0, 180, width=150),
            self.token("total", "TOTAL 10.31", 0, 200, width=100),
        )
        evidence = self.evidence(tokens)

        output = self.output(evidence)

        self.assertEqual(1, len(output.items))
        self.assertEqual("MILK", output.items[0].description.value)
        self.assertEqual(("item",), output.items[0].description.source_token_ids)
        self.assertIs(evidence, output.source_evidence)
        self.assertEqual(
            (
                "DISCOUNT 2.00",
                "ROUNDING 0.05",
                "VOUCHER 5.00",
                "SERVICE CHARGE 0.60",
            ),
            tuple(token.original_text for token in evidence.tokens[2:6]),
        )
        self.assertEqual(0.81, evidence.tokens[2].raw_confidence)

    def test_summary_words_inside_longer_product_descriptions_are_not_filtered(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 0, 0, width=170),
            self.token("discount-product", "DISCOUNT BISCUITS 2.00", 0, 20, width=180),
            self.token("rounding-product", "ROUNDING TOOL 0.05", 0, 40, width=160),
            self.token("voucher-product", "VOUCHER HOLDER 5.00", 0, 60, width=170),
            self.token(
                "service-charge-product",
                "SERVICE CHARGE BISCUITS 0.60",
                0,
                80,
                width=220,
            ),
            self.token("total", "TOTAL 7.65", 0, 100, width=100),
        )

        output = self.output(self.evidence(tokens))

        self.assertEqual(
            (
                "DISCOUNT BISCUITS",
                "ROUNDING TOOL",
                "VOUCHER HOLDER",
                "SERVICE CHARGE BISCUITS",
            ),
            tuple(row.description.value for row in output.items),
        )
        self.assertTrue(
            all(row.line_total.status is FieldStatus.EXTRACTED for row in output.items)
        )
        self.assertTrue(
            all(row.quantity.status is FieldStatus.MISSING for row in output.items)
        )

    def test_detected_partial_item_row_does_not_infer_quantity_or_unit_price(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 0, 0, width=170),
            self.token("date-label", "DATE:", 0, 20),
            self.token("date-value", "2026-10-13", 60, 20, width=90),
            self.token("bread-description", "BREAD", 0, 40),
            self.token("bread-total", "8.40", 80, 40),
            self.token("total-label", "TOTAL", 0, 60),
            self.token("total-value", "8.40", 70, 60),
        )

        output = self.output(self.evidence(tokens))
        row = output.items[0]

        self.assertEqual(FieldStatus.EXTRACTED, row.description.status)
        self.assertEqual(FieldStatus.MISSING, row.quantity.status)
        self.assertEqual(FieldStatus.MISSING, row.unit_price.status)
        self.assertEqual(FieldStatus.EXTRACTED, row.line_total.status)
        self.assertEqual("8.40", row.line_total.value)
        self.assertEqual(ReceiptExtractionStatus.PARTIAL, output.extraction_status)

    def test_undetected_item_line_is_not_fabricated(self) -> None:
        tokens = tuple(
            token
            for token in self.simple_tokens()
            if not token.token_id.startswith("item2-")
        )

        output = self.output(self.evidence(tokens))

        self.assertEqual(1, len(output.items))
        self.assertEqual("MILK", output.items[0].description.value)

    def test_insufficient_gate_returns_fallback_without_structured_output(self) -> None:
        evidence = self.evidence(
            gate_result=self.gate(SourceEvidenceDecision.INSUFFICIENT)
        )

        result = extract_b1(evidence)

        self.assertIsNone(result.receipt_output)
        self.assertIsNotNone(result.pre_resolution_disposition)
        self.assertEqual(
            PolicyState.FALLBACK_NO_UPDATE,
            result.pre_resolution_disposition.state,
        )
        self.assertIs(
            evidence.gate_result,
            result.pre_resolution_disposition.gate_result,
        )

    def test_extractor_does_not_invoke_a_second_source_gate(self) -> None:
        gate_calls = 0

        def source_evidence_sufficient_fixture() -> SourceEvidenceGateResult:
            nonlocal gate_calls
            gate_calls += 1
            return self.gate()

        evidence = self.evidence(gate_result=source_evidence_sufficient_fixture())
        self.assertEqual(1, gate_calls)

        self.output(evidence)

        self.assertEqual(1, gate_calls)

    def test_repeated_extraction_is_deterministic(self) -> None:
        evidence = self.evidence(
            self.simple_tokens()
            + (self.token("discount", "DISCOUNT 2.00", 0, 100, width=100),)
        )

        first = extract_b1(evidence)
        second = extract_b1(evidence)

        self.assertEqual(first, second)

    def test_ambiguous_item_amount_association_remains_unresolved(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 0, 0, width=170),
            self.token("ambiguous-item", "MILK 2 x 5.50 11.00 12.00", 0, 20, width=220),
            self.token("total", "TOTAL 12.00", 0, 40, width=100),
        )

        output = self.output(self.evidence(tokens))
        row = output.items[0]

        self.assertEqual("MILK", row.description.value)
        self.assertEqual("2", row.quantity.value)
        self.assertEqual(FieldStatus.UNRESOLVED, row.unit_price.status)
        self.assertEqual(FieldStatus.UNRESOLVED, row.line_total.status)
        self.assertIsNone(row.unit_price.value)
        self.assertIsNone(row.line_total.value)

    def test_overlapping_row_regions_do_not_create_a_silent_association(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 0, 0, width=170),
            self.token("overlap-description", "MILK", 0, 20, width=100),
            self.token("overlap-values", "2 x 5.50 11.00", 60, 20, width=120),
            self.token("total", "TOTAL 11.00", 0, 40, width=100),
        )

        output = self.output(self.evidence(tokens))

        self.assertEqual((), output.items)

    def test_original_ocr_text_confidence_and_evidence_identity_are_preserved(self) -> None:
        tokens = list(self.simple_tokens())
        tokens[0] = self.token(
            "store",
            "  PANTRYPROOF TEST MART  ",
            0,
            0,
            width=190,
            confidence=0.713,
        )
        evidence = self.evidence(tuple(tokens))

        output = self.output(evidence)

        self.assertIs(evidence, output.source_evidence)
        self.assertEqual("  PANTRYPROOF TEST MART  ", evidence.tokens[0].original_text)
        self.assertEqual(0.713, evidence.tokens[0].raw_confidence)
        self.assertEqual("PANTRYPROOF TEST MART", output.store_name.value)
        self.assertIsNone(output.store_name.confidence)

    def test_b1_api_has_no_external_price_or_retailer_reference_input(self) -> None:
        parameters = tuple(inspect.signature(extract_b1).parameters)

        self.assertEqual(("source_evidence",), parameters)
        self.assertEqual(2, len(self.output().items))

    def test_sufficient_output_stays_pre_review_and_has_no_policy_or_persistence_event(self) -> None:
        result = extract_b1(self.evidence())

        self.assertIsNotNone(result.receipt_output)
        self.assertEqual(
            OutputStage.PRE_REVIEW_AUTOMATIC,
            result.receipt_output.output_stage,
        )
        self.assertIsNone(result.pre_resolution_disposition)
        self.assertFalse(hasattr(result, "persistence_outcome"))


if __name__ == "__main__":
    unittest.main()
