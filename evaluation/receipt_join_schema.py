"""Immutable synthetic-only receipt-join records for offline evaluation.

The records in this module preserve an explicit association boundary between
runtime prediction identities and independent reference identities.  They do
not infer associations, authenticate external evidence, or authorize real-data
evaluation.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from evaluation.manifest_schema import EvaluationManifest
from evaluation.prediction_schema import EvaluationRunScope, PredictionBundle
from evaluation.reference_schema import TierAReferenceReceipt, to_json_compatible


RECEIPT_JOIN_SCHEMA_VERSION = "0"
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text.")


def _require_identifier(value: object, name: str) -> None:
    _require_text(value, name)
    assert isinstance(value, str)
    if _IDENTIFIER_RE.fullmatch(value) is None:
        raise ValueError(f"{name} has an invalid identifier format.")


def _require_optional_identifier(value: object, name: str) -> None:
    if value is not None:
        _require_identifier(value, name)


def _require_tuple(value: object, name: str) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple.")


def _require_unique_identifiers(values: tuple[str, ...], name: str) -> None:
    _require_tuple(values, name)
    for value in values:
        _require_identifier(value, f"{name} member")
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must not contain duplicates.")


def _require_schema_version(value: object) -> None:
    if value != RECEIPT_JOIN_SCHEMA_VERSION:
        raise ValueError(
            f"This module implements receipt-join schema "
            f"{RECEIPT_JOIN_SCHEMA_VERSION}."
        )


class ReceiptJoinOutcome(str, Enum):
    """One terminal receipt-coverage outcome within a join set."""

    JOINED = "JOINED"
    REFERENCE_ONLY = "REFERENCE_ONLY"
    PREDICTION_ONLY = "PREDICTION_ONLY"


class ReceiptJoinEvidenceKind(str, Enum):
    """The claim supported by an entry's evidence."""

    IDENTITY_ASSOCIATION = "IDENTITY_ASSOCIATION"
    COVERAGE_ABSENCE = "COVERAGE_ABSENCE"


class ReceiptJoinVerificationState(str, Enum):
    """Declared evidence state; the enum itself is not authentication."""

    UNVERIFIED = "UNVERIFIED"
    DECLARED = "DECLARED"
    INDEPENDENTLY_VERIFIED = "INDEPENDENTLY_VERIFIED"


class ReceiptJoinAuthorizationState(str, Enum):
    """Declared join-authorization state; external authority remains separate."""

    UNAVAILABLE = "UNAVAILABLE"
    DECLARED = "DECLARED"
    INDEPENDENTLY_VERIFIED = "INDEPENDENTLY_VERIFIED"


class ReceiptJoinTrustBoundaryKind(str, Enum):
    """Trust registries permitted by this synthetic-only V0 implementation."""

    SYNTHETIC_FIXTURE = "SYNTHETIC_FIXTURE"


@dataclass(frozen=True, slots=True)
class ReceiptJoinProvenance:
    """Audit references for one join, revision, or trust-context event."""

    event_id: str
    process_version: str
    source_references: tuple[str, ...]
    actor_reference: str
    recorded_at: str | None = None
    schema_version: str = RECEIPT_JOIN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_identifier(self.event_id, "join provenance event_id")
        _require_identifier(self.process_version, "join provenance process_version")
        _require_unique_identifiers(
            self.source_references, "join provenance source_references"
        )
        if not self.source_references:
            raise ValueError("Join provenance requires at least one source reference.")
        _require_identifier(self.actor_reference, "join provenance actor_reference")
        if self.recorded_at is not None:
            _require_text(self.recorded_at, "join provenance recorded_at")
        _require_schema_version(self.schema_version)


