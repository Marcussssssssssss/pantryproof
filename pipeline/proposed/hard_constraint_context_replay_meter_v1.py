"""Opt-in logical accounting for stored hard-constraint input preparation."""

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
from pipeline import contracts as b2
from pipeline.layout_b2 import B2ExtractionResult
from . import finalization_replay_meter_v1 as finalization
from .adapter import ProposedAdapterResultV1
from .contracts import B3CompatibleSeedV1, ConfigurationRefV1, MethodReadyFieldV1
from .contracts import CandidateProvenanceV1, CandidateRecordV1
from .owned_numeric_producer_v1 import (
    OwnedNumericErrorCodeV1,
    OwnedNumericErrorV1,
    current_owned_numeric_scope_v1,
)


class HardConstraintContextReplayCodeV1(str, Enum):
    INVALID_PROFILE = "INVALID_PROFILE"
    INVALID_SCOPE = "INVALID_SCOPE"
    FOREIGN_SCOPE = "FOREIGN_SCOPE"
    SCOPE_CLOSED = "SCOPE_CLOSED"
    FINALIZATION_SCOPE_REQUIRED = "FINALIZATION_SCOPE_REQUIRED"
    INVALID_SHAPE = "INVALID_SHAPE"
    ACTIVE_PATH_CYCLE = "ACTIVE_PATH_CYCLE"
    INVALID_NUMERIC_OWNERSHIP = "INVALID_NUMERIC_OWNERSHIP"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"


class HardConstraintContextReplayErrorV1(RuntimeError):
    def __init__(self, code: HardConstraintContextReplayCodeV1, limit: str | None = None):
        if type(code) is not HardConstraintContextReplayCodeV1:
            raise TypeError("Invalid hard-constraint context replay error code.")
        if code is _Code.RESOURCE_LIMIT:
            if type(limit) is not str or limit not in _LIMIT_FIELDS:
                raise TypeError("Invalid hard-constraint context replay limit name.")
        elif limit is not None:
            raise TypeError("Only a resource refusal names a hard-constraint context replay limit.")
        self.code = code
        self.limit = limit
        super().__init__(code.value if limit is None else f"{code.value}: {limit}")


@dataclass(frozen=True, slots=True, kw_only=True)
class HardConstraintContextReplayProfileV1:
    """All limits are explicit and inclusive."""

    version: ClassVar[str] = "hard-constraint-context-replay-meter-v1"
    max_int_bits: int
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
    max_receipt_token_rebuilds: int
    max_lookup_pairs: int
    max_validations: int
    max_shared_validations: int
    max_provenance_validations: int
    max_member_occurrences: int
    max_set_probes: int
    max_uniqueness_pairs: int
    max_occurrences: int
    max_comparison_work: int
    max_records: int
    max_temporary_slots: int
    max_work_units: int


_Code = HardConstraintContextReplayCodeV1
_LIMIT_FIELDS = tuple(item.name for item in fields(HardConstraintContextReplayProfileV1))
_PER_VALUE = _LIMIT_FIELDS[:5]
_ACTIVE: ContextVar[HardConstraintContextReplayScopeV1 | None] = ContextVar(
    "hard_constraint_context_replay_meter_v1", default=None
)


@cache
def _layouts():
    # Share the pinned exact field vocabulary, never the upstream ledgers.
    base_records, base_enums = finalization._layouts()
    records, enums = base_records.copy(), base_enums.copy()
    for kind in (
        b2.SourceProvenance, b2.ReceiptSourceEvidence, b2.ReceiptItemRow,
        b2.ReceiptOutput, b2.PreResolutionDisposition, B2ExtractionResult,
        B3CompatibleSeedV1, ProposedAdapterResultV1,
    ):
        layout = []
        hints = get_type_hints(kind)
        for item in fields(kind):
            if item.compare:
                slot = vars(kind)[item.name]
                if type(slot) is not MemberDescriptorType:
                    raise HardConstraintContextReplayErrorV1(_Code.INVALID_SHAPE)
                layout.append((slot, hints[item.name]))
        records[id(kind)] = tuple(layout)
    for kind in (
        b2.OutputStage, b2.PolicyState, b2.FailureStage,
    ):
        enums[id(kind)] = tuple(kind)
    return records, enums


