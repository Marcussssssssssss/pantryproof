"""T09 synchronous processor over an injected, approved OCR runtime.

The transport owns full HTTP and PNG admission. The injected provider owns native
lifecycle and must safely decode the original admitted bytes.
Cooperative checkpointing never asserts that native execution has terminated.
"""

from collections.abc import Callable
from dataclasses import dataclass, replace
from hashlib import sha256
from math import isfinite
from struct import unpack_from
from time import monotonic
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from pipeline.contracts import SourceEvidenceDecision, SourceProcessingStatus
from pipeline.gate_c_live_source_gate_v0 import (
    GROCERY_LIVE_GATE_V1, LiveSourceGateRefusal, MAX_REGIONS, MAX_VERTICES,
    check_image_dimensions_v0, evaluate_live_source_gate_v0,
    require_approved_live_policy_v0, validate_ocr_texts_v0,
)
from pipeline.layout_b2 import B2ExtractionResult, extract_b2
from pipeline.ocr_adapter import AdaptedOcrSource, adapt_paddleocr_result, attach_gate_result
from pipeline.presentation_v1.b2_synthetic_projection_v0 import _protocol_id
from pipeline.presentation_v1.review_conformance import REVIEW_SCHEMA
from pipeline.presentation_v1.local_image_projection_v0 import (
    LOCAL_IMAGE_SOURCE_SYSTEM, LiveGateApprovalV0, LocalImageFailureV0,
    LocalImagePresentationContextV0, RetainedLiveGateV0, RetainedLocalImageAttemptV0,
    project_retained_local_image_presentation_v1,
)
from pipeline.real_receipt_http_service_v1 import (
    CONTENT_TYPE, MAX_IMAGE_BYTES, MAX_IMAGE_DIMENSION,
    ProcessingContext, ProcessingRefusal, ReceiptProcessor, ReceiptRequest,
)

if TYPE_CHECKING:
    from pipeline.operational_receipt_method_v1 import OperationalReceiptMethodV1
    from pipeline.proposed.purchase_date_correction_v0 import PurchaseDateCorrectionResultV0


_PNG_IHDR_PREFIX = b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR"
_GEOMETRY_KEYS = ("rec_polys", "dt_polys", "rec_boxes")
_RECOGNITION_KEYS = frozenset(("rec_texts", "rec_scores", *_GEOMETRY_KEYS))
_T09_REFUSALS = {
    "PROCESSOR_UNAVAILABLE": ProcessingRefusal.UNAVAILABLE,
    "DEADLINE_EXCEEDED": ProcessingRefusal.DEADLINE_EXCEEDED,
    "CANCELLED": ProcessingRefusal.CANCELLED,
}


