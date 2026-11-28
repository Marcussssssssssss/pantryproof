"""Ratified byte fixtures and prototype composition with no network or native OCR."""

from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
from threading import Event, Thread
from time import monotonic, time
from unittest.mock import Mock

import pytest

from pipeline import backend_local_image_receipt_v0 as backend
from pipeline import gate_c_live_source_gate_v0 as gate
from pipeline import native_local_image_dev_controls_v0 as controls
from pipeline import real_receipt_http_service_v1 as http
from pipeline.presentation_v1 import conformance as v1
from pipeline.presentation_v1 import review_projection
from pipeline.presentation_v1.review_conformance import (
    decode_and_validate_receipt_review_v1,
    object_member_bytes,
)
from pipeline.proposed import receipt_research_v1
from scripts import dev_local_image_backend_v0 as bootstrap
from tests.test_backend_local_image_receipt_v0 import _GENERATED_PNG, _payload, _provider
from tests.test_dev_local_image_backend_v0 import _TOKEN, _write_pin, approved_export
from tests.test_operational_receipt_method_v1 import _select_proposed
from tests.test_real_receipt_http_service_v1 import (
    _MemoryConnection, _TOKEN as TRANSPORT_TOKEN, _envelope, _exchange, _head, _memory_select, _response,
)
from tests.test_receipt_correction_v1 import resources as synthetic_resources


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/receipt_presentation_v1/review_v1"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_bytes())
SCHEMA = b"X-Response-Schema"


def _fixture(raw):
    metadata = v1.decode_strict_json_object(raw)
    context = metadata["consumerContext"]
    expected = {
        "expected_request_id": context["expectedRequestId"],
        "expected_image_id": context["expectedImageId"],
        "consumer_mode": context["consumerMode"],
        "expected_image_width": context.get("expectedImageWidth"),
        "expected_image_height": context.get("expectedImageHeight"),
    }
    return metadata, object_member_bytes(raw, "envelope"), expected


def _assert_result(body, context, case):
    if case["expectedResult"] == "ACCEPT":
        assert case["expectedPath"] is None
        decode_and_validate_receipt_review_v1(body, **context)
    else:
        with pytest.raises(v1.ConformanceViolation) as error:
            decode_and_validate_receipt_review_v1(body, **context)
        assert (error.value.code, error.value.path) == (case["expectedResult"], case["expectedPath"])


@pytest.mark.parametrize("case", MANIFEST["fixtures"], ids=lambda case: Path(case["path"]).stem)
def test_canonical_review_fixture(case):
    raw = (FIXTURES / case["path"]).read_bytes()
    assert len(raw) == case["byteLength"] and sha256(raw).hexdigest() == case["sha256"]
    metadata, body, context = _fixture(raw)
    for key in ("expectedResult", "expectedPath"):
        assert metadata[key] == case[key]
    embedded = metadata["envelope"]["presentation"]
    v1.decode_and_validate_presentation_v1(
        object_member_bytes(body, "presentation"), expected_request_id=embedded["requestId"],
        expected_image_id=embedded["imageId"], consumer_mode=context["consumer_mode"],
    )
    _assert_result(body, context, case)


@pytest.mark.parametrize("case", MANIFEST["byteLimitCases"], ids=lambda case: case["id"])
def test_canonical_review_byte_limits(case):
    _, base, context = _fixture((FIXTURES / case["baseFixture"]).read_bytes())
    presentation = object_member_bytes(base, "presentation")
    index = base.index(presentation)
    position = {"insidePresentation": index + 1, "beforePresentation": index, "insideWrapper": 1}
    insert = position[case["location"]]
    body = base[:insert] + b" " * case["spaceCount"] + base[insert:]
    assert len(body) == case["bodyByteLength"]
    assert sha256(body).hexdigest() == case["bodySha256"]
    assert len(object_member_bytes(body, "presentation")) == case["presentationByteLength"]
    _assert_result(body, context, case)


