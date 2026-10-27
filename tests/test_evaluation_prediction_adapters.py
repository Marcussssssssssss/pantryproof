"""Synthetic tests for the B1/B2/B3 offline prediction adapters V0."""

from __future__ import annotations

import ast
import inspect
import unittest
from dataclasses import replace

import evaluation.prediction_adapters as prediction_adapters
from evaluation.manifest_schema import DatasetTier
from evaluation.prediction_adapters import (
    PredictionAdapterError,
    adapt_b1_result_to_prediction_receipt,
    adapt_b2_result_to_prediction_receipt,
    adapt_b3_result_to_prediction_receipt,
)
from evaluation.prediction_schema import (
    EvaluationRunScope,
    PredictionBundle,
    PredictionExecutionState,
    PredictionProvenance,
    serialize_prediction_collection,
)
from evaluation.prediction_validation import validate_prediction_collection
from pipeline.baseline_b1 import (
    B1ExtractionResult,
    EXTRACTOR_VERSION as B1_VERSION,
    extract_b1,
)
from pipeline.baseline_b3 import (
    EXTRACTOR_VERSION as B3_VERSION,
    apply_b3,
)
from pipeline.contracts import (
    FieldStatus,
    OcrSourceToken,
    OutputStage,
    Point,
    ReceiptExtractionStatus,
    ReceiptFieldName,
    ReceiptSourceEvidence,
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
    SourceProcessingStatus,
    SourceProvenance,
)
from pipeline.layout_b2 import (
    B2ExtractionResult,
    EXTRACTOR_VERSION as B2_VERSION,
    extract_b2,
)


