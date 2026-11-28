"""Explicit synthetic reservations for the preliminary non-price rank path."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, fields
from decimal import Decimal
from enum import Enum
from functools import cache, wraps
from math import isfinite
from types import MemberDescriptorType, UnionType
from typing import ClassVar, get_args, get_origin, get_type_hints

from pipeline.proposed import identity_replay_meter_v1 as identity
from pipeline.proposed import provenance_replay_meter_v1 as provenance
from pipeline.proposed.owned_numeric_producer_v1 import (
    OwnedNumericErrorCodeV1,
    OwnedNumericErrorV1,
    OwnedNumericScopeV1,
    current_owned_numeric_scope_v1,
)


class RankingReplayCodeV1(str, Enum):
    INVALID_PROFILE = "INVALID_PROFILE"
    INVALID_SCOPE = "INVALID_SCOPE"
    FOREIGN_SCOPE = "FOREIGN_SCOPE"
    SCOPE_CLOSED = "SCOPE_CLOSED"
    DEPENDENCY_SCOPE_REQUIRED = "DEPENDENCY_SCOPE_REQUIRED"
    INVALID_SHAPE = "INVALID_SHAPE"
    ACTIVE_PATH_CYCLE = "ACTIVE_PATH_CYCLE"
    INVALID_TEXT = "INVALID_TEXT"
    NUMERIC_OWNERSHIP = "NUMERIC_OWNERSHIP"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"


class RankingReplayErrorV1(RuntimeError):
    def __init__(self, code: RankingReplayCodeV1, limit: str | None = None):
        if type(code) is not RankingReplayCodeV1:
            raise TypeError("Invalid ranking replay error code.")
        if code is RankingReplayCodeV1.RESOURCE_LIMIT:
            if type(limit) is not str or limit not in _PROFILE_FIELDS:
                raise TypeError("Invalid ranking replay limit name.")
        elif limit is not None:
            raise TypeError("Only a resource refusal names a ranking limit.")
        self.code = code
        self.limit = limit
        super().__init__(code.value if limit is None else f"{code.value}: {limit}")


@dataclass(frozen=True, slots=True, kw_only=True)
class RankingReplayProfileV1:
    version: ClassVar[str] = "ranking-replay-meter-v1"
    max_depth: int
    max_tuple_arity: int
    max_text_codepoints: int
    max_distance_codepoints: int
    max_int_bits: int
    max_product_bits: int
    max_decimal_digits: int
    max_decimal_exponent: int
    max_dp_live_slots: int
    max_preimage_bytes: int
    max_occurrences: int
    max_candidates: int
    max_tokens: int
    max_spans: int
    max_slice_codepoints: int
    max_dp_cells: int
    max_dp_row_slots: int
    max_displacement_pairs: int
    max_ratio_comparisons: int
    max_sort_comparisons: int
    max_divisions: int
    max_canonical_bytes: int
    max_hash_calls: int
    max_comparison_work: int
    max_records: int
    max_temporary_slots: int
    max_work_units: int


_PROFILE_FIELDS = tuple(item.name for item in fields(RankingReplayProfileV1))
_PER_VALUE = (
    "max_depth", "max_tuple_arity", "max_text_codepoints", "max_distance_codepoints",
    "max_int_bits", "max_product_bits", "max_decimal_digits", "max_decimal_exponent",
    "max_dp_live_slots", "max_preimage_bytes",
)
_ACTIVE: ContextVar[RankingReplayScopeV1 | None] = ContextVar("ranking_replay_meter_v1", default=None)
_Code = RankingReplayCodeV1


@cache
def _layouts():
    from pipeline.proposed import candidate_ranking as ranking, contracts

    upstream, upstream_enums = provenance._layouts()
    records = upstream.copy()
    for kind in (
        contracts.ConfigurationRefV1, ranking.CandidateRankingConfigurationV0,
        ranking.EditSimilarityAuditV0, ranking.SourceOrderDisplacementAuditV0,
        ranking.RankedAlteredCandidateV0, ranking.CandidateRankingBlockV0,
    ):
        hints = get_type_hints(kind)
        layout = []
        for item in fields(kind):
            if item.compare:
                slot = vars(kind)[item.name]
                if type(slot) is not MemberDescriptorType:
                    raise RankingReplayErrorV1(_Code.INVALID_SHAPE)
                hint = ranking._TIE_SHAPE | None if item.name == "tie_identity_payload" else hints[item.name]
                layout.append((slot, hint))
        records[id(kind)] = tuple(layout)
    enums = upstream_enums.copy()
    for kind in (
        contracts.ConfigurationKind, contracts.ConfigurationState,
        ranking.ProvenanceMaterializationStatusV0, ranking.DisplacementAvailabilityV0,
        ranking.CandidateRankingReadinessV0, ranking.CandidateRankingBlockReasonV0,
    ):
        enums[id(kind)] = tuple(kind)
    return records, enums


class RankingReplayScopeV1:
    """Explicit single-use synchronous scope with an independent ledger."""

    def __init__(self, *, profile: RankingReplayProfileV1):
        if type(profile) is not RankingReplayProfileV1:
            raise RankingReplayErrorV1(_Code.INVALID_PROFILE)
        self._limits = {}
        for item in fields(profile):
            value = getattr(profile, item.name, None)
            if type(value) is not int or not 1 <= value < (1 << 31):
                raise RankingReplayErrorV1(_Code.INVALID_PROFILE)
            self._limits[item.name] = value
        if (self._limits["max_depth"] > 32 or self._limits["max_int_bits"] > 64
                or self._limits["max_product_bits"] > 128):
            raise RankingReplayErrorV1(_Code.INVALID_PROFILE)
        self._used = {key: 0 for key in self._limits if key not in _PER_VALUE}
        self._owner = identity._execution_owner()
        self._dependencies = self._numeric_profile = self._token = None
        self._state = "NEW"

    @property
    def state(self) -> str:
        return self._state

    def usage(self) -> dict[str, int]:
        if identity._execution_owner() != self._owner:
            raise RankingReplayErrorV1(_Code.FOREIGN_SCOPE)
        return self._used.copy()

    def __enter__(self) -> RankingReplayScopeV1:
        if identity._execution_owner() != self._owner:
            raise RankingReplayErrorV1(_Code.FOREIGN_SCOPE)
        if self._state != "NEW" or _ACTIVE.get() is not None:
            raise RankingReplayErrorV1(_Code.INVALID_SCOPE)
        try:
            pv, numeric = provenance.selected(), current_owned_numeric_scope_v1()
            if (
                type(pv) is not provenance.ProvenanceReplayScopeV1
                or type(numeric) is not OwnedNumericScopeV1
            ):
                self.reject(_Code.DEPENDENCY_SCOPE_REQUIRED)
            self._numeric_profile = numeric.inspect_capacity_v1().profile
            _layouts()
        except BaseException:
            self._state = "FAILED"
            raise
        self._dependencies = (pv, numeric)
        self._token = _ACTIVE.set(self)
        self._state = "OPEN"
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if identity._execution_owner() != self._owner or _ACTIVE.get() is not self:
            raise RankingReplayErrorV1(_Code.INVALID_SCOPE)
        _ACTIVE.reset(self._token)
        self._dependencies = self._numeric_profile = self._token = None
        self._state = "FAILED" if exc_type or self._state == "FAILED" else "CLOSED"

    def _check(self) -> None:
        if identity._execution_owner() != self._owner:
            raise RankingReplayErrorV1(_Code.FOREIGN_SCOPE)
        if self._state != "OPEN" or _ACTIVE.get() is not self:
            raise RankingReplayErrorV1(_Code.SCOPE_CLOSED)
        try:
            pv, numeric = provenance.selected(), current_owned_numeric_scope_v1()
        except (OwnedNumericErrorV1, provenance.ProvenanceReplayErrorV1, identity.IdentityReplayMeterErrorV1):
            self._state = "FAILED"
            raise
        if pv is not self._dependencies[0] or numeric is not self._dependencies[1]:
            self.reject(_Code.DEPENDENCY_SCOPE_REQUIRED)

    def reject(self, code: RankingReplayCodeV1, limit: str | None = None):
        self._state = "FAILED"
        raise RankingReplayErrorV1(code, limit)

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

    def text_length(self, value: str) -> int:
        if type(value) is not str:
            self.reject(_Code.INVALID_SHAPE)
        length = len(value)
        self.limit("max_text_codepoints", length)
        return length

    def int_width(self, value: int) -> int:
        if type(value) is not int:
            self.reject(_Code.INVALID_SHAPE)
        width = int.bit_length(value)
        self.limit("max_int_bits", width)
        return width

    def owned_weight(self, value: Decimal) -> int:
        self.reserve(max_work_units=1)
        profile = self._numeric_profile
        owned = False
        try:
            self._dependencies[1].require_owned(value)
            owned = True
        except OwnedNumericErrorV1 as exc:
            if exc.code not in (
                OwnedNumericErrorCodeV1.UNREGISTERED_DECIMAL,
                OwnedNumericErrorCodeV1.FOREIGN_SCOPE,
                OwnedNumericErrorCodeV1.UNSUPPORTED_NUMERIC_TYPE,
            ):
                self._state = "FAILED"
                raise
        if not owned:
            self.reject(_Code.NUMERIC_OWNERSHIP)
        self.limit("max_decimal_digits", profile.max_coefficient_digits)
        self.limit("max_decimal_exponent", profile.max_exponent_magnitude)
        return profile.max_coefficient_digits + profile.max_exponent_magnitude.bit_length()

    def walk(self, root: object, hint: object = None, *, canonical: bool = False) -> int:
        """Walk exact trusted field layouts. Charge both aliases and frames."""
        self.reserve(max_work_units=1, max_temporary_slots=7)
        stack = [(root, hint, 0, False)]
        active = []
        weight = size = 0
        records, enums = _layouts()
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
                width = self.int_width(value)
                weight += width
                if canonical:
                    self.reserve(max_work_units=(1 + width) ** 2)
                    magnitude = abs(value)
                    size += 1 + (value < 0)
                    while magnitude >= 10:
                        magnitude //= 10
                        size += 1
            elif not canonical and (value is None or kind is bool):
                pass
            elif not canonical and kind is float:
                if not isfinite(value):
                    self.reject(_Code.INVALID_SHAPE)
                weight += 64
            elif not canonical and kind is Decimal:
                weight += self.owned_weight(value)
            elif not canonical and id(kind) in enums:
                members = enums[id(kind)]
                self.reserve(max_work_units=len(members))
                if not any(value is member for member in members):
                    self.reject(_Code.INVALID_SHAPE)
                weight += len(value.value)
            elif kind is tuple or (not canonical and id(kind) in records):
                arity = len(value) if kind is tuple else len(records[id(kind)])
                if kind is tuple:
                    self.limit("max_tuple_arity", arity)
                self.reserve(max_temporary_slots=6 + 5 * arity, max_work_units=1 + arity)
                active.append(ident)
                stack.append((value, None, depth, True))
                if kind is tuple:
                    if canonical:
                        size += 2 + max(0, arity - 1)
                    if get_origin(expected) is UnionType:
                        expected = next(item for item in get_args(expected) if identity._matches(tuple, item))
                    hints = get_args(expected)
                    repeat = len(hints) == 2 and hints[1] is Ellipsis
                    if hints and not repeat and len(hints) != arity:
                        self.reject(_Code.INVALID_SHAPE)
                    for i in range(arity - 1, -1, -1):
                        stack.append((value[i], hints[0 if repeat else i] if hints else None, depth + 1, False))
                else:
                    for slot, child_hint in reversed(records[id(kind)]):
                        try:
                            child = slot.__get__(value, kind)
                        except AttributeError:
                            self.reject(_Code.INVALID_SHAPE)
                        stack.append((child, child_hint, depth + 1, False))
            else:
                self.reject(_Code.INVALID_SHAPE)
            if canonical:
                self.limit("max_preimage_bytes", size)
        return size if canonical else weight

    def reserve_distance(self, left: str, right: str) -> None:
        n, m = self.text_length(left), self.text_length(right)
        self.limit("max_distance_codepoints", max(n, m))
        width = (max(n, m) + 1).bit_length()
        self.limit("max_int_bits", width)
        cells = n * m
        row = min(n, m) + 1 if cells else 0
        total_slots = (max(n, m) + 1) * row
        scratch = 8 + 7 * cells + (max(n, m) if cells else 0)
        self.limit("max_dp_live_slots", 2 * row)
        comparisons = 2 + n + m + cells * (4 + 4 * width)
        self.reserve(max_dp_cells=cells, max_dp_row_slots=total_slots,
                     max_temporary_slots=total_slots + scratch,
                     max_comparison_work=comparisons,
                     max_work_units=comparisons + cells * (8 + 4 * width) + total_slots)

    def reserve_ratio(self, ln: int, ld: int, rn: int, rd: int) -> None:
        a, b, c, d = (self.int_width(x) for x in (ln, ld, rn, rd))
        if ln < 0 or rn < 0 or ld <= 0 or rd <= 0:
            self.reject(_Code.INVALID_SHAPE)
        self.limit("max_product_bits", max(a + d, c + b))
        work = 2 * (2 + a + b + c + d)
        self.reserve(max_ratio_comparisons=1, max_comparison_work=work,
                     max_temporary_slots=2, max_work_units=work + (a + 1) * (d + 1) + (c + 1) * (b + 1))


def selected() -> RankingReplayScopeV1 | None:
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
    if meter is not None and type(value) is not kind:
        meter.reject(_Code.INVALID_SHAPE)


def exact_union(value, hint) -> None:
    meter = selected()
    if meter is not None and not identity._matches(type(value), hint):
        meter.reject(_Code.INVALID_SHAPE)


def screen(value, hint) -> None:
    meter = selected()
    if meter is not None:
        meter.walk(value, hint)


def reserve(**charges) -> None:
    meter = selected()
    if meter is not None:
        meter.reserve(**charges)


def not_equal(left, right) -> bool:
    meter = selected()
    if meter is not None:
        cost = meter.walk(left) + meter.walk(right)
        meter.reserve(max_comparison_work=cost, max_work_units=cost)
    return left != right


def compare_text(left: str, right: str) -> int:
    meter = selected()
    if meter is not None:
        cost = 2 * (2 + meter.text_length(left) + meter.text_length(right))
        meter.reserve(max_comparison_work=cost, max_work_units=cost)
    return (left > right) - (left < right)


class LinearIndex:
    """Selected exact-key lookup. Source insertion order stays available."""

    def __init__(self):
        self._pairs = []

    def _find(self, key):
        meter = selected()
        meter.walk(key, str | tuple[int, int, int, int])
        for i, (previous, _) in enumerate(self._pairs):
            reserve(max_work_units=1)
            if not not_equal(key, previous):
                return i
        return -1

    def get(self, key, default=None):
        i = self._find(key)
        return default if i < 0 else self._pairs[i][1]

    def __getitem__(self, key):
        i = self._find(key)
        if i < 0:
            raise KeyError("Missing ranking key.")
        return self._pairs[i][1]

    def __contains__(self, key):
        return self._find(key) >= 0

    def __len__(self):
        return len(self._pairs)

    def __setitem__(self, key, value):
        i = self._find(key)
        reserve(max_work_units=1, max_temporary_slots=3)
        if i < 0:
            self._pairs.append((key, value))
        else:
            self._pairs[i] = (key, value)

    def items(self):
        return iter(self._pairs)


def index():
    return {} if selected() is None else LinearIndex()


def unique(values):
    if selected() is None:
        return set(values)
    result = LinearIndex()
    for value in values:
        result[value] = None
    return result


def different_keys(left, right) -> bool:
    if selected() is None:
        return set(left) != set(right)
    a, b = unique(left), unique(right)
    return len(a) != len(b) or any(key not in b for key, _ in a.items())


def sort_selected(values, compare):
    count = len(values)
    pairs = count * (count - 1) // 2
    reserve(max_sort_comparisons=pairs, max_temporary_slots=count, max_work_units=2 * count + 2 * pairs)
    return _insertion_sort(values, compare)


def _insertion_sort(values, compare):
    result = list(values)
    for i in range(1, len(result)):
        item = result[i]
        j = i
        while j and compare(result[j - 1], item) > 0:
            result[j] = result[j - 1]
            j -= 1
        result[j] = item
    return result


def minimum_displacement(support, original):
    meter = selected()
    if meter is not None:
        meter.walk(support, tuple[int, ...])
        meter.walk(original, tuple[int, ...])
        pairs = len(support) * len(original)
        bits = 1 + meter._limits["max_int_bits"]
        cost = pairs * (2 + 2 * bits)
        meter.reserve(max_displacement_pairs=pairs, max_comparison_work=cost,
                      max_work_units=cost + pairs * (3 + bits))
    return min(abs(a - b) for a in support for b in original)


def slice_text(text, start, end):
    meter = selected()
    if meter is not None:
        meter.text_length(text)
        meter.int_width(start)
        meter.int_width(end)
        length = end - start
        meter.reserve(max_slice_codepoints=length, max_temporary_slots=length, max_work_units=length)
    return _slice_text(text, start, end)


def _slice_text(text, start, end):
    return text[start:end]
