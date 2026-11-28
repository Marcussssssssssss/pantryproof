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

from pipeline.contracts import OcrSourceToken, ReceiptOutput, ReceiptSourceEvidence
from pipeline.layout_b2 import B2ExtractionResult
from pipeline.proposed import provenance_replay_meter_v1 as pv
from pipeline.proposed.adapter import ProposedAdapterResultV1
from pipeline.proposed.candidate_deduplication import (
    CandidateDeduplicationResultV0, EquivalentToC0AuditV0,
)
from pipeline.proposed.candidate_generation import CandidateGenerationResultV0, OriginalCandidateDraftV0
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
    MethodReadyFieldV1,
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

_PAYLOAD_SHAPE = tuple[
    str, str, str, str, str, str, str, tuple[str, ...], tuple[tuple[str, int, int, str], ...],
    str | None, int | None, str | None, str | None,
]
_TokenIndex = dict[str, OcrSourceToken] | pv.LinearKeys


def _require_text(value: str, name: str) -> None:
    meter = pv.selected()
    if meter is not None:
        length = meter.text_length(value)
        meter.reserve(max_work_units=1 + 2 * length, max_temporary_slots=length)
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
    if pv.not_equal(schema, PROVENANCE_MEMBER_SCHEMA_VERSION):
        raise CandidateProvenanceIntegrityError(
            "Unsupported altered-provenance identity schema."
        )
    if pv.not_equal(contract_version, PROPOSED_CONTRACT_VERSION):
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
        _payload_source_kind(source_kind)
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
    if len(source_token_ids) != len(pv.unique_keys(source_token_ids)):
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
    derived_token_ids = pv.first_keys(span[0] for span in span_values)
    if pv.not_equal(source_token_ids, derived_token_ids):
        raise CandidateProvenanceIntegrityError(
            "Payload token IDs must equal first source-span appearance order."
        )
    if source_order_relationship is not None or source_order_position is not None:
        raise CandidateProvenanceIntegrityError(
            "This materializer cannot claim an unrecorded source-order relationship."
        )
    parsed_source_kind = _payload_source_kind(source_kind)
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


def _payload_source_kind(value: str) -> CandidateSourceKind:
    if pv.selected() is not None:
        for member in CandidateSourceKind:
            if not pv.not_equal(value, member.value):
                return member
        raise ValueError("Unsupported source kind.")
    return CandidateSourceKind(value)


