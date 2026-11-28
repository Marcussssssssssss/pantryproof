"""Opt-in logical work accounting for the raw seven-slot observations."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, fields
from enum import Enum
from functools import cache, wraps
from math import isfinite
from typing import get_args, get_type_hints

from pipeline import contracts as b2

from . import hard_constraint_operand_replay_meter_v1 as op
from .contracts import CandidateProvenanceV1, CandidateRecordV1, FeatureSlot, MethodReadyFieldV1
from .hard_constraint_context import HardConstraintInputResultV0
from .hard_constraint_operands import (
    CandidateOperandAuditV0,
    HardConstraintOperandAuditResultV0,
    ItemRowOperandEvidenceV0,
    OperandEvidenceV0,
)
from .identity_replay_meter_v1 import _execution_owner, _matches


class FeatureReadinessReplayCodeV1(str, Enum):
    INVALID_PROFILE = "INVALID_PROFILE"
    INVALID_SCOPE = "INVALID_SCOPE"
    FOREIGN_SCOPE = "FOREIGN_SCOPE"
    OPERAND_SCOPE_REQUIRED = "OPERAND_SCOPE_REQUIRED"
    INVALID_SHAPE = "INVALID_SHAPE"
    ACTIVE_PATH_CYCLE = "ACTIVE_PATH_CYCLE"
    UNSUPPORTED_NUMBER = "UNSUPPORTED_NUMBER"
    NONFINITE_NUMBER = "NONFINITE_NUMBER"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"


class FeatureReadinessReplayErrorV1(RuntimeError):
    def __init__(self, code: FeatureReadinessReplayCodeV1, limit: str | None = None):
        self.code, self.limit = code, limit
        super().__init__(code.value if limit is None else f"{code.value}: {limit}")


@dataclass(frozen=True, slots=True)
class FeatureReadinessReplayProfileV1:
    max_depth: int
    max_int_bits: int
    max_text_codepoints: int
    max_tuple_arity: int
    max_occurrences: int
    max_text_characters: int
    max_reference_items: int
    max_reference_pairs: int
    max_tokens: int
    max_polygon_points: int
    max_coordinates: int
    max_constructed_facts: int
    max_slot_tuples: int
    max_slots: int
    max_candidate_records: int
    max_result_records: int
    max_parent_replays: int
    max_candidate_audit_replays: int
    max_shared_candidate_replays: int
    max_fact_validations: int
    max_slot_validations: int
    max_candidate_validations: int
    max_result_validations: int
    max_fingerprints: int
    max_fingerprint_chars: int
    max_fingerprint_bytes: int
    max_format_work: int
    max_identity_pairs: int
    max_comparison_work: int
    max_primitive_tuples: int
    max_temporary_slots: int
    max_work_units: int


_Code = FeatureReadinessReplayCodeV1
_LIMITS = tuple(item.name for item in fields(FeatureReadinessReplayProfileV1))
_PER_VALUE = _LIMITS[:4]
_ACTIVE: ContextVar[FeatureReadinessReplayScopeV1 | None] = ContextVar(
    "feature_readiness_replay_meter_v1", default=None
)


@cache
def _layouts():
    from . import feature_readiness as readiness

    records = {}
    for kind in (readiness.InputFactObservationV0, readiness.FeatureSlotInputObservationV0):
        hints = get_type_hints(kind)
        records[id(kind)] = tuple((vars(kind)[item.name], hints[item.name]) for item in fields(kind))
    enums = {
        id(kind): tuple(kind)
        for kind in (FeatureSlot, readiness.InputFactKindV0, readiness.InputFactPresenceV0)
    }
    return records, enums


class FeatureReadinessReplayScopeV1:
    """Single-use, owned by the creating thread and task and bound to OP01."""

    def __init__(self, *, profile: FeatureReadinessReplayProfileV1):
        if type(profile) is not FeatureReadinessReplayProfileV1:
            raise FeatureReadinessReplayErrorV1(_Code.INVALID_PROFILE)
        limits = {name: getattr(profile, name, None) for name in _LIMITS}
        if (any(type(value) is not int or not 1 <= value < 2**31 for value in limits.values())
                or limits["max_depth"] > 32 or limits["max_int_bits"] > 64):
            raise FeatureReadinessReplayErrorV1(_Code.INVALID_PROFILE)
        self._limits = limits
        self._used = dict.fromkeys((name for name in _LIMITS if name not in _PER_VALUE), 0)
        self._owner = _execution_owner()
        self._state = "NEW"
        self._operations = 0
        self._operand = self._token = None

    @property
    def state(self) -> str:
        return self._state

    def usage(self) -> dict[str, int]:
        self._check_owner()
        return self._used.copy()

    def _check_owner(self):
        if _execution_owner() != self._owner:
            raise FeatureReadinessReplayErrorV1(_Code.FOREIGN_SCOPE)

    def __enter__(self):
        self._check_owner()
        if (type(self) is not FeatureReadinessReplayScopeV1
                or self._state != "NEW" or _ACTIVE.get() is not None):
            raise FeatureReadinessReplayErrorV1(_Code.INVALID_SCOPE)
        try:
            self._operand = op.selected()
            if type(self._operand) is not op.HardConstraintOperandReplayScopeV1:
                self._reject(_Code.OPERAND_SCOPE_REQUIRED)
            op._require_runtime()
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
            raise FeatureReadinessReplayErrorV1(_Code.INVALID_SCOPE)
        _ACTIVE.reset(self._token)
        self._operand = self._token = None
        self._state = "FAILED" if exc_type or self._state == "FAILED" else "CLOSED"

    def _check(self):
        self._check_owner()
        if self._state != "OPEN" or _ACTIVE.get() is not self:
            raise FeatureReadinessReplayErrorV1(_Code.INVALID_SCOPE)
        try:
            if op.selected() is not self._operand:
                self._reject(_Code.OPERAND_SCOPE_REQUIRED)
        except BaseException:
            self._state = "FAILED"
            raise

    def _reject(self, code, limit=None):
        self._state = "FAILED"
        raise FeatureReadinessReplayErrorV1(code, limit)

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

    def _tuple(self, values):
        self._exact(values, tuple)
        size = len(values)
        self._cap("max_tuple_arity", size)
        return size

    def _text(self, value):
        self._exact(value, str)
        size = len(value)
        self._cap("max_text_codepoints", size)
        self._reserve(max_text_characters=size, max_work_units=1 + 3 * size,
                      max_temporary_slots=size)
        return size

    def _walk(self, root, expected=None):
        records, enums = _layouts()
        active = []

        def visit(value, hint, depth):
            marker = id(value)
            kind = type(value)
            self._cap("max_depth", depth)
            self._reserve(max_occurrences=1, max_work_units=3 + depth, max_temporary_slots=1)
            if marker in active:
                self._reject(_Code.ACTIVE_PATH_CYCLE)
            if not _matches(kind, hint):
                self._reject(_Code.INVALID_SHAPE)
            if kind is str:
                return 1 + self._text(value)
            if value is None:
                return 1
            if id(kind) in enums:
                members = enums[id(kind)]
                self._reserve(max_work_units=len(members))
                if not any(value is member for member in members):
                    self._reject(_Code.INVALID_SHAPE)
                return 1 + self._text(value.value)
            active.append(marker)
            try:
                if kind is tuple:
                    size = self._tuple(value)
                    self._reserve(max_work_units=size)
                    hints = get_args(hint)
                    if len(hints) == 2 and hints[1] is Ellipsis:
                        return 1 + size + sum(visit(item, hints[0], depth + 1) for item in value)
                    if not hints:
                        return 1 + size + sum(visit(item, None, depth + 1) for item in value)
                    if size != len(hints):
                        self._reject(_Code.INVALID_SHAPE)
                    return 1 + size + sum(visit(item, child, depth + 1)
                                          for item, child in zip(value, hints, strict=True))
                if id(kind) in records:
                    layout = records[id(kind)]
                    self._reserve(max_work_units=len(layout))
                    return 1 + len(layout) + sum(visit(slot.__get__(value), child, depth + 1)
                                                 for slot, child in layout)
                self._reject(_Code.INVALID_SHAPE)
            finally:
                active.pop()

        return visit(root, expected, 1)


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


def exact(value, kind):
    meter = selected()
    if meter is not None:
        meter._exact(value, kind)


def text(value):
    meter = selected()
    if meter is not None:
        meter._text(value)


def sequence(values, *, copies=1, extra=0, kind=None):
    meter = selected()
    if meter is not None:
        size = meter._tuple(values)
        meter._cap("max_tuple_arity", size + extra)
        meter._reserve(max_work_units=copies * (size + extra) + 1,
                       max_temporary_slots=copies * (size + extra))
        if kind is not None:
            for value in values:
                meter._exact(value, kind)


def reserve_fingerprint(value):
    meter = selected()
    if meter is None:
        return
    kind = type(value)
    if kind is int:
        width = value.bit_length()
        meter._cap("max_int_bits", width)
        literal = 1 + max(1, (width + 2) // 3)
        formatting = (1 + width) ** 2 + literal
        name_width = 3
    elif kind is float:
        if not isfinite(value):
            meter._reject(_Code.NONFINITE_NUMBER)
        literal = 24
        formatting = 1074 + 1024 + 17 * 53 + literal
        name_width = 5
    else:
        meter._reject(_Code.UNSUPPORTED_NUMBER)
    characters = 8 + name_width + literal
    comparison = 2 * (4 + characters)
    meter._reserve(max_fingerprints=1, max_fingerprint_chars=characters,
                   max_fingerprint_bytes=characters, max_format_work=formatting,
                   max_temporary_slots=3 + characters, max_comparison_work=comparison,
                   max_work_units=formatting + 3 + characters + comparison)


def _reference_bound(meter, values):
    size = meter._tuple(values)
    meter._reserve(max_reference_items=size, max_work_units=size)
    longest = 0
    for value in values:
        if value is not None:
            longest = max(longest, meter._text(value))
    pairs = size * (size - 1) // 2
    work = pairs * (1 + longest)
    meter._reserve(max_reference_pairs=pairs, max_comparison_work=work,
                   max_work_units=work + size + 8, max_temporary_slots=8 + 3 * size)


def first_references(meter, values):
    _reference_bound(meter, values)
    return _deduplicate(values)


def _deduplicate(values):
    distinct = []
    for value in values:
        if value is not None and value not in distinct:
            distinct.append(value)
    return tuple(distinct)


def duplicate_references(meter, values):
    _reference_bound(meter, values)
    return len(_deduplicate(values)) != len(values)


def fact_validation(record, kind):
    meter = selected()
    if meter is not None:
        meter._reserve(max_fact_validations=1)
        weight = meter._walk(record, kind)
        meter._reserve(max_work_units=4 * weight, max_temporary_slots=8)


def duplicate_facts(meter, facts):
    size = meter._tuple(facts)
    meter._reserve(max_work_units=size)
    width = 0
    for fact in facts:
        references = fact.source_references
        meter._reserve(max_work_units=len(references))
        width = max(width, sum(1 + len(reference) for reference in references))
    pairs = size * (size - 1) // 2
    work = pairs * (2 + width)
    meter._reserve(max_identity_pairs=pairs, max_comparison_work=work, max_work_units=work)
    return _duplicate_fact_identity(facts)


def _duplicate_fact_identity(facts):
    for index, fact in enumerate(facts):
        for other in range(index):
            prior = facts[other]
            if fact.kind is prior.kind and fact.source_references == prior.source_references:
                return True
    return False


def different(left, right):
    meter = selected()
    if meter is not None:
        weight = 2 * (meter._walk(left) + meter._walk(right))
        meter._reserve(max_comparison_work=weight, max_work_units=weight,
                       max_temporary_slots=2 * weight)
    return _compare(left, right)


def _compare(left, right):
    return left != right


def observation_different(left, right):
    if selected() is None:
        return left != right
    reserve(max_work_units=3)
    # Generated equality short-circuits these exact shared references.
    return (left.operand_audit is not right.operand_audit
            or left.candidate_audit is not right.candidate_audit
            or left.candidate is not right.candidate
            or different(left.slots, right.slots)
            or different(left.record_version, right.record_version))


def replay_parent(record):
    exact(record, HardConstraintOperandAuditResultV0)
    reserve(max_parent_replays=1, max_work_units=1)
    record.__post_init__()


def replay_candidate_audit(record):
    exact(record, CandidateOperandAuditV0)
    reserve(max_candidate_audit_replays=1, max_work_units=1)
    record.__post_init__()


def replay_shared_candidate(record):
    if selected() is None:
        record.__post_init__()
    else:
        reserve(max_shared_candidate_replays=1, max_work_units=1)
        op.validate_candidate(record)


def construct_fact(references, texts, numbers=(), polygons=()):
    meter = selected()
    if meter is None:
        return
    total = sum(meter._tuple(group) for group in (references, texts, numbers, polygons))
    meter._reserve(max_constructed_facts=1, max_temporary_slots=16 + 4 * total,
                   max_work_units=16 + 4 * total)
    for literal in texts:
        meter._text(literal)
    for polygon in polygons:
        points = meter._tuple(polygon)
        meter._reserve(max_work_units=points, max_temporary_slots=4 + 4 * points)
        for point in polygon:
            if meter._tuple(point) != 2:
                meter._reject(_Code.INVALID_SHAPE)


def slot_plan(audit, context):
    meter = selected()
    if meter is None:
        return
    meter._exact(audit, CandidateOperandAuditV0)
    meter._exact(context, HardConstraintInputResultV0)
    method = context.method_ready_field
    meter._exact(method, MethodReadyFieldV1)
    meter._exact(audit.candidate, CandidateRecordV1)
    tokens = method.source_tokens
    n = meter._tuple(tokens)
    p = meter._tuple(audit.candidate.provenance)
    rows = meter._tuple(audit.item_rows)
    meter._cap("max_tuple_arity", 7)
    meter._reserve(max_tokens=n, max_slot_tuples=1, max_slots=7,
                   max_work_units=rows + n + p)
    arithmetic = 0
    for row in audit.item_rows:
        meter._exact(row, ItemRowOperandEvidenceV0)
        count = meter._tuple(row.operands)
        meter._reserve(max_work_units=count)
        arithmetic += count
        for item in row.operands:
            meter._exact(item, OperandEvidenceV0)
    for token in tokens:
        meter._exact(token, b2.OcrSourceToken)
        meter._text(token.token_id)
        meter._text(token.original_text)
        points = meter._tuple(token.polygon)
        meter._reserve(max_polygon_points=points, max_coordinates=2 * points,
                       max_work_units=5 * points, max_temporary_slots=4 + 5 * points)
        for point in token.polygon:
            meter._exact(point, b2.Point)
    for member in audit.candidate.provenance:
        meter._exact(member, CandidateProvenanceV1)
        sequence(member.source_token_ids, copies=4, extra=3)
    for size in (2 * n + 1, 4, n + p + 3, n + 3, 3, arithmetic + 3, 5):
        meter._cap("max_tuple_arity", size)
    facts = 4 * n + p + arithmetic + 22
    # The allowance includes temporary starred lists and the fixed slot pairs.
    meter._reserve(max_temporary_slots=128 + 6 * facts,
                   max_work_units=4096 + 8 * facts + rows)


def overflow_overlap(meter, overflow, candidates):
    count = meter._tuple(overflow)
    retained = meter._tuple(candidates)
    meter._reserve(max_work_units=count + retained)
    width = 0
    for group in (overflow, candidates):
        for item in group:
            meter._exact(item, CandidateRecordV1)
            width = max(width, meter._text(item.candidate_id))
    work = count * retained * (1 + width)
    meter._reserve(max_comparison_work=work, max_work_units=work)
    return any(a.candidate_id == b.candidate_id for a in overflow for b in candidates)


def primitive_plan(observations, candidate_kind):
    meter = selected()
    if meter is None:
        return
    count = meter._tuple(observations)
    meter._reserve(max_work_units=count)
    tuples = 1 + 2 * count
    slots = 4 * count
    scan = count
    for item in observations:
        meter._exact(item, candidate_kind)
        meter._exact(item.candidate, CandidateRecordV1)
        meter._text(item.candidate.candidate_id)
        meter._text(item.candidate.value)
        count_slots = meter._tuple(item.slots)
        scan += meter._walk(item.slots)
        tuples += 2 * count_slots
        slots += 3 * count_slots
        for slot in item.slots:
            size = meter._tuple(slot.facts)
            tuples += size
            slots += 8 * size
    meter._reserve(max_primitive_tuples=tuples, max_temporary_slots=4 * (slots + tuples),
                   max_work_units=4 * (slots + tuples) + scan)
