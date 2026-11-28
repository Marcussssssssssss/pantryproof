"""Host controls for an approved, non-private generated receipt development run.

The development profile uses an operator attestation, samples Windows link state
and current-compartment IP routes, and observes the dedicated scratch directory.
Sampling can miss brief changes and paths outside the observed tables. Scratch
counts and pin checks are point-in-time evidence. Production isolation and
operational authority require separate controls.
"""

from __future__ import annotations

from ctypes import Structure, WinDLL, byref, c_uint64, c_void_p, create_unicode_buffer, sizeof
from ctypes import wintypes as wt
from dataclasses import dataclass
from functools import cache
from hashlib import sha256
from ipaddress import ip_address, ip_network
import json
import os
from pathlib import Path
import re
from threading import Event, Thread
from time import monotonic_ns, time_ns

from pipeline.native_local_image_executor_v0 import (
    NativeLocalImageRuntimeProfileV0, _unique_pairs, _validate_frame,
)
from scripts.gate_c_native_worker_host_v0 import FinalObservation, HostError, _same_path
from scripts.gate_c_ocr_b2_probe_v0 import _file_pin


DEVELOPMENT_SCOPE = "GENERATED_RECEIPT_ONLY"
PROTOTYPE_SCOPE = "LOCAL_GROCERY_RECEIPTS_V1"
NETWORK_OBSERVATION = "WINDOWS_LINK_AND_ROUTE_V0"
_QUERY_LIMIT_NS = 6_000_000_000
_SAMPLE_INTERVAL = 1.0
_MAX_SAMPLE_AGE_NS = 8_000_000_000
_CONFIRMATION_AGE_NS = 600_000_000_000
_MAX_CONTROLS_BYTES = 4096
_MAX_TABLE_ROWS = 4096
_MAX_ENTRIES = 512
_MAX_DEPTH = 12
_DIGEST = re.compile(r"[0-9a-f]{64}")
_LOOPBACK_V4, _LOOPBACK_V6, _LINK_LOCAL_V6 = map(ip_network, ("127.0.0.0/8", "::1/128", "fe80::/10"))
_PROTOCOL_ROUTES = frozenset(map(ip_network, ("224.0.0.0/4", "255.255.255.255/32", "ff00::/8")))


@dataclass(frozen=True, slots=True, repr=False)
class DevelopmentLocalImageRuntimeApprovalV0:
    """Exact generated Android payload and runtime authorized for the demo."""

    profile: NativeLocalImageRuntimeProfileV0
    encoded_sha256: str
    bgr8_sha256: str
    width: int
    height: int
    scope: str


@dataclass(frozen=True, slots=True)
class DevelopmentIsolationEvidenceV0:
    """Positive development observations only, with no strict-isolation fields."""

    offline_observed: bool
    owned_scratch_observed: bool
    monitor_active: bool

    def permits_development(self) -> bool:
        return (
            self.offline_observed is True and self.owned_scratch_observed is True
            and self.monitor_active is True
        )


def _confirmation_deadline(pin) -> int:
    """Read the operator's per-run attestation from the pinned development manifest."""
    if not _file_pin(pin) or pin.length > _MAX_CONTROLS_BYTES:
        return 0
    try:
        with Path(pin.path).open("rb") as stream:
            raw = stream.read(_MAX_CONTROLS_BYTES + 1)
        if len(raw) != pin.length or sha256(raw).hexdigest() != pin.sha256:
            return 0
        record = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except (OSError, ValueError, RecursionError, HostError):
        return 0
    if type(record) is not dict or record.keys() != {
        "scope", "network_observation", "physical_disconnection_confirmed_unix_s",
    }:
        return 0
    confirmed = record["physical_disconnection_confirmed_unix_s"]
    if (
        record["scope"] != DEVELOPMENT_SCOPE or record["network_observation"] != NETWORK_OBSERVATION
        or type(confirmed) is not int or confirmed <= 0
    ):
        return 0
    now = monotonic_ns()
    age = time_ns() - confirmed * 1_000_000_000
    return now + _CONFIRMATION_AGE_NS - age if 0 <= age < _CONFIRMATION_AGE_NS else 0


