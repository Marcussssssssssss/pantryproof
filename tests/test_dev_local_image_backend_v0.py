"""T15 source-only focused tests. Listener and runtime preflight use doubles."""

from dataclasses import asdict, replace
from hashlib import sha256
from io import BytesIO
import json
from time import monotonic
from unittest.mock import Mock

from PIL import Image
import pytest

from scripts import dev_local_image_backend_v0 as bootstrap


_TOKEN = b"1" * 64
_RATIFIED_DIGEST = "bc478fd4544e96e64dfe4ac3fa960c5aa68f2dec490c29fea75594472293cdba"


def _unconfigured():
    assert bootstrap.t13._AUTHORIZED_RUNTIME is None
    assert bootstrap.t13._DEVELOPMENT_RUNTIME is None
    assert bootstrap.t10._APPROVED_RUNTIME is None
    assert bootstrap.gate._APPROVED_POLICY_SHA256 is None


def _png(color):
    with BytesIO() as stream, Image.new("RGB", (2, 1), color) as image:
        image.save(stream, format="PNG")
        return stream.getvalue()


def _write_pin(path, raw):
    path.write_bytes(raw)
    return bootstrap.FilePin(str(path), len(raw), sha256(raw).hexdigest())


@pytest.fixture
def approved_export(tmp_path):
    original = _write_pin(tmp_path / "original.png", _png((11, 22, 33)))
    encoded = _png((20, 40, 60))
    transmitted = _write_pin(tmp_path / "android.png", encoded)
    pinned_file = _write_pin(tmp_path / "profile-file", b"generated profile double")
    profile = bootstrap.t13.NativeLocalImageRuntimeProfileV0(
        launch=bootstrap.LaunchSpec(
            str(tmp_path / "base-python.exe"), str(tmp_path / "scratch"),
            (str(tmp_path),), (("SystemRoot", str(tmp_path)),),
        ),
        launcher=pinned_file, worker=pinned_file, runtime=(pinned_file,),
        detector=(pinned_file,), recognizer=(pinned_file,),
        configuration=pinned_file, controls_manifest=pinned_file,
        memory_bytes=4096, scratch_bytes=4096, minimum_work_ns=1, teardown_reserve_ns=1,
    )
    manifest = {
        "scope": bootstrap.DEVELOPMENT_SCOPE,
        "original": asdict(original),
        "transmitted": asdict(transmitted),
        "raster": {
            "bgr8_sha256": sha256(bytes((60, 40, 20)) * 2).hexdigest(),
            "width": 2,
            "height": 1,
        },
        "gate_policy_sha256": _RATIFIED_DIGEST,
        "profile": json.loads(json.dumps(asdict(profile))),
    }
    return manifest, encoded


@pytest.fixture
def approved_launch(approved_export, monkeypatch):
    manifest, encoded = approved_export
    launch = bootstrap._prepare_launch(manifest, bootstrap._preflight_deadline())
    monkeypatch.setattr(bootstrap, "_check_runtime", Mock())
    return launch, encoded


def test_default_cli_does_not_start_or_enable_the_backend(monkeypatch):
    serve = Mock()
    monkeypatch.setattr(bootstrap.http, "serve_development", serve)
    _unconfigured()
    with pytest.raises(SystemExit) as result:
        bootstrap.main([])
    assert result.value.code == 2
    serve.assert_not_called()
    _unconfigured()


@pytest.mark.parametrize("defect", ("digest", "scope"))
def test_approved_manifest_digest_and_generated_scope_are_required(tmp_path, defect):
    scope = "WRONG_SCOPE" if defect == "scope" else bootstrap.DEVELOPMENT_SCOPE
    pin = _write_pin(tmp_path / "approved.json", json.dumps({"scope": scope}).encode("utf-8"))
    approved_digest = "0" * 64 if defect == "digest" else pin.sha256
    with pytest.raises(bootstrap.DevelopmentBootstrapRefusal):
        bootstrap._read_manifest(pin.path, approved_digest)
    _unconfigured()


def test_android_export_and_ratified_gate_are_independently_bound(approved_export):
    manifest, encoded = approved_export
    launch = bootstrap._prepare_launch(manifest, bootstrap._preflight_deadline())
    assert launch.policy is bootstrap.gate.PROPOSED_LIVE_GATE_V0
    assert launch.policy.revision == "T10-P01" and launch.policy.policy_sha256 == _RATIFIED_DIGEST
    assert launch.approval.encoded_sha256 == sha256(encoded).hexdigest()
    assert launch.approval.encoded_sha256 != manifest["original"]["sha256"]
    assert launch.approval.bgr8_sha256 == manifest["raster"]["bgr8_sha256"]
    assert (launch.approval.width, launch.approval.height) == (2, 1)
    _unconfigured()


