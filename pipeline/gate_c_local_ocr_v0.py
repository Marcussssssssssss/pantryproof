"""One-use, host-local PNG admission for a trusted, injected OCR mock."""

from dataclasses import dataclass, field
from hashlib import sha256
from math import isfinite
from secrets import token_hex
from threading import Lock
from time import monotonic_ns
from typing import Callable
from weakref import ReferenceType, ref
import zlib

from pipeline.contracts import SourceProcessingStatus, SourceProvenance
from pipeline.ocr_adapter import AdaptedOcrSource, adapt_paddleocr_result


_WIDTH = 1100
_HEIGHT = 700
_ROW_BYTES = _WIDTH * 3
_PIXEL_BYTES = _ROW_BYTES * _HEIGHT
_SCANLINE_BYTES = (_ROW_BYTES + 1) * _HEIGHT
_MIN_ENCODED_BYTES = 58
_MAX_ENCODED_BYTES = 2_400_000
_MAX_IDAT_CHUNKS = 64
_MAX_IDAT_BYTES = _MAX_ENCODED_BYTES - 57
_MAX_LOGICAL_PNG_PAYLOAD_BYTES = 11_910_643
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_IHDR = b"\x00\x00\x04\x4c\x00\x00\x02\xbc\x08\x02\x00\x00\x00"
_VIEW_SHAPE = (_HEIGHT, _WIDTH, 3)
_VIEW_STRIDES = (_ROW_BYTES, 3, 1)
_TRANSFORM = "P03-RGB8-TO-BGR8-1"
_SOURCE_SYSTEM = "GATE_C_P03_MOCK"
_HEX = frozenset("0123456789abcdef")
_MAX_REGIONS = 128
_MAX_TEXT_CODEPOINTS = 256
_MAX_TEXT_BYTES = 1024
_MAX_TOTAL_CODEPOINTS = 16_384
_MAX_TOTAL_TEXT_BYTES = 49_152
_MAX_VERTICES = 8
_OPTIONAL_FIELDS = ("rec_scores", "rec_polys", "dt_polys", "rec_boxes")
_FIELDS = ("rec_texts", *_OPTIONAL_FIELDS)


