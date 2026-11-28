"""Opt-in logical accounting for the synthetic finalization projection."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, fields
from decimal import Decimal
from enum import Enum
from functools import cache, wraps
from math import isfinite
from types import MemberDescriptorType, UnionType
from typing import ClassVar, get_args, get_origin, get_type_hints

from . import identity_replay_meter_v1 as identity
from . import limiting_replay_meter_v1 as limiting
from .contracts import CandidateProvenanceV1, CandidateRecordV1
from .owned_numeric_producer_v1 import (
    OwnedNumericErrorCodeV1,
    OwnedNumericErrorV1,
    current_owned_numeric_scope_v1,
)


class FinalizationReplayCodeV1(str, Enum):
    INVALID_PROFILE = "INVALID_PROFILE"
    INVALID_SCOPE = "INVALID_SCOPE"
    FOREIGN_SCOPE = "FOREIGN_SCOPE"
    SCOPE_CLOSED = "SCOPE_CLOSED"
    LIMITING_SCOPE_REQUIRED = "LIMITING_SCOPE_REQUIRED"
    INVALID_SHAPE = "INVALID_SHAPE"
    ACTIVE_PATH_CYCLE = "ACTIVE_PATH_CYCLE"
    INVALID_NUMERIC_OWNERSHIP = "INVALID_NUMERIC_OWNERSHIP"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"


class FinalizationReplayErrorV1(RuntimeError):
    def __init__(self, code: FinalizationReplayCodeV1, limit: str | None = None):
        if type(code) is not FinalizationReplayCodeV1:
            raise TypeError("Invalid finalization replay error code.")
        if code is _Code.RESOURCE_LIMIT:
            if type(limit) is not str or limit not in _LIMIT_FIELDS:
                raise TypeError("Invalid finalization replay limit name.")
        elif limit is not None:
            raise TypeError("Only a resource refusal names a finalization replay limit.")
        self.code = code
        self.limit = limit
        super().__init__(code.value if limit is None else f"{code.value}: {limit}")


@dataclass(frozen=True, slots=True, kw_only=True)
class FinalizationReplayProfileV1:
    """All limits are explicit and inclusive."""

    version: ClassVar[str] = "finalization-replay-meter-v1"
    max_int_bits: int
    max_text_codepoints: int
    max_depth: int
    max_tuple_arity: int
    max_population: int
    max_candidate_occurrences: int
    max_upstream_replays: int
    max_scan_items: int
    max_coverage_id_slots: int
    max_shared_validations: int
    max_provenance_validations: int
    max_member_occurrences: int
    max_set_probes: int
    max_span_token_pairs: int
    max_uniqueness_pairs: int
    max_occurrences: int
    max_comparison_work: int
    max_records: int
    max_temporary_slots: int
    max_work_units: int


_Code = FinalizationReplayCodeV1
_LIMIT_FIELDS = tuple(item.name for item in fields(FinalizationReplayProfileV1))
_PER_VALUE = _LIMIT_FIELDS[:5]
_ACTIVE: ContextVar[FinalizationReplayScopeV1 | None] = ContextVar(
    "finalization_replay_meter_v1", default=None
)


@cache
def _layouts():
    from . import candidate_finalization as finalization

    # Share the pinned exact field vocabulary, never the upstream ledgers.
    base_records, base_enums = limiting._layouts()
    records, enums = base_records.copy(), base_enums.copy()
    for kind in (
        finalization.BlockedCandidateFinalizationAuditV0,
        finalization.CandidateFinalizationCoverageV0,
    ):
        layout = []
        hints = get_type_hints(kind)
        for item in fields(kind):
            if item.compare:
                slot = vars(kind)[item.name]
                if type(slot) is not MemberDescriptorType:
                    raise FinalizationReplayErrorV1(_Code.INVALID_SHAPE)
                layout.append((slot, hints[item.name]))
        records[id(kind)] = tuple(layout)
    for kind in (
        finalization.CandidateFinalizationReadinessV0,
        finalization.CandidateFinalizationCoverageStatusV0,
    ):
        enums[id(kind)] = tuple(kind)
    return records, enums


class FinalizationReplayScopeV1:
    """A single-use local ledger owned by the creating thread and task."""

    def __init__(self, *, profile: FinalizationReplayProfileV1):
        if type(profile) is not FinalizationReplayProfileV1:
            raise FinalizationReplayErrorV1(_Code.INVALID_PROFILE)
        limits = {name: getattr(profile, name, None) for name in _LIMIT_FIELDS}
        if any(type(limit) is not int or not 1 <= limit < 2**31 for limit in limits.values()):
            raise FinalizationReplayErrorV1(_Code.INVALID_PROFILE)
        if not (
            limits["max_depth"] <= 32
            and limits["max_int_bits"] <= 64
        ):
            raise FinalizationReplayErrorV1(_Code.INVALID_PROFILE)
        self._limits = limits
        self._used = {name: 0 for name in limits if name not in _PER_VALUE}
        self._owner = identity._execution_owner()
        self._state = "NEW"
        self._limiting = self._numeric = self._numeric_profile = self._token = None

    @property
    def state(self) -> str:
        return self._state

    def usage(self) -> dict[str, int]:
        self._check_owner()
        return self._used.copy()

    def _check_owner(self) -> None:
        if identity._execution_owner() != self._owner:
            raise FinalizationReplayErrorV1(_Code.FOREIGN_SCOPE)

    def __enter__(self) -> FinalizationReplayScopeV1:
        self._check_owner()
        if self._state != "NEW" or _ACTIVE.get() is not None:
            raise FinalizationReplayErrorV1(_Code.INVALID_SCOPE)
        try:
            lm01 = limiting.selected()
            if type(lm01) is not limiting.LimitingReplayScopeV1:
                self._reject(_Code.LIMITING_SCOPE_REQUIRED)
            owner = current_owned_numeric_scope_v1()
            profile = owner.inspect_capacity_v1().profile
            _layouts()
        except BaseException:
            self._state = "FAILED"
            raise
        self._limiting, self._numeric, self._numeric_profile = lm01, owner, profile
        self._token = _ACTIVE.set(self)
        self._state = "OPEN"
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._check_owner()
        if _ACTIVE.get() is not self:
            raise FinalizationReplayErrorV1(_Code.INVALID_SCOPE)
        _ACTIVE.reset(self._token)
        self._limiting = self._numeric = self._numeric_profile = self._token = None
        self._state = "FAILED" if exc_type or self._state == "FAILED" else "CLOSED"

    def _check(self) -> None:
        self._check_owner()
        if self._state != "OPEN" or _ACTIVE.get() is not self:
            raise FinalizationReplayErrorV1(_Code.SCOPE_CLOSED)
        try:
            if limiting.selected() is not self._limiting:
                self._reject(_Code.LIMITING_SCOPE_REQUIRED)
        except BaseException:
            self._state = "FAILED"
            raise

    def _reject(self, code: FinalizationReplayCodeV1, limit: str | None = None):
        self._state = "FAILED"
        raise FinalizationReplayErrorV1(code, limit)

    def _cap(self, name: str, amount: int) -> None:
        if amount > self._limits[name]:
            self._reject(_Code.RESOURCE_LIMIT, name)

    def _reserve(self, **charges: int) -> None:
        self._check()
        for name, amount in charges.items():
            if name not in self._used or type(amount) is not int or amount < 0:
                self._reject(_Code.INVALID_PROFILE)
            if amount > self._limits[name] - self._used[name]:
                self._reject(_Code.RESOURCE_LIMIT, name)
        for name, amount in charges.items():
            self._used[name] += amount

    def _exact(self, value, kind) -> None:
        if type(value) is not kind:
            self._reject(_Code.INVALID_SHAPE)

    def _width(self, value: int) -> int:
        self._exact(value, int)
        width = value.bit_length()
        self._cap("max_int_bits", width)
        return width

    def _text(self, value: str) -> int:
        self._exact(value, str)
        size = len(value)
        self._cap("max_text_codepoints", size)
        return size

    def _decimal_weight(self, value: Decimal) -> int:
        owned = False
        try:
            self._numeric.require_owned(value)
            owned = True
        except OwnedNumericErrorV1 as exc:
            if exc.code not in (
                OwnedNumericErrorCodeV1.UNREGISTERED_DECIMAL,
                OwnedNumericErrorCodeV1.FOREIGN_SCOPE,
            ):
                self._state = "FAILED"
                raise
        if not owned:
            self._reject(_Code.INVALID_NUMERIC_OWNERSHIP)
        profile = self._numeric_profile
        return profile.max_coefficient_digits + profile.max_exponent_magnitude.bit_length()

    def _walk(self, root, expected=None) -> int:
        """Admission and comparison weight for an actual, possibly detached operand."""
        records, enums = _layouts()
        active: list[int] = []

        def visit(value, hint, depth):
            self._reserve(max_occurrences=1, max_work_units=1 + depth, max_temporary_slots=1)
            self._cap("max_depth", depth)
            marker = id(value)
            if marker in active:
                self._reject(_Code.ACTIVE_PATH_CYCLE)
            kind = type(value)
            if not identity._matches(kind, hint):
                self._reject(_Code.INVALID_SHAPE)
            if kind is str:
                return 1 + self._text(value)
            if kind is int:
                return 1 + self._width(value)
            if value is None or kind is bool:
                return 1
            if kind is float and isfinite(value):
                return 65
            if kind is Decimal:
                return 1 + self._decimal_weight(value)
            if id(kind) in enums:
                members = enums[id(kind)]
                self._reserve(max_work_units=len(members))
                if not any(value is member for member in members):
                    self._reject(_Code.INVALID_SHAPE)
                return 1 + len(value.value)
            layout = records.get(id(kind))
            if kind is not tuple and layout is None:
                self._reject(_Code.INVALID_SHAPE)
            active.append(marker)
            try:
                if kind is tuple:
                    arity = len(value)
                    self._cap("max_tuple_arity", arity)
                    if get_origin(hint) is UnionType:
                        hint = next(item for item in get_args(hint)
                                    if identity._matches(tuple, item))
                    hints = get_args(hint)
                    repeating = len(hints) == 2 and hints[1] is Ellipsis
                    if hints and not repeating and arity != len(hints):
                        self._reject(_Code.INVALID_SHAPE)
                    self._reserve(max_work_units=arity)
                    return 1 + sum(
                        visit(item, hints[0 if repeating else i] if hints else None, depth + 1)
                        for i, item in enumerate(value)
                    )
                self._reserve(max_work_units=len(layout))
                weight = 1
                for slot, child_hint in layout:
                    try:
                        child = slot.__get__(value, kind)
                    except AttributeError:
                        self._reject(_Code.INVALID_SHAPE)
                    weight += visit(child, child_hint, depth + 1)
                return weight
            finally:
                active.pop()

        return visit(root, expected, 0)


def selected() -> FinalizationReplayScopeV1 | None:
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


def exact(value, kind) -> None:
    meter = selected()
    if meter is not None:
        meter._exact(value, kind)


def screen(value, hint) -> None:
    meter = selected()
    if meter is not None:
        meter._walk(value, hint)


def reserve(**charges) -> None:
    meter = selected()
    if meter is not None:
        meter._reserve(**charges)


def population(*groups: tuple) -> None:
    meter = selected()
    if meter is not None:
        count = 0
        for group in groups:
            meter._exact(group, tuple)
            size = len(group)
            meter._cap("max_tuple_arity", size)
            count += size
        meter._cap("max_population", count)
        meter._width(count)
        meter._reserve(max_candidate_occurrences=count)


def reserve_id_checks(values: tuple[str, ...]) -> None:
    meter = selected()
    if meter is not None:
        meter._exact(values, tuple)
        meter._cap("max_population", len(values))
        size = meter._walk(values, tuple[str, ...])
        meter._reserve(max_scan_items=len(values), max_temporary_slots=size, max_work_units=size)


def reserve_comparison(left, right) -> None:
    meter = selected()
    if meter is not None:
        cost = meter._walk(left) + meter._walk(right)
        meter._reserve(max_comparison_work=cost, max_work_units=cost)


def not_equal(left, right) -> bool:
    reserve_comparison(left, right)
    return left != right


def equal(left, right) -> bool:
    reserve_comparison(left, right)
    return left == right


def has_duplicate_ids(ids: tuple[str, ...]) -> bool:
    meter = selected()
    if meter is None:
        return len(ids) != len(set(ids))
    count = len(ids)
    width = meter._walk(ids, tuple[str, ...]) - 1
    pairs = count * (count - 1) // 2
    cost = max(0, count - 1) * width
    meter._reserve(max_uniqueness_pairs=pairs, max_comparison_work=cost,
                   max_work_units=count + pairs + cost)
    return _has_duplicate_ids_linear(ids)


def _has_duplicate_ids_linear(ids: tuple[str, ...]) -> bool:
    for right, key in enumerate(ids):
        for left in range(right):
            if ids[left] == key:
                return True
    return False

def reserve_sequence(size: int, *, coverage: bool = False) -> None:
    meter = selected()
    if meter is not None:
        meter._cap("max_tuple_arity", size)
        if coverage:
            meter._reserve(max_coverage_id_slots=size, max_scan_items=size,
                           max_temporary_slots=size, max_work_units=size)
        else:
            meter._reserve(max_scan_items=size, max_temporary_slots=size, max_work_units=size)


def _shared_set_cost(count: int, characters: int, longest: int) -> tuple[int, int, int, int]:
    """The approved insertion-only set bound for the pinned 64-bit CPython."""
    capacity = 8 if count < 5 else 1 << (4 * count).bit_length()
    growths = 0 if count < 5 else count
    per_insert = identity._set_probe_bound(capacity)
    probes = count if count <= 1 else count * per_insert
    moves = growths * count * per_insert
    comparisons = 0 if count <= 1 else 2 * probes * (2 + 2 * longest)
    tables = 8 + growths * capacity
    work = (count + 4 * characters + probes + moves + comparisons + tables
            + capacity + growths * (capacity + capacity.bit_length()))
    slots = 2 * (tables + 8 * growths)
    return work, comparisons, slots, probes + moves


def _str_lengths(keys) -> tuple[int, int]:
    characters = longest = 0
    for key in keys:
        size = len(key)
        characters += size
        longest = max(longest, size)
    return characters, longest


@cache
def _candidate_layout():
    layouts, _ = _layouts()
    layout = layouts[id(CandidateRecordV1)]
    return layout, tuple[tuple(hint for _, hint in layout)]


def reserve_candidate_fields(values: tuple, *, construct: bool = False) -> None:
    meter = selected()
    if meter is None:
        return
    _, expected = _candidate_layout()
    weight = meter._walk(values, expected)
    provenance = values[7]
    count = len(provenance)
    meter._reserve(max_work_units=count)
    chars, longest = _str_lengths(member.provenance_id for member in provenance)
    work, comparisons, slots, probes = _shared_set_cost(count, chars, longest)
    # Each member may compare all three header IDs to its own IDs. Price
    # the repeatedly visited header independently from all other text leaves.
    identity_work = 4 * weight + 4 * count * sum(1 + len(values[i]) for i in range(3))
    meter._reserve(max_shared_validations=1, max_member_occurrences=count,
                   max_set_probes=probes, max_comparison_work=comparisons + identity_work,
                   max_scan_items=3 * count, max_records=int(construct),
                   max_temporary_slots=12 * int(construct) + count + slots + weight,
                   max_work_units=24 + 2 * weight + 3 * count + work + identity_work)


def reserve_candidate_record(record: CandidateRecordV1) -> None:
    meter = selected()
    if meter is not None:
        meter._exact(record, CandidateRecordV1)
        layout, _ = _candidate_layout()
        meter._reserve(max_work_units=12, max_temporary_slots=12)
        try:
            values = tuple(slot.__get__(record, CandidateRecordV1)
                           for slot, _ in layout)
        except AttributeError:
            meter._reject(_Code.INVALID_SHAPE)
        reserve_candidate_fields(values)


def reserve_provenance(record: CandidateProvenanceV1) -> None:
    meter = selected()
    if meter is None:
        return
    weight = meter._walk(record, CandidateProvenanceV1)
    tokens, spans = record.source_token_ids, record.source_spans
    t, s = len(tokens), len(spans)
    meter._reserve(max_work_units=t + s)
    chars, longest = _str_lengths(tokens)
    work, comparisons, slots, probes = _shared_set_cost(t, chars, longest)
    # Tuple membership can inspect each declared token for each span.
    span_work = t * sum(2 + longest + len(span.token_id) for span in spans)
    meter._reserve(max_provenance_validations=1, max_member_occurrences=1,
                   max_set_probes=probes, max_span_token_pairs=t * s, max_scan_items=t + s,
                   max_comparison_work=comparisons + span_work + weight,
                   max_temporary_slots=13 + weight + slots + s,
                   max_work_units=24 + 2 * weight + work + span_work + t + s)

