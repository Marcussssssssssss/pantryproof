"""Synthetic tests for the B1 minimal deterministic receipt extractor."""

from __future__ import annotations

import ast
import inspect
import unittest

import pipeline.baseline_b1 as baseline_b1
from pipeline.baseline_b1 import (
    B1_GEOMETRY_EPSILON,
    B1_LINE_CLUSTER_TOLERANCE_HEIGHTS,
    B1_STORE_HEADER_MAX_NORMALIZED_Y,
    EXTRACTOR_VERSION,
    extract_b1,
)
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
        height: float = 10,
        confidence: float | None = 0.9,
    ) -> OcrSourceToken:
        return OcrSourceToken(
            receipt_id=self.RECEIPT_ID,
            token_id=token_id,
            original_text=text,
            polygon=(
                Point(x, y),
                Point(x + width, y),
                Point(x + width, y + height),
                Point(x, y + height),
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

    def test_numeric_date_parser_accepts_equivalent_interpretations(self) -> None:
        cases = {
            "11/11/2026": ("VALID", "2026-11-11"),
            "02/02/2026": ("VALID", "2026-02-02"),
        }
        for observed, expected in cases.items():
            with self.subTest(observed=observed):
                self.assertEqual(expected, baseline_b1._parse_date(observed))

    def test_numeric_date_parser_keeps_genuine_ambiguity(self) -> None:
        self.assertEqual(("AMBIGUOUS", None), baseline_b1._parse_date("10/11/2026"))

    def test_numeric_date_parser_accepts_only_valid_calendar_interpretation(self) -> None:
        cases = {
            "13/10/2026": ("VALID", "2026-10-13"),
            "10/13/2026": ("VALID", "2026-10-13"),
            "13-10-2026": ("VALID", "2026-10-13"),
        }
        for observed, expected in cases.items():
            with self.subTest(observed=observed):
                self.assertEqual(expected, baseline_b1._parse_date(observed))

    def test_numeric_date_parser_rejects_calendar_invalid_values(self) -> None:
        for observed in ("00/00/2026", "11/00/2026"):
            with self.subTest(observed=observed):
                self.assertEqual(("INVALID", None), baseline_b1._parse_date(observed))

    def test_numeric_date_parser_rejects_mixed_separators(self) -> None:
        self.assertEqual(("INVALID", None), baseline_b1._parse_date("13-10/2026"))

    def test_equivalent_numeric_date_is_extracted_publicly(self) -> None:
        tokens = tuple(
            self.token("date-value", "11/11/2026", 60, 20, width=90)
            if token.token_id == "date-value"
            else token
            for token in self.simple_tokens()
        )

        output = self.output(self.evidence(tokens))

        self.assertEqual(FieldStatus.EXTRACTED, output.purchase_date.status)
        self.assertEqual("2026-11-11", output.purchase_date.value)
        self.assertEqual(("date-value",), output.purchase_date.source_token_ids)

    def test_invalid_and_mixed_separator_anchored_dates_are_unresolved(self) -> None:
        for observed in ("00/00/2026", "11/00/2026", "13-10/2026"):
            with self.subTest(observed=observed):
                tokens = tuple(
                    self.token("date-value", observed, 60, 20, width=90)
                    if token.token_id == "date-value"
                    else token
                    for token in self.simple_tokens()
                )
                output = self.output(self.evidence(tokens))
                self.assertEqual(FieldStatus.UNRESOLVED, output.purchase_date.status)
                self.assertIsNone(output.purchase_date.value)
                self.assertEqual(
                    ("date-value",), output.purchase_date.source_token_ids
                )

    def test_mixed_separator_standalone_date_is_not_selected(self) -> None:
        tokens = (
            self.token("store", "TEST MART", 0, 0),
            self.token("mixed-date", "13-10/2026", 0, 20, width=90),
            self.token("item", "MILK 5.50", 0, 40, width=100),
            self.token("total", "TOTAL 5.50", 0, 60, width=100),
        )

        output = self.output(self.evidence(tokens))

        self.assertEqual(FieldStatus.MISSING, output.purchase_date.status)

    def test_same_separator_numeric_standalone_date_remains_supported(self) -> None:
        tokens = (
            self.token("store", "TEST MART", 0, 0),
            self.token("date", "13/10/2026", 0, 20, width=90),
            self.token("item", "MILK 5.50", 0, 40, width=100),
            self.token("total", "TOTAL 5.50", 0, 60, width=100),
        )

        output = self.output(self.evidence(tokens))

        self.assertEqual(FieldStatus.EXTRACTED, output.purchase_date.status)
        self.assertEqual("2026-10-13", output.purchase_date.value)
        self.assertEqual(("date",), output.purchase_date.source_token_ids)

    def test_year_first_date_allows_one_or_two_digit_components(self) -> None:
        cases = {
            "2026-1-2": ("VALID", "2026-01-02"),
            "2026-01-02": ("VALID", "2026-01-02"),
        }
        for observed, expected in cases.items():
            with self.subTest(observed=observed):
                self.assertEqual(expected, baseline_b1._parse_date(observed))

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
        last_valid = self.output(self.evidence(competing))
        self.assertEqual(FieldStatus.EXTRACTED, last_valid.receipt_total.status)
        self.assertEqual("23.90", last_valid.receipt_total.value)
        self.assertEqual(
            ("second-total-value",), last_valid.receipt_total.source_token_ids
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
        self.assertEqual(FieldStatus.EXTRACTED, row.line_total.status)
        self.assertEqual("12.00", row.line_total.value)
        self.assertIsNone(row.unit_price.value)

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

    def test_frozen_v1_constants_and_identifier(self) -> None:
        self.assertEqual("B1-deterministic-v1", EXTRACTOR_VERSION)
        self.assertEqual(0.25, B1_STORE_HEADER_MAX_NORMALIZED_Y)
        self.assertEqual(0.50, B1_LINE_CLUSTER_TOLERANCE_HEIGHTS)
        self.assertEqual(1e-9, B1_GEOMETRY_EPSILON)

    def test_store_selection_skips_ineligible_header_noise(self) -> None:
        tokens = (
            self.token("noise", "***", 0, 0),
            self.token("store", "PANTRYPROOF TEST MART", 0, 10, width=170),
            self.token("item", "MILK 5.50", 0, 50, width=100),
            self.token("total", "TOTAL 5.50", 0, 90, width=100),
        )
        output = self.output(self.evidence(tokens))
        self.assertEqual("PANTRYPROOF TEST MART", output.store_name.value)
        self.assertEqual(("store",), output.store_name.source_token_ids)

    def test_store_outside_observed_envelope_header_zone_is_missing(self) -> None:
        tokens = (
            self.token("noise", "***", 0, 0),
            self.token("late-store", "LATE MART", 0, 40),
            self.token("item", "MILK 5.50", 0, 60, width=100),
            self.token("total", "TOTAL 5.50", 0, 90, width=100),
        )
        output = self.output(self.evidence(tokens))
        self.assertEqual(FieldStatus.MISSING, output.store_name.status)

    def test_vertical_centroid_controls_line_reading_order(self) -> None:
        tokens = (
            self.token("tall", "TALL", 0, 0, height=100),
            self.token("short", "SHORT", 0, 1, height=1),
        )
        lines = baseline_b1._reading_order_lines(tokens)
        self.assertEqual(("SHORT", "TALL"), tuple(line.text for line in lines))

    def test_line_cluster_exact_tolerance_boundary_is_inclusive(self) -> None:
        tokens = (
            self.token("a", "LEFT", 0, 0),
            self.token("b", "RIGHT", 60, 5),
        )
        lines = baseline_b1._reading_order_lines(tokens)
        self.assertEqual(1, len(lines))
        self.assertEqual("LEFT RIGHT", lines[0].text)

    def test_line_cluster_just_outside_tolerance_is_rejected(self) -> None:
        tokens = (
            self.token("a", "FIRST", 0, 0),
            self.token("b", "SECOND", 0, 5.000001),
        )
        lines = baseline_b1._reading_order_lines(tokens)
        self.assertEqual(2, len(lines))

    def test_bridge_between_adjacent_rows_marks_clusters_ambiguous(self) -> None:
        tokens = (
            self.token("row-1", "ROW ONE", 0, 0),
            self.token("bridge", "BRIDGE", 60, 5),
            self.token("row-2", "ROW TWO", 0, 10),
        )
        lines = baseline_b1._reading_order_lines(tokens)
        self.assertEqual(2, len(lines))
        self.assertTrue(all(line.ambiguous_cluster for line in lines))

    def test_unanchored_complete_date_is_supported(self) -> None:
        tokens = (
            self.token("store", "TEST MART", 0, 0),
            self.token("date", "13 OCTOBER 2026", 0, 20, width=130),
            self.token("item", "MILK 5.50", 0, 40, width=100),
            self.token("total", "TOTAL 5.50", 0, 60, width=100),
        )
        output = self.output(self.evidence(tokens))
        self.assertEqual("2026-10-13", output.purchase_date.value)
        self.assertEqual(("date",), output.purchase_date.source_token_ids)

    def test_conflicting_valid_dates_remain_unresolved(self) -> None:
        tokens = (
            self.token("store", "TEST MART", 0, 0),
            self.token("date-1", "DATE: 2026-10-13", 0, 20, width=140),
            self.token("date-2", "14 OCT 2026", 0, 40, width=100),
            self.token("item", "MILK 5.50", 0, 60, width=100),
            self.token("total", "TOTAL 5.50", 0, 80, width=100),
        )
        output = self.output(self.evidence(tokens))
        self.assertEqual(FieldStatus.UNRESOLVED, output.purchase_date.status)
        self.assertEqual({"date-1", "date-2"}, set(output.purchase_date.source_token_ids))

    def test_equivalent_duplicate_dates_choose_earliest(self) -> None:
        tokens = (
            self.token("store", "TEST MART", 0, 0),
            self.token("date-1", "2026-10-13", 0, 20, width=90),
            self.token("date-2", "13 OCT 2026", 0, 40, width=100),
            self.token("item", "MILK 5.50", 0, 60, width=100),
            self.token("total", "TOTAL 5.50", 0, 80, width=100),
        )
        output = self.output(self.evidence(tokens))
        self.assertEqual("2026-10-13", output.purchase_date.value)
        self.assertEqual(("date-1",), output.purchase_date.source_token_ids)

    def test_date_shaped_text_in_detected_item_row_is_not_purchase_date(self) -> None:
        tokens = (
            self.token("store", "TEST MART", 0, 0),
            self.token("dated-item", "CALENDAR 2026-10-13 5.50", 0, 20, width=190),
            self.token("total", "TOTAL 5.50", 0, 40, width=100),
        )
        output = self.output(self.evidence(tokens))
        self.assertEqual(FieldStatus.MISSING, output.purchase_date.status)
        self.assertEqual("CALENDAR 2026-10-13", output.items[0].description.value)

    def test_explicit_and_unmarked_quantity_grammars(self) -> None:
        tokens = (
            self.token("store", "TEST MART", 0, 0),
            self.token("marked", "MILK QTY: 2 5.50 11.00", 0, 20, width=190),
            self.token("unmarked", "RICE 1 12.90 12.90", 0, 40, width=180),
            self.token("total", "TOTAL 23.90", 0, 60, width=100),
        )
        output = self.output(self.evidence(tokens))
        self.assertEqual(("2", "1"), tuple(row.quantity.value for row in output.items))
        self.assertEqual(("5.50", "12.90"), tuple(row.unit_price.value for row in output.items))
        self.assertEqual(("11.00", "12.90"), tuple(row.line_total.value for row in output.items))

    def test_equal_position_separate_money_regions_are_unresolved(self) -> None:
        tokens = (
            self.token("store", "TEST MART", 0, 0),
            self.token("description", "MILK", 0, 20),
            self.token("quantity", "2", 50, 20, width=10),
            self.token("marker", "x", 70, 20, width=10),
            self.token("total-candidate", "11.00", 95, 20, width=45),
            self.token("unit-candidate", "5.50", 100, 20, width=40),
            self.token("total", "TOTAL 11.00", 0, 40, width=100),
        )
        output = self.output(self.evidence(tokens))
        row = output.items[0]
        self.assertEqual(FieldStatus.UNRESOLVED, row.line_total.status)
        self.assertEqual(
            {"total-candidate", "unit-candidate"}, set(row.line_total.source_token_ids)
        )

    def test_malformed_total_anchors_do_not_override_last_valid_total(self) -> None:
        tokens = (
            self.token("store", "TEST MART", 0, 0),
            self.token("bad-earlier", "TOTAL ERROR", 0, 20),
            self.token("valid", "TOTAL 8.40", 0, 40, width=100),
            self.token("bad-later", "GRAND TOTAL ERROR", 0, 60, width=130),
        )
        output = self.output(self.evidence(tokens))
        self.assertEqual("8.40", output.receipt_total.value)
        self.assertEqual(("valid",), output.receipt_total.source_token_ids)

    def test_shuffled_input_produces_identical_output(self) -> None:
        ordered = self.simple_tokens()
        first = self.output(self.evidence(ordered))
        shuffled = self.output(self.evidence(tuple(reversed(ordered))))
        self.assertEqual(first.store_name, shuffled.store_name)
        self.assertEqual(first.purchase_date, shuffled.purchase_date)
        self.assertEqual(first.items, shuffled.items)
        self.assertEqual(first.receipt_total, shuffled.receipt_total)
        self.assertEqual(first.extraction_status, shuffled.extraction_status)

    def test_module_has_no_b2_retailer_price_or_correction_dependency(self) -> None:
        source = inspect.getsource(baseline_b1)
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertFalse(
            any(
                forbidden in name.lower()
                for name in imported
                for forbidden in ("layout_b2", "retailer", "price", "correction")
            )
        )
        self.assertEqual(("source_evidence",), tuple(inspect.signature(extract_b1).parameters))


if __name__ == "__main__":
    unittest.main()
