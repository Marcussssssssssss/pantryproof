"""Source-bound native OCR adapter for T10. An executor must be supplied separately."""

from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
from io import BytesIO
from threading import Lock
from typing import Protocol

from PIL import Image

from pipeline.backend_local_image_receipt_v0 import (
    LocalImageOcrRequestV0,
    LocalImageProcessingContextV0,
    LocalImageProcessingRefusal,
    RetainedLocalImageRecognitionV0,
    _capture_processing_context,
    _checkpoint,
    _snapshot_payload,
)
from pipeline.presentation_v1.conformance import _protocol_id
from pipeline.presentation_v1.local_image_projection_v0 import LocalImagePresentationContextV0
from pipeline.real_receipt_http_service_v1 import CONTENT_TYPE, MAX_IMAGE_BYTES, _png_for_decoding


@dataclass(frozen=True, slots=True, repr=False)
class NativeLocalImageBindingV0:
    """Correlation fields for the admitted PNG and the exact raster used for OCR."""

    attempt_id: str
    request_id: str
    image_id: str
    encoded_sha256: str
    bgr8_sha256: str
    width: int
    height: int


@dataclass(frozen=True, slots=True, repr=False)
class NativeLocalImageInputV0:
    """Top-down, tightly packed BGR8 with row stride 3 * width, in pixel coordinates."""

    binding: NativeLocalImageBindingV0
    packed_bgr8: bytes


class NativeLocalImageStatusV0(Enum):
    COMPLETED = "COMPLETED"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True, repr=False)
class NativeLocalImageCompletionV0:
    """Terminal observation issued by the trusted supervisor.

    native_stopped confirms that no native work was started or that all work
    exited. cleanup_confirmed accounts for handles, IPC, buffers and scratch.
    Both facts must come from host-side observation rather than worker output.
    Only COMPLETED carries a plain PaddleOCR recognition dict. A completed
    empty rec_texts array records a genuine zero-token result.

    The T10 payload has required rec_texts and optional rec_scores,
    rec_polys, dt_polys and rec_boxes. Supply aligned arrays of plain values
    within T10's text, score, region and coordinate limits.
    """

    binding: NativeLocalImageBindingV0
    status: NativeLocalImageStatusV0
    native_stopped: bool
    cleanup_confirmed: bool
    payload: dict | None = None


class NativeLocalImageExecutorV0(Protocol):
    """Run one authorized native attempt and return a source-bound terminal observation.

    Verify length and the BGR8 digest before inference. Bind worker frames to
    this attempt, verify which pixels the worker consumed, and return the
    observed binding. Preserve text, scores and geometry in the input frame.
    Convert native containers to plain values using bounded IPC. Keep the
    pixels and recognition in memory for the attempt and release them on return.

    Use the T10 absolute monotonic deadline and cancellation signal from before
    startup through inference and supervision. Reserve time for cancellation,
    termination and cleanup within the deadline. If this cannot be confirmed,
    refuse, quarantine the execution boundary and keep supervising any
    outstanding native work. A Python return or exception is not proof of exit.
    """

    def __call__(
        self,
        frame: NativeLocalImageInputV0,
        processing_context: LocalImageProcessingContextV0,
        /,
    ) -> NativeLocalImageCompletionV0: ...


def _prepare_frame(
    request: LocalImageOcrRequestV0, context: LocalImageProcessingContextV0
) -> tuple[NativeLocalImageInputV0, bytes, LocalImagePresentationContextV0]:
    if type(request) is not LocalImageOcrRequestV0:
        raise LocalImageProcessingRefusal("INVALID_ADMITTED_REQUEST")
    presentation = request.presentation
    encoded = request.encoded_image
    if (
        type(presentation) is not LocalImagePresentationContextV0
        or type(request.content_type) is not str or request.content_type != CONTENT_TYPE
        or type(encoded) is not bytes or not 0 < len(encoded) <= MAX_IMAGE_BYTES
    ):
        raise LocalImageProcessingRefusal("INVALID_ADMITTED_REQUEST")

    request_id, image_id, attempt_id = (
        presentation.request_id, presentation.image_id, request.gate_result_id
    )
    try:
        for value in (request_id, image_id, attempt_id):
            if type(value) is not str or len(value) > 96:
                raise ValueError
            _protocol_id(value, "$context.sourceId")
    except ValueError:
        raise LocalImageProcessingRefusal("INVALID_ADMITTED_REQUEST") from None

    encoded_digest = sha256(encoded).hexdigest()
    if type(request.image_sha256) is not str or request.image_sha256 != encoded_digest:
        raise LocalImageProcessingRefusal("OCR_SOURCE_BINDING_MISMATCH")

    try:
        # Reuse T09's PNG bounds and strip non-pixel metadata before decoding.
        with BytesIO(_png_for_decoding(encoded, context.deadline)) as stream:
            with Image.open(stream, formats=("PNG",)) as image:
                width, height = image.size
                # Keep the encoded coordinate frame and composite transparency on white.
                with image.convert("RGBA") as rgba, rgba.getchannel("A") as alpha:
                    with Image.new("RGB", image.size, "white") as rgb:
                        rgb.paste(rgba, (0, 0), alpha)
                        pixels = rgb.tobytes("raw", "BGR")
    except Exception:
        _checkpoint(context)
        raise LocalImageProcessingRefusal("INVALID_ADMITTED_IMAGE") from None
    _checkpoint(context)
    if len(pixels) != width * height * 3:
        raise LocalImageProcessingRefusal("INVALID_ADMITTED_IMAGE")

    frame = NativeLocalImageInputV0(
        NativeLocalImageBindingV0(
            attempt_id, request_id, image_id, encoded_digest, sha256(pixels).hexdigest(),
            width, height,
        ),
        pixels,
    )
    return frame, encoded, presentation


