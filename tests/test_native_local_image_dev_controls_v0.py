"""T14 source-only test definitions using generated frames and host doubles."""

from dataclasses import replace
from hashlib import sha256
from ipaddress import ip_address, ip_network
import json
from pathlib import Path
from threading import Event
from time import monotonic_ns, time_ns
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pipeline import native_local_image_dev_controls_v0 as t14
from pipeline import native_local_image_executor_v0 as t13
from pipeline.native_local_image_provider_v0 import (
    NativeLocalImageStatusV0, _prepare_frame,
)
from scripts.gate_c_native_worker_host_v0 import FinalObservation, IsolationEvidence
from scripts.gate_c_ocr_b2_probe_v0 import FilePin
from tests.test_native_local_image_provider_v0 import _context, _request


@pytest.fixture
def configuration(tmp_path):
    controls_pin = _controls_pin(tmp_path, _manifest())
    source = Path(t14.__file__).resolve()
    source_bytes = source.read_bytes()
    runtime_pin = FilePin(str(source), len(source_bytes), sha256(source_bytes).hexdigest())
    frame, _, _ = _prepare_frame(_request(), _context())
    profile = t13.NativeLocalImageRuntimeProfileV0(
        launch=t13.LaunchSpec("test", str(tmp_path / "scratch"), (), ()),
        launcher=None, worker=None, runtime=(runtime_pin,), detector=(), recognizer=(),
        configuration=None, controls_manifest=controls_pin, memory_bytes=1, scratch_bytes=32,
        minimum_work_ns=1, teardown_reserve_ns=8_000_000_000,
    )
    b = frame.binding
    approval = t14.DevelopmentLocalImageRuntimeApprovalV0(
        profile, b.encoded_sha256, b.bgr8_sha256, b.width, b.height, t14.DEVELOPMENT_SCOPE,
    )
    return frame, profile, t14.DevelopmentLocalImageHostControlsV0(approval)


