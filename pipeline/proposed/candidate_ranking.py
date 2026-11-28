"""Deterministic preliminary non-price ranking for altered candidates.

This component consumes the complete provenance-materialization boundary.  It
calculates ranking metadata only; it does not apply ``candidateLimit`` or
construct altered ``CandidateRecordV1`` records.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from enum import Enum
from functools import cmp_to_key
from math import gcd
from typing import Any

from pipeline.contracts import OcrSourceToken, ReceiptOutput, ReceiptSourceEvidence
from pipeline.layout_b2 import B2ExtractionResult
from pipeline.proposed import ranking_replay_meter_v1 as rm
from pipeline.proposed.adapter import ProposedAdapterResultV1
from pipeline.proposed.owned_numeric_producer_v1 import current_owned_numeric_scope_v1

from pipeline.proposed.candidate_deduplication import (
    CandidateDeduplicationResultV0,
    CandidateNormalizationV0,
    EquivalentToC0AuditV0,
)
from pipeline.proposed.candidate_generation import (
    CandidateGenerationResultV0,
    OriginalCandidateDraftV0,
)
from pipeline.proposed.candidate_identity import (
    AlteredCandidateIdentityDraftV0,
    AlteredCandidateProvenanceAuditV0,
    CandidateIdentityPreparationResultV0,
)
from pipeline.proposed.candidate_provenance import (
    AlteredCandidateProvenanceMaterializationV0,
    BlockedAlteredCandidateProvenanceV0,
    CandidateProvenanceMaterializationResultV0,
)
from pipeline.proposed.contracts import (
    CandidateSourceKind,
    CandidateRecordV1,
    ConfigurationKind,
    ConfigurationRefV1,
    ConfigurationState,
    MethodReadyFieldV1,
    PreliminaryRankV1,
)
from pipeline.proposed.suspicion import SuspicionResultV0


CANDIDATE_RANKING_PROFILE_ID = "candidate-preliminary-non-price-rank-v0"
CANDIDATE_RANKING_COMPONENT_VERSION = "candidate-ranking-v0"
CANDIDATE_RANKING_RECORD_VERSION = "candidate-ranking-record-v0"
EDIT_SIMILARITY_RECORD_VERSION = "candidate-edit-similarity-audit-v0"
SOURCE_DISPLACEMENT_RECORD_VERSION = "candidate-source-displacement-audit-v0"
TIE_IDENTITY_SCHEMA_VERSION = "pantryproof-preliminary-rank-tie-id-v1"
TIE_GROUP_ID_PREFIX = "pp:rank:tie:v1:sha256:"
SIMILARITY_DECIMAL_PRECISION = 34

_SOURCE_PRIORITY = {
    CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR: 1,
    CandidateSourceKind.GENERIC_NORMALIZATION: 2,
    CandidateSourceKind.RETAILER_MAPPING: 3,
    CandidateSourceKind.PANTRY_TERMINOLOGY: 4,
}

_MISSING_SOURCE_POSITION_REASON = (
    "A best-priority source/neighbour contribution has no genuine source spans."
)
_UNSUPPORTED_SOURCE_POSITION_REASON = (
    "The best-priority source kind has no approved OCR displacement convention."
)
_AGGREGATE_BLOCKED_REASON = (
    "Definitive rank positions are unavailable because another altered identity "
    "cannot be ranked defensibly."
)


class CandidateRankingIntegrityError(ValueError):
    """Ranking input or output contradicts its retained upstream evidence."""


class ProvenanceMaterializationStatusV0(str, Enum):
    """Whether an altered identity has a complete shared provenance union."""

    MATERIALIZED = "MATERIALIZED"
    BLOCKED = "BLOCKED"


class DisplacementAvailabilityV0(str, Enum):
    """Availability of the prescribed source-order displacement component."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class CandidateRankingReadinessV0(str, Enum):
    """Whether definitive positions exist for the complete altered set."""

    READY = "READY"
    RANKING_BLOCKED = "RANKING_BLOCKED"


class CandidateRankingBlockReasonV0(str, Enum):
    """Why one identity has no definitive preliminary rank position."""

    SOURCE_ORDER_DISPLACEMENT_UNAVAILABLE = (
        "SOURCE_ORDER_DISPLACEMENT_UNAVAILABLE"
    )
    AGGREGATE_BLOCKED_BY_PEER = "AGGREGATE_BLOCKED_BY_PEER"


AlteredProvenanceRecordV0 = (
    AlteredCandidateProvenanceMaterializationV0
    | BlockedAlteredCandidateProvenanceV0
)
_TIE_SHAPE = tuple[str, str, str, str, str, str, str, int, int, int, int]
_SORT_SHAPE = tuple[int, int, int, int, str, str]


def _require_text(value: str, name: str) -> None:
    meter = rm.selected()
    if meter is not None:
        length = meter.text_length(value)
        meter.reserve(max_work_units=1 + length, max_temporary_slots=length)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")


def _require_nonnegative_int(value: int, name: str) -> None:
    meter = rm.selected()
    if meter is not None:
        meter.reserve(max_work_units=1 + meter.int_width(value))
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer.")


@rm.operation
def _levenshtein_distance(left: str, right: str) -> int:
    """Return code-point Levenshtein distance using O(min(n, m)) memory."""

    meter = rm.selected()
    if meter is not None:
        meter.reserve_distance(left, right)
    if not isinstance(left, str) or not isinstance(right, str):
        raise TypeError("Levenshtein inputs must be strings.")
    if left == right:
        return 0
    if len(left) < len(right):
        left, right = right, left
    if not right:
        return len(left)
    return _levenshtein_rows(left, right)


def _levenshtein_rows(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, 1):
        current = [left_index]
        for right_index, right_character in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1]
                    + (left_character != right_character),
                )
            )
        previous = current
    return previous[-1]


@rm.operation
def _reduced_similarity(
    c0_text: str, candidate_text: str
) -> tuple[int, int, int, int]:
    rm.exact(c0_text, str)
    rm.exact(candidate_text, str)
    if not isinstance(c0_text, str) or not c0_text:
        raise CandidateRankingIntegrityError(
            "Normalized c0 comparison text must be nonempty."
        )
    if not isinstance(candidate_text, str) or not candidate_text:
        raise CandidateRankingIntegrityError(
            "Normalized candidate comparison text must be nonempty."
        )
    maximum_length = max(len(c0_text), len(candidate_text))
    distance = _levenshtein_distance(c0_text, candidate_text)
    width = maximum_length.bit_length()
    rm.reserve(max_work_units=(2 * width + 4) * (width + 1) ** 2,
               max_temporary_slots=8)
    numerator = maximum_length - distance
    divisor = gcd(numerator, maximum_length)
    return distance, maximum_length, numerator // divisor, maximum_length // divisor


