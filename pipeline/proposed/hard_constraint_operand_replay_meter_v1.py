"""Opt-in logical accounting for stored B2 operand reconstruction."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, fields
from decimal import Decimal
import sys
from enum import Enum
from functools import cache, wraps
from math import isfinite
from types import MemberDescriptorType, UnionType
from typing import ClassVar, get_args, get_origin, get_type_hints

from . import identity_replay_meter_v1 as identity
from pipeline import contracts as b2
from . import finalization_replay_meter_v1 as finalization
from . import hard_constraint_context_replay_meter_v1 as context
from .contracts import CandidateRecordV1
from .owned_numeric_producer_v1 import (
    OwnedNumericErrorCodeV1,
    OwnedNumericErrorV1,
    current_owned_numeric_scope_v1,
)


class HardConstraintOperandReplayCodeV1(str, Enum):
    INVALID_PROFILE = "INVALID_PROFILE"
    INVALID_SCOPE = "INVALID_SCOPE"
    FOREIGN_SCOPE = "FOREIGN_SCOPE"
    SCOPE_CLOSED = "SCOPE_CLOSED"
    CONTEXT_SCOPE_REQUIRED = "CONTEXT_SCOPE_REQUIRED"
    UNSUPPORTED_RUNTIME = "UNSUPPORTED_RUNTIME"
    UNSUPPORTED_NUMBER = "UNSUPPORTED_NUMBER"
    NONFINITE_NUMBER = "NONFINITE_NUMBER"
    INVALID_SHAPE = "INVALID_SHAPE"
    ACTIVE_PATH_CYCLE = "ACTIVE_PATH_CYCLE"
    INVALID_NUMERIC_OWNERSHIP = "INVALID_NUMERIC_OWNERSHIP"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"


class HardConstraintOperandReplayErrorV1(RuntimeError):
    def __init__(self, code: HardConstraintOperandReplayCodeV1, limit: str | None = None):
        if type(code) is not HardConstraintOperandReplayCodeV1:
            raise TypeError("Invalid hard-constraint operand replay error code.")
        if code is _Code.RESOURCE_LIMIT:
            if type(limit) is not str or limit not in _LIMIT_FIELDS:
                raise TypeError("Invalid hard-constraint operand replay limit name.")
        elif limit is not None:
            raise TypeError("Only a resource refusal names a hard-constraint operand replay limit.")
        self.code = code
        self.limit = limit
        super().__init__(code.value if limit is None else f"{code.value}: {limit}")


@dataclass(frozen=True, slots=True, kw_only=True)
class HardConstraintOperandReplayProfileV1:
    """All limits are explicit and inclusive."""

    version: ClassVar[str] = "hard-constraint-operand-replay-meter-v1"
    max_int_bits: int
    max_numeric_int_bits: int
    max_text_codepoints: int
    max_depth: int
    max_tuple_arity: int
    max_population: int
    max_candidate_occurrences: int
    max_upstream_replays: int
    max_scan_items: int
    max_receipt_rows: int
    max_receipt_fields: int
    max_receipt_tokens: int
    max_polygon_points: int
    max_field_observations: int
    max_token_observations: int
    max_fingerprints: int
    max_fingerprint_chars: int
    max_fingerprint_bytes: int
    max_format_work: int
    max_validations: int
    max_operand_validations: int
    max_shared_validations: int
    max_member_occurrences: int
    max_set_probes: int
    max_uniqueness_pairs: int
    max_occurrences: int
    max_comparison_work: int
    max_records: int
    max_temporary_slots: int
    max_work_units: int


_Code = HardConstraintOperandReplayCodeV1
_LIMIT_FIELDS = tuple(item.name for item in fields(HardConstraintOperandReplayProfileV1))
_PER_VALUE = _LIMIT_FIELDS[:6]
_ACTIVE: ContextVar[HardConstraintOperandReplayScopeV1 | None] = ContextVar(
    "hard_constraint_operand_replay_meter_v1", default=None
)


@cache
def _layouts():
    # Share the pinned exact field vocabulary, never the upstream ledgers.
    from . import hard_constraint_operands as operands

    base_records, base_enums = context._layouts()
    records, enums = base_records.copy(), base_enums.copy()
    for kind in (
        operands._StructuredFieldObservationV0, operands._SourceTokenObservationV0,
        operands.OperandEvidenceV0, operands.ItemRowOperandEvidenceV0,
        operands.CandidateSubstitutionPositionV0, operands.CandidateOperandAuditV0,
    ):
        layout = []
        hints = get_type_hints(kind)
        for item in fields(kind):
            if item.compare:
                slot = vars(kind)[item.name]
                if type(slot) is not MemberDescriptorType:
                    raise HardConstraintOperandReplayErrorV1(_Code.INVALID_SHAPE)
                hint = hints[item.name]
                if kind is operands._StructuredFieldObservationV0 and item.name == "confidence":
                    hint = int | float | None
                layout.append((slot, hint))
        records[id(kind)] = tuple(layout)
    for kind in (
        operands.OperandAvailabilityV0, operands.RelationshipAvailabilityV0,
        operands.CandidateSubstitutionScopeV0,
    ):
        enums[id(kind)] = tuple(kind)
    return records, enums


class HardConstraintOperandReplayScopeV1:
    """A single-use local ledger owned by the creating thread and task."""

    def __init__(self, *, profile: HardConstraintOperandReplayProfileV1):
        if type(profile) is not HardConstraintOperandReplayProfileV1:
            raise HardConstraintOperandReplayErrorV1(_Code.INVALID_PROFILE)
        limits = {name: getattr(profile, name, None) for name in _LIMIT_FIELDS}
        if any(type(limit) is not int or not 1 <= limit < 2**31 for limit in limits.values()):
            raise HardConstraintOperandReplayErrorV1(_Code.INVALID_PROFILE)
        if not (
            limits["max_depth"] <= 32
            and limits["max_numeric_int_bits"] <= limits["max_int_bits"] <= 64
        ):
            raise HardConstraintOperandReplayErrorV1(_Code.INVALID_PROFILE)
        self._limits = limits
        self._used = {name: 0 for name in limits if name not in _PER_VALUE}
        self._owner = identity._execution_owner()
        self._state = "NEW"
        self._context = self._numeric = self._numeric_profile = self._token = None

    @property
    def state(self) -> str:
        return self._state

    def usage(self) -> dict[str, int]:
        self._check_owner()
        return self._used.copy()

    def _check_owner(self) -> None:
        if identity._execution_owner() != self._owner:
            raise HardConstraintOperandReplayErrorV1(_Code.FOREIGN_SCOPE)

    def __enter__(self) -> HardConstraintOperandReplayScopeV1:
        self._check_owner()
        if self._state != "NEW" or _ACTIVE.get() is not None:
            raise HardConstraintOperandReplayErrorV1(_Code.INVALID_SCOPE)
        try:
            hc01 = context.selected()
            if type(hc01) is not context.HardConstraintContextReplayScopeV1:
                self._reject(_Code.CONTEXT_SCOPE_REQUIRED)
            _require_runtime()
            owner = current_owned_numeric_scope_v1()
            profile = owner.inspect_capacity_v1().profile
            _layouts()
        except BaseException:
            self._state = "FAILED"
            raise
        self._context, self._numeric, self._numeric_profile = hc01, owner, profile
        self._token = _ACTIVE.set(self)
        self._state = "OPEN"
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._check_owner()
        if _ACTIVE.get() is not self:
            raise HardConstraintOperandReplayErrorV1(_Code.INVALID_SCOPE)
        _ACTIVE.reset(self._token)
        self._context = self._numeric = self._numeric_profile = self._token = None
        self._state = "FAILED" if exc_type or self._state == "FAILED" else "CLOSED"

    def _check(self) -> None:
        self._check_owner()
        if self._state != "OPEN" or _ACTIVE.get() is not self:
            raise HardConstraintOperandReplayErrorV1(_Code.SCOPE_CLOSED)
        try:
            if context.selected() is not self._context:
                self._reject(_Code.CONTEXT_SCOPE_REQUIRED)
        except BaseException:
            self._state = "FAILED"
            raise

    def _reject(self, code: HardConstraintOperandReplayCodeV1, limit: str | None = None):
        self._state = "FAILED"
        raise HardConstraintOperandReplayErrorV1(code, limit)

    def _cap(self, name: str, amount: int) -> None:
        if amount > self._limits[name]:
            self._reject(_Code.RESOURCE_LIMIT, name)

    def _reserve(self, **charges: int) -> None:
        self._require_capacity(**charges)
        for name, amount in charges.items():
            self._used[name] += amount

    def _require_capacity(self, **charges: int) -> None:
        self._check()
        for name, amount in charges.items():
            if name not in self._used or type(amount) is not int or amount < 0:
                self._reject(_Code.INVALID_PROFILE)
            if amount > self._limits[name] - self._used[name]:
                self._reject(_Code.RESOURCE_LIMIT, name)

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


def selected() -> HardConstraintOperandReplayScopeV1 | None:
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

def sequence(size: int) -> None:
    meter = selected()
    if meter is not None:
        meter._cap("max_tuple_arity", size)
        meter._reserve(max_scan_items=size, max_temporary_slots=size, max_work_units=size)


def scan(size: int) -> None:
    reserve(max_scan_items=size, max_work_units=size)


def _keys(keys):
    # Called only on exact fields of a screened operand. No key is hashed here.
    chars = longest = 0
    for key in keys:
        length = len(key)
        chars += length
        longest = max(longest, length)
    return chars, longest


def _validator(weight: int, *, scans: int = 0, slots: int = 0,
               comparison: int = 0, shared: bool = False) -> None:
    reserve(max_validations=1, max_shared_validations=int(shared), max_scan_items=scans,
            max_comparison_work=4 * weight + comparison,
            max_temporary_slots=32 + 2 * weight + slots,
            max_work_units=64 + 8 * weight + scans + comparison)


def _set(keys, count: int, *, repeats: int = 1) -> None:
    if not repeats:
        return
    scan(count)
    chars, longest = _keys(keys)
    work, compare, slots, probes = finalization._shared_set_cost(count, chars, longest)
    reserve(max_set_probes=repeats * probes, max_comparison_work=repeats * compare,
            max_temporary_slots=repeats * slots, max_work_units=repeats * work)

def _require_runtime() -> None:
    info = sys.float_info
    if (sys.version != identity._C0_RUNTIME or sys.float_repr_style != "short"
            or float.__getformat__("double") != "IEEE, little-endian"
            or (info.radix, info.mant_dig, info.min_exp, info.max_exp) != (2, 53, -1021, 1024)):
        raise HardConstraintOperandReplayErrorV1(_Code.UNSUPPORTED_RUNTIME)


def reserve_fingerprint(value: object) -> None:
    meter = selected()
    if meter is None:
        return
    kind = type(value)
    if kind is int:
        width = meter._width(value)
        meter._cap("max_numeric_int_bits", width)
        # 2**3 < 10. Add a possible sign to the digit bound.
        literal = 1 + max(1, (width + 2) // 3)
        formatting = (1 + width) ** 2 + literal
        type_chars = 3
    elif kind is float:
        if not isfinite(value):
            meter._reject(_Code.NONFINITE_NUMBER)
        literal = 24
        # Cover binary exponent range, significand width, digit generation
        # and final ASCII emission in the logical formatter schedule.
        formatting = 1074 + 1024 + 17 * 53 + literal
        type_chars = 5
    else:
        meter._reject(_Code.UNSUPPORTED_NUMBER)
    text = 8 + type_chars + literal  # "builtins" and the exact type name
    comparison = 2 * (4 + text)  # tuple and three leaves, twice
    meter._reserve(max_fingerprints=1, max_fingerprint_chars=text,
                   max_fingerprint_bytes=text, max_format_work=formatting,
                   max_temporary_slots=3 + text,
                   max_comparison_work=comparison,
                   max_work_units=formatting + 3 + text + comparison)


def admit(value, kind) -> None:
    meter = selected()
    if meter is not None:
        meter._walk(value, kind)


def admit_items(values: tuple, kind) -> int:
    meter = selected()
    if meter is None:
        return len(values)
    meter._exact(values, tuple)
    count = len(values)
    meter._cap("max_tuple_arity", count)
    scan(count)
    for value in values:
        meter._exact(value, kind)
    return count


def construct(slots: int) -> None:
    reserve(max_records=1, max_temporary_slots=slots, max_work_units=slots)


def reserve_field_observation(field) -> None:
    meter = selected()
    if meter is not None:
        meter._walk(field, b2.StructuredField)
        meter._reserve(max_field_observations=1, max_records=1,
                       max_temporary_slots=10, max_work_units=10)


def reserve_token_observation(token) -> None:
    meter = selected()
    if meter is not None:
        meter._walk(token, b2.OcrSourceToken)
        points = len(token.polygon)
        meter._reserve(max_token_observations=1, max_polygon_points=points,
                       max_records=1, max_scan_items=points,
                       max_temporary_slots=5 + 3 * points, max_work_units=5 + 3 * points)


def receipt_population(output) -> None:
    meter = selected()
    if meter is not None:
        meter._exact(output, b2.ReceiptOutput)
        meter._exact(output.items, tuple)
        rows = len(output.items)
        meter._reserve(max_receipt_rows=rows, max_receipt_fields=3 + 4 * rows)


def source_token_population(tokens) -> None:
    meter = selected()
    if meter is not None:
        meter._exact(tokens, tuple)
        meter._reserve(max_receipt_tokens=len(tokens))
        sequence(len(tokens))


def validate_field(record) -> None:
    meter = selected()
    if meter is not None:
        weight = meter._walk(record, b2.StructuredField)
        _set(record.source_token_ids, len(record.source_token_ids))
        _validator(weight)
    record.__post_init__()


def validate_row(record) -> None:
    meter = selected()
    if meter is not None:
        weight = meter._walk(record, b2.ReceiptItemRow)
        _validator(weight)
    record.__post_init__()


def validate_candidate(record) -> None:
    meter = selected()
    if meter is not None:
        weight = meter._walk(record, CandidateRecordV1)
        count = len(record.provenance)
        reserve(max_member_occurrences=count)
        _set((member.provenance_id for member in record.provenance), count)
        repeated = 4 * count * sum(
            1 + len(key) for key in (record.candidate_id, record.receipt_id, record.field_id)
        )
        _validator(weight, scans=3 * count, slots=count, comparison=repeated, shared=True)
    record.__post_init__()

