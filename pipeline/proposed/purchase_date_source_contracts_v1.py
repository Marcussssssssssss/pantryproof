"""Immutable, Python-local D1 evidence for literal OCR date discovery."""

from __future__ import annotations

import hashlib
import json
import re
import struct
import sys
import unicodedata
from dataclasses import dataclass, field, fields
from datetime import date
from enum import Enum
from itertools import zip_longest
from math import isfinite
from types import UnionType
from typing import Callable, Iterator, get_args, get_origin, get_type_hints

from pipeline.baseline_b3 import RULESET_ID, B3ParseState, DateParseResult, parse_generic_date
from pipeline.contracts import (
    CONTRACT_VERSION, FailureStage, FieldStatus, OcrSourceToken, OutputStage,
    Point, PolicyState, PreResolutionDisposition, ReceiptExtractionStatus,
    ReceiptFieldName, ReceiptItemRow, ReceiptOutput, ReceiptSourceEvidence,
    SourceEvidenceDecision, SourceEvidenceGateResult, SourceProcessingStatus,
    SourceProvenance, StructuredField,
)
from pipeline.layout_b2 import EXTRACTOR_VERSION as B2_VERSION
from pipeline.layout_b2 import B2ExtractionResult
from pipeline.proposed.contracts import (
    PROPOSED_CONTRACT_VERSION, CandidateLimitStatus, CandidateProvenanceV1,
    CandidateRecordV1, CandidateRole, CandidateSourceKind, ConfigurationKind,
    ConfigurationRefV1, ConfigurationState, SourceCharacterSpanV1,
)

SCHEMA_ID = "pantryproof-purchase-date-source-discovery-v1"
RECORD_VERSION = "1"
AUTHORITY_SCOPE = "SOURCE_DISCOVERY_ONLY"
PYTHON_RUNTIME_VERSION = (
    "3.13.7 (tags/v3.13.7:bcee1c3, Aug 14 2025, 14:15:11) [MSC v.1944 64 bit (AMD64)]"
)
UNICODE_DATABASE_VERSION = "15.1.0"
PARSER_SOURCE_SHA256 = "f417ca5158af5fcb0a0f5757a01e75b708f59a07bc358d93a7eb7ef04c4abb4e"


class DateOriginalStateV1(str, Enum):
    EXTRACTED_WITH_SUPPLIED_C0 = "EXTRACTED_WITH_SUPPLIED_C0"
    EXTRACTED_NO_SUPPLIED_C0 = "EXTRACTED_NO_SUPPLIED_C0"
    UNRESOLVED_NO_C0 = "UNRESOLVED_NO_C0"
    MISSING_NO_C0 = "MISSING_NO_C0"
    NO_B2_OUTPUT = "NO_B2_OUTPUT"


class DateObservationKindV1(str, Enum):
    WHOLE_TOKEN = "WHOLE_TOKEN"
    ANCHORED_BODY = "ANCHORED_BODY"
    ANCHOR_ONLY = "ANCHOR_ONLY"


class DateDiscoveryStatusV1(str, Enum):
    COMPLETE_WITH_PROPOSALS = "COMPLETE_WITH_PROPOSALS"
    COMPLETE_NO_PROPOSALS = "COMPLETE_NO_PROPOSALS"
    NOT_PROCESSABLE_STORED_FALLBACK = "NOT_PROCESSABLE_STORED_FALLBACK"


class DateDiscoveryDiagnosticCodeV1(str, Enum):
    STORED_SOURCE_INSUFFICIENT = "STORED_SOURCE_INSUFFICIENT"
    NO_METHOD_READY_ORIGINAL = "NO_METHOD_READY_ORIGINAL"
    NO_SUPPLIED_C0 = "NO_SUPPLIED_C0"
    B2_MULTI_TOKEN_CONTEXT_UNCOMPOSED = "B2_MULTI_TOKEN_CONTEXT_UNCOMPOSED"
    B2_VALUE_NOT_SINGLE_TOKEN_SOURCE = "B2_VALUE_NOT_SINGLE_TOKEN_SOURCE"
    ANCHOR_WITHOUT_BODY = "ANCHOR_WITHOUT_BODY"
    INVALID_OR_UNSUPPORTED_LITERAL = "INVALID_OR_UNSUPPORTED_LITERAL"
    AMBIGUOUS_INTERPRETATIONS_RETAINED = "AMBIGUOUS_INTERPRETATIONS_RETAINED"
    NO_SUPPORTED_DATE_PROPOSALS = "NO_SUPPORTED_DATE_PROPOSALS"


class DateDiscoveryErrorCodeV1(str, Enum):
    INPUT_TYPE_INVALID = "INPUT_TYPE_INVALID"
    INPUT_SHAPE_INVALID = "INPUT_SHAPE_INVALID"
    PROFILE_UNSUPPORTED = "PROFILE_UNSUPPORTED"
    RESOURCE_LIMIT_EXCEEDED = "RESOURCE_LIMIT_EXCEEDED"
    SOURCE_BINDING_MISMATCH = "SOURCE_BINDING_MISMATCH"
    THETA_A_ASSOCIATION_MISMATCH = "THETA_A_ASSOCIATION_MISMATCH"
    ORIGINAL_ASSOCIATION_MISMATCH = "ORIGINAL_ASSOCIATION_MISMATCH"
    PARSER_CONTRACT_MISMATCH = "PARSER_CONTRACT_MISMATCH"
    CONTENT_ID_MISMATCH = "CONTENT_ID_MISMATCH"
    CONTENT_ID_COLLISION = "CONTENT_ID_COLLISION"


class DateDiscoveryError(ValueError):
    """Failure with schema paths and a closed, source-free message."""

    __slots__ = ("_code", "_path", "_limit_field")

    def __init__(self, code: DateDiscoveryErrorCodeV1, path: str, limit_field: str | None = None):
        super().__init__(code.value)
        object.__setattr__(self, "_code", code)
        object.__setattr__(self, "_path", path)
        object.__setattr__(self, "_limit_field", limit_field)

    def __setattr__(self, name: str, value: object) -> None:
        if name in DateDiscoveryError.__slots__:
            raise AttributeError(f"{name} is read-only")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name in DateDiscoveryError.__slots__:
            raise AttributeError(f"{name} is read-only")
        super().__delattr__(name)

    @property
    def code(self) -> DateDiscoveryErrorCodeV1:
        return self._code

    @property
    def path(self) -> str:
        return self._path

    @property
    def limit_field(self) -> str | None:
        return self._limit_field


_Err = DateDiscoveryErrorCodeV1
_Diag = DateDiscoveryDiagnosticCodeV1
_Shape = _Err.INPUT_SHAPE_INVALID
_Source = _Err.SOURCE_BINDING_MISMATCH
_Original = _Err.ORIGINAL_ASSOCIATION_MISMATCH


@dataclass(frozen=True, slots=True)
class DateDiscoveryLimitsV1:
    max_input_nodes: int
    max_input_depth: int
    max_input_utf8_bytes: int
    max_source_tokens: int
    max_polygon_points_per_token: int
    max_token_codepoints: int
    max_observations: int
    max_derivations: int
    max_proposals: int
    max_diagnostics: int
    max_canonical_bytes: int

    def __post_init__(self) -> None:
        for item in fields(self):
            value = getattr(self, item.name)
            if type(value) is not int or not 0 < value < 2**63:
                raise DateDiscoveryError(_Shape, "method_profile.limits." + item.name)