# Win32 netioapi.h layouts. Fields unused by the observation still occupy
# their native positions so ctypes can read each row at its aligned stride.
class _InterfaceRow(Structure):
    _fields_ = [
        ("luid", c_uint64), ("index", wt.ULONG), ("guid", wt.DWORD * 4),
        ("alias", wt.WCHAR * 257), ("description", wt.WCHAR * 257),
        ("physical_address_length", wt.ULONG), ("physical_addresses", wt.BYTE * 64),
        ("mtu", wt.ULONG), ("kind", wt.ULONG), ("media_metadata", wt.ULONG * 5),
        ("flags", wt.BYTE), ("oper", wt.ULONG), ("admin", wt.ULONG), ("media", wt.ULONG),
        ("network_guid", wt.DWORD * 4), ("connection_type", wt.ULONG),
        ("link_speeds_and_counters", c_uint64 * 20),
    ]


class _SocketAddress(Structure):
    _fields_ = [
        ("family", wt.USHORT), ("port", wt.USHORT), ("ipv4_or_flow", wt.BYTE * 4),
        ("ipv6", wt.BYTE * 16), ("scope_id", wt.ULONG),
    ]

    def address(self):
        if self.family == 2:  # AF_INET
            return ip_address(bytes(self.ipv4_or_flow))
        if self.family == 23:  # AF_INET6
            return ip_address(bytes(self.ipv6))
        raise HostError("Windows route address family unavailable.")


class _AddressPrefix(Structure):
    _fields_ = [("address", _SocketAddress), ("length", wt.BYTE)]


class _RouteRow(Structure):
    _fields_ = [
        ("luid", c_uint64), ("index", wt.ULONG), ("destination", _AddressPrefix),
        ("next_hop", _SocketAddress), ("site_prefix_length", wt.BYTE),
        ("lifetime_metric_protocol", wt.ULONG * 4), ("flags", wt.BYTE * 4),
        ("age", wt.ULONG), ("origin", wt.ULONG),
    ]


class _InterfaceTable(Structure):
    _fields_ = [("count", wt.ULONG), ("first", _InterfaceRow)]


class _RouteTable(Structure):
    _fields_ = [("count", wt.ULONG), ("first", _RouteRow)]


def _read_table(query, free, table_type, deadline, project, *query_args):
    address = c_void_p()
    try:
        _check_time(deadline)
        if query(*query_args, byref(address)) != 0 or not address.value:
            raise HostError("Windows IP Helper table unavailable.")
        table = table_type.from_address(address.value)
        if not 0 < table.count <= _MAX_TABLE_ROWS:
            raise HostError("Windows IP Helper table size refused.")
        row_type = type(table.first)
        rows = (row_type * table.count).from_address(address.value + table_type.first.offset)
        result = []
        for row in rows:
            _check_time(deadline)
            result.append(project(row))
        return result
    finally:
        if address.value:
            free(address)


def _route_evidence(row):
    network = ip_network((row.destination.address.address(), row.destination.length))
    return row.index, row.luid, network, row.next_hop.address()


@cache
def _network_api():
    api = WinDLL("iphlpapi.dll", winmode=0x800)  # LOAD_LIBRARY_SEARCH_SYSTEM32
    for function, parameters in (
        (api.GetIfTable2, (c_void_p,)),
        (api.GetIpForwardTable2, (wt.USHORT, c_void_p)),
    ):
        function.argtypes = parameters
        function.restype = wt.ULONG
    api.FreeMibTable.argtypes = (c_void_p,)
    api.FreeMibTable.restype = None
    return api


def _windows_network_tables(deadline):
    api = _network_api()
    links = _read_table(
        api.GetIfTable2, api.FreeMibTable, _InterfaceTable, deadline,
        lambda row: (row.index, row.luid, row.kind, row.flags, row.oper, row.media),
    )
    # AF_UNSPEC returns IPv4 and IPv6 together.
    routes = _read_table(api.GetIpForwardTable2, api.FreeMibTable, _RouteTable, deadline, _route_evidence, 0)
    return links, routes


