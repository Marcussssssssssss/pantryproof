"""T13 test definitions. No real worker or native inference is needed."""

from dataclasses import asdict, replace
from hashlib import sha256
import json
from threading import Event
from time import monotonic
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pipeline import backend_local_image_receipt_v0 as t10
from pipeline import native_local_image_executor_v0 as t13
from pipeline.native_local_image_provider_v0 import (
    NativeLocalImageBindingV0, NativeLocalImageInputV0, NativeLocalImageProviderV0,
    NativeLocalImageStatusV0,
)
from tests.test_native_local_image_provider_v0 import _request


def _frame():
    raster = bytes((30, 20, 10, 255, 255, 255))
    return NativeLocalImageInputV0(
        NativeLocalImageBindingV0(
            "gat-test", "req-test", "img-test", sha256(b"admitted").hexdigest(),
            sha256(raster).hexdigest(), 2, 1,
        ),
        raster,
    )


def _context(event=None, deadline=None):
    return t10.LocalImageProcessingContextV0(
        monotonic() + 60 if deadline is None else deadline,
        Event() if event is None else event,
    )


def _payload():
    return {"rec_texts": ["  ORIGINAL  "], "rec_scores": [0.82],
            "rec_polys": [[[0, 0], [2, 0], [2, 1], [0, 1]]]}


def _empty():
    return {"rec_texts": [], "rec_scores": [], "rec_polys": []}


def _wire(binding, *, status="COMPLETED", payload=None, nonce="abc"):
    return json.dumps({
        "version": t13._FRAME_VERSION, "binding": asdict(binding), "dispatch": nonce,
        "status": status, "payload": payload,
    }).encode("ascii")


def test_default_unavailable_preserves_verified_binding(monkeypatch):
    dispatch = Mock(side_effect=AssertionError("No native work permitted."))
    monkeypatch.setattr(t13, "_WindowsAttempt", dispatch)
    frame = _frame()
    result = t13.SupervisedNativeLocalImageExecutorV0()(frame, _context())
    assert result.binding == frame.binding
    assert result.status is NativeLocalImageStatusV0.UNAVAILABLE
    assert result.native_stopped is result.cleanup_confirmed is True and result.payload is None
    dispatch.assert_not_called()


@pytest.mark.parametrize("defect", ["length", "digest", "dimension", "attempt-id", "encoded-digest"])
def test_malformed_frame_is_refused_before_dispatch(defect, monkeypatch):
    frame = _frame()
    dispatch = Mock()
    monkeypatch.setattr(t13, "_WindowsAttempt", dispatch)
    if defect == "length":
        frame = replace(frame, packed_bgr8=frame.packed_bgr8[:-1])
    else:
        attribute, value = {
            "digest": ("bgr8_sha256", "0" * 64), "dimension": ("width", 1601),
            "attempt-id": ("attempt_id", "bad id"), "encoded-digest": ("encoded_sha256", "bad"),
        }[defect]
        frame = replace(frame, binding=replace(frame.binding, **{attribute: value}))
    with pytest.raises(t13.NativeLocalImageInputError):
        t13.SupervisedNativeLocalImageExecutorV0()(frame, _context())
    dispatch.assert_not_called()


@pytest.mark.parametrize("member", ["attempt_id", "image_id", "request_id", "encoded_sha256", "bgr8_sha256", "dispatch"])
def test_terminal_requires_exact_worker_association(member):
    binding = _frame().binding
    if member == "dispatch":
        raw = _wire(binding, payload=_empty(), nonce="wrong")
    else:
        raw = _wire(replace(binding, **{member: "0" * 64}), payload=_empty())
    with pytest.raises(t13.HostError, match="terminal binding"):
        t13._terminal(raw, "abc", binding)


def test_terminal_accepts_zero_tokens_and_distinguishes_native_failure():
    binding = _frame().binding
    assert t13._terminal(_wire(binding, payload=_empty()), "abc", binding) == (
        NativeLocalImageStatusV0.COMPLETED, {"rec_texts": (), "rec_scores": (), "rec_polys": ()},
    )
    assert t13._terminal(_wire(binding, status="FAILED"), "abc", binding) == (
        NativeLocalImageStatusV0.FAILED, None,
    )