LIMITS_V1 = DateDiscoveryLimitsV1(500000, 48, 4194304, 512, 64, 2048, 512, 512, 1024, 2048, 16777216)


@dataclass(frozen=True, slots=True)
class _LocalRecord:
    schema_id: str = field(default=SCHEMA_ID, init=False)
    record_version: str = field(default=RECORD_VERSION, init=False)

    def __post_init__(self) -> None:
        _validate_local_record(self)


@dataclass(frozen=True, slots=True)
class DateDiscoveryMethodProfileV1(_LocalRecord):
    component_version: str
    method_id: str
    method_version: str
    anchor_grammar_id: str
    anchor_grammar_version: str
    encoding_id: str
    encoding_version: str
    parser_callable: str
    parser_ruleset_id: str
    parser_source_sha256: str
    required_b2_extractor_version: str
    python_runtime_version: str
    unicode_database_version: str
    theta_a_reference: ConfigurationRefV1
    limits: DateDiscoveryLimitsV1
    profile_content_id: str


@dataclass(frozen=True, slots=True)
class DateOriginalAnchorV1(_LocalRecord):
    anchor_id: str
    context_id: str
    receipt_id: str
    image_id: str
    b2_purchase_date_field: StructuredField | None
    existing_c0: CandidateRecordV1 | None
    original_state: DateOriginalStateV1


@dataclass(frozen=True, slots=True)
class DateSourceObservationV1(_LocalRecord):
    observation_id: str
    context_id: str
    source_token: OcrSourceToken
    token_position: int
    observation_kind: DateObservationKindV1
    body_span: SourceCharacterSpanV1 | None
    anchor_span: SourceCharacterSpanV1 | None
    is_b2_date_reference: bool


@dataclass(frozen=True, slots=True)
class DateDerivationV1(_LocalRecord):
    derivation_id: str
    context_id: str
    observation_id: str
    parse_state: B3ParseState
    normalized_value: str | None
    interpretations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DateProposalV1(_LocalRecord):
    proposal_id: str
    context_id: str
    normalized_value: str
    derivation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DateDiscoveryDiagnosticV1(_LocalRecord):
    code: DateDiscoveryDiagnosticCodeV1
    token_ids: tuple[str, ...]
    observation_id: str | None


@dataclass(frozen=True, slots=True)
class DateDiscoveryResultV1(_LocalRecord):
    result_id: str
    context_id: str
    source_evidence: ReceiptSourceEvidence
    b2_result: B2ExtractionResult
    theta_a_reference: ConfigurationRefV1
    method_profile: DateDiscoveryMethodProfileV1
    existing_c0: CandidateRecordV1 | None
    original_anchor: DateOriginalAnchorV1
    observations: tuple[DateSourceObservationV1, ...]
    derivations: tuple[DateDerivationV1, ...]
    proposals: tuple[DateProposalV1, ...]
    diagnostics: tuple[DateDiscoveryDiagnosticV1, ...]
    status: DateDiscoveryStatusV1
    authority_scope: str

    def __post_init__(self) -> None:
        validate_date_discovery_result_v1(self)


# Only these exact classes may enter the typed encoding. Field specifications
# follow their declaration order, including init=False fields.
_LOCAL_RECORDS = (
    DateDiscoveryMethodProfileV1, DateOriginalAnchorV1, DateSourceObservationV1,
    DateDerivationV1, DateProposalV1, DateDiscoveryDiagnosticV1, DateDiscoveryResultV1,
)
_RECORD_TYPES = (
    Point, SourceProvenance, OcrSourceToken, SourceEvidenceGateResult,
    ReceiptSourceEvidence, StructuredField, ReceiptItemRow, ReceiptOutput,
    PreResolutionDisposition, B2ExtractionResult, ConfigurationRefV1,
    CandidateRecordV1, CandidateProvenanceV1, SourceCharacterSpanV1,
    DateDiscoveryLimitsV1, *_LOCAL_RECORDS,
)
_ENUM_TYPES = (
    SourceProcessingStatus, SourceEvidenceDecision, ReceiptFieldName, FieldStatus,
    ReceiptExtractionStatus, OutputStage, PolicyState, FailureStage, ConfigurationKind,
    ConfigurationState, CandidateRole, CandidateLimitStatus, CandidateSourceKind,
    B3ParseState, DateOriginalStateV1, DateObservationKindV1, DateDiscoveryStatusV1,
    DateDiscoveryDiagnosticCodeV1, DateDiscoveryErrorCodeV1,
)
_TAGS = {cls: f"{cls.__module__}.{cls.__name__}" for cls in (*_RECORD_TYPES, *_ENUM_TYPES)}
_ENUM_VALUES = {cls: tuple((member, member.value) for member in cls) for cls in _ENUM_TYPES}
_OVERRIDES = {
    (Point, "x"): int | float,
    (Point, "y"): int | float,
    (OcrSourceToken, "raw_confidence"): int | float | None,
    (StructuredField, "confidence"): int | float | None,
    (CandidateRecordV1, "preliminary_rank"): type(None),
}
_SCHEMAS = {}
for _cls in _RECORD_TYPES:
    _hints = get_type_hints(_cls)
    _SCHEMAS[_cls] = tuple(
        (f.name, _OVERRIDES.get((_cls, f.name), _hints[f.name])) for f in fields(_cls)
    )
_SORTED_FIELDS = {cls: tuple(sorted(k for k, _ in spec)) for cls, spec in _SCHEMAS.items()}
_ROOT_SPECS = (
    ("source_evidence", ReceiptSourceEvidence),
    ("b2_result", B2ExtractionResult),
    ("theta_a_reference", ConfigurationRefV1),
    ("method_profile", DateDiscoveryMethodProfileV1),
    ("existing_c0", CandidateRecordV1 | None),
)
_PROFILE_PINS = {
    "schema_id": SCHEMA_ID,
    "record_version": RECORD_VERSION,
    "component_version": "purchase-date-source-discovery-v1",
    "method_id": "purchase-date-single-token-observation",
    "method_version": "1",
    "anchor_grammar_id": "purchase-date-source-token-anchor",
    "anchor_grammar_version": "1",
    "encoding_id": "pantryproof-date-source-typed-json",
    "encoding_version": "1",
    "parser_callable": "pipeline.baseline_b3.parse_generic_date",
    "parser_ruleset_id": "B3-generic-rules-v0",
    "parser_source_sha256": PARSER_SOURCE_SHA256,
    "required_b2_extractor_version": "B2-layout-graph-v0",
    "python_runtime_version": PYTHON_RUNTIME_VERSION,
    "unicode_database_version": UNICODE_DATABASE_VERSION,
}
_DOMAINS = {
    DateDiscoveryMethodProfileV1: ("profile_content_id", "pantryproof-date-discovery-profile-v1"),
    DateOriginalAnchorV1: ("anchor_id", "pantryproof-date-original-anchor-v1"),
    DateSourceObservationV1: ("observation_id", "pantryproof-date-source-observation-v1"),
    DateDerivationV1: ("derivation_id", "pantryproof-date-source-derivation-v1"),
    DateProposalV1: ("proposal_id", "pantryproof-date-source-proposal-v1"),
    DateDiscoveryResultV1: ("result_id", "pantryproof-date-source-result-v1"),
}
_CONTEXT_DOMAIN = "pantryproof-date-discovery-context-v1"
_COLLECTION_CAPS = {
    (ReceiptSourceEvidence, "tokens"): "max_source_tokens",
    (OcrSourceToken, "polygon"): "max_polygon_points_per_token",
    (OcrSourceToken, "original_text"): "max_token_codepoints",
    (DateDiscoveryResultV1, "observations"): "max_observations",
    (DateDiscoveryResultV1, "derivations"): "max_derivations",
    (DateDiscoveryResultV1, "proposals"): "max_proposals",
    (DateDiscoveryResultV1, "diagnostics"): "max_diagnostics",
}
_MISSING = object()
_I64_MIN, _I64_MAX = -(2**63), 2**63 - 1