def _binding_matches(actual: object, expected: NativeLocalImageBindingV0) -> bool:
    return (
        type(actual) is NativeLocalImageBindingV0
        and type(actual.attempt_id) is str and actual.attempt_id == expected.attempt_id
        and type(actual.request_id) is str and actual.request_id == expected.request_id
        and type(actual.image_id) is str and actual.image_id == expected.image_id
        and type(actual.encoded_sha256) is str and actual.encoded_sha256 == expected.encoded_sha256
        and type(actual.bgr8_sha256) is str and actual.bgr8_sha256 == expected.bgr8_sha256
        and type(actual.width) is int and actual.width == expected.width
        and type(actual.height) is int and actual.height == expected.height
    )


class NativeLocalImageProviderV0:
    """T10 provider with one injected native executor and no default runtime."""

    def __init__(self, executor: NativeLocalImageExecutorV0 | None = None) -> None:
        if executor is not None and not callable(executor):
            raise TypeError("The native executor must be callable.")
        self._executor = executor
        self._active = Lock()
        self._quarantined = False

    @property
    def quarantined(self) -> bool:
        return self._quarantined and not self._active.locked()

    def __call__(
        self,
        request: LocalImageOcrRequestV0,
        processing_context: LocalImageProcessingContextV0,
    ) -> RetainedLocalImageRecognitionV0:
        executor = self._executor
        if executor is None:
            raise LocalImageProcessingRefusal("PROCESSOR_UNAVAILABLE")
        context = _capture_processing_context(processing_context)
        _checkpoint(context)
        if not self._active.acquire(blocking=False):
            raise LocalImageProcessingRefusal("NATIVE_EXECUTOR_BUSY")
        try:
            if self._quarantined:
                raise LocalImageProcessingRefusal("PROCESSOR_UNAVAILABLE")
            frame, original_png, presentation = _prepare_frame(request, context)
            expected = frame.binding
            _checkpoint(context)

            # An invocation that fails to establish its own clean exit closes admission.
            self._quarantined = True
            try:
                completion = executor(replace(frame, binding=replace(expected)), replace(context))
            except Exception:
                _checkpoint(context)
                raise LocalImageProcessingRefusal("NATIVE_TEARDOWN_UNCONFIRMED") from None

            if type(completion) is not NativeLocalImageCompletionV0:
                _checkpoint(context)
                raise LocalImageProcessingRefusal("NATIVE_TEARDOWN_UNCONFIRMED")
            if not _binding_matches(completion.binding, expected):
                _checkpoint(context)
                raise LocalImageProcessingRefusal("OCR_SOURCE_BINDING_MISMATCH")
            if completion.native_stopped is not True or completion.cleanup_confirmed is not True:
                _checkpoint(context)
                raise LocalImageProcessingRefusal("NATIVE_TEARDOWN_UNCONFIRMED")
            self._quarantined = False
            _checkpoint(context)

            if type(completion.status) is not NativeLocalImageStatusV0:
                raise LocalImageProcessingRefusal("INVALID_NATIVE_COMPLETION")
            if completion.status is not NativeLocalImageStatusV0.COMPLETED:
                if completion.payload is not None:
                    raise LocalImageProcessingRefusal("INVALID_NATIVE_COMPLETION")
                code = (
                    "PROCESSOR_UNAVAILABLE"
                    if completion.status is NativeLocalImageStatusV0.UNAVAILABLE
                    else "OCR_ENGINE_FAILURE"
                )
                raise LocalImageProcessingRefusal(code)
            if (
                request.presentation is not presentation or request.encoded_image is not original_png
                or presentation.request_id != expected.request_id
                or presentation.image_id != expected.image_id
                or request.gate_result_id != expected.attempt_id
                or request.image_sha256 != expected.encoded_sha256
                or request.content_type != CONTENT_TYPE
            ):
                raise LocalImageProcessingRefusal("OCR_SOURCE_BINDING_MISMATCH")

            if type(completion.payload) is not dict:
                raise LocalImageProcessingRefusal("INVALID_RECOGNITION")
            recognition = RetainedLocalImageRecognitionV0(
                request, expected.encoded_sha256, expected.width, expected.height, completion.payload
            )
            try:
                payload = _snapshot_payload(recognition)
            except Exception:
                _checkpoint(context)
                raise LocalImageProcessingRefusal("INVALID_RECOGNITION") from None
            _checkpoint(context)
            return replace(recognition, payload=payload)
        finally:
            self._active.release()
