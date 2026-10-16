"""Synthetic conformance tests for the B3 generic-rule baseline."""

from __future__ import annotations

import ast
import inspect
import unittest
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, ROUND_HALF_UP, localcontext

import pipeline.baseline_b3 as baseline_b3
from pipeline.baseline_b3 import (
    AdjustmentDirection,
    AdjustmentKind,
    ArithmeticOutcome,
    ArithmeticPhase,
    ArithmeticScope,
    B3ParseState,
    B3RuleOutcome,
    CURRENCY_QUANTUM,
    CURRENCY_TOLERANCE,
    DiagnosticCode,
    EXTRACTOR_VERSION,
    PUNCTUATION_MAP,
    REQUIRED_B2_EXTRACTOR_VERSION,
    ROUNDING_MODE,
    RULESET_ID,
    SourceSlice,
    WEIGHT_UNITS,
    apply_b3,
    normalize_receipt_text,
    parse_generic_date,
    parse_money,
    parse_positive_quantity,
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
from pipeline.layout_b2 import (
    B2ExtractionResult,
    EXTRACTOR_VERSION as B2_EXTRACTOR_VERSION,
    extract_b2,
)


class BaselineB3Tests(unittest.TestCase):
    RECEIPT_ID = "synthetic-b3-receipt"

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
            gate_result_id="synthetic-b3-gate",
            receipt_id=self.RECEIPT_ID,
            decision=decision,
            reasons=("Synthetic source evidence is insufficient.",)
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
            image_id="synthetic-b3-image",
            provenance=SourceProvenance(
                source_system="synthetic-unit-test",
                source_reference="memory://synthetic-b3-image",
            ),
            processing_status=SourceProcessingStatus.OCR_COMPLETED,
            tokens=tokens if tokens is not None else self.simple_tokens(),
            gate_result=gate_result or self.gate(),
        )

    def simple_tokens(
        self,
        *,
        store: str = "PANTRYPROOF TEST MART",
        date_value: str = "2026-10-13",
        description: str = "MILK",
        quantity: str = "2",
        unit_price: str = "5.50",
        line_total: str = "11.00",
        receipt_total: str = "11.00",
        extra_tokens: tuple[OcrSourceToken, ...] = (),
    ) -> tuple[OcrSourceToken, ...]:
        return (
            self.token("store", store, 20, 0, width=190),
            self.token("date-label", "DATE:", 10, 20, width=45),
            self.token("date-value", date_value, 70, 20, width=105),
            self.token("description", description, 10, 45, width=90),
            self.token("quantity", quantity, 110, 45, width=35),
            self.token("multiplier", "x", 150, 45, width=8),
            self.token("unit-price", unit_price, 170, 45, width=70),
            self.token("line-total", line_total, 255, 45, width=70),
            *extra_tokens,
            self.token("total-label", "TOTAL", 170, 100, width=65),
            self.token("total-value", receipt_total, 255, 100, width=70),
        )

    def b2_result(
        self, tokens: tuple[OcrSourceToken, ...] | None = None
    ) -> B2ExtractionResult:
        return extract_b2(self.evidence(tokens))

    def b3_result(self, tokens: tuple[OcrSourceToken, ...] | None = None):
        b2_result = self.b2_result(tokens)
        self.assertIsNotNone(b2_result.receipt_output)
        return b2_result, apply_b3(b2_result)

    @staticmethod
    def with_extra_source_tokens(
        b2_result: B2ExtractionResult,
        *tokens: OcrSourceToken,
    ) -> B2ExtractionResult:
        output = b2_result.receipt_output
        evidence = replace(
            output.source_evidence,
            tokens=(*output.source_evidence.tokens, *tokens),
        )
        return B2ExtractionResult(replace(output, source_evidence=evidence), None)

    @staticmethod
    def fields(output):
        values = [output.store_name, output.purchase_date]
        values.extend(field for item in output.items for field in item.fields)
        values.append(output.receipt_total)
        return tuple(values)

    @staticmethod
    def arithmetic(result, scope: ArithmeticScope, phase: ArithmeticPhase):
        return tuple(
            diagnostic
            for diagnostic in result.arithmetic_diagnostics
            if diagnostic.scope is scope and diagnostic.phase is phase
        )

    def test_public_identifiers_and_decimal_constants_are_frozen(self) -> None:
        self.assertEqual("B3-generic-rules-v0", EXTRACTOR_VERSION)
        self.assertEqual(EXTRACTOR_VERSION, RULESET_ID)
        self.assertEqual("B2-layout-graph-v0", REQUIRED_B2_EXTRACTOR_VERSION)
        self.assertEqual(B2_EXTRACTOR_VERSION, REQUIRED_B2_EXTRACTOR_VERSION)
        self.assertEqual(Decimal("0.01"), CURRENCY_QUANTUM)
        self.assertEqual(Decimal("0.01"), CURRENCY_TOLERANCE)
        self.assertEqual(ROUND_HALF_UP, ROUNDING_MODE)
        self.assertEqual(("kg", "g", "lb", "lbs", "oz"), WEIGHT_UNITS)
        self.assertTrue(PUNCTUATION_MAP)

    def test_text_normalization_is_nfkc_casefolded_and_conservative(self) -> None:
        observed = "  ＭＩＬＫ\u00a0—\t“PREMIUM”…  "

        self.assertEqual('milk - "premium"...', normalize_receipt_text(observed))
        self.assertEqual("m&m 7-up o'brien", normalize_receipt_text("M&M 7-UP O'Brien"))

    def test_date_parser_accepts_supported_complete_formats(self) -> None:
        cases = {
            "2026-1-3": "2026-01-03",
            "2026-10-13": "2026-10-13",
            "13/10/2026": "2026-10-13",
            "10/13/2026": "2026-10-13",
            "11/11/2026": "2026-11-11",
            "13 OCT 2026": "2026-10-13",
            "October 13, 2026": "2026-10-13",
        }
        for observed, expected in cases.items():
            with self.subTest(observed=observed):
                parsed = parse_generic_date(observed)
                self.assertEqual(B3ParseState.VALID, parsed.state)
                self.assertEqual(expected, parsed.normalized_value)

    def test_date_parser_distinguishes_ambiguity_invalidity_and_mixed_separators(self) -> None:
        ambiguous = parse_generic_date("10/11/2026")
        self.assertEqual(B3ParseState.AMBIGUOUS, ambiguous.state)
        self.assertEqual(
            {"2026-10-11", "2026-11-10"}, set(ambiguous.interpretations)
        )
        for observed in (
            "00/00/2026",
            "31/02/2026",
            "13-10/2026",
            "2026/10/13",
            "today",
        ):
            with self.subTest(observed=observed):
                self.assertEqual(
                    B3ParseState.INVALID, parse_generic_date(observed).state
                )

    def test_positive_quantity_parser_uses_decimal_and_rejects_guessing(self) -> None:
        cases = {
            "2": ("2", Decimal("2")),
            "02.500": ("2.5", Decimal("2.500")),
            "1,234.500": ("1234.5", Decimal("1234.500")),
        }
        for observed, (normalized, decimal_value) in cases.items():
            with self.subTest(observed=observed):
                parsed = parse_positive_quantity(observed)
                self.assertEqual(B3ParseState.VALID, parsed.state)
                self.assertEqual(normalized, parsed.normalized_value)
                self.assertEqual(decimal_value, parsed.decimal_value)
        for observed in ("0", "-1", "+1", "1e3", "1,5", "1 1/2", "kg"):
            with self.subTest(observed=observed):
                self.assertEqual(
                    B3ParseState.INVALID, parse_positive_quantity(observed).state
                )

    def test_money_parser_supports_declared_formats_and_one_fraction_digit(self) -> None:
        cases = {
            "5.50": ("5.50", Decimal("5.50"), None),
            "RM 1,234.5": ("1234.50", Decimal("1234.5"), "RM"),
            "MYR12.9": ("12.90", Decimal("12.9"), "MYR"),
            "$ 0.1": ("0.10", Decimal("0.1"), "$"),
        }
        for observed, expected in cases.items():
            with self.subTest(observed=observed):
                parsed = parse_money(observed)
                self.assertEqual(B3ParseState.VALID, parsed.state)
                self.assertEqual(expected[0], parsed.normalized_value)
                self.assertEqual(expected[1], parsed.decimal_value)
                self.assertEqual(expected[2], parsed.currency_marker)

    def test_money_parser_rejects_ambiguous_or_unsupported_formats(self) -> None:
        for observed in (
            "1",
            "1.",
            "1.234",
            "1,23.45",
            "1.234,50",
            "1,234,50",
            "-1.00",
            "(1.00)",
            "EUR 1.00",
            "NaN",
            "Infinity",
        ):
            with self.subTest(observed=observed):
                self.assertEqual(B3ParseState.INVALID, parse_money(observed).state)

    def test_decimal_work_is_exact_and_independent_of_ambient_precision(self) -> None:
        huge = "12345678901234567890123456789.00"
        with localcontext() as context:
            context.prec = 3
            parsed = parse_money(huge)
            outcome, difference = baseline_b3._classify_arithmetic(
                Decimal("12345678901234567890123456789.005"),
                Decimal("12345678901234567890123456789.01"),
            )

        self.assertEqual(B3ParseState.VALID, parsed.state)
        self.assertEqual(huge, parsed.normalized_value)
        self.assertEqual(ArithmeticOutcome.MATCH_AFTER_CURRENCY_ROUNDING, outcome)
        self.assertEqual(Decimal("0"), difference)

    def test_b3_retains_exact_b2_result_and_builds_distinct_automatic_output(self) -> None:
        b2_result, result = self.b3_result()
        original = b2_result.receipt_output
        transformed = result.receipt_output

        self.assertIs(b2_result, result.original_b2_result)
        self.assertIs(b2_result, result.b2_result)
        self.assertIsNot(original, transformed)
        self.assertIs(transformed, result.transformed_output)
        self.assertIs(original.source_evidence, transformed.source_evidence)
        self.assertEqual(EXTRACTOR_VERSION, transformed.extractor_version)
        self.assertEqual(RULESET_ID, result.ruleset_id)
        self.assertEqual(OutputStage.PRE_REVIEW_AUTOMATIC, transformed.output_stage)
        self.assertIsNone(result.pre_resolution_disposition)
        self.assertEqual(original.extraction_status, transformed.extraction_status)

    def test_field_row_status_reference_and_identity_boundaries_are_preserved(self) -> None:
        b2_result, result = self.b3_result()
        original = b2_result.receipt_output
        transformed = result.receipt_output
        original_fields = self.fields(original)
        transformed_fields = self.fields(transformed)

        self.assertEqual(
            tuple(field.field_id for field in original_fields),
            tuple(field.field_id for field in transformed_fields),
        )
        self.assertEqual(
            tuple(field.status for field in original_fields),
            tuple(field.status for field in transformed_fields),
        )
        self.assertEqual(
            tuple(field.source_token_ids for field in original_fields),
            tuple(field.source_token_ids for field in transformed_fields),
        )
        self.assertEqual(
            tuple(field.confidence for field in original_fields),
            tuple(field.confidence for field in transformed_fields),
        )
        self.assertEqual(
            tuple(row.row_id for row in original.items),
            tuple(row.row_id for row in transformed.items),
        )
        self.assertEqual(
            tuple(row.pantry_product_identity for row in original.items),
            tuple(row.pantry_product_identity for row in transformed.items),
        )
        self.assertEqual(len(original_fields), len(result.field_transformations))
        for original_field, transformed_field, relationship in zip(
            original_fields, transformed_fields, result.field_transformations
        ):
            self.assertIs(original_field, relationship.original_field)
            self.assertIs(transformed_field, relationship.transformed_field)

    def test_text_date_quantity_and_money_normalize_without_mutating_b2(self) -> None:
        tokens = self.simple_tokens(
            store="  ＰＡＮＴＲＹＰＲＯＯＦ\u00a0ＭＡＲＴ  ",
            date_value="13/10/2026",
            description="MILK—PREMIUM",
            quantity="02.500",
            unit_price="RM 4.00",
            line_total="MYR 10.00",
            receipt_total="$ 10.00",
        )
        b2_result, result = self.b3_result(tokens)
        original = b2_result.receipt_output
        transformed = result.receipt_output

        self.assertEqual(
            "ＰＡＮＴＲＹＰＲＯＯＦ\u00a0ＭＡＲＴ",
            original.store_name.value.strip(),
        )
        self.assertEqual("MILK—PREMIUM", original.items[0].description.value)
        self.assertEqual("13/10/2026", original.purchase_date.value)
        self.assertEqual("02.500", original.items[0].quantity.value)
        self.assertEqual("RM 4.00", original.items[0].unit_price.value)
        self.assertEqual("pantryproof mart", transformed.store_name.value)
        self.assertEqual("milk-premium", transformed.items[0].description.value)
        self.assertEqual("2026-10-13", transformed.purchase_date.value)
        self.assertEqual("2.5", transformed.items[0].quantity.value)
        self.assertEqual("4.00", transformed.items[0].unit_price.value)
        self.assertEqual("10.00", transformed.items[0].line_total.value)
        self.assertEqual("10.00", transformed.receipt_total.value)
        self.assertTrue(
            any(
                event.outcome is B3RuleOutcome.REPRESENTATION_CHANGED
                for event in result.rule_events
            )
        )

    def test_public_output_retains_invalid_or_ambiguous_parses_with_diagnostics(self) -> None:
        for observed, expected_code in (
            ("10/11/2026", DiagnosticCode.AMBIGUOUS_DATE),
            ("31/02/2026", DiagnosticCode.INVALID_DATE),
        ):
            with self.subTest(observed=observed):
                b2_result = self.b2_result()
                output = b2_result.receipt_output
                synthetic_b2 = B2ExtractionResult(
                    replace(
                        output,
                        purchase_date=replace(output.purchase_date, value=observed),
                    ),
                    None,
                )
                result = apply_b3(synthetic_b2)
                self.assertEqual(observed, result.receipt_output.purchase_date.value)
                self.assertIn(
                    expected_code,
                    {diagnostic.code for diagnostic in result.diagnostics},
                )

        b2_result = self.b2_result()
        output = b2_result.receipt_output
        row = output.items[0]
        synthetic_b2 = B2ExtractionResult(
            replace(
                output,
                items=(
                    replace(
                        row,
                        unit_price=replace(row.unit_price, value="EUR 5.50"),
                    ),
                ),
            ),
            None,
        )
        result = apply_b3(synthetic_b2)
        self.assertEqual("EUR 5.50", result.receipt_output.items[0].unit_price.value)
        self.assertIn(
            DiagnosticCode.INVALID_MONEY,
            {diagnostic.code for diagnostic in result.diagnostics},
        )
        for phase in ArithmeticPhase:
            self.assertEqual(
                ArithmeticOutcome.INCOMPLETE_OPERANDS,
                self.arithmetic(result, ArithmeticScope.ITEM, phase)[0].outcome,
            )

    def test_b3_local_audit_records_are_immutable(self) -> None:
        _, result = self.b3_result()

        with self.assertRaises(FrozenInstanceError):
            result.rule_events[0].message = "changed"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            result.field_transformations[0].field_id = "changed"  # type: ignore[misc]

    def test_original_ocr_objects_text_geometry_and_confidence_are_immutable(self) -> None:
        tokens = self.simple_tokens(store="  PANTRYPROOF TEST MART  ")
        evidence = self.evidence(tokens)
        original_token = evidence.tokens[0]
        original_polygon = original_token.polygon
        b2_result = extract_b2(evidence)

        result = apply_b3(b2_result)

        self.assertIs(evidence, result.receipt_output.source_evidence)
        self.assertIs(original_token, result.receipt_output.source_evidence.tokens[0])
        self.assertEqual("  PANTRYPROOF TEST MART  ", original_token.original_text)
        self.assertEqual(original_polygon, original_token.polygon)
        self.assertEqual(0.9, original_token.raw_confidence)
        with self.assertRaises(FrozenInstanceError):
            original_token.original_text = "changed"  # type: ignore[misc]

    def test_events_and_diagnostics_are_deterministic_and_contiguously_ordered(self) -> None:
        tax = self.token("tax", "TAX 0.60", 10, 70, width=120)
        b2_result = self.with_extra_source_tokens(
            self.b2_result(self.simple_tokens(quantity="0")), tax
        )

        first = apply_b3(b2_result)
        second = apply_b3(b2_result)

        self.assertEqual(first, second)
        self.assertEqual(
            tuple(range(len(first.rule_events))),
            tuple(event.sequence for event in first.rule_events),
        )
        self.assertEqual(
            tuple(
                f"{self.RECEIPT_ID}:b3:event:{index:06d}"
                for index in range(len(first.rule_events))
            ),
            tuple(event.event_id for event in first.rule_events),
        )
        self.assertEqual(
            (
                "B3-TEXT-NORMALIZE",
                "B3-TEXT-NORMALIZE",
                "B3-DATE-PARSE",
                "B3-QUANTITY-PARSE",
                "B3-MONEY-PARSE",
                "B3-MONEY-PARSE",
                "B3-MONEY-PARSE",
                "B3-ADJUSTMENT-SCAN",
                "B3-ARITHMETIC-ITEM",
                "B3-ARITHMETIC-RECEIPT",
                "B3-ARITHMETIC-ITEM",
                "B3-ARITHMETIC-RECEIPT",
            ),
            tuple(event.rule_id for event in first.rule_events),
        )
        self.assertEqual(
            tuple(
                f"{self.RECEIPT_ID}:b3:diagnostic:{index:06d}"
                for index in range(len(first.diagnostics))
            ),
            tuple(item.diagnostic_id for item in first.diagnostics),
        )
        self.assertEqual(
            (
                DiagnosticCode.INVALID_QUANTITY,
                DiagnosticCode.ADJUSTMENT_OBSERVED,
                DiagnosticCode.ADJUSTMENT_SCOPE_OR_DIRECTION_UNKNOWN,
            ),
            tuple(item.code for item in first.diagnostics),
        )
        self.assertEqual(
            (
                (ArithmeticPhase.PRE_CORRECTION, ArithmeticScope.ITEM, 0),
                (
                    ArithmeticPhase.PRE_CORRECTION,
                    ArithmeticScope.OBSERVED_RECEIPT_ROWS,
                    1,
                ),
                (ArithmeticPhase.FINAL, ArithmeticScope.ITEM, 0),
                (
                    ArithmeticPhase.FINAL,
                    ArithmeticScope.OBSERVED_RECEIPT_ROWS,
                    1,
                ),
            ),
            tuple(
                (
                    item.phase,
                    item.scope,
                    int(item.diagnostic_id.rsplit(":", 1)[1]),
                )
                for item in first.arithmetic_diagnostics
            ),
        )

    def test_two_real_b2_rows_keep_order_and_feed_observed_receipt_sum(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=190),
            self.token("date-label", "DATE:", 10, 20, width=45),
            self.token("date-value", "2026-10-13", 70, 20, width=105),
            self.token("d1", "MILK", 10, 45, width=70),
            self.token("q1", "2", 100, 45, width=25),
            self.token("x1", "x", 130, 45, width=8),
            self.token("u1", "5.50", 150, 45, width=55),
            self.token("l1", "11.00", 240, 45, width=65),
            self.token("d2", "RICE", 10, 62, width=70),
            self.token("q2", "1", 100, 62, width=25),
            self.token("x2", "x", 130, 62, width=8),
            self.token("u2", "3.00", 150, 62, width=55),
            self.token("l2", "3.00", 240, 62, width=65),
            self.token("total-label", "TOTAL", 150, 100, width=65),
            self.token("total-value", "14.00", 240, 100, width=65),
        )
        b2_result, result = self.b3_result(tokens)
        original = b2_result.receipt_output
        transformed = result.receipt_output

        self.assertEqual(2, len(original.items))
        self.assertEqual(
            tuple(row.row_id for row in original.items),
            tuple(row.row_id for row in transformed.items),
        )
        self.assertEqual(
            tuple(field.field_id for field in self.fields(original)),
            tuple(field.field_id for field in self.fields(transformed)),
        )
        for phase in ArithmeticPhase:
            receipt = self.arithmetic(
                result, ArithmeticScope.OBSERVED_RECEIPT_ROWS, phase
            )[0]
            self.assertEqual(ArithmeticOutcome.RAW_EXACT_MATCH, receipt.outcome)
            self.assertEqual("14", receipt.expected_value)
            self.assertEqual("14", receipt.observed_value)

    def test_insufficient_source_fallback_runs_no_b3_rules(self) -> None:
        evidence = self.evidence(
            gate_result=self.gate(SourceEvidenceDecision.INSUFFICIENT)
        )
        b2_result = extract_b2(evidence)

        result = apply_b3(b2_result)

        self.assertIs(b2_result, result.original_b2_result)
        self.assertIsNone(result.receipt_output)
        self.assertIs(
            b2_result.pre_resolution_disposition,
            result.pre_resolution_disposition,
        )
        self.assertEqual(
            PolicyState.FALLBACK_NO_UPDATE,
            result.pre_resolution_disposition.state,
        )
        self.assertEqual((), result.field_transformations)
        self.assertEqual((), result.rule_events)
        self.assertEqual((), result.candidates)
        self.assertEqual((), result.arithmetic_diagnostics)
        self.assertEqual((), result.adjustments)
        self.assertEqual((), result.diagnostics)

    def test_structurally_failed_b2_output_remains_automatic_not_fallback(self) -> None:
        b2_result = extract_b2(self.evidence(()))
        self.assertEqual(
            ReceiptExtractionStatus.FAILED,
            b2_result.receipt_output.extraction_status,
        )

        result = apply_b3(b2_result)

        self.assertIsNotNone(result.receipt_output)
        self.assertEqual(
            ReceiptExtractionStatus.FAILED,
            result.receipt_output.extraction_status,
        )
        self.assertEqual(OutputStage.PRE_REVIEW_AUTOMATIC, result.receipt_output.output_stage)
        self.assertIsNone(result.pre_resolution_disposition)

    def test_wrong_sufficient_extractor_identifier_is_rejected(self) -> None:
        b2_result = self.b2_result()
        wrong_output = replace(
            b2_result.receipt_output, extractor_version="B2-layout-graph-not-frozen"
        )

        with self.assertRaises(ValueError):
            apply_b3(B2ExtractionResult(wrong_output, None))

    def test_exact_decimal_arithmetic_is_recorded_before_and_after_rules(self) -> None:
        _, result = self.b3_result()

        for phase in ArithmeticPhase:
            item = self.arithmetic(result, ArithmeticScope.ITEM, phase)
            receipt = self.arithmetic(
                result, ArithmeticScope.OBSERVED_RECEIPT_ROWS, phase
            )
            self.assertEqual(1, len(item))
            self.assertEqual(ArithmeticOutcome.RAW_EXACT_MATCH, item[0].outcome)
            self.assertEqual("11", item[0].expected_value)
            self.assertEqual("11", item[0].observed_value)
            self.assertEqual(1, len(receipt))
            self.assertEqual(ArithmeticOutcome.RAW_EXACT_MATCH, receipt[0].outcome)

    def test_currency_rounding_and_inclusive_tolerance_are_distinct(self) -> None:
        rounding_tokens = self.simple_tokens(
            quantity="0.5",
            unit_price="0.01",
            line_total="0.01",
            receipt_total="0.01",
        )
        tolerance_tokens = self.simple_tokens(
            quantity="3",
            unit_price="0.33",
            line_total="1.00",
            receipt_total="1.00",
        )

        _, rounded = self.b3_result(rounding_tokens)
        _, tolerated = self.b3_result(tolerance_tokens)

        for phase in ArithmeticPhase:
            self.assertEqual(
                ArithmeticOutcome.MATCH_AFTER_CURRENCY_ROUNDING,
                self.arithmetic(rounded, ArithmeticScope.ITEM, phase)[0].outcome,
            )
            tolerance = self.arithmetic(
                tolerated, ArithmeticScope.ITEM, phase
            )[0]
            self.assertEqual(
                ArithmeticOutcome.WITHIN_INCLUSIVE_TOLERANCE,
                tolerance.outcome,
            )
            self.assertEqual("0.01", tolerance.absolute_difference)

        outside = baseline_b3._classify_arithmetic(
            Decimal("1.00"), Decimal("1.02")
        )
        self.assertEqual(ArithmeticOutcome.MISMATCH_BEYOND_TOLERANCE, outside[0])
        self.assertEqual(Decimal("0.02"), outside[1])

    def test_mismatch_beyond_tolerance_does_not_overwrite_observed_value(self) -> None:
        tokens = self.simple_tokens(
            quantity="2",
            unit_price="5.50",
            line_total="12.00",
            receipt_total="12.00",
        )
        b2_result, result = self.b3_result(tokens)

        for phase in ArithmeticPhase:
            self.assertEqual(
                ArithmeticOutcome.MISMATCH_BEYOND_TOLERANCE,
                self.arithmetic(result, ArithmeticScope.ITEM, phase)[0].outcome,
            )
        self.assertEqual("12.00", result.receipt_output.items[0].line_total.value)
        self.assertEqual(
            b2_result.receipt_output.items[0].line_total.source_token_ids,
            result.receipt_output.items[0].line_total.source_token_ids,
        )
        self.assertIn(
            DiagnosticCode.CORRECTION_NO_DIRECT_SUPPORT,
            {diagnostic.code for diagnostic in result.diagnostics},
        )
        self.assertNotIn(
            B3RuleOutcome.CANDIDATE_APPLIED,
            {event.outcome for event in result.rule_events},
        )

    def test_contract_adversarial_unique_candidate_keeps_exact_offsets(self) -> None:
        b2_result = self.b2_result()
        original_output = b2_result.receipt_output
        original_row = original_output.items[0]
        synthetic_wrong_line = replace(original_row.line_total, value="12.00")
        synthetic_wrong_row = replace(original_row, line_total=synthetic_wrong_line)
        synthetic_b2 = B2ExtractionResult(
            replace(original_output, items=(synthetic_wrong_row,)), None
        )

        result = apply_b3(synthetic_b2)

        self.assertEqual("12.00", synthetic_b2.receipt_output.items[0].line_total.value)
        self.assertEqual("11.00", result.receipt_output.items[0].line_total.value)
        self.assertIn(
            DiagnosticCode.CORRECTION_APPLIED,
            {diagnostic.code for diagnostic in result.diagnostics},
        )
        applied = tuple(
            event
            for event in result.rule_events
            if event.outcome is B3RuleOutcome.CANDIDATE_APPLIED
        )
        self.assertEqual(1, len(applied))
        self.assertEqual(("11.00",), applied[0].candidate_values)
        self.assertEqual(1, len(applied[0].source_slices))
        self.assertEqual(1, len(result.candidates))
        self.assertEqual(
            result.receipt_output.items[0].line_total.field_id,
            result.candidates[0].target_field_id,
        )
        self.assertEqual("11.00", result.candidates[0].value)
        source_slice = applied[0].source_slices[0]
        source_token = next(
            token
            for token in synthetic_b2.receipt_output.source_evidence.tokens
            if token.token_id == source_slice.token_id
        )
        self.assertEqual("line-total", source_slice.token_id)
        self.assertEqual("11.00", source_slice.text)
        self.assertEqual(
            source_slice.text,
            source_token.original_text[source_slice.start : source_slice.end],
        )
        self.assertEqual(
            ArithmeticOutcome.MISMATCH_BEYOND_TOLERANCE,
            self.arithmetic(
                result, ArithmeticScope.ITEM, ArithmeticPhase.PRE_CORRECTION
            )[0].outcome,
        )
        self.assertEqual(
            ArithmeticOutcome.RAW_EXACT_MATCH,
            self.arithmetic(
                result, ArithmeticScope.ITEM, ArithmeticPhase.FINAL
            )[0].outcome,
        )

    def test_tolerance_does_not_authorize_candidate_application(self) -> None:
        tokens = self.simple_tokens(
            quantity="2",
            unit_price="5.50",
            line_total="11.01",
            receipt_total="12.00",
        )
        b2_result = self.b2_result(tokens)
        original_output = b2_result.receipt_output
        original_row = original_output.items[0]
        synthetic_row = replace(
            original_row,
            line_total=replace(original_row.line_total, value="12.00"),
        )
        synthetic_b2 = B2ExtractionResult(
            replace(original_output, items=(synthetic_row,)), None
        )

        result = apply_b3(synthetic_b2)

        self.assertEqual("12.00", result.receipt_output.items[0].line_total.value)
        self.assertEqual(("11.01",), tuple(item.value for item in result.candidates))
        self.assertIn(
            DiagnosticCode.CORRECTION_NOT_CORROBORATED,
            {diagnostic.code for diagnostic in result.diagnostics},
        )
        self.assertNotIn(
            B3RuleOutcome.CANDIDATE_APPLIED,
            {event.outcome for event in result.rule_events},
        )

    def test_contract_adversarial_competing_candidates_are_not_tiebroken(self) -> None:
        tokens = self.simple_tokens(
            quantity="2",
            unit_price="5.00",
            line_total="12.00",
            receipt_total="10.00",
        )
        b2_result = self.b2_result(tokens)
        original_output = b2_result.receipt_output
        original_row = original_output.items[0]
        synthetic_row = replace(
            original_row,
            unit_price=replace(original_row.unit_price, value="6.00"),
            line_total=replace(original_row.line_total, value="10.00"),
        )
        synthetic_b2 = B2ExtractionResult(
            replace(original_output, items=(synthetic_row,)), None
        )

        first = apply_b3(synthetic_b2)
        second = apply_b3(synthetic_b2)

        self.assertEqual(first, second)
        self.assertEqual("6.00", first.receipt_output.items[0].unit_price.value)
        self.assertEqual("10.00", first.receipt_output.items[0].line_total.value)
        self.assertIn(
            DiagnosticCode.CORRECTION_COMPETING_CANDIDATES,
            {diagnostic.code for diagnostic in first.diagnostics},
        )
        proposed = tuple(
            event
            for event in first.rule_events
            if event.outcome is B3RuleOutcome.CANDIDATE_PROPOSED
        )
        self.assertEqual(1, len(proposed))
        self.assertEqual(("5.00", "12.00"), proposed[0].candidate_values)
        self.assertEqual(
            ("5.00", "12.00"), tuple(candidate.value for candidate in first.candidates)
        )
        self.assertNotIn(
            B3RuleOutcome.CANDIDATE_APPLIED,
            {event.outcome for event in first.rule_events},
        )

    def test_contract_adversarial_receipt_candidate_uses_observed_row_check(self) -> None:
        b2_result = self.b2_result()
        original_output = b2_result.receipt_output
        synthetic_b2 = B2ExtractionResult(
            replace(
                original_output,
                receipt_total=replace(original_output.receipt_total, value="12.00"),
            ),
            None,
        )

        result = apply_b3(synthetic_b2)

        self.assertEqual("12.00", synthetic_b2.receipt_output.receipt_total.value)
        self.assertEqual("11.00", result.receipt_output.receipt_total.value)
        self.assertEqual(1, len(result.candidates))
        self.assertEqual(
            result.receipt_output.receipt_total.field_id,
            result.candidates[0].target_field_id,
        )
        self.assertEqual(
            ArithmeticOutcome.MISMATCH_BEYOND_TOLERANCE,
            self.arithmetic(
                result,
                ArithmeticScope.OBSERVED_RECEIPT_ROWS,
                ArithmeticPhase.PRE_CORRECTION,
            )[0].outcome,
        )
        self.assertEqual(
            ArithmeticOutcome.RAW_EXACT_MATCH,
            self.arithmetic(
                result,
                ArithmeticScope.OBSERVED_RECEIPT_ROWS,
                ArithmeticPhase.FINAL,
            )[0].outcome,
        )

    def test_shared_multi_value_token_cannot_prove_a_semantic_alternative(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=190),
            self.token("date", "DATE: 2026-10-13", 10, 20, width=165),
            self.token("whole-item", "MILK 2 x 5.50 11.00", 10, 45, width=300),
            self.token("total", "TOTAL 11.00", 170, 80, width=155),
        )
        b2_result = self.b2_result(tokens)
        original_output = b2_result.receipt_output
        original_row = original_output.items[0]
        synthetic_row = replace(
            original_row,
            line_total=replace(original_row.line_total, value="12.00"),
        )
        synthetic_b2 = B2ExtractionResult(
            replace(original_output, items=(synthetic_row,)), None
        )

        result = apply_b3(synthetic_b2)

        self.assertEqual("12.00", result.receipt_output.items[0].line_total.value)
        self.assertIn(
            DiagnosticCode.CORRECTION_SHARED_TOKEN_AMBIGUOUS,
            {diagnostic.code for diagnostic in result.diagnostics},
        )
        self.assertNotIn(
            B3RuleOutcome.CANDIDATE_APPLIED,
            {event.outcome for event in result.rule_events},
        )

    def test_identical_candidates_deduplicate_and_retain_every_source_slice(self) -> None:
        base = self.with_extra_source_tokens(
            self.b2_result(),
            self.token("alternative-a", "11.00", 10, 140, width=55),
            self.token("alternative-b", "11.00", 75, 140, width=55),
        )
        output = base.receipt_output
        row = output.items[0]
        line_total = replace(
            row.line_total,
            value="12.00",
            source_token_ids=("alternative-a", "alternative-b"),
        )
        synthetic_b2 = B2ExtractionResult(
            replace(output, items=(replace(row, line_total=line_total),)), None
        )

        result = apply_b3(synthetic_b2)

        self.assertEqual("11.00", result.receipt_output.items[0].line_total.value)
        self.assertEqual(1, len(result.candidates))
        self.assertEqual(
            ("alternative-a", "alternative-b"),
            result.candidates[0].source_token_ids,
        )
        self.assertEqual(2, len(result.candidates[0].source_slices))

    def test_split_candidate_marker_is_retained_and_unknown_marker_is_vetoed(self) -> None:
        for marker, expected_value in (("RM", "11.00"), ("USD", "12.00")):
            with self.subTest(marker=marker):
                marker_id = f"marker-{marker}"
                base = self.with_extra_source_tokens(
                    self.b2_result(),
                    self.token(marker_id, marker, 10, 140, width=35),
                    self.token("marked-alternative", "11.00", 50, 140, width=55),
                )
                output = base.receipt_output
                row = output.items[0]
                line_total = replace(
                    row.line_total,
                    value="12.00",
                    source_token_ids=(marker_id, "marked-alternative"),
                )
                synthetic_b2 = B2ExtractionResult(
                    replace(output, items=(replace(row, line_total=line_total),)),
                    None,
                )

                result = apply_b3(synthetic_b2)

                self.assertEqual(
                    expected_value, result.receipt_output.items[0].line_total.value
                )
                if marker == "RM":
                    self.assertEqual(1, len(result.candidates))
                    self.assertEqual(
                        (marker_id, "marked-alternative"),
                        result.candidates[0].source_token_ids,
                    )
                else:
                    self.assertEqual((), result.candidates)

    def test_unsupported_or_signed_money_substrings_are_not_candidates(self) -> None:
        for index, literal in enumerate(("EUR 11.00", "(11.00)", "-11.00")):
            with self.subTest(literal=literal):
                token_id = f"unsafe-{index}"
                base = self.with_extra_source_tokens(
                    self.b2_result(),
                    self.token(token_id, literal, 10, 140, width=90),
                )
                output = base.receipt_output
                row = output.items[0]
                line_total = replace(
                    row.line_total,
                    value="12.00",
                    source_token_ids=(token_id,),
                )
                synthetic_b2 = B2ExtractionResult(
                    replace(output, items=(replace(row, line_total=line_total),)),
                    None,
                )

                result = apply_b3(synthetic_b2)

                self.assertEqual(
                    "12.00", result.receipt_output.items[0].line_total.value
                )
                self.assertEqual((), result.candidates)
                self.assertNotIn(
                    B3RuleOutcome.CANDIDATE_APPLIED,
                    {event.outcome for event in result.rule_events},
                )

    def test_receipt_candidate_rejects_token_owned_by_item_monetary_role(self) -> None:
        b2_result = self.b2_result()
        output = b2_result.receipt_output
        shared_token_id = output.items[0].line_total.source_token_ids[0]
        synthetic_b2 = B2ExtractionResult(
            replace(
                output,
                receipt_total=replace(
                    output.receipt_total,
                    value="12.00",
                    source_token_ids=(shared_token_id,),
                ),
            ),
            None,
        )

        result = apply_b3(synthetic_b2)

        self.assertEqual("12.00", result.receipt_output.receipt_total.value)
        self.assertEqual((), result.candidates)
        self.assertIn(
            DiagnosticCode.CORRECTION_SHARED_TOKEN_AMBIGUOUS,
            {diagnostic.code for diagnostic in result.diagnostics},
        )

    def test_invalid_source_slice_provenance_is_rejected_by_result_validation(self) -> None:
        with self.assertRaises(ValueError):
            SourceSlice("token", 1, 1, "x")
        with self.assertRaises(ValueError):
            SourceSlice("token", -1, 1, "x")

        _, result = self.b3_result()
        first_event = result.rule_events[0]
        invalid_event = replace(
            first_event,
            source_slices=(SourceSlice("not-a-source-token", 0, 1, "x"),),
        )
        with self.assertRaises(ValueError):
            replace(result, rule_events=(invalid_event, *result.rule_events[1:]))

        original_slice = first_event.source_slices[0]
        for invalid_slice in (
            replace(original_slice, end=original_slice.end + 10_000),
            replace(original_slice, text="not-the-original-token-text"),
        ):
            with self.subTest(invalid_slice=invalid_slice):
                event = replace(first_event, source_slices=(invalid_slice,))
                with self.assertRaises(ValueError):
                    replace(result, rule_events=(event, *result.rule_events[1:]))

        b2_result = self.b2_result()
        original_output = b2_result.receipt_output
        original_row = original_output.items[0]
        synthetic_b2 = B2ExtractionResult(
            replace(
                original_output,
                items=(
                    replace(
                        original_row,
                        line_total=replace(original_row.line_total, value="12.00"),
                    ),
                ),
            ),
            None,
        )
        corrected = apply_b3(synthetic_b2)
        self.assertEqual(1, len(corrected.candidates))
        invalid_candidate = replace(
            corrected.candidates[0], target_field_id="unknown-field"
        )
        with self.assertRaises(ValueError):
            replace(corrected, candidates=(invalid_candidate,))
        with self.assertRaises(ValueError):
            replace(corrected, candidates=())
        outside_boundary = replace(
            corrected.candidates[0],
            source_slices=(SourceSlice("unit-price", 0, 4, "5.50"),),
        )
        with self.assertRaises(ValueError):
            replace(corrected, candidates=(outside_boundary,))

        tolerated_tokens = self.simple_tokens(
            quantity="2",
            unit_price="5.50",
            line_total="11.01",
            receipt_total="12.00",
        )
        tolerated_b2 = self.b2_result(tolerated_tokens)
        tolerated_output = tolerated_b2.receipt_output
        tolerated_row = tolerated_output.items[0]
        rejected = apply_b3(
            B2ExtractionResult(
                replace(
                    tolerated_output,
                    items=(
                        replace(
                            tolerated_row,
                            line_total=replace(
                                tolerated_row.line_total, value="12.00"
                            ),
                        ),
                    ),
                ),
                None,
            )
        )
        contradictory_candidate = replace(rejected.candidates[0], value="10.00")
        with self.assertRaises(ValueError):
            replace(rejected, candidates=(contradictory_candidate,))

    def test_incomplete_item_and_receipt_operands_remain_in_evaluation(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=190),
            self.token("date", "DATE: 2026-10-13", 10, 20, width=165),
            self.token("item", "MILK 11.00", 10, 45, width=190),
        )
        b2_result, result = self.b3_result(tokens)

        self.assertEqual(ReceiptExtractionStatus.PARTIAL, result.receipt_output.extraction_status)
        self.assertEqual(FieldStatus.MISSING, result.receipt_output.items[0].quantity.status)
        self.assertEqual(FieldStatus.MISSING, result.receipt_output.receipt_total.status)
        for phase in ArithmeticPhase:
            self.assertEqual(
                ArithmeticOutcome.INCOMPLETE_OPERANDS,
                self.arithmetic(result, ArithmeticScope.ITEM, phase)[0].outcome,
            )
            self.assertEqual(
                ArithmeticOutcome.INCOMPLETE_OPERANDS,
                self.arithmetic(
                    result, ArithmeticScope.OBSERVED_RECEIPT_ROWS, phase
                )[0].outcome,
            )
        self.assertIs(b2_result.receipt_output.source_evidence, result.receipt_output.source_evidence)

    def test_conflicting_currency_markers_are_diagnostic_not_conversion(self) -> None:
        tokens = self.simple_tokens(
            unit_price="RM 5.50",
            line_total="$ 11.00",
            receipt_total="MYR 11.00",
        )
        _, result = self.b3_result(tokens)

        for phase in ArithmeticPhase:
            self.assertEqual(
                ArithmeticOutcome.CONFLICTING_CURRENCY_MARKERS,
                self.arithmetic(result, ArithmeticScope.ITEM, phase)[0].outcome,
            )
            self.assertEqual(
                ArithmeticOutcome.CONFLICTING_CURRENCY_MARKERS,
                self.arithmetic(
                    result, ArithmeticScope.OBSERVED_RECEIPT_ROWS, phase
                )[0].outcome,
            )
        self.assertEqual("5.50", result.receipt_output.items[0].unit_price.value)
        self.assertEqual("11.00", result.receipt_output.items[0].line_total.value)

    def test_split_currency_marker_tokens_preserve_conflict_semantics(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=190),
            self.token("date-label", "DATE:", 10, 20, width=45),
            self.token("date-value", "2026-10-13", 70, 20, width=105),
            self.token("description", "MILK", 10, 45, width=90),
            self.token("quantity", "2", 110, 45, width=35),
            self.token("multiplier", "x", 150, 45, width=8),
            self.token("rm", "RM", 165, 45, width=18),
            self.token("unit-price", "5.50", 190, 45, width=45),
            self.token("dollar", "$", 245, 45, width=10),
            self.token("line-total", "11.00", 265, 45, width=55),
            self.token("total-label", "TOTAL", 170, 100, width=65),
            self.token("total-rm", "RM", 240, 100, width=18),
            self.token("total-value", "11.00", 265, 100, width=55),
        )
        b2_result, result = self.b3_result(tokens)

        self.assertEqual(
            ("rm", "unit-price"),
            b2_result.receipt_output.items[0].unit_price.source_token_ids,
        )
        self.assertEqual(
            ("dollar", "line-total"),
            b2_result.receipt_output.items[0].line_total.source_token_ids,
        )
        for phase in ArithmeticPhase:
            self.assertEqual(
                ArithmeticOutcome.CONFLICTING_CURRENCY_MARKERS,
                self.arithmetic(result, ArithmeticScope.ITEM, phase)[0].outcome,
            )
            self.assertEqual(
                ArithmeticOutcome.CONFLICTING_CURRENCY_MARKERS,
                self.arithmetic(
                    result, ArithmeticScope.OBSERVED_RECEIPT_ROWS, phase
                )[0].outcome,
            )

    def test_rm_and_myr_are_one_arithmetic_currency_group(self) -> None:
        tokens = self.simple_tokens(
            unit_price="RM 5.50",
            line_total="MYR 11.00",
            receipt_total="RM 11.00",
        )
        _, result = self.b3_result(tokens)

        for phase in ArithmeticPhase:
            self.assertEqual(
                ArithmeticOutcome.RAW_EXACT_MATCH,
                self.arithmetic(result, ArithmeticScope.ITEM, phase)[0].outcome,
            )
            self.assertEqual(
                ArithmeticOutcome.RAW_EXACT_MATCH,
                self.arithmetic(
                    result, ArithmeticScope.OBSERVED_RECEIPT_ROWS, phase
                )[0].outcome,
            )

    def test_weighted_goods_require_matching_quantity_and_rate_units(self) -> None:
        matched = self.simple_tokens(
            description="BANANA 0.750 kg RM 10.00/kg",
            quantity="0.750",
            unit_price="10.00",
            line_total="7.50",
            receipt_total="7.50",
        )
        incomplete = self.simple_tokens(
            description="BANANA 0.750 kg",
            quantity="0.750",
            unit_price="10.00",
            line_total="7.50",
            receipt_total="7.50",
        )
        conflicting = self.simple_tokens(
            description="BANANA 0.750 kg RM 10.00/lb",
            quantity="0.750",
            unit_price="10.00",
            line_total="7.50",
            receipt_total="7.50",
        )
        quantity_conflict = self.simple_tokens(
            description="BANANA 0.500 kg RM 10.00/kg",
            quantity="0.750",
            unit_price="10.00",
            line_total="7.50",
            receipt_total="7.50",
        )

        _, matched_result = self.b3_result(matched)
        _, incomplete_result = self.b3_result(incomplete)
        _, conflicting_result = self.b3_result(conflicting)
        _, quantity_conflict_result = self.b3_result(quantity_conflict)

        for phase in ArithmeticPhase:
            self.assertEqual(
                ArithmeticOutcome.RAW_EXACT_MATCH,
                self.arithmetic(matched_result, ArithmeticScope.ITEM, phase)[0].outcome,
            )
            self.assertEqual(
                ArithmeticOutcome.AMBIGUOUS_OR_CONFLICTING_UNITS,
                self.arithmetic(
                    incomplete_result, ArithmeticScope.ITEM, phase
                )[0].outcome,
            )
            self.assertEqual(
                ArithmeticOutcome.AMBIGUOUS_OR_CONFLICTING_UNITS,
                self.arithmetic(
                    conflicting_result, ArithmeticScope.ITEM, phase
                )[0].outcome,
            )
            self.assertEqual(
                ArithmeticOutcome.AMBIGUOUS_OR_CONFLICTING_UNITS,
                self.arithmetic(
                    quantity_conflict_result, ArithmeticScope.ITEM, phase
                )[0].outcome,
            )
        self.assertEqual("0.75", incomplete_result.receipt_output.items[0].quantity.value)
        self.assertEqual("10.00", incomplete_result.receipt_output.items[0].unit_price.value)
        self.assertIn(
            DiagnosticCode.WEIGHT_EVIDENCE_INCOMPLETE,
            {item.code for item in incomplete_result.diagnostics},
        )
        self.assertIn(
            DiagnosticCode.WEIGHT_UNIT_CONFLICT,
            {item.code for item in conflicting_result.diagnostics},
        )
        self.assertIn(
            DiagnosticCode.WEIGHT_UNIT_CONFLICT,
            {item.code for item in quantity_conflict_result.diagnostics},
        )

    def test_split_weight_evidence_checks_unit_rate_and_currency_context(self) -> None:
        def split_weight_tokens(
            marker: str, source_rate: str, denominator: str
        ):
            values = (
                ("store", "PANTRYPROOF TEST MART", 10, 0, 180),
                ("date-label", "DATE:", 10, 20, 40),
                ("date-value", "2026-10-13", 55, 20, 90),
                ("d0", "BANANA", 10, 45, 55),
                ("wq", "0.750", 68, 45, 42),
                ("wu", "kg", 113, 45, 20),
                ("wrm", marker, 136, 45, 28),
                ("wp", source_rate, 167, 45, 42),
                ("wden", denominator, 212, 45, 30),
                ("quantity", "0.750", 245, 45, 42),
                ("x", "x", 290, 45, 8),
                ("unit", "10.00", 301, 45, 42),
                ("line", "7.50", 346, 45, 38),
                ("total-label", "TOTAL", 301, 100, 42),
                ("total", "7.50", 346, 100, 38),
            )
            return tuple(
                self.token(token_id, text, x, y, width=width)
                for token_id, text, x, y, width in values
            )

        unit_conflict_tokens = split_weight_tokens("RM", "10.00", "/lb")
        rate_conflict_tokens = split_weight_tokens("RM", "20.00", "/kg")
        unsupported_currency_tokens = split_weight_tokens("EUR", "10.00", "/kg")

        b2_unit, unit_conflict = self.b3_result(unit_conflict_tokens)
        _, rate_conflict = self.b3_result(rate_conflict_tokens)
        _, unsupported_currency = self.b3_result(unsupported_currency_tokens)

        self.assertEqual(
            ("d0", "wq", "wu", "wrm", "wp", "wden"),
            b2_unit.receipt_output.items[0].description.source_token_ids,
        )
        for result in (unit_conflict, rate_conflict, unsupported_currency):
            for phase in ArithmeticPhase:
                self.assertEqual(
                    ArithmeticOutcome.AMBIGUOUS_OR_CONFLICTING_UNITS,
                    self.arithmetic(result, ArithmeticScope.ITEM, phase)[0].outcome,
                )
            self.assertTrue(
                {
                    DiagnosticCode.WEIGHT_EVIDENCE_INCOMPLETE,
                    DiagnosticCode.WEIGHT_UNIT_CONFLICT,
                }
                & {item.code for item in result.diagnostics}
            )

    def test_b2_unresolved_fields_remain_unresolved_and_automatic(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=190),
            self.token("date", "DATE: 10/11/2026", 10, 20, width=165),
            self.token("item", "MILK 2 5.50 11.00", 10, 45, width=260),
            self.token("total", "TOTAL 11.00", 170, 80, width=155),
        )
        b2_result, result = self.b3_result(tokens)
        original = b2_result.receipt_output
        transformed = result.receipt_output

        self.assertEqual(FieldStatus.UNRESOLVED, original.purchase_date.status)
        self.assertEqual(FieldStatus.UNRESOLVED, transformed.purchase_date.status)
        self.assertIsNone(transformed.purchase_date.value)
        self.assertTrue(
            any(
                field.status is FieldStatus.UNRESOLVED
                for field in transformed.items[0].fields
            )
        )
        self.assertEqual(OutputStage.PRE_REVIEW_AUTOMATIC, transformed.output_stage)

    def test_every_declared_adjustment_label_has_a_complete_single_token_grammar(self) -> None:
        cases = {
            "DISCOUNT 1.00": AdjustmentKind.DISCOUNT,
            "VOUCHER 1.00": AdjustmentKind.VOUCHER,
            "COUPON 1.00": AdjustmentKind.COUPON,
            "REBATE 1.00": AdjustmentKind.REBATE,
            "TAX 1.00": AdjustmentKind.TAX,
            "GST 1.00": AdjustmentKind.GST,
            "SST 1.00": AdjustmentKind.SST,
            "SERVICE TAX 1.00": AdjustmentKind.SERVICE_TAX,
            "SERVICE CHARGE 1.00": AdjustmentKind.SERVICE_CHARGE,
            "SURCHARGE 1.00": AdjustmentKind.SURCHARGE,
            "SUBTOTAL 1.00": AdjustmentKind.SUBTOTAL,
            "ROUNDING - 0.01": AdjustmentKind.ROUNDING,
        }
        for index, (observed, expected_kind) in enumerate(cases.items()):
            with self.subTest(observed=observed):
                adjustment = self.token(
                    f"adjustment-{index}", observed, 10, 70, width=190
                )
                b2_result = self.with_extra_source_tokens(
                    self.b2_result(), adjustment
                )
                result = apply_b3(b2_result)
                self.assertEqual(1, len(result.adjustments))
                self.assertEqual(expected_kind, result.adjustments[0].kind)

    def test_complete_single_token_adjustments_are_recorded_without_double_counting(self) -> None:
        adjustment = self.token("discount", "DISCOUNT 1.00", 10, 70, width=150)
        tokens = self.simple_tokens(
            line_total="11.00",
            receipt_total="10.00",
        )
        b2_result = self.with_extra_source_tokens(self.b2_result(tokens), adjustment)
        result = apply_b3(b2_result)

        self.assertEqual(1, len(result.adjustments))
        observed = result.adjustments[0]
        self.assertEqual(AdjustmentKind.DISCOUNT, observed.kind)
        self.assertEqual(AdjustmentDirection.SUBTRACT, observed.direction)
        self.assertEqual("1.00", observed.amount)
        self.assertEqual("discount", observed.source_slice.token_id)
        self.assertEqual("1.00", observed.source_slice.text)
        self.assertFalse(observed.already_represented)
        self.assertIn(
            DiagnosticCode.ADJUSTMENT_OBSERVED,
            {diagnostic.code for diagnostic in result.diagnostics},
        )
        for phase in ArithmeticPhase:
            self.assertEqual(
                ArithmeticOutcome.EXPLICIT_PROMOTION_OR_ADJUSTMENT_EXCEPTION,
                self.arithmetic(
                    result, ArithmeticScope.OBSERVED_RECEIPT_ROWS, phase
                )[0].outcome,
            )
        self.assertEqual("10.00", result.receipt_output.receipt_total.value)
        with self.assertRaises(ValueError):
            replace(
                result,
                adjustments=(replace(observed, amount="2.00"),),
            )

    def test_adjustment_representation_uses_matching_monetary_component_only(self) -> None:
        adjustment = self.token("discount", "DISCOUNT 1.00", 10, 140, width=150)
        base = self.with_extra_source_tokens(self.b2_result(), adjustment)
        output = base.receipt_output
        represented_b2 = B2ExtractionResult(
            replace(
                output,
                receipt_total=replace(
                    output.receipt_total,
                    value="1.00",
                    source_token_ids=("discount",),
                ),
            ),
            None,
        )

        result = apply_b3(represented_b2)

        self.assertTrue(result.adjustments[0].already_represented)
        for phase in ArithmeticPhase:
            self.assertEqual(
                ArithmeticOutcome.MISMATCH_BEYOND_TOLERANCE,
                self.arithmetic(
                    result, ArithmeticScope.OBSERVED_RECEIPT_ROWS, phase
                )[0].outcome,
            )

    def test_adjustment_currency_conflict_cannot_explain_receipt_mismatch(self) -> None:
        discount = self.token(
            "dollar-discount", "DISCOUNT $ 1.00", 10, 140, width=175
        )
        tokens = self.simple_tokens(
            unit_price="RM 5.50",
            line_total="RM 11.00",
            receipt_total="RM 10.00",
        )
        b2_result = self.with_extra_source_tokens(self.b2_result(tokens), discount)

        result = apply_b3(b2_result)

        self.assertFalse(result.adjustments[0].already_represented)
        for phase in ArithmeticPhase:
            self.assertEqual(
                ArithmeticOutcome.CONFLICTING_CURRENCY_MARKERS,
                self.arithmetic(
                    result, ArithmeticScope.OBSERVED_RECEIPT_ROWS, phase
                )[0].outcome,
            )

    def test_subtotal_reference_does_not_explain_receipt_total_mismatch(self) -> None:
        subtotal = self.token("subtotal", "SUBTOTAL 11.00", 10, 70, width=150)
        tokens = self.simple_tokens(
            line_total="11.00",
            receipt_total="12.00",
        )

        b2_result = self.with_extra_source_tokens(self.b2_result(tokens), subtotal)
        result = apply_b3(b2_result)

        self.assertEqual(AdjustmentDirection.REFERENCE_ONLY, result.adjustments[0].direction)
        for phase in ArithmeticPhase:
            self.assertEqual(
                ArithmeticOutcome.MISMATCH_BEYOND_TOLERANCE,
                self.arithmetic(
                    result, ArithmeticScope.OBSERVED_RECEIPT_ROWS, phase
                )[0].outcome,
            )

    def test_adjustment_direction_is_conservative_for_rounding_and_signed_conflicts(self) -> None:
        extras = (
            self.token("rounding", "ROUNDING 0.01", 10, 65, width=145),
            self.token("tax", "TAX 0.60", 10, 77, width=120),
            self.token("conflict", "DISCOUNT + 1.00", 10, 89, width=165),
        )
        b2_result = self.with_extra_source_tokens(self.b2_result(), *extras)
        result = apply_b3(b2_result)
        by_kind = {adjustment.kind: adjustment for adjustment in result.adjustments}

        self.assertEqual(AdjustmentDirection.UNKNOWN, by_kind[AdjustmentKind.ROUNDING].direction)
        self.assertEqual(AdjustmentDirection.ADD, by_kind[AdjustmentKind.TAX].direction)
        self.assertEqual(AdjustmentDirection.UNKNOWN, by_kind[AdjustmentKind.DISCOUNT].direction)
        self.assertIn(
            "Rounding direction is also unknown.",
            by_kind[AdjustmentKind.ROUNDING].ambiguity_reason,
        )
        self.assertIn(
            "observed sign conflicts with the label direction",
            by_kind[AdjustmentKind.DISCOUNT].ambiguity_reason,
        )
        self.assertNotIn(
            "Rounding direction",
            by_kind[AdjustmentKind.DISCOUNT].ambiguity_reason,
        )

    def test_adjustment_words_inside_product_descriptions_are_not_adjustments(self) -> None:
        tokens = self.simple_tokens(
            description="DISCOUNT BISCUITS",
            quantity="1",
            unit_price="2.00",
            line_total="2.00",
            receipt_total="2.00",
        )
        _, result = self.b3_result(tokens)

        self.assertEqual((), result.adjustments)
        self.assertEqual("discount biscuits", result.receipt_output.items[0].description.value)

        exact_tokens = self.simple_tokens(
            description="DISCOUNT 1.00",
            quantity="1",
            unit_price="2.00",
            line_total="2.00",
            receipt_total="2.00",
        )
        _, exact_result = self.b3_result(exact_tokens)
        self.assertEqual((), exact_result.adjustments)
        self.assertEqual(
            "discount 1.00", exact_result.receipt_output.items[0].description.value
        )

    def test_split_adjustment_tokens_are_not_regrouped_by_b3(self) -> None:
        extras = (
            self.token("discount-label", "DISCOUNT", 10, 70, width=90),
            self.token("discount-value", "1.00", 120, 70, width=55),
        )

        b2_result = self.with_extra_source_tokens(self.b2_result(), *extras)
        result = apply_b3(b2_result)

        self.assertEqual((), result.adjustments)

    def test_explicit_promotion_qualifies_mismatch_without_price_rewrite(self) -> None:
        tokens = self.simple_tokens(
            description="PROMO MILK",
            quantity="2",
            unit_price="5.50",
            line_total="10.00",
            receipt_total="10.00",
        )
        _, result = self.b3_result(tokens)

        for phase in ArithmeticPhase:
            self.assertEqual(
                ArithmeticOutcome.EXPLICIT_PROMOTION_OR_ADJUSTMENT_EXCEPTION,
                self.arithmetic(result, ArithmeticScope.ITEM, phase)[0].outcome,
            )
        self.assertEqual("5.50", result.receipt_output.items[0].unit_price.value)
        self.assertEqual("10.00", result.receipt_output.items[0].line_total.value)

    def test_public_boundary_has_no_ocr_external_price_review_or_persistence_dependency(self) -> None:
        parameters = tuple(inspect.signature(apply_b3).parameters)
        imported_modules: set[str] = set()
        imported_names: set[str] = set()
        tree = ast.parse(inspect.getsource(baseline_b3))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_modules.add(node.module)
                imported_names.update(alias.name for alias in node.names)

        self.assertEqual(("b2_result",), parameters)
        self.assertNotIn("extract_b2", imported_names)
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
        _, result = self.b3_result()
        self.assertFalse(hasattr(result, "persistence_outcome"))
        self.assertFalse(hasattr(result, "review_record"))
        self.assertTrue(
            all(
                row.pantry_product_identity is None
                for row in result.receipt_output.items
            )
        )


if __name__ == "__main__":
    unittest.main()