@rm.operation
def _decimal_from_fraction(numerator: int, denominator: int) -> Decimal:
    meter = rm.selected()
    if meter is not None:
        widths = meter.int_width(numerator) + meter.int_width(denominator)
        meter.reserve(max_divisions=1, max_work_units=1 + widths)
    owned = current_owned_numeric_scope_v1()
    if owned is not None:
        return owned.divide_ratio(numerator=numerator, denominator=denominator)
    _require_nonnegative_int(numerator, "similarity numerator")
    if type(denominator) is not int or denominator <= 0:
        raise ValueError("similarity denominator must be a positive integer.")
    if numerator > denominator:
        raise ValueError("similarity numerator cannot exceed its denominator.")
    context = Context(
        prec=SIMILARITY_DECIMAL_PRECISION,
        rounding=ROUND_HALF_EVEN,
    )
    with localcontext(context):
        return Decimal(numerator) / Decimal(denominator)


@rm.operation
def _compare_exact_ratios(
    left_numerator: int,
    left_denominator: int,
    right_numerator: int,
    right_denominator: int,
) -> int:
    """Compare two non-negative ratios without Decimal or float rounding."""

    meter = rm.selected()
    if meter is not None:
        meter.reserve_ratio(
            left_numerator, left_denominator, right_numerator, right_denominator
        )
    return _compare_ratio_products(
        left_numerator, left_denominator, right_numerator, right_denominator
    )


def _compare_ratio_products(
    left_numerator: int,
    left_denominator: int,
    right_numerator: int,
    right_denominator: int,
) -> int:
    left = left_numerator * right_denominator
    right = right_numerator * left_denominator
    return (left > right) - (left < right)


@rm.operation
def _compare_rank_components(
    left: tuple[int, int, int, int, str, str],
    right: tuple[int, int, int, int, str, str],
) -> int:
    """Compare priority, exact similarity, displacement, text and candidate ID."""

    meter = rm.selected()
    if meter is not None:
        work = 2 * (meter.walk(left, _SORT_SHAPE) + meter.walk(right, _SORT_SHAPE))
        meter.reserve(max_work_units=work, max_comparison_work=work)
    if left[0] != right[0]:
        return -1 if left[0] < right[0] else 1
    ratio_order = _compare_exact_ratios(left[1], left[2], right[1], right[2])
    if ratio_order:
        return -ratio_order  # Descending exact similarity.
    if left[3] != right[3]:
        return -1 if left[3] < right[3] else 1
    if left[4] != right[4]:
        return -1 if left[4] < right[4] else 1
    return (left[5] > right[5]) - (left[5] < right[5])


@dataclass(frozen=True, slots=True)
class CandidateRankingConfigurationV0:
    """Ranking profile structurally bound to the existing READY Theta_A ref."""

    theta_a_ref: ConfigurationRefV1
    ranking_profile_id: str = CANDIDATE_RANKING_PROFILE_ID
    component_version: str = CANDIDATE_RANKING_COMPONENT_VERSION
    record_version: str = CANDIDATE_RANKING_RECORD_VERSION

    @rm.operation
    def __post_init__(self) -> None:
        rm.screen(self, CandidateRankingConfigurationV0)
        if not isinstance(self.theta_a_ref, ConfigurationRefV1):
            raise TypeError("theta_a_ref must be ConfigurationRefV1.")
        if self.theta_a_ref.kind is not ConfigurationKind.THETA_A:
            raise ValueError("Candidate ranking requires a THETA_A reference.")
        if self.theta_a_ref.state is not ConfigurationState.READY:
            raise ValueError("Candidate ranking requires READY THETA_A.")
        _require_text(self.theta_a_ref.content_hash or "", "Theta_A content hash")
        if rm.not_equal(self.ranking_profile_id, CANDIDATE_RANKING_PROFILE_ID):
            raise ValueError("Unsupported candidate-ranking profile.")
        if rm.not_equal(self.component_version, CANDIDATE_RANKING_COMPONENT_VERSION):
            raise ValueError("Unsupported candidate-ranking component version.")
        if rm.not_equal(self.record_version, CANDIDATE_RANKING_RECORD_VERSION):
            raise ValueError("Unsupported candidate-ranking record version.")


@dataclass(frozen=True, slots=True)
class EditSimilarityAuditV0:
    """Exact Levenshtein similarity plus its bounded shared Decimal form."""

    c0_text: str
    candidate_text: str
    edit_distance: int
    maximum_length: int
    exact_numerator: int
    exact_denominator: int
    decimal_value: Decimal
    record_version: str = EDIT_SIMILARITY_RECORD_VERSION

    @rm.operation
    def __post_init__(self) -> None:
        rm.screen(self, EditSimilarityAuditV0)
        rm.reserve(max_temporary_slots=6, max_work_units=6)
        owned = current_owned_numeric_scope_v1()
        if owned is not None:
            owned.require_owned(self.decimal_value)
        expected = _reduced_similarity(self.c0_text, self.candidate_text)
        observed = (
            self.edit_distance,
            self.maximum_length,
            self.exact_numerator,
            self.exact_denominator,
        )
        if rm.not_equal(observed, expected):
            raise CandidateRankingIntegrityError(
                "Edit-similarity audit must equal the exact normalized-text derivation."
            )
        if rm.not_equal(self.decimal_value, _decimal_from_fraction(*expected[2:])):
            raise CandidateRankingIntegrityError(
                "Similarity Decimal must use the fixed 34-digit private context."
            )
        if rm.not_equal(self.record_version, EDIT_SIMILARITY_RECORD_VERSION):
            raise ValueError("Unsupported edit-similarity audit version.")