@pytest.mark.parametrize("defect", ["protocol-size", "region-count", "coordinate", "worker-teardown"])
def test_worker_recognition_admission_is_bounded(defect):
    binding = _frame().binding
    payload = _payload()
    if defect == "protocol-size":
        raw = b"x" * (t13._MAX_TERMINAL_BYTES + 1)
    elif defect == "worker-teardown":
        reply = json.loads(_wire(binding, payload=payload))
        reply["native_stopped"] = reply["cleanup_confirmed"] = True
        raw = json.dumps(reply).encode("ascii")
    else:
        if defect == "region-count":
            payload = {key: value * 129 for key, value in payload.items()}
        else:
            payload["rec_polys"][0][0][0] = 3
        raw = _wire(binding, payload=payload)
    with pytest.raises((ValueError, t13.HostError)):
        t13._terminal(raw, "abc", binding)


@pytest.fixture
def approved(monkeypatch):
    def configure(*, stopped=True, clean=True, violation=False, exit_code=0, cancel_event=None,
                  status=NativeLocalImageStatusV0.COMPLETED):
        profile = SimpleNamespace(minimum_work_ns=1_000_000, teardown_reserve_ns=8_000_000_000)
        controls = object()
        attempt = Mock(stopped=stopped, cleaned=clean, violation=violation, exit_code=exit_code, forced=False)

        def dispatch(frame, pins, work_deadline):
            assert pins == ("approved",)
            if cancel_event is not None:
                cancel_event.set()
            payload = _payload() if status is NativeLocalImageStatusV0.COMPLETED else None
            return status, payload

        attempt.dispatch.side_effect = dispatch
        attempt.finish.return_value = clean
        monkeypatch.setattr(t13, "sys", SimpleNamespace(platform="win32"))
        monkeypatch.setattr(t13, "_AUTHORIZED_RUNTIME", (profile, controls))
        monkeypatch.setattr(t13, "_QUARANTINED", None)
        monkeypatch.setattr(t13, "_profile_pins", lambda received: ("approved",) if received is profile else ())
        monkeypatch.setattr(t13, "_WindowsAttempt", Mock(return_value=attempt))
        monkeypatch.setattr(t13, "Thread", Mock())
        return t13.SupervisedNativeLocalImageExecutorV0(profile, controls), attempt
    return configure


def test_budget_and_precancel_leave_native_dispatched_zero_times(approved):
    executor, attempt = approved()
    event = Event()
    event.set()
    for context in (_context(deadline=monotonic() + 1), _context(event)):
        assert executor(_frame(), context).status is NativeLocalImageStatusV0.UNAVAILABLE
    attempt.dispatch.assert_not_called()


def test_late_cancellation_discards_recognition_after_host_cleanup(approved):
    event = Event()
    executor, attempt = approved(cancel_event=event)
    context = _context(event)
    result = executor(_frame(), context)
    assert result.status is NativeLocalImageStatusV0.FAILED and result.payload is None
    assert result.native_stopped is result.cleanup_confirmed is True
    work, overall = attempt.finish.call_args.args
    assert overall - work == 8_000_000_000
    assert overall == int(context.deadline * 1_000_000_000)


@pytest.mark.parametrize(("stopped", "clean", "violation"), [
    (False, False, False), (True, False, False), (True, True, True),
])
def test_unconfirmed_or_isolation_violation_quarantines_all_executors(approved, stopped, clean, violation):
    executor, attempt = approved(stopped=stopped, clean=clean, violation=violation)
    first = executor(_frame(), _context())
    assert first.status is NativeLocalImageStatusV0.FAILED and first.payload is None
    assert (first.native_stopped, first.cleanup_confirmed) == (stopped, clean)
    second = t13.SupervisedNativeLocalImageExecutorV0(executor.profile, executor.controls)(_frame(), _context())
    assert second.status is NativeLocalImageStatusV0.UNAVAILABLE and second.payload is None
    attempt.dispatch.assert_called_once()
    attempt.finish.assert_called_once()


def test_native_failure_has_no_recognition(approved):
    executor, _ = approved(status=NativeLocalImageStatusV0.FAILED)
    result = executor(_frame(), _context())
    assert result.status is NativeLocalImageStatusV0.FAILED
    assert result.payload is None and result.native_stopped and result.cleanup_confirmed


def test_clean_host_completion_composes_through_original_t12_adapter(approved):
    executor, attempt = approved()
    request = _request()
    recognized = NativeLocalImageProviderV0(executor)(request, _context())
    assert recognized.request is request and recognized.image_sha256 == request.image_sha256
    assert recognized.payload["rec_texts"] == ("  ORIGINAL  ",)
    assert recognized.payload["rec_scores"] == (0.82,)
    assert recognized.payload["rec_polys"] == (((0, 0), (2, 0), (2, 1), (0, 1)),)
    attempt.dispatch.assert_called_once()
    attempt.finish.assert_called_once()


