"""B1 minimal deterministic receipt extraction for Contract Version 0.

The extractor consumes an already-gated ``ReceiptSourceEvidence`` package. It
does not execute the source gate, correct OCR, consult retailer data, score
correction candidates, review output, or persist inventory updates.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from pipeline.contracts import (
    FieldStatus,
    OcrSourceToken,
    PolicyState,
    PreResolutionDisposition,
    ReceiptExtractionStatus,
    ReceiptFieldName,
    ReceiptItemRow,
    ReceiptOutput,
    ReceiptSourceEvidence,
    SourceEvidenceDecision,
    StructuredField,
)


EXTRACTOR_VERSION = "B1-deterministic-v0"

_AMOUNT = r"(?:RM\s*|MYR\s*|\$\s*)?\d+(?:,\d{3})*\.\d{2}"
_DATE_ANCHOR_RE = re.compile(
    r"^\s*(?:DATE|PURCHASE\s+DATE|TRANSACTION\s+DATE)\b\s*[:#-]?\s*"
    r"(?P<body>.*?)\s*$",
    re.IGNORECASE,
)
_TOTAL_ANCHOR_RE = re.compile(
    rf"^\s*(?:GRAND\s+TOTAL|TOTAL)\b\s*[:=]?\s*(?P<amount>{_AMOUNT})\s*$",
    re.IGNORECASE,
)
_ANY_TOTAL_ANCHOR_RE = re.compile(
    r"^\s*(?:GRAND\s+TOTAL|TOTAL)\b", re.IGNORECASE
)
_NON_ITEM_ANCHOR_RE = re.compile(
    r"^\s*(?:DATE|PURCHASE\s+DATE|TRANSACTION\s+DATE|GRAND\s+TOTAL|"
    r"TOTAL|SUB\s*TOTAL|TAX|CHANGE|CASH|TENDERED|BALANCE)\b",
    re.IGNORECASE,
)
_FINANCIAL_SUMMARY_RE = re.compile(
    rf"^\s*(?:DISCOUNT|ROUNDING|VOUCHER|SERVICE\s+CHARGE|SERVICE\s+TAX|"
    rf"GST|SST|PAYMENT\s+TOTAL|AMOUNT\s+PAID)\b"
    rf"\s*[:=]?\s*{_AMOUNT}\s*$",
    re.IGNORECASE,
)
_FULL_ITEM_RE = re.compile(
    rf"^\s*(?P<description>.+?)\s+"
    rf"(?P<quantity>\d+(?:\.\d+)?)\s+[xX×]\s+"
    rf"(?P<unit_price>{_AMOUNT})\s+"
    rf"(?P<line_total>{_AMOUNT})\s*$",
    re.IGNORECASE,
)
_PARTIAL_ITEM_RE = re.compile(
    rf"^\s*(?P<description>.+?)\s+(?P<line_total>{_AMOUNT})\s*$",
    re.IGNORECASE,
)
_AMBIGUOUS_ITEM_RE = re.compile(
    r"^\s*(?P<description>.+?)\s+"
    r"(?P<quantity>\d+(?:\.\d+)?)\s+[xX×]\s+(?P<body>.+?)\s*$",
    re.IGNORECASE,
)
_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_NUMERIC_DATE_RE = re.compile(
    r"(?P<first>\d{1,2})(?P<separator>[/-])(?P<second>\d{1,2})"
    r"(?P=separator)(?P<year>\d{4})"
)
_NAMED_DATE_RE = re.compile(
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|MAY|"
    r"JUN(?:E)?|JUL(?:Y)?|AUG(?:UST)?|SEP(?:TEMBER)?|OCT(?:OBER)?|"
    r"NOV(?:EMBER)?|DEC(?:EMBER)?)\s+"
    r"(?P<year>\d{4})",
    re.IGNORECASE,
)
_MONTHS = {
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


@dataclass(frozen=True, slots=True)
class B1ExtractionResult:
    """Either structured B1 output or the required insufficient-source fallback."""

    receipt_output: ReceiptOutput | None
    pre_resolution_disposition: PreResolutionDisposition | None

    def __post_init__(self) -> None:
        if self.receipt_output is None:
            if (
                self.pre_resolution_disposition is None
                or self.pre_resolution_disposition.state
                is not PolicyState.FALLBACK_NO_UPDATE
            ):
                raise ValueError(
                    "A result without structured output requires FALLBACK_NO_UPDATE."
                )
        elif self.pre_resolution_disposition is not None:
            raise ValueError(
                "B1 does not assign a pre-resolution decision to structured output."
            )


@dataclass(frozen=True, slots=True)
class _Region:
    token: OcrSourceToken
    left: float
    top: float
    right: float
    bottom: float

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2


@dataclass(frozen=True, slots=True)
class _Line:
    text: str
    tokens: tuple[OcrSourceToken, ...]
    spans: tuple[tuple[int, int, str], ...]
    top: float
    left: float
    ambiguous_order: bool

    @property
    def token_ids(self) -> tuple[str, ...]:
        return tuple(token.token_id for token in self.tokens)

    def references_for(self, span: tuple[int, int]) -> tuple[str, ...]:
        start, end = span
        return tuple(
            token_id
            for token_start, token_end, token_id in self.spans
            if token_start < end and token_end > start
        )


def extract_b1(source_evidence: ReceiptSourceEvidence) -> B1ExtractionResult:
    """Map already-gated OCR evidence with the documented B1 rules.

    The recorded source-gate result is consumed directly. No gate callable is
    accepted or invoked by this function.
    """

    if not isinstance(source_evidence, ReceiptSourceEvidence):
        raise TypeError("source_evidence must be ReceiptSourceEvidence.")

    if (
        source_evidence.gate_result.decision
        is SourceEvidenceDecision.INSUFFICIENT
    ):
        return B1ExtractionResult(
            receipt_output=None,
            pre_resolution_disposition=PreResolutionDisposition(
                state=PolicyState.FALLBACK_NO_UPDATE,
                gate_result=source_evidence.gate_result,
            ),
        )

    lines = _reading_order_lines(source_evidence.tokens)
    store_name, store_line = _store_field(source_evidence.receipt_id, lines)
    purchase_date = _date_field(source_evidence.receipt_id, lines)
    receipt_total = _total_field(source_evidence.receipt_id, lines)
    items = _item_rows(source_evidence.receipt_id, lines, store_line)
    extraction_status = _extraction_status(
        store_name, purchase_date, items, receipt_total
    )

    output = ReceiptOutput(
        receipt_id=source_evidence.receipt_id,
        store_name=store_name,
        purchase_date=purchase_date,
        items=items,
        receipt_total=receipt_total,
        source_evidence=source_evidence,
        extraction_status=extraction_status,
        extractor_version=EXTRACTOR_VERSION,
    )
    return B1ExtractionResult(
        receipt_output=output,
        pre_resolution_disposition=None,
    )


def _reading_order_lines(tokens: tuple[OcrSourceToken, ...]) -> tuple[_Line, ...]:
    regions = []
    for token in tokens:
        xs = tuple(point.x for point in token.polygon)
        ys = tuple(point.y for point in token.polygon)
        regions.append(
            _Region(token, min(xs), min(ys), max(xs), max(ys))
        )
    regions.sort(key=lambda region: (region.top, region.left, region.token.token_id))

    groups: list[list[_Region]] = []
    for region in regions:
        if groups and _same_visual_line(groups[-1], region):
            groups[-1].append(region)
        else:
            groups.append([region])

    lines = [_build_line(group) for group in groups]
    lines.sort(key=lambda line: (line.top, line.left, line.token_ids))
    return tuple(lines)


def _same_visual_line(group: list[_Region], candidate: _Region) -> bool:
    top = min(region.top for region in group)
    bottom = max(region.bottom for region in group)
    center = (top + bottom) / 2
    return (
        top <= candidate.center_y <= bottom
        and candidate.top <= center <= candidate.bottom
    )


def _build_line(regions: list[_Region]) -> _Line:
    ordered = sorted(regions, key=lambda region: (region.left, region.token.token_id))
    parts: list[str] = []
    spans: list[tuple[int, int, str]] = []
    cursor = 0
    for region in ordered:
        text = region.token.original_text.strip()
        if parts:
            cursor += 1
        start = cursor
        parts.append(text)
        cursor += len(text)
        spans.append((start, cursor, region.token.token_id))

    ambiguous_order = any(
        first.right > second.left for first, second in zip(ordered, ordered[1:])
    )
    return _Line(
        text=" ".join(parts),
        tokens=tuple(region.token for region in ordered),
        spans=tuple(spans),
        top=min(region.top for region in ordered),
        left=min(region.left for region in ordered),
        ambiguous_order=ambiguous_order,
    )


def _store_field(
    receipt_id: str, lines: tuple[_Line, ...]
) -> tuple[StructuredField, _Line | None]:
    field_id = _field_id(receipt_id, "store-name")
    if not lines:
        return _empty_field(
            field_id,
            receipt_id,
            ReceiptFieldName.STORE_NAME,
            FieldStatus.MISSING,
            "No OCR line is available for a store heading.",
        ), None

    first = lines[0]
    if _is_control_line(first.text) or _item_kind(first.text) is not None:
        return _empty_field(
            field_id,
            receipt_id,
            ReceiptFieldName.STORE_NAME,
            FieldStatus.MISSING,
            "The first reading-order line is not a safe store heading.",
        ), None
    if not any(character.isalpha() for character in first.text):
        return _empty_field(
            field_id,
            receipt_id,
            ReceiptFieldName.STORE_NAME,
            FieldStatus.MISSING,
            "The first reading-order line has no alphabetic heading evidence.",
        ), None
    if first.ambiguous_order:
        return _empty_field(
            field_id,
            receipt_id,
            ReceiptFieldName.STORE_NAME,
            FieldStatus.UNRESOLVED,
            "Overlapping OCR regions make the heading reading order ambiguous.",
            first.token_ids,
        ), first
    return _extracted_field(
        field_id,
        receipt_id,
        ReceiptFieldName.STORE_NAME,
        first.text,
        first.token_ids,
    ), first


def _date_field(receipt_id: str, lines: tuple[_Line, ...]) -> StructuredField:
    field_id = _field_id(receipt_id, "purchase-date")
    candidates = [
        (line, match)
        for line in lines
        if (match := _DATE_ANCHOR_RE.fullmatch(line.text)) is not None
    ]
    if not candidates:
        return _empty_field(
            field_id,
            receipt_id,
            ReceiptFieldName.PURCHASE_DATE,
            FieldStatus.MISSING,
            "No supported DATE-like anchored value was observed.",
        )
    if len(candidates) != 1:
        return _empty_field(
            field_id,
            receipt_id,
            ReceiptFieldName.PURCHASE_DATE,
            FieldStatus.UNRESOLVED,
            "Multiple DATE-like anchored values were observed.",
            _unique_ids(line for line, _ in candidates),
        )

    line, match = candidates[0]
    references = line.references_for(match.span("body")) or line.token_ids
    if line.ambiguous_order:
        return _empty_field(
            field_id,
            receipt_id,
            ReceiptFieldName.PURCHASE_DATE,
            FieldStatus.UNRESOLVED,
            "Overlapping OCR regions make the date reading order ambiguous.",
            line.token_ids,
        )

    value = match.group("body")
    date_state = _date_state(value)
    if date_state == "valid":
        return _extracted_field(
            field_id,
            receipt_id,
            ReceiptFieldName.PURCHASE_DATE,
            value,
            references,
        )
    reason = (
        "The anchored numeric date is ambiguous between day-first and month-first."
        if date_state == "ambiguous"
        else "The anchored value is not a valid supported date without repair."
    )
    return _empty_field(
        field_id,
        receipt_id,
        ReceiptFieldName.PURCHASE_DATE,
        FieldStatus.UNRESOLVED,
        reason,
        line.token_ids,
    )


def _date_state(value: str) -> str:
    if _ISO_DATE_RE.fullmatch(value):
        year, month, day = (int(part) for part in value.split("-"))
        return "valid" if _valid_date(year, month, day) else "invalid"

    numeric = _NUMERIC_DATE_RE.fullmatch(value)
    if numeric is not None:
        first = int(numeric.group("first"))
        second = int(numeric.group("second"))
        year = int(numeric.group("year"))
        day_first = _valid_date(year, second, first)
        month_first = _valid_date(year, first, second)
        if day_first and month_first and first != second:
            return "ambiguous"
        return "valid" if day_first or month_first else "invalid"

    named = _NAMED_DATE_RE.fullmatch(value)
    if named is not None:
        month = _MONTHS[named.group("month")[:3].upper()]
        return (
            "valid"
            if _valid_date(int(named.group("year")), month, int(named.group("day")))
            else "invalid"
        )
    return "invalid"


def _valid_date(year: int, month: int, day: int) -> bool:
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


def _total_field(receipt_id: str, lines: tuple[_Line, ...]) -> StructuredField:
    field_id = _field_id(receipt_id, "receipt-total")
    anchored = [line for line in lines if _ANY_TOTAL_ANCHOR_RE.match(line.text)]
    if not anchored:
        return _empty_field(
            field_id,
            receipt_id,
            ReceiptFieldName.RECEIPT_TOTAL,
            FieldStatus.MISSING,
            "No explicit TOTAL or GRAND TOTAL anchor was observed.",
        )
    if len(anchored) != 1:
        return _empty_field(
            field_id,
            receipt_id,
            ReceiptFieldName.RECEIPT_TOTAL,
            FieldStatus.UNRESOLVED,
            "Multiple explicit receipt-total candidates were observed.",
            _unique_ids(anchored),
        )

    line = anchored[0]
    match = _TOTAL_ANCHOR_RE.fullmatch(line.text)
    if line.ambiguous_order or match is None:
        return _empty_field(
            field_id,
            receipt_id,
            ReceiptFieldName.RECEIPT_TOTAL,
            FieldStatus.UNRESOLVED,
            "The explicit total line does not contain one safely associated amount.",
            line.token_ids,
        )
    return _extracted_field(
        field_id,
        receipt_id,
        ReceiptFieldName.RECEIPT_TOTAL,
        match.group("amount"),
        line.references_for(match.span("amount")) or line.token_ids,
    )


def _item_rows(
    receipt_id: str,
    lines: tuple[_Line, ...],
    store_line: _Line | None,
) -> tuple[ReceiptItemRow, ...]:
    rows: list[ReceiptItemRow] = []
    for line in lines:
        if line is store_line or _is_control_line(line.text) or line.ambiguous_order:
            continue
        kind = _item_kind(line.text)
        if kind is None:
            continue
        row_id = f"{receipt_id}:b1:row:{len(rows):06d}"
        rows.append(_item_row(receipt_id, row_id, line, kind))
    return tuple(rows)


def _item_kind(text: str) -> str | None:
    full = _FULL_ITEM_RE.fullmatch(text)
    if full is not None and _valid_description(full.group("description")):
        return "full"

    ambiguous = _AMBIGUOUS_ITEM_RE.fullmatch(text)
    if ambiguous is not None and _valid_description(ambiguous.group("description")):
        return "ambiguous"

    partial = _PARTIAL_ITEM_RE.fullmatch(text)
    if partial is not None:
        description = partial.group("description")
        if (
            _valid_description(description)
            and re.search(r"(?:^|\s)[xX](?:\s|$)|×", description) is None
        ):
            return "partial"
    return None


def _valid_description(value: str) -> bool:
    return any(character.isalpha() for character in value)


def _item_row(
    receipt_id: str, row_id: str, line: _Line, kind: str
) -> ReceiptItemRow:
    names = {
        "description": ReceiptFieldName.ITEM_DESCRIPTION,
        "quantity": ReceiptFieldName.QUANTITY,
        "unit-price": ReceiptFieldName.UNIT_PRICE,
        "line-total": ReceiptFieldName.LINE_TOTAL,
    }
    if kind == "full":
        match = _FULL_ITEM_RE.fullmatch(line.text)
        assert match is not None
        fields = {
            "description": _matched_item_field(
                receipt_id, row_id, names["description"], "description", match, line
            ),
            "quantity": _matched_item_field(
                receipt_id, row_id, names["quantity"], "quantity", match, line
            ),
            "unit-price": _matched_item_field(
                receipt_id, row_id, names["unit-price"], "unit_price", match, line
            ),
            "line-total": _matched_item_field(
                receipt_id, row_id, names["line-total"], "line_total", match, line
            ),
        }
    elif kind == "partial":
        match = _PARTIAL_ITEM_RE.fullmatch(line.text)
        assert match is not None
        fields = {
            "description": _matched_item_field(
                receipt_id, row_id, names["description"], "description", match, line
            ),
            "quantity": _item_empty_field(
                receipt_id,
                row_id,
                names["quantity"],
                "No explicit quantity was observed on the detected item row.",
            ),
            "unit-price": _item_empty_field(
                receipt_id,
                row_id,
                names["unit-price"],
                "No explicit unit price was observed on the detected item row.",
            ),
            "line-total": _matched_item_field(
                receipt_id, row_id, names["line-total"], "line_total", match, line
            ),
        }
    else:
        match = _AMBIGUOUS_ITEM_RE.fullmatch(line.text)
        assert match is not None
        body_references = line.references_for(match.span("body")) or line.token_ids
        fields = {
            "description": _matched_item_field(
                receipt_id, row_id, names["description"], "description", match, line
            ),
            "quantity": _matched_item_field(
                receipt_id, row_id, names["quantity"], "quantity", match, line
            ),
            "unit-price": _item_empty_field(
                receipt_id,
                row_id,
                names["unit-price"],
                "The observed amounts cannot be safely associated with unit price.",
                FieldStatus.UNRESOLVED,
                body_references,
            ),
            "line-total": _item_empty_field(
                receipt_id,
                row_id,
                names["line-total"],
                "The observed amounts cannot be safely associated with line total.",
                FieldStatus.UNRESOLVED,
                body_references,
            ),
        }

    return ReceiptItemRow(
        row_id=row_id,
        receipt_id=receipt_id,
        description=fields["description"],
        quantity=fields["quantity"],
        unit_price=fields["unit-price"],
        line_total=fields["line-total"],
    )


def _matched_item_field(
    receipt_id: str,
    row_id: str,
    field_name: ReceiptFieldName,
    group_name: str,
    match: re.Match[str],
    line: _Line,
) -> StructuredField:
    return _extracted_field(
        _item_field_id(row_id, field_name),
        receipt_id,
        field_name,
        match.group(group_name).strip(),
        line.references_for(match.span(group_name)) or line.token_ids,
        row_id,
    )


def _item_empty_field(
    receipt_id: str,
    row_id: str,
    field_name: ReceiptFieldName,
    reason: str,
    status: FieldStatus = FieldStatus.MISSING,
    source_token_ids: tuple[str, ...] = (),
) -> StructuredField:
    return _empty_field(
        _item_field_id(row_id, field_name),
        receipt_id,
        field_name,
        status,
        reason,
        source_token_ids,
        row_id,
    )


def _extraction_status(
    store_name: StructuredField,
    purchase_date: StructuredField,
    items: tuple[ReceiptItemRow, ...],
    receipt_total: StructuredField,
) -> ReceiptExtractionStatus:
    fields = [store_name, purchase_date, receipt_total]
    fields.extend(field for item in items for field in item.fields)
    extracted_count = sum(field.status is FieldStatus.EXTRACTED for field in fields)
    if not extracted_count:
        return ReceiptExtractionStatus.FAILED
    if items and all(field.status is FieldStatus.EXTRACTED for field in fields):
        return ReceiptExtractionStatus.EXTRACTED
    return ReceiptExtractionStatus.PARTIAL


def _is_control_line(text: str) -> bool:
    return (
        _NON_ITEM_ANCHOR_RE.match(text) is not None
        or _FINANCIAL_SUMMARY_RE.fullmatch(text) is not None
    )


def _unique_ids(lines: Iterable[_Line]) -> tuple[str, ...]:
    ordered: list[str] = []
    for line in lines:
        for token_id in line.token_ids:
            if token_id not in ordered:
                ordered.append(token_id)
    return tuple(ordered)


def _field_id(receipt_id: str, suffix: str) -> str:
    return f"{receipt_id}:b1:{suffix}"


def _item_field_id(row_id: str, field_name: ReceiptFieldName) -> str:
    return f"{row_id}:{field_name.value.lower().replace('_', '-')}"


def _extracted_field(
    field_id: str,
    receipt_id: str,
    field_name: ReceiptFieldName,
    value: str,
    source_token_ids: tuple[str, ...],
    item_row_id: str | None = None,
) -> StructuredField:
    return StructuredField(
        field_id=field_id,
        receipt_id=receipt_id,
        field_name=field_name,
        status=FieldStatus.EXTRACTED,
        value=value,
        item_row_id=item_row_id,
        source_token_ids=source_token_ids,
        confidence=None,
    )


def _empty_field(
    field_id: str,
    receipt_id: str,
    field_name: ReceiptFieldName,
    status: FieldStatus,
    reason: str,
    source_token_ids: tuple[str, ...] = (),
    item_row_id: str | None = None,
) -> StructuredField:
    return StructuredField(
        field_id=field_id,
        receipt_id=receipt_id,
        field_name=field_name,
        status=status,
        item_row_id=item_row_id,
        source_token_ids=source_token_ids,
        unresolved_reason=reason,
    )
