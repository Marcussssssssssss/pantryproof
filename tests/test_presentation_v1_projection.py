"""Tests for the synthetic-only Contract V0 presentation projection boundary."""

from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from pipeline.contracts import (
    FieldStatus,
    OcrSourceToken,
    Point,
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
)
from pipeline.presentation_v1.conformance import validate_presentation_v1_object
from tests.presentation_v1_projection_support import (
    project_available_receipt,
    project_insufficient_source_evidence,
)


class PresentationV1ProjectionTest(unittest.TestCase):
    def test_fixtures_67_and_67a_are_exact_genuine_v0_projections(self) -> None:
        fixture_root = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "receipt_presentation_v1"
            / "v1"
            / "fixtures"
        )
        cases = (
            (
                "67-result-with-ocr-failed-evidence.json",
                "result-ocr-failed-001",
                SourceProcessingStatus.OCR_FAILED,
                ReceiptExtractionStatus.PARTIAL,
            ),
            (
                "67a-result-with-received-evidence.json",
                "result-received-001",
                SourceProcessingStatus.RECEIVED,
                ReceiptExtractionStatus.EXTRACTED,
            ),
        )
        for filename, identity, source_status, extraction_status in cases:
            with self.subTest(filename=filename):
                output = _canonical_fixture_output(
                    identity,
                    source_status=source_status,
                    extraction_status=extraction_status,
                )
                projected = project_available_receipt(
                    output,
                    request_id="request-" + identity,
                    image_id="image-" + identity,
                    producer_id="SYNTHETIC_CONTRACT_V0_PROJECTOR",
                )
                wrapper = json.loads((fixture_root / filename).read_text("utf-8"))
                self.assertEqual(projected, wrapper["envelope"])

    def test_available_result_preserves_all_four_contract_v0_source_statuses(self) -> None:
        for status in SourceProcessingStatus:
            with self.subTest(status=status.value):
                output = _complete_output(status)
                envelope = project_available_receipt(
                    output,
                    request_id=_request_id(status),
                    image_id=output.source_evidence.image_id,
                    producer_id="HANDCRAFTED_SYNTHETIC_PRODUCER",
                )

                validated = validate_presentation_v1_object(
                    envelope,
                    expected_request_id=_request_id(status),
                    expected_image_id=output.source_evidence.image_id,
                    consumer_mode="FIXTURE",
                )

                self.assertIsNotNone(validated)
                self.assertEqual(
                    status.value,
                    envelope["sourceEvidence"]["sourceProcessingStatus"],
                )
                self.assertEqual("SUFFICIENT", envelope["sourceGate"]["decision"])

    def test_insufficient_result_preserves_all_four_contract_v0_source_statuses(
        self,
    ) -> None:
        for status in SourceProcessingStatus:
            with self.subTest(status=status.value):
                evidence = _insufficient_evidence(status)
                envelope = project_insufficient_source_evidence(
                    evidence,
                    request_id=_request_id(status),
                    image_id=evidence.image_id,
                )

                validated = validate_presentation_v1_object(
                    envelope,
                    expected_request_id=_request_id(status),
                    expected_image_id=evidence.image_id,
                    consumer_mode="FIXTURE",
                )

                self.assertIsNotNone(validated)
                self.assertEqual(
                    "SOURCE_EVIDENCE_INSUFFICIENT", envelope["outcome"]["status"]
                )
                self.assertEqual(status.value, envelope["sourceEvidence"]["sourceProcessingStatus"])
                self.assertEqual("INSUFFICIENT", envelope["sourceGate"]["decision"])
                self.assertIsNone(envelope["automaticExtraction"])
                self.assertIsNone(envelope["receipt"])

    def test_failed_extraction_status_is_preserved_not_recomputed(self) -> None:
        output = _failed_structural_output()

        envelope = project_available_receipt(
            output,
            request_id="request-synthetic-failed-status",
            image_id=output.source_evidence.image_id,
            producer_id="HANDCRAFTED_SYNTHETIC_PRODUCER",
        )
        validated = validate_presentation_v1_object(
            envelope,
            expected_request_id="request-synthetic-failed-status",
            expected_image_id=output.source_evidence.image_id,
            consumer_mode="FIXTURE",
        )

        self.assertIsNotNone(validated)
        self.assertEqual("FAILED", envelope["automaticExtraction"]["extractionStatus"])
        self.assertEqual([], envelope["receipt"]["itemRows"])
        self.assertTrue(
            all(
                field["status"] != "EXTRACTED"
                for field in envelope["receipt"]["receiptFields"]
            )
        )

    def test_projection_preserves_identities_tokens_original_values_and_order(self) -> None:
        output = _complete_output(SourceProcessingStatus.OCR_COMPLETED)
        envelope = project_available_receipt(
            output,
            request_id="request-synthetic-integrity",
            image_id=output.source_evidence.image_id,
            producer_id="HANDCRAFTED_SYNTHETIC_PRODUCER",
        )

        self.assertEqual("request-synthetic-integrity", envelope["requestId"])
        self.assertEqual(output.source_evidence.image_id, envelope["imageId"])
        self.assertEqual(output.receipt_id, envelope["receipt"]["receiptId"])
        self.assertEqual(
            output.source_evidence.gate_result.gate_result_id,
            envelope["sourceGate"]["gateResultId"],
        )
        self.assertEqual(
            [token.token_id for token in output.source_evidence.tokens],
            envelope["sourceEvidence"]["tokenIds"],
        )
        self.assertEqual(
            ["STORE_NAME", "PURCHASE_DATE", "RECEIPT_TOTAL"],
            [field["role"] for field in envelope["receipt"]["receiptFields"]],
        )
        self.assertEqual(
            ["ITEM_DESCRIPTION", "QUANTITY", "UNIT_PRICE", "LINE_TOTAL"],
            [field["role"] for field in envelope["receipt"]["itemRows"][0]["fields"]],
        )

        receipt_total = envelope["receipt"]["receiptFields"][2]
        self.assertEqual("RM 12.50", receipt_total["originalAutomaticValue"])
        self.assertEqual("12.50", receipt_total["presentationValue"])
        unit_price = envelope["receipt"]["itemRows"][0]["fields"][2]
        self.assertEqual("MYR 10.00", unit_price["originalAutomaticValue"])
        self.assertEqual("10.00", unit_price["presentationValue"])
        self.assertEqual(
            "HANDCRAFTED_SYNTHETIC_PRODUCER",
            envelope["automaticExtraction"]["producer"]["producerId"],
        )
        self.assertEqual(
            output.extractor_version,
            envelope["automaticExtraction"]["producer"]["producerVersion"],
        )

    def test_projection_redacts_raw_contract_v0_provenance(self) -> None:
        output = _complete_output(SourceProcessingStatus.OCR_COMPLETED)
        raw_system = output.source_evidence.provenance.source_system
        raw_reference = output.source_evidence.provenance.source_reference

        envelope = project_available_receipt(
            output,
            request_id="request-synthetic-redaction",
            image_id=output.source_evidence.image_id,
            producer_id="HANDCRAFTED_SYNTHETIC_PRODUCER",
        )
        serialized = json.dumps(envelope, ensure_ascii=False)

        self.assertNotIn(raw_system, serialized)
        self.assertNotIn(raw_reference, serialized)
        self.assertEqual(
            "M3E_SYNTHETIC_V0", envelope["source"]["provenance"]["sourceSystem"]
        )
        self.assertIsNone(envelope["source"]["provenance"]["contentSha256"])
        self.assertNotIn("original_text", serialized)
        self.assertNotIn("polygon", serialized)

    def test_projection_rejects_caller_image_identity_mismatch(self) -> None:
        output = _complete_output(SourceProcessingStatus.OCR_COMPLETED)

        with self.assertRaisesRegex(ValueError, "image_id"):
            project_available_receipt(
                output,
                request_id="request-synthetic-mismatch",
                image_id="image-synthetic-other",
                producer_id="HANDCRAFTED_SYNTHETIC_PRODUCER",
            )

    def test_projection_rejects_unsafe_ids_and_free_text_provenance(self) -> None:
        output = _complete_output(SourceProcessingStatus.OCR_COMPLETED)
        with self.assertRaisesRegex(ValueError, "privacy-safe protocol identifier"):
            project_available_receipt(
                output,
                request_id="request/unsafe",
                image_id=output.source_evidence.image_id,
                producer_id="HANDCRAFTED_SYNTHETIC_PRODUCER",
            )

        evidence = _insufficient_evidence(SourceProcessingStatus.OCR_PARTIAL)
        unsafe_gate = replace(
            evidence.gate_result,
            reasons=("file:///tmp/participant-001-receipt.txt",),
        )
        unsafe_evidence = replace(evidence, gate_result=unsafe_gate)
        with self.assertRaisesRegex(ValueError, "prohibited path, URI"):
            project_insufficient_source_evidence(
                unsafe_evidence,
                request_id="request-synthetic-unsafe-reason",
                image_id=unsafe_evidence.image_id,
            )

    def test_insufficient_projection_rejects_sufficient_gate(self) -> None:
        evidence = _complete_output(
            SourceProcessingStatus.OCR_COMPLETED
        ).source_evidence

        with self.assertRaisesRegex(ValueError, "INSUFFICIENT"):
            project_insufficient_source_evidence(
                evidence,
                request_id="request-synthetic-wrong-gate",
                image_id=evidence.image_id,
            )

    def test_projector_does_not_round_or_correct_invalid_original_money(self) -> None:
        output = _complete_output(
            SourceProcessingStatus.OCR_COMPLETED,
            receipt_total="RM 12.345",
        )

        with self.assertRaisesRegex(ValueError, "cannot be canonically projected"):
            project_available_receipt(
                output,
                request_id="request-synthetic-no-rounding",
                image_id=output.source_evidence.image_id,
                producer_id="HANDCRAFTED_SYNTHETIC_PRODUCER",
            )

    def test_producer_id_is_an_explicit_required_argument(self) -> None:
        output = _complete_output(SourceProcessingStatus.OCR_COMPLETED)

        with self.assertRaises(TypeError):
            project_available_receipt(  # type: ignore[call-arg]
                output,
                request_id="request-synthetic-explicit-producer",
                image_id=output.source_evidence.image_id,
            )


