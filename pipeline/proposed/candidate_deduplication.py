"""Field-compatible normalization and local candidate-draft deduplication.

This bounded component consumes one validated ``CandidateGenerationResultV0``.
It computes separate canonical keys while preserving permanent B2 c0 and every
raw altered proposal.  It deliberately does not rank, limit, constrain, score,
or materialize shared candidate records.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from pipeline.baseline_b3 import (
    B3ParseState,
    RULESET_ID as B3_RULESET_ID,
    normalize_receipt_text,
    parse_generic_date,
    parse_money,
    parse_positive_quantity,
)
from pipeline.contracts import ReceiptFieldName
from pipeline.proposed.candidate_generation import (
    AlteredCandidateProposalV0,
    CandidateGenerationResultV0,
)
from pipeline.proposed.contracts import CandidateSourceKind


NORMALIZATION_PROFILE_ID = "candidate-field-normalization-v0"
CANDIDATE_DEDUPLICATION_VERSION = "candidate-deduplication-v0"
CANDIDATE_DEDUPLICATION_RECORD_VERSION = "candidate-deduplication-record-v0"
B3_NORMALIZATION_DEPENDENCY = B3_RULESET_ID

_TEXT_FIELDS = {
    ReceiptFieldName.STORE_NAME,
    ReceiptFieldName.ITEM_DESCRIPTION,
}
_MONEY_FIELDS = {
    ReceiptFieldName.UNIT_PRICE,
    ReceiptFieldName.LINE_TOTAL,
    ReceiptFieldName.RECEIPT_TOTAL,
}
_SOURCE_PRIORITY = {
    CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR: 1,
    CandidateSourceKind.GENERIC_NORMALIZATION: 2,
    CandidateSourceKind.RETAILER_MAPPING: 3,
    CandidateSourceKind.PANTRY_TERMINOLOGY: 4,
}


class CandidateDeduplicationIntegrityError(ValueError):
    """A reconstructed record differs from its canonical upstream derivation."""


class NormalizationParseStatusV0(str, Enum):
    """How a field-compatible key was obtained."""

    TEXT_NORMALIZED = "TEXT_NORMALIZED"
    PARSED_VALID = "PARSED_VALID"
    PARSE_AMBIGUOUS_FALLBACK = "PARSE_AMBIGUOUS_FALLBACK"
    PARSE_INVALID_FALLBACK = "PARSE_INVALID_FALLBACK"


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")


def _key(*parts: str) -> str:
    """Serialize a canonical key without delimiter or Unicode ambiguity."""

    return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))


def _fallback_key(
    field_name: ReceiptFieldName,
    tag: str,
    exact_value: str,
) -> tuple[str, str]:
    normalized = normalize_receipt_text(exact_value)
    return normalized, _key(
        NORMALIZATION_PROFILE_ID,
        field_name.value,
        tag,
        normalized,
    )


def _derive_normalization(
    field_name: ReceiptFieldName,
    exact_value: str,
) -> tuple[str, str, NormalizationParseStatusV0]:
    if field_name in _TEXT_FIELDS:
        normalized = normalize_receipt_text(exact_value)
        return (
            normalized,
            _key(
                NORMALIZATION_PROFILE_ID,
                field_name.value,
                "TEXT",
                normalized,
            ),
            NormalizationParseStatusV0.TEXT_NORMALIZED,
        )

    if field_name is ReceiptFieldName.PURCHASE_DATE:
        parsed = parse_generic_date(exact_value)
        if parsed.state is B3ParseState.VALID:
            assert parsed.normalized_value is not None
            return (
                parsed.normalized_value,
                _key(
                    NORMALIZATION_PROFILE_ID,
                    field_name.value,
                    "DATE_VALID",
                    parsed.normalized_value,
                ),
                NormalizationParseStatusV0.PARSED_VALID,
            )
        tag = (
            "DATE_AMBIGUOUS_TEXT"
            if parsed.state is B3ParseState.AMBIGUOUS
            else "DATE_INVALID_TEXT"
        )
        canonical, key = _fallback_key(field_name, tag, exact_value)
        status = (
            NormalizationParseStatusV0.PARSE_AMBIGUOUS_FALLBACK
            if parsed.state is B3ParseState.AMBIGUOUS
            else NormalizationParseStatusV0.PARSE_INVALID_FALLBACK
        )
        return canonical, key, status

    if field_name is ReceiptFieldName.QUANTITY:
        parsed = parse_positive_quantity(exact_value)
        if parsed.state is B3ParseState.VALID:
            assert parsed.normalized_value is not None
            return (
                parsed.normalized_value,
                _key(
                    NORMALIZATION_PROFILE_ID,
                    field_name.value,
                    "QUANTITY_VALID",
                    parsed.normalized_value,
                ),
                NormalizationParseStatusV0.PARSED_VALID,
            )
        canonical, key = _fallback_key(
            field_name, "QUANTITY_INVALID_TEXT", exact_value
        )
        return canonical, key, NormalizationParseStatusV0.PARSE_INVALID_FALLBACK

    if field_name in _MONEY_FIELDS:
        parsed = parse_money(exact_value)
        if parsed.state is B3ParseState.VALID:
            assert parsed.normalized_value is not None
            if parsed.currency_marker in {"RM", "MYR"}:
                currency_group = "MYR"
            elif parsed.currency_marker == "$":
                currency_group = "USD_SYMBOL"
            else:
                currency_group = "NO_CURRENCY"
            canonical = f"{currency_group}:{parsed.normalized_value}"
            return (
                canonical,
                _key(
                    NORMALIZATION_PROFILE_ID,
                    field_name.value,
                    "MONEY_VALID",
                    currency_group,
                    parsed.normalized_value,
                ),
                NormalizationParseStatusV0.PARSED_VALID,
            )
        canonical, key = _fallback_key(field_name, "MONEY_INVALID_TEXT", exact_value)
        return canonical, key, NormalizationParseStatusV0.PARSE_INVALID_FALLBACK

    raise ValueError(f"Unsupported receipt field for normalization: {field_name!r}.")


@dataclass(frozen=True, slots=True)
class CandidateNormalizationV0:
    """A separate canonical key for one exact candidate value."""

    field_name: ReceiptFieldName
    exact_value: str
    canonical_value: str
    normalized_key: str
    parse_status: NormalizationParseStatusV0
    profile_id: str = NORMALIZATION_PROFILE_ID
    b3_dependency: str = B3_NORMALIZATION_DEPENDENCY
    record_version: str = CANDIDATE_DEDUPLICATION_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.field_name, ReceiptFieldName):
            raise TypeError("field_name must be ReceiptFieldName.")
        _require_text(self.exact_value, "exact_value")
        if not isinstance(self.parse_status, NormalizationParseStatusV0):
            raise TypeError("parse_status must be NormalizationParseStatusV0.")
        expected = _derive_normalization(self.field_name, self.exact_value)
        if (self.canonical_value, self.normalized_key, self.parse_status) != expected:
            raise CandidateDeduplicationIntegrityError(
                "Normalization output must equal the canonical field derivation."
            )
        if self.profile_id != NORMALIZATION_PROFILE_ID:
            raise ValueError("Unsupported normalization profile.")
        if self.b3_dependency != B3_NORMALIZATION_DEPENDENCY:
            raise ValueError("Unexpected frozen B3 normalization dependency.")
        if self.record_version != CANDIDATE_DEDUPLICATION_RECORD_VERSION:
            raise ValueError("Unsupported candidate-deduplication record version.")


def normalize_candidate_value(
    *,
    field_name: ReceiptFieldName,
    exact_value: str,
) -> CandidateNormalizationV0:
    """Build a deterministic field-tagged key without changing exact input."""

    if not isinstance(field_name, ReceiptFieldName):
        raise TypeError("field_name must be ReceiptFieldName.")
    _require_text(exact_value, "exact_value")
    canonical, normalized_key, status = _derive_normalization(
        field_name, exact_value
    )
    return CandidateNormalizationV0(
        field_name=field_name,
        exact_value=exact_value,
        canonical_value=canonical,
        normalized_key=normalized_key,
        parse_status=status,
    )


def _proposal_order_key(
    proposal: AlteredCandidateProposalV0,
) -> tuple[int, str, str]:
    try:
        priority = _SOURCE_PRIORITY[proposal.source_kind]
    except KeyError as exc:
        raise CandidateDeduplicationIntegrityError(
            "An altered proposal has no permitted source-category priority."
        ) from exc
    return priority, proposal.proposed_value, proposal.proposal_reference


def _validate_proposal_collection(
    proposals: tuple[AlteredCandidateProposalV0, ...],
) -> None:
    if not proposals:
        raise ValueError("A proposal collection must not be empty.")
    if any(not isinstance(item, AlteredCandidateProposalV0) for item in proposals):
        raise TypeError("Proposal collections must contain altered proposals.")
    if proposals != tuple(sorted(proposals, key=_proposal_order_key)):
        raise ValueError("Contributing proposals must use canonical source/value order.")
    references = tuple(item.proposal_reference for item in proposals)
    if len(references) != len(set(references)):
        raise ValueError("Contributing proposal references must be unique.")


@dataclass(frozen=True, slots=True)
class DeduplicatedAlteredGroupV0:
    """One normalized altered value with every raw contributing proposal."""

    normalization: CandidateNormalizationV0
    representative: AlteredCandidateProposalV0
    contributing_proposals: tuple[AlteredCandidateProposalV0, ...]
    record_version: str = CANDIDATE_DEDUPLICATION_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.normalization, CandidateNormalizationV0):
            raise TypeError("normalization must be CandidateNormalizationV0.")
        if not isinstance(self.representative, AlteredCandidateProposalV0):
            raise TypeError("representative must be an altered proposal.")
        _validate_proposal_collection(self.contributing_proposals)
        if self.representative != self.contributing_proposals[0]:
            raise ValueError("Representative must equal the canonical first proposal.")
        method = self.representative.method_ready_field
        for proposal in self.contributing_proposals:
            if proposal.method_ready_field != method:
                raise ValueError("A group cannot mix method-ready field identities.")
            derived = normalize_candidate_value(
                field_name=method.field_name,
                exact_value=proposal.proposed_value,
            )
            if derived.normalized_key != self.normalization.normalized_key:
                raise ValueError("Every grouped proposal must share the normalized key.")
        expected_normalization = normalize_candidate_value(
            field_name=method.field_name,
            exact_value=self.representative.proposed_value,
        )
        if self.normalization != expected_normalization:
            raise ValueError("Group normalization must describe its representative.")
        if self.record_version != CANDIDATE_DEDUPLICATION_RECORD_VERSION:
            raise ValueError("Unsupported candidate-deduplication record version.")


@dataclass(frozen=True, slots=True)
class EquivalentToC0AuditV0:
    """Altered proposals suppressed because their key equals permanent c0."""

    c0_normalization: CandidateNormalizationV0
    equivalent_proposals: tuple[AlteredCandidateProposalV0, ...]
    record_version: str = CANDIDATE_DEDUPLICATION_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.c0_normalization, CandidateNormalizationV0):
            raise TypeError("c0_normalization must be CandidateNormalizationV0.")
        _validate_proposal_collection(self.equivalent_proposals)
        method = self.equivalent_proposals[0].method_ready_field
        if method.field_name is not self.c0_normalization.field_name:
            raise ValueError("c0 audit field type must match its proposals.")
        if method.c0_value != self.c0_normalization.exact_value:
            raise ValueError("c0 audit must retain the exact method-ready c0 value.")
        for proposal in self.equivalent_proposals:
            if proposal.method_ready_field != method:
                raise ValueError("A c0 audit cannot mix method-ready field identities.")
            derived = normalize_candidate_value(
                field_name=method.field_name,
                exact_value=proposal.proposed_value,
            )
            if derived.normalized_key != self.c0_normalization.normalized_key:
                raise ValueError("Every audited proposal must normalize to c0.")
        if self.record_version != CANDIDATE_DEDUPLICATION_RECORD_VERSION:
            raise ValueError("Unsupported candidate-deduplication record version.")


def _derive_deduplication(
    candidate_drafts: CandidateGenerationResultV0,
) -> tuple[
    CandidateNormalizationV0,
    tuple[DeduplicatedAlteredGroupV0, ...],
    EquivalentToC0AuditV0 | None,
]:
    method = candidate_drafts.original.method_ready_field
    original_normalization = normalize_candidate_value(
        field_name=method.field_name,
        exact_value=candidate_drafts.original.value,
    )
    by_key: dict[str, list[AlteredCandidateProposalV0]] = {}
    equivalent_to_c0: list[AlteredCandidateProposalV0] = []
    for proposal in candidate_drafts.altered_proposals:
        if proposal.method_ready_field != method:
            raise CandidateDeduplicationIntegrityError(
                "Candidate drafts cannot mix receipt or field identities."
            )
        normalized = normalize_candidate_value(
            field_name=method.field_name,
            exact_value=proposal.proposed_value,
        )
        if normalized.normalized_key == original_normalization.normalized_key:
            equivalent_to_c0.append(proposal)
        else:
            by_key.setdefault(normalized.normalized_key, []).append(proposal)

    groups: list[DeduplicatedAlteredGroupV0] = []
    for proposals in by_key.values():
        ordered = tuple(sorted(proposals, key=_proposal_order_key))
        representative = ordered[0]
        groups.append(
            DeduplicatedAlteredGroupV0(
                normalization=normalize_candidate_value(
                    field_name=method.field_name,
                    exact_value=representative.proposed_value,
                ),
                representative=representative,
                contributing_proposals=ordered,
            )
        )
    ordered_groups = tuple(
        sorted(
            groups,
            key=lambda group: (
                _proposal_order_key(group.representative),
                group.normalization.normalized_key,
            ),
        )
    )
    audit = None
    if equivalent_to_c0:
        audit = EquivalentToC0AuditV0(
            c0_normalization=original_normalization,
            equivalent_proposals=tuple(
                sorted(equivalent_to_c0, key=_proposal_order_key)
            ),
        )
    return original_normalization, ordered_groups, audit


@dataclass(frozen=True, slots=True)
class CandidateDeduplicationResultV0:
    """Reconstructable one-field normalization and local-deduplication output."""

    candidate_drafts: CandidateGenerationResultV0
    original_normalization: CandidateNormalizationV0
    altered_groups: tuple[DeduplicatedAlteredGroupV0, ...]
    equivalent_to_c0: EquivalentToC0AuditV0 | None
    profile_id: str = NORMALIZATION_PROFILE_ID
    deduplicator_version: str = CANDIDATE_DEDUPLICATION_VERSION
    record_version: str = CANDIDATE_DEDUPLICATION_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_drafts, CandidateGenerationResultV0):
            raise TypeError("candidate_drafts must be CandidateGenerationResultV0.")
        if not isinstance(self.original_normalization, CandidateNormalizationV0):
            raise TypeError("original_normalization must be CandidateNormalizationV0.")
        if any(
            not isinstance(item, DeduplicatedAlteredGroupV0)
            for item in self.altered_groups
        ):
            raise TypeError("altered_groups must contain deduplicated groups.")
        if self.equivalent_to_c0 is not None and not isinstance(
            self.equivalent_to_c0, EquivalentToC0AuditV0
        ):
            raise TypeError("equivalent_to_c0 must be an equivalence audit or None.")
        if self.profile_id != NORMALIZATION_PROFILE_ID:
            raise ValueError("Unsupported normalization profile.")
        if self.deduplicator_version != CANDIDATE_DEDUPLICATION_VERSION:
            raise ValueError("Unsupported candidate deduplicator version.")
        if self.record_version != CANDIDATE_DEDUPLICATION_RECORD_VERSION:
            raise ValueError("Unsupported candidate-deduplication record version.")
        expected = _derive_deduplication(self.candidate_drafts)
        if (
            self.original_normalization,
            self.altered_groups,
            self.equivalent_to_c0,
        ) != expected:
            raise CandidateDeduplicationIntegrityError(
                "Deduplication result must equal its canonical upstream derivation."
            )


def deduplicate_candidate_drafts(
    *,
    candidate_drafts: CandidateGenerationResultV0,
) -> CandidateDeduplicationResultV0:
    """Normalize and deduplicate one field while retaining all raw evidence."""

    if not isinstance(candidate_drafts, CandidateGenerationResultV0):
        raise TypeError("candidate_drafts must be CandidateGenerationResultV0.")
    original, groups, audit = _derive_deduplication(candidate_drafts)
    return CandidateDeduplicationResultV0(
        candidate_drafts=candidate_drafts,
        original_normalization=original,
        altered_groups=groups,
        equivalent_to_c0=audit,
    )
