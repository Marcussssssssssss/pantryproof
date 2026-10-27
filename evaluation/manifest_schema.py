"""Immutable offline Tier A dataset-manifest records.

These records describe declared dataset organization only. Structural validity
does not authenticate evidence, approve a cohort, freeze a methodology, or
authorize validation or held-out execution.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum

from evaluation.reference_schema import to_json_compatible


MANIFEST_SCHEMA_VERSION = "0"
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


class DatasetTier(str, Enum):
    """Dataset tier supported by the bounded V0 manifest."""

    TIER_A = "TIER_A"


class PartitionRole(str, Enum):
    """The three independent Tier A partition roles."""

    TRAINING = "TRAINING"
    VALIDATION = "VALIDATION"
    HELD_OUT_TEST = "HELD_OUT_TEST"


class CohortKind(str, Enum):
    """Distinct prospective analysis cohorts; presence is not approval."""

    PRIMARY_TIER_A = "PRIMARY_TIER_A"
    UNSEEN_RETAILER = "UNSEEN_RETAILER"
    BRANCH_GENERALIZATION = "BRANCH_GENERALIZATION"


class RelatedGroupKind(str, Enum):
    """Declared relationship types that must remain partition-co-located."""

    TRANSACTION = "TRANSACTION"
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    NEAR_DUPLICATE = "NEAR_DUPLICATE"
    ALTERNATE_CAPTURE = "ALTERNATE_CAPTURE"
    RELATED_RECORD = "RELATED_RECORD"
    CONTRIBUTOR = "CONTRIBUTOR"


class FittingExclusionEvidenceState(str, Enum):
    """Whether fitting exclusion is merely declared or independently checked."""

    DECLARED = "DECLARED"
    INDEPENDENTLY_VERIFIED = "INDEPENDENTLY_VERIFIED"


class DigestEvidenceState(str, Enum):
    """Authentication boundary for manifest digest evidence."""

    UNAVAILABLE = "UNAVAILABLE"
    DECLARED_DIGEST = "DECLARED_DIGEST"
    VERIFIED_DIGEST = "VERIFIED_DIGEST"


@dataclass(frozen=True, slots=True)
class AuditProvenance:
    """Reference to an external audit event/source without asserting approval."""

    event_id: str
    source_reference: str
    process_version: str
    recorded_at: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.event_id, "audit event_id")
        _require_identifier(self.source_reference, "audit source_reference")
        _require_identifier(self.process_version, "audit process_version")
        if self.recorded_at is not None:
            _require_text(self.recorded_at, "audit recorded_at")


@dataclass(frozen=True, slots=True)
class PartitionDefinition:
    """One named partition identity and its fixed role."""

    partition_id: str
    role: PartitionRole

    def __post_init__(self) -> None:
        _require_identifier(self.partition_id, "partition_id")
        if not isinstance(self.role, PartitionRole):
            raise TypeError("role must be a PartitionRole.")


@dataclass(frozen=True, slots=True)
class ReceiptManifestEntry:
    """One de-identified reference-receipt membership assignment."""

    receipt_id: str
    partition_id: str
    membership_provenance_reference: str

    def __post_init__(self) -> None:
        _require_identifier(self.receipt_id, "receipt_id")
        _require_identifier(self.partition_id, "partition_id")
        _require_identifier(
            self.membership_provenance_reference,
            "membership_provenance_reference",
        )


@dataclass(frozen=True, slots=True)
class RelatedRecordGroup:
    """A declared group whose transitive closure cannot cross partitions."""

    group_id: str
    kind: RelatedGroupKind
    receipt_ids: tuple[str, ...]
    provenance_reference: str

    def __post_init__(self) -> None:
        _require_identifier(self.group_id, "group_id")
        if not isinstance(self.kind, RelatedGroupKind):
            raise TypeError("kind must be a RelatedGroupKind.")
        _require_unique_identifiers(self.receipt_ids, "group receipt_ids")
        if not self.receipt_ids:
            raise ValueError("A related-record group requires at least one receipt.")
        _require_identifier(self.provenance_reference, "group provenance_reference")


@dataclass(frozen=True, slots=True)
class CohortDefinition:
    """Declared cohort membership; this record does not approve the cohort."""

    cohort_id: str
    kind: CohortKind
    dataset_id: str
    receipt_ids: tuple[str, ...]
    definition_reference: str

    def __post_init__(self) -> None:
        _require_identifier(self.cohort_id, "cohort_id")
        if not isinstance(self.kind, CohortKind):
            raise TypeError("kind must be a CohortKind.")
        _require_identifier(self.dataset_id, "cohort dataset_id")
        _require_unique_identifiers(self.receipt_ids, "cohort receipt_ids")
        _require_identifier(self.definition_reference, "cohort definition_reference")


@dataclass(frozen=True, slots=True)
class AlignmentDevelopmentSubset:
    """Training-only subset used to develop and freeze line alignment."""

    subset_id: str
    receipt_ids: tuple[str, ...]
    selection_provenance_reference: str

    def __post_init__(self) -> None:
        _require_identifier(self.subset_id, "alignment subset_id")
        _require_unique_identifiers(
            self.receipt_ids, "alignment subset receipt_ids"
        )
        if not self.receipt_ids:
            raise ValueError("The alignment-development subset cannot be empty.")
        _require_identifier(
            self.selection_provenance_reference,
            "alignment selection_provenance_reference",
        )


@dataclass(frozen=True, slots=True)
class FittingExclusionEvidence:
    """Declared evidence that alignment receipts were excluded from fitting."""

    subset_id: str
    excluded_receipt_ids: tuple[str, ...]
    fit_manifest_reference: str
    state: FittingExclusionEvidenceState
    verification_reference: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.subset_id, "fitting exclusion subset_id")
        _require_unique_identifiers(
            self.excluded_receipt_ids, "fitting excluded_receipt_ids"
        )
        if not self.excluded_receipt_ids:
            raise ValueError("Fitting exclusion evidence requires receipt IDs.")
        _require_identifier(self.fit_manifest_reference, "fit_manifest_reference")
        if not isinstance(self.state, FittingExclusionEvidenceState):
            raise TypeError("state must be a FittingExclusionEvidenceState.")
        if self.state is FittingExclusionEvidenceState.INDEPENDENTLY_VERIFIED:
            _require_identifier(
                self.verification_reference, "fitting verification_reference"
            )
        elif self.verification_reference is not None:
            raise ValueError(
                "Declared fitting exclusion evidence cannot claim verification."
            )


@dataclass(frozen=True, slots=True)
class DigestVerificationEvidence:
    """External evidence for an independently verified declared digest."""

    verifier_reference: str
    verification_reference: str
    verification_timestamp: str

    def __post_init__(self) -> None:
        _require_identifier(self.verifier_reference, "verifier_reference")
        _require_identifier(self.verification_reference, "verification_reference")
        _require_text(self.verification_timestamp, "verification_timestamp")


@dataclass(frozen=True, slots=True)
class DigestEvidence:
    """Unavailable, declared, or independently verified digest evidence."""

    evidence_id: str
    subject_reference: str
    state: DigestEvidenceState
    algorithm: str | None = None
    digest_value: str | None = None
    verification: DigestVerificationEvidence | None = None
    unavailable_reason: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.evidence_id, "digest evidence_id")
        _require_identifier(self.subject_reference, "digest subject_reference")
        if not isinstance(self.state, DigestEvidenceState):
            raise TypeError("state must be a DigestEvidenceState.")

        if self.state is DigestEvidenceState.UNAVAILABLE:
            if (
                self.algorithm is not None
                or self.digest_value is not None
                or self.verification is not None
            ):
                raise ValueError(
                    "Unavailable digest evidence cannot contain digest or verification data."
                )
            _require_text(self.unavailable_reason, "digest unavailable_reason")
            return

        _require_identifier(self.algorithm, "digest algorithm")
        _require_text(self.digest_value, "digest_value")
        if self.unavailable_reason is not None:
            raise ValueError("Present digest evidence cannot have unavailable_reason.")
        if self.state is DigestEvidenceState.VERIFIED_DIGEST:
            if not isinstance(self.verification, DigestVerificationEvidence):
                raise ValueError(
                    "VERIFIED_DIGEST requires independent verification evidence."
                )
        elif self.verification is not None:
            raise ValueError(
                "A declared digest must not be represented as independently verified."
            )


@dataclass(frozen=True, slots=True)
class EvaluationManifest:
    """Provisional offline Tier A membership and leakage-control manifest."""

    manifest_id: str
    manifest_version: str
    dataset_id: str
    dataset_version: str
    dataset_tier: DatasetTier
    annotation_version: str
    partitions: tuple[PartitionDefinition, ...]
    receipts: tuple[ReceiptManifestEntry, ...]
    related_groups: tuple[RelatedRecordGroup, ...]
    cohorts: tuple[CohortDefinition, ...]
    provenance: AuditProvenance
    alignment_subset: AlignmentDevelopmentSubset | None = None
    fitting_exclusion_evidence: FittingExclusionEvidence | None = None
    digest_evidence: tuple[DigestEvidence, ...] = ()
    grouping_policy_reference: str | None = None
    eligibility_policy_reference: str | None = None
    schema_version: str = MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_identifier(self.manifest_id, "manifest_id")
        _require_identifier(self.manifest_version, "manifest_version")
        _require_identifier(self.dataset_id, "dataset_id")
        _require_identifier(self.dataset_version, "dataset_version")
        if not isinstance(self.dataset_tier, DatasetTier):
            raise TypeError("dataset_tier must be a DatasetTier.")
        _require_identifier(self.annotation_version, "annotation_version")
        for value, name, expected in (
            (self.partitions, "partitions", PartitionDefinition),
            (self.receipts, "receipts", ReceiptManifestEntry),
            (self.related_groups, "related_groups", RelatedRecordGroup),
            (self.cohorts, "cohorts", CohortDefinition),
            (self.digest_evidence, "digest_evidence", DigestEvidence),
        ):
            _require_tuple(value, name)
            if any(not isinstance(item, expected) for item in value):
                raise TypeError(f"{name} contains an invalid record.")
        if not isinstance(self.provenance, AuditProvenance):
            raise TypeError("provenance must be AuditProvenance.")
        if self.alignment_subset is not None and not isinstance(
            self.alignment_subset, AlignmentDevelopmentSubset
        ):
            raise TypeError("alignment_subset has an invalid type.")
        if self.fitting_exclusion_evidence is not None and not isinstance(
            self.fitting_exclusion_evidence, FittingExclusionEvidence
        ):
            raise TypeError("fitting_exclusion_evidence has an invalid type.")
        _require_optional_identifier(
            self.grouping_policy_reference, "grouping_policy_reference"
        )
        _require_optional_identifier(
            self.eligibility_policy_reference, "eligibility_policy_reference"
        )
        if self.schema_version != MANIFEST_SCHEMA_VERSION:
            raise ValueError(
                f"This module implements manifest schema {MANIFEST_SCHEMA_VERSION}."
            )

        from evaluation.manifest_validation import validate_evaluation_manifest

        validate_evaluation_manifest(self)


def serialize_evaluation_manifest(manifest: EvaluationManifest) -> str:
    """Validate and serialize a manifest in canonical identifier order."""

    from evaluation.manifest_validation import validate_evaluation_manifest

    validate_evaluation_manifest(manifest)
    payload = to_json_compatible(manifest)
    for key, identity_key in (
        ("partitions", "partition_id"),
        ("receipts", "receipt_id"),
        ("related_groups", "group_id"),
        ("cohorts", "cohort_id"),
        ("digest_evidence", "evidence_id"),
    ):
        payload[key] = sorted(payload[key], key=lambda item: item[identity_key])
    for group in payload["related_groups"]:
        group["receipt_ids"] = sorted(group["receipt_ids"])
    for cohort in payload["cohorts"]:
        cohort["receipt_ids"] = sorted(cohort["receipt_ids"])
    if payload["alignment_subset"] is not None:
        payload["alignment_subset"]["receipt_ids"] = sorted(
            payload["alignment_subset"]["receipt_ids"]
        )
    if payload["fitting_exclusion_evidence"] is not None:
        evidence = payload["fitting_exclusion_evidence"]
        evidence["excluded_receipt_ids"] = sorted(evidence["excluded_receipt_ids"])
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