@pytest.mark.parametrize(("transform", "code", "path"), (
    (lambda raw: b"\xef\xbb\xbf" + raw, "REJECT_INVALID_JSON", "$"),
    (lambda raw: raw.replace(b'"1"}', b'"\xff"}'), "REJECT_INVALID_JSON", "$"),
    (lambda raw: raw.replace(b'"1"}', b'"\\ud800"}'), "REJECT_INVALID_JSON", "$.schemaVersion"),
    (lambda raw: br'{"\u0070resentation":null,' + raw[1:], "REJECT_DUPLICATE_JSON_KEY", "$"),
))
def test_strict_review_lexical_failures(transform, code, path):
    _, body, context = _fixture((FIXTURES / MANIFEST["fixtures"][0]["path"]).read_bytes())
    _assert_result(transform(body), context, {"expectedResult": code, "expectedPath": path})


def _composition(monkeypatch, manifest, payload, *, verified=False):
    _select_proposed(manifest, verified=verified)
    method = replace(bootstrap._load_proposed_method(manifest["receipt_method"]),
                     resources=synthetic_resources())
    recognize = Mock(side_effect=_provider(payload))
    runtime = backend.LocalImageRuntimeApprovalV0(recognize, backend.LOCAL_IMAGE_SOURCE_SYSTEM)
    monkeypatch.setattr(backend, "_APPROVED_PROTOTYPE_RUNTIME", runtime)
    monkeypatch.setattr(gate, "_APPROVED_GROCERY_POLICY_SHA256", gate.GROCERY_LIVE_GATE_V1.policy_sha256)
    coordinator = backend.LocalImageReceiptProcessorV0(
        gate_policy=gate.GROCERY_LIVE_GATE_V1, runtime=runtime, proposed_method=method,
    )
    return backend.as_t09_receipt_processor_v0(coordinator), recognize


