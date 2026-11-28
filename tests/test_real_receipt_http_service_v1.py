"""Focused HTTP-boundary tests using only generated images and in-memory connections."""

from __future__ import annotations

from collections import deque
from hashlib import sha256
from io import BytesIO
import json
from struct import pack, unpack_from
from threading import Event, Thread
import zlib

from PIL import Image
import pytest

from pipeline import real_receipt_http_service_v1 as http


_TOKEN = b"generated-test-token"
_REQUEST_ID = "request-t09"
_IMAGE_ID = "image-t09"


class _MemoryConnection:
    def __init__(self, *parts: bytes) -> None:
        self._parts = deque(part for part in parts if part)
        self._readable = Event()
        if self._parts:
            self._readable.set()
        self.received = 0
        self.output = bytearray()

    def settimeout(self, timeout: float) -> None:
        assert timeout > 0

    def recv(self, size: int, flags: int = 0) -> bytes:
        if not self._parts:
            return b""
        if flags == http.MSG_PEEK:
            return self._parts[0][:size]
        part = self._parts.popleft()
        if len(part) > size:
            self._parts.appendleft(part[size:])
        if not self._parts:
            self._readable.clear()
        received = part[:size]
        self.received += len(received)
        return received

    def sendall(self, block: bytes) -> None:
        self.output.extend(block)

    def disconnect(self) -> None:
        self._readable.set()


@pytest.fixture(autouse=True)
def _memory_select(monkeypatch):
    def select_in_memory(reads, writes, errors, timeout):
        (connection,) = reads
        return (reads if connection._readable.wait(timeout) else (), writes, errors)

    monkeypatch.setattr(http, "select", select_in_memory)


def _png(size=(3, 2)) -> bytes:
    with BytesIO() as stream, Image.new("RGBA", size, (2, 4, 6, 255)) as image:
        image.save(stream, format="PNG")
        return stream.getvalue()


def _head(
    image: bytes,
    *,
    change: dict[bytes, bytes | None] | None = None,
    extra: tuple[bytes, ...] = (),
    request_line: bytes = b"POST /v1/receipts/process HTTP/1.1",
) -> bytes:
    headers = {
        b"Host": b"10.0.2.2:" + str(http.DEFAULT_PORT).encode("ascii"),
        b"Authorization": b"Bearer " + _TOKEN,
        b"Content-Type": b"image/png",
        b"Content-Length": str(len(image)).encode("ascii"),
        b"X-Request-Id": _REQUEST_ID.encode("ascii"),
        b"X-Image-Id": _IMAGE_ID.encode("ascii"),
    }
    headers.update(change or {})
    fields = [name + b": " + value for name, value in headers.items() if value is not None]
    return b"\r\n".join((request_line, *fields, *extra, b"", b""))


def _envelope(request: http.ReceiptRequest, **overrides) -> bytes:
    value = {
        "schemaName": "receipt-presentation",
        "schemaVersion": "1",
        "sourceContractVersion": "0",
        "requestId": request.request_id,
        "imageId": request.image_id,
        "source": {
            "type": "LOCAL_IMAGE",
            "provenance": {
                "sourceSystem": "T09_TEST_PROCESSOR",
                "sourceReference": "opaque-image",
                "contentSha256": sha256(request.encoded_image).hexdigest(),
            },
        },
        "outcome": {"status": "SOURCE_EVIDENCE_INSUFFICIENT", "failure": None},
        "sourceEvidence": {"sourceProcessingStatus": "OCR_COMPLETED", "tokenIds": []},
        "sourceGate": {
            "gateResultId": "gate-t09",
            "decision": "INSUFFICIENT",
            "reasons": ["Receipt text is insufficient."],
        },
        "automaticExtraction": None,
        "receipt": None,
    }
    value.update(overrides)
    return json.dumps(value).encode("utf-8")


def _reject_unexpected_call(request, context):
    raise AssertionError("Processor should not be reached.")


def _exchange(service, image, **headers) -> _MemoryConnection:
    connection = _MemoryConnection(_head(image, **headers), image)
    service.handle_connection(connection, port=http.DEFAULT_PORT)
    return connection


def _response(connection, expected_status):
    head, body = bytes(connection.output).split(b"\r\n\r\n", 1)
    status, *field_lines = head.split(b"\r\n")
    assert status.split(b" ", 2)[:2] == [b"HTTP/1.1", str(expected_status).encode("ascii")]
    fields = dict(line.split(b": ", 1) for line in field_lines)
    assert fields[b"Connection"] == b"close"
    assert fields[b"Cache-Control"] == b"no-store"
    assert int(fields[b"Content-Length"]) == len(body)
    if expected_status != 200:
        assert body == b""
        assert b"Content-Type" not in fields
    return fields, body


