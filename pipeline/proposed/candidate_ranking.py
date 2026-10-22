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

from pipeline.proposed.candidate_deduplication import (
    CandidateNormalizationV0,
    EquivalentToC0AuditV0,
)
from pipeline.proposed.candidate_identity import (
    AlteredCandidateIdentityDraftV0,
    AlteredCandidateProvenanceAuditV0,
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
    PreliminaryRankV1,
)


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


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")


def _require_nonnegative_int(value: int, name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer.")


def _levenshtein_distance(left: str, right: str) -> int:
    """Return code-point Levenshtein distance using O(min(n, m)) memory."""

    if not isinstance(left, str) or not isinstance(right, str):
        raise TypeError("Levenshtein inputs must be strings.")
    if left == right:
        return 0
    if len(left) < len(right):
        left, right = right, left
    if not right:
        return len(left)

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


def _reduced_similarity(
    c0_text: str, candidate_text: str
) -> tuple[int, int, int, int]:
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
    numerator = maximum_length - distance
    divisor = gcd(numerator, maximum_length)
    return distance, maximum_length, numerator // divisor, maximum_length // divisor


def _decimal_from_fraction(numerator: int, denominator: int) -> Decimal:
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


def _compare_exact_ratios(
    left_numerator: int,
    left_denominator: int,
    right_numerator: int,
    right_denominator: int,
) -> int:
    """Compare two non-negative ratios without Decimal or float rounding."""

    left = left_numerator * right_denominator
    right = right_numerator * left_denominator
    return (left > right) - (left < right)


def _compare_rank_components(
    left: tuple[int, int, int, int, str, str],
    right: tuple[int, int, int, int, str, str],
) -> int:
    """Compare priority, exact similarity, displacement, text and candidate ID."""

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

    def __post_init__(self) -> None:
        if not isinstance(self.theta_a_ref, ConfigurationRefV1):
            raise TypeError("theta_a_ref must be ConfigurationRefV1.")
        if self.theta_a_ref.kind is not ConfigurationKind.THETA_A:
            raise ValueError("Candidate ranking requires a THETA_A reference.")
        if self.theta_a_ref.state is not ConfigurationState.READY:
            raise ValueError("Candidate ranking requires READY THETA_A.")
        _require_text(self.theta_a_ref.content_hash or "", "Theta_A content hash")
        if self.ranking_profile_id != CANDIDATE_RANKING_PROFILE_ID:
            raise ValueError("Unsupported candidate-ranking profile.")
        if self.component_version != CANDIDATE_RANKING_COMPONENT_VERSION:
            raise ValueError("Unsupported candidate-ranking component version.")
        if self.record_version != CANDIDATE_RANKING_RECORD_VERSION:
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

    def __post_init__(self) -> None:
        expected = _reduced_similarity(self.c0_text, self.candidate_text)
        observed = (
            self.edit_distance,
            self.maximum_length,
            self.exact_numerator,
            self.exact_denominator,
        )
        if observed != expected:
            raise CandidateRankingIntegrityError(
                "Edit-similarity audit must equal the exact normalized-text derivation."
            )
        if self.decimal_value != _decimal_from_fraction(*expected[2:]):
            raise CandidateRankingIntegrityError(
                "Similarity Decimal must use the fixed 34-digit private context."
            )
        if self.record_version != EDIT_SIMILARITY_RECORD_VERSION:
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

    def __post_init__(self) -> None:
        if self.source_kind not in _SOURCE_PRIORITY:
            raise ValueError("Displacement audit requires an altered source kind.")
        if not self.c0_token_ids:
            raise CandidateRankingIntegrityError(
                "Displacement requires at least one exact c0 source token."
            )
        if len(self.c0_token_ids) != len(set(self.c0_token_ids)):
            raise ValueError("c0_token_ids must be unique.")
        if len(self.supporting_token_ids) != len(set(self.supporting_token_ids)):
            raise ValueError("supporting_token_ids must be unique.")
        if len(self.supporting_token_ids) != len(self.supporting_token_positions):
            raise ValueError("Supporting token IDs and positions must align.")
        if len(self.c0_token_ids) != len(self.c0_token_positions):
            raise ValueError("c0 token IDs and positions must align.")
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
                expected = min(
                    abs(candidate - original)
                    for candidate in self.supporting_token_positions
                    for original in self.c0_token_positions
                )
                if self.displacement != expected:
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
        if self.record_version != SOURCE_DISPLACEMENT_RECORD_VERSION:
            raise ValueError("Unsupported source-displacement audit version.")


def _source_audit(
    record: AlteredProvenanceRecordV0,
) -> AlteredCandidateProvenanceAuditV0:
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
    return EditSimilarityAuditV0(
        c0_text=c0_text,
        candidate_text=candidate_text,
        edit_distance=distance,
        maximum_length=maximum,
        exact_numerator=numerator,
        exact_denominator=denominator,
        decimal_value=_decimal_from_fraction(numerator, denominator),
    )


def _derive_displacement(
    record: AlteredProvenanceRecordV0,
    best_priority: int,
    token_by_id: dict[str, Any],
    token_position: dict[str, int],
) -> SourceOrderDisplacementAuditV0:
    audit = _source_audit(record)
    method = audit.identity.deduplicated_group.representative.method_ready_field
    if not method.source_token_ids:
        raise CandidateRankingIntegrityError(
            "Permanent c0 has no source-token references for displacement."
        )
    if len(method.source_token_ids) != len(set(method.source_token_ids)):
        raise CandidateRankingIntegrityError("Permanent c0 source tokens repeat.")
    for token_id, source_token in zip(method.source_token_ids, method.source_tokens):
        token = token_by_id.get(token_id)
        if token is None or token != source_token:
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
        return SourceOrderDisplacementAuditV0(
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
        ordered_support: set[str] = set()
        missing_span = False
        for contribution in best_contributions:
            if not contribution.source_spans:
                missing_span = True
            for span in contribution.source_spans:
                token = token_by_id.get(span.token_id)
                if token is None:
                    raise CandidateRankingIntegrityError(
                        f"Unknown original OCR token ID {span.token_id!r}."
                    )
                if token.receipt_id != method.receipt_id:
                    raise CandidateRankingIntegrityError(
                        "Candidate support token belongs to another receipt."
                    )
                if (
                    type(span.start) is not int
                    or type(span.end) is not int
                    or span.start < 0
                    or span.end <= span.start
                    or span.end > len(token.original_text)
                    or span.text != token.original_text[span.start : span.end]
                ):
                    raise CandidateRankingIntegrityError(
                        "Candidate source span contradicts original OCR evidence."
                    )
                ordered_support.add(span.token_id)
        supporting_ids = tuple(
            token_id
            for token_id, _ in sorted(token_position.items(), key=lambda item: item[1])
            if token_id in ordered_support
        )
        supporting_positions = tuple(token_position[item] for item in supporting_ids)
        if missing_span or not supporting_ids:
            return SourceOrderDisplacementAuditV0(
                source_kind=source_kind,
                supporting_token_ids=supporting_ids,
                supporting_token_positions=supporting_positions,
                c0_token_ids=method.source_token_ids,
                c0_token_positions=c0_positions,
                availability=DisplacementAvailabilityV0.UNAVAILABLE,
                displacement=None,
                unavailable_reason=_MISSING_SOURCE_POSITION_REASON,
            )
        displacement = min(
            abs(candidate - original)
            for candidate in supporting_positions
            for original in c0_positions
        )
        return SourceOrderDisplacementAuditV0(
            source_kind=source_kind,
            supporting_token_ids=supporting_ids,
            supporting_token_positions=supporting_positions,
            c0_token_ids=method.source_token_ids,
            c0_token_positions=c0_positions,
            availability=DisplacementAvailabilityV0.AVAILABLE,
            displacement=displacement,
            unavailable_reason=None,
        )

    return SourceOrderDisplacementAuditV0(
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


def _canonical_tie_json(payload: tuple[Any, ...]) -> tuple[str, bytes]:
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


def _tie_identifier(payload: tuple[Any, ...]) -> tuple[str, str]:
    serialized, encoded = _canonical_tie_json(payload)
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

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, CandidateRankingConfigurationV0):
            raise TypeError("configuration must be CandidateRankingConfigurationV0.")
        audit = _source_audit(self.source_record)
        method = audit.identity.deduplicated_group.representative.method_ready_field
        if not isinstance(self.original_normalization, CandidateNormalizationV0):
            raise TypeError("original_normalization must be CandidateNormalizationV0.")
        if (
            self.original_normalization.field_name is not method.field_name
            or self.original_normalization.exact_value != method.c0_value
        ):
            raise CandidateRankingIntegrityError(
                "Original normalization must describe the exact permanent c0 value."
            )
        if self.provenance_status is not _provenance_status(self.source_record):
            raise CandidateRankingIntegrityError(
                "Provenance materialization status contradicts the source partition."
            )
        if self.best_source_priority != _best_source_priority(self.source_record):
            raise CandidateRankingIntegrityError(
                "Recorded source priority contradicts the complete contribution audit."
            )
        if not isinstance(self.similarity, EditSimilarityAuditV0):
            raise TypeError("similarity must be EditSimilarityAuditV0.")
        candidate_text = audit.identity.deduplicated_group.normalization.canonical_value
        expected_similarity = _make_similarity(
            self.original_normalization.canonical_value, candidate_text
        )
        if self.similarity != expected_similarity:
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
        if observed_rank_components != expected_rank_components:
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
                self.tie_identity_payload != expected_payload
                or self.tie_identity_payload_json != expected_json
                or self.preliminary_rank.tie_group_id != expected_id
            ):
                raise CandidateRankingIntegrityError(
                    "Tie-group identity must equal its canonical rank-component payload."
                )
        elif self.preliminary_rank.tie_group_id is not None:
            raise CandidateRankingIntegrityError(
                "A tie-group ID requires its canonical local payload audit."
            )
        if self.component_version != CANDIDATE_RANKING_COMPONENT_VERSION:
            raise ValueError("Unsupported candidate-ranking component version.")
        if self.record_version != CANDIDATE_RANKING_RECORD_VERSION:
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

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, CandidateRankingConfigurationV0):
            raise TypeError("configuration must be CandidateRankingConfigurationV0.")
        audit = _source_audit(self.source_record)
        method = audit.identity.deduplicated_group.representative.method_ready_field
        if not isinstance(self.original_normalization, CandidateNormalizationV0):
            raise TypeError("original_normalization must be CandidateNormalizationV0.")
        if (
            self.original_normalization.field_name is not method.field_name
            or self.original_normalization.exact_value != method.c0_value
        ):
            raise CandidateRankingIntegrityError(
                "Original normalization must describe the exact permanent c0 value."
            )
        if self.provenance_status is not _provenance_status(self.source_record):
            raise CandidateRankingIntegrityError(
                "Blocked rank provenance status contradicts the source partition."
            )
        if self.best_source_priority != _best_source_priority(self.source_record):
            raise CandidateRankingIntegrityError(
                "Blocked rank source priority contradicts the complete audit."
            )
        if not isinstance(self.similarity, EditSimilarityAuditV0):
            raise TypeError("similarity must be EditSimilarityAuditV0.")
        expected_similarity = _make_similarity(
            self.original_normalization.canonical_value,
            audit.identity.deduplicated_group.normalization.canonical_value,
        )
        if self.similarity != expected_similarity:
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
        if (self.reason_code, self.reason) != expected:
            raise CandidateRankingIntegrityError(
                "Ranking-block reason must equal the candidate's derived availability."
            )
        if self.component_version != CANDIDATE_RANKING_COMPONENT_VERSION:
            raise ValueError("Unsupported candidate-ranking component version.")
        if self.record_version != CANDIDATE_RANKING_RECORD_VERSION:
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
        return (
            self.best_source_priority,
            self.similarity.exact_numerator,
            self.similarity.exact_denominator,
            self.displacement.displacement,
        )