class LocalOcrRefusal(ValueError):
    """A local refusal with a fixed, non-reflecting reason code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True, eq=False)
class MockOcrProfile:
    """An exact profile instance binds attempts to the fixed P03 mock lane."""

    profile_id: str = field(default="GATE_C_P03_LOCAL_MOCK_V0", init=False)
    transform_revision: str = field(default=_TRANSFORM, init=False)


class _TicketSeal:
    def __init__(self) -> None:
        self.original: ReferenceType[MockOcrAttempt] | None = None


@dataclass(frozen=True, slots=True, weakref_slot=True, eq=False, repr=False)
class MockOcrAttempt:
    request_id: str
    image_id: str
    receipt_id: str
    attempt_id: str
    profile: MockOcrProfile
    encoded_length: int
    encoded_sha256: str
    deadline_ns: int | None
    _issuer: object = field(repr=False)
    _seal: _TicketSeal = field(repr=False)


@dataclass(frozen=True, slots=True)
class MockOcrWitness:
    """The original gate-free source and its local, non-wire binding."""

    source: AdaptedOcrSource = field(repr=False)
    attempt: MockOcrAttempt = field(repr=False)
    rgb_sha256: str = field(repr=False)
    bgr_sha256: str = field(repr=False)


@dataclass(slots=True)
class _AttemptState:
    ticket: MockOcrAttempt
    claimed: bool = False
    dispatched: bool = False
    cancelled: bool = False
    finished: bool = False


class MockOcrOwner:
    """Own one current ticket and serialize dispatch, cancellation and publication."""

    def __init__(self, profile: MockOcrProfile) -> None:
        if type(profile) is not MockOcrProfile:
            raise LocalOcrRefusal("BINDING_MISMATCH")
        self._profile = profile
        self._issuer = object()
        self._lock = Lock()
        self._current: _AttemptState | None = None
        self._cleanup_failed = False

    def issue(
        self, *, encoded_length: int, encoded_sha256: str, deadline_ns: int | None = None
    ) -> MockOcrAttempt:
        """Bind independently supplied image pins to fresh, distinct identities.

        A supplied deadline is an absolute monotonic nanosecond value. Issuing a
        new ticket replaces the current ticket without interrupting an in-flight mock.
        """
        if (
            type(encoded_length) is not int
            or not _MIN_ENCODED_BYTES <= encoded_length <= _MAX_ENCODED_BYTES
            or type(encoded_sha256) is not str
            or len(encoded_sha256) != 64
            or not all(digit in _HEX for digit in encoded_sha256.lower())
            or (
                deadline_ns is not None
                and (type(deadline_ns) is not int or deadline_ns < 0)
            )
        ):
            raise LocalOcrRefusal("BINDING_MISMATCH")
        suffixes = tuple(token_hex(16) for _ in range(4))
        if len(set(suffixes)) != 4:
            raise LocalOcrRefusal("BINDING_MISMATCH")
        request, image, receipt, attempt = suffixes
        seal = _TicketSeal()
        ticket = MockOcrAttempt(
            f"req-{request}",
            f"img-{image}",
            f"rct-{receipt}",
            f"att-{attempt}",
            self._profile,
            encoded_length,
            encoded_sha256.lower(),
            deadline_ns,
            self._issuer,
            seal,
        )
        seal.original = ref(ticket)
        with self._lock:
            if self._cleanup_failed:
                raise LocalOcrRefusal("CLEANUP_FAILED")
            self._current = _AttemptState(ticket)
        return ticket

    def cancel(self, ticket: MockOcrAttempt) -> bool:
        """Order cancellation against dispatch and publication for this ticket."""
        with self._lock:
            state = self._current
            if state is None or state.ticket is not ticket or state.finished:
                return False
            state.cancelled = True
            return True

    def _claim(self, ticket: MockOcrAttempt, profile: MockOcrProfile) -> _AttemptState:
        with self._lock:
            if (
                type(ticket) is not MockOcrAttempt
                or ticket._issuer is not self._issuer
                or type(ticket._seal) is not _TicketSeal
                or type(ticket._seal.original) is not ReferenceType
                or ticket._seal.original() is not ticket
                or ticket.profile is not profile
                or profile is not self._profile
            ):
                raise LocalOcrRefusal("BINDING_MISMATCH")
            state = self._current
            if state is None or state.ticket is not ticket:
                raise LocalOcrRefusal("ATTEMPT_STALE")
            if state.claimed:
                raise LocalOcrRefusal("ATTEMPT_DUPLICATE")
            state.claimed = True
            return state

    def _refusal(self, state: _AttemptState) -> str | None:
        # Only called under the lock.
        if self._current is not state:
            return "ATTEMPT_STALE"
        if state.cancelled:
            return "ATTEMPT_CANCELLED"
        deadline = state.ticket.deadline_ns
        if deadline is not None and monotonic_ns() >= deadline:
            return "ATTEMPT_EXPIRED"
        if self._cleanup_failed:
            return "CLEANUP_FAILED"
        return None

    def _checkpoint(self, state: _AttemptState, *, dispatch: bool = False) -> None:
        with self._lock:
            reason = self._refusal(state)
            if reason is not None:
                raise LocalOcrRefusal(reason)
            if dispatch:
                if state.dispatched:
                    raise LocalOcrRefusal("ATTEMPT_DUPLICATE")
                state.dispatched = True

    def _finish(
        self, state: _AttemptState, *, ready: bool, cleanup_failed: bool
    ) -> str | None:
        with self._lock:
            state.finished = True
            if cleanup_failed:
                self._cleanup_failed = True
                return "CLEANUP_FAILED"
            if ready:
                return self._refusal(state)
            return None


def _check_encoded_input(image_bytes: bytes) -> None:
    if type(image_bytes) is not bytes:
        raise LocalOcrRefusal("INPUT_TYPE")
    if not _MIN_ENCODED_BYTES <= len(image_bytes) <= _MAX_ENCODED_BYTES:
        raise LocalOcrRefusal("INPUT_SIZE_LIMIT")


def _idat_payload(encoded: bytes) -> bytes:
    if not encoded.startswith(_PNG_SIGNATURE):
        raise LocalOcrRefusal("PNG_MALFORMED")

    with memoryview(encoded) as image:
        position = len(_PNG_SIGNATURE)
        first = True
        chunks: list[tuple[int, int]] = []
        idat_bytes = 0
        while True:
            if len(image) - position < 12:
                raise LocalOcrRefusal("PNG_MALFORMED")
            length = int.from_bytes(image[position:position + 4], "big")
            start = position + 8
            end = start + length
            if end + 4 > len(image):
                raise LocalOcrRefusal("PNG_MALFORMED")
            kind = image[position + 4:start]
            if first:
                if kind != b"IHDR" or length != 13:
                    raise LocalOcrRefusal("PNG_MALFORMED")
            elif kind == b"IDAT":
                if length == 0:
                    raise LocalOcrRefusal("PNG_MALFORMED")
                if len(chunks) == _MAX_IDAT_CHUNKS or idat_bytes + length > _MAX_IDAT_BYTES:
                    raise LocalOcrRefusal("PNG_CHUNK_LIMIT")
            elif kind != b"IEND" or length != 0 or not chunks:
                raise LocalOcrRefusal("PNG_MALFORMED")

            expected_crc = int.from_bytes(image[end:end + 4], "big")
            if zlib.crc32(image[position + 4:end]) != expected_crc:
                raise LocalOcrRefusal("PNG_CRC_MISMATCH")

            if first:
                if image[start:end] != _IHDR:
                    raise LocalOcrRefusal("PNG_PROFILE_UNSUPPORTED")
                first = False
            elif kind == b"IEND":
                if end + 4 != len(image):
                    raise LocalOcrRefusal("PNG_TRAILING_DATA")
                return b"".join(image[left:right] for left, right in chunks)
            else:
                chunks.append((start, end))
                idat_bytes += length
            position = end + 4


def _inflate_png(encoded: bytes) -> bytes:
    compressed = _idat_payload(encoded)
    # Charge the compressed copy and a full joined-input allowance for each
    # exposed zlib tail. This is a logical byte bound, outside native workspace.
    cap = _SCANLINE_BYTES + 1
    if len(encoded) + 3 * len(compressed) + cap > _MAX_LOGICAL_PNG_PAYLOAD_BYTES:
        raise LocalOcrRefusal("PNG_INFLATE_LIMIT")
    inflater = zlib.decompressobj(zlib.MAX_WBITS)
    try:
        inflated = inflater.decompress(compressed, cap)
    except zlib.error:
        raise LocalOcrRefusal("PNG_ZLIB_INVALID") from None
    if len(inflated) > _SCANLINE_BYTES:
        raise LocalOcrRefusal("PNG_INFLATE_LIMIT")
    if not inflater.eof:
        raise LocalOcrRefusal("PNG_INFLATE_TRUNCATED")
    if inflater.unused_data or inflater.unconsumed_tail:
        raise LocalOcrRefusal("PNG_ZLIB_TRAILING_DATA")
    if len(inflated) != _SCANLINE_BYTES:
        raise LocalOcrRefusal("PNG_INFLATE_LENGTH")
    return inflated


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    left_distance = abs(estimate - left)
    above_distance = abs(estimate - above)
    diagonal_distance = abs(estimate - upper_left)
    if left_distance <= above_distance and left_distance <= diagonal_distance:
        return left
    if above_distance <= diagonal_distance:
        return above
    return upper_left


def _restore_row(
    filtered: memoryview, kind: int, previous: bytearray, row: bytearray
) -> None:
    if kind == 0:
        row[:] = filtered
        return
    if kind > 4:
        raise LocalOcrRefusal("PNG_FILTER_INVALID")
    for column, value in enumerate(filtered):
        left = row[column - 3] if column >= 3 else 0
        above = previous[column]
        if kind == 1:
            predictor = left
        elif kind == 2:
            predictor = above
        elif kind == 3:
            predictor = (left + above) // 2
        else:
            upper_left = previous[column - 3] if column >= 3 else 0
            predictor = _paeth(left, above, upper_left)
        row[column] = (value + predictor) & 255


def _build_bgr(scanlines: bytes) -> tuple[bytearray, str]:
    rgb_hash = sha256()
    previous = bytearray(_ROW_BYTES)
    current = bytearray(_ROW_BYTES)
    bgr = bytearray(_PIXEL_BYTES)
    with memoryview(scanlines) as data:
        for y in range(_HEIGHT):
            offset = y * (_ROW_BYTES + 1)
            row_start = y * _ROW_BYTES
            _restore_row(data[offset + 1:offset + 1 + _ROW_BYTES], data[offset], previous, current)
            rgb_hash.update(current)
            for column in range(0, _ROW_BYTES, 3):
                target = row_start + column
                bgr[target] = current[column + 2]
                bgr[target + 1] = current[column + 1]
                bgr[target + 2] = current[column]
            previous, current = current, previous
    return bgr, rgb_hash.hexdigest()


def _decode_png(encoded: bytes) -> tuple[bytes, str, str]:
    _check_encoded_input(encoded)
    staging, rgb_digest = _build_bgr(_inflate_png(encoded))
    # Scanlines and row buffers are out of scope before the final copy.
    pixels = bytes(staging)
    return pixels, rgb_digest, sha256(pixels).hexdigest()


def _verify_view(pixels: bytes, view: memoryview, digest: str) -> None:
    try:
        valid = (
            type(pixels) is bytes
            and view.obj is pixels
            and view.readonly
            and view.format == "B"
            and view.shape == _VIEW_SHAPE
            and view.strides == _VIEW_STRIDES
            and view.nbytes == _PIXEL_BYTES
            and sha256(view).hexdigest() == digest
        )
    except (ValueError, BufferError):
        valid = False
    if not valid:
        raise LocalOcrRefusal("MOCK_EXECUTION_FAILED")


def _release_view(view: memoryview) -> None:
    view.release()


def _check_mock_text(texts: tuple) -> None:
    codepoints = utf8_bytes = 0
    for item in texts:
        if type(item) is not str or not item:
            raise LocalOcrRefusal("MOCK_RESULT_MALFORMED")
        length = len(item)
        codepoints += length
        if length > _MAX_TEXT_CODEPOINTS or codepoints > _MAX_TOTAL_CODEPOINTS:
            raise LocalOcrRefusal("MOCK_RESULT_LIMIT")
        if not item.strip():
            raise LocalOcrRefusal("MOCK_RESULT_MALFORMED")
        try:
            size = len(item.encode("utf-8", errors="strict"))
        except UnicodeEncodeError:
            size = None
        if size is None:
            raise LocalOcrRefusal("MOCK_RESULT_MALFORMED") from None
        utf8_bytes += size
        if size > _MAX_TEXT_BYTES or utf8_bytes > _MAX_TOTAL_TEXT_BYTES:
            raise LocalOcrRefusal("MOCK_RESULT_LIMIT")


def _coordinate(value: object, maximum: int) -> None:
    kind = type(value)
    # Integer range is checked without converting an arbitrary integer to float.
    if kind not in (int, float) or (kind is float and not isfinite(value)):
        raise LocalOcrRefusal("MOCK_RESULT_MALFORMED")
    if not 0 <= value <= maximum:
        raise LocalOcrRefusal("MOCK_RESULT_MALFORMED")


def _check_geometry(region: object, *, box: bool) -> bool:
    if region is None:
        return False
    if type(region) is not tuple:
        raise LocalOcrRefusal("MOCK_RESULT_MALFORMED")
    if not region:
        return False
    if box:
        if len(region) != 4:
            raise LocalOcrRefusal("MOCK_RESULT_MALFORMED")
        x_min, y_min, x_max, y_max = region
        _coordinate(x_min, _WIDTH)
        _coordinate(x_max, _WIDTH)
        _coordinate(y_min, _HEIGHT)
        _coordinate(y_max, _HEIGHT)
        if x_min >= x_max or y_min >= y_max:
            raise LocalOcrRefusal("MOCK_RESULT_MALFORMED")
    else:
        if len(region) > _MAX_VERTICES:
            raise LocalOcrRefusal("MOCK_RESULT_LIMIT")
        if len(region) < 3:
            raise LocalOcrRefusal("MOCK_RESULT_MALFORMED")
        for pair in region:
            if type(pair) is not tuple or len(pair) != 2:
                raise LocalOcrRefusal("MOCK_RESULT_MALFORMED")
            _coordinate(pair[0], _WIDTH)
            _coordinate(pair[1], _HEIGHT)
    return True


def _check_mock_result(result: object) -> dict:
    if type(result) is not tuple:
        raise LocalOcrRefusal("MOCK_RESULT_MALFORMED")
    if len(result) > 1:
        raise LocalOcrRefusal("MOCK_RESULT_LIMIT")
    if not result or type(result[0]) is not dict:
        raise LocalOcrRefusal("MOCK_RESULT_MALFORMED")
    mapping = result[0]
    if len(mapping) > len(_FIELDS):
        raise LocalOcrRefusal("MOCK_RESULT_LIMIT")
    if any(type(key) is not str or len(key) > 10 or key not in _FIELDS for key in mapping):
        raise LocalOcrRefusal("MOCK_RESULT_MALFORMED")
    texts = mapping.get("rec_texts")
    if type(texts) is not tuple:
        raise LocalOcrRefusal("MOCK_RESULT_MALFORMED")
    count = len(texts)
    if count > _MAX_REGIONS:
        raise LocalOcrRefusal("MOCK_RESULT_LIMIT")
    for field_name in _OPTIONAL_FIELDS:
        values = mapping.get(field_name)
        if values is None:
            continue
        if type(values) is not tuple:
            raise LocalOcrRefusal("MOCK_RESULT_MALFORMED")
        if len(values) > _MAX_REGIONS:
            raise LocalOcrRefusal("MOCK_RESULT_LIMIT")
        if len(values) != count:
            raise LocalOcrRefusal("MOCK_RESULT_MALFORMED")

    _check_mock_text(texts)
    scores, recognition, detection, boxes = (mapping.get(name) for name in _OPTIONAL_FIELDS)
    for index in range(count):
        if scores is not None:
            score = scores[index]
            if score is not None and (type(score) is not float or not 0.0 <= score <= 1.0):
                raise LocalOcrRefusal("MOCK_SCORE_INVALID")
        # Check every supplied alternative, even if a higher-priority one is usable.
        rec_ok = _check_geometry(recognition[index], box=False) if recognition is not None else False
        det_ok = _check_geometry(detection[index], box=False) if detection is not None else False
        box_ok = _check_geometry(boxes[index], box=True) if boxes is not None else False
        if not (rec_ok or det_ok or box_ok):
            raise LocalOcrRefusal("MOCK_RESULT_MALFORMED")
    return mapping


def _check_source(source: AdaptedOcrSource, attempt: MockOcrAttempt) -> None:
    if (
        type(source) is not AdaptedOcrSource
        or source.receipt_id is not attempt.receipt_id
        or source.image_id is not attempt.image_id
        or source.processing_status is not SourceProcessingStatus.OCR_COMPLETED
        or type(source.provenance) is not SourceProvenance
        or source.provenance.source_system is not _SOURCE_SYSTEM
        or source.provenance.source_reference is not attempt.attempt_id
        or source.provenance.content_sha256 is not None
    ):
        raise LocalOcrRefusal("ADAPTED_SOURCE_MISMATCH")


def run_gate_c_local_ocr_v0(
    *,
    image_bytes: bytes,
    owner: MockOcrOwner,
    attempt: MockOcrAttempt,
    profile: MockOcrProfile,
    mock_engine: Callable[[memoryview], object],
) -> MockOcrWitness:
    """Run an injected mock once and return its original gate-free adapter output."""
    state = view = pixels = raw = mapping = source = witness = None
    refusal = None
    try:
        _check_encoded_input(image_bytes)
        if type(owner) is not MockOcrOwner or not callable(mock_engine):
            raise LocalOcrRefusal("BINDING_MISMATCH")
        state = owner._claim(attempt, profile)
        owner._checkpoint(state)
        if len(image_bytes) != attempt.encoded_length:
            raise LocalOcrRefusal("INPUT_LENGTH_MISMATCH")
        if sha256(image_bytes).hexdigest() != attempt.encoded_sha256:
            raise LocalOcrRefusal("INPUT_DIGEST_MISMATCH")

        pixels, rgb_digest, bgr_digest = _decode_png(image_bytes)
        view = memoryview(pixels).cast("B", shape=_VIEW_SHAPE)
        _verify_view(pixels, view, bgr_digest)
        owner._checkpoint(state, dispatch=True)
        mock_failed = False
        try:
            raw = mock_engine(view)
        except Exception:
            mock_failed = True
        owner._checkpoint(state)
        if mock_failed:
            raise LocalOcrRefusal("MOCK_EXECUTION_FAILED")
        _verify_view(pixels, view, bgr_digest)
        mapping = _check_mock_result(raw)
        owner._checkpoint(state)
        try:
            source = adapt_paddleocr_result(
                mapping,
                receipt_id=attempt.receipt_id,
                image_id=attempt.image_id,
                source_system=_SOURCE_SYSTEM,
                source_reference=attempt.attempt_id,
                processing_status=SourceProcessingStatus.OCR_COMPLETED,
            )
        except Exception:
            raise LocalOcrRefusal("ADAPTATION_FAILED") from None
        _check_source(source, attempt)
        witness = MockOcrWitness(source, attempt, rgb_digest, bgr_digest)
    except LocalOcrRefusal as error:
        refusal = error.code
    finally:
        cleanup_failed = False
        try:
            if view is not None:
                _release_view(view)
        except Exception:
            cleanup_failed = True
        finally:
            view = pixels = raw = mapping = source = image_bytes = None
            if state is not None:
                outcome = owner._finish(
                    state, ready=refusal is None and witness is not None, cleanup_failed=cleanup_failed
                )
                if outcome is not None:
                    refusal = outcome

    if refusal is not None:
        witness = None
        raise LocalOcrRefusal(refusal) from None
    return witness
