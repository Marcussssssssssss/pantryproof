"""Windows process boundary for the P06 generated-image witness.

Job Objects constrain processes and memory. An independently approved host
provisioner must establish and observe the inherited OS security boundary
covering network, filesystem, scratch and diagnostics. There is no default
provisioner, and this module changes no host policy.
"""

from __future__ import annotations

from ctypes import (
    Structure, addressof, byref, c_size_t, c_void_p, create_string_buffer, create_unicode_buffer, sizeof,
)
from ctypes import wintypes as wt
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
from secrets import token_hex
import stat
import struct
from subprocess import list2cmdline
import sys
from threading import Event, Lock
from time import monotonic_ns
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from scripts.gate_c_ocr_b2_probe_v0 import Asset, NativeProfile, _Assignment


_HEADER = struct.Struct(">I")
_IO_CHUNK = 65_536
_MAX_FRAME = 0x7FFF_FFFF
_WAIT_SLICE_MS = 20
_WAIT_TIMEOUT = 258
_BROKEN_PIPE = 109
_PIPE_CONNECTED = 535
_OPERATION_ABORTED = 995
_IO_INCOMPLETE = 996
_IO_PENDING = 997
_NOT_FOUND = 1168
_JOB_LIMITS = 0x0008 | 0x0100 | 0x0200 | 0x2000  # One process, process/job commit, kill on close.
_EXTENDED_JOB_INFORMATION = 9


class HostError(RuntimeError):
    """Fixed host diagnostic. Never includes OS messages or evidence."""


@dataclass(frozen=True, slots=True, repr=False)
class LaunchSpec:
    executable: str
    working_directory: str
    import_paths: tuple[str, ...]
    environment: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True, repr=False)
class RegisteredProcess:
    """Borrowed process handle, valid only for the duration of policy checks."""

    handle: int
    pid: int


@dataclass(frozen=True, slots=True)
class IsolationEvidence:
    network_denied: bool
    filesystem_allowlist_enforced: bool
    scratch_bounded: bool
    pinned_paths_immutable: bool
    external_process_launch_denied: bool
    private_handles_and_diagnostics: bool
    violation_monitoring_active: bool
    startup_deadline_guard_active: bool

    def complete(self):
        return (
            self.network_denied is True
            and self.filesystem_allowlist_enforced is True
            and self.scratch_bounded is True
            and self.pinned_paths_immutable is True
            and self.external_process_launch_denied is True
            and self.private_handles_and_diagnostics is True
            and self.violation_monitoring_active is True
            and self.startup_deadline_guard_active is True
        )


@dataclass(frozen=True, slots=True)
class FinalObservation:
    clean: bool
    isolation_violation: bool


class ProvisionedControls(Protocol):
    """Trusted host configuration and monitor, independent of worker frames.

    approve checks exact approved pins, assets, launch configuration and custody.
    before_launch verifies controls already in force for the inherited identity
    and starts per-attempt monitoring. suspended_process checks the registered
    child in that same boundary before resume. Neither method installs policy.
    finish finalizes monitoring and verifies approved scratch/artifact cleanup,
    including partial startup with no registered process. Implementations must
    respect the passed absolute monotonic deadlines and emit no private detail.
    The pre-launch boundary must cover synchronous Windows startup calls that
    cannot be interrupted by the Python I/O loop.
    violation_seen is a nonblocking snapshot of the monitor's sticky flag,
    available even when exit or cleanup cannot be established.
    """

    def approve(self, profile: NativeProfile, assets: tuple[Asset, Asset], launch: LaunchSpec) -> bool: ...
    def before_launch(self, profile: NativeProfile, launch: LaunchSpec, deadline: int) -> IsolationEvidence: ...
    def suspended_process(
        self, process: RegisteredProcess, profile: NativeProfile, launch: LaunchSpec, deadline: int
    ) -> IsolationEvidence: ...
    def finish(
        self, process: RegisteredProcess | None, profile: NativeProfile, deadline: int
    ) -> FinalObservation: ...
    def violation_seen(self, profile: NativeProfile) -> bool: ...