def test_development_default_deny_never_uses_strict_pin(configuration, monkeypatch):
    frame, profile, controls = configuration
    factory = Mock()
    monkeypatch.setattr(t13, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(t13, "_AUTHORIZED_RUNTIME", (profile, controls))
    monkeypatch.setattr(t13, "_DEVELOPMENT_RUNTIME", None)
    monkeypatch.setattr(t13, "_WindowsAttempt", factory)
    assert t13.SupervisedNativeLocalImageExecutorV0(
        profile, controls, development=True,
    )(frame, _context()).status is NativeLocalImageStatusV0.UNAVAILABLE
    factory.assert_not_called()


def test_strict_controls_do_not_fall_back_to_development(configuration, monkeypatch):
    frame, profile, controls = configuration
    factory = Mock()
    monkeypatch.setattr(t13, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(t13, "_AUTHORIZED_RUNTIME", None)
    monkeypatch.setattr(t13, "_DEVELOPMENT_RUNTIME", (profile, controls))
    monkeypatch.setattr(t13, "_WindowsAttempt", factory)
    assert t13.SupervisedNativeLocalImageExecutorV0(profile, controls)(
        frame, _context(),
    ).status is NativeLocalImageStatusV0.UNAVAILABLE
    factory.assert_not_called()


def test_strict_and_development_evidence_are_distinct(configuration):
    _, profile, controls = configuration
    cancel = Mock()
    strict = t13._WindowsAttempt(profile, controls, cancel)
    development = t13._WindowsAttempt(profile, controls, cancel, development=True)
    strict_evidence = IsolationEvidence(*([True] * 8))
    dev_evidence = t14.DevelopmentIsolationEvidenceV0(True, True, True)
    strict._require_host_evidence(strict_evidence)
    development._require_host_evidence(dev_evidence)
    with pytest.raises(t13.HostError, match="Native isolation"):
        strict._require_host_evidence(replace(strict_evidence, startup_deadline_guard_active=False))
    with pytest.raises(t13.HostError, match="Native isolation"):
        strict._require_host_evidence(dev_evidence)
    with pytest.raises(t13.HostError, match="Development host"):
        development._require_host_evidence(strict_evidence)


@pytest.mark.parametrize("substitution", ["encoded_sha256", "bgr8_sha256", "width", "scope"])
def test_generated_png_and_raster_identity_required_before_dispatch(
    substitution, configuration, monkeypatch,
):
    frame, profile, controls = configuration
    assert controls.admits(frame, profile)
    replacement = {"width": frame.binding.width + 1, "scope": "UNAPPROVED"}.get(
        substitution, "0" * 64,
    )
    other = t14.DevelopmentLocalImageHostControlsV0(
        replace(controls._approval, **{substitution: replacement}),
    )
    factory = Mock()
    monkeypatch.setattr(t13, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(t13, "_DEVELOPMENT_RUNTIME", (profile, other))
    monkeypatch.setattr(t13, "_QUARANTINED", None)
    monkeypatch.setattr(t13, "_WindowsAttempt", factory)
    result = t13.SupervisedNativeLocalImageExecutorV0(profile, other, development=True)(
        frame, _context(),
    )
    assert result.status is NativeLocalImageStatusV0.UNAVAILABLE
    factory.assert_not_called()


@pytest.mark.parametrize(("stopped", "clean"), [(True, True), (False, False), (True, False)])
def test_development_publication_requires_observed_exit_and_cleanup(
    stopped, clean, configuration, monkeypatch,
):
    frame, profile, controls = configuration
    attempt = Mock(stopped=stopped, cleaned=clean, violation=False, exit_code=0, forced=False)
    payload = {"rec_texts": (), "rec_scores": (), "rec_polys": ()}
    attempt.dispatch.return_value = NativeLocalImageStatusV0.COMPLETED, payload
    attempt.finish.return_value = clean
    factory = Mock(return_value=attempt)
    monkeypatch.setattr(t13, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(t13, "_DEVELOPMENT_RUNTIME", (profile, controls))
    monkeypatch.setattr(t13, "_QUARANTINED", None)
    monkeypatch.setattr(t13, "_profile_pins", Mock(return_value=()))
    monkeypatch.setattr(t13, "_WindowsAttempt", factory)
    monkeypatch.setattr(t13, "Thread", Mock())

    result = t13.SupervisedNativeLocalImageExecutorV0(
        profile, controls, development=True,
    )(frame, _context())
    assert result.binding == frame.binding
    assert (result.native_stopped, result.cleanup_confirmed) == (stopped, clean)
    if stopped and clean:
        assert result.status is NativeLocalImageStatusV0.COMPLETED and result.payload == payload
    else:
        assert result.status is NativeLocalImageStatusV0.FAILED and result.payload is None
        assert t13._QUARANTINED is attempt
    assert factory.call_args.kwargs == {"development": True}
    attempt.dispatch.assert_called_once()



def _manifest(**changes):
    return {
        "scope": t14.DEVELOPMENT_SCOPE,
        "network_observation": t14.NETWORK_OBSERVATION,
        "physical_disconnection_confirmed_unix_s": time_ns() // 1_000_000_000,
        **changes,
    }


def _controls_pin(tmp_path, record):
    raw = json.dumps(record).encode("utf-8")
    path = tmp_path / "development-controls.json"
    path.write_bytes(raw)
    return FilePin(str(path), len(raw), sha256(raw).hexdigest())


@pytest.mark.parametrize("defect", ["missing", "old", "future", "boolean", "wrong-profile", "modified"])
def test_physical_confirmation_is_fresh_and_bound_to_the_controls_pin(configuration, tmp_path, defect):
    frame, profile, controls = configuration
    deadline = monotonic_ns() + 5_000_000_000
    assert controls.admits(frame, profile)
    assert controls.approve(profile, deadline)

    pin = profile.controls_manifest
    if defect == "missing":
        pin = None
    elif defect == "modified":
        Path(pin.path).write_bytes(b"{}")
    elif defect == "wrong-profile":
        pin = _controls_pin(tmp_path, _manifest(network_observation="other"))
    else:
        confirmed = time_ns() // 1_000_000_000
        value = {"old": confirmed - 600, "future": confirmed + 60, "boolean": True}[defect]
        pin = _controls_pin(tmp_path, _manifest(physical_disconnection_confirmed_unix_s=value))
    profile = replace(profile, controls_manifest=pin)
    controls = t14.DevelopmentLocalImageHostControlsV0(replace(controls._approval, profile=profile))
    assert not controls.approve(profile, deadline)


def _route(index, luid, network, hop="0.0.0.0"):
    return index, luid, ip_network(network), ip_address(hop)


def _windows_tables():
    return [
        (1, 100, 24, 0, 1, 0),  # OS software loopback.
        (2, 101, 6, 5, 2, 0),  # Down hardware with unknown media, confirmed physically disconnected by owner.
        (3, 102, 23, 0, 1, 1),  # Internal software interface without an external route.
    ], [
        _route(1, 100, "127.0.0.0/8"),
        _route(1, 100, "::1/128", "::"),
        _route(2, 101, "224.0.0.0/4"),
        _route(2, 101, "255.255.255.255/32"),
        _route(2, 101, "ff00::/8", "::"),
        _route(2, 101, "fe80::/64", "::"),
        _route(2, 101, "fe80::1234/128", "::"),
    ]


def test_loopback_only_tables_allow_the_emulators_host_side_path(monkeypatch):
    monkeypatch.setattr(t14, "_windows_network_tables", lambda _: _windows_tables())
    # The guest's 10.0.2.2 maps to this Windows loopback. It needs no host-side private subnet.
    assert t14._offline_sample(monotonic_ns() + 1_000_000_000)


@pytest.mark.parametrize("defect", [
    "physical-up", "connected-media", "connector-only", "v4-default", "v6-default",
    "gateway", "virtual-private-subnet", "nonloopback-loopback-route",
])
def test_external_or_unverified_network_path_is_refused(monkeypatch, defect):
    links, routes = _windows_tables()
    if defect == "physical-up":
        links[1] = (2, 101, 6, 5, 1, 0)
    elif defect == "connected-media":
        links[1] = (2, 101, 6, 5, 2, 1)
    elif defect == "connector-only":
        links[1] = (2, 101, 6, 4, 1, 0)
    else:
        routes.append({
            "v4-default": _route(2, 101, "0.0.0.0/0"),
            "v6-default": _route(3, 102, "::/0", "::"),
            "gateway": _route(3, 102, "198.51.100.0/24", "192.168.1.1"),
            "virtual-private-subnet": _route(3, 102, "10.0.2.0/24"),
            "nonloopback-loopback-route": _route(3, 102, "127.0.0.1/32"),
        }[defect])
    monkeypatch.setattr(t14, "_windows_network_tables", lambda _: (links, routes))
    assert not t14._offline_sample(monotonic_ns() + 1_000_000_000)


def test_network_table_decode_uses_native_row_stride_and_frees_memory():
    from ctypes import POINTER, Structure, addressof, c_void_p, cast, sizeof
    from ctypes.wintypes import ULONG

    class Routes(Structure):
        _fields_ = [("count", ULONG), ("rows", t14._RouteRow * 2)]

    table = Routes(count=2)
    first, second = table.rows
    for row, family, prefix in ((first, 2, 8), (second, 23, 128)):
        row.index, row.luid = 1, 100
        row.destination.address.family = row.next_hop.family = family
        row.destination.length = prefix
    first.destination.address.ipv4_or_flow[:] = 127, 0, 0, 0
    second.destination.address.ipv6[-1] = 1
    released = Mock()

    def query(out):
        cast(out, POINTER(c_void_p))[0] = addressof(table)
        return 0

    assert (sizeof(t14._InterfaceRow), sizeof(t14._RouteRow), t14._RouteTable.first.offset) == (1352, 104, 8)
    assert t14._read_table(
        query, released, t14._RouteTable, monotonic_ns() + 1_000_000_000, t14._route_evidence,
    ) == [_route(1, 100, "127.0.0.0/8"), _route(1, 100, "::1/128", "::")]
    assert released.call_args.args[0].value == addressof(table)

    released.reset_mock()
    second.destination.length = 129
    with pytest.raises(ValueError):
        t14._read_table(
            query, released, t14._RouteTable, monotonic_ns() + 1_000_000_000, t14._route_evidence,
        )
    released.assert_called_once()


def test_missing_route_interface_fails_closed(monkeypatch):
    links, routes = _windows_tables()
    routes.append(_route(1, 999, "127.0.0.0/8"))
    monkeypatch.setattr(t14, "_windows_network_tables", lambda _: (links, routes))
    with pytest.raises(t14.HostError, match="route interface association"):
        t14._offline_sample(monotonic_ns() + 1_000_000_000)


@pytest.mark.parametrize("failure", [None, "network-change", "query-error", "post-refusal"])
def test_monitor_uses_pre_during_and_post_samples_and_preserves_cleanup(configuration, monkeypatch, failure):
    _, profile, controls = configuration
    monkeypatch.setattr(t14, "_SAMPLE_INTERVAL", 0.005)
    scratch = Mock()
    monkeypatch.setattr(t14, "_Scratch", Mock(return_value=scratch))
    periodic = Event()
    samples = []

    def sample(deadline):
        phase = "post" if deadline == controls._post_deadline else "periodic" if samples else "pre"
        samples.append(phase)
        if phase == "periodic":
            periodic.set()
            if failure == "query-error":
                raise OSError("observation unavailable")
            return failure != "network-change"
        return phase != "post" or failure != "post-refusal"

    monkeypatch.setattr(t14, "_offline_sample", sample)
    deadline = monotonic_ns() + 5_000_000_000
    cancellation = controls.monitor_cancellation(Event())
    assert controls.before_launch(profile, deadline).permits_development()
    assert periodic.wait(2)
    if failure in ("network-change", "query-error"):
        assert controls._violation.wait(2)
        assert cancellation.is_set()
    assert controls.finish(None, profile, deadline) == FinalObservation(True, failure is not None)
    assert samples[0] == "pre" and samples[-1] == "post" and samples.count("post") == 1
    assert controls.violation_seen(profile) is (failure is not None)
    scratch.clean.assert_called_once_with(deadline)


def test_monitor_with_expired_or_missing_evidence_cancels(configuration, monkeypatch):
    _, profile, controls = configuration
    now = monotonic_ns()
    monkeypatch.setattr(t14, "monotonic_ns", lambda: now)
    controls._scratch = Mock()
    controls._thread = Mock(is_alive=lambda: True)
    controls._confirmed_until = now + 20_000_000_000
    controls._last_sample = now - t14._MAX_SAMPLE_AGE_NS + 1
    assert controls._evidence().permits_development()
    controls._thread.is_alive = lambda: False
    assert not controls._evidence().permits_development()
    controls._thread.is_alive = lambda: True
    now += 1
    assert controls.monitor_cancellation(Event()).is_set()
    assert controls.violation_seen(profile)


@pytest.mark.parametrize("cancelled", [False, True])
def test_stalled_initial_observation_bounds_prelaunch_wait(configuration, monkeypatch, cancelled):
    _, profile, controls = configuration
    scratch = Mock()
    monkeypatch.setattr(t14, "_Scratch", Mock(return_value=scratch))
    release = Event()
    requested = Event()

    def sample(_deadline):
        if cancelled:
            requested.set()
        assert release.wait(2)
        return True

    monkeypatch.setattr(t14, "_offline_sample", sample)
    monkeypatch.setattr(t14, "_QUERY_LIMIT_NS", 200_000_000)
    controls.monitor_cancellation(requested)
    deadline = monotonic_ns() + 5_000_000_000
    try:
        with pytest.raises(InterruptedError if cancelled else t14.HostError):
            controls.before_launch(profile, deadline)
    finally:
        release.set()
    assert controls.finish(None, profile, deadline) == FinalObservation(True, True)
    scratch.clean.assert_called_once_with(deadline)


def test_cleanup_failure_refuses_publication_even_after_positive_observation(configuration, monkeypatch):
    _, profile, controls = configuration
    scratch = Mock()
    scratch.clean.side_effect = OSError
    monkeypatch.setattr(t14, "_Scratch", Mock(return_value=scratch))
    monkeypatch.setattr(t14, "_offline_sample", Mock(return_value=True))
    deadline = monotonic_ns() + 5_000_000_000
    assert controls.before_launch(profile, deadline).permits_development()
    assert controls.finish(None, profile, deadline) == FinalObservation(False, True)
    assert controls.violation_seen(profile)


def test_cleanup_retry_waits_for_stalled_post_observation(configuration, monkeypatch):
    _, profile, controls = configuration
    scratch = Mock()
    monkeypatch.setattr(t14, "_Scratch", Mock(return_value=scratch))
    release = Event()

    def sample(deadline):
        if deadline == controls._post_deadline:
            assert release.wait(2)
            t14._check_time(deadline)
        return True

    monkeypatch.setattr(t14, "_offline_sample", sample)
    deadline = monotonic_ns() + 5_000_000_000
    assert controls.before_launch(profile, deadline).permits_development()
    monkeypatch.setattr(t14, "_QUERY_LIMIT_NS", 50_000_000)
    try:
        assert controls.finish(None, profile, deadline) == FinalObservation(False, True)
        scratch.clean.assert_not_called()
        join = controls._thread.join

        def retry_join(timeout):
            assert timeout > 0
            release.set()
            join(timeout)

        monkeypatch.setattr(controls._thread, "join", retry_join)
        assert controls.finish(None, profile, deadline) == FinalObservation(True, True)
        scratch.clean.assert_called_once_with(deadline)
    finally:
        release.set()