@dataclass(frozen=True, slots=True)
class SourceOrderDisplacementAuditV0:
    """Receipt-token displacement or an explicit unavailable explanation."""

    source_kind: CandidateSourceKind
    supporting_token_ids: tuple[str, ...]
    supporting_token_positions: tuple[int, ...]
    c0_token_ids: tuple[str, ...]
    c0_token_positions: tuple[int, ...]
    availability: DisplacementAvailabilityV0
    displacement: int | None
    unavailable_reason: str | None
    record_version: str = SOURCE_DISPLACEMENT_RECORD_VERSION

    @rm.operation
    def __post_init__(self) -> None:
        rm.screen(self, SourceOrderDisplacementAuditV0)
        if self.source_kind not in _SOURCE_PRIORITY:
            raise ValueError("Displacement audit requires an altered source kind.")
        if not self.c0_token_ids:
            raise CandidateRankingIntegrityError(
                "Displacement requires at least one exact c0 source token."
            )
        if len(self.c0_token_ids) != len(rm.unique(self.c0_token_ids)):
            raise ValueError("c0_token_ids must be unique.")
        if len(self.supporting_token_ids) != len(rm.unique(self.supporting_token_ids)):
            raise ValueError("supporting_token_ids must be unique.")
        if len(self.supporting_token_ids) != len(self.supporting_token_positions):
            raise ValueError("Supporting token IDs and positions must align.")
        if len(self.c0_token_ids) != len(self.c0_token_positions):
            raise ValueError("c0 token IDs and positions must align.")
        if rm.selected() is not None:
            slots = len(self.supporting_token_positions) + len(self.c0_token_positions)
            rm.reserve(max_temporary_slots=slots, max_work_units=slots)
        for position in (*self.supporting_token_positions, *self.c0_token_positions):
            _require_nonnegative_int(position, "OCR token position")
        if not isinstance(self.availability, DisplacementAvailabilityV0):
            raise TypeError("availability must be DisplacementAvailabilityV0.")

        if self.availability is DisplacementAvailabilityV0.AVAILABLE:
            _require_nonnegative_int(self.displacement, "source-order displacement")
            if self.unavailable_reason is not None:
                raise ValueError("Available displacement has no unavailable reason.")
            if self.source_kind is CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR:
                if not self.supporting_token_ids:
                    raise CandidateRankingIntegrityError(
                        "Available source/neighbour displacement requires support tokens."
                    )
                expected = rm.minimum_displacement(
                    self.supporting_token_positions, self.c0_token_positions
                )
                if rm.not_equal(self.displacement, expected):
                    raise CandidateRankingIntegrityError(
                        "Source/neighbour displacement does not match OCR token order."
                    )
            elif self.source_kind is CandidateSourceKind.GENERIC_NORMALIZATION:
                if self.supporting_token_ids or self.displacement != 0:
                    raise CandidateRankingIntegrityError(
                        "Generic normalization uses only the provisional c0-anchored zero."
                    )
            else:
                raise CandidateRankingIntegrityError(
                    "This source kind has no approved available displacement rule."
                )
        else:
            if self.displacement is not None:
                raise ValueError("Unavailable displacement must remain null.")
            _require_text(self.unavailable_reason or "", "unavailable_reason")
        if rm.not_equal(self.record_version, SOURCE_DISPLACEMENT_RECORD_VERSION):
            raise ValueError("Unsupported source-displacement audit version.")


def _source_audit(
    record: AlteredProvenanceRecordV0,
) -> AlteredCandidateProvenanceAuditV0:
    rm.exact_union(record, AlteredProvenanceRecordV0)
    if not isinstance(
        record,
        (
            AlteredCandidateProvenanceMaterializationV0,
            BlockedAlteredCandidateProvenanceV0,
        ),
    ):
        raise TypeError("Unsupported altered provenance record.")
    return record.source_audit


def _identity(record: AlteredProvenanceRecordV0) -> AlteredCandidateIdentityDraftV0:
    return _source_audit(record).identity


def _provenance_status(
    record: AlteredProvenanceRecordV0,
) -> ProvenanceMaterializationStatusV0:
    if isinstance(record, AlteredCandidateProvenanceMaterializationV0):
        return ProvenanceMaterializationStatusV0.MATERIALIZED
    return ProvenanceMaterializationStatusV0.BLOCKED


def _best_source_priority(record: AlteredProvenanceRecordV0) -> int:
    audit = _source_audit(record)
    if rm.selected() is not None:
        rm.screen(audit, AlteredCandidateProvenanceAuditV0)
        rm.reserve(max_work_units=len(audit.contributions))
    try:
        priority = min(
            _SOURCE_PRIORITY[contribution.source_kind]
            for contribution in audit.contributions
        )
    except KeyError as exc:
        raise CandidateRankingIntegrityError(
            "An altered contribution has no permitted source priority."
        ) from exc
    if isinstance(record, AlteredCandidateProvenanceMaterializationV0):
        meter = rm.selected()
        if meter is not None:
            rm.screen(record, AlteredCandidateProvenanceMaterializationV0)
            # Price the actual operands even if replay receives a forged priority.
            for member in record.members:
                priority_width = meter.int_width(member.provenance.source_priority)
                meter.reserve(max_work_units=1 + 2 * priority_width,
                              max_comparison_work=2 * priority_width)
        shared_priority = min(
            member.provenance.source_priority for member in record.members
        )
        if shared_priority != priority:
            raise CandidateRankingIntegrityError(
                "Shared provenance priority contradicts the complete source audit."
            )
    return priority


def _make_similarity(
    c0_text: str, candidate_text: str
) -> EditSimilarityAuditV0:
    distance, maximum, numerator, denominator = _reduced_similarity(
        c0_text, candidate_text
    )
    _reserve_record(8)
    return EditSimilarityAuditV0(
        c0_text=c0_text,
        candidate_text=candidate_text,
        edit_distance=distance,
        maximum_length=maximum,
        exact_numerator=numerator,
        exact_denominator=denominator,
        decimal_value=_decimal_from_fraction(numerator, denominator),
    )


def _reserve_record(slots: int, count: int = 1) -> None:
    rm.reserve(max_records=count, max_temporary_slots=slots, max_work_units=slots)


def _reserve_slots(slots: int) -> None:
    rm.reserve(max_temporary_slots=slots, max_work_units=slots)


def _displacement_audit(**values) -> SourceOrderDisplacementAuditV0:
    _reserve_record(9)
    return SourceOrderDisplacementAuditV0(**values)


