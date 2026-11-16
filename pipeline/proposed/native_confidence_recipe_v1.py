"""D3 native-confidence recipes: standalone synthetic proof-of-concept.

Authority: Design 03 Closure 01, accepted component-local specification.
Logical budgets are not execution-time or byte-exact native-memory bounds.
No producer, consumer, D3 graph, Theta_A or operational authentication wiring.
"""

from __future__ import annotations

import decimal
import enum
import math
import struct
import sys
import unicodedata
from dataclasses import dataclass, fields

from pipeline.contracts import FieldStatus, OcrSourceToken, StructuredField
from pipeline.proposed.bounded_numeric_ingress_v1 import (
    IngressContextV1,
    IngressProfileV1,
    NumericIngressError,
    NumericIngressErrorCode,
)


class NativeConfidenceRoleV1(enum.Enum):
    OCR_CONFIDENCE = "OCR_CONFIDENCE"
    EXTRACTOR_CONFIDENCE = "EXTRACTOR_CONFIDENCE"


class NativeConfidenceErrorCodeV1(enum.Enum):
    PROFILE_INVALID = "PROFILE_INVALID"
    SCOPE_CLOSED = "SCOPE_CLOSED"
    SOURCE_BINDING_ERROR = "SOURCE_BINDING_ERROR"
    UNSUPPORTED_NATIVE_TYPE = "UNSUPPORTED_NATIVE_TYPE"
    NONFINITE_VALUE = "NONFINITE_VALUE"
    INVALID_NUMERIC_SHAPE = "INVALID_NUMERIC_SHAPE"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    RUNTIME_INCOMPATIBLE = "RUNTIME_INCOMPATIBLE"
    UNREGISTERED_DECIMAL = "UNREGISTERED_DECIMAL"
    CONSTRUCTION_FAILURE = "CONSTRUCTION_FAILURE"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"


class NativeConfidenceScopeStateV1(enum.Enum):
    OPEN = "OPEN"
    EXHAUSTED = "EXHAUSTED"
    ABORTED = "ABORTED"
    CLOSED = "CLOSED"


@dataclass(frozen=True, slots=True)
class NativeConfidenceProfileV1:
    """Thirteen explicit synthetic limits; there are no production defaults."""

    max_native_int_bits: int
    max_native_text_chars: int
    max_coefficient_digits: int
    max_quantum_exponent_magnitude: int
    max_attempts: int
    max_work_units: int
    max_live_text_chars: int
    max_live_digit_cells: int
    max_live_int_format_limb_cells: int
    max_live_binary_bytes: int
    max_registry_entries: int
    max_source_anchors: int
    max_retained_int_bits: int

    def __post_init__(self) -> None:
        _profile_snapshot(self)


_LIMIT_NAMES = tuple(field.name for field in fields(NativeConfidenceProfileV1))
_LOCATIONS = frozenset((
    "scope", "profile", "runtime", "source", "value", "text", "recipe.sign",
    "recipe.coefficient", "recipe.quantum_exponent", "budget", "registry",
))
_LOCATION_MAX = max(map(len, _LOCATIONS))
_LIMIT_MAX = max(map(len, _LIMIT_NAMES))