@pv.operation
def _canonical_provenance_json(payload: tuple[Any, ...]) -> tuple[str, bytes]:
    meter = pv.selected()
    if meter is not None:
        size = meter.walk(payload, _PAYLOAD_SHAPE, canonical=True)
        # Includes the validation pass over the canonical grammar, its
        # token whitespace checks, and the two JSON buffers.
        meter.reserve(max_canonical_bytes=size, max_temporary_slots=3 * size,
                      max_work_units=4 * size)
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
    prefix_length = len(ALTERED_PROVENANCE_ID_PREFIX)
    pv.reserve(max_hash_calls=1, max_work_units=len(encoded) + prefix_length + 64,
               max_temporary_slots=prefix_length + 128 + 2)
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
    if pv.selected() is not None:
        slots = 13 + 5 * len(source_spans)
        pv.reserve(max_temporary_slots=slots, max_work_units=slots)
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
    pv.reserve(max_temporary_slots=2, max_work_units=6)
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
    pv.reserve(max_temporary_slots=4, max_work_units=6)
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
    if pv.not_equal((
        contribution.projection_classification,
        contribution.projection_reason,
    ), expected):
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

    @pv.operation
    def __post_init__(self) -> None:
        pv.screen(self, ProvenanceBlockingRecordV0)
        if not isinstance(self.contribution, ProposalProvenanceAuditV0):
            raise TypeError("contribution must be ProposalProvenanceAuditV0.")
        if not isinstance(self.reason_code, ProvenanceBlockingReasonV0):
            raise TypeError("reason_code must be ProvenanceBlockingReasonV0.")
        expected = _blocking_shape(self.contribution)
        pv.reserve(max_temporary_slots=2, max_work_units=2)
        if expected is None or pv.not_equal((self.reason_code, self.reason), expected):
            raise CandidateProvenanceIntegrityError(
                "Blocking status must equal the contribution's recorded evidence shape."
            )
        if pv.not_equal(self.component_version, PROVENANCE_MATERIALIZER_VERSION):
            raise ValueError("Unsupported provenance materializer version.")
        if pv.not_equal(self.record_version, PROVENANCE_MATERIALIZATION_RECORD_VERSION):
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

    @pv.operation
    def __post_init__(self) -> None:
        pv.screen(self, ProvenanceMemberProjectionV0)
        if not isinstance(self.provenance, CandidateProvenanceV1):
            raise TypeError("provenance must be CandidateProvenanceV1.")
        _require_text(self.identity_payload_json, "identity_payload_json")
        if not self.contributing_proposal_references:
            raise ValueError("A provenance projection requires proposal references.")
        if any(
            not _nonblank_reference(reference)
            for reference in self.contributing_proposal_references
        ):
            raise ValueError("Proposal references must be non-empty strings.")
        if len(self.contributing_proposal_references) != len(
            pv.unique_keys(self.contributing_proposal_references)
        ):
            raise ValueError("Contributing proposal references must be unique.")
        expected_id, expected_json = _provenance_identifier(self.identity_payload)
        if pv.not_equal(self.identity_payload_json, expected_json):
            raise CandidateProvenanceIntegrityError(
                "Stored provenance payload JSON is not canonical."
            )
        if pv.not_equal(self.provenance.provenance_id, expected_id):
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
        if pv.not_equal(self.identity_payload, expected_payload):
            raise CandidateProvenanceIntegrityError(
                "Provenance payload must equal the complete shared record content."
            )
        if self.provenance.source_kind is CandidateSourceKind.ORIGINAL:
            raise CandidateProvenanceIntegrityError(
                "Altered provenance projection cannot claim ORIGINAL."
            )
        if pv.not_equal(self.component_version, PROVENANCE_MATERIALIZER_VERSION):
            raise ValueError("Unsupported provenance materializer version.")
        if pv.not_equal(self.record_version, PROVENANCE_MATERIALIZATION_RECORD_VERSION):
            raise ValueError("Unsupported provenance materialization record version.")


def _nonblank_reference(value: str) -> bool:
    meter = pv.selected()
    if meter is not None:
        length = meter.text_length(value)
        meter.reserve(max_work_units=1 + 2 * length, max_temporary_slots=length)
    return isinstance(value, str) and bool(value.strip())


def _member_key(member: ProvenanceMemberProjectionV0) -> tuple[int, str]:
    return member.provenance.source_priority, member.identity_payload_json