@dataclass(frozen=True, slots=True)
class ReceiptJoinVerificationEvidence:
    """Metadata naming an external verification event, not proof by itself."""

    verification_event_id: str
    verifier_reference: str
    verification_record_reference: str
    verified_at: str | None = None
    schema_version: str = RECEIPT_JOIN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_identifier(self.verification_event_id, "verification_event_id")
        _require_identifier(self.verifier_reference, "verifier_reference")
        _require_identifier(
            self.verification_record_reference, "verification_record_reference"
        )
        if self.verified_at is not None:
            _require_text(self.verified_at, "verified_at")
        _require_schema_version(self.schema_version)


@dataclass(frozen=True, slots=True)
class ReceiptJoinEvidence:
    """Outcome-specific association or coverage/absence evidence metadata."""

    kind: ReceiptJoinEvidenceKind
    state: ReceiptJoinVerificationState
    evidence_references: tuple[str, ...] = ()
    verification: ReceiptJoinVerificationEvidence | None = None
    unavailable_reason: str | None = None
    schema_version: str = RECEIPT_JOIN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ReceiptJoinEvidenceKind):
            raise TypeError("kind must be a ReceiptJoinEvidenceKind.")
        if not isinstance(self.state, ReceiptJoinVerificationState):
            raise TypeError("state must be a ReceiptJoinVerificationState.")
        _require_unique_identifiers(
            self.evidence_references, "join evidence_references"
        )
        if self.verification is not None and not isinstance(
            self.verification, ReceiptJoinVerificationEvidence
        ):
            raise TypeError("verification has an invalid type.")

        if self.state is ReceiptJoinVerificationState.UNVERIFIED:
            if self.evidence_references or self.verification is not None:
                raise ValueError(
                    "UNVERIFIED evidence cannot contain declared or verified evidence."
                )
            _require_text(self.unavailable_reason, "evidence unavailable_reason")
        else:
            if not self.evidence_references:
                raise ValueError("Declared evidence requires evidence references.")
            if self.unavailable_reason is not None:
                raise ValueError("Present evidence cannot have unavailable_reason.")
            if self.state is ReceiptJoinVerificationState.INDEPENDENTLY_VERIFIED:
                if not isinstance(
                    self.verification, ReceiptJoinVerificationEvidence
                ):
                    raise ValueError(
                        "INDEPENDENTLY_VERIFIED evidence requires verification metadata."
                    )
            elif self.verification is not None:
                raise ValueError(
                    "Declared evidence cannot contain independent verification metadata."
                )
        _require_schema_version(self.schema_version)


@dataclass(frozen=True, slots=True)
class ReceiptJoinAuthorization:
    """Authorization metadata whose references are not self-authenticating."""

    state: ReceiptJoinAuthorizationState
    authority_reference: str | None = None
    authorization_record_reference: str | None = None
    verification: ReceiptJoinVerificationEvidence | None = None
    unavailable_reason: str | None = None
    schema_version: str = RECEIPT_JOIN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.state, ReceiptJoinAuthorizationState):
            raise TypeError("state must be a ReceiptJoinAuthorizationState.")
        if self.verification is not None and not isinstance(
            self.verification, ReceiptJoinVerificationEvidence
        ):
            raise TypeError("authorization verification has an invalid type.")

        if self.state is ReceiptJoinAuthorizationState.UNAVAILABLE:
            if (
                self.authority_reference is not None
                or self.authorization_record_reference is not None
                or self.verification is not None
            ):
                raise ValueError(
                    "Unavailable authorization cannot contain authority or verification."
                )
            _require_text(
                self.unavailable_reason, "authorization unavailable_reason"
            )
        else:
            _require_identifier(self.authority_reference, "authority_reference")
            _require_identifier(
                self.authorization_record_reference,
                "authorization_record_reference",
            )
            if self.unavailable_reason is not None:
                raise ValueError(
                    "Present authorization cannot have unavailable_reason."
                )
            if self.state is ReceiptJoinAuthorizationState.INDEPENDENTLY_VERIFIED:
                if not isinstance(
                    self.verification, ReceiptJoinVerificationEvidence
                ):
                    raise ValueError(
                        "INDEPENDENTLY_VERIFIED authorization requires verification "
                        "metadata."
                    )
            elif self.verification is not None:
                raise ValueError(
                    "Declared authorization cannot contain verification metadata."
                )
        _require_schema_version(self.schema_version)


