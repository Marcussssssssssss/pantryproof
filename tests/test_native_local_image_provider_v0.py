"""Source-only T12 test definitions with generated inputs and non-native executors."""

from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from threading import Event
from time import monotonic

from PIL import Image
from PIL.PngImagePlugin import PngInfo
import pytest

from pipeline import backend_local_image_receipt_v0 as t10
from pipeline import real_receipt_http_service_v1 as t09
from pipeline.native_local_image_provider_v0 import (
    NativeLocalImageCompletionV0,
    NativeLocalImageProviderV0,
    NativeLocalImageStatusV0,
)
from pipeline.presentation_v1.local_image_projection_v0 import LocalImagePresentationContextV0


def _png(size=(2, 1)) -> bytes:
    metadata = PngInfo()
    metadata.add_text("Comment", "generated metadata for the admission test")
    with BytesIO() as stream, Image.new("RGBA", size, (33, 55, 77, 0)) as image:
        image.putpixel((0, 0), (10, 20, 30, 255))
        image.save(stream, format="PNG", pnginfo=metadata)
        return stream.getvalue()


def _request(encoded=None) -> t10.LocalImageOcrRequestV0:
    if encoded is None:
        encoded = _png()
    presentation = LocalImagePresentationContextV0("req-t12", "img-t12", "rct-t12", "alias-t12")
    return t10.LocalImageOcrRequestV0(
        presentation, "image/png", encoded, sha256(encoded).hexdigest(), "gat-t12"
    )


def _context() -> t10.LocalImageProcessingContextV0:
    return t10.LocalImageProcessingContextV0(monotonic() + 60, Event())


def _complete(frame, payload) -> NativeLocalImageCompletionV0:
    return NativeLocalImageCompletionV0(
        frame.binding, NativeLocalImageStatusV0.COMPLETED,
        native_stopped=True, cleanup_confirmed=True, payload=payload,
    )


def _unexpected_executor(frame, context):
    pytest.fail("This request must be refused before calling the executor.")


def _refuses(code, provider, request, context):
    with pytest.raises(t10.LocalImageProcessingRefusal) as failure:
        provider(request, context)
    assert failure.value.code == code


def test_default_provider_is_unavailable():
    _refuses("PROCESSOR_UNAVAILABLE", NativeLocalImageProviderV0(), _request(), _context())


def test_t10_and_t09_bridge_stay_unavailable_without_operational_pins():
    request = _request()
    admitted = t09.ReceiptRequest(
        request.presentation.request_id, request.presentation.image_id,
        request.content_type, request.encoded_image,
    )
    processor = t10.as_t09_receipt_processor_v0(t10.LocalImageReceiptProcessorV0())
    assert processor(admitted, t09.ProcessingContext(monotonic() + 60)) is t09.ProcessingRefusal.UNAVAILABLE


def test_exact_png_and_raster_binding_through_the_t10_recognition_seam():
    request = _request()
    context = _context()
    original_png = request.encoded_image
    expected_pixels = bytes((30, 20, 10, 255, 255, 255))
    evidence = {
        "rec_texts": ["  ORIGINAL  "],
        "rec_scores": [0.82],
        "rec_polys": [[[0, 0], [2, 0], [2, 1], [0, 1]]],
    }
    calls = []

    def executor(frame, budget):
        calls.append(frame.binding)
        binding = frame.binding
        assert (binding.request_id, binding.image_id) == ("req-t12", "img-t12")
        assert binding.attempt_id == request.gate_result_id
        assert type(frame.packed_bgr8) is bytes and frame.packed_bgr8 == expected_pixels
        assert (binding.width, binding.height) == (2, 1)
        assert binding.encoded_sha256 == sha256(original_png).hexdigest()
        assert binding.bgr8_sha256 == sha256(expected_pixels).hexdigest()
        assert budget.deadline == context.deadline and budget.cancel_event is context.cancel_event
        return _complete(frame, evidence)

    provider: t10.LocalImageOcrProviderV0 = NativeLocalImageProviderV0(executor)
    retained = t10._recognize(provider, request, context)
    evidence["rec_texts"][0] = "changed after completion"
    evidence["rec_polys"][0][0][0] = 1

    assert len(calls) == 1
    assert type(retained) is t10.RetainedLocalImageRecognitionV0 and retained.request is request
    assert retained.request.encoded_image is original_png
    assert retained.image_sha256 == sha256(original_png).hexdigest()
    assert (retained.width, retained.height) == (2, 1)
    assert t10._snapshot_payload(retained) == {
        "rec_texts": ("  ORIGINAL  ",),
        "rec_scores": (0.82,),
        "rec_polys": (((0, 0), (2, 0), (2, 1), (0, 1)),),
    }


def test_input_digest_mismatch_is_refused_before_dispatch():
    request = replace(_request(), image_sha256="0" * 64)
    _refuses(
        "OCR_SOURCE_BINDING_MISMATCH", NativeLocalImageProviderV0(_unexpected_executor),
        request, _context(),
    )