class HardConstraintContextReplayScopeV1:
    """A single-use local ledger owned by the creating thread and task."""

    def __init__(self, *, profile: HardConstraintContextReplayProfileV1):
        if type(profile) is not HardConstraintContextReplayProfileV1:
            raise HardConstraintContextReplayErrorV1(_Code.INVALID_PROFILE)
        limits = {name: getattr(profile, name, None) for name in _LIMIT_FIELDS}
        if any(type(limit) is not int or not 1 <= limit < 2**31 for limit in limits.values()):
            raise HardConstraintContextReplayErrorV1(_Code.INVALID_PROFILE)
        if not (
            limits["max_depth"] <= 32
            and limits["max_int_bits"] <= 64
        ):
            raise HardConstraintContextReplayErrorV1(_Code.INVALID_PROFILE)
        self._limits = limits
        self._used = {name: 0 for name in limits if name not in _PER_VALUE}
        self._owner = identity._execution_owner()
        self._state = "NEW"
        self._finalization = self._numeric = self._numeric_profile = self._token = None

    @property
    def state(self) -> str:
        return self._state

    def usage(self) -> dict[str, int]:
        self._check_owner()
        return self._used.copy()

    def _check_owner(self) -> None:
        if identity._execution_owner() != self._owner:
            raise HardConstraintContextReplayErrorV1(_Code.FOREIGN_SCOPE)

    def __enter__(self) -> HardConstraintContextReplayScopeV1:
        self._check_owner()
        if self._state != "NEW" or _ACTIVE.get() is not None:
            raise HardConstraintContextReplayErrorV1(_Code.INVALID_SCOPE)
        try:
            fn01 = finalization.selected()
            if type(fn01) is not finalization.FinalizationReplayScopeV1:
                self._reject(_Code.FINALIZATION_SCOPE_REQUIRED)
            owner = current_owned_numeric_scope_v1()
            profile = owner.inspect_capacity_v1().profile
            _layouts()
        except BaseException:
            self._state = "FAILED"
            raise
        self._finalization, self._numeric, self._numeric_profile = fn01, owner, profile
        self._token = _ACTIVE.set(self)
        self._state = "OPEN"
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._check_owner()
        if _ACTIVE.get() is not self:
            raise HardConstraintContextReplayErrorV1(_Code.INVALID_SCOPE)
        _ACTIVE.reset(self._token)
        self._finalization = self._numeric = self._numeric_profile = self._token = None
        self._state = "FAILED" if exc_type or self._state == "FAILED" else "CLOSED"

    def _check(self) -> None:
        self._check_owner()
        if self._state != "OPEN" or _ACTIVE.get() is not self:
            raise HardConstraintContextReplayErrorV1(_Code.SCOPE_CLOSED)
        try:
            if finalization.selected() is not self._finalization:
                self._reject(_Code.FINALIZATION_SCOPE_REQUIRED)
        except BaseException:
            self._state = "FAILED"
            raise

    def _reject(self, code: HardConstraintContextReplayCodeV1, limit: str | None = None):
        self._state = "FAILED"
        raise HardConstraintContextReplayErrorV1(code, limit)

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


