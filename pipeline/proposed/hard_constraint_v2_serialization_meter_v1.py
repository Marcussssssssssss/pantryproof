"""Opt-in logical work limits for the existing V2 audit JSON codec."""

from __future__ import annotations

import json
import re
import unicodedata
from contextvars import ContextVar
from dataclasses import dataclass, fields
from decimal import Decimal
from enum import Enum
from functools import wraps
from typing import get_args

from . import hard_constraint_v2_replay_meter_v1 as replay
from .contracts import CandidateProvenanceV1, CandidateRecordV1, PreliminaryRankV1
from .finalization_replay_meter_v1 import _shared_set_cost
from .identity_replay_meter_v1 import _escaped_width, _execution_owner, _matches
from .owned_numeric_producer_v1 import current_owned_numeric_scope_v1


class HardConstraintV2SerializationCodeV1(str, Enum):
    INVALID_PROFILE = "INVALID_PROFILE"
    INVALID_SCOPE = "INVALID_SCOPE"
    FOREIGN_SCOPE = "FOREIGN_SCOPE"
    V201_SCOPE_REQUIRED = "V201_SCOPE_REQUIRED"
    UNSUPPORTED_RUNTIME = "UNSUPPORTED_RUNTIME"
    INVALID_SHAPE = "INVALID_SHAPE"
    ACTIVE_PATH_CYCLE = "ACTIVE_PATH_CYCLE"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"


class HardConstraintV2SerializationMeterErrorV1(RuntimeError):
    def __init__(self, code: HardConstraintV2SerializationCodeV1, limit: str | None = None):
        self.code = code
        self.limit = limit
        super().__init__(code.value if limit is None else f"{code.value}: {limit}")


@dataclass(frozen=True, slots=True)
class HardConstraintV2SerializationProfileV1:
    max_depth: int
    max_integer_bits: int
    max_decimal_coefficient_digits: int
    max_decimal_exponent_magnitude: int
    max_input_codepoints: int
    max_input_utf8_bytes: int
    max_output_codepoints: int
    max_output_utf8_bytes: int
    max_escape_expansion: int
    max_json_tokens: int
    max_array_elements: int
    max_object_members: int
    max_dictionary_slots: int
    max_set_slots: int
    max_key_comparisons: int
    max_records: int
    max_validator_dispatches: int
    max_decimal_recipes: int
    max_temporary_slots: int
    max_work_units: int


_Code = HardConstraintV2SerializationCodeV1
_LIMITS = tuple(field.name for field in fields(HardConstraintV2SerializationProfileV1))
_PER_VALUE = _LIMITS[:4]
_ACTIVE: ContextVar[HardConstraintV2SerializationScopeV1 | None] = ContextVar(
    "hard_constraint_v2_serialization_meter_v1", default=None
)
_FINITE_DECIMAL = re.compile(r"([+-]?)(?:([0-9]+)(?:\.([0-9]*))?|\.([0-9]+))(?:[eE]([+-]?)([0-9]+))?\Z")
_JSON_SPACE = " \t\r\n"
_ENTRY_NAMES = {"encode": "constraint_result_v2_to_json", "decode": "constraint_result_v2_from_json"}


