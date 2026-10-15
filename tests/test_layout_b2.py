"""Synthetic tests for the B2 deterministic layout-aware extractor."""

from __future__ import annotations

import ast
import inspect
import unittest

import pipeline.layout_b2 as layout_b2
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
from pipeline.layout_b2 import EXTRACTOR_VERSION, extract_b2


class LayoutB2Tests(unittest.TestCase):
    RECEIPT_ID = "synthetic-b2-receipt"

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

    def gate(
        self,
        decision: SourceEvidenceDecision = SourceEvidenceDecision.SUFFICIENT,
    ) -> SourceEvidenceGateResult:
        return SourceEvidenceGateResult(
            gate_result_id="synthetic-b2-gate",
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
            image_id="synthetic-b2-image",
            provenance=SourceProvenance(
                source_system="synthetic-unit-test",
                source_reference="memory://synthetic-b2-image",
            ),
            processing_status=SourceProcessingStatus.OCR_COMPLETED,
            tokens=tokens if tokens is not None else self.simple_tokens(),
            gate_result=gate_result or self.gate(),
        )

    def output(self, evidence: ReceiptSourceEvidence | None = None):
        result = extract_b2(evidence or self.evidence())
        self.assertIsNone(result.pre_resolution_disposition)
        self.assertIsNotNone(result.receipt_output)
        return result.receipt_output

    def simple_tokens(self) -> tuple[OcrSourceToken, ...]:
        return (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=180),
            self.token("date-label", "DATE:", 10, 20, width=45),
            self.token("date-value", "2026-10-13", 70, 20, width=90),
            self.token("item1-description", "MILK", 10, 45, width=45),
            self.token("item1-quantity", "2", 110, 45, width=10),
            self.token("item1-x", "x", 130, 45, width=8),
            self.token("item1-unit", "5.50", 155, 45, width=38),
            self.token("item1-total", "11.00", 220, 45, width=45),
            self.token("item2-description", "RICE", 10, 65, width=45),
            self.token("item2-quantity", "1", 110, 65, width=10),
            self.token("item2-x", "x", 130, 65, width=8),
            self.token("item2-unit", "12.90", 155, 65, width=38),
            self.token("item2-total", "12.90", 220, 65, width=45),
            self.token("total-label", "TOTAL", 130, 95, width=55),
            self.token("total-value", "23.90", 220, 95, width=45),
        )

    def test_simple_complete_receipt(self) -> None:
        output = self.output()

        self.assertEqual("PANTRYPROOF TEST MART", output.store_name.value)
        self.assertEqual("2026-10-13", output.purchase_date.value)
        self.assertEqual(
            (("MILK", "2", "5.50", "11.00"), ("RICE", "1", "12.90", "12.90")),
            tuple(tuple(field.value for field in row.fields) for row in output.items),
        )
        self.assertEqual("23.90", output.receipt_total.value)
        self.assertEqual(ReceiptExtractionStatus.EXTRACTED, output.extraction_status)
        self.assertEqual(OutputStage.PRE_REVIEW_AUTOMATIC, output.output_stage)
        self.assertEqual(EXTRACTOR_VERSION, output.extractor_version)

    def test_split_token_column_row_uses_source_regions(self) -> None:
        output = self.output()
        first = output.items[0]

        self.assertEqual(
            (
                ("item1-description",),
                ("item1-quantity",),
                ("item1-unit",),
                ("item1-total",),
            ),
            tuple(field.source_token_ids for field in first.fields),
        )

    def test_whole_line_region_is_supported_without_fake_word_tokens(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=180),
            self.token("date", "DATE: 2026-10-13", 10, 20, width=150),
            self.token("whole-item", "MILK 2 x 5.50 11.00", 10, 45, width=255),
            self.token("total", "TOTAL 11.00", 130, 75, width=135),
        )

        row = self.output(self.evidence(tokens)).items[0]

        self.assertEqual(("MILK", "2", "5.50", "11.00"), tuple(f.value for f in row.fields))
        self.assertTrue(all(f.source_token_ids == ("whole-item",) for f in row.fields))

    def test_unmarked_whole_line_retains_observed_quantity_as_unresolved(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=180),
            self.token("date", "DATE: 2026-10-13", 10, 20, width=150),
            self.token("whole-item", "MILK 2 5.50 11.00", 10, 45, width=255),
            self.token("total", "TOTAL 11.00", 130, 75, width=135),
        )

        row = self.output(self.evidence(tokens)).items[0]

        self.assertEqual("MILK", row.description.value)
        self.assertEqual(FieldStatus.UNRESOLVED, row.quantity.status)
        self.assertEqual(("whole-item",), row.quantity.source_token_ids)
        self.assertEqual(FieldStatus.UNRESOLVED, row.unit_price.status)
        self.assertEqual(FieldStatus.UNRESOLVED, row.line_total.status)

    def test_repeated_columns_extract_rows_without_multiplier_tokens(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=180),
            self.token("date", "DATE: 2026-10-13", 10, 20, width=150),
            self.token("d1", "MILK", 10, 45, width=45),
            self.token("q1", "2", 110, 45, width=10),
            self.token("u1", "5.50", 155, 45, width=38),
            self.token("l1", "11.00", 220, 45, width=45),
            self.token("d2", "RICE", 10, 65, width=45),
            self.token("q2", "1", 109, 65, width=11),
            self.token("u2", "12.90", 154, 65, width=39),
            self.token("l2", "12.90", 219, 65, width=46),
            self.token("total", "TOTAL 23.90", 130, 95, width=135),
        )

        output = self.output(self.evidence(tokens))

        self.assertEqual(
            (("MILK", "2", "5.50", "11.00"), ("RICE", "1", "12.90", "12.90")),
            tuple(tuple(field.value for field in row.fields) for row in output.items),
        )

    def test_vertical_jitter_within_tolerance_keeps_one_complete_row(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=180),
            self.token("date", "DATE: 2026-10-13", 10, 20, width=150),
            self.token("description", "MILK", 10, 45, width=45),
            self.token("quantity", "2", 110, 47, width=10),
            self.token("multiplier", "x", 130, 44, width=8),
            self.token("unit", "5.50", 155, 46, width=38),
            self.token("line-total", "11.00", 220, 45, width=45),
            self.token("total", "TOTAL 11.00", 130, 80, width=135),
        )

        row = self.output(self.evidence(tokens)).items[0]

        self.assertEqual(("MILK", "2", "5.50", "11.00"), tuple(f.value for f in row.fields))

    def test_line_grouping_tolerance_accepts_equality(self) -> None:
        self.assertEqual(0.50, layout_b2.LINE_MIN_VERTICAL_OVERLAP)
        self.assertEqual(0.50, layout_b2.LINE_MAX_CENTER_DISTANCE)
        tokens = (
            self.token("left", "LEFT", 0, 0, width=30),
            self.token("right", "RIGHT", 50, 5, width=35),
        )

        graph = layout_b2._build_layout_graph(tokens)

        self.assertEqual(1, len(graph.lines))
        self.assertEqual(("left", "right"), graph.lines[0].token_ids)

    def test_line_grouping_tolerance_rejects_just_outside_boundary(self) -> None:
        tokens = (
            self.token("left", "LEFT", 0, 0, width=30),
            self.token("right", "RIGHT", 50, 5.00001, width=35),
        )

        graph = layout_b2._build_layout_graph(tokens)

        self.assertEqual(2, len(graph.lines))

    def test_two_column_item_keeps_quantity_and_unit_price_missing(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=180),
            self.token("date", "DATE: 2026-10-13", 10, 20, width=150),
            self.token("description", "BREAD", 10, 45, width=55),
            self.token("line-total", "8.40", 220, 45, width=45),
            self.token("total", "TOTAL 8.40", 140, 75, width=125),
        )

        row = self.output(self.evidence(tokens)).items[0]

        self.assertEqual("BREAD", row.description.value)
        self.assertEqual(FieldStatus.MISSING, row.quantity.status)
        self.assertEqual(FieldStatus.MISSING, row.unit_price.status)
        self.assertEqual("8.40", row.line_total.value)

    def test_horizontally_disconnected_regions_do_not_form_an_item(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=180),
            self.token("date", "DATE: 2026-10-13", 10, 20, width=150),
            self.token("description", "MILK", 10, 45, width=45),
            self.token("far-amount", "11.00", 2000, 45, width=45),
            self.token("total", "TOTAL 11.00", 1900, 80, width=145),
        )

        output = self.output(self.evidence(tokens))

        self.assertEqual((), output.items)

    def test_repeated_integer_column_right_of_amounts_is_not_quantity(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=180),
            self.token("date", "DATE: 2026-10-13", 10, 20, width=150),
            self.token("d1", "MILK", 10, 45, width=45),
            self.token("u1", "5.50", 100, 45, width=38),
            self.token("l1", "11.00", 160, 45, width=45),
            self.token("q1", "2", 230, 45, width=10),
            self.token("d2", "RICE", 10, 65, width=45),
            self.token("u2", "12.90", 100, 65, width=38),
            self.token("l2", "12.90", 160, 65, width=45),
            self.token("q2", "1", 230, 65, width=10),
            self.token("total", "TOTAL 23.90", 120, 95, width=120),
        )

        output = self.output(self.evidence(tokens))

        self.assertEqual(2, len(output.items))
        self.assertTrue(
            all(row.quantity.status is FieldStatus.UNRESOLVED for row in output.items)
        )

    def test_four_field_item_row_with_explicit_multiplier(self) -> None:
        row = self.output().items[0]

        self.assertTrue(all(field.status is FieldStatus.EXTRACTED for field in row.fields))
        self.assertEqual(("MILK", "2", "5.50", "11.00"), tuple(f.value for f in row.fields))

    def test_multiple_amount_interpretations_remain_unresolved(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=180),
            self.token("date", "DATE: 2026-10-13", 10, 20, width=150),
            self.token("description", "MILK", 10, 45, width=45),
            self.token("amount-a", "5.50", 155, 45, width=38),
            self.token("amount-b", "11.00", 220, 45, width=45),
            self.token("total", "TOTAL 11.00", 130, 75, width=135),
        )

        row = self.output(self.evidence(tokens)).items[0]

        self.assertEqual(FieldStatus.MISSING, row.quantity.status)
        self.assertEqual(FieldStatus.UNRESOLVED, row.unit_price.status)
        self.assertEqual(FieldStatus.UNRESOLVED, row.line_total.status)
        self.assertEqual(("amount-a", "amount-b"), row.unit_price.source_token_ids)
        self.assertEqual(("amount-a", "amount-b"), row.line_total.source_token_ids)

    def test_competing_receipt_totals_are_unresolved_with_all_evidence(self) -> None:
        base = tuple(
            token
            for token in self.simple_tokens()
            if token.token_id not in {"total-label", "total-value"}
        )
        tokens = base + (
            self.token("total1-label", "TOTAL", 130, 95, width=55),
            self.token("total1-value", "23.90", 220, 95, width=45),
            self.token("total2-label", "GRAND TOTAL", 100, 115, width=85),
            self.token("total2-value", "23.90", 220, 115, width=45),
        )

        field = self.output(self.evidence(tokens)).receipt_total

        self.assertEqual(FieldStatus.UNRESOLVED, field.status)
        self.assertEqual(
            {"total1-label", "total1-value", "total2-label", "total2-value"},
            set(field.source_token_ids),
        )

    def test_competing_dates_are_unresolved_with_all_evidence(self) -> None:
        base = tuple(
            token
            for token in self.simple_tokens()
            if token.token_id not in {"date-label", "date-value"}
        )
        tokens = base + (
            self.token("date1-label", "DATE:", 10, 15, width=45),
            self.token("date1-value", "2026-10-13", 70, 15, width=90),
            self.token("date2-label", "PURCHASE DATE:", 10, 30, width=105),
            self.token("date2-value", "2026-10-14", 130, 30, width=90),
        )

        field = self.output(self.evidence(tokens)).purchase_date

        self.assertEqual(FieldStatus.UNRESOLVED, field.status)
        self.assertEqual(
            {"date1-label", "date1-value", "date2-label", "date2-value"},
            set(field.source_token_ids),
        )

    def test_unanchored_date_is_not_reused_as_store_name(self) -> None:
        tokens = (
            self.token("date", "13 OCT 2026", 10, 0, width=120),
            self.token("item", "MILK 11.00", 10, 35, width=180),
            self.token("total", "TOTAL 11.00", 80, 65, width=110),
        )

        output = self.output(self.evidence(tokens))

        self.assertEqual(FieldStatus.MISSING, output.store_name.status)
        self.assertEqual("13 OCT 2026", output.purchase_date.value)

    def test_financial_summary_and_control_lines_are_not_items(self) -> None:
        labels = (
            "SUBTOTAL 11.00",
            "TAX 0.66",
            "CHANGE 3.00",
            "CASH 15.00",
            "TENDERED 15.00",
            "BALANCE 0.00",
            "DISCOUNT 2.00",
            "ROUNDING 0.05",
            "VOUCHER 5.00",
            "SERVICE CHARGE 0.60",
            "SERVICE TAX 0.66",
            "GST 0.66",
            "SST 0.66",
            "PAYMENT TOTAL 11.00",
            "AMOUNT PAID 11.00",
        )
        tokens = [
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=180),
            self.token("date", "DATE: 2026-10-13", 10, 20, width=150),
            self.token("item", "MILK 2 x 5.50 11.00", 10, 45, width=255),
        ]
        for index, label in enumerate(labels):
            tokens.append(
                self.token(
                    f"summary-{index}", label, 10, 65 + index * 15, width=190
                )
            )
        tokens.append(
            self.token("total", "TOTAL 11.00", 130, 305, width=135)
        )

        output = self.output(self.evidence(tuple(tokens)))

        self.assertEqual(1, len(output.items))
        self.assertEqual("MILK", output.items[0].description.value)

    def test_summary_words_inside_product_descriptions_are_not_filtered(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=180),
            self.token("date", "DATE: 2026-10-13", 10, 20, width=150),
            self.token("discount-product", "DISCOUNT BISCUITS 2.00", 10, 45, width=220),
            self.token("voucher-product", "VOUCHER HOLDER 5.00", 10, 65, width=210),
            self.token("rounding-product", "ROUNDING TOOL 0.05", 10, 85, width=190),
            self.token("total", "TOTAL 7.05", 130, 115, width=135),
        )

        output = self.output(self.evidence(tokens))

        self.assertEqual(
            ("DISCOUNT BISCUITS", "VOUCHER HOLDER", "ROUNDING TOOL"),
            tuple(row.description.value for row in output.items),
        )

    def test_overlapping_ocr_tokens_do_not_create_a_silent_item_order(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=180),
            self.token("date", "DATE: 2026-10-13", 10, 20, width=150),
            self.token("overlap-description", "MILK", 10, 45, width=80),
            self.token("overlap-values", "2 x 5.50 11.00", 60, 45, width=150),
            self.token("total", "TOTAL 11.00", 130, 75, width=135),
        )

        output = self.output(self.evidence(tokens))

        self.assertEqual((), output.items)

    def test_ambiguous_adjacent_rows_do_not_use_token_id_as_semantic_tie_break(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=180),
            self.token("date", "DATE: 2026-10-13", 10, 20, width=150),
            self.token("row1-description", "MILK", 10, 45, width=45),
            self.token("row1-total", "11.00", 220, 45, width=45),
            self.token("shared-number", "5.50", 155, 50, width=38),
            self.token("row2-description", "RICE", 10, 55, width=45),
            self.token("row2-total", "12.90", 220, 55, width=45),
            self.token("total", "TOTAL 23.90", 130, 85, width=135),
        )

        output = self.output(self.evidence(tokens))

        self.assertEqual((), output.items)

    def test_undetected_item_line_is_not_fabricated(self) -> None:
        tokens = tuple(
            token
            for token in self.simple_tokens()
            if not token.token_id.startswith("item2-")
        )

        output = self.output(self.evidence(tokens))

        self.assertEqual(1, len(output.items))
        self.assertEqual("MILK", output.items[0].description.value)

    def test_receipt_total_is_not_derived_from_detected_items(self) -> None:
        tokens = tuple(
            token
            for token in self.simple_tokens()
            if token.token_id not in {"total-label", "total-value"}
        )

        output = self.output(self.evidence(tokens))

        self.assertEqual(2, len(output.items))
        self.assertEqual(FieldStatus.MISSING, output.receipt_total.status)
        self.assertIsNone(output.receipt_total.value)

    def test_all_extracted_fields_reference_actual_source_tokens(self) -> None:
        output = self.output()

        self.assertEqual(("store",), output.store_name.source_token_ids)
        self.assertEqual(("date-value",), output.purchase_date.source_token_ids)
        self.assertEqual(("total-value",), output.receipt_total.source_token_ids)
        self.assertEqual(
            {
                "item1-description",
                "item1-quantity",
                "item1-unit",
                "item1-total",
            },
            {token_id for field in output.items[0].fields for token_id in field.source_token_ids},
        )
        source_ids = output.source_evidence.token_ids
        self.assertTrue(
            all(
                token_id in source_ids
                for row in output.items
                for field in row.fields
                for token_id in field.source_token_ids
            )
        )

    def test_source_text_geometry_confidence_and_identity_are_preserved(self) -> None:
        tokens = list(self.simple_tokens())
        tokens[0] = self.token(
            "store",
            "  PANTRYPROOF TEST MART  ",
            20,
            0,
            width=195,
            confidence=0.713,
        )
        evidence = self.evidence(tuple(tokens))
        original_polygon = evidence.tokens[0].polygon

        output = self.output(evidence)

        self.assertIs(evidence, output.source_evidence)
        self.assertIs(evidence.tokens[0], output.source_evidence.tokens[0])
        self.assertEqual("  PANTRYPROOF TEST MART  ", evidence.tokens[0].original_text)
        self.assertEqual(original_polygon, evidence.tokens[0].polygon)
        self.assertEqual(0.713, evidence.tokens[0].raw_confidence)
        self.assertEqual("PANTRYPROOF TEST MART", output.store_name.value)
        self.assertTrue(
            all(
                field.confidence is None
                for field in (
                    output.store_name,
                    output.purchase_date,
                    output.receipt_total,
                    *(field for row in output.items for field in row.fields),
                )
            )
        )

    def test_insufficient_gate_returns_fallback_without_structured_output(self) -> None:
        evidence = self.evidence(
            gate_result=self.gate(SourceEvidenceDecision.INSUFFICIENT)
        )

        result = extract_b2(evidence)

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
        self.assertEqual(("source_evidence",), tuple(inspect.signature(extract_b2).parameters))

    def test_unique_description_continuation_is_attached_with_provenance(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=180),
            self.token("date", "DATE: 2026-10-13", 10, 20, width=150),
            self.token("continuation", "ORGANIC WHOLE", 10, 45, width=110),
            self.token("item", "MILK 2 x 5.50 11.00", 10, 62, width=255),
            self.token("total", "TOTAL 11.00", 130, 95, width=135),
        )

        row = self.output(self.evidence(tokens)).items[0]

        self.assertEqual("ORGANIC WHOLE MILK", row.description.value)
        self.assertEqual(("continuation", "item"), row.description.source_token_ids)

    def test_equidistant_description_continuation_is_not_attached(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=180),
            self.token("date", "DATE: 2026-10-13", 10, 20, width=150),
            self.token("row1", "MILK 5.00", 10, 45, width=255),
            self.token("ambiguous-continuation", "ORGANIC", 10, 60, width=80),
            self.token("row2", "RICE 6.00", 10, 75, width=255),
            self.token("total", "TOTAL 11.00", 130, 105, width=135),
        )

        output = self.output(self.evidence(tokens))

        self.assertTrue(
            all(
                row.description.status is FieldStatus.UNRESOLVED
                for row in output.items
            )
        )
        self.assertTrue(
            all(
                "ambiguous-continuation" in row.description.source_token_ids
                for row in output.items
            )
        )

    def test_repeated_extraction_has_identical_rows_fields_and_ids(self) -> None:
        evidence = self.evidence()

        first = extract_b2(evidence)
        second = extract_b2(evidence)

        self.assertEqual(first, second)
        self.assertEqual(
            (f"{self.RECEIPT_ID}:b2:row:000000", f"{self.RECEIPT_ID}:b2:row:000001"),
            tuple(row.row_id for row in first.receipt_output.items),
        )

    def test_public_boundary_has_no_correction_price_or_persistence_dependency(self) -> None:
        parameters = tuple(inspect.signature(extract_b2).parameters)
        result = extract_b2(self.evidence())
        imported_modules: set[str] = set()
        for node in ast.walk(ast.parse(inspect.getsource(layout_b2))):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.add(node.module)

        self.assertEqual(("source_evidence",), parameters)
        self.assertNotIn("pipeline.baseline_b1", imported_modules)
        self.assertTrue(
            imported_modules.isdisjoint(
                {
                    "numpy",
                    "paddleocr",
                    "requests",
                    "sqlite3",
                    "tensorflow",
                    "torch",
                }
            )
        )
        self.assertFalse(hasattr(result, "persistence_outcome"))
        self.assertIsNone(result.pre_resolution_disposition)
        self.assertTrue(
            all(row.pantry_product_identity is None for row in result.receipt_output.items)
        )


if __name__ == "__main__":
    unittest.main()