@rm.operation
def _derive_displacement(
    record: AlteredProvenanceRecordV0,
    best_priority: int,
    token_by_id: dict[str, Any],
    token_position: dict[str, int],
) -> SourceOrderDisplacementAuditV0:
    audit = _source_audit(record)
    meter = rm.selected()
    if meter is not None:
        rm.screen(audit, AlteredCandidateProvenanceAuditV0)
        rm.exact(token_by_id, rm.LinearIndex)
        rm.exact(token_position, rm.LinearIndex)
    method = audit.identity.deduplicated_group.representative.method_ready_field
    if not method.source_token_ids:
        raise CandidateRankingIntegrityError(
            "Permanent c0 has no source-token references for displacement."
        )
    if len(method.source_token_ids) != len(rm.unique(method.source_token_ids)):
        raise CandidateRankingIntegrityError("Permanent c0 source tokens repeat.")
    if meter is not None:
        slots = len(method.source_token_ids) + len(audit.contributions)
        meter.reserve(max_temporary_slots=slots, max_work_units=3 * slots)
    for token_id, source_token in zip(method.source_token_ids, method.source_tokens):
        token = token_by_id.get(token_id)
        if token is None or rm.not_equal(token, source_token):
            raise CandidateRankingIntegrityError(
                "Method-ready c0 token references contradict original OCR evidence."
            )
    c0_positions = tuple(token_position[token_id] for token_id in method.source_token_ids)
    best_contributions = tuple(
        contribution
        for contribution in audit.contributions
        if _SOURCE_PRIORITY.get(contribution.source_kind) == best_priority
    )
    source_kind = best_contributions[0].source_kind
    if any(item.source_kind is not source_kind for item in best_contributions):
        raise CandidateRankingIntegrityError(
            "One source priority unexpectedly maps to different source kinds."
        )

    if source_kind is CandidateSourceKind.GENERIC_NORMALIZATION:
        return _displacement_audit(
            source_kind=source_kind,
            supporting_token_ids=(),
            supporting_token_positions=(),
            c0_token_ids=method.source_token_ids,
            c0_token_positions=c0_positions,
            availability=DisplacementAvailabilityV0.AVAILABLE,
            displacement=0,
            unavailable_reason=None,
        )

    if source_kind is CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR:
        ordered_support = set() if meter is None else rm.LinearIndex()
        missing_span = False
        for contribution in best_contributions:
            if meter is not None:
                meter.reserve(max_spans=len(contribution.source_spans),
                              max_work_units=4 * len(contribution.source_spans))
            if not contribution.source_spans:
                missing_span = True
            for span in contribution.source_spans:
                token = token_by_id.get(span.token_id)
                if token is None:
                    if meter is not None:
                        raise CandidateRankingIntegrityError("Unknown original OCR token ID.")
                    raise CandidateRankingIntegrityError(
                        f"Unknown original OCR token ID {span.token_id!r}."
                    )
                if rm.not_equal(token.receipt_id, method.receipt_id):
                    raise CandidateRankingIntegrityError(
                        "Candidate support token belongs to another receipt."
                    )
                if (
                    type(span.start) is not int
                    or type(span.end) is not int
                    or span.start < 0
                    or span.end <= span.start
                    or span.end > len(token.original_text)
                    or rm.not_equal(
                        span.text,
                        rm.slice_text(token.original_text, span.start, span.end),
                    )
                ):
                    raise CandidateRankingIntegrityError(
                        "Candidate source span contradicts original OCR evidence."
                    )
                if meter is None:
                    ordered_support.add(span.token_id)
                else:
                    ordered_support[span.token_id] = None
        if meter is not None:
            meter.reserve(max_temporary_slots=2 * len(token_position),
                          max_work_units=2 * len(token_position))
            # Receipt context inserts tokens in the original ascending order.
            positions = token_position.items()
        else:
            positions = sorted(token_position.items(), key=lambda item: item[1])
        supporting_ids = tuple(
            token_id
            for token_id, _ in positions
            if token_id in ordered_support
        )
        supporting_positions = tuple(token_position[item] for item in supporting_ids)
        if missing_span or not supporting_ids:
            return _displacement_audit(
                source_kind=source_kind,
                supporting_token_ids=supporting_ids,
                supporting_token_positions=supporting_positions,
                c0_token_ids=method.source_token_ids,
                c0_token_positions=c0_positions,
                availability=DisplacementAvailabilityV0.UNAVAILABLE,
                displacement=None,
                unavailable_reason=_MISSING_SOURCE_POSITION_REASON,
            )
        displacement = rm.minimum_displacement(supporting_positions, c0_positions)
        return _displacement_audit(
            source_kind=source_kind,
            supporting_token_ids=supporting_ids,
            supporting_token_positions=supporting_positions,
            c0_token_ids=method.source_token_ids,
            c0_token_positions=c0_positions,
            availability=DisplacementAvailabilityV0.AVAILABLE,
            displacement=displacement,
            unavailable_reason=None,
        )

    return _displacement_audit(
        source_kind=source_kind,
        supporting_token_ids=(),
        supporting_token_positions=(),
        c0_token_ids=method.source_token_ids,
        c0_token_positions=c0_positions,
        availability=DisplacementAvailabilityV0.UNAVAILABLE,
        displacement=None,
        unavailable_reason=_UNSUPPORTED_SOURCE_POSITION_REASON,
    )


def _validate_payload_part(value: Any) -> None:
    if isinstance(value, str):
        return
    if type(value) is int:
        return
    if isinstance(value, tuple):
        for item in value:
            _validate_payload_part(item)
        return
    raise CandidateRankingIntegrityError(
        "Tie identity payloads may contain only strings, integers and tuples."
    )


@rm.operation
def _canonical_tie_json(payload: tuple[Any, ...]) -> tuple[str, bytes]:
    meter = rm.selected()
    if meter is not None:
        size = meter.walk(payload, _TIE_SHAPE, canonical=True)
        meter.reserve(max_canonical_bytes=size, max_temporary_slots=2 * size,
                      max_work_units=3 * size)
    if not isinstance(payload, tuple) or not payload:
        raise CandidateRankingIntegrityError("Tie identity payload must be nonempty.")
    _validate_payload_part(payload)
    try:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        encoded = serialized.encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise CandidateRankingIntegrityError(
            "Tie identity payload requires strict canonical UTF-8."
        ) from exc
    return serialized, encoded


def _sha256_hex(encoded: bytes) -> str:
    return hashlib.sha256(encoded).hexdigest()


def _tie_payload(
    *,
    configuration: CandidateRankingConfigurationV0,
    identity: AlteredCandidateIdentityDraftV0,
    source_priority: int,
    similarity: EditSimilarityAuditV0,
    displacement: int,
) -> tuple[Any, ...]:
    rm.reserve(max_temporary_slots=11, max_work_units=11)
    theta = configuration.theta_a_ref
    assert theta.content_hash is not None
    return (
        TIE_IDENTITY_SCHEMA_VERSION,
        configuration.ranking_profile_id,
        identity.receipt_id,
        identity.field_id,
        theta.configuration_id,
        theta.configuration_version,
        theta.content_hash,
        source_priority,
        similarity.exact_numerator,
        similarity.exact_denominator,
        displacement,
    )


@rm.operation
def _tie_identifier(payload: tuple[Any, ...]) -> tuple[str, str]:
    serialized, encoded = _canonical_tie_json(payload)
    slots = len(TIE_GROUP_ID_PREFIX) + 2 * 64
    rm.reserve(max_hash_calls=1, max_temporary_slots=slots,
               max_work_units=len(encoded) + slots)
    return f"{TIE_GROUP_ID_PREFIX}{_sha256_hex(encoded)}", serialized