def _request_id(status: SourceProcessingStatus) -> str:
    return "request-synthetic-" + status.value.lower().replace("_", "-")


def _complete_output(
    status: SourceProcessingStatus,
    *,
    receipt_total: str = "RM 12.50",
) -> ReceiptOutput:
    receipt_id = "receipt-synthetic-projection"
    image_id = "image-synthetic-" + status.value.lower().replace("_", "-")
    token_roles = (
        "store",
        "date",
        "receipt-total",
        "description",
        "quantity",
        "unit-price",
        "line-total",
    )
    tokens = tuple(
        _token(receipt_id, "token-synthetic-" + role, role)
        for role in token_roles
    )
    evidence = _evidence(
        receipt_id=receipt_id,
        image_id=image_id,
        status=status,
        decision=SourceEvidenceDecision.SUFFICIENT,
        tokens=tokens,
    )

    row_id = "row-synthetic-001"
    row = ReceiptItemRow(
        row_id=row_id,
        receipt_id=receipt_id,
        description=_extracted_field(
            "field-synthetic-description",
            receipt_id,
            ReceiptFieldName.ITEM_DESCRIPTION,
            "Beras Tempatan 1kg",
            "token-synthetic-description",
            row_id=row_id,
        ),
        quantity=_extracted_field(
            "field-synthetic-quantity",
            receipt_id,
            ReceiptFieldName.QUANTITY,
            "0.750",
            "token-synthetic-quantity",
            row_id=row_id,
        ),
        unit_price=_extracted_field(
            "field-synthetic-unit-price",
            receipt_id,
            ReceiptFieldName.UNIT_PRICE,
            "MYR 10.00",
            "token-synthetic-unit-price",
            row_id=row_id,
        ),
        line_total=_extracted_field(
            "field-synthetic-line-total",
            receipt_id,
            ReceiptFieldName.LINE_TOTAL,
            "RM 7.50",
            "token-synthetic-line-total",
            row_id=row_id,
        ),
    )
    return ReceiptOutput(
        receipt_id=receipt_id,
        store_name=_extracted_field(
            "field-synthetic-store",
            receipt_id,
            ReceiptFieldName.STORE_NAME,
            "Kedai Runcit Harmoni",
            "token-synthetic-store",
            confidence=-1.5,
        ),
        purchase_date=_extracted_field(
            "field-synthetic-date",
            receipt_id,
            ReceiptFieldName.PURCHASE_DATE,
            "2026-11-05",
            "token-synthetic-date",
        ),
        items=(row,),
        receipt_total=_extracted_field(
            "field-synthetic-receipt-total",
            receipt_id,
            ReceiptFieldName.RECEIPT_TOTAL,
            receipt_total,
            "token-synthetic-receipt-total",
        ),
        source_evidence=evidence,
        extraction_status=ReceiptExtractionStatus.EXTRACTED,
        extractor_version="synthetic-v0-projector-test-1",
    )


