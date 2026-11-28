"""Supervised Windows execution of one T12 BGR8 frame.

Runtime authority is absent by default. A future approved bootstrap must
provide the exact LOCAL_IMAGE profile and independent host controls. Then use
NativeLocalImageProviderV0(SupervisedNativeLocalImageExecutorV0(profile, controls)),
wrap that provider in T10's LocalImageRuntimeApprovalV0, and pass the enabled
coordinator through as_t09_receipt_processor_v0 to ReceiptHttpService.
"""

from __future__ import annotations

from ctypes import Structure, byref, c_size_t, sizeof
from ctypes import wintypes as wt
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from secrets import token_hex
import sys
from threading import Lock, Thread
from time import monotonic_ns
from types import SimpleNamespace
from typing import Protocol

from pipeline.backend_local_image_receipt_v0 import (
    LocalImageProcessingContextV0, _capture_processing_context, _snapshot_payload,
)
from pipeline.native_local_image_provider_v0 import (
    NativeLocalImageBindingV0, NativeLocalImageCompletionV0, NativeLocalImageInputV0,
    NativeLocalImageStatusV0, _binding_matches,
)
from pipeline.presentation_v1.conformance import _protocol_id
from pipeline.real_receipt_http_service_v1 import MAX_IMAGE_DIMENSION
from scripts import gate_c_ocr_b2_probe_v0 as probe
from scripts.gate_c_native_worker_host_v0 import (
    FinalObservation, HostError, IsolationEvidence, LaunchSpec, RegisteredProcess,
    _EXTENDED_JOB_INFORMATION, _ExtendedLimits, _JOB_LIMITS, _Overlapped,
    _IO_PENDING, _PIPE_CONNECTED, _WAIT_TIMEOUT, _Pipe, _ProcessInfo, _Win32,
    _launch_ok, _same_path, _verify_file,
)


_ROOT = Path(__file__).absolute().parents[1]
_WORKER = _ROOT / "scripts" / "native_local_image_worker_v0.py"
_MAX_RASTER_BYTES = 3 * MAX_IMAGE_DIMENSION**2
_MAX_METADATA_BYTES = 8192
_MAX_TERMINAL_BYTES = 512 * 1024
_FRAME_VERSION = "pantryproof-t13-native-v0"
_HASH = re.compile(r"[0-9a-f]{64}")
_NONCE = re.compile(r"[0-9a-f]{32}")
_BOOTSTRAP = (
    "import runpy,sys; script=sys.argv[1]; n=int(sys.argv[2]); "
    "sys.path.extend(sys.argv[3:3+n]); sys.argv=[script,*sys.argv[3+n:]]; "
    "runpy.run_path(script,run_name='__main__')"
)


@dataclass(frozen=True, slots=True, repr=False)
class NativeLocalImageRuntimeProfileV0:
    launch: LaunchSpec  # executable is the base Python, working_directory is private scratch
    launcher: probe.FilePin  # virtual-environment launcher identity, never started here
    worker: probe.FilePin
    runtime: tuple[probe.FilePin, ...]
    detector: tuple[probe.FilePin, ...]
    recognizer: tuple[probe.FilePin, ...]
    configuration: probe.FilePin
    controls_manifest: probe.FilePin
    memory_bytes: int
    scratch_bytes: int
    minimum_work_ns: int
    teardown_reserve_ns: int
    cpu_threads: int = 2


class NativeLocalImageHostControlsV0(Protocol):
    """Independent, provisioned policy for LOCAL_IMAGE, with bounded methods.

    Before launch, verify offline and private filesystem/scratch controls and
    start monitoring, including an independent guard for synchronous startup.
    At suspension, verify the child and its containment before it can run.
    Finish observes scratch and isolation after the entire job has exited.
    This interface never installs security policy.
    """

    def approve(self, profile: NativeLocalImageRuntimeProfileV0, deadline: int) -> bool: ...
    def before_launch(self, profile: NativeLocalImageRuntimeProfileV0, deadline: int) -> IsolationEvidence: ...
    def suspended_process(
        self, process: RegisteredProcess, profile: NativeLocalImageRuntimeProfileV0, deadline: int,
    ) -> IsolationEvidence: ...
    def finish(
        self, process: RegisteredProcess | None, profile: NativeLocalImageRuntimeProfileV0, deadline: int,
    ) -> FinalObservation: ...
    def violation_seen(self, profile: NativeLocalImageRuntimeProfileV0) -> bool: ...