@pytest.mark.parametrize("authorization", (None, b"Bearer wrong", b"Basic generated-test-token"))
def test_unauthorized_request_does_not_consume_body(authorization):
    image = _png()
    head = _head(image, change={b"Authorization": authorization})
    conn = _MemoryConnection(head, image)
    service = http.ReceiptHttpService(_TOKEN, processor=_reject_unexpected_call)

    service.handle_connection(conn, port=http.DEFAULT_PORT)

    fields, _ = _response(conn, 401)
    assert fields[b"WWW-Authenticate"] == b"Bearer"
    assert conn.received == len(head)


@pytest.mark.parametrize(
    ("header", "value"),
    (
        (b"X-Request-Id", None),
        (b"X-Image-Id", None),
        (b"X-Request-Id", b"has a space"),
        (b"X-Image-Id", b"image-participant-47"),
        (b"X-Image-Id", b"a" * 97),
    ),
)
def test_invalid_ids(header, value):
    service = http.ReceiptHttpService(_TOKEN, processor=_reject_unexpected_call)
    _response(_exchange(service, _png(), change={header: value}), 400)


@pytest.mark.parametrize(
    "headers",
    (
        {"change": {b"Content-Length": None}},
        {"change": {b"Content-Length": b"+12"}},
        {"extra": (b"content-length: 4",)},
        {"extra": (b"Transfer-Encoding: chunked",)},
        {"extra": (b"Expect: 100-continue",)},
        {"extra": (b"X-Long: " + b"a" * 8192,)},
        {"extra": tuple(b"X-Limit: " + b"a" * 800 for _ in range(11))},
        {"request_line": b"GET /v1/receipts/process HTTP/1.1"},
        {"request_line": b"POST /v1/receipts/process?draft=1 HTTP/1.1"},
    ),
)
def test_malformed_http_request(headers):
    service = http.ReceiptHttpService(_TOKEN, processor=_reject_unexpected_call)
    _response(_exchange(service, _png(), **headers), 400)


def test_surplus_bytes_are_not_dispatched():
    image = _png()
    service = http.ReceiptHttpService(_TOKEN, processor=_reject_unexpected_call)
    conn = _MemoryConnection(_head(image), image + b"x")
    service.handle_connection(conn, port=http.DEFAULT_PORT)
    _response(conn, 400)


def test_oversized_content_length_is_refused_without_a_body_read():
    service = http.ReceiptHttpService(_TOKEN, processor=_reject_unexpected_call)
    head = _head(b"", change={b"Content-Length": b"4194305"})
    conn = _MemoryConnection(head, b"unread body")
    service.handle_connection(conn, port=http.DEFAULT_PORT)
    _response(conn, 413)
    assert conn.received == len(head)


@pytest.mark.parametrize(
    "change",
    (
        {b"Content-Type": b"image/jpeg"},
        {b"Content-Type": None},
        {b"Content-Encoding": b"gzip"},
    ),
)
def test_unsupported_media(change):
    service = http.ReceiptHttpService(_TOKEN, processor=_reject_unexpected_call)
    _response(_exchange(service, b"not a PNG", change=change), 415)


@pytest.mark.parametrize("invalid_case", ("empty", "signature", "crc", "trailing", "dimensions"))
def test_invalid_png_content_or_dimensions(invalid_case):
    valid = _png()
    cases = {
        "empty": b"",
        "signature": b"not a PNG",
        "crc": valid[:-1] + bytes([valid[-1] ^ 1]),
        "trailing": valid + b"x",
        "dimensions": _png((1601, 1)),
    }
    service = http.ReceiptHttpService(_TOKEN, processor=_reject_unexpected_call)
    _response(_exchange(service, cases[invalid_case]), 422)


def test_valid_png_chunk_crcs_do_not_bypass_the_decompressed_image_size():
    image = _png()
    offset = image.index(b"IDAT") - 4
    original_length = unpack_from(">I", image, offset)[0]
    # A 3-by-2 RGBA PNG has 26 filtered bytes. This stream expands beyond that.
    compressed = zlib.compress(b"\x00" * 27)
    chunk = b"IDAT" + compressed
    replacement = pack(">I", len(compressed)) + chunk + pack(">I", zlib.crc32(chunk))
    malformed = image[:offset] + replacement + image[offset + original_length + 12:]
    service = http.ReceiptHttpService(_TOKEN, processor=_reject_unexpected_call)
    _response(_exchange(service, malformed), 422)


def test_default_service_returns_unavailable_for_a_valid_image():
    _response(_exchange(http.ReceiptHttpService(_TOKEN), _png()), 503)