# Exact component-local emission schema, including the resource helpers'
# closed call-site expansions. These rows are not arbitrary token products.
_CONFIDENCE_ROLES = tuple(NativeConfidenceRoleV1)
_DIAGNOSTIC_ROWS = (
    (NativeConfidenceErrorCodeV1.PROFILE_INVALID, "profile", (None,), (None, *_LIMIT_NAMES)),
    (NativeConfidenceErrorCodeV1.SCOPE_CLOSED, "scope", (None,), (None,)),
    (NativeConfidenceErrorCodeV1.SOURCE_BINDING_ERROR, "source", _CONFIDENCE_ROLES, (None,)),
    (NativeConfidenceErrorCodeV1.UNSUPPORTED_NATIVE_TYPE, "value", _CONFIDENCE_ROLES, (None,)),
    (NativeConfidenceErrorCodeV1.NONFINITE_VALUE, "value", _CONFIDENCE_ROLES, (None,)),
    (NativeConfidenceErrorCodeV1.INVALID_NUMERIC_SHAPE, "source", (None,), (None,)),
    (NativeConfidenceErrorCodeV1.RUNTIME_INCOMPATIBLE, "runtime", (None,), (None,)),
    (NativeConfidenceErrorCodeV1.RUNTIME_INCOMPATIBLE, "text", _CONFIDENCE_ROLES, (None,)),
    (NativeConfidenceErrorCodeV1.UNREGISTERED_DECIMAL, "registry", (None,), (None,)),
    (NativeConfidenceErrorCodeV1.CONSTRUCTION_FAILURE, "registry", _CONFIDENCE_ROLES, (None,)),
    (NativeConfidenceErrorCodeV1.INTERNAL_FAILURE, "scope", (None, *_CONFIDENCE_ROLES), (None,)),
    (NativeConfidenceErrorCodeV1.INTERNAL_FAILURE, "registry", (None,), (None,)),
    (NativeConfidenceErrorCodeV1.RESOURCE_LIMIT, "source", (None,), ("max_source_anchors",)),
    (NativeConfidenceErrorCodeV1.RESOURCE_LIMIT, "budget", (None,), ("max_attempts",)),
    (NativeConfidenceErrorCodeV1.RESOURCE_LIMIT, "registry", _CONFIDENCE_ROLES,
     ("max_registry_entries",)),
    (NativeConfidenceErrorCodeV1.RESOURCE_LIMIT, "value", _CONFIDENCE_ROLES,
     ("max_native_int_bits",)),
    (NativeConfidenceErrorCodeV1.RESOURCE_LIMIT, "recipe.coefficient", _CONFIDENCE_ROLES,
     ("max_coefficient_digits",)),
    (NativeConfidenceErrorCodeV1.RESOURCE_LIMIT, "recipe.quantum_exponent", _CONFIDENCE_ROLES,
     ("max_quantum_exponent_magnitude",)),
    (NativeConfidenceErrorCodeV1.RESOURCE_LIMIT, "budget", _CONFIDENCE_ROLES,
     ("max_retained_int_bits", "max_live_binary_bytes", "max_live_text_chars",
      "max_live_digit_cells", "max_live_int_format_limb_cells")),
    (NativeConfidenceErrorCodeV1.RESOURCE_LIMIT, "profile", (None,), ("max_work_units",)),
    (NativeConfidenceErrorCodeV1.RESOURCE_LIMIT, "budget", (None,), ("max_work_units",)),
    (NativeConfidenceErrorCodeV1.RESOURCE_LIMIT, "runtime", (None,), ("max_work_units",)),
    (NativeConfidenceErrorCodeV1.RESOURCE_LIMIT, "registry", (None, *_CONFIDENCE_ROLES),
     ("max_work_units",)),
    (NativeConfidenceErrorCodeV1.RESOURCE_LIMIT, "source", _CONFIDENCE_ROLES,
     ("max_work_units",)),
    (NativeConfidenceErrorCodeV1.RESOURCE_LIMIT, "value", _CONFIDENCE_ROLES,
     ("max_work_units",)),
    (NativeConfidenceErrorCodeV1.RESOURCE_LIMIT, "text", _CONFIDENCE_ROLES,
     ("max_work_units",)),
    (NativeConfidenceErrorCodeV1.RESOURCE_LIMIT, "recipe.coefficient", _CONFIDENCE_ROLES,
     ("max_work_units",)),
)
_EMITTED_DIAGNOSTICS = frozenset(
    (code, location, role, limit)
    for code, location, roles, limits in _DIAGNOSTIC_ROWS
    for role in roles for limit in limits
)


class NativeConfidenceErrorV1(ValueError):
    """Preserve an emitted combination or use the fixed code/scope fallback."""

    def __init__(self, code: NativeConfidenceErrorCodeV1, location: object,
                 *, role: object = None, limit_field: object = None) -> None:
        if type(code) is not NativeConfidenceErrorCodeV1:
            raise TypeError("code must be a NativeConfidenceErrorCodeV1")
        self.code = code
        # Exact-type and length checks precede combination hashing/equality.
        # Invalid raw tokens must not be sanitized into a different emitted row.
        valid_tokens = (
            type(location) is str and len(location) <= _LOCATION_MAX
            and location in _LOCATIONS
            and (role is None or type(role) is NativeConfidenceRoleV1)
            and (limit_field is None or (
                type(limit_field) is str and len(limit_field) <= _LIMIT_MAX
                and limit_field in _LIMIT_NAMES))
        )
        if valid_tokens and (code, location, role, limit_field) in _EMITTED_DIAGNOSTICS:
            self.location, self.role, self.limit_field = location, role, limit_field
        else:
            self.location, self.role, self.limit_field = "scope", None, None
        tokens = [code.value, self.location]
        if self.role is not None:
            tokens.append(self.role.value)
        if self.limit_field is not None:
            tokens.append(self.limit_field)
        super().__init__(": ".join(tokens))