def _check_limit(limits: DateDiscoveryLimitsV1, name: str, value: int, path: str) -> None:
    if value > getattr(limits, name):
        raise DateDiscoveryError(_Err.RESOURCE_LIMIT_EXCEEDED, path, name)


def _matches(value: object, spec: object) -> bool:
    origin = get_origin(spec)
    if origin is UnionType:
        return any(_matches(value, variant) for variant in get_args(spec))
    return type(value) is (origin or spec)


def _enum_literal(value: Enum) -> str | None:
    literal = getattr(value, "value", _MISSING)
    if type(literal) is not str:
        return None
    for member, declared in _ENUM_VALUES[type(value)]:
        if value is member and literal == declared:
            return declared
    return None


class _InputBudget:
    def __init__(self, limits: DateDiscoveryLimitsV1):
        self.limits = limits
        self.nodes = 0
        self.utf8_bytes = 0
        self.active: set[int] = set()

    def charge_node(self, depth: int, path: str) -> None:
        _check_limit(self.limits, "max_input_depth", depth, path)
        self.nodes += 1
        _check_limit(self.limits, "max_input_nodes", self.nodes, path)

    def charge_text(self, text: str, path: str) -> None:
        # Every Unicode scalar needs at least one byte. Avoid encoding a huge
        # string simply to determine that it exceeds the remaining budget.
        _check_limit(self.limits, "max_input_utf8_bytes", self.utf8_bytes + len(text), path)
        for start in range(0, len(text), 256):
            try:
                size = len(text[start:start + 256].encode("utf-8", errors="strict"))
            except UnicodeEncodeError:
                size = None
            if size is None:
                raise DateDiscoveryError(_Shape, path)
            self.utf8_bytes += size
            _check_limit(self.limits, "max_input_utf8_bytes", self.utf8_bytes, path)

    def walk(self, value: object, spec: object, path: str, depth: int, cap: str | None = None) -> None:
        cls = type(value)
        if not _matches(value, spec) or id(value) in self.active:
            raise DateDiscoveryError(_Shape, path)
        if cls is int and not _I64_MIN <= value <= _I64_MAX:
            raise DateDiscoveryError(_Shape, path)
        if cls is float and not isfinite(value):
            raise DateDiscoveryError(_Shape, path)
        enum_text = None
        if cls in _ENUM_TYPES:
            enum_text = _enum_literal(value)
            if enum_text is None:
                raise DateDiscoveryError(_Shape, path)
        if cap == "max_polygon_points_per_token" and len(value) < 3:
            raise DateDiscoveryError(_Shape, path)
        if cap == "max_token_codepoints" and not value:
            raise DateDiscoveryError(_Shape, path)
        self.charge_node(depth, path)
        if cap is not None:
            _check_limit(self.limits, cap, len(value), path)
        if cls is str:
            self.charge_text(value, path)
            return
        if enum_text is not None:
            self.charge_text(enum_text, path)
            return
        if cls in (bool, int, float, type(None)):
            return
        self.active.add(id(value))
        try:
            if cls is tuple:
                tuple_spec = spec
                if get_origin(spec) is UnionType:
                    tuple_spec = next(s for s in get_args(spec) if get_origin(s) is tuple)
                (item_spec, _) = get_args(tuple_spec)
                for i, item in enumerate(value):
                    self.walk(item, item_spec, f"{path}[{i}]", depth + 1)
            else:
                for name, child_spec in _SCHEMAS[cls]:
                    child = getattr(value, name, _MISSING)
                    child_path = f"{path}.{name}"
                    self.walk(child, child_spec, child_path, depth + 1, _COLLECTION_CAPS.get((cls, name)))
                    _check_version(cls, name, child, child_path)
        finally:
            self.active.remove(id(value))


def _check_version(cls: type, name: str, value: object, path: str) -> None:
    expected = None
    if cls is ReceiptOutput:
        expected = {"contract_version": "0", "extractor_version": "B2-layout-graph-v0"}.get(name)
    elif name == "record_version":
        expected = RECORD_VERSION
    elif name == "schema_id" and cls in _LOCAL_RECORDS:
        expected = SCHEMA_ID
    if expected is not None and value != expected:
        raise DateDiscoveryError(_Err.PROFILE_UNSUPPORTED, path)


def _check_profile(profile: DateDiscoveryMethodProfileV1) -> None:
    for name, spec in _SCHEMAS[DateDiscoveryMethodProfileV1]:
        value = getattr(profile, name, _MISSING)
        path = f"method_profile.{name}"
        if not _matches(value, spec):
            raise DateDiscoveryError(_Shape, path)
        if name in _PROFILE_PINS and value != _PROFILE_PINS[name]:
            raise DateDiscoveryError(_Err.PROFILE_UNSUPPORTED, path)
        if name == "limits":
            for limit, _ in _SCHEMAS[DateDiscoveryLimitsV1]:
                number = getattr(value, limit, _MISSING)
                if type(number) is not int or not 0 < number <= _I64_MAX:
                    raise DateDiscoveryError(_Shape, f"{path}.{limit}")
                if number != getattr(LIMITS_V1, limit):
                    raise DateDiscoveryError(_Err.PROFILE_UNSUPPORTED, f"{path}.{limit}")
    runtime_checks = (
        (sys.implementation.name == "cpython" and sys.version == PYTHON_RUNTIME_VERSION, "python_runtime_version"),
        (unicodedata.unidata_version == UNICODE_DATABASE_VERSION, "unicode_database_version"),
        (RULESET_ID == "B3-generic-rules-v0", "parser_ruleset_id"),
        (B2_VERSION == "B2-layout-graph-v0", "required_b2_extractor_version"),
        (CONTRACT_VERSION == "0" and PROPOSED_CONTRACT_VERSION == "1", "record_version"),
    )
    for ok, name in runtime_checks:
        if not ok:
            raise DateDiscoveryError(_Err.PROFILE_UNSUPPORTED, f"method_profile.{name}")


def _string_chunks(text: str) -> Iterator[bytes]:
    yield b'"'
    for start in range(0, len(text), 256):
        yield json.dumps(text[start:start + 256], ensure_ascii=False)[1:-1].encode("utf-8")
    yield b'"'


def _mapping_chunks(items: Iterator[tuple[str, object]]) -> Iterator[bytes]:
    yield b"{"
    for index, (key, value) in enumerate(items):
        if index:
            yield b","
        yield b'"' + key.encode("ascii") + b'":'
        yield from _typed_chunks(value)
    yield b"}"