def _local_path(value):
    if type(value) is not str or "\0" in value:
        return False
    path = Path(value)
    return path.is_absolute() and not path.drive.startswith("\\\\") and ".." not in path.parts


def _same_path(left, right):
    return os.path.normcase(os.path.normpath(left)) == os.path.normcase(os.path.normpath(right))


def _launch_ok(launch):
    if (type(launch) is not LaunchSpec or not _local_path(launch.executable)
            or not _local_path(launch.working_directory)
            or type(launch.import_paths) is not tuple or not launch.import_paths
            or not all(_local_path(path) for path in launch.import_paths)
            or type(launch.environment) is not tuple):
        return False
    names = set()
    for item in launch.environment:
        if type(item) is not tuple or len(item) != 2:
            return False
        name, value = item
        if (type(name) is not str or type(value) is not str or not name
                or any(char in name for char in "=\0") or "\0" in value
                or name.upper() in names):
            return False
        names.add(name.upper())
    return "SYSTEMROOT" in names


def _check_time(deadline, interrupted=None):
    if interrupted is not None and interrupted.is_set():
        raise InterruptedError("Worker operation interrupted.")
    if monotonic_ns() >= deadline:
        raise TimeoutError("Worker deadline reached.")


def _verify_file(pin, deadline):
    path = Path(pin.path)
    for component in (path, *path.parents):
        _check_time(deadline)
        if component.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise HostError("Worker file identity refused.")
    if not path.is_file() or path.stat().st_size != pin.length:
        raise HostError("Worker file identity refused.")
    digest = sha256()
    with path.open("rb") as stream:
        remaining = pin.length
        while remaining:
            _check_time(deadline)
            chunk = stream.read(min(_IO_CHUNK, remaining))
            if not chunk:
                raise HostError("Worker file identity refused.")
            digest.update(chunk)
            remaining -= len(chunk)
        if stream.read(1) or digest.hexdigest() != pin.sha256:
            raise HostError("Worker file identity refused.")
    _check_time(deadline)


class _Overlapped(Structure):
    _fields_ = [
        ("internal", c_size_t), ("internal_high", c_size_t),
        ("offset", wt.DWORD), ("offset_high", wt.DWORD), ("event", wt.HANDLE),
    ]


class _BasicLimits(Structure):
    _fields_ = [
        ("process_time", wt.LARGE_INTEGER), ("job_time", wt.LARGE_INTEGER),
        ("flags", wt.DWORD), ("min_working_set", c_size_t), ("max_working_set", c_size_t),
        ("active_process_limit", wt.DWORD), ("affinity", c_size_t),
        ("priority", wt.DWORD), ("scheduling", wt.DWORD),
    ]


class _ExtendedLimits(Structure):
    _fields_ = [
        ("basic", _BasicLimits), ("io_counters", wt.LARGE_INTEGER * 6),
        ("process_memory", c_size_t), ("job_memory", c_size_t),
        ("peak_process_memory", c_size_t), ("peak_job_memory", c_size_t),
    ]


class _StartupInfo(Structure):
    _fields_ = [
        ("size", wt.DWORD), ("reserved", wt.LPWSTR), ("desktop", wt.LPWSTR),
        ("title", wt.LPWSTR), ("x", wt.DWORD), ("y", wt.DWORD),
        ("x_size", wt.DWORD), ("y_size", wt.DWORD), ("x_chars", wt.DWORD),
        ("y_chars", wt.DWORD), ("fill", wt.DWORD), ("flags", wt.DWORD),
        ("show", wt.WORD), ("reserved_size", wt.WORD), ("reserved_bytes", c_void_p),
        ("stdin", wt.HANDLE), ("stdout", wt.HANDLE), ("stderr", wt.HANDLE),
    ]


class _StartupInfoEx(Structure):
    _fields_ = [("startup", _StartupInfo), ("attributes", c_void_p)]


class _ProcessInfo(Structure):
    _fields_ = [("handle", wt.HANDLE), ("thread", wt.HANDLE), ("pid", wt.DWORD), ("tid", wt.DWORD)]