def _failed_structural_output() -> ReceiptOutput:
    receipt_id = "receipt-synthetic-extraction-failed"
    evidence = _evidence(
        receipt_id=receipt_id,
        image_id="image-synthetic-extraction-failed",
        status=SourceProcessingStatus.OCR_PARTIAL,
        decision=SourceEvidenceDecision.SUFFICIENT,
        tokens=(),
    )
    return ReceiptOutput(
        receipt_id=receipt_id,
        store_name=_absent_field(
            "field-failed-store",
            receipt_id,
            ReceiptFieldName.STORE_NAME,
            FieldStatus.MISSING,
            "STORE_NOT_FOUND",
        ),
        purchase_date=_absent_field(
            "field-failed-date",
            receipt_id,
            ReceiptFieldName.PURCHASE_DATE,
            FieldStatus.UNRESOLVED,
            "DATE_AMBIGUOUS",
        ),
        items=(),
        receipt_total=_absent_field(
            "field-failed-total",
            receipt_id,
            ReceiptFieldName.RECEIPT_TOTAL,
            FieldStatus.MISSING,
            "TOTAL_NOT_FOUND",
        ),
        source_evidence=evidence,
        extraction_status=ReceiptExtractionStatus.FAILED,
        extractor_version="synthetic-v0-projector-test-failed-1",
    )


