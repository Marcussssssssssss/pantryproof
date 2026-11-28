"""T10 in-memory verification using provider stubs and test-only pins."""

from dataclasses import dataclass, replace
import json
from struct import pack
from threading import Event, Thread
from time import monotonic
from unittest.mock import Mock
from zlib import crc32

import pytest

from pipeline import backend_local_image_receipt_v0 as backend
from pipeline import gate_c_live_source_gate_v0 as gate
from pipeline import real_receipt_http_service_v1 as http
from pipeline.contracts import SourceProcessingStatus
from pipeline.ocr_adapter import adapt_paddleocr_result
from pipeline.presentation_v1.conformance import decode_and_validate_presentation_v1
from tests import test_real_receipt_http_service_v1 as http_fixtures


_GENERATED_PNG = http_fixtures._png((400, 200))


@dataclass(frozen=True)
class _Request:
    request_id: str = "req-local-01"
    image_id: str = "img-local-01"
    content_type: str = "image/png"
    encoded_image: bytes = _GENERATED_PNG


def _context(event=None):
    return backend.LocalImageProcessingContextV0(
        monotonic() + 90, Event() if event is None else event
    )


def _payload(store="SUNNY MART", *, split=False):
    receipt_rows = [("MILK 2 x 5.50 11.00", 10, 50, 240),
                    ("TOTAL RM 11.00", 130, 100, 260)]
    if split:
        receipt_rows = [
            ("MILK", 10, 50, 50), ("2", 90, 50, 105), ("x", 115, 50, 125),
            ("5.50", 138, 50, 170), ("11.00", 200, 50, 240),
            ("TOTAL", 130, 100, 175), ("RM 11.00", 195, 100, 260),
        ]
    regions = [(store, 10, 5, 160), ("DATE: 2026-10-13", 10, 25, 190), *receipt_rows]
    return {
        "rec_texts": [text for text, *_ in regions],
        "rec_boxes": [[left, top, right, top + 10] for _, left, top, right in regions],
    }


@pytest.fixture
def configure(monkeypatch):
    def bind(implementation):
        provider = Mock(side_effect=implementation)
        runtime = backend.LocalImageRuntimeApprovalV0(provider, backend.LOCAL_IMAGE_SOURCE_SYSTEM)
        monkeypatch.setattr(backend, "_APPROVED_RUNTIME", runtime)
        monkeypatch.setattr(gate, "_APPROVED_POLICY_SHA256", gate.PROPOSED_LIVE_GATE_V0.policy_sha256)
        return backend.LocalImageReceiptProcessorV0(gate.PROPOSED_LIVE_GATE_V0, runtime), provider
    return bind


def _provider(payload):
    def recognize(request, context):
        return backend.RetainedLocalImageRecognitionV0(
            request, request.image_sha256, 400, 200, payload,
        )
    return recognize


def _decode(raw, request=None):
    request = _Request() if request is None else request
    return decode_and_validate_presentation_v1(
        raw,
        expected_request_id=request.request_id,
        expected_image_id=request.image_id,
        consumer_mode="LIVE",
    )


@pytest.mark.parametrize(("split", "store"), [(False, "SUNNY MART"), (True, "RAINY GROCER")])
def test_whole_and_split_rows_produce_original_b2_values(configure, monkeypatch, split, store):
    process, provider = configure(_provider(_payload(store, split=split)))
    projector = Mock(wraps=backend.project_retained_local_image_presentation_v1)
    extractor = Mock(wraps=backend.extract_b2)
    monkeypatch.setattr(backend, "project_retained_local_image_presentation_v1", projector)
    monkeypatch.setattr(backend, "extract_b2", extractor)
    raw = process(_Request(), _context())
    dto = _decode(raw)
    receipt = json.loads(raw)["receipt"]
    assert dto.outcome.status == "RESULT_AVAILABLE"
    assert receipt["receiptFields"][0]["originalAutomaticValue"] == store
    total = receipt["receiptFields"][2]
    assert total["originalAutomaticValue"] == "RM 11.00"
    assert total["presentationValue"] == "11.00"
    assert receipt["itemRows"][0]["fields"][0]["originalAutomaticValue"] == "MILK"
    provider.assert_called_once()
    projector.assert_called_once()
    extractor.assert_called_once()
    attempt = projector.call_args.kwargs["attempt"]
    assert attempt.gate.adapted_source is attempt.adapted_source
    assert attempt.source_evidence.gate_result is attempt.gate.result
    assert attempt.b2_result.receipt_output.source_evidence is attempt.source_evidence
    assert attempt.adapted_source.tokens is attempt.source_evidence.tokens
    assert b'"contentSha256":null' in raw