class HardConstraintV2SerializationScopeV1:
    """Single-use, cumulative and bound to one V201 scope, thread and task."""

    def __init__(self, *, profile: HardConstraintV2SerializationProfileV1):
        if type(profile) is not HardConstraintV2SerializationProfileV1:
            raise HardConstraintV2SerializationMeterErrorV1(_Code.INVALID_PROFILE)
        limits = {name: getattr(profile, name, None) for name in _LIMITS}
        if (any(type(value) is not int or not 1 <= value < 2**31 for value in limits.values())
                or limits["max_depth"] > 32 or limits["max_integer_bits"] > 64):
            raise HardConstraintV2SerializationMeterErrorV1(_Code.INVALID_PROFILE)
        self._limits = limits
        self._used = dict.fromkeys((name for name in _LIMITS if name not in _PER_VALUE), 0)
        self._owner = _execution_owner()
        self._state = "NEW"
        self._phase = None
        self._token = self._v201 = self._numeric = self._numeric_profile = None

    @property
    def state(self) -> str:
        return self._state

    def usage(self) -> dict[str, int]:
        self._check_owner()
        return self._used.copy()

    def _check_owner(self):
        if self._owner != _execution_owner():
            raise HardConstraintV2SerializationMeterErrorV1(_Code.FOREIGN_SCOPE)

    def __enter__(self):
        self._check_owner()
        if (type(self) is not HardConstraintV2SerializationScopeV1
                or self._state != "NEW" or _ACTIVE.get() is not None):
            raise HardConstraintV2SerializationMeterErrorV1(_Code.INVALID_SCOPE)
        try:
            self._v201 = replay.selected()
            if type(self._v201) is not replay.HardConstraintV2ReplayScopeV1:
                self._reject(_Code.V201_SCOPE_REQUIRED)
            self._numeric = current_owned_numeric_scope_v1()
            self._numeric_profile = self._numeric.inspect_capacity_v1().profile
            if not _native_json_available():
                self._reject(_Code.UNSUPPORTED_RUNTIME)
            replay._layouts()
        except BaseException:
            self._state = "FAILED"
            raise
        self._token = _ACTIVE.set(self)
        self._state = "OPEN"
        return self

    def __exit__(self, exc_type, exc, traceback):
        self._check_owner()
        if _ACTIVE.get() is not self:
            raise HardConstraintV2SerializationMeterErrorV1(_Code.INVALID_SCOPE)
        _ACTIVE.reset(self._token)
        self._token = self._v201 = self._numeric = self._numeric_profile = None
        self._state = "FAILED" if exc_type or self._state == "FAILED" else "CLOSED"

    def _check(self):
        self._check_owner()
        if self._state != "OPEN" or _ACTIVE.get() is not self:
            raise HardConstraintV2SerializationMeterErrorV1(_Code.INVALID_SCOPE)
        try:
            if (replay.selected() is not self._v201
                    or current_owned_numeric_scope_v1() is not self._numeric):
                self._reject(_Code.V201_SCOPE_REQUIRED)
        except BaseException:
            self._state = "FAILED"
            raise

    def _reject(self, code, limit=None):
        self._state = "FAILED"
        raise HardConstraintV2SerializationMeterErrorV1(code, limit)

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


def _codec(direction):
    """The public call owns one direction of the codec until completion."""
    def decorate(function):
        @wraps(function)
        def invoke(*args, **kwargs):
            meter = _ACTIVE.get()
            if meter is None:
                replay.exclude_serialization()
                return function(*args, **kwargs)
            meter._check()
            from . import hard_constraint_contracts_v2 as v2

            if meter._phase is not None or getattr(v2, _ENTRY_NAMES[direction]) is not invoke:
                meter._reject(_Code.INVALID_SCOPE)
            meter._phase = direction
            try:
                result = function(*args, **kwargs)
                meter._check()
                return result
            except BaseException:
                meter._state = "FAILED"
                raise
            finally:
                meter._phase = None

        return invoke
    return decorate


def helper(direction):
    meter = _ACTIVE.get()
    if meter is None:
        replay.exclude_serialization()
    else:
        meter._check()
        if meter._phase != direction:
            meter._reject(_Code.INVALID_SCOPE)
    return meter


def _wire_error(message):
    from .hard_constraint_contracts_v2 import HardConstraintSerializationError

    raise HardConstraintSerializationError(message)


def _native_json_available():
    try:
        import _json
    except ImportError:
        return False
    return (json.encoder.c_make_encoder is _json.make_encoder
            and json.scanner.make_scanner is _json.make_scanner
            and json.decoder.scanstring is _json.scanstring)


def _utf8_width(char):
    point = ord(char)
    if 0xD800 <= point <= 0xDFFF:
        _wire_error("JSON contains a lone surrogate.")
    return 1 if point < 128 else 2 if point < 2048 else 3 if point < 65536 else 4


def _dict_cost(meter, count, characters, width, *, lookups=0):
    # Insertion-only CPython compact dictionaries, including growth and reinsertion.
    if not count and not lookups:
        return
    capacity = max(8, 1 << (4 * count).bit_length())
    probes = capacity + 14  # 64-bit perturb, then a full power-of-two cycle.
    comparisons = (count + lookups) * probes
    growths = capacity.bit_length()
    moves = count * (2 * capacity + 14 * growths + 2 * probes)
    slots = 8 * capacity + 4 * count
    meter._reserve(max_dictionary_slots=slots, max_key_comparisons=comparisons,
                   max_work_units=slots + moves + comparisons * (1 + width) + characters)