@dataclass(frozen=True, slots=True)
class ReceiptJoinEntry:
    """One explicit terminal coverage record for one or both receipt sides."""

    join_entry_id: str
    outcome: ReceiptJoinOutcome
    runtime_receipt_id: str | None
    reference_receipt_id: str | None
    evidence: ReceiptJoinEvidence
    provenance: ReceiptJoinProvenance
    unmatched_reason: str | None = None
    schema_version: str = RECEIPT_JOIN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_identifier(self.join_entry_id, "join_entry_id")
        if not isinstance(self.outcome, ReceiptJoinOutcome):
            raise TypeError("outcome must be a ReceiptJoinOutcome.")
        if not isinstance(self.evidence, ReceiptJoinEvidence):
            raise TypeError("evidence must be a ReceiptJoinEvidence.")
        if not isinstance(self.provenance, ReceiptJoinProvenance):
            raise TypeError("provenance must be a ReceiptJoinProvenance.")

        if self.outcome is ReceiptJoinOutcome.JOINED:
            _require_text(self.runtime_receipt_id, "runtime_receipt_id")
            _require_identifier(self.reference_receipt_id, "reference_receipt_id")
            if self.evidence.kind is not ReceiptJoinEvidenceKind.IDENTITY_ASSOCIATION:
                raise ValueError("JOINED requires identity-association evidence.")
            if self.unmatched_reason is not None:
                raise ValueError("JOINED cannot contain unmatched_reason.")
        elif self.outcome is ReceiptJoinOutcome.REFERENCE_ONLY:
            if self.runtime_receipt_id is not None:
                raise ValueError(
                    "REFERENCE_ONLY must not fabricate a runtime receipt identity."
                )
            _require_identifier(self.reference_receipt_id, "reference_receipt_id")
            if self.evidence.kind is not ReceiptJoinEvidenceKind.COVERAGE_ABSENCE:
                raise ValueError(
                    "REFERENCE_ONLY requires coverage/absence evidence."
                )
            _require_text(self.unmatched_reason, "unmatched_reason")
        else:
            _require_text(self.runtime_receipt_id, "runtime_receipt_id")
            if self.reference_receipt_id is not None:
                raise ValueError(
                    "PREDICTION_ONLY must not fabricate a reference receipt identity."
                )
            if self.evidence.kind is not ReceiptJoinEvidenceKind.COVERAGE_ABSENCE:
                raise ValueError(
                    "PREDICTION_ONLY requires coverage/absence evidence."
                )
            _require_text(self.unmatched_reason, "unmatched_reason")
        _require_schema_version(self.schema_version)