class PredictionAdapterTests(unittest.TestCase):
    RECEIPT_ID = "synthetic-adapter-receipt"

    def token(
        self,
        token_id: str,
        text: str,
        x: float,
        y: float,
        *,
        width: float = 40,
        height: float = 10,
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
            raw_confidence=0.9,
        )

    def gate(
        self,
        decision: SourceEvidenceDecision = SourceEvidenceDecision.SUFFICIENT,
    ) -> SourceEvidenceGateResult:
        return SourceEvidenceGateResult(
            gate_result_id="synthetic-adapter-gate",
            receipt_id=self.RECEIPT_ID,
            decision=decision,
            reasons=("Synthetic source evidence is insufficient.",)
            if decision is SourceEvidenceDecision.INSUFFICIENT
            else (),
        )

    def evidence(
        self,
        tokens: tuple[OcrSourceToken, ...],
        *,
        decision: SourceEvidenceDecision = SourceEvidenceDecision.SUFFICIENT,
    ) -> ReceiptSourceEvidence:
        return ReceiptSourceEvidence(
            receipt_id=self.RECEIPT_ID,
            image_id="synthetic-adapter-image",
            provenance=SourceProvenance(
                source_system="synthetic-unit-test",
                source_reference="memory://synthetic-adapter-image",
            ),
            processing_status=SourceProcessingStatus.OCR_COMPLETED,
            tokens=tokens,
            gate_result=self.gate(decision),
        )

    def b1_tokens(self) -> tuple[OcrSourceToken, ...]:
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

    def b2_tokens(
        self,
        *,
        store: str = "PANTRYPROOF TEST MART",
        date_value: str = "2026-10-13",
        first_description: str = "MILK",
        second_description: str = "RICE",
        quantity: str = "2",
        unit_price: str = "5.50",
        line_total: str = "11.00",
        receipt_total: str = "23.90",
    ) -> tuple[OcrSourceToken, ...]:
        return (
            self.token("store", store, 20, 0, width=190),
            self.token("date-label", "DATE:", 10, 20, width=45),
            self.token("date-value", date_value, 70, 20, width=105),
            self.token("item1-description", first_description, 10, 45, width=90),
            self.token("item1-quantity", quantity, 110, 45, width=35),
            self.token("item1-x", "x", 150, 45, width=8),
            self.token("item1-unit", unit_price, 170, 45, width=70),
            self.token("item1-total", line_total, 255, 45, width=70),
            self.token("item2-description", second_description, 10, 65, width=90),
            self.token("item2-quantity", "1", 110, 65, width=35),
            self.token("item2-x", "x", 150, 65, width=8),
            self.token("item2-unit", "12.90", 170, 65, width=70),
            self.token("item2-total", "12.90", 255, 65, width=70),
            self.token("total-label", "TOTAL", 170, 100, width=65),
            self.token("total-value", receipt_total, 255, 100, width=70),
        )

    def provenance(self, suffix: str = "result") -> PredictionProvenance:
        return PredictionProvenance(
            event_id=f"adapter-event-{suffix}",
            source_record_reference=f"memory://producer-artifact/{suffix}",
            recorder_version="adapter-test-recorder-v0",
        )

    @staticmethod
    def ordinals(output, *, start: int = 10):
        return tuple(
            (row.row_id, start + index * 10)
            for index, row in enumerate(output.items)
        )

    @staticmethod
    def runtime_fields(output):
        fields = [output.store_name, output.purchase_date, output.receipt_total]
        fields.extend(field for row in output.items for field in row.fields)
        return tuple(fields)

    @staticmethod
    def prediction_fields(receipt):
        fields = list(receipt.receipt_fields)
        fields.extend(field for row in receipt.rows for field in row.fields)
        return tuple(fields)

    def b1_result(self) -> B1ExtractionResult:
        return extract_b1(self.evidence(self.b1_tokens()))

    def b2_result(self, tokens=None) -> B2ExtractionResult:
        return extract_b2(self.evidence(tokens or self.b2_tokens()))

    def assert_exact_field_copy(self, runtime_output, receipt) -> None:
        runtime_fields = self.runtime_fields(runtime_output)
        prediction_fields = self.prediction_fields(receipt)
        self.assertEqual(len(runtime_fields), len(prediction_fields))
        for source, copied in zip(runtime_fields, prediction_fields):
            self.assertEqual(source.field_id, copied.runtime_field_id)
            self.assertEqual(source.receipt_id, copied.runtime_receipt_id)
            self.assertIs(source.field_name, copied.field_name)
            self.assertIs(source.status, copied.status)
            self.assertEqual(source.item_row_id, copied.item_row_id)
            self.assertEqual(source.value, copied.value)
            self.assertEqual(source.source_token_ids, copied.source_token_ids)
            self.assertEqual(source.unresolved_reason, copied.unresolved_reason)

    def test_b1_structured_output_preserves_all_runtime_fields(self) -> None:
        result = self.b1_result()
        output = result.receipt_output
        receipt = adapt_b1_result_to_prediction_receipt(
            result,
            provenance=self.provenance("b1"),
            row_ordinals=self.ordinals(output),
            expected_version=B1_VERSION,
        )

        self.assertTrue(receipt.structured_output_present)
        self.assertIs(PredictionExecutionState.STRUCTURED_OUTPUT, receipt.execution_state)
        self.assertIs(output.extraction_status, receipt.extraction_status)
        self.assertEqual(output.receipt_id, receipt.runtime_receipt_id)
        self.assertEqual(tuple(row.row_id for row in output.items), tuple(
            row.runtime_row_id for row in receipt.rows
        ))
        self.assertEqual((10, 20), tuple(row.output_ordinal for row in receipt.rows))
        self.assert_exact_field_copy(output, receipt)
        self.assertEqual(
            set(ReceiptFieldName),
            {field.field_name for field in self.prediction_fields(receipt)},
        )

    def test_b2_structured_output_preserves_ids_values_and_token_order(self) -> None:
        result = self.b2_result()
        output = result.receipt_output
        receipt = adapt_b2_result_to_prediction_receipt(
            result,
            provenance=self.provenance("b2"),
            row_ordinals=self.ordinals(output, start=3),
            expected_version=B2_VERSION,
        )

        self.assertEqual((3, 13), tuple(row.output_ordinal for row in receipt.rows))
        self.assert_exact_field_copy(output, receipt)

    def test_b3_uses_transformed_values_and_preserves_b2_identity(self) -> None:
        tokens = self.b2_tokens(
            store="  ＰＡＮＴＲＹＰＲＯＯＦ\u00a0ＭＡＲＴ  ",
            date_value="13/10/2026",
            first_description="MILK—PREMIUM",
            quantity="02.500",
            unit_price="RM 4.00",
            line_total="MYR 10.00",
            receipt_total="$ 22.90",
        )
        b2_result = self.b2_result(tokens)
        b3_result = apply_b3(b2_result)
        b2_output = b2_result.receipt_output
        b3_output = b3_result.receipt_output
        receipt = adapt_b3_result_to_prediction_receipt(
            b3_result,
            provenance=self.provenance("stored-b3-artifact"),
            row_ordinals=self.ordinals(b3_output),
            expected_version=B3_VERSION,
        )

        self.assertNotEqual(b2_output.store_name.value, receipt.receipt_fields[0].value)
        self.assertEqual(b3_output.store_name.value, receipt.receipt_fields[0].value)
        self.assertEqual(
            tuple(field.field_id for field in self.runtime_fields(b2_output)),
            tuple(field.runtime_field_id for field in self.prediction_fields(receipt)),
        )
        self.assertEqual(
            tuple(row.row_id for row in b2_output.items),
            tuple(row.runtime_row_id for row in receipt.rows),
        )
        self.assertEqual(
            "memory://producer-artifact/stored-b3-artifact",
            receipt.provenance.source_record_reference,
        )

    def test_missing_and_unresolved_fields_remain_present(self) -> None:
        missing_tokens = tuple(
            token
            for token in self.b1_tokens()
            if token.token_id not in {"date-label", "date-value"}
        )
        missing_result = extract_b1(self.evidence(missing_tokens))
        missing_output = missing_result.receipt_output
        missing_receipt = adapt_b1_result_to_prediction_receipt(
            missing_result,
            provenance=self.provenance("missing"),
            row_ordinals=self.ordinals(missing_output),
        )
        copied_date = next(
            field
            for field in missing_receipt.receipt_fields
            if field.field_name is ReceiptFieldName.PURCHASE_DATE
        )
        self.assertIs(FieldStatus.MISSING, copied_date.status)
        self.assertIsNone(copied_date.value)
        self.assertEqual(
            missing_output.purchase_date.unresolved_reason,
            copied_date.unresolved_reason,
        )

        unresolved_tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=180),
            self.token("date", "DATE: 2026-10-13", 10, 20, width=150),
            self.token("description", "MILK", 10, 45, width=45),
            self.token("amount-a", "5.50", 155, 45, width=38),
            self.token("amount-b", "11.00", 220, 45, width=45),
            self.token("total", "TOTAL 11.00", 130, 75, width=135),
        )
        unresolved_result = self.b2_result(unresolved_tokens)
        unresolved_output = unresolved_result.receipt_output
        unresolved_receipt = adapt_b2_result_to_prediction_receipt(
            unresolved_result,
            provenance=self.provenance("unresolved"),
            row_ordinals=self.ordinals(unresolved_output),
        )
        unit_price = unresolved_receipt.rows[0].fields[2]
        self.assertIs(FieldStatus.UNRESOLVED, unit_price.status)
        self.assertEqual(("amount-a", "amount-b"), unit_price.source_token_ids)
        self.assertEqual(
            unresolved_output.items[0].unit_price.unresolved_reason,
            unit_price.unresolved_reason,
        )

    def test_empty_item_tuple_is_preserved(self) -> None:
        tokens = (
            self.token("store", "PANTRYPROOF TEST MART", 20, 0, width=180),
            self.token("date", "DATE: 2026-10-13", 10, 20, width=150),
            self.token("description", "MILK", 10, 45, width=45),
            self.token("far-amount", "11.00", 2000, 45, width=45),
            self.token("total", "TOTAL 11.00", 1900, 80, width=145),
        )
        result = self.b2_result(tokens)
        self.assertEqual((), result.receipt_output.items)
        receipt = adapt_b2_result_to_prediction_receipt(
            result,
            provenance=self.provenance("empty-items"),
            row_ordinals=(),
        )
        self.assertEqual((), receipt.rows)
        self.assertEqual(3, len(receipt.receipt_fields))

    def test_duplicate_descriptions_remain_distinct_rows(self) -> None:
        result = self.b2_result(self.b2_tokens(second_description="MILK"))
        output = result.receipt_output
        receipt = adapt_b2_result_to_prediction_receipt(
            result,
            provenance=self.provenance("duplicate-description"),
            row_ordinals=self.ordinals(output),
        )
        self.assertEqual(("MILK", "MILK"), tuple(
            row.fields[0].value for row in receipt.rows
        ))
        self.assertEqual(2, len({row.runtime_row_id for row in receipt.rows}))

    def test_b1_b2_and_b3_fallbacks_require_and_preserve_caller_detail(self) -> None:
        evidence = self.evidence(
            self.b2_tokens(), decision=SourceEvidenceDecision.INSUFFICIENT
        )
        b1_result = extract_b1(evidence)
        b2_result = extract_b2(evidence)
        b3_result = apply_b3(b2_result)
        cases = (
            (adapt_b1_result_to_prediction_receipt, b1_result),
            (adapt_b2_result_to_prediction_receipt, b2_result),
            (adapt_b3_result_to_prediction_receipt, b3_result),
        )
        for adapter, result in cases:
            with self.subTest(adapter=adapter.__name__):
                receipt = adapter(
                    result,
                    provenance=self.provenance(adapter.__name__),
                    row_ordinals=(),
                    state_detail="Caller-recorded fallback detail.",
                )
                self.assertEqual(self.RECEIPT_ID, receipt.runtime_receipt_id)
                self.assertFalse(receipt.structured_output_present)
                self.assertIs(
                    PredictionExecutionState.FALLBACK_NO_UPDATE,
                    receipt.execution_state,
                )
                self.assertIsNone(receipt.extraction_status)
                self.assertEqual((), receipt.receipt_fields)
                self.assertEqual((), receipt.rows)
                self.assertEqual(
                    "Caller-recorded fallback detail.", receipt.state_detail
                )

    def test_fallback_rejects_missing_or_blank_detail(self) -> None:
        result = extract_b1(
            self.evidence(
                self.b1_tokens(), decision=SourceEvidenceDecision.INSUFFICIENT
            )
        )
        for detail in (None, "", "   "):
            with self.subTest(detail=detail):
                with self.assertRaises(PredictionAdapterError):
                    adapt_b1_result_to_prediction_receipt(
                        result,
                        provenance=self.provenance("bad-detail"),
                        row_ordinals=(),
                        state_detail=detail,
                    )

    def test_fallback_rejects_nonempty_row_declarations(self) -> None:
        result = extract_b2(
            self.evidence(
                self.b2_tokens(), decision=SourceEvidenceDecision.INSUFFICIENT
            )
        )
        with self.assertRaises(PredictionAdapterError):
            adapt_b2_result_to_prediction_receipt(
                result,
                provenance=self.provenance("fallback-row"),
                row_ordinals=(("fabricated-row", 0),),
                state_detail="Fallback detail.",
            )

    def test_structured_output_rejects_fallback_detail(self) -> None:
        result = self.b1_result()
        with self.assertRaises(PredictionAdapterError):
            adapt_b1_result_to_prediction_receipt(
                result,
                provenance=self.provenance("structured-detail"),
                row_ordinals=self.ordinals(result.receipt_output),
                state_detail="Not applicable.",
            )

    def test_missing_row_declaration_is_rejected(self) -> None:
        result = self.b2_result()
        declarations = self.ordinals(result.receipt_output)
        with self.assertRaises(PredictionAdapterError):
            adapt_b2_result_to_prediction_receipt(
                result,
                provenance=self.provenance("missing-ordinal"),
                row_ordinals=declarations[:-1],
            )

    def test_extra_row_declaration_is_rejected(self) -> None:
        result = self.b2_result()
        with self.assertRaises(PredictionAdapterError):
            adapt_b2_result_to_prediction_receipt(
                result,
                provenance=self.provenance("extra-ordinal"),
                row_ordinals=(*self.ordinals(result.receipt_output), ("extra-row", 99)),
            )

    def test_duplicate_row_declaration_is_rejected(self) -> None:
        result = self.b2_result()
        declarations = self.ordinals(result.receipt_output)
        with self.assertRaises(PredictionAdapterError):
            adapt_b2_result_to_prediction_receipt(
                result,
                provenance=self.provenance("duplicate-row-ordinal"),
                row_ordinals=(*declarations, declarations[0]),
            )

    def test_duplicate_ordinal_is_rejected(self) -> None:
        result = self.b2_result()
        row_ids = tuple(row.row_id for row in result.receipt_output.items)
        with self.assertRaises(PredictionAdapterError):
            adapt_b2_result_to_prediction_receipt(
                result,
                provenance=self.provenance("duplicate-ordinal"),
                row_ordinals=((row_ids[0], 7), (row_ids[1], 7)),
            )

    def test_invalid_ordinal_values_are_rejected(self) -> None:
        result = self.b1_result()
        row_ids = tuple(row.row_id for row in result.receipt_output.items)
        for invalid in (-1, True, 1.5):
            with self.subTest(invalid=invalid):
                declarations = ((row_ids[0], invalid), (row_ids[1], 2))
                with self.assertRaises((PredictionAdapterError, TypeError)):
                    adapt_b1_result_to_prediction_receipt(
                        result,
                        provenance=self.provenance("invalid-ordinal"),
                        row_ordinals=declarations,
                    )

    def test_ordinal_declarations_must_be_explicit_and_immutable(self) -> None:
        result = self.b1_result()
        with self.assertRaises(TypeError):
            adapt_b1_result_to_prediction_receipt(
                result, provenance=self.provenance("no-ordinals")
            )
        with self.assertRaises(TypeError):
            adapt_b1_result_to_prediction_receipt(
                result,
                provenance=self.provenance("mutable-ordinals"),
                row_ordinals=list(self.ordinals(result.receipt_output)),
            )

    def test_structured_failed_extraction_status_remains_structured(self) -> None:
        original = self.b2_result()
        failed_output = replace(
            original.receipt_output,
            extraction_status=ReceiptExtractionStatus.FAILED,
        )
        result = B2ExtractionResult(failed_output, None)
        receipt = adapt_b2_result_to_prediction_receipt(
            result,
            provenance=self.provenance("structured-failed"),
            row_ordinals=self.ordinals(failed_output),
        )
        self.assertTrue(receipt.structured_output_present)
        self.assertIs(PredictionExecutionState.STRUCTURED_OUTPUT, receipt.execution_state)
        self.assertIs(ReceiptExtractionStatus.FAILED, receipt.extraction_status)

    def test_b2_and_b3_identity_reuse_is_valid_under_separate_scopes(self) -> None:
        b2_result = self.b2_result()
        b3_result = apply_b3(b2_result)
        declarations = self.ordinals(b2_result.receipt_output)
        b2_receipt = adapt_b2_result_to_prediction_receipt(
            b2_result,
            provenance=self.provenance("b2-scope"),
            row_ordinals=declarations,
        )
        b3_receipt = adapt_b3_result_to_prediction_receipt(
            b3_result,
            provenance=self.provenance("b3-scope"),
            row_ordinals=declarations,
        )
        common = dict(
            dataset_id="synthetic-dataset",
            dataset_tier=DatasetTier.TIER_A,
            partition_id="synthetic-validation",
            cohort_id="synthetic-primary",
            run_id="synthetic-run",
            configuration_id="synthetic-config",
            output_stage=OutputStage.PRE_REVIEW_AUTOMATIC,
        )
        bundles = (
            PredictionBundle(
                bundle_id="b2-bundle",
                scope=EvaluationRunScope(system_id="B2", **common),
                receipts=(b2_receipt,),
                provenance=self.provenance("b2-bundle"),
            ),
            PredictionBundle(
                bundle_id="b3-bundle",
                scope=EvaluationRunScope(system_id="B3", **common),
                receipts=(b3_receipt,),
                provenance=self.provenance("b3-bundle"),
            ),
        )
        self.assertEqual(
            tuple(field.runtime_field_id for field in self.prediction_fields(b2_receipt)),
            tuple(field.runtime_field_id for field in self.prediction_fields(b3_receipt)),
        )
        validate_prediction_collection(bundles)

    def test_expected_versions_are_verified_for_structured_results(self) -> None:
        b1_result = self.b1_result()
        b2_result = self.b2_result()
        b3_result = apply_b3(b2_result)
        cases = (
            (adapt_b1_result_to_prediction_receipt, b1_result, B1_VERSION),
            (adapt_b2_result_to_prediction_receipt, b2_result, B2_VERSION),
            (adapt_b3_result_to_prediction_receipt, b3_result, B3_VERSION),
        )
        for adapter, result, version in cases:
            with self.subTest(adapter=adapter.__name__):
                adapter(
                    result,
                    provenance=self.provenance(f"version-{version}"),
                    row_ordinals=self.ordinals(result.receipt_output),
                    expected_version=version,
                )
                with self.assertRaises(PredictionAdapterError):
                    adapter(
                        result,
                        provenance=self.provenance(f"wrong-{version}"),
                        row_ordinals=self.ordinals(result.receipt_output),
                        expected_version="unexpected-version",
                    )

    def test_fallback_version_verification_respects_artifact_limits(self) -> None:
        evidence = self.evidence(
            self.b2_tokens(), decision=SourceEvidenceDecision.INSUFFICIENT
        )
        b1_result = extract_b1(evidence)
        b2_result = extract_b2(evidence)
        for adapter, result, version in (
            (adapt_b1_result_to_prediction_receipt, b1_result, B1_VERSION),
            (adapt_b2_result_to_prediction_receipt, b2_result, B2_VERSION),
        ):
            with self.subTest(adapter=adapter.__name__):
                with self.assertRaises(PredictionAdapterError):
                    adapter(
                        result,
                        provenance=self.provenance("unverifiable-fallback"),
                        row_ordinals=(),
                        state_detail="Fallback detail.",
                        expected_version=version,
                    )

        b3_result = apply_b3(b2_result)
        adapt_b3_result_to_prediction_receipt(
            b3_result,
            provenance=self.provenance("verifiable-b3-fallback"),
            row_ordinals=(),
            state_detail="Fallback detail.",
            expected_version=B3_VERSION,
        )
        with self.assertRaises(PredictionAdapterError):
            adapt_b3_result_to_prediction_receipt(
                b3_result,
                provenance=self.provenance("wrong-b3-fallback"),
                row_ordinals=(),
                state_detail="Fallback detail.",
                expected_version="unexpected-version",
            )

    def test_non_null_confidence_is_rejected_instead_of_discarded(self) -> None:
        original = self.b1_result()
        output = original.receipt_output
        unsupported = replace(
            output,
            store_name=replace(output.store_name, confidence=0.75),
        )
        result = B1ExtractionResult(unsupported, None)
        with self.assertRaises(PredictionAdapterError):
            adapt_b1_result_to_prediction_receipt(
                result,
                provenance=self.provenance("confidence"),
                row_ordinals=self.ordinals(unsupported),
            )

    def test_pantry_product_identity_is_rejected_instead_of_discarded(self) -> None:
        original = self.b2_result()
        output = original.receipt_output
        unsupported_row = replace(
            output.items[0], pantry_product_identity="synthetic-product"
        )
        unsupported = replace(output, items=(unsupported_row, *output.items[1:]))
        result = B2ExtractionResult(unsupported, None)
        with self.assertRaises(PredictionAdapterError):
            adapt_b2_result_to_prediction_receipt(
                result,
                provenance=self.provenance("pantry-identity"),
                row_ordinals=self.ordinals(unsupported),
            )

    def test_adapted_receipts_use_canonical_c1a_serialization(self) -> None:
        result = self.b1_result()
        receipt = adapt_b1_result_to_prediction_receipt(
            result,
            provenance=self.provenance("serialization"),
            row_ordinals=tuple(reversed(self.ordinals(result.receipt_output))),
        )
        scope = EvaluationRunScope(
            dataset_id="synthetic-dataset",
            dataset_tier=DatasetTier.TIER_A,
            partition_id="synthetic-training",
            cohort_id="synthetic-primary",
            run_id="synthetic-run",
            system_id="B1",
            configuration_id="synthetic-config",
            output_stage=OutputStage.PRE_REVIEW_AUTOMATIC,
        )
        bundle = PredictionBundle(
            bundle_id="synthetic-b1-bundle",
            scope=scope,
            receipts=(receipt,),
            provenance=self.provenance("serialization-bundle"),
        )
        first = serialize_prediction_collection((bundle,))
        second = serialize_prediction_collection((bundle,))
        self.assertEqual(first, second)
        self.assertIn('"output_ordinal":10', first)
        self.assertIn('"state_detail":null', first)

    def test_adapter_module_has_no_reference_truth_dependency(self) -> None:
        tree = ast.parse(inspect.getsource(prediction_adapters))
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        self.assertFalse(
            any(module.startswith("evaluation.reference") for module in imported_modules)
        )
        for adapter in (
            adapt_b1_result_to_prediction_receipt,
            adapt_b2_result_to_prediction_receipt,
            adapt_b3_result_to_prediction_receipt,
        ):
            parameters = inspect.signature(adapter).parameters
            self.assertNotIn("reference_receipt_id", parameters)
            self.assertNotIn("reference", parameters)


if __name__ == "__main__":
    unittest.main()