class _SecurityAttributes(Structure):
    _fields_ = [("length", wt.DWORD), ("descriptor", c_void_p), ("inherit", wt.BOOL)]


class _Win32:
    """Windows-only bindings. Constructed only by a prepared worker at start."""

    def __init__(self):
        import _winapi
        from ctypes import WinDLL, get_last_error

        self.api = _winapi
        self.last_error = get_last_error
        kernel = WinDLL("kernel32", use_last_error=True)

        def bind(name, result, *params, library=kernel):
            function = getattr(library, name)
            function.restype = result
            function.argtypes = params
            setattr(self, name, function)

        handle, pointer, dword, boolean = wt.HANDLE, c_void_p, wt.DWORD, wt.BOOL
        bind("CreateJobObjectW", handle, pointer, wt.LPCWSTR)
        bind("SetInformationJobObject", boolean, handle, dword, pointer, dword)
        bind("QueryInformationJobObject", boolean, handle, dword, pointer, dword, pointer)
        bind("IsProcessInJob", boolean, handle, handle, pointer)
        bind("TerminateJobObject", boolean, handle, wt.UINT)
        bind("InitializeProcThreadAttributeList", boolean, pointer, dword, dword, pointer)
        bind("UpdateProcThreadAttribute", boolean, pointer, dword, c_size_t, pointer,
             c_size_t, pointer, pointer)
        bind("DeleteProcThreadAttributeList", None, pointer)
        bind("CreateProcessW", boolean, wt.LPCWSTR, wt.LPWSTR, pointer, pointer, boolean,
             dword, pointer, wt.LPCWSTR, pointer, pointer)
        bind("ResumeThread", dword, handle)
        bind("GetProcessId", dword, handle)
        bind("GetNamedPipeClientProcessId", boolean, handle, pointer)
        bind("GetNamedPipeServerProcessId", boolean, handle, pointer)
        bind("CreateNamedPipeW", handle, wt.LPCWSTR, dword, dword, dword, dword, dword, dword, pointer)
        bind("ConnectNamedPipe", boolean, handle, pointer)
        bind("LocalFree", handle, handle)
        bind("ConvertStringSecurityDescriptorToSecurityDescriptorW", boolean, wt.LPCWSTR, dword,
             pointer, pointer, library=WinDLL("advapi32", use_last_error=True))
        bind("QueryFullProcessImageNameW", boolean, handle, dword, wt.LPWSTR, pointer)
        bind("ReadFile", boolean, handle, pointer, dword, pointer, pointer)
        bind("WriteFile", boolean, handle, pointer, dword, pointer, pointer)
        bind("CancelIoEx", boolean, handle, pointer)
        bind("GetOverlappedResult", boolean, handle, pointer, pointer, boolean)

    def pipe_pid(self, handle, *, server):
        pid = wt.DWORD()
        query = self.GetNamedPipeServerProcessId if server else self.GetNamedPipeClientProcessId
        if not query(handle, byref(pid)) or not pid.value:
            raise HostError("Worker channel ownership unconfirmed.")
        return pid.value

    def open_pipe(self, name):
        descriptor = c_void_p()
        # Protected DACL. Only the owner and SYSTEM may open the endpoint.
        if not self.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            "D:P(A;;GA;;;OW)(A;;GA;;;SY)", 1, byref(descriptor), None
        ):
            raise HostError("Worker channel security unavailable.")
        try:
            security = _SecurityAttributes(sizeof(_SecurityAttributes), descriptor.value, False)
            mode = self.api.PIPE_ACCESS_DUPLEX | self.api.FILE_FLAG_OVERLAPPED
            mode |= self.api.FILE_FLAG_FIRST_PIPE_INSTANCE
            handle = self.CreateNamedPipeW(
                name, mode, 0x0008, 1, _IO_CHUNK, _IO_CHUNK, 0, byref(security)
            )
            if handle is None or handle == c_void_p(-1).value:
                raise HostError("Worker channel unavailable.")
            return handle
        finally:
            self.LocalFree(descriptor)

    def require_job(self, process, job=None):
        assigned = wt.BOOL()
        if not self.IsProcessInJob(process, job, byref(assigned)) or not assigned.value:
            raise HostError("Worker job membership unconfirmed.")

    def verify_process(self, process, path):
        name = create_unicode_buffer(32_768)
        size = wt.DWORD(len(name))
        if (self.GetProcessId(process.handle) != process.pid
                or not self.QueryFullProcessImageNameW(process.handle, 0, name, byref(size))
                or not _same_path(name.value, path)):
            raise HostError("Worker process identity refused.")

    def launch_suspended(self, launch, args, peer, stdio, job, process):
        size = c_size_t()
        self.InitializeProcThreadAttributeList(None, 3, 0, byref(size))
        if self.last_error() != 122 or not size.value:
            raise HostError("Worker launch attributes unavailable.")
        attributes = create_string_buffer(size.value)
        if not self.InitializeProcThreadAttributeList(attributes, 3, 0, byref(size)):
            raise HostError("Worker launch attributes unavailable.")
        try:
            allowed_handles = (wt.HANDLE * 2)(peer, stdio)
            jobs = (wt.HANDLE * 1)(job)
            deny_children = wt.DWORD(1)
            # HANDLE_LIST, JOB_LIST and CHILD_PROCESS_POLICY.
            for key, value in ((0x20002, allowed_handles), (0x2000D, jobs), (0x2000E, deny_children)):
                if not self.UpdateProcThreadAttribute(
                    attributes, 0, key, byref(value), sizeof(value), None, None
                ):
                    raise HostError("Worker launch attributes refused.")
            info = _StartupInfoEx()
            info.startup.size = sizeof(info)
            info.startup.flags = 0x100  # STARTF_USESTDHANDLES
            info.startup.stdin = info.startup.stdout = info.startup.stderr = stdio
            info.attributes = addressof(attributes)
            environment = create_unicode_buffer(
                "\0".join(f"{key}={value}" for key, value in
                          sorted(launch.environment, key=lambda item: item[0].upper())) + "\0"
            )
            command = create_unicode_buffer(list2cmdline(args))
            os.set_handle_inheritable(peer, True)
            os.set_handle_inheritable(stdio, True)
            # Suspended, Unicode environment, extended attributes, no console.
            if not self.CreateProcessW(
                launch.executable, command, None, None, True, 0x08080404, byref(environment),
                launch.working_directory, byref(info), byref(process)
            ):
                raise HostError("Worker creation refused.")
        finally:
            self.DeleteProcThreadAttributeList(attributes)