@dataclass(frozen=True, slots=True)
class AlteredCandidateProvenanceMaterializationV0:
    """A complete shared provenance union for one altered identity."""

    source_audit: AlteredCandidateProvenanceAuditV0
    members: tuple[ProvenanceMemberProjectionV0, ...]
    component_version: str = PROVENANCE_MATERIALIZER_VERSION
    record_version: str = PROVENANCE_MATERIALIZATION_RECORD_VERSION

    @pv.operation
    def __post_init__(self) -> None:
        pv.screen(self, AlteredCandidateProvenanceMaterializationV0)
        if pv.selected() is not None:
            # Type checking, relationship checks and subsequent slot counting.
            pv.reserve(max_work_units=3 * len(self.members))
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
                pv.not_equal(provenance.receipt_id, identity.receipt_id)
                or pv.not_equal(provenance.field_id, identity.field_id)
                or pv.not_equal(provenance.candidate_id, identity.candidate_id)
            ):
                raise CandidateProvenanceIntegrityError(
                    "Shared provenance identity must match its altered candidate."
                )
        if pv.not_equal(self.members, pv.sort_members(self.members, _member_key)):
            raise CandidateProvenanceIntegrityError(
                "Shared provenance members must use canonical source-priority order."
            )
        if pv.selected() is not None:
            slots = (len(self.members) + len(self.source_audit.contributions)
                     + sum(len(member.contributing_proposal_references) for member in self.members))
            pv.reserve(max_temporary_slots=slots, max_work_units=slots)
        ids = tuple(member.provenance.provenance_id for member in self.members)
        if len(ids) != len(pv.unique_keys(ids)):
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
            len(linked_references) != len(pv.unique_keys(linked_references))
            or pv.different_keys(linked_references, expected_references)
        ):
            raise CandidateProvenanceIntegrityError(
                "Every upstream contribution must link to exactly one shared member."
            )
        if pv.not_equal(self.component_version, PROVENANCE_MATERIALIZER_VERSION):
            raise ValueError("Unsupported provenance materializer version.")
        if pv.not_equal(self.record_version, PROVENANCE_MATERIALIZATION_RECORD_VERSION):
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

    @pv.operation
    def __post_init__(self) -> None:
        pv.screen(self, BlockedAlteredCandidateProvenanceV0)
        if pv.selected() is not None:
            pv.reserve(max_work_units=len(self.blocking_records))
        if not isinstance(self.source_audit, AlteredCandidateProvenanceAuditV0):
            raise TypeError("source_audit must be AlteredCandidateProvenanceAuditV0.")
        if not self.blocking_records or any(
            not isinstance(record, ProvenanceBlockingRecordV0)
            for record in self.blocking_records
        ):
            raise TypeError("blocking_records must contain blocking records.")
        if pv.selected() is not None:
            slots = len(self.source_audit.contributions) + len(self.blocking_records)
            pv.reserve(max_temporary_slots=slots, max_work_units=slots)
        expected = tuple(
            contribution
            for contribution in self.source_audit.contributions
            if _blocking_shape(contribution) is not None
        )
        if pv.not_equal(tuple(record.contribution for record in self.blocking_records), expected):
            raise CandidateProvenanceIntegrityError(
                "Blocking records must preserve every blocked contribution in order."
            )
        if pv.not_equal(self.component_version, PROVENANCE_MATERIALIZER_VERSION):
            raise ValueError("Unsupported provenance materializer version.")
        if pv.not_equal(self.record_version, PROVENANCE_MATERIALIZATION_RECORD_VERSION):
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
) -> _TokenIndex:
    pv.exact(identity_preparation, CandidateIdentityPreparationResultV0)
    pv.exact(identity_preparation.deduplication_result, CandidateDeduplicationResultV0)
    generation = (
        identity_preparation.deduplication_result.candidate_drafts
    )
    pv.exact(generation, CandidateGenerationResultV0)
    adapter = generation.adapter_result
    pv.exact(adapter, ProposedAdapterResultV1)
    pv.exact(adapter.original_b2_result, B2ExtractionResult)
    output = adapter.original_b2_result.receipt_output
    pv.exact(generation.original, OriginalCandidateDraftV0)
    method = generation.original.method_ready_field
    pv.exact(method, MethodReadyFieldV1)
    if output is None:
        raise CandidateProvenanceIntegrityError(
            "Altered provenance requires the original structured B2 receipt output."
        )
    pv.exact(output, ReceiptOutput)
    pv.exact(output.source_evidence, ReceiptSourceEvidence)
    if pv.selected() is not None:
        pv.reserve(max_temporary_slots=4, max_work_units=4)
        pv.screen(
            (output.receipt_id, adapter.receipt_id, method.receipt_id, output.source_evidence.receipt_id),
            tuple[str, ...],
        )
    if pv.not_equal(output.receipt_id, method.receipt_id) or pv.not_equal(adapter.receipt_id, method.receipt_id):
        raise CandidateProvenanceIntegrityError(
            "Original receipt, adapter and method-ready receipt identities differ."
        )
    if pv.not_equal(output.source_evidence.receipt_id, method.receipt_id):
        raise CandidateProvenanceIntegrityError(
            "Original OCR evidence belongs to another receipt."
        )
    tokens = output.source_evidence.tokens
    if pv.selected() is not None:
        pv.exact(tokens, tuple)
        count = len(tokens)
        pv.reserve(max_tokens=count, max_temporary_slots=count, max_work_units=3 * count)
        pv.screen(tokens, tuple[OcrSourceToken, ...])
    token_ids = tuple(token.token_id for token in tokens)
    if len(token_ids) != len(pv.unique_keys(token_ids)):
        raise CandidateProvenanceIntegrityError(
            "Original receipt OCR token IDs must be unique."
        )
    if any(pv.not_equal(token.receipt_id, method.receipt_id) for token in tokens):
        raise CandidateProvenanceIntegrityError(
            "Every original OCR token must belong to the altered candidate receipt."
        )
    if pv.selected() is None:
        return {token.token_id: token for token in tokens}
    index = pv.LinearKeys()
    for token in tokens:
        index[token.token_id] = token
    return index


