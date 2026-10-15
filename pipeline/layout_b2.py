"""Deterministic layout-aware B2 receipt extraction for Contract Version 0.

The extractor consumes immutable, already-gated OCR evidence.  It builds an
internal geometry graph, but it never mutates or replaces the source OCR
tokens.  B2 deliberately does not perform correction, calibration, review,
retailer matching, arithmetic inference, or inventory persistence.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from math import isfinite
from statistics import median

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


EXTRACTOR_VERSION = "B2-layout-graph-v0"

# Provisional V0 geometry constants.  Equality is accepted for every maximum
# or minimum boundary below; only horizontal overlap strictly above its limit
# is ambiguous.
LINE_MIN_VERTICAL_OVERLAP = 0.50
LINE_MAX_CENTER_DISTANCE = 0.50
HORIZONTAL_OVERLAP_AMBIGUITY = 0.10
HORIZONTAL_ADJACENCY_MAX_GAP_HEIGHTS = 8.0
HORIZONTAL_ADJACENCY_MAX_GAP_WIDTH_FRACTION = 0.70
COLUMN_WIDTH_FRACTION = 0.04
COLUMN_HEIGHT_FACTOR = 0.75
COLUMN_MAX_LINE_STEP = 3
MIN_COLUMN_SUPPORT_ROWS = 2
STORE_ZONE_MAX_NORMALIZED_Y = 0.25
STORE_TIE_BAND_HEIGHTS = 0.50
DATE_ZONE_MAX_NORMALIZED_Y = 0.50
TOTAL_ZONE_MIN_NORMALIZED_Y = 0.50
CONTINUATION_MAX_EDGE_GAP_HEIGHTS = 1.25
CONTINUATION_LEFT_TOLERANCE_HEIGHTS = 1.0
CONTINUATION_LEFT_TOLERANCE_WIDTH_FRACTION = 0.05
NUMERIC_TIE_EPSILON = 1e-9

_AMOUNT = r"(?:RM\s*|MYR\s*|\$\s*)?\d+(?:,\d{3})*\.\d{2}"
_AMOUNT_FULL_RE = re.compile(rf"{_AMOUNT}", re.IGNORECASE)
_AMOUNT_FIND_RE = re.compile(_AMOUNT, re.IGNORECASE)
_QUANTITY_FULL_RE = re.compile(r"\d+(?:\.\d+)?")
_MULTIPLIER_FULL_RE = re.compile(r"[xX×]")
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
_COLUMN_HEADER_RE = re.compile(
    r"^\s*(?:(?:ITEM|DESCRIPTION|DESC|QTY|QUANTITY|UNIT\s+PRICE|PRICE|"
    r"AMOUNT|LINE\s+TOTAL|TOTAL)(?:\s+|$))+\s*$",
    re.IGNORECASE,
)
_FOOTER_TEXT_RE = re.compile(
    r"^\s*(?:THANK\s+YOU|PLEASE\s+COME\s+AGAIN|RECEIPT\s+COPY)\s*[!.]*\s*$",
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
_AMBIGUOUS_MULTIPLIER_RE = re.compile(
    r"^\s*(?P<description>.+?)\s+"
    r"(?P<quantity>\d+(?:\.\d+)?)\s+[xX×]\s+(?P<body>.+?)\s*$",
    re.IGNORECASE,
)
_UNMARKED_WHOLE_ITEM_RE = re.compile(
    rf"^\s*(?P<description>.+?)\s+"
    rf"(?P<quantity>\d+(?:\.\d+)?)\s+"
    rf"(?P<first_amount>{_AMOUNT})\s+"
    rf"(?P<second_amount>{_AMOUNT})\s*$",
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
class B2ExtractionResult:
    """Structured B2 output, or the required insufficient-source fallback."""

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
                "B2 does not assign a pre-resolution decision to structured output."
            )


@dataclass(frozen=True, slots=True)
class _TokenView:
    token: OcrSourceToken
    input_index: int
    text: str
    left: float
    right: float
    top: float
    bottom: float
    width: float
    height: float
    center_x: float
    center_y: float
    normalized_left: float
    normalized_right: float
    normalized_top: float
    normalized_bottom: float
    normalized_center_x: float
    normalized_center_y: float
    has_text: bool
    is_amount: bool
    is_quantity: bool
    is_multiplier: bool
    is_date: bool
    is_summary_anchor: bool

    @property
    def token_id(self) -> str:
        return self.token.token_id


@dataclass(frozen=True, slots=True)
class _HorizontalEdge:
    left_token_id: str
    right_token_id: str
    gap: float


@dataclass(frozen=True, slots=True)
class _VerticalEdge:
    upper_token_id: str
    lower_token_id: str
    alignment_distance: float


@dataclass(frozen=True, slots=True)
class _VisualLine:
    index: int
    views: tuple[_TokenView, ...]
    text: str
    spans: tuple[tuple[int, int, str], ...]
    left: float
    right: float
    top: float
    bottom: float
    center_y: float
    normalized_center_y: float
    ambiguous: bool

    @property
    def token_ids(self) -> tuple[str, ...]:
        return tuple(view.token_id for view in self.views)

    def references_for(self, span: tuple[int, int]) -> tuple[str, ...]:
        start, end = span
        return tuple(
            token_id
            for token_start, token_end, token_id in self.spans
            if token_start < end and token_end > start
        )


@dataclass(frozen=True, slots=True)
class _LayoutGraph:
    views: tuple[_TokenView, ...]
    lines: tuple[_VisualLine, ...]
    horizontal_edges: tuple[_HorizontalEdge, ...]
    vertical_edges: tuple[_VerticalEdge, ...]
    envelope_left: float
    envelope_top: float
    envelope_width: float
    envelope_height: float
    median_height: float
    column_tolerance: float


@dataclass(slots=True)
class _LineGroup:
    members: list[_TokenView]
    ambiguous: bool = False


@dataclass(frozen=True, slots=True)
class _Column:
    views: tuple[_TokenView, ...]
    right_edge: float
    line_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _ColumnModel:
    amount_columns: tuple[_Column, ...]
    quantity_columns: tuple[_Column, ...]
    tolerance: float


@dataclass(frozen=True, slots=True)
class _FieldEvidence:
    status: FieldStatus
    value: str | None
    source_token_ids: tuple[str, ...]
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class _ParsedRow:
    line: _VisualLine
    description_left: float
    description: _FieldEvidence
    quantity: _FieldEvidence
    unit_price: _FieldEvidence
    line_total: _FieldEvidence


def extract_b2(source_evidence: ReceiptSourceEvidence) -> B2ExtractionResult:
    """Extract a receipt from one already-gated immutable evidence package.

    The function deliberately accepts no gate callable or external evidence,
    so it consumes the recorded gate result without executing the source gate
    again.
    """

    if not isinstance(source_evidence, ReceiptSourceEvidence):
        raise TypeError("source_evidence must be ReceiptSourceEvidence.")

    if (
        source_evidence.gate_result.decision
        is SourceEvidenceDecision.INSUFFICIENT
    ):
        return B2ExtractionResult(
            receipt_output=None,
            pre_resolution_disposition=PreResolutionDisposition(
                state=PolicyState.FALLBACK_NO_UPDATE,
                gate_result=source_evidence.gate_result,
            ),
        )

    graph = _build_layout_graph(source_evidence.tokens)
    store_name, store_lines = _store_field(source_evidence.receipt_id, graph)
    purchase_date, date_lines = _date_field(source_evidence.receipt_id, graph)
    receipt_total, total_lines = _total_field(source_evidence.receipt_id, graph)
    reserved_lines = store_lines | date_lines | total_lines
    items = _item_rows(source_evidence.receipt_id, graph, reserved_lines)
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
    return B2ExtractionResult(output, None)


def _build_layout_graph(tokens: tuple[OcrSourceToken, ...]) -> _LayoutGraph:
    raw: list[tuple[OcrSourceToken, int, str, float, float, float, float]] = []
    for input_index, token in enumerate(tokens):
        text = token.original_text.strip()
        coordinates = tuple((point.x, point.y) for point in token.polygon)
        if not text or not all(isfinite(value) for pair in coordinates for value in pair):
            continue
        xs = tuple(pair[0] for pair in coordinates)
        ys = tuple(pair[1] for pair in coordinates)
        left, right = min(xs), max(xs)
        top, bottom = min(ys), max(ys)
        if right <= left or bottom <= top:
            continue
        raw.append((token, input_index, text, left, right, top, bottom))

    if raw:
        envelope_left = min(item[3] for item in raw)
        envelope_right = max(item[4] for item in raw)
        envelope_top = min(item[5] for item in raw)
        envelope_bottom = max(item[6] for item in raw)
        envelope_width = envelope_right - envelope_left
        envelope_height = envelope_bottom - envelope_top
    else:
        envelope_left = envelope_top = 0.0
        envelope_width = envelope_height = 1.0

    views = tuple(
        _make_token_view(
            token,
            input_index,
            text,
            left,
            right,
            top,
            bottom,
            envelope_left,
            envelope_top,
            envelope_width,
            envelope_height,
        )
        for token, input_index, text, left, right, top, bottom in raw
    )
    ordered_views = tuple(
        sorted(views, key=lambda view: (view.center_y, view.top, view.left, view.token_id))
    )
    median_height = median(view.height for view in ordered_views) if ordered_views else 1.0
    column_tolerance = max(
        COLUMN_WIDTH_FRACTION * envelope_width,
        COLUMN_HEIGHT_FACTOR * median_height,
    )
    maximum_horizontal_gap = max(
        HORIZONTAL_ADJACENCY_MAX_GAP_HEIGHTS * median_height,
        HORIZONTAL_ADJACENCY_MAX_GAP_WIDTH_FRACTION * envelope_width,
    )
    lines = _associate_lines(ordered_views, maximum_horizontal_gap)
    horizontal_edges = _horizontal_edges(lines, maximum_horizontal_gap)
    vertical_edges = _vertical_edges(lines, column_tolerance)
    return _LayoutGraph(
        views=ordered_views,
        lines=lines,
        horizontal_edges=horizontal_edges,
        vertical_edges=vertical_edges,
        envelope_left=envelope_left,
        envelope_top=envelope_top,
        envelope_width=envelope_width,
        envelope_height=envelope_height,
        median_height=median_height,
        column_tolerance=column_tolerance,
    )


def _make_token_view(
    token: OcrSourceToken,
    input_index: int,
    text: str,
    left: float,
    right: float,
    top: float,
    bottom: float,
    envelope_left: float,
    envelope_top: float,
    envelope_width: float,
    envelope_height: float,
) -> _TokenView:
    width = right - left
    height = bottom - top
    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    is_amount = _AMOUNT_FULL_RE.fullmatch(text) is not None
    is_quantity = not is_amount and _QUANTITY_FULL_RE.fullmatch(text) is not None
    return _TokenView(
        token=token,
        input_index=input_index,
        text=text,
        left=left,
        right=right,
        top=top,
        bottom=bottom,
        width=width,
        height=height,
        center_x=center_x,
        center_y=center_y,
        normalized_left=(left - envelope_left) / envelope_width,
        normalized_right=(right - envelope_left) / envelope_width,
        normalized_top=(top - envelope_top) / envelope_height,
        normalized_bottom=(bottom - envelope_top) / envelope_height,
        normalized_center_x=(center_x - envelope_left) / envelope_width,
        normalized_center_y=(center_y - envelope_top) / envelope_height,
        has_text=any(character.isalpha() for character in text),
        is_amount=is_amount,
        is_quantity=is_quantity,
        is_multiplier=_MULTIPLIER_FULL_RE.fullmatch(text) is not None,
        is_date=(
            _DATE_ANCHOR_RE.fullmatch(text) is not None
            or _date_state(text) in {"valid", "ambiguous"}
        ),
        is_summary_anchor=(
            _NON_ITEM_ANCHOR_RE.match(text) is not None
            or _FINANCIAL_SUMMARY_RE.fullmatch(text) is not None
        ),
    )


def _associate_lines(
    views: tuple[_TokenView, ...], maximum_horizontal_gap: float
) -> tuple[_VisualLine, ...]:
    groups: list[_LineGroup] = []
    membership: dict[str, _LineGroup] = {}
    for view in views:
        eligible = [
            group
            for group in groups
            if all(_same_visual_line(view, member) for member in group.members)
        ]
        if not eligible:
            group = _LineGroup([view])
            groups.append(group)
        elif len(eligible) == 1:
            group = eligible[0]
            group.members.append(view)
        else:
            for competing in eligible:
                competing.ambiguous = True
            group = _LineGroup([view], ambiguous=True)
            groups.append(group)
        membership[view.token_id] = group

    # A token that is compatible with two completed lines is substantive
    # layout ambiguity.  Token ID ordering only stabilizes serialization.
    for view in views:
        own = membership[view.token_id]
        compatible = [own]
        for group in groups:
            if group is own:
                continue
            if all(_same_visual_line(view, member) for member in group.members):
                compatible.append(group)
        if len(compatible) > 1:
            for group in compatible:
                group.ambiguous = True

    groups.sort(
        key=lambda group: (
            median(member.center_y for member in group.members),
            min(member.left for member in group.members),
            tuple(sorted(member.token_id for member in group.members)),
        )
    )
    return tuple(
        _build_visual_line(index, group, maximum_horizontal_gap)
        for index, group in enumerate(groups)
    )


def _same_visual_line(first: _TokenView, second: _TokenView) -> bool:
    overlap = max(0.0, min(first.bottom, second.bottom) - max(first.top, second.top))
    overlap_ratio = overlap / min(first.height, second.height)
    center_distance = abs(first.center_y - second.center_y) / max(
        first.height, second.height
    )
    return (
        overlap_ratio + NUMERIC_TIE_EPSILON >= LINE_MIN_VERTICAL_OVERLAP
        and center_distance <= LINE_MAX_CENTER_DISTANCE + NUMERIC_TIE_EPSILON
    )


def _build_visual_line(
    index: int, group: _LineGroup, maximum_horizontal_gap: float
) -> _VisualLine:
    ordered = tuple(
        sorted(group.members, key=lambda view: (view.left, view.center_x, view.token_id))
    )
    parts: list[str] = []
    spans: list[tuple[int, int, str]] = []
    cursor = 0
    for view in ordered:
        if parts:
            cursor += 1
        start = cursor
        parts.append(view.text)
        cursor += len(view.text)
        spans.append((start, cursor, view.token_id))

    horizontal_ambiguity = any(
        _horizontal_overlap_ratio(first, second)
        > HORIZONTAL_OVERLAP_AMBIGUITY + NUMERIC_TIE_EPSILON
        for first, second in zip(ordered, ordered[1:])
    )
    disconnected = any(
        second.left - first.right
        > maximum_horizontal_gap + NUMERIC_TIE_EPSILON
        for first, second in zip(ordered, ordered[1:])
    )
    return _VisualLine(
        index=index,
        views=ordered,
        text=" ".join(parts),
        spans=tuple(spans),
        left=min(view.left for view in ordered),
        right=max(view.right for view in ordered),
        top=min(view.top for view in ordered),
        bottom=max(view.bottom for view in ordered),
        center_y=median(view.center_y for view in ordered),
        normalized_center_y=median(view.normalized_center_y for view in ordered),
        ambiguous=group.ambiguous or horizontal_ambiguity or disconnected,
    )


def _horizontal_overlap_ratio(first: _TokenView, second: _TokenView) -> float:
    overlap = max(0.0, min(first.right, second.right) - max(first.left, second.left))
    return overlap / min(first.width, second.width)


def _horizontal_edges(
    lines: tuple[_VisualLine, ...], maximum_gap: float
) -> tuple[_HorizontalEdge, ...]:
    edges: list[_HorizontalEdge] = []
    for line in lines:
        for first, second in zip(line.views, line.views[1:]):
            gap = max(0.0, second.left - first.right)
            if gap <= maximum_gap + NUMERIC_TIE_EPSILON:
                edges.append(_HorizontalEdge(first.token_id, second.token_id, gap))
    return tuple(edges)


def _vertical_edges(
    lines: tuple[_VisualLine, ...], tolerance: float
) -> tuple[_VerticalEdge, ...]:
    edges: list[_VerticalEdge] = []
    for upper_index, upper in enumerate(lines):
        for lower in lines[upper_index + 1 :]:
            if lower.index - upper.index > COLUMN_MAX_LINE_STEP:
                break
            for first in upper.views:
                for second in lower.views:
                    distance = min(
                        abs(first.right - second.right),
                        abs(first.center_x - second.center_x),
                    )
                    if distance <= tolerance + NUMERIC_TIE_EPSILON:
                        edges.append(
                            _VerticalEdge(first.token_id, second.token_id, distance)
                        )
    return tuple(edges)


def _store_field(
    receipt_id: str, graph: _LayoutGraph
) -> tuple[StructuredField, frozenset[int]]:
    field_id = _field_id(receipt_id, "store-name")
    candidates = [
        line
        for line in graph.lines
        if line.normalized_center_y
        <= STORE_ZONE_MAX_NORMALIZED_Y + NUMERIC_TIE_EPSILON
        and not line.ambiguous
        and any(view.has_text for view in line.views)
        and not _is_control_line(line.text)
        and not _is_column_header(line.text)
        and _FOOTER_TEXT_RE.fullmatch(line.text) is None
        and not any(view.is_date or view.is_summary_anchor for view in line.views)
        and not _looks_like_item(line)
    ]
    if not candidates:
        return (
            _empty_field(
                field_id,
                receipt_id,
                ReceiptFieldName.STORE_NAME,
                FieldStatus.MISSING,
                "No safe alphabetic heading was observed in the header zone.",
            ),
            frozenset(),
        )

    first = min(candidates, key=lambda line: (line.center_y, line.left, line.token_ids))
    tied = [
        line
        for line in candidates
        if abs(line.center_y - first.center_y)
        <= STORE_TIE_BAND_HEIGHTS * graph.median_height + NUMERIC_TIE_EPSILON
    ]
    reserved = frozenset(line.index for line in tied)
    if len(tied) > 1:
        return (
            _empty_field(
                field_id,
                receipt_id,
                ReceiptFieldName.STORE_NAME,
                FieldStatus.UNRESOLVED,
                "Multiple equally top-ranked heading lines were observed.",
                _line_ids(tied),
            ),
            reserved,
        )
    return (
        _extracted_field(
            field_id,
            receipt_id,
            ReceiptFieldName.STORE_NAME,
            first.text,
            first.token_ids,
        ),
        frozenset({first.index}),
    )


def _date_field(
    receipt_id: str, graph: _LayoutGraph
) -> tuple[StructuredField, frozenset[int]]:
    field_id = _field_id(receipt_id, "purchase-date")
    anchored = [
        (line, match)
        for line in graph.lines
        if (match := _DATE_ANCHOR_RE.fullmatch(line.text)) is not None
    ]
    if len(anchored) > 1:
        lines = [line for line, _ in anchored]
        return (
            _empty_field(
                field_id,
                receipt_id,
                ReceiptFieldName.PURCHASE_DATE,
                FieldStatus.UNRESOLVED,
                "Multiple DATE-like anchored values were observed.",
                _line_ids(lines),
            ),
            frozenset(line.index for line in lines),
        )

    if anchored:
        line, match = anchored[0]
        references = line.references_for(match.span("body")) or line.token_ids
        if (
            line.ambiguous
            or line.normalized_center_y
            > DATE_ZONE_MAX_NORMALIZED_Y + NUMERIC_TIE_EPSILON
        ):
            return (
                _empty_field(
                    field_id,
                    receipt_id,
                    ReceiptFieldName.PURCHASE_DATE,
                    FieldStatus.UNRESOLVED,
                    "The anchored date has ambiguous layout or lies outside the date zone.",
                    line.token_ids,
                ),
                frozenset({line.index}),
            )
        field = _date_value_field(field_id, receipt_id, match.group("body"), references)
        return field, frozenset({line.index})

    unanchored = [
        line
        for line in graph.lines
        if not line.ambiguous
        and line.normalized_center_y
        <= DATE_ZONE_MAX_NORMALIZED_Y + NUMERIC_TIE_EPSILON
        and _date_state(line.text) in {"valid", "ambiguous"}
    ]
    if not unanchored:
        return (
            _empty_field(
                field_id,
                receipt_id,
                ReceiptFieldName.PURCHASE_DATE,
                FieldStatus.MISSING,
                "No supported purchase-date evidence was observed in the date zone.",
            ),
            frozenset(),
        )
    if len(unanchored) > 1:
        return (
            _empty_field(
                field_id,
                receipt_id,
                ReceiptFieldName.PURCHASE_DATE,
                FieldStatus.UNRESOLVED,
                "Multiple unanchored date candidates were observed in the date zone.",
                _line_ids(unanchored),
            ),
            frozenset(line.index for line in unanchored),
        )
    line = unanchored[0]
    return (
        _date_value_field(field_id, receipt_id, line.text, line.token_ids),
        frozenset({line.index}),
    )


def _date_value_field(
    field_id: str,
    receipt_id: str,
    value: str,
    references: tuple[str, ...],
) -> StructuredField:
    state = _date_state(value)
    if state == "valid":
        return _extracted_field(
            field_id,
            receipt_id,
            ReceiptFieldName.PURCHASE_DATE,
            value,
            references,
        )
    reason = (
        "The numeric date is ambiguous between day-first and month-first."
        if state == "ambiguous"
        else "The observed value is not a valid supported date without repair."
    )
    return _empty_field(
        field_id,
        receipt_id,
        ReceiptFieldName.PURCHASE_DATE,
        FieldStatus.UNRESOLVED,
        reason,
        references,
    )


def _date_state(value: str) -> str:
    value = value.strip()
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


def _total_field(
    receipt_id: str, graph: _LayoutGraph
) -> tuple[StructuredField, frozenset[int]]:
    field_id = _field_id(receipt_id, "receipt-total")
    anchored = [line for line in graph.lines if _ANY_TOTAL_ANCHOR_RE.match(line.text)]
    if not anchored:
        return (
            _empty_field(
                field_id,
                receipt_id,
                ReceiptFieldName.RECEIPT_TOTAL,
                FieldStatus.MISSING,
                "No explicit TOTAL or GRAND TOTAL anchor was observed.",
            ),
            frozenset(),
        )
    reserved = frozenset(line.index for line in anchored)
    if len(anchored) > 1:
        return (
            _empty_field(
                field_id,
                receipt_id,
                ReceiptFieldName.RECEIPT_TOTAL,
                FieldStatus.UNRESOLVED,
                "Multiple explicit receipt-total candidates were observed.",
                _line_ids(anchored),
            ),
            reserved,
        )

    line = anchored[0]
    match = _TOTAL_ANCHOR_RE.fullmatch(line.text)
    if (
        line.ambiguous
        or match is None
        or line.normalized_center_y
        + NUMERIC_TIE_EPSILON
        < TOTAL_ZONE_MIN_NORMALIZED_Y
    ):
        return (
            _empty_field(
                field_id,
                receipt_id,
                ReceiptFieldName.RECEIPT_TOTAL,
                FieldStatus.UNRESOLVED,
                "The explicit total lacks one safe amount in the footer zone.",
                line.token_ids,
            ),
            reserved,
        )
    return (
        _extracted_field(
            field_id,
            receipt_id,
            ReceiptFieldName.RECEIPT_TOTAL,
            match.group("amount"),
            line.references_for(match.span("amount")) or line.token_ids,
        ),
        reserved,
    )


def _item_rows(
    receipt_id: str,
    graph: _LayoutGraph,
    reserved_lines: frozenset[int],
) -> tuple[ReceiptItemRow, ...]:
    candidate_lines = tuple(
        line
        for line in graph.lines
        if line.index not in reserved_lines
        and not line.ambiguous
        and not _is_control_line(line.text)
        and not _is_column_header(line.text)
    )
    column_lines = tuple(line for line in candidate_lines if _looks_like_item(line))
    model = _column_model(column_lines, graph)
    horizontal_pairs = frozenset(
        frozenset((edge.left_token_id, edge.right_token_id))
        for edge in graph.horizontal_edges
    )
    parsed = [
        row
        for line in candidate_lines
        if (row := _parse_item_line(line, model, horizontal_pairs)) is not None
    ]
    parsed = _attach_continuations(parsed, candidate_lines, graph)
    parsed.sort(key=lambda row: (row.line.center_y, row.line.left, row.line.token_ids))

    rows: list[ReceiptItemRow] = []
    for index, row in enumerate(parsed):
        row_id = f"{receipt_id}:b2:row:{index:06d}"
        rows.append(
            ReceiptItemRow(
                row_id=row_id,
                receipt_id=receipt_id,
                description=_structured_item_field(
                    receipt_id,
                    row_id,
                    ReceiptFieldName.ITEM_DESCRIPTION,
                    row.description,
                ),
                quantity=_structured_item_field(
                    receipt_id, row_id, ReceiptFieldName.QUANTITY, row.quantity
                ),
                unit_price=_structured_item_field(
                    receipt_id, row_id, ReceiptFieldName.UNIT_PRICE, row.unit_price
                ),
                line_total=_structured_item_field(
                    receipt_id, row_id, ReceiptFieldName.LINE_TOTAL, row.line_total
                ),
            )
        )
    return tuple(rows)


def _column_model(
    lines: tuple[_VisualLine, ...], graph: _LayoutGraph
) -> _ColumnModel:
    line_by_token = {
        view.token_id: line.index for line in lines for view in line.views
    }
    vertical_pairs = frozenset(
        frozenset((edge.upper_token_id, edge.lower_token_id))
        for edge in graph.vertical_edges
    )
    amounts = tuple(
        view for line in lines for view in line.views if view.is_amount
    )
    quantities = tuple(
        view for line in lines for view in line.views if view.is_quantity
    )
    amount_columns = _supported_columns(
        amounts, line_by_token, graph.column_tolerance, vertical_pairs
    )
    quantity_columns = _supported_columns(
        quantities, line_by_token, graph.column_tolerance, vertical_pairs
    )
    return _ColumnModel(amount_columns, quantity_columns, graph.column_tolerance)


def _supported_columns(
    views: tuple[_TokenView, ...],
    line_by_token: dict[str, int],
    tolerance: float,
    vertical_pairs: frozenset[frozenset[str]],
) -> tuple[_Column, ...]:
    groups: list[list[_TokenView]] = []
    for view in sorted(views, key=lambda item: (item.right, item.center_y, item.token_id)):
        eligible = [
            group
            for group in groups
            if all(abs(view.right - member.right) <= tolerance + NUMERIC_TIE_EPSILON for member in group)
            and any(
                0 < abs(line_by_token[view.token_id] - line_by_token[member.token_id])
                <= COLUMN_MAX_LINE_STEP
                and frozenset((view.token_id, member.token_id)) in vertical_pairs
                for member in group
            )
        ]
        if len(eligible) == 1:
            eligible[0].append(view)
        else:
            # Zero support starts a new potential column.  Multiple compatible
            # columns are not merged through a deterministic token-ID choice.
            groups.append([view])

    columns = []
    for group in groups:
        line_indices = tuple(
            sorted({line_by_token[view.token_id] for view in group})
        )
        if len(line_indices) >= MIN_COLUMN_SUPPORT_ROWS:
            columns.append(
                _Column(
                    tuple(group),
                    median(view.right for view in group),
                    line_indices,
                )
            )
    columns.sort(key=lambda column: (column.right_edge, _ids(column.views)))
    return tuple(columns)


def _parse_item_line(
    line: _VisualLine,
    model: _ColumnModel,
    horizontal_pairs: frozenset[frozenset[str]],
) -> _ParsedRow | None:
    full = _FULL_ITEM_RE.fullmatch(line.text)
    if full is not None and _valid_description(full.group("description")):
        description = _match_evidence(line, full, "description")
        return _ParsedRow(
            line=line,
            description_left=_reference_left(line, description.source_token_ids),
            description=description,
            quantity=_match_evidence(line, full, "quantity"),
            unit_price=_match_evidence(line, full, "unit_price"),
            line_total=_match_evidence(line, full, "line_total"),
        )

    ambiguous_multiplier = _AMBIGUOUS_MULTIPLIER_RE.fullmatch(line.text)
    if (
        ambiguous_multiplier is not None
        and _valid_description(ambiguous_multiplier.group("description"))
        and _AMOUNT_FIND_RE.search(ambiguous_multiplier.group("body")) is not None
    ):
        body_references = (
            line.references_for(ambiguous_multiplier.span("body")) or line.token_ids
        )
        description = _match_evidence(line, ambiguous_multiplier, "description")
        return _ParsedRow(
            line=line,
            description_left=_reference_left(line, description.source_token_ids),
            description=description,
            quantity=_match_evidence(line, ambiguous_multiplier, "quantity"),
            unit_price=_unresolved(
                "Observed multiplier amounts cannot be uniquely assigned to unit price.",
                body_references,
            ),
            line_total=_unresolved(
                "Observed multiplier amounts cannot be uniquely assigned to line total.",
                body_references,
            ),
        )

    unmarked_whole = _UNMARKED_WHOLE_ITEM_RE.fullmatch(line.text)
    if (
        len(line.views) == 1
        and unmarked_whole is not None
        and _valid_description(unmarked_whole.group("description"))
    ):
        amount_references = _unique_strings(
            token_id
            for group_name in ("first_amount", "second_amount")
            for token_id in (
                line.references_for(unmarked_whole.span(group_name)) or line.token_ids
            )
        )
        description = _match_evidence(line, unmarked_whole, "description")
        quantity_references = (
            line.references_for(unmarked_whole.span("quantity")) or line.token_ids
        )
        return _ParsedRow(
            line,
            _reference_left(line, description.source_token_ids),
            description,
            _unresolved(
                "A quantity-shaped value was observed without multiplier or word-level column geometry.",
                quantity_references,
            ),
            _unresolved(
                "Two in-region amounts lack word-level geometry for unit-price assignment.",
                amount_references,
            ),
            _unresolved(
                "Two in-region amounts lack word-level geometry for line-total assignment.",
                amount_references,
            ),
        )

    amount_views = tuple(view for view in line.views if view.is_amount)
    quantity_views = tuple(view for view in line.views if view.is_quantity)
    numeric_views = tuple(
        view
        for view in line.views
        if view.is_amount or view.is_quantity or view.is_multiplier
    )
    if amount_views:
        first_numeric_left = min(view.left for view in numeric_views)
        description_views = tuple(
            view
            for view in line.views
            if view.has_text and view.left < first_numeric_left
        )
        if not description_views:
            return None
        if any(
            frozenset((first.token_id, second.token_id)) not in horizontal_pairs
            for first, second in zip(description_views, description_views[1:])
        ):
            return None
        if any(
            view.has_text
            and not (view.is_amount or view.is_quantity or view.is_multiplier)
            and view.left >= first_numeric_left
            for view in line.views
        ):
            return None
        description = _extracted(
            " ".join(view.text for view in description_views), _ids(description_views)
        )
        quantity = _quantity_evidence(quantity_views, model)
        unit_price, line_total = _amount_evidence(amount_views, model)
        return _ParsedRow(
            line,
            min(view.left for view in description_views),
            description,
            quantity,
            unit_price,
            line_total,
        )

    amount_matches = tuple(_AMOUNT_FIND_RE.finditer(line.text))
    partial = _PARTIAL_ITEM_RE.fullmatch(line.text)
    if (
        len(amount_matches) == 1
        and partial is not None
        and _valid_description(partial.group("description"))
        and re.search(r"(?:^|\s)[xX](?:\s|$)|×", partial.group("description"))
        is None
    ):
        description = _match_evidence(line, partial, "description")
        return _ParsedRow(
            line,
            _reference_left(line, description.source_token_ids),
            description,
            _missing("No explicit quantity was observed on the detected item row."),
            _missing("No explicit unit price was observed on the detected item row."),
            _match_evidence(line, partial, "line_total"),
        )

    if len(amount_matches) >= 2:
        description_text = line.text[: amount_matches[0].start()].strip()
        if _valid_description(description_text):
            references = line.references_for((0, amount_matches[0].start())) or line.token_ids
            amount_references = _unique_strings(
                token_id
                for match in amount_matches
                for token_id in (line.references_for(match.span()) or line.token_ids)
            )
            return _ParsedRow(
                line,
                _reference_left(line, references),
                _extracted(description_text, references),
                _missing("No uniquely assigned quantity was observed on the item row."),
                _unresolved(
                    "Multiple in-region amounts lack word-level geometry for unit-price assignment.",
                    amount_references,
                ),
                _unresolved(
                    "Multiple in-region amounts lack word-level geometry for line-total assignment.",
                    amount_references,
                ),
            )
    return None


def _quantity_evidence(
    views: tuple[_TokenView, ...], model: _ColumnModel
) -> _FieldEvidence:
    if not views:
        return _missing("No explicit quantity was observed on the detected item row.")
    if len(views) != 1:
        return _unresolved(
            "Multiple observed numeric values could represent quantity.", _ids(views)
        )
    view = views[0]
    if len(model.quantity_columns) != 1:
        return _unresolved(
            "The observed numeric value lacks one stable repeated quantity column.",
            (view.token_id,),
        )
    if (
        model.amount_columns
        and model.quantity_columns[0].right_edge
        >= model.amount_columns[0].right_edge - NUMERIC_TIE_EPSILON
    ):
        return _unresolved(
            "The repeated numeric column is not left of the amount columns, so it cannot be safely assigned as quantity.",
            (view.token_id,),
        )
    memberships = _column_memberships(view, model.quantity_columns, model.tolerance)
    if memberships != (0,):
        return _unresolved(
            "The observed numeric value cannot be uniquely assigned to the quantity column.",
            (view.token_id,),
        )
    return _extracted(view.text, (view.token_id,))


def _amount_evidence(
    views: tuple[_TokenView, ...], model: _ColumnModel
) -> tuple[_FieldEvidence, _FieldEvidence]:
    references = _ids(views)
    columns = model.amount_columns
    if len(views) == 1:
        view = views[0]
        if not columns:
            return (
                _missing("No explicit unit price was observed on the detected item row."),
                _extracted(view.text, (view.token_id,)),
            )
        memberships = _column_memberships(view, columns, model.tolerance)
        if len(columns) == 1 and memberships == (0,):
            return (
                _missing("No explicit unit price was observed on the detected item row."),
                _extracted(view.text, (view.token_id,)),
            )
        if len(columns) == 2 and memberships == (0,):
            return (
                _extracted(view.text, (view.token_id,)),
                _missing("No explicit line total was observed on the detected item row."),
            )
        if len(columns) == 2 and memberships == (1,):
            return (
                _missing("No explicit unit price was observed on the detected item row."),
                _extracted(view.text, (view.token_id,)),
            )
        reason = "The observed amount cannot be uniquely assigned to a numeric role."
        return _unresolved(reason, references), _unresolved(reason, references)

    if len(views) == 2 and len(columns) == 2:
        ordered = tuple(sorted(views, key=lambda view: (view.left, view.token_id)))
        memberships = tuple(
            _column_memberships(view, columns, model.tolerance) for view in ordered
        )
        if memberships == ((0,), (1,)):
            return (
                _extracted(ordered[0].text, (ordered[0].token_id,)),
                _extracted(ordered[1].text, (ordered[1].token_id,)),
            )

    reason = "Observed amounts have multiple unsupported unit-price/line-total interpretations."
    return _unresolved(reason, references), _unresolved(reason, references)


def _column_memberships(
    view: _TokenView,
    columns: tuple[_Column, ...],
    tolerance: float,
) -> tuple[int, ...]:
    return tuple(
        index
        for index, column in enumerate(columns)
        if abs(view.right - column.right_edge) <= tolerance + NUMERIC_TIE_EPSILON
    )


def _attach_continuations(
    rows: list[_ParsedRow],
    candidate_lines: tuple[_VisualLine, ...],
    graph: _LayoutGraph,
) -> list[_ParsedRow]:
    row_line_indices = {row.line.index for row in rows}
    descriptions = [
        line
        for line in candidate_lines
        if line.index not in row_line_indices
        and line.normalized_center_y
        > STORE_ZONE_MAX_NORMALIZED_Y + NUMERIC_TIE_EPSILON
        and _description_only_line(line)
    ]
    left_tolerance = max(
        CONTINUATION_LEFT_TOLERANCE_HEIGHTS * graph.median_height,
        CONTINUATION_LEFT_TOLERANCE_WIDTH_FRACTION * graph.envelope_width,
    )
    maximum_gap = CONTINUATION_MAX_EDGE_GAP_HEIGHTS * graph.median_height
    candidates_by_description: dict[int, list[int]] = {}
    candidates_by_row: dict[int, list[int]] = {}
    for description_index, line in enumerate(descriptions):
        for row_index, row in enumerate(rows):
            gap = _line_edge_gap(line, row.line)
            if (
                abs(line.index - row.line.index) == 1
                and gap <= maximum_gap + NUMERIC_TIE_EPSILON
                and abs(line.left - row.description_left)
                <= left_tolerance + NUMERIC_TIE_EPSILON
            ):
                candidates_by_description.setdefault(description_index, []).append(row_index)
                candidates_by_row.setdefault(row_index, []).append(description_index)

    updated = list(rows)
    ambiguous_rows: dict[int, set[int]] = {}
    for description_index, row_indexes in candidates_by_description.items():
        if len(row_indexes) > 1:
            for row_index in row_indexes:
                ambiguous_rows.setdefault(row_index, set()).add(description_index)
    for row_index, description_indexes in candidates_by_row.items():
        if len(description_indexes) > 1:
            ambiguous_rows.setdefault(row_index, set()).update(description_indexes)

    for row_index, description_indexes in ambiguous_rows.items():
        row = updated[row_index]
        competing_ids = _unique_strings(
            token_id
            for description_index in sorted(description_indexes)
            for token_id in descriptions[description_index].token_ids
        )
        updated[row_index] = _ParsedRow(
            row.line,
            row.description_left,
            _unresolved(
                "Description continuation evidence has multiple spatially plausible row associations.",
                _unique_strings(row.description.source_token_ids + competing_ids),
            ),
            row.quantity,
            row.unit_price,
            row.line_total,
        )

    for description_index, row_indexes in candidates_by_description.items():
        if len(row_indexes) != 1:
            continue
        row_index = row_indexes[0]
        if (
            len(candidates_by_row.get(row_index, ())) != 1
            or row_index in ambiguous_rows
        ):
            continue
        line = descriptions[description_index]
        row = updated[row_index]
        if line.center_y < row.line.center_y:
            value = f"{line.text} {row.description.value}"
            references = line.token_ids + row.description.source_token_ids
        else:
            value = f"{row.description.value} {line.text}"
            references = row.description.source_token_ids + line.token_ids
        updated[row_index] = _ParsedRow(
            row.line,
            min(row.description_left, line.left),
            _extracted(value, _unique_strings(references)),
            row.quantity,
            row.unit_price,
            row.line_total,
        )
    return updated


def _description_only_line(line: _VisualLine) -> bool:
    return (
        not line.ambiguous
        and any(view.has_text for view in line.views)
        and not any(
            view.is_amount or view.is_quantity or view.is_multiplier
            for view in line.views
        )
        and not _AMOUNT_FIND_RE.search(line.text)
        and not _is_control_line(line.text)
        and not _is_column_header(line.text)
        and _FOOTER_TEXT_RE.fullmatch(line.text) is None
        and not any(view.is_date or view.is_summary_anchor for view in line.views)
        and _date_state(line.text) == "invalid"
    )


def _line_edge_gap(first: _VisualLine, second: _VisualLine) -> float:
    if first.bottom < second.top:
        return second.top - first.bottom
    if second.bottom < first.top:
        return first.top - second.bottom
    return 0.0


def _match_evidence(
    line: _VisualLine, match: re.Match[str], group_name: str
) -> _FieldEvidence:
    references = line.references_for(match.span(group_name)) or line.token_ids
    return _extracted(match.group(group_name).strip(), references)


def _reference_left(line: _VisualLine, references: tuple[str, ...]) -> float:
    relevant = [view.left for view in line.views if view.token_id in references]
    return min(relevant) if relevant else line.left


def _looks_like_item(line: _VisualLine) -> bool:
    if line.ambiguous or _is_control_line(line.text) or _is_column_header(line.text):
        return False
    if _FULL_ITEM_RE.fullmatch(line.text) is not None:
        return True
    if any(view.is_amount for view in line.views) and any(
        view.has_text for view in line.views
    ):
        return True
    partial = _PARTIAL_ITEM_RE.fullmatch(line.text)
    return partial is not None and _valid_description(partial.group("description"))


def _is_control_line(text: str) -> bool:
    return (
        _NON_ITEM_ANCHOR_RE.match(text) is not None
        or _FINANCIAL_SUMMARY_RE.fullmatch(text) is not None
    )


def _is_column_header(text: str) -> bool:
    return _COLUMN_HEADER_RE.fullmatch(text) is not None


def _valid_description(value: str) -> bool:
    return any(character.isalpha() for character in value)


def _line_ids(lines: Iterable[_VisualLine]) -> tuple[str, ...]:
    return _unique_strings(
        token_id for line in lines for token_id in line.token_ids
    )


def _ids(views: Iterable[_TokenView]) -> tuple[str, ...]:
    return _unique_strings(view.token_id for view in views)


def _unique_strings(values: Iterable[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    for value in values:
        if value not in ordered:
            ordered.append(value)
    return tuple(ordered)


def _extracted(value: str, source_token_ids: tuple[str, ...]) -> _FieldEvidence:
    return _FieldEvidence(FieldStatus.EXTRACTED, value, source_token_ids)


def _missing(reason: str) -> _FieldEvidence:
    return _FieldEvidence(FieldStatus.MISSING, None, (), reason)


def _unresolved(reason: str, source_token_ids: tuple[str, ...]) -> _FieldEvidence:
    return _FieldEvidence(FieldStatus.UNRESOLVED, None, source_token_ids, reason)


def _structured_item_field(
    receipt_id: str,
    row_id: str,
    field_name: ReceiptFieldName,
    evidence: _FieldEvidence,
) -> StructuredField:
    field_id = f"{row_id}:{field_name.value.lower().replace('_', '-')}"
    if evidence.status is FieldStatus.EXTRACTED:
        assert evidence.value is not None
        return _extracted_field(
            field_id,
            receipt_id,
            field_name,
            evidence.value,
            evidence.source_token_ids,
            row_id,
        )
    assert evidence.reason is not None
    return _empty_field(
        field_id,
        receipt_id,
        field_name,
        evidence.status,
        evidence.reason,
        evidence.source_token_ids,
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


def _field_id(receipt_id: str, suffix: str) -> str:
    return f"{receipt_id}:b2:{suffix}"


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
