"""Synthetic-only tests for the offline Tier A evaluation manifest V0."""

from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError, replace

from evaluation.manifest_schema import (
    AlignmentDevelopmentSubset,
    AuditProvenance,
    CohortDefinition,
    CohortKind,
    DatasetTier,
    DigestEvidence,
    DigestEvidenceState,
    DigestVerificationEvidence,
    EvaluationManifest,
    FittingExclusionEvidence,
    FittingExclusionEvidenceState,
    PartitionDefinition,
    PartitionRole,
    ReceiptManifestEntry,
    RelatedGroupKind,
    RelatedRecordGroup,
    serialize_evaluation_manifest,
)
from evaluation.manifest_validation import (
    ManifestValidationError,
    related_receipt_components,
    validate_evaluation_manifest,
)


def synthetic_audit() -> AuditProvenance:
    return AuditProvenance(
        event_id="synthetic-manifest-event",
        source_reference="synthetic-manifest-source",
        process_version="synthetic-process-v0",
    )


def synthetic_manifest() -> EvaluationManifest:
    receipt_ids = ("receipt-train", "receipt-validation", "receipt-held-out")
    return EvaluationManifest(
        manifest_id="synthetic-manifest-v0",
        manifest_version="0",
        dataset_id="synthetic-tier-a",
        dataset_version="synthetic-dataset-v0",
        dataset_tier=DatasetTier.TIER_A,
        annotation_version="synthetic-annotation-v0",
        partitions=(
            PartitionDefinition("partition-training", PartitionRole.TRAINING),
            PartitionDefinition("partition-validation", PartitionRole.VALIDATION),
            PartitionDefinition("partition-held-out", PartitionRole.HELD_OUT_TEST),
        ),
        receipts=(
            ReceiptManifestEntry(
                "receipt-train",
                "partition-training",
                "synthetic-membership-train",
            ),
            ReceiptManifestEntry(
                "receipt-validation",
                "partition-validation",
                "synthetic-membership-validation",
            ),
            ReceiptManifestEntry(
                "receipt-held-out",
                "partition-held-out",
                "synthetic-membership-held-out",
            ),
        ),
        related_groups=(
            *(
                RelatedRecordGroup(
                    group_id=f"transaction-{receipt_id}",
                    kind=RelatedGroupKind.TRANSACTION,
                    receipt_ids=(receipt_id,),
                    provenance_reference=f"synthetic-transaction-{receipt_id}",
                )
                for receipt_id in receipt_ids
            ),
            *(
                RelatedRecordGroup(
                    group_id=f"contributor-{receipt_id}",
                    kind=RelatedGroupKind.CONTRIBUTOR,
                    receipt_ids=(receipt_id,),
                    provenance_reference=f"synthetic-contributor-{receipt_id}",
                )
                for receipt_id in receipt_ids
            ),
        ),
        cohorts=(
            CohortDefinition(
                cohort_id="cohort-primary",
                kind=CohortKind.PRIMARY_TIER_A,
                dataset_id="synthetic-tier-a",
                receipt_ids=receipt_ids,
                definition_reference="synthetic-primary-definition",
            ),
            CohortDefinition(
                cohort_id="cohort-unseen-retailer",
                kind=CohortKind.UNSEEN_RETAILER,
                dataset_id="synthetic-tier-a",
                receipt_ids=("receipt-held-out",),
                definition_reference="synthetic-unseen-definition",
            ),
            CohortDefinition(
                cohort_id="cohort-branch-generalization",
                kind=CohortKind.BRANCH_GENERALIZATION,
                dataset_id="synthetic-tier-a",
                receipt_ids=(),
                definition_reference="synthetic-branch-definition",
            ),
        ),
        alignment_subset=AlignmentDevelopmentSubset(
            subset_id="alignment-development-v0",
            receipt_ids=("receipt-train",),
            selection_provenance_reference="synthetic-alignment-selection",
        ),
        fitting_exclusion_evidence=FittingExclusionEvidence(
            subset_id="alignment-development-v0",
            excluded_receipt_ids=("receipt-train",),
            fit_manifest_reference="synthetic-fit-manifest",
            state=FittingExclusionEvidenceState.DECLARED,
        ),
        digest_evidence=(
            DigestEvidence(
                evidence_id="digest-dataset",
                subject_reference="synthetic-dataset-subject",
                state=DigestEvidenceState.DECLARED_DIGEST,
                algorithm="sha256",
                digest_value="synthetic-declared-digest",
            ),
        ),
        provenance=synthetic_audit(),
        grouping_policy_reference=None,
        eligibility_policy_reference=None,
    )