def _ordered_source_records(
    provenance_result: CandidateProvenanceMaterializationResultV0,
) -> tuple[AlteredProvenanceRecordV0, ...]:
    by_id: dict[str, AlteredProvenanceRecordV0] = {}
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
    if set(ordered_ids) != set(by_id) or len(ordered_ids) != len(by_id):
        raise CandidateRankingIntegrityError(
            "Every upstream altered identity must occur in one provenance partition."
        )
    return tuple(by_id[candidate_id] for candidate_id in ordered_ids)


def _receipt_context(
    provenance_result: CandidateProvenanceMaterializationResultV0,
) -> tuple[dict[str, Any], dict[str, int]]:
    generation = (
        provenance_result.identity_preparation
        .deduplication_result.candidate_drafts
    )
    output = generation.adapter_result.original_b2_result.receipt_output
    method = generation.original.method_ready_field
    if output is None:
        raise CandidateRankingIntegrityError(
            "Preliminary ranking requires the retained structured B2 receipt output."
        )
    if (
        output.receipt_id != method.receipt_id
        or output.source_evidence.receipt_id != method.receipt_id
    ):
        raise CandidateRankingIntegrityError(
            "Receipt-wide OCR evidence contradicts the method-ready field identity."
        )
    tokens = output.source_evidence.tokens
    token_ids = tuple(token.token_id for token in tokens)
    if len(token_ids) != len(set(token_ids)):
        raise CandidateRankingIntegrityError("Original OCR token IDs must be unique.")
    if any(token.receipt_id != method.receipt_id for token in tokens):
        raise CandidateRankingIntegrityError(
            "Every original OCR token must belong to the ranking receipt."
        )
    return (
        {token.token_id: token for token in tokens},
        {token.token_id: position for position, token in enumerate(tokens)},
    )