def _typed_chunks(value: object, omit: str | None = None) -> Iterator[bytes]:
    """Encode only an already bounded, type-checked graph."""
    cls = type(value)
    if value is None:
        yield b"null"
    elif cls is str:
        yield from _string_chunks(value)
    elif cls is bool:
        yield b'{"bool":true}' if value else b'{"bool":false}'
    elif cls is int:
        yield b'{"int":"' + str(value).encode("ascii") + b'"}'
    elif cls is float:
        yield b'{"binary64":"' + struct.pack(">d", value).hex().encode("ascii") + b'"}'
    elif cls in _ENUM_TYPES:
        yield b'{"enum_type":'
        yield from _string_chunks(_TAGS[cls])
        yield b',"value":'
        yield from _string_chunks(value.value)
        yield b"}"
    elif cls is tuple:
        yield b'{"tuple":['
        for i, member in enumerate(value):
            if i:
                yield b","
            yield from _typed_chunks(member)
        yield b"]}"
    else:
        yield b'{"fields":'
        yield from _mapping_chunks(
            (key, getattr(value, key)) for key in _SORTED_FIELDS[cls] if key != omit
        )
        yield b',"record_type":'
        yield from _string_chunks(_TAGS[cls])
        yield b"}"


class _Identifiers:
    """Stream each hash and retain bounded record references for collision checks."""

    def __init__(self, limits: DateDiscoveryLimitsV1):
        self.limits = limits
        self.preimages: dict[str, Callable[[], Iterator[bytes]]] = {}

    def identify(self, domain: str, chunks: Callable[[], Iterator[bytes]], path: str) -> str:
        prefix = domain.encode("ascii") + b"\0"
        count = len(prefix)
        _check_limit(self.limits, "max_canonical_bytes", count, path)
        digest = hashlib.sha256()
        digest.update(prefix)
        for chunk in chunks():
            count += len(chunk)
            _check_limit(self.limits, "max_canonical_bytes", count, path)
            digest.update(chunk)
        identifier = domain + ":sha256:" + digest.hexdigest()
        previous = self.preimages.get(identifier)
        # The encoder splits equal typed projections into identical chunks.
        if previous is not None:
            if any(a != b for a, b in zip_longest(previous(), chunks(), fillvalue=None)):
                raise DateDiscoveryError(_Err.CONTENT_ID_COLLISION, path)
        else:
            self.preimages[identifier] = chunks
        return identifier

    def record_id(self, record: _LocalRecord, path: str) -> str:
        name, domain = _DOMAINS[type(record)]
        return self.identify(domain, lambda: _typed_chunks(record, name), f"{path}.{name}")

    def seal(self, record: _LocalRecord, path: str) -> None:
        name, _ = _DOMAINS[type(record)]
        object.__setattr__(record, name, self.record_id(record, path))


def _new_record(cls: type, **values: object):
    """Private construction for records derived from checked inputs.

    Public constructors validate caller-provided records. The builder already
    has the bounded derivation and seals each record before it can escape.
    """
    record = object.__new__(cls)
    object.__setattr__(record, "schema_id", SCHEMA_ID)
    object.__setattr__(record, "record_version", RECORD_VERSION)
    for name, value in values.items():
        object.__setattr__(record, name, value)
    return record


def make_purchase_date_discovery_profile_v1(
    theta_a_reference: ConfigurationRefV1,
) -> DateDiscoveryMethodProfileV1:
    """Bind the frozen D1 profile to the caller's existing method reference."""
    values = {
        name: value for name, value in _PROFILE_PINS.items()
        if name not in ("schema_id", "record_version")
    }
    profile = _new_record(
        DateDiscoveryMethodProfileV1, **values,
        theta_a_reference=theta_a_reference, limits=LIMITS_V1,
    )
    _Identifiers(LIMITS_V1).seal(profile, "method_profile")
    profile.__post_init__()
    return profile


def _nonblank(value: str, path: str, code: _Err = _Shape) -> None:
    if not value or not any(not char.isspace() for char in value):
        raise DateDiscoveryError(code, path)


def _unique(values: tuple[str, ...], path: str, code: _Err) -> None:
    seen = set()
    for index, value in enumerate(values):
        if value in seen:
            raise DateDiscoveryError(code, f"{path}[{index}]")
        seen.add(value)


def _token_shape(token: OcrSourceToken, path: str) -> None:
    _nonblank(token.receipt_id, path + ".receipt_id")
    _nonblank(token.token_id, path + ".token_id")
    if not token.original_text:
        raise DateDiscoveryError(_Shape, path + ".original_text")
    if len(token.polygon) < 3:
        raise DateDiscoveryError(_Shape, path + ".polygon")


def _source_index(source: ReceiptSourceEvidence) -> dict[str, OcrSourceToken]:
    root = "source_evidence"
    _nonblank(source.receipt_id, root + ".receipt_id")
    _nonblank(source.image_id, root + ".image_id")
    provenance = source.provenance
    for name in ("source_system", "source_reference", "content_sha256"):
        value = getattr(provenance, name)
        if value is not None:
            _nonblank(value, root + ".provenance." + name)
    index = {}
    for i, token in enumerate(source.tokens):
        path = f"{root}.tokens[{i}]"
        _nonblank(token.receipt_id, path + ".receipt_id")
        if token.receipt_id != source.receipt_id:
            raise DateDiscoveryError(_Source, path + ".receipt_id")
        _nonblank(token.token_id, path + ".token_id")
        if token.token_id in index:
            raise DateDiscoveryError(_Source, path + ".token_id")
        index[token.token_id] = token
    gate = source.gate_result
    path = root + ".gate_result"
    _nonblank(gate.gate_result_id, path + ".gate_result_id")
    _nonblank(gate.receipt_id, path + ".receipt_id")
    if gate.receipt_id != source.receipt_id:
        raise DateDiscoveryError(_Source, path + ".receipt_id")
    _unique(gate.reasons, path + ".reasons", _Source)
    if gate.decision is SourceEvidenceDecision.INSUFFICIENT and not gate.reasons:
        raise DateDiscoveryError(_Shape, path + ".reasons")
    return index


def _field_content(field_: StructuredField, path: str) -> None:
    _nonblank(field_.field_id, path + ".field_id")
    _nonblank(field_.receipt_id, path + ".receipt_id")
    if field_.item_row_id is not None:
        _nonblank(field_.item_row_id, path + ".item_row_id")
    if field_.status is FieldStatus.EXTRACTED:
        if field_.value is None:
            raise DateDiscoveryError(_Shape, path + ".value")
        _nonblank(field_.value, path + ".value")
        if not field_.source_token_ids:
            raise DateDiscoveryError(_Shape, path + ".source_token_ids")
        if field_.unresolved_reason is not None:
            raise DateDiscoveryError(_Shape, path + ".unresolved_reason")
    else:
        for name in ("value", "confidence"):
            if getattr(field_, name) is not None:
                raise DateDiscoveryError(_Shape, f"{path}.{name}")
        if field_.unresolved_reason is None:
            raise DateDiscoveryError(_Shape, path + ".unresolved_reason")
        _nonblank(field_.unresolved_reason, path + ".unresolved_reason")