@pytest.mark.parametrize("payload", [
    {"rec_texts": []},
    {"rec_texts": ["Plain words."], "rec_boxes": [[1, 1, 90, 12]]},
])
def test_completed_unstructured_ocr_has_insufficient_outcome(configure, payload):
    process, _ = configure(_provider(payload))
    result = _decode(process(_Request(), _context()))
    assert result.outcome.status == "SOURCE_EVIDENCE_INSUFFICIENT"
    assert result.source_evidence.source_processing_status == "OCR_COMPLETED"
    assert result.source_gate.reasons == (gate.PUBLIC_INSUFFICIENCY_REASON,)
    assert result.receipt is None


@pytest.mark.parametrize(("extra", "code"), [
    ("TOTAL 12.00", "AMBIGUOUS_EVIDENCE"),
    ("UNKNOWN 12.00", "UNSUPPORTED_LAYOUT"),
])
def test_gate_refuses_conflicting_or_unsupported_lines(configure, extra, code):
    process, _ = configure(_provider(_payload()))
    reserved = backend._reserve(_Request(), process.gate_policy)
    payload = _payload()
    payload["rec_texts"].append(extra)
    payload["rec_boxes"].append([130, 125, 260, 135])
    original = adapt_paddleocr_result(
        payload,
        receipt_id=reserved.presentation.receipt_id,
        image_id=reserved.presentation.image_id,
        source_system=backend.LOCAL_IMAGE_SOURCE_SYSTEM,
        source_reference=reserved.presentation.source_reference,
        processing_status=SourceProcessingStatus.OCR_COMPLETED,
    )
    with pytest.raises(gate.LiveSourceGateRefusal, match=code):
        gate.evaluate_live_source_gate_v0(
            context=reserved.presentation, source=original,
            gate_result_id=reserved.gate_result_id, image_width=400, image_height=200,
        )


def test_sufficient_source_with_public_reason_conflict_is_refused(configure):
    process, _ = configure(_provider(_payload()))
    reserved = backend._reserve(_Request(), process.gate_policy)
    payload = _payload()
    payload["rec_texts"].append(gate.PUBLIC_INSUFFICIENCY_REASON)
    payload["rec_boxes"].append([10, 125, 250, 135])
    source = adapt_paddleocr_result(
        payload,
        receipt_id=reserved.presentation.receipt_id,
        image_id=reserved.presentation.image_id,
        source_system=backend.LOCAL_IMAGE_SOURCE_SYSTEM,
        source_reference=reserved.presentation.source_reference,
        processing_status=SourceProcessingStatus.OCR_COMPLETED,
    )
    assert gate._has_receipt_structure(source.tokens) is True
    with pytest.raises(gate.LiveSourceGateRefusal) as refusal:
        gate.evaluate_live_source_gate_v0(
            context=reserved.presentation, source=source,
            gate_result_id=reserved.gate_result_id, image_width=400, image_height=200,
        )
    assert refusal.value.code == "GATE_REASON_CONFLICT"


