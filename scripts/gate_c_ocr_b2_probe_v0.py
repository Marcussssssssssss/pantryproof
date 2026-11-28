"""Gate C P06 local witness probe.

A trusted host implementation must supply a registered, isolated worker and
bounded private IPC. This module has no default launcher or native approval.
Only the supervisor's run method publishes a FIXTURE payload.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum, auto
from hashlib import sha256
from math import isfinite
from pathlib import Path
from secrets import token_hex
from threading import Lock
from time import monotonic_ns
from typing import Protocol
import json
import re
import sys

from pipeline import backend_generated_paddleocr_v0 as handoff
from pipeline import backend_synthetic_coordinator_v0 as coordinator
from pipeline import ocr_adapter
from pipeline.contracts import PolicyState, SourceEvidenceDecision, SourceProcessingStatus, SourceProvenance
from pipeline.gate_c_local_ocr_v0 import LocalOcrRefusal, _decode_png
from pipeline.presentation_v1.conformance import (
    ConformanceViolation, decode_and_validate_presentation_v1,
)
from pipeline.presentation_v1.synthetic_failure_projection_v0 import SyntheticFailureContextV0


_DIGEST = re.compile(r"[0-9a-f]{64}")
_MODEL_FILES = ("inference.json", "inference.pdiparams", "inference.yml")
_DETECTOR = "PP-OCRv6_medium_det"
_RECOGNIZER = "PP-OCRv6_medium_rec"
_REASON = "Synthetic source structure was unavailable."
_RESULT_FIELDS = frozenset({
    "input_path", "page_index", "doc_preprocessor_res", "model_settings", "dt_polys",
    "text_det_params", "text_type", "text_rec_score_thresh", "return_word_box",
    "rec_texts", "rec_scores", "rec_polys", "rec_boxes", "vis_fonts",
})


class Refusal(str, Enum):
    PROFILE_UNAPPROVED = "PROFILE_UNAPPROVED"
    ATTEMPT_FOREIGN = "ATTEMPT_FOREIGN"
    ATTEMPT_STALE = "ATTEMPT_STALE"
    ATTEMPT_DUPLICATE = "ATTEMPT_DUPLICATE"
    ATTEMPT_CANCELLED = "ATTEMPT_CANCELLED"
    ATTEMPT_EXPIRED = "ATTEMPT_EXPIRED"
    INPUT_INVALID = "INPUT_INVALID"
    ENCODED_IDENTITY_MISMATCH = "ENCODED_IDENTITY_MISMATCH"
    PNG_REJECTED = "PNG_REJECTED"
    DECODED_IDENTITY_MISMATCH = "DECODED_IDENTITY_MISMATCH"
    PROVIDER_INPUT_MISMATCH = "PROVIDER_INPUT_MISMATCH"
    PROVIDER_EXECUTION_FAILED = "PROVIDER_EXECUTION_FAILED"
    PROVIDER_RESULT_COUNT = "PROVIDER_RESULT_COUNT"
    PROVIDER_IMAGE_MISMATCH = "PROVIDER_IMAGE_MISMATCH"
    PROVIDER_RESULT_INVALID = "PROVIDER_RESULT_INVALID"
    PROVIDER_RESULT_LIMIT = "PROVIDER_RESULT_LIMIT"
    ADAPTER_REFUSED = "ADAPTER_REFUSED"
    GATE_RESERVATION_REFUSED = "GATE_RESERVATION_REFUSED"
    P04_REFUSED = "P04_REFUSED"
    ATTACHMENT_REFUSED = "ATTACHMENT_REFUSED"
    B2_REFUSED = "B2_REFUSED"
    V1_REFUSED = "V1_REFUSED"
    ISOLATION_VIOLATION = "ISOLATION_VIOLATION"
    CLEANUP_UNCONFIRMED = "CLEANUP_UNCONFIRMED"


class _Stop(Exception):
    def __init__(self, reason: Refusal):
        self.reason = reason
        super().__init__(reason.value)


def _need(condition, reason):
    if not condition:
        raise _Stop(reason)


def _digest(value):
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _positive(value):
    return type(value) is int and 0 < value <= (1 << 63) - 1


@dataclass(frozen=True, slots=True, repr=False)
class FilePin:
    path: str
    length: int
    sha256: str


@dataclass(frozen=True, slots=True, repr=False)
class NativeProfile:
    """Independent host approval must verify every pin and enforce every limit."""
    runtime: tuple[FilePin, ...]
    detector: tuple[FilePin, ...]
    recognizer: tuple[FilePin, ...]
    configuration: FilePin
    controls: FilePin
    cpu_threads: int
    run_ns: int
    termination_grace_ns: int
    memory_bytes: int
    scratch_path: str
    scratch_bytes: int
    ipc_bytes: int
    candidate_bytes: int


class Witness(Enum):
    POSITIVE = auto()
    BLANK = auto()


@dataclass(frozen=True, slots=True, repr=False)
class Asset:
    witness: Witness
    length: int
    encoded: str
    rgb: str
    bgr: str


def _absolute(value):
    if type(value) is not str or "\0" in value:
        return False
    path = Path(value)
    return path.is_absolute() and not path.drive.startswith("\\\\") and ".." not in path.parts


def _file_pin(pin):
    return (type(pin) is FilePin and _absolute(pin.path) and
            _positive(pin.length) and _digest(pin.sha256))


def _model_pins(pins, name):
    return (type(pins) is tuple and len(pins) == len(_MODEL_FILES) and
            all(_file_pin(pin) for pin in pins) and
            {Path(pin.path).name for pin in pins} == set(_MODEL_FILES) and
            len({Path(pin.path).parent for pin in pins}) == 1 and
            Path(pins[0].path).parent.name == name)


def _asset_ok(asset):
    return (type(asset) is Asset and type(asset.witness) is Witness and
            type(asset.length) is int and 58 <= asset.length <= 2_400_000 and
            all(_digest(x) for x in (asset.encoded, asset.rgb, asset.bgr)))


def _profile_ok(profile, assets):
    return (
        type(profile) is NativeProfile and type(assets) is tuple and len(assets) == 2
        and all(_asset_ok(asset) for asset in assets)
        and {asset.witness for asset in assets} == {Witness.POSITIVE, Witness.BLANK}
        and assets[0].encoded != assets[1].encoded
        and assets[0].rgb != assets[1].rgb and assets[0].bgr != assets[1].bgr
        and type(profile.runtime) is tuple and bool(profile.runtime)
        and all(_file_pin(pin) for pin in profile.runtime)
        and _model_pins(profile.detector, _DETECTOR)
        and _model_pins(profile.recognizer, _RECOGNIZER)
        and _file_pin(profile.configuration) and _file_pin(profile.controls)
        and _absolute(profile.scratch_path)
        and all(_positive(x) for x in (profile.cpu_threads, profile.run_ns,
                                      profile.termination_grace_ns, profile.memory_bytes,
                                      profile.scratch_bytes, profile.ipc_bytes, profile.candidate_bytes))
        and profile.ipc_bytes >= profile.candidate_bytes + 768
    )


@dataclass(frozen=True, slots=True, repr=False)
class Ticket:
    request_id: str
    image_id: str
    receipt_id: str
    attempt_id: str


@dataclass(frozen=True, slots=True, repr=False)
class _Assignment:
    ticket: Ticket
    asset: Asset
    assets: tuple[Asset, Asset]
    profile: NativeProfile
    deadline: int
    gate_id: str

    def key(self):
        t = self.ticket
        profile_digest = sha256(json.dumps(asdict(self.profile), sort_keys=True,
                                           separators=(",", ":")).encode("utf-8")).hexdigest()
        return "|".join((t.request_id, t.image_id, t.receipt_id, t.attempt_id,
                         self.gate_id, str(self.asset.length), self.asset.encoded,
                         self.asset.rgb, self.asset.bgr, profile_digest,
                         str(self.deadline))).encode("ascii") + b"|"


class _Channel(Protocol):
    # These operations enforce the deadline and byte bound at the transport
    # boundary, before materializing a frame. None is EOF, never a timeout.
    def send(self, frame: bytes, deadline: int) -> None: ...
    def receive(self, maximum: int, deadline: int) -> bytes | None: ...


class WorkerHandle(_Channel, Protocol):
    # A trusted host retains the real process handle. prepare() must be inert.
    # start() must associate even a partial launch with this same handle.
    def start(self, assignment: _Assignment, image_bytes: bytes, deadline: int) -> None: ...
    def wait_exited(self, deadline: int) -> bool: ...
    def exit_code(self) -> int | None: ...
    def interrupt(self) -> None: ...
    def terminate(self, deadline: int) -> None: ...
    def cleanup(self, deadline: int) -> bool: ...
    # Host-side sticky observation, valid even if the child caught an error.
    def isolation_failed(self) -> bool: ...


class WorkerHost(Protocol):
    # Type/shape validation is not approval. This authority must independently
    # authorize this exact profile/assets and verify pins, custody and controls.
    def authorize(self, profile: NativeProfile, assets: tuple[Asset, Asset]) -> bool: ...
    def prepare(self, profile: NativeProfile, deadline: int) -> WorkerHandle: ...


class _State(Enum):
    ISSUED = auto()
    CLAIMED = auto()
    DISPATCHED = auto()
    GATE_GRANTED = auto()
    CANDIDATE_HELD = auto()
    TERMINATED_CLEAN = auto()
    REFUSED = auto()
    PUBLISHED = auto()


@dataclass(slots=True, eq=False, repr=False)
class _Slot:
    ticket: Ticket
    asset: Asset
    gate_id: str
    state: _State = _State.ISSUED
    cancelled: bool = False


@dataclass(frozen=True, slots=True, repr=False)
class ProbeResult:
    refusal: Refusal | None
    payload: bytes | None = None


def _encoded(image, asset):
    _need(type(image) is bytes and 58 <= len(image) <= 2_400_000, Refusal.INPUT_INVALID)
    _need(len(image) == asset.length and sha256(image).hexdigest() == asset.encoded,
          Refusal.ENCODED_IDENTITY_MISMATCH)


def _pixels(image, asset):
    _encoded(image, asset)
    try:
        pixels, rgb, bgr = _decode_png(image)
    except LocalOcrRefusal:
        raise _Stop(Refusal.PNG_REJECTED) from None
    _need(type(pixels) is bytes and len(pixels) == 2_310_000 and
          rgb == asset.rgb and bgr == asset.bgr and sha256(pixels).hexdigest() == asset.bgr,
          Refusal.DECODED_IDENTITY_MISMATCH)
    return pixels


def _array_ok(array, backing, digest, np):
    return (type(array) is np.ndarray and array.dtype == np.dtype("uint8") and
            array.shape == (700, 1100, 3) and array.strides == (3300, 3, 1) and
            array.nbytes == 2_310_000 and array.flags.c_contiguous and not array.flags.writeable
            and array.base is backing and sha256(memoryview(array)).hexdigest() == digest)


def _record(provider, array, result_type):
    try:
        iterator = iter(provider.predict_iter(
            array, use_doc_orientation_classify=False, use_doc_unwarping=False,
            use_textline_orientation=False, return_word_box=False,
        ))
    except Exception:
        return None, None, Refusal.PROVIDER_EXECUTION_FAILED

    try:
        try:
            result = next(iterator)
        except StopIteration:
            return iterator, None, Refusal.PROVIDER_RESULT_COUNT
        if isinstance(result, dict) and "error" in result:
            return iterator, None, Refusal.PROVIDER_EXECUTION_FAILED
        if type(result) is not result_type or not isinstance(result, dict):
            return iterator, None, Refusal.PROVIDER_RESULT_INVALID
        try:
            next(iterator)
        except StopIteration:
            return iterator, result, None
        return iterator, None, Refusal.PROVIDER_RESULT_COUNT
    except Exception:
        return iterator, None, Refusal.PROVIDER_EXECUTION_FAILED


def _association(record, array):
    process = record.get("doc_preprocessor_res")
    settings = record.get("model_settings")
    _need("input_path" in record and record["input_path"] is None and
          "page_index" in record and record["page_index"] is None and
          type(process) is dict and process.get("output_img") is array and
          type(settings) is dict and settings.get("use_doc_preprocessor") is False and
          settings.get("use_textline_orientation") is False and
          record.get("return_word_box") is False, Refusal.PROVIDER_IMAGE_MISMATCH)


def _polygon(value, np):
    if type(value) is np.ndarray:
        _need(value.ndim == 2 and value.shape[1] == 2 and value.dtype == np.dtype("int16"),
              Refusal.PROVIDER_RESULT_INVALID)
    else:
        _need(type(value) in (list, tuple), Refusal.PROVIDER_RESULT_INVALID)
    _need(len(value) <= 8, Refusal.PROVIDER_RESULT_LIMIT)
    _need(len(value) >= 3, Refusal.PROVIDER_RESULT_INVALID)
    points = value.tolist() if type(value) is np.ndarray else value
    for point in points:
        _need(type(point) in (list, tuple) and len(point) == 2, Refusal.PROVIDER_RESULT_INVALID)
        for coordinate, limit in zip(point, (1100, 700)):
            _need(type(coordinate) in (int, float) and 0 <= coordinate <= limit,
                  Refusal.PROVIDER_RESULT_INVALID)
    return points


def _recognition(record, np):
    names = ("rec_texts", "rec_scores", "rec_polys")
    # The pinned result has no partial-success or additional status fields.
    _need(len(record) <= len(_RESULT_FIELDS) and
          all(type(key) is str and key in _RESULT_FIELDS for key in record),
          Refusal.PROVIDER_RESULT_INVALID)
    texts, scores, polygons = (record.get(name) for name in names)
    _need(all(type(x) is list for x in (texts, scores, polygons)),
          Refusal.PROVIDER_RESULT_INVALID)
    _need(max(len(texts), len(scores), len(polygons)) <= 128, Refusal.PROVIDER_RESULT_LIMIT)
    _need(len(texts) == len(scores) == len(polygons), Refusal.PROVIDER_RESULT_INVALID)
    total_chars = total_bytes = total_points = 0
    source_polygons = []
    for text, score, polygon in zip(texts, scores, polygons):
        _need(type(text) is str, Refusal.PROVIDER_RESULT_INVALID)
        total_chars += len(text)
        _need(len(text) <= 256 and total_chars <= 16_384, Refusal.PROVIDER_RESULT_LIMIT)
        _need(bool(text.strip()), Refusal.PROVIDER_RESULT_INVALID)
        try:
            length = len(text.encode("utf-8", errors="strict"))
        except UnicodeError:
            raise _Stop(Refusal.PROVIDER_RESULT_INVALID) from None
        total_bytes += length
        _need(length <= 1024 and total_bytes <= 49_152, Refusal.PROVIDER_RESULT_LIMIT)
        _need(score is None or (type(score) is float and isfinite(score)), Refusal.PROVIDER_RESULT_INVALID)
        checked = _polygon(polygon, np)
        total_points += len(checked)
        _need(total_points <= 1024, Refusal.PROVIDER_RESULT_LIMIT)
        source_polygons.append(checked)
    return dict(zip(names, (texts, scores, source_polygons)))


def _verify_adapted_source(source, recognized, ticket, provenance):
    _need(type(source) is ocr_adapter.AdaptedOcrSource and
          source.receipt_id == ticket.receipt_id and source.image_id == ticket.image_id and
          source.processing_status is SourceProcessingStatus.OCR_COMPLETED and
          source.provenance is provenance and type(source.tokens) is tuple and
          len(source.tokens) == len(recognized["rec_texts"]), Refusal.ADAPTER_REFUSED)
    for index, (token, text, score, polygon) in enumerate(zip(
        source.tokens, recognized["rec_texts"], recognized["rec_scores"], recognized["rec_polys"],
        strict=True,
    )):
        _need(token.receipt_id == ticket.receipt_id and
              token.token_id == f"{ticket.receipt_id}:paddleocr:{index:06d}" and
              token.original_text == text and token.raw_confidence == score and
              tuple((p.x, p.y) for p in token.polygon) == tuple(map(tuple, polygon)),
              Refusal.ADAPTER_REFUSED)


_COORDINATOR_REFUSALS = {
    coordinator.SyntheticCoordinatorRejectionReasonV0.INVALID_INPUT: Refusal.ADAPTER_REFUSED,
    coordinator.SyntheticCoordinatorRejectionReasonV0.INVALID_GATE_RESULT: Refusal.P04_REFUSED,
    coordinator.SyntheticCoordinatorRejectionReasonV0.GATE_EXCEPTION: Refusal.P04_REFUSED,
    coordinator.SyntheticCoordinatorRejectionReasonV0.ATTACHMENT_REJECTED: Refusal.ATTACHMENT_REFUSED,
    coordinator.SyntheticCoordinatorRejectionReasonV0.B2_EXCEPTION: Refusal.B2_REFUSED,
    coordinator.SyntheticCoordinatorRejectionReasonV0.INVALID_B2_RESULT: Refusal.B2_REFUSED,
}
_HANDOFF_REFUSALS = {
    handoff.GeneratedPaddleOcrRefusalV0.INVALID_CONTEXT: Refusal.ADAPTER_REFUSED,
    handoff.GeneratedPaddleOcrRefusalV0.OCR_INPUT_REJECTED: Refusal.ADAPTER_REFUSED,
    handoff.GeneratedPaddleOcrRefusalV0.GATE_CONTEXT_REJECTED: Refusal.GATE_RESERVATION_REFUSED,
    handoff.GeneratedPaddleOcrRefusalV0.EVIDENCE_CHANGED: Refusal.ATTACHMENT_REFUSED,
}


def _frame(kind, assignment, body=b""):
    return kind + assignment.key() + body


def _read(channel, assignment):
    message = channel.receive(assignment.profile.ipc_bytes, assignment.deadline)
    if message is None:
        return None, b""
    key = assignment.key()
    _need(type(message) is bytes and 1 + len(key) <= len(message) <= assignment.profile.ipc_bytes
          and message[1:1 + len(key)] == key, Refusal.ATTEMPT_FOREIGN)
    return message[:1], message[1 + len(key):]


def _request(channel, assignment, command, reply, reason):
    try:
        channel.send(_frame(command, assignment), assignment.deadline)
        kind, body = _read(channel, assignment)
        _need(kind == command and body == reply, reason)
    except Exception:
        raise _Stop(reason) from None


def _verify_trace(composed, source):
    trace = composed.trace
    evidence, b2 = trace.source_evidence, trace.b2_result
    original_gate = trace.gate_result
    _need(trace.adapted_source is source and original_gate is not None and
          evidence is not None and
          evidence.gate_result is original_gate and evidence.tokens is source.tokens and
          evidence.provenance is source.provenance and evidence.receipt_id == source.receipt_id and
          evidence.image_id == source.image_id and evidence.processing_status is source.processing_status,
          Refusal.ATTACHMENT_REFUSED)
    _need(b2 is not None, Refusal.B2_REFUSED)
    output = b2.receipt_output
    if original_gate.decision is SourceEvidenceDecision.SUFFICIENT:
        _need(output is not None and output.source_evidence is evidence and
              b2.pre_resolution_disposition is None, Refusal.B2_REFUSED)
    else:
        fallback = b2.pre_resolution_disposition
        _need(output is None and fallback is not None and
              fallback.state is PolicyState.FALLBACK_NO_UPDATE and
              fallback.gate_result is original_gate, Refusal.B2_REFUSED)


def _compose(recognized, assignment, channel):
    ticket = assignment.ticket
    context = SyntheticFailureContextV0(ticket.request_id, ticket.image_id,
                                        ticket.attempt_id[4:], "FIXTURE")
    provenance = SourceProvenance("GATE_C_P06_GENERATED_OCR", ticket.image_id)
    source = None
    gate_refusal = None
    touched = False

    def validate_source(adapted):
        nonlocal source
        _verify_adapted_source(adapted, recognized, ticket, provenance)
        source = adapted

    def reserve_gate():
        nonlocal gate_refusal, touched
        try:
            _need(not touched, Refusal.GATE_RESERVATION_REFUSED)
            touched = True
            _request(channel, assignment, b"G", assignment.gate_id.encode("ascii"),
                     Refusal.GATE_RESERVATION_REFUSED)
        except _Stop as exc:
            gate_refusal = exc.reason
            raise

    # Count calls to the pinned implementations without replacing project globals.
    stages = (coordinator.attach_gate_result.__code__, coordinator.extract_b2.__code__,
              coordinator.project_retained_b2_fixture_presentation_v1.__code__)
    counts = [0, 0, 0]

    def observe(frame, event, _arg):
        if event == "call" and frame.f_code in stages:
            counts[stages.index(frame.f_code)] += 1

    _need(sys.getprofile() is None, Refusal.PROFILE_UNAPPROVED)
    sys.setprofile(observe)
    try:
        composed = handoff.process_generated_paddleocr_result_v0(
            result=recognized, receipt_id=ticket.receipt_id, result_request_id=ticket.request_id,
            result_image_id=ticket.image_id, provenance=provenance, gate_result_id=assignment.gate_id,
            context=context, validate_source=validate_source, reserve_gate=reserve_gate,
            producer_id="GATE_C_P06_OCR_B2_V0",
        )
    finally:
        sys.setprofile(None)

    if gate_refusal is not None:
        raise _Stop(gate_refusal)
    if type(composed) is handoff.GeneratedPaddleOcrRefusalV0:
        raise _Stop(_HANDOFF_REFUSALS[composed])
    if type(composed.result) is coordinator.SyntheticCoordinatorRejectionV0:
        raise _Stop(_COORDINATOR_REFUSALS.get(composed.result.reason, Refusal.V1_REFUSED))
    _need(type(composed.result) is bytes, Refusal.V1_REFUSED)
    _verify_trace(composed, source)
    _need(touched and composed.trace.gate_result.gate_result_id == assignment.gate_id and
          counts == [1, 1, 1], Refusal.V1_REFUSED)
    return bytes((1, 1, *counts)) + composed.result


def _candidate(candidate, assignment):
    _need(len(candidate) > 5 and candidate[:5] == b"\x01" * 5 and
          len(candidate) - 5 <= assignment.profile.candidate_bytes, Refusal.V1_REFUSED)
    t = assignment.ticket
    payload = candidate[5:]
    try:
        dto = decode_and_validate_presentation_v1(
            payload, expected_request_id=t.request_id, expected_image_id=t.image_id,
            consumer_mode="FIXTURE",
        )
        for actual, expected_code in ((t.request_id, "REJECT_REQUEST_ID_MISMATCH"),
                                      (t.image_id, "REJECT_IMAGE_ID_MISMATCH")):
            wrong = actual[:-1] + ("0" if actual[-1] != "0" else "1")
            try:
                decode_and_validate_presentation_v1(
                    payload, expected_request_id=wrong if actual == t.request_id else t.request_id,
                    expected_image_id=wrong if actual == t.image_id else t.image_id,
                    consumer_mode="FIXTURE",
                )
            except ConformanceViolation as exc:
                _need(exc.code == expected_code, Refusal.V1_REFUSED)
            else:
                raise _Stop(Refusal.V1_REFUSED)
    except ConformanceViolation:
        raise _Stop(Refusal.V1_REFUSED) from None

    _need(dto.source.type == "SYNTHETIC_FIXTURE" and dto.source.provenance.content_sha256 is None
          and dto.source_evidence is not None and
          dto.source_evidence.source_processing_status == "OCR_COMPLETED" and
          dto.source_gate is not None and dto.outcome.failure is None, Refusal.V1_REFUSED)
    # Witness class is used only to accept/reject an already produced result.
    if assignment.asset.witness is Witness.POSITIVE:
        _need(dto.outcome.status == "RESULT_AVAILABLE" and dto.source_gate.decision == "SUFFICIENT"
              and dto.source_gate.reasons == () and dto.receipt is not None and
              dto.automatic_extraction is not None, Refusal.V1_REFUSED)
    else:
        _need(dto.outcome.status == "SOURCE_EVIDENCE_INSUFFICIENT"
              and dto.source_gate.decision == "INSUFFICIENT" and dto.source_gate.reasons == (_REASON,)
              and dto.source_evidence.token_ids == () and dto.receipt is None and
              dto.automatic_extraction is None, Refusal.V1_REFUSED)
    return payload


def _open_native(profile):
    """Called only after the supervised worker has its dispatch grant."""
    from paddleocr import PaddleOCR
    from paddlex.inference.pipelines.ocr.result import OCRResult

    provider = PaddleOCR(
        paddlex_config=profile.configuration.path,
        text_detection_model_name=_DETECTOR,
        text_detection_model_dir=str(Path(profile.detector[0].path).parent),
        text_recognition_model_name=_RECOGNIZER,
        text_recognition_model_dir=str(Path(profile.recognizer[0].path).parent),
        device="cpu", cpu_threads=profile.cpu_threads, enable_mkldnn=False,
        use_doc_orientation_classify=False, use_doc_unwarping=False,
        use_textline_orientation=False, return_word_box=False,
    )
    return provider, OCRResult


def _work(assignment, image, channel, np, open_provider):
    provider = iterator = record = recognized = array = backing = None
    outcome = (b"R", Refusal.PROVIDER_EXECUTION_FAILED.value.encode("ascii"))
    try:
        backing = _pixels(image, assignment.asset)
        array = np.ndarray((700, 1100, 3), dtype=np.uint8, buffer=backing)
        _need(_array_ok(array, backing, assignment.asset.bgr, np), Refusal.PROVIDER_INPUT_MISMATCH)
        _request(channel, assignment, b"D", b"", Refusal.ATTEMPT_STALE)
        provider, result_type = open_provider(assignment.profile)
        iterator, record, reason = _record(provider, array, result_type)
        if reason is not None:
            raise _Stop(reason)
        _association(record, array)
        _need(_array_ok(array, backing, assignment.asset.bgr, np), Refusal.PROVIDER_IMAGE_MISMATCH)
        recognized = _recognition(record, np)
        result = _compose(recognized, assignment, channel)
        _need(len(result) - 5 <= assignment.profile.candidate_bytes, Refusal.V1_REFUSED)
        outcome = (b"V", result)
    except _Stop as exc:
        outcome = (b"R", exc.reason.value.encode("ascii"))
    except BaseException:
        # Termination still requires independent supervisor observation.
        pass
    finally:
        cleanup_failed = False
        if iterator is not None:
            try:
                iterator.close()
            except BaseException:
                cleanup_failed = True
        if provider is not None:
            try:
                provider.close()
            except BaseException:
                cleanup_failed = True
        iterator = provider = record = recognized = array = backing = image = None
        if cleanup_failed:
            outcome = (b"R", Refusal.CLEANUP_UNCONFIRMED.value.encode("ascii"))
    message = _frame(outcome[0], assignment, outcome[1])
    _need(len(message) <= assignment.profile.ipc_bytes, Refusal.V1_REFUSED)
    channel.send(message, assignment.deadline)


def _native_worker(assignment, image, channel):
    """Private entry used only by an authorized WorkerHost on registered IPC."""
    _need(type(assignment) is _Assignment and
          _profile_ok(assignment.profile, assignment.assets) and
          any(asset is assignment.asset for asset in assignment.assets),
          Refusal.PROFILE_UNAPPROVED)
    import numpy

    _work(assignment, image, channel, numpy, _open_native)


def _finish_worker(worker, deadline, grace, clock, abort):
    """Use supervisor-side observations only. A child frame cannot prove exit."""
    exited = clean = isolation = normal_exit = False
    try:
        if not abort:
            exited = worker.wait_exited(deadline) is True
            if exited:
                code = worker.exit_code()
                normal_exit = type(code) is int and code == 0
    except BaseException:
        pass
    cleanup_deadline = deadline
    if not exited:
        cleanup_deadline = clock() + grace
        try:
            worker.terminate(cleanup_deadline)
            exited = worker.wait_exited(cleanup_deadline) is True
        except BaseException:
            pass
    try:
        if exited:
            clean = worker.cleanup(cleanup_deadline) is True
    except BaseException:
        pass
    try:
        observation = worker.isolation_failed()
        isolation = observation is True
        clean = clean and type(observation) is bool
    except BaseException:
        clean = False
    return exited and clean, isolation, normal_exit


class Supervisor:
    """One synchronous host-local caller. WorkerHost is the trusted OS boundary.

    An external host must enforce bounded non-network IPC, process supervision,
    offline isolation and cleanup. No permissive implementation is supplied.
    """

    def __init__(self, profile=None, assets=(), *, host=None, clock=monotonic_ns, nonce=token_hex):
        self._profile = profile
        self._assets = assets
        self._host = host
        self._clock = clock
        self._nonce = nonce
        self._lock = Lock()
        self._slots = [None, None]
        self._current = self._active = self._worker = None
        self._quarantined = False

    def issue(self, asset):
        """Return the original ticket, or a fixed refusal with no payload."""
        if not _profile_ok(self._profile, self._assets):
            return ProbeResult(Refusal.PROFILE_UNAPPROVED)
        try:
            with self._lock:
                index = next((i for i, expected in enumerate(self._assets) if asset is expected), None)
                _need(index is not None, Refusal.ATTEMPT_FOREIGN)
                _need(not self._quarantined, Refusal.PROFILE_UNAPPROVED)
                _need(self._slots[index] is None and self._active is None, Refusal.ATTEMPT_DUPLICATE)
                suffixes = tuple(self._nonce(16) for _ in range(5))
                _need(all(type(s) is str and re.fullmatch(r"[0-9a-f]{32}", s) for s in suffixes),
                      Refusal.PROFILE_UNAPPROVED)
                used = set()
                for slot in self._slots:
                    if slot is not None:
                        t = slot.ticket
                        used.update((t.request_id[4:], t.image_id[4:], t.receipt_id[4:],
                                     t.attempt_id[4:], slot.gate_id[4:]))
                _need(len(set(suffixes)) == 5 and not used.intersection(suffixes),
                      Refusal.GATE_RESERVATION_REFUSED)
                ids = tuple(prefix + suffix for prefix, suffix in zip(
                    ("req-", "img-", "rct-", "att-", "gat-"), suffixes))
                ticket = Ticket(*ids[:4])
                self._current = self._slots[index] = _Slot(ticket, asset, ids[4])
                return ticket
        except _Stop as exc:
            return ProbeResult(exc.reason)
        except Exception:
            return ProbeResult(Refusal.PROFILE_UNAPPROVED)

    def cancel(self, ticket):
        with self._lock:
            slot = self._current
            if (slot is None or slot.ticket is not ticket or slot.cancelled or
                    slot.state in (_State.REFUSED, _State.PUBLISHED)):
                return False
            slot.cancelled = True
            worker = self._worker if self._active is slot else None
        if worker is not None:
            # Wake bounded waits. The run owner performs termination and cleanup.
            try:
                worker.interrupt()
            except Exception:
                pass
        return True

    def _live(self, slot, deadline):
        _need(slot is self._current and slot is self._active, Refusal.ATTEMPT_STALE)
        _need(not slot.cancelled, Refusal.ATTEMPT_CANCELLED)
        _need(self._clock() < deadline, Refusal.ATTEMPT_EXPIRED)

    def _claim(self, ticket):
        slot = next((s for s in self._slots if s is not None and s.ticket is ticket), None)
        _need(slot is not None, Refusal.ATTEMPT_FOREIGN)
        _need(slot is self._current, Refusal.ATTEMPT_STALE)
        _need(slot.state is _State.ISSUED and self._active is None, Refusal.ATTEMPT_DUPLICATE)
        if slot.cancelled:
            slot.state = _State.REFUSED
            raise _Stop(Refusal.ATTEMPT_CANCELLED)
        deadline = self._clock() + self._profile.run_ns
        slot.state = _State.CLAIMED
        self._active = slot
        return slot, _Assignment(ticket, slot.asset, self._assets, self._profile, deadline, slot.gate_id)

    def _drive(self, worker, slot, assignment):
        # The registered handle is the only source of frames for this attempt.
        # At most dispatch, gate, candidate/refusal, then EOF.
        refusal = None
        while True:
            with self._lock:
                self._live(slot, assignment.deadline)
            kind, body = _read(worker, assignment)
            with self._lock:
                self._live(slot, assignment.deadline)
                if kind == b"D":
                    _need(slot.state is _State.CLAIMED and not body, Refusal.ATTEMPT_DUPLICATE)
                    slot.state = _State.DISPATCHED
                    reply = b""
                elif kind == b"G":
                    _need(slot.state is _State.DISPATCHED and not body, Refusal.GATE_RESERVATION_REFUSED)
                    slot.state = _State.GATE_GRANTED
                    reply = slot.gate_id.encode("ascii")
                elif kind == b"V":
                    _need(slot.state is _State.GATE_GRANTED, Refusal.GATE_RESERVATION_REFUSED)
                    slot.state = _State.CANDIDATE_HELD
                    break
                elif kind == b"R":
                    _need(len(body) <= 40, Refusal.PROVIDER_EXECUTION_FAILED)
                    try:
                        refusal = Refusal(body.decode("ascii"))
                    except (UnicodeError, ValueError):
                        raise _Stop(Refusal.PROVIDER_EXECUTION_FAILED) from None
                    break
                else:
                    raise _Stop(Refusal.PROVIDER_EXECUTION_FAILED)
            worker.send(_frame(kind, assignment, reply), assignment.deadline)
        _need(_read(worker, assignment) == (None, b""), Refusal.PROVIDER_EXECUTION_FAILED)
        return (body, None) if refusal is None else (None, refusal)

    def run(self, ticket, image_bytes):
        """Return bytes only from the supervisor's final locked checkpoint."""
        try:
            _need(self._host is not None and _profile_ok(self._profile, self._assets)
                  and self._host.authorize(self._profile, self._assets) is True, Refusal.PROFILE_UNAPPROVED)
        except Exception:
            return ProbeResult(Refusal.PROFILE_UNAPPROVED)
        try:
            with self._lock:
                _need(not self._quarantined, Refusal.PROFILE_UNAPPROVED)
                slot, assignment = self._claim(ticket)
        except _Stop as exc:
            return ProbeResult(exc.reason)

        worker = candidate = reason = None
        clean = True
        isolation = abort = transport_failed = False
        deadline = assignment.deadline
        try:
            _encoded(image_bytes, assignment.asset)
            with self._lock:
                self._live(slot, deadline)
            worker = self._host.prepare(self._profile, deadline)
            with self._lock:
                self._live(slot, deadline)
                self._worker = worker
            worker.start(assignment, image_bytes, deadline)
            candidate, reason = self._drive(worker, slot, assignment)
        except _Stop as exc:
            abort, reason = True, exc.reason
        except BaseException:
            abort = transport_failed = True
            reason = Refusal.PROVIDER_EXECUTION_FAILED
        finally:
            if worker is not None:
                clean, isolation, normal_exit = _finish_worker(
                    worker, deadline, self._profile.termination_grace_ns,
                    self._clock, abort or slot.cancelled,
                )
                if (candidate is not None and not normal_exit and not slot.cancelled
                        and self._clock() < deadline):
                    clean = False
        if reason is Refusal.ISOLATION_VIOLATION:
            isolation = True
        if reason is Refusal.CLEANUP_UNCONFIRMED:
            clean = False

        payload = None
        if clean and not isolation and reason is None:
            try:
                with self._lock:
                    self._live(slot, deadline)
                payload = _candidate(candidate, assignment)
            except _Stop as exc:
                reason = exc.reason
            except BaseException:
                reason = Refusal.V1_REFUSED

        with self._lock:
            if isolation or not clean:
                self._quarantined = True
                reason = Refusal.ISOLATION_VIOLATION if isolation else Refusal.CLEANUP_UNCONFIRMED
            elif transport_failed or reason is None:
                # An interrupted transport may only have observed a generic error.
                try:
                    self._live(slot, deadline)
                except _Stop as exc:
                    reason = exc.reason
            self._active = self._worker = None
            if clean and not isolation and slot.state is _State.CANDIDATE_HELD:
                slot.state = _State.TERMINATED_CLEAN
            if (reason is None and slot is self._current and
                    slot.state is _State.TERMINATED_CLEAN and payload is not None):
                slot.state = _State.PUBLISHED
                return ProbeResult(None, payload)
            slot.state = _State.REFUSED
            return ProbeResult(reason if reason is not None else Refusal.V1_REFUSED)
