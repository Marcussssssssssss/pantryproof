"""Explicit provenance-only reservations for the synthetic replay route."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, fields
from decimal import Decimal
from enum import Enum
from functools import cache, wraps
from math import isfinite
import sys
from types import MemberDescriptorType, UnionType
from typing import ClassVar, get_args, get_origin, get_type_hints

from pipeline.proposed import identity_replay_meter_v1 as identity
from pipeline.proposed.owned_numeric_producer_v1 import (
    OwnedNumericErrorV1, current_owned_numeric_scope_v1,
)


class ProvenanceReplayCodeV1(str, Enum):
    INVALID_PROFILE = "INVALID_PROFILE"
    INVALID_SCOPE = "INVALID_SCOPE"
    FOREIGN_SCOPE = "FOREIGN_SCOPE"
    SCOPE_CLOSED = "SCOPE_CLOSED"
    IDENTITY_SCOPE_REQUIRED = "IDENTITY_SCOPE_REQUIRED"
    INVALID_SHAPE = "INVALID_SHAPE"
    ACTIVE_PATH_CYCLE = "ACTIVE_PATH_CYCLE"
    INVALID_TEXT = "INVALID_TEXT"
    NUMERIC_OWNERSHIP = "NUMERIC_OWNERSHIP"
    UNSUPPORTED_RUNTIME = "UNSUPPORTED_RUNTIME"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"


class ProvenanceReplayErrorV1(RuntimeError):
    def __init__(self, code: ProvenanceReplayCodeV1, limit: str | None = None):
        self.code = code
        self.limit = limit
        super().__init__(code.value if limit is None else f"{code.value}: {limit}")


@dataclass(frozen=True, slots=True, kw_only=True)
class ProvenanceReplayProfileV1:
    version: ClassVar[str] = "provenance-replay-meter-v1"
    max_depth: int
    max_tuple_arity: int
    max_text_codepoints: int
    max_int_bits: int
    max_decimal_digits: int
    max_decimal_exponent: int
    max_occurrences: int
    max_tokens: int
    max_groups: int
    max_contributions: int
    max_spans: int
    max_slice_codepoints: int
    max_preimage_bytes: int
    max_canonical_bytes: int
    max_hash_calls: int
    max_comparison_work: int
    max_sort_comparisons: int
    max_records: int
    max_temporary_slots: int
    max_work_units: int


_PER_VALUE = (
    "max_depth", "max_tuple_arity", "max_text_codepoints", "max_int_bits",
    "max_decimal_digits", "max_decimal_exponent", "max_preimage_bytes",
)
_ACTIVE: ContextVar[ProvenanceReplayScopeV1 | None] = ContextVar(
    "provenance_replay_meter_v1", default=None,
)
_Code = ProvenanceReplayCodeV1
_MISSING = object()


@cache
def _layouts():
    from pipeline.proposed import candidate_provenance as provenance

    # Copy the fixed accepted schema, never the identity meter's ledger.
    base_records, base_enums = identity._shapes()
    records = base_records.copy()
    for kind in (
        provenance.ProvenanceBlockingRecordV0, provenance.ProvenanceMemberProjectionV0,
        provenance.AlteredCandidateProvenanceMaterializationV0,
        provenance.BlockedAlteredCandidateProvenanceV0,
    ):
        hints = get_type_hints(kind)
        record = []
        for field in fields(kind):
            if field.compare:
                slot = vars(kind)[field.name]
                if type(slot) is not MemberDescriptorType:
                    raise ProvenanceReplayErrorV1(_Code.INVALID_SHAPE)
                hint = None if field.name == "identity_payload" else hints[field.name]
                record.append((slot, hint))
        records[id(kind)] = tuple(record)
    enums = base_enums.copy()
    enums[id(provenance.ProvenanceBlockingReasonV0)] = tuple(provenance.ProvenanceBlockingReasonV0)
    return records, enums


class ProvenanceReplayScopeV1:
    """One explicit synchronous invocation. Requires a live ID02 scope."""

    def __init__(self, *, profile: ProvenanceReplayProfileV1):
        if type(profile) is not ProvenanceReplayProfileV1:
            raise ProvenanceReplayErrorV1(_Code.INVALID_PROFILE)
        self._limits = {}
        for item in fields(profile):
            value = getattr(profile, item.name, None)
            if type(value) is not int or not 1 <= value < (1 << 31):
                raise ProvenanceReplayErrorV1(_Code.INVALID_PROFILE)
            self._limits[item.name] = value
        if self._limits["max_depth"] > 32 or self._limits["max_int_bits"] > 64:
            raise ProvenanceReplayErrorV1(_Code.INVALID_PROFILE)
        self._used = {key: 0 for key in self._limits if key not in _PER_VALUE}
        self._owner = identity._execution_owner()
        self._identity = self._token = None
        self._state = "NEW"

    @property
    def state(self) -> str:
        return self._state

    def usage(self) -> dict[str, int]:
        if identity._execution_owner() != self._owner:
            raise ProvenanceReplayErrorV1(_Code.FOREIGN_SCOPE)
        return self._used.copy()

    def __enter__(self) -> ProvenanceReplayScopeV1:
        if identity._execution_owner() != self._owner:
            raise ProvenanceReplayErrorV1(_Code.FOREIGN_SCOPE)
        if self._state != "NEW" or _ACTIVE.get() is not None:
            raise ProvenanceReplayErrorV1(_Code.INVALID_SCOPE)
        self._identity = identity.selected_meter()
        if type(self._identity) is not identity.IdentityReplayMeterScopeV1:
            self.reject(_Code.IDENTITY_SCOPE_REQUIRED)
        if (sys.implementation.name != "cpython" or sys.version != identity._C0_RUNTIME
                or sys.maxsize != (1 << 63) - 1 or not sys._is_gil_enabled()
                or (sys.hash_info.width, sys.hash_info.algorithm, sys.hash_info.cutoff)
                != (64, "siphash13", 0)):
            self.reject(_Code.UNSUPPORTED_RUNTIME)
        _layouts()
        self._token = _ACTIVE.set(self)
        self._state = "OPEN"
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if identity._execution_owner() != self._owner or _ACTIVE.get() is not self:
            raise ProvenanceReplayErrorV1(_Code.INVALID_SCOPE)
        _ACTIVE.reset(self._token)
        self._identity = self._token = None
        self._state = "FAILED" if exc_type or self._state == "FAILED" else "CLOSED"

    def _check(self) -> None:
        if identity._execution_owner() != self._owner:
            raise ProvenanceReplayErrorV1(_Code.FOREIGN_SCOPE)
        if self._state != "OPEN" or _ACTIVE.get() is not self:
            raise ProvenanceReplayErrorV1(_Code.SCOPE_CLOSED)
        try:
            active = identity.selected_meter()
        except identity.IdentityReplayMeterErrorV1:
            self._state = "FAILED"
            raise
        if active is not self._identity:
            self.reject(_Code.IDENTITY_SCOPE_REQUIRED)

    def reject(self, code: ProvenanceReplayCodeV1, limit: str | None = None):
        self._state = "FAILED"
        raise ProvenanceReplayErrorV1(code, limit)

    def reserve(self, **charges: int) -> None:
        self._check()
        for name, amount in charges.items():
            if name not in self._used or type(amount) is not int or amount < 0:
                self.reject(_Code.INVALID_PROFILE)
            if amount > self._limits[name] - self._used[name]:
                self.reject(_Code.RESOURCE_LIMIT, name)
        for name, amount in charges.items():
            self._used[name] += amount

    def limit(self, name: str, amount: int) -> None:
        if amount > self._limits[name]:
            self.reject(_Code.RESOURCE_LIMIT, name)

    def _owned_weight(self, value: Decimal) -> int:
        numeric_profile = None
        try:
            owner = current_owned_numeric_scope_v1()
            if owner is not None:
                owner.require_owned(value)
                numeric_profile = owner.inspect_capacity_v1().profile
        except OwnedNumericErrorV1:
            pass
        if numeric_profile is None:
            self.reject(_Code.NUMERIC_OWNERSHIP)
        self.limit("max_decimal_digits", numeric_profile.max_coefficient_digits)
        self.limit("max_decimal_exponent", numeric_profile.max_exponent_magnitude)
        return numeric_profile.max_coefficient_digits + numeric_profile.max_exponent_magnitude.bit_length()

    def text_length(self, value: str) -> int:
        if type(value) is not str:
            self.reject(_Code.INVALID_SHAPE)
        size = len(value)
        self.limit("max_text_codepoints", size)
        return size

    def walk(self, root: object, hint: object = None, *, canonical: bool = False) -> int:
        """Charge a closed storage walk and return weight or exact JSON bytes."""
        self.reserve(max_work_units=1, max_temporary_slots=7)
        stack = [(root, hint, 0, False)]
        active = []
        weight = size = 0
        layouts, enums = _layouts()
        while stack:
            value, expected, depth, leave = stack.pop()
            if leave:
                active.pop()
                continue
            self.reserve(max_occurrences=1, max_work_units=1 + len(active))
            ident = id(value)
            if ident in active:
                self.reject(_Code.ACTIVE_PATH_CYCLE)
            self.limit("max_depth", depth)
            kind = type(value)
            if not identity._matches(kind, expected):
                self.reject(_Code.INVALID_SHAPE)
            weight += 1
            if kind is str:
                length = self.text_length(value)
                weight += length
                if canonical:
                    self.reserve(max_work_units=length)
                    size += 2
                    for char in value:
                        width = identity._escaped_width(char)
                        if not width:
                            self.reject(_Code.INVALID_TEXT)
                        size += width
            elif kind is int:
                width = int.bit_length(value)
                self.limit("max_int_bits", width)
                weight += width
                if canonical:
                    # Count digits by bounded division, with no string creation.
                    self.reserve(max_work_units=(1 + width) ** 2)
                    magnitude = abs(value)
                    size += 1 + (value < 0)
                    while magnitude >= 10:
                        magnitude //= 10
                        size += 1
            elif value is None:
                size += 4
            elif not canonical and kind is bool:
                pass
            elif not canonical and kind is float:
                if not isfinite(value):
                    self.reject(_Code.INVALID_SHAPE)
                weight += 64
            elif not canonical and kind is Decimal:
                self.reserve(max_work_units=1)
                weight += self._owned_weight(value)
            elif not canonical and id(kind) in enums:
                members = enums[id(kind)]
                self.reserve(max_work_units=len(members))
                if not any(value is member for member in members):
                    self.reject(_Code.INVALID_SHAPE)
                weight += len(value.value)
            elif kind is tuple or (not canonical and id(kind) in layouts):
                arity = len(value) if kind is tuple else len(layouts[id(kind)])
                if kind is tuple:
                    self.limit("max_tuple_arity", arity)
                self.reserve(max_work_units=1 + arity, max_temporary_slots=6 + 5 * arity)
                active.append(ident)
                stack.append((value, None, depth, True))
                if kind is tuple:
                    if canonical:
                        size += 2 + max(0, arity - 1)
                    if get_origin(expected) is UnionType:
                        expected = next(item for item in get_args(expected) if identity._matches(tuple, item))
                    hints = get_args(expected)
                    repeated = len(hints) == 2 and hints[1] is Ellipsis
                    if hints and not repeated and arity != len(hints):
                        self.reject(_Code.INVALID_SHAPE)
                    for index in range(arity - 1, -1, -1):
                        child_hint = hints[0 if repeated else index] if hints else None
                        stack.append((value[index], child_hint, depth + 1, False))
                else:
                    for slot, child_hint in reversed(layouts[id(kind)]):
                        try:
                            child = slot.__get__(value, kind)
                        except AttributeError:
                            child = _MISSING
                        if child is _MISSING:
                            self.reject(_Code.INVALID_SHAPE)
                        stack.append((child, child_hint, depth + 1, False))
            else:
                self.reject(_Code.INVALID_SHAPE)
            if canonical:
                self.limit("max_preimage_bytes", size)
        return size if canonical else weight


def selected() -> ProvenanceReplayScopeV1 | None:
    meter = _ACTIVE.get()
    if meter is not None:
        meter._check()
    return meter


def operation(function):
    @wraps(function)
    def invoke(*args, **kwargs):
        meter = selected()
        if meter is None:
            return function(*args, **kwargs)
        try:
            return function(*args, **kwargs)
        except BaseException:
            meter._state = "FAILED"
            raise
    return invoke


def reserve(**charges: int) -> None:
    meter = selected()
    if meter is not None:
        meter.reserve(**charges)


def screen(value: object, expected: object) -> None:
    meter = selected()
    if meter is not None:
        meter.walk(value, expected)


def exact(value: object, kind: type) -> None:
    meter = selected()
    if meter is not None and type(value) is not kind:
        meter.reject(_Code.INVALID_SHAPE)


def not_equal(left: object, right: object) -> bool:
    meter = selected()
    if meter is not None:
        charge = meter.walk(left) + meter.walk(right)
        meter.reserve(max_comparison_work=charge, max_work_units=charge)
    return left != right


class LinearKeys:
    """Insertion-order table over admitted exact strings for selected work."""

    def __init__(self):
        self._pairs = []

    def _find(self, key: str) -> int:
        meter = selected()
        length = meter.text_length(key)
        for i, (existing, _) in enumerate(self._pairs):
            cost = 2 + length + len(existing)
            meter.reserve(max_comparison_work=cost, max_work_units=cost + 1)
            if key == existing:
                return i
        return -1

    def get(self, key, default=None):
        index = self._find(key)
        return default if index < 0 else self._pairs[index][1]

    def __contains__(self, key):
        return self._find(key) >= 0

    def __len__(self):
        return len(self._pairs)

    def __setitem__(self, key, value):
        index = self._find(key)
        reserve(max_temporary_slots=3, max_work_units=1)
        pair = (key, value)
        if index < 0:
            self._pairs.append(pair)
        else:
            self._pairs[index] = pair

    def setdefault(self, key, value):
        index = self._find(key)
        if index >= 0:
            return self._pairs[index][1]
        reserve(max_temporary_slots=3, max_work_units=1)
        self._pairs.append((key, value))
        return value

    def items(self):
        return iter(self._pairs)


def key_table():
    return {} if selected() is None else LinearKeys()


def unique_keys(values):
    if selected() is None:
        return set(values)
    keys = LinearKeys()
    for value in values:
        keys[value] = None
    return keys


def different_keys(left, right) -> bool:
    if selected() is None:
        return set(left) != set(right)
    a, b = unique_keys(left), unique_keys(right)
    return len(a) != len(b) or any(key not in b for key, _ in a.items())


def first_keys(values) -> tuple[str, ...]:
    if selected() is None:
        return tuple(dict.fromkeys(values))
    keys = unique_keys(values)
    reserve(max_temporary_slots=len(keys), max_work_units=len(keys))
    return tuple(key for key, _ in keys.items())


def _stable_key_sort(items, keys) -> tuple:
    # Move only strictly greater keys to preserve original order on ties.
    for i in range(1, len(items)):
        item, key = items[i], keys[i]
        j = i
        while j and keys[j - 1] > key:
            items[j], keys[j] = items[j - 1], keys[j - 1]
            j -= 1
        items[j], keys[j] = item, key
    return tuple(items)


def sort_members(members, key) -> tuple:
    meter = selected()
    if meter is None:
        return tuple(sorted(members, key=key))
    exact(members, tuple)
    count = len(members)
    meter.limit("max_tuple_arity", count)
    meter.reserve(max_temporary_slots=5 * count, max_work_units=3 * count)
    keys = []
    longest = 0
    for item in members:
        order_key = key(item)
        priority, text = order_key
        if type(priority) is not int:
            meter.reject(_Code.INVALID_SHAPE)
        meter.limit("max_int_bits", int.bit_length(priority))
        longest = max(longest, meter.text_length(text))
        keys.append(order_key)
    pairs = count * (count - 1) // 2
    # Tuple ordering can check equality and then order on the deciding field.
    work = pairs * (6 + 4 * longest + 4 * meter._limits["max_int_bits"])
    meter.reserve(max_sort_comparisons=pairs, max_comparison_work=work,
                  max_work_units=work + 2 * pairs + 2 * count)
    return _stable_key_sort(list(members), keys)


def slice_span(original: str, start: int, end: int) -> str:
    meter = selected()
    if meter is not None:
        # The caller checks half-open bounds using exact admitted offsets.
        length = end - start
        meter.reserve(max_slice_codepoints=length, max_temporary_slots=length,
                      max_work_units=length)
    return _slice_span(original, start, end)


def _slice_span(original: str, start: int, end: int) -> str:
    return original[start:end]


def reserve_shared_provenance(
    text_fields: tuple[str, ...], token_ids: tuple[str, ...], spans: tuple,
) -> None:
    """Prepay the unchanged shared CandidateProvenanceV1 constructor."""
    meter = selected()
    if meter is None:
        return
    meter.reserve(max_work_units=len(text_fields) + len(token_ids) + len(spans))
    text = sum(meter.text_length(item) for item in text_fields)
    chars = longest = 0
    for item in token_ids:
        size = meter.text_length(item)
        chars += size
        longest = max(longest, size)
    count = len(token_ids)
    # Insertion-only CPython set. Reserve the largest possible table at
    # every growth and at most count growths, including resize scratch.
    capacity = 8 if count < 5 else 1 << (4 * count).bit_length()
    growths = 0 if count < 5 else count
    probes = count if count <= 1 else count * identity._set_probe_bound(capacity)
    rebuild = growths * (capacity + capacity.bit_length() + count * identity._set_probe_bound(capacity))
    table = 8 + growths * capacity
    comparisons = 0 if count <= 1 else 2 * probes * (2 + 2 * longest)
    comparisons += sum(
        count * (2 + longest + meter.text_length(span.token_id)) for span in spans
    )
    meter.reserve(
        max_comparison_work=comparisons,
        max_temporary_slots=13 + text + len(spans) + 2 * (table + 8 * growths),
        max_work_units=(24 + 2 * text + count + 4 * chars + probes + rebuild
                        + table + capacity + len(spans) + comparisons),
    )