@pv.operation
def _validate_spans(
    contribution: ProposalProvenanceAuditV0,
    token_by_id: _TokenIndex,
) -> tuple[str, ...]:
    pv.screen(contribution, ProposalProvenanceAuditV0)
    if pv.selected() is not None:
        pv.exact(token_by_id, pv.LinearKeys)
        count = len(contribution.source_spans)
        pv.reserve(max_spans=count, max_work_units=8 * count)
        seen = pv.LinearKeys()
    else:
        seen = None
    ordered_token_ids: list[str] = []
    for span in contribution.source_spans:
        token = token_by_id.get(span.token_id)
        if token is None:
            if seen is not None:
                raise CandidateProvenanceIntegrityError("Unknown original OCR token ID.")
            raise CandidateProvenanceIntegrityError(
                f"Unknown original OCR token ID {span.token_id!r}."
            )
        pv.screen(token, OcrSourceToken)
        if pv.not_equal(token.receipt_id, contribution.parent_identity.receipt_id):
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
        literal = pv.slice_span(token.original_text, span.start, span.end)
        if pv.not_equal(span.text, literal):
            raise CandidateProvenanceIntegrityError(
                "Candidate source span text does not equal the original OCR slice."
            )
        if seen is not None:
            if span.token_id not in seen:
                seen[span.token_id] = None
        elif span.token_id not in ordered_token_ids:
            ordered_token_ids.append(span.token_id)
    if seen is not None:
        pv.reserve(max_temporary_slots=len(seen), max_work_units=len(seen))
        expected = tuple(key for key, _ in seen.items())
    else:
        expected = tuple(ordered_token_ids)
    if pv.not_equal(contribution.source_token_ids, expected):
        raise CandidateProvenanceIntegrityError(
            "Candidate source-token IDs must equal first span appearance order."
        )
    return expected


@pv.operation
def _project_contribution(
    contribution: ProposalProvenanceAuditV0,
    token_by_id: _TokenIndex,
) -> _ProjectionDraft | ProvenanceBlockingRecordV0:
    source_token_ids = _validate_spans(contribution, token_by_id)
    blocking = _blocking_shape(contribution)
    if blocking is not None:
        pv.reserve(max_records=1, max_temporary_slots=5, max_work_units=5)
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
    if pv.selected() is not None:
        pv.reserve(max_records=2, max_temporary_slots=18, max_work_units=18)
        pv.reserve_shared_provenance(
            (provenance_id, identity.receipt_id, identity.field_id, identity.candidate_id,
             original_observed_value, PROPOSED_CONTRACT_VERSION)
            + (() if generic_rule_id is None else (generic_rule_id,)),
            source_token_ids, contribution.source_spans,
        )
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


@pv.operation
def _materialize_one(
    source_audit: AlteredCandidateProvenanceAuditV0,
    token_by_id: _TokenIndex,
) -> (
    AlteredCandidateProvenanceMaterializationV0
    | BlockedAlteredCandidateProvenanceV0
):
    pv.screen(source_audit, AlteredCandidateProvenanceAuditV0)
    if pv.selected() is not None:
        count = len(source_audit.contributions)
        pv.reserve(max_contributions=count, max_temporary_slots=count, max_work_units=3 * count)
    for contribution in source_audit.contributions:
        _validate_identity_projection_state(contribution)
    if pv.not_equal(source_audit.has_blocked_contributions, any(
        contribution.is_blocked for contribution in source_audit.contributions
    )):
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
        if pv.selected() is not None:
            pv.reserve(max_records=1, max_temporary_slots=4 + len(blocked),
                       max_work_units=4 + len(blocked))
        return BlockedAlteredCandidateProvenanceV0(
            source_audit=source_audit,
            blocking_records=tuple(blocked),
        )

    by_payload = pv.key_table()
    for draft in projected:
        pv.reserve(max_temporary_slots=1, max_work_units=1)
        by_payload.setdefault(draft.payload_json, []).append(draft)

    def member(payload_json, drafts):
        if pv.selected() is not None:
            slots = 6 + len(drafts)
            pv.reserve(max_records=1, max_temporary_slots=slots, max_work_units=slots)
        return ProvenanceMemberProjectionV0(
            provenance=drafts[0].provenance,
            identity_payload=drafts[0].payload,
            identity_payload_json=payload_json,
            contributing_proposal_references=tuple(draft.proposal_reference for draft in drafts),
        )
    created = (member(payload_json, drafts) for payload_json, drafts in by_payload.items())
    if pv.selected() is not None:
        pv.reserve(max_temporary_slots=len(by_payload), max_work_units=len(by_payload))
        created = tuple(created)
    members = pv.sort_members(created, _member_key)
    pv.reserve(max_records=1, max_temporary_slots=4, max_work_units=4)
    return AlteredCandidateProvenanceMaterializationV0(
        source_audit=source_audit,
        members=members,
    )