@dataclass(frozen=True, slots=True)
class RankedAlteredCandidateV0:
    """One altered identity with a definitive preliminary rank position."""

    source_record: AlteredProvenanceRecordV0
    provenance_status: ProvenanceMaterializationStatusV0
    configuration: CandidateRankingConfigurationV0
    original_normalization: CandidateNormalizationV0
    best_source_priority: int
    similarity: EditSimilarityAuditV0
    displacement: SourceOrderDisplacementAuditV0
    preliminary_rank: PreliminaryRankV1
    tie_identity_payload: tuple[Any, ...] | None = None
    tie_identity_payload_json: str | None = None
    component_version: str = CANDIDATE_RANKING_COMPONENT_VERSION
    record_version: str = CANDIDATE_RANKING_RECORD_VERSION

    @rm.operation
    def __post_init__(self) -> None:
        rm.screen(self, RankedAlteredCandidateV0)
        _reserve_slots(10)
        if not isinstance(self.configuration, CandidateRankingConfigurationV0):
            raise TypeError("configuration must be CandidateRankingConfigurationV0.")
        audit = _source_audit(self.source_record)
        method = audit.identity.deduplicated_group.representative.method_ready_field
        if not isinstance(self.original_normalization, CandidateNormalizationV0):
            raise TypeError("original_normalization must be CandidateNormalizationV0.")
        if (
            self.original_normalization.field_name is not method.field_name
            or rm.not_equal(self.original_normalization.exact_value, method.c0_value)
        ):
            raise CandidateRankingIntegrityError(
                "Original normalization must describe the exact permanent c0 value."
            )
        if self.provenance_status is not _provenance_status(self.source_record):
            raise CandidateRankingIntegrityError(
                "Provenance materialization status contradicts the source partition."
            )
        if rm.not_equal(self.best_source_priority, _best_source_priority(self.source_record)):
            raise CandidateRankingIntegrityError(
                "Recorded source priority contradicts the complete contribution audit."
            )
        if not isinstance(self.similarity, EditSimilarityAuditV0):
            raise TypeError("similarity must be EditSimilarityAuditV0.")
        candidate_text = audit.identity.deduplicated_group.normalization.canonical_value
        expected_similarity = _make_similarity(
            self.original_normalization.canonical_value, candidate_text
        )
        if rm.not_equal(self.similarity, expected_similarity):
            raise CandidateRankingIntegrityError(
                "Similarity must equal the exact c0/candidate normalization derivation."
            )
        if not isinstance(self.displacement, SourceOrderDisplacementAuditV0):
            raise TypeError("displacement must be SourceOrderDisplacementAuditV0.")
        if self.displacement.availability is not DisplacementAvailabilityV0.AVAILABLE:
            raise CandidateRankingIntegrityError(
                "A definitively ranked candidate requires available displacement."
            )
        if not isinstance(self.preliminary_rank, PreliminaryRankV1):
            raise TypeError("preliminary_rank must be PreliminaryRankV1.")
        expected_rank_components = (
            self.best_source_priority,
            self.similarity.decimal_value,
            self.displacement.displacement,
            candidate_text,
        )
        observed_rank_components = (
            self.preliminary_rank.source_priority_rank,
            self.preliminary_rank.normalized_edit_similarity,
            self.preliminary_rank.source_order_displacement,
            self.preliminary_rank.normalized_candidate_text,
        )
        if rm.not_equal(observed_rank_components, expected_rank_components):
            raise CandidateRankingIntegrityError(
                "Shared preliminary rank contradicts exact local ranking evidence."
            )
        has_payload = self.tie_identity_payload is not None
        if has_payload != (self.tie_identity_payload_json is not None):
            raise ValueError("Tie payload and canonical JSON must be jointly present.")
        if has_payload:
            assert self.tie_identity_payload is not None
            assert self.tie_identity_payload_json is not None
            expected_payload = _tie_payload(
                configuration=self.configuration,
                identity=audit.identity,
                source_priority=self.best_source_priority,
                similarity=self.similarity,
                displacement=self.displacement.displacement,
            )
            expected_id, expected_json = _tie_identifier(expected_payload)
            if (
                rm.not_equal(self.tie_identity_payload, expected_payload)
                or rm.not_equal(self.tie_identity_payload_json, expected_json)
                or rm.not_equal(self.preliminary_rank.tie_group_id, expected_id)
            ):
                raise CandidateRankingIntegrityError(
                    "Tie-group identity must equal its canonical rank-component payload."
                )
        elif self.preliminary_rank.tie_group_id is not None:
            raise CandidateRankingIntegrityError(
                "A tie-group ID requires its canonical local payload audit."
            )
        if rm.not_equal(self.component_version, CANDIDATE_RANKING_COMPONENT_VERSION):
            raise ValueError("Unsupported candidate-ranking component version.")
        if rm.not_equal(self.record_version, CANDIDATE_RANKING_RECORD_VERSION):
            raise ValueError("Unsupported candidate-ranking record version.")

    @property
    def identity(self) -> AlteredCandidateIdentityDraftV0:
        return _identity(self.source_record)

    @property
    def source_audit(self) -> AlteredCandidateProvenanceAuditV0:
        return _source_audit(self.source_record)