def _offline_sample(deadline: int) -> bool:
    """Refuse connected physical media and unexpected routes using local tables."""
    _check_time(deadline)
    links, routes = _windows_network_tables(deadline)
    interfaces = {}
    for index, luid, kind, flags, oper, media in links:
        identity = (index, luid)
        if not index or not luid or identity in interfaces:
            raise HostError("Windows network interface identity unavailable.")
        down = oper in (2, 6, 7) and media in (0, 2)  # Down, absent or lower-layer down.
        physical = bool(flags & 0x05)  # HardwareInterface or ConnectorPresent.
        if physical and not down:
            return False
        interfaces[identity] = (kind == 24 and oper == 1 and not physical, down)

    loopback_v4 = False
    for index, luid, network, next_hop in routes:
        _check_time(deadline)
        link = interfaces.get((index, luid))
        if link is None:
            raise HostError("Windows route interface association unavailable.")
        loopback, down = link
        if not network.prefixlen or next_hop.version != network.version or not next_hop.is_unspecified:
            return False
        if network in _PROTOCOL_ROUTES:
            continue  # Standard Windows on-link multicast and limited broadcast entries.
        if loopback:
            allowed = _LOOPBACK_V4 if network.version == 4 else _LOOPBACK_V6
            if network.subnet_of(allowed):
                loopback_v4 |= network.version == 4 and ip_address("127.0.0.1") in network
                continue
        if not (down and network.version == 6 and network.subnet_of(_LINK_LOCAL_V6)):
            return False
    _check_time(deadline)
    return loopback_v4


class _FileInfo(Structure):
    _fields_ = [
        ("attributes", wt.DWORD), ("created", wt.FILETIME), ("accessed", wt.FILETIME),
        ("written", wt.FILETIME), ("volume", wt.DWORD), ("size_high", wt.DWORD),
        ("size_low", wt.DWORD), ("links", wt.DWORD), ("id_high", wt.DWORD),
        ("id_low", wt.DWORD),
    ]

    @property
    def identity(self):
        return self.volume, self.id_high, self.id_low


def _kernel():
    api = WinDLL("kernel32", use_last_error=True)
    api.CreateFileW.argtypes = (
        wt.LPCWSTR, wt.DWORD, wt.DWORD, c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE,
    )
    api.CreateFileW.restype = wt.HANDLE
    api.GetFileInformationByHandle.argtypes = (wt.HANDLE, c_void_p)
    api.GetFinalPathNameByHandleW.argtypes = (wt.HANDLE, wt.LPWSTR, wt.DWORD, wt.DWORD)
    api.GetFinalPathNameByHandleW.restype = wt.DWORD
    api.SetFileInformationByHandle.argtypes = (wt.HANDLE, wt.DWORD, c_void_p, wt.DWORD)
    api.CloseHandle.argtypes = (wt.HANDLE,)
    api.GetDriveTypeW.argtypes = (wt.LPCWSTR,)
    return api


def _check_time(deadline):
    if monotonic_ns() >= deadline:
        raise HostError("Development host observation timed out.")