# Installed only by separately authorized LOCAL_IMAGE provisioning. Identity
# comparison prevents a supplied profile or T11 approval from enabling itself.
_AUTHORIZED_RUNTIME: tuple[NativeLocalImageRuntimeProfileV0, NativeLocalImageHostControlsV0] | None = None
_DEVELOPMENT_RUNTIME = None  # Exact (profile, T14 controls) pair, authorized separately.
_PROTOTYPE_RUNTIME = None
_ACTIVE = Lock()
_QUARANTINED: _WindowsAttempt | None = None


class NativeLocalImageInputError(ValueError):
    """An input without an independently verified T12 binding."""


def _binding(value: NativeLocalImageBindingV0) -> None:
    if (
        type(value) is not NativeLocalImageBindingV0
        or type(value.width) is not int or type(value.height) is not int
        or not 1 <= value.width <= MAX_IMAGE_DIMENSION or not 1 <= value.height <= MAX_IMAGE_DIMENSION
    ):
        raise NativeLocalImageInputError("Invalid native frame binding.")
    for identifier in (value.attempt_id, value.request_id, value.image_id):
        if type(identifier) is not str or not 0 < len(identifier) <= 96:
            raise NativeLocalImageInputError("Invalid native frame identity.")
        try:
            _protocol_id(identifier, "$context.sourceId")
        except ValueError:
            raise NativeLocalImageInputError("Invalid native frame identity.") from None
    for digest in (value.encoded_sha256, value.bgr8_sha256):
        if type(digest) is not str or len(digest) != 64 or _HASH.fullmatch(digest) is None:
            raise NativeLocalImageInputError("Invalid native frame digest.")


def _validate_frame(frame: NativeLocalImageInputV0) -> NativeLocalImageInputV0:
    if type(frame) is not NativeLocalImageInputV0 or type(frame.packed_bgr8) is not bytes:
        raise NativeLocalImageInputError("Invalid native frame.")
    binding = frame.binding
    _binding(binding)
    binding = replace(binding)
    raster = frame.packed_bgr8
    if (
        len(raster) != 3 * binding.width * binding.height or len(raster) > _MAX_RASTER_BYTES
        or sha256(raster).hexdigest() != binding.bgr8_sha256
    ):
        raise NativeLocalImageInputError("Native raster length or digest differs.")
    return NativeLocalImageInputV0(binding, raster)


def _pack(value: dict, maximum: int) -> bytes:
    data = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")
    if not 0 < len(data) <= maximum:
        raise HostError("Native IPC frame size refused.")
    return data


def _unique_pairs(entries):
    value = dict(entries)
    if len(value) != len(entries):
        raise HostError("Duplicate native IPC member.")
    return value


def _invalid_constant(_value):
    raise HostError("Invalid native IPC numeric constant.")


def _unpack(data: bytes | None, maximum: int) -> dict:
    if type(data) is not bytes or not 0 < len(data) <= maximum:
        raise HostError("Native IPC frame size refused.")
    value = json.loads(
        data.decode("ascii"), object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant,
    )
    if type(value) is not dict:
        raise HostError("Invalid native IPC frame.")
    return value


def _recognized_payload(payload, binding: NativeLocalImageBindingV0) -> dict:
    # The same bounded plain recognition admission is used in T10 and T12.
    if type(payload) is not dict or set(payload) != {"rec_texts", "rec_scores", "rec_polys"}:
        raise HostError("Invalid native recognition fields.")
    snapshot = _snapshot_payload(SimpleNamespace(payload=payload, width=binding.width, height=binding.height))
    polygons = snapshot.get("rec_polys")
    if (
        "rec_scores" not in snapshot or polygons is None
        or any(type(polygon) is not tuple or len(polygon) < 3 for polygon in polygons)
        or sum(map(len, polygons)) > 1024
    ):
        raise HostError("Native recognition geometry refused.")
    return snapshot


