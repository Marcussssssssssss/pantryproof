"""Synthetic tests for the provisional Tier A reference contract V0."""

from __future__ import annotations

import inspect
import json
import unittest
from dataclasses import FrozenInstanceError, replace

from evaluation.reference_schema import (
    REFERENCE_SCHEMA_VERSION,
    AdjudicationEventReference,
    AnnotationEventReference,
    AnnotationProvenance,
    QADiagnosticStatus,
    ReferenceAvailability,
    ReferenceField,
    ReferenceItemRow,
    ReferenceQADiagnostic,
    ReferenceRecordStatus,
    ReferenceValue,
    ReferenceValueKind,
    TierAReferenceReceipt,
    serialize_reference_collection,
    serialize_reference_receipt,
)
from evaluation.reference_validation import (
    ReferenceValidationError,
    validate_evaluation_ready_receipt,
    validate_reference_collection,
    validate_reference_receipt,
)
from pipeline.contracts import ReceiptFieldName


class TierAReferenceSchemaTests(unittest.TestCase):
    RECEIPT_ID = "tier-a-synthetic-001"
    ANNOTATION_EVENT_ID = "annotation-event-001"
    ADJUDICATION_EVENT_ID = "adjudication-event-001"

    def provenance(self) -> AnnotationProvenance:
        return AnnotationProvenance(
            schema_version=REFERENCE_SCHEMA_VERSION,
            annotation_guideline_version="guideline-v0",
            annotation_events=(
                AnnotationEventReference(
                    event_id=self.ANNOTATION_EVENT_ID,
                    source_reference="annotation-form-001",
                ),
            ),
            adjudication_events=(
                AdjudicationEventReference(
                    event_id=self.ADJUDICATION_EVENT_ID,
                    adjudicated_reference_source="adjudicated-record-001",
                ),
            ),
        )

    def field(
        self,
        field_id: str,
        field_name: ReceiptFieldName,
        original: str | None,
        *,
        row_id: str | None = None,
        receipt_id: str | None = None,
        normalized: str | None = None,
        availability: ReferenceAvailability = ReferenceAvailability.AVAILABLE,
        unavailable_reason: str | None = None,
        adjudication_event_id: str | None = ADJUDICATION_EVENT_ID,
    ) -> ReferenceField:
        value = None
        if original is not None:
            value = ReferenceValue(
                original_transcription=original,
                normalized_value=normalized,
                normalization_spec_version="normalization-v0"
                if normalized is not None
                else None,
            )
        return ReferenceField(
            field_id=field_id,
            receipt_id=receipt_id or self.RECEIPT_ID,
            field_name=field_name,
            availability=availability,
            annotation_event_id=self.ANNOTATION_EVENT_ID,
            adjudication_event_id=adjudication_event_id,
            item_row_id=row_id,
            value=value,
            unavailable_reason=unavailable_reason,
        )

    def row(
        self,
        number: int,
        *,
        receipt_id: str | None = None,
        unit_price_available: bool = True,
    ) -> ReferenceItemRow:
        row_id = f"row-{number}"
        actual_receipt_id = receipt_id or self.RECEIPT_ID
        if unit_price_available:
            unit_price = self.field(
                f"field-{number}-unit-price",
                ReceiptFieldName.UNIT_PRICE,
                "RM 5.00",
                row_id=row_id,
                receipt_id=actual_receipt_id,
                normalized="5.00",
            )
        else:
            unit_price = self.field(
                f"field-{number}-unit-price",
                ReceiptFieldName.UNIT_PRICE,
                None,
                row_id=row_id,
                receipt_id=actual_receipt_id,
                availability=ReferenceAvailability.UNAVAILABLE,
                unavailable_reason="No unit price is visibly attributable to this row.",
            )
        return ReferenceItemRow(
            row_id=row_id,
            receipt_id=actual_receipt_id,
            source_order=number - 1,
            description=self.field(
                f"field-{number}-description",
                ReceiptFieldName.ITEM_DESCRIPTION,
                f"ITEM {number}",
                row_id=row_id,
                receipt_id=actual_receipt_id,
                normalized=f"item {number}",
            ),
            quantity=self.field(
                f"field-{number}-quantity",
                ReceiptFieldName.QUANTITY,
                "2",
                row_id=row_id,
                receipt_id=actual_receipt_id,
                normalized="2",
            ),
            unit_price=unit_price,
            line_total=self.field(
                f"field-{number}-line-total",
                ReceiptFieldName.LINE_TOTAL,
                "RM 10.00",
                row_id=row_id,
                receipt_id=actual_receipt_id,
                normalized="10.00",
            ),
        )

    def receipt(
        self,
        *,
        receipt_id: str | None = None,
        items: tuple[ReferenceItemRow, ...] | None = None,
        store_name: ReferenceField | None = None,
        purchase_date: ReferenceField | None = None,
        receipt_total: ReferenceField | None = None,
        status: ReferenceRecordStatus = ReferenceRecordStatus.FINALIZED,
        provenance: AnnotationProvenance | None = None,
        diagnostics: tuple[ReferenceQADiagnostic, ...] = (),
    ) -> TierAReferenceReceipt:
        actual_receipt_id = receipt_id or self.RECEIPT_ID
        return TierAReferenceReceipt(
            receipt_id=actual_receipt_id,
            source_reference_id=f"source-{actual_receipt_id}",
            provenance=provenance or self.provenance(),
            store_name=store_name
            or self.field(
                "field-store",
                ReceiptFieldName.STORE_NAME,
                "SYNTHETIC MART",
                receipt_id=actual_receipt_id,
                normalized="synthetic mart",
            ),
            purchase_date=purchase_date
            or self.field(
                "field-date",
                ReceiptFieldName.PURCHASE_DATE,
                "23/10/2026",
                receipt_id=actual_receipt_id,
                normalized="2026-10-23",
            ),
            items=(self.row(1, receipt_id=actual_receipt_id),)
            if items is None
            else items,
            receipt_total=receipt_total
            or self.field(
                "field-total",
                ReceiptFieldName.RECEIPT_TOTAL,
                "RM 9.00",
                receipt_id=actual_receipt_id,
                normalized="9.00",
            ),
            status=status,
            qa_diagnostics=diagnostics,
        )

    def test_valid_multiple_rows_cover_all_seven_roles_in_source_order(self) -> None:
        receipt = self.receipt(items=(self.row(1), self.row(2)))

        self.assertEqual((0, 1), tuple(row.source_order for row in receipt.items))
        self.assertEqual(
            set(ReceiptFieldName), {field.field_name for field in receipt.all_fields}
        )
        validate_evaluation_ready_receipt(receipt)

    def test_available_and_unavailable_unit_price_are_distinct(self) -> None:
        receipt = self.receipt(
            items=(self.row(1), self.row(2, unit_price_available=False))
        )

        self.assertIs(
            receipt.items[0].unit_price.availability,
            ReferenceAvailability.AVAILABLE,
        )
        unavailable = receipt.items[1].unit_price
        self.assertIs(unavailable.availability, ReferenceAvailability.UNAVAILABLE)
        self.assertIsNone(unavailable.value)
        self.assertFalse(hasattr(unavailable, "external_retailer_price"))

    def test_receipt_level_fields_can_be_unavailable_without_values(self) -> None:
        unavailable = {
            name: self.field(
                field_id,
                name,
                None,
                availability=ReferenceAvailability.UNAVAILABLE,
                unavailable_reason="Not visibly supported in the synthetic receipt.",
            )
            for name, field_id in (
                (ReceiptFieldName.STORE_NAME, "field-store-unavailable"),
                (ReceiptFieldName.PURCHASE_DATE, "field-date-unavailable"),
                (ReceiptFieldName.RECEIPT_TOTAL, "field-total-unavailable"),
            )
        }
        receipt = self.receipt(
            store_name=unavailable[ReceiptFieldName.STORE_NAME],
            purchase_date=unavailable[ReceiptFieldName.PURCHASE_DATE],
            receipt_total=unavailable[ReceiptFieldName.RECEIPT_TOTAL],
        )

        self.assertTrue(all(field.value is None for field in receipt.receipt_fields))

    def test_duplicate_receipt_ids_are_rejected(self) -> None:
        first = self.receipt()
        second = self.receipt()
        with self.assertRaisesRegex(ReferenceValidationError, "Duplicate receipt ID"):
            validate_reference_collection((first, second))

    def test_duplicate_item_row_ids_are_rejected(self) -> None:
        first = self.row(1)
        duplicate = replace(first, source_order=1)
        with self.assertRaisesRegex(ReferenceValidationError, "Duplicate item-row ID"):
            self.receipt(items=(first, duplicate))

    def test_duplicate_field_identity_is_rejected(self) -> None:
        row = self.row(1)
        duplicate_quantity = replace(
            row.quantity,
            field_id=row.description.field_id,
        )
        with self.assertRaisesRegex(ReferenceValidationError, "Duplicate field identity"):
            self.receipt(items=(replace(row, quantity=duplicate_quantity),))

    def test_conflicting_field_role_is_rejected(self) -> None:
        row = self.row(1)
        wrong = replace(row.quantity, field_name=ReceiptFieldName.LINE_TOTAL)
        with self.assertRaisesRegex(ReferenceValidationError, "conflicting role"):
            self.receipt(items=(replace(row, quantity=wrong),))

    def test_item_row_linked_to_another_receipt_is_rejected(self) -> None:
        foreign = self.row(1, receipt_id="tier-a-foreign")
        with self.assertRaisesRegex(ReferenceValidationError, "another receipt"):
            self.receipt(items=(foreign,))

    def test_field_pointing_to_nonexistent_row_is_rejected(self) -> None:
        row = self.row(1)
        wrong = replace(row.quantity, item_row_id="missing-row")
        with self.assertRaisesRegex(ReferenceValidationError, "nonexistent or incorrect"):
            self.receipt(items=(replace(row, quantity=wrong),))

    def test_receipt_field_attached_to_item_row_is_rejected(self) -> None:
        store = replace(self.receipt().store_name, item_row_id="row-1")
        with self.assertRaisesRegex(ReferenceValidationError, "must not reference"):
            self.receipt(store_name=store)

    def test_item_field_represented_at_receipt_level_is_rejected(self) -> None:
        wrong = self.field(
            "field-store",
            ReceiptFieldName.ITEM_DESCRIPTION,
            "ITEM AT TOP",
        )
        with self.assertRaisesRegex(ReferenceValidationError, "conflicting role"):
            self.receipt(store_name=wrong)

    def test_unavailable_field_cannot_contain_a_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "fabricated value"):
            self.field(
                "field-invalid-unavailable",
                ReceiptFieldName.UNIT_PRICE,
                "RM 4.00",
                row_id="row-1",
                availability=ReferenceAvailability.UNAVAILABLE,
                unavailable_reason="Synthetic contradiction.",
            )

    def test_available_field_requires_reference_truth(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires an adjudicated"):
            self.field(
                "field-invalid-available",
                ReceiptFieldName.UNIT_PRICE,
                None,
                row_id="row-1",
            )

    def test_original_and_normalized_values_remain_separate_and_literal(self) -> None:
        value = ReferenceValue(
            original_transcription="  RM ０５.００  ",
            normalized_value="5.00",
            normalization_spec_version="normalization-v0",
        )

        self.assertEqual("  RM ０５.００  ", value.original_transcription)
        self.assertEqual("5.00", value.normalized_value)

    def test_normalized_value_requires_a_versioned_specification(self) -> None:
        with self.assertRaisesRegex(ValueError, "normalization_spec_version"):
            ReferenceValue(
                original_transcription="RM 5.00",
                normalized_value="5.00",
            )

    def test_adjudicated_unit_price_can_reference_literal_same_row_evidence(self) -> None:
        row = self.row(1)
        derived = ReferenceValue(
            original_transcription=None,
            value_kind=ReferenceValueKind.ADJUDICATED_DERIVED,
            derived_value="5.00",
            derivation_rule_reference="annotation-rule-unit-price-v1",
            derivation_evidence_field_ids=(
                row.quantity.field_id,
                row.line_total.field_id,
            ),
        )
        unit_price = replace(row.unit_price, value=derived)
        receipt = self.receipt(items=(replace(row, unit_price=unit_price),))

        self.assertEqual("5.00", receipt.items[0].unit_price.value.adjudicated_value)
        self.assertIsNone(receipt.items[0].unit_price.value.original_transcription)
        validate_evaluation_ready_receipt(receipt)

    def test_derived_value_cannot_claim_fabricated_source_transcription(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not fabricate"):
            ReferenceValue(
                original_transcription="RM 5.00",
                value_kind=ReferenceValueKind.ADJUDICATED_DERIVED,
                derived_value="5.00",
                derivation_rule_reference="annotation-rule-unit-price-v1",
                derivation_evidence_field_ids=("field-1-line-total",),
            )

    def test_derived_value_requires_rule_and_receipt_evidence_provenance(self) -> None:
        cases = (
            {
                "derivation_rule_reference": None,
                "derivation_evidence_field_ids": ("field-1-line-total",),
            },
            {
                "derivation_rule_reference": "annotation-rule-unit-price-v1",
                "derivation_evidence_field_ids": (),
            },
        )
        for case in cases:
            with self.subTest(case=case):
                with self.assertRaises(ValueError):
                    ReferenceValue(
                        original_transcription=None,
                        value_kind=ReferenceValueKind.ADJUDICATED_DERIVED,
                        derived_value="5.00",
                        **case,
                    )

    def test_derived_value_rejects_unknown_or_cross_row_evidence(self) -> None:
        first = self.row(1)
        second = self.row(2)
        for evidence_id, message in (
            ("missing-field", "unknown receipt evidence"),
            (second.line_total.field_id, "outside its item row"),
        ):
            with self.subTest(evidence_id=evidence_id):
                derived = ReferenceValue(
                    original_transcription=None,
                    value_kind=ReferenceValueKind.ADJUDICATED_DERIVED,
                    derived_value="5.00",
                    derivation_rule_reference="annotation-rule-unit-price-v1",
                    derivation_evidence_field_ids=(evidence_id,),
                )
                unit_price = replace(first.unit_price, value=derived)
                with self.assertRaisesRegex(ReferenceValidationError, message):
                    self.receipt(
                        items=(replace(first, unit_price=unit_price), second)
                    )

    def test_derived_reference_value_is_limited_to_unit_price(self) -> None:
        row = self.row(1)
        derived = ReferenceValue(
            original_transcription=None,
            value_kind=ReferenceValueKind.ADJUDICATED_DERIVED,
            derived_value="10.00",
            derivation_rule_reference="annotation-rule-unit-price-v1",
            derivation_evidence_field_ids=(row.quantity.field_id,),
        )

        with self.assertRaisesRegex(ValueError, "Only unit-price"):
            replace(row.line_total, value=derived)

    def test_finalized_derived_unit_price_requires_adjudication_event(self) -> None:
        row = self.row(1)
        derived = ReferenceValue(
            original_transcription=None,
            value_kind=ReferenceValueKind.ADJUDICATED_DERIVED,
            derived_value="5.00",
            derivation_rule_reference="annotation-rule-unit-price-v1",
            derivation_evidence_field_ids=(
                row.quantity.field_id,
                row.line_total.field_id,
            ),
        )
        unit_price = replace(
            row.unit_price,
            value=derived,
            adjudication_event_id=None,
        )

        with self.assertRaisesRegex(ReferenceValidationError, "lacks adjudication"):
            self.receipt(items=(replace(row, unit_price=unit_price),))

    def test_serialization_is_deterministic_and_preserves_item_order(self) -> None:
        receipt = self.receipt(items=(self.row(1), self.row(2)))
        first = serialize_reference_receipt(receipt)
        second = serialize_reference_receipt(receipt)
        payload = json.loads(first)

        self.assertEqual(first, second)
        self.assertEqual(["row-1", "row-2"], [row["row_id"] for row in payload["items"]])
        self.assertEqual("RM 5.00", payload["items"][0]["unit_price"]["value"]["original_transcription"])

    def test_collection_serialization_is_canonical_by_receipt_id(self) -> None:
        first = self.receipt(receipt_id="receipt-a", items=(self.row(1, receipt_id="receipt-a"),))
        second = self.receipt(receipt_id="receipt-b", items=(self.row(1, receipt_id="receipt-b"),))

        self.assertEqual(
            serialize_reference_collection((second, first)),
            serialize_reference_collection((first, second)),
        )

    def test_draft_record_is_distinguishable_and_not_evaluation_ready(self) -> None:
        row = self.row(1)
        draft_row = replace(
            row,
            description=replace(row.description, adjudication_event_id=None),
        )
        draft = self.receipt(
            items=(draft_row,), status=ReferenceRecordStatus.DRAFT
        )

        validate_reference_receipt(draft)
        with self.assertRaisesRegex(ReferenceValidationError, "Draft"):
            validate_evaluation_ready_receipt(draft)

    def test_finalized_field_requires_known_adjudication_provenance(self) -> None:
        row = self.row(1)
        incomplete = replace(row.quantity, adjudication_event_id=None)
        with self.assertRaisesRegex(ReferenceValidationError, "lacks adjudication"):
            self.receipt(items=(replace(row, quantity=incomplete),))

    def test_unknown_annotation_event_is_contradictory_provenance(self) -> None:
        row = self.row(1)
        wrong = replace(row.description, annotation_event_id="unknown-annotation")
        with self.assertRaisesRegex(ReferenceValidationError, "unknown annotation"):
            self.receipt(items=(replace(row, description=wrong),))

    def test_annotation_and_adjudication_event_ids_must_be_distinct(self) -> None:
        with self.assertRaisesRegex(ValueError, "distinct events"):
            AnnotationProvenance(
                schema_version=REFERENCE_SCHEMA_VERSION,
                annotation_guideline_version="guideline-v0",
                annotation_events=(
                    AnnotationEventReference("event-1", "annotation-source-1"),
                ),
                adjudication_events=(
                    AdjudicationEventReference("event-1", "adjudicated-source-1"),
                ),
            )

    def test_qa_review_is_not_a_structural_error_but_blocks_finalization(self) -> None:
        diagnostic = ReferenceQADiagnostic(
            diagnostic_id="qa-001",
            receipt_id=self.RECEIPT_ID,
            code="TOTAL_REVIEW",
            message="Synthetic discrepancy requires adjudicator review.",
            related_field_ids=("field-total",),
            status=QADiagnosticStatus.REVIEW_REQUIRED,
        )
        draft = self.receipt(
            status=ReferenceRecordStatus.DRAFT,
            diagnostics=(diagnostic,),
        )
        validate_reference_receipt(draft)

        with self.assertRaisesRegex(ReferenceValidationError, "unresolved QA"):
            replace(draft, status=ReferenceRecordStatus.FINALIZED)

    def test_resolved_qa_diagnostic_retains_adjudication_audit(self) -> None:
        diagnostic = ReferenceQADiagnostic(
            diagnostic_id="qa-002",
            receipt_id=self.RECEIPT_ID,
            code="PROMOTION_EXPLAINS_TOTAL",
            message="Receipt total differs from line sum after a visible promotion.",
            related_field_ids=("field-total", "field-1-line-total"),
            status=QADiagnosticStatus.RESOLVED,
            resolution_adjudication_event_id=self.ADJUDICATION_EVENT_ID,
            resolution_note="Visible receipt promotion accounts for the difference.",
        )
        receipt = self.receipt(diagnostics=(diagnostic,))

        validate_evaluation_ready_receipt(receipt)

    def test_promotional_total_may_differ_from_unadjusted_line_sum(self) -> None:
        receipt = self.receipt(
            items=(self.row(1), self.row(2)),
            receipt_total=self.field(
                "field-total",
                ReceiptFieldName.RECEIPT_TOTAL,
                "RM 18.00",
                normalized="18.00",
            ),
        )

        # Two RM10.00 lines need not force the receipt total to RM20.00.
        validate_evaluation_ready_receipt(receipt)
        self.assertEqual("18.00", receipt.receipt_total.value.normalized_value)

    def test_records_are_frozen_and_slotted(self) -> None:
        receipt = self.receipt()
        self.assertFalse(hasattr(receipt, "__dict__"))
        with self.assertRaises(FrozenInstanceError):
            receipt.receipt_id = "changed"  # type: ignore[misc]

    def test_schema_has_no_prediction_input_or_constructor(self) -> None:
        signature = inspect.signature(TierAReferenceReceipt)
        self.assertTrue(all("prediction" not in name for name in signature.parameters))
        self.assertFalse(hasattr(TierAReferenceReceipt, "from_prediction"))
        self.assertFalse(hasattr(TierAReferenceReceipt, "from_ocr"))

    def test_finalized_structure_does_not_claim_tier_a_eligibility(self) -> None:
        no_pantry_lines = self.receipt(items=())

        # Structurally complete truth may proceed to the separate frozen
        # eligibility checklist, where the missing pantry line is assessed.
        validate_evaluation_ready_receipt(no_pantry_lines)
        self.assertEqual((), no_pantry_lines.items)
        self.assertFalse(hasattr(no_pantry_lines, "tier_a_eligible"))

    def test_invalid_required_identifier_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "receipt_id"):
            replace(self.receipt(), receipt_id="contains spaces")


if __name__ == "__main__":
    unittest.main()