def _decimal_digits(number):
    length = 1
    while number >= 10:
        number //= 10
        length += 1
    return length


def _decimal_length(meter, value):
    meter._numeric.require_owned(value)
    width = meter._numeric_profile.max_coefficient_digits
    meter._reserve(max_work_units=8 * width + 64, max_temporary_slots=4 * width + 32)
    sign, digits, exponent = value.as_tuple()
    size = len(digits)
    meter._cap("max_decimal_coefficient_digits", size)
    meter._cap("max_decimal_exponent_magnitude", abs(exponent))
    left = size + exponent
    if exponent == 0:
        return sign + size
    if exponent < 0 and left > -6:
        return sign + size + (1 if left > 0 else 2 - left)
    return sign + size + (size > 1) + 2 + _decimal_digits(abs(left - 1))


def preflight_encode(value, expected):
    meter = helper("encode")
    if meter is None:
        return
    layouts, enums = replay._layouts()
    active = []

    def output(codepoints, byte_count, expansion=0):
        meter._reserve(max_output_codepoints=codepoints, max_output_utf8_bytes=byte_count,
                       max_escape_expansion=expansion, max_temporary_slots=4 * codepoints,
                       max_work_units=codepoints + byte_count)

    def string(value):
        length = len(value)
        meter._reserve(max_work_units=2 * length + 1)
        codepoints = byte_count = 2
        for char in value:
            escaped = _escaped_width(char)
            if not escaped:
                _wire_error("JSON contains a lone surrogate.")
            byte_count += escaped
            codepoints += escaped if ord(char) < 128 else 1
        output(codepoints, byte_count, codepoints - length - 2)

    def visit(value, hint, depth):
        kind = type(value)
        if not _matches(kind, hint):
            meter._reject(_Code.INVALID_SHAPE)
        marker = id(value)
        meter._reserve(max_json_tokens=1, max_work_units=4 + depth, max_temporary_slots=1)
        if marker in active:
            meter._reject(_Code.ACTIVE_PATH_CYCLE)
        if kind is str:
            string(value)
        elif kind is int:
            width = value.bit_length()
            meter._cap("max_integer_bits", width)
            meter._reserve(max_work_units=width + 1)
            length = _decimal_digits(abs(value)) + (value < 0)
            output(length, length)
        elif kind is bool or value is None:
            length = 5 if value is False else 4
            output(length, length)
        elif kind is Decimal:
            length = _decimal_length(meter, value) + 2
            output(length, length)
        elif id(kind) in enums:
            members = enums[id(kind)]
            meter._reserve(max_work_units=len(members))
            if not any(value is item for item in members):
                meter._reject(_Code.INVALID_SHAPE)
            string(value.value)
        else:
            meter._cap("max_depth", depth)
            active.append(marker)
            try:
                if kind is tuple:
                    count = len(value)
                    meter._reserve(max_array_elements=count, max_temporary_slots=4 + 4 * count,
                                   max_work_units=count)
                    punctuation = 2 + max(0, count - 1)
                    output(punctuation, punctuation)
                    # Selected V201 layouts use only homogeneous variadic tuples.
                    item_type = get_args(hint)[0]
                    for item in value:
                        visit(item, item_type, depth + 1)
                elif id(kind) in layouts:
                    layout = layouts[id(kind)]
                    count = len(layout)
                    meter._reserve(max_object_members=count, max_json_tokens=count,
                                   max_work_units=4 * count, max_temporary_slots=8 + 8 * count)
                    characters = sum(len(slot.__name__) for slot, _ in layout)
                    width = max(len(slot.__name__) for slot, _ in layout)
                    _dict_cost(meter, count, characters, width)
                    pairs = 16 * count * (count + 1)
                    meter._reserve(max_key_comparisons=pairs, max_work_units=pairs * (1 + width))
                    punctuation = 2 + count + max(0, count - 1)
                    output(punctuation, punctuation)
                    for slot, item_type in layout:
                        string(slot.__name__)
                        visit(slot.__get__(value), item_type, depth + 1)
                else:
                    meter._reject(_Code.INVALID_SHAPE)
            finally:
                active.pop()

    visit(value, expected, 1)