class _Pipe:
    """A single reader and writer, used sequentially by each endpoint."""

    def __init__(self, win, handle, ceiling, interrupted):
        self.win = win
        self.handle = handle
        self.ceiling = ceiling
        self.interrupted = interrupted
        self.pending = None

    def _settle(self):
        operation, buffer = self.pending
        done = wt.DWORD()
        if self.win.GetOverlappedResult(self.handle, byref(operation), byref(done), False):
            error = 0
        else:
            error = self.win.last_error()
            if error == _IO_INCOMPLETE:
                return None
        self.win.api.CloseHandle(operation.event)
        self.pending = None
        return done.value, error, buffer

    def _wait(self, deadline, *, cancel=False):
        while True:
            _check_time(deadline, None if cancel else self.interrupted)
            operation, _ = self.pending
            remaining = (deadline - monotonic_ns() + 999_999) // 1_000_000
            result = self.win.api.WaitForSingleObject(
                operation.event, max(0, min(_WAIT_SLICE_MS, remaining))
            )
            if result == _WAIT_TIMEOUT:
                continue
            if result != 0:
                raise HostError("Worker channel wait failed.")
            settled = self._settle()
            if settled is None:
                raise HostError("Worker channel completion unconfirmed.")
            return settled

    def _cancel(self):
        operation, _ = self.pending
        return (self.win.CancelIoEx(self.handle, byref(operation))
                or self.win.last_error() == _NOT_FOUND)

    def _transfer(self, size, deadline, data=None):
        _check_time(deadline, self.interrupted)
        if self.handle is None or self.pending is not None:
            raise HostError("Worker channel unavailable.")
        buffer = create_string_buffer(size) if data is None else create_string_buffer(data, size)
        operation = _Overlapped()
        operation.event = self.win.api.CreateEvent(None, True, False, None)
        self.pending = operation, buffer
        action = self.win.ReadFile if data is None else self.win.WriteFile
        if action(self.handle, buffer, size, None, byref(operation)):
            settled = self._settle()
        else:
            error = self.win.last_error()
            if error == _IO_PENDING:
                settled = self._wait(deadline)
            else:
                self.win.api.CloseHandle(operation.event)
                self.pending = None
                settled = 0, error, buffer
        _check_time(deadline, self.interrupted)
        if settled is None:
            raise HostError("Worker channel completion unconfirmed.")
        count, error, result = settled
        if error == _BROKEN_PIPE and data is None:
            return None
        if error or not 0 < count <= size:
            raise HostError("Worker channel transfer failed.")
        return result[:count] if data is None else count

    def _read_exact(self, size, deadline, *, allow_eof=False):
        frame = bytearray()
        while len(frame) < size:
            part = self._transfer(min(size - len(frame), _IO_CHUNK), deadline)
            if part is None:
                if allow_eof and not frame:
                    return None
                raise HostError("Worker channel frame truncated.")
            frame.extend(part)
        return bytes(frame)

    def receive(self, maximum, deadline):
        if type(maximum) is not int or not 0 < maximum <= self.ceiling:
            raise HostError("Worker frame bound refused.")
        header = self._read_exact(_HEADER.size, deadline, allow_eof=True)
        if header is None:
            return None
        size, = _HEADER.unpack(header)
        if not 0 < size <= maximum:
            raise HostError("Worker frame bound refused.")
        return self._read_exact(size, deadline)

    def send(self, frame, deadline):
        if type(frame) is not bytes or not 0 < len(frame) <= self.ceiling:
            raise HostError("Worker frame bound refused.")
        for data in (_HEADER.pack(len(frame)), frame):
            offset = 0
            while offset < len(data):
                part = data[offset:offset + _IO_CHUNK]
                offset += self._transfer(len(part), deadline, part)

    def close(self, deadline):
        if self.pending is not None:
            if not self._cancel():
                return False
            _, error, _ = self._wait(deadline, cancel=True)
            if error not in (0, _OPERATION_ABORTED, _BROKEN_PIPE):
                return False
        if self.handle is not None:
            self.win.api.CloseHandle(self.handle)
            self.handle = None
        return True


