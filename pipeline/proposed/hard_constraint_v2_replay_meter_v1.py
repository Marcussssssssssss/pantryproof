"""Opt-in logical accounting for the existing V2 audit validation."""

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
from . import finalization_replay_meter_v1 as finalization
from . import hard_constraint_operand_replay_meter_v1 as operand
from .contracts import CandidateProvenanceV1
from .contracts import CandidateRecordV1
from .owned_numeric_producer_v1 import (
    OwnedNumericErrorCodeV1,
    OwnedNumericErrorV1,
    current_owned_numeric_scope_v1,
)


class HardConstraintV2ReplayCodeV1(str, Enum):
    INVALID_PROFILE = "INVALID_PROFILE"
    INVALID_SCOPE = "INVALID_SCOPE"
    FOREIGN_SCOPE = "FOREIGN_SCOPE"
    SCOPE_CLOSED = "SCOPE_CLOSED"
    OPERAND_SCOPE_REQUIRED = "OPERAND_SCOPE_REQUIRED"
    SERIALIZATION_OUT_OF_SCOPE = "SERIALIZATION_OUT_OF_SCOPE"
    INVALID_SHAPE = "INVALID_SHAPE"
    ACTIVE_PATH_CYCLE = "ACTIVE_PATH_CYCLE"
    INVALID_NUMERIC_OWNERSHIP = "INVALID_NUMERIC_OWNERSHIP"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"


class HardConstraintV2ReplayErrorV1(RuntimeError):
    def __init__(self, code: HardConstraintV2ReplayCodeV1, limit: str | None = None):
        if type(code) is not HardConstraintV2ReplayCodeV1:
            raise TypeError("Invalid hard-constraint V2 replay error code.")
        if code is _Code.RESOURCE_LIMIT:
            if type(limit) is not str or limit not in _LIMIT_FIELDS:
                raise TypeError("Invalid hard-constraint V2 replay limit name.")
        elif limit is not None:
            raise TypeError("Only a resource refusal names a hard-constraint V2 replay limit.")
        self.code = code
        self.limit = limit
        super().__init__(code.value if limit is None else f"{code.value}: {limit}")


@dataclass(frozen=True, slots=True, kw_only=True)
class HardConstraintV2ReplayProfileV1:
    """All limits are explicit and inclusive."""

    version: ClassVar[str] = "hard-constraint-v2-replay-meter-v1"
    max_int_bits: int
    max_text_codepoints: int
    max_depth: int
    max_tuple_arity: int
    max_population: int
    max_candidate_occurrences: int
    max_scan_items: int
    max_profiles: int
    max_rules: int
    max_resources: int
    max_resource_references: int
    max_outcomes: int
    max_result_validations: int
    max_evidence: int
    max_operand_replays: int
    max_candidate_audit_replays: int
    max_candidate_validations: int
    max_provenance_validations: int
    max_span_validations: int
    max_rank_validations: int
    max_configuration_validations: int
    max_member_occurrences: int
    max_token_occurrences: int
    max_span_occurrences: int
    max_set_probes: int
    max_lookup_pairs: int
    max_uniqueness_pairs: int
    max_occurrences: int
    max_comparison_work: int
    max_records: int
    max_temporary_slots: int
    max_work_units: int


_Code = HardConstraintV2ReplayCodeV1
_LIMIT_FIELDS = tuple(item.name for item in fields(HardConstraintV2ReplayProfileV1))
_PER_VALUE = _LIMIT_FIELDS[:5]
_ACTIVE: ContextVar[HardConstraintV2ReplayScopeV1 | None] = ContextVar(
    "hard_constraint_v2_replay_meter_v1", default=None
)


@cache
def _layouts():
    # Share the pinned exact field vocabulary, never the upstream ledgers.
    from . import hard_constraint_contracts_v2 as v2

    base_records, base_enums = operand._layouts()
    records, enums = base_records.copy(), base_enums.copy()
    for kind in (
        v2.HardConstraintResourceRefV2, v2.HardConstraintRuleSpecV2,
        v2.HardConstraintProfileRefV2, v2.EvidenceReferenceV2,
        v2.ConstraintRuleOutcomeV2, v2.ConstraintResultV2,
    ):
        layout = []
        hints = get_type_hints(kind)
        for item in fields(kind):
            if item.compare:
                slot = vars(kind)[item.name]
                if type(slot) is not MemberDescriptorType:
                    raise HardConstraintV2ReplayErrorV1(_Code.INVALID_SHAPE)
                layout.append((slot, hints[item.name]))
        records[id(kind)] = tuple(layout)
    for kind in (
        v2.RuleRequirementV2, v2.RuleOutcomeStateV2, v2.RuleEvidenceAvailabilityV2,
        v2.ConstraintAggregateStateV2, v2.ConstraintAggregateReasonV2,
        v2.RuleOutcomeReasonKindV2,
    ):
        enums[id(kind)] = tuple(kind)
    return records, enums