def _upstream_theta(
    provenance_result: CandidateProvenanceMaterializationResultV0,
) -> ConfigurationRefV1:
    return (
        provenance_result.identity_preparation
        .deduplication_result.candidate_drafts.suspicion_result.theta_a_ref
    )


def _derive_ranking(
    provenance_result: CandidateProvenanceMaterializationResultV0,
    configuration: CandidateRankingConfigurationV0,
) -> tuple[
    CandidateRankingReadinessV0,
    tuple[RankedAlteredCandidateV0, ...],
    tuple[CandidateRankingBlockV0, ...],
]:
    try:
        provenance_result.__post_init__()
    except (TypeError, ValueError) as exc:
        raise CandidateRankingIntegrityError(
            "Provenance result failed complete upstream reconstruction."
        ) from exc
    if configuration.theta_a_ref != _upstream_theta(provenance_result):
        raise CandidateRankingIntegrityError(
            "Ranking configuration must equal the upstream suspicion Theta_A reference."
        )

    records = _ordered_source_records(provenance_result)
    token_by_id, token_position = _receipt_context(provenance_result)
    original_normalization = (
        provenance_result.identity_preparation.deduplication_result
        .original_normalization
    )
    c0_text = original_normalization.canonical_value
    evaluations: list[_CandidateEvaluation] = []
    for record in records:
        identity = _identity(record)
        candidate_text = identity.deduplicated_group.normalization.canonical_value
        similarity = _make_similarity(c0_text, candidate_text)
        priority = _best_source_priority(record)
        displacement = _derive_displacement(
            record, priority, token_by_id, token_position
        )
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
            for item in sorted(evaluations, key=lambda value: value.identity.candidate_id)
        )
        return CandidateRankingReadinessV0.RANKING_BLOCKED, (), blocks

    ordered = tuple(
        sorted(
            evaluations,
            key=cmp_to_key(
                lambda left, right: _compare_rank_components(
                    left.sort_components, right.sort_components
                )
            ),
        )
    )
    tie_counts: dict[tuple[int, int, int, int], int] = {}
    for item in ordered:
        tie_counts[item.tie_components] = tie_counts.get(item.tie_components, 0) + 1

    payload_by_tie_id: dict[str, str] = {}
    ranked: list[RankedAlteredCandidateV0] = []
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
            if prior is not None and prior != tie_json:
                raise CandidateRankingIntegrityError(
                    "Distinct tie-component payloads produced the same tie-group ID."
                )
            payload_by_tie_id[tie_id] = tie_json
        preliminary = PreliminaryRankV1(
            source_priority_rank=item.best_source_priority,
            normalized_edit_similarity=item.similarity.decimal_value,
            source_order_displacement=item.displacement.displacement,
            normalized_candidate_text=item.normalized_candidate_text,
            rank_position=position,
            tie_group_id=tie_id,
        )
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

    def __post_init__(self) -> None:
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
        if self.component_version != CANDIDATE_RANKING_COMPONENT_VERSION:
            raise ValueError("Unsupported candidate-ranking component version.")
        if self.record_version != CANDIDATE_RANKING_RECORD_VERSION:
            raise ValueError("Unsupported candidate-ranking record version.")
        expected = _derive_ranking(self.provenance_result, self.configuration)
        if (
            self.readiness,
            self.ranked_candidates,
            self.ranking_blocks,
        ) != expected:
            raise CandidateRankingIntegrityError(
                "Ranking result must equal its complete deterministic derivation."
            )
        upstream_ids = {
            item.identity.candidate_id
            for item in self.provenance_result.identity_preparation.altered_candidates
        }
        output_ids = tuple(
            item.identity.candidate_id
            for item in (*self.ranked_candidates, *self.ranking_blocks)
        )
        if len(output_ids) != len(set(output_ids)) or set(output_ids) != upstream_ids:
            raise CandidateRankingIntegrityError(
                "Every altered identity must be accounted for exactly once."
            )


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
    return PreliminaryCandidateRankingResultV0(
        provenance_result=provenance_result,
        configuration=configuration,
        original_candidate=provenance_result.original_candidate,
        equivalent_to_c0=provenance_result.equivalent_to_c0,
        readiness=readiness,
        ranked_candidates=ranked,
        ranking_blocks=blocks,
    )