@pv.operation
def _derive_materialization(
    identity_preparation: CandidateIdentityPreparationResultV0,
) -> tuple[
    tuple[AlteredCandidateProvenanceMaterializationV0, ...],
    tuple[BlockedAlteredCandidateProvenanceV0, ...],
]:
    pv.exact(identity_preparation, CandidateIdentityPreparationResultV0)
    try:
        identity_preparation.__post_init__()
    except (TypeError, ValueError) as exc:
        raise CandidateProvenanceIntegrityError(
            "Identity preparation failed complete upstream reconstruction."
        ) from exc
    if pv.selected() is not None:
        pv.exact(identity_preparation.altered_candidates, tuple)
        count = len(identity_preparation.altered_candidates)
        pv.reserve(max_groups=count, max_temporary_slots=2 * count + 2,
                   max_work_units=2 * count + 2)
    token_by_id = _receipt_tokens(identity_preparation)
    materialized: list[AlteredCandidateProvenanceMaterializationV0] = []
    blocked: list[BlockedAlteredCandidateProvenanceV0] = []
    payload_by_id = pv.key_table()
    for source_audit in identity_preparation.altered_candidates:
        outcome = _materialize_one(source_audit, token_by_id)
        if isinstance(outcome, BlockedAlteredCandidateProvenanceV0):
            blocked.append(outcome)
            continue
        if pv.selected() is not None:
            pv.reserve(max_work_units=len(outcome.members))
        for member in outcome.members:
            provenance_id = member.provenance.provenance_id
            previous_payload = payload_by_id.get(provenance_id)
            if previous_payload is not None and pv.not_equal(previous_payload, member.identity_payload_json):
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

    @pv.operation
    def __post_init__(self) -> None:
        if pv.selected() is not None:
            pv.exact(self, CandidateProvenanceMaterializationResultV0)
            pv.exact(self.identity_preparation, CandidateIdentityPreparationResultV0)
            pv.screen(self.materialized_candidates, tuple[AlteredCandidateProvenanceMaterializationV0, ...])
            pv.screen(self.blocked_candidates, tuple[BlockedAlteredCandidateProvenanceV0, ...])
            pv.screen(self.identity_preparation.altered_candidates, tuple[AlteredCandidateProvenanceAuditV0, ...])
            count = (len(self.identity_preparation.altered_candidates)
                     + 2 * (len(self.materialized_candidates) + len(self.blocked_candidates)))
            pv.reserve(max_temporary_slots=count, max_work_units=2 * count + 4)
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
        if len(output_ids) != len(pv.unique_keys(output_ids)) or pv.different_keys(output_ids, upstream_ids):
            raise CandidateProvenanceIntegrityError(
                "Every altered identity must occur in exactly one provenance partition."
            )
        if pv.not_equal(self.component_version, PROVENANCE_MATERIALIZER_VERSION):
            raise ValueError("Unsupported provenance materializer version.")
        if pv.not_equal(self.record_version, PROVENANCE_MATERIALIZATION_RECORD_VERSION):
            raise ValueError("Unsupported provenance materialization record version.")
        expected_materialized, expected_blocked = _derive_materialization(
            self.identity_preparation
        )
        if (
            pv.not_equal(self.materialized_candidates, expected_materialized)
            or pv.not_equal(self.blocked_candidates, expected_blocked)
        ):
            raise CandidateProvenanceIntegrityError(
                "Materialization result must equal its complete deterministic derivation."
            )


@pv.operation
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
    pv.reserve(max_records=1, max_temporary_slots=7, max_work_units=7)
    return CandidateProvenanceMaterializationResultV0(
        identity_preparation=identity_preparation,
        original_candidate=identity_preparation.original_candidate,
        materialized_candidates=materialized,
        blocked_candidates=blocked,
        equivalent_to_c0=identity_preparation.equivalent_to_c0,
    )