@pytest.mark.parametrize("defect", ("policy", "encoded", "raster", "dimensions"))
def test_mismatched_approval_is_refused_during_preflight(approved_export, defect):
    manifest, _ = approved_export
    if defect == "policy":
        manifest["gate_policy_sha256"] = "0" * 64
    elif defect == "encoded":
        manifest["transmitted"]["sha256"] = "0" * 64
    elif defect == "raster":
        manifest["raster"]["bgr8_sha256"] = "0" * 64
    else:
        manifest["raster"]["width"] = 1
    with pytest.raises((bootstrap.DevelopmentBootstrapRefusal, bootstrap.t13.HostError)):
        bootstrap._prepare_launch(manifest, bootstrap._preflight_deadline())
    _unconfigured()


def test_explicit_development_composition_admits_only_one_approved_png(approved_launch, monkeypatch):
    launch, encoded = approved_launch
    bridge = Mock(return_value=bootstrap.http.ProcessingRefusal.FAILED)
    adapt = Mock(return_value=bridge)
    monkeypatch.setattr(bootstrap.t10, "as_t09_receipt_processor_v0", adapt)
    observed_services = []

    def serve(service, *, port):
        observed_services.append(service)
        assert type(service) is bootstrap.http.ReceiptHttpService and port == 8765
        assert bootstrap.t13._AUTHORIZED_RUNTIME is None
        profile, controls = bootstrap.t13._DEVELOPMENT_RUNTIME
        assert profile is launch.approval.profile
        assert type(controls) is bootstrap.DevelopmentLocalImageHostControlsV0
        runtime = bootstrap.t10._APPROVED_RUNTIME
        executor = runtime.provider._executor
        assert type(executor) is bootstrap.t13.SupervisedNativeLocalImageExecutorV0
        assert executor.development is True and executor.profile is profile and executor.controls is controls
        assert runtime.source_system == "ANDROID_LOCAL_IMAGE"
        coordinator = adapt.call_args.args[0]
        assert type(coordinator) is bootstrap.t10.LocalImageReceiptProcessorV0
        assert coordinator.runtime is runtime and coordinator.gate_policy is launch.policy
        assert bootstrap.gate._APPROVED_POLICY_SHA256 == _RATIFIED_DIGEST

        request = bootstrap.http.ReceiptRequest("req-t15", "img-t15", "image/png", encoded)
        context = bootstrap.http.ProcessingContext(monotonic() + 100)
        other = replace(request, encoded_image=_png((5, 6, 7)))
        assert service._processor(other, context) is bootstrap.http.ProcessingRefusal.UNAVAILABLE
        bridge.assert_not_called()
        assert service._processor(request, context) is bootstrap.http.ProcessingRefusal.FAILED
        assert service._processor(request, context) is bootstrap.http.ProcessingRefusal.UNAVAILABLE
        bridge.assert_called_once_with(request, context)

    monkeypatch.setattr(bootstrap.http, "serve_development", serve)
    bootstrap._serve_approved(launch, _TOKEN)
    assert len(observed_services) == 1 and observed_services[0]._stopping.is_set()
    _unconfigured()


def test_startup_failure_clears_all_process_scoped_approvals(approved_launch, monkeypatch):
    launch, _ = approved_launch
    serve = Mock(side_effect=OSError("generated bind failure"))
    monkeypatch.setattr(bootstrap.http, "serve_development", serve)
    with pytest.raises(OSError, match="generated bind failure"):
        bootstrap._serve_approved(launch, _TOKEN)
    serve.assert_called_once()
    assert serve.call_args.args[0]._stopping.is_set()
    _unconfigured()


def test_invalid_policy_dependencies_block_listener_and_clear_pins(approved_launch, monkeypatch):
    launch, _ = approved_launch
    serve = Mock()
    monkeypatch.setattr(bootstrap.http, "serve_development", serve)
    monkeypatch.setattr(
        bootstrap.gate, "require_approved_live_policy_v0",
        Mock(side_effect=bootstrap.gate.LiveSourceGateRefusal("LIVE_POLICY_DEPENDENCY_CHANGED")),
    )
    with pytest.raises(bootstrap.gate.LiveSourceGateRefusal):
        bootstrap._serve_approved(launch, _TOKEN)
    serve.assert_not_called()
    _unconfigured()


def test_unconfirmed_native_cleanup_refuses_shutdown_success(approved_launch, monkeypatch):
    launch, _ = approved_launch
    monkeypatch.setattr(bootstrap.t13, "_QUARANTINED", None)
    sentinel = object()

    def serve(_service, *, port):
        bootstrap.t13._QUARANTINED = sentinel

    monkeypatch.setattr(bootstrap.http, "serve_development", serve)
    with pytest.raises(bootstrap.DevelopmentBootstrapRefusal, match="cleanup remains unconfirmed"):
        bootstrap._serve_approved(launch, _TOKEN)
    assert bootstrap.t13._QUARANTINED is sentinel
    _unconfigured()