def _startup_frame(assignment, import_paths):
    data = {
        "ticket": asdict(assignment.ticket),
        "assets": [dict(asdict(asset), witness=asset.witness.name) for asset in assignment.assets],
        "witness": assignment.asset.witness.name,
        "profile": asdict(assignment.profile),
        "deadline": assignment.deadline,
        "gate_id": assignment.gate_id,
        "import_paths": import_paths,
    }
    return json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("ascii")


def _restore_assignment(data):
    from scripts import gate_c_ocr_b2_probe_v0 as probe

    payload = dict(data["profile"])
    for key in ("runtime", "detector", "recognizer"):
        payload[key] = tuple(probe.FilePin(**pin) for pin in payload[key])
    for key in ("configuration", "controls"):
        payload[key] = probe.FilePin(**payload[key])
    profile = probe.NativeProfile(**payload)
    assets = tuple(probe.Asset(**dict(asset, witness=probe.Witness[asset["witness"]]))
                   for asset in data["assets"])
    asset = next(asset for asset in assets if asset.witness.name == data["witness"])
    if not probe._profile_ok(profile, assets):
        raise HostError("Worker assignment refused.")
    return probe._Assignment(
        probe.Ticket(**data["ticket"]), asset, assets, profile, data["deadline"], data["gate_id"]
    )


