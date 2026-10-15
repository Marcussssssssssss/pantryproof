"""Thesis-conformant deterministic B1 receipt extractor (provisional V1).

Consumes Contract V0 source evidence after its recorded source gate. It uses
only frozen generic grammars and simple token geometry; it does not perform
OCR, correction, calibration, review, persistence, or B2 layout inference.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from math import isfinite

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


EXTRACTOR_VERSION = "B1-deterministic-v1"
B1_STORE_HEADER_MAX_NORMALIZED_Y = 0.25
B1_LINE_CLUSTER_TOLERANCE_HEIGHTS = 0.50
B1_GEOMETRY_EPSILON = 1e-9

_AMOUNT = r"(?:RM\s*|MYR\s*|\$\s*)?\d+(?:,\d{3})*\.\d{2}"
_AMOUNT_SEQUENCE = rf"{_AMOUNT}(?:\s+{_AMOUNT})*"
_QUANTITY = r"\d+(?:\.\d+)?"
_AMOUNT_RE = re.compile(_AMOUNT, re.IGNORECASE)
_FULL_AMOUNT_RE = re.compile(rf"^\s*{_AMOUNT}\s*$", re.IGNORECASE)
_DATE_ANCHOR_RE = re.compile(
    r"^\s*(?:DATE|PURCHASE\s+DATE|TRANSACTION\s+DATE)\b\s*[:#-]?\s*"
    r"(?P<body>.*?)\s*$", re.IGNORECASE,
)
_STANDALONE_DATE_RE = re.compile(
    r"^\s*(?:\d{4}-\d{1,2}-\d{1,2}|"
    r"\d{1,2}(?P<numeric_separator>[/-])\d{1,2}"
    r"(?P=numeric_separator)\d{4}|"
    r"\d{1,2}\s+(?:JAN(?:UARY)?|FEB(?:RUARY)?|MAR(?:CH)?|APR(?:IL)?|"
    r"MAY|JUN(?:E)?|JUL(?:Y)?|AUG(?:UST)?|SEP(?:TEMBER)?|OCT(?:OBER)?|"
    r"NOV(?:EMBER)?|DEC(?:EMBER)?)\s+\d{4})\s*$", re.IGNORECASE,
)
_TOTAL_PREFIX_RE = re.compile(r"^\s*(?:GRAND\s+TOTAL|TOTAL)\b", re.IGNORECASE)
_TOTAL_VALID_RE = re.compile(
    rf"^\s*(?:GRAND\s+TOTAL|TOTAL)\b\s*[:=]?\s*(?P<amounts>{_AMOUNT_SEQUENCE})\s*$",
    re.IGNORECASE,
)
_NON_ITEM_ANCHOR_RE = re.compile(
    r"^\s*(?:DATE|PURCHASE\s+DATE|TRANSACTION\s+DATE|GRAND\s+TOTAL|"
    r"TOTAL|SUB\s*TOTAL|TAX|CHANGE|CASH|TENDERED|BALANCE)\b", re.IGNORECASE,
)
_FINANCIAL_SUMMARY_RE = re.compile(
    r"^\s*(?:DISCOUNT|ROUNDING|VOUCHER|SERVICE\s+CHARGE|GST|SST|"
    r"SERVICE\s+TAX|PAYMENT\s+TOTAL|AMOUNT\s+PAID)\b"
    r"(?:\s*[:=]?\s*" + _AMOUNT + r")?\s*$",
    re.IGNORECASE,
)
_MULTIPLIER_ITEM_RE = re.compile(
    rf"^\s*(?P<description>.+?\D)\s+(?P<quantity>{_QUANTITY})\s*[x×]\s*"
    rf"(?P<body>{_AMOUNT_SEQUENCE})\s*$", re.IGNORECASE,
)
_LABELED_QUANTITY_ITEM_RE = re.compile(
    rf"^\s*(?P<description>.+?\D)\s+(?:QTY|QUANTITY)\s*[:=]?\s*"
    rf"(?P<quantity>{_QUANTITY})\s+(?P<body>{_AMOUNT_SEQUENCE})\s*$",
    re.IGNORECASE,
)
_UNMARKED_QUANTITY_ITEM_RE = re.compile(
    rf"^\s*(?P<description>.+?\D)\s+(?P<quantity>{_QUANTITY})\s+"
    rf"(?P<body>{_AMOUNT_SEQUENCE})\s*$", re.IGNORECASE,
)
_PARTIAL_ITEM_RE = re.compile(
    rf"^\s*(?P<description>.+?)\s+(?P<body>{_AMOUNT_SEQUENCE})\s*$",
    re.IGNORECASE,
)

_MONTHS = {
    "JAN": 1, "JANUARY": 1, "FEB": 2, "FEBRUARY": 2,
    "MAR": 3, "MARCH": 3, "APR": 4, "APRIL": 4, "MAY": 5,
    "JUN": 6, "JUNE": 6, "JUL": 7, "JULY": 7, "AUG": 8,
    "AUGUST": 8, "SEP": 9, "SEPTEMBER": 9, "OCT": 10,
    "OCTOBER": 10, "NOV": 11, "NOVEMBER": 11, "DEC": 12,
    "DECEMBER": 12,
}


@dataclass(frozen=True, slots=True)
class B1ExtractionResult:
    receipt_output: ReceiptOutput | None
    pre_resolution_disposition: PreResolutionDisposition | None

    def __post_init__(self) -> None:
        if self.receipt_output is None:
            if (
                self.pre_resolution_disposition is None
                or self.pre_resolution_disposition.state is not PolicyState.FALLBACK_NO_UPDATE
            ):
                raise ValueError("a result without output requires FALLBACK_NO_UPDATE")
        elif self.pre_resolution_disposition is not None:
            raise ValueError("structured B1 output has no pre-resolution disposition")


@dataclass(frozen=True, slots=True)
class _Region:
    token: OcrSourceToken
    left: float
    top: float
    right: float
    bottom: float

    @property
    def center_x(self) -> float: return (self.left + self.right) / 2.0
    @property
    def center_y(self) -> float: return (self.top + self.bottom) / 2.0
    @property
    def height(self) -> float: return self.bottom - self.top


@dataclass(slots=True)
class _LineGroup:
    anchor: _Region
    regions: list[_Region] = field(default_factory=list)
    ambiguous: bool = False

    def __post_init__(self) -> None:
        if not self.regions:
            self.regions.append(self.anchor)


@dataclass(frozen=True, slots=True)
class _Line:
    index: int
    regions: tuple[_Region, ...]
    text: str
    spans: tuple[tuple[int, int, _Region], ...]
    top: float
    bottom: float
    center_y: float
    normalized_center_y: float
    ambiguous_cluster: bool
    overlapping_order: bool

    @property
    def token_ids(self) -> tuple[str, ...]:
        return tuple(region.token.token_id for region in self.regions)

    def refs_for_span(self, start: int, end: int) -> tuple[str, ...]:
        refs = {
            region.token.token_id for span_start, span_end, region in self.spans
            if span_start < end and start < span_end
        }
        return tuple(sorted(refs))

    def right_for(self, references: tuple[str, ...]) -> float:
        return max(r.right for r in self.regions if r.token.token_id in references)


@dataclass(frozen=True, slots=True)
class _ItemSyntax:
    description: str
    description_span: tuple[int, int]
    quantity: str | None
    quantity_span: tuple[int, int] | None
    money_span: tuple[int, int]
    quantity_schema: bool


@dataclass(frozen=True, slots=True)
class _MoneyCandidate:
    value: str
    references: tuple[str, ...]
    right: float
    text_start: int


@dataclass(frozen=True, slots=True)
class _DateCandidate:
    line: _Line
    observed: str
    references: tuple[str, ...]
    state: str
    canonical: str | None


def extract_b1(source_evidence: ReceiptSourceEvidence) -> B1ExtractionResult:
    """Apply B1 to an already-recorded source-gate result."""
    gate = source_evidence.gate_result
    if gate.decision is SourceEvidenceDecision.INSUFFICIENT:
        return B1ExtractionResult(
            receipt_output=None,
            pre_resolution_disposition=PreResolutionDisposition(
                gate_result=gate,
                state=PolicyState.FALLBACK_NO_UPDATE,
            ),
        )

    lines = _reading_order_lines(source_evidence.tokens)
    store = _extract_store(source_evidence.receipt_id, lines)
    items, item_line_indices = _extract_items(
        source_evidence.receipt_id, lines, store.source_token_ids
    )
    purchase_date = _extract_date(source_evidence.receipt_id, lines, item_line_indices)
    receipt_total = _extract_total(source_evidence.receipt_id, lines)
    extraction_status = _extraction_status(store, purchase_date, items, receipt_total)
    receipt = ReceiptOutput(
        receipt_id=source_evidence.receipt_id,
        store_name=store,
        purchase_date=purchase_date,
        items=tuple(items),
        receipt_total=receipt_total,
        source_evidence=source_evidence,
        extraction_status=extraction_status,
        extractor_version=EXTRACTOR_VERSION,
    )
    return B1ExtractionResult(
        receipt_output=receipt,
        pre_resolution_disposition=None,
    )


def _region(token: OcrSourceToken) -> _Region | None:
    xs = [point.x for point in token.polygon]
    ys = [point.y for point in token.polygon]
    if not all(isfinite(value) for value in (*xs, *ys)):
        return None
    left, right, top, bottom = min(xs), max(xs), min(ys), max(ys)
    if right - left <= B1_GEOMETRY_EPSILON or bottom - top <= B1_GEOMETRY_EPSILON:
        return None
    return _Region(token, left, top, right, bottom)


def _same_visual_line(left: _Region, right: _Region) -> bool:
    """Fixed overlap/centroid-gap test, normalized by the shorter height."""
    shorter = min(left.height, right.height)
    overlap = max(0.0, min(left.bottom, right.bottom) - max(left.top, right.top))
    overlap_ratio = overlap / shorter
    center_gap = abs(left.center_y - right.center_y) / shorter
    tolerance = B1_LINE_CLUSTER_TOLERANCE_HEIGHTS
    return (
        overlap_ratio + B1_GEOMETRY_EPSILON >= 1.0 - tolerance
        and center_gap <= tolerance + B1_GEOMETRY_EPSILON
    )


def _reading_order_lines(tokens: Iterable[OcrSourceToken]) -> tuple[_Line, ...]:
    regions: list[_Region] = []
    for token in tokens:
        if not token.original_text.strip():
            continue
        candidate = _region(token)
        if candidate is not None:
            regions.append(candidate)
    if not regions:
        return ()

    envelope_top = min(region.top for region in regions)
    envelope_bottom = max(region.bottom for region in regions)
    envelope_height = envelope_bottom - envelope_top
    regions.sort(key=lambda r: (r.center_y, r.center_x, r.token.token_id))

    groups: list[_LineGroup] = []
    for region in regions:
        matches = [group for group in groups if _same_visual_line(group.anchor, region)]
        if len(matches) == 1:
            matches[0].regions.append(region)
        elif len(matches) > 1:
            for group in matches:
                group.ambiguous = True
            groups.append(_LineGroup(region, ambiguous=True))
        else:
            groups.append(_LineGroup(region))

    # A bridge token compatible with multiple fixed anchors makes every
    # affected cluster unsafe even if stable iteration attached it earlier.
    for region in regions:
        compatible = [group for group in groups if _same_visual_line(group.anchor, region)]
        if len(compatible) > 1:
            for group in compatible:
                group.ambiguous = True

    groups.sort(key=lambda g: (g.anchor.center_y, g.anchor.left, g.anchor.token.token_id))
    return tuple(
        _build_line(index, group, envelope_top, envelope_height)
        for index, group in enumerate(groups)
    )


def _build_line(
    index: int,
    group: _LineGroup,
    envelope_top: float,
    envelope_height: float,
) -> _Line:
    regions = sorted(group.regions, key=lambda r: (r.left, r.center_x, r.token.token_id))
    parts: list[str] = []
    spans: list[tuple[int, int, _Region]] = []
    cursor = 0
    for region in regions:
        if parts:
            cursor += 1
        text = region.token.original_text.strip()
        parts.append(text)
        spans.append((cursor, cursor + len(text), region))
        cursor += len(text)
    overlapping_order = any(
        current.left < previous.right - B1_GEOMETRY_EPSILON
        for previous, current in zip(regions, regions[1:])
    )
    top = min(region.top for region in regions)
    bottom = max(region.bottom for region in regions)
    center_y = sum(region.center_y for region in regions) / len(regions)
    normalized = (center_y - envelope_top) / envelope_height
    return _Line(
        index=index,
        regions=tuple(regions),
        text=" ".join(parts),
        spans=tuple(spans),
        top=top,
        bottom=bottom,
        center_y=center_y,
        normalized_center_y=normalized,
        ambiguous_cluster=group.ambiguous,
        overlapping_order=overlapping_order,
    )


def _field(
    receipt_id: str,
    name: ReceiptFieldName,
    status: FieldStatus,
    value: str | None = None,
    references: tuple[str, ...] = (),
    item_row_id: str | None = None,
    reason: str | None = None,
) -> StructuredField:
    field_id = (
        f"{item_row_id}:{name.value.lower().replace('_', '-')}"
        if item_row_id is not None
        else f"{receipt_id}:b1:{name.value.lower().replace('_', '-')}"
    )
    return StructuredField(
        field_id=field_id,
        receipt_id=receipt_id,
        field_name=name,
        status=status,
        value=value,
        item_row_id=item_row_id,
        source_token_ids=references,
        confidence=None,
        unresolved_reason=(
            None if status is FieldStatus.EXTRACTED
            else reason
            or (
                "not observed by B1"
                if status is FieldStatus.MISSING
                else "unsafe or conflicting B1 evidence"
            )
        ),
    )


def _is_control_line(text: str) -> bool:
    return bool(
        _NON_ITEM_ANCHOR_RE.match(text)
        or _FINANCIAL_SUMMARY_RE.fullmatch(text)
        or _STANDALONE_DATE_RE.fullmatch(text)
    )


def _extract_store(receipt_id: str, lines: tuple[_Line, ...]) -> StructuredField:
    ambiguous_refs: set[str] = set()
    for line in lines:
        if line.normalized_center_y > B1_STORE_HEADER_MAX_NORMALIZED_Y + B1_GEOMETRY_EPSILON:
            continue
        text = line.text.strip()
        if not text or not any(character.isalpha() for character in text):
            continue
        if _is_control_line(text) or _item_syntax(text) is not None:
            continue
        if line.ambiguous_cluster or line.overlapping_order:
            ambiguous_refs.update(line.token_ids)
            return _field(
                receipt_id,
                ReceiptFieldName.STORE_NAME,
                FieldStatus.UNRESOLVED,
                references=tuple(sorted(ambiguous_refs)),
            )
        return _field(
            receipt_id,
            ReceiptFieldName.STORE_NAME,
            FieldStatus.EXTRACTED,
            text,
            line.token_ids,
        )
    if ambiguous_refs:
        return _field(
            receipt_id,
            ReceiptFieldName.STORE_NAME,
            FieldStatus.UNRESOLVED,
            references=tuple(sorted(ambiguous_refs)),
        )
    return _field(receipt_id, ReceiptFieldName.STORE_NAME, FieldStatus.MISSING)


def _extract_date(
    receipt_id: str,
    lines: tuple[_Line, ...],
    item_line_indices: frozenset[int],
) -> StructuredField:
    candidates: list[_DateCandidate] = []
    for line in lines:
        if line.index in item_line_indices:
            continue
        anchor = _DATE_ANCHOR_RE.fullmatch(line.text)
        standalone = _STANDALONE_DATE_RE.fullmatch(line.text)
        if anchor:
            body = anchor.group("body").strip()
            start, end = anchor.span("body")
        elif standalone:
            body = standalone.group(0).strip()
            start, end = standalone.span(0)
        else:
            continue
        state, canonical = _parse_date(body)
        candidates.append(
            _DateCandidate(
                line=line,
                observed=body,
                references=line.refs_for_span(start, end) or line.token_ids,
                state=state,
                canonical=canonical,
            )
        )

    if not candidates:
        return _field(receipt_id, ReceiptFieldName.PURCHASE_DATE, FieldStatus.MISSING)
    all_refs = tuple(sorted({ref for candidate in candidates for ref in candidate.references}))
    if any(
        candidate.state != "VALID"
        or candidate.line.ambiguous_cluster
        or candidate.line.overlapping_order
        for candidate in candidates
    ):
        return _field(
            receipt_id,
            ReceiptFieldName.PURCHASE_DATE,
            FieldStatus.UNRESOLVED,
            references=all_refs,
        )
    canonicals = {candidate.canonical for candidate in candidates}
    if len(canonicals) != 1:
        return _field(
            receipt_id,
            ReceiptFieldName.PURCHASE_DATE,
            FieldStatus.UNRESOLVED,
            references=all_refs,
        )
    chosen = candidates[0]
    return _field(
        receipt_id,
        ReceiptFieldName.PURCHASE_DATE,
        FieldStatus.EXTRACTED,
        chosen.canonical,
        chosen.references,
    )


def _parse_date(value: str) -> tuple[str, str | None]:
    value = value.strip()
    iso = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", value)
    if iso:
        return _validated_date(int(iso[1]), int(iso[2]), int(iso[3]))
    numeric = re.fullmatch(
        r"(?P<first>\d{1,2})(?P<separator>[/-])(?P<second>\d{1,2})"
        r"(?P=separator)(?P<year>\d{4})",
        value,
    )
    if numeric:
        first = int(numeric.group("first"))
        second = int(numeric.group("second"))
        year = int(numeric.group("year"))
        day_first = _calendar_date(year, second, first)
        month_first = _calendar_date(year, first, second)
        valid_dates = {candidate for candidate in (day_first, month_first) if candidate}
        if not valid_dates:
            return "INVALID", None
        if len(valid_dates) == 1:
            return "VALID", next(iter(valid_dates)).isoformat()
        return "AMBIGUOUS", None
    named = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", value)
    if named:
        month = _MONTHS.get(named[2].upper())
        if month is None:
            return "INVALID", None
        return _validated_date(int(named[3]), month, int(named[1]))
    return "INVALID", None


def _validated_date(year: int, month: int, day: int) -> tuple[str, str | None]:
    parsed = _calendar_date(year, month, day)
    if parsed is None:
        return "INVALID", None
    return "VALID", parsed.isoformat()


def _calendar_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _extract_total(receipt_id: str, lines: tuple[_Line, ...]) -> StructuredField:
    anchors = [line for line in lines if _TOTAL_PREFIX_RE.match(line.text)]
    if not anchors:
        return _field(receipt_id, ReceiptFieldName.RECEIPT_TOTAL, FieldStatus.MISSING)

    valid: list[tuple[_Line, _MoneyCandidate]] = []
    unsafe_by_index: dict[int, tuple[str, ...]] = {}
    for line in anchors:
        match = _TOTAL_VALID_RE.fullmatch(line.text)
        if not match:
            continue  # malformed anchors do not override a valid occurrence
        amounts = _money_candidates(line, match.span("amounts"))
        selected, tied_refs = _rightmost_money(amounts)
        if line.ambiguous_cluster or line.overlapping_order or selected is None:
            refs = tied_refs or line.token_ids
            unsafe_by_index[line.index] = tuple(sorted(set(refs)))
        else:
            valid.append((line, selected))

    if not valid:
        refs = tuple(sorted({ref for line in anchors for ref in line.token_ids}))
        return _field(
            receipt_id,
            ReceiptFieldName.RECEIPT_TOTAL,
            FieldStatus.UNRESOLVED,
            references=refs,
        )

    chosen_line, chosen = valid[-1]
    later_unsafe = {
        ref
        for index, refs in unsafe_by_index.items()
        if index >= chosen_line.index
        for ref in refs
    }
    if later_unsafe:
        later_unsafe.update(chosen.references)
        return _field(
            receipt_id,
            ReceiptFieldName.RECEIPT_TOTAL,
            FieldStatus.UNRESOLVED,
            references=tuple(sorted(later_unsafe)),
        )
    return _field(
        receipt_id,
        ReceiptFieldName.RECEIPT_TOTAL,
        FieldStatus.EXTRACTED,
        chosen.value,
        chosen.references,
    )


def _extract_items(
    receipt_id: str,
    lines: tuple[_Line, ...],
    store_refs: tuple[str, ...],
) -> tuple[list[ReceiptItemRow], frozenset[int]]:
    rows: list[ReceiptItemRow] = []
    item_indices: set[int] = set()
    store_set = set(store_refs)
    for line in lines:
        if store_set and store_set == set(line.token_ids):
            continue
        if _is_control_line(line.text):
            continue
        syntax = _item_syntax(line.text)
        if syntax is None:
            continue
        item_indices.add(line.index)
        if line.ambiguous_cluster or _unsafe_nonmonetary_overlap(line):
            continue
        row = _item_row(receipt_id, line, syntax, len(rows))
        if row is not None:
            rows.append(row)
    return rows, frozenset(item_indices)


def _item_syntax(text: str) -> _ItemSyntax | None:
    if _is_control_without_item_recursion(text):
        return None
    for pattern, quantity_schema in (
        (_MULTIPLIER_ITEM_RE, True),
        (_LABELED_QUANTITY_ITEM_RE, True),
        (_UNMARKED_QUANTITY_ITEM_RE, True),
        (_PARTIAL_ITEM_RE, False),
    ):
        match = pattern.fullmatch(text)
        if not match:
            continue
        description = match.group("description").strip()
        if not description or not any(character.isalpha() for character in description):
            continue
        raw_description = match.group("description")
        description_start = (
            match.start("description")
            + len(raw_description)
            - len(raw_description.lstrip())
        )
        description_end = description_start + len(description)
        quantity = match.groupdict().get("quantity")
        quantity_span = match.span("quantity") if quantity is not None else None
        return _ItemSyntax(
            description=description,
            description_span=(description_start, description_end),
            quantity=quantity,
            quantity_span=quantity_span,
            money_span=match.span("body"),
            quantity_schema=quantity_schema,
        )
    return None


def _is_control_without_item_recursion(text: str) -> bool:
    return bool(
        _NON_ITEM_ANCHOR_RE.match(text)
        or _FINANCIAL_SUMMARY_RE.fullmatch(text)
        or _STANDALONE_DATE_RE.fullmatch(text)
    )


def _item_row(
    receipt_id: str, line: _Line, syntax: _ItemSyntax, row_number: int
) -> ReceiptItemRow | None:
    row_id = f"{receipt_id}:b1:item-{row_number + 1}"
    description_refs = line.refs_for_span(*syntax.description_span)
    if not description_refs:
        return None
    amounts = _money_candidates(line, syntax.money_span)
    line_total, tied_refs = _rightmost_money(amounts)
    if line_total is None:
        line_total_field = _field(
            receipt_id,
            ReceiptFieldName.LINE_TOTAL,
            FieldStatus.UNRESOLVED,
            references=tied_refs
            or tuple(sorted({r for amount in amounts for r in amount.references})),
            item_row_id=row_id,
        )
        unit_candidates = amounts
    else:
        line_total_field = _field(
            receipt_id,
            ReceiptFieldName.LINE_TOTAL,
            FieldStatus.EXTRACTED,
            line_total.value,
            line_total.references,
            row_id,
        )
        unit_candidates = [amount for amount in amounts if amount is not line_total]

    quantity_field = (
        _field(
            receipt_id,
            ReceiptFieldName.QUANTITY,
            FieldStatus.EXTRACTED,
            syntax.quantity,
            line.refs_for_span(*syntax.quantity_span),
            row_id,
        )
        if syntax.quantity is not None and syntax.quantity_span is not None
        else _field(
            receipt_id,
            ReceiptFieldName.QUANTITY,
            FieldStatus.MISSING,
            item_row_id=row_id,
        )
    )

    if not unit_candidates:
        unit_price = _field(
            receipt_id,
            ReceiptFieldName.UNIT_PRICE,
            FieldStatus.MISSING,
            item_row_id=row_id,
        )
    elif syntax.quantity_schema and len(unit_candidates) == 1 and line_total is not None:
        candidate = unit_candidates[0]
        unit_price = _field(
            receipt_id,
            ReceiptFieldName.UNIT_PRICE,
            FieldStatus.EXTRACTED,
            candidate.value,
            candidate.references,
            row_id,
        )
    else:
        unit_price = _field(
            receipt_id,
            ReceiptFieldName.UNIT_PRICE,
            FieldStatus.UNRESOLVED,
            references=tuple(sorted({r for amount in unit_candidates for r in amount.references})),
            item_row_id=row_id,
        )

    return ReceiptItemRow(
        row_id=row_id,
        receipt_id=receipt_id,
        description=_field(
            receipt_id,
            ReceiptFieldName.ITEM_DESCRIPTION,
            FieldStatus.EXTRACTED,
            syntax.description,
            description_refs,
            row_id,
        ),
        quantity=quantity_field,
        unit_price=unit_price,
        line_total=line_total_field,
    )


def _money_candidates(line: _Line, span: tuple[int, int]) -> list[_MoneyCandidate]:
    start, end = span
    candidates: list[_MoneyCandidate] = []
    for match in _AMOUNT_RE.finditer(line.text, start, end):
        references = line.refs_for_span(match.start(), match.end())
        if not references:
            continue
        candidates.append(
            _MoneyCandidate(
                value=match.group(0).strip(),
                references=references,
                right=line.right_for(references),
                text_start=match.start(),
            )
        )
    return candidates


def _rightmost_money(
    candidates: list[_MoneyCandidate],
) -> tuple[_MoneyCandidate | None, tuple[str, ...]]:
    if not candidates:
        return None, ()
    max_right = max(candidate.right for candidate in candidates)
    tied = [
        candidate for candidate in candidates
        if abs(candidate.right - max_right) <= B1_GEOMETRY_EPSILON
    ]
    if len(tied) == 1:
        return tied[0], ()
    reference_sets = {candidate.references for candidate in tied}
    if len(reference_sets) == 1 and len(next(iter(reference_sets))) == 1:
        return max(tied, key=lambda candidate: candidate.text_start), ()
    references = tuple(sorted({ref for candidate in tied for ref in candidate.references}))
    return None, references


def _unsafe_nonmonetary_overlap(line: _Line) -> bool:
    if not line.overlapping_order:
        return False
    regions = line.regions
    for previous, current in zip(regions, regions[1:]):
        if current.left >= previous.right - B1_GEOMETRY_EPSILON:
            continue
        if not (
            _FULL_AMOUNT_RE.fullmatch(previous.token.original_text)
            and _FULL_AMOUNT_RE.fullmatch(current.token.original_text)
        ):
            return True
    return False


def _extraction_status(
    store_name: StructuredField,
    purchase_date: StructuredField,
    items: list[ReceiptItemRow],
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