@pytest.mark.parametrize("invalid", ("media", "encoded-size", "dimensions", "malformed"))
def test_invalid_image_is_refused_before_dispatch(invalid):
    if invalid == "media":
        request = replace(_request(), content_type="image/jpeg")
    elif invalid == "encoded-size":
        request = _request(b"x" * (t09.MAX_IMAGE_BYTES + 1))
    elif invalid == "dimensions":
        request = _request(_png((t09.MAX_IMAGE_DIMENSION + 1, 1)))
    else:
        request = _request(b"malformed PNG")
    code = (
        "INVALID_ADMITTED_REQUEST" if invalid in ("media", "encoded-size") else "INVALID_ADMITTED_IMAGE"
    )
    _refuses(code, NativeLocalImageProviderV0(_unexpected_executor), request, _context())


@pytest.mark.parametrize(
    ("field", "wrong"),
    (
        ("attempt_id", "old-attempt"), ("request_id", "other-request"), ("image_id", "other-image"),
        ("encoded_sha256", "0" * 64), ("bgr8_sha256", "0" * 64), ("width", 1), ("height", True),
    ),
)
def test_executor_binding_mismatch_is_refused(field, wrong):
    def executor(frame, context):
        completion = _complete(frame, {"rec_texts": []})
        return replace(completion, binding=replace(completion.binding, **{field: wrong}))

    _refuses(
        "OCR_SOURCE_BINDING_MISMATCH", NativeLocalImageProviderV0(executor), _request(), _context()
    )


def test_mutated_executor_input_cannot_replace_the_independent_binding():
    def executor(frame, context):
        object.__setattr__(frame.binding, "image_id", "different-image")
        return _complete(frame, {"rec_texts": []})

    _refuses(
        "OCR_SOURCE_BINDING_MISMATCH", NativeLocalImageProviderV0(executor), _request(), _context()
    )


@pytest.mark.parametrize(
    "payload",
    (
        {"rec_texts": ["x" * 257]},
        {"rec_texts": ["WORD"], "rec_scores": [float("nan")]},
        {"rec_texts": ["WORD"], "rec_boxes": [[0, 0, 3, 1]]},
        {"rec_texts": ["WORD"], "rec_scores": []},
    ),
    ids=("text-bound", "score-bound", "frame-bound", "parallel-arrays"),
)
def test_invalid_recognition_is_refused(payload):
    provider = NativeLocalImageProviderV0(lambda frame, context: _complete(frame, payload))
    _refuses("INVALID_RECOGNITION", provider, _request(), _context())


def test_zero_token_completion_is_distinct_from_execution_failure():
    def failure(frame, context):
        return NativeLocalImageCompletionV0(
            frame.binding, NativeLocalImageStatusV0.FAILED,
            native_stopped=True, cleanup_confirmed=True,
        )

    provider = NativeLocalImageProviderV0(lambda frame, context: _complete(frame, {"rec_texts": []}))
    request = _request()
    assert provider(request, _context()).payload == {"rec_texts": ()}
    _refuses("OCR_ENGINE_FAILURE", NativeLocalImageProviderV0(failure), request, _context())


@pytest.mark.parametrize("interruption", ("deadline", "cancellation"))
def test_interruption_refuses_before_dispatch(interruption):
    context = _context()
    if interruption == "deadline":
        context = replace(context, deadline=monotonic() - 1)
    else:
        context.cancel_event.set()
    code = "DEADLINE_EXCEEDED" if interruption == "deadline" else "CANCELLED"
    _refuses(code, NativeLocalImageProviderV0(_unexpected_executor), _request(), context)


@pytest.mark.parametrize("interruption", ("deadline", "cancellation"))
def test_interruption_after_dispatch_suppresses_clean_late_recognition(monkeypatch, interruption):
    now = [monotonic()]
    context = t10.LocalImageProcessingContextV0(now[0] + 60, Event())
    monkeypatch.setattr(t10, "monotonic", lambda: now[0])

    def executor(frame, budget):
        if interruption == "deadline":
            now[0] = budget.deadline
        else:
            budget.cancel_event.set()
        return _complete(frame, {"rec_texts": ["LATE"]})

    code = "DEADLINE_EXCEEDED" if interruption == "deadline" else "CANCELLED"
    _refuses(code, NativeLocalImageProviderV0(executor), _request(), context)


@pytest.mark.parametrize("missing", ("native_stopped", "cleanup_confirmed"))
def test_unconfirmed_native_teardown_suppresses_recognition_and_closes_admission(missing):
    calls = []

    def executor(frame, context):
        calls.append(frame.binding)
        return replace(_complete(frame, {"rec_texts": ["DISCARDED"]}), **{missing: False})

    provider = NativeLocalImageProviderV0(executor)
    _refuses("NATIVE_TEARDOWN_UNCONFIRMED", provider, _request(), _context())
    _refuses("PROCESSOR_UNAVAILABLE", provider, _request(), _context())
    assert len(calls) == 1


def test_executor_exception_proves_neither_termination_nor_cleanup():
    def executor(frame, context):
        raise RuntimeError("generated private diagnostic")

    provider = NativeLocalImageProviderV0(executor)
    _refuses("NATIVE_TEARDOWN_UNCONFIRMED", provider, _request(), _context())
    _refuses("PROCESSOR_UNAVAILABLE", provider, _request(), _context())