def _profile_snapshot(profile: object) -> dict[str, int]:
    if type(profile) is not NativeConfidenceProfileV1:
        raise NativeConfidenceErrorV1(NativeConfidenceErrorCodeV1.PROFILE_INVALID,
                                      "profile")
    result: dict[str, int] = {}
    for name in _LIMIT_NAMES:
        try:
            value = getattr(profile, name)
        except AttributeError as exc:
            raise NativeConfidenceErrorV1(
                NativeConfidenceErrorCodeV1.PROFILE_INVALID, "profile", limit_field=name) from exc
        if type(value) is not int or int.bit_length(value) > 31 or value < 1:
            raise NativeConfidenceErrorV1(
                NativeConfidenceErrorCodeV1.PROFILE_INVALID, "profile", limit_field=name)
        result[name] = value
    if result["max_native_int_bits"] > 4300:
        raise NativeConfidenceErrorV1(NativeConfidenceErrorCodeV1.PROFILE_INVALID,
                                      "profile", limit_field="max_native_int_bits")
    if result["max_native_text_chars"] < max(24, result["max_native_int_bits"] + 1):
        raise NativeConfidenceErrorV1(NativeConfidenceErrorCodeV1.PROFILE_INVALID,
                                      "profile", limit_field="max_native_text_chars")
    return result


_PINNED_VERSION = (
    "3.13.7 (tags/v3.13.7:bcee1c3, Aug 14 2025, 14:15:11) "
    "[MSC v.1944 64 bit (AMD64)]"
)


def _verify_runtime(limits: dict[str, int]) -> None:
    """Ten fixed requirement groups. Inspect, never change runtime settings."""
    info = sys.float_info
    checks = (
        sys.implementation.name == "cpython",
        sys.version == _PINNED_VERSION,
        sys.maxsize == 9223372036854775807,
        unicodedata.unidata_version == "15.1.0",
        (info.radix, info.mant_dig, info.max_exp, info.min_exp, info.rounds)
        == (2, 53, 1024, -1021, 1),
        sys.float_repr_style == "short",
        struct.calcsize("d") == 8 and float.__getformat__("double") == "IEEE, little-endian",
        (sys.int_info.bits_per_digit, sys.int_info.sizeof_digit,
         sys.int_info.default_max_str_digits, sys.int_info.str_digits_check_threshold)
        == (30, 4, 4300, 640),
        sys.get_int_max_str_digits() == 4300,
        decimal.__version__ == "1.70" and decimal.__libmpdec_version__ == "4.0.0"
        and limits["max_coefficient_digits"] <= decimal.MAX_PREC
        and limits["max_quantum_exponent_magnitude"] <= decimal.MAX_EMAX
        and -limits["max_quantum_exponent_magnitude"] >= decimal.MIN_ETINY,
    )
    if not all(checks):
        raise NativeConfidenceErrorV1(
            NativeConfidenceErrorCodeV1.RUNTIME_INCOMPATIBLE, "runtime")


@dataclass(frozen=True, slots=True)
class _Anchor:
    role: NativeConfidenceRoleV1
    source: OcrSourceToken | StructuredField
    native: int | float | None
    status: FieldStatus | None
    integer_bits: int
    float_bits: bytes | None


@dataclass(frozen=True, slots=True)
class _Produced:
    value: decimal.Decimal
    anchor: _Anchor
    sign: int
    coefficient: str
    quantum_exponent: int


def _format_native(value: int | float) -> str:
    # Only exact, admitted builtins reach this seam. Also permits fault injection.
    return str(value)