class EvaluationManifestTests(unittest.TestCase):
    def test_valid_manifest_preserves_partition_cohort_and_group_identities(self) -> None:
        manifest = synthetic_manifest()

        validate_evaluation_manifest(manifest)
        self.assertEqual(set(PartitionRole), {item.role for item in manifest.partitions})
        self.assertEqual(
            {
                CohortKind.PRIMARY_TIER_A,
                CohortKind.UNSEEN_RETAILER,
                CohortKind.BRANCH_GENERALIZATION,
            },
            {item.kind for item in manifest.cohorts},
        )
        self.assertTrue(all(not hasattr(item, "reference_fields") for item in manifest.receipts))
        self.assertFalse(hasattr(manifest, "held_out_ready"))

    def test_invalid_manifest_identity_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "partition_id"):
            PartitionDefinition("", PartitionRole.TRAINING)

    def test_duplicate_receipt_membership_is_rejected(self) -> None:
        manifest = synthetic_manifest()
        duplicate = replace(
            manifest.receipts[0],
            membership_provenance_reference="synthetic-duplicate-membership",
        )
        with self.assertRaisesRegex(ManifestValidationError, "Duplicate receipt"):
            replace(manifest, receipts=(*manifest.receipts, duplicate))

    def test_conflicting_partition_assignment_is_rejected(self) -> None:
        manifest = synthetic_manifest()
        conflict = replace(
            manifest.receipts[0],
            partition_id="partition-validation",
            membership_provenance_reference="synthetic-conflicting-membership",
        )
        with self.assertRaisesRegex(ManifestValidationError, "conflicting partition"):
            replace(manifest, receipts=(*manifest.receipts, conflict))

    def test_direct_contributor_leakage_is_rejected(self) -> None:
        manifest = synthetic_manifest()
        groups = tuple(
            group
            for group in manifest.related_groups
            if not (
                group.kind is RelatedGroupKind.CONTRIBUTOR
                and set(group.receipt_ids)
                <= {"receipt-train", "receipt-validation"}
            )
        )
        leaking = RelatedRecordGroup(
            group_id="contributor-leaking",
            kind=RelatedGroupKind.CONTRIBUTOR,
            receipt_ids=("receipt-train", "receipt-validation"),
            provenance_reference="synthetic-contributor-leak",
        )

        with self.assertRaisesRegex(ManifestValidationError, "spans partitions"):
            replace(manifest, related_groups=(*groups, leaking))

    def test_direct_duplicate_leakage_is_rejected(self) -> None:
        manifest = synthetic_manifest()
        leaking = RelatedRecordGroup(
            group_id="exact-duplicate-leaking",
            kind=RelatedGroupKind.EXACT_DUPLICATE,
            receipt_ids=("receipt-train", "receipt-held-out"),
            provenance_reference="synthetic-exact-duplicate-leak",
        )
        with self.assertRaisesRegex(ManifestValidationError, "spans partitions"):
            replace(manifest, related_groups=(*manifest.related_groups, leaking))

    def test_transitive_related_group_leakage_is_rejected(self) -> None:
        manifest = synthetic_manifest()
        non_contributor_groups = tuple(
            group
            for group in manifest.related_groups
            if group.kind is not RelatedGroupKind.CONTRIBUTOR
        )
        links = (
            RelatedRecordGroup(
                group_id="contributor-transitive-link",
                kind=RelatedGroupKind.CONTRIBUTOR,
                receipt_ids=("receipt-train", "receipt-validation"),
                provenance_reference="synthetic-contributor-transitive-link",
            ),
            RelatedRecordGroup(
                group_id="contributor-held-out",
                kind=RelatedGroupKind.CONTRIBUTOR,
                receipt_ids=("receipt-held-out",),
                provenance_reference="synthetic-contributor-held-out",
            ),
            RelatedRecordGroup(
                group_id="near-duplicate-link",
                kind=RelatedGroupKind.NEAR_DUPLICATE,
                receipt_ids=("receipt-validation", "receipt-held-out"),
                provenance_reference="synthetic-near-link",
            ),
        )
        with self.assertRaisesRegex(ManifestValidationError, "connected related-record"):
            replace(manifest, related_groups=(*non_contributor_groups, *links))

    def test_components_are_canonical_and_transitive(self) -> None:
        manifest = synthetic_manifest()
        same_partition_link = RelatedRecordGroup(
            group_id="declared-self-related",
            kind=RelatedGroupKind.RELATED_RECORD,
            receipt_ids=("receipt-train",),
            provenance_reference="synthetic-related-link",
        )
        linked = replace(
            manifest, related_groups=(*manifest.related_groups, same_partition_link)
        )
        self.assertEqual(
            (
                ("receipt-held-out",),
                ("receipt-train",),
                ("receipt-validation",),
            ),
            related_receipt_components(linked),
        )

    def test_alignment_development_receipt_must_be_training(self) -> None:
        manifest = synthetic_manifest()
        subset = replace(
            manifest.alignment_subset,
            receipt_ids=("receipt-validation",),
        )
        evidence = replace(
            manifest.fitting_exclusion_evidence,
            excluded_receipt_ids=("receipt-validation",),
        )
        with self.assertRaisesRegex(ManifestValidationError, "subset of training"):
            replace(
                manifest,
                alignment_subset=subset,
                fitting_exclusion_evidence=evidence,
            )

    def test_alignment_subset_requires_fitting_exclusion_evidence(self) -> None:
        with self.assertRaisesRegex(ManifestValidationError, "lacks fitting-exclusion"):
            replace(synthetic_manifest(), fitting_exclusion_evidence=None)

    def test_declared_fitting_exclusion_does_not_claim_manifest_was_checked(self) -> None:
        evidence = synthetic_manifest().fitting_exclusion_evidence
        assert evidence is not None
        self.assertIs(evidence.state, FittingExclusionEvidenceState.DECLARED)
        self.assertIsNone(evidence.verification_reference)
        self.assertFalse(hasattr(evidence, "fit_manifest_checked"))

    def test_contradictory_cohort_dataset_is_rejected(self) -> None:
        manifest = synthetic_manifest()
        wrong = replace(manifest.cohorts[1], dataset_id="another-dataset")
        with self.assertRaisesRegex(ManifestValidationError, "another dataset"):
            replace(manifest, cohorts=(manifest.cohorts[0], wrong, manifest.cohorts[2]))

    def test_duplicate_cohort_kind_is_rejected(self) -> None:
        manifest = synthetic_manifest()
        duplicate_kind = replace(
            manifest.cohorts[1],
            cohort_id="cohort-unseen-second",
        )
        with self.assertRaisesRegex(ManifestValidationError, "Each cohort kind"):
            replace(manifest, cohorts=(*manifest.cohorts, duplicate_kind))

    def test_all_three_cohort_identities_are_required_but_not_approved(self) -> None:
        manifest = synthetic_manifest()
        with self.assertRaisesRegex(ManifestValidationError, "separate primary"):
            replace(manifest, cohorts=manifest.cohorts[:2])
        self.assertTrue(all(not hasattr(item, "approved") for item in manifest.cohorts))

    def test_unverified_digest_cannot_be_presented_as_verified(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires independent verification"):
            DigestEvidence(
                evidence_id="digest-invalid-verified",
                subject_reference="synthetic-subject",
                state=DigestEvidenceState.VERIFIED_DIGEST,
                algorithm="sha256",
                digest_value="bare-hash-string",
            )

    def test_declared_digest_is_not_authenticated(self) -> None:
        digest = synthetic_manifest().digest_evidence[0]
        self.assertIs(digest.state, DigestEvidenceState.DECLARED_DIGEST)
        self.assertIsNone(digest.verification)

    def test_unavailable_declared_and_verified_digest_states_are_distinct(self) -> None:
        unavailable = DigestEvidence(
            evidence_id="digest-unavailable",
            subject_reference="synthetic-unavailable-subject",
            state=DigestEvidenceState.UNAVAILABLE,
            unavailable_reason="No authentic digest evidence was supplied.",
        )
        declared = synthetic_manifest().digest_evidence[0]
        verified = DigestEvidence(
            evidence_id="digest-verified",
            subject_reference="synthetic-verified-subject",
            state=DigestEvidenceState.VERIFIED_DIGEST,
            algorithm="sha256",
            digest_value="synthetic-verified-digest",
            verification=DigestVerificationEvidence(
                verifier_reference="synthetic-independent-verifier",
                verification_reference="synthetic-verification-record",
                verification_timestamp="SYNTHETIC_TIMESTAMP_NOT_REAL",
            ),
        )

        self.assertEqual(
            {
                DigestEvidenceState.UNAVAILABLE,
                DigestEvidenceState.DECLARED_DIGEST,
                DigestEvidenceState.VERIFIED_DIGEST,
            },
            {unavailable.state, declared.state, verified.state},
        )

    def test_serialization_is_canonical_and_deterministic(self) -> None:
        manifest = synthetic_manifest()
        first = serialize_evaluation_manifest(manifest)
        second = serialize_evaluation_manifest(manifest)
        payload = json.loads(first)

        self.assertEqual(first, second)
        self.assertEqual(
            sorted(item["receipt_id"] for item in payload["receipts"]),
            [item["receipt_id"] for item in payload["receipts"]],
        )

    def test_manifest_records_are_frozen_and_slotted(self) -> None:
        manifest = synthetic_manifest()
        self.assertFalse(hasattr(manifest, "__dict__"))
        with self.assertRaises(FrozenInstanceError):
            manifest.dataset_id = "changed"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
