"""The ratified S01 sufficiency policy for the generated-only Gate C lane."""

from dataclasses import dataclass
from math import isfinite

from pipeline.contracts import (
    OcrSourceToken,
    Point,
    SourceEvidenceDecision,
    SourceEvidenceGateResult,
    SourceProcessingStatus,
    SourceProvenance,
)
from pipeline.ocr_adapter import AdaptedOcrSource


_POLICY_ID = "GATE_C_SOURCE_GATE_V0"
_POLICY_REVISION = "S01"
_CANONICAL_SHA256 = "488F962428AEFA098DCFA73D435A9711A73E90EEC74FCAA88DB4ECED0C98C72A"
_REASON = "Synthetic source structure was unavailable."
_REASON_MAP = (
    ("NO_RECOGNITION_EVIDENCE", _REASON),
    ("NO_RECEIPT_STRUCTURE", _REASON),
)
_REFUSAL_CODES = frozenset({
    "POLICY_UNAPPROVED",
    "POLICY_INCOMPLETE",
    "INVALID_GATE_ID",
    "SOURCE_BINDING_MISMATCH",
    "UNSUPPORTED_EVIDENCE_STATUS",
    "MALFORMED_SOURCE",
    "EVIDENCE_LIMIT_EXCEEDED",
    "GATE_REASON_CONFLICT",
    "AMBIGUOUS_EVIDENCE",
    "GATE_EXECUTION_FAILED",
})
_MAX_REFUSAL_CODE_LENGTH = max(map(len, _REFUSAL_CODES))
_MAX_TOKENS = 128
_MAX_TEXT_CODEPOINTS = 256
_MAX_TEXT_BYTES = 1_024
_MAX_SOURCE_CODEPOINTS = 16_384
_MAX_SOURCE_TEXT_BYTES = 49_152
_MAX_VERTICES = 8
_MAX_POINTS = 1_024
_WIDTH = 1_100
_HEIGHT = 700
_HEX = frozenset("0123456789abcdef")
_CASE_AND_SEPARATOR = str.maketrans("abcdefghijklmnopqrstuvwxyz\t", "ABCDEFGHIJKLMNOPQRSTUVWXYZ ")
_CONTROL_WORDS = frozenset({
    "RECEIPT", "INVOICE", "TOTAL", "GRAND", "SUB", "SUBTOTAL", "DATE", "PURCHASE",
    "TRANSACTION", "ITEM", "ITEMS", "QTY", "QUANTITY", "PRICE", "AMOUNT", "TAX",
    "CASH", "CHANGE", "TENDERED", "BALANCE", "DISCOUNT", "ROUNDING", "VOUCHER",
    "SERVICE", "PAYMENT", "GST", "SST",
})


@dataclass(frozen=True, slots=True, eq=False)
class GateCSourceGatePolicyV0:
    """A policy record. Evaluation admits only the canonical instance."""

    policy_id: str
    revision: str
    canonical_sha256: str
    reason_map: tuple[tuple[str, str], ...]


GATE_C_SOURCE_GATE_V0 = GateCSourceGatePolicyV0(
    _POLICY_ID, _POLICY_REVISION, _CANONICAL_SHA256, _REASON_MAP
)