def _terminal(data: bytes | None, nonce: str, expected: NativeLocalImageBindingV0):
    value = _unpack(data, _MAX_TERMINAL_BYTES)
    if (
        set(value) != {"version", "dispatch", "binding", "status", "payload"}
        or value["version"] != _FRAME_VERSION or value["dispatch"] != nonce
        or type(value["binding"]) is not dict
        or not _binding_matches(NativeLocalImageBindingV0(**value["binding"]), expected)
    ):
        raise HostError("Native terminal binding refused.")
    status = NativeLocalImageStatusV0(value["status"])
    if status is NativeLocalImageStatusV0.COMPLETED:
        return status, _recognized_payload(value["payload"], expected)
    if status is not NativeLocalImageStatusV0.FAILED or value["payload"] is not None:
        raise HostError("Invalid native terminal status.")
    return status, None


def _profile_pins(profile: NativeLocalImageRuntimeProfileV0) -> tuple[probe.FilePin, ...]:
    if (
        type(profile) is not NativeLocalImageRuntimeProfileV0 or not _launch_ok(profile.launch)
        or type(profile.runtime) is not tuple or not 1 <= len(profile.runtime) <= 64
        or not probe._model_pins(profile.detector, probe._DETECTOR)
        or not probe._model_pins(profile.recognizer, probe._RECOGNIZER)
        or type(profile.cpu_threads) is not int or profile.cpu_threads != 2
        or not all(type(number) is int and 0 < number < (1 << 63) for number in (
            profile.memory_bytes, profile.scratch_bytes, profile.minimum_work_ns, profile.teardown_reserve_ns,
        ))
        or profile.memory_bytes >= 1 << (8 * sizeof(c_size_t))
    ):
        raise HostError("Native runtime profile refused.")
    pins = (profile.launcher, profile.worker, profile.configuration, profile.controls_manifest,
            *profile.runtime, *profile.detector, *profile.recognizer)
    if not all(probe._file_pin(pin) for pin in pins):
        raise HostError("Native runtime pin invalid.")

    venv = _ROOT / ".venv"
    scratch = Path(profile.launch.working_directory)
    runtime_paths = tuple(pin.path for pin in profile.runtime)
    required_paths = (
        profile.launch.executable, str(venv / "pyvenv.cfg"), str(Path(__file__).absolute()),
        str(_ROOT / "scripts" / "gate_c_native_worker_host_v0.py"),
        str(_ROOT / "scripts" / "gate_c_ocr_b2_probe_v0.py"),
        str(_ROOT / "scripts" / "synthetic_receipt_backend_smoke_v0.py"),
    )
    expected_imports = (str(_ROOT), str(venv / "Lib" / "site-packages"))
    if (
        not _same_path(profile.launch.executable, sys._base_executable)
        or _same_path(profile.launch.executable, profile.launcher.path)
        or not _same_path(profile.launcher.path, str(venv / "Scripts" / "python.exe"))
        or not _same_path(profile.worker.path, str(_WORKER))
        or len(profile.launch.import_paths) != len(expected_imports)
        or not all(_same_path(a, b) for a, b in zip(profile.launch.import_paths, expected_imports))
        or not _same_path(profile.configuration.path, str(
            Path(expected_imports[1]) / "paddlex" / "configs" / "pipelines" / "OCR.yaml"
        ))
        or not all(any(_same_path(path, pin) for pin in runtime_paths) for path in required_paths)
        or scratch.is_relative_to(_ROOT) or _ROOT.is_relative_to(scratch)
        or any(Path(pin.path).is_relative_to(scratch) for pin in pins)
    ):
        raise HostError("Native runtime or scratch association refused.")
    return pins


@dataclass(frozen=True, slots=True)
class _Cancellation:
    context: LocalImageProcessingContextV0

    def is_set(self) -> bool:
        value = self.context.cancel_event.is_set()
        if type(value) is not bool:
            raise HostError("Native cancellation signal invalid.")
        return value


class _JobAccounting(Structure):
    _fields_ = [
        ("times", wt.LARGE_INTEGER * 4), ("faults", wt.DWORD), ("total", wt.DWORD),
        ("active", wt.DWORD), ("terminated", wt.DWORD),
    ]