class WindowsWorkerHost:
    """One registered worker at a time. Unprovisioned hosts refuse admission."""

    def __init__(self, *, launch: LaunchSpec, controls: ProvisionedControls | None = None):
        self._launch = launch
        self._controls = controls
        self._lock = Lock()
        self._approved = None
        self._worker = None
        self._quarantined = False

    def authorize(self, profile: NativeProfile, assets: tuple[Asset, Asset]) -> bool:
        from scripts import gate_c_ocr_b2_probe_v0 as probe

        with self._lock:
            self._approved = None
            if (sys.platform != "win32" or self._controls is None or self._quarantined
                    or self._worker is not None or not _launch_ok(self._launch)
                    or not probe._profile_ok(profile, assets) or profile.ipc_bytes > _MAX_FRAME
                    or profile.memory_bytes >= 1 << (8 * sizeof(c_size_t))):
                return False
            source = str(Path(__file__).absolute())
            pins = tuple(next((pin for pin in profile.runtime if _same_path(pin.path, path)), None)
                         for path in (self._launch.executable, source))
            if any(pin is None for pin in pins):
                return False
            try:
                if self._controls.approve(profile, assets, self._launch) is not True:
                    return False
            except Exception:
                return False
            self._approved = profile, assets, pins
            return True

    def prepare(self, profile: NativeProfile, deadline: int):
        _check_time(deadline)
        with self._lock:
            if (self._quarantined or self._worker is not None or self._approved is None
                    or self._approved[0] is not profile):
                raise HostError("Worker admission refused.")
            _, assets, pins = self._approved
            self._approved = None
            self._worker = WindowsWorkerHandle(self, profile, assets, pins, deadline)
            return self._worker

    def _retire(self, worker, safe):
        with self._lock:
            if not safe:
                self._quarantined = True  # Retain handles and any pending I/O buffer.
            elif self._worker is worker:
                self._worker = None