@pytest.mark.parametrize("mode", (
    "policy", "not-ready", "fallback", "method-failure", "ocr-failure", "partial", "weighted", "total-only",
))
def test_real_review_projection_through_http(approved_export, monkeypatch, mode):
    manifest, _ = approved_export
    payload = _payload("PANTRYPROOF TEST MART", split=True)
    idx = payload["rec_texts"].index("MILK")
    payload["rec_texts"][idx] = "MLK"
    payload["rec_scores"] = [0.91] * len(payload["rec_texts"])
    payload["rec_scores"][idx] = 0.20
    if mode == "fallback":
        payload = {"rec_texts": ["THANK YOU"], "rec_boxes": [[10, 5, 160, 15]]}
    elif mode in ("partial", "weighted"):
        payload = _payload("PANTRYPROOF TEST MART")
        payload["rec_texts"][2] = "MILK 11.00" if mode == "partial" else "MILK 0.750 x 5.50 4.13"
        payload["rec_texts"][3] = "THANK YOU"
    elif mode == "total-only":
        payload = {"rec_texts": ["TOTAL RM 11.00"], "rec_boxes": [[10, 10, 250, 20]]}
    elif mode == "method-failure":
        monkeypatch.setattr(receipt_research_v1, "run_proposed_receipt_v1",
                            Mock(side_effect=ValueError("private exception detail")))

    processor, recognize = _composition(monkeypatch, manifest, payload, verified=mode == "policy")
    if mode == "ocr-failure":
        recognize.side_effect = RuntimeError("private exception detail")
    emitted_v1 = []
    project_v1 = review_projection.project_retained_local_image_presentation_v1

    def record_v1(**kwargs):
        original = project_v1(**kwargs)
        emitted_v1.append(original)
        return original

    monkeypatch.setattr(review_projection, "project_retained_local_image_presentation_v1", record_v1)
    service = http.ReceiptHttpService(TRANSPORT_TOKEN, processor=processor, review_enabled=True)
    _, body = _response(_exchange(service, _GENERATED_PNG, change={SCHEMA: b"receipt-review-v1"}), 200)
    assert object_member_bytes(body, "presentation") == emitted_v1[-1]
    result = json.loads(body)
    presentation, review = result["presentation"], result["review"]
    assert (result["schemaName"], result["schemaVersion"]) == ("receipt-review", "1")
    recognize.assert_called_once()
    if mode == "fallback":
        assert presentation["outcome"]["status"] == "SOURCE_EVIDENCE_INSUFFICIENT"
        assert review["fields"] == [] and review["ocrEvidence"]["tokens"][0]["originalText"] == "THANK YOU"
        return
    if mode in ("method-failure", "ocr-failure"):
        assert presentation["outcome"]["status"] == "PROCESSING_FAILED"
        assert review["fields"] == [] and b"private exception detail" not in body
        assert review["failure"]["code"] == (
            "PROPOSED_METHOD_FAILURE" if mode == "method-failure" else "OCR_ENGINE_FAILURE"
        )
        assert (review["ocrEvidence"] is None) == (mode == "ocr-failure")
        return
    if mode == "total-only":
        assert presentation["outcome"]["status"] == "RESULT_AVAILABLE"
        assert presentation["receipt"]["itemRows"] == []
        assert review["pantryMappings"] == []
        return

    fields = {item["role"]: item for item in review["fields"]}
    assert list(fields) == [
        "STORE_NAME", "PURCHASE_DATE", "RECEIPT_TOTAL", "ITEM_DESCRIPTION", "QUANTITY", "UNIT_PRICE", "LINE_TOTAL",
    ]
    assert review["ocrEvidence"]["coordinateFrame"]["imageWidth"] == 400
    item = fields["ITEM_DESCRIPTION"]
    if mode == "policy":
        assert review["methodReadiness"] == "POLICY_APPLIED"
        assert item["selectedPreReview"]["value"] == "MILK"
        assert item["originalB2"]["value"] == "MLK"
        assert item["calibratedProbability"] is not None
        selected = next(candidate for candidate in item["alternativeCandidates"]
                        if candidate["candidateId"] == item["selectedPreReview"]["candidateId"])
        assert selected["sourceTokenIds"] == item["originalB2"]["sourceTokenIds"]
    else:
        assert review["methodReadiness"] == "NOT_READY"
        assert all(field["calibratedProbability"] is None for field in fields.values())
        if mode == "not-ready":
            recommendation = item["developmentRecommendation"]
            assert recommendation["recommendation"] == "CORRECT"
            alternative, = (
                candidate for candidate in item["alternativeCandidates"]
                if candidate["candidateId"] == recommendation["recommendedCandidateId"]
            )
            assert alternative["value"] == "MILK"
            assert alternative["calibratedProbability"] is None
            assert review["receiptDisposition"] == item["fieldDisposition"] == "UNVERIFIED_DRAFT"
            assert item["automaticCommitPermitted"] is False
            original, selected = item["originalB2"], item["selectedPreReview"]
            assert selected["candidateId"] == original["c0CandidateId"]
            assert selected["candidateId"] != recommendation["recommendedCandidateId"]
            assert selected["value"] == original["value"] == "MLK"
            assert selected["changedFromC0"] is False
        elif mode == "partial":
            assert fields["UNIT_PRICE"]["selectedPreReview"]["value"] is None
            assert fields["UNIT_PRICE"]["optionalWhenMissing"] is True
            assert fields["RECEIPT_TOTAL"]["selectedPreReview"]["value"] is None
        else:
            assert fields["QUANTITY"]["selectedPreReview"]["value"] == "0.750"
            tokens = {token["tokenId"]: token["originalText"] for token in review["ocrEvidence"]["tokens"]}
            assert any("0.750" in tokens[key] for key in fields["QUANTITY"]["originalB2"]["sourceTokenIds"])


@pytest.mark.parametrize(("changes", "extra", "status"), [
    ({b"Authorization": b"Bearer wrong", SCHEMA: b"bad value", b"Content-Type": b"unknown"}, (), 401),
    ({SCHEMA: b""}, (), 400),
    ({SCHEMA: b"receipt-review-v1,receipt-presentation-v1"}, (), 400),
    ({SCHEMA: b"receipt-review-v1"}, (b"x-response-schema: receipt-review-v1",), 400),
    ({SCHEMA: b"receipt-review-v2", b"Content-Type": b"unknown"}, (), 406),
    ({SCHEMA: b"receipt-review-v1"}, (), 503),
])
def test_negotiation_refuses_before_body(changes, extra, status):
    processor = Mock()
    service = http.ReceiptHttpService(TRANSPORT_TOKEN, processor=processor)
    header = _head(_GENERATED_PNG, change=changes, extra=extra)
    connection = _MemoryConnection(header, _GENERATED_PNG)
    service.handle_connection(connection, port=http.DEFAULT_PORT)
    _response(connection, status)
    assert connection.received == len(header)
    processor.assert_not_called()