@dataclass(frozen=True, slots=True)
class CandidateRankingBlockV0:
    """One preserved identity without a definitive aggregate rank position."""

    source_record: AlteredProvenanceRecordV0
    provenance_status: ProvenanceMaterializationStatusV0
    configuration: CandidateRankingConfigurationV0
    original_normalization: CandidateNormalizationV0
    best_source_priority: int
    similarity: EditSimilarityAuditV0
    displacement: SourceOrderDisplacementAuditV0
    reason_code: CandidateRankingBlockReasonV0
    reason: str
    component_version: str = CANDIDATE_RANKING_COMPONENT_VERSION
    record_version: str = CANDIDATE_RANKING_RECORD_VERSION

    @rm.operation
    def __post_init__(self) -> None:
        rm.screen(self, CandidateRankingBlockV0)
        _reserve_slots(5)
        if not isinstance(self.configuration, CandidateRankingConfigurationV0):
            raise TypeError("configuration must be CandidateRankingConfigurationV0.")
        audit = _source_audit(self.source_record)
        method = audit.identity.deduplicated_group.representative.method_ready_field
        if not isinstance(self.original_normalization, CandidateNormalizationV0):
            raise TypeError("original_normalization must be CandidateNormalizationV0.")
        if (
            self.original_normalization.field_name is not method.field_name
            or rm.not_equal(self.original_normalization.exact_value, method.c0_value)
        ):
            raise CandidateRankingIntegrityError(
                "Original normalization must describe the exact permanent c0 value."
            )
        if self.provenance_status is not _provenance_status(self.source_record):
            raise CandidateRankingIntegrityError(
                "Blocked rank provenance status contradicts the source partition."
            )
        if rm.not_equal(self.best_source_priority, _best_source_priority(self.source_record)):
            raise CandidateRankingIntegrityError(
                "Blocked rank source priority contradicts the complete audit."
            )
        if not isinstance(self.similarity, EditSimilarityAuditV0):
            raise TypeError("similarity must be EditSimilarityAuditV0.")
        expected_similarity = _make_similarity(
            self.original_normalization.canonical_value,
            audit.identity.deduplicated_group.normalization.canonical_value,
        )
        if rm.not_equal(self.similarity, expected_similarity):
            raise CandidateRankingIntegrityError(
                "Blocked similarity must equal the exact normalization derivation."
            )
        if not isinstance(self.displacement, SourceOrderDisplacementAuditV0):
            raise TypeError("displacement must be SourceOrderDisplacementAuditV0.")
        if not isinstance(self.reason_code, CandidateRankingBlockReasonV0):
            raise TypeError("reason_code must be CandidateRankingBlockReasonV0.")
        if self.displacement.availability is DisplacementAvailabilityV0.UNAVAILABLE:
            expected = (
                CandidateRankingBlockReasonV0.SOURCE_ORDER_DISPLACEMENT_UNAVAILABLE,
                self.displacement.unavailable_reason,
            )
        else:
            expected = (
                CandidateRankingBlockReasonV0.AGGREGATE_BLOCKED_BY_PEER,
                _AGGREGATE_BLOCKED_REASON,
            )
        if rm.not_equal((self.reason_code, self.reason), expected):
            raise CandidateRankingIntegrityError(
                "Ranking-block reason must equal the candidate's derived availability."
            )
        if rm.not_equal(self.component_version, CANDIDATE_RANKING_COMPONENT_VERSION):
            raise ValueError("Unsupported candidate-ranking component version.")
        if rm.not_equal(self.record_version, CANDIDATE_RANKING_RECORD_VERSION):
            raise ValueError("Unsupported candidate-ranking record version.")

    @property
    def identity(self) -> AlteredCandidateIdentityDraftV0:
        return _identity(self.source_record)

    @property
    def source_audit(self) -> AlteredCandidateProvenanceAuditV0:
        return _source_audit(self.source_record)


@dataclass(frozen=True, slots=True)
class _CandidateEvaluation:
    source_record: AlteredProvenanceRecordV0
    provenance_status: ProvenanceMaterializationStatusV0
    original_normalization: CandidateNormalizationV0
    best_source_priority: int
    similarity: EditSimilarityAuditV0
    displacement: SourceOrderDisplacementAuditV0

    @property
    def identity(self) -> AlteredCandidateIdentityDraftV0:
        return _identity(self.source_record)

    @property
    def normalized_candidate_text(self) -> str:
        return self.identity.deduplicated_group.normalization.canonical_value

    @property
    def sort_components(self) -> tuple[int, int, int, int, str, str]:
        if self.displacement.displacement is None:
            raise CandidateRankingIntegrityError(
                "Unavailable displacement has no definitive sort tuple."
            )
        _reserve_slots(6)
        return (
            self.best_source_priority,
            self.similarity.exact_numerator,
            self.similarity.exact_denominator,
            self.displacement.displacement,
            self.normalized_candidate_text,
            self.identity.candidate_id,
        )

    @property
    def tie_components(self) -> tuple[int, int, int, int]:
        if self.displacement.displacement is None:
            raise CandidateRankingIntegrityError(
                "Unavailable displacement has no definitive tie tuple."
            )
        _reserve_slots(4)
        return (
            self.best_source_priority,
            self.similarity.exact_numerator,
            self.similarity.exact_denominator,
            self.displacement.displacement,
        )


@rm.operation
def _ordered_source_records(
    provenance_result: CandidateProvenanceMaterializationResultV0,
) -> tuple[AlteredProvenanceRecordV0, ...]:
    meter = rm.selected()
    if meter is not None:
        count = (
            len(provenance_result.materialized_candidates)
            + len(provenance_result.blocked_candidates)
        )
        upstream = len(provenance_result.identity_preparation.altered_candidates)
        meter.reserve(max_candidates=count + upstream, max_temporary_slots=count + 2 * upstream,
                      max_work_units=3 * (count + upstream))
    by_id = rm.index()
    for record in (
        *provenance_result.materialized_candidates,
        *provenance_result.blocked_candidates,
    ):
        candidate_id = record.identity.candidate_id
        if candidate_id in by_id:
            raise CandidateRankingIntegrityError(
                "An altered identity occurs in multiple provenance partitions."
            )
        by_id[candidate_id] = record
    ordered_ids = tuple(
        item.identity.candidate_id
        for item in provenance_result.identity_preparation.altered_candidates
    )
    if meter is None:
        different = set(ordered_ids) != set(by_id) or len(ordered_ids) != len(by_id)
    else:
        different = (
            len(ordered_ids) != len(by_id)
            or len(rm.unique(ordered_ids)) != len(by_id)
            or any(key not in by_id for key in ordered_ids)
        )
    if different:
        raise CandidateRankingIntegrityError(
            "Every upstream altered identity must occur in one provenance partition."
        )
    return tuple(by_id[candidate_id] for candidate_id in ordered_ids)


def _generation(
    provenance_result: CandidateProvenanceMaterializationResultV0,
) -> CandidateGenerationResultV0:
    rm.exact(provenance_result, CandidateProvenanceMaterializationResultV0)
    preparation = provenance_result.identity_preparation
    rm.exact(preparation, CandidateIdentityPreparationResultV0)
    deduplication = preparation.deduplication_result
    rm.exact(deduplication, CandidateDeduplicationResultV0)
    generation = deduplication.candidate_drafts
    rm.exact(generation, CandidateGenerationResultV0)
    return generation