class GateCSourceGateRefusal(ValueError):
    """A fixed local refusal with no V0 result."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class _Box:
    left: int | float
    top: int | float
    right: int | float
    bottom: int | float

    @property
    def degenerate(self) -> bool:
        return self.left == self.right or self.top == self.bottom

    def precedes(self, summary: "_Box") -> bool:
        return (
            self.bottom <= summary.top
            and max(self.left, summary.left) < min(self.right, summary.right)
        )


def _matches_literal(value: object, literal: str) -> bool:
    return type(value) is str and len(value) == len(literal) and value == literal


def _validate_policy(policy: GateCSourceGatePolicyV0) -> None:
    if policy is not GATE_C_SOURCE_GATE_V0 or not (
        _matches_literal(policy.policy_id, _POLICY_ID)
        and _matches_literal(policy.revision, _POLICY_REVISION)
        and _matches_literal(policy.canonical_sha256, _CANONICAL_SHA256)
    ):
        raise GateCSourceGateRefusal("POLICY_UNAPPROVED")

    mapping = policy.reason_map
    if type(mapping) is not tuple or len(mapping) != len(_REASON_MAP):
        raise GateCSourceGateRefusal("POLICY_INCOMPLETE")
    for entry, (kind, reason) in zip(mapping, _REASON_MAP):
        if type(entry) is not tuple or len(entry) != 2 or not (
            _matches_literal(entry[0], kind) and _matches_literal(entry[1], reason)
        ):
            raise GateCSourceGateRefusal("POLICY_INCOMPLETE")


def _is_host_identity(value: object, prefix: str) -> bool:
    return (
        type(value) is str
        and len(value) == len(prefix) + 32
        and value.startswith(prefix)
        and all(character in _HEX for character in value[len(prefix):])
    )


def _validate_source_header(source: AdaptedOcrSource) -> None:
    if (
        type(source) is not AdaptedOcrSource
        or type(source.processing_status) is not SourceProcessingStatus
        or type(source.provenance) is not SourceProvenance
    ):
        raise GateCSourceGateRefusal("MALFORMED_SOURCE")

    # Match the P02 host issuer's bounded identifier shape. The invocation
    # owner, which alone has the original attempt, checks ownership by identity.
    if not (
        _is_host_identity(source.receipt_id, "rct-")
        and _is_host_identity(source.image_id, "img-")
    ):
        raise GateCSourceGateRefusal("SOURCE_BINDING_MISMATCH")
    if source.processing_status is not SourceProcessingStatus.OCR_COMPLETED:
        raise GateCSourceGateRefusal("UNSUPPORTED_EVIDENCE_STATUS")


def _coordinate_valid(value: object, upper_edge: int) -> bool:
    if type(value) is int:
        return 0 <= value <= upper_edge
    return type(value) is float and isfinite(value) and 0 <= value <= upper_edge


def _extrema(polygon: tuple[Point, ...]) -> _Box:
    left = top = right = bottom = None
    for point in polygon:
        if (
            type(point) is not Point
            or not _coordinate_valid(point.x, _WIDTH)
            or not _coordinate_valid(point.y, _HEIGHT)
        ):
            raise GateCSourceGateRefusal("MALFORMED_SOURCE")
        x, y = point.x, point.y
        if left is None:
            left = right = x
            top = bottom = y
        else:
            left, right = min(left, x), max(right, x)
            top, bottom = min(top, y), max(bottom, y)
    return _Box(left, top, right, bottom)


def _utf8_length(text: str) -> int:
    try:
        return len(text.encode("utf-8", errors="strict"))
    except UnicodeEncodeError:
        pass
    raise GateCSourceGateRefusal("MALFORMED_SOURCE") from None


def _validate_regions(source: AdaptedOcrSource) -> list[_Box]:
    if type(source.tokens) is not tuple:
        raise GateCSourceGateRefusal("MALFORMED_SOURCE")
    if len(source.tokens) > _MAX_TOKENS:
        raise GateCSourceGateRefusal("EVIDENCE_LIMIT_EXCEEDED")

    boxes = []
    codepoints = utf8_bytes = points = 0
    for ordinal, token in enumerate(source.tokens):
        if type(token) is not OcrSourceToken:
            raise GateCSourceGateRefusal("MALFORMED_SOURCE")
        expected_id = f"{source.receipt_id}:paddleocr:{ordinal:06d}"
        if not (
            _matches_literal(token.receipt_id, source.receipt_id)
            and _matches_literal(token.token_id, expected_id)
        ):
            raise GateCSourceGateRefusal("SOURCE_BINDING_MISMATCH")

        text, polygon, score = token.original_text, token.polygon, token.raw_confidence
        if type(text) is not str or not text or type(polygon) is not tuple or len(polygon) < 3:
            raise GateCSourceGateRefusal("MALFORMED_SOURCE")
        if score is not None and (type(score) is not float or not isfinite(score)):
            raise GateCSourceGateRefusal("MALFORMED_SOURCE")

        text_size, vertices = len(text), len(polygon)
        codepoints += text_size
        points += vertices
        if (
            text_size > _MAX_TEXT_CODEPOINTS
            or codepoints > _MAX_SOURCE_CODEPOINTS
            or vertices > _MAX_VERTICES
            or points > _MAX_POINTS
        ):
            raise GateCSourceGateRefusal("EVIDENCE_LIMIT_EXCEEDED")
        if not text.strip():
            raise GateCSourceGateRefusal("MALFORMED_SOURCE")
        encoded_size = _utf8_length(text)
        utf8_bytes += encoded_size
        if encoded_size > _MAX_TEXT_BYTES or utf8_bytes > _MAX_SOURCE_TEXT_BYTES:
            raise GateCSourceGateRefusal("EVIDENCE_LIMIT_EXCEEDED")

        boxes.append(_extrema(polygon))
    return boxes


def _ascii_letters(word: str) -> bool:
    return word.isascii() and word.isalpha()


def _ascii_digits(word: str) -> bool:
    return word.isascii() and word.isdigit()


def _quantity(word: str) -> bool:
    whole, dot, fraction = word.partition(".")
    return _ascii_digits(whole) and (not dot or _ascii_digits(fraction))


def _amount_end(words: tuple[str, ...], start: int) -> int | None:
    if start < len(words) and words[start] in ("RM", "MYR"):
        start += 1
    if start >= len(words):
        return None
    whole, dot, fraction = words[start].partition(".")
    if (
        dot
        and _ascii_digits(whole)
        and (whole == "0" or whole[0] != "0")
        and len(fraction) == 2
        and _ascii_digits(fraction)
    ):
        return start + 1
    return None


def _summary_head(words: tuple[str, ...]) -> int | None:
    label = 1 if words[0] == "GRAND" else 0
    if label < len(words) and (words[label] == "TOTAL" or words[label].startswith("TOTAL:")):
        return label
    return None


def _complete_summary(words: tuple[str, ...], head: int) -> bool:
    return words[head] in ("TOTAL", "TOTAL:") and _amount_end(words, head + 1) == len(words)


def _full_item(words: tuple[str, ...]) -> bool:
    if words[0] in _CONTROL_WORDS:
        return False
    for index, word in enumerate(words):
        if _ascii_letters(word):
            continue
        if index == 0 or not _quantity(word) or words[index + 1:index + 2] != ("X",):
            return False
        first_end = _amount_end(words, index + 2)
        return first_end is not None and _amount_end(words, first_end) == len(words)
    return False


def _only_plain_words(words: tuple[str, ...]) -> bool:
    # Strip at most one terminal period, solely in the recognition view.
    last_word = words[-1].removesuffix(".")
    return (
        _ascii_letters(last_word)
        and last_word not in _CONTROL_WORDS
        and all(_ascii_letters(word) and word not in _CONTROL_WORDS for word in words[:-1])
    )


def _classify_nonempty(source: AdaptedOcrSource, boxes: list[_Box]) -> str:
    if any(box.degenerate for box in boxes):
        raise GateCSourceGateRefusal("AMBIGUOUS_EVIDENCE")

    heads = 0
    summary = None
    items = []
    words_only = True
    for token, box in zip(source.tokens, boxes):
        words = tuple(word for word in token.original_text.translate(_CASE_AND_SEPARATOR).split(" ") if word)
        # Text normalization removes only ASCII spaces and tabs; a valid
        # nonblank source region always leaves at least one comparison word.
        head = _summary_head(words)
        if head is not None:
            heads += 1
            if _complete_summary(words, head):
                summary = box
        elif _full_item(words):
            items.append(box)
        words_only = words_only and _only_plain_words(words)

    if heads == 1 and summary is not None and items and all(item.precedes(summary) for item in items):
        return "SUFFICIENT"
    if words_only:
        return "NO_RECEIPT_STRUCTURE"
    raise GateCSourceGateRefusal("AMBIGUOUS_EVIDENCE")


def evaluate_gate_c_source_v0(
    *,
    source: AdaptedOcrSource,
    gate_result_id: str,
    policy: GateCSourceGatePolicyV0,
) -> SourceEvidenceGateResult:
    """Evaluate one original source. The caller owns invocation and ID reservation."""
    try:
        _validate_policy(policy)
        if not _is_host_identity(gate_result_id, "gat-"):
            raise GateCSourceGateRefusal("INVALID_GATE_ID")
        _validate_source_header(source)
        boxes = _validate_regions(source)
        classification = _classify_nonempty(source, boxes) if boxes else "NO_RECOGNITION_EVIDENCE"

        if classification == "SUFFICIENT":
            return SourceEvidenceGateResult(
                gate_result_id, source.receipt_id, SourceEvidenceDecision.SUFFICIENT, ()
            )

        for kind, reason in policy.reason_map:
            if kind == classification:
                if any(_matches_literal(token.original_text, reason) for token in source.tokens):
                    raise GateCSourceGateRefusal("GATE_REASON_CONFLICT")
                return SourceEvidenceGateResult(
                    gate_result_id, source.receipt_id, SourceEvidenceDecision.INSUFFICIENT, (reason,)
                )
        raise GateCSourceGateRefusal("POLICY_INCOMPLETE")
    except Exception as error:
        code = "GATE_EXECUTION_FAILED"
        if type(error) is GateCSourceGateRefusal:
            candidate = getattr(error, "code", None)
            if (
                type(candidate) is str
                and len(candidate) <= _MAX_REFUSAL_CODE_LENGTH
                and candidate in _REFUSAL_CODES
            ):
                code = candidate
    # Recreate the safe refusal outside the active handler, without its metadata.
    raise GateCSourceGateRefusal(code) from None