def _b2_field(
    b2: B2ExtractionResult, source: ReceiptSourceEvidence, tokens: dict[str, OcrSourceToken],
) -> StructuredField | None:
    output = b2.receipt_output
    disposition = b2.pre_resolution_disposition
    if output is None:
        root = "b2_result.pre_resolution_disposition"
        if disposition is None:
            raise DateDiscoveryError(_Source, root)
        for name, ok in (
            ("state", disposition.state is PolicyState.FALLBACK_NO_UPDATE),
            ("gate_result", disposition.gate_result is source.gate_result
             and source.gate_result.decision is SourceEvidenceDecision.INSUFFICIENT),
            ("failure_stage", disposition.failure_stage is None),
            ("failure_reason", disposition.failure_reason is None),
        ):
            if not ok:
                raise DateDiscoveryError(_Source, f"{root}.{name}")
        return None

    root = "b2_result.receipt_output"
    _nonblank(output.receipt_id, root + ".receipt_id")
    if output.receipt_id != source.receipt_id:
        raise DateDiscoveryError(_Source, root + ".receipt_id")
    if source.gate_result.decision is not SourceEvidenceDecision.SUFFICIENT:
        raise DateDiscoveryError(_Source, root + ".source_evidence")
    if disposition is not None:
        raise DateDiscoveryError(_Source, "b2_result.pre_resolution_disposition")

    field_ids: set[str] = set()
    row_ids: set[str] = set()
    n_extracted = 0
    n_fields = 0

    def verify(field_: StructuredField, name: ReceiptFieldName, row_id: str | None, path: str) -> int:
        nonlocal n_extracted, n_fields
        _field_content(field_, path)
        if field_.field_id in field_ids:
            raise DateDiscoveryError(_Source, path + ".field_id")
        field_ids.add(field_.field_id)
        for key, expected in (("receipt_id", source.receipt_id), ("field_name", name), ("item_row_id", row_id)):
            if getattr(field_, key) != expected:
                raise DateDiscoveryError(_Source, f"{path}.{key}")
        _unique(field_.source_token_ids, path + ".source_token_ids", _Source)
        for index, token_id in enumerate(field_.source_token_ids):
            if token_id not in tokens:
                raise DateDiscoveryError(_Source, f"{path}.source_token_ids[{index}]")
        extracted = int(field_.status is FieldStatus.EXTRACTED)
        n_fields += 1
        n_extracted += extracted
        return extracted

    verify(output.store_name, ReceiptFieldName.STORE_NAME, None, root + ".store_name")
    verify(output.purchase_date, ReceiptFieldName.PURCHASE_DATE, None, root + ".purchase_date")
    for i, row in enumerate(output.items):
        path = f"{root}.items[{i}]"
        _nonblank(row.row_id, path + ".row_id")
        if row.row_id in row_ids:
            raise DateDiscoveryError(_Source, path + ".row_id")
        row_ids.add(row.row_id)
        if row.receipt_id != source.receipt_id:
            raise DateDiscoveryError(_Source, path + ".receipt_id")
        extracted = 0
        for key, field_name in (
            ("description", ReceiptFieldName.ITEM_DESCRIPTION),
            ("quantity", ReceiptFieldName.QUANTITY),
            ("unit_price", ReceiptFieldName.UNIT_PRICE),
            ("line_total", ReceiptFieldName.LINE_TOTAL),
        ):
            extracted += verify(getattr(row, key), field_name, row.row_id, f"{path}.{key}")
        if not extracted:
            raise DateDiscoveryError(_Source, path)
        if row.pantry_product_identity is not None:
            _nonblank(row.pantry_product_identity, path + ".pantry_product_identity")
    verify(output.receipt_total, ReceiptFieldName.RECEIPT_TOTAL, None, root + ".receipt_total")
    if output.source_evidence is not source:
        raise DateDiscoveryError(_Source, root + ".source_evidence")
    expected = ReceiptExtractionStatus.PARTIAL
    if n_extracted == 0:
        expected = ReceiptExtractionStatus.FAILED
    elif output.items and n_extracted == n_fields:
        expected = ReceiptExtractionStatus.EXTRACTED
    if output.extraction_status is not expected:
        raise DateDiscoveryError(_Source, root + ".extraction_status")
    if output.output_stage is not OutputStage.PRE_REVIEW_AUTOMATIC:
        raise DateDiscoveryError(_Source, root + ".output_stage")
    return output.purchase_date


def _theta_shape(ref: ConfigurationRefV1, path: str) -> None:
    if ref.kind is not ConfigurationKind.THETA_A:
        raise DateDiscoveryError(_Shape, path + ".kind")
    _nonblank(ref.configuration_id, path + ".configuration_id")
    _nonblank(ref.configuration_version, path + ".configuration_version")
    if ref.content_hash is not None:
        _nonblank(ref.content_hash, path + ".content_hash")
    if ref.state is ConfigurationState.READY:
        if ref.content_hash is None:
            raise DateDiscoveryError(_Shape, path + ".content_hash")
        if ref.status_reason is not None:
            raise DateDiscoveryError(_Shape, path + ".status_reason")
    elif ref.state in (ConfigurationState.NOT_READY, ConfigurationState.NOT_VALID):
        if ref.status_reason is None:
            raise DateDiscoveryError(_Shape, path + ".status_reason")
        _nonblank(ref.status_reason, path + ".status_reason")
    else:
        raise DateDiscoveryError(_Shape, path + ".state")


def _verify_span(
    span: SourceCharacterSpanV1, token: OcrSourceToken, path: str, code: _Err,
) -> None:
    if span.token_id != token.token_id:
        raise DateDiscoveryError(code, path + ".token_id")
    if span.start < 0:
        raise DateDiscoveryError(code, path + ".start")
    if not span.start < span.end <= len(token.original_text):
        raise DateDiscoveryError(code, path + ".end")
    if span.text != token.original_text[span.start:span.end]:
        raise DateDiscoveryError(code, path + ".text")


def _verify_original(
    original: CandidateRecordV1 | None,
    purchase: StructuredField | None,
    tokens: dict[str, OcrSourceToken] | None,
    path: str = "existing_c0",
) -> None:
    if original is None:
        return
    if purchase is None or purchase.status is not FieldStatus.EXTRACTED:
        raise DateDiscoveryError(_Original, path)
    for key, expected in (
        ("candidate_id", purchase.field_id + ":c0"),
        ("receipt_id", purchase.receipt_id),
        ("field_id", purchase.field_id),
        ("c0_candidate_id", original.candidate_id),
        ("value", purchase.value),
        ("role", CandidateRole.ORIGINAL),
        ("limit_status", CandidateLimitStatus.RETAINED),
        ("preliminary_rank", None),
        ("overflow_reason", None),
    ):
        if getattr(original, key) != expected:
            raise DateDiscoveryError(_Original, f"{path}.{key}")
    _nonblank(original.normalized_dedup_key, path + ".normalized_dedup_key", _Original)
    if not original.provenance:
        raise DateDiscoveryError(_Original, path + ".provenance")
    source_ids = set(purchase.source_token_ids)
    provenance_ids = set()
    for i, item in enumerate(original.provenance):
        prefix = f"{path}.provenance[{i}]"
        _nonblank(item.provenance_id, prefix + ".provenance_id", _Original)
        if item.provenance_id in provenance_ids:
            raise DateDiscoveryError(_Original, prefix + ".provenance_id")
        provenance_ids.add(item.provenance_id)
        for key, expected in (
            ("receipt_id", purchase.receipt_id),
            ("field_id", purchase.field_id),
            ("candidate_id", original.candidate_id),
            ("source_kind", CandidateSourceKind.ORIGINAL),
            ("original_observed_value", purchase.value),
            ("source_token_ids", purchase.source_token_ids),
            ("source_order_relationship", None),
            ("source_order_position", None),
            ("generic_rule_id", None),
            ("resource_snapshot_id", None),
        ):
            if getattr(item, key) != expected:
                raise DateDiscoveryError(_Original, f"{prefix}.{key}")
        for j, span in enumerate(item.source_spans):
            span_path = f"{prefix}.source_spans[{j}]"
            if span.token_id not in source_ids:
                raise DateDiscoveryError(_Original, span_path + ".token_id")
            if tokens is not None:
                _verify_span(span, tokens[span.token_id], span_path, _Original)
            elif not 0 <= span.start < span.end or span.end - span.start != len(span.text):
                raise DateDiscoveryError(_Original, span_path)


