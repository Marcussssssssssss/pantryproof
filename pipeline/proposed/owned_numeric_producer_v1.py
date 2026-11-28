"""Opt-in synthetic numerical production, not complete D3 admission.

Ownership is established only by the three construction operations below.
It is local bookkeeping under trusted-code/quiescent-alias assumptions, not
producer authentication. No existing Decimal can be adopted. Logical counters
do not bound whole-graph validation, physical memory, or elapsed time.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, fields
import decimal
from enum import Enum
from functools import wraps
import sys
import threading
from weakref import WeakValueDictionary, ref

from pipeline.contracts import FieldStatus, OcrSourceToken, StructuredField
from pipeline.proposed.bounded_numeric_ingress_v1 import (
    IngressContextV1, IngressProfileV1, NumericIngressError,
    NumericIngressErrorCode,
)
from pipeline.proposed.native_confidence_recipe_v1 import (
    NativeConfidenceErrorV1, NativeConfidenceErrorCodeV1,
    NativeConfidenceProfileV1, NativeConfidenceScopeStateV1, NativeConfidenceScopeV1,
)


class OwnedNumericErrorCodeV1(str, Enum):
    PROFILE_INVALID = "PROFILE_INVALID"
    UNSUPPORTED_NUMERIC_TYPE = "UNSUPPORTED_NUMERIC_TYPE"
    INVALID_NUMERIC_VALUE = "INVALID_NUMERIC_VALUE"
    UNREGISTERED_DECIMAL = "UNREGISTERED_DECIMAL"
    FOREIGN_SCOPE = "FOREIGN_SCOPE"
    SCOPE_CLOSED = "SCOPE_CLOSED"
    SCOPE_INVALID = "SCOPE_INVALID"
    CONTEXT_MISMATCH = "CONTEXT_MISMATCH"
    REPRESENTATION_LIMIT = "REPRESENTATION_LIMIT"
    REGISTRY_CAPACITY_EXCEEDED = "REGISTRY_CAPACITY_EXCEEDED"
    WORK_BUDGET_EXHAUSTED = "WORK_BUDGET_EXHAUSTED"
    SOURCE_BINDING_ERROR = "SOURCE_BINDING_ERROR"
    CONTROLLED_OPERATION_FAILED = "CONTROLLED_OPERATION_FAILED"


class OwnedNumericErrorV1(RuntimeError):
    """Closed diagnostics, deliberately outside legacy ValueError wrappers."""

    def __init__(self, code: OwnedNumericErrorCodeV1):
        if type(code) is not OwnedNumericErrorCodeV1:
            raise TypeError("Invalid owned numeric error code.")
        self.code = code
        super().__init__(code.value)


_Code = OwnedNumericErrorCodeV1


def _reject(code: OwnedNumericErrorCodeV1) -> None:
    raise OwnedNumericErrorV1(code)


@dataclass(frozen=True, slots=True, kw_only=True)
class OwnedNumericProfileV1:
    """Every limit is mandatory; no production defaults are supplied."""

    max_coefficient_digits: int
    max_exponent_magnitude: int
    max_recipe_constructions: int
    max_recipe_work_units: int
    max_registry_entries: int
    max_owner_work_units: int
    max_divisions: int
    max_ratio_int_bits: int
    max_source_id_codepoints: int
    native_confidence_profile: NativeConfidenceProfileV1

    def __post_init__(self) -> None:
        _snapshot_profile(self)


def _snapshot_profile(profile: object) -> tuple[dict[str, int], NativeConfidenceProfileV1]:
    if type(profile) is not OwnedNumericProfileV1:
        _reject(_Code.PROFILE_INVALID)
    limits = {}
    for item in fields(OwnedNumericProfileV1):
        if item.name == "native_confidence_profile":
            continue
        value = getattr(profile, item.name, None)
        if type(value) is not int or int.bit_length(value) > 31 or value < 1:
            _reject(_Code.PROFILE_INVALID)
        limits[item.name] = value
    # The derived-ratio representation proof in S01 covers at most 64 bits.
    if limits["max_ratio_int_bits"] > 64:
        _reject(_Code.PROFILE_INVALID)
    native = getattr(profile, "native_confidence_profile", None)
    if type(native) is not NativeConfidenceProfileV1:
        _reject(_Code.PROFILE_INVALID)
    try:
        native_copy = NativeConfidenceProfileV1(**{
            item.name: getattr(native, item.name) for item in fields(NativeConfidenceProfileV1)
        })
    except (AttributeError, NativeConfidenceErrorV1):
        _reject(_Code.PROFILE_INVALID)
    if (native_copy.max_coefficient_digits > limits["max_coefficient_digits"]
            or native_copy.max_quantum_exponent_magnitude > limits["max_exponent_magnitude"]
            or limits["max_exponent_magnitude"] > decimal.MAX_EMAX
            or -limits["max_exponent_magnitude"] < decimal.MIN_ETINY
            or limits["max_coefficient_digits"] > decimal.MAX_PREC):
        _reject(_Code.PROFILE_INVALID)
    return limits, native_copy


@dataclass(frozen=True, slots=True)
class NumericCapacityV1:
    limit: int
    used: int

    @property
    def remaining(self) -> int:
        return self.limit - self.used


@dataclass(frozen=True, slots=True)
class OwnedNumericRegistryUsageV1:
    """Selected owner's fixed slot reservation and prepaid registry work."""

    process_capacity: int
    reserved_slots: int
    work_reserved: int