def selected() -> HardConstraintContextReplayScopeV1 | None:
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
               comparison: int = 0) -> None:
    reserve(max_validations=1, max_scan_items=scans,
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


def _membership(count: int, searches: int, width: int, *, hashed: bool = False) -> None:
    if not searches:
        return
    # Use the same full-period bound even for a missing key and an empty set.
    capacity = 8 if count < 5 else 1 << (4 * count).bit_length()
    pairs = searches * (identity._set_probe_bound(capacity) if hashed else count)
    work = 2 * pairs * (2 + 2 * width)
    hashing = 4 * searches * width if hashed else 0
    reserve(max_lookup_pairs=pairs, max_comparison_work=work,
            max_work_units=work + searches + pairs + hashing,
            max_set_probes=pairs if hashed else 0)


def validate_plain(record, kind) -> None:
    meter = selected()
    if meter is not None:
        _validator(meter._walk(record, kind))
    record.__post_init__()


def admit_method_relationships(method, adapter, suspicion_method) -> None:
    meter = selected()
    if meter is not None:
        meter._walk(method, MethodReadyFieldV1)
        meter._walk(suspicion_method, MethodReadyFieldV1)
        # B2 is fully admitted at the stored-receipt boundary. The matching
        # scan only reads these exact declared collections beforehand.
        meter._walk(adapter.method_ready_fields, tuple[MethodReadyFieldV1, ...])
        meter._walk(adapter.excluded_b2_field_ids, tuple[str, ...])
        sequence(len(adapter.method_ready_fields))


def _reserve_adapter(adapter) -> None:
    meter = selected()
    weight = meter._walk(adapter, ProposedAdapterResultV1)
    m, e, b = len(adapter.method_ready_fields), len(adapter.excluded_b2_field_ids), len(adapter.b3_seeds)
    width = max(len(adapter.receipt_id), _longest_field_id(adapter))
    _set((item.field_id for item in adapter.method_ready_fields), m, repeats=2)
    _set(adapter.excluded_b2_field_ids, e)
    _set((item.seed_id for item in adapter.b3_seeds), b)
    _membership(m, b, width, hashed=True)
    _validator(weight, scans=3 * m + e + 3 * b,
               comparison=2 * (m + b) * (1 + meter._text(adapter.receipt_id)))


def _longest_field_id(adapter):
    # The caller charges both traversals before taking the maximum.
    scan(len(adapter.method_ready_fields) + len(adapter.b3_seeds))
    return max(
        max((len(item.field_id) for item in adapter.method_ready_fields), default=0),
        max((len(item.field_id) for item in adapter.b3_seeds), default=0),
    )


def _reserve_method(method) -> None:
    meter = selected()
    weight = meter._walk(method, MethodReadyFieldV1)
    _set(method.source_token_ids, len(method.source_token_ids))
    _set(method.b3_seed_ids, len(method.b3_seed_ids))
    n = len(method.source_tokens)
    _validator(weight, scans=2 * n, slots=n,
               comparison=2 * n * (1 + len(method.receipt_id)))


def _receipt_field_values(output):
    yield output.store_name
    yield output.purchase_date
    for row in output.items:
        yield row.description
        yield row.quantity
        yield row.unit_price
        yield row.line_total
    yield output.receipt_total


def _receipt_dimensions(output) -> tuple[int, int, int, int]:
    evidence = output.source_evidence
    rows, tokens = len(output.items), len(evidence.tokens)
    scan(tokens)
    points = sum(len(token.polygon) for token in evidence.tokens)
    reserve(max_temporary_slots=4, max_work_units=4)
    return rows, 3 + 4 * rows, tokens, points


def preflight_stored_b2(adapter) -> None:
    meter = selected()
    if meter is None:
        return
    b2_result = adapter.original_b2_result
    meter._walk(b2_result, B2ExtractionResult)
    if b2_result.receipt_output is not None:
        rows, fields, tokens, points = _receipt_dimensions(b2_result.receipt_output)
        meter._cap("max_tuple_arity", fields)
        meter._require_capacity(max_receipt_fields=fields, max_receipt_rows=rows,
                                max_receipt_tokens=tokens, max_polygon_points=points)


def _reserve_receipt(output) -> None:
    meter = selected()
    weight = meter._walk(output, b2.ReceiptOutput)
    evidence = output.source_evidence
    rows, fields, tokens, points = _receipt_dimensions(output)
    meter._cap("max_tuple_arity", fields)
    meter._reserve(max_receipt_fields=fields, max_receipt_rows=rows,
                   max_receipt_tokens=tokens, max_polygon_points=points)
    _set((row.row_id for row in output.items), rows)
    _set((field.field_id for field in _receipt_field_values(output)), fields)
    references = longest = 0
    scan(fields)
    for field in _receipt_field_values(output):
        sequence_count = len(field.source_token_ids)
        scan(sequence_count)
        references += sequence_count
        longest = max(longest, max(map(len, field.source_token_ids), default=0))
    meter._reserve(max_receipt_token_rebuilds=references)
    _set((token.token_id for token in evidence.tokens), tokens, repeats=references)
    scan(tokens)
    longest = max(longest, max((len(token.token_id) for token in evidence.tokens), default=0))
    _membership(tokens, references, longest, hashed=True)
    # All references may be unknown. Price the transient set, its sorted
    # error list and the escaped exact-string diagnostics before dispatch.
    unknown_work, unknown_compare, unknown_slots, unknown_probes = (
        finalization._shared_set_cost(references, references * longest, longest)
    )
    # CPython's merge count is at most R-1. The bound allows 16 full
    # comparison passes per merge, including gallops and run setup.
    sort_pairs = 16 * references * (references + 1)
    diagnostic = 32 + references * (16 + 10 * longest)
    meter._reserve(
        max_set_probes=unknown_probes, max_lookup_pairs=sort_pairs,
        max_comparison_work=unknown_compare + sort_pairs * (2 + 2 * longest),
        max_temporary_slots=unknown_slots + 3 * references + 2 * diagnostic,
        max_work_units=unknown_work + sort_pairs * (4 + 2 * longest) + 3 * diagnostic,
    )
    _validator(weight, scans=rows + 3 * fields + references,
               slots=rows + 2 * fields + 4 * rows,
               comparison=2 * rows * (1 + len(output.receipt_id)))


def validate_adapter(adapter) -> None:
    if selected() is not None:
        _reserve_adapter(adapter)
    adapter.__post_init__()


def validate_method(method) -> None:
    if selected() is not None:
        _reserve_method(method)
    method.__post_init__()


def validate_receipt(output) -> None:
    if selected() is not None:
        _reserve_receipt(output)
    output.__post_init__()


def validate_evidence(evidence) -> None:
    meter = selected()
    if meter is not None:
        weight = meter._walk(evidence, b2.ReceiptSourceEvidence)
        n = len(evidence.tokens)
        _set((token.token_id for token in evidence.tokens), n)
        _validator(weight, scans=2 * n, slots=n,
                   comparison=2 * n * (1 + len(evidence.receipt_id)))
    evidence.__post_init__()


def validate_gate(gate) -> None:
    meter = selected()
    if meter is not None:
        weight = meter._walk(gate, b2.SourceEvidenceGateResult)
        _set(gate.reasons, len(gate.reasons))
        _validator(weight)
    gate.__post_init__()


def validate_field(field) -> None:
    meter = selected()
    if meter is not None:
        weight = meter._walk(field, b2.StructuredField)
        _set(field.source_token_ids, len(field.source_token_ids))
        _validator(weight)
    field.__post_init__()


def validate_candidate(candidate) -> None:
    meter = selected()
    if meter is not None:
        weight = meter._walk(candidate, CandidateRecordV1)
        n = len(candidate.provenance)
        _set((member.provenance_id for member in candidate.provenance), n)
        _validator(weight, scans=3 * n, slots=n, comparison=4 * n * sum(
            1 + len(key) for key in (candidate.candidate_id, candidate.receipt_id, candidate.field_id)
        ))
        meter._reserve(max_shared_validations=1, max_member_occurrences=n)
    candidate.__post_init__()


def validate_provenance(provenance) -> None:
    meter = selected()
    if meter is not None:
        weight = meter._walk(provenance, CandidateProvenanceV1)
        tokens, spans = provenance.source_token_ids, provenance.source_spans
        n, s = len(tokens), len(spans)
        _set(tokens, n)
        scan(n + s)
        width = max(max(map(len, tokens), default=0),
                    max((len(span.token_id) for span in spans), default=0))
        _membership(n, s, width)
        _validator(weight, scans=s, slots=s)
        meter._reserve(max_provenance_validations=1, max_member_occurrences=1)
    provenance.__post_init__()


def excluded(field_id, excluded_ids) -> bool:
    if selected() is None:
        return field_id in excluded_ids
    scan(len(excluded_ids))
    for item in excluded_ids:
        reserve(max_lookup_pairs=1)
        if equal(field_id, item):
            return True
    return False


def token_lookup(tokens, token_id):
    scan(len(tokens))
    for token in tokens:
        reserve(max_lookup_pairs=1)
        if equal(token.token_id, token_id):
            return token
    return None


def has_overlap(overflow, candidate_ids) -> bool:
    if selected() is None:
        return bool({candidate.candidate_id for candidate in overflow}.intersection(candidate_ids))
    scan(len(overflow))
    for candidate in overflow:
        scan(len(candidate_ids))
        for candidate_id in candidate_ids:
            reserve(max_lookup_pairs=1)
            if equal(candidate.candidate_id, candidate_id):
                return True
    return False

