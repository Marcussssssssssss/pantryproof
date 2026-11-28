"""Proposed source-bound LIVE gate. Operational approval is disabled."""

from hashlib import sha256
import json
from math import isfinite

from pipeline import layout_b2 as b2
from pipeline.contracts import (
    OcrSourceToken, Point, SourceEvidenceDecision, SourceEvidenceGateResult,
    SourceProcessingStatus, SourceProvenance,
)
from pipeline.gate_c_source_gate_v0 import (
    _CASE_AND_SEPARATOR, _is_host_identity, _only_plain_words,
)
from pipeline.ocr_adapter import AdaptedOcrSource
from pipeline.presentation_v1.b2_synthetic_projection_v0 import _ORIGINAL_MONEY
from pipeline.presentation_v1.local_image_projection_v0 import (
    LOCAL_IMAGE_SOURCE_SYSTEM, LiveGateApprovalV0, LocalImagePresentationContextV0,
    RetainedLiveGateV0,
)


MAX_IMAGE_EDGE = 8192
MAX_IMAGE_PIXELS = 20_000_000
MAX_REGIONS = 128
MAX_REGION_CODEPOINTS = 256
MAX_REGION_UTF8_BYTES = 1024
MAX_OCR_CODEPOINTS = 16_384
MAX_OCR_UTF8_BYTES = 49_152
MAX_VERTICES = 8
MAX_POINTS = 1024

PUBLIC_INSUFFICIENCY_REASON = "Receipt structure was unavailable."

# This compact sorted JSON is the reviewable digest preimage. Bounds and B2
# geometry literals are asserted against their actual dependencies below.
_POLICY = {
    "id": "GATE_C_LIVE_SOURCE_GATE_V0",
    "revision": "T10-P01",
    "source": "ANDROID_LOCAL_IMAGE",
    "bounds": [8192, 20_000_000, 128, 256, 1024, 16_384, 49_152, 8, 1024],
    "geometry": [0.50, 0.50, 0.10, 8.0, 0.70, 1e-9, 0.50],
    "geometry_order": ["vertical_overlap_min", "center_distance_max", "overlap_ambiguity",
                       "gap_median_height_factor", "gap_envelope_width_factor", "epsilon",
                       "total_footer_min"],
    "bounds_order": ["side", "pixels", "regions", "region_chars", "region_utf8",
                     "total_chars", "total_utf8", "vertices_per_region", "total_vertices"],
    "binding": "Exact retained adapted source; reserved rct/gat IDs, image ID, Android source system and opaque source alias; OCR_COMPLETED only.",
    "validation": "Strict adapter token IDs in ordinal order; UTF-8 text; finite numeric confidence in [0,1] or null; 3 to 8 points in the closed image rectangle.",
    "grouping": "B2 layout graph, no extraction; degenerate region, ambiguous visual line or multiple explicit total anchors refuse.",
    "sufficient": "Exactly one complete TOTAL or GRAND TOTAL line in the B2 footer zone; at least one full B2 multiplier item; all such items above and horizontally overlapping total; amounts in V1 MYR lexical grammar.",
    "unsupported": "Refuse other layouts, including incomplete totals, freestanding amounts and non-control item-like lines outside the full multiplier grammar.",
    "insufficient": "Completed empty recognition or every unambiguous visual line consists of generated Gate C plain ASCII words with no control words and optional final period.",
    "public_reason": "Receipt structure was unavailable.",
    "reason_conflict": "Refuse if the public reason equals any original OCR region text.",
}
LIVE_POLICY_CANONICAL_BYTES = json.dumps(
    _POLICY, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False,
).encode("ascii")
PROPOSED_LIVE_GATE_V0 = LiveGateApprovalV0(
    _POLICY["id"], _POLICY["revision"], sha256(LIVE_POLICY_CANONICAL_BYTES).hexdigest(),
    (PUBLIC_INSUFFICIENCY_REASON,),
)