def test_gate_refusal_does_not_run_extraction(configure, monkeypatch):
    process, _ = configure(_provider({"rec_texts": ["TOTAL 2.00"], "rec_boxes": [[1, 1, 90, 12]]}))
    extract = Mock()
    monkeypatch.setattr(backend, "extract_b2", extract)
    dto = _decode(process(_Request(), _context()))
    assert dto.outcome.failure.stage == "SOURCE_GATE"
    assert dto.source_gate is None
    extract.assert_not_called()


@pytest.mark.parametrize("payload", [
    {"rec_texts": ["SECRET"], "rec_boxes": []},
    {"rec_texts": ["a"] * (gate.MAX_REGIONS + 1)},
    {"rec_texts": ["x"], "rec_boxes": [[1, 1, 401, 2]]},
])
def test_malformed_ocr_has_safe_failure(configure, payload):
    process, _ = configure(_provider(payload))
    raw = process(_Request(), _context())
    assert _decode(raw).outcome.failure.code == "OCR_ENGINE_FAILURE"
    assert b"SECRET" not in raw


def test_failed_ocr_is_not_empty_recognition(configure):
    def fail(*args):
        raise RuntimeError("PRIVATE NATIVE DETAIL")

    process, _ = configure(fail)
    raw = process(_Request(), _context())
    assert _decode(raw).outcome.failure.code == "OCR_ENGINE_FAILURE"
    assert b"PRIVATE NATIVE DETAIL" not in raw


def test_unconfigured_or_substituted_approvals_never_call_provider(configure, monkeypatch):
    ready, provider = configure(_provider(_payload()))
    for process in (
        backend.LocalImageReceiptProcessorV0(),
        replace(ready, gate_policy=None),
        replace(ready, gate_policy=replace(ready.gate_policy)),
        replace(ready, runtime=replace(ready.runtime)),
    ):
        with pytest.raises(backend.LocalImageProcessingRefusal, match="PROCESSOR_UNAVAILABLE"):
            process(_Request(), _context())
    monkeypatch.setattr(gate, "_APPROVED_POLICY_SHA256", None)
    with pytest.raises(backend.LocalImageProcessingRefusal, match="PROCESSOR_UNAVAILABLE"):
        ready(_Request(), _context())
    provider.assert_not_called()


@pytest.mark.parametrize("identity", ["request_id", "image_id", "image_sha256", "detached"])
def test_foreign_recognition_is_refused(configure, identity):
    def recognize(request, context):
        correct = _provider(_payload())(request, context)
        if identity == "image_sha256":
            return replace(correct, image_sha256="0" * 64)
        if identity == "detached":
            return replace(correct, request=replace(request))
        presentation = replace(request.presentation, **{identity: "different-opaque-id"})
        return replace(correct, request=replace(request, presentation=presentation))

    process, _ = configure(recognize)
    with pytest.raises(backend.LocalImageProcessingRefusal, match="OCR_SOURCE_BINDING_MISMATCH"):
        process(_Request(), _context())


@pytest.mark.parametrize("stage", ["adapter", "gate", "attachment", "b2"])
def test_detached_stage_records_are_refused(configure, monkeypatch, stage):
    process, _ = configure(_provider(_payload()))
    if stage == "adapter":
        adapt = backend.adapt_paddleocr_result

        def foreign_adapter(*args, **kwargs):
            return replace(adapt(*args, **kwargs), image_id="different-image")

        monkeypatch.setattr(backend, "adapt_paddleocr_result", foreign_adapter)
        code = "ADAPTED_SOURCE_BINDING_MISMATCH"
    elif stage == "gate":
        evaluate = backend.evaluate_live_source_gate_v0

        def detached_gate(**kwargs):
            result = evaluate(**kwargs)
            return replace(result, adapted_source=replace(result.adapted_source))

        monkeypatch.setattr(backend, "evaluate_live_source_gate_v0", detached_gate)
        code = "GATE_SOURCE_BINDING_MISMATCH"
    elif stage == "attachment":
        attach = backend.attach_gate_result

        def detached_attachment(source, result):
            return attach(source, replace(result))

        monkeypatch.setattr(backend, "attach_gate_result", detached_attachment)
        code = "EVIDENCE_ATTACHMENT_FAILED"
    else:
        extract = backend.extract_b2
        monkeypatch.setattr(backend, "extract_b2", lambda evidence: extract(replace(evidence)))
        code = "B2_SOURCE_BINDING_MISMATCH"
    with pytest.raises(backend.LocalImageProcessingRefusal, match=code):
        process(_Request(), _context())