def _checked_context(roots: dict[str, object], limits: DateDiscoveryLimitsV1):
    for name, spec in _ROOT_SPECS:
        if not _matches(roots[name], spec):
            raise DateDiscoveryError(_Err.INPUT_TYPE_INVALID, name)
    profile = roots["method_profile"]
    _check_profile(profile)
    budget = _InputBudget(limits)
    budget.charge_node(0, "context")
    for name, spec in _ROOT_SPECS:
        budget.walk(roots[name], spec, name, 1)

    source = roots["source_evidence"]
    tokens = _source_index(source)
    purchase = _b2_field(roots["b2_result"], source, tokens)
    theta = roots["theta_a_reference"]
    _theta_shape(theta, "theta_a_reference")
    _theta_shape(profile.theta_a_reference, "method_profile.theta_a_reference")
    if theta != profile.theta_a_reference:
        raise DateDiscoveryError(_Err.THETA_A_ASSOCIATION_MISMATCH, "theta_a_reference")
    _verify_original(roots["existing_c0"], purchase, tokens)

    ids = _Identifiers(limits)
    if ids.record_id(profile, "method_profile") != profile.profile_content_id:
        raise DateDiscoveryError(_Err.CONTENT_ID_MISMATCH, "method_profile.profile_content_id")
    context_id = ids.identify(
        _CONTEXT_DOMAIN, lambda: _mapping_chunks(iter(sorted(roots.items()))), "result.context_id"
    )
    return purchase, context_id, ids


_ANCHOR_PREFIX = re.compile(r"^\s*(?:DATE|PURCHASE\s+DATE|TRANSACTION\s+DATE)\b", re.IGNORECASE)
_Obs = DateObservationKindV1


def _split_literal(text: str) -> tuple[DateObservationKindV1, int, int]:
    match = _ANCHOR_PREFIX.match(text)
    if match is None:
        return _Obs.WHOLE_TOKEN, 0, len(text)
    start, end = match.end(), len(text)
    while start < end and text[start].isspace():
        start += 1
    if start < end and text[start] in ":#-":
        start += 1
        while start < end and text[start].isspace():
            start += 1
    if start == end:
        return _Obs.ANCHOR_ONLY, end, end
    while end > start and text[end - 1].isspace():
        end -= 1
    if text.find("\n", start, end) >= 0:
        return _Obs.WHOLE_TOKEN, 0, len(text)
    return _Obs.ANCHORED_BODY, start, end


def _iso(text: object) -> bool:
    if type(text) is not str or len(text) != 10:
        return False
    try:
        return date.fromisoformat(text).isoformat() == text
    except ValueError:
        return False


def _parse_parts_ok(state: object, normalized: object, interpretations: object) -> bool:
    if type(state) is not B3ParseState or _enum_literal(state) is None or type(interpretations) is not tuple:
        return False
    count = {B3ParseState.VALID: 1, B3ParseState.AMBIGUOUS: 2, B3ParseState.INVALID: 0}.get(state)
    if len(interpretations) != count or not all(_iso(value) for value in interpretations):
        return False
    if len(set(interpretations)) != count:
        return False
    if state is B3ParseState.VALID:
        return type(normalized) is str and normalized == interpretations[0]
    return normalized is None


def _parse(literal: str, index: int) -> DateParseResult:
    path = f"result.derivations[{index}]"
    try:
        result = parse_generic_date(literal)
    except MemoryError:
        raise
    except Exception:
        result = _MISSING
    if type(result) is not DateParseResult:
        raise DateDiscoveryError(_Err.PARSER_CONTRACT_MISMATCH, path)
    original = getattr(result, "original", _MISSING)
    if type(original) is not str or original != literal or not _parse_parts_ok(
        getattr(result, "state", _MISSING),
        getattr(result, "normalized_value", _MISSING),
        getattr(result, "interpretations", _MISSING),
    ):
        raise DateDiscoveryError(_Err.PARSER_CONTRACT_MISMATCH, path)
    return result


def _original_state(purchase: StructuredField | None, original: CandidateRecordV1 | None) -> DateOriginalStateV1:
    state = DateOriginalStateV1
    if purchase is None:
        return state.NO_B2_OUTPUT
    if purchase.status is FieldStatus.UNRESOLVED:
        return state.UNRESOLVED_NO_C0
    if purchase.status is FieldStatus.MISSING:
        return state.MISSING_NO_C0
    return state.EXTRACTED_WITH_SUPPLIED_C0 if original is not None else state.EXTRACTED_NO_SUPPLIED_C0


