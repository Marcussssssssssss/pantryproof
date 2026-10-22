"""Materialize complete, safely projectable altered-candidate provenance.

This component consumes the lossless identity-stage audit.  It creates shared
``CandidateProvenanceV1`` members only when every contribution behind an
altered identity can be projected without inventing evidence.  Altered
``CandidateRecordV1`` records remain outside this pre-ranking boundary.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pipeline.proposed.candidate_deduplication import EquivalentToC0AuditV0
from pipeline.proposed.candidate_identity import (
    AlteredCandidateIdentityDraftV0,
    AlteredCandidateProvenanceAuditV0,
    CandidateIdentityPreparationResultV0,
    ProposalProvenanceAuditV0,
    ProvenanceProjectionClassificationV0,
)
from pipeline.proposed.contracts import (
    PROPOSED_CONTRACT_VERSION,
    CandidateProvenanceV1,
    CandidateRecordV1,
    CandidateSourceKind,
    SourceCharacterSpanV1,
)


PROVENANCE_MEMBER_SCHEMA_VERSION = (
    "pantryproof-altered-provenance-member-id-v1"
)
ALTERED_PROVENANCE_ID_PREFIX = "pp:provenance:altered:v1:sha256:"
PROVENANCE_MATERIALIZER_VERSION = "candidate-provenance-materializer-v0"
PROVENANCE_MATERIALIZATION_RECORD_VERSION = (
    "candidate-provenance-materialization-record-v0"
)

_COMPOSITE_GENERIC_REASON = (
    "Generic normalization has multiple rule IDs without a verified "
    "event-to-rule mapping."
)
_MISSING_SOURCE_SPAN_REASON = (
    "Source/neighbour provenance has no genuine candidate-specific token spans."
)
_MULTIPLE_SOURCE_SPANS_REASON = (
    "Source/neighbour provenance has multiple distinct spans without an "
    "approved observed-value composition rule."
)
_UNSUPPORTED_SOURCE_REASON = (
    "The candidate source kind lacks approved projection evidence or an "
    "immutable resource snapshot."
)


class CandidateProvenanceIntegrityError(ValueError):
    """Stored provenance or materialized output contradicts original evidence."""


class ProvenanceBlockingReasonV0(str, Enum):
    """Why one contribution prevents an atomic shared provenance union."""

    COMPOSITE_GENERIC_RULES = "COMPOSITE_GENERIC_RULES"
    MISSING_SOURCE_NEIGHBOUR_SPANS = "MISSING_SOURCE_NEIGHBOUR_SPANS"
    MULTIPLE_SOURCE_NEIGHBOUR_SPANS = "MULTIPLE_SOURCE_NEIGHBOUR_SPANS"
    UNSUPPORTED_SOURCE_KIND_OR_RESOURCE = "UNSUPPORTED_SOURCE_KIND_OR_RESOURCE"


_BLOCKING_TEXT = {
    ProvenanceBlockingReasonV0.COMPOSITE_GENERIC_RULES: _COMPOSITE_GENERIC_REASON,
    ProvenanceBlockingReasonV0.MISSING_SOURCE_NEIGHBOUR_SPANS: (
        _MISSING_SOURCE_SPAN_REASON
    ),
    ProvenanceBlockingReasonV0.MULTIPLE_SOURCE_NEIGHBOUR_SPANS: (
        _MULTIPLE_SOURCE_SPANS_REASON
    ),
    ProvenanceBlockingReasonV0.UNSUPPORTED_SOURCE_KIND_OR_RESOURCE: (
        _UNSUPPORTED_SOURCE_REASON
    ),
}


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")


def _validate_payload_value(value: Any) -> None:
    if value is None or isinstance(value, str):
        return
    if type(value) is int:
        return
    if isinstance(value, (tuple, list)):
        for item in value:
            _validate_payload_value(item)
        return
    raise CandidateProvenanceIntegrityError(
        "Provenance identity payloads support only strings, non-Boolean "
        "integers, null, and approved nested arrays."
    )


def _validate_payload_shape(payload: tuple[Any, ...]) -> None:
    if not isinstance(payload, tuple) or len(payload) != 13:
        raise CandidateProvenanceIntegrityError(
            "A provenance identity payload must be the approved 13-part tuple."
        )
    _validate_payload_value(payload)
    (
        schema,
        contract_version,
        receipt_id,
        field_id,
        candidate_id,
        source_kind,
        original_observed_value,
        source_token_ids,
        span_values,
        source_order_relationship,
        source_order_position,
        generic_rule_id,
        resource_snapshot_id,
    ) = payload
    if schema != PROVENANCE_MEMBER_SCHEMA_VERSION:
        raise CandidateProvenanceIntegrityError(
            "Unsupported altered-provenance identity schema."
        )
    if contract_version != PROPOSED_CONTRACT_VERSION:
        raise CandidateProvenanceIntegrityError(
            "Provenance identity must declare the shared contract version."
        )
    for name, value in (
        ("receipt_id", receipt_id),
        ("field_id", field_id),
        ("candidate_id", candidate_id),
        ("source_kind", source_kind),
        ("original_observed_value", original_observed_value),
    ):
        _require_text(value, name)
    try:
        CandidateSourceKind(source_kind)
    except ValueError as exc:
        raise CandidateProvenanceIntegrityError(
            "Provenance payload has an unsupported source kind."
        ) from exc
    if not isinstance(source_token_ids, tuple) or any(
        not isinstance(item, str) or not item.strip() for item in source_token_ids
    ):
        raise CandidateProvenanceIntegrityError(
            "Provenance token identities must be an approved tuple of strings."
        )
    if len(source_token_ids) != len(set(source_token_ids)):
        raise CandidateProvenanceIntegrityError(
            "Provenance token identities must be unique."
        )
    if not isinstance(span_values, tuple):
        raise CandidateProvenanceIntegrityError(
            "Provenance spans must use the approved nested tuple shape."
        )
    for span in span_values:
        if not isinstance(span, tuple) or len(span) != 4:
            raise CandidateProvenanceIntegrityError(
                "Each provenance span payload must contain four positional values."
            )
        token_id, start, end, text = span
        _require_text(token_id, "span token_id")
        if type(start) is not int or type(end) is not int:
            raise CandidateProvenanceIntegrityError(
                "Provenance span offsets must be non-Boolean integers."
            )
        if start < 0 or end <= start:
            raise CandidateProvenanceIntegrityError(
                "Provenance span offsets must form a non-empty range."
            )
        if not isinstance(text, str) or not text:
            raise CandidateProvenanceIntegrityError(
                "Provenance span text must be a non-empty literal string."
            )
    if source_order_relationship is not None:
        _require_text(source_order_relationship, "source_order_relationship")
    if source_order_position is not None and type(source_order_position) is not int:
        raise CandidateProvenanceIntegrityError(
            "Source-order position must be a non-Boolean integer or null."
        )
    if source_order_position is not None and source_order_position < 0:
        raise CandidateProvenanceIntegrityError(
            "Source-order position cannot be negative."
        )
    for name, value in (
        ("generic_rule_id", generic_rule_id),
        ("resource_snapshot_id", resource_snapshot_id),
    ):
        if value is not None:
            _require_text(value, name)
    derived_token_ids = tuple(dict.fromkeys(span[0] for span in span_values))
    if source_token_ids != derived_token_ids:
        raise CandidateProvenanceIntegrityError(
            "Payload token IDs must equal first source-span appearance order."
        )
    if source_order_relationship is not None or source_order_position is not None:
        raise CandidateProvenanceIntegrityError(
            "This materializer cannot claim an unrecorded source-order relationship."
        )
    parsed_source_kind = CandidateSourceKind(source_kind)
    if parsed_source_kind is CandidateSourceKind.ORIGINAL:
        raise CandidateProvenanceIntegrityError(
            "Altered provenance payload cannot claim ORIGINAL."
        )
    if parsed_source_kind is CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR:
        if len(span_values) != 1 or len(source_token_ids) != 1:
            raise CandidateProvenanceIntegrityError(
                "Source/neighbour payload requires one genuine literal span."
            )
        if generic_rule_id is not None or resource_snapshot_id is not None:
            raise CandidateProvenanceIntegrityError(
                "Source/neighbour payload cannot claim a rule or resource."
            )
    elif parsed_source_kind is CandidateSourceKind.GENERIC_NORMALIZATION:
        if generic_rule_id is None or resource_snapshot_id is not None:
            raise CandidateProvenanceIntegrityError(
                "Generic payload requires one rule and no resource snapshot."
            )
    elif resource_snapshot_id is None:
        raise CandidateProvenanceIntegrityError(
            "Resource-derived payload requires an immutable snapshot ID."
        )


def _canonical_provenance_json(payload: tuple[Any, ...]) -> tuple[str, bytes]:
    _validate_payload_shape(payload)
    try:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        encoded = serialized.encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise CandidateProvenanceIntegrityError(
            "Provenance payload must have a strict canonical UTF-8 representation."
        ) from exc
    return serialized, encoded


def _sha256_hex(encoded: bytes) -> str:
    return hashlib.sha256(encoded).hexdigest()


def _provenance_identifier(payload: tuple[Any, ...]) -> tuple[str, str]:
    serialized, encoded = _canonical_provenance_json(payload)
    return f"{ALTERED_PROVENANCE_ID_PREFIX}{_sha256_hex(encoded)}", serialized


def _provenance_payload(
    *,
    receipt_id: str,
    field_id: str,
    candidate_id: str,
    source_kind: CandidateSourceKind,
    original_observed_value: str,
    source_token_ids: tuple[str, ...],
    source_spans: tuple[SourceCharacterSpanV1, ...],
    generic_rule_id: str | None,
    resource_snapshot_id: str | None,
) -> tuple[Any, ...]:
    return (
        PROVENANCE_MEMBER_SCHEMA_VERSION,
        PROPOSED_CONTRACT_VERSION,
        receipt_id,
        field_id,
        candidate_id,
        source_kind.value,
        original_observed_value,
        source_token_ids,
        tuple((span.token_id, span.start, span.end, span.text) for span in source_spans),
        None,
        None,
        generic_rule_id,
        resource_snapshot_id,
    )


def _blocking_shape(
    contribution: ProposalProvenanceAuditV0,
) -> tuple[ProvenanceBlockingReasonV0, str] | None:
    if contribution.source_kind is CandidateSourceKind.GENERIC_NORMALIZATION:
        if len(contribution.b3_rule_ids) != 1:
            return (
                ProvenanceBlockingReasonV0.COMPOSITE_GENERIC_RULES,
                _COMPOSITE_GENERIC_REASON,
            )
        return None
    if contribution.source_kind is CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR:
        if not contribution.source_spans:
            return (
                ProvenanceBlockingReasonV0.MISSING_SOURCE_NEIGHBOUR_SPANS,
                _MISSING_SOURCE_SPAN_REASON,
            )
        if len(contribution.source_spans) != 1:
            return (
                ProvenanceBlockingReasonV0.MULTIPLE_SOURCE_NEIGHBOUR_SPANS,
                _MULTIPLE_SOURCE_SPANS_REASON,
            )
        return None
    return (
        ProvenanceBlockingReasonV0.UNSUPPORTED_SOURCE_KIND_OR_RESOURCE,
        _UNSUPPORTED_SOURCE_REASON,
    )


def _validate_identity_projection_state(
    contribution: ProposalProvenanceAuditV0,
) -> None:
    if (
        contribution.source_kind is CandidateSourceKind.GENERIC_NORMALIZATION
        and len(contribution.b3_rule_ids) > 1
    ):
        expected = (
            ProvenanceProjectionClassificationV0.BLOCKED_COMPOSITE_GENERIC_RULES,
            _COMPOSITE_GENERIC_REASON,
        )
    elif (
        contribution.source_kind
        is CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR
        and not contribution.source_spans
    ):
        expected = (
            ProvenanceProjectionClassificationV0.BLOCKED_MISSING_SOURCE_TOKENS,
            _MISSING_SOURCE_SPAN_REASON,
        )
    else:
        expected = (ProvenanceProjectionClassificationV0.PROJECTION_DEFERRED, None)
    if (
        contribution.projection_classification,
        contribution.projection_reason,
    ) != expected:
        raise CandidateProvenanceIntegrityError(
            "Identity-stage projection classification was forged or contradicted."
        )


@dataclass(frozen=True, slots=True)
class ProvenanceBlockingRecordV0:
    """One exact upstream contribution that prevents atomic materialization."""

    contribution: ProposalProvenanceAuditV0
    reason_code: ProvenanceBlockingReasonV0
    reason: str
    component_version: str = PROVENANCE_MATERIALIZER_VERSION
    record_version: str = PROVENANCE_MATERIALIZATION_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.contribution, ProposalProvenanceAuditV0):
            raise TypeError("contribution must be ProposalProvenanceAuditV0.")
        if not isinstance(self.reason_code, ProvenanceBlockingReasonV0):
            raise TypeError("reason_code must be ProvenanceBlockingReasonV0.")
        expected = _blocking_shape(self.contribution)
        if expected is None or (self.reason_code, self.reason) != expected:
            raise CandidateProvenanceIntegrityError(
                "Blocking status must equal the contribution's recorded evidence shape."
            )
        if self.component_version != PROVENANCE_MATERIALIZER_VERSION:
            raise ValueError("Unsupported provenance materializer version.")
        if self.record_version != PROVENANCE_MATERIALIZATION_RECORD_VERSION:
            raise ValueError("Unsupported provenance materialization record version.")


@dataclass(frozen=True, slots=True)
class ProvenanceMemberProjectionV0:
    """One unique shared member plus every proposal that projected to it."""

    provenance: CandidateProvenanceV1
    identity_payload: tuple[Any, ...]
    identity_payload_json: str
    contributing_proposal_references: tuple[str, ...]
    component_version: str = PROVENANCE_MATERIALIZER_VERSION
    record_version: str = PROVENANCE_MATERIALIZATION_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.provenance, CandidateProvenanceV1):
            raise TypeError("provenance must be CandidateProvenanceV1.")
        _require_text(self.identity_payload_json, "identity_payload_json")
        if not self.contributing_proposal_references:
            raise ValueError("A provenance projection requires proposal references.")
        if any(
            not isinstance(reference, str) or not reference.strip()
            for reference in self.contributing_proposal_references
        ):
            raise ValueError("Proposal references must be non-empty strings.")
        if len(self.contributing_proposal_references) != len(
            set(self.contributing_proposal_references)
        ):
            raise ValueError("Contributing proposal references must be unique.")
        expected_id, expected_json = _provenance_identifier(self.identity_payload)
        if self.identity_payload_json != expected_json:
            raise CandidateProvenanceIntegrityError(
                "Stored provenance payload JSON is not canonical."
            )
        if self.provenance.provenance_id != expected_id:
            raise CandidateProvenanceIntegrityError(
                "Shared provenance ID does not match its canonical payload."
            )
        expected_payload = _provenance_payload(
            receipt_id=self.provenance.receipt_id,
            field_id=self.provenance.field_id,
            candidate_id=self.provenance.candidate_id,
            source_kind=self.provenance.source_kind,
            original_observed_value=self.provenance.original_observed_value,
            source_token_ids=self.provenance.source_token_ids,
            source_spans=self.provenance.source_spans,
            generic_rule_id=self.provenance.generic_rule_id,
            resource_snapshot_id=self.provenance.resource_snapshot_id,
        )
        if self.identity_payload != expected_payload:
            raise CandidateProvenanceIntegrityError(
                "Provenance payload must equal the complete shared record content."
            )
        if self.provenance.source_kind is CandidateSourceKind.ORIGINAL:
            raise CandidateProvenanceIntegrityError(
                "Altered provenance projection cannot claim ORIGINAL."
            )
        if self.component_version != PROVENANCE_MATERIALIZER_VERSION:
            raise ValueError("Unsupported provenance materializer version.")
        if self.record_version != PROVENANCE_MATERIALIZATION_RECORD_VERSION:
            raise ValueError("Unsupported provenance materialization record version.")


@dataclass(frozen=True, slots=True)
class AlteredCandidateProvenanceMaterializationV0:
    """A complete shared provenance union for one altered identity."""

    source_audit: AlteredCandidateProvenanceAuditV0
    members: tuple[ProvenanceMemberProjectionV0, ...]
    component_version: str = PROVENANCE_MATERIALIZER_VERSION
    record_version: str = PROVENANCE_MATERIALIZATION_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.source_audit, AlteredCandidateProvenanceAuditV0):
            raise TypeError("source_audit must be AlteredCandidateProvenanceAuditV0.")
        if not self.members or any(
            not isinstance(member, ProvenanceMemberProjectionV0)
            for member in self.members
        ):
            raise TypeError("members must contain shared provenance projections.")
        identity = self.source_audit.identity
        for member in self.members:
            provenance = member.provenance
            if (
                provenance.receipt_id != identity.receipt_id
                or provenance.field_id != identity.field_id
                or provenance.candidate_id != identity.candidate_id
            ):
                raise CandidateProvenanceIntegrityError(
                    "Shared provenance identity must match its altered candidate."
                )
        if self.members != tuple(
            sorted(
                self.members,
                key=lambda member: (
                    member.provenance.source_priority,
                    member.identity_payload_json,
                ),
            )
        ):
            raise CandidateProvenanceIntegrityError(
                "Shared provenance members must use canonical source-priority order."
            )
        ids = tuple(member.provenance.provenance_id for member in self.members)
        if len(ids) != len(set(ids)):
            raise CandidateProvenanceIntegrityError(
                "A materialized provenance union cannot repeat member IDs."
            )
        expected_references = tuple(
            contribution.proposal_reference
            for contribution in self.source_audit.contributions
        )
        linked_references = tuple(
            reference
            for member in self.members
            for reference in member.contributing_proposal_references
        )
        if (
            len(linked_references) != len(set(linked_references))
            or set(linked_references) != set(expected_references)
        ):
            raise CandidateProvenanceIntegrityError(
                "Every upstream contribution must link to exactly one shared member."
            )
        if self.component_version != PROVENANCE_MATERIALIZER_VERSION:
            raise ValueError("Unsupported provenance materializer version.")
        if self.record_version != PROVENANCE_MATERIALIZATION_RECORD_VERSION:
            raise ValueError("Unsupported provenance materialization record version.")

    @property
    def identity(self) -> AlteredCandidateIdentityDraftV0:
        return self.source_audit.identity

    @property
    def shared_provenance(self) -> tuple[CandidateProvenanceV1, ...]:
        return tuple(member.provenance for member in self.members)


@dataclass(frozen=True, slots=True)
class BlockedAlteredCandidateProvenanceV0:
    """A preserved altered identity whose complete shared union is unavailable."""

    source_audit: AlteredCandidateProvenanceAuditV0
    blocking_records: tuple[ProvenanceBlockingRecordV0, ...]
    component_version: str = PROVENANCE_MATERIALIZER_VERSION
    record_version: str = PROVENANCE_MATERIALIZATION_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.source_audit, AlteredCandidateProvenanceAuditV0):
            raise TypeError("source_audit must be AlteredCandidateProvenanceAuditV0.")
        if not self.blocking_records or any(
            not isinstance(record, ProvenanceBlockingRecordV0)
            for record in self.blocking_records
        ):
            raise TypeError("blocking_records must contain blocking records.")
        expected = tuple(
            contribution
            for contribution in self.source_audit.contributions
            if _blocking_shape(contribution) is not None
        )
        if tuple(record.contribution for record in self.blocking_records) != expected:
            raise CandidateProvenanceIntegrityError(
                "Blocking records must preserve every blocked contribution in order."
            )
        if self.component_version != PROVENANCE_MATERIALIZER_VERSION:
            raise ValueError("Unsupported provenance materializer version.")
        if self.record_version != PROVENANCE_MATERIALIZATION_RECORD_VERSION:
            raise ValueError("Unsupported provenance materialization record version.")

    @property
    def identity(self) -> AlteredCandidateIdentityDraftV0:
        return self.source_audit.identity

    @property
    def shared_provenance(self) -> tuple[CandidateProvenanceV1, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class _ProjectionDraft:
    provenance: CandidateProvenanceV1
    payload: tuple[Any, ...]
    payload_json: str
    proposal_reference: str


def _receipt_tokens(
    identity_preparation: CandidateIdentityPreparationResultV0,
) -> dict[str, Any]:
    generation = (
        identity_preparation.deduplication_result.candidate_drafts
    )
    adapter = generation.adapter_result
    output = adapter.original_b2_result.receipt_output
    method = generation.original.method_ready_field
    if output is None:
        raise CandidateProvenanceIntegrityError(
            "Altered provenance requires the original structured B2 receipt output."
        )
    if output.receipt_id != method.receipt_id or adapter.receipt_id != method.receipt_id:
        raise CandidateProvenanceIntegrityError(
            "Original receipt, adapter and method-ready receipt identities differ."
        )
    if output.source_evidence.receipt_id != method.receipt_id:
        raise CandidateProvenanceIntegrityError(
            "Original OCR evidence belongs to another receipt."
        )
    tokens = output.source_evidence.tokens
    token_ids = tuple(token.token_id for token in tokens)
    if len(token_ids) != len(set(token_ids)):
        raise CandidateProvenanceIntegrityError(
            "Original receipt OCR token IDs must be unique."
        )
    if any(token.receipt_id != method.receipt_id for token in tokens):
        raise CandidateProvenanceIntegrityError(
            "Every original OCR token must belong to the altered candidate receipt."
        )
    return {token.token_id: token for token in tokens}


def _validate_spans(
    contribution: ProposalProvenanceAuditV0,
    token_by_id: dict[str, Any],
) -> tuple[str, ...]:
    ordered_token_ids: list[str] = []
    for span in contribution.source_spans:
        token = token_by_id.get(span.token_id)
        if token is None:
            raise CandidateProvenanceIntegrityError(
                f"Unknown original OCR token ID {span.token_id!r}."
            )
        if token.receipt_id != contribution.parent_identity.receipt_id:
            raise CandidateProvenanceIntegrityError(
                "A candidate source span references a token from another receipt."
            )
        if (
            type(span.start) is not int
            or type(span.end) is not int
            or span.start < 0
            or span.end <= span.start
            or span.end > len(token.original_text)
        ):
            raise CandidateProvenanceIntegrityError(
                "Candidate source span has invalid literal OCR offsets."
            )
        literal = token.original_text[span.start : span.end]
        if span.text != literal:
            raise CandidateProvenanceIntegrityError(
                "Candidate source span text does not equal the original OCR slice."
            )
        if span.token_id not in ordered_token_ids:
            ordered_token_ids.append(span.token_id)
    expected = tuple(ordered_token_ids)
    if contribution.source_token_ids != expected:
        raise CandidateProvenanceIntegrityError(
            "Candidate source-token IDs must equal first span appearance order."
        )
    return expected


def _project_contribution(
    contribution: ProposalProvenanceAuditV0,
    token_by_id: dict[str, Any],
) -> _ProjectionDraft | ProvenanceBlockingRecordV0:
    source_token_ids = _validate_spans(contribution, token_by_id)
    blocking = _blocking_shape(contribution)
    if blocking is not None:
        return ProvenanceBlockingRecordV0(
            contribution=contribution,
            reason_code=blocking[0],
            reason=blocking[1],
        )

    if contribution.source_kind is CandidateSourceKind.GENERIC_NORMALIZATION:
        original_observed_value = contribution.c0_value
        generic_rule_id = contribution.b3_rule_ids[0]
    elif (
        contribution.source_kind
        is CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR
    ):
        original_observed_value = contribution.source_spans[0].text
        generic_rule_id = None
    else:  # Defensive; _blocking_shape handles every other source kind.
        raise CandidateProvenanceIntegrityError(
            "Unsupported source kind escaped fail-closed projection."
        )

    identity = contribution.parent_identity
    payload = _provenance_payload(
        receipt_id=identity.receipt_id,
        field_id=identity.field_id,
        candidate_id=identity.candidate_id,
        source_kind=contribution.source_kind,
        original_observed_value=original_observed_value,
        source_token_ids=source_token_ids,
        source_spans=contribution.source_spans,
        generic_rule_id=generic_rule_id,
        resource_snapshot_id=None,
    )
    provenance_id, payload_json = _provenance_identifier(payload)
    provenance = CandidateProvenanceV1(
        provenance_id=provenance_id,
        receipt_id=identity.receipt_id,
        field_id=identity.field_id,
        candidate_id=identity.candidate_id,
        source_kind=contribution.source_kind,
        original_observed_value=original_observed_value,
        source_token_ids=source_token_ids,
        source_spans=contribution.source_spans,
        source_order_relationship=None,
        source_order_position=None,
        generic_rule_id=generic_rule_id,
        resource_snapshot_id=None,
    )
    return _ProjectionDraft(
        provenance=provenance,
        payload=payload,
        payload_json=payload_json,
        proposal_reference=contribution.proposal_reference,
    )


def _materialize_one(
    source_audit: AlteredCandidateProvenanceAuditV0,
    token_by_id: dict[str, Any],
) -> (
    AlteredCandidateProvenanceMaterializationV0
    | BlockedAlteredCandidateProvenanceV0
):
    for contribution in source_audit.contributions:
        _validate_identity_projection_state(contribution)
    if source_audit.has_blocked_contributions != any(
        contribution.is_blocked for contribution in source_audit.contributions
    ):
        raise CandidateProvenanceIntegrityError(
            "Identity-stage blocked-contribution status was forged or contradicted."
        )
    projected: list[_ProjectionDraft] = []
    blocked: list[ProvenanceBlockingRecordV0] = []
    for contribution in source_audit.contributions:
        result = _project_contribution(contribution, token_by_id)
        if isinstance(result, ProvenanceBlockingRecordV0):
            blocked.append(result)
        else:
            projected.append(result)
    if blocked:
        return BlockedAlteredCandidateProvenanceV0(
            source_audit=source_audit,
            blocking_records=tuple(blocked),
        )

    by_payload: dict[str, list[_ProjectionDraft]] = {}
    for draft in projected:
        by_payload.setdefault(draft.payload_json, []).append(draft)
    members = tuple(
        sorted(
            (
                ProvenanceMemberProjectionV0(
                    provenance=drafts[0].provenance,
                    identity_payload=drafts[0].payload,
                    identity_payload_json=payload_json,
                    contributing_proposal_references=tuple(
                        draft.proposal_reference for draft in drafts
                    ),
                )
                for payload_json, drafts in by_payload.items()
            ),
            key=lambda member: (
                member.provenance.source_priority,
                member.identity_payload_json,
            ),
        )
    )
    return AlteredCandidateProvenanceMaterializationV0(
        source_audit=source_audit,
        members=members,
    )


def _derive_materialization(
    identity_preparation: CandidateIdentityPreparationResultV0,
) -> tuple[
    tuple[AlteredCandidateProvenanceMaterializationV0, ...],
    tuple[BlockedAlteredCandidateProvenanceV0, ...],
]:
    try:
        identity_preparation.__post_init__()
    except (TypeError, ValueError) as exc:
        raise CandidateProvenanceIntegrityError(
            "Identity preparation failed complete upstream reconstruction."
        ) from exc
    token_by_id = _receipt_tokens(identity_preparation)
    materialized: list[AlteredCandidateProvenanceMaterializationV0] = []
    blocked: list[BlockedAlteredCandidateProvenanceV0] = []
    payload_by_id: dict[str, str] = {}
    for source_audit in identity_preparation.altered_candidates:
        outcome = _materialize_one(source_audit, token_by_id)
        if isinstance(outcome, BlockedAlteredCandidateProvenanceV0):
            blocked.append(outcome)
            continue
        for member in outcome.members:
            provenance_id = member.provenance.provenance_id
            previous_payload = payload_by_id.get(provenance_id)
            if previous_payload is not None and previous_payload != member.identity_payload_json:
                raise CandidateProvenanceIntegrityError(
                    "Distinct canonical payloads produced the same provenance-member ID."
                )
            if previous_payload is not None:
                raise CandidateProvenanceIntegrityError(
                    "A provenance-member ID was unexpectedly reused across candidates."
                )
            payload_by_id[provenance_id] = member.identity_payload_json
        materialized.append(outcome)
    return tuple(materialized), tuple(blocked)


@dataclass(frozen=True, slots=True)
class CandidateProvenanceMaterializationResultV0:
    """Reconstructable partition of every altered identity by provenance status."""

    identity_preparation: CandidateIdentityPreparationResultV0
    original_candidate: CandidateRecordV1
    materialized_candidates: tuple[
        AlteredCandidateProvenanceMaterializationV0, ...
    ]
    blocked_candidates: tuple[BlockedAlteredCandidateProvenanceV0, ...]
    equivalent_to_c0: EquivalentToC0AuditV0 | None
    component_version: str = PROVENANCE_MATERIALIZER_VERSION
    record_version: str = PROVENANCE_MATERIALIZATION_RECORD_VERSION

    def __post_init__(self) -> None:
        if not isinstance(
            self.identity_preparation, CandidateIdentityPreparationResultV0
        ):
            raise TypeError(
                "identity_preparation must be CandidateIdentityPreparationResultV0."
            )
        if self.original_candidate is not self.identity_preparation.original_candidate:
            raise CandidateProvenanceIntegrityError(
                "Permanent c0 must be preserved unchanged and by reference."
            )
        if self.equivalent_to_c0 is not self.identity_preparation.equivalent_to_c0:
            raise CandidateProvenanceIntegrityError(
                "The c0-equivalence audit must be preserved unchanged and by reference."
            )
        if any(
            not isinstance(item, AlteredCandidateProvenanceMaterializationV0)
            for item in self.materialized_candidates
        ):
            raise TypeError("materialized_candidates contains an unsupported record.")
        if any(
            not isinstance(item, BlockedAlteredCandidateProvenanceV0)
            for item in self.blocked_candidates
        ):
            raise TypeError("blocked_candidates contains an unsupported record.")
        upstream_ids = tuple(
            audit.identity.candidate_id
            for audit in self.identity_preparation.altered_candidates
        )
        output_ids = tuple(
            item.identity.candidate_id
            for item in (*self.materialized_candidates, *self.blocked_candidates)
        )
        if len(output_ids) != len(set(output_ids)) or set(output_ids) != set(upstream_ids):
            raise CandidateProvenanceIntegrityError(
                "Every altered identity must occur in exactly one provenance partition."
            )
        if self.component_version != PROVENANCE_MATERIALIZER_VERSION:
            raise ValueError("Unsupported provenance materializer version.")
        if self.record_version != PROVENANCE_MATERIALIZATION_RECORD_VERSION:
            raise ValueError("Unsupported provenance materialization record version.")
        expected_materialized, expected_blocked = _derive_materialization(
            self.identity_preparation
        )
        if (
            self.materialized_candidates != expected_materialized
            or self.blocked_candidates != expected_blocked
        ):
            raise CandidateProvenanceIntegrityError(
                "Materialization result must equal its complete deterministic derivation."
            )


def materialize_altered_provenance(
    *,
    identity_preparation: CandidateIdentityPreparationResultV0,
) -> CandidateProvenanceMaterializationResultV0:
    """Project complete altered provenance unions without ranking candidates."""

    if not isinstance(identity_preparation, CandidateIdentityPreparationResultV0):
        raise TypeError(
            "identity_preparation must be CandidateIdentityPreparationResultV0."
        )
    materialized, blocked = _derive_materialization(identity_preparation)
    return CandidateProvenanceMaterializationResultV0(
        identity_preparation=identity_preparation,
        original_candidate=identity_preparation.original_candidate,
        materialized_candidates=materialized,
        blocked_candidates=blocked,
        equivalent_to_c0=identity_preparation.equivalent_to_c0,
    )
