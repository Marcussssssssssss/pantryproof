"""Deterministic generic-rule B3 baseline for Contract Version 0.

B3 is a downstream transformation of the frozen B2 automatic prediction.  It
normalizes generic representations, records exact-source rule evidence, and
computes Decimal arithmetic diagnostics.  It never runs B2 or the source gate,
mutates OCR evidence, uses retailer knowledge, or abstains from evaluation.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from enum import Enum
from typing import TypeVar

from pipeline.contracts import (
    FieldStatus,
    OutputStage,
    PolicyState,
    PreResolutionDisposition,
    ReceiptItemRow,
    ReceiptOutput,
    StructuredField,
)
from pipeline.layout_b2 import B2ExtractionResult


_T = TypeVar("_T")


EXTRACTOR_VERSION = "B3-generic-rules-v0"
RULESET_ID = EXTRACTOR_VERSION
REQUIRED_B2_EXTRACTOR_VERSION = "B2-layout-graph-v0"

CURRENCY_QUANTUM = Decimal("0.01")
CURRENCY_TOLERANCE = Decimal("0.01")
ROUNDING_MODE = ROUND_HALF_UP
WEIGHT_UNITS = ("kg", "g", "lb", "lbs", "oz")

# This is a mapping, not a deletion list.  NFKC is applied before these pairs.
PUNCTUATION_MAP: tuple[tuple[str, str], ...] = (
    ("\u2018", "'"),
    ("\u2019", "'"),
    ("\u201a", "'"),
    ("\u201b", "'"),
    ("\u201c", '"'),
    ("\u201d", '"'),
    ("\u201e", '"'),
    ("\u201f", '"'),
    ("\u2010", "-"),
    ("\u2011", "-"),
    ("\u2012", "-"),
    ("\u2013", "-"),
    ("\u2014", "-"),
    ("\u2212", "-"),
    ("\u2026", "..."),
)
_PUNCTUATION_TRANSLATION = str.maketrans(dict(PUNCTUATION_MAP))

_YEAR_FIRST_DATE_RE = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})"
)
_NUMERIC_DATE_RE = re.compile(
    r"(?P<first>\d{1,2})(?P<separator>[/-])(?P<second>\d{1,2})"
    r"(?P=separator)(?P<year>\d{4})"
)
_MONTH_NAMES = (
    r"JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|"
    r"JUN(?:E)?|JUL(?:Y)?|AUG(?:UST)?|SEP(?:TEMBER)?|OCT(?:OBER)?|"
    r"NOV(?:EMBER)?|DEC(?:EMBER)?"
)
_DAY_MONTH_NAME_RE = re.compile(
    rf"(?P<day>\d{{1,2}})\s+(?P<month>{_MONTH_NAMES})\s+"
    r"(?P<year>\d{4})",
    re.IGNORECASE,
)
_MONTH_NAME_DAY_RE = re.compile(
    rf"(?P<month>{_MONTH_NAMES})\s+(?P<day>\d{{1,2}}),?\s+"
    r"(?P<year>\d{4})",
    re.IGNORECASE,
)
_MONTH_NUMBERS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

_QUANTITY_NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_QUANTITY_RE = re.compile(rf"(?P<number>{_QUANTITY_NUMBER})")
_MONEY_NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{1,2}"
_MONEY_PATTERN = rf"(?:(?P<prefix>RM|MYR|\$)\s*)?(?P<number>{_MONEY_NUMBER})"
_MONEY_RE = re.compile(_MONEY_PATTERN, re.IGNORECASE)
_MONEY_SCAN_RE = re.compile(
    rf"(?<![\w.,+-]){_MONEY_PATTERN}(?![\w.,])", re.IGNORECASE
)
_CURRENCY_MARKER_TOKEN_RE = re.compile(r"(?:RM|MYR|\$)", re.IGNORECASE)
_UNSUPPORTED_CURRENCY_MARKER_TOKEN_RE = re.compile(
    r"(?:[A-Z]{3}|[€£¥])", re.IGNORECASE
)

_ADJUSTMENT_RE = re.compile(
    rf"^\s*(?P<label>SERVICE\s+CHARGE|SERVICE\s+TAX|DISCOUNT|VOUCHER|"
    rf"COUPON|REBATE|SURCHARGE|SUBTOTAL|ROUNDING|TAX|GST|SST)\b"
    rf"\s*[:=]?\s*(?P<sign>[+-])?\s*(?P<amount>{_MONEY_PATTERN})\s*$",
    re.IGNORECASE,
)
_PROMOTION_RE = re.compile(
    r"\b(?:PROMO(?:TION)?|SPECIAL\s+OFFER|OFFER|"
    r"BUY\s+\d+\s+GET\s+\d+)\b",
    re.IGNORECASE,
)
_WEIGHT_QUANTITY_RE = re.compile(
    rf"(?<![\w.])(?P<quantity>{_QUANTITY_NUMBER})\s*"
    r"(?P<unit>kg|g|lbs?|oz)\b",
    re.IGNORECASE,
)
_WEIGHT_DENOMINATOR_RE = re.compile(
    rf"{_MONEY_PATTERN}\s*(?:/\s*|PER\s+)(?P<unit>kg|g|lbs?|oz)\b",
    re.IGNORECASE,
)


class B3ParseState(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    AMBIGUOUS = "AMBIGUOUS"


class B3RuleOutcome(str, Enum):
    UNCHANGED = "UNCHANGED"
    REPRESENTATION_CHANGED = "REPRESENTATION_CHANGED"
    EVIDENCE_RECORDED = "EVIDENCE_RECORDED"
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
    CANDIDATE_PROPOSED = "CANDIDATE_PROPOSED"
    CANDIDATE_APPLIED = "CANDIDATE_APPLIED"
    CANDIDATE_REJECTED = "CANDIDATE_REJECTED"


class ArithmeticPhase(str, Enum):
    PRE_CORRECTION = "PRE_CORRECTION"
    FINAL = "FINAL"


class ArithmeticScope(str, Enum):
    ITEM = "ITEM"
    OBSERVED_RECEIPT_ROWS = "OBSERVED_RECEIPT_ROWS"


class ArithmeticOutcome(str, Enum):
    RAW_EXACT_MATCH = "RAW_EXACT_MATCH"
    MATCH_AFTER_CURRENCY_ROUNDING = "MATCH_AFTER_CURRENCY_ROUNDING"
    WITHIN_INCLUSIVE_TOLERANCE = "WITHIN_INCLUSIVE_TOLERANCE"
    MISMATCH_BEYOND_TOLERANCE = "MISMATCH_BEYOND_TOLERANCE"
    INCOMPLETE_OPERANDS = "INCOMPLETE_OPERANDS"
    AMBIGUOUS_OR_CONFLICTING_UNITS = "AMBIGUOUS_OR_CONFLICTING_UNITS"
    CONFLICTING_CURRENCY_MARKERS = "CONFLICTING_CURRENCY_MARKERS"
    EXPLICIT_PROMOTION_OR_ADJUSTMENT_EXCEPTION = (
        "EXPLICIT_PROMOTION_OR_ADJUSTMENT_EXCEPTION"
    )


class AdjustmentKind(str, Enum):
    DISCOUNT = "DISCOUNT"
    VOUCHER = "VOUCHER"
    COUPON = "COUPON"
    REBATE = "REBATE"
    TAX = "TAX"
    GST = "GST"
    SST = "SST"
    SERVICE_TAX = "SERVICE_TAX"
    SERVICE_CHARGE = "SERVICE_CHARGE"
    SURCHARGE = "SURCHARGE"
    SUBTOTAL = "SUBTOTAL"
    ROUNDING = "ROUNDING"


class AdjustmentDirection(str, Enum):
    ADD = "ADD"
    SUBTRACT = "SUBTRACT"
    REFERENCE_ONLY = "REFERENCE_ONLY"
    UNKNOWN = "UNKNOWN"


class DiagnosticCode(str, Enum):
    INVALID_DATE = "INVALID_DATE"
    AMBIGUOUS_DATE = "AMBIGUOUS_DATE"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    INVALID_MONEY = "INVALID_MONEY"
    ADJUSTMENT_OBSERVED = "ADJUSTMENT_OBSERVED"
    ADJUSTMENT_SCOPE_OR_DIRECTION_UNKNOWN = "ADJUSTMENT_SCOPE_OR_DIRECTION_UNKNOWN"
    WEIGHT_EVIDENCE_INCOMPLETE = "WEIGHT_EVIDENCE_INCOMPLETE"
    WEIGHT_UNIT_CONFLICT = "WEIGHT_UNIT_CONFLICT"
    CORRECTION_NO_DIRECT_SUPPORT = "CORRECTION_NO_DIRECT_SUPPORT"
    CORRECTION_SHARED_TOKEN_AMBIGUOUS = "CORRECTION_SHARED_TOKEN_AMBIGUOUS"
    CORRECTION_COMPETING_CANDIDATES = "CORRECTION_COMPETING_CANDIDATES"
    CORRECTION_NOT_CORROBORATED = "CORRECTION_NOT_CORROBORATED"
    CORRECTION_APPLIED = "CORRECTION_APPLIED"


class CandidateKind(str, Enum):
    DIRECT_MONETARY_SOURCE = "DIRECT_MONETARY_SOURCE"


@dataclass(frozen=True, slots=True)
class SourceSlice:
    """Exact half-open character slice into an original OCR token."""

    token_id: str
    start: int
    end: int
    text: str

    def __post_init__(self) -> None:
        if not self.token_id or not self.token_id.strip():
            raise ValueError("token_id must be non-empty.")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("source-slice offsets must form a non-empty range.")
        if not self.text:
            raise ValueError("source-slice text must be non-empty.")


@dataclass(frozen=True, slots=True)
class DateParseResult:
    original: str
    state: B3ParseState
    normalized_value: str | None = None
    interpretations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class QuantityParseResult:
    original: str
    state: B3ParseState
    normalized_value: str | None = None
    decimal_value: Decimal | None = None


@dataclass(frozen=True, slots=True)
class MoneyParseResult:
    original: str
    state: B3ParseState
    normalized_value: str | None = None
    decimal_value: Decimal | None = None
    currency_marker: str | None = None


@dataclass(frozen=True, slots=True)
class B3Candidate:
    target_field_id: str
    value: str
    kind: CandidateKind
    source_slices: tuple[SourceSlice, ...]

    def __post_init__(self) -> None:
        if not self.target_field_id or not self.target_field_id.strip():
            raise ValueError("candidate target_field_id must be non-empty.")
        if not self.value or not self.value.strip():
            raise ValueError("candidate value must be non-empty.")
        if not self.source_slices:
            raise ValueError("a B3 candidate requires exact source slices.")

    @property
    def source_token_ids(self) -> tuple[str, ...]:
        return _unique(item.token_id for item in self.source_slices)


@dataclass(frozen=True, slots=True)
class B3RuleEvent:
    event_id: str
    sequence: int
    rule_id: str
    outcome: B3RuleOutcome
    target_field_ids: tuple[str, ...] = ()
    original_values: tuple[str | None, ...] = ()
    resulting_values: tuple[str | None, ...] = ()
    source_slices: tuple[SourceSlice, ...] = ()
    candidate_values: tuple[str, ...] = ()
    message: str = ""


@dataclass(frozen=True, slots=True)
class B3Diagnostic:
    diagnostic_id: str
    code: DiagnosticCode
    rule_id: str
    field_ids: tuple[str, ...]
    source_token_ids: tuple[str, ...]
    message: str


@dataclass(frozen=True, slots=True)
class ArithmeticDiagnostic:
    diagnostic_id: str
    phase: ArithmeticPhase
    scope: ArithmeticScope
    outcome: ArithmeticOutcome
    field_ids: tuple[str, ...]
    source_token_ids: tuple[str, ...]
    equation: str
    expected_value: str | None = None
    observed_value: str | None = None
    absolute_difference: str | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class AdjustmentEvidence:
    adjustment_id: str
    kind: AdjustmentKind
    label: str
    amount: str
    currency_marker: str | None
    direction: AdjustmentDirection
    source_slice: SourceSlice
    already_represented: bool
    ambiguity_reason: str | None = None


@dataclass(frozen=True, slots=True)
class B3FieldTransformation:
    field_id: str
    original_field: StructuredField
    transformed_field: StructuredField
    event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.field_id != self.original_field.field_id:
            raise ValueError("field transformation must identify its original field.")
        if self.field_id != self.transformed_field.field_id:
            raise ValueError("field transformation must retain the field ID.")
        if self.original_field.status is not self.transformed_field.status:
            raise ValueError("B3 V0 must preserve field status.")
        if self.original_field.receipt_id != self.transformed_field.receipt_id:
            raise ValueError("B3 V0 must preserve field receipt identity.")
        if self.original_field.field_name is not self.transformed_field.field_name:
            raise ValueError("B3 V0 must preserve the field name.")
        if self.original_field.item_row_id != self.transformed_field.item_row_id:
            raise ValueError("B3 V0 must preserve item-row association.")
        if (
            self.original_field.source_token_ids
            != self.transformed_field.source_token_ids
        ):
            raise ValueError("B3 V0 must preserve field source references.")
        if self.original_field.confidence != self.transformed_field.confidence:
            raise ValueError("B3 V0 must preserve field confidence semantics.")
        if (
            self.original_field.unresolved_reason
            != self.transformed_field.unresolved_reason
        ):
            raise ValueError("B3 V0 must preserve unresolved reasons.")


@dataclass(frozen=True, slots=True)
class B3Result:
    """Original B2 result plus a distinct automatic B3 prediction and audit trail."""

    original_b2_result: B2ExtractionResult
    receipt_output: ReceiptOutput | None
    field_transformations: tuple[B3FieldTransformation, ...] = ()
    rule_events: tuple[B3RuleEvent, ...] = ()
    candidates: tuple[B3Candidate, ...] = ()
    arithmetic_diagnostics: tuple[ArithmeticDiagnostic, ...] = ()
    adjustments: tuple[AdjustmentEvidence, ...] = ()
    diagnostics: tuple[B3Diagnostic, ...] = ()
    ruleset_id: str = field(default=RULESET_ID, init=False)

    def __post_init__(self) -> None:
        original = self.original_b2_result.receipt_output
        if original is None:
            disposition = self.original_b2_result.pre_resolution_disposition
            if (
                disposition is None
                or disposition.state is not PolicyState.FALLBACK_NO_UPDATE
            ):
                raise ValueError("B3 fallback requires the original B2 fallback.")
            if self.receipt_output is not None:
                raise ValueError("B3 cannot create output after B2 fallback.")
            if any(
                (
                    self.field_transformations,
                    self.rule_events,
                    self.candidates,
                    self.arithmetic_diagnostics,
                    self.adjustments,
                    self.diagnostics,
                )
            ):
                raise ValueError("B3 fallback must not run downstream rules.")
            return

        if self.original_b2_result.pre_resolution_disposition is not None:
            raise ValueError("Structured B2 input must not also contain fallback.")
        if self.receipt_output is None:
            raise ValueError("Structured B2 input requires an automatic B3 output.")
        output = self.receipt_output
        if output.receipt_id != original.receipt_id:
            raise ValueError("B3 must preserve receipt identity.")
        if output.source_evidence is not original.source_evidence:
            raise ValueError("B3 must retain the exact source-evidence object.")
        if output.extraction_status is not original.extraction_status:
            raise ValueError("B3 V0 must preserve B2 extraction status.")
        if output.output_stage is not OutputStage.PRE_REVIEW_AUTOMATIC:
            raise ValueError("B3 output must remain pre-review automatic.")
        if output.extractor_version != EXTRACTOR_VERSION:
            raise ValueError("Unexpected B3 extractor version.")

        original_fields = _flatten_fields(original)
        transformed_fields = _flatten_fields(output)
        if tuple(original_fields) != tuple(transformed_fields):
            raise ValueError("B3 must retain every B2 field ID and order.")
        if tuple(item.row_id for item in original.items) != tuple(
            item.row_id for item in output.items
        ):
            raise ValueError("B3 must retain B2 item rows and order.")
        if tuple(item.pantry_product_identity for item in original.items) != tuple(
            item.pantry_product_identity for item in output.items
        ):
            raise ValueError("B3 must not change pantry product identity.")
        if tuple(t.field_id for t in self.field_transformations) != tuple(
            original_fields
        ):
            raise ValueError("B3 requires one ordered relationship per B2 field.")
        for transformation in self.field_transformations:
            if transformation.original_field is not original_fields[
                transformation.field_id
            ]:
                raise ValueError("A field relationship must retain its B2 field object.")
            if transformation.transformed_field is not transformed_fields[
                transformation.field_id
            ]:
                raise ValueError("A field relationship must retain its B3 field object.")

        candidate_keys = tuple(
            (candidate.target_field_id, candidate.value)
            for candidate in self.candidates
        )
        if len(candidate_keys) != len(set(candidate_keys)):
            raise ValueError("B3 candidates must be distinct per target and value.")
        monetary_fields = {
            field_value.field_id: field_value
            for field_value in _monetary_fields(output)
        }
        for candidate in self.candidates:
            if candidate.target_field_id not in transformed_fields:
                raise ValueError("A B3 candidate targets an unknown field.")
            if candidate.target_field_id not in monetary_fields:
                raise ValueError("A B3 candidate must target a monetary field.")
            if parse_money(candidate.value).state is not B3ParseState.VALID:
                raise ValueError("A B3 candidate must contain a valid money value.")
            target_references = set(
                transformed_fields[candidate.target_field_id].source_token_ids
            )
            if not set(candidate.source_token_ids).issubset(target_references):
                raise ValueError(
                    "Candidate support must remain inside the target field boundary."
                )
            if any(
                set(candidate.source_token_ids).intersection(
                    field_value.source_token_ids
                )
                for field_id, field_value in monetary_fields.items()
                if field_id != candidate.target_field_id
            ):
                raise ValueError(
                    "Candidate support cannot be shared with another monetary role."
                )
        candidate_by_key = {
            (candidate.target_field_id, candidate.value): candidate
            for candidate in self.candidates
        }

        event_ids = tuple(event.event_id for event in self.rule_events)
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("B3 event IDs must be unique.")
        if tuple(event.sequence for event in self.rule_events) != tuple(
            range(len(self.rule_events))
        ):
            raise ValueError("B3 events must have contiguous deterministic sequence.")
        known_event_ids = set(event_ids)
        if any(
            target_field_id not in transformed_fields
            for event in self.rule_events
            for target_field_id in event.target_field_ids
        ):
            raise ValueError("A B3 event targets an unknown field.")
        if any(
            event_id not in known_event_ids
            for relation in self.field_transformations
            for event_id in relation.event_ids
        ):
            raise ValueError("A field relationship references an unknown rule event.")
        event_by_id = {event.event_id: event for event in self.rule_events}
        for event in self.rule_events:
            if event.outcome is not B3RuleOutcome.CANDIDATE_APPLIED:
                continue
            if (
                len(event.target_field_ids) != 1
                or len(event.candidate_values) != 1
                or len(event.resulting_values) != 1
            ):
                raise ValueError(
                    "An applied candidate event requires one target and value."
                )
            key = (event.target_field_ids[0], event.candidate_values[0])
            selected = candidate_by_key.get(key)
            if selected is None:
                raise ValueError("An applied value must belong to B3 candidates.")
            if event.resulting_values[0] != selected.value:
                raise ValueError("Applied event output must equal its candidate value.")
            if event.source_slices != selected.source_slices:
                raise ValueError("Applied event must retain candidate source slices.")
        for relationship in self.field_transformations:
            if any(
                relationship.field_id
                not in event_by_id[event_id].target_field_ids
                for event_id in relationship.event_ids
            ):
                raise ValueError(
                    "A field relationship may reference only events targeting that field."
                )
            if (
                relationship.original_field.value
                != relationship.transformed_field.value
                and not any(
                    event_by_id[event_id].outcome
                    in {
                        B3RuleOutcome.REPRESENTATION_CHANGED,
                        B3RuleOutcome.CANDIDATE_APPLIED,
                    }
                    for event_id in relationship.event_ids
                )
            ):
                raise ValueError("Every changed B3 value requires an applied rule event.")
        for identifiers, label in (
            (tuple(item.diagnostic_id for item in self.diagnostics), "diagnostic"),
            (
                tuple(item.diagnostic_id for item in self.arithmetic_diagnostics),
                "arithmetic diagnostic",
            ),
            (tuple(item.adjustment_id for item in self.adjustments), "adjustment"),
        ):
            if len(identifiers) != len(set(identifiers)):
                raise ValueError(f"B3 {label} IDs must be unique.")
        _validate_candidate_literals(self)
        _validate_adjustments(self)
        _validate_source_slices(self)

    @property
    def pre_resolution_disposition(self) -> PreResolutionDisposition | None:
        return self.original_b2_result.pre_resolution_disposition

    @property
    def transformed_output(self) -> ReceiptOutput | None:
        return self.receipt_output

    @property
    def b2_result(self) -> B2ExtractionResult:
        return self.original_b2_result


def normalize_receipt_text(value: str) -> str:
    """Apply the frozen NFKC/case/punctuation/whitespace representation rules."""

    if not isinstance(value, str):
        raise TypeError("value must be a string.")
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.casefold()
    normalized = normalized.translate(_PUNCTUATION_TRANSLATION)
    return " ".join(normalized.split())


def parse_generic_date(value: str) -> DateParseResult:
    """Parse only complete, calendar-valid, locale-independent date evidence."""

    if not isinstance(value, str):
        raise TypeError("value must be a string.")
    observed = unicodedata.normalize("NFKC", value).strip()

    match = _YEAR_FIRST_DATE_RE.fullmatch(observed)
    if match:
        parsed = _calendar_date(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )
        if parsed is None:
            return DateParseResult(value, B3ParseState.INVALID)
        iso = parsed.isoformat()
        return DateParseResult(value, B3ParseState.VALID, iso, (iso,))

    match = _NUMERIC_DATE_RE.fullmatch(observed)
    if match:
        first = int(match.group("first"))
        second = int(match.group("second"))
        year = int(match.group("year"))
        day_first = _calendar_date(year, second, first)
        month_first = _calendar_date(year, first, second)
        interpretations = _unique(
            item.isoformat()
            for item in (day_first, month_first)
            if item is not None
        )
        if not interpretations:
            return DateParseResult(value, B3ParseState.INVALID)
        if len(interpretations) > 1:
            return DateParseResult(
                value, B3ParseState.AMBIGUOUS, None, interpretations
            )
        return DateParseResult(
            value, B3ParseState.VALID, interpretations[0], interpretations
        )

    for pattern in (_DAY_MONTH_NAME_RE, _MONTH_NAME_DAY_RE):
        match = pattern.fullmatch(observed)
        if match:
            parsed = _calendar_date(
                int(match.group("year")),
                _MONTH_NUMBERS[match.group("month")[:3].upper()],
                int(match.group("day")),
            )
            if parsed is None:
                return DateParseResult(value, B3ParseState.INVALID)
            iso = parsed.isoformat()
            return DateParseResult(value, B3ParseState.VALID, iso, (iso,))

    return DateParseResult(value, B3ParseState.INVALID)


def parse_positive_quantity(value: str) -> QuantityParseResult:
    """Parse a complete positive, unitless Decimal quantity representation."""

    if not isinstance(value, str):
        raise TypeError("value must be a string.")
    observed = unicodedata.normalize("NFKC", value).strip()
    match = _QUANTITY_RE.fullmatch(observed)
    if match is None:
        return QuantityParseResult(value, B3ParseState.INVALID)
    try:
        number = Decimal(match.group("number").replace(",", ""))
    except InvalidOperation:
        return QuantityParseResult(value, B3ParseState.INVALID)
    if not number.is_finite() or number <= 0:
        return QuantityParseResult(value, B3ParseState.INVALID)
    normalized = _plain_decimal(number)
    return QuantityParseResult(value, B3ParseState.VALID, normalized, number)


def parse_money(value: str) -> MoneyParseResult:
    """Parse the frozen dot-decimal monetary grammar without currency conversion."""

    if not isinstance(value, str):
        raise TypeError("value must be a string.")
    observed = unicodedata.normalize("NFKC", value).strip()
    match = _MONEY_RE.fullmatch(observed)
    if match is None:
        return MoneyParseResult(value, B3ParseState.INVALID)
    try:
        number = Decimal(match.group("number").replace(",", ""))
    except InvalidOperation:
        return MoneyParseResult(value, B3ParseState.INVALID)
    if not number.is_finite() or number < 0:
        return MoneyParseResult(value, B3ParseState.INVALID)
    marker = _currency_marker(match.group("prefix"))
    normalized = format(_quantize_currency(number), ".2f")
    return MoneyParseResult(
        value, B3ParseState.VALID, normalized, number, marker
    )


@dataclass(slots=True)
class _AuditBuilder:
    receipt_id: str
    field_event_ids: dict[str, list[str]]
    events: list[B3RuleEvent] = field(default_factory=list)
    candidates: list[B3Candidate] = field(default_factory=list)
    diagnostics: list[B3Diagnostic] = field(default_factory=list)

    def event(
        self,
        rule_id: str,
        outcome: B3RuleOutcome,
        *,
        target_field_ids: tuple[str, ...] = (),
        original_values: tuple[str | None, ...] = (),
        resulting_values: tuple[str | None, ...] = (),
        source_slices: tuple[SourceSlice, ...] = (),
        candidate_values: tuple[str, ...] = (),
        message: str = "",
    ) -> str:
        sequence = len(self.events)
        event_id = f"{self.receipt_id}:b3:event:{sequence:06d}"
        event = B3RuleEvent(
            event_id=event_id,
            sequence=sequence,
            rule_id=rule_id,
            outcome=outcome,
            target_field_ids=target_field_ids,
            original_values=original_values,
            resulting_values=resulting_values,
            source_slices=source_slices,
            candidate_values=candidate_values,
            message=message,
        )
        self.events.append(event)
        for field_id in target_field_ids:
            if field_id in self.field_event_ids:
                self.field_event_ids[field_id].append(event_id)
        return event_id

    def diagnostic(
        self,
        code: DiagnosticCode,
        rule_id: str,
        *,
        field_ids: tuple[str, ...],
        source_token_ids: tuple[str, ...],
        message: str,
    ) -> str:
        sequence = len(self.diagnostics)
        diagnostic_id = f"{self.receipt_id}:b3:diagnostic:{sequence:06d}"
        self.diagnostics.append(
            B3Diagnostic(
                diagnostic_id=diagnostic_id,
                code=code,
                rule_id=rule_id,
                field_ids=field_ids,
                source_token_ids=source_token_ids,
                message=message,
            )
        )
        return diagnostic_id


def apply_b3(b2_result: B2ExtractionResult) -> B3Result:
    """Apply frozen generic B3 rules to one already-computed B2 result."""

    if not isinstance(b2_result, B2ExtractionResult):
        raise TypeError("b2_result must be B2ExtractionResult.")

    original = b2_result.receipt_output
    if original is None:
        # B2ExtractionResult and PreResolutionDisposition validate this branch.
        return B3Result(original_b2_result=b2_result, receipt_output=None)

    if original.extractor_version != REQUIRED_B2_EXTRACTOR_VERSION:
        raise ValueError(
            "B3 requires the exact frozen B2 extractor identifier "
            f"{REQUIRED_B2_EXTRACTOR_VERSION!r}."
        )

    original_fields = _flatten_fields(original)
    transformed_fields = dict(original_fields)
    field_event_ids = {field_id: [] for field_id in original_fields}
    audit = _AuditBuilder(original.receipt_id, field_event_ids)

    _apply_text_normalization(original, transformed_fields, audit)
    _apply_date_normalization(original, transformed_fields, audit)
    _apply_quantity_normalization(original, transformed_fields, audit)
    _apply_money_normalization(original, transformed_fields, audit)
    normalized_output = _rebuild_output(original, transformed_fields)

    adjustments = _scan_adjustments(normalized_output, audit)
    pre_arithmetic = _arithmetic_diagnostics(
        normalized_output, adjustments, ArithmeticPhase.PRE_CORRECTION
    )
    _record_arithmetic_events(pre_arithmetic, audit)

    corrected_fields = dict(_flatten_fields(normalized_output))
    _apply_source_supported_corrections(
        normalized_output, corrected_fields, adjustments, pre_arithmetic, audit
    )
    final_output = _rebuild_output(original, corrected_fields)

    final_arithmetic = _arithmetic_diagnostics(
        final_output, adjustments, ArithmeticPhase.FINAL
    )
    _record_arithmetic_events(final_arithmetic, audit)

    final_fields = _flatten_fields(final_output)
    relationships = tuple(
        B3FieldTransformation(
            field_id=field_id,
            original_field=original_field,
            transformed_field=final_fields[field_id],
            event_ids=tuple(field_event_ids[field_id]),
        )
        for field_id, original_field in original_fields.items()
    )
    return B3Result(
        original_b2_result=b2_result,
        receipt_output=final_output,
        field_transformations=relationships,
        rule_events=tuple(audit.events),
        candidates=tuple(audit.candidates),
        arithmetic_diagnostics=pre_arithmetic + final_arithmetic,
        adjustments=adjustments,
        diagnostics=tuple(audit.diagnostics),
    )


def _apply_text_normalization(
    output: ReceiptOutput,
    fields: dict[str, StructuredField],
    audit: _AuditBuilder,
) -> None:
    targets = [output.store_name]
    targets.extend(item.description for item in output.items)
    for original_field in targets:
        field_value = fields[original_field.field_id]
        if field_value.status is not FieldStatus.EXTRACTED:
            continue
        assert field_value.value is not None
        normalized = normalize_receipt_text(field_value.value)
        changed = normalized != field_value.value
        if changed:
            fields[field_value.field_id] = replace(field_value, value=normalized)
        audit.event(
            "B3-TEXT-NORMALIZE",
            B3RuleOutcome.REPRESENTATION_CHANGED
            if changed
            else B3RuleOutcome.UNCHANGED,
            target_field_ids=(field_value.field_id,),
            original_values=(field_value.value,),
            resulting_values=(normalized,),
            source_slices=_whole_source_slices(output, field_value),
            message=(
                "Applied NFKC, casefold, frozen punctuation mapping, and Unicode "
                "whitespace collapse."
                if changed
                else "The frozen text representation was already canonical."
            ),
        )


def _apply_date_normalization(
    output: ReceiptOutput,
    fields: dict[str, StructuredField],
    audit: _AuditBuilder,
) -> None:
    target = fields[output.purchase_date.field_id]
    if target.status is not FieldStatus.EXTRACTED:
        return
    assert target.value is not None
    parsed = parse_generic_date(target.value)
    slices = _whole_source_slices(output, target)
    if parsed.state is B3ParseState.VALID:
        assert parsed.normalized_value is not None
        changed = parsed.normalized_value != target.value
        if changed:
            fields[target.field_id] = replace(target, value=parsed.normalized_value)
        audit.event(
            "B3-DATE-PARSE",
            B3RuleOutcome.REPRESENTATION_CHANGED
            if changed
            else B3RuleOutcome.UNCHANGED,
            target_field_ids=(target.field_id,),
            original_values=(target.value,),
            resulting_values=(parsed.normalized_value,),
            source_slices=slices,
            message="Parsed one complete calendar-valid generic date.",
        )
        return

    code = (
        DiagnosticCode.AMBIGUOUS_DATE
        if parsed.state is B3ParseState.AMBIGUOUS
        else DiagnosticCode.INVALID_DATE
    )
    audit.diagnostic(
        code,
        "B3-DATE-PARSE",
        field_ids=(target.field_id,),
        source_token_ids=target.source_token_ids,
        message=(
            "Numeric date has distinct valid day-first and month-first readings."
            if parsed.state is B3ParseState.AMBIGUOUS
            else "Date is outside the frozen complete grammar or is calendar-invalid."
        ),
    )
    audit.event(
        "B3-DATE-PARSE",
        B3RuleOutcome.DIAGNOSTIC_ONLY,
        target_field_ids=(target.field_id,),
        original_values=(target.value,),
        resulting_values=(target.value,),
        source_slices=slices,
        candidate_values=parsed.interpretations,
        message="Unsafe date evidence was retained unchanged.",
    )


def _apply_quantity_normalization(
    output: ReceiptOutput,
    fields: dict[str, StructuredField],
    audit: _AuditBuilder,
) -> None:
    for item in output.items:
        target = fields[item.quantity.field_id]
        if target.status is not FieldStatus.EXTRACTED:
            continue
        assert target.value is not None
        parsed = parse_positive_quantity(target.value)
        slices = _whole_source_slices(output, target)
        if parsed.state is B3ParseState.VALID:
            assert parsed.normalized_value is not None
            changed = parsed.normalized_value != target.value
            if changed:
                fields[target.field_id] = replace(target, value=parsed.normalized_value)
            audit.event(
                "B3-QUANTITY-PARSE",
                B3RuleOutcome.REPRESENTATION_CHANGED
                if changed
                else B3RuleOutcome.UNCHANGED,
                target_field_ids=(target.field_id,),
                original_values=(target.value,),
                resulting_values=(parsed.normalized_value,),
                source_slices=slices,
                message="Parsed an unambiguous positive Decimal quantity.",
            )
        else:
            audit.diagnostic(
                DiagnosticCode.INVALID_QUANTITY,
                "B3-QUANTITY-PARSE",
                field_ids=(target.field_id,),
                source_token_ids=target.source_token_ids,
                message="Quantity is invalid under the frozen positive Decimal grammar.",
            )
            audit.event(
                "B3-QUANTITY-PARSE",
                B3RuleOutcome.DIAGNOSTIC_ONLY,
                target_field_ids=(target.field_id,),
                original_values=(target.value,),
                resulting_values=(target.value,),
                source_slices=slices,
                message="Invalid quantity was retained unchanged.",
            )


def _apply_money_normalization(
    output: ReceiptOutput,
    fields: dict[str, StructuredField],
    audit: _AuditBuilder,
) -> None:
    targets: list[StructuredField] = []
    for item in output.items:
        targets.extend((item.unit_price, item.line_total))
    targets.append(output.receipt_total)
    for original_field in targets:
        target = fields[original_field.field_id]
        if target.status is not FieldStatus.EXTRACTED:
            continue
        assert target.value is not None
        parsed = parse_money(target.value)
        slices = _whole_source_slices(output, target)
        if parsed.state is B3ParseState.VALID:
            assert parsed.normalized_value is not None
            changed = parsed.normalized_value != target.value
            if changed:
                fields[target.field_id] = replace(target, value=parsed.normalized_value)
            audit.event(
                "B3-MONEY-PARSE",
                B3RuleOutcome.REPRESENTATION_CHANGED
                if changed
                else B3RuleOutcome.UNCHANGED,
                target_field_ids=(target.field_id,),
                original_values=(target.value,),
                resulting_values=(parsed.normalized_value,),
                source_slices=slices,
                message=(
                    "Parsed dot-decimal currency representation without conversion."
                ),
            )
        else:
            audit.diagnostic(
                DiagnosticCode.INVALID_MONEY,
                "B3-MONEY-PARSE",
                field_ids=(target.field_id,),
                source_token_ids=target.source_token_ids,
                message="Money value is invalid under the frozen complete grammar.",
            )
            audit.event(
                "B3-MONEY-PARSE",
                B3RuleOutcome.DIAGNOSTIC_ONLY,
                target_field_ids=(target.field_id,),
                original_values=(target.value,),
                resulting_values=(target.value,),
                source_slices=slices,
                message="Invalid monetary representation was retained unchanged.",
            )


def _scan_adjustments(
    output: ReceiptOutput, audit: _AuditBuilder
) -> tuple[AdjustmentEvidence, ...]:
    description_ids = {
        token_id
        for item in output.items
        for token_id in item.description.source_token_ids
    }
    adjustments: list[AdjustmentEvidence] = []
    for token in output.source_evidence.tokens:
        if token.token_id in description_ids:
            continue
        match = _ADJUSTMENT_RE.fullmatch(token.original_text)
        if match is None:
            continue
        money = parse_money(match.group("amount"))
        if money.state is not B3ParseState.VALID:
            continue
        assert money.normalized_value is not None
        label = " ".join(match.group("label").upper().split())
        kind = AdjustmentKind(label.replace(" ", "_"))
        sign = match.group("sign")
        direction = _adjustment_direction(kind, sign)
        ambiguity_reason = _adjustment_ambiguity_reason(kind, direction)
        source_slice = SourceSlice(
            token_id=token.token_id,
            start=match.start("amount"),
            end=match.end("amount"),
            text=token.original_text[match.start("amount") : match.end("amount")],
        )
        evidence = AdjustmentEvidence(
            adjustment_id=(
                f"{output.receipt_id}:b3:adjustment:{len(adjustments):06d}"
            ),
            kind=kind,
            label=match.group("label"),
            amount=money.normalized_value,
            currency_marker=money.currency_marker,
            direction=direction,
            source_slice=source_slice,
            already_represented=_adjustment_already_represented(
                output, token.token_id, money.normalized_value
            ),
            ambiguity_reason=ambiguity_reason,
        )
        adjustments.append(evidence)
        audit.diagnostic(
            DiagnosticCode.ADJUSTMENT_OBSERVED,
            "B3-ADJUSTMENT-SCAN",
            field_ids=(),
            source_token_ids=(token.token_id,),
            message=f"Observed complete anchored {kind.value} adjustment evidence.",
        )
        audit.diagnostic(
            DiagnosticCode.ADJUSTMENT_SCOPE_OR_DIRECTION_UNKNOWN,
            "B3-ADJUSTMENT-SCAN",
            field_ids=(),
            source_token_ids=(token.token_id,),
            message=ambiguity_reason,
        )
        audit.event(
            "B3-ADJUSTMENT-SCAN",
            B3RuleOutcome.EVIDENCE_RECORDED,
            source_slices=(source_slice,),
            resulting_values=(money.normalized_value,),
            message=(
                "Recorded complete single-token adjustment evidence without "
                "changing an output field."
            ),
        )
    return tuple(adjustments)


def _adjustment_direction(
    kind: AdjustmentKind, sign: str | None
) -> AdjustmentDirection:
    subtraction = {
        AdjustmentKind.DISCOUNT,
        AdjustmentKind.VOUCHER,
        AdjustmentKind.COUPON,
        AdjustmentKind.REBATE,
    }
    addition = {
        AdjustmentKind.TAX,
        AdjustmentKind.GST,
        AdjustmentKind.SST,
        AdjustmentKind.SERVICE_TAX,
        AdjustmentKind.SERVICE_CHARGE,
        AdjustmentKind.SURCHARGE,
    }
    if kind is AdjustmentKind.SUBTOTAL:
        return AdjustmentDirection.REFERENCE_ONLY
    if kind is AdjustmentKind.ROUNDING:
        if sign == "+":
            return AdjustmentDirection.ADD
        if sign == "-":
            return AdjustmentDirection.SUBTRACT
        return AdjustmentDirection.UNKNOWN
    if kind in subtraction:
        return (
            AdjustmentDirection.UNKNOWN
            if sign == "+"
            else AdjustmentDirection.SUBTRACT
        )
    if kind in addition:
        return (
            AdjustmentDirection.UNKNOWN
            if sign == "-"
            else AdjustmentDirection.ADD
        )
    return AdjustmentDirection.UNKNOWN


def _adjustment_ambiguity_reason(
    kind: AdjustmentKind, direction: AdjustmentDirection
) -> str:
    reason = "Adjustment scope is not represented in Contract V0."
    if direction is AdjustmentDirection.UNKNOWN:
        reason += (
            " Rounding direction is also unknown."
            if kind is AdjustmentKind.ROUNDING
            else " The observed sign conflicts with the label direction."
        )
    return reason


def _arithmetic_diagnostics(
    output: ReceiptOutput,
    adjustments: tuple[AdjustmentEvidence, ...],
    phase: ArithmeticPhase,
) -> tuple[ArithmeticDiagnostic, ...]:
    diagnostics: list[ArithmeticDiagnostic] = []
    for item in output.items:
        diagnostics.append(
            _item_arithmetic_diagnostic(
                output, item, phase, len(diagnostics)
            )
        )
    diagnostics.append(
        _receipt_arithmetic_diagnostic(
            output, adjustments, phase, len(diagnostics)
        )
    )
    return tuple(diagnostics)


def _item_arithmetic_diagnostic(
    output: ReceiptOutput,
    item: ReceiptItemRow,
    phase: ArithmeticPhase,
    index: int,
) -> ArithmeticDiagnostic:
    fields = (item.quantity, item.unit_price, item.line_total)
    field_ids = tuple(item_field.field_id for item_field in fields)
    source_ids = _unique(
        token_id for item_field in fields for token_id in item_field.source_token_ids
    )
    diagnostic_id = (
        f"{output.receipt_id}:b3:arithmetic:{phase.value.lower()}:{index:06d}"
    )
    if any(item_field.status is not FieldStatus.EXTRACTED for item_field in fields):
        return ArithmeticDiagnostic(
            diagnostic_id,
            phase,
            ArithmeticScope.ITEM,
            ArithmeticOutcome.INCOMPLETE_OPERANDS,
            field_ids,
            source_ids,
            "quantity * unit_price = line_total",
            message="At least one B2 item operand is missing or unresolved.",
        )
    assert item.quantity.value is not None
    assert item.unit_price.value is not None
    assert item.line_total.value is not None
    quantity = parse_positive_quantity(item.quantity.value)
    unit_price = parse_money(item.unit_price.value)
    line_total = parse_money(item.line_total.value)
    if (
        quantity.state is not B3ParseState.VALID
        or unit_price.state is not B3ParseState.VALID
        or line_total.state is not B3ParseState.VALID
    ):
        return ArithmeticDiagnostic(
            diagnostic_id,
            phase,
            ArithmeticScope.ITEM,
            ArithmeticOutcome.INCOMPLETE_OPERANDS,
            field_ids,
            source_ids,
            "quantity * unit_price = line_total",
            message="At least one item operand is invalid under the frozen grammar.",
        )

    weight_state = _weight_state(output, item)
    if weight_state in {"INCOMPLETE", "CONFLICT"}:
        return ArithmeticDiagnostic(
            diagnostic_id,
            phase,
            ArithmeticScope.ITEM,
            ArithmeticOutcome.AMBIGUOUS_OR_CONFLICTING_UNITS,
            field_ids,
            source_ids,
            "quantity * unit_price = line_total",
            message=(
                "Explicit weighted-goods evidence lacks a matching quantity unit "
                "and unit-price denominator."
                if weight_state == "INCOMPLETE"
                else (
                    "Explicit weighted-goods quantity, rate, or unit evidence "
                    "conflicts; no conversion is allowed."
                )
            ),
        )

    if _currency_conflict(output, (item.unit_price, item.line_total)):
        return ArithmeticDiagnostic(
            diagnostic_id,
            phase,
            ArithmeticScope.ITEM,
            ArithmeticOutcome.CONFLICTING_CURRENCY_MARKERS,
            field_ids,
            source_ids,
            "quantity * unit_price = line_total",
            message="Direct source evidence contains conflicting currency markers.",
        )

    assert quantity.decimal_value is not None
    assert unit_price.decimal_value is not None
    assert line_total.decimal_value is not None
    expected = _multiply_exact(quantity.decimal_value, unit_price.decimal_value)
    observed = line_total.decimal_value
    outcome, difference = _classify_arithmetic(expected, observed)
    if (
        outcome is ArithmeticOutcome.MISMATCH_BEYOND_TOLERANCE
        and _row_has_promotion(output, item)
    ):
        outcome = ArithmeticOutcome.EXPLICIT_PROMOTION_OR_ADJUSTMENT_EXCEPTION
    return ArithmeticDiagnostic(
        diagnostic_id,
        phase,
        ArithmeticScope.ITEM,
        outcome,
        field_ids,
        source_ids,
        "quantity * unit_price = line_total",
        expected_value=_plain_decimal(expected),
        observed_value=_plain_decimal(observed),
        absolute_difference=_plain_decimal(difference),
        message=(
            "Promotion evidence qualifies the mismatch; values remain unchanged."
            if outcome
            is ArithmeticOutcome.EXPLICIT_PROMOTION_OR_ADJUSTMENT_EXCEPTION
            else "Exact Decimal item-equation diagnostic."
        ),
    )


def _receipt_arithmetic_diagnostic(
    output: ReceiptOutput,
    adjustments: tuple[AdjustmentEvidence, ...],
    phase: ArithmeticPhase,
    index: int,
) -> ArithmeticDiagnostic:
    line_fields = tuple(item.line_total for item in output.items)
    fields = line_fields + (output.receipt_total,)
    field_ids = tuple(item_field.field_id for item_field in fields)
    source_ids = _unique(
        token_id for item_field in fields for token_id in item_field.source_token_ids
    )
    diagnostic_id = (
        f"{output.receipt_id}:b3:arithmetic:{phase.value.lower()}:{index:06d}"
    )
    parsed_lines: list[Decimal] = []
    complete = bool(line_fields)
    for line_field in line_fields:
        if line_field.status is not FieldStatus.EXTRACTED or line_field.value is None:
            complete = False
            continue
        parsed = parse_money(line_field.value)
        if parsed.state is not B3ParseState.VALID:
            complete = False
            continue
        assert parsed.decimal_value is not None
        parsed_lines.append(parsed.decimal_value)
    receipt = output.receipt_total
    receipt_value = (
        parse_money(receipt.value)
        if receipt.status is FieldStatus.EXTRACTED and receipt.value is not None
        else None
    )
    if (
        not complete
        or not parsed_lines
        or receipt_value is None
        or receipt_value.state is not B3ParseState.VALID
    ):
        return ArithmeticDiagnostic(
            diagnostic_id,
            phase,
            ArithmeticScope.OBSERVED_RECEIPT_ROWS,
            ArithmeticOutcome.INCOMPLETE_OPERANDS,
            field_ids,
            source_ids,
            "sum(observed line_totals) = receipt_total",
            expected_value=(
                _plain_decimal(_sum_exact(parsed_lines))
                if parsed_lines
                else None
            ),
            message=(
                "Observed-row consistency is incomplete; it is not proof of "
                "complete item detection."
            ),
        )
    applicable_adjustments = tuple(
        evidence
        for evidence in adjustments
        if not evidence.already_represented
        and evidence.direction is not AdjustmentDirection.REFERENCE_ONLY
    )
    if _currency_conflict(output, fields) or _adjustment_currency_conflict(
        output, fields, applicable_adjustments
    ):
        source_ids = _unique(
            (*source_ids, *(a.source_slice.token_id for a in applicable_adjustments))
        )
        return ArithmeticDiagnostic(
            diagnostic_id,
            phase,
            ArithmeticScope.OBSERVED_RECEIPT_ROWS,
            ArithmeticOutcome.CONFLICTING_CURRENCY_MARKERS,
            field_ids,
            source_ids,
            "sum(observed line_totals) = receipt_total",
            message="Direct source evidence contains conflicting currency markers.",
        )
    assert receipt_value.decimal_value is not None
    expected = _sum_exact(parsed_lines)
    observed = receipt_value.decimal_value
    outcome, difference = _classify_arithmetic(expected, observed)
    if (
        outcome is ArithmeticOutcome.MISMATCH_BEYOND_TOLERANCE
        and applicable_adjustments
    ):
        outcome = ArithmeticOutcome.EXPLICIT_PROMOTION_OR_ADJUSTMENT_EXCEPTION
        source_ids = _unique(
            (*source_ids, *(a.source_slice.token_id for a in applicable_adjustments))
        )
    return ArithmeticDiagnostic(
        diagnostic_id,
        phase,
        ArithmeticScope.OBSERVED_RECEIPT_ROWS,
        outcome,
        field_ids,
        source_ids,
        "sum(observed line_totals) = receipt_total",
        expected_value=_plain_decimal(expected),
        observed_value=_plain_decimal(observed),
        absolute_difference=_plain_decimal(difference),
        message=(
            "Explicit adjustment evidence qualifies the observed-row mismatch; "
            "no adjustment is double counted or applied."
            if outcome
            is ArithmeticOutcome.EXPLICIT_PROMOTION_OR_ADJUSTMENT_EXCEPTION
            else "Observed-row Decimal consistency check; not a completeness claim."
        ),
    )


def _classify_arithmetic(
    expected_raw: Decimal, observed: Decimal
) -> tuple[ArithmeticOutcome, Decimal]:
    if expected_raw == observed:
        return ArithmeticOutcome.RAW_EXACT_MATCH, Decimal("0")
    rounded = _quantize_currency(expected_raw)
    if rounded == observed:
        return (
            ArithmeticOutcome.MATCH_AFTER_CURRENCY_ROUNDING,
            Decimal("0"),
        )
    difference = _absolute_difference_exact(rounded, observed)
    if difference <= CURRENCY_TOLERANCE:
        return ArithmeticOutcome.WITHIN_INCLUSIVE_TOLERANCE, difference
    return ArithmeticOutcome.MISMATCH_BEYOND_TOLERANCE, difference


def _record_arithmetic_events(
    diagnostics: tuple[ArithmeticDiagnostic, ...], audit: _AuditBuilder
) -> None:
    for diagnostic in diagnostics:
        if (
            diagnostic.phase is ArithmeticPhase.FINAL
            and diagnostic.outcome
            is ArithmeticOutcome.AMBIGUOUS_OR_CONFLICTING_UNITS
        ):
            incomplete = "lacks a matching" in diagnostic.message
            audit.diagnostic(
                DiagnosticCode.WEIGHT_EVIDENCE_INCOMPLETE
                if incomplete
                else DiagnosticCode.WEIGHT_UNIT_CONFLICT,
                "B3-ARITHMETIC-ITEM",
                field_ids=diagnostic.field_ids,
                source_token_ids=diagnostic.source_token_ids,
                message=diagnostic.message,
            )
        audit.event(
            "B3-ARITHMETIC-ITEM"
            if diagnostic.scope is ArithmeticScope.ITEM
            else "B3-ARITHMETIC-RECEIPT",
            B3RuleOutcome.DIAGNOSTIC_ONLY,
            target_field_ids=diagnostic.field_ids,
            resulting_values=(
                diagnostic.expected_value,
                diagnostic.observed_value,
                diagnostic.absolute_difference,
            ),
            message=f"{diagnostic.phase.value}: {diagnostic.outcome.value}.",
        )


def _apply_source_supported_corrections(
    output: ReceiptOutput,
    fields: dict[str, StructuredField],
    adjustments: tuple[AdjustmentEvidence, ...],
    pre_arithmetic: tuple[ArithmeticDiagnostic, ...],
    audit: _AuditBuilder,
) -> None:
    item_diagnostics = {
        diagnostic.field_ids: diagnostic
        for diagnostic in pre_arithmetic
        if diagnostic.scope is ArithmeticScope.ITEM
    }
    for item in output.items:
        field_ids = (
            item.quantity.field_id,
            item.unit_price.field_id,
            item.line_total.field_id,
        )
        diagnostic = item_diagnostics.get(field_ids)
        if (
            diagnostic is None
            or diagnostic.outcome
            is not ArithmeticOutcome.MISMATCH_BEYOND_TOLERANCE
        ):
            continue
        _correct_item_equation(output, item, fields, adjustments, audit)

    interim = _rebuild_output(output, fields)
    receipt_diagnostic = _receipt_arithmetic_diagnostic(
        interim,
        adjustments,
        ArithmeticPhase.PRE_CORRECTION,
        len(interim.items),
    )
    if (
        receipt_diagnostic.outcome
        is ArithmeticOutcome.MISMATCH_BEYOND_TOLERANCE
    ):
        _correct_receipt_total(interim, fields, adjustments, audit)


def _correct_item_equation(
    output: ReceiptOutput,
    item: ReceiptItemRow,
    fields: dict[str, StructuredField],
    adjustments: tuple[AdjustmentEvidence, ...],
    audit: _AuditBuilder,
) -> None:
    quantity = fields[item.quantity.field_id]
    unit_price = fields[item.unit_price.field_id]
    line_total = fields[item.line_total.field_id]
    targets = (unit_price, line_total)
    target_ids = tuple(target.field_id for target in targets)
    row_token_ids = _unique(
        token_id for row_field in item.fields for token_id in row_field.source_token_ids
    )
    if (
        any(target.status is not FieldStatus.EXTRACTED for target in targets)
        or quantity.status is not FieldStatus.EXTRACTED
        or _row_has_promotion(output, item)
        or _weight_state(output, item) in {"INCOMPLETE", "CONFLICT"}
        or _currency_conflict(output, targets)
        or any(
            adjustment.source_slice.token_id in row_token_ids
            for adjustment in adjustments
        )
    ):
        audit.event(
            "B3-CANDIDATE-DISCOVERY",
            B3RuleOutcome.CANDIDATE_REJECTED,
            target_field_ids=target_ids,
            message=(
                "Promotion, adjustment, unit, currency, or incomplete-row evidence "
                "vetoed semantic correction."
            ),
        )
        return
    assert quantity.value is not None
    assert unit_price.value is not None
    assert line_total.value is not None
    parsed_quantity = parse_positive_quantity(quantity.value)
    parsed_unit = parse_money(unit_price.value)
    parsed_line = parse_money(line_total.value)
    if any(
        parsed.state is not B3ParseState.VALID
        for parsed in (parsed_quantity, parsed_unit, parsed_line)
    ):
        return
    assert parsed_quantity.decimal_value is not None
    assert parsed_unit.decimal_value is not None
    assert parsed_line.decimal_value is not None

    all_candidates: list[B3Candidate] = []
    shared_ambiguity = False
    for target in targets:
        candidates, shared = _direct_money_candidates(output, target)
        all_candidates.extend(candidates)
        shared_ambiguity = shared_ambiguity or shared
    if shared_ambiguity:
        audit.diagnostic(
            DiagnosticCode.CORRECTION_SHARED_TOKEN_AMBIGUOUS,
            "B3-CANDIDATE-DISCOVERY",
            field_ids=target_ids,
            source_token_ids=row_token_ids,
            message=(
                "A source token is shared across monetary roles or contains "
                "several monetary values; it cannot prove one field-role alternative."
            ),
        )
    if not all_candidates:
        audit.diagnostic(
            DiagnosticCode.CORRECTION_NO_DIRECT_SUPPORT,
            "B3-CANDIDATE-DISCOVERY",
            field_ids=target_ids,
            source_token_ids=row_token_ids,
            message=(
                "Arithmetic mismatch supplied no unique alternative directly present "
                "inside an unambiguous target source boundary."
            ),
        )
        audit.event(
            "B3-CANDIDATE-DISCOVERY",
            B3RuleOutcome.CANDIDATE_REJECTED,
            target_field_ids=target_ids,
            message="Arithmetic alone did not create a replacement candidate.",
        )
        return

    audit.event(
        "B3-CANDIDATE-DISCOVERY",
        B3RuleOutcome.CANDIDATE_PROPOSED,
        target_field_ids=target_ids,
        source_slices=tuple(
            source_slice
            for candidate in all_candidates
            for source_slice in candidate.source_slices
        ),
        candidate_values=tuple(candidate.value for candidate in all_candidates),
        message="Recorded directly observed alternatives before arithmetic filtering.",
    )
    audit.candidates.extend(all_candidates)
    eligible: list[B3Candidate] = []
    for candidate in all_candidates:
        parsed = parse_money(candidate.value)
        assert parsed.decimal_value is not None
        if candidate.target_field_id == unit_price.field_id:
            expected = _multiply_exact(
                parsed_quantity.decimal_value, parsed.decimal_value
            )
            observed = parsed_line.decimal_value
        else:
            expected = _multiply_exact(
                parsed_quantity.decimal_value, parsed_unit.decimal_value
            )
            observed = parsed.decimal_value
        outcome, _ = _classify_arithmetic(expected, observed)
        if outcome in {
            ArithmeticOutcome.RAW_EXACT_MATCH,
            ArithmeticOutcome.MATCH_AFTER_CURRENCY_ROUNDING,
        }:
            eligible.append(candidate)

    eligible = _deduplicate_candidates(eligible)
    if len(eligible) != 1:
        code = (
            DiagnosticCode.CORRECTION_COMPETING_CANDIDATES
            if len(eligible) > 1
            else DiagnosticCode.CORRECTION_NOT_CORROBORATED
        )
        audit.diagnostic(
            code,
            "B3-CANDIDATE-APPLY",
            field_ids=target_ids,
            source_token_ids=_unique(
                token_id
                for candidate in all_candidates
                for token_id in candidate.source_token_ids
            ),
            message=(
                "Several directly supported candidates remain; deterministic tie "
                "breaking is forbidden."
                if len(eligible) > 1
                else "Direct candidates exist, but arithmetic does not corroborate one."
            ),
        )
        audit.event(
            "B3-CANDIDATE-APPLY",
            B3RuleOutcome.CANDIDATE_REJECTED,
            target_field_ids=target_ids,
            candidate_values=tuple(candidate.value for candidate in eligible),
            message="No uniquely justified candidate was applied.",
        )
        return

    selected = eligible[0]
    current = fields[selected.target_field_id]
    fields[selected.target_field_id] = replace(current, value=selected.value)
    audit.diagnostic(
        DiagnosticCode.CORRECTION_APPLIED,
        "B3-CANDIDATE-APPLY",
        field_ids=(selected.target_field_id,),
        source_token_ids=selected.source_token_ids,
        message="Applied the sole directly supported and arithmetically corroborated value.",
    )
    audit.event(
        "B3-CANDIDATE-APPLY",
        B3RuleOutcome.CANDIDATE_APPLIED,
        target_field_ids=(selected.target_field_id,),
        original_values=(current.value,),
        resulting_values=(selected.value,),
        source_slices=selected.source_slices,
        candidate_values=(selected.value,),
        message=(
            "Applied one source-literal candidate; arithmetic corroborated but did "
            "not create it."
        ),
    )


def _correct_receipt_total(
    output: ReceiptOutput,
    fields: dict[str, StructuredField],
    adjustments: tuple[AdjustmentEvidence, ...],
    audit: _AuditBuilder,
) -> None:
    target = fields[output.receipt_total.field_id]
    line_totals = tuple(fields[item.line_total.field_id] for item in output.items)
    target_ids = tuple(item.field_id for item in line_totals) + (target.field_id,)
    if (
        target.status is not FieldStatus.EXTRACTED
        or not line_totals
        or any(item.status is not FieldStatus.EXTRACTED for item in line_totals)
        or any(not adjustment.already_represented for adjustment in adjustments)
        or _currency_conflict(output, line_totals + (target,))
    ):
        return
    parsed_lines = tuple(parse_money(item.value or "") for item in line_totals)
    if any(item.state is not B3ParseState.VALID for item in parsed_lines):
        return
    expected = _sum_exact(
        item.decimal_value
        for item in parsed_lines
        if item.decimal_value is not None
    )
    candidates, shared = _direct_money_candidates(output, target)
    if shared:
        audit.diagnostic(
            DiagnosticCode.CORRECTION_SHARED_TOKEN_AMBIGUOUS,
            "B3-CANDIDATE-DISCOVERY",
            field_ids=(target.field_id,),
            source_token_ids=target.source_token_ids,
            message=(
                "Receipt-total support is shared across monetary roles or contains "
                "several monetary values."
            ),
        )
    if not candidates:
        audit.diagnostic(
            DiagnosticCode.CORRECTION_NO_DIRECT_SUPPORT,
            "B3-CANDIDATE-DISCOVERY",
            field_ids=(target.field_id,),
            source_token_ids=target.source_token_ids,
            message="Observed-row arithmetic alone cannot replace receipt total.",
        )
        return
    audit.event(
        "B3-CANDIDATE-DISCOVERY",
        B3RuleOutcome.CANDIDATE_PROPOSED,
        target_field_ids=(target.field_id,),
        source_slices=tuple(
            source_slice
            for candidate in candidates
            for source_slice in candidate.source_slices
        ),
        candidate_values=tuple(candidate.value for candidate in candidates),
        message="Recorded direct receipt-total alternatives.",
    )
    audit.candidates.extend(candidates)
    eligible = []
    for candidate in candidates:
        parsed = parse_money(candidate.value)
        assert parsed.decimal_value is not None
        outcome, _ = _classify_arithmetic(expected, parsed.decimal_value)
        if outcome in {
            ArithmeticOutcome.RAW_EXACT_MATCH,
            ArithmeticOutcome.MATCH_AFTER_CURRENCY_ROUNDING,
        }:
            eligible.append(candidate)
    eligible = _deduplicate_candidates(eligible)
    if len(eligible) != 1:
        audit.diagnostic(
            DiagnosticCode.CORRECTION_COMPETING_CANDIDATES
            if len(eligible) > 1
            else DiagnosticCode.CORRECTION_NOT_CORROBORATED,
            "B3-CANDIDATE-APPLY",
            field_ids=target_ids,
            source_token_ids=_unique(
                token_id
                for candidate in candidates
                for token_id in candidate.source_token_ids
            ),
            message="Receipt-total candidate was not uniquely justified.",
        )
        return
    selected = eligible[0]
    fields[target.field_id] = replace(target, value=selected.value)
    audit.diagnostic(
        DiagnosticCode.CORRECTION_APPLIED,
        "B3-CANDIDATE-APPLY",
        field_ids=(target.field_id,),
        source_token_ids=selected.source_token_ids,
        message="Applied the sole directly supported receipt-total candidate.",
    )
    audit.event(
        "B3-CANDIDATE-APPLY",
        B3RuleOutcome.CANDIDATE_APPLIED,
        target_field_ids=(target.field_id,),
        original_values=(target.value,),
        resulting_values=(selected.value,),
        source_slices=selected.source_slices,
        candidate_values=(selected.value,),
        message="Observed-row arithmetic corroborated a direct source literal.",
    )


def _direct_money_candidates(
    output: ReceiptOutput,
    target: StructuredField,
) -> tuple[list[B3Candidate], bool]:
    token_by_id = {token.token_id: token for token in output.source_evidence.tokens}
    other_money_fields = tuple(
        item_field
        for item_field in _monetary_fields(output)
        if item_field.field_id != target.field_id
    )
    raw_candidates: list[B3Candidate] = []
    shared_ambiguity = False
    current = parse_money(target.value or "")
    current_value = current.normalized_value
    other_reference_ids = {
        token_id
        for item_field in other_money_fields
        for token_id in item_field.source_token_ids
    }
    marker_slices: list[SourceSlice] = []
    marker_groups: set[str] = set()
    unsupported_marker = False
    for token_id in target.source_token_ids:
        token = token_by_id[token_id]
        normalized_token = unicodedata.normalize("NFKC", token.original_text).strip()
        approved = _CURRENCY_MARKER_TOKEN_RE.fullmatch(normalized_token)
        unsupported = _UNSUPPORTED_CURRENCY_MARKER_TOKEN_RE.fullmatch(
            normalized_token
        )
        if approved is None and unsupported is None:
            continue
        if token_id in other_reference_ids:
            shared_ambiguity = True
            unsupported_marker = True
            continue
        if unsupported is not None:
            unsupported_marker = True
            continue
        marker = _currency_marker(approved.group())
        assert marker is not None
        marker_groups.add(_currency_group(marker))
        start = len(token.original_text) - len(token.original_text.lstrip())
        end = len(token.original_text.rstrip())
        marker_slices.append(
            SourceSlice(token_id, start, end, token.original_text[start:end])
        )
    if unsupported_marker or len(marker_groups) > 1:
        return [], True

    for token_id in target.source_token_ids:
        token = token_by_id[token_id]
        if any(
            token_id in item_field.source_token_ids
            for item_field in other_money_fields
        ):
            shared_ambiguity = True
            continue
        matches = tuple(_MONEY_SCAN_RE.finditer(token.original_text))
        if len(matches) > 1:
            shared_ambiguity = True
            continue
        if len(matches) != 1:
            continue
        match = matches[0]
        # Candidate evidence must itself be a complete approved money literal.
        # A numeric substring inside an unknown currency, sign, accounting
        # wrapper, label, or other enclosing text has an ambiguous role and is
        # intentionally not reinterpreted by B3.
        if token.original_text[: match.start()].strip() or token.original_text[
            match.end() :
        ].strip():
            continue
        observed = token.original_text[match.start() : match.end()]
        parsed = parse_money(observed)
        if (
            parsed.state is not B3ParseState.VALID
            or parsed.normalized_value is None
            or parsed.normalized_value == current_value
        ):
            continue
        raw_candidates.append(
            B3Candidate(
                target_field_id=target.field_id,
                value=parsed.normalized_value,
                kind=CandidateKind.DIRECT_MONETARY_SOURCE,
                source_slices=(
                    *marker_slices,
                    SourceSlice(
                        token_id=token_id,
                        start=match.start(),
                        end=match.end(),
                        text=observed,
                    ),
                ),
            )
        )
    return _deduplicate_candidates(raw_candidates), shared_ambiguity


def _deduplicate_candidates(candidates: list[B3Candidate]) -> list[B3Candidate]:
    ordered: list[B3Candidate] = []
    index_by_key: dict[tuple[str, str], int] = {}
    for candidate in candidates:
        key = (candidate.target_field_id, candidate.value)
        if key not in index_by_key:
            index_by_key[key] = len(ordered)
            ordered.append(candidate)
            continue
        index = index_by_key[key]
        prior = ordered[index]
        combined_slices = tuple(
            dict.fromkeys((*prior.source_slices, *candidate.source_slices))
        )
        ordered[index] = replace(prior, source_slices=combined_slices)
    return ordered


def _flatten_fields(output: ReceiptOutput) -> dict[str, StructuredField]:
    ordered: list[StructuredField] = [output.store_name, output.purchase_date]
    for item in output.items:
        ordered.extend(item.fields)
    ordered.append(output.receipt_total)
    return {item.field_id: item for item in ordered}


def _monetary_fields(output: ReceiptOutput) -> tuple[StructuredField, ...]:
    fields: list[StructuredField] = []
    for item in output.items:
        fields.extend((item.unit_price, item.line_total))
    fields.append(output.receipt_total)
    return tuple(fields)


def _rebuild_output(
    original: ReceiptOutput, fields: dict[str, StructuredField]
) -> ReceiptOutput:
    items = tuple(
        replace(
            item,
            description=fields[item.description.field_id],
            quantity=fields[item.quantity.field_id],
            unit_price=fields[item.unit_price.field_id],
            line_total=fields[item.line_total.field_id],
        )
        for item in original.items
    )
    return ReceiptOutput(
        receipt_id=original.receipt_id,
        store_name=fields[original.store_name.field_id],
        purchase_date=fields[original.purchase_date.field_id],
        items=items,
        receipt_total=fields[original.receipt_total.field_id],
        source_evidence=original.source_evidence,
        extraction_status=original.extraction_status,
        extractor_version=EXTRACTOR_VERSION,
        contract_version=original.contract_version,
    )


def _whole_source_slices(
    output: ReceiptOutput, field_value: StructuredField
) -> tuple[SourceSlice, ...]:
    token_by_id = {token.token_id: token for token in output.source_evidence.tokens}
    return tuple(
        SourceSlice(
            token_id,
            0,
            len(token_by_id[token_id].original_text),
            token_by_id[token_id].original_text,
        )
        for token_id in field_value.source_token_ids
    )


def _weight_state(output: ReceiptOutput, item: ReceiptItemRow) -> str:
    token_by_id = {token.token_id: token for token in output.source_evidence.tokens}
    token_ids = _unique(
        token_id for item_field in item.fields for token_id in item_field.source_token_ids
    )
    texts = tuple(token_by_id[token_id].original_text for token_id in token_ids)
    joined_field_texts = tuple(
        " ".join(
            token_by_id[token_id].original_text
            for token_id in field_value.source_token_ids
        )
        for field_value in item.fields
        if field_value.source_token_ids
    )
    evidence_texts = _unique((*texts, *joined_field_texts))
    quantity_evidence = _unique(
        (
            Decimal(match.group("quantity").replace(",", "")),
            _canonical_weight_unit(match.group("unit")),
        )
        for text in evidence_texts
        for match in _WEIGHT_QUANTITY_RE.finditer(text)
    )
    denominator_matches = tuple(
        match
        for text in evidence_texts
        for match in _WEIGHT_DENOMINATOR_RE.finditer(text)
        if match.group("prefix") is not None
        or not _has_unsupported_money_context(text, match.start())
    )
    denominator_evidence = _unique(
        (
            Decimal(match.group("number").replace(",", "")),
            _canonical_weight_unit(match.group("unit")),
        )
        for match in denominator_matches
    )
    denominator_currency_groups = {
        _currency_group(marker)
        for match in denominator_matches
        if (marker := _currency_marker(match.group("prefix"))) is not None
    }
    if not quantity_evidence and not denominator_evidence:
        return "NONE"
    if len(quantity_evidence) != 1 or len(denominator_evidence) != 1:
        return (
            "INCOMPLETE"
            if not quantity_evidence or not denominator_evidence
            else "CONFLICT"
        )
    parsed_quantity = parse_positive_quantity(item.quantity.value or "")
    parsed_unit_price = parse_money(item.unit_price.value or "")
    structured_currency_groups = set(
        _source_currency_markers(output, item.unit_price)
    )
    if (
        parsed_quantity.state is not B3ParseState.VALID
        or parsed_quantity.decimal_value != quantity_evidence[0][0]
        or parsed_unit_price.state is not B3ParseState.VALID
        or parsed_unit_price.decimal_value != denominator_evidence[0][0]
        or len(denominator_currency_groups) > 1
        or (
            denominator_currency_groups
            and structured_currency_groups
            and len(denominator_currency_groups | structured_currency_groups) > 1
        )
    ):
        return "CONFLICT"
    return (
        "MATCHED"
        if quantity_evidence[0][1] == denominator_evidence[0][1]
        else "CONFLICT"
    )


def _canonical_weight_unit(value: str) -> str:
    lowered = value.casefold()
    return "lb" if lowered in {"lb", "lbs"} else lowered


def _has_unsupported_money_context(text: str, match_start: int) -> bool:
    prefix = text[:match_start].rstrip()
    if not prefix:
        return False
    if prefix[-1] in "+-(€£¥":
        return True
    word = re.search(r"(?<![A-Za-z])([A-Za-z]{3})$", prefix)
    return word is not None and word.group(1).upper() not in {"RM", "MYR"}


def _currency_conflict(
    output: ReceiptOutput, fields: tuple[StructuredField, ...]
) -> bool:
    marker_groups: list[str] = []
    for item_field in fields:
        markers = _source_currency_markers(output, item_field)
        marker_groups.extend(markers)
    groups = set(marker_groups)
    return len(groups) > 1


def _adjustment_currency_conflict(
    output: ReceiptOutput,
    fields: tuple[StructuredField, ...],
    adjustments: tuple[AdjustmentEvidence, ...],
) -> bool:
    field_groups = {
        marker
        for field_value in fields
        for marker in _source_currency_markers(output, field_value)
    }
    adjustment_groups = {
        _currency_group(adjustment.currency_marker)
        for adjustment in adjustments
        if adjustment.currency_marker is not None
    }
    return len(adjustment_groups) > 1 or bool(
        field_groups
        and adjustment_groups
        and len(field_groups | adjustment_groups) > 1
    )


def _source_currency_markers(
    output: ReceiptOutput, field_value: StructuredField
) -> tuple[str, ...]:
    token_by_id = {token.token_id: token for token in output.source_evidence.tokens}
    markers: list[str] = []
    for token_id in field_value.source_token_ids:
        text = token_by_id[token_id].original_text
        standalone = _CURRENCY_MARKER_TOKEN_RE.fullmatch(
            unicodedata.normalize("NFKC", text).strip()
        )
        if standalone is not None:
            marker = _currency_marker(standalone.group())
            assert marker is not None
            markers.append(_currency_group(marker))
        for match in _MONEY_SCAN_RE.finditer(text):
            marker = _currency_marker(match.group("prefix"))
            if marker is not None:
                markers.append(_currency_group(marker))
    return _unique(markers)


def _row_has_promotion(output: ReceiptOutput, item: ReceiptItemRow) -> bool:
    token_by_id = {token.token_id: token for token in output.source_evidence.tokens}
    token_ids = _unique(
        token_id for item_field in item.fields for token_id in item_field.source_token_ids
    )
    return any(
        _PROMOTION_RE.search(token_by_id[token_id].original_text)
        for token_id in token_ids
    )


def _adjustment_already_represented(
    output: ReceiptOutput, token_id: str, normalized_amount: str
) -> bool:
    for field_value in _monetary_fields(output):
        if (
            token_id not in field_value.source_token_ids
            or field_value.status is not FieldStatus.EXTRACTED
            or field_value.value is None
        ):
            continue
        parsed = parse_money(field_value.value)
        if (
            parsed.state is B3ParseState.VALID
            and parsed.normalized_value == normalized_amount
        ):
            return True
    return False


def _currency_marker(prefix: str | None) -> str | None:
    if prefix is None:
        return None
    upper = prefix.upper()
    return upper if upper == "$" else upper


def _currency_group(marker: str) -> str:
    return "MYR" if marker in {"RM", "MYR"} else marker


def _calendar_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _decimal_context(*values: Decimal) -> Context:
    """Return an operation-local context large enough for exact operands.

    Python's ambient Decimal context is process mutable and defaults to 28
    significant digits.  B3 derives precision from the accepted operands so a
    caller's context cannot round or reject a grammar-valid value.
    """

    precision = max(
        28,
        sum(max(1, len(value.as_tuple().digits)) for value in values)
        + len(values)
        + 4,
    )
    return Context(prec=precision, rounding=ROUNDING_MODE)


def _quantize_currency(value: Decimal) -> Decimal:
    with localcontext(_decimal_context(value, CURRENCY_QUANTUM)):
        return value.quantize(CURRENCY_QUANTUM, rounding=ROUNDING_MODE)


def _multiply_exact(left: Decimal, right: Decimal) -> Decimal:
    with localcontext(_decimal_context(left, right)):
        return left * right


def _sum_exact(values: Iterable[Decimal]) -> Decimal:
    operands = tuple(values)
    if not operands:
        return Decimal("0")
    with localcontext(_decimal_context(*operands)):
        return sum(operands, Decimal("0"))


def _absolute_difference_exact(left: Decimal, right: Decimal) -> Decimal:
    with localcontext(_decimal_context(left, right)):
        return abs(left - right)


def _plain_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("Decimal diagnostic values must be finite.")
    plain = format(value, "f")
    if "." in plain:
        plain = plain.rstrip("0").rstrip(".")
    return plain or "0"


def _unique(values: Iterable[_T]) -> tuple[_T, ...]:
    # A small stable de-duplicator used only with hashable immutable values.
    ordered: list[_T] = []
    seen: set[_T] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


def _validate_source_slices(result: B3Result) -> None:
    output = result.receipt_output
    if output is None:
        return
    token_by_id = {token.token_id: token for token in output.source_evidence.tokens}
    slices = [item for event in result.rule_events for item in event.source_slices]
    slices.extend(
        item for candidate in result.candidates for item in candidate.source_slices
    )
    slices.extend(adjustment.source_slice for adjustment in result.adjustments)
    for source_slice in slices:
        if source_slice.token_id not in token_by_id:
            raise ValueError("B3 source slice references an unknown OCR token.")
        original_text = token_by_id[source_slice.token_id].original_text
        if source_slice.end > len(original_text):
            raise ValueError("B3 source slice exceeds its original OCR token.")
        if original_text[source_slice.start : source_slice.end] != source_slice.text:
            raise ValueError("B3 source slice does not match original OCR text.")

    known_ids = set(token_by_id)
    referenced_ids = {
        token_id
        for diagnostic in result.diagnostics
        for token_id in diagnostic.source_token_ids
    }
    referenced_ids.update(
        token_id
        for diagnostic in result.arithmetic_diagnostics
        for token_id in diagnostic.source_token_ids
    )
    if not referenced_ids.issubset(known_ids):
        raise ValueError("B3 diagnostics reference unknown OCR tokens.")


def _validate_candidate_literals(result: B3Result) -> None:
    for candidate in result.candidates:
        observed_values: list[str] = []
        for source_slice in candidate.source_slices:
            parsed = parse_money(source_slice.text)
            if parsed.state is B3ParseState.VALID:
                assert parsed.normalized_value is not None
                observed_values.append(parsed.normalized_value)
                continue
            normalized = unicodedata.normalize("NFKC", source_slice.text).strip()
            if _CURRENCY_MARKER_TOKEN_RE.fullmatch(normalized) is None:
                raise ValueError(
                    "Candidate slices must be approved marker or money literals."
                )
        if not observed_values or any(
            value != candidate.value for value in observed_values
        ):
            raise ValueError(
                "Candidate value must equal every supporting source money literal."
            )


def _validate_adjustments(result: B3Result) -> None:
    output = result.receipt_output
    if output is None:
        return
    token_by_id = {token.token_id: token for token in output.source_evidence.tokens}
    description_ids = {
        token_id
        for item in output.items
        for token_id in item.description.source_token_ids
    }
    for adjustment in result.adjustments:
        source_slice = adjustment.source_slice
        if source_slice.token_id in description_ids:
            raise ValueError("Product-description evidence cannot be an adjustment.")
        token = token_by_id.get(source_slice.token_id)
        if token is None:
            raise ValueError("Adjustment references an unknown OCR token.")
        match = _ADJUSTMENT_RE.fullmatch(token.original_text)
        if match is None:
            raise ValueError("Adjustment evidence must match the anchored grammar.")
        parsed = parse_money(match.group("amount"))
        label = match.group("label")
        kind = AdjustmentKind(" ".join(label.upper().split()).replace(" ", "_"))
        direction = _adjustment_direction(kind, match.group("sign"))
        if (
            parsed.state is not B3ParseState.VALID
            or parsed.normalized_value != adjustment.amount
            or parsed.currency_marker != adjustment.currency_marker
            or adjustment.label != label
            or adjustment.kind is not kind
            or adjustment.direction is not direction
            or adjustment.ambiguity_reason
            != _adjustment_ambiguity_reason(kind, direction)
            or source_slice.start != match.start("amount")
            or source_slice.end != match.end("amount")
            or adjustment.already_represented
            != _adjustment_already_represented(
                output, source_slice.token_id, adjustment.amount
            )
        ):
            raise ValueError("Adjustment record contradicts its source evidence.")