@pytest.mark.parametrize("stage", ["EXTRACTION", "PRESENTATION_ADAPTER"])
def test_safe_terminal_failures_after_sufficient_gate(configure, monkeypatch, stage):
    process, _ = configure(_provider(_payload()))

    def fail(*args, **kwargs):
        raise ValueError("PRIVATE FAILURE DETAIL")

    if stage == "EXTRACTION":
        monkeypatch.setattr(backend, "extract_b2", fail)
    else:
        project = backend.project_retained_local_image_presentation_v1

        def fail_success(*, context, attempt):
            if attempt.failure is None:
                fail()
            return project(context=context, attempt=attempt)

        monkeypatch.setattr(backend, "project_retained_local_image_presentation_v1", fail_success)

    raw = process(_Request(), _context())
    dto = _decode(raw)
    assert dto.outcome.status == "PROCESSING_FAILED"
    assert dto.outcome.failure.stage == stage
    assert dto.source_gate.decision == "SUFFICIENT"
    assert dto.receipt is None and b"PRIVATE FAILURE DETAIL" not in raw


def test_post_insufficient_failure_is_typed_refusal(configure, monkeypatch):
    process, _ = configure(_provider({"rec_texts": []}))
    monkeypatch.setattr(backend, "extract_b2", Mock(side_effect=ValueError("private")))
    with pytest.raises(backend.LocalImageProcessingRefusal, match="POST_INSUFFICIENT_FAILURE"):
        process(_Request(), _context())


def test_expired_and_cancelled_requests_never_start_ocr(configure):
    process, provider = configure(_provider(_payload()))
    with pytest.raises(backend.LocalImageProcessingRefusal, match="DEADLINE_EXCEEDED"):
        process(_Request(), replace(_context(), deadline=-1.0))
    event = Event()
    event.set()
    with pytest.raises(backend.LocalImageProcessingRefusal, match="CANCELLED"):
        process(_Request(), _context(event))
    provider.assert_not_called()


def test_cancellation_after_recognition_prevents_adapter_dispatch(configure, monkeypatch):
    event = Event()

    def cancel(request, context):
        result = _provider(_payload())(request, context)
        event.set()
        return result

    process, provider = configure(cancel)
    adapt = Mock()
    monkeypatch.setattr(backend, "adapt_paddleocr_result", adapt)
    with pytest.raises(backend.LocalImageProcessingRefusal, match="CANCELLED"):
        process(_Request(), _context(event))
    provider.assert_called_once()
    adapt.assert_not_called()


def test_t09_default_unavailability_and_deadline_refusal():
    processor = backend.as_t09_receipt_processor_v0(backend.LocalImageReceiptProcessorV0())
    request = http.ReceiptRequest("request-t09", "image-t09", "image/png", _GENERATED_PNG)
    context = http.ProcessingContext(monotonic() + 90)
    assert processor(request, context) is http.ProcessingRefusal.UNAVAILABLE
    assert http._processor_response(processor, request, context).status == 503
    assert processor(request, http.ProcessingContext(-1.0)) is http.ProcessingRefusal.DEADLINE_EXCEEDED