class HardConstraintV2ReplayScopeV1:
    """A single-use local ledger owned by the creating thread and task."""

    def __init__(self, *, profile: HardConstraintV2ReplayProfileV1):
        if type(profile) is not HardConstraintV2ReplayProfileV1:
            raise HardConstraintV2ReplayErrorV1(_Code.INVALID_PROFILE)
        limits = {name: getattr(profile, name, None) for name in _LIMIT_FIELDS}
        if any(type(limit) is not int or not 1 <= limit < 2**31 for limit in limits.values()):
            raise HardConstraintV2ReplayErrorV1(_Code.INVALID_PROFILE)
        if not (
            limits["max_depth"] <= 32
            and limits["max_int_bits"] <= 64
        ):
            raise HardConstraintV2ReplayErrorV1(_Code.INVALID_PROFILE)
        self._limits = limits
        self._used = {name: 0 for name in limits if name not in _PER_VALUE}
        self._owner = identity._execution_owner()
        self._state = "NEW"
        self._operand = self._numeric = self._numeric_profile = self._token = None

    @property
    def state(self) -> str:
        return self._state

    def usage(self) -> dict[str, int]:
        self._check_owner()
        return self._used.copy()

    def _check_owner(self) -> None:
        if identity._execution_owner() != self._owner:
            raise HardConstraintV2ReplayErrorV1(_Code.FOREIGN_SCOPE)

    def __enter__(self) -> HardConstraintV2ReplayScopeV1:
        self._check_owner()
        if self._state != "NEW" or _ACTIVE.get() is not None:
            raise HardConstraintV2ReplayErrorV1(_Code.INVALID_SCOPE)
        try:
            op01 = operand.selected()
            if type(op01) is not operand.HardConstraintOperandReplayScopeV1:
                self._reject(_Code.OPERAND_SCOPE_REQUIRED)
            owner = current_owned_numeric_scope_v1()
            profile = owner.inspect_capacity_v1().profile
            _layouts()
        except BaseException:
            self._state = "FAILED"
            raise
        self._operand, self._numeric, self._numeric_profile = op01, owner, profile
        self._token = _ACTIVE.set(self)
        self._state = "OPEN"
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._check_owner()
        if _ACTIVE.get() is not self:
            raise HardConstraintV2ReplayErrorV1(_Code.INVALID_SCOPE)
        _ACTIVE.reset(self._token)
        self._operand = self._numeric = self._numeric_profile = self._token = None
        self._state = "FAILED" if exc_type or self._state == "FAILED" else "CLOSED"

    def _check(self) -> None:
        self._check_owner()
        if self._state != "OPEN" or _ACTIVE.get() is not self:
            raise HardConstraintV2ReplayErrorV1(_Code.SCOPE_CLOSED)
        try:
            if operand.selected() is not self._operand:
                self._reject(_Code.OPERAND_SCOPE_REQUIRED)
        except BaseException:
            self._state = "FAILED"
            raise

    def _reject(self, code: HardConstraintV2ReplayCodeV1, limit: str | None = None):
        self._state = "FAILED"
        raise HardConstraintV2ReplayErrorV1(code, limit)

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


def selected() -> HardConstraintV2ReplayScopeV1 | None:
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


def admit(value, kind) -> None:
    meter = selected()
    if meter is not None:
        meter._walk(value, kind)


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


def has_duplicate_ids(ids: tuple, key_type=str) -> bool:
    meter = selected()
    if meter is None:
        return len(ids) != len(set(ids))
    count = len(ids)
    width = meter._walk(ids, tuple[key_type, ...]) - 1
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

def exclude_serialization() -> None:
    meter = selected()
    if meter is not None:
        meter._reject(_Code.SERIALIZATION_OUT_OF_SCOPE)


def text_cost(value: str, *, pattern: bool = False) -> None:
    meter = selected()
    if meter is not None:
        length = meter._text(value)
        if pattern:
            # The fixed rule grammar has one initial class and one
            # repeated class. Price one linear pass, including failure.
            meter._reserve(max_work_units=2 * length + 1)
        else:
            meter._reserve(max_temporary_slots=length, max_work_units=length + 1)