class WindowsWorkerHandle:
    """Owns one attempt. Only interrupt is called from a second thread."""

    def __init__(self, host, profile, assets, pins, deadline):
        self._host = host
        self._profile = profile
        self._assets = assets
        self._pins = pins
        self._deadline = deadline
        self._interrupted = Event()
        self._win = self._pipe = self._job = None
        self._process = _ProcessInfo()
        self._peer = self._stdio = None
        self._job_assigned = self._started = self._monitoring = False
        self._ready = False
        self._terminating = False
        self._exited = self._cleaned = self._isolation = False
        self._code = None

    def _close(self, field):
        handle = getattr(self, field)
        if handle is not None:
            self._win.api.CloseHandle(handle)
            setattr(self, field, None)

    def _open_transport(self, deadline):
        win, api = self._win, self._win.api
        name = r"\\.\pipe\pantryproof-p06-" + token_hex(32)
        server = win.open_pipe(name)
        self._pipe = _Pipe(win, server, self._profile.ipc_bytes, self._interrupted)
        self._peer = api.CreateFile(
            name, api.GENERIC_READ | api.GENERIC_WRITE, 0, 0, api.OPEN_EXISTING,
            api.FILE_FLAG_OVERLAPPED | 0x00110000, 0,  # SQOS present, identification only.
        )
        operation = _Overlapped()
        operation.event = api.CreateEvent(None, True, False, None)
        # The peer is already connected. Any other outcome is a failed binding.
        self._pipe.pending = operation, None
        connected = win.ConnectNamedPipe(server, byref(operation))
        error = 0 if connected else win.last_error()
        if error != _IO_PENDING:
            api.CloseHandle(operation.event)
            self._pipe.pending = None
        if error != _PIPE_CONNECTED or win.pipe_pid(server, server=False) != os.getpid():
            self._isolation = True
            raise HostError("Worker channel ownership refused.")
        _check_time(deadline, self._interrupted)
        self._stdio = api.CreateFile(
            "NUL", api.GENERIC_READ | api.GENERIC_WRITE, 3, 0, api.OPEN_EXISTING, 0, 0
        )

    def _open_job(self):
        win = self._win
        self._job = win.CreateJobObjectW(None, None)
        if not self._job:
            self._job = None
            raise HostError("Worker job unavailable.")
        limits = _ExtendedLimits()
        limits.basic.flags = _JOB_LIMITS
        limits.basic.active_process_limit = 1
        limits.process_memory = limits.job_memory = self._profile.memory_bytes
        if not win.SetInformationJobObject(
            self._job, _EXTENDED_JOB_INFORMATION, byref(limits), sizeof(limits)
        ):
            raise HostError("Worker job limits refused.")
        actual = _ExtendedLimits()
        if (not win.QueryInformationJobObject(
                self._job, _EXTENDED_JOB_INFORMATION, byref(actual), sizeof(actual), None
            ) or actual.basic.flags != _JOB_LIMITS or actual.basic.active_process_limit != 1
                or actual.process_memory != limits.process_memory or actual.job_memory != limits.job_memory):
            raise HostError("Worker job limits unconfirmed.")

    def _launch_suspended(self):
        launch = self._host._launch
        args = [launch.executable, "-I", "-S", "-B", self._pins[1].path, "--p06-worker",
                str(self._peer), str(os.getpid()), str(self._profile.ipc_bytes), str(self._deadline)]
        try:
            self._win.launch_suspended(
                launch, args, self._peer, self._stdio, self._job, self._process
            )
            self._job_assigned = True
        finally:
            self._close("_peer")  # Parent must release its copy for real EOF.
            self._close("_stdio")

    def _registered_process(self):
        if self._process.handle:
            return RegisteredProcess(self._process.handle, self._process.pid)
        return None

    def _close_process_handle(self, field):
        handle = getattr(self._process, field)
        if handle:
            self._win.api.CloseHandle(handle)
            setattr(self._process, field, None)

    def _require_controls(self, evidence):
        if type(evidence) is not IsolationEvidence or not evidence.complete():
            self._isolation = True
            raise HostError("Worker OS isolation unconfirmed.")

    def start(self, assignment: _Assignment, image_bytes: bytes, deadline: int) -> None:
        from scripts import gate_c_ocr_b2_probe_v0 as probe

        if self._started or self._exited or self._cleaned:
            raise HostError("Worker start refused.")
        self._started = True
        _check_time(self._deadline, self._interrupted)
        if (type(assignment) is not probe._Assignment or assignment.profile is not self._profile
                or assignment.assets is not self._assets or deadline != self._deadline
                or assignment.deadline != deadline
                or not any(asset is assignment.asset for asset in self._assets)):
            raise HostError("Worker assignment refused.")
        probe._encoded(image_bytes, assignment.asset)
        launch, controls = self._host._launch, self._host._controls
        bootstrap = _startup_frame(assignment, launch.import_paths)
        if max(len(bootstrap), len(image_bytes)) > self._profile.ipc_bytes:
            raise HostError("Worker bootstrap bound refused.")
        try:
            self._monitoring = True
            self._require_controls(controls.before_launch(self._profile, launch, deadline))
            for pin in self._pins:
                _verify_file(pin, deadline)
            self._win = _Win32()
            self._open_job()
            self._open_transport(deadline)
            _check_time(deadline, self._interrupted)
            self._launch_suspended()
            process = self._registered_process()
            if process is None:
                raise HostError("Worker registration refused.")
            self._win.verify_process(process, launch.executable)
            self._win.require_job(self._process.handle, self._job)
            self._require_controls(controls.suspended_process(
                process, self._profile, launch, deadline
            ))
        except (TimeoutError, InterruptedError):
            raise
        except Exception:
            self._isolation = True
            raise HostError("Worker containment failed.") from None
        _check_time(deadline, self._interrupted)
        if self._win.ResumeThread(self._process.thread) != 1:
            self._isolation = True
            raise HostError("Worker resume refused.")
        self._close_process_handle("thread")
        self._pipe.send(bootstrap, deadline)
        self._pipe.send(image_bytes, deadline)
        self._ready = True

    def send(self, frame: bytes, deadline: int) -> None:
        if not self._ready or self._exited:
            raise HostError("Worker channel unavailable.")
        self._pipe.send(frame, min(deadline, self._deadline))

    def receive(self, maximum: int, deadline: int) -> bytes | None:
        if not self._ready or self._exited:
            raise HostError("Worker channel unavailable.")
        return self._pipe.receive(maximum, min(deadline, self._deadline))

    def interrupt(self) -> None:
        self._interrupted.set()

    def terminate(self, deadline: int) -> None:
        self._terminating = True
        self.interrupt()
        if not self._process.handle or self._exited:
            return
        _check_time(deadline)
        if self._job_assigned:
            if not self._win.TerminateJobObject(self._job, 1):
                self._close("_job")  # Kernel kill-on-close is part of the same verified job.
        else:
            self._win.api.TerminateProcess(self._process.handle, 1)

    def wait_exited(self, deadline: int) -> bool:
        if self._exited or not self._process.handle:
            self._exited = True
            return True
        process = self._process.handle
        while True:
            remaining = (deadline - monotonic_ns()) // 1_000_000
            result = self._win.api.WaitForSingleObject(
                process, max(0, min(_WAIT_SLICE_MS, remaining))
            )
            if result == 0:
                self._exited = True
                try:
                    self._code = self._win.api.GetExitCodeProcess(process)
                except OSError:
                    self._code = None
                return True
            if result != _WAIT_TIMEOUT:
                raise HostError("Worker exit unconfirmed.")
            if monotonic_ns() >= deadline:
                return False
            if self._interrupted.is_set() and not self._terminating:
                return False

    def exit_code(self) -> int | None:
        return self._code if self._exited else None

    def cleanup(self, deadline: int) -> bool:
        if self._cleaned:
            return True
        if not self._exited:
            self._host._retire(self, False)
            return False
        clean = not self._monitoring
        try:
            # Observe independently even if another cleanup step fails.
            if self._monitoring:
                observation = self._host._controls.finish(self._registered_process(), self._profile, deadline)
                if type(observation) is FinalObservation:
                    self._isolation |= observation.isolation_violation is True
                    clean = observation.clean is True and type(observation.isolation_violation) is bool
        except Exception:
            pass
        for field in ("_peer", "_stdio", "_job"):
            try:
                self._close(field)
            except Exception:
                clean = False
        for field in ("thread", "handle"):
            try:
                self._close_process_handle(field)
            except Exception:
                clean = False
        try:
            if self._pipe is not None and not self._pipe.close(deadline):
                clean = False
        except Exception:
            clean = False
        self._cleaned = clean and monotonic_ns() < deadline
        self._host._retire(self, self._cleaned and not self._isolation)
        return self._cleaned

    def isolation_failed(self) -> bool:
        if not self._cleaned:
            if self._monitoring:
                try:
                    self._isolation |= self._host._controls.violation_seen(self._profile) is True
                except Exception:
                    pass  # Cleanup was already unconfirmed, so publication remains blocked.
            try:
                self._close("_job")
            except Exception:
                pass
            self._host._retire(self, False)
        return self._isolation


