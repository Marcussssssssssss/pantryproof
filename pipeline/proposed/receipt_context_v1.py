"""Receipt-local association and B3-compatible arithmetic for the proposed path."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from re import compile, IGNORECASE

from pipeline.baseline_b3 import (
    AdjustmentEvidence, ArithmeticDiagnostic, ArithmeticOutcome, ArithmeticPhase, B3ParseState,
    _item_arithmetic_diagnostic, _receipt_arithmetic_diagnostic,
    _row_has_promotion, _weight_state, parse_generic_date, parse_money, parse_positive_quantity,
)
from pipeline.contracts import FieldStatus, ReceiptFieldName as Name, ReceiptOutput, StructuredField
from pipeline.proposed.contracts import SourceCharacterSpanV1

ITEM_NUMERIC = frozenset((Name.QUANTITY, Name.UNIT_PRICE, Name.LINE_TOTAL))
NUMERIC = ITEM_NUMERIC | {Name.RECEIPT_TOTAL}
EXACT = frozenset((
    ArithmeticOutcome.RAW_EXACT_MATCH, ArithmeticOutcome.MATCH_AFTER_CURRENCY_ROUNDING,
))
MATCH = EXACT | {ArithmeticOutcome.WITHIN_INCLUSIVE_TOLERANCE}
CONTRADICTION = frozenset((
    ArithmeticOutcome.MISMATCH_BEYOND_TOLERANCE,
    ArithmeticOutcome.CONFLICTING_CURRENCY_MARKERS,
))
EXCEPTION = frozenset((
    ArithmeticOutcome.AMBIGUOUS_OR_CONFLICTING_UNITS,
    ArithmeticOutcome.EXPLICIT_PROMOTION_OR_ADJUSTMENT_EXCEPTION,
))

_LABELS = {
    Name.STORE_NAME: r"STORE(?:\s+NAME)?|MERCHANT",
    Name.ITEM_DESCRIPTION: r"ITEM\s+DESCRIPTION|ITEM\s+DESC",
    Name.QUANTITY: r"QTY|QUANTITY",
    Name.UNIT_PRICE: r"UNIT\s+PRICE",
    Name.LINE_TOTAL: r"LINE\s+TOTAL|EXTENDED\s+PRICE",
    Name.RECEIPT_TOTAL: r"GRAND\s+TOTAL|AMOUNT\s+DUE|TOTAL\s+PAYABLE|TOTAL",
}
_LABEL = r"(?:" + "|".join(f"(?P<{name.name}>{label})" for name, label in _LABELS.items()) + r")"
_ANCHOR = compile(
    r"^\s*" + _LABEL + r"\s*(?P<separator>:|=|\s)\s*(?P<value>\S(?:[^\r\n]*?\S)?)\s*$",
    IGNORECASE,
)
_SPLIT_LABEL = compile(r"^\s*" + _LABEL + r"\s*(?P<separator>:|=)?\s*$", IGNORECASE)


@dataclass(frozen=True, slots=True)
class ReceiptAnchor:
    field_id: str
    span: SourceCharacterSpanV1
    displacement: int | None
    label_span: SourceCharacterSpanV1 | None = None


def ordered_fields(output: ReceiptOutput) -> tuple[StructuredField, ...]:
    return (
        output.store_name, output.purchase_date,
        *(field for row in output.items for field in row.fields), output.receipt_total,
    )


def replace_fields(output: ReceiptOutput, fields: dict[str, StructuredField]) -> ReceiptOutput:
    def get(field):
        return fields.get(field.field_id, field)

    return replace(
        output, store_name=get(output.store_name), purchase_date=get(output.purchase_date),
        receipt_total=get(output.receipt_total),
        items=tuple(replace(
            row, description=get(row.description), quantity=get(row.quantity),
            unit_price=get(row.unit_price), line_total=get(row.line_total),
        ) for row in output.items),
    )


def _vertical_band(token) -> tuple[float, float]:
    return min(point.y for point in token.polygon), max(point.y for point in token.polygon)


def find_receipt_anchors(output: ReceiptOutput) -> dict[str, tuple[ReceiptAnchor, ...]]:
    """Read explicit roles from OCR, with unique B2 row linkage and source ownership."""
    tokens = output.source_evidence.tokens
    order = {token.token_id: index for index, token in enumerate(tokens)}
    bands = {token.token_id: _vertical_band(token) for token in tokens}
    owners = defaultdict(set)
    for field in ordered_fields(output):
        for token_id in field.source_token_ids:
            owners[token_id].add(field.field_id)
    x_ranges = {
        token.token_id: (min(point.x for point in token.polygon),
                         max(point.x for point in token.polygon)) for token in tokens
    }
    row_bands = []
    for row in output.items:
        # Price/quantity boxes define bands when present. A wrapped description can
        # span several display lines and would associate adjacent annotations.
        ids = {token_id for field in row.fields[1:] for token_id in field.source_token_ids}
        ids = ids or set(row.description.source_token_ids)
        row_ids = ids | set(row.description.source_token_ids)
        span = (min(x_ranges[token_id][0] for token_id in row_ids),
                max(x_ranges[token_id][1] for token_id in row_ids))
        row_bands.append((row, tuple(bands[token_id] for token_id in ids), span))
    min_body = min((top for _, boxes, _ in row_bands for top, _ in boxes), default=None)
    max_body = max((bottom for _, boxes, _ in row_bands for _, bottom in boxes), default=None)
    dates = tuple(bands[token_id][0] for token_id in output.purchase_date.source_token_ids)
    if dates:
        min_body = min((*dates, min_body)) if min_body is not None else min(dates)

    result = defaultdict(list)
    for token in tokens:
        if len(token.original_text) > 256:
            continue
        match = _ANCHOR.fullmatch(token.original_text)
        split = match is None
        if split:
            match = _SPLIT_LABEL.fullmatch(token.original_text)
        if match is None:
            continue
        name = next(name for name in _LABELS if match[name.name] is not None)
        if name is not Name.RECEIPT_TOTAL and match["separator"] not in (":", "="):
            continue
        top, bottom = bands[token.token_id]
        if name in ITEM_NUMERIC or name is Name.ITEM_DESCRIPTION:
            center = (top + bottom) / 2
            x0, x1 = x_ranges[token.token_id]
            rows = [
                row for row, boxes, (left, right) in row_bands
                if any(y0 <= center <= y1
                       and max(left - x1, x0 - right) <= 12 * max(bottom - top, y1 - y0)
                       for y0, y1 in boxes)
            ]
            if len(rows) != 1:
                continue
            target = next(field for field in rows[0].fields if field.field_name is name)
        elif name is Name.STORE_NAME:
            if min_body is None or bottom > min_body:
                continue
            target = output.store_name
        else:
            if max_body is None or top < max_body:
                continue
            target = output.receipt_total
        if owners[token.token_id] - {target.field_id}:
            continue

        label_span = None
        if split:
            if name in (Name.STORE_NAME, Name.ITEM_DESCRIPTION):
                continue
            parser = parse_positive_quantity if name is Name.QUANTITY else parse_money
            peers = []
            for body in tokens:
                gap = x_ranges[body.token_id][0] - x_ranges[token.token_id][1]
                y0, y1 = bands[body.token_id]
                if (body is not token and max(top, y0) < min(bottom, y1)
                        and 0 <= gap <= 4 * max(bottom - top, y1 - y0)
                        and parser(body.original_text).state is B3ParseState.VALID):
                    peers.append(body)
            if len(peers) != 1 or owners[peers[0].token_id] - {target.field_id}:
                continue
            body, = peers
            label_span = SourceCharacterSpanV1(token.token_id, 0, len(token.original_text),
                                               token.original_text)
            span = SourceCharacterSpanV1(body.token_id, 0, len(body.original_text), body.original_text)
        else:
            start, end = match.span("value")
            span = SourceCharacterSpanV1(token.token_id, start, end, match["value"])
        displacement = min(
            (abs(order[span.token_id] - order[token_id]) for token_id in target.source_token_ids),
            default=None,
        )
        result[target.field_id].append(ReceiptAnchor(target.field_id, span, displacement, label_span))

    return {key: tuple(values) for key, values in result.items()}


def check_arithmetic(
    output: ReceiptOutput, field: StructuredField, adjustments: tuple[AdjustmentEvidence, ...],
    *, row_index: int | None,
) -> tuple[ArithmeticDiagnostic, ...]:
    """Evaluate a candidate against the frozen B3 equations and exception grammar."""
    if field.field_name not in NUMERIC:
        return ()
    checks = []
    if row_index is not None:
        row = output.items[row_index]
        attribute = field.field_name.value.lower()
        if field is not getattr(row, attribute):
            row = replace(row, **{attribute: field})
        check = _item_arithmetic_diagnostic(output, row, ArithmeticPhase.PRE_CORRECTION, row_index)
        row_ids = {token_id for value in row.fields for token_id in value.source_token_ids}
        if check.outcome is not ArithmeticOutcome.CONFLICTING_CURRENCY_MARKERS and (
            _row_has_promotion(output, row) or any(a.source_slice.token_id in row_ids for a in adjustments)
        ):
            check = replace(
                check, outcome=ArithmeticOutcome.EXPLICIT_PROMOTION_OR_ADJUSTMENT_EXCEPTION,
                message="Promotion or adjustment evidence qualifies the item equation.",
            )
        checks.append(check)
    if field.field_name in (Name.LINE_TOTAL, Name.RECEIPT_TOTAL):
        if field is not (output.receipt_total if row_index is None
                         else output.items[row_index].line_total):
            output = replace_fields(output, {field.field_id: field})
        checks.append(_receipt_arithmetic_diagnostic(
            output, adjustments, ArithmeticPhase.PRE_CORRECTION, len(output.items),
        ))
    return tuple(checks)


def weight_state(output: ReceiptOutput, row_index: int) -> str:
    return _weight_state(output, output.items[row_index])


def has_promotion(output: ReceiptOutput, row_index: int) -> bool:
    return _row_has_promotion(output, output.items[row_index])


def associated_split_date(output, label_token_id):
    """Confirm a split date label against B2's one date value and same-line OCR."""
    field = output.purchase_date
    tokens = {token.token_id: token for token in output.source_evidence.tokens}
    label = tokens[label_token_id]
    label_top, label_bottom = _vertical_band(label)
    label_right = max(point.x for point in label.polygon)
    bodies = []
    for token in tokens.values():
        top, bottom = _vertical_band(token)
        x0 = min(point.x for point in token.polygon)
        if token is label or max(label_top, top) >= min(label_bottom, bottom):
            continue
        if not 0 <= x0 - label_right <= 4 * max(label_bottom - label_top, bottom - top):
            continue
        parsed = parse_generic_date(token.original_text.strip())
        if parsed.state is not B3ParseState.INVALID:
            bodies.append((token, parsed))
    if len(bodies) != 1:
        return None
    (body, parsed), = bodies
    original = parse_generic_date(field.value or "")
    if (field.source_token_ids != (body.token_id,) or parsed.state is not B3ParseState.VALID
            or original.normalized_value != parsed.normalized_value):
        return None
    return label, body

