"""Adapt PaddleOCR 3.x result dictionaries into Contract V0 source evidence.

This module deliberately stops at the source-evidence boundary. It neither
evaluates source sufficiency nor extracts receipt fields.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from pathlib import Path
from typing import Any

from pipeline.contracts import (
    OcrSourceToken,
    Point,
    ReceiptSourceEvidence,
    SourceEvidenceGateResult,
    SourceProcessingStatus,
    SourceProvenance,
)


class OcrAdapterError(ValueError):
    """Raised when PaddleOCR output cannot be represented without fabrication."""


@dataclass(frozen=True, slots=True)
class AdaptedOcrSource:
    """Stage-A gate-free OCR package awaiting an external gate result."""

    receipt_id: str
    image_id: str
    provenance: SourceProvenance
    processing_status: SourceProcessingStatus
    tokens: tuple[OcrSourceToken, ...]

    def __post_init__(self) -> None:
        if not self.receipt_id or not self.receipt_id.strip():
            raise OcrAdapterError("receipt_id must be non-empty.")
        if not self.image_id or not self.image_id.strip():
            raise OcrAdapterError("image_id must be non-empty.")
        token_ids = tuple(token.token_id for token in self.tokens)
        if len(token_ids) != len(set(token_ids)):
            raise OcrAdapterError("Adapted OCR token IDs must be unique.")
        if any(token.receipt_id != self.receipt_id for token in self.tokens):
            raise OcrAdapterError("Every adapted token must belong to the receipt.")


def adapt_paddleocr_result(
    result: Mapping[str, Any],
    *,
    receipt_id: str,
    image_id: str,
    source_system: str,
    source_reference: str,
    processing_status: SourceProcessingStatus,
    source_image_path: str | Path | None = None,
) -> AdaptedOcrSource:
    """Convert one PaddleOCR 3.x result into validated, gate-free source tokens.

    ``rec_texts`` is required. ``rec_scores`` may be absent or ``None``; in
    that case token confidence remains ``None``. Geometry is selected per
    region from ``rec_polys``, then ``dt_polys``, then ``rec_boxes``. Every
    supplied array must match the number of recognition texts.
    """

    if not isinstance(result, Mapping):
        raise OcrAdapterError("result must be a mapping with PaddleOCR result keys.")
    if "rec_texts" not in result:
        raise OcrAdapterError("PaddleOCR result is missing required rec_texts.")

    texts = _required_array(result["rec_texts"], "rec_texts")
    count = len(texts)
    scores = _optional_array(result, "rec_scores", count)
    rec_polys = _optional_array(result, "rec_polys", count)
    dt_polys = _optional_array(result, "dt_polys", count)
    rec_boxes = _optional_array(result, "rec_boxes", count)

    if count and rec_polys is None and dt_polys is None and rec_boxes is None:
        raise OcrAdapterError(
            "Recognized regions require rec_polys, dt_polys, or rec_boxes geometry."
        )

    provenance = SourceProvenance(
        source_system=source_system,
        source_reference=source_reference,
        content_sha256=_image_sha256(source_image_path)
        if source_image_path is not None
        else None,
    )

    tokens: list[OcrSourceToken] = []
    for index, text in enumerate(texts):
        if not isinstance(text, str):
            raise OcrAdapterError(f"rec_texts[{index}] must be a string.")
        if not text.strip():
            raise OcrAdapterError(
                f"rec_texts[{index}] must not be empty or whitespace-only."
            )

        confidence = None
        if scores is not None and scores[index] is not None:
            confidence = _finite_number(scores[index], f"rec_scores[{index}]")

        polygon = _region_polygon(
            index=index,
            rec_polys=rec_polys,
            dt_polys=dt_polys,
            rec_boxes=rec_boxes,
        )
        tokens.append(
            OcrSourceToken(
                receipt_id=receipt_id,
                token_id=_token_id(receipt_id, index),
                original_text=text,
                polygon=polygon,
                raw_confidence=confidence,
            )
        )

    return AdaptedOcrSource(
        receipt_id=receipt_id,
        image_id=image_id,
        provenance=provenance,
        processing_status=processing_status,
        tokens=tuple(tokens),
    )


def attach_gate_result(
    adapted: AdaptedOcrSource,
    gate_result: SourceEvidenceGateResult,
) -> ReceiptSourceEvidence:
    """Attach an externally recorded gate result to a Stage-A OCR package."""

    if not isinstance(adapted, AdaptedOcrSource):
        raise OcrAdapterError("adapted must be an AdaptedOcrSource.")
    if not isinstance(gate_result, SourceEvidenceGateResult):
        raise OcrAdapterError("An external SourceEvidenceGateResult is required.")
    if gate_result.receipt_id != adapted.receipt_id:
        raise OcrAdapterError(
            "Gate result receipt_id does not match the adapted OCR package."
        )

    return ReceiptSourceEvidence(
        receipt_id=adapted.receipt_id,
        image_id=adapted.image_id,
        provenance=adapted.provenance,
        processing_status=adapted.processing_status,
        tokens=adapted.tokens,
        gate_result=gate_result,
    )


def _token_id(receipt_id: str, index: int) -> str:
    return f"{receipt_id}:paddleocr:{index:06d}"


def _to_plain(value: Any) -> Any:
    """Convert NumPy-compatible array/scalar wrappers without importing NumPy."""

    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return tolist()
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    return value


def _required_array(value: Any, name: str) -> list[Any]:
    plain = _to_plain(value)
    if isinstance(plain, (str, bytes, bytearray)) or not isinstance(plain, Sequence):
        raise OcrAdapterError(f"{name} must be an array-like sequence.")
    return list(plain)


def _optional_array(
    result: Mapping[str, Any], name: str, expected_length: int
) -> list[Any] | None:
    if name not in result or result[name] is None:
        return None
    values = _required_array(result[name], name)
    if len(values) != expected_length:
        raise OcrAdapterError(
            f"{name} length {len(values)} does not match rec_texts length "
            f"{expected_length}."
        )
    return values


def _region_polygon(
    *,
    index: int,
    rec_polys: list[Any] | None,
    dt_polys: list[Any] | None,
    rec_boxes: list[Any] | None,
) -> tuple[Point, ...]:
    for name, polygons in (("rec_polys", rec_polys), ("dt_polys", dt_polys)):
        if polygons is None or _is_unavailable(polygons[index]):
            continue
        return _polygon(polygons[index], f"{name}[{index}]")

    if rec_boxes is not None and not _is_unavailable(rec_boxes[index]):
        return _box_polygon(rec_boxes[index], f"rec_boxes[{index}]")

    raise OcrAdapterError(f"OCR region {index} has no available geometry.")


def _is_unavailable(value: Any) -> bool:
    if value is None:
        return True
    plain = _to_plain(value)
    return (
        isinstance(plain, Sequence)
        and not isinstance(plain, (str, bytes, bytearray))
        and len(plain) == 0
    )


def _polygon(value: Any, name: str) -> tuple[Point, ...]:
    points = _required_array(value, name)
    if len(points) < 3:
        raise OcrAdapterError(f"{name} must contain at least three coordinate pairs.")

    converted: list[Point] = []
    for point_index, point in enumerate(points):
        pair = _required_array(point, f"{name}[{point_index}]")
        if len(pair) != 2:
            raise OcrAdapterError(
                f"{name}[{point_index}] must contain exactly two coordinates."
            )
        converted.append(
            Point(
                _finite_number(pair[0], f"{name}[{point_index}][0]"),
                _finite_number(pair[1], f"{name}[{point_index}][1]"),
            )
        )
    return tuple(converted)


def _box_polygon(value: Any, name: str) -> tuple[Point, ...]:
    box = _required_array(value, name)
    if len(box) != 4:
        raise OcrAdapterError(f"{name} must contain [x_min, y_min, x_max, y_max].")
    x_min, y_min, x_max, y_max = (
        _finite_number(coordinate, f"{name}[{index}]")
        for index, coordinate in enumerate(box)
    )
    if x_max <= x_min or y_max <= y_min:
        raise OcrAdapterError(f"{name} must have positive width and height.")
    return (
        Point(x_min, y_min),
        Point(x_max, y_min),
        Point(x_max, y_max),
        Point(x_min, y_max),
    )


def _finite_number(value: Any, name: str) -> float:
    plain = _to_plain(value)
    if isinstance(plain, bool):
        raise OcrAdapterError(f"{name} must be numeric, not boolean.")
    try:
        number = float(plain)
    except (TypeError, ValueError) as exc:
        raise OcrAdapterError(f"{name} must be numeric.") from exc
    if not isfinite(number):
        raise OcrAdapterError(f"{name} must be finite.")
    return number


def _image_sha256(path: str | Path) -> str:
    image_path = Path(path)
    if not image_path.is_file():
        raise OcrAdapterError(f"Source image does not exist or is not a file: {image_path}")
    digest = sha256()
    with image_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