@dataclass(frozen=True, slots=True)
class ReceiptJoinSet:
    """One revision joining one complete prediction bundle to one population."""

    join_set_id: str
    join_set_version: str
    revision_id: str
    manifest_id: str
    manifest_version: str
    dataset_version: str
    prediction_bundle_id: str
    prediction_scope: EvaluationRunScope
    entries: tuple[ReceiptJoinEntry, ...]
    authorization: ReceiptJoinAuthorization
    provenance: ReceiptJoinProvenance
    predecessor_revision_id: str | None = None
    amendment_reason: str | None = None
    amendment_provenance: ReceiptJoinProvenance | None = None
    schema_version: str = RECEIPT_JOIN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for value, name in (
            (self.join_set_id, "join_set_id"),
            (self.join_set_version, "join_set_version"),
            (self.revision_id, "revision_id"),
            (self.manifest_id, "manifest_id"),
            (self.manifest_version, "manifest_version"),
            (self.dataset_version, "dataset_version"),
            (self.prediction_bundle_id, "prediction_bundle_id"),
        ):
            _require_identifier(value, name)
        if not isinstance(self.prediction_scope, EvaluationRunScope):
            raise TypeError("prediction_scope must be an EvaluationRunScope.")
        _require_tuple(self.entries, "join entries")
        if any(not isinstance(item, ReceiptJoinEntry) for item in self.entries):
            raise TypeError("entries contains an invalid join entry.")
        if not isinstance(self.authorization, ReceiptJoinAuthorization):
            raise TypeError("authorization must be a ReceiptJoinAuthorization.")
        if not isinstance(self.provenance, ReceiptJoinProvenance):
            raise TypeError("provenance must be a ReceiptJoinProvenance.")

        _require_optional_identifier(
            self.predecessor_revision_id, "predecessor_revision_id"
        )
        if self.predecessor_revision_id is None:
            if self.amendment_reason is not None or self.amendment_provenance is not None:
                raise ValueError(
                    "An initial revision cannot contain amendment metadata."
                )
        else:
            _require_text(self.amendment_reason, "amendment_reason")
            if not isinstance(self.amendment_provenance, ReceiptJoinProvenance):
                raise ValueError(
                    "A successor revision requires amendment provenance."
                )
            if self.authorization.state is ReceiptJoinAuthorizationState.UNAVAILABLE:
                raise ValueError(
                    "A successor revision requires at least declared authorization."
                )
        _require_schema_version(self.schema_version)


@dataclass(frozen=True, slots=True)
class ReceiptJoinTrustedEntryClaim:
    """External synthetic trust claim bound to one exact join entry."""

    claim_id: str
    verification: ReceiptJoinVerificationEvidence
    manifest_id: str
    manifest_version: str
    dataset_version: str
    prediction_bundle_id: str
    prediction_scope: EvaluationRunScope
    join_set_id: str
    join_set_version: str
    revision_id: str
    join_entry_id: str
    outcome: ReceiptJoinOutcome
    runtime_receipt_id: str | None
    reference_receipt_id: str | None
    evidence_references: tuple[str, ...]
    schema_version: str = RECEIPT_JOIN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for value, name in (
            (self.claim_id, "trusted entry claim_id"),
            (self.manifest_id, "trusted entry manifest_id"),
            (self.manifest_version, "trusted entry manifest_version"),
            (self.dataset_version, "trusted entry dataset_version"),
            (self.prediction_bundle_id, "trusted entry prediction_bundle_id"),
            (self.join_set_id, "trusted entry join_set_id"),
            (self.join_set_version, "trusted entry join_set_version"),
            (self.revision_id, "trusted entry revision_id"),
            (self.join_entry_id, "trusted entry join_entry_id"),
        ):
            _require_identifier(value, name)
        if not isinstance(self.verification, ReceiptJoinVerificationEvidence):
            raise TypeError(
                "trusted entry verification must be "
                "ReceiptJoinVerificationEvidence."
            )
        if not isinstance(self.prediction_scope, EvaluationRunScope):
            raise TypeError(
                "trusted entry prediction_scope must be an EvaluationRunScope."
            )
        if not isinstance(self.outcome, ReceiptJoinOutcome):
            raise TypeError("trusted entry outcome must be a ReceiptJoinOutcome.")
        _require_unique_identifiers(
            self.evidence_references, "trusted entry evidence_references"
        )
        if not self.evidence_references:
            raise ValueError("A trusted entry claim requires evidence references.")

        if self.outcome is ReceiptJoinOutcome.JOINED:
            _require_text(
                self.runtime_receipt_id, "trusted entry runtime_receipt_id"
            )
            _require_identifier(
                self.reference_receipt_id, "trusted entry reference_receipt_id"
            )
        elif self.outcome is ReceiptJoinOutcome.REFERENCE_ONLY:
            if self.runtime_receipt_id is not None:
                raise ValueError(
                    "A REFERENCE_ONLY trusted claim cannot name a runtime receipt."
                )
            _require_identifier(
                self.reference_receipt_id, "trusted entry reference_receipt_id"
            )
        else:
            _require_text(
                self.runtime_receipt_id, "trusted entry runtime_receipt_id"
            )
            if self.reference_receipt_id is not None:
                raise ValueError(
                    "A PREDICTION_ONLY trusted claim cannot name a reference receipt."
                )
        _require_schema_version(self.schema_version)

    @property
    def verification_event_id(self) -> str:
        """Return the exact verification-event identity carried by the claim."""

        return self.verification.verification_event_id


