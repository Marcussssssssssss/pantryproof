"""Synthetic tests for the PaddleOCR-to-Contract V0 adapter."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from pipeline.contracts import (
    Point,
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
    SourceProcessingStatus,
)
from pipeline.ocr_adapter import (
    AdaptedOcrSource,
    OcrAdapterError,
    adapt_paddleocr_result,
    attach_gate_result,
)


class ArrayLike:
    """Small NumPy-compatible test double exposing tolist()."""

    def __init__(self, value: object) -> None:
        self.value = value

    def tolist(self) -> object:
        return self.value


class OcrAdapterTests(unittest.TestCase):
    RECEIPT_ID = "synthetic-receipt-001"

    def valid_result(self) -> dict[str, object]:
        return {
            "rec_texts": ["M1LK", "TOTAL 23.90"],
            "rec_scores": [0.91, 0.98],
            "rec_polys": [
                [[1, 2], [11, 2], [11, 7], [1, 7]],
                [[2, 10], [22, 10], [22, 16], [2, 16]],
            ],
            "dt_polys": [
                [[1, 2], [11, 2], [11, 7], [1, 7]],
                [[2, 10], [22, 10], [22, 16], [2, 16]],
            ],
            "rec_boxes": [[1, 2, 11, 7], [2, 10, 22, 16]],
        }

    def adapt(
        self,
        result: dict[str, object] | None = None,
        *,
        source_image_path: Path | None = None,
    ) -> AdaptedOcrSource:
        return adapt_paddleocr_result(
            result if result is not None else self.valid_result(),
            receipt_id=self.RECEIPT_ID,
            image_id="synthetic-image-001",
            source_system="paddleocr-3.7-test",
            source_reference="memory://synthetic-image-001",
            processing_status=SourceProcessingStatus.OCR_COMPLETED,
            source_image_path=source_image_path,
        )

    def gate_result(self, receipt_id: str | None = None) -> SourceEvidenceGateResult:
        return SourceEvidenceGateResult(
            gate_result_id="synthetic-gate-001",
            receipt_id=receipt_id or self.RECEIPT_ID,
            decision=SourceEvidenceDecision.SUFFICIENT,
        )

    def test_multiple_valid_ocr_tokens(self) -> None:
        adapted = self.adapt()

        self.assertEqual(2, len(adapted.tokens))
        self.assertEqual((0.91, 0.98), tuple(t.raw_confidence for t in adapted.tokens))

    def test_literal_text_and_source_order_are_preserved(self) -> None:
        result = self.valid_result()
        result["rec_texts"] = ["  M1LK  ", "TOTAL 23.90"]

        adapted = self.adapt(result)

        self.assertEqual(
            ("  M1LK  ", "TOTAL 23.90"),
            tuple(token.original_text for token in adapted.tokens),
        )

    def test_token_ids_are_deterministic_and_unique(self) -> None:
        first = self.adapt()
        second = self.adapt()

        first_ids = tuple(token.token_id for token in first.tokens)
        self.assertEqual(first_ids, tuple(token.token_id for token in second.tokens))
        self.assertEqual(len(first_ids), len(set(first_ids)))
        self.assertEqual(
            (
                f"{self.RECEIPT_ID}:paddleocr:000000",
                f"{self.RECEIPT_ID}:paddleocr:000001",
            ),
            first_ids,
        )

    def test_numpy_compatible_polygon_coordinates_are_converted(self) -> None:
        result = self.valid_result()
        result["rec_polys"] = ArrayLike(
            [
                ArrayLike([[1, 2], [11, 2], [11, 7], [1, 7]]),
                ArrayLike([[2, 10], [22, 10], [22, 16], [2, 16]]),
            ]
        )

        adapted = self.adapt(result)

        self.assertEqual(
            (Point(1.0, 2.0), Point(11.0, 2.0), Point(11.0, 7.0), Point(1.0, 7.0)),
            adapted.tokens[0].polygon,
        )

    def test_rectangular_box_fallback_creates_four_point_polygon(self) -> None:
        result = self.valid_result()
        result["rec_polys"] = [None, None]
        result["dt_polys"] = [None, None]

        adapted = self.adapt(result)

        self.assertEqual(
            (Point(1.0, 2.0), Point(11.0, 2.0), Point(11.0, 7.0), Point(1.0, 7.0)),
            adapted.tokens[0].polygon,
        )

    def test_missing_recognition_scores_remain_absent(self) -> None:
        result = self.valid_result()
        result.pop("rec_scores")

        adapted = self.adapt(result)

        self.assertTrue(all(token.raw_confidence is None for token in adapted.tokens))

    def test_non_finite_scores_and_geometry_are_rejected(self) -> None:
        for invalid in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(kind="score", value=invalid):
                result = self.valid_result()
                result["rec_scores"] = [invalid, 0.98]
                with self.assertRaises(OcrAdapterError):
                    self.adapt(result)
            with self.subTest(kind="geometry", value=invalid):
                result = self.valid_result()
                result["rec_polys"] = [
                    [[invalid, 2], [11, 2], [11, 7], [1, 7]],
                    [[2, 10], [22, 10], [22, 16], [2, 16]],
                ]
                with self.assertRaises(OcrAdapterError):
                    self.adapt(result)

    def test_empty_ocr_result_produces_empty_gate_free_package(self) -> None:
        adapted = self.adapt({"rec_texts": []})

        self.assertEqual((), adapted.tokens)
        self.assertFalse(hasattr(adapted, "gate_result"))

    def test_mismatched_ocr_array_lengths_are_rejected(self) -> None:
        keys = ("rec_scores", "rec_polys", "dt_polys", "rec_boxes")
        for key in keys:
            with self.subTest(key=key):
                result = self.valid_result()
                result[key] = list(result[key])[:1]  # type: ignore[arg-type]
                with self.assertRaises(OcrAdapterError):
                    self.adapt(result)

    def test_actual_source_image_hash_is_recorded_in_provenance(self) -> None:
        content = b"synthetic image bytes"
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "receipt.jpg"
            image_path.write_bytes(content)

            adapted = self.adapt(source_image_path=image_path)

        self.assertEqual("paddleocr-3.7-test", adapted.provenance.source_system)
        self.assertEqual(
            "memory://synthetic-image-001", adapted.provenance.source_reference
        )
        self.assertEqual(hashlib.sha256(content).hexdigest(), adapted.provenance.content_sha256)

    def test_mismatched_gate_result_is_rejected(self) -> None:
        adapted = self.adapt()

        with self.assertRaises(OcrAdapterError):
            attach_gate_result(adapted, self.gate_result("different-receipt"))

    def test_external_gate_result_is_attached_successfully(self) -> None:
        adapted = self.adapt()
        gate = self.gate_result()

        evidence = attach_gate_result(adapted, gate)

        self.assertIs(gate, evidence.gate_result)
        self.assertIs(adapted.tokens, evidence.tokens)
        self.assertEqual(adapted.provenance, evidence.provenance)

    def test_adapter_does_not_assign_source_sufficiency(self) -> None:
        adapted = self.adapt()

        self.assertFalse(hasattr(adapted, "gate_result"))
        with self.assertRaises(OcrAdapterError):
            attach_gate_result(adapted, None)  # type: ignore[arg-type]

    def test_empty_text_region_is_rejected_instead_of_dropped(self) -> None:
        for invalid_text in ("", "   "):
            with self.subTest(text=invalid_text):
                result = self.valid_result()
                result["rec_texts"] = [invalid_text, "TOTAL 23.90"]

                with self.assertRaises(OcrAdapterError):
                    self.adapt(result)


if __name__ == "__main__":
    unittest.main()