class _Scratch:
    """Track a newly created tree and clean it using no-follow Windows handles."""

    def __init__(self, path, max_bytes):
        self.path = path
        self.max_bytes = max_bytes
        self.api = None
        self.ancestors = []
        self.root_handle = None
        self.identity = None
        self.created = False
        self.empty_at_creation = False

    def _open(self, path, *, delete=False):
        # Pin ordinary entries against rename and open reparse points themselves.
        handle = self.api.CreateFileW(
            str(path), 0x00010000 if delete else 0, 3, None, 3,
            0x02000000 | 0x00200000, None,
        )
        if handle in (None, c_void_p(-1).value):
            raise HostError("Development scratch entry unavailable.")
        info = _FileInfo()
        if (
            not self.api.GetFileInformationByHandle(handle, byref(info))
            or info.attributes & 0x400 or not info.attributes & 0x10 and info.links != 1
        ):
            self._close(handle)
            raise HostError("Development scratch entry is unsafe.")
        resolved = create_unicode_buffer(32768)
        length = self.api.GetFinalPathNameByHandleW(handle, resolved, len(resolved), 0)
        if (
            not 0 < length < len(resolved) or not resolved.value.startswith("\\\\?\\")
            or not _same_path(resolved.value[4:], str(path))
        ):
            self._close(handle)
            raise HostError("Development scratch path identity differs.")
        return handle, info

    def _close(self, handle):
        if not self.api.CloseHandle(handle):
            raise HostError("Development scratch handle did not close.")

    def start(self, deadline):
        self.api = _kernel()
        if (
            not self.path.is_absolute() or len(self.path.parts) < 3
            or not re.fullmatch(r"[A-Za-z]:\\", self.path.anchor)
            or any(part in (".", "..") or ":" in part for part in self.path.parts[1:])
            or self.api.GetDriveTypeW(self.path.anchor) != 3
        ):
            raise HostError("Development scratch must be on an ordinary local volume.")
        for parent in reversed(self.path.parents):
            if parent == Path(self.path.anchor):
                continue  # Fixed volume root has no renameable parent.
            _check_time(deadline)
            handle, info = self._open(parent)
            self.ancestors.append(handle)
            if not info.attributes & 0x10:
                raise HostError("Development scratch parent is not a directory.")
        _check_time(deadline)
        self.path.mkdir()  # Refuse existing data, including an existing empty directory.
        self.created = True
        self.root_handle, info = self._open(self.path)
        if not info.attributes & 0x10:
            raise HostError("Development scratch is not a directory.")
        self.identity = info.identity
        if self._scan(deadline, delete=False):
            raise HostError("Development scratch was not empty.")
        self.empty_at_creation = True

    def _scan(self, deadline, *, delete):
        opened = []
        postorder = []
        visited = 0
        observed_bytes = 0

        def visit(directory, depth):
            nonlocal visited, observed_bytes
            if depth > _MAX_DEPTH:
                raise HostError("Development scratch nesting exceeded.")
            with os.scandir(directory) as entries:
                for entry in entries:
                    _check_time(deadline)
                    visited += 1
                    if visited > _MAX_ENTRIES:
                        raise HostError("Development scratch entry count exceeded.")
                    if ":" in entry.name or entry.name.rstrip(" .") != entry.name:
                        raise HostError("Development scratch entry name refused.")
                    path = Path(entry.path)
                    handle, info = self._open(path, delete=delete)
                    opened.append(handle)
                    if info.identity[0] != self.identity[0]:
                        raise HostError("Development scratch changed volume.")
                    if info.attributes & 0x10:
                        visit(path, depth + 1)
                    else:
                        observed_bytes += (info.size_high << 32) + info.size_low
                        if not delete and observed_bytes > self.max_bytes:
                            raise HostError("Observed development scratch usage exceeded.")
                    postorder.append((path, handle))

        try:
            visit(self.path, 0)
            if delete:
                for path, handle in postorder:
                    _check_time(deadline)
                    self._delete(handle)
                    self._close(handle)
                    opened.remove(handle)
                    if os.path.lexists(path):
                        raise HostError("Development scratch entry remains after cleanup.")
            return visited
        finally:
            for handle in reversed(opened):
                self._close(handle)

    def _delete(self, handle):
        disposition = wt.BYTE(1)  # FILE_DISPOSITION_INFO.DeleteFile is BOOLEAN
        if not self.api.SetFileInformationByHandle(handle, 4, byref(disposition), sizeof(disposition)):
            raise HostError("Development scratch deletion was not confirmed.")

    def observe(self, deadline):
        if self.root_handle is None:
            raise HostError("Development scratch ownership is unconfirmed.")
        self._scan(deadline, delete=False)
        _check_time(deadline)

    def clean(self, deadline):
        if not self.created and not self.ancestors:
            return
        _check_time(deadline)
        if self.created:
            if self.identity is None or not self.empty_at_creation:
                raise HostError("Development scratch ownership is unconfirmed.")
            if self.root_handle is not None:
                self._close(self.root_handle)
                self.root_handle = None
            handle, info = self._open(self.path, delete=True)
            try:
                if info.identity != self.identity or not info.attributes & 0x10:
                    raise HostError("Development scratch identity changed.")
                self._scan(deadline, delete=True)
                self._delete(handle)
            finally:
                self._close(handle)
            # Missing, rather than merely unreadable or delete-pending, is required.
            try:
                self.path.lstat()
            except FileNotFoundError:
                self.created = False
            else:
                raise HostError("Development scratch remains after cleanup.")
        while self.ancestors:
            self._close(self.ancestors[-1])
            self.ancestors.pop()
        _check_time(deadline)


