# PantryProof PaddleOCR Adapter Version 0

Status: minimal source-evidence adapter for review. It does not extract receipt
fields or decide whether source evidence is sufficient.

## Supported input

`adapt_paddleocr_result()` accepts one PaddleOCR 3.x result mapping using the
same keys as `scripts/ocr_smoke_test.py`:

- `rec_texts` - required recognition strings in source order.
- `rec_scores` - optional raw recognition scores.
- `rec_polys` - preferred recognition polygons.
- `dt_polys` - detection polygon fallback.
- `rec_boxes` - rectangular `[x_min, y_min, x_max, y_max]` fallback.

Python sequences and array/scalar wrappers exposing `tolist()` or `item()` are
supported without introducing a NumPy dependency. Every supplied OCR array must
have exactly the same length as `rec_texts`; mismatches are rejected rather than
truncated.

## Stage A: gate-free adaptation

`adapt_paddleocr_result()` returns an immutable `AdaptedOcrSource`. It contains
receipt/image identity, provenance, caller-supplied processing status and
ordered `OcrSourceToken` records, but intentionally has no gate decision.

For each recognized region the adapter:

1. Preserves the exact OCR string and source order.
2. Assigns `"{receipt_id}:paddleocr:{zero-padded index}"` as the deterministic
   token ID.
3. Uses a nonempty `rec_polys` entry, otherwise a nonempty `dt_polys` entry.
4. Converts a valid rectangle into top-left, top-right, bottom-right and
   bottom-left points only when both polygon entries are unavailable.
5. Preserves a supplied finite recognition score as model-native raw
   confidence. It does not treat that score as calibrated extraction
   confidence.

If `source_image_path` identifies an available file, the adapter calculates its
SHA-256 from the file bytes. Without an image path, provenance retains no
content hash rather than fabricating one.

## Invalid and empty regions

- Missing `rec_scores` or a `None` score produces `raw_confidence=None`.
- An empty overall `rec_texts` array produces a valid package with zero tokens;
  it does not imply source sufficiency.
- Empty or whitespace-only recognized strings are rejected rather than
  silently removed.
- Missing geometry for a recognized region is rejected.
- Malformed selected geometry is rejected rather than silently replaced by lower-priority geometry. Unused lower-priority geometry entries are not validated beyond array-length checks.
- Non-numeric or non-finite coordinates and non-finite scores are rejected.
- Rectangles with non-positive width or height are rejected.

## Stage B: external gate attachment

`attach_gate_result()` requires a caller-supplied `SourceEvidenceGateResult`
whose receipt ID matches the Stage-A package. It then creates the existing
`ReceiptSourceEvidence` record while preserving tokens, provenance and
processing status.

The adapter never runs `sourceEvidenceSufficient()`, never creates a gate
result, and never assumes `OCR_COMPLETED` means `SUFFICIENT`. Exactly-once gate
execution remains the responsibility of later orchestration.

## Version 0 boundaries

This adapter does not implement structured field extraction, B1/B2/B3,
correction candidates, retailer matching, correction scoring, calibration,
selective verification, review, persistence, evaluation or UI behavior.
