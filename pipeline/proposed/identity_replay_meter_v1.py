"""Opt-in logical cost meter for selected candidate-identity operations."""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
from dataclasses import dataclass, fields
from decimal import Decimal
from enum import Enum
from functools import cache, wraps
from math import isfinite
import sys
from threading import current_thread
from types import MemberDescriptorType, UnionType
from typing import ClassVar, get_args, get_origin, get_type_hints

from pipeline.proposed.owned_numeric_producer_v1 import (
    OwnedNumericErrorV1,
    current_owned_numeric_scope_v1,
)


class IdentityReplayMeterCodeV1(str, Enum):
    INVALID_PROFILE = "INVALID_PROFILE"
    INVALID_SCOPE = "INVALID_SCOPE"
    FOREIGN_SCOPE = "FOREIGN_SCOPE"
    SCOPE_CLOSED = "SCOPE_CLOSED"
    INVALID_SHAPE = "INVALID_SHAPE"
    ACTIVE_PATH_CYCLE = "ACTIVE_PATH_CYCLE"
    INVALID_TEXT = "INVALID_TEXT"
    NUMERIC_OWNERSHIP = "NUMERIC_OWNERSHIP"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    UNSUPPORTED_RUNTIME = "UNSUPPORTED_RUNTIME"


class IdentityReplayMeterErrorV1(RuntimeError):
    def __init__(self, code: IdentityReplayMeterCodeV1, limit: str | None = None):
        self.code = code
        self.limit = limit
        super().__init__(code.value if limit is None else f"{code.value}: {limit}")


@dataclass(frozen=True, slots=True, kw_only=True)
class IdentityReplayMeterProfileV1:
    version: ClassVar[str] = "identity-replay-meter-v1"
    profile_id: ClassVar[str] = "pantryproof-d3-s02-id01-logical-v1"
    cost_revision: ClassVar[str] = "id02"

    max_depth: int
    max_tuple_arity: int
    max_text_codepoints: int
    max_int_bits: int
    max_decimal_digits: int
    max_decimal_exponent: int
    max_groups: int
    max_contributions: int
    max_occurrences: int
    max_comparison_work: int
    max_temporary_slots: int
    max_records: int
    max_preimage_bytes: int
    max_canonical_bytes: int
    max_hash_calls: int
    max_work_units: int


_CONSUMED = (
    "max_occurrences", "max_comparison_work", "max_temporary_slots",
    "max_records", "max_canonical_bytes", "max_hash_calls", "max_work_units",
    "max_groups", "max_contributions",
)
_ACTIVE: ContextVar[IdentityReplayMeterScopeV1 | None] = ContextVar(
    "identity_replay_meter_v1", default=None,
)
_Code = IdentityReplayMeterCodeV1
_NONE = type(None)
_C0_RUNTIME = (
    "3.13.7 (tags/v3.13.7:bcee1c3, Aug 14 2025, 14:15:11) "
    "[MSC v.1944 64 bit (AMD64)]"
)


def _set_probe_bound(capacity: int) -> int:
    # 13 rounds to exhaust a 64-bit perturb value shifted by five, then
    # a full period of the 5*i+1 recurrence on the power-of-two table.
    # The inspected base slot is included in the linear run.
    return (13 + capacity) * (10 if capacity >= 10 else 1)


def _execution_owner() -> tuple[object, object]:
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    return current_thread(), task


@cache
def _shapes():
    # These are the declared comparison subgraphs at the selected sites.
    # Imports run only on first explicit use of the synthetic meter.
    from pipeline import contracts as base
    from pipeline.proposed import candidate_identity as identity
    from pipeline.proposed import candidate_deduplication as dedup
    from pipeline.proposed import candidate_generation as generation
    from pipeline.proposed import contracts as shared

    records = (
        base.Point, base.OcrSourceToken, base.SourceEvidenceGateResult, base.StructuredField,
        shared.SourceCharacterSpanV1, shared.B3CompatibleSeedV1, shared.MethodReadyFieldV1,
        shared.CandidateProvenanceV1, shared.PreliminaryRankV1, shared.CandidateRecordV1,
        generation.AlteredCandidateProposalV0, dedup.CandidateNormalizationV0,
        dedup.DeduplicatedAlteredGroupV0, dedup.EquivalentToC0AuditV0,
        identity.AlteredCandidateIdentityDraftV0, identity.ProposalProvenanceAuditV0,
        identity.AlteredCandidateProvenanceAuditV0,
    )
    enum_types = (
        base.ReceiptFieldName, base.FieldStatus, base.SourceProcessingStatus,
        base.ReceiptExtractionStatus, base.SourceEvidenceDecision,
        shared.CandidateSourceKind, shared.CandidateRole, shared.CandidateLimitStatus,
        dedup.NormalizationParseStatusV0, identity.ProvenanceProjectionClassificationV0,
    )
    numbers = {(base.Point, "x"), (base.Point, "y"), (base.OcrSourceToken, "raw_confidence"),
               (base.StructuredField, "confidence")}
    layouts = {}
    for record in records:
        hints = get_type_hints(record)
        layout = []
        for field in fields(record):
            if not field.compare:
                continue
            slot = vars(record)[field.name]
            if type(slot) is not MemberDescriptorType:
                raise IdentityReplayMeterErrorV1(_Code.INVALID_SHAPE)
            hint = hints[field.name]
            if (record, field.name) in numbers:
                hint = (int | float) if hint is float else (int | float | None)
            layout.append((slot, hint))
        layouts[id(record)] = tuple(layout)
    return layouts, {id(kind): tuple(kind) for kind in enum_types}