class LocalImageProcessingRefusal(RuntimeError):
    """One safe internal code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class AdmittedImageRequestV0(Protocol):
    request_id: str
    image_id: str
    content_type: str
    encoded_image: bytes


class CancellationSignalV0(Protocol):
    def is_set(self) -> bool: ...

    def wait(self, timeout: float | None = None) -> bool: ...


@dataclass(frozen=True, slots=True, repr=False)
class _T09CancellationSignal:
    context: ProcessingContext

    def is_set(self) -> bool:
        return self.context.cancelled

    def wait(self, timeout: float | None = None) -> bool:
        return self.context.wait_for_cancellation(timeout)


@dataclass(frozen=True, slots=True, repr=False)
class LocalImageProcessingContextV0:
    deadline: float  # Absolute seconds in time.monotonic() units.
    cancel_event: CancellationSignalV0


@dataclass(frozen=True, slots=True, repr=False)
class LocalImageOcrRequestV0:
    presentation: LocalImagePresentationContextV0
    content_type: str
    encoded_image: bytes
    image_sha256: str
    gate_result_id: str


@dataclass(frozen=True, slots=True, repr=False)
class RetainedLocalImageRecognitionV0:
    """Provider completion associated with its exact input and recognized bytes.

    Dimensions describe the OCR coordinate frame of the admitted image. Pass
    ordinary Python OCR arrays. Empty rec_texts is a successful completion,
    whereas native execution failures must be raised by the provider.
    """

    request: LocalImageOcrRequestV0
    image_sha256: str
    width: int
    height: int
    payload: dict


class LocalImageOcrProviderV0(Protocol):
    def __call__(
        self, request: LocalImageOcrRequestV0, processing_context: LocalImageProcessingContextV0,
    ) -> RetainedLocalImageRecognitionV0: ...


@dataclass(frozen=True, slots=True, repr=False)
class LocalImageRuntimeApprovalV0:
    provider: LocalImageOcrProviderV0
    source_system: str


# No installed provider or runtime authority. A constructed approval object
# never activates processing. The approved bootstrap must install exact pins.
_APPROVED_RUNTIME: LocalImageRuntimeApprovalV0 | None = None
_APPROVED_PROTOTYPE_RUNTIME: LocalImageRuntimeApprovalV0 | None = None


def _checkpoint(context: LocalImageProcessingContextV0) -> None:
    try:
        cancelled = context.cancel_event.is_set()
    except Exception:
        cancelled = None
    if type(cancelled) is not bool:
        raise LocalImageProcessingRefusal("INVALID_PROCESSING_CONTEXT")
    # T09's public cancellation state includes expiry. Keep a distinct
    # deadline refusal even if expiry occurs while reading that state.
    if monotonic() >= context.deadline:
        raise LocalImageProcessingRefusal("DEADLINE_EXCEEDED")
    if cancelled:
        raise LocalImageProcessingRefusal("CANCELLED")


def _capture_processing_context(context) -> LocalImageProcessingContextV0:
    try:
        deadline, cancel_event = context.deadline, context.cancel_event
        if type(deadline) in (int, float) and isfinite(deadline) and callable(cancel_event.is_set):
            return LocalImageProcessingContextV0(deadline, cancel_event)
    except (AttributeError, OverflowError):
        pass
    raise LocalImageProcessingRefusal("INVALID_PROCESSING_CONTEXT") from None


def _within_admitted_png_dimensions(image: bytes) -> bool:
    """Check the IHDR frame only. T09 checks the complete PNG and its pixels."""
    if len(image) < 24 or not image.startswith(_PNG_IHDR_PREFIX):
        return False
    width, height = unpack_from(">II", image, 16)
    return 1 <= width <= MAX_IMAGE_DIMENSION and 1 <= height <= MAX_IMAGE_DIMENSION


def _reserve(request: AdmittedImageRequestV0, policy: LiveGateApprovalV0) -> LocalImageOcrRequestV0:
    try:
        request_id, image_id = request.request_id, request.image_id
        _protocol_id(request_id)
        _protocol_id(image_id)
        image, content_type = request.encoded_image, request.content_type
        if (
            len(request_id) <= 96 and len(image_id) <= 96
            and type(image) is bytes and 0 < len(image) <= MAX_IMAGE_BYTES
            and type(content_type) is str and content_type == CONTENT_TYPE
            and _within_admitted_png_dimensions(image)
        ):
            presentation = LocalImagePresentationContextV0(
                request_id, image_id, f"rct-{uuid4().hex}", uuid4().hex, policy,
            )
            return LocalImageOcrRequestV0(
                presentation, content_type, image, sha256(image).hexdigest(), f"gat-{uuid4().hex}",
            )
    except (AttributeError, ValueError, TypeError):
        pass
    raise LocalImageProcessingRefusal("INVALID_ADMITTED_REQUEST") from None


def _array(value, maximum: int) -> tuple:
    if type(value) not in (list, tuple) or len(value) > maximum:
        raise ValueError("Malformed recognition array.")
    return tuple(value)


def _number(value, maximum: int) -> None:
    if type(value) not in (int, float) or not 0 <= value <= maximum or not isfinite(value):
        raise ValueError("Malformed recognition number.")


def _geometry(value, key: str, width: int, height: int):
    if value is None:
        return None
    coordinates = _array(value, 4 if key == "rec_boxes" else MAX_VERTICES)
    if not coordinates:
        return coordinates  # The adapter may use another recognized geometry source.
    if key == "rec_boxes":
        if len(coordinates) != 4:
            raise ValueError("Malformed recognition box.")
        for index, coordinate in enumerate(coordinates):
            _number(coordinate, width if index % 2 == 0 else height)
        return coordinates
    if len(coordinates) < 3:
        raise ValueError("Malformed recognition polygon.")
    points = []
    for value in coordinates:
        point = _array(value, 2)
        if len(point) != 2:
            raise ValueError("Malformed recognition point.")
        _number(point[0], width)
        _number(point[1], height)
        points.append(point)
    return tuple(points)


def _snapshot_payload(recognition: RetainedLocalImageRecognitionV0) -> dict:
    width, height = recognition.width, recognition.height
    check_image_dimensions_v0(width, height)
    payload = recognition.payload
    if (
        type(payload) is not dict or len(payload) > len(_RECOGNITION_KEYS)
        or any(type(key) is not str or key not in _RECOGNITION_KEYS for key in payload)
        or "rec_texts" not in payload
    ):
        raise ValueError("Malformed recognition payload.")
    texts = _array(payload["rec_texts"], MAX_REGIONS)
    validate_ocr_texts_v0(texts)
    result = {"rec_texts": texts}
    for key in ("rec_scores", *_GEOMETRY_KEYS):
        value = payload.get(key)
        if value is None:
            continue
        entries = _array(value, len(texts))
        if len(entries) != len(texts):
            raise ValueError("Recognition array lengths disagree.")
        if key == "rec_scores":
            for score in entries:
                if score is not None:
                    _number(score, 1)
            result[key] = entries
        else:
            result[key] = tuple(_geometry(entry, key, width, height) for entry in entries)
    return result


def _recognize(provider, request, context) -> RetainedLocalImageRecognitionV0:
    try:
        recognition = provider(request, context)
    except Exception:
        recognition = None
    _checkpoint(context)
    if type(recognition) is not RetainedLocalImageRecognitionV0:
        raise ValueError("OCR failed or returned no completed recognition.")
    if (
        recognition.request is not request
        or type(recognition.image_sha256) is not str
        or recognition.image_sha256 != request.image_sha256
    ):
        raise LocalImageProcessingRefusal("OCR_SOURCE_BINDING_MISMATCH")
    return recognition


def _require_b2_source(result: B2ExtractionResult, evidence) -> None:
    if type(result) is not B2ExtractionResult:
        raise LocalImageProcessingRefusal("B2_SOURCE_BINDING_MISMATCH")
    if evidence.gate_result.decision is SourceEvidenceDecision.SUFFICIENT:
        valid = result.receipt_output is not None and result.receipt_output.source_evidence is evidence
    else:
        fallback = result.pre_resolution_disposition
        valid = result.receipt_output is None and fallback is not None and fallback.gate_result is evidence.gate_result
    if not valid:
        raise LocalImageProcessingRefusal("B2_SOURCE_BINDING_MISMATCH")


def _terminal_failure(context, attempt, failure, budget,
                      project=project_retained_local_image_presentation_v1) -> bytes:
    _checkpoint(budget)
    if attempt.gate is not None and attempt.gate.result.decision is SourceEvidenceDecision.INSUFFICIENT:
        # There is no frozen technical-failure envelope following insufficiency.
        raise LocalImageProcessingRefusal("POST_INSUFFICIENT_FAILURE")
    try:
        payload = project(
            context=context, attempt=replace(attempt, failure=failure),
        )
    except Exception:
        payload = None
    _checkpoint(budget)
    if payload is None:
        raise LocalImageProcessingRefusal("TERMINAL_FAILURE_UNREPRESENTABLE") from None
    return payload


@dataclass(frozen=True, slots=True, repr=False)
class LocalImageReceiptProcessorV0:
    """Run the receipt stages using the internal processing context."""

    gate_policy: LiveGateApprovalV0 | None = None
    runtime: LocalImageRuntimeApprovalV0 | None = None
    enable_purchase_date_correction: bool = False
    correction_observer: Callable[["PurchaseDateCorrectionResultV0"], None] | None = None
    proposed_method: "OperationalReceiptMethodV1 | None" = None
    attempt_observer: Callable[[RetainedLocalImageAttemptV0], None] | None = None

    def __post_init__(self) -> None:
        if self.proposed_method is not None and self.enable_purchase_date_correction:
            raise ValueError("Select one receipt correction method.")

    def __call__(self, request: AdmittedImageRequestV0, processing_context) -> bytes:
        budget = _capture_processing_context(processing_context)
        _checkpoint(budget)
        runtime = self.runtime
        prototype = self.gate_policy is GROCERY_LIVE_GATE_V1
        approved_runtime = _APPROVED_PROTOTYPE_RUNTIME if prototype else _APPROVED_RUNTIME
        if (
            type(runtime) is not LocalImageRuntimeApprovalV0 or runtime is not approved_runtime
            or runtime.source_system != LOCAL_IMAGE_SOURCE_SYSTEM or not callable(runtime.provider)
            or (prototype and self.proposed_method is None)
        ):
            raise LocalImageProcessingRefusal("PROCESSOR_UNAVAILABLE")
        try:
            require_approved_live_policy_v0(self.gate_policy)
        except LiveSourceGateRefusal:
            raise LocalImageProcessingRefusal("PROCESSOR_UNAVAILABLE") from None

        reserved = _reserve(request, self.gate_policy)
        _checkpoint(budget)
        context = reserved.presentation
        dimensions = unpack_from(">II", reserved.encoded_image, 16)
        project = project_retained_local_image_presentation_v1
        if getattr(request, "response_schema", None) == REVIEW_SCHEMA:
            if self.proposed_method is None or not prototype:
                raise LocalImageProcessingRefusal("PROCESSOR_UNAVAILABLE")
            from functools import partial
            from pipeline.presentation_v1.review_projection import project_retained_local_image_review_v1

            project = partial(project_retained_local_image_review_v1,
                              method=self.proposed_method, expected_dimensions=dimensions)
        attempt = RetainedLocalImageAttemptV0(context.request_id, context.image_id)
        failure = LocalImageFailureV0.OCR_ENGINE_FAILURE
        try:
            recognition = _recognize(runtime.provider, reserved, budget)
            if prototype and (recognition.width, recognition.height) != dimensions:
                raise LocalImageProcessingRefusal("OCR_SOURCE_BINDING_MISMATCH")
            raw = _snapshot_payload(recognition)
            _checkpoint(budget)
            adapted = adapt_paddleocr_result(
                raw, receipt_id=context.receipt_id, image_id=context.image_id,
                source_system=LOCAL_IMAGE_SOURCE_SYSTEM,
                source_reference=context.source_reference,
                processing_status=SourceProcessingStatus.OCR_COMPLETED,
            )
            if (
                type(adapted) is not AdaptedOcrSource
                or adapted.receipt_id != context.receipt_id or adapted.image_id != context.image_id
                or adapted.provenance.source_system != LOCAL_IMAGE_SOURCE_SYSTEM
                or adapted.provenance.source_reference != context.source_reference
                or adapted.processing_status is not SourceProcessingStatus.OCR_COMPLETED
            ):
                raise LocalImageProcessingRefusal("ADAPTED_SOURCE_BINDING_MISMATCH")
            attempt = replace(attempt, adapted_source=adapted,
                              image_dimensions=dimensions if prototype else None)
            _checkpoint(budget)

            failure = LocalImageFailureV0.SOURCE_GATE_EXECUTION_FAILURE
            gate = evaluate_live_source_gate_v0(
                context=context, source=adapted, gate_result_id=reserved.gate_result_id,
                image_width=recognition.width, image_height=recognition.height,
            )
            if (
                type(gate) is not RetainedLiveGateV0 or gate.adapted_source is not adapted
                or gate.policy is not self.gate_policy or gate.result.receipt_id != context.receipt_id
                or gate.result.gate_result_id != reserved.gate_result_id
            ):
                raise LocalImageProcessingRefusal("GATE_SOURCE_BINDING_MISMATCH")
            _checkpoint(budget)

            try:
                evidence = attach_gate_result(adapted, gate.result)
            except Exception:
                evidence = None
            if (
                evidence is None or evidence.gate_result is not gate.result
                or evidence.tokens is not adapted.tokens or evidence.provenance is not adapted.provenance
                or evidence.receipt_id != adapted.receipt_id or evidence.image_id != adapted.image_id
                or evidence.processing_status is not adapted.processing_status
            ):
                raise LocalImageProcessingRefusal("EVIDENCE_ATTACHMENT_FAILED")
            attempt = replace(attempt, gate=gate, source_evidence=evidence)
            _checkpoint(budget)

            failure = LocalImageFailureV0.EXTRACTION_ENGINE_FAILURE
            b2_result = extract_b2(evidence)
            _require_b2_source(b2_result, evidence)
            attempt = replace(attempt, b2_result=b2_result)
            _checkpoint(budget)

            failure = LocalImageFailureV0.PRESENTATION_PROJECTION_FAILURE
            if b2_result.receipt_output is not None:
                if self.proposed_method is not None:
                    from pipeline.proposed.receipt_research_v1 import (
                        ProposedReceiptResearchResult, ResearchMethodState, run_proposed_receipt_v1,
                    )

                    method = self.proposed_method
                    attempt = replace(attempt, proposed_failure="PROPOSED_METHOD_FAILURE")
                    proposed = run_proposed_receipt_v1(
                        b2_result, resources=method.resources, region=method.region,
                        correction_config=method.correction_config, verification=method.verification,
                    )
                    expected = (ResearchMethodState.NOT_READY if method.verification is None
                                else ResearchMethodState.POLICY_APPLIED)
                    if type(proposed) is not ProposedReceiptResearchResult or proposed.state is not expected:
                        raise ValueError("Unexpected proposed receipt output.")
                    attempt = replace(attempt, proposed=proposed, proposed_failure=None)
                    _checkpoint(budget)
                elif self.enable_purchase_date_correction:
                    from pipeline.proposed.purchase_date_correction_v0 import correct_purchase_date_v0

                    attempt = replace(attempt, correction=correct_purchase_date_v0(b2_result))
                    _checkpoint(budget)

            payload = project(context=context, attempt=attempt)
            _checkpoint(budget)
            if attempt.correction is not None and self.correction_observer is not None:
                self.correction_observer(attempt.correction)
                _checkpoint(budget)
            if self.attempt_observer is not None:
                self.attempt_observer(attempt)
                _checkpoint(budget)
            return payload
        except LocalImageProcessingRefusal as refusal:
            if self.attempt_observer is not None:
                self.attempt_observer(replace(attempt, refusal_code=refusal.code))
            raise
        except Exception:
            pass
        if self.attempt_observer is not None:
            self.attempt_observer(replace(attempt, failure=failure))
        return _terminal_failure(context, attempt, failure, budget, project)


def as_t09_receipt_processor_v0(processor: LocalImageReceiptProcessorV0) -> ReceiptProcessor:
    """Adapt the core to T09's public request, processing context and refusals."""

    def process(request: ReceiptRequest, context: ProcessingContext, /) -> bytes | ProcessingRefusal:
        budget = LocalImageProcessingContextV0(context.deadline, _T09CancellationSignal(context))
        try:
            payload = processor(request, budget)
            _checkpoint(budget)
        except LocalImageProcessingRefusal as refusal:
            return _T09_REFUSALS.get(refusal.code, ProcessingRefusal.FAILED)
        return payload

    return process