def _lexical_shape(meter, payload):
    """Count a superset of parser work, including any prefix of malformed JSON."""
    frames = []
    in_string = escaped = atom = key_string = False
    tokens = members = elements = key_width = string_width = 0
    for char in payload:
        if in_string:
            string_width += 1
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
                if key_string:
                    key_width = max(key_width, string_width - 1)
            continue
        if char == '"':
            in_string, atom, string_width = True, False, 0
            key_string = bool(frames and frames[-1][0] == "{" and frames[-1][3])
            if key_string:
                frames[-1][3] = False
            tokens += 1
        elif char in "[{":
            tokens += 1
            atom = False
            meter._cap("max_depth", len(frames) + 1)
            meter._reserve(max_temporary_slots=8)
            frames.append([char, 0, False, True])
            continue
        elif char in "]}":
            atom = False
            if not frames or (frames[-1][0] == "[") != (char == "]"):
                _wire_error("Invalid JSON container structure.")
            opening, commas, nonempty, _ = frames.pop()
            if opening == "[":
                elements += commas + nonempty
            else:
                members += commas + nonempty
        elif char == ",":
            atom = False
            if frames:
                frames[-1][1] += 1
                frames[-1][3] = True
        elif char == ":" or char in _JSON_SPACE:
            atom = False
            continue
        elif not atom:
            atom = True
            tokens += 1
        if frames:
            frames[-1][2] = True
    if frames or in_string:
        _wire_error("Incomplete JSON container or string.")
    return tokens, members, elements, key_width


def load_json(payload, pairs_hook):
    meter = helper("decode")
    if meter is None:
        return json.loads(payload, object_pairs_hook=pairs_hook)
    if type(payload) is not str:
        meter._reject(_Code.INVALID_SHAPE)
    size = len(payload)
    meter._reserve(max_input_codepoints=size, max_work_units=8 * size + 32)
    meter._reserve(max_input_utf8_bytes=sum(_utf8_width(char) for char in payload))
    tokens, members, elements, width = _lexical_shape(meter, payload)
    meter._reserve(max_json_tokens=tokens, max_object_members=members, max_array_elements=elements,
                   max_temporary_slots=4 * size + 8 * tokens + 4 * members + 4 * elements,
                   max_work_units=16 * size + 8 * tokens + 8 * members + 8 * elements)
    _dict_cost(meter, members, 4 * size, width)  # _json's parser-wide name memo.
    return json.loads(payload, object_pairs_hook=pairs_hook,
                      parse_int=_parse_integer, parse_float=_reject_json_number,
                      parse_constant=_reject_json_number)


def _reject_json_number(_):
    helper("decode")
    _wire_error("Unexpected JSON numeric literal.")


def _parse_integer(text):
    meter = helper("decode")
    length = len(text)
    meter._reserve(max_work_units=length + 1)
    negative = text[0] == "-"
    value = 0
    for index in range(negative, length):
        value = value * 10 + ord(text[index]) - 48
        meter._cap("max_integer_bits", value.bit_length())
    return -value if negative else value


def unique_object(meter, pairs):
    count = len(pairs)
    characters = width = 0
    meter._reserve(max_work_units=count)
    for key, _ in pairs:
        characters += len(key)
        width = max(width, len(key))
        check_string(meter, key)
    comparisons = count * (count - 1) // 2
    meter._reserve(max_key_comparisons=comparisons, max_work_units=comparisons * (1 + width))
    for index, (key, _) in enumerate(pairs):
        for other in range(index):
            if key == pairs[other][0]:
                _wire_error("Duplicate JSON object key is not permitted.")
    _dict_cost(meter, count, 4 * characters, width)
    return dict(pairs)


def check_object(meter, value, expected, name):
    if type(value) is not dict:
        _wire_error(f"{name} must be a JSON object.")
    if len(value) != len(expected):
        _wire_error(f"{name} fields differ.")
    count = len(expected)
    pairs = count * count
    width = max(map(len, expected))
    meter._reserve(max_key_comparisons=pairs, max_work_units=pairs * (width + 1))
    if any(not any(key == expected_key for expected_key in expected) for key in value):
        _wire_error(f"{name} fields differ.")
    _dict_cost(meter, count, 4 * width * count, width, lookups=2 * count)
    return value


def check_string(meter, value):
    meter._reserve(max_work_units=2 * len(value) + 1)
    for char in value:
        _utf8_width(char)