def _matches(kind: type, hint: object) -> bool:
    if hint is None or kind is hint:
        return True
    origin = get_origin(hint)
    if origin is UnionType:
        return any(_matches(kind, alternative) for alternative in get_args(hint))
    return kind is tuple and origin is tuple


def _escaped_width(char: str) -> int:
    value = ord(char)
    if 0xD800 <= value <= 0xDFFF:
        return 0
    if char in '\"\\\b\f\n\r\t':
        return 2
    if value < 32:
        return 6
    return 1 if value < 128 else 2 if value < 2048 else 3 if value < 65536 else 4


class IdentityReplayMeterScopeV1:
    """Exclusive synchronous selection and an inclusive, cumulative ledger."""

    def __init__(self, *, profile: IdentityReplayMeterProfileV1):
        if type(profile) is not IdentityReplayMeterProfileV1:
            raise IdentityReplayMeterErrorV1(_Code.INVALID_PROFILE)
        self._limits = {}
        for field in fields(profile):
            value = getattr(profile, field.name)
            if type(value) is not int or value < 1 or value.bit_length() > 31:
                raise IdentityReplayMeterErrorV1(_Code.INVALID_PROFILE)
            self._limits[field.name] = value
        # Canonical validation and generated equality use a recursive runtime.
        if self._limits["max_depth"] > 32:
            raise IdentityReplayMeterErrorV1(_Code.INVALID_PROFILE)
        self._used = dict.fromkeys(_CONSUMED, 0)
        self._owner = _execution_owner()
        self._state = "NEW"
        self._token = None

    @property
    def state(self) -> str:
        return self._state

    def usage(self) -> dict[str, int]:
        if _execution_owner() != self._owner:
            raise IdentityReplayMeterErrorV1(_Code.FOREIGN_SCOPE)
        return self._used.copy()

    def __enter__(self) -> IdentityReplayMeterScopeV1:
        if self._state != "NEW" or _ACTIVE.get() is not None or _execution_owner() != self._owner:
            raise IdentityReplayMeterErrorV1(_Code.INVALID_SCOPE)
        _shapes()
        self._token = _ACTIVE.set(self)
        self._state = "OPEN"
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if _execution_owner() != self._owner or _ACTIVE.get() is not self:
            raise IdentityReplayMeterErrorV1(_Code.INVALID_SCOPE)
        _ACTIVE.reset(self._token)
        self._token = None
        self._state = "FAILED" if exc_type or self._state == "FAILED" else "CLOSED"

    def _check_open(self) -> None:
        if _execution_owner() != self._owner:
            raise IdentityReplayMeterErrorV1(_Code.FOREIGN_SCOPE)
        if self._state != "OPEN" or _ACTIVE.get() is not self:
            raise IdentityReplayMeterErrorV1(_Code.SCOPE_CLOSED)

    def _reject(self, code: IdentityReplayMeterCodeV1, limit: str | None = None):
        self._state = "FAILED"
        raise IdentityReplayMeterErrorV1(code, limit)

    def reserve(self, **charges: int) -> None:
        """Reserve internal logical units before dispatch."""
        self._check_open()
        for key, amount in charges.items():
            if key not in self._used or type(amount) is not int or amount < 0:
                self._reject(_Code.INVALID_PROFILE)
            if amount > self._limits[key] - self._used[key]:
                self._reject(_Code.RESOURCE_LIMIT, key)
        for key, amount in charges.items():
            self._used[key] += amount

    def _limit(self, key: str, amount: int) -> None:
        if amount > self._limits[key]:
            self._reject(_Code.RESOURCE_LIMIT, key)

    def _text_length(self, value: str) -> int:
        if type(value) is not str:
            self._reject(_Code.INVALID_SHAPE)
        size = len(value)
        self._limit("max_text_codepoints", size)
        return size

    def _scalar_weight(self, value: object) -> int:
        if type(value) is str:
            return 1 + self._text_length(value)
        if type(value) is bool or value is None:
            return 1
        if type(value) is int:
            width = int.bit_length(value)
            self._limit("max_int_bits", width)
            return 1 + width
        self._reject(_Code.INVALID_SHAPE)

    def _string_set_cost(self, values: tuple[str, ...]) -> tuple[int, int, int]:
        """Return work, comparison work and slots for one transient set."""
        if type(values) is not tuple:
            self._reject(_Code.INVALID_SHAPE)
        count = len(values)
        self._limit("max_tuple_arity", count)
        self.reserve(max_work_units=1 + count)
        total = longest = 0
        for value in values:
            size = self._text_length(value)
            total += size
            longest = max(longest, size)

        # Growth depends on the number of distinct successful insertions.
        # All distinct is the longest growth schedule. Duplicates and aliases
        # still pay for an insertion attempt, including a cold hash allowance.
        capacity = table_entries = 8
        resize_work = resize_scratch = 0
        while True:
            self.reserve(max_work_units=1)
            trigger = (3 * (capacity - 1) + 4) // 5
            if trigger > count:
                break
            old_capacity = capacity
            factor = 2 if trigger > 50000 else 4
            width = (factor * trigger).bit_length()
            capacity = 1 << width
            table_entries += capacity
            resize_work += old_capacity + width + trigger * _set_probe_bound(capacity)
            resize_scratch += 8

        probes = count if count <= 1 else count * _set_probe_bound(capacity)
        # An unequal exact Unicode key may take the fast comparison and then
        # the rich comparison. Reserve both even for occupied nonmatching hashes.
        comparisons = 0 if count <= 1 else 2 * probes * (2 + 2 * longest)
        work = count + 4 * total + probes + comparisons + table_entries + capacity + resize_work
        return work, comparisons, 2 * (table_entries + resize_scratch)

    def reserve_c0_constructors(
        self, *, provenance_id: str, receipt_id: str, field_id: str,
        candidate_id: str, value: str, normalized_key: str,
        source_token_ids: tuple[str, ...], record_version: str,
    ) -> None:
        """Prepay both unchanged shared constructor bodies on the c0 route."""
        self._check_open()
        if (sys.implementation.name != "cpython" or sys.version != _C0_RUNTIME
                or sys.maxsize != (1 << 63) - 1 or not sys._is_gil_enabled()
                or (sys.hash_info.width, sys.hash_info.algorithm, sys.hash_info.cutoff)
                != (64, "siphash13", 0)):
            self._reject(_Code.UNSUPPORTED_RUNTIME)
        self.reserve(max_work_units=7)
        p = self._text_length(provenance_id)
        r = self._text_length(receipt_id)
        f = self._text_length(field_id)
        c = self._text_length(candidate_id)
        v = self._text_length(value)
        k = self._text_length(normalized_key)
        version = self._text_length(record_version)
        source_work, source_compare, source_slots = self._string_set_cost(source_token_ids)
        self.reserve(max_temporary_slots=1, max_work_units=1)
        id_work, id_compare, id_slots = self._string_set_cost((provenance_id,))

        # One provenance record with no spans and no optional strings, then
        # one ORIGINAL candidate with that single provenance and no rank.
        strip_chars = p + 2 * (r + f + v) + 3 * c + k
        field_compare = 12 + 2 * (r + f + 2 * c + 2 * version)
        comparisons = source_compare + id_compare + field_compare
        self.reserve(
            max_records=2,
            max_comparison_work=comparisons,
            max_temporary_slots=27 + strip_chars + source_slots + id_slots,
            max_work_units=(27 + 32 + 11 + 2 * strip_chars + field_compare
                            + source_work + id_work),
        )

    def _decimal_cost(self, value: Decimal) -> int:
        failed = False
        try:
            owner = current_owned_numeric_scope_v1()
            if owner is None:
                failed = True
            else:
                owner.require_owned(value)
                profile = owner.inspect_capacity_v1().profile
        except OwnedNumericErrorV1:
            failed = True
        if failed:
            self._reject(_Code.NUMERIC_OWNERSHIP)
        self._limit("max_decimal_digits", profile.max_coefficient_digits)
        self._limit("max_decimal_exponent", profile.max_exponent_magnitude)
        return profile.max_coefficient_digits + profile.max_exponent_magnitude.bit_length()

    def walk(self, root: object, hint: object = None, *, canonical: bool = False) -> int:
        """Prepay a bounded storage walk and return a scalar-weighted visit count."""
        # Two empty lists plus a four-slot frame stored in the stack.
        self.reserve(max_temporary_slots=7, max_work_units=1)
        pending = [(root, hint, 0, False)]
        active = []
        weight = 0
        encoded = 0
        layouts, enums = _shapes()
        while pending:
            value, expected, depth, leave = pending.pop()
            if leave:
                active.pop()
                continue
            self.reserve(max_occurrences=1, max_work_units=1 + len(active))
            ident = id(value)
            if ident in active:
                self._reject(_Code.ACTIVE_PATH_CYCLE)
            self._limit("max_depth", depth)
            kind = type(value)
            if not _matches(kind, expected):
                self._reject(_Code.INVALID_SHAPE)
            weight += 1
            if kind is str:
                size = len(value)
                self._limit("max_text_codepoints", size)
                weight += size
                if canonical:
                    self.reserve(max_work_units=size)
                    encoded += 2
                    for char in value:
                        width = _escaped_width(char)
                        if not width:
                            self._reject(_Code.INVALID_TEXT)
                        encoded += width
            elif not canonical and kind is int:
                width = int.bit_length(value)
                self._limit("max_int_bits", width)
                weight += width
            elif not canonical and kind is float:
                if not isfinite(value):
                    self._reject(_Code.INVALID_SHAPE)
                weight += 64
            elif not canonical and (kind is bool or kind is _NONE):
                pass
            elif not canonical and kind is Decimal:
                self.reserve(max_work_units=1)
                weight += self._decimal_cost(value)
            elif not canonical and id(kind) in enums:
                members = enums[id(kind)]
                self.reserve(max_work_units=len(members))
                if not any(value is member for member in members):
                    self._reject(_Code.INVALID_SHAPE)
                weight += len(value.value)
            elif kind is tuple or (not canonical and id(kind) in layouts):
                is_tuple = kind is tuple
                size = len(value) if is_tuple else len(layouts[id(kind)])
                if is_tuple:
                    self._limit("max_tuple_arity", size)
                self.reserve(max_temporary_slots=6 + 5 * size, max_work_units=1 + size)
                active.append(ident)
                pending.append((value, None, depth, True))
                if is_tuple:
                    if canonical:
                        encoded += 2 + max(0, size - 1)
                    if get_origin(expected) is UnionType:
                        expected = next(h for h in get_args(expected) if _matches(tuple, h))
                    items = get_args(expected)
                    repeated = len(items) == 2 and items[1] is Ellipsis
                    if items and not repeated and len(items) != size:
                        self._reject(_Code.INVALID_SHAPE)
                    for index in range(size - 1, -1, -1):
                        hint = items[0 if repeated else index] if items else None
                        pending.append((value[index], hint, depth + 1, False))
                else:
                    for slot, child_hint in reversed(layouts[id(kind)]):
                        try:
                            child = slot.__get__(value, kind)
                        except AttributeError:
                            child = _MISSING
                        if child is _MISSING:
                            self._reject(_Code.INVALID_SHAPE)
                        pending.append((child, child_hint, depth + 1, False))
            else:
                self._reject(_Code.INVALID_SHAPE)
            if canonical:
                self._limit("max_preimage_bytes", encoded)
        return encoded if canonical else weight


