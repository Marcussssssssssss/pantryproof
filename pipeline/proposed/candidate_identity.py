"""Deterministic candidate identity and lossless local provenance audits.

This component materializes permanent c0 as one shared ORIGINAL candidate.
Altered values remain component-local identity drafts because preliminary rank
and candidate-limit results do not exist yet.  Every raw proposal remains in a
lossless audit, including provenance that cannot yet map safely into the shared
V1 provenance shape.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pipeline.proposed.candidate_deduplication import (
    NORMALIZATION_PROFILE_ID,
    CandidateDeduplicationResultV0,
    CandidateNormalizationV0,
    DeduplicatedAlteredGroupV0,
    EquivalentToC0AuditV0,
)
from pipeline.proposed.candidate_generation import (
    AlteredCandidateProposalV0,
    CandidateGenerationResultV0,
    DateDiscoveryCandidateProposalV0,
    OriginalCandidateDraftV0,
)
from pipeline.proposed.contracts import (
    B3CompatibleSeedV1,
    PROPOSED_CONTRACT_VERSION,
    CandidateLimitStatus,
    CandidateProvenanceV1,
    CandidateRecordV1,
    CandidateRole,
    CandidateSourceKind,
    MethodReadyFieldV1,
    SourceCharacterSpanV1,
)
from pipeline.proposed.identity_replay_meter_v1 import (
    IdentityReplayMeterCodeV1,
    identity_missing_member,
    identity_not_equal,
    identity_operation,
    identity_scalar_equal,
    identity_scalar_not_equal,
    reserve_identity,
    selected_meter,
)


ALTERED_IDENTITY_SCHEMA_VERSION = "pantryproof-altered-candidate-id-v1"
ORIGINAL_PROVENANCE_SCHEMA_VERSION = "pantryproof-original-provenance-id-v1"
CANDIDATE_IDENTITY_COMPONENT_VERSION = "candidate-identity-v0"
CANDIDATE_IDENTITY_RECORD_VERSION = "candidate-identity-record-v0"

ALTERED_CANDIDATE_ID_PREFIX = "pp:candidate:altered:v1:sha256:"
ORIGINAL_PROVENANCE_ID_PREFIX = "pp:provenance:original:v1:sha256:"

_COMPOSITE_REASON = (
    "Generic normalization has multiple rule IDs without a verified "
    "event-to-rule mapping."
)
_MISSING_TOKENS_REASON = (
    "Source/neighbour provenance has no genuine candidate-specific token spans."
)


class CandidateIdentityIntegrityError(ValueError):
    """Identity or provenance output contradicts its validated upstream input."""


class ProvenanceProjectionClassificationV0(str, Enum):
    """Nonbinding readiness classification for later shared provenance work."""

    PROJECTION_DEFERRED = "PROJECTION_DEFERRED"
    BLOCKED_COMPOSITE_GENERIC_RULES = "BLOCKED_COMPOSITE_GENERIC_RULES"
    BLOCKED_MISSING_SOURCE_TOKENS = "BLOCKED_MISSING_SOURCE_TOKENS"


def _require_text(value: str, name: str) -> None:
    if selected_meter() is not None:
        _exact(value, str)
        reserve_identity(max_temporary_slots=len(value), max_work_units=len(value))
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")


def _screen(value: object, hint: object) -> None:
    meter = selected_meter()
    if meter is not None:
        meter.walk(value, hint)


def _exact(value: object, kind: type) -> None:
    meter = selected_meter()
    if meter is not None and type(value) is not kind:
        meter._reject(IdentityReplayMeterCodeV1.INVALID_SHAPE)


def _validate_payload_part(value: Any) -> None:
    if isinstance(value, str):
        return
    if isinstance(value, tuple):
        for item in value:
            _validate_payload_part(item)
        return
    raise CandidateIdentityIntegrityError(
        "Identity payloads may contain only strings and nested tuples."
    )


@identity_operation
def _canonical_identity_json(payload: tuple[Any, ...]) -> tuple[str, bytes]:
    meter = selected_meter()
    if meter is not None:
        if type(payload) is not tuple:
            meter._reject(IdentityReplayMeterCodeV1.INVALID_SHAPE)
        size = meter.walk(payload, canonical=True)
        # Both retained encoding buffers plus serialization/encoding work.
        meter.reserve(max_canonical_bytes=size, max_temporary_slots=2 * size,
                      max_work_units=3 * size)
    if not isinstance(payload, tuple) or not payload:
        raise CandidateIdentityIntegrityError(
            "An identity payload must be a nonempty positional tuple."
        )
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
        raise CandidateIdentityIntegrityError(
            "Identity payload must have a strict canonical UTF-8 representation."
        ) from exc
    return serialized, encoded


def _sha256_hex(encoded: bytes) -> str:
    return hashlib.sha256(encoded).hexdigest()


def _identifier(prefix: str, payload: tuple[Any, ...]) -> tuple[str, str]:
    serialized, encoded = _canonical_identity_json(payload)
    reserve_identity(max_hash_calls=1, max_work_units=len(encoded) + len(prefix) + 64,
                     max_temporary_slots=len(prefix) + 128 + 2)
    return f"{prefix}{_sha256_hex(encoded)}", serialized


def _altered_identity_payload(
    *,
    normalization_profile_id: str,
    receipt_id: str,
    field_id: str,
    c0_candidate_id: str,
    normalized_dedup_key: str,
) -> tuple[str, ...]:
    reserve_identity(max_temporary_slots=6, max_work_units=6)
    return (
        ALTERED_IDENTITY_SCHEMA_VERSION,
        normalization_profile_id,
        receipt_id,
        field_id,
        c0_candidate_id,
        normalized_dedup_key,
    )


def _original_provenance_payload(
    method: MethodReadyFieldV1,
) -> tuple[Any, ...]:
    reserve_identity(max_temporary_slots=6, max_work_units=6)
    return (
        ORIGINAL_PROVENANCE_SCHEMA_VERSION,
        method.receipt_id,
        method.field_id,
        method.c0_candidate_id,
        method.c0_value,
        method.source_token_ids,
    )


@dataclass(frozen=True, slots=True)
class AlteredCandidateIdentityDraftV0:
    """Stable identity for one deduplicated altered value, before ranking."""

    candidate_id: str
    receipt_id: str
    field_id: str
    c0_candidate_id: str
    normalized_dedup_key: str
    representative_value: str
    deduplicated_group: DeduplicatedAlteredGroupV0
    identity_payload: tuple[str, ...]
    identity_payload_json: str
    normalization_profile_id: str = NORMALIZATION_PROFILE_ID
    identity_schema_version: str = ALTERED_IDENTITY_SCHEMA_VERSION
    component_version: str = CANDIDATE_IDENTITY_COMPONENT_VERSION
    record_version: str = CANDIDATE_IDENTITY_RECORD_VERSION

    @identity_operation
    def __post_init__(self) -> None:
        _screen(self, AlteredCandidateIdentityDraftV0)
        for name in (
            "candidate_id",
            "receipt_id",
            "field_id",
            "c0_candidate_id",
            "normalized_dedup_key",
            "representative_value",
            "identity_payload_json",
        ):
            _require_text(getattr(self, name), name)
        if not isinstance(self.deduplicated_group, DeduplicatedAlteredGroupV0):
            raise TypeError("deduplicated_group must be DeduplicatedAlteredGroupV0.")
        method = self.deduplicated_group.representative.method_ready_field
        expected_payload = _altered_identity_payload(
            normalization_profile_id=self.normalization_profile_id,
            receipt_id=method.receipt_id,
            field_id=method.field_id,
            c0_candidate_id=method.c0_candidate_id,
            normalized_dedup_key=(
                self.deduplicated_group.normalization.normalized_key
            ),
        )
        expected_id, expected_json = _identifier(
            ALTERED_CANDIDATE_ID_PREFIX, expected_payload
        )
        reserve_identity(max_temporary_slots=16, max_work_units=16)
        expected = (
            expected_id,
            method.receipt_id,
            method.field_id,
            method.c0_candidate_id,
            self.deduplicated_group.normalization.normalized_key,
            self.deduplicated_group.representative.proposed_value,
            expected_payload,
            expected_json,
        )
        observed = (
            self.candidate_id,
            self.receipt_id,
            self.field_id,
            self.c0_candidate_id,
            self.normalized_dedup_key,
            self.representative_value,
            self.identity_payload,
            self.identity_payload_json,
        )
        if identity_not_equal(observed, expected):
            raise CandidateIdentityIntegrityError(
                "Altered identity must equal its canonical deduplicated derivation."
            )
        if identity_scalar_equal(self.candidate_id, self.c0_candidate_id):
            raise CandidateIdentityIntegrityError(
                "An altered identity cannot reuse permanent c0 identity."
            )
        if identity_scalar_not_equal(self.normalization_profile_id, NORMALIZATION_PROFILE_ID):
            raise ValueError("Unsupported normalization profile.")
        if identity_scalar_not_equal(self.identity_schema_version, ALTERED_IDENTITY_SCHEMA_VERSION):
            raise ValueError("Unsupported altered-candidate identity schema.")
        if identity_scalar_not_equal(self.component_version, CANDIDATE_IDENTITY_COMPONENT_VERSION):
            raise ValueError("Unsupported candidate-identity component version.")
        if identity_scalar_not_equal(self.record_version, CANDIDATE_IDENTITY_RECORD_VERSION):
            raise ValueError("Unsupported candidate-identity record version.")


def _projection_classification(
    proposal: AlteredCandidateProposalV0,
) -> tuple[ProvenanceProjectionClassificationV0, str | None]:
    # Two source-kind guards, the rule count and span presence, then
    # the returned classification pair.
    reserve_identity(max_temporary_slots=2, max_work_units=6)
    if (
        proposal.source_kind is CandidateSourceKind.GENERIC_NORMALIZATION
        and len(proposal.b3_rule_ids) > 1
    ):
        return (
            ProvenanceProjectionClassificationV0.BLOCKED_COMPOSITE_GENERIC_RULES,
            _COMPOSITE_REASON,
        )
    if (
        proposal.source_kind is CandidateSourceKind.SOURCE_TOKEN_OR_NEIGHBOUR
        and not proposal.source_spans
    ):
        return (
            ProvenanceProjectionClassificationV0.BLOCKED_MISSING_SOURCE_TOKENS,
            _MISSING_TOKENS_REASON,
        )
    return ProvenanceProjectionClassificationV0.PROJECTION_DEFERRED, None


def _span_token_ids(
    spans: tuple[SourceCharacterSpanV1, ...],
) -> tuple[str, ...]:
    meter = selected_meter()
    if meter is not None:
        meter.walk(spans, tuple[SourceCharacterSpanV1, ...])
        # Keep first occurrence order. The selected route avoids opaque
        # hash-table probe costs and reserves before each membership attempt.
        ids = []
        for span in spans:
            token_id = span.token_id
            meter.reserve(max_temporary_slots=len(ids), max_work_units=len(ids))
            if identity_missing_member(token_id, tuple(ids)):
                meter.reserve(max_temporary_slots=1, max_work_units=1)
                ids.append(token_id)
        meter.reserve(max_temporary_slots=len(ids), max_work_units=len(ids))
        return tuple(ids)
    return tuple(dict.fromkeys(span.token_id for span in spans))


@dataclass(frozen=True, slots=True)
class ProposalProvenanceAuditV0:
    """Complete proposal evidence plus a nonbinding projection classification."""

    parent_identity: AlteredCandidateIdentityDraftV0
    proposal: AlteredCandidateProposalV0
    proposal_reference: str
    b3_seed: B3CompatibleSeedV1
    source_kind: CandidateSourceKind
    proposed_value: str
    adapter_seed_position: int
    b3_ruleset_id: str
    b3_event_ids: tuple[str, ...]
    b3_rule_ids: tuple[str, ...]
    source_spans: tuple[SourceCharacterSpanV1, ...]
    source_token_ids: tuple[str, ...]
    method_ready_field: MethodReadyFieldV1
    c0_candidate_id: str
    c0_value: str
    projection_classification: ProvenanceProjectionClassificationV0
    projection_reason: str | None
    component_version: str = CANDIDATE_IDENTITY_COMPONENT_VERSION
    record_version: str = CANDIDATE_IDENTITY_RECORD_VERSION

    @identity_operation
    def __post_init__(self) -> None:
        _screen(self, ProposalProvenanceAuditV0)
        if not isinstance(self.parent_identity, AlteredCandidateIdentityDraftV0):
            raise TypeError("parent_identity must be an altered identity draft.")
        if not isinstance(self.proposal, AlteredCandidateProposalV0):
            raise TypeError("proposal must be AlteredCandidateProposalV0.")
        proposal = self.proposal
        if type(proposal) is DateDiscoveryCandidateProposalV0:
            if type(self) is not DateDiscoveryProvenanceAuditV0:
                raise TypeError("D1 proposals require a D1 provenance audit.")
            if (
                not any(proposal is item for item in self.parent_identity.deduplicated_group.contributing_proposals)
                or len(self.source_spans) != 1
                or self.source_spans[0] is not proposal.observation.body_span
            ):
                raise CandidateIdentityIntegrityError("D1 provenance requires its original proposal and body span.")
            b3_ruleset_id = None
        else:
            if type(self) is DateDiscoveryProvenanceAuditV0 or not isinstance(self.b3_seed, B3CompatibleSeedV1):
                raise TypeError("B3 proposal audits require B3CompatibleSeedV1.")
            b3_ruleset_id = proposal.b3_seed.b3_ruleset_id
        if not isinstance(self.method_ready_field, MethodReadyFieldV1):
            raise TypeError("method_ready_field must be MethodReadyFieldV1.")
        if not isinstance(
            self.projection_classification, ProvenanceProjectionClassificationV0
        ):
            raise TypeError("projection_classification has an unsupported type.")
        if identity_missing_member(proposal, self.parent_identity.deduplicated_group.contributing_proposals):
            raise CandidateIdentityIntegrityError(
                "A provenance contribution must belong to its parent group."
            )
        expected_classification, expected_reason = _projection_classification(proposal)
        reserve_identity(max_temporary_slots=30, max_work_units=30)
        expected = (
            proposal.proposal_reference,
            proposal.b3_seed,
            proposal.source_kind,
            proposal.proposed_value,
            proposal.adapter_seed_position,
            b3_ruleset_id,
            proposal.b3_event_ids,
            proposal.b3_rule_ids,
            proposal.source_spans,
            _span_token_ids(proposal.source_spans),
            proposal.method_ready_field,
            proposal.method_ready_field.c0_candidate_id,
            proposal.method_ready_field.c0_value,
            expected_classification,
            expected_reason,
        )
        observed = (
            self.proposal_reference,
            self.b3_seed,
            self.source_kind,
            self.proposed_value,
            self.adapter_seed_position,
            self.b3_ruleset_id,
            self.b3_event_ids,
            self.b3_rule_ids,
            self.source_spans,
            self.source_token_ids,
            self.method_ready_field,
            self.c0_candidate_id,
            self.c0_value,
            self.projection_classification,
            self.projection_reason,
        )
        if identity_not_equal(observed, expected):
            raise CandidateIdentityIntegrityError(
                "Provenance audit must equal its complete proposal derivation."
            )
        if (
            identity_scalar_not_equal(self.method_ready_field.receipt_id, self.parent_identity.receipt_id)
            or identity_scalar_not_equal(self.method_ready_field.field_id, self.parent_identity.field_id)
            or identity_scalar_not_equal(self.c0_candidate_id, self.parent_identity.c0_candidate_id)
        ):
            raise CandidateIdentityIntegrityError(
                "Provenance contribution identity contradicts its parent candidate."
            )
        if identity_scalar_not_equal(self.component_version, CANDIDATE_IDENTITY_COMPONENT_VERSION):
            raise ValueError("Unsupported candidate-identity component version.")
        if identity_scalar_not_equal(self.record_version, CANDIDATE_IDENTITY_RECORD_VERSION):
            raise ValueError("Unsupported candidate-identity record version.")

    @property
    def is_blocked(self) -> bool:
        return (
            self.projection_classification
            is not ProvenanceProjectionClassificationV0.PROJECTION_DEFERRED
        )


@dataclass(frozen=True, slots=True)
class DateDiscoveryProvenanceAuditV0(ProposalProvenanceAuditV0):
    """Local D1 contribution. Its proposal carries the discovery and OCR references."""

    proposal: DateDiscoveryCandidateProposalV0
    b3_seed: None
    adapter_seed_position: None
    b3_ruleset_id: None


@dataclass(frozen=True, slots=True)
class AlteredCandidateProvenanceAuditV0:
    """One altered identity and every ordered proposal contribution behind it."""

    identity: AlteredCandidateIdentityDraftV0
    contributions: tuple[ProposalProvenanceAuditV0, ...]
    has_blocked_contributions: bool
    component_version: str = CANDIDATE_IDENTITY_COMPONENT_VERSION
    record_version: str = CANDIDATE_IDENTITY_RECORD_VERSION

    @identity_operation
    def __post_init__(self) -> None:
        _screen(self, AlteredCandidateProvenanceAuditV0)
        meter = selected_meter()
        if meter is not None:
            # Presence, type scan, parent scan and blocked-classification scan.
            meter.reserve(max_work_units=1 + 3 * len(self.contributions))
        if not isinstance(self.identity, AlteredCandidateIdentityDraftV0):
            raise TypeError("identity must be an altered identity draft.")
        if not self.contributions:
            raise CandidateIdentityIntegrityError(
                "An altered identity requires provenance contributions."
            )
        if any(
            not isinstance(item, ProposalProvenanceAuditV0)
            for item in self.contributions
        ):
            raise TypeError("contributions must contain proposal provenance audits.")
        if any(identity_not_equal(item.parent_identity, self.identity) for item in self.contributions):
            raise CandidateIdentityIntegrityError(
                "Every contribution must reference the same altered identity."
            )
        expected_proposals = self.identity.deduplicated_group.contributing_proposals
        if selected_meter() is not None:
            count = len(self.contributions)
            reserve_identity(max_temporary_slots=count, max_work_units=count)
        if identity_not_equal(tuple(item.proposal for item in self.contributions), expected_proposals):
            raise CandidateIdentityIntegrityError(
                "Contributions must preserve every proposal in canonical order."
            )
        if identity_scalar_not_equal(
            self.has_blocked_contributions, any(item.is_blocked for item in self.contributions)
        ):
            raise CandidateIdentityIntegrityError(
                "Blocked-contribution state must equal the complete audit."
            )
        if identity_scalar_not_equal(self.component_version, CANDIDATE_IDENTITY_COMPONENT_VERSION):
            raise ValueError("Unsupported candidate-identity component version.")
        if identity_scalar_not_equal(self.record_version, CANDIDATE_IDENTITY_RECORD_VERSION):
            raise ValueError("Unsupported candidate-identity record version.")


@identity_operation
def _make_identity(
    deduplication_result: CandidateDeduplicationResultV0,
    group: DeduplicatedAlteredGroupV0,
) -> AlteredCandidateIdentityDraftV0:
    method = deduplication_result.candidate_drafts.original.method_ready_field
    if identity_not_equal(group.representative.method_ready_field, method):
        raise CandidateIdentityIntegrityError(
            "An altered group must share the upstream method-ready identity."
        )
    payload = _altered_identity_payload(
        normalization_profile_id=deduplication_result.profile_id,
        receipt_id=method.receipt_id,
        field_id=method.field_id,
        c0_candidate_id=method.c0_candidate_id,
        normalized_dedup_key=group.normalization.normalized_key,
    )
    candidate_id, payload_json = _identifier(ALTERED_CANDIDATE_ID_PREFIX, payload)
    reserve_identity(max_records=1, max_temporary_slots=13, max_work_units=13)
    return AlteredCandidateIdentityDraftV0(
        candidate_id=candidate_id,
        receipt_id=method.receipt_id,
        field_id=method.field_id,
        c0_candidate_id=method.c0_candidate_id,
        normalized_dedup_key=group.normalization.normalized_key,
        representative_value=group.representative.proposed_value,
        deduplicated_group=group,
        identity_payload=payload,
        identity_payload_json=payload_json,
        normalization_profile_id=deduplication_result.profile_id,
    )


def _make_contribution(
    identity: AlteredCandidateIdentityDraftV0,
    proposal: AlteredCandidateProposalV0,
) -> ProposalProvenanceAuditV0:
    classification, reason = _projection_classification(proposal)
    reserve_identity(max_records=1, max_temporary_slots=17, max_work_units=17)
    audit_type = (
        DateDiscoveryProvenanceAuditV0
        if type(proposal) is DateDiscoveryCandidateProposalV0 else ProposalProvenanceAuditV0
    )
    return audit_type(
        parent_identity=identity,
        proposal=proposal,
        proposal_reference=proposal.proposal_reference,
        b3_seed=proposal.b3_seed,
        source_kind=proposal.source_kind,
        proposed_value=proposal.proposed_value,
        adapter_seed_position=proposal.adapter_seed_position,
        b3_ruleset_id=None if proposal.b3_seed is None else proposal.b3_seed.b3_ruleset_id,
        b3_event_ids=proposal.b3_event_ids,
        b3_rule_ids=proposal.b3_rule_ids,
        source_spans=proposal.source_spans,
        source_token_ids=_span_token_ids(proposal.source_spans),
        method_ready_field=proposal.method_ready_field,
        c0_candidate_id=proposal.method_ready_field.c0_candidate_id,
        c0_value=proposal.method_ready_field.c0_value,
        projection_classification=classification,
        projection_reason=reason,
    )


def _materialize_original_candidate(
    deduplication_result: CandidateDeduplicationResultV0,
) -> CandidateRecordV1:
    method = deduplication_result.candidate_drafts.original.method_ready_field
    payload = _original_provenance_payload(method)
    provenance_id, _ = _identifier(ORIGINAL_PROVENANCE_ID_PREFIX, payload)
    meter = selected_meter()
    if meter is not None:
        meter.reserve_c0_constructors(
            provenance_id=provenance_id, receipt_id=method.receipt_id,
            field_id=method.field_id, candidate_id=method.c0_candidate_id,
            value=method.c0_value, normalized_key=deduplication_result.original_normalization.normalized_key,
            source_token_ids=method.source_token_ids, record_version=PROPOSED_CONTRACT_VERSION,
        )
    provenance = CandidateProvenanceV1(
        provenance_id=provenance_id,
        receipt_id=method.receipt_id,
        field_id=method.field_id,
        candidate_id=method.c0_candidate_id,
        source_kind=CandidateSourceKind.ORIGINAL,
        original_observed_value=method.c0_value,
        source_token_ids=method.source_token_ids,
        source_spans=(),
        source_order_relationship=None,
        source_order_position=None,
        generic_rule_id=None,
        resource_snapshot_id=None,
    )
    return CandidateRecordV1(
        candidate_id=method.c0_candidate_id,
        receipt_id=method.receipt_id,
        field_id=method.field_id,
        c0_candidate_id=method.c0_candidate_id,
        value=method.c0_value,
        normalized_dedup_key=(
            deduplication_result.original_normalization.normalized_key
        ),
        role=CandidateRole.ORIGINAL,
        provenance=(provenance,),
        limit_status=CandidateLimitStatus.RETAINED,
        preliminary_rank=None,
        overflow_reason=None,
    )


@identity_operation
def _derive_preparation(
    deduplication_result: CandidateDeduplicationResultV0,
) -> tuple[
    CandidateRecordV1,
    tuple[AlteredCandidateProvenanceAuditV0, ...],
    EquivalentToC0AuditV0 | None,
]:
    meter = selected_meter()
    if meter is not None:
        _exact(deduplication_result, CandidateDeduplicationResultV0)
        _exact(deduplication_result.candidate_drafts, CandidateGenerationResultV0)
        _exact(deduplication_result.candidate_drafts.original, OriginalCandidateDraftV0)
        _screen(deduplication_result.candidate_drafts.original.method_ready_field, MethodReadyFieldV1)
        _screen(deduplication_result.original_normalization, CandidateNormalizationV0)
        _screen(deduplication_result.profile_id, str)
        _screen(deduplication_result.equivalent_to_c0, EquivalentToC0AuditV0 | None)
        _exact(deduplication_result.altered_groups, tuple)
        groups = len(deduplication_result.altered_groups)
        meter._limit("max_tuple_arity", groups)
        meter.reserve(max_groups=groups, max_temporary_slots=2 + 2 * groups,
                      max_work_units=1 + groups)
        for group in deduplication_result.altered_groups:
            _screen(group, DeduplicatedAlteredGroupV0)
            meter.reserve(max_contributions=len(group.contributing_proposals))
    original = _materialize_original_candidate(deduplication_result)
    altered: list[AlteredCandidateProvenanceAuditV0] = []
    payload_by_candidate_id: dict[str, tuple[str, ...]] = {}
    metered_payloads: list[tuple[str, tuple[str, ...]]] | None = [] if meter is not None else None
    for group in deduplication_result.altered_groups:
        identity = _make_identity(deduplication_result, group)
        if metered_payloads is None:
            prior_payload = payload_by_candidate_id.get(identity.candidate_id)
        else:
            prior_payload = None
            for previous_id, payload in metered_payloads:
                if not identity_not_equal(previous_id, identity.candidate_id):
                    prior_payload = payload
                    break
        if prior_payload is not None and identity_not_equal(prior_payload, identity.identity_payload):
            raise CandidateIdentityIntegrityError(
                "Distinct canonical payloads produced the same candidate ID."
            )
        duplicate = (identity.candidate_id in payload_by_candidate_id
                     if metered_payloads is None else prior_payload is not None)
        if duplicate:
            raise CandidateIdentityIntegrityError(
                "Duplicate altered candidate identity was produced."
            )
        if metered_payloads is None:
            payload_by_candidate_id[identity.candidate_id] = identity.identity_payload
        else:
            reserve_identity(max_temporary_slots=3, max_work_units=3)
            metered_payloads.append((identity.candidate_id, identity.identity_payload))
        if meter is not None:
            count = len(group.contributing_proposals)
            # Contribution construction loop and blocked classification scan.
            reserve_identity(max_temporary_slots=count, max_work_units=2 * count)
        contributions = tuple(
            _make_contribution(identity, proposal)
            for proposal in group.contributing_proposals
        )
        reserve_identity(max_records=1, max_temporary_slots=6, max_work_units=5)
        altered.append(
            AlteredCandidateProvenanceAuditV0(
                identity=identity,
                contributions=contributions,
                has_blocked_contributions=any(
                    contribution.is_blocked for contribution in contributions
                ),
            )
        )
    reserve_identity(max_temporary_slots=3, max_work_units=3)
    return original, tuple(altered), deduplication_result.equivalent_to_c0


@dataclass(frozen=True, slots=True)
class CandidateIdentityPreparationResultV0:
    """Reconstructable c0 materialization and altered provenance-audit output."""

    deduplication_result: CandidateDeduplicationResultV0
    original_candidate: CandidateRecordV1
    altered_candidates: tuple[AlteredCandidateProvenanceAuditV0, ...]
    equivalent_to_c0: EquivalentToC0AuditV0 | None
    component_version: str = CANDIDATE_IDENTITY_COMPONENT_VERSION
    record_version: str = CANDIDATE_IDENTITY_RECORD_VERSION

    @identity_operation
    def __post_init__(self) -> None:
        if selected_meter() is not None:
            _exact(self, CandidateIdentityPreparationResultV0)
            _screen(self.original_candidate, CandidateRecordV1)
            _screen(self.altered_candidates, tuple[AlteredCandidateProvenanceAuditV0, ...])
            _screen(self.equivalent_to_c0, EquivalentToC0AuditV0 | None)
            _screen(self.component_version, str)
            _screen(self.record_version, str)
            reserve_identity(max_work_units=len(self.altered_candidates))
        if not isinstance(self.deduplication_result, CandidateDeduplicationResultV0):
            raise TypeError(
                "deduplication_result must be CandidateDeduplicationResultV0."
            )
        if not isinstance(self.original_candidate, CandidateRecordV1):
            raise TypeError("original_candidate must be CandidateRecordV1.")
        if any(
            not isinstance(item, AlteredCandidateProvenanceAuditV0)
            for item in self.altered_candidates
        ):
            raise TypeError("altered_candidates must contain local altered audits.")
        if self.equivalent_to_c0 is not None and not isinstance(
            self.equivalent_to_c0, EquivalentToC0AuditV0
        ):
            raise TypeError("equivalent_to_c0 must be an equivalence audit or None.")
        if identity_scalar_not_equal(self.component_version, CANDIDATE_IDENTITY_COMPONENT_VERSION):
            raise ValueError("Unsupported candidate-identity component version.")
        if identity_scalar_not_equal(self.record_version, CANDIDATE_IDENTITY_RECORD_VERSION):
            raise ValueError("Unsupported candidate-identity record version.")
        expected = _derive_preparation(self.deduplication_result)
        reserve_identity(max_temporary_slots=3, max_work_units=3)
        if identity_not_equal((
            self.original_candidate,
            self.altered_candidates,
            self.equivalent_to_c0,
        ), expected):
            raise CandidateIdentityIntegrityError(
                "Identity preparation must equal its canonical upstream derivation."
            )


@identity_operation
def prepare_candidate_identities(
    *,
    deduplication_result: CandidateDeduplicationResultV0,
) -> CandidateIdentityPreparationResultV0:
    """Materialize c0 and prepare altered identities without ranking or limiting."""

    if not isinstance(deduplication_result, CandidateDeduplicationResultV0):
        raise TypeError(
            "deduplication_result must be CandidateDeduplicationResultV0."
        )
    original, altered, equivalence = _derive_preparation(deduplication_result)
    reserve_identity(max_records=1, max_temporary_slots=7, max_work_units=7)
    return CandidateIdentityPreparationResultV0(
        deduplication_result=deduplication_result,
        original_candidate=original,
        altered_candidates=altered,
        equivalent_to_c0=equivalence,
    )