@dataclass(frozen=True, slots=True)
class ReceiptJoinTrustedAuthorizationClaim:
    """External synthetic trust claim bound to one exact set authorization."""

    claim_id: str
    verification: ReceiptJoinVerificationEvidence
    manifest_id: str
    manifest_version: str
    dataset_version: str
    prediction_bundle_id: str
    prediction_scope: EvaluationRunScope
    join_set_id: str
    join_set_version: str
    revision_id: str
    authority_reference: str
    authorization_record_reference: str
    schema_version: str = RECEIPT_JOIN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for value, name in (
            (self.claim_id, "trusted authorization claim_id"),
            (self.manifest_id, "trusted authorization manifest_id"),
            (self.manifest_version, "trusted authorization manifest_version"),
            (self.dataset_version, "trusted authorization dataset_version"),
            (
                self.prediction_bundle_id,
                "trusted authorization prediction_bundle_id",
            ),
            (self.join_set_id, "trusted authorization join_set_id"),
            (self.join_set_version, "trusted authorization join_set_version"),
            (self.revision_id, "trusted authorization revision_id"),
            (self.authority_reference, "trusted authorization authority_reference"),
            (
                self.authorization_record_reference,
                "trusted authorization authorization_record_reference",
            ),
        ):
            _require_identifier(value, name)
        if not isinstance(self.verification, ReceiptJoinVerificationEvidence):
            raise TypeError(
                "trusted authorization verification must be "
                "ReceiptJoinVerificationEvidence."
            )
        if not isinstance(self.prediction_scope, EvaluationRunScope):
            raise TypeError(
                "trusted authorization prediction_scope must be an "
                "EvaluationRunScope."
            )
        _require_schema_version(self.schema_version)

    @property
    def verification_event_id(self) -> str:
        """Return the exact verification-event identity carried by the claim."""

        return self.verification.verification_event_id


@dataclass(frozen=True, slots=True)
class ReceiptJoinTrustContext:
    """External, claim-bound synthetic trust data for readiness validation."""

    context_id: str
    boundary_kind: ReceiptJoinTrustBoundaryKind
    entry_claims: tuple[ReceiptJoinTrustedEntryClaim, ...]
    authorization_claims: tuple[ReceiptJoinTrustedAuthorizationClaim, ...]
    provenance: ReceiptJoinProvenance
    schema_version: str = RECEIPT_JOIN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_identifier(self.context_id, "trust context_id")
        if not isinstance(self.boundary_kind, ReceiptJoinTrustBoundaryKind):
            raise TypeError("boundary_kind must be a ReceiptJoinTrustBoundaryKind.")
        _require_tuple(self.entry_claims, "trust-context entry_claims")
        if any(
            not isinstance(item, ReceiptJoinTrustedEntryClaim)
            for item in self.entry_claims
        ):
            raise TypeError("entry_claims contains an invalid trusted claim.")
        _require_tuple(
            self.authorization_claims, "trust-context authorization_claims"
        )
        if any(
            not isinstance(item, ReceiptJoinTrustedAuthorizationClaim)
            for item in self.authorization_claims
        ):
            raise TypeError(
                "authorization_claims contains an invalid trusted claim."
            )
        claims = (*self.entry_claims, *self.authorization_claims)
        claim_ids = tuple(item.claim_id for item in claims)
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("Trust-context claim IDs must be unique.")
        event_ids = tuple(item.verification_event_id for item in claims)
        if len(event_ids) != len(set(event_ids)):
            raise ValueError(
                "A synthetic verification event cannot support multiple trust claims."
            )
        if not isinstance(self.provenance, ReceiptJoinProvenance):
            raise TypeError("trust-context provenance has an invalid type.")
        _require_schema_version(self.schema_version)