def _worker_main(args):
    if sys.platform != "win32" or len(args) != 5 or args[0] != "--p06-worker":
        return 2
    handle, parent, ceiling, deadline = map(int, args[1:])
    if not 0 < ceiling <= _MAX_FRAME:
        return 2
    win = _Win32()
    win.require_job(win.api.GetCurrentProcess())
    if win.pipe_pid(handle, server=True) != parent:
        return 2
    os.set_handle_inheritable(handle, False)
    pipe = _Pipe(win, handle, ceiling, Event())
    try:
        metadata = pipe.receive(ceiling, deadline)
        if metadata is None:
            return 2
        data = json.loads(metadata.decode("ascii"))
        paths = data["import_paths"]
        if type(paths) is not list or not paths or not all(_local_path(path) for path in paths):
            return 2
        sys.path.extend(paths)
        assignment = _restore_assignment(data)
        if assignment.deadline != deadline or assignment.profile.ipc_bytes != ceiling:
            return 2
        image = pipe.receive(min(assignment.asset.length, ceiling), deadline)
        _check_time(deadline)
        from scripts import gate_c_ocr_b2_probe_v0 as probe

        probe._encoded(image, assignment.asset)
        probe._native_worker(assignment, image, pipe)
        return 0
    finally:
        if not pipe.close(deadline):
            raise HostError("Worker channel cleanup unconfirmed.")


if __name__ == "__main__":
    try:
        code = _worker_main(sys.argv[1:])
    except BaseException:
        code = 2
    os._exit(code)