def _parse_text(text: str, *, floating: bool) -> tuple[int, str, int]:
    """Bounded two-pass ASCII parser. No regex, Decimal or exponent expansion."""
    length = len(text)
    pos = 0
    sign = 0
    if pos < length and text[pos] == "-":
        sign, pos = 1, pos + 1
    start = pos
    while pos < length and "0" <= text[pos] <= "9":
        pos += 1
    if pos == start or (pos - start > 1 and text[start] == "0"):
        raise ValueError("unexpected builtin numeric text")
    integer_end = pos
    fractional_start = pos
    fractional_end = pos
    if floating and pos < length and text[pos] == ".":
        pos += 1
        fractional_start = pos
        while pos < length and "0" <= text[pos] <= "9":
            pos += 1
        fractional_end = pos
        if fractional_start == fractional_end:
            raise ValueError("unexpected builtin numeric text")
    has_fraction = fractional_end > fractional_start
    exponent = 0
    has_exponent = False
    if floating and pos < length and text[pos] == "e":
        has_exponent = True
        pos += 1
        if pos >= length or text[pos] not in ("+", "-"):
            raise ValueError("unexpected builtin numeric text")
        exponent_negative = text[pos] == "-"
        pos += 1
        exponent_start = pos
        # At most three digits before any exponent arithmetic.
        if not 2 <= length - pos <= 3:
            raise ValueError("unexpected builtin numeric text")
        while pos < length and "0" <= text[pos] <= "9":
            exponent = exponent * 10 + (ord(text[pos]) - 48)
            pos += 1
        if pos == exponent_start:
            raise ValueError("unexpected builtin numeric text")
        if exponent_negative:
            exponent = -exponent
        if integer_end - start != 1 or text[start] == "0":
            raise ValueError("unexpected builtin numeric text")
    if pos != length or (floating and not (has_fraction or has_exponent)):
        raise ValueError("unexpected builtin numeric text")
    characters = [text[index] for index in range(start, integer_end)]
    characters.extend(text[index] for index in range(fractional_start, fractional_end))
    joined = "".join(characters)
    first = 0
    while first < len(joined) - 1 and joined[first] == "0":
        first += 1
    coefficient = joined[first:]
    return sign, coefficient, exponent - (fractional_end - fractional_start)