# No public setter or fallback to the generated-only approval.
_APPROVED_POLICY_SHA256: str | None = None
_GROCERY_POLICY = {
    **_POLICY,
    "id": "GATE_C_LIVE_GROCERY_V1",
    "revision": "1",
    "grouping": "B2 visual lines without extraction. Ignore ambiguous lines for positive cues.",
    "sufficient": "At least one unambiguous complete MYR total or supported B2 item cue.",
    "unsupported": "Malformed evidence, binding defects and grouping execution failures are technical failures.",
    "insufficient": "Completed OCR without a trustworthy positive cue.",
}
GROCERY_POLICY_CANONICAL_BYTES = json.dumps(
    _GROCERY_POLICY, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False,
).encode("ascii")
GROCERY_LIVE_GATE_V1 = LiveGateApprovalV0(
    _GROCERY_POLICY["id"], _GROCERY_POLICY["revision"],
    sha256(GROCERY_POLICY_CANONICAL_BYTES).hexdigest(), (PUBLIC_INSUFFICIENCY_REASON,),
)
_APPROVED_GROCERY_POLICY_SHA256: str | None = None


class LiveSourceGateRefusal(ValueError):
    """A fixed internal refusal code with no OCR text."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def require_approved_live_policy_v0(policy: LiveGateApprovalV0 | None) -> None:
    if policy is GROCERY_LIVE_GATE_V1:
        expected, approved, payload, record = (
            GROCERY_LIVE_GATE_V1, _APPROVED_GROCERY_POLICY_SHA256, GROCERY_POLICY_CANONICAL_BYTES, _GROCERY_POLICY,
        )
    else:
        expected, approved, payload, record = (
            PROPOSED_LIVE_GATE_V0, _APPROVED_POLICY_SHA256, LIVE_POLICY_CANONICAL_BYTES, _POLICY,
        )
    if (
        policy is not expected
        or approved != expected.policy_sha256
        or sha256(payload).hexdigest() != policy.policy_sha256
        or policy.policy_id != record["id"]
        or policy.revision != record["revision"]
        or policy.public_reasons != (PUBLIC_INSUFFICIENCY_REASON,)
    ):
        raise LiveSourceGateRefusal("LIVE_POLICY_UNAPPROVED")
    bounds = (
        MAX_IMAGE_EDGE, MAX_IMAGE_PIXELS, MAX_REGIONS, MAX_REGION_CODEPOINTS,
        MAX_REGION_UTF8_BYTES, MAX_OCR_CODEPOINTS, MAX_OCR_UTF8_BYTES, MAX_VERTICES, MAX_POINTS,
    )
    geometry = (
        b2.LINE_MIN_VERTICAL_OVERLAP, b2.LINE_MAX_CENTER_DISTANCE,
        b2.HORIZONTAL_OVERLAP_AMBIGUITY, b2.HORIZONTAL_ADJACENCY_MAX_GAP_HEIGHTS,
        b2.HORIZONTAL_ADJACENCY_MAX_GAP_WIDTH_FRACTION, b2.NUMERIC_TIE_EPSILON,
        b2.TOTAL_ZONE_MIN_NORMALIZED_Y,
    )
    if tuple(record["bounds"]) != bounds or tuple(record["geometry"]) != geometry:
        raise LiveSourceGateRefusal("LIVE_POLICY_DEPENDENCY_CHANGED")


def check_image_dimensions_v0(width: int, height: int) -> None:
    if (
        type(width) is not int or type(height) is not int
        or not 1 <= width <= MAX_IMAGE_EDGE or not 1 <= height <= MAX_IMAGE_EDGE
        or width * height > MAX_IMAGE_PIXELS
    ):
        raise LiveSourceGateRefusal("IMAGE_DIMENSIONS_INVALID")


def _bounded_number(value: object, maximum: int) -> bool:
    return type(value) in (int, float) and 0 <= value <= maximum and isfinite(value)


def validate_ocr_texts_v0(texts: tuple[str, ...]) -> None:
    if len(texts) > MAX_REGIONS:
        raise LiveSourceGateRefusal("EVIDENCE_LIMIT_EXCEEDED")
    codepoints = utf8_bytes = 0
    for text in texts:
        if type(text) is not str or not text:
            raise LiveSourceGateRefusal("MALFORMED_EVIDENCE")
        if len(text) > MAX_REGION_CODEPOINTS:
            raise LiveSourceGateRefusal("EVIDENCE_LIMIT_EXCEEDED")
        if not text.strip():
            raise LiveSourceGateRefusal("MALFORMED_EVIDENCE")
        try:
            byte_count = len(text.encode("utf-8"))
        except UnicodeEncodeError:
            byte_count = None
        if byte_count is None:
            raise LiveSourceGateRefusal("MALFORMED_EVIDENCE")
        codepoints += len(text)
        utf8_bytes += byte_count
        if (byte_count > MAX_REGION_UTF8_BYTES or codepoints > MAX_OCR_CODEPOINTS
                or utf8_bytes > MAX_OCR_UTF8_BYTES):
            raise LiveSourceGateRefusal("EVIDENCE_LIMIT_EXCEEDED")


def _validate_source(source, context, gate_result_id, width, height) -> None:
    check_image_dimensions_v0(width, height)
    if (
        type(source) is not AdaptedOcrSource or type(source.provenance) is not SourceProvenance
        or source.receipt_id != context.receipt_id or source.image_id != context.image_id
        or not _is_host_identity(source.receipt_id, "rct-")
        or not _is_host_identity(gate_result_id, "gat-")
        or source.provenance.source_system != LOCAL_IMAGE_SOURCE_SYSTEM
        or source.provenance.source_reference != context.source_reference
    ):
        raise LiveSourceGateRefusal("SOURCE_BINDING_MISMATCH")
    if source.processing_status is not SourceProcessingStatus.OCR_COMPLETED:
        raise LiveSourceGateRefusal("OCR_NOT_COMPLETED")
    if type(source.tokens) is not tuple:
        raise LiveSourceGateRefusal("MALFORMED_EVIDENCE")
    if len(source.tokens) > MAX_REGIONS:
        raise LiveSourceGateRefusal("EVIDENCE_LIMIT_EXCEEDED")

    total_points = 0
    for index, token in enumerate(source.tokens):
        if (
            type(token) is not OcrSourceToken or token.receipt_id != source.receipt_id
            or token.token_id != f"{source.receipt_id}:paddleocr:{index:06d}"
            or type(token.polygon) is not tuple or len(token.polygon) < 3
            or (token.raw_confidence is not None and not _bounded_number(token.raw_confidence, 1))
        ):
            raise LiveSourceGateRefusal("MALFORMED_EVIDENCE")
        total_points += len(token.polygon)
        if len(token.polygon) > MAX_VERTICES or total_points > MAX_POINTS:
            raise LiveSourceGateRefusal("EVIDENCE_LIMIT_EXCEEDED")
        for point in token.polygon:
            if (
                type(point) is not Point or not _bounded_number(point.x, width)
                or not _bounded_number(point.y, height)
            ):
                raise LiveSourceGateRefusal("MALFORMED_EVIDENCE")
        if (
            len({point.x for point in token.polygon}) < 2
            or len({point.y for point in token.polygon}) < 2
        ):
            raise LiveSourceGateRefusal("AMBIGUOUS_EVIDENCE")
    validate_ocr_texts_v0(tuple(token.original_text for token in source.tokens))


def _plain_words(text: str) -> bool:
    words = tuple(part for part in text.translate(_CASE_AND_SEPARATOR).split(" ") if part)
    return bool(words) and _only_plain_words(words)


def _precedes(item, total) -> bool:
    return item.bottom <= total.top and max(item.left, total.left) < min(item.right, total.right)


def _has_receipt_structure(tokens: tuple[OcrSourceToken, ...]) -> bool:
    if not tokens:
        return False
    lines = b2._build_layout_graph(tokens).lines
    totals = tuple(line for line in lines if b2._ANY_TOTAL_ANCHOR_RE.match(line.text))
    if any(line.ambiguous for line in lines) or len(totals) > 1:
        raise LiveSourceGateRefusal("AMBIGUOUS_EVIDENCE")
    if not totals and all(_plain_words(line.text) for line in lines):
        return False
    if not totals:
        raise LiveSourceGateRefusal("UNSUPPORTED_LAYOUT")
    (total,) = totals
    amount = b2._TOTAL_ANCHOR_RE.fullmatch(total.text)
    if (
        amount is None or _ORIGINAL_MONEY.fullmatch(amount["amount"]) is None
        or total.normalized_center_y + b2.NUMERIC_TIE_EPSILON < b2.TOTAL_ZONE_MIN_NORMALIZED_Y
    ):
        raise LiveSourceGateRefusal("UNSUPPORTED_LAYOUT")

    found_item = False
    for line in lines:
        if line is total or b2._is_control_line(line.text) or b2._is_column_header(line.text):
            continue
        item = b2._FULL_ITEM_RE.fullmatch(line.text)
        if item is not None:
            if (
                not b2._valid_description(item["description"])
                or _ORIGINAL_MONEY.fullmatch(item["unit_price"]) is None
                or _ORIGINAL_MONEY.fullmatch(item["line_total"]) is None
            ):
                raise LiveSourceGateRefusal("UNSUPPORTED_LAYOUT")
            if not _precedes(line, total):
                raise LiveSourceGateRefusal("AMBIGUOUS_EVIDENCE")
            found_item = True
        elif b2._looks_like_item(line) or b2._AMOUNT_FIND_RE.search(line.text):
            raise LiveSourceGateRefusal("UNSUPPORTED_LAYOUT")
    if not found_item:
        raise LiveSourceGateRefusal("UNSUPPORTED_LAYOUT")
    return True


def _has_grocery_cue(tokens: tuple[OcrSourceToken, ...]) -> bool:
    if not tokens:
        return False
    for line in b2._build_layout_graph(tokens).lines:
        if line.ambiguous:
            continue
        total = b2._TOTAL_ANCHOR_RE.fullmatch(line.text)
        if total is not None and _ORIGINAL_MONEY.fullmatch(total["amount"]):
            return True
        if b2._is_control_line(line.text) or b2._is_column_header(line.text):
            continue
        whole = b2._UNMARKED_WHOLE_ITEM_RE.fullmatch(line.text)
        if whole is not None and b2._valid_description(whole["description"]) and all(
            _ORIGINAL_MONEY.fullmatch(whole[name]) for name in ("first_amount", "second_amount")
        ):
            return True
        if b2._looks_like_item(line):
            return True
    return False


def evaluate_live_source_gate_v0(
    *,
    context: LocalImagePresentationContextV0,
    source: AdaptedOcrSource,
    gate_result_id: str,
    image_width: int,
    image_height: int,
) -> RetainedLiveGateV0:
    """Evaluate the caller-retained source without running B2 extraction."""

    if type(context) is not LocalImagePresentationContextV0:
        raise LiveSourceGateRefusal("SOURCE_BINDING_MISMATCH")
    policy = context.approved_gate
    require_approved_live_policy_v0(policy)
    _validate_source(source, context, gate_result_id, image_width, image_height)
    if any(token.original_text == PUBLIC_INSUFFICIENCY_REASON for token in source.tokens):
        raise LiveSourceGateRefusal("GATE_REASON_CONFLICT")
    cue = _has_grocery_cue if policy is GROCERY_LIVE_GATE_V1 else _has_receipt_structure
    if cue(source.tokens):
        decision, reasons = SourceEvidenceDecision.SUFFICIENT, ()
    else:
        decision, reasons = SourceEvidenceDecision.INSUFFICIENT, (PUBLIC_INSUFFICIENCY_REASON,)
    result = SourceEvidenceGateResult(gate_result_id, source.receipt_id, decision, reasons)
    return RetainedLiveGateV0(policy, source, result)