@dataclass(frozen=True, slots=True)
class OwnedNumericCapacityV1:
    """Point-in-time accounting data with no reference to the live owner."""

    profile: OwnedNumericProfileV1
    owner_work: NumericCapacityV1
    owner_registry: NumericCapacityV1
    owner_constructions: int
    divisions: NumericCapacityV1
    recipe_constructions: NumericCapacityV1
    recipe_work: NumericCapacityV1
    native_attempts: NumericCapacityV1
    native_work: NumericCapacityV1
    native_registry: NumericCapacityV1
    native_recipe_constructions: NumericCapacityV1
    native_recipe_work: NumericCapacityV1
    native_live_text: NumericCapacityV1
    native_live_digits: NumericCapacityV1
    native_live_limbs: NumericCapacityV1
    native_live_binary: NumericCapacityV1
    native_source_anchors: NumericCapacityV1
    native_retained_int_bits: NumericCapacityV1
    bounded_registry: OwnedNumericRegistryUsageV1 | None = None


def _capacity(limit: int, used: int) -> NumericCapacityV1:
    if type(used) is not int or not 0 <= used <= limit:
        _reject(_Code.SCOPE_INVALID)
    return NumericCapacityV1(limit=limit, used=used)


_ACTIVE: ContextVar[OwnedNumericScopeV1 | None] = ContextVar("owned_numeric_scope_v1", default=None)
_INSPECTING_ANCHORS: ContextVar[OwnedNumericScopeV1 | None] = ContextVar(
    "inspecting_owned_numeric_anchors_v1", default=None,
)
# Weak owners plus strong local Decimal references prevent stale id reuse.
# This registry distinguishes a live foreign owner; it is not an attestation.
_OWNERS: WeakValueDictionary[int, OwnedNumericScopeV1] = WeakValueDictionary()
_OWNERS_LOCK = threading.RLock()


_REGISTRY_MUTEX = threading.Lock()
_REGISTRY_THREAD = threading.local()
_CONFIGURING = object()
_LEGACY = object()
_REGISTRY_MODE = None


@contextmanager
def _registry_lock():
    # Also reject same-thread reentry from runtime callbacks before waiting.
    if getattr(_REGISTRY_THREAD, "locked", False):
        _reject(_Code.SCOPE_INVALID)
    _REGISTRY_THREAD.locked = True
    try:
        with _REGISTRY_MUTEX:
            yield
    finally:
        _REGISTRY_THREAD.locked = False


class _RegistryReservation:
    __slots__ = ("owner", "retired", "reclaimable")

    def __init__(self, owner: OwnedNumericScopeV1):
        self.owner = ref(owner)
        self.retired = False
        self.reclaimable = False


class _RegistrySlot:
    __slots__ = ("reservation", "key")

    def __init__(self):
        self.reservation: _RegistryReservation | None = None
        self.key: int | None = None

    def reserve(self, reservation: _RegistryReservation) -> None:
        self.reservation = reservation

    def clear(self) -> None:
        # Keep the slot occupied until its old key has been discarded.
        self.key = None
        self.reservation = None


class _BoundedRegistry:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.slots = [_RegistrySlot() for _ in range(capacity)]

    def _sweep(self) -> None:
        for slot in self.slots:
            with _registry_lock():
                reservation = slot.reservation
            if reservation is None:
                continue
            # A temporary strong reference from this call is dropped outside
            # the mutex. A dead weak reference cannot become live again.
            if reservation.reclaimable or reservation.owner() is None:
                with _registry_lock():
                    if slot.reservation is reservation:
                        slot.clear()

    def _clear(self, reservation: _RegistryReservation) -> None:
        for slot in self.slots:
            if slot.reservation is reservation:
                slot.clear()

    def reserve(self, reservation: _RegistryReservation, count: int) -> None:
        self._sweep()
        with _registry_lock():
            free = 0
            for slot in self.slots:
                free += slot.reservation is None
            if free < count:
                _reject(_Code.REGISTRY_CAPACITY_EXCEEDED)
            try:
                for slot in self.slots:
                    if slot.reservation is None:
                        slot.reserve(reservation)
                        count -= 1
                        if count == 0:
                            return
                _reject(_Code.SCOPE_INVALID)
            except BaseException:
                reservation.retired = True
                reservation.reclaimable = True  # no local values allocated yet
                self._clear(reservation)
                raise

    def publish(self, reservation: _RegistryReservation, key: int) -> None:
        with _registry_lock():
            if reservation.retired:
                _reject(_Code.SCOPE_INVALID)
            for slot in self.slots:
                if slot.reservation is reservation and slot.key is None:
                    slot.key = key
                    return
            _reject(_Code.SCOPE_INVALID)

    def find_owner(self, key: int) -> OwnedNumericScopeV1 | None:
        owner = None
        with _registry_lock():
            for slot in self.slots:
                reservation = slot.reservation
                if (slot.key == key and reservation is not None
                        and not reservation.retired):
                    owner = reservation.owner()
                    if owner is not None:
                        break
        return owner

    def retire(self, reservation: _RegistryReservation) -> None:
        with _registry_lock():
            self._clear(reservation)


