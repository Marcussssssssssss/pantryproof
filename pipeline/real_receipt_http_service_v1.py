"""Loopback development HTTP boundary for an injected receipt processor."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from hmac import compare_digest
from http import HTTPStatus
from io import BytesIO
import os
from queue import Empty, Queue
import re
from select import select
from socket import MSG_PEEK, socket
from socketserver import BaseRequestHandler, TCPServer, ThreadingMixIn
from struct import unpack_from
from threading import BoundedSemaphore, Event, Lock, Thread
from time import monotonic
from typing import Protocol
import zlib

from PIL import Image

from pipeline.presentation_v1 import conformance
from pipeline.presentation_v1.review_conformance import (
    MAX_PRESENTATION_BYTES, MAX_REVIEW_BYTES, PRESENTATION_SCHEMA, REVIEW_SCHEMA,
    decode_and_validate_receipt_review_v1,
)


ROUTE = "/v1/receipts/process"
CONTENT_TYPE = "image/png"
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_IMAGE_DIMENSION = 1600
MAX_RESPONSE_BYTES = MAX_PRESENTATION_BYTES
DEFAULT_PORT = 8765
TOKEN_ENV = "PANTRYPROOF_RECEIPT_TOKEN"

_HEADER_BYTES = 8192
_HEADER_LINE_BYTES = 2048
_HEADER_FIELDS = 32
_ID_BYTES = 96
_HTTP_WORKERS = 4
_POLL_SECONDS = 0.025
_REQUEST_LINE = f"POST {ROUTE} HTTP/1.1".encode("ascii")
_HEADER_NAME = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
_HEADER_VALUE = re.compile(rb"[\t\x20-\x7e]*")
_BODY_LENGTH = re.compile(rb"0|[1-9][0-9]*")
_BEARER_TOKEN = re.compile(rb"[A-Za-z0-9._~+/-]+=*")
_SCHEMA_TOKEN = re.compile(rb"[A-Za-z0-9][A-Za-z0-9._-]{0,95}")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_CHUNK_NAME = re.compile(rb"[A-Za-z]{2}[A-Z][A-Za-z]")
_PNG_MODES = {
    0: (1, (1, 2, 4, 8, 16)),
    2: (3, (8, 16)),
    3: (1, (1, 2, 4, 8)),
    4: (2, (8, 16)),
    6: (4, (8, 16)),
}
_ADAM7_PASSES = (
    (0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
    (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2),
)


@dataclass(frozen=True, slots=True)
class Deadlines:
    """Seconds, measured from HTTP handling or the start of each named phase."""

    ingress: float = 10.0
    processing: float = 100.0
    response_write: float = 5.0
    overall: float = 115.0

    def __post_init__(self) -> None:
        durations = (self.ingress, self.processing, self.response_write, self.overall)
        if any(type(value) not in (float, int) or not 0 < value < 120 for value in durations):
            raise ValueError("Deadlines must be positive and below 120 seconds.")
        if self.ingress + self.response_write >= self.overall:
            raise ValueError("Overall deadline must leave time for processing.")


@dataclass(frozen=True, slots=True, repr=False)
class ReceiptRequest:
    request_id: str
    image_id: str
    content_type: str
    encoded_image: bytes
    response_schema: str = PRESENTATION_SCHEMA


class ReceiptSession(Protocol):
    def is_active(self) -> bool: ...
    def permits(self, deadline: float | None, processing_deadline: float | None = None) -> bool: ...


@dataclass(frozen=True, slots=True, repr=False)
class ProcessingContext:
    deadline: float
    session: ReceiptSession | None = field(default=None, repr=False)
    stopping: Event | None = field(default=None, repr=False)
    _cancel: Event = field(default_factory=Event, init=False)

    @property
    def cancelled(self) -> bool:
        return (self._cancel.is_set() or monotonic() >= self.deadline
                or (self.stopping is not None and self.stopping.is_set())
                or (self.session is not None and not self.session.is_active()))

    def wait_for_cancellation(self, timeout: float | None = None) -> bool:
        remaining = max(0.0, self.deadline - monotonic())
        self._cancel.wait(remaining if timeout is None else min(remaining, timeout))
        return self.cancelled


class ProcessingRefusal(Enum):
    FAILED = HTTPStatus.INTERNAL_SERVER_ERROR
    UNAVAILABLE = HTTPStatus.SERVICE_UNAVAILABLE
    DEADLINE_EXCEEDED = HTTPStatus.GATEWAY_TIMEOUT
    CANCELLED = None


class ReceiptProcessor(Protocol):
    """Process this image once, honor cancellation, and release its data on return."""

    def __call__(
        self, request: ReceiptRequest, context: ProcessingContext, /
    ) -> bytes | ProcessingRefusal: ...


class _Refusal(Exception):
    def __init__(self, status: HTTPStatus) -> None:
        self.status = status
        super().__init__(status)


class _Disconnected(Exception):
    pass


@dataclass(frozen=True, slots=True, repr=False)
class _Response:
    status: HTTPStatus
    body: bytes = b""


def _parse_headers(
    head: bytes, port: int, token: bytes
) -> tuple[str, str, int, str]:
    lines = head.split(b"\r\n")
    if lines[0] != _REQUEST_LINE or len(lines) - 1 > _HEADER_FIELDS:
        raise _Refusal(HTTPStatus.BAD_REQUEST)

    fields: dict[bytes, bytes] = {}
    for line in lines[1:]:
        name, colon, value = line.partition(b":")
        name = name.lower()
        if (
            len(line) > _HEADER_LINE_BYTES or not colon or not _HEADER_NAME.fullmatch(name)
            or name in fields or not _HEADER_VALUE.fullmatch(value)
        ):
            raise _Refusal(HTTPStatus.BAD_REQUEST)
        fields[name] = value.strip(b" \t")

    port_suffix = b":" + str(port).encode("ascii")
    hosts = (b"127.0.0.1", b"10.0.2.2", b"localhost")
    host = fields.get(b"host", b"").lower()
    length = fields.get(b"content-length", b"")
    if (
        not (host in (name + port_suffix for name in hosts) or (port == 80 and host in hosts))
        or not _BODY_LENGTH.fullmatch(length)
        or fields.keys() & {b"transfer-encoding", b"expect", b"trailer", b"upgrade"}
    ):
        raise _Refusal(HTTPStatus.BAD_REQUEST)

    scheme, _, credential = fields.get(b"authorization", b"").partition(b" ")
    if scheme.lower() != b"bearer" or not credential or not compare_digest(credential, token):
        raise _Refusal(HTTPStatus.UNAUTHORIZED)

    schema = fields.get(b"x-response-schema", PRESENTATION_SCHEMA.encode("ascii"))
    if not _SCHEMA_TOKEN.fullmatch(schema):
        raise _Refusal(HTTPStatus.BAD_REQUEST)
    selection = schema.decode("ascii")
    if selection not in (PRESENTATION_SCHEMA, REVIEW_SCHEMA):
        raise _Refusal(HTTPStatus.NOT_ACCEPTABLE)

    if len(length) > len(str(MAX_IMAGE_BYTES)) or int(length) > MAX_IMAGE_BYTES:
        raise _Refusal(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
    if (
        fields.get(b"content-type", b"").lower() != CONTENT_TYPE.encode("ascii")
        or b"content-encoding" in fields
    ):
        raise _Refusal(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)

    request_id = fields.get(b"x-request-id", b"")
    image_id = fields.get(b"x-image-id", b"")
    if any(not 0 < len(value) <= _ID_BYTES for value in (request_id, image_id)):
        raise _Refusal(HTTPStatus.BAD_REQUEST)
    try:
        # Reuse the frozen V1 identity rules at admission as well as at egress.
        return (
            conformance._protocol_id(request_id.decode("ascii"), "$context.expectedRequestId"),
            conformance._protocol_id(image_id.decode("ascii"), "$context.expectedImageId"),
            int(length),
            selection,
        )
    except conformance.ConformanceViolation:
        raise _Refusal(HTTPStatus.BAD_REQUEST) from None


def _ingress_remaining(deadline: float) -> float:
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise _Refusal(HTTPStatus.BAD_REQUEST)
    return remaining


def _receive(connection: socket, amount: int, deadline: float) -> bytes:
    connection.settimeout(_ingress_remaining(deadline))
    try:
        received = connection.recv(amount)
    except TimeoutError:
        raise _Refusal(HTTPStatus.BAD_REQUEST) from None
    if not received:
        raise _Disconnected
    return received


def _read_request(connection: socket, port: int, token: bytes, deadline: float, *,
                  review_enabled: bool = False, session: ReceiptSession | None = None,
                  overall_deadline: float | None = None) -> ReceiptRequest:
    buffer = bytearray()
    while (end := buffer.find(b"\r\n\r\n")) < 0:
        remaining = _HEADER_BYTES - len(buffer)
        if not remaining:
            raise _Refusal(HTTPStatus.BAD_REQUEST)
        buffer.extend(_receive(connection, min(4096, remaining), deadline))

    request_id, image_id, length, selection = _parse_headers(bytes(buffer[:end]), port, token)
    if (selection == REVIEW_SCHEMA and not review_enabled) or (
        session is not None and not session.permits(overall_deadline)
    ):
        raise _Refusal(HTTPStatus.SERVICE_UNAVAILABLE)
    del buffer[:end + 4]
    if len(buffer) > length:
        raise _Refusal(HTTPStatus.BAD_REQUEST)
    while len(buffer) < length:
        buffer.extend(_receive(connection, min(65536, length - len(buffer)), deadline))
    return ReceiptRequest(request_id, image_id, CONTENT_TYPE, bytes(buffer), selection)


def _check_peer(connection: socket, wait: float = 0.0) -> None:
    readable, _, _ = select((connection,), (), (), wait)
    if readable:
        if connection.recv(1, MSG_PEEK):
            raise _Refusal(HTTPStatus.BAD_REQUEST)
        raise _Disconnected


def _png_scanline_bytes(header: memoryview) -> tuple[int, int, int]:
    width, height, depth, color, compression, filter_method, interlace = unpack_from(
        ">IIBBBBB", header
    )
    mode = _PNG_MODES.get(color)
    if (
        not 0 < width <= MAX_IMAGE_DIMENSION or not 0 < height <= MAX_IMAGE_DIMENSION
        or mode is None or depth not in mode[1] or compression or filter_method
        or interlace not in (0, 1)
    ):
        raise _Refusal(HTTPStatus.UNPROCESSABLE_ENTITY)

    bits_per_pixel = mode[0] * depth
    if not interlace:
        return height * ((width * bits_per_pixel + 7) // 8 + 1), color, depth

    total = 0
    for left, top, dx, dy in _ADAM7_PASSES:
        columns = (width - left + dx - 1) // dx
        rows = (height - top + dy - 1) // dy
        if columns > 0 and rows > 0:
            total += rows * ((columns * bits_per_pixel + 7) // 8 + 1)
    return total, color, depth


def _png_for_decoding(encoded: bytes, deadline: float) -> bytearray:
    """Verify PNG framing and deflate bounds. Only pixel chunks reach Pillow."""
    invalid = HTTPStatus.UNPROCESSABLE_ENTITY
    if not encoded.startswith(_PNG_SIGNATURE):
        raise _Refusal(invalid)

    pixels_only = bytearray(_PNG_SIGNATURE)
    inflater = zlib.decompressobj()
    view = memoryview(encoded)
    offset = len(_PNG_SIGNATURE)
    remaining = color = palette_entries = 0
    have_transparency = have_data = data_closed = False
    while len(view) - offset >= 12:
        _ingress_remaining(deadline)
        size, kind = unpack_from(">I4s", view, offset)
        start = offset + 8
        end = start + size
        if end + 4 > len(view) or not _PNG_CHUNK_NAME.fullmatch(kind):
            raise _Refusal(invalid)
        if zlib.crc32(view[offset + 4:end]) != unpack_from(">I", view, end)[0]:
            raise _Refusal(invalid)

        if offset == len(_PNG_SIGNATURE):
            if kind != b"IHDR" or size != 13:
                raise _Refusal(invalid)
            remaining, color, depth = _png_scanline_bytes(view[start:end])
        elif kind == b"PLTE":
            if (
                palette_entries or color in (0, 4) or have_transparency or have_data
                or not 0 < size <= 768 or size % 3 or (color == 3 and size // 3 > 2**depth)
            ):
                raise _Refusal(invalid)
            palette_entries = size // 3
        elif kind == b"tRNS":
            valid_size = (
                (color == 0 and size == 2) or (color == 2 and size == 6)
                or (color == 3 and 0 < size <= palette_entries)
            )
            if have_transparency or have_data or not valid_size:
                raise _Refusal(invalid)
            have_transparency = True
        elif kind == b"IDAT":
            if data_closed or (color == 3 and not palette_entries):
                raise _Refusal(invalid)
            remaining -= len(inflater.decompress(view[start:end], remaining + 1))
            if remaining < 0 or inflater.unused_data or inflater.unconsumed_tail:
                raise _Refusal(invalid)
            have_data = True
        elif kind == b"IEND":
            if size or remaining or not inflater.eof or end + 4 != len(view):
                raise _Refusal(invalid)
            pixels_only.extend(view[offset:end + 4])
            return pixels_only
        else:
            if kind in (b"acTL", b"fcTL", b"fdAT"):
                raise _Refusal(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            if kind[0] < ord("a"):
                raise _Refusal(invalid)
            data_closed = have_data
            offset = end + 4
            continue

        pixels_only.extend(view[offset:end + 4])
        offset = end + 4
    raise _Refusal(invalid)


def _validate_png(encoded: bytes, deadline: float) -> None:
    try:
        with BytesIO(_png_for_decoding(encoded, deadline)) as stream:
            with Image.open(stream, formats=("PNG",)) as image:
                image.load()
    except (OSError, SyntaxError, ValueError, zlib.error, Image.DecompressionBombError):
        raise _Refusal(HTTPStatus.UNPROCESSABLE_ENTITY) from None
    _ingress_remaining(deadline)


def _processor_response(
    processor: ReceiptProcessor, request: ReceiptRequest, context: ProcessingContext
) -> _Response | None:
    request_id, image_id, encoded = request.request_id, request.image_id, request.encoded_image
    review = request.response_schema == REVIEW_SCHEMA
    result = processor(request, context)
    if context.cancelled or result is ProcessingRefusal.CANCELLED:
        return None
    if isinstance(result, ProcessingRefusal):
        return _Response(result.value)
    limit = MAX_REVIEW_BYTES if review else MAX_RESPONSE_BYTES
    if type(result) is not bytes or not 0 < len(result) <= limit:
        return _Response(HTTPStatus.INTERNAL_SERVER_ERROR)

    if review:
        width, height = unpack_from(">II", encoded, 16)
        parsed = decode_and_validate_receipt_review_v1(
            result, expected_request_id=request_id, expected_image_id=image_id, consumer_mode="LIVE",
            expected_image_width=width, expected_image_height=height,
        ).presentation
    else:
        parsed = conformance.decode_and_validate_presentation_v1(
            result, expected_request_id=request_id, expected_image_id=image_id, consumer_mode="LIVE"
        )
    digest = parsed.source.provenance.content_sha256
    if parsed.source.type != "LOCAL_IMAGE" or (
        digest is not None and digest != sha256(encoded).hexdigest()
    ):
        return _Response(HTTPStatus.INTERNAL_SERVER_ERROR)
    return _Response(HTTPStatus.OK, result)


def _write_response(connection: socket, response: _Response, deadline: float) -> None:
    status = response.status
    headers = [
        f"HTTP/1.1 {status.value} {status.phrase}",
        "Connection: close",
        "Cache-Control: no-store",
        f"Content-Length: {len(response.body)}",
    ]
    if response.body:
        headers.append("Content-Type: application/json")
    if status is HTTPStatus.UNAUTHORIZED:
        headers.append("WWW-Authenticate: Bearer")

    head = ("\r\n".join(headers) + "\r\n\r\n").encode("ascii")
    for block in (head, response.body):
        if block:
            remaining = deadline - monotonic()
            if remaining <= 0:
                return
            connection.settimeout(remaining)
            connection.sendall(block)


class ReceiptHttpService:
    """Handle one fixed-length request per connection and one active processor call."""

    def __init__(
        self,
        token: bytes,
        *,
        processor: ReceiptProcessor | None = None,
        deadlines: Deadlines = Deadlines(),
        review_enabled: bool = False,
        session: ReceiptSession | None = None,
    ) -> None:
        if type(token) is not bytes or not 0 < len(token) <= 256 or not _BEARER_TOKEN.fullmatch(token):
            raise ValueError("Configure a valid bearer token.")
        if processor is not None and not callable(processor):
            raise TypeError("The injected receipt processor must be callable.")
        self._token = token
        self._processor = processor
        self._deadlines = deadlines
        self._active = Lock()
        self._stopping = Event()
        self._review_enabled = review_enabled
        self._session = session

    def stop(self) -> None:
        """Stop admitting work and cancel pending HTTP results."""
        self._stopping.set()
        if self._session is not None:
            self._token = b""

    def drain(self, timeout: float) -> bool:
        """Wait until the active processor has returned from teardown."""
        if not self._active.acquire(timeout=timeout):
            return False
        self._active.release()
        return True

    def _run_processor(
        self,
        processor: ReceiptProcessor,
        request: ReceiptRequest,
        context: ProcessingContext,
        results: Queue[_Response | None],
    ) -> None:
        response = None
        try:
            if not context.cancelled and not self._stopping.is_set():
                try:
                    response = _processor_response(processor, request, context)
                except BaseException:
                    # A provider exception can contain receipt data, including in its traceback.
                    response = _Response(HTTPStatus.INTERNAL_SERVER_ERROR)
        finally:
            self._active.release()
        if not context.cancelled:
            results.put_nowait(response)

    def _process(
        self, connection: socket, request: ReceiptRequest, deadline: float,
        overall_deadline: float | None = None,
    ) -> _Response:
        processor = self._processor
        if processor is None:
            return _Response(HTTPStatus.SERVICE_UNAVAILABLE)
        if monotonic() >= deadline:
            return _Response(HTTPStatus.GATEWAY_TIMEOUT)
        if not self._active.acquire(blocking=False):
            return _Response(HTTPStatus.TOO_MANY_REQUESTS)

        try:
            if self._stopping.is_set() or (self._session is not None and
                    not self._session.permits(overall_deadline, deadline)):
                self._active.release()
                return _Response(HTTPStatus.SERVICE_UNAVAILABLE)
            context = ProcessingContext(deadline, self._session, self._stopping if self._session else None)
            results: Queue[_Response | None] = Queue(maxsize=1)
            Thread(
                target=self._run_processor, args=(processor, request, context, results), daemon=True
            ).start()
        except Exception:
            self._active.release()
            return _Response(HTTPStatus.INTERNAL_SERVER_ERROR)

        try:
            while not self._stopping.is_set():
                if self._session is not None and not self._session.is_active():
                    return _Response(HTTPStatus.SERVICE_UNAVAILABLE)
                remaining = deadline - monotonic()
                if remaining <= 0:
                    return _Response(HTTPStatus.GATEWAY_TIMEOUT)
                try:
                    response = results.get_nowait()
                except Empty:
                    _check_peer(connection, min(_POLL_SECONDS, remaining))
                    continue
                if response is None:
                    raise _Disconnected
                return response
            raise _Disconnected
        finally:
            context._cancel.set()

    def handle_connection(self, connection: socket, *, port: int) -> None:
        started = monotonic()
        overall_deadline = started + self._deadlines.overall
        ingress_deadline = started + self._deadlines.ingress
        try:
            if self._stopping.is_set():
                return
            request = _read_request(connection, port, self._token, ingress_deadline,
                                    review_enabled=self._review_enabled, session=self._session,
                                    overall_deadline=overall_deadline)
            _check_peer(connection)
            if self._session is not None and not self._session.is_active():
                raise _Refusal(HTTPStatus.SERVICE_UNAVAILABLE)
            _validate_png(request.encoded_image, ingress_deadline)
            _check_peer(connection)
            if self._stopping.is_set():
                return
            processing_deadline = min(
                monotonic() + self._deadlines.processing, overall_deadline - self._deadlines.response_write
            )
            response = self._process(connection, request, processing_deadline, overall_deadline)
            del request
            _check_peer(connection)
            if response.status is HTTPStatus.OK and monotonic() >= processing_deadline:
                response = _Response(HTTPStatus.GATEWAY_TIMEOUT)
        except (_Disconnected, OSError):
            return
        except _Refusal as refusal:
            response = _Response(refusal.status)
        except Exception:
            response = _Response(HTTPStatus.INTERNAL_SERVER_ERROR)

        if self._stopping.is_set():
            return
        if (response.status is HTTPStatus.OK and self._session is not None
                and not self._session.permits(overall_deadline)):
            response = _Response(HTTPStatus.SERVICE_UNAVAILABLE)
        try:
            _write_response(
                connection, response, min(overall_deadline, monotonic() + self._deadlines.response_write)
            )
        except OSError:
            return


class _ConnectionHandler(BaseRequestHandler):
    def handle(self) -> None:
        self.server.service.handle_connection(self.request, port=self.server.server_address[1])


class _DevelopmentServer(ThreadingMixIn, TCPServer):
    def __init__(self, port: int, service: ReceiptHttpService) -> None:
        self.service = service
        self._connections = BoundedSemaphore(_HTTP_WORKERS)
        super().__init__(("127.0.0.1", port), _ConnectionHandler)

    def process_request(self, request: socket, client_address: tuple[str, int]) -> None:
        if not self._connections.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._connections.release()
            raise

    def process_request_thread(self, request: socket, client_address: tuple[str, int]) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._connections.release()

    def handle_error(self, request: socket, client_address: tuple[str, int]) -> None:
        """Keep socketserver from printing request, peer, or traceback details."""


def serve_development(service: ReceiptHttpService, *, port: int = DEFAULT_PORT) -> None:
    """Run the development listener on IPv4 loopback."""
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Port must be in the range 1 to 65535.")
    with _DevelopmentServer(port, service) as server:
        try:
            server.serve_forever()
        finally:
            service.stop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    defaults = Deadlines()
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--ingress-seconds", type=float, default=defaults.ingress)
    parser.add_argument("--processing-seconds", type=float, default=defaults.processing)
    parser.add_argument("--write-seconds", type=float, default=defaults.response_write)
    parser.add_argument("--overall-seconds", type=float, default=defaults.overall)
    options = parser.parse_args(argv)
    try:
        token = os.environ.get(TOKEN_ENV, "").encode("ascii")
        deadlines = Deadlines(
            ingress=options.ingress_seconds,
            processing=options.processing_seconds,
            response_write=options.write_seconds,
            overall=options.overall_seconds,
        )
        service = ReceiptHttpService(token, deadlines=deadlines)
        serve_development(service, port=options.port)
    except (ValueError, OSError):
        parser.error("Check the bearer token setting, deadlines, and loopback port.")
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