class NativeConfidenceScopeV1:
    """Exclusive synchronous scope; consistency with supplied anchors only.

    References are captured once. This is not source-byte authentication,
    full receipt/D3 membership validation or protection from coordinated
    in-process mutation of trusted code and private state.
    """

    def __init__(self, *, profile: NativeConfidenceProfileV1,
                 ocr_sources: tuple[OcrSourceToken, ...],
                 extractor_sources: tuple[StructuredField, ...]) -> None:
        self._limits = _profile_snapshot(profile)
        self._state = NativeConfidenceScopeStateV1.OPEN
        self._attempts = 0
        self._work_units = 0
        self._live_text_chars = 0
        self._live_digit_cells = 0
        self._live_int_format_limb_cells = 0
        self._live_binary_bytes = 0
        self._retained_int_bits = 0
        self._anchors: list[_Anchor] = []
        self._produced: list[_Produced] = []
        self._ingress: IngressContextV1 | None = None
        try:
            self._charge(26, "profile")
            _verify_runtime(self._limits)
            if type(ocr_sources) is not tuple or type(extractor_sources) is not tuple:
                raise NativeConfidenceErrorV1(
                    NativeConfidenceErrorCodeV1.INVALID_NUMERIC_SHAPE, "source")
            if len(ocr_sources) + len(extractor_sources) > self._limits["max_source_anchors"]:
                self._exhaust("source", "max_source_anchors")
            for source in ocr_sources:
                self._capture(source, NativeConfidenceRoleV1.OCR_CONFIDENCE)
            for source in extractor_sources:
                self._capture(source, NativeConfidenceRoleV1.EXTRACTOR_CONFIDENCE)
            self._ingress = IngressContextV1(IngressProfileV1(
                max_coefficient_digits=self._limits["max_coefficient_digits"],
                max_exponent_magnitude=self._limits["max_quantum_exponent_magnitude"],
                max_constructions=self._limits["max_registry_entries"],
                max_work_units=self._limits["max_work_units"],
            ))
        except NativeConfidenceErrorV1:
            self._abort()
            raise
        except MemoryError:
            self._abort()
            raise
        except Exception as exc:
            self._abort()
            raise NativeConfidenceErrorV1(
                NativeConfidenceErrorCodeV1.INTERNAL_FAILURE, "scope") from exc
        except BaseException:
            self._abort()
            raise

    @property
    def state(self) -> NativeConfidenceScopeStateV1:
        return self._state

    @property
    def attempts(self) -> int:
        return self._attempts

    @property
    def work_units(self) -> int:
        return self._work_units

    @property
    def registry_size(self) -> int:
        return len(self._produced)

    @property
    def source_count(self) -> int:
        return len(self._anchors)

    @property
    def live_text_chars(self) -> int:
        return self._live_text_chars

    @property
    def live_digit_cells(self) -> int:
        return self._live_digit_cells

    @property
    def live_int_format_limb_cells(self) -> int:
        return self._live_int_format_limb_cells

    @property
    def live_binary_bytes(self) -> int:
        return self._live_binary_bytes

    @property
    def retained_int_bits(self) -> int:
        return self._retained_int_bits

    def _exhaust(self, location: str, limit: str,
                 role: NativeConfidenceRoleV1 | None = None) -> None:
        self._state = NativeConfidenceScopeStateV1.EXHAUSTED
        raise NativeConfidenceErrorV1(NativeConfidenceErrorCodeV1.RESOURCE_LIMIT,
                                      location, role=role, limit_field=limit)

    def _charge(self, units: int, location: str,
                role: NativeConfidenceRoleV1 | None = None) -> None:
        if units > self._limits["max_work_units"] - self._work_units:
            self._exhaust(location, "max_work_units", role)
        self._work_units += units

    def _reserve(self, attribute: str, limit: str, units: int,
                 role: NativeConfidenceRoleV1 | None = None) -> None:
        current = getattr(self, attribute)
        if units > self._limits[limit] - current:
            self._exhaust("budget", limit, role)
        setattr(self, attribute, current + units)

    def _capture(self, source: object, role: NativeConfidenceRoleV1) -> None:
        self._charge(1 + len(self._anchors), "source", role)
        if any(anchor.source is source for anchor in self._anchors):
            raise NativeConfidenceErrorV1(
                NativeConfidenceErrorCodeV1.SOURCE_BINDING_ERROR, "source", role=role)
        self._charge(1, "source", role)
        if role is NativeConfidenceRoleV1.OCR_CONFIDENCE:
            if type(source) is not OcrSourceToken:
                raise NativeConfidenceErrorV1(
                    NativeConfidenceErrorCodeV1.SOURCE_BINDING_ERROR, "source", role=role)
            native, status = source.raw_confidence, None
        else:
            if type(source) is not StructuredField:
                raise NativeConfidenceErrorV1(
                    NativeConfidenceErrorCodeV1.SOURCE_BINDING_ERROR, "source", role=role)
            native, status = source.confidence, source.status
            if not any(status is member for member in (
                    FieldStatus.EXTRACTED, FieldStatus.MISSING, FieldStatus.UNRESOLVED)):
                raise NativeConfidenceErrorV1(
                    NativeConfidenceErrorCodeV1.SOURCE_BINDING_ERROR, "source", role=role)
            if status is not FieldStatus.EXTRACTED and native is not None:
                raise NativeConfidenceErrorV1(
                    NativeConfidenceErrorCodeV1.SOURCE_BINDING_ERROR, "source", role=role)
        bits, binary = 0, None
        if native is not None:
            if type(native) is int:
                self._charge(1, "value", role)
                bits = int.bit_length(native)
                if bits > self._limits["max_native_int_bits"]:
                    raise NativeConfidenceErrorV1(
                        NativeConfidenceErrorCodeV1.RESOURCE_LIMIT, "value", role=role,
                        limit_field="max_native_int_bits")
                self._charge(bits, "value", role)
                self._reserve("_retained_int_bits", "max_retained_int_bits", bits, role)
            elif type(native) is float:
                self._charge(1, "value", role)
                if not math.isfinite(native):
                    raise NativeConfidenceErrorV1(
                        NativeConfidenceErrorCodeV1.NONFINITE_VALUE, "value", role=role)
                self._charge(8, "value", role)
                self._reserve("_live_binary_bytes", "max_live_binary_bytes", 8, role)
                binary = struct.pack("!d", native)
            else:
                raise NativeConfidenceErrorV1(
                    NativeConfidenceErrorCodeV1.UNSUPPORTED_NATIVE_TYPE, "value", role=role)
        self._anchors.append(_Anchor(role, source, native, status, bits, binary))

    def _begin(self) -> None:
        if self._state is not NativeConfidenceScopeStateV1.OPEN:
            raise NativeConfidenceErrorV1(NativeConfidenceErrorCodeV1.SCOPE_CLOSED, "scope")
        if self._attempts >= self._limits["max_attempts"]:
            self._exhaust("budget", "max_attempts")
        self._attempts += 1
        self._charge(1, "budget")
        self._charge(1, "runtime")
        if sys.get_int_max_str_digits() != 4300:
            raise NativeConfidenceErrorV1(
                NativeConfidenceErrorCodeV1.RUNTIME_INCOMPATIBLE, "runtime")

    def _check_anchor(self, anchor: _Anchor) -> None:
        self._charge(1, "source", anchor.role)
        if anchor.role is NativeConfidenceRoleV1.OCR_CONFIDENCE:
            unchanged = anchor.source.raw_confidence is anchor.native
        else:
            unchanged = (anchor.source.confidence is anchor.native
                         and anchor.source.status is anchor.status)
        if not unchanged:
            raise NativeConfidenceErrorV1(
                NativeConfidenceErrorCodeV1.SOURCE_BINDING_ERROR, "source", role=anchor.role)

    def _lookup(self, source: object, role: NativeConfidenceRoleV1) -> _Anchor:
        self._charge(1 + len(self._anchors), "source", role)
        for anchor in self._anchors:
            if anchor.source is source and anchor.role is role:
                self._check_anchor(anchor)
                return anchor
        raise NativeConfidenceErrorV1(
            NativeConfidenceErrorCodeV1.SOURCE_BINDING_ERROR, "source", role=role)

    def _convert(self, source: object, role: NativeConfidenceRoleV1) -> decimal.Decimal | None:
        self._begin()
        anchor = self._lookup(source, role)
        native = anchor.native
        if native is None:
            return None
        if len(self._produced) >= self._limits["max_registry_entries"]:
            self._exhaust("registry", "max_registry_entries", role)
        # Captured exact builtin objects are immutable, so their width proof is reusable.
        floating = type(native) is float
        width = anchor.integer_bits
        envelope = 24 if floating else max(1, width + 1)
        limbs = (width + 29) // 30
        scratch = 0 if floating else 1 + limbs + limbs // 99
        digits_bound = min(self._limits["max_coefficient_digits"], envelope)
        text_reserved = digit_reserved = limb_reserved = 0
        text = coefficient = recipe = result = produced = None
        try:
            self._reserve("_live_text_chars", "max_live_text_chars", 5 * envelope, role)
            text_reserved = 5 * envelope
            self._reserve("_live_digit_cells", "max_live_digit_cells", 2 * digits_bound, role)
            digit_reserved = 2 * digits_bound
            self._reserve("_live_int_format_limb_cells", "max_live_int_format_limb_cells",
                          scratch, role)
            limb_reserved = scratch
            format_work = (25 if floating else
                           1 + limbs * scratch + 2 * limbs + scratch + envelope)
            self._charge(format_work, "text", role)
            text = _format_native(native)
            if type(text) is not str or not text or len(text) > envelope:
                raise NativeConfidenceErrorV1(
                    NativeConfidenceErrorCodeV1.RUNTIME_INCOMPATIBLE, "text", role=role)
            self._charge(1 + 5 * envelope, "text", role)
            try:
                recipe = _parse_text(text, floating=floating)
            except ValueError as exc:
                raise NativeConfidenceErrorV1(
                    NativeConfidenceErrorCodeV1.RUNTIME_INCOMPATIBLE, "text", role=role) from exc
            sign, coefficient, quantum = recipe
            digits = len(coefficient)
            if floating and (digits > 17 or abs(quantum) > 340):
                raise NativeConfidenceErrorV1(
                    NativeConfidenceErrorCodeV1.RUNTIME_INCOMPATIBLE, "text", role=role)
            if digits > self._limits["max_coefficient_digits"]:
                raise NativeConfidenceErrorV1(
                    NativeConfidenceErrorCodeV1.RESOURCE_LIMIT, "recipe.coefficient",
                    role=role, limit_field="max_coefficient_digits")
            if abs(quantum) > self._limits["max_quantum_exponent_magnitude"]:
                raise NativeConfidenceErrorV1(
                    NativeConfidenceErrorCodeV1.RESOURCE_LIMIT, "recipe.quantum_exponent",
                    role=role, limit_field="max_quantum_exponent_magnitude")
            # Prepay scan, construction and all publication work before calling V1.
            self._charge(digits, "recipe.coefficient", role)
            self._charge(1 + digits, "registry", role)
            self._charge(4 * (len(self._produced) + 1), "registry", role)
            result = self._ingress.construct_decimal(sign, coefficient, quantum, "field.confidence")
            produced = _Produced(result, anchor, sign, coefficient, quantum)
            self._publish(produced)
            # Transfer part of the live reservations to persistent recipe/Decimal cells.
            self._live_text_chars -= text_reserved - digits
            text_reserved = 0
            self._live_digit_cells -= digit_reserved - digits
            digit_reserved = 0
            return result
        finally:
            # Recoverable rejections must not retain formatted buffers in tracebacks.
            text = coefficient = recipe = result = produced = None
            self._live_text_chars -= text_reserved
            self._live_digit_cells -= digit_reserved
            self._live_int_format_limb_cells -= limb_reserved

    def _publish(self, produced: _Produced) -> None:
        """Private publication seam. The result is returned only after completion."""
        self._produced.append(produced)

    def _execute(self, source: object, role: NativeConfidenceRoleV1) -> decimal.Decimal | None:
        try:
            return self._convert(source, role)
        except NativeConfidenceErrorV1 as exc:
            if exc.code in (NativeConfidenceErrorCodeV1.SOURCE_BINDING_ERROR,
                            NativeConfidenceErrorCodeV1.RUNTIME_INCOMPATIBLE):
                self._abort()
            raise
        except NumericIngressError as exc:
            self._abort()
            if isinstance(exc.__cause__, MemoryError):
                raise exc.__cause__ from None
            raise NativeConfidenceErrorV1(
                NativeConfidenceErrorCodeV1.CONSTRUCTION_FAILURE, "registry", role=role) from exc
        except MemoryError:
            self._abort()
            raise
        except Exception as exc:
            self._abort()
            raise NativeConfidenceErrorV1(
                NativeConfidenceErrorCodeV1.INTERNAL_FAILURE, "scope", role=role) from exc
        except BaseException:
            self._abort()
            raise

    def convert_ocr_confidence(self, *, source: OcrSourceToken) -> decimal.Decimal | None:
        return self._execute(source, NativeConfidenceRoleV1.OCR_CONFIDENCE)

    def convert_extractor_confidence(self, *, source: StructuredField) -> decimal.Decimal | None:
        return self._execute(source, NativeConfidenceRoleV1.EXTRACTOR_CONFIDENCE)

    def check_registered(self, *, value: object) -> decimal.Decimal:
        try:
            self._begin()
            self._charge(1 + 2 * len(self._produced), "registry")
            for produced in self._produced:
                if produced.value is value:
                    self._check_anchor(produced.anchor)
                    return self._ingress.check_registered(value, "field.confidence")
            raise NativeConfidenceErrorV1(
                NativeConfidenceErrorCodeV1.UNREGISTERED_DECIMAL, "registry")
        except NativeConfidenceErrorV1 as exc:
            if exc.code in (NativeConfidenceErrorCodeV1.SOURCE_BINDING_ERROR,
                            NativeConfidenceErrorCodeV1.RUNTIME_INCOMPATIBLE):
                self._abort()
            raise
        except MemoryError:
            self._abort()
            raise
        except Exception as exc:
            self._abort()
            raise NativeConfidenceErrorV1(
                NativeConfidenceErrorCodeV1.INTERNAL_FAILURE, "registry") from exc
        except BaseException:
            self._abort()
            raise

    def _abort(self) -> None:
        self._state = NativeConfidenceScopeStateV1.ABORTED
        self._ingress = None
        self._produced.clear()
        self._anchors.clear()
        self._live_text_chars = self._live_digit_cells = 0
        self._live_int_format_limb_cells = self._live_binary_bytes = 0
        self._retained_int_bits = 0

    def close(self) -> None:
        self._abort()
        self._state = NativeConfidenceScopeStateV1.CLOSED