@pytest.mark.parametrize("selector", (None, b"receipt-presentation-v1", b"receipt-review-v1"))
def test_negotiation_preserves_bare_bytes_without_fallback(selector):
    processor = Mock(side_effect=lambda request, _: _envelope(request))
    service = http.ReceiptHttpService(TRANSPORT_TOKEN, processor=processor, review_enabled=True)
    connection = _exchange(service, _GENERATED_PNG, change={SCHEMA: selector})
    if selector == b"receipt-review-v1":
        _response(connection, 500)
    else:
        _, body = _response(connection, 200)
        assert body == _envelope(processor.call_args.args[0])


@pytest.mark.parametrize(("extra", "status"), ((0, 200), (1, 500)))
def test_http_bare_presentation_limit(extra, status):
    def processor(request, _):
        bare = _envelope(request)
        return bare + b" " * (http.MAX_RESPONSE_BYTES - len(bare) + extra)

    service = http.ReceiptHttpService(TRANSPORT_TOKEN, processor=processor, review_enabled=True)
    _, body = _response(_exchange(service, _GENERATED_PNG), status)
    assert len(body) == (http.MAX_RESPONSE_BYTES if not extra else 0)


def _attestation(tmp_path, *, confirmed, expires):
    value = {"scope": controls.PROTOTYPE_SCOPE, "network_observation": controls.NETWORK_OBSERVATION,
             "physical_disconnection_confirmed_unix_s": confirmed, "expires_unix_s": expires}
    return _write_pin(tmp_path / "prototype-controls.json", json.dumps(value).encode())