def read_enum(meter, text, enum_type, name):
    members = replay._layouts()[1][id(enum_type)]
    meter._reserve(max_key_comparisons=len(members),
                   max_work_units=sum(1 + len(item.value) for item in members))
    for member in members:
        if text == member.value:
            return member
    _wire_error(f"{name} contains an unknown {enum_type.__name__} value.")


def read_decimal(meter, value, name):
    size = len(value)
    meter._reserve(max_decimal_recipes=1, max_work_units=32 * size + 32,
                   max_temporary_slots=12 * size + 32)
    normalized = "".join(
        chr(48 + unicodedata.decimal(char)) if ord(char) >= 128 and char.isdecimal() else char
        for char in value.strip() if char != "_"
    )
    match = _FINITE_DECIMAL.fullmatch(normalized)
    if match is None:
        _wire_error(f"{name} is not a finite Decimal string.")
    sign, integral, fractional, only_fractional, exponent_sign, digits = match.groups()
    fractional = fractional or only_fractional or ""
    coefficient = ((integral or "") + fractional).lstrip("0") or "0"
    coefficient_cap = min(meter._limits["max_decimal_coefficient_digits"],
                          meter._numeric_profile.max_coefficient_digits)
    exponent_cap = min(meter._limits["max_decimal_exponent_magnitude"],
                       meter._numeric_profile.max_exponent_magnitude)
    if len(coefficient) > coefficient_cap:
        meter._reject(_Code.RESOURCE_LIMIT, "max_decimal_coefficient_digits")
    magnitude = 0
    for digit in digits or "":
        magnitude = magnitude * 10 + ord(digit) - 48
        if magnitude > exponent_cap + len(fractional):
            meter._reject(_Code.RESOURCE_LIMIT, "max_decimal_exponent_magnitude")
    exponent = (-magnitude if exponent_sign == "-" else magnitude) - len(fractional)
    if abs(exponent) > exponent_cap:
        meter._reject(_Code.RESOURCE_LIMIT, "max_decimal_exponent_magnitude")
    return meter._numeric.construct_decimal(sign=int(sign == "-"), coefficient=coefficient,
                                            quantum_exponent=exponent)


def reserve_record(kind):
    meter = helper("decode")
    if meter is not None:
        count = len(replay._layouts()[0][id(kind)])
        meter._reserve(max_records=1, max_validator_dispatches=1, max_temporary_slots=8 + 8 * count,
                       max_work_units=16 + 8 * count)
        _dict_cost(meter, count, 32 * count, 32)


def _reserve_shared(meter, keys, count, pairs=0, other_width=0):
    meter._reserve(max_work_units=count, max_temporary_slots=2 * count)
    characters = width = 0
    for key in keys:
        characters += len(key)
        width = max(width, len(key))
    work, comparisons, slots, _ = _shared_set_cost(count, characters, width)
    meter._reserve(max_set_slots=slots, max_key_comparisons=comparisons + pairs,
                   max_work_units=work + pairs * (1 + max(width, other_width)))


def construct_record(kind, /, **values):
    meter = helper("decode")
    if meter is not None:
        # V2 validators also dispatch the genuine V201 path. The five V1
        # constructors are plain shared dataclasses and need their own prepay.
        characters = sum(len(value) for value in values.values() if type(value) is str)
        meter._reserve(max_work_units=4 * characters, max_temporary_slots=4 * characters)
        if kind is CandidateRecordV1:
            records = values["provenance"]
            width = max(map(len, (values["candidate_id"], values["receipt_id"], values["field_id"])))
            _reserve_shared(meter, (record.provenance_id for record in records),
                            len(records), 3 * len(records), width)
        elif kind is CandidateProvenanceV1:
            tokens, spans = values["source_token_ids"], values["source_spans"]
            meter._reserve(max_work_units=len(spans), max_temporary_slots=2 * len(spans))
            width = max((len(span.token_id) for span in spans), default=0)
            _reserve_shared(meter, tokens, len(tokens), len(tokens) * len(spans), width)
        elif kind is PreliminaryRankV1:
            digits = meter._numeric_profile.max_coefficient_digits
            meter._reserve(max_work_units=8 * digits + 32, max_temporary_slots=4 * digits + 16)
    return kind(**values)