def _canonical_fixture_output(
    identity: str,
    *,
    source_status: SourceProcessingStatus,
    extraction_status: ReceiptExtractionStatus,
) -> ReceiptOutput:
    """Build the exact genuine Contract V0 source for fixtures 67 and 67a."""

    receipt_id = "receipt-" + identity
    image_id = "image-" + identity
    token_ids = {
        role: f"token-{identity}-{role}"
        for role in (
            "store",
            "date",
            "description",
            "quantity",
            "unit-price",
            "line-total",
            "receipt-total",
        )
    }
    tokens = tuple(
        _token(receipt_id, token_id, role)
        for role, token_id in token_ids.items()
    )
    evidence = _evidence(
        receipt_id=receipt_id,
        image_id=image_id,
        status=source_status,
        decision=SourceEvidenceDecision.SUFFICIENT,
        tokens=tokens,
        gate_result_id="gate-" + identity,
    )
    row_id = f"row-{identity}-001"
    row = ReceiptItemRow(
        row_id=row_id,
        receipt_id=receipt_id,
        description=_extracted_field(
            f"field-{identity}-description",
            receipt_id,
            ReceiptFieldName.ITEM_DESCRIPTION,
            "Garam Halus",
            token_ids["description"],
            row_id=row_id,
        ),
        quantity=_extracted_field(
            f"field-{identity}-quantity",
            receipt_id,
            ReceiptFieldName.QUANTITY,
            "1",
            token_ids["quantity"],
            row_id=row_id,
        ),
        unit_price=_extracted_field(
            f"field-{identity}-unit-price",
            receipt_id,
            ReceiptFieldName.UNIT_PRICE,
            "RM 2.50",
            token_ids["unit-price"],
            row_id=row_id,
        ),
        line_total=_extracted_field(
            f"field-{identity}-line-total",
            receipt_id,
            ReceiptFieldName.LINE_TOTAL,
            "RM 2.50",
            token_ids["line-total"],
            row_id=row_id,
        ),
    )
    return ReceiptOutput(
        receipt_id=receipt_id,
        store_name=_extracted_field(
            f"field-{identity}-store",
            receipt_id,
            ReceiptFieldName.STORE_NAME,
            "Pasar Mini Harmoni",
            token_ids["store"],
        ),
        purchase_date=_extracted_field(
            f"field-{identity}-date",
            receipt_id,
            ReceiptFieldName.PURCHASE_DATE,
            "2026-11-05",
            token_ids["date"],
        ),
        items=(row,),
        receipt_total=_extracted_field(
            f"field-{identity}-receipt-total",
            receipt_id,
            ReceiptFieldName.RECEIPT_TOTAL,
            "RM 2.50",
            token_ids["receipt-total"],
        ),
        source_evidence=evidence,
        extraction_status=extraction_status,
        extractor_version="m3e-1",
    )