@dataclass(frozen=True, slots=True)
class _MonitoredCancellation:
    requested: object
    controls: DevelopmentLocalImageHostControlsV0

    def is_set(self):
        return self.requested.is_set() or self.controls.interrupted()


class DevelopmentLocalImageHostControlsV0:
    """One process-scoped host monitor, used only by T13's development mode."""

    def __init__(self, approval: DevelopmentLocalImageRuntimeApprovalV0):
        if type(approval) is not DevelopmentLocalImageRuntimeApprovalV0:
            raise HostError("Development approval type refused.")
        self._initialize(approval)

    def _initialize(self, approval):
        self._approval = approval
        self._scratch = None
        self._requested = None
        self._thread = None
        self._ready = Event()
        self._stop = Event()
        self._violation = Event()
        self._confirmed_until = 0
        self._post_deadline = 0
        self._post_offline = False
        self._last_sample = 0
        self._process = None

    def admits(self, frame, profile) -> bool:
        approved = self._approval
        if (
            profile is not approved.profile or type(profile) is not NativeLocalImageRuntimeProfileV0
            or approved.scope != DEVELOPMENT_SCOPE or self._violation.is_set()
            or not all(type(d) is str and _DIGEST.fullmatch(d) is not None
                       for d in (approved.encoded_sha256, approved.bgr8_sha256))
            or type(approved.width) is not int or type(approved.height) is not int
        ):
            return False
        # T12 hashes the exact HTTP bytes before decode. Reverify the packed
        # raster here and compare both identities, with no path/name admission.
        binding = _validate_frame(frame).binding
        return (
            binding.encoded_sha256 == approved.encoded_sha256
            and binding.bgr8_sha256 == approved.bgr8_sha256
            and binding.width == approved.width and binding.height == approved.height
        )

    def approve(self, profile, deadline) -> bool:
        if self._approval.scope != DEVELOPMENT_SCOPE or not self._ready_for_profile(profile, deadline):
            return False
        self._confirmed_until = _confirmation_deadline(profile.controls_manifest)
        return monotonic_ns() < min(deadline, self._confirmed_until)

    def _ready_for_profile(self, profile, deadline):
        return (
            profile is self._approval.profile and type(profile) is NativeLocalImageRuntimeProfileV0
            and self._scratch is None and self._thread is None
            and not self._violation.is_set() and monotonic_ns() < deadline
            and any(_same_path(pin.path, str(Path(__file__).absolute())) for pin in profile.runtime)
        )

    def _observe(self, deadline):
        started = monotonic_ns()
        deadline = min(deadline, self._confirmed_until, started + _QUERY_LIMIT_NS)
        self._scratch.observe(deadline)
        if not _offline_sample(deadline):
            raise HostError("Development offline observation refused.")
        _check_time(deadline)
        self._last_sample = started

    def _monitor(self, first_deadline, deadline):
        try:
            self._observe(first_deadline)
            self._ready.set()
            while not self._stop.wait(_SAMPLE_INTERVAL):
                if monotonic_ns() >= deadline:
                    break
                self._observe(min(deadline, self._last_sample + _MAX_SAMPLE_AGE_NS))
        except Exception:
            self._violation.set()
        finally:
            self._ready.set()
        # The controller requests the final sample only after T13 confirms worker exit.
        self._stop.wait()
        try:
            self._post_offline = _offline_sample(self._post_deadline)
        except Exception:
            self._violation.set()

    def before_launch(self, profile, deadline) -> DevelopmentIsolationEvidenceV0:
        if not self.approve(profile, deadline):
            raise HostError("Development runtime refused.")
        scratch = Path(profile.launch.working_directory)
        if any(
            scratch.is_relative_to(Path(pin.path).parent) for pin in (*profile.detector, *profile.recognizer)
        ):
            raise HostError("Development scratch overlaps native model storage.")
        self._scratch = _Scratch(scratch, profile.scratch_bytes)
        try:
            self._scratch.start(deadline)
            first_deadline = min(deadline, self._confirmed_until, monotonic_ns() + _QUERY_LIMIT_NS)
            thread = Thread(
                target=self._monitor, args=(first_deadline, deadline),
                name="pantryproof-t14-observation", daemon=True,
            )
            thread.start()
            self._thread = thread
            # Windows table reads are synchronous. Bound the caller's wait independently.
            while True:
                if self._requested is not None and self._requested.is_set():
                    raise InterruptedError("Development startup cancelled.")
                _check_time(first_deadline)
                if self._ready.wait(min(0.05, (first_deadline - monotonic_ns()) / 1_000_000_000)):
                    break
            _check_time(first_deadline)
            evidence = self._evidence()
            if not evidence.permits_development():
                raise HostError("Development pre-launch observation refused.")
            return evidence
        except Exception:
            self._violation.set()
            raise

    def _evidence(self):
        active = self._thread is not None and self._thread.is_alive() and not self._stop.is_set()
        now = monotonic_ns()
        recent = (
            not self._violation.is_set() and self._last_sample > 0
            and now < min(self._confirmed_until, self._last_sample + _MAX_SAMPLE_AGE_NS)
        )
        return DevelopmentIsolationEvidenceV0(
            recent, self._scratch is not None and self._scratch.root_handle is not None, active,
        )

    def suspended_process(self, process, profile, deadline) -> DevelopmentIsolationEvidenceV0:
        _check_time(deadline)
        if profile is not self._approval.profile or self._process is not None:
            raise HostError("Development process association refused.")
        # T13 has already verified the actual process image and job membership.
        self._process = process
        return self._evidence()

    def monitor_cancellation(self, requested):
        self._requested = requested
        return _MonitoredCancellation(requested, self)

    def interrupted(self) -> bool:
        if self._thread is not None and not self._evidence().permits_development():
            self._violation.set()
        return self._violation.is_set()

    def finish(self, process, profile, deadline) -> FinalObservation:
        # Called by T13 only after root exit and job count zero were observed.
        if profile is not self._approval.profile or (
            self._process is not None and self._process != process
        ):
            self._violation.set()
            return FinalObservation(False, True)
        if self._thread is not None:
            wait_deadline = deadline
            if not self._stop.is_set():
                self._post_deadline = self._teardown_observation_deadline(deadline)
                self._stop.set()
                wait_deadline = self._post_deadline
            self._thread.join(max(0, (wait_deadline - monotonic_ns()) / 1_000_000_000))
            if self._thread.is_alive():
                self._violation.set()
                return FinalObservation(False, True)
            self._thread = None
        if not self._post_offline:
            self._violation.set()
        try:
            if self._scratch is not None:
                try:
                    self._scratch.observe(deadline)
                except Exception:
                    self._violation.set()
                self._scratch.clean(deadline)
                self._scratch = None
        except Exception:
            self._violation.set()
            return FinalObservation(False, True)
        self._process = None
        self._requested = None
        self._confirmed_until = 0
        self._post_deadline = 0
        self._post_offline = False
        self._last_sample = 0
        self._ready.clear()
        self._stop.clear()
        return FinalObservation(True, self._violation.is_set())

    def _teardown_observation_deadline(self, deadline):
        return min(deadline, self._confirmed_until, monotonic_ns() + _QUERY_LIMIT_NS)

    def violation_seen(self, profile) -> bool:
        return profile is not self._approval.profile or self._violation.is_set()

