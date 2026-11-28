"""In-process handoff from an approved generated-image PaddleOCR producer."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from enum import Enum

from pipeline.backend_synthetic_coordinator_v0 import (
    SyntheticCoordinatorResultV0,
    coordinate_synthetic_receipt_v0,
)
from pipeline.contracts import SourceEvidenceGateResult, SourceProcessingStatus, SourceProvenance
from pipeline.gate_c_source_gate_v0 import GATE_C_SOURCE_GATE_V0, evaluate_gate_c_source_v0
from pipeline.ocr_adapter import AdaptedOcrSource, adapt_paddleocr_result
from pipeline.presentation_v1.synthetic_failure_projection_v0 import SyntheticFailureContextV0


class GeneratedPaddleOcrRefusalV0(Enum):
    INVALID_CONTEXT = "INVALID_CONTEXT"
    OCR_INPUT_REJECTED = "OCR_INPUT_REJECTED"
    GATE_CONTEXT_REJECTED = "GATE_CONTEXT_REJECTED"
    EVIDENCE_CHANGED = "EVIDENCE_CHANGED"


def process_generated_paddleocr_result_v0(
    *,
    result: Mapping[str, object],
    receipt_id: str,
    result_request_id: str,
    result_image_id: str,
    provenance: SourceProvenance,
    gate_result_id: str,
    context: SyntheticFailureContextV0,
    validate_source: Callable[[AdaptedOcrSource], None] | None = None,
    reserve_gate: Callable[[], None] | None = None,
    producer_id: str = "GATE_C_PADDLEOCR_B2_HANDOFF_V0",
) -> SyntheticCoordinatorResultV0 | GeneratedPaddleOcrRefusalV0:
    """Process one completed result from a trusted generated-image producer.

    The producer supplies the result, its already bound request and image IDs,
    and the original provenance. The caller independently retains the expected
    context and reserves the receipt and gate IDs for the Gate C policy.
    A result mapping alone cannot prove how it was produced. This entry point
    accepts approved generated inputs in FIXTURE mode and opens no image file
    or model. The returned trace is private in-memory evidence. Only the
    coordinator's validated bytes are suitable for a FIXTURE consumer.

    The supervised producer can check the adapted source before dispatch and
    reserve its single-use gate grant immediately before the existing policy.
    Both hooks must raise on refusal.
    """
    if (
        type(context) is not SyntheticFailureContextV0
        or type(context.consumer_mode) is not str
        or context.consumer_mode != "FIXTURE"
        or type(result_request_id) is not str
        or type(result_image_id) is not str
        or type(context.request_id) is not str
        or type(context.image_id) is not str
        or result_request_id != context.request_id
        or result_image_id != context.image_id
        or (validate_source is not None and not callable(validate_source))
        or (reserve_gate is not None and not callable(reserve_gate))
    ):
        return GeneratedPaddleOcrRefusalV0.INVALID_CONTEXT

    if type(provenance) is not SourceProvenance:
        return GeneratedPaddleOcrRefusalV0.OCR_INPUT_REJECTED
    try:
        source = adapt_paddleocr_result(
            result,
            receipt_id=receipt_id,
            image_id=result_image_id,
            source_system=provenance.source_system,
            source_reference=provenance.source_reference,
            processing_status=SourceProcessingStatus.OCR_COMPLETED,
        )
        # The producer already owns the provenance, including any input
        # digest. Preserve it without reading or rehashing an image path.
        source = replace(source, provenance=provenance)
        if validate_source is not None:
            validate_source(source)
    except Exception:
        return GeneratedPaddleOcrRefusalV0.OCR_INPUT_REJECTED

    gate_attempted = False
    gate_context_rejected = False
    gate_result = None

    def evaluate(adapted: AdaptedOcrSource) -> SourceEvidenceGateResult:
        nonlocal gate_attempted, gate_context_rejected, gate_result
        if (
            gate_attempted or adapted is not source
            or adapted.receipt_id != receipt_id or adapted.image_id != result_image_id
        ):
            gate_context_rejected = True
            raise ValueError("Generated OCR gate context changed.")
        gate_attempted = True
        if reserve_gate is not None:
            reserve_gate()
        gate_result = evaluate_gate_c_source_v0(
            source=adapted, gate_result_id=gate_result_id, policy=GATE_C_SOURCE_GATE_V0,
        )
        return gate_result

    composed = coordinate_synthetic_receipt_v0(
        adapted_source=source,
        gate_evaluator=evaluate,
        context=context,
        producer_id=producer_id,
    )
    if gate_context_rejected:
        return GeneratedPaddleOcrRefusalV0.GATE_CONTEXT_REJECTED
    if type(composed.result) is bytes and (
        gate_result is None
        or composed.trace.adapted_source is not source
        or composed.trace.gate_result is not gate_result
    ):
        return GeneratedPaddleOcrRefusalV0.EVIDENCE_CHANGED
    return composed