class _Scan:
    """Collect bounded observations and links before hashing any child."""

    def __init__(self, limits: DateDiscoveryLimitsV1):
        self.limits = limits
        self.observations: list[DateSourceObservationV1] = []
        self.derivations: list[tuple[int, DateParseResult]] = []
        self.groups: dict[str, list[int]] = {}
        self.diagnostics: list[tuple[DateDiscoveryDiagnosticCodeV1, tuple[str, ...], int | None]] = []
        self.seen_diagnostics: set[tuple[DateDiscoveryDiagnosticCodeV1, tuple[str, ...], int | None]] = set()

    def check_append(self, collection: str, index: int) -> None:
        _check_limit(self.limits, f"max_{collection}", index + 1, f"result.{collection}[{index}]")

    def diagnostic(self, code: DateDiscoveryDiagnosticCodeV1, token_ids: tuple[str, ...] = (), obs: int | None = None) -> None:
        key = (code, token_ids, obs)
        if key not in self.seen_diagnostics:
            self.check_append("diagnostics", len(self.diagnostics))
            self.seen_diagnostics.add(key)
            self.diagnostics.append(key)

    def structured(self, source: ReceiptSourceEvidence, purchase: StructuredField, original: CandidateRecordV1 | None, context_id: str) -> None:
        refs = set(purchase.source_token_ids)
        ordered_refs = tuple(t.token_id for t in source.tokens if t.token_id in refs)
        splits = tuple(_split_literal(t.original_text) for t in source.tokens)
        if purchase.status is not FieldStatus.EXTRACTED:
            self.diagnostic(_Diag.NO_METHOD_READY_ORIGINAL, ordered_refs)
        elif original is None:
            self.diagnostic(_Diag.NO_SUPPLIED_C0, ordered_refs)
        if len(refs) > 1:
            self.diagnostic(_Diag.B2_MULTI_TOKEN_CONTEXT_UNCOMPOSED, ordered_refs)
        if purchase.status is FieldStatus.EXTRACTED and not any(
            token.token_id in refs and kind is not _Obs.ANCHOR_ONLY
            and token.original_text[start:end] == purchase.value
            for token, (kind, start, end) in zip(source.tokens, splits, strict=True)
        ):
            self.diagnostic(_Diag.B2_VALUE_NOT_SINGLE_TOKEN_SOURCE, ordered_refs)
        for index, (token, split) in enumerate(zip(source.tokens, splits, strict=True)):
            self.observe(token, index, split, token.token_id in refs, context_id)
        if not self.groups:
            self.diagnostic(_Diag.NO_SUPPORTED_DATE_PROPOSALS)

    def observe(self, token: OcrSourceToken, index: int, split, referenced: bool, context_id: str) -> None:
        self.check_append("observations", index)
        kind, start, end = split
        text = token.original_text
        body = None if kind is _Obs.ANCHOR_ONLY else SourceCharacterSpanV1(token.token_id, start, end, text[start:end])
        anchor = None if kind is _Obs.WHOLE_TOKEN else SourceCharacterSpanV1(token.token_id, 0, start, text[:start])
        self.observations.append(_new_record(
            DateSourceObservationV1, context_id=context_id, source_token=token, token_position=index,
            observation_kind=kind, body_span=body, anchor_span=anchor, is_b2_date_reference=referenced,
        ))
        if body is None:
            self.diagnostic(_Diag.ANCHOR_WITHOUT_BODY, (token.token_id,), index)
            return
        derivation_index = len(self.derivations)
        parsed = _parse(body.text, derivation_index)
        self.check_append("derivations", derivation_index)
        self.derivations.append((index, parsed))
        for value in parsed.interpretations:
            if value not in self.groups:
                self.check_append("proposals", len(self.groups))
                self.groups[value] = []
            # A parser result contains no duplicate interpretation.
            self.groups[value].append(derivation_index)
        if parsed.state is B3ParseState.INVALID:
            self.diagnostic(_Diag.INVALID_OR_UNSUPPORTED_LITERAL, (token.token_id,), index)
        elif parsed.state is B3ParseState.AMBIGUOUS:
            self.diagnostic(_Diag.AMBIGUOUS_INTERPRETATIONS_RETAINED, (token.token_id,), index)


def _build_result(roots: dict[str, object]) -> DateDiscoveryResultV1:
    purchase, context_id, ids = _checked_context(roots, LIMITS_V1)
    source = roots["source_evidence"]
    original = roots["existing_c0"]
    scan = _Scan(LIMITS_V1)
    status = DateDiscoveryStatusV1
    if purchase is None:
        scan.diagnostic(_Diag.STORED_SOURCE_INSUFFICIENT)
        scan.diagnostic(_Diag.NO_METHOD_READY_ORIGINAL)
        outcome = status.NOT_PROCESSABLE_STORED_FALLBACK
    else:
        scan.structured(source, purchase, original, context_id)
        outcome = status.COMPLETE_WITH_PROPOSALS if scan.groups else status.COMPLETE_NO_PROPOSALS

    anchor = _new_record(
        DateOriginalAnchorV1, context_id=context_id, receipt_id=source.receipt_id,
        image_id=source.image_id, b2_purchase_date_field=purchase, existing_c0=original,
        original_state=_original_state(purchase, original),
    )
    ids.seal(anchor, "result.original_anchor")
    for i, observation in enumerate(scan.observations):
        ids.seal(observation, f"result.observations[{i}]")
    derivations = []
    for i, (position, parsed) in enumerate(scan.derivations):
        record = _new_record(
            DateDerivationV1, context_id=context_id, observation_id=scan.observations[position].observation_id,
            parse_state=parsed.state, normalized_value=parsed.normalized_value, interpretations=parsed.interpretations,
        )
        ids.seal(record, f"result.derivations[{i}]")
        derivations.append(record)
    proposals = []
    for i, (value, contributors) in enumerate(scan.groups.items()):
        record = _new_record(
            DateProposalV1, context_id=context_id, normalized_value=value,
            derivation_ids=tuple(derivations[j].derivation_id for j in contributors),
        )
        ids.seal(record, f"result.proposals[{i}]")
        proposals.append(record)
    diagnostics = tuple(
        _new_record(
            DateDiscoveryDiagnosticV1, code=code, token_ids=token_ids,
            observation_id=None if position is None else scan.observations[position].observation_id,
        )
        for code, token_ids, position in scan.diagnostics
    )
    result = _new_record(
        DateDiscoveryResultV1, context_id=context_id, **roots, original_anchor=anchor,
        observations=tuple(scan.observations), derivations=tuple(derivations),
        proposals=tuple(proposals), diagnostics=diagnostics, status=outcome,
        authority_scope=AUTHORITY_SCOPE,
    )
    ids.seal(result, "result")
    return result


_LOCAL_PATHS = {
    DateDiscoveryMethodProfileV1: "method_profile",
    DateOriginalAnchorV1: "result.original_anchor",
    DateSourceObservationV1: "result.observations[0]",
    DateDerivationV1: "result.derivations[0]",
    DateProposalV1: "result.proposals[0]",
    DateDiscoveryDiagnosticV1: "result.diagnostics[0]",
}
_OBSERVATION_DIAGNOSTICS = (
    _Diag.ANCHOR_WITHOUT_BODY, _Diag.INVALID_OR_UNSUPPORTED_LITERAL,
    _Diag.AMBIGUOUS_INTERPRETATIONS_RETAINED,
)
_TOKENLESS_DIAGNOSTICS = (_Diag.STORED_SOURCE_INSUFFICIENT, _Diag.NO_SUPPORTED_DATE_PROPOSALS)