def test_session_expiry_revocation_and_explicit_renewal(approved_export, tmp_path):
    manifest, _ = approved_export
    profile = bootstrap._parse_profile(manifest["profile"])
    second = 1_000_000_000
    now = 5 * second
    wall = 1_800_000_000
    def open_session(confirmed, expires):
        pin = _attestation(tmp_path, confirmed=confirmed, expires=expires)
        return controls.PrototypeSessionV1(
            replace(profile, controls_manifest=pin), clock_ns=lambda: now, wall_ns=lambda: wall * second,
        )

    session = open_session(wall - 10, wall + 14_390)
    assert session.deadline_ns == (5 + 14_390) * second
    assert session.permits(60, 45)
    assert not session.permits(45, 5)
    assert not session.permits(session.deadline_ns // second + 1)
    now = session.deadline_ns
    assert not session.is_active()
    now = 5 * second
    assert not session.is_active()
    with pytest.raises(controls.HostError):
        open_session(wall, wall + 14_401)
    with pytest.raises(controls.HostError):
        open_session(wall - 60, wall)
    with pytest.raises(controls.HostError):
        open_session(wall + 1, wall + 60)
    renewed = open_session(wall, wall + 3_600)
    assert renewed.permits(60, 45)
    (tmp_path / "prototype-controls.json").write_bytes(b"changed")
    assert not renewed.controls_valid() and not renewed.is_active()
    replacement = open_session(wall, wall + 120)
    replacement.observe_runtime(lambda: True)
    assert not replacement.is_active()


def test_changed_controls_block_publication(approved_export, tmp_path):
    manifest, _ = approved_export
    wall = int(time())
    pin = _attestation(tmp_path, confirmed=wall, expires=wall+600)
    profile = replace(bootstrap._parse_profile(manifest["profile"]), controls_manifest=pin)
    session = controls.PrototypeSessionV1(profile)

    def detached_result(request, _):
        Path(pin.path).write_bytes(b"replaced after processing admission")
        return _envelope(request)

    service = http.ReceiptHttpService(TRANSPORT_TOKEN, processor=detached_result, session=session)
    _response(_exchange(service, _GENERATED_PNG), 503)
    assert not session.is_active()


@pytest.mark.parametrize("termination", ("disconnect", "quarantine", "revocation", "shutdown"))
def test_prototype_cancellation_owns_slot_until_teardown(approved_export, tmp_path, termination):
    manifest, _ = approved_export
    wall = int(time())
    profile = replace(bootstrap._parse_profile(manifest["profile"]),
                      controls_manifest=_attestation(tmp_path, confirmed=wall, expires=wall+600))
    session = controls.PrototypeSessionV1(profile)
    quarantined = Event()
    session.observe_runtime(quarantined.is_set)
    entered, finish_cleanup = Event(), Event()
    calls = []

    def process(request, context):
        calls.append(context)
        if len(calls) == 1:
            entered.set()
            assert finish_cleanup.wait(5)
            if termination == "quarantine":
                quarantined.set()
        return _envelope(request)

    service = http.ReceiptHttpService(TRANSPORT_TOKEN, processor=process, session=session)
    connection = _MemoryConnection(_head(_GENERATED_PNG), _GENERATED_PNG)
    thread = Thread(target=service.handle_connection, args=(connection,),
                    kwargs={"port": http.DEFAULT_PORT}, daemon=True)
    thread.start()
    try:
        assert entered.wait(3)
        _response(_exchange(service, _GENERATED_PNG), 429)
        if termination == "revocation":
            session.revoke()
        elif termination == "shutdown":
            service.stop()
        else:
            connection.disconnect()
        thread.join(3)
        assert not thread.is_alive() and calls[0].cancelled
        assert not service.drain(0)
        if termination == "revocation":
            _response(connection, 503)
        else:
            assert not connection.output
        prior_output = bytes(connection.output)
    finally:
        finish_cleanup.set()
        thread.join(3)
    assert service.drain(3) and bytes(connection.output) == prior_output
    if termination == "shutdown":
        assert not _exchange(service, _GENERATED_PNG).output
    else:
        _response(_exchange(service, _GENERATED_PNG), 200 if termination == "disconnect" else 503)
    assert len(calls) == (2 if termination == "disconnect" else 1)


def test_prototype_launch_is_separate_and_admits_two_independent_requests(approved_export, monkeypatch, tmp_path):
    original, _ = approved_export
    _select_proposed(original, verified=False)
    manifest = {key: original[key] for key in ("profile", "receipt_method")}
    manifest["scope"] = controls.PROTOTYPE_SCOPE
    manifest["gate_policy_sha256"] = gate.GROCERY_LIVE_GATE_V1.policy_sha256
    source_pins = []
    for filename in bootstrap._PROTOTYPE_SOURCES:
        path = ROOT / filename
        raw = path.read_bytes()
        source_pins.append({"path": str(path), "length": len(raw), "sha256": sha256(raw).hexdigest()})
    manifest["source_pins"] = source_pins
    with pytest.raises(bootstrap.DevelopmentBootstrapRefusal):
        bootstrap._prepare_prototype_launch({**manifest, "source_pins": source_pins[1:]})
    wall = int(time())
    pin = _attestation(tmp_path, confirmed=wall, expires=wall + 600)
    manifest["profile"]["controls_manifest"] = asdict(pin)
    launch = bootstrap._prepare_prototype_launch(manifest)
    launch = replace(launch, method=replace(launch.method, resources=synthetic_resources()))
    recognize = Mock(side_effect=_provider(_payload(split=True)))
    recognize.quarantined = False
    monkeypatch.setattr(bootstrap, "_check_runtime", Mock())
    monkeypatch.setattr(bootstrap.PrototypeLocalImageHostControlsV1, "approve", Mock(return_value=True))
    executor = Mock()
    monkeypatch.setattr(bootstrap.t13, "SupervisedNativeLocalImageExecutorV0", executor)
    monkeypatch.setattr(bootstrap, "NativeLocalImageProviderV0", lambda _: recognize)
    served = []

    def serve(service, *, port):
        assert port == 8765
        assert bootstrap.t13._DEVELOPMENT_RUNTIME is None and bootstrap.t10._APPROVED_RUNTIME is None
        for index in (1, 2):
            headers = {SCHEMA: b"receipt-review-v1", b"Authorization": b"Bearer " + _TOKEN,
                       b"X-Request-Id": f"request-{index}".encode(), b"X-Image-Id": f"image-{index}".encode()}
            _, body = _response(_exchange(service, _GENERATED_PNG, change=headers), 200)
            assert json.loads(body)["presentation"]["requestId"] == f"request-{index}"
        served.append(service)

    monkeypatch.setattr(bootstrap.http, "serve_development", serve)
    bootstrap._serve_prototype(launch, _TOKEN)
    assert recognize.call_count == 2
    assert executor.call_args.kwargs == {"prototype": True}
    assert served[0].drain(0) and not served[0]._session.is_active()
    assert bootstrap.t13._PROTOTYPE_RUNTIME is None and bootstrap.t10._APPROVED_PROTOTYPE_RUNTIME is None
    assert gate._APPROVED_GROCERY_POLICY_SHA256 is None
