"""Independent logical-work reservations for purchase-date feature construction."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, fields
from decimal import Decimal
from enum import Enum
from functools import cache, wraps
from math import isfinite

from pipeline.contracts import OcrSourceToken, StructuredField

from . import feature_readiness_replay_meter_v1 as fr
from . import hard_constraint_operand_replay_meter_v1 as op
from . import hard_constraint_v2_replay_meter_v1 as v2
from .identity_replay_meter_v1 import _execution_owner
from .owned_numeric_producer_v1 import OwnedNumericScopeV1, current_owned_numeric_scope_v1


class FeatureConstructionReplayCodeV1(str, Enum):
    INVALID_PROFILE = "INVALID_PROFILE"
    INVALID_SCOPE = "INVALID_SCOPE"
    FOREIGN_SCOPE = "FOREIGN_SCOPE"
    OPERAND_SCOPE_REQUIRED = "OPERAND_SCOPE_REQUIRED"
    READINESS_SCOPE_REQUIRED = "READINESS_SCOPE_REQUIRED"
    V2_SCOPE_REQUIRED = "V2_SCOPE_REQUIRED"
    NUMERIC_SCOPE_REQUIRED = "NUMERIC_SCOPE_REQUIRED"
    INVALID_SHAPE = "INVALID_SHAPE"
    ACTIVE_PATH_CYCLE = "ACTIVE_PATH_CYCLE"
    UNSUPPORTED_NUMBER = "UNSUPPORTED_NUMBER"
    INVALID_SOURCE_BINDING = "INVALID_SOURCE_BINDING"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"


class FeatureConstructionReplayErrorV1(RuntimeError):
    def __init__(self, code: FeatureConstructionReplayCodeV1, limit: str | None = None):
        self.code, self.limit = code, limit
        super().__init__(code.value if limit is None else f"{code.value}: {limit}")


@dataclass(frozen=True, slots=True)
class FeatureConstructionReplayProfileV1:
    max_depth: int
    max_tuple_arity: int
    max_text_codepoints: int
    max_integer_bits: int
    max_occurrences: int
    max_text_characters: int
    max_reference_items: int
    max_reference_pairs: int
    max_identity_checks: int
    max_retained_items: int
    max_filter_items: int
    max_duplicate_pairs: int
    max_numeric_conversions: int
    max_decimal_work: int
    max_slot_groups: int
    max_slot_records: int
    max_vector_records: int
    max_result_records: int
    max_slot_validations: int
    max_vector_validations: int
    max_result_validations: int
    max_parent_replays: int
    max_candidate_audit_replays: int
    max_shared_candidate_replays: int
    max_v2_replays: int
    max_readiness_replays: int
    max_readiness_inspections: int
    max_reconstructed_vectors: int
    max_comparison_work: int
    max_temporary_slots: int
    max_work_units: int


_Code = FeatureConstructionReplayCodeV1
_LIMITS = tuple(item.name for item in fields(FeatureConstructionReplayProfileV1))
_ACTIVE: ContextVar[FeatureConstructionReplayScopeV1 | None] = ContextVar(
    "feature_construction_replay_meter_v1", default=None
)


@cache
def _layouts():
    from . import feature_construction as fc

    upstream_records, upstream_enums = v2._layouts()
    readiness_records, readiness_enums = fr._layouts()
    kind = fc.FeatureSlotValueV0
    slot_fields = tuple(vars(kind)[item.name] for item in fields(kind))
    return (upstream_records | readiness_records | {id(kind): tuple((slot, None) for slot in slot_fields)},
            upstream_enums | readiness_enums | {
                id(group): tuple(group)
                for group in (fc.FeatureValueAvailabilityV0, fc.FeatureValueReasonV0)
            })


class FeatureConstructionReplayScopeV1:
    """One cumulative ledger, owned by its creating thread and asyncio task."""

    def __init__(self, *, profile: FeatureConstructionReplayProfileV1):
        if type(profile) is not FeatureConstructionReplayProfileV1:
            raise FeatureConstructionReplayErrorV1(_Code.INVALID_PROFILE)
        limits = {name: getattr(profile, name, None) for name in _LIMITS}
        if (any(type(value) is not int or not 1 <= value < 2**31 for value in limits.values())
                or limits["max_depth"] > 32 or limits["max_integer_bits"] > 64):
            raise FeatureConstructionReplayErrorV1(_Code.INVALID_PROFILE)
        self._limits = limits
        self._used = dict.fromkeys(_LIMITS[4:], 0)
        self._owner = _execution_owner()
        self._state = "NEW"
        self._operations = 0
        self._operand = self._readiness = self._v2 = self._numeric = self._token = None
        self._decimal_width = 0

    @property
    def state(self) -> str:
        return self._state

    def usage(self) -> dict[str, int]:
        self._check_owner()
        return self._used.copy()

    def _check_owner(self):
        if _execution_owner() != self._owner:
            raise FeatureConstructionReplayErrorV1(_Code.FOREIGN_SCOPE)

    def __enter__(self):
        self._check_owner()
        if (type(self) is not FeatureConstructionReplayScopeV1
                or self._state != "NEW" or _ACTIVE.get() is not None):
            raise FeatureConstructionReplayErrorV1(_Code.INVALID_SCOPE)
        try:
            self._operand = op.selected()
            if type(self._operand) is not op.HardConstraintOperandReplayScopeV1:
                self._reject(_Code.OPERAND_SCOPE_REQUIRED)
            self._readiness, self._v2 = fr.selected(), v2.selected()
            if self._readiness is not None and self._readiness._operand is not self._operand:
                self._reject(_Code.READINESS_SCOPE_REQUIRED)
            if self._v2 is not None and self._v2._operand is not self._operand:
                self._reject(_Code.V2_SCOPE_REQUIRED)
            self._numeric = current_owned_numeric_scope_v1()
            if type(self._numeric) is not OwnedNumericScopeV1:
                self._reject(_Code.NUMERIC_SCOPE_REQUIRED)
            if self._v2 is not None and self._v2._numeric is not self._numeric:
                self._reject(_Code.NUMERIC_SCOPE_REQUIRED)
            profile = self._numeric.inspect_capacity_v1().profile
            self._decimal_width = 1 + profile.max_coefficient_digits + profile.max_exponent_magnitude.bit_length()
            _layouts()
        except BaseException:
            self._state = "FAILED"
            raise
        self._token = _ACTIVE.set(self)
        self._state = "OPEN"
        return self

    def __exit__(self, exc_type, exc, traceback):
        self._check_owner()
        if _ACTIVE.get() is not self or self._operations:
            raise FeatureConstructionReplayErrorV1(_Code.INVALID_SCOPE)
        _ACTIVE.reset(self._token)
        self._operand = self._readiness = self._v2 = self._numeric = self._token = None
        self._state = "FAILED" if exc_type or self._state == "FAILED" else "CLOSED"

    def _check(self):
        self._check_owner()
        if self._state != "OPEN" or _ACTIVE.get() is not self:
            raise FeatureConstructionReplayErrorV1(_Code.INVALID_SCOPE)
        try:
            if op.selected() is not self._operand:
                self._reject(_Code.OPERAND_SCOPE_REQUIRED)
            if self._readiness is not None and fr.selected() is not self._readiness:
                self._reject(_Code.READINESS_SCOPE_REQUIRED)
            if self._v2 is not None and v2.selected() is not self._v2:
                self._reject(_Code.V2_SCOPE_REQUIRED)
            if current_owned_numeric_scope_v1() is not self._numeric:
                self._reject(_Code.NUMERIC_SCOPE_REQUIRED)
        except BaseException:
            self._state = "FAILED"
            raise

    def _reject(self, code, limit=None):
        self._state = "FAILED"
        raise FeatureConstructionReplayErrorV1(code, limit)

    def _cap(self, name, amount):
        if amount > self._limits[name]:
            self._reject(_Code.RESOURCE_LIMIT, name)

    def _reserve(self, **charges):
        self._check()
        for name, amount in charges.items():
            if name not in self._used or type(amount) is not int or amount < 0:
                self._reject(_Code.INVALID_PROFILE)
            if amount > self._limits[name] - self._used[name]:
                self._reject(_Code.RESOURCE_LIMIT, name)
        for name, amount in charges.items():
            self._used[name] += amount

    def _exact(self, value, kind):
        if type(value) is not kind:
            self._reject(_Code.INVALID_SHAPE)

    def _tuple(self, value):
        self._exact(value, tuple)
        size = len(value)
        self._cap("max_tuple_arity", size)
        return size

    def _text(self, value):
        self._exact(value, str)
        width = len(value)
        self._cap("max_text_codepoints", width)
        self._reserve(max_text_characters=width, max_temporary_slots=width,
                      max_work_units=1 + 3 * width)
        return width

    def _decimal(self, value):
        self._exact(value, Decimal)
        self._reserve(max_work_units=1)
        self._numeric.require_owned(value)
        return self._decimal_width

    def _walk(self, root):
        records, enums = _layouts()
        active = []

        def visit(value, depth):
            self._cap("max_depth", depth)
            self._reserve(max_occurrences=1, max_work_units=4 + depth, max_temporary_slots=1)
            marker, kind = id(value), type(value)
            if marker in active:
                self._reject(_Code.ACTIVE_PATH_CYCLE)
            if kind is str:
                return 1 + self._text(value), 0
            if value is None or kind is bool:
                return 1, 0
            if kind is int:
                self._cap("max_integer_bits", value.bit_length())
                return 1 + value.bit_length(), 0
            if kind is Decimal:
                return 1 + self._decimal(value), 1
            if id(kind) in enums:
                group = enums[id(kind)]
                self._reserve(max_work_units=len(group))
                if not any(value is member for member in group):
                    self._reject(_Code.INVALID_SHAPE)
                return 1 + self._text(value.value), 0
            active.append(marker)
            try:
                if kind is tuple:
                    count = self._tuple(value)
                    children = value
                elif id(kind) in records:
                    layout = records[id(kind)]
                    count = len(layout)
                    children = (slot.__get__(value) for slot, _ in layout)
                else:
                    self._reject(_Code.INVALID_SHAPE)
                self._reserve(max_work_units=count)
                total, decimals = 1 + count, 0
                for child in children:
                    weight, numbers = visit(child, depth + 1)
                    total += weight
                    decimals += numbers
                return total, decimals
            finally:
                active.pop()

        return visit(root, 1)


def selected():
    meter = _ACTIVE.get()
    if meter is not None:
        meter._check()
    return meter


def operation(function=None, *, entry=False):
    if function is None:
        return lambda callback: operation(callback, entry=entry)

    @wraps(function)
    def invoke(*args, **kwargs):
        meter = selected()
        if meter is None:
            return function(*args, **kwargs)
        if entry and meter._operations:
            meter._reject(_Code.INVALID_SCOPE)
        meter._operations += 1
        try:
            result = function(*args, **kwargs)
            meter._check()
            return result
        except BaseException:
            meter._state = "FAILED"
            raise
        finally:
            meter._operations -= 1

    return invoke


def reserve(**charges):
    meter = selected()
    if meter is not None:
        meter._reserve(**charges)


def require_dependencies(*, readiness=False, constraints=False):
    meter = selected()
    if meter is not None:
        if readiness and type(meter._readiness) is not fr.FeatureReadinessReplayScopeV1:
            meter._reject(_Code.READINESS_SCOPE_REQUIRED)
        if constraints and type(meter._v2) is not v2.HardConstraintV2ReplayScopeV1:
            meter._reject(_Code.V2_SCOPE_REQUIRED)


def exact(value, kind):
    meter = selected()
    if meter is not None:
        meter._exact(value, kind)


def text(value):
    meter = selected()
    if meter is not None:
        meter._text(value)


def sequence(values, *, kind=None, copies=1, extra=0):
    meter = selected()
    if meter is not None:
        count = meter._tuple(values)
        meter._cap("max_tuple_arity", count + extra)
        capacity = copies * (count + extra)
        meter._reserve(max_work_units=1 + capacity, max_temporary_slots=capacity)
        if kind is not None:
            for value in values:
                meter._exact(value, kind)


def same(left, right):
    reserve(max_identity_checks=1, max_work_units=1)
    return _identical(left, right)


def _identical(left, right):
    return left is right


def different(left, right):
    meter = selected()
    if meter is not None:
        left_weight, left_decimals = meter._walk(left)
        right_weight, right_decimals = meter._walk(right)
        work = 2 * (left_weight + right_weight)
        decimal_work = (left_decimals + right_decimals) * meter._decimal_width ** 2
        meter._reserve(max_comparison_work=work, max_decimal_work=decimal_work,
                       max_temporary_slots=2 * work + decimal_work,
                       max_work_units=work + decimal_work)
    return _compare(left, right)


def _compare(left, right):
    return left != right


def slot_values_different(left, right):
    if different(left, right):
        return True
    meter = selected()
    if meter is None:
        return False
    meter._reserve(max_work_units=len(left) + 1)
    for observed, expected in zip(left, right, strict=True):
        if type(observed.value) is not type(expected.value):
            return True
        if type(observed.value) is Decimal:
            # Both operands have already passed the owned-Decimal tree walk.
            width = meter._decimal_width
            with_representation = 16 * width
            meter._reserve(max_decimal_work=with_representation,
                           max_temporary_slots=8 * width, max_work_units=with_representation)
            if observed.value.as_tuple() != expected.value.as_tuple():
                return True
    return False


def readiness_different(left, right):
    if selected() is None:
        return left != right
    if (not same(left.operand_audit, right.operand_audit)
            or different(left.component_version, right.component_version)
            or different(left.record_version, right.record_version)):
        return True
    a, b = left.candidate_observations, right.candidate_observations
    sequence(a)
    sequence(b)
    if len(a) != len(b):
        return True
    for observed, expected in zip(a, b, strict=True):
        if (not same(observed.operand_audit, expected.operand_audit)
                or not same(observed.candidate_audit, expected.candidate_audit)
                or not same(observed.candidate, expected.candidate)
                or different(observed.slots, expected.slots)
                or different(observed.record_version, expected.record_version)):
            return True
    return False


def vector_different(left, right):
    if selected() is None:
        return left != right
    # Source objects have just passed the caller's exact-reference guards.
    return (different(left.theta_a_reference, right.theta_a_reference)
            or different(left.feature_schema_id, right.feature_schema_id)
            or different(left.record_version, right.record_version)
            or slot_values_different(left.slot_values, right.slot_values))


def reserve_confidence(value, source_id, source):
    meter = selected()
    if meter is None:
        return
    kind = type(value)
    if kind is int:
        meter._cap("max_integer_bits", value.bit_length())
    elif kind is not float or not isfinite(value):
        meter._reject(_Code.UNSUPPORTED_NUMBER)
    width = meter._text(source_id)
    source_kind = type(source)
    if source_kind is not OcrSourceToken and source_kind is not StructuredField:
        meter._reject(_Code.INVALID_SOURCE_BINDING)
    anchors = meter._numeric._sources
    count = len(anchors)
    work = 2 * meter._decimal_width ** 2
    meter._reserve(max_numeric_conversions=1, max_decimal_work=work,
                   max_identity_checks=count, max_temporary_slots=work + 2 * count,
                   max_work_units=work + 1 + width + count * (4 + width))
    # Admit the actual record as well as its captured native scalar. S01
    # remains responsible for the native recipe and its own source lookup.
    role = "OCR" if source_kind is OcrSourceToken else "EXTRACTOR"
    for name, (anchored, anchored_role, _) in anchors.items():
        if name == source_id:
            if source is not anchored or role != anchored_role:
                meter._reject(_Code.INVALID_SOURCE_BINDING)
            return
    meter._reject(_Code.INVALID_SOURCE_BINDING)


def minimum(values):
    meter = selected()
    if meter is not None:
        work = max(0, len(values) - 1) * meter._decimal_width ** 2
        meter._reserve(max_decimal_work=work, max_temporary_slots=work, max_work_units=1 + work)
    return min(values)


def slot_validation(record):
    meter = selected()
    if meter is not None:
        meter._reserve(max_slot_validations=1, max_work_units=12)
        meter._walk(record)
        meter._reserve(max_work_units=3 * len(record.provenance_references))


def _reference_cost(meter, values):
    count = meter._tuple(values)
    meter._reserve(max_reference_items=count, max_work_units=count)
    width = max((meter._text(value) for value in values), default=0)
    pairs = count * (count - 1) // 2
    work = pairs * (1 + width)
    meter._reserve(max_reference_pairs=pairs, max_work_units=work + count + 8,
                   max_temporary_slots=8 + 3 * count)


def references(meter, values):
    _reference_cost(meter, values)
    return _deduplicate(values)


def _deduplicate(values):
    distinct = []
    for value in values:
        if value not in distinct:
            distinct.append(value)
    return tuple(distinct)


def duplicate_references(meter, values):
    return len(references(meter, values)) != len(values)


def seen(key, previous):
    meter = selected()
    size = len(previous)
    width = meter._text(key)
    # Equality on exact strings can scan at most the new key's width.
    meter._reserve(max_duplicate_pairs=size, max_work_units=size * (1 + width) + 1)
    return _contains(key, previous)


def _contains(key, previous):
    return key in previous


def replay(record, counter):
    reserve(**{counter: 1}, max_work_units=1)
    record.__post_init__()


def replay_shared_candidate(record):
    if selected() is None:
        record.__post_init__()
    else:
        reserve(max_shared_candidate_replays=1, max_work_units=1)
        op.validate_candidate(record)


def inspect_readiness(inspect, operand_audit):
    require_dependencies(readiness=True)
    reserve(max_readiness_inspections=1, max_work_units=1)
    return inspect(operand_audit=operand_audit)