def _validate_local_record(record: _LocalRecord) -> None:
    """Check invariants available without an aggregate's live source roots."""
    cls = type(record)
    if cls not in _LOCAL_PATHS:
        raise DateDiscoveryError(_Err.INPUT_TYPE_INVALID, "result")
    path = _LOCAL_PATHS[cls]
    if cls is DateDiscoveryMethodProfileV1:
        _check_profile(record)
    _InputBudget(LIMITS_V1).walk(record, cls, path, 0)
    if cls is not DateDiscoveryDiagnosticV1 and cls is not DateDiscoveryMethodProfileV1:
        _nonblank(record.context_id, path + ".context_id")

    if cls is DateDiscoveryMethodProfileV1:
        _theta_shape(record.theta_a_reference, path + ".theta_a_reference")
    elif cls is DateOriginalAnchorV1:
        _nonblank(record.receipt_id, path + ".receipt_id")
        _nonblank(record.image_id, path + ".image_id")
        purchase = record.b2_purchase_date_field
        if purchase is not None:
            prefix = path + ".b2_purchase_date_field"
            _field_content(purchase, prefix)
            if (purchase.field_name is not ReceiptFieldName.PURCHASE_DATE
                    or purchase.item_row_id is not None or purchase.receipt_id != record.receipt_id):
                raise DateDiscoveryError(_Source, prefix)
            _unique(purchase.source_token_ids, prefix + ".source_token_ids", _Source)
        _verify_original(record.existing_c0, purchase, None, path + ".existing_c0")
        if record.original_state is not _original_state(purchase, record.existing_c0):
            raise DateDiscoveryError(_Original, path + ".original_state")
    elif cls is DateSourceObservationV1:
        _token_shape(record.source_token, path + ".source_token")
        if not 0 <= record.token_position < LIMITS_V1.max_source_tokens:
            raise DateDiscoveryError(_Shape, path + ".token_position")
        kind, start, end = _split_literal(record.source_token.original_text)
        if record.observation_kind is not kind:
            raise DateDiscoveryError(_Source, path + ".observation_kind")
        for key, interval in (
            ("body_span", None if kind is _Obs.ANCHOR_ONLY else (start, end)),
            ("anchor_span", None if kind is _Obs.WHOLE_TOKEN else (0, start)),
        ):
            span = getattr(record, key)
            prefix = f"{path}.{key}"
            if interval is None:
                if span is not None:
                    raise DateDiscoveryError(_Source, prefix)
            elif span is None or (span.start, span.end) != interval:
                raise DateDiscoveryError(_Source, prefix)
            else:
                _verify_span(span, record.source_token, prefix, _Source)
    elif cls is DateDerivationV1:
        _nonblank(record.observation_id, path + ".observation_id")
        if not _parse_parts_ok(record.parse_state, record.normalized_value, record.interpretations):
            raise DateDiscoveryError(_Err.PARSER_CONTRACT_MISMATCH, path)
    elif cls is DateProposalV1:
        if not _iso(record.normalized_value):
            raise DateDiscoveryError(_Shape, path + ".normalized_value")
        if not record.derivation_ids or len(record.derivation_ids) > LIMITS_V1.max_derivations:
            raise DateDiscoveryError(_Shape, path + ".derivation_ids")
        _unique(record.derivation_ids, path + ".derivation_ids", _Source)
        for i, value in enumerate(record.derivation_ids):
            _nonblank(value, f"{path}.derivation_ids[{i}]")
    else:
        _unique(record.token_ids, path + ".token_ids", _Source)
        for i, token_id in enumerate(record.token_ids):
            _nonblank(token_id, f"{path}.token_ids[{i}]")
        if record.code in _OBSERVATION_DIAGNOSTICS:
            if record.observation_id is None or len(record.token_ids) != 1:
                raise DateDiscoveryError(_Source, path)
            _nonblank(record.observation_id, path + ".observation_id")
        elif record.observation_id is not None or (record.code in _TOKENLESS_DIAGNOSTICS and record.token_ids):
            raise DateDiscoveryError(_Source, path)

    if cls in _DOMAINS:
        name, _ = _DOMAINS[cls]
        if _Identifiers(LIMITS_V1).record_id(record, path) != getattr(record, name):
            raise DateDiscoveryError(_Err.CONTENT_ID_MISMATCH, f"{path}.{name}")


_EXACT_REFERENCES = {
    DateDiscoveryResultV1: dict((name, _Source) for name, _ in _ROOT_SPECS),
    DateOriginalAnchorV1: {
        "b2_purchase_date_field": _Source, "existing_c0": _Original,
    },
    DateSourceObservationV1: {"source_token": _Source},
}


def _compare_result(
    supplied: object, expected: object, spec: object, path: str, stale_ids: list[str],
    *, cap: str | None = None, mismatch: _Err = _Source,
) -> None:
    """Compare only against the bounded expected shape, without encoding supplied children."""
    if not _matches(supplied, spec):
        raise DateDiscoveryError(_Shape, path)
    if cap is not None:
        _check_limit(LIMITS_V1, cap, len(supplied), f"{path}[{getattr(LIMITS_V1, cap)}]")
    cls = type(expected)
    if type(supplied) is not cls:
        raise DateDiscoveryError(mismatch, path)
    if cls is tuple:
        if len(supplied) != len(expected):
            raise DateDiscoveryError(mismatch, path)
        # Expected tuple lengths are already bounded by the scan.
        tuple_spec = spec if get_origin(spec) is tuple else next(
            s for s in get_args(spec) if get_origin(s) is tuple
        )
        item_spec, _ = get_args(tuple_spec)
        for i, (actual, wanted) in enumerate(zip(supplied, expected, strict=True)):
            _compare_result(actual, wanted, item_spec, f"{path}[{i}]", stale_ids, mismatch=mismatch)
        return
    if cls in _SCHEMAS:
        refs = _EXACT_REFERENCES.get(cls, {})
        own_id = _DOMAINS[cls][0] if cls in _DOMAINS else None
        for name, child_spec in _SCHEMAS[cls]:
            actual = getattr(supplied, name, _MISSING)
            wanted = getattr(expected, name)
            prefix = f"{path}.{name}"
            if not _matches(actual, child_spec):
                raise DateDiscoveryError(_Shape, prefix)
            _check_version(cls, name, actual, prefix)
            if name in refs:
                if actual is not wanted:
                    raise DateDiscoveryError(refs[name], prefix)
                continue
            child_mismatch = _Err.CONTENT_ID_MISMATCH if name in (own_id, "context_id") else mismatch
            _compare_result(
                actual, wanted, child_spec, prefix, stale_ids,
                cap=_COLLECTION_CAPS.get((cls, name)), mismatch=child_mismatch,
            )
        return
    if cls is int and not _I64_MIN <= supplied <= _I64_MAX:
        raise DateDiscoveryError(_Shape, path)
    if cls is float:
        if not isfinite(supplied):
            raise DateDiscoveryError(_Shape, path)
        equal = struct.pack(">d", supplied) == struct.pack(">d", expected)
    elif cls in _ENUM_TYPES:
        if _enum_literal(supplied) is None:
            raise DateDiscoveryError(_Shape, path)
        equal = supplied is expected
    else:
        equal = supplied == expected
    if not equal:
        if cls is str and len(supplied) <= LIMITS_V1.max_input_utf8_bytes:
            # The normal comparison is allocation-free. Check Unicode shape for
            # mismatches within the bounded size of an admissible source string.
            _InputBudget(LIMITS_V1).charge_text(supplied, path)
        if mismatch is _Err.CONTENT_ID_MISMATCH:
            stale_ids.append(path)
        else:
            raise DateDiscoveryError(mismatch, path)


def validate_date_discovery_result_v1(result: DateDiscoveryResultV1) -> None:
    """Rebuild the complete discovery from its retained live input references."""
    if type(result) is not DateDiscoveryResultV1:
        raise DateDiscoveryError(_Err.INPUT_TYPE_INVALID, "result")
    roots = {}
    for name, spec in _ROOT_SPECS:
        value = getattr(result, name, _MISSING)
        if not _matches(value, spec):
            raise DateDiscoveryError(_Shape, f"result.{name}")
        roots[name] = value
    expected = _build_result(roots)
    stale_ids: list[str] = []
    _compare_result(result, expected, DateDiscoveryResultV1, "result", stale_ids)
    if stale_ids:
        raise DateDiscoveryError(_Err.CONTENT_ID_MISMATCH, stale_ids[0])