@rm.operation
def _receipt_context(
    provenance_result: CandidateProvenanceMaterializationResultV0,
) -> tuple[dict[str, Any] | rm.LinearIndex, dict[str, int] | rm.LinearIndex]:
    generation = _generation(provenance_result)
    adapter = generation.adapter_result
    rm.exact(adapter, ProposedAdapterResultV1)
    b2 = adapter.original_b2_result
    rm.exact(b2, B2ExtractionResult)
    output = b2.receipt_output
    rm.exact(generation.original, OriginalCandidateDraftV0)
    method = generation.original.method_ready_field
    rm.exact(method, MethodReadyFieldV1)
    if output is None:
        raise CandidateRankingIntegrityError(
            "Preliminary ranking requires the retained structured B2 receipt output."
        )
    rm.exact(output, ReceiptOutput)
    rm.exact(output.source_evidence, ReceiptSourceEvidence)
    if (
        rm.not_equal(output.receipt_id, method.receipt_id)
        or rm.not_equal(output.source_evidence.receipt_id, method.receipt_id)
    ):
        raise CandidateRankingIntegrityError(
            "Receipt-wide OCR evidence contradicts the method-ready field identity."
        )
    tokens = output.source_evidence.tokens
    meter = rm.selected()
    if meter is not None:
        rm.exact(tokens, tuple)
        meter.reserve(max_tokens=len(tokens), max_temporary_slots=len(tokens),
                      max_work_units=5 * len(tokens))
        rm.screen(tokens, tuple[OcrSourceToken, ...])
    token_ids = tuple(token.token_id for token in tokens)
    if len(token_ids) != len(rm.unique(token_ids)):
        raise CandidateRankingIntegrityError("Original OCR token IDs must be unique.")
    if any(rm.not_equal(token.receipt_id, method.receipt_id) for token in tokens):
        raise CandidateRankingIntegrityError(
            "Every original OCR token must belong to the ranking receipt."
        )
    if meter is not None:
        by_id, by_position = rm.LinearIndex(), rm.LinearIndex()
        for position, token in enumerate(tokens):
            meter.int_width(position)
            by_id[token.token_id] = token
            by_position[token.token_id] = position
        return by_id, by_position
    return (
        {token.token_id: token for token in tokens},
        {token.token_id: position for position, token in enumerate(tokens)},
    )


def _upstream_theta(
    provenance_result: CandidateProvenanceMaterializationResultV0,
) -> ConfigurationRefV1:
    suspicion = _generation(provenance_result).suspicion_result
    rm.exact(suspicion, SuspicionResultV0)
    return suspicion.theta_a_ref


@rm.operation
def _derive_ranking(
    provenance_result: CandidateProvenanceMaterializationResultV0,
    configuration: CandidateRankingConfigurationV0,
) -> tuple[
    CandidateRankingReadinessV0,
    tuple[RankedAlteredCandidateV0, ...],
    tuple[CandidateRankingBlockV0, ...],
]:
    meter = rm.selected()
    rm.exact(provenance_result, CandidateProvenanceMaterializationResultV0)
    rm.screen(configuration, CandidateRankingConfigurationV0)
    try:
        provenance_result.__post_init__()
    except (TypeError, ValueError) as exc:
        raise CandidateRankingIntegrityError(
            "Provenance result failed complete upstream reconstruction."
        ) from exc
    if rm.not_equal(configuration.theta_a_ref, _upstream_theta(provenance_result)):
        raise CandidateRankingIntegrityError(
            "Ranking configuration must equal the upstream suspicion Theta_A reference."
        )

    records = _ordered_source_records(provenance_result)
    token_by_id, token_position = _receipt_context(provenance_result)
    original_normalization = (
        provenance_result.identity_preparation.deduplication_result
        .original_normalization
    )
    rm.screen(original_normalization, CandidateNormalizationV0)
    c0_text = original_normalization.canonical_value
    evaluations: list[_CandidateEvaluation] = []
    _reserve_slots(4 * len(records))
    for record in records:
        identity = _identity(record)
        candidate_text = identity.deduplicated_group.normalization.canonical_value
        similarity = _make_similarity(c0_text, candidate_text)
        priority = _best_source_priority(record)
        displacement = _derive_displacement(
            record, priority, token_by_id, token_position
        )
        _reserve_record(6)
        evaluations.append(
            _CandidateEvaluation(
                source_record=record,
                provenance_status=_provenance_status(record),
                original_normalization=original_normalization,
                best_source_priority=priority,
                similarity=similarity,
                displacement=displacement,
            )
        )

    if any(
        item.displacement.availability is DisplacementAvailabilityV0.UNAVAILABLE
        for item in evaluations
    ):
        if meter is None:
            blocked_order = sorted(evaluations, key=lambda value: value.identity.candidate_id)
        else:
            blocked_order = rm.sort_selected(
                evaluations,
                lambda left, right: rm.compare_text(left.identity.candidate_id, right.identity.candidate_id),
            )
        _reserve_record(12 * len(evaluations), len(evaluations))
        blocks = tuple(
            CandidateRankingBlockV0(
                source_record=item.source_record,
                provenance_status=item.provenance_status,
                configuration=configuration,
                original_normalization=item.original_normalization,
                best_source_priority=item.best_source_priority,
                similarity=item.similarity,
                displacement=item.displacement,
                reason_code=(
                    CandidateRankingBlockReasonV0.SOURCE_ORDER_DISPLACEMENT_UNAVAILABLE
                    if item.displacement.availability
                    is DisplacementAvailabilityV0.UNAVAILABLE
                    else CandidateRankingBlockReasonV0.AGGREGATE_BLOCKED_BY_PEER
                ),
                reason=(
                    item.displacement.unavailable_reason
                    if item.displacement.availability
                    is DisplacementAvailabilityV0.UNAVAILABLE
                    else _AGGREGATE_BLOCKED_REASON
                ),
            )
            for item in blocked_order
        )
        return CandidateRankingReadinessV0.RANKING_BLOCKED, (), blocks

    def compare(left, right):
        return _compare_rank_components(left.sort_components, right.sort_components)

    _reserve_slots(len(evaluations))
    ordered = tuple(sorted(evaluations, key=cmp_to_key(compare)) if meter is None
                    else rm.sort_selected(evaluations, compare))
    tie_counts = rm.index()
    for item in ordered:
        tie_counts[item.tie_components] = tie_counts.get(item.tie_components, 0) + 1

    payload_by_tie_id = rm.index()
    ranked: list[RankedAlteredCandidateV0] = []
    _reserve_slots(2 * len(ordered))
    for position, item in enumerate(ordered, 1):
        tie_id = None
        tie_payload = None
        tie_json = None
        if tie_counts[item.tie_components] >= 2:
            assert item.displacement.displacement is not None
            tie_payload = _tie_payload(
                configuration=configuration,
                identity=item.identity,
                source_priority=item.best_source_priority,
                similarity=item.similarity,
                displacement=item.displacement.displacement,
            )
            tie_id, tie_json = _tie_identifier(tie_payload)
            prior = payload_by_tie_id.get(tie_id)
            if prior is not None and rm.not_equal(prior, tie_json):
                raise CandidateRankingIntegrityError(
                    "Distinct tie-component payloads produced the same tie-group ID."
                )
            payload_by_tie_id[tie_id] = tie_json
        if meter is not None:
            width = meter.int_width(position)
            text_work = meter.text_length(item.normalized_candidate_text)
            if tie_id is not None:
                text_work += meter.text_length(tie_id)
            numeric_work = meter.owned_weight(item.similarity.decimal_value)
            meter.reserve(max_work_units=2 * (text_work + numeric_work + width),
                          max_temporary_slots=text_work)
        _reserve_record(6)
        preliminary = PreliminaryRankV1(
            source_priority_rank=item.best_source_priority,
            normalized_edit_similarity=item.similarity.decimal_value,
            source_order_displacement=item.displacement.displacement,
            normalized_candidate_text=item.normalized_candidate_text,
            rank_position=position,
            tie_group_id=tie_id,
        )
        _reserve_record(12)
        ranked.append(
            RankedAlteredCandidateV0(
                source_record=item.source_record,
                provenance_status=item.provenance_status,
                configuration=configuration,
                original_normalization=item.original_normalization,
                best_source_priority=item.best_source_priority,
                similarity=item.similarity,
                displacement=item.displacement,
                preliminary_rank=preliminary,
                tie_identity_payload=tie_payload,
                tie_identity_payload_json=tie_json,
            )
        )
    return CandidateRankingReadinessV0.READY, tuple(ranked), ()


