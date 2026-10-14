"""Synthetic unit tests for the PantryProof version-0 receipt contract."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, replace

from pipeline.contracts import (
    CandidateValue,
    CorrectionEvidence,
    CorrectionStatus,
    EvidenceAvailability,
    ExternalPriceReference,
    FailureStage,
    FieldStatus,
    OcrSourceToken,
    OutputStage,
    PersistenceOutcome,
    Point,
    PolicyState,
    PreResolutionDisposition,
    ReceiptExtractionStatus,
    ReceiptFieldName,
    ReceiptItemRow,
    ReceiptOutput,
    ReceiptSourceEvidence,
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
    SourceProcessingStatus,
    SourceProvenance,
    StructuredField,
    UncertaintyState,
)


class ContractTests(unittest.TestCase):
    RECEIPT_ID = "synthetic-receipt-001"

    def token(
        self, token_id: str, text: str, confidence: float | None = None
    ) -> OcrSourceToken:
        return OcrSourceToken(
            receipt_id=self.RECEIPT_ID,
            token_id=token_id,
            original_text=text,
            polygon=(Point(0, 0), Point(10, 0), Point(10, 5), Point(0, 5)),
            raw_confidence=confidence,
        )

    def evidence(
        self,
        decision: SourceEvidenceDecision = SourceEvidenceDecision.SUFFICIENT,
    ) -> ReceiptSourceEvidence:
        tokens = (
            self.token("store", "SYNTHETIC MART", 0.99),
            self.token("date", "2026-10-14"),
            self.token("item-1-description", "MILK"),
            self.token("item-1-quantity", "2"),
            self.token("item-1-unit-price", "5.50"),
            self.token("item-1-line-total", "11.00"),
            self.token("item-2-description", "RICE"),
            self.token("item-2-quantity", "1"),
            self.token("item-2-unit-price", "12.90"),
            self.token("item-2-line-total", "12.90"),
            self.token("total", "23.90"),
        )
        return ReceiptSourceEvidence(
            receipt_id=self.RECEIPT_ID,
            image_id="synthetic-image-001",
            provenance=SourceProvenance(
                source_system="unit-test",
                source_reference="memory://synthetic-receipt-001",
            ),
            processing_status=SourceProcessingStatus.OCR_COMPLETED,
            tokens=tokens,
            gate_result=SourceEvidenceGateResult(
                gate_result_id="gate-001",
                receipt_id=self.RECEIPT_ID,
                decision=decision,
                reasons=("Synthetic source evidence is insufficient.",)
                if decision is SourceEvidenceDecision.INSUFFICIENT
                else (),
            ),
        )

    def extracted_field(
        self,
        field_id: str,
        field_name: ReceiptFieldName,
        value: str,
        token_id: str,
        row_id: str | None = None,
        confidence: float | None = None,
    ) -> StructuredField:
        return StructuredField(
            field_id=field_id,
            receipt_id=self.RECEIPT_ID,
            field_name=field_name,
            status=FieldStatus.EXTRACTED,
            value=value,
            item_row_id=row_id,
            source_token_ids=(token_id,),
            confidence=confidence,
        )

    def missing_field(
        self,
        field_id: str,
        field_name: ReceiptFieldName,
        reason: str,
        row_id: str | None = None,
    ) -> StructuredField:
        return StructuredField(
            field_id=field_id,
            receipt_id=self.RECEIPT_ID,
            field_name=field_name,
            status=FieldStatus.MISSING,
            item_row_id=row_id,
            unresolved_reason=reason,
        )

    def item_row(self, number: int) -> ReceiptItemRow:
        row_id = f"row-{number}"
        prefix = f"item-{number}"
        values = (
            (ReceiptFieldName.ITEM_DESCRIPTION, "MILK" if number == 1 else "RICE", "description"),
            (ReceiptFieldName.QUANTITY, "2" if number == 1 else "1", "quantity"),
            (ReceiptFieldName.UNIT_PRICE, "5.50" if number == 1 else "12.90", "unit-price"),
            (ReceiptFieldName.LINE_TOTAL, "11.00" if number == 1 else "12.90", "line-total"),
        )
        fields = [
            self.extracted_field(
                f"{row_id}-{suffix}",
                field_name,
                value,
                f"{prefix}-{suffix}",
                row_id,
            )
            for field_name, value, suffix in values
        ]
        return ReceiptItemRow(
            row_id=row_id,
            receipt_id=self.RECEIPT_ID,
            description=fields[0],
            quantity=fields[1],
            unit_price=fields[2],
            line_total=fields[3],
        )

    def receipt(
        self,
        items: tuple[ReceiptItemRow, ...],
        source_evidence: ReceiptSourceEvidence | None = None,
    ) -> ReceiptOutput:
        return ReceiptOutput(
            receipt_id=self.RECEIPT_ID,
            store_name=self.extracted_field(
                "store-field", ReceiptFieldName.STORE_NAME, "SYNTHETIC MART", "store"
            ),
            purchase_date=self.extracted_field(
                "date-field", ReceiptFieldName.PURCHASE_DATE, "2026-10-14", "date"
            ),
            items=items,
            receipt_total=self.extracted_field(
                "total-field", ReceiptFieldName.RECEIPT_TOTAL, "23.90", "total"
            ),
            source_evidence=source_evidence or self.evidence(),
            extraction_status=ReceiptExtractionStatus.EXTRACTED,
            extractor_version="synthetic-test-extractor",
        )

    def test_valid_receipt_with_two_detected_item_rows(self) -> None:
        receipt = self.receipt((self.item_row(1), self.item_row(2)))

        self.assertEqual(2, len(receipt.items))
        self.assertEqual("MILK", receipt.items[0].description.value)
        self.assertEqual("RICE", receipt.items[1].description.value)
        self.assertEqual("23.90", receipt.receipt_total.value)

    def test_missing_field_has_no_fabricated_value(self) -> None:
        missing = self.missing_field(
            "missing-date", ReceiptFieldName.PURCHASE_DATE, "No date token detected."
        )

        self.assertIsNone(missing.value)
        self.assertEqual(FieldStatus.MISSING, missing.status)
        self.assertEqual((), missing.source_token_ids)

    def test_correction_candidate_does_not_change_original_ocr_text(self) -> None:
        token = self.token("description", "M1LK")
        correction = CorrectionEvidence(
            field_id="description-field",
            original_candidate=CandidateValue("M1LK", ("description",)),
            gate_result_id="gate-001",
            status=CorrectionStatus.ALTERNATIVE_PROPOSED,
            uncertainty=UncertaintyState.UNRESOLVED,
            alternatives=(CandidateValue("MILK", ("retailer-reference-1",)),),
            uncertainty_reason="Original and alternative differ.",
        )

        self.assertEqual("M1LK", token.original_text)
        self.assertEqual("M1LK", correction.original_candidate.value)
        self.assertEqual("MILK", correction.alternatives[0].value)
        with self.assertRaises(FrozenInstanceError):
            token.original_text = "MILK"  # type: ignore[misc]

    def test_field_references_correct_source_token(self) -> None:
        field = self.extracted_field(
            "total-field", ReceiptFieldName.RECEIPT_TOTAL, "23.90", "total"
        )
        receipt = self.receipt((self.item_row(1), self.item_row(2)))

        self.assertEqual(("total",), field.source_token_ids)
        self.assertIn(field.source_token_ids[0], receipt.source_evidence.token_ids)

    def test_optional_confidence_remains_absent(self) -> None:
        token = self.token("no-score", "VISIBLE TEXT")
        field = self.extracted_field(
            "store-field", ReceiptFieldName.STORE_NAME, "VISIBLE TEXT", "no-score"
        )

        self.assertIsNone(token.raw_confidence)
        self.assertIsNone(field.confidence)

    def test_missing_external_price_reference_does_not_invalidate_ground_truth(self) -> None:
        unit_price = self.item_row(1).unit_price
        external_reference = ExternalPriceReference(
            availability=EvidenceAvailability.UNAVAILABLE,
            unavailable_reason="No retailer reference was supplied.",
        )

        self.assertEqual(FieldStatus.EXTRACTED, unit_price.status)
        self.assertEqual("5.50", unit_price.value)
        self.assertEqual(EvidenceAvailability.UNAVAILABLE, external_reference.availability)

    def test_pre_resolution_and_persistence_failures_are_distinct(self) -> None:
        gate_result = self.evidence().gate_result
        pre_resolution = PreResolutionDisposition(
            state=PolicyState.FAILED,
            gate_result=gate_result,
            failure_stage=FailureStage.PRE_RESOLUTION,
            failure_reason="Synthetic pre-resolution failure.",
        )
        automatic = PreResolutionDisposition(
            state=PolicyState.AUTO_RESOLVED,
            gate_result=gate_result,
        )
        persistence = PersistenceOutcome(
            pre_resolution=automatic,
            state=PolicyState.FAILED,
            failure_stage=FailureStage.INVENTORY_PERSISTENCE,
            failure_reason="Synthetic persistence failure.",
        )

        self.assertNotEqual(pre_resolution.failure_stage, persistence.failure_stage)
        with self.assertRaises(ValueError):
            PersistenceOutcome(
                pre_resolution=automatic,
                state=PolicyState.COMMITTED,
            )
        committed = PersistenceOutcome(
            pre_resolution=automatic,
            state=PolicyState.COMMITTED,
            inventory_write_reference="synthetic-write-001",
        )
        self.assertEqual(PolicyState.COMMITTED, committed.state)

    def test_no_item_row_is_manufactured_for_undetected_line(self) -> None:
        receipt = self.receipt((self.item_row(1),))

        self.assertEqual(1, len(receipt.items))
        all_missing_row = "undetected-row"
        with self.assertRaises(ValueError):
            ReceiptItemRow(
                row_id=all_missing_row,
                receipt_id=self.RECEIPT_ID,
                description=self.missing_field(
                    "missing-description",
                    ReceiptFieldName.ITEM_DESCRIPTION,
                    "No source detection.",
                    all_missing_row,
                ),
                quantity=self.missing_field(
                    "missing-quantity",
                    ReceiptFieldName.QUANTITY,
                    "No source detection.",
                    all_missing_row,
                ),
                unit_price=self.missing_field(
                    "missing-unit-price",
                    ReceiptFieldName.UNIT_PRICE,
                    "No source detection.",
                    all_missing_row,
                ),
                line_total=self.missing_field(
                    "missing-line-total",
                    ReceiptFieldName.LINE_TOTAL,
                    "No source detection.",
                    all_missing_row,
                ),
            )

    def test_insufficient_gate_rejects_structured_output_and_requires_fallback(self) -> None:
        evidence = self.evidence(SourceEvidenceDecision.INSUFFICIENT)

        with self.assertRaises(ValueError):
            self.receipt((self.item_row(1),), source_evidence=evidence)
        with self.assertRaises(ValueError):
            PreResolutionDisposition(
                state=PolicyState.AUTO_RESOLVED,
                gate_result=evidence.gate_result,
            )
        fallback = PreResolutionDisposition(
            state=PolicyState.FALLBACK_NO_UPDATE,
            gate_result=evidence.gate_result,
        )
        self.assertEqual(PolicyState.FALLBACK_NO_UPDATE, fallback.state)

    def test_accepted_alternative_requires_candidate(self) -> None:
        with self.assertRaises(ValueError):
            CorrectionEvidence(
                field_id="description-field",
                original_candidate=CandidateValue("M1LK", ("description",)),
                gate_result_id="gate-001",
                status=CorrectionStatus.ALTERNATIVE_ACCEPTED,
                uncertainty=UncertaintyState.RESOLVED,
            )

    def test_selected_candidate_must_belong_to_alternatives(self) -> None:
        offered = CandidateValue("MILK", ("retailer-reference-1",))
        not_offered = CandidateValue("MILK POWDER", ("retailer-reference-2",))

        with self.assertRaises(ValueError):
            CorrectionEvidence(
                field_id="description-field",
                original_candidate=CandidateValue("M1LK", ("description",)),
                gate_result_id="gate-001",
                status=CorrectionStatus.ALTERNATIVE_ACCEPTED,
                uncertainty=UncertaintyState.RESOLVED,
                alternatives=(offered,),
                selected_alternative=not_offered,
            )

    def test_duplicate_field_ids_are_rejected_within_receipt(self) -> None:
        receipt = self.receipt((self.item_row(1),))
        duplicate_date = replace(
            receipt.purchase_date,
            field_id=receipt.store_name.field_id,
        )

        with self.assertRaises(ValueError):
            replace(receipt, purchase_date=duplicate_date)

    def test_non_finite_ocr_and_field_confidence_are_rejected(self) -> None:
        for invalid in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(kind="ocr", value=invalid):
                with self.assertRaises(ValueError):
                    self.token("invalid-score", "TEXT", invalid)
            with self.subTest(kind="field", value=invalid):
                with self.assertRaises(ValueError):
                    self.extracted_field(
                        "invalid-score-field",
                        ReceiptFieldName.STORE_NAME,
                        "TEXT",
                        "store",
                        confidence=invalid,
                    )

    def test_initial_receipt_cannot_claim_review_or_oracle_stage(self) -> None:
        receipt = self.receipt((self.item_row(1),))
        self.assertEqual(OutputStage.PRE_REVIEW_AUTOMATIC, receipt.output_stage)

        for invalid_stage in (
            OutputStage.HUMAN_REVIEWED,
            OutputStage.ORACLE_MODIFIED,
        ):
            with self.subTest(stage=invalid_stage):
                with self.assertRaises(TypeError):
                    replace(receipt, output_stage=invalid_stage)

    def test_persistence_outcome_retains_frozen_pre_resolution_decision(self) -> None:
        pre_resolution = PreResolutionDisposition(
            state=PolicyState.AUTO_RESOLVED,
            gate_result=self.evidence().gate_result,
        )
        persistence = PersistenceOutcome(
            pre_resolution=pre_resolution,
            state=PolicyState.COMMITTED,
            inventory_write_reference="synthetic-write-001",
        )

        self.assertIs(pre_resolution, persistence.pre_resolution)
        self.assertEqual(PolicyState.AUTO_RESOLVED, persistence.pre_resolution.state)
        with self.assertRaises(FrozenInstanceError):
            pre_resolution.state = PolicyState.REVIEW_REQUIRED  # type: ignore[misc]

    def test_committed_is_rejected_after_fallback(self) -> None:
        fallback = PreResolutionDisposition(
            state=PolicyState.FALLBACK_NO_UPDATE,
            gate_result=self.evidence(SourceEvidenceDecision.INSUFFICIENT).gate_result,
        )

        with self.assertRaises(ValueError):
            PersistenceOutcome(
                pre_resolution=fallback,
                state=PolicyState.COMMITTED,
                inventory_write_reference="synthetic-write-001",
            )

    def test_committed_is_rejected_after_pre_resolution_failure(self) -> None:
        failed = PreResolutionDisposition(
            state=PolicyState.FAILED,
            gate_result=self.evidence().gate_result,
            failure_stage=FailureStage.PRE_RESOLUTION,
            failure_reason="Synthetic pre-resolution failure.",
        )

        with self.assertRaises(ValueError):
            PersistenceOutcome(
                pre_resolution=failed,
                state=PolicyState.COMMITTED,
                inventory_write_reference="synthetic-write-001",
            )

    def test_committed_is_rejected_after_unresolved_review(self) -> None:
        review = PreResolutionDisposition(
            state=PolicyState.REVIEW_REQUIRED,
            gate_result=self.evidence().gate_result,
        )

        with self.assertRaises(ValueError):
            PersistenceOutcome(
                pre_resolution=review,
                state=PolicyState.COMMITTED,
                inventory_write_reference="synthetic-write-001",
            )

    def test_persistence_failure_is_rejected_after_terminal_dispositions(self) -> None:
        dispositions = (
            PreResolutionDisposition(
                state=PolicyState.FALLBACK_NO_UPDATE,
                gate_result=self.evidence(
                    SourceEvidenceDecision.INSUFFICIENT
                ).gate_result,
            ),
            PreResolutionDisposition(
                state=PolicyState.FAILED,
                gate_result=self.evidence().gate_result,
                failure_stage=FailureStage.PRE_RESOLUTION,
                failure_reason="Synthetic pre-resolution failure.",
            ),
        )

        for disposition in dispositions:
            with self.subTest(state=disposition.state):
                with self.assertRaises(ValueError):
                    PersistenceOutcome(
                        pre_resolution=disposition,
                        state=PolicyState.FAILED,
                        failure_stage=FailureStage.INVENTORY_PERSISTENCE,
                        failure_reason="Synthetic persistence failure.",
                    )

    def test_sufficient_evidence_cannot_create_fallback(self) -> None:
        with self.assertRaises(ValueError):
            PreResolutionDisposition(
                state=PolicyState.FALLBACK_NO_UPDATE,
                gate_result=self.evidence().gate_result,
            )

    def test_auto_resolved_can_enter_persistence_without_losing_disposition(self) -> None:
        automatic = PreResolutionDisposition(
            state=PolicyState.AUTO_RESOLVED,
            gate_result=self.evidence().gate_result,
        )
        persistence = PersistenceOutcome(
            pre_resolution=automatic,
            state=PolicyState.COMMITTED,
            inventory_write_reference="synthetic-write-002",
        )

        self.assertIs(automatic, persistence.pre_resolution)
        self.assertEqual(PolicyState.AUTO_RESOLVED, persistence.pre_resolution.state)


if __name__ == "__main__":
    unittest.main()