def _insufficient_evidence(status: SourceProcessingStatus) -> ReceiptSourceEvidence:
    receipt_id = "receipt-synthetic-insufficient-" + status.value.lower().replace(
        "_", "-"
    )
    image_id = "image-synthetic-insufficient-" + status.value.lower().replace(
        "_", "-"
    )
    token = _token(receipt_id, "token-synthetic-insufficient", "unresolved")
    return _evidence(
        receipt_id=receipt_id,
        image_id=image_id,
        status=status,
        decision=SourceEvidenceDecision.INSUFFICIENT,
        tokens=(token,),
    )


def _evidence(
    *,
    receipt_id: str,
    image_id: str,
    status: SourceProcessingStatus,
    decision: SourceEvidenceDecision,
    tokens: tuple[OcrSourceToken, ...],
    gate_result_id: str | None = None,
) -> ReceiptSourceEvidence:
    return ReceiptSourceEvidence(
        receipt_id=receipt_id,
        image_id=image_id,
        provenance=SourceProvenance(
            source_system="RAW_SYNTHETIC_TEST_SYSTEM_SHOULD_BE_REDACTED",
            source_reference=r"C:\synthetic-test-only\receipt-image.png",
            content_sha256="a" * 64,
        ),
        processing_status=status,
        tokens=tokens,
        gate_result=SourceEvidenceGateResult(
            gate_result_id=gate_result_id or "gate-" + receipt_id,
            receipt_id=receipt_id,
            decision=decision,
            reasons=("SOURCE_TEXT_INCOMPLETE",)
            if decision is SourceEvidenceDecision.INSUFFICIENT
            else (),
        ),
    )


def _token(receipt_id: str, token_id: str, original_text: str) -> OcrSourceToken:
    return OcrSourceToken(
        receipt_id=receipt_id,
        token_id=token_id,
        original_text=original_text,
        polygon=(Point(0.0, 0.0), Point(1.0, 0.0), Point(1.0, 1.0)),
        raw_confidence=0.8,
    )


def _extracted_field(
    field_id: str,
    receipt_id: str,
    role: ReceiptFieldName,
    value: str,
    token_id: str,
    *,
    row_id: str | None = None,
    confidence: float | None = None,
) -> StructuredField:
    return StructuredField(
        field_id=field_id,
        receipt_id=receipt_id,
        field_name=role,
        status=FieldStatus.EXTRACTED,
        value=value,
        item_row_id=row_id,
        source_token_ids=(token_id,),
        confidence=confidence,
    )


def _absent_field(
    field_id: str,
    receipt_id: str,
    role: ReceiptFieldName,
    status: FieldStatus,
    reason: str,
) -> StructuredField:
    return StructuredField(
        field_id=field_id,
        receipt_id=receipt_id,
        field_name=role,
        status=status,
        value=None,
        source_token_ids=(),
        confidence=None,
        unresolved_reason=reason,
    )


if __name__ == "__main__":
    unittest.main()