def test_cli_consumes_ephemeral_token_and_suppresses_exception_detail(monkeypatch, capsys):
    token = _TOKEN.decode("ascii")
    monkeypatch.setenv(bootstrap.http.TOKEN_ENV, token)
    monkeypatch.setattr(bootstrap, "_read_manifest", Mock(return_value={}))
    monkeypatch.setattr(bootstrap, "_prepare_launch", Mock(return_value=object()))

    def fail(_launch, credential, *, evidence_path):
        assert credential == _TOKEN and bootstrap.http.TOKEN_ENV not in bootstrap.os.environ
        assert evidence_path.name == "generated-research-evidence.json"
        raise OSError(token)

    monkeypatch.setattr(bootstrap, "_serve_approved", fail)
    assert bootstrap.main(["serve", "--manifest", "unused", "--approval-sha256", "unused"]) == 2
    capture = capsys.readouterr()
    assert not capture.out and capture.err == "Development preflight or listener failed.\n"
    assert token not in capture.err
    _unconfigured()


@pytest.mark.parametrize("structured", (True, False), ids=("correct", "no-b2"))
def test_generated_research_evidence_through_real_coordinator(approved_launch, tmp_path, monkeypatch, structured):
    launch, encoded = approved_launch
    evidence = tmp_path / "generated-research-evidence.json"
    regions = (
        ("SUNNY MART", 10, 5, 160), ("2026-10-14", 10, 20, 120),
        ("REFERENCE", 10, 38, 84), ("PURCHASE DATE: 2026-10-15", 85, 38, 315),
        ("REFERENCE", 10, 56, 84), ("PURCHASE DATE: 15/10/2026", 85, 56, 315),
        ("MILK 2 x 5.50 11.00", 10, 98, 240), ("TOTAL RM 11.00", 130, 125, 260),
    ) if structured else ()
    payload = {
        "rec_texts": [text for text, *_ in regions],
        "rec_scores": [0.91] * len(regions),
        "rec_boxes": [[left, top, right, top + 10] for _, left, top, right in regions],
    }

    def recognize(request, context):
        return bootstrap.t10.RetainedLocalImageRecognitionV0(
            request, request.image_sha256, 400, 200, payload,
        )

    provider = Mock(side_effect=recognize)
    monkeypatch.setattr(bootstrap, "NativeLocalImageProviderV0", lambda executor: provider)

    def serve(service, *, port):
        request = bootstrap.http.ReceiptRequest("req-t15", "img-t15", "image/png", encoded)
        context = bootstrap.http.ProcessingContext(monotonic() + 100)
        assert service._processor(replace(request, encoded_image=b"different"), context) is (
            bootstrap.http.ProcessingRefusal.UNAVAILABLE
        )
        provider.assert_not_called()
        raw = service._processor(request, context)
        assert not evidence.exists()
        presentation = json.loads(raw)
        if structured:
            assert presentation["automaticExtraction"]["producer"] == {
                "producerId": "B2_PURCHASE_DATE_CORRECTION",
                "producerVersion": "purchase-date-correction-development-v0",
            }
            assert presentation["receipt"]["receiptFields"][1]["presentationValue"] == "2026-10-15"
        else:
            assert presentation["outcome"]["status"] == "SOURCE_EVIDENCE_INSUFFICIENT"
            assert presentation["receipt"] is None

    monkeypatch.setattr(bootstrap.http, "serve_development", serve)
    bootstrap._serve_approved(launch, _TOKEN, evidence_path=evidence)
    provider.assert_called_once()
    record = json.loads(evidence.read_text(encoding="utf-8"))
    assert record["ocr_state"] == "COMPLETED" and record["recognition"] == payload
    assert record["provider_elapsed_ns"] >= 0 and record["encoded_sha256"] == launch.approval.encoded_sha256
    assert record["cleanup_confirmed"] is True
    presentation = record["validated_processor_presentation"]
    assert presentation["sourceGate"]["decision"] == ("SUFFICIENT" if structured else "INSUFFICIENT")
    assert _TOKEN.decode("ascii") not in evidence.read_text(encoding="utf-8")
    if structured:
        correction = record["purchase_date_correction"]
        assert correction["c0"]["value"] == correction["original_b2"]["purchase_date"]["value"] == "2026-10-14"
        assert correction["final_output"]["purchase_date"]["value"] == "2026-10-15"
        assert correction["decision"] == "CORRECT" and correction["reason"] == "ANCHOR_SUPPORTS_ALTERNATIVE"
        assert correction["suspicion_reasons"] == ["LINE_ASSOCIATION_CONFLICT"]
        assert correction["candidate_alternatives"][0]["provenance"]
        assert correction["features"] and correction["diagnostic_scores"] and correction["hard_constraints"]
    else:
        assert record["purchase_date_correction"] is None
    _unconfigured()


def test_generated_evidence_cap_refuses_without_creating_partial_file(tmp_path, monkeypatch):
    path = tmp_path / "generated-research-evidence.json"
    evidence = bootstrap._GeneratedResearchEvidence(path)
    evidence.ids = ("req-t15", "img-t15")
    monkeypatch.setattr(bootstrap, "_RESEARCH_EVIDENCE_LIMIT", 16)
    with pytest.raises(bootstrap.DevelopmentBootstrapRefusal, match="byte limit"):
        evidence.write(cleanup_confirmed=True)
    assert not path.exists()