def test_host_does_not_count_root_exit_as_empty_job():
    profile = SimpleNamespace()
    attempt = t13._WindowsAttempt(profile, None, t13._Cancellation(_context()))
    attempt.process.handle = 31
    attempt.job = 42
    observed = []
    clock = iter(range(100, 105))

    def query(handle, info_class, destination, size, returned):
        observed.append((handle, info_class))
        destination._obj.active = 1
        return True

    attempt.win = SimpleNamespace(
        api=SimpleNamespace(WaitForSingleObject=lambda *_: 0, GetExitCodeProcess=Mock(return_value=0)),
        QueryInformationJobObject=query,
    )
    from unittest.mock import patch

    with patch.object(t13, "monotonic_ns", side_effect=lambda: next(clock)):
        assert not attempt._wait_stopped(104)
    assert observed == [(42, 1), (42, 1)]
    attempt.win.api.GetExitCodeProcess.assert_not_called()


def test_profile_pins_requires_distinct_bound_base_and_venv_executables(monkeypatch):
    venv = t13._ROOT / ".venv"
    site_packages = venv / "Lib" / "site-packages"
    fixture_root = t13._ROOT.parent / "t13-profile-fixture"
    base = fixture_root / "Python" / "python.exe"
    launcher = venv / "Scripts" / "python.exe"

    def pin(path):
        fixture_bytes = str(path).encode("utf-8")
        return t13.probe.FilePin(str(path), len(fixture_bytes), sha256(fixture_bytes).hexdigest())

    def model_pins(name):
        return tuple(pin(fixture_root / "models" / name / file) for file in t13.probe._MODEL_FILES)

    profile = t13.NativeLocalImageRuntimeProfileV0(
        launch=t13.LaunchSpec(
            str(base), str(fixture_root / "scratch"), (str(t13._ROOT), str(site_packages)),
            (("SystemRoot", str(fixture_root / "Windows")),),
        ),
        launcher=pin(launcher),
        worker=pin(t13._WORKER),
        runtime=(
            pin(base), pin(venv / "pyvenv.cfg"),
            pin(t13._ROOT / "pipeline" / "native_local_image_executor_v0.py"),
            pin(t13._ROOT / "scripts" / "gate_c_native_worker_host_v0.py"),
            pin(t13._ROOT / "scripts" / "gate_c_ocr_b2_probe_v0.py"),
            pin(t13._ROOT / "scripts" / "synthetic_receipt_backend_smoke_v0.py"),
        ),
        detector=model_pins(t13.probe._DETECTOR),
        recognizer=model_pins(t13.probe._RECOGNIZER),
        configuration=pin(site_packages / "paddlex" / "configs" / "pipelines" / "OCR.yaml"),
        controls_manifest=pin(fixture_root / "controls.json"),
        memory_bytes=1024**3,
        scratch_bytes=1024**2,
        minimum_work_ns=1_000_000_000,
        teardown_reserve_ns=8_000_000_000,
    )
    monkeypatch.setattr(t13, "sys", SimpleNamespace(_base_executable=str(base)))

    assert t13._profile_pins(profile) == (
        profile.launcher, profile.worker, profile.configuration, profile.controls_manifest,
        *profile.runtime, *profile.detector, *profile.recognizer,
    )

    # Supply a matching runtime pin so absence of that pin cannot cause refusal.
    substituted_base = base.with_name("other-python.exe")
    bad_base = replace(
        profile, launch=replace(profile.launch, executable=str(substituted_base)),
        runtime=(pin(substituted_base), *profile.runtime[1:]),
    )
    with pytest.raises(t13.HostError, match="runtime or scratch association"):
        t13._profile_pins(bad_base)
    with pytest.raises(t13.HostError, match="runtime or scratch association"):
        t13._profile_pins(replace(profile, launcher=pin(launcher.with_name("other-python.exe"))))

    # Simulate a base identity that resolves to the venv launcher itself.
    monkeypatch.setattr(t13, "sys", SimpleNamespace(_base_executable=str(launcher)))
    same_executable = replace(
        profile, launch=replace(profile.launch, executable=str(launcher)),
        runtime=(pin(launcher), *profile.runtime[1:]),
    )
    with pytest.raises(t13.HostError, match="runtime or scratch association"):
        t13._profile_pins(same_executable)