def configure_owned_numeric_registry_capacity_v1(capacity: int) -> None:
    """Select fixed-capacity S01 ownership before the first owner enters."""
    global _REGISTRY_MODE
    if type(capacity) is not int or not 0 < capacity <= sys.maxsize:
        _reject(_Code.PROFILE_INVALID)
    configured_here = False
    failed = False
    try:
        with _registry_lock():
            if _REGISTRY_MODE is not None:
                _reject(_Code.SCOPE_INVALID)
            configured_here = True
            _REGISTRY_MODE = _CONFIGURING
        try:
            registry = _BoundedRegistry(capacity)
        except (MemoryError, KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            failed = True
        if failed:
            _reject(_Code.CONTROLLED_OPERATION_FAILED)
        with _registry_lock():
            _REGISTRY_MODE = registry
    except BaseException:
        if configured_here:
            with _registry_lock():
                if _REGISTRY_MODE is _CONFIGURING:
                    _REGISTRY_MODE = None
        raise


def _select_registry() -> _BoundedRegistry | None:
    global _REGISTRY_MODE
    with _registry_lock():
        if _REGISTRY_MODE is None:
            _REGISTRY_MODE = _LEGACY
        if _REGISTRY_MODE is _CONFIGURING:
            _reject(_Code.SCOPE_INVALID)
        return None if _REGISTRY_MODE is _LEGACY else _REGISTRY_MODE


def _execution_owner() -> tuple[int, object]:
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    return threading.get_ident(), task


def _arithmetic_context() -> decimal.Context:
    # Legacy ranking specifies precision/rounding and inherits the other
    # Context defaults. Refuse incompatible defaults instead of changing them.
    legacy = decimal.Context(prec=34, rounding=decimal.ROUND_HALF_EVEN)
    if ((legacy.prec, legacy.rounding, legacy.Emin, legacy.Emax,
         legacy.capitals, legacy.clamp) != (34, decimal.ROUND_HALF_EVEN,
                                           -999999, 999999, 1, 0)
            or {signal for signal, enabled in legacy.traps.items() if enabled}
            != {decimal.DivisionByZero, decimal.InvalidOperation, decimal.Overflow}):
        _reject(_Code.CONTEXT_MISMATCH)
    return legacy


def current_owned_numeric_scope_v1() -> OwnedNumericScopeV1 | None:
    """Producer hook. An aborted selection never falls back to legacy."""
    scope = _ACTIVE.get()
    if scope is not None:
        scope._check_open()
    return scope


def _operation(function):
    """Sanitize dependency errors and invalidate all ownership on failure."""
    @wraps(function)
    def invoke(self, *args, **kwargs):
        if _execution_owner() != self._owner:
            _reject(_Code.FOREIGN_SCOPE)
        if self._registry is None:
            return perform(self, *args, **kwargs)
        self._check_not_busy()
        self._busy = True
        try:
            return perform(self, *args, **kwargs)
        finally:
            self._busy = False

    def perform(self, *args, **kwargs):
        failure = None
        try:
            self._check_open()
            return function(self, *args, **kwargs)
        except OwnedNumericErrorV1 as exc:
            failure = exc.code
        except NumericIngressError as exc:
            failure = {
                NumericIngressErrorCode.RESOURCE_LIMIT: _Code.REPRESENTATION_LIMIT,
                NumericIngressErrorCode.INVALID_NUMERIC_VALUE: _Code.INVALID_NUMERIC_VALUE,
                NumericIngressErrorCode.INVALID_SHAPE: _Code.UNSUPPORTED_NUMERIC_TYPE,
            }.get(exc.code, _Code.CONTROLLED_OPERATION_FAILED)
            if exc.code is NumericIngressErrorCode.RESOURCE_LIMIT and exc.limit_field == "max_work_units":
                failure = _Code.WORK_BUDGET_EXHAUSTED
        except NativeConfidenceErrorV1 as exc:
            failure = {
                NativeConfidenceErrorCodeV1.RESOURCE_LIMIT: _Code.REPRESENTATION_LIMIT,
                NativeConfidenceErrorCodeV1.UNSUPPORTED_NATIVE_TYPE: _Code.UNSUPPORTED_NUMERIC_TYPE,
                NativeConfidenceErrorCodeV1.NONFINITE_VALUE: _Code.INVALID_NUMERIC_VALUE,
                NativeConfidenceErrorCodeV1.SOURCE_BINDING_ERROR: _Code.SOURCE_BINDING_ERROR,
                NativeConfidenceErrorCodeV1.RUNTIME_INCOMPATIBLE: _Code.CONTEXT_MISMATCH,
            }.get(exc.code, _Code.CONTROLLED_OPERATION_FAILED)
            if exc.code is NativeConfidenceErrorCodeV1.RESOURCE_LIMIT and exc.limit_field == "max_work_units":
                failure = _Code.WORK_BUDGET_EXHAUSTED
        except (MemoryError, KeyboardInterrupt, SystemExit):
            self._release("ABORTED")
            raise
        except Exception:
            failure = _Code.CONTROLLED_OPERATION_FAILED
        except BaseException:
            if self._registry is not None:
                self._release("ABORTED")
            raise
        self._release("ABORTED")
        # Outside the dependency handler: neither cause nor context is forwarded.
        raise OwnedNumericErrorV1(failure)
    return invoke


class OwnedNumericScopeV1:
    """Explicit synchronous scope; one thread/task, no nesting or transfer.

    Construct before confidence-rule construction; enter before making any
    owned values. Keep it open through graph construction and reuse. Source
    anchors must be genuine existing records. This class does not validate a
    whole receipt graph or bound work already done to construct those records.
    """

    def __init__(self, *, profile: OwnedNumericProfileV1,
                 ocr_sources: tuple[OcrSourceToken, ...],
                 extractor_sources: tuple[StructuredField, ...]):
        self._limits, self._native_profile = _snapshot_profile(profile)
        self._state = "NEW"
        self._owner = _execution_owner()
        self._token = None
        self._entries: dict[int, tuple[decimal.Decimal, str]] = {}
        self._sources: dict[str, tuple[object, str, object]] = {}
        self._anchors = (ocr_sources, extractor_sources)
        self._source_native: NativeConfidenceScopeV1 | None = None
        self._extractor_statuses: tuple[FieldStatus, ...] = ()
        self._native = self._ingress = None
        self._zero = self._one = None
        self._work = self._constructions = self._divisions = 0
        self._registry = self._reservation = self._local_entries = None
        self._registry_work = 0
        self._busy = False

    def __enter__(self) -> OwnedNumericScopeV1:
        if (self._state != "NEW" or _ACTIVE.get() is not None
                or _execution_owner() != self._owner):
            _reject(_Code.SCOPE_INVALID)
        self._state = "ENTERING"
        try:
            self._registry = _select_registry()
            self._token = _ACTIVE.set(self)
            self._state = "OPEN"
            self._initialize()
        except BaseException:
            self._state = "ABORTED"
            self._reset_selection()
            raise
        return self

    @_operation
    def _initialize(self) -> None:
        if self._registry is not None:
            self._reserve_registry()
        _arithmetic_context()
        tokens, fields_ = self._anchors
        self._native = NativeConfidenceScopeV1(
            profile=self._native_profile, ocr_sources=tokens, extractor_sources=fields_)
        if self._registry is not None:
            # The native child just captured these same frozen records.
            # Both passes observe the same status under the scope's
            # trusted-code and quiescent-source contract.
            self._extractor_statuses = tuple(source.status for source in fields_)
            self._source_native = self._native
        # Native scope checked exact containers, types, counts and native sizes.
        for sources, role in ((tokens, "OCR"), (fields_, "EXTRACTOR")):
            for source in sources:
                name = source.token_id if role == "OCR" else source.field_id
                if type(name) is not str:
                    _reject(_Code.SOURCE_BINDING_ERROR)
                if len(name) > self._limits["max_source_id_codepoints"]:
                    _reject(_Code.REPRESENTATION_LIMIT)
                self._charge(1 + len(name))
                if not name or name in self._sources:
                    _reject(_Code.SOURCE_BINDING_ERROR)
                native = source.raw_confidence if role == "OCR" else source.confidence
                self._sources[name] = (source, role, native)
        self._ingress = IngressContextV1(IngressProfileV1(
            max_coefficient_digits=self._limits["max_coefficient_digits"],
            max_exponent_magnitude=self._limits["max_exponent_magnitude"],
            max_constructions=self._limits["max_recipe_constructions"],
            max_work_units=self._limits["max_recipe_work_units"],
        ))
        self._zero = self._construct_operand("0")
        self._one = self._construct_operand("1")
        self._anchors = None

    def _construct_operand(self, coefficient: str) -> decimal.Decimal:
        construct = (self.construct_decimal if self._registry is None
                     else self._construct_decimal)
        return construct(sign=0, coefficient=coefficient, quantum_exponent=0)

    def _check_not_busy(self) -> None:
        if (self._busy or _INSPECTING_ANCHORS.get() is self
                or (self._registry is not None
                    and getattr(_REGISTRY_THREAD, "locked", False))):
            _reject(_Code.SCOPE_INVALID)

    def _check_open(self) -> None:
        if _execution_owner() != self._owner or _ACTIVE.get() is not self:
            _reject(_Code.FOREIGN_SCOPE if self._state == "OPEN" else _Code.SCOPE_CLOSED)
        if self._state != "OPEN":
            _reject(_Code.SCOPE_CLOSED)

    def _charge(self, units: int) -> None:
        if units > self._limits["max_owner_work_units"] - self._work:
            _reject(_Code.WORK_BUDGET_EXHAUSTED)
        self._work += units

    def _charge_registry(self, units: int) -> None:
        self._charge(units)
        self._registry_work += units

    def _reserve_registry(self) -> None:
        registry = self._registry
        count = self._limits["max_registry_entries"]
        if count > registry.capacity:
            _reject(_Code.REGISTRY_CAPACITY_EXCEEDED)
        # Sweep, free count, reservation, rollback, retirement, and local
        # fixed storage initialization/release. Cleanup needs no later charge.
        self._charge_registry(6 * registry.capacity + 2 * count)
        reservation = _RegistryReservation(self)
        self._reservation = reservation
        registry.reserve(reservation, count)
        self._local_entries = [None] * count

    def _reserve_publication(self) -> None:
        if self._registry is not None:
            self._charge_registry(self._registry.capacity + 1)

    def _reserve_entries(self, count: int) -> None:
        if count > self._limits["max_registry_entries"] - self.registry_size:
            _reject(_Code.REPRESENTATION_LIMIT)

    def _publish_created(self, value: decimal.Decimal, origin: str) -> decimal.Decimal:
        # Only controlled recipe, anchored-native and division sites call here.
        if self._registry is None:
            self._entries[id(value)] = (value, origin)
            with _OWNERS_LOCK:
                _OWNERS[id(value)] = self
        else:
            self._local_entries[self._constructions] = (value, origin)
            self._registry.publish(self._reservation, id(value))
        self._constructions += 1
        return value

    @_operation
    def construct_decimal(self, *, sign: int, coefficient: str,
                          quantum_exponent: int) -> decimal.Decimal:
        """Construct an owned recipe; never accept an existing Decimal."""
        return self._construct_decimal(sign=sign, coefficient=coefficient,
                                       quantum_exponent=quantum_exponent)

    def _construct_decimal(self, *, sign: int, coefficient: str,
                           quantum_exponent: int) -> decimal.Decimal:
        self._reserve_entries(1)
        if type(sign) is not int or type(quantum_exponent) is not int or type(coefficient) is not str:
            _reject(_Code.UNSUPPORTED_NUMERIC_TYPE)
        if int.bit_length(sign) > 1 or int.bit_length(quantum_exponent) > 31:
            _reject(_Code.REPRESENTATION_LIMIT)
        if len(coefficient) > self._limits["max_coefficient_digits"]:
            _reject(_Code.REPRESENTATION_LIMIT)
        self._charge(1 + len(coefficient))
        self._reserve_publication()
        value = self._ingress.construct_decimal(sign, coefficient, quantum_exponent, "field")
        return self._publish_created(value, "RECIPE")

    @_operation
    def require_owned(self, value: object) -> decimal.Decimal:
        """Identity lookup only; do not inspect or coerce an opaque value."""
        self._charge(1)
        if type(value) is not decimal.Decimal:
            _reject(_Code.UNSUPPORTED_NUMERIC_TYPE)
        if self._registry is None:
            entry = self._entries.get(id(value))
            if entry is not None and entry[0] is value:
                return value
            with _OWNERS_LOCK:
                owner = _OWNERS.get(id(value))
        else:
            self._charge_registry(self._limits["max_registry_entries"])
            for index in range(self._constructions):
                if self._local_entries[index][0] is value:
                    return value
            self._charge_registry(self._registry.capacity)
            owner = self._registry.find_owner(id(value))
        if owner is not None and owner is not self:
            _reject(_Code.FOREIGN_SCOPE)
        _reject(_Code.UNREGISTERED_DECIMAL)

    @_operation
    def _reject_numeric_value(self) -> None:
        """Producer semantic rejection without publishing private source IDs."""
        _reject(_Code.INVALID_NUMERIC_VALUE)

    @_operation
    def confidence(self, *, value: object, source_id: str) -> decimal.Decimal | None:
        """Convert captured native confidence only; never accept a Decimal.

        Numerical ownership is independent of attribution. Existing producer
        callers supply original native values, so Decimal reuse belongs solely
        to require_owned(), not this source-conversion boundary.
        """
        if type(source_id) is not str:
            _reject(_Code.SOURCE_BINDING_ERROR)
        if len(source_id) > self._limits["max_source_id_codepoints"]:
            _reject(_Code.REPRESENTATION_LIMIT)
        self._charge(1 + len(source_id))
        anchor = self._sources.get(source_id)
        if anchor is None:
            _reject(_Code.SOURCE_BINDING_ERROR)
        source, role, captured_native = anchor
        if role == "OCR" and type(source) is OcrSourceToken:
            stored, stored_id = source.raw_confidence, source.token_id
        elif role == "EXTRACTOR" and type(source) is StructuredField:
            stored, stored_id = source.confidence, source.field_id
        else:
            _reject(_Code.SOURCE_BINDING_ERROR)
        if type(stored_id) is not str or stored_id != source_id or stored is not captured_native:
            _reject(_Code.SOURCE_BINDING_ERROR)
        if value is not None and type(value) not in (int, float):
            _reject(_Code.UNSUPPORTED_NUMERIC_TYPE)
        if stored is not value:
            _reject(_Code.SOURCE_BINDING_ERROR)
        if value is not None:
            self._reserve_entries(1)
            self._reserve_publication()
        result = (self._native.convert_ocr_confidence(source=source) if role == "OCR"
                  else self._native.convert_extractor_confidence(source=source))
        return None if result is None else self._publish_created(result, "NATIVE_CONFIDENCE")

    @_operation
    def divide_ratio(self, *, numerator: int, denominator: int) -> decimal.Decimal:
        """Produce the exact legacy precision-34 normalized-ratio result."""
        context = _arithmetic_context()
        if type(numerator) is not int or type(denominator) is not int:
            _reject(_Code.UNSUPPORTED_NUMERIC_TYPE)
        bits = self._limits["max_ratio_int_bits"]
        if int.bit_length(numerator) > bits or int.bit_length(denominator) > bits:
            _reject(_Code.REPRESENTATION_LIMIT)
        if denominator <= 0 or numerator < 0 or numerator > denominator:
            _reject(_Code.INVALID_NUMERIC_VALUE)
        if self._divisions >= self._limits["max_divisions"]:
            _reject(_Code.WORK_BUDGET_EXHAUSTED)
        # Decimal integer spelling has <= bits digits. A nonzero ratio is
        # >= 1/(2**bits-1), adjusted exponent >= -bits; precision 34 implies
        # quantum >= -bits-33. Zero division has quantum zero here.
        if (max(bits, 34) > self._limits["max_coefficient_digits"]
                or bits + 33 > self._limits["max_exponent_magnitude"]):
            _reject(_Code.REPRESENTATION_LIMIT)
        self._reserve_entries(3)
        # 2**3 < 10: ceil(bits/3) decimal digits is a conservative bound.
        decimal_digits = (bits + 2) // 3
        self._charge((2 * decimal_digits + 34) ** 2)
        self._divisions += 1
        left = self._construct_operand(str(numerator))
        right = self._construct_operand(str(denominator))
        self._reserve_publication()
        result = context.divide(left, right)
        return self._publish_created(result, "DERIVED_DIVISION")

    @property
    def zero(self) -> decimal.Decimal:
        self._check_open()
        return self._zero

    @property
    def one(self) -> decimal.Decimal:
        self._check_open()
        return self._one

    @property
    def state(self) -> str:
        return self._state

    @property
    def work_units(self) -> int:
        return self._work

    @property
    def constructions(self) -> int:
        return self._constructions

    @property
    def division_calls(self) -> int:
        return self._divisions

    @property
    def registry_size(self) -> int:
        if self._registry is None:
            return len(self._entries)
        return self._constructions if self._local_entries is not None else 0

    def inspect_source_anchor_binding_v1(
        self, *,
        ocr_sources: tuple[OcrSourceToken, ...],
        extractor_sources: tuple[StructuredField, ...],
        max_anchor_count: int,
        max_source_id_codepoints: int,
        max_total_source_id_codepoints: int,
        max_work_units: int,
    ) -> None:
        """Check the original ordered sources of an active bounded owner.

        A successful check reports the current relationship only. Budgets
        belong to this inspection and neither charge nor reserve owner work.
        """
        try:
            if type(self) is not OwnedNumericScopeV1:
                _reject(_Code.SCOPE_INVALID)
            thread, task = _execution_owner()
            owner_thread, owner_task = self._owner
            if thread != owner_thread or task is not owner_task:
                _reject(_Code.FOREIGN_SCOPE)
            self._check_not_busy()
            self._check_open()
            token = _INSPECTING_ANCHORS.set(self)
            try:
                self._verify_source_anchor_inventory(
                    ocr_sources, extractor_sources, max_anchor_count,
                    max_source_id_codepoints, max_total_source_id_codepoints,
                    max_work_units,
                )
            finally:
                _INSPECTING_ANCHORS.reset(token)
        except OwnedNumericErrorV1 as exc:
            failure = exc.code
        except Exception:
            failure = _Code.CONTROLLED_OPERATION_FAILED
        else:
            return
        # Publish a fresh closed error. A caller already handling an exception
        # must not attach its ambient exception to the public refusal either.
        try:
            raise OwnedNumericErrorV1(failure) from None
        except OwnedNumericErrorV1 as exc:
            exc.__context__ = None
            raise

    def _verify_source_anchor_inventory(
        self, ocr_sources, extractor_sources, max_anchor_count,
        max_source_id_codepoints, max_total_source_id_codepoints, max_work_units,
    ) -> None:
        native = self._native
        reservation = self._reservation
        if (type(self._registry) is not _BoundedRegistry
                or type(reservation) is not _RegistryReservation or reservation.retired
                or type(native) is not NativeConfidenceScopeV1
                or native is not self._source_native
                or native.state is not NativeConfidenceScopeStateV1.OPEN):
            _reject(_Code.SCOPE_INVALID)
        if type(ocr_sources) is not tuple or type(extractor_sources) is not tuple:
            _reject(_Code.SOURCE_BINDING_ERROR)
        for limit in (max_anchor_count, max_source_id_codepoints,
                      max_total_source_id_codepoints, max_work_units):
            if type(limit) is not int or limit <= 0:
                _reject(_Code.PROFILE_INVALID)
        count = len(ocr_sources) + len(extractor_sources)
        if count > max_anchor_count:
            _reject(_Code.REPRESENTATION_LIMIT)
        sources = self._sources
        if type(sources) is not dict or native.source_count != len(sources):
            _reject(_Code.SCOPE_INVALID)
        statuses = self._extractor_statuses
        if count != len(sources) or len(extractor_sources) != len(statuses):
            _reject(_Code.SOURCE_BINDING_ERROR)
        # One setup unit, one fixed unit per anchor, and a budget for the
        # code points in both operands of every reached identifier comparison.
        # Limit the product to machine-sized dimensions even for huge budgets.
        comparison_limit = min(
            max_total_source_id_codepoints,
            2 * count * min(max_source_id_codepoints, sys.maxsize),
        )
        if 1 + count + comparison_limit > max_work_units:
            _reject(_Code.WORK_BUDGET_EXHAUSTED)

        # Only unique insertions occur while populating this private dictionary.
        # Its dense, insertion-ordered items supply each capture exactly once.
        captured = iter(sources.items())
        captured_statuses = iter(statuses)
        remaining = comparison_limit
        for supplied, role, source_type in (
            (ocr_sources, "OCR", OcrSourceToken),
            (extractor_sources, "EXTRACTOR", StructuredField),
        ):
            for source in supplied:
                if type(source) is not source_type:
                    _reject(_Code.SOURCE_BINDING_ERROR)
                name = source.token_id if role == "OCR" else source.field_id
                captured_id, (original, captured_role, native_value) = next(captured)
                if type(name) is not str or type(captured_id) is not str:
                    _reject(_Code.SOURCE_BINDING_ERROR)
                width, captured_width = len(name), len(captured_id)
                if max(width, captured_width) > max_source_id_codepoints:
                    _reject(_Code.REPRESENTATION_LIMIT)
                comparison = width + captured_width
                if comparison > remaining:
                    _reject(_Code.WORK_BUDGET_EXHAUSTED)
                remaining -= comparison
                if source is not original or role != captured_role or name != captured_id:
                    _reject(_Code.SOURCE_BINDING_ERROR)
                if role == "OCR":
                    unchanged = source.raw_confidence is native_value
                else:
                    status = next(captured_statuses)
                    unchanged = source.confidence is native_value and source.status is status
                if not unchanged:
                    _reject(_Code.SOURCE_BINDING_ERROR)

    def inspect_capacity_v1(self) -> OwnedNumericCapacityV1:
        """Read current counters on the owning thread/task between operations.

        The caller must exclude reentrant use. The returned data neither
        reserves capacity nor authorizes later work. This check does not
        consume budget or abort the owner on refusal.
        """
        if type(self) is not OwnedNumericScopeV1:
            _reject(_Code.SCOPE_INVALID)
        if _execution_owner() != self._owner:
            _reject(_Code.FOREIGN_SCOPE)
        self._check_not_busy()
        self._check_open()
        ingress, native = self._ingress, self._native
        if (type(ingress) is not IngressContextV1
                or type(native) is not NativeConfidenceScopeV1
                or native.state is not NativeConfidenceScopeStateV1.OPEN):
            _reject(_Code.SCOPE_INVALID)

        limits = self._limits
        native_profile = NativeConfidenceProfileV1(**{
            item.name: getattr(self._native_profile, item.name)
            for item in fields(NativeConfidenceProfileV1)
        })
        produced = native.registry_size
        recipe_count = ingress.constructions
        text = native.live_text_chars
        digits = native.live_digit_cells
        limbs = native.live_int_format_limb_cells
        if (produced > native.attempts or text != digits or limbs != 0
                or ingress.registry_size != recipe_count
                or self.registry_size != self.constructions
                or self.constructions != recipe_count + produced + self.division_calls
                or native.source_count != len(self._sources)):
            _reject(_Code.SCOPE_INVALID)
        # With native OPEN between calls, each retained result has exactly one
        # child recipe. Retained text is the sum of coefficient lengths, and
        # ingress charges 1 + coefficient length per successful construction.
        native_recipe_work = produced + text
        if native_recipe_work > native.work_units:
            _reject(_Code.SCOPE_INVALID)
        bounded_registry = None
        if self._registry is not None:
            bounded_registry = OwnedNumericRegistryUsageV1(
                process_capacity=self._registry.capacity,
                reserved_slots=limits["max_registry_entries"],
                work_reserved=self._registry_work,
            )
        return OwnedNumericCapacityV1(
            profile=OwnedNumericProfileV1(**limits, native_confidence_profile=native_profile),
            owner_work=_capacity(limits["max_owner_work_units"], self.work_units),
            owner_registry=_capacity(limits["max_registry_entries"], self.registry_size),
            owner_constructions=self.constructions,
            divisions=_capacity(limits["max_divisions"], self.division_calls),
            recipe_constructions=_capacity(limits["max_recipe_constructions"], recipe_count),
            recipe_work=_capacity(limits["max_recipe_work_units"], ingress.work_units),
            native_attempts=_capacity(native_profile.max_attempts, native.attempts),
            native_work=_capacity(native_profile.max_work_units, native.work_units),
            native_registry=_capacity(native_profile.max_registry_entries, produced),
            native_recipe_constructions=_capacity(native_profile.max_registry_entries, produced),
            native_recipe_work=_capacity(native_profile.max_work_units, native_recipe_work),
            native_live_text=_capacity(native_profile.max_live_text_chars, text),
            native_live_digits=_capacity(native_profile.max_live_digit_cells, digits),
            native_live_limbs=_capacity(native_profile.max_live_int_format_limb_cells, limbs),
            native_live_binary=_capacity(native_profile.max_live_binary_bytes, native.live_binary_bytes),
            native_source_anchors=_capacity(native_profile.max_source_anchors, native.source_count),
            native_retained_int_bits=_capacity(native_profile.max_retained_int_bits, native.retained_int_bits),
            bounded_registry=bounded_registry,
        )

    def _release(self, state: str) -> None:
        if self._registry is not None:
            self._release_bounded(state)
            return
        with _OWNERS_LOCK:
            for key in self._entries:
                if _OWNERS.get(key) is self:
                    del _OWNERS[key]
        self._entries.clear()
        self._clear_local_sources()
        self._state = state

    def _clear_local_sources(self) -> None:
        self._sources.clear()
        self._anchors = None
        self._source_native = None
        self._extractor_statuses = ()
        if self._native is not None:
            self._native.close()
        self._native = self._ingress = None
        self._zero = self._one = None

    def _release_bounded(self, state: str) -> None:
        reservation = self._reservation
        if reservation is not None:
            # Publish a one-way retirement flag before any fallible cleanup.
            reservation.retired = True
        self._state = state
        self._reservation = None
        failed = False
        try:
            try:
                self._local_entries = None
                if reservation is not None:
                    reservation.reclaimable = True
                    self._registry.retire(reservation)
            finally:
                native = self._native
                self._native = None
                self._clear_local_sources()
                if native is not None:
                    native.close()
        except (MemoryError, KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            failed = True
        if failed:
            self._state = "ABORTED"
            _reject(_Code.CONTROLLED_OPERATION_FAILED)

    def close(self) -> None:
        """Invalidate ownership; selection stays fail-closed until context exit."""
        if _execution_owner() != self._owner:
            _reject(_Code.FOREIGN_SCOPE)
        self._check_not_busy()
        self._release("CLOSED")

    def __exit__(self, exc_type, exc, traceback) -> None:
        if _execution_owner() != self._owner or _ACTIVE.get() is not self:
            _reject(_Code.FOREIGN_SCOPE)
        self._check_not_busy()
        state = "ABORTED" if exc_type is not None or self._state == "ABORTED" else "CLOSED"
        if self._registry is None:
            self._release(state)
            self._reset_selection()
        else:
            try:
                self._release(state)
            finally:
                self._reset_selection()

    def _reset_selection(self) -> None:
        if self._token is not None:
            _ACTIVE.reset(self._token)
            self._token = None


__all__ = ("OwnedNumericProfileV1", "OwnedNumericScopeV1", "OwnedNumericErrorV1",
           "OwnedNumericErrorCodeV1", "NumericCapacityV1", "OwnedNumericCapacityV1",
           "OwnedNumericRegistryUsageV1", "configure_owned_numeric_registry_capacity_v1")