def test_accepted_image_dispatches_once_and_returns_exact_v1_bytes():
    image = _png((1600, 1600))
    calls = []

    def processor(request, context):
        assert request.encoded_image == image
        assert (request.request_id, request.image_id) == (_REQUEST_ID, _IMAGE_ID)
        assert request.content_type == "image/png"
        assert context.deadline > http.monotonic()
        result = _envelope(request)
        calls.append(result)
        return result

    service = http.ReceiptHttpService(_TOKEN, processor=processor)
    fields, body = _response(_exchange(service, image), 200)
    assert fields[b"Content-Type"] == b"application/json"
    assert calls == [body]
    assert json.loads(body)["outcome"]["status"] == "SOURCE_EVIDENCE_INSUFFICIENT"


@pytest.mark.parametrize(
    ("member", "value"),
    (
        ("requestId", "other-request"),
        ("imageId", "other-image"),
        (
            "source",
            {
                "type": "SYNTHETIC_FIXTURE",
                "provenance": {
                    "sourceSystem": "TEST_FIXTURE",
                    "sourceReference": "opaque-fixture",
                    "contentSha256": None,
                },
            },
        ),
        (
            "source",
            {
                "type": "LOCAL_IMAGE",
                "provenance": {
                    "sourceSystem": "T09_TEST_PROCESSOR",
                    "sourceReference": "opaque-image",
                    "contentSha256": "0" * 64,
                },
            },
        ),
    ),
)
def test_mismatched_or_fixture_output_is_refused(member, value):
    def processor(request, context):
        return _envelope(request, **{member: value})

    service = http.ReceiptHttpService(_TOKEN, processor=processor)
    _response(_exchange(service, _png()), 500)


def test_expected_id_is_retained_independently_of_the_injected_request_object():
    def processor(request, context):
        object.__setattr__(request, "request_id", "substituted-request")
        return _envelope(request)

    service = http.ReceiptHttpService(_TOKEN, processor=processor)
    _response(_exchange(service, _png()), 500)


@pytest.mark.parametrize(
    "result",
    (b"\xff", b"\xef\xbb\xbf{}", b"x" * (http.MAX_RESPONSE_BYTES + 1)),
    ids=("invalid-utf8", "utf8-bom", "oversized"),
)
def test_malformed_or_oversized_processor_output_is_refused(result):
    service = http.ReceiptHttpService(_TOKEN, processor=lambda request, context: result)
    _response(_exchange(service, _png()), 500)


@pytest.mark.parametrize(
    ("refusal", "status"),
    (
        (http.ProcessingRefusal.FAILED, 500),
        (http.ProcessingRefusal.UNAVAILABLE, 503),
        (http.ProcessingRefusal.DEADLINE_EXCEEDED, 504),
    ),
)
def test_typed_processor_refusals_use_empty_http_errors(refusal, status):
    service = http.ReceiptHttpService(_TOKEN, processor=lambda request, context: refusal)
    _response(_exchange(service, _png()), status)


def test_processor_cancellation_closes_without_publishing():
    service = http.ReceiptHttpService(
        _TOKEN, processor=lambda request, context: http.ProcessingRefusal.CANCELLED
    )
    assert not _exchange(service, _png()).output


def test_processor_exception_details_are_suppressed(capsys):
    def processor(request, context):
        raise RuntimeError("generated secret marker")

    service = http.ReceiptHttpService(_TOKEN, processor=processor)
    _response(_exchange(service, _png()), 500)
    captured = capsys.readouterr()
    assert not captured.out and not captured.err


@pytest.mark.parametrize("interruption", ("deadline", "disconnect"))
def test_interruption_suppresses_late_output_but_leaves_worker_busy(monkeypatch, interruption):
    image = _png()
    now = [1000.0]
    monkeypatch.setattr(http, "monotonic", lambda: now[0])
    entered = Event()
    release = Event()
    contexts = []

    def processor(request, context):
        contexts.append(context)
        if len(contexts) == 1:
            entered.set()
            assert release.wait(10)
        return _envelope(request)

    service = http.ReceiptHttpService(_TOKEN, processor=processor)
    conn = _MemoryConnection(_head(image), image)
    handler = Thread(
        target=service.handle_connection, args=(conn,), kwargs={"port": http.DEFAULT_PORT}, daemon=True
    )
    handler.start()
    try:
        assert entered.wait(3)
        _response(_exchange(service, image), 429)
        if interruption == "deadline":
            now[0] = contexts[0].deadline + 1
        else:
            conn.disconnect()

        handler.join(3)
        assert not handler.is_alive()
        assert contexts[0].wait_for_cancellation(0)
        if interruption == "deadline":
            _response(conn, 504)
        else:
            assert not conn.output

        before_worker_exit = bytes(conn.output)
        _response(_exchange(service, image), 429)
        assert len(contexts) == 1
    finally:
        release.set()
        handler.join(3)

    assert service._active.acquire(timeout=3)
    service._active.release()
    assert bytes(conn.output) == before_worker_exit
    _response(_exchange(service, image), 200)
    assert len(contexts) == 2