def diagnostic(value: str) -> None:
    meter = selected()
    if meter is not None:
        length = 64 + meter._text(value)
        meter._reserve(max_temporary_slots=2 * length, max_work_units=2 * length)


def integer(value: int) -> None:
    meter = selected()
    if meter is not None:
        width = meter._width(value)
        meter._reserve(max_work_units=1 + width)


def tuple_shape(value: tuple) -> None:
    meter = selected()
    if meter is not None:
        meter._exact(value, tuple)
        meter._cap("max_tuple_arity", len(value))


def start_record(value, kind, counter: str) -> None:
    meter = selected()
    if meter is not None:
        meter._exact(value, kind)
        meter._reserve(max_work_units=1, **{counter: 1})


def contains(key, values) -> bool:
    scan(len(values))
    for item in values:
        reserve(max_lookup_pairs=1)
        if equal(key, item):
            return True
    return False


def project_resources(reference_ids: tuple[str, ...], resources: tuple) -> tuple:
    sequence(len(reference_ids))
    return tuple(_find_resource(key, resources) for key in reference_ids)


def _find_resource(key, resources):
    scan(len(resources))
    for resource in resources:
        reserve(max_lookup_pairs=1)
        if equal(key, resource.resource_reference_id):
            return resource
    raise KeyError(key)


def validate_rule_positions(rules: tuple) -> bool:
    meter = selected()
    count = len(rules)
    width = count.bit_length()
    meter._cap("max_int_bits", width)
    sequence(count)
    sequence(count)
    reserve(max_work_units=count * (1 + width))
    return not_equal(tuple(rule.position for rule in rules), tuple(range(count)))


def admit_parent(aggregate) -> None:
    from .hard_constraint_context import HardConstraintInputResultV0

    parent = aggregate.hard_constraint_input
    exact(parent, HardConstraintInputResultV0)
    population(aggregate.candidate_audits)
    population(parent.candidates)


def _reserve_set(keys, count: int) -> None:
    scan(count)
    chars, longest = _keys(keys)
    work, comparisons, slots, probes = finalization._shared_set_cost(count, chars, longest)
    reserve(max_set_probes=probes, max_comparison_work=comparisons,
            max_temporary_slots=slots, max_work_units=work)


def _reserve_validator(weight: int, counter: str, *, scans: int = 0, slots: int = 0,
                       repeated_compare: int = 0) -> None:
    compare = 4 * weight + repeated_compare
    reserve(max_scan_items=scans, max_comparison_work=compare,
            max_temporary_slots=32 + 2 * weight + slots,
            max_work_units=64 + 8 * weight + scans + repeated_compare,
            **{counter: 1})


def reserve_v1(record, kind) -> None:
    meter = selected()
    if meter is None:
        return
    weight = meter._walk(record, kind)
    from .contracts import ConfigurationRefV1, PreliminaryRankV1, SourceCharacterSpanV1

    if kind is CandidateRecordV1:
        count = len(record.provenance)
        reserve(max_member_occurrences=count)
        _reserve_set((item.provenance_id for item in record.provenance), count)
        headers = sum(1 + len(text) for text in (record.candidate_id, record.receipt_id, record.field_id))
        _reserve_validator(weight, "max_candidate_validations", scans=3 * count,
                           slots=count, repeated_compare=4 * count * headers)
    elif kind is CandidateProvenanceV1:
        tokens, spans = record.source_token_ids, record.source_spans
        count, span_count = len(tokens), len(spans)
        reserve(max_token_occurrences=count, max_span_occurrences=span_count)
        _reserve_set(tokens, count)
        scan(count + span_count)
        width = max(max(map(len, tokens), default=0),
                    max((len(span.token_id) for span in spans), default=0))
        pairs = count * span_count
        reserve(max_lookup_pairs=pairs)
        _reserve_validator(weight, "max_provenance_validations", scans=span_count + pairs,
                           slots=span_count, repeated_compare=2 * pairs * (1 + width))
    elif kind is SourceCharacterSpanV1:
        _reserve_validator(weight, "max_span_validations")
    elif kind is PreliminaryRankV1:
        _reserve_validator(weight, "max_rank_validations")
    elif kind is ConfigurationRefV1:
        _reserve_validator(weight, "max_configuration_validations")
    else:
        meter._reject(_Code.INVALID_SHAPE)