@dataclass(frozen=True, slots=True)
class PreliminaryCandidateRankingResultV0:
    """Reconstructable complete ranking or fail-closed blocked aggregate."""

    provenance_result: CandidateProvenanceMaterializationResultV0
    configuration: CandidateRankingConfigurationV0
    original_candidate: CandidateRecordV1
    equivalent_to_c0: EquivalentToC0AuditV0 | None
    readiness: CandidateRankingReadinessV0
    ranked_candidates: tuple[RankedAlteredCandidateV0, ...]
    ranking_blocks: tuple[CandidateRankingBlockV0, ...]
    component_version: str = CANDIDATE_RANKING_COMPONENT_VERSION
    record_version: str = CANDIDATE_RANKING_RECORD_VERSION

    @rm.operation
    def __post_init__(self) -> None:
        meter = rm.selected()
        rm.exact(self, PreliminaryCandidateRankingResultV0)
        rm.exact(self.provenance_result, CandidateProvenanceMaterializationResultV0)
        rm.exact(self.configuration, CandidateRankingConfigurationV0)
        rm.exact(self.readiness, CandidateRankingReadinessV0)
        if meter is not None:
            rm.exact(self.ranked_candidates, tuple)
            rm.exact(self.ranking_blocks, tuple)
            meter.reserve(max_candidates=len(self.ranked_candidates) + len(self.ranking_blocks))
        rm.screen(self.ranked_candidates, tuple[RankedAlteredCandidateV0, ...])
        rm.screen(self.ranking_blocks, tuple[CandidateRankingBlockV0, ...])
        if not isinstance(
            self.provenance_result, CandidateProvenanceMaterializationResultV0
        ):
            raise TypeError(
                "provenance_result must be CandidateProvenanceMaterializationResultV0."
            )
        if not isinstance(self.configuration, CandidateRankingConfigurationV0):
            raise TypeError("configuration must be CandidateRankingConfigurationV0.")
        if self.original_candidate is not self.provenance_result.original_candidate:
            raise CandidateRankingIntegrityError(
                "Permanent c0 must be preserved unchanged and by reference."
            )
        if self.equivalent_to_c0 is not self.provenance_result.equivalent_to_c0:
            raise CandidateRankingIntegrityError(
                "The c0-equivalence audit must be preserved unchanged and by reference."
            )
        if not isinstance(self.readiness, CandidateRankingReadinessV0):
            raise TypeError("readiness must be CandidateRankingReadinessV0.")
        if any(
            not isinstance(item, RankedAlteredCandidateV0)
            for item in self.ranked_candidates
        ):
            raise TypeError("ranked_candidates contains an unsupported record.")
        if any(
            not isinstance(item, CandidateRankingBlockV0)
            for item in self.ranking_blocks
        ):
            raise TypeError("ranking_blocks contains an unsupported record.")
        if rm.not_equal(self.component_version, CANDIDATE_RANKING_COMPONENT_VERSION):
            raise ValueError("Unsupported candidate-ranking component version.")
        if rm.not_equal(self.record_version, CANDIDATE_RANKING_RECORD_VERSION):
            raise ValueError("Unsupported candidate-ranking record version.")
        expected = _derive_ranking(self.provenance_result, self.configuration)
        _reserve_slots(3)
        observed = self.readiness, self.ranked_candidates, self.ranking_blocks
        if rm.not_equal(observed, expected):
            raise CandidateRankingIntegrityError(
                "Ranking result must equal its complete deterministic derivation."
            )
        if meter is not None:
            size = len(self.ranked_candidates) + len(self.ranking_blocks)
            inputs = len(self.provenance_result.identity_preparation.altered_candidates)
            meter.reserve(max_candidates=inputs)
            _reserve_slots(3 * size + inputs)
        upstream_ids = (
            item.identity.candidate_id
            for item in self.provenance_result.identity_preparation.altered_candidates
        )
        upstream_ids = set(upstream_ids) if meter is None else tuple(upstream_ids)
        output_ids = tuple(
            item.identity.candidate_id
            for item in (*self.ranked_candidates, *self.ranking_blocks)
        )
        duplicate = len(output_ids) != len(rm.unique(output_ids))
        if not duplicate:
            different = (
                set(output_ids) != upstream_ids if meter is None
                else rm.different_keys(output_ids, upstream_ids)
            )
        if duplicate or different:
            raise CandidateRankingIntegrityError(
                "Every altered identity must be accounted for exactly once."
            )


@rm.operation
def compute_preliminary_candidate_ranking(
    *,
    provenance_result: CandidateProvenanceMaterializationResultV0,
    configuration: CandidateRankingConfigurationV0,
) -> PreliminaryCandidateRankingResultV0:
    """Compute the complete altered-candidate rank or an explicit blocked state."""

    if not isinstance(
        provenance_result, CandidateProvenanceMaterializationResultV0
    ):
        raise TypeError(
            "provenance_result must be CandidateProvenanceMaterializationResultV0."
        )
    if not isinstance(configuration, CandidateRankingConfigurationV0):
        raise TypeError("configuration must be CandidateRankingConfigurationV0.")
    readiness, ranked, blocks = _derive_ranking(provenance_result, configuration)
    _reserve_record(9)
    return PreliminaryCandidateRankingResultV0(
        provenance_result=provenance_result,
        configuration=configuration,
        original_candidate=provenance_result.original_candidate,
        equivalent_to_c0=provenance_result.equivalent_to_c0,
        readiness=readiness,
        ranked_candidates=ranked,
        ranking_blocks=blocks,
    )