class _WindowsAttempt:
    """Own one atomically assigned, one-process Windows job and private pipe."""

    def __init__(self, profile, controls, cancel, *, development=False):
        self.profile, self.controls = profile, controls
        self.development = development
        self.cancel = controls.monitor_cancellation(cancel) if development else cancel
        self.nonce = token_hex(16)
        self.win = None
        self.job = self.peer = self.stdio = self.pipe = None
        self.process = _ProcessInfo()
        self.monitoring = False
        self.stopped = False
        self.cleaned = False
        self.violation = False
        self.exit_code = None
        self.forced = False

    def _registered(self):
        if self.process.handle:
            return RegisteredProcess(self.process.handle, self.process.pid)
        return None

    def _check(self, deadline):
        if self.cancel.is_set():
            raise InterruptedError("Native attempt cancelled.")
        if monotonic_ns() >= deadline:
            raise TimeoutError("Native attempt deadline reached.")

    def _require_isolation(self, evidence):
        if type(evidence) is not IsolationEvidence or not evidence.complete():
            self.violation = True
            raise HostError("Native isolation unconfirmed.")

    def _require_host_evidence(self, evidence):
        if not self.development:
            self._require_isolation(evidence)
            return
        from pipeline.native_local_image_dev_controls_v0 import DevelopmentIsolationEvidenceV0

        if type(evidence) is not DevelopmentIsolationEvidenceV0 or not evidence.permits_development():
            self.violation = True
            raise HostError("Development host observations unconfirmed.")

    def _open_job(self):
        self.job = self.win.CreateJobObjectW(None, None)
        if not self.job:
            raise HostError("Native job unavailable.")
        limits = _ExtendedLimits()
        limits.basic.flags = _JOB_LIMITS
        limits.basic.active_process_limit = 1
        limits.process_memory = limits.job_memory = self.profile.memory_bytes
        observed = _ExtendedLimits()
        if (
            not self.win.SetInformationJobObject(self.job, _EXTENDED_JOB_INFORMATION, byref(limits), sizeof(limits))
            or not self.win.QueryInformationJobObject(
                self.job, _EXTENDED_JOB_INFORMATION, byref(observed), sizeof(observed), None,
            )
            or observed.basic.flags != _JOB_LIMITS or observed.basic.active_process_limit != 1
            or observed.process_memory != limits.process_memory or observed.job_memory != limits.job_memory
        ):
            raise HostError("Native job limits unconfirmed.")

    def _open_pipe(self):
        win, api = self.win, self.win.api
        name = r"\\.\pipe\pantryproof-t13-" + token_hex(32)
        handle = win.open_pipe(name)
        self.pipe = _Pipe(win, handle, _MAX_RASTER_BYTES, self.cancel)
        self.peer = api.CreateFile(
            name, api.GENERIC_READ | api.GENERIC_WRITE, 0, 0, api.OPEN_EXISTING,
            api.FILE_FLAG_OVERLAPPED | 0x00110000, 0,
        )
        operation = _Overlapped()
        operation.event = api.CreateEvent(None, True, False, None)
        self.pipe.pending = operation, None
        connected = win.ConnectNamedPipe(handle, byref(operation))
        error = 0 if connected else win.last_error()
        if error != _IO_PENDING:  # _Pipe.close owns pending operations.
            api.CloseHandle(operation.event)
            self.pipe.pending = None
        if error != _PIPE_CONNECTED or win.pipe_pid(handle, server=False) != os.getpid():
            self.violation = True
            raise HostError("Native pipe ownership unconfirmed.")
        self.stdio = api.CreateFile("NUL", api.GENERIC_READ | api.GENERIC_WRITE, 3, 0, api.OPEN_EXISTING, 0, 0)

    def _close(self, owner, field):
        handle = getattr(owner, field)
        if handle:
            self.win.api.CloseHandle(handle)
            setattr(owner, field, None)

    def dispatch(self, frame: NativeLocalImageInputV0, pins, deadline: int):
        self._check(deadline)
        if self.controls.approve(self.profile, deadline) is not True:
            raise HostError("Native runtime authority refused.")
        self.monitoring = True
        self._require_host_evidence(self.controls.before_launch(self.profile, deadline))
        for pin in pins:
            self._check(deadline)
            _verify_file(pin, deadline)
        launch = self.profile.launch
        bootstrap = _pack({
            "version": _FRAME_VERSION, "dispatch": self.nonce, "binding": asdict(frame.binding),
            "configuration": self.profile.configuration.path,
            "detector": self.profile.detector[0].path, "recognizer": self.profile.recognizer[0].path,
            "scratch": launch.working_directory,
        }, _MAX_METADATA_BYTES)
        self.win = _Win32()
        self._open_job()
        self._open_pipe()
        self._check(deadline)
        argv = [
            launch.executable, "-I", "-S", "-B", "-c", _BOOTSTRAP,
            self.profile.worker.path, str(len(launch.import_paths)), *launch.import_paths,
            "--t13-worker", str(self.peer), str(os.getpid()), str(deadline),
        ]
        self.win.launch_suspended(launch, argv, self.peer, self.stdio, self.job, self.process)
        self._close(self, "peer")  # The parent must release its client copy for EOF.
        self._close(self, "stdio")
        registered = self._registered()
        if registered is None:
            raise HostError("Native process registration unconfirmed.")
        self.win.verify_process(registered, launch.executable)
        self.win.require_job(registered.handle, self.job)
        self._require_host_evidence(self.controls.suspended_process(registered, self.profile, deadline))
        self._check(deadline)
        if self.win.ResumeThread(self.process.thread) != 1:
            raise HostError("Native process resume refused.")
        self._close(self.process, "thread")
        self.pipe.send(bootstrap, deadline)
        self.pipe.send(frame.packed_bgr8, deadline)
        status, payload = _terminal(self.pipe.receive(_MAX_TERMINAL_BYTES, deadline), self.nonce, frame.binding)
        if self.pipe.receive(_MAX_TERMINAL_BYTES, deadline) is not None:
            raise HostError("Multiple native terminal frames.")
        self._check(deadline)
        return status, payload

    def _wait_stopped(self, deadline, *, cancellable=False):
        while monotonic_ns() < deadline:
            if cancellable and self.cancel.is_set():
                return False
            root_exited = not self.process.handle
            if self.process.handle:
                ms = max(0, min(20, (deadline - monotonic_ns()) // 1_000_000))
                result = self.win.api.WaitForSingleObject(self.process.handle, ms)
                if result not in (0, _WAIT_TIMEOUT):
                    return False
                root_exited = result == 0
            if root_exited:
                if self.job:
                    accounting = _JobAccounting()
                    if not self.win.QueryInformationJobObject(self.job, 1, byref(accounting), sizeof(accounting), None):
                        return False
                    if accounting.active:
                        continue
                if self.process.handle:
                    self.exit_code = self.win.api.GetExitCodeProcess(self.process.handle)
                return True
        return False

    def finish(self, work_deadline, deadline, *, graceful):
        """Require an actual exit and job count zero before closing host resources."""
        if not self.stopped:
            try:
                if graceful:
                    self.stopped = self._wait_stopped(work_deadline, cancellable=True)
                if not self.stopped:
                    self.forced = True
                    if self.job and not self.win.TerminateJobObject(self.job, 1) and self.process.handle:
                        # Preserve the job handle for independent accounting.
                        self.win.api.TerminateProcess(self.process.handle, 1)
                    self.stopped = self._wait_stopped(deadline)
            except Exception:
                self.stopped = False
            if not self.stopped:
                return False
        clean = True
        if self.monitoring:
            try:
                observed = self.controls.finish(self._registered(), self.profile, deadline)
                violation = self.controls.violation_seen(self.profile)
                clean = type(observed) is FinalObservation and type(observed.isolation_violation) is bool
                self.violation |= not clean or observed.isolation_violation or violation is not False
                clean = clean and observed.clean is True
            except Exception:
                clean = False
                self.violation = True
            if clean:
                self.monitoring = False
        for owner, field in ((self, "peer"), (self, "stdio")):
            try:
                self._close(owner, field)
            except Exception:
                clean = False
        try:
            if self.pipe is not None:
                if self.pipe.close(deadline):
                    self.pipe = None
                else:
                    clean = False
        except Exception:
            clean = False
        if clean:
            for owner, field in ((self.process, "thread"), (self.process, "handle"), (self, "job")):
                try:
                    self._close(owner, field)
                except Exception:
                    clean = False
        self.cleaned = clean and monotonic_ns() < deadline
        return self.cleaned

    def reap(self):
        """Best-effort emergency cleanup after refusing an unconfirmed attempt."""
        now = monotonic_ns()
        self.finish(now, now + self.profile.teardown_reserve_ns, graceful=False)


def _refusal(binding, status=NativeLocalImageStatusV0.UNAVAILABLE, *, stopped=True, clean=True):
    return NativeLocalImageCompletionV0(binding, status, stopped, clean)


class SupervisedNativeLocalImageExecutorV0:
    """Concrete T12 executor. All instances share one process-wide admission slot."""

    def __init__(self, profile=None, controls=None, *, development=False, prototype=False):
        self.profile, self.controls = profile, controls
        self.development = development
        self.prototype = prototype

    def __call__(self, frame: NativeLocalImageInputV0, processing_context, /) -> NativeLocalImageCompletionV0:
        global _QUARANTINED

        frame = _validate_frame(frame)
        binding = frame.binding
        if (type(self.development) is not bool or type(self.prototype) is not bool
                or (self.development and self.prototype)):
            return _refusal(binding)
        approved = (_PROTOTYPE_RUNTIME if self.prototype else
                    _DEVELOPMENT_RUNTIME if self.development else _AUTHORIZED_RUNTIME)
        if (
            sys.platform != "win32" or approved is None or approved[0] is not self.profile
            or approved[1] is not self.controls or not _ACTIVE.acquire(blocking=False)
        ):
            return _refusal(binding)
        try:
            if _QUARANTINED is not None:
                return _refusal(binding, stopped=_QUARANTINED.stopped, clean=_QUARANTINED.cleaned)
            try:
                if self.development or self.prototype:
                    from pipeline.native_local_image_dev_controls_v0 import (
                        DevelopmentLocalImageHostControlsV0, PrototypeLocalImageHostControlsV1,
                    )

                    controls_type = (PrototypeLocalImageHostControlsV1 if self.prototype
                                     else DevelopmentLocalImageHostControlsV0)
                    if (
                        type(self.controls) is not controls_type
                        or not self.controls.admits(frame, self.profile)
                    ):
                        return _refusal(binding)
                pins = _profile_pins(self.profile)
                context = _capture_processing_context(processing_context)
                cancel = _Cancellation(context)
                deadline = int(context.deadline * 1_000_000_000)
                work_deadline = deadline - self.profile.teardown_reserve_ns
                if (
                    not 0 < deadline < (1 << 63) or cancel.is_set()
                    or work_deadline - monotonic_ns() < self.profile.minimum_work_ns
                ):
                    return _refusal(binding)
            except Exception:
                return _refusal(binding)

            if self.development or self.prototype:
                attempt = _WindowsAttempt(self.profile, self.controls, cancel, development=True)
            else:
                attempt = _WindowsAttempt(self.profile, self.controls, cancel)
            status, payload = NativeLocalImageStatusV0.FAILED, None
            terminal = False
            try:
                status, payload = attempt.dispatch(frame, pins, work_deadline)
                terminal = True
            except Exception:
                pass
            finally:
                clean = attempt.finish(work_deadline, deadline, graceful=terminal)
                if not attempt.stopped or not clean or attempt.violation:
                    _QUARANTINED = attempt
                    if not attempt.stopped or not clean:
                        try:
                            Thread(target=attempt.reap, name="pantryproof-t13-reap", daemon=True).start()
                        except Exception:
                            pass  # Keep the job and handles for the independent monitor.
            if _QUARANTINED is attempt:
                return _refusal(binding, NativeLocalImageStatusV0.FAILED,
                                stopped=attempt.stopped, clean=attempt.cleaned)
            try:
                publishable = (
                    terminal and not attempt.forced and attempt.exit_code == 0
                    and not cancel.is_set() and monotonic_ns() < deadline
                )
            except Exception:
                publishable = False
            if not publishable or status is not NativeLocalImageStatusV0.COMPLETED:
                return _refusal(binding, NativeLocalImageStatusV0.FAILED)
            return NativeLocalImageCompletionV0(binding, status, True, True, payload)
        finally:
            _ACTIVE.release()