def _canonical_join_set_payload(join_set: ReceiptJoinSet) -> dict[str, Any]:
    payload = to_json_compatible(join_set)
    payload["entries"] = sorted(
        payload["entries"],
        key=lambda item: (
            item["outcome"],
            item["reference_receipt_id"] or "",
            item["runtime_receipt_id"] or "",
            item["join_entry_id"],
        ),
    )
    payload["provenance"]["source_references"] = sorted(
        payload["provenance"]["source_references"]
    )
    if payload["amendment_provenance"] is not None:
        payload["amendment_provenance"]["source_references"] = sorted(
            payload["amendment_provenance"]["source_references"]
        )
    for entry in payload["entries"]:
        entry["evidence"]["evidence_references"] = sorted(
            entry["evidence"]["evidence_references"]
        )
        entry["provenance"]["source_references"] = sorted(
            entry["provenance"]["source_references"]
        )
    return payload


def serialize_receipt_join_set(
    join_set: ReceiptJoinSet,
    *,
    manifest: EvaluationManifest,
    prediction_bundle: PredictionBundle,
    reference_receipts: tuple[TierAReferenceReceipt, ...],
) -> str:
    """Structurally validate and canonically serialize one join-set revision."""

    from evaluation.receipt_join_validation import validate_receipt_join_set

    validate_receipt_join_set(
        join_set,
        manifest=manifest,
        prediction_bundle=prediction_bundle,
        reference_receipts=reference_receipts,
    )
    return json.dumps(
        _canonical_join_set_payload(join_set),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def serialize_receipt_join_collection(
    join_sets: tuple[ReceiptJoinSet, ...],
    *,
    manifests: tuple[EvaluationManifest, ...],
    prediction_bundles: tuple[PredictionBundle, ...],
    reference_receipts: tuple[TierAReferenceReceipt, ...],
) -> str:
    """Validate lineage and serialize all revisions without collapsing history."""

    from evaluation.receipt_join_validation import validate_receipt_join_collection

    validate_receipt_join_collection(
        join_sets,
        manifests=manifests,
        prediction_bundles=prediction_bundles,
        reference_receipts=reference_receipts,
    )
    payload = [_canonical_join_set_payload(item) for item in join_sets]
    payload.sort(
        key=lambda item: (
            item["manifest_id"],
            item["manifest_version"],
            item["prediction_scope"]["dataset_id"],
            item["dataset_version"],
            item["prediction_scope"]["partition_id"],
            item["prediction_scope"]["cohort_id"],
            item["prediction_bundle_id"],
            item["prediction_scope"]["run_id"],
            item["prediction_scope"]["system_id"],
            item["prediction_scope"]["configuration_id"],
            item["prediction_scope"]["output_stage"],
            item["join_set_id"],
            item["join_set_version"],
            item["revision_id"],
        )
    )
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


__all__ = (
    "RECEIPT_JOIN_SCHEMA_VERSION",
    "ReceiptJoinAuthorization",
    "ReceiptJoinAuthorizationState",
    "ReceiptJoinEntry",
    "ReceiptJoinEvidence",
    "ReceiptJoinEvidenceKind",
    "ReceiptJoinOutcome",
    "ReceiptJoinProvenance",
    "ReceiptJoinSet",
    "ReceiptJoinTrustBoundaryKind",
    "ReceiptJoinTrustContext",
    "ReceiptJoinTrustedAuthorizationClaim",
    "ReceiptJoinTrustedEntryClaim",
    "ReceiptJoinVerificationEvidence",
    "ReceiptJoinVerificationState",
    "serialize_receipt_join_collection",
    "serialize_receipt_join_set",
)