_PROTO_MAX_NS = 14_400_000_000_000


def _prototype_control_bytes(pin):
    if not _file_pin(pin) or pin.length > _MAX_CONTROLS_BYTES:
        raise HostError("Prototype controls pin refused.")
    with Path(pin.path).open("rb") as stream:
        raw = stream.read(_MAX_CONTROLS_BYTES + 1)
    if len(raw) != pin.length or sha256(raw).hexdigest() != pin.sha256:
        raise HostError("Prototype controls pin changed.")
    return raw


class PrototypeSessionV1:
    """A monotonic session over one immutable, approved controls attestation."""

    def __init__(self, profile, *, clock_ns=monotonic_ns, wall_ns=time_ns):
        self.profile = profile
        self._clock_ns = clock_ns
        self._revoked = Event()
        self._unavailable = ()
        try:
            record = json.loads(_prototype_control_bytes(profile.controls_manifest).decode("utf-8"),
                                object_pairs_hook=_unique_pairs)
            if (type(record) is not dict or record.keys() != {
                "scope", "network_observation", "physical_disconnection_confirmed_unix_s", "expires_unix_s",
            } or record["scope"] != PROTOTYPE_SCOPE or record["network_observation"] != NETWORK_OBSERVATION):
                raise ValueError
            confirmed, expires = record["physical_disconnection_confirmed_unix_s"], record["expires_unix_s"]
            opened_at = clock_ns()
            wall = wall_ns()
            if (type(confirmed) is not int or type(expires) is not int or confirmed <= 0
                    or not confirmed * 1_000_000_000 <= wall < expires * 1_000_000_000
                    or not 0 < expires - confirmed <= 14_400):
                raise ValueError
        except (OSError, ValueError, RecursionError, HostError):
            raise HostError("Prototype control evidence refused.") from None
        self.deadline_ns = opened_at + min(_PROTO_MAX_NS, expires * 1_000_000_000 - wall)

    def observe_runtime(self, *unavailable):
        """Bind request-independent containment and quarantine observations."""
        self._unavailable = unavailable

    def revoke(self):
        self._revoked.set()

    def is_active(self):
        if self._clock_ns() >= self.deadline_ns or any(check() for check in self._unavailable):
            self.revoke()
        return not self._revoked.is_set()

    def evidence_unchanged(self):
        try:
            _prototype_control_bytes(self.profile.controls_manifest)
        except (OSError, HostError):
            self.revoke()
            return False
        return True

    def controls_valid(self):
        return self.evidence_unchanged() and self.is_active()

    def permits(self, deadline, processing_deadline=None):
        if not self.is_active() or deadline is None or deadline * 1_000_000_000 > self.deadline_ns:
            return False
        if processing_deadline is not None:
            remaining = int(processing_deadline * 1_000_000_000) - self._clock_ns()
            if remaining < self.profile.minimum_work_ns + self.profile.teardown_reserve_ns:
                return False
        return self.controls_valid()


class PrototypeLocalImageHostControlsV1(DevelopmentLocalImageHostControlsV0):
    """Reuse the monitored job/scratch lifecycle under a distinct prototype grant."""

    def __init__(self, session: PrototypeSessionV1):
        self.session = session
        self._initialize(session)

    def admits(self, frame, profile):
        if profile is not self.session.profile or not self.session.controls_valid():
            return False
        _validate_frame(frame)
        return True

    def approve(self, profile, deadline):
        if not self._ready_for_profile(profile, deadline) or not self.session.controls_valid():
            return False
        self._confirmed_until = self.session.deadline_ns
        return deadline <= self._confirmed_until

    def _observe(self, deadline):
        if not self.session.evidence_unchanged():
            raise HostError("Prototype control evidence invalidated.")
        super()._observe(deadline)

    def _teardown_observation_deadline(self, deadline):
        return min(deadline, monotonic_ns() + _QUERY_LIMIT_NS)