@pytest.mark.parametrize(
    "case", ["jpeg", "over-size", "too-wide", "too-tall"],
    ids=["jpeg", "over-4-mib", "width-1601", "height-1601"],
)
def test_t09_admitted_request_limits_refuse_before_ocr(configure, case):
    core, provider = configure(_provider(_payload()))
    processor = backend.as_t09_receipt_processor_v0(core)
    content_type = "image/jpeg" if case == "jpeg" else "image/png"
    image = _GENERATED_PNG
    if case == "over-size":
        image += b"\0" * (http.MAX_IMAGE_BYTES - len(image) + 1)
    elif case == "too-wide":
        image = http_fixtures._png((1601, 1))
    elif case == "too-tall":
        image = http_fixtures._png((1, 1601))
    request = http.ReceiptRequest("request-t09", "image-t09", content_type, image)
    assert processor(request, http.ProcessingContext(monotonic() + 90)) is http.ProcessingRefusal.FAILED
    provider.assert_not_called()


@pytest.fixture
def memory_http(monkeypatch):
    def select_in_memory(reads, writes, errors, timeout):
        (connection,) = reads
        return (reads if connection._readable.wait(timeout) else (), writes, errors)

    monkeypatch.setattr(http, "select", select_in_memory)


def test_t09_in_memory_exchange_accepts_png_at_size_and_dimension_limits(configure, memory_http):
    image = http_fixtures._png((1600, 1600))
    # Add a valid ancillary chunk to reach exactly the admitted byte limit.
    chunk_size = http.MAX_IMAGE_BYTES - len(image) - 12
    chunk = b"tEXt" + b"Comment\0" + b"x" * (chunk_size - 8)
    image = image[:-12] + pack(">I", chunk_size) + chunk + pack(">I", crc32(chunk)) + image[-12:]
    assert len(image) == http.MAX_IMAGE_BYTES

    core, provider = configure(_provider(_payload("RAINY GROCER", split=True)))
    service = http.ReceiptHttpService(
        http_fixtures._TOKEN, processor=backend.as_t09_receipt_processor_v0(core),
    )
    connection = http_fixtures._exchange(service, image)
    fields, body = http_fixtures._response(connection, 200)
    assert fields[b"Content-Type"] == b"application/json"
    result = _decode(body, http.ReceiptRequest("request-t09", "image-t09", "image/png", image))
    assert (result.request_id, result.image_id) == ("request-t09", "image-t09")
    assert result.outcome.status == "RESULT_AVAILABLE"
    assert json.loads(body)["receipt"]["receiptFields"][0]["originalAutomaticValue"] == "RAINY GROCER"
    provider.assert_called_once()
    assert provider.call_args.args[0].encoded_image == image


def test_t09_disconnect_maps_cancellation_and_discards_late_recognition(configure, memory_http):
    entered = Event()
    finished = Event()
    observed = []

    def late_provider(request, context):
        entered.set()
        # This invokes T09's real public wait through the compatibility signal.
        observed.append(context.cancel_event.wait(5))
        return _provider(_payload())(request, context)

    core, provider = configure(late_provider)
    adapt = backend.as_t09_receipt_processor_v0(core)

    def processor(request, context):
        assert type(context) is http.ProcessingContext
        observed.append(adapt(request, context))
        finished.set()
        return observed[-1]

    service = http.ReceiptHttpService(http_fixtures._TOKEN, processor=processor)
    connection = http_fixtures._MemoryConnection(
        http_fixtures._head(_GENERATED_PNG), _GENERATED_PNG,
    )
    handler = Thread(
        target=service.handle_connection, args=(connection,), kwargs={"port": http.DEFAULT_PORT},
        daemon=True,
    )
    handler.start()
    try:
        assert entered.wait(3)
        connection.disconnect()
        handler.join(3)
        assert not handler.is_alive()
        assert finished.wait(3)
        assert observed == [True, http.ProcessingRefusal.CANCELLED]
        assert not connection.output
        provider.assert_called_once()
    finally:
        service.stop()
        handler.join(3)