_MISSING = object()


def selected_meter() -> IdentityReplayMeterScopeV1 | None:
    meter = _ACTIVE.get()
    if meter is not None:
        meter._check_open()
    return meter


def identity_operation(function):
    @wraps(function)
    def invoke(*args, **kwargs):
        meter = selected_meter()
        if meter is None:
            return function(*args, **kwargs)
        try:
            return function(*args, **kwargs)
        except BaseException:
            meter._state = "FAILED"
            raise
    return invoke


def reserve_identity(**charges: int) -> None:
    meter = selected_meter()
    if meter is not None:
        meter.reserve(**charges)


def identity_not_equal(left: object, right: object) -> bool:
    meter = selected_meter()
    if meter is not None:
        work = meter.walk(left) + meter.walk(right)
        meter.reserve(max_comparison_work=work, max_work_units=work)
    return left != right


def _reserve_scalar_comparison(left: object, right: object) -> None:
    meter = selected_meter()
    if meter is not None:
        meter.reserve(max_work_units=1)
        work = meter._scalar_weight(left) + meter._scalar_weight(right)
        meter.reserve(max_comparison_work=work, max_work_units=work)


def identity_scalar_equal(left: object, right: object) -> bool:
    _reserve_scalar_comparison(left, right)
    return left == right


def identity_scalar_not_equal(left: object, right: object) -> bool:
    _reserve_scalar_comparison(left, right)
    return left != right


def identity_missing_member(value: object, members: tuple) -> bool:
    meter = selected_meter()
    if meter is not None:
        if type(members) is not tuple:
            meter._reject(_Code.INVALID_SHAPE)
        member_weight = meter.walk(members)
        work = member_weight + len(members) * meter.walk(value)
        meter.reserve(max_comparison_work=work, max_work_units=work)
    return value not in members
