"""Strict synthetic conformance for the approved receipt-presentation V1 design.

This module validates the language-neutral presentation envelope only.  It does
not run OCR, infer source-gate decisions, recompute extraction completeness, or
accept the test-only fixture wrapper.  Callers must supply the request/image
identities that the result is expected to belong to.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import json
import math
import re
from types import MappingProxyType
from typing import Any, NoReturn


class ConformanceViolation(ValueError):
    """A deterministic receipt-presentation V1 rejection."""

    __slots__ = ("code", "path", "detail")

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code} at {path}: {detail}")


@dataclass(frozen=True, slots=True)
class PresentationProvenance:
    source_system: str
    source_reference: str
    content_sha256: str | None


@dataclass(frozen=True, slots=True)
class PresentationSource:
    type: str
    provenance: PresentationProvenance


@dataclass(frozen=True, slots=True)
class PresentationFailure:
    stage: str
    code: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class PresentationOutcome:
    status: str
    failure: PresentationFailure | None


@dataclass(frozen=True, slots=True)
class PresentationSourceEvidence:
    source_processing_status: str
    token_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PresentationSourceGate:
    gate_result_id: str
    decision: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PresentationProducer:
    producer_id: str
    producer_version: str


@dataclass(frozen=True, slots=True)
class PresentationAutomaticExtraction:
    stage: str
    extraction_status: str
    producer: PresentationProducer


@dataclass(frozen=True, slots=True)
class PresentationField:
    field_id: str
    role: str
    status: str
    original_automatic_value: str | None
    presentation_value: str | None
    absence_reason: str | None
    source_token_ids: tuple[str, ...]
    native_confidence: Decimal | None


@dataclass(frozen=True, slots=True)
class PresentationItemRow:
    row_id: str
    fields: tuple[PresentationField, ...]


@dataclass(frozen=True, slots=True)
class PresentationReceipt:
    receipt_id: str
    currency_code: str
    receipt_fields: tuple[PresentationField, ...]
    item_rows: tuple[PresentationItemRow, ...]


@dataclass(frozen=True, slots=True)
class ReceiptPresentationV1:
    schema_name: str
    schema_version: str
    source_contract_version: str
    request_id: str
    image_id: str
    source: PresentationSource
    outcome: PresentationOutcome
    source_evidence: PresentationSourceEvidence | None
    source_gate: PresentationSourceGate | None
    automatic_extraction: PresentationAutomaticExtraction | None
    receipt: PresentationReceipt | None


_TOP_MEMBERS = frozenset(
    {
        "schemaName",
        "schemaVersion",
        "sourceContractVersion",
        "requestId",
        "imageId",
        "source",
        "outcome",
        "sourceEvidence",
        "sourceGate",
        "automaticExtraction",
        "receipt",
    }
)
_SOURCE_MEMBERS = frozenset({"type", "provenance"})
_PROVENANCE_MEMBERS = frozenset(
    {"sourceSystem", "sourceReference", "contentSha256"}
)
_OUTCOME_MEMBERS = frozenset({"status", "failure"})
_FAILURE_MEMBERS = frozenset({"stage", "code", "retryable"})
_EVIDENCE_MEMBERS = frozenset({"sourceProcessingStatus", "tokenIds"})
_GATE_MEMBERS = frozenset({"gateResultId", "decision", "reasons"})
_EXTRACTION_MEMBERS = frozenset({"stage", "extractionStatus", "producer"})
_PRODUCER_MEMBERS = frozenset({"producerId", "producerVersion"})
_RECEIPT_MEMBERS = frozenset(
    {"receiptId", "currencyCode", "receiptFields", "itemRows"}
)
_ROW_MEMBERS = frozenset({"rowId", "fields"})
_FIELD_MEMBERS = frozenset(
    {
        "fieldId",
        "role",
        "status",
        "originalAutomaticValue",
        "presentationValue",
        "absenceReason",
        "sourceTokenIds",
        "nativeConfidence",
    }
)

_OUTCOME_STATUSES = frozenset(
    {
        "RESULT_AVAILABLE",
        "SOURCE_EVIDENCE_INSUFFICIENT",
        "PROCESSING_UNAVAILABLE",
        "PROCESSING_FAILED",
    }
)
_FAILURE_STAGES = frozenset(
    {"AVAILABILITY", "OCR", "SOURCE_GATE", "EXTRACTION", "PRESENTATION_ADAPTER"}
)
_EVIDENCE_STATUSES = frozenset(
    {"RECEIVED", "OCR_COMPLETED", "OCR_PARTIAL", "OCR_FAILED"}
)
_GATE_DECISIONS = frozenset({"SUFFICIENT", "INSUFFICIENT"})
_EXTRACTION_STATUSES = frozenset({"EXTRACTED", "PARTIAL", "FAILED"})
_FIELD_STATUSES = frozenset({"EXTRACTED", "MISSING", "UNRESOLVED"})
_FIELD_ROLES = frozenset(
    {
        "STORE_NAME",
        "PURCHASE_DATE",
        "ITEM_DESCRIPTION",
        "QUANTITY",
        "UNIT_PRICE",
        "LINE_TOTAL",
        "RECEIPT_TOTAL",
    }
)
_RECEIPT_ROLE_ORDER = ("STORE_NAME", "PURCHASE_DATE", "RECEIPT_TOTAL")
_ITEM_ROLE_ORDER = ("ITEM_DESCRIPTION", "QUANTITY", "UNIT_PRICE", "LINE_TOTAL")
_MONEY_ROLES = frozenset({"UNIT_PRICE", "LINE_TOTAL", "RECEIPT_TOTAL"})
_TEXT_ROLES = frozenset({"STORE_NAME", "ITEM_DESCRIPTION"})

_PROTOCOL_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_DIGEST_RE = re.compile(r"\A[0-9a-f]{64}\Z")
_FAILURE_CODE_RE = re.compile(r"\A[A-Z][A-Z0-9_]*\Z")
_MONEY_RE = re.compile(r"\A(0|[1-9][0-9]*)\.[0-9]{2}\Z")
_ORIGINAL_MONEY_RE = re.compile(
    r"\A(?:(?i:RM|MYR)[ ]*)?"
    r"(?P<integer>(?:0|[1-9][0-9]*)|(?:[1-9][0-9]{0,2}(?:,[0-9]{3})+))"
    r"\.(?P<fraction>[0-9]{2})\Z",
    re.ASCII,
)
_QUANTITY_RE = re.compile(r"\A(0|[1-9][0-9]*)(?:\.[0-9]{1,3})?\Z")
_DATE_RE = re.compile(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_PRIVATE_ID_MARKER_RE = re.compile(
    r"(?:\A|[._-])(?:participant|evaluation|ground[-_]?truth|annotation|held[-_]?out)"
    r"(?:\Z|[._-])",
    re.IGNORECASE | re.ASCII,
)
_REASON_URI_RE = re.compile(
    r"(?<![A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]*:(?=\S)",
    re.ASCII,
)
_REASON_WINDOWS_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:[A-Za-z]:[\\/]|\\\\[^\\/\s]+[\\/][^\\/\s]+|//[^/\s]+/[^/\s]+)",
    re.ASCII,
)
_REASON_UNIX_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9])/(?!/)(?=[^\s])(?:[^/\s]+)(?:/[^/\s]*)*",
    re.ASCII,
)
_REASON_LABELLED_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:path|file)\s*(?:=|:)\s*[^\s=:]*[\\/][^\s]+",
    re.IGNORECASE | re.ASCII,
)
_REASON_RELATIVE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:\.{1,2}[\\/](?=[^\s])|[A-Za-z0-9._-]+\\[A-Za-z0-9._-]+"
    r"(?:\\[A-Za-z0-9._-]+)*|[A-Za-z0-9._-]+/[A-Za-z0-9._-]+"
    r"\.[A-Za-z0-9._-]+)",
    re.ASCII,
)
_REASON_FORWARD_RELATIVE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9._-])"
    r"(?=[A-Za-z0-9._-]*[A-Za-z0-9])"
    r"[A-Za-z0-9._-]+"
    r"(?:/(?=[A-Za-z0-9._-]*[A-Za-z0-9])[A-Za-z0-9._-]+)+"
    r"(?![A-Za-z0-9._-])",
    re.ASCII,
)
_REASON_PROTECTED_MARKER_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:participant|reference|ref|evaluation|annotation|"
    r"ground(?:[ _-]+)truth|held(?:[ _-]+)out)"
    r"(?![A-Za-z0-9])",
    re.ASCII,
)
_REASON_ID_CHAR_RUN_RE = re.compile(r"[A-Za-z0-9._-]+", re.ASCII)
_REASON_WHITESPACE_CODEPOINTS = frozenset(
    (*range(0x0009, 0x000E), 0x0020, 0x0085, 0x00A0, 0x1680,
     *range(0x2000, 0x200B), 0x2028, 0x2029, 0x202F, 0x205F, 0x3000)
)
_REASON_INVISIBLE_CODEPOINTS = frozenset(
    (0x00AD, 0x034F, 0x061C, 0x180E,
     *range(0x200B, 0x2010), *range(0x202A, 0x202F),
     *range(0x2060, 0x2070), 0xFEFF)
)
_REASON_TEXT_DELIMITERS = frozenset(
    "()[]{}\"'“”‘’«»‹›,;:!?"
)
_REASON_STRUCTURED_PREFIX = frozenset(":=#._-")
_REASON_WRAPPER_OPEN_TO_CLOSE = {
    "(": ")",
    "[": "]",
    "{": "}",
    "“": "”",
    "‘": "’",
    "«": "»",
    "‹": "›",
}
_REASON_WRAPPER_CLOSERS = frozenset(_REASON_WRAPPER_OPEN_TO_CLOSE.values())
_REASON_SYMMETRIC_QUOTES = frozenset(("\"", "'"))


def _reject(code: str, path: str, detail: str) -> NoReturn:
    raise ConformanceViolation(code, path, detail)


def _is_nonblank(value: str) -> bool:
    return any(character not in "\t\n\r " for character in value)


def _ensure_unicode_scalar_string(value: str, path: str) -> None:
    """Reject unpaired UTF-16 surrogate escapes without normalizing strings."""

    index = 0
    while index < len(value):
        code_point = ord(value[index])
        if 0xD800 <= code_point <= 0xDBFF:
            if index + 1 >= len(value) or not (
                0xDC00 <= ord(value[index + 1]) <= 0xDFFF
            ):
                _reject("REJECT_INVALID_JSON", path, "unpaired high surrogate")
            index += 2
            continue
        if 0xDC00 <= code_point <= 0xDFFF:
            _reject("REJECT_INVALID_JSON", path, "unpaired low surrogate")
        index += 1


def _freeze_and_check_json(value: Any, path: str = "$") -> Any:
    if isinstance(value, str):
        _ensure_unicode_scalar_string(value, path)
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, member in value.items():
            if not isinstance(key, str):
                _reject("REJECT_INVALID_JSON", path, "object member name is not a string")
            _ensure_unicode_scalar_string(key, path)
            frozen[key] = _freeze_and_check_json(member, f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, list):
        return tuple(
            _freeze_and_check_json(member, f"{path}[{index}]")
            for index, member in enumerate(value)
        )
    return value


def decode_strict_json_object(raw_json: bytes) -> Mapping[str, object]:
    """Decode one strict UTF-8 JSON object into a deeply immutable mapping.

    This generic decoder exists so a test harness can strictly decode its
    fixture wrapper once and pass only the nested envelope object to
    :func:`validate_presentation_v1_object`.  It does not make fixture wrappers
    part of the production presentation contract.
    """

    if type(raw_json) is not bytes:
        _reject("REJECT_INVALID_JSON", "$", "input must be raw bytes")
    if raw_json.startswith(b"\xef\xbb\xbf"):
        _reject("REJECT_INVALID_JSON", "$", "UTF-8 BOM is forbidden")
    try:
        text = raw_json.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        _reject("REJECT_INVALID_JSON", "$", f"malformed UTF-8 at byte {error.start}")

    def reject_constant(token: str) -> NoReturn:
        _reject("REJECT_INVALID_JSON", "$", f"nonstandard numeric token {token!r}")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _reject(
                    "REJECT_DUPLICATE_JSON_KEY",
                    "$",
                    f"duplicate object member {key!r}",
                )
            result[key] = value
        return result

    def parse_integer(token: str) -> int | Decimal:
        # Normal JSON integers remain ordinary ``int`` values (the fixture
        # harness relies on that type).  If the interpreter's defensive digit
        # limit rejects an otherwise valid JSON integer, retain it as Decimal
        # so semantic validation, rather than a parser implementation detail,
        # decides whether the value is permitted.
        try:
            return int(token)
        except ValueError:
            return Decimal(token)

    try:
        decoded = json.loads(
            text,
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
            parse_float=Decimal,
            parse_int=parse_integer,
        )
    except ConformanceViolation:
        raise
    except (json.JSONDecodeError, UnicodeError, ValueError, RecursionError) as error:
        _reject("REJECT_INVALID_JSON", "$", f"malformed JSON: {error}")
    if not isinstance(decoded, Mapping):
        _reject("REJECT_INVALID_JSON", "$", "JSON root must be an object")
    frozen = _freeze_and_check_json(decoded)
    assert isinstance(frozen, Mapping)
    return frozen


def _object(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _reject("REJECT_INVALID_JSON", path, "expected object")
    if any(not isinstance(key, str) for key in value):
        _reject("REJECT_INVALID_JSON", path, "object member name is not a string")
    return value


def _members(
    value: object, path: str, expected: frozenset[str]
) -> Mapping[str, object]:
    result = _object(value, path)
    keys = set(result)
    missing = sorted(expected - keys)
    if missing:
        _reject("REJECT_MISSING_MEMBER", path, f"missing member {missing[0]!r}")
    unknown = sorted(keys - expected)
    if unknown:
        _reject("REJECT_UNKNOWN_MEMBER", path, f"unknown member {unknown[0]!r}")
    return result


def _string(value: object, path: str) -> str:
    if not isinstance(value, str):
        _reject("REJECT_INVALID_JSON", path, "expected string")
    _ensure_unicode_scalar_string(value, path)
    return value


def _nonblank_string(value: object, path: str, code: str = "REJECT_INVALID_JSON") -> str:
    result = _string(value, path)
    if not _is_nonblank(result):
        _reject(code, path, "expected nonblank string")
    return result


def _reason_detection_view(value: str) -> str:
    mapped: list[str] = []
    previous_was_space = False
    for character in value:
        codepoint = ord(character)
        if 0xFF01 <= codepoint <= 0xFF5E:
            character = chr(codepoint - 0xFEE0)
            codepoint = ord(character)
        if codepoint in _REASON_WHITESPACE_CODEPOINTS:
            if not previous_was_space:
                mapped.append(" ")
            previous_was_space = True
            continue
        previous_was_space = False
        if "A" <= character <= "Z":
            character = chr(ord(character) + 0x20)
        mapped.append(character)
    return "".join(mapped)


def _reason_has_existing_uri_or_path(value: str) -> bool:
    return any(
        pattern.search(value) is not None
        for pattern in (
            _REASON_URI_RE,
            _REASON_WINDOWS_PATH_RE,
            _REASON_UNIX_PATH_RE,
            _REASON_LABELLED_PATH_RE,
            _REASON_RELATIVE_PATH_RE,
            _REASON_FORWARD_RELATIVE_PATH_RE,
        )
    )


def _reason_has_mixed_script_structured_label(value: str) -> bool:
    boundaries = _REASON_STRUCTURED_PREFIX | frozenset((" ",))
    index = 0
    while index < len(value):
        while index < len(value) and value[index] in boundaries:
            index += 1
        start = index
        while index < len(value) and value[index] not in boundaries:
            index += 1
        token = value[start:index]
        following = index
        while following < len(value) and value[following] == " ":
            following += 1
        if (
            token
            and any("a" <= character <= "z" for character in token)
            and any(ord(character) > 0x7F for character in token)
            and following < len(value)
            and value[following] in _REASON_STRUCTURED_PREFIX
        ):
            return True
    return False


def _reason_has_incomplete_wrappers(value: str) -> bool:
    stack: list[str] = []
    for character in value:
        if character in _REASON_SYMMETRIC_QUOTES:
            if stack and stack[-1] == character:
                stack.pop()
            else:
                stack.append(character)
        elif character in _REASON_WRAPPER_OPEN_TO_CLOSE:
            stack.append(_REASON_WRAPPER_OPEN_TO_CLOSE[character])
        elif character in _REASON_WRAPPER_CLOSERS:
            if not stack or stack[-1] != character:
                return True
            stack.pop()
    return bool(stack)


def _reason_complete_atoms(value: str) -> tuple[str, ...]:
    atoms: list[str] = []
    start: int | None = None
    for index, character in enumerate(value):
        if character == " " or character in _REASON_TEXT_DELIMITERS:
            if start is not None:
                atoms.append(value[start:index])
                start = None
        elif start is None:
            start = index
    if start is not None:
        atoms.append(value[start:])
    return tuple(atoms)


def _reason_has_candidate02_protected_identifier(value: str) -> bool:
    for marker in _REASON_PROTECTED_MARKER_RE.finditer(value):
        post_marker_span = value[marker.end():]
        immediate = post_marker_span.lstrip(" ")
        if immediate:
            if immediate[0] in _REASON_STRUCTURED_PREFIX:
                return True
            if "0" <= immediate[0] <= "9":
                return True
            for qualifier in ("id", "case"):
                if immediate.startswith(qualifier) and (
                    len(immediate) == len(qualifier)
                    or not (
                        "a" <= immediate[len(qualifier)] <= "z"
                        or "0" <= immediate[len(qualifier)] <= "9"
                    )
                ):
                    return True

        atoms = _reason_complete_atoms(post_marker_span)
        for atom in atoms:
            if any(ord(character) > 0x7F for character in atom):
                return True
            if any(
                any("0" <= character <= "9" for character in match.group())
                for match in _REASON_ID_CHAR_RUN_RE.finditer(atom)
            ):
                return True
            if any(
                0x21 <= ord(character) <= 0x7E
                and not (
                    "a" <= character <= "z"
                    or "0" <= character <= "9"
                    or character in "._-"
                    or character in _REASON_TEXT_DELIMITERS
                )
                for character in atom
            ):
                return True

        if _reason_has_incomplete_wrappers(post_marker_span):
            return True
        if not atoms and any(
            character in _REASON_WRAPPER_OPEN_TO_CLOSE
            or character in _REASON_WRAPPER_CLOSERS
            or character in _REASON_SYMMETRIC_QUOTES
            for character in post_marker_span
        ):
            return True
    return False


def _reason_has_unsafe_provenance(value: str) -> bool:
    if _reason_has_existing_uri_or_path(value):
        return True
    if any(ord(character) in _REASON_INVISIBLE_CODEPOINTS for character in value):
        return True
    detection_view = _reason_detection_view(value)
    return (
        _reason_has_existing_uri_or_path(detection_view)
        or _reason_has_mixed_script_structured_label(detection_view)
        or _reason_has_candidate02_protected_identifier(detection_view)
    )


def _privacy_safe_reason(value: object, path: str, state_code: str) -> str:
    result = _nonblank_string(value, path, state_code)
    if _reason_has_unsafe_provenance(result):
        _reject(
            "REJECT_UNSAFE_PROVENANCE",
            path,
            "reason contains a prohibited URI, path, or protected data identifier",
        )
    return result


def _boolean(value: object, path: str) -> bool:
    if type(value) is not bool:
        _reject("REJECT_INVALID_JSON", path, "expected boolean")
    return value


def _array(value: object, path: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        _reject("REJECT_INVALID_JSON", path, "expected array")
    return value


def _protocol_id(value: object, path: str, code: str = "REJECT_INVALID_ID") -> str:
    result = _string(value, path)
    if _PROTOCOL_ID_RE.fullmatch(result) is None:
        _reject(code, path, "invalid opaque protocol identifier")
    if _PRIVATE_ID_MARKER_RE.search(result) is not None:
        _reject(code, path, "research/participant identity is forbidden")
    return result


def _enum(value: object, path: str, allowed: frozenset[str]) -> str:
    result = _string(value, path)
    if result not in allowed:
        _reject("REJECT_UNKNOWN_ENUM", path, f"unknown enum value {result!r}")
    return result


def _parse_source(value: object, path: str, consumer_mode: str) -> PresentationSource:
    source = _members(value, path, _SOURCE_MEMBERS)
    source_type = _enum(
        source["type"], f"{path}.type", frozenset({"LOCAL_IMAGE", "SYNTHETIC_FIXTURE"})
    )
    if source_type == "SYNTHETIC_FIXTURE" and consumer_mode != "FIXTURE":
        _reject(
            "REJECT_SOURCE_MODE_MISMATCH",
            f"{path}.type",
            "synthetic fixture source is forbidden outside FIXTURE mode",
        )
    provenance_raw = _members(
        source["provenance"], f"{path}.provenance", _PROVENANCE_MEMBERS
    )
    source_system = _protocol_id(
        provenance_raw["sourceSystem"], f"{path}.provenance.sourceSystem"
    )
    source_reference = _protocol_id(
        provenance_raw["sourceReference"],
        f"{path}.provenance.sourceReference",
        "REJECT_UNSAFE_PROVENANCE",
    )
    if _PRIVATE_ID_MARKER_RE.search(source_reference) is not None:
        _reject(
            "REJECT_UNSAFE_PROVENANCE",
            f"{path}.provenance.sourceReference",
            "source reference contains a prohibited participant/evaluation marker",
        )
    digest_raw = provenance_raw["contentSha256"]
    if digest_raw is None:
        digest = None
    else:
        digest = _string(digest_raw, f"{path}.provenance.contentSha256")
        if _DIGEST_RE.fullmatch(digest) is None:
            _reject(
                "REJECT_INVALID_DIGEST",
                f"{path}.provenance.contentSha256",
                "digest must be 64 lowercase hexadecimal characters",
            )
    return PresentationSource(
        type=source_type,
        provenance=PresentationProvenance(source_system, source_reference, digest),
    )


def _parse_failure(value: object, path: str) -> PresentationFailure:
    failure = _members(value, path, _FAILURE_MEMBERS)
    stage = _enum(failure["stage"], f"{path}.stage", _FAILURE_STAGES)
    code = _string(failure["code"], f"{path}.code")
    if _FAILURE_CODE_RE.fullmatch(code) is None:
        _reject("REJECT_UNKNOWN_ENUM", f"{path}.code", "invalid failure code token")
    retryable = _boolean(failure["retryable"], f"{path}.retryable")
    return PresentationFailure(stage, code, retryable)


def _parse_outcome(value: object, path: str) -> PresentationOutcome:
    outcome = _members(value, path, _OUTCOME_MEMBERS)
    status = _enum(outcome["status"], f"{path}.status", _OUTCOME_STATUSES)
    failure_raw = outcome["failure"]
    failure = None if failure_raw is None else _parse_failure(failure_raw, f"{path}.failure")
    return PresentationOutcome(status, failure)


def _parse_evidence(value: object, path: str) -> PresentationSourceEvidence:
    evidence = _members(value, path, _EVIDENCE_MEMBERS)
    status = _enum(
        evidence["sourceProcessingStatus"],
        f"{path}.sourceProcessingStatus",
        _EVIDENCE_STATUSES,
    )
    token_values = _array(evidence["tokenIds"], f"{path}.tokenIds")
    token_ids: list[str] = []
    seen: set[str] = set()
    for index, raw_token_id in enumerate(token_values):
        token_id = _protocol_id(raw_token_id, f"{path}.tokenIds[{index}]")
        if token_id in seen:
            _reject(
                "REJECT_DUPLICATE_TOKEN_ID",
                f"{path}.tokenIds[{index}]",
                "duplicate token registry identity",
            )
        seen.add(token_id)
        token_ids.append(token_id)
    return PresentationSourceEvidence(status, tuple(token_ids))


def _parse_gate(value: object, path: str) -> PresentationSourceGate:
    gate = _members(value, path, _GATE_MEMBERS)
    gate_result_id = _protocol_id(gate["gateResultId"], f"{path}.gateResultId")
    decision = _enum(gate["decision"], f"{path}.decision", _GATE_DECISIONS)
    reason_values = _array(gate["reasons"], f"{path}.reasons")
    reasons: list[str] = []
    seen: set[str] = set()
    for index, raw_reason in enumerate(reason_values):
        reason = _nonblank_string(
            raw_reason, f"{path}.reasons[{index}]", "REJECT_GATE_STATE"
        )
        if reason in seen:
            _reject(
                "REJECT_GATE_STATE",
                f"{path}.reasons[{index}]",
                "duplicate gate reason",
            )
        seen.add(reason)
        reasons.append(reason)
    if decision == "INSUFFICIENT" and not reasons:
        _reject(
            "REJECT_GATE_STATE",
            f"{path}.reasons",
            "an insufficient gate requires at least one recorded reason",
        )
    for index, reason in enumerate(reasons):
        _privacy_safe_reason(
            reason, f"{path}.reasons[{index}]", "REJECT_GATE_STATE"
        )
    return PresentationSourceGate(gate_result_id, decision, tuple(reasons))


def _parse_extraction(value: object, path: str) -> PresentationAutomaticExtraction:
    extraction = _members(value, path, _EXTRACTION_MEMBERS)
    stage = _string(extraction["stage"], f"{path}.stage")
    if stage != "PRE_REVIEW_AUTOMATIC":
        _reject("REJECT_UNKNOWN_ENUM", f"{path}.stage", "unknown extraction stage")
    extraction_status = _enum(
        extraction["extractionStatus"],
        f"{path}.extractionStatus",
        _EXTRACTION_STATUSES,
    )
    producer_path = f"{path}.producer"
    producer_object = _object(extraction["producer"], producer_path)
    if "producerVersion" not in producer_object:
        _reject(
            "REJECT_PRODUCER_METADATA",
            producer_path,
            "producerVersion is required",
        )
    producer_raw = _members(producer_object, producer_path, _PRODUCER_MEMBERS)
    producer_id = _protocol_id(
        producer_raw["producerId"], f"{path}.producer.producerId"
    )
    producer_version = _nonblank_string(
        producer_raw["producerVersion"],
        f"{path}.producer.producerVersion",
        "REJECT_PRODUCER_METADATA",
    )
    return PresentationAutomaticExtraction(
        stage,
        extraction_status,
        PresentationProducer(producer_id, producer_version),
    )


def _parse_confidence(value: object, path: str) -> Decimal | None:
    if value is None:
        return None
    if type(value) is bool or not isinstance(value, (int, float, Decimal)):
        _reject("REJECT_INVALID_CONFIDENCE", path, "confidence must be a JSON number")
    try:
        if isinstance(value, Decimal):
            exact = value
        elif isinstance(value, int):
            exact = Decimal(value)
        else:
            exact = Decimal.from_float(value)
        binary64 = float(exact)
    except (InvalidOperation, OverflowError, ValueError):
        _reject("REJECT_INVALID_CONFIDENCE", path, "confidence is not finite binary64")
    if not exact.is_finite() or not math.isfinite(binary64):
        _reject("REJECT_INVALID_CONFIDENCE", path, "confidence is not finite binary64")
    return exact


def _validate_money(original: str, presentation: str, path: str) -> None:
    if _MONEY_RE.fullmatch(presentation) is None:
        _reject(
            "REJECT_INVALID_MONEY",
            f"{path}.presentationValue",
            "money must be a non-negative canonical decimal with scale two",
        )
    if original.startswith("$"):
        _reject(
            "REJECT_CURRENCY_MISMATCH",
            f"{path}.originalAutomaticValue",
            "dollar-prefixed source value is not established as MYR",
        )
    match = _ORIGINAL_MONEY_RE.fullmatch(original)
    if match is None:
        _reject(
            "REJECT_VALUE_RELATIONSHIP",
            f"{path}.originalAutomaticValue",
            "original money is outside the approved lexical grammar",
        )
    normalized = (
        match.group("integer").replace(",", "") + "." + match.group("fraction")
    )
    if normalized != presentation:
        _reject(
            "REJECT_VALUE_RELATIONSHIP",
            path,
            "money presentation differs beyond approved lexical normalization",
        )


def _validate_date(original: str, presentation: str, path: str) -> None:
    if original != presentation:
        _reject(
            "REJECT_VALUE_RELATIONSHIP",
            path,
            "date original and presentation values must be identical",
        )
    if _DATE_RE.fullmatch(presentation) is None:
        _reject("REJECT_INVALID_DATE", f"{path}.presentationValue", "invalid ISO date")
    try:
        date.fromisoformat(presentation)
    except ValueError:
        _reject(
            "REJECT_INVALID_DATE",
            f"{path}.presentationValue",
            "date is not Gregorian-valid",
        )


def _validate_quantity(original: str, presentation: str, path: str) -> None:
    if original != presentation:
        _reject(
            "REJECT_VALUE_RELATIONSHIP",
            path,
            "quantity original and presentation values must be identical",
        )
    if _QUANTITY_RE.fullmatch(presentation) is None:
        _reject(
            "REJECT_INVALID_QUANTITY",
            f"{path}.presentationValue",
            "quantity is outside canonical scale-zero-to-three grammar",
        )
    try:
        numeric = Decimal(presentation)
    except InvalidOperation:
        _reject("REJECT_INVALID_QUANTITY", f"{path}.presentationValue", "invalid quantity")
    if numeric <= 0:
        _reject(
            "REJECT_INVALID_QUANTITY",
            f"{path}.presentationValue",
            "quantity must be greater than zero",
        )


def _parse_field(
    value: object,
    path: str,
    known_tokens: frozenset[str],
    field_ids: set[str],
) -> PresentationField:
    field = _members(value, path, _FIELD_MEMBERS)
    field_id = _protocol_id(field["fieldId"], f"{path}.fieldId")
    if field_id in field_ids:
        _reject("REJECT_DUPLICATE_FIELD_ID", f"{path}.fieldId", "duplicate field identity")
    field_ids.add(field_id)

    role = _string(field["role"], f"{path}.role")
    if role not in _FIELD_ROLES:
        _reject("REJECT_UNKNOWN_ROLE", f"{path}.role", f"unknown role {role!r}")
    status = _enum(field["status"], f"{path}.status", _FIELD_STATUSES)

    original_raw = field["originalAutomaticValue"]
    presentation_raw = field["presentationValue"]
    reason_raw = field["absenceReason"]
    confidence = _parse_confidence(field["nativeConfidence"], f"{path}.nativeConfidence")

    token_values = _array(field["sourceTokenIds"], f"{path}.sourceTokenIds")
    token_ids: list[str] = []
    seen_tokens: set[str] = set()
    for index, raw_token_id in enumerate(token_values):
        token_id = _protocol_id(raw_token_id, f"{path}.sourceTokenIds[{index}]")
        if token_id in seen_tokens:
            _reject(
                "REJECT_DUPLICATE_TOKEN_REFERENCE",
                f"{path}.sourceTokenIds[{index}]",
                "duplicate token reference",
            )
        if token_id not in known_tokens:
            _reject(
                "REJECT_UNKNOWN_TOKEN_REFERENCE",
                f"{path}.sourceTokenIds[{index}]",
                "token reference is absent from source evidence",
            )
        seen_tokens.add(token_id)
        token_ids.append(token_id)

    if status == "EXTRACTED":
        if original_raw is None or presentation_raw is None:
            _reject(
                "REJECT_CONTRADICTORY_FIELD_STATE",
                path,
                "extracted field requires both values",
            )
        original = _nonblank_string(
            original_raw, f"{path}.originalAutomaticValue", "REJECT_CONTRADICTORY_FIELD_STATE"
        )
        presentation = _nonblank_string(
            presentation_raw, f"{path}.presentationValue", "REJECT_CONTRADICTORY_FIELD_STATE"
        )
        if reason_raw is not None:
            _reject(
                "REJECT_CONTRADICTORY_FIELD_STATE",
                f"{path}.absenceReason",
                "extracted field must not carry an absence reason",
            )
        reason = None
        if not token_ids:
            _reject(
                "REJECT_TOKEN_INTEGRITY",
                f"{path}.sourceTokenIds",
                "extracted field requires at least one token reference",
            )
        if role in _TEXT_ROLES:
            if original != presentation:
                _reject(
                    "REJECT_VALUE_RELATIONSHIP",
                    path,
                    "text original and presentation values must be identical",
                )
        elif role == "PURCHASE_DATE":
            _validate_date(original, presentation, path)
        elif role == "QUANTITY":
            _validate_quantity(original, presentation, path)
        elif role in _MONEY_ROLES:
            _validate_money(original, presentation, path)
    else:
        if original_raw is not None or presentation_raw is not None:
            _reject(
                "REJECT_CONTRADICTORY_FIELD_STATE",
                path,
                "missing or unresolved field values must be null",
            )
        if confidence is not None:
            _reject(
                "REJECT_CONTRADICTORY_FIELD_STATE",
                f"{path}.nativeConfidence",
                "missing or unresolved field confidence must be null",
            )
        reason = _privacy_safe_reason(
            reason_raw, f"{path}.absenceReason", "REJECT_CONTRADICTORY_FIELD_STATE"
        )
        original = None
        presentation = None

    return PresentationField(
        field_id,
        role,
        status,
        original,
        presentation,
        reason,
        tuple(token_ids),
        confidence,
    )


def _parse_field_group(
    value: object,
    path: str,
    expected_roles: tuple[str, ...],
    known_tokens: frozenset[str],
    field_ids: set[str],
) -> tuple[PresentationField, ...]:
    values = _array(value, path)
    fields = tuple(
        _parse_field(raw_field, f"{path}[{index}]", known_tokens, field_ids)
        for index, raw_field in enumerate(values)
    )
    roles = tuple(field.role for field in fields)
    if len(roles) != len(expected_roles) or set(roles) != set(expected_roles):
        _reject("REJECT_ROLE_SET", path, "field role set is incomplete or duplicated")
    if roles != expected_roles:
        _reject("REJECT_ROLE_ORDER", path, "field roles are not in normative order")
    return fields


def _parse_receipt(
    value: object, path: str, known_tokens: frozenset[str]
) -> PresentationReceipt:
    receipt_object = _object(value, path)
    if "currencyCode" not in receipt_object:
        _reject(
            "REJECT_CURRENCY_METADATA",
            path,
            "available receipt requires currencyCode",
        )
    receipt = _members(receipt_object, path, _RECEIPT_MEMBERS)
    receipt_id = _protocol_id(receipt["receiptId"], f"{path}.receiptId")
    currency_code = _string(receipt["currencyCode"], f"{path}.currencyCode")
    if currency_code != "MYR":
        _reject(
            "REJECT_CURRENCY_METADATA",
            f"{path}.currencyCode",
            "V1 available receipts require exact currency code MYR",
        )

    field_ids: set[str] = set()
    receipt_fields = _parse_field_group(
        receipt["receiptFields"],
        f"{path}.receiptFields",
        _RECEIPT_ROLE_ORDER,
        known_tokens,
        field_ids,
    )

    row_values = _array(receipt["itemRows"], f"{path}.itemRows")
    rows: list[PresentationItemRow] = []
    row_ids: set[str] = set()
    for index, raw_row in enumerate(row_values):
        row_path = f"{path}.itemRows[{index}]"
        row = _members(raw_row, row_path, _ROW_MEMBERS)
        row_id = _protocol_id(row["rowId"], f"{row_path}.rowId")
        if row_id in row_ids:
            _reject("REJECT_DUPLICATE_ROW_ID", f"{row_path}.rowId", "duplicate row identity")
        row_ids.add(row_id)
        fields = _parse_field_group(
            row["fields"],
            f"{row_path}.fields",
            _ITEM_ROLE_ORDER,
            known_tokens,
            field_ids,
        )
        if not any(field.status == "EXTRACTED" for field in fields):
            _reject(
                "REJECT_TOKEN_INTEGRITY",
                f"{row_path}.fields",
                "item row requires at least one OCR-backed extracted field",
            )
        rows.append(PresentationItemRow(row_id, fields))

    return PresentationReceipt(receipt_id, currency_code, receipt_fields, tuple(rows))


def _validate_outcome_matrix(
    outcome: PresentationOutcome,
    evidence: PresentationSourceEvidence | None,
    gate: PresentationSourceGate | None,
    extraction: PresentationAutomaticExtraction | None,
    receipt: PresentationReceipt | None,
) -> None:
    status = outcome.status
    failure = outcome.failure
    if status == "RESULT_AVAILABLE":
        if failure is not None:
            _reject(
                "REJECT_OUTCOME_STATE_MISMATCH",
                "$.outcome.failure",
                "available result must not carry a technical failure",
            )
        if evidence is None:
            _reject(
                "REJECT_OUTCOME_STATE_MISMATCH",
                "$.sourceEvidence",
                "available result requires genuine source evidence",
            )
        if gate is None or gate.decision != "SUFFICIENT":
            _reject(
                "REJECT_GATE_OUTCOME_MISMATCH",
                "$.sourceGate",
                "available result requires a recorded sufficient gate",
            )
        if extraction is None or receipt is None:
            _reject(
                "REJECT_OUTCOME_STATE_MISMATCH",
                "$.automaticExtraction" if extraction is None else "$.receipt",
                "available result requires extraction metadata and receipt",
            )
        return

    if status == "SOURCE_EVIDENCE_INSUFFICIENT":
        if failure is not None or extraction is not None or receipt is not None:
            _reject(
                "REJECT_OUTCOME_STATE_MISMATCH",
                "$.outcome",
                "insufficient-evidence result must have null failure, extraction, and receipt",
            )
        if evidence is None:
            _reject(
                "REJECT_OUTCOME_STATE_MISMATCH",
                "$.sourceEvidence",
                "insufficient-evidence result requires genuine source evidence",
            )
        if gate is None or gate.decision != "INSUFFICIENT":
            _reject(
                "REJECT_GATE_OUTCOME_MISMATCH",
                "$.sourceGate",
                "insufficient-evidence result requires a recorded insufficient gate",
            )
        return

    if status == "PROCESSING_UNAVAILABLE":
        if failure is None:
            _reject(
                "REJECT_OUTCOME_STATE_MISMATCH",
                "$.outcome.failure",
                "unavailable outcome requires a failure diagnostic",
            )
        if failure.stage != "AVAILABILITY":
            _reject(
                "REJECT_OUTCOME_STAGE_MISMATCH",
                "$.outcome.failure.stage",
                "unavailable outcome requires AVAILABILITY stage",
            )
        if any(member is not None for member in (evidence, gate, extraction, receipt)):
            _reject(
                "REJECT_OUTCOME_STATE_MISMATCH",
                "$",
                "unavailable outcome requires null evidence, gate, extraction, and receipt",
            )
        return

    # PROCESSING_FAILED is the only remaining closed outcome.
    if failure is None:
        _reject(
            "REJECT_OUTCOME_STATE_MISMATCH",
            "$.outcome.failure",
            "technical failure requires a failure diagnostic",
        )
    if failure.stage == "AVAILABILITY":
        _reject(
            "REJECT_OUTCOME_STAGE_MISMATCH",
            "$.outcome.failure.stage",
            "PROCESSING_FAILED cannot use AVAILABILITY stage",
        )
    if extraction is not None or receipt is not None:
        _reject(
            "REJECT_OUTCOME_STATE_MISMATCH",
            "$",
            "technical failure requires null extraction and receipt",
        )

    if failure.stage == "OCR":
        if gate is not None:
            _reject(
                "REJECT_GATE_OUTCOME_MISMATCH",
                "$.sourceGate",
                "OCR-stage failure cannot carry a gate",
            )
        if evidence is not None and evidence.source_processing_status != "OCR_FAILED":
            _reject(
                "REJECT_EVIDENCE_STAGE_MISMATCH",
                "$.sourceEvidence.sourceProcessingStatus",
                "OCR-stage failure permits null or OCR_FAILED evidence only",
            )
        return

    if evidence is None or evidence.source_processing_status not in {
        "OCR_COMPLETED",
        "OCR_PARTIAL",
    }:
        _reject(
            "REJECT_EVIDENCE_STAGE_MISMATCH",
            "$.sourceEvidence",
            "downstream technical failure requires completed or partial OCR evidence",
        )
    if failure.stage == "SOURCE_GATE":
        if gate is not None:
            _reject(
                "REJECT_GATE_OUTCOME_MISMATCH",
                "$.sourceGate",
                "source-gate failure means no durable gate result exists",
            )
        return
    if gate is None or gate.decision != "SUFFICIENT":
        _reject(
            "REJECT_GATE_OUTCOME_MISMATCH",
            "$.sourceGate",
            "extraction/adapter failure requires a recorded sufficient gate",
        )


def validate_presentation_v1_object(
    envelope: Mapping[str, object],
    *,
    expected_request_id: str,
    expected_image_id: str,
    consumer_mode: str,
) -> ReceiptPresentationV1:
    """Validate an already strictly decoded *envelope* object.

    This entry point is intended for a test wrapper that has used
    :func:`decode_strict_json_object`, and for a handcrafted in-memory projector
    boundary.  It never accepts or unwraps fixture metadata.
    """

    if consumer_mode not in {"FIXTURE", "LIVE"}:
        _reject("REJECT_SOURCE_MODE_MISMATCH", "$context.mode", "unknown consumer mode")
    expected_request = _protocol_id(expected_request_id, "$context.expectedRequestId")
    expected_image = _protocol_id(expected_image_id, "$context.expectedImageId")

    root_object = _object(envelope, "$")
    # Version identity is checked before payload mapping, as required by V1.
    for member in ("schemaName", "schemaVersion", "sourceContractVersion"):
        if member not in root_object:
            _reject("REJECT_MISSING_MEMBER", "$", f"missing member {member!r}")
    schema_name = _string(root_object["schemaName"], "$.schemaName")
    schema_version = _string(root_object["schemaVersion"], "$.schemaVersion")
    source_contract_version = _string(
        root_object["sourceContractVersion"], "$.sourceContractVersion"
    )
    if schema_name != "receipt-presentation" or schema_version != "1":
        _reject(
            "REJECT_UNSUPPORTED_SCHEMA_VERSION",
            "$.schemaVersion",
            "unsupported receipt-presentation schema identity/version",
        )
    if source_contract_version != "0":
        _reject(
            "REJECT_UNSUPPORTED_CONTRACT_VERSION",
            "$.sourceContractVersion",
            "unsupported source contract version",
        )
    root = _members(root_object, "$", _TOP_MEMBERS)

    request_id = _protocol_id(root["requestId"], "$.requestId")
    image_id = _protocol_id(root["imageId"], "$.imageId")
    if request_id != expected_request:
        _reject(
            "REJECT_REQUEST_ID_MISMATCH",
            "$.requestId",
            "envelope request identity does not match caller context",
        )
    if image_id != expected_image:
        _reject(
            "REJECT_IMAGE_ID_MISMATCH",
            "$.imageId",
            "envelope image identity does not match caller context",
        )

    source = _parse_source(root["source"], "$.source", consumer_mode)
    outcome = _parse_outcome(root["outcome"], "$.outcome")
    evidence_raw = root["sourceEvidence"]
    evidence = (
        None if evidence_raw is None else _parse_evidence(evidence_raw, "$.sourceEvidence")
    )
    gate_raw = root["sourceGate"]
    gate = None if gate_raw is None else _parse_gate(gate_raw, "$.sourceGate")
    extraction_raw = root["automaticExtraction"]
    extraction = (
        None
        if extraction_raw is None
        else _parse_extraction(extraction_raw, "$.automaticExtraction")
    )
    known_tokens = frozenset(evidence.token_ids) if evidence is not None else frozenset()
    receipt_raw = root["receipt"]
    receipt = (
        None
        if receipt_raw is None
        else _parse_receipt(receipt_raw, "$.receipt", known_tokens)
    )

    _validate_outcome_matrix(outcome, evidence, gate, extraction, receipt)
    return ReceiptPresentationV1(
        schema_name,
        schema_version,
        source_contract_version,
        request_id,
        image_id,
        source,
        outcome,
        evidence,
        gate,
        extraction,
        receipt,
    )


def decode_and_validate_presentation_v1(
    raw_json: bytes,
    *,
    expected_request_id: str,
    expected_image_id: str,
    consumer_mode: str,
) -> ReceiptPresentationV1:
    """Strictly decode and validate one receipt-presentation V1 envelope."""

    envelope = decode_strict_json_object(raw_json)
    return validate_presentation_v1_object(
        envelope,
        expected_request_id=expected_request_id,
        expected_image_id=expected_image_id,
        consumer_mode=consumer_mode,
    )


__all__ = [
    "ConformanceViolation",
    "PresentationAutomaticExtraction",
    "PresentationFailure",
    "PresentationField",
    "PresentationItemRow",
    "PresentationOutcome",
    "PresentationProducer",
    "PresentationProvenance",
    "PresentationReceipt",
    "PresentationSource",
    "PresentationSourceEvidence",
    "PresentationSourceGate",
    "ReceiptPresentationV1",
    "decode_and_validate_presentation_v1",
    "decode_strict_json_object",
    "validate_presentation_v1_object",
]
